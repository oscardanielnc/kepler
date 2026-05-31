"""
E23 — A2 (paso 0): ¿el ORDER-BOOK IMBALANCE es ORTOGONAL a los 7 sleeves, o redundante?
(2026-05-31). Liquidaciones quedó sin histórico gratis (Binance retiró allForceOrders +
liquidationSnapshot). bookDepth SÍ está en data.binance.vision (2023+), misma infra que metrics.

Chequeo BARATO (estilo e22): antes de bajar bookDepth de los 32 símbolos × 3.4a (~11GB), medir
sobre un subconjunto líquido + ventana contigua si la señal de profundidad es ortogonal a los 7
sleeves (sobre todo a taker_flow, que también es microestructura/flujo). Si corr alta → redundante,
parar. Si baja + edge>0 → vale el download completo + walk-forward.

bookDepth: snapshot cada 30s, notional CUMULATIVO de bids (%neg) y asks (%pos) a ±1..±5% del mid.
  imbalance_k = mean_t (bid_notional@-k − ask_notional@+k)/(bid+ask)    (cross-seccional, β-neutral)

python -m research.e23_orderbook_check [START END N_SYMS]
"""
from __future__ import annotations
import os, sys, io, zipfile, time
from datetime import date, timedelta, datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"
CACHE = os.path.join(config.DATA_DIR, "bookdepth_daily"); os.makedirs(CACHE, exist_ok=True)
# Subconjunto líquido (todos con historia larga de klines → en load()).
SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"]
_sess = requests.Session()


def _imb_day(sym, d):
    """Descarga un día de bookDepth y devuelve (imb1, imb2, imb5, n_snaps) o None."""
    url = f"{BASE}/{sym}/{sym}-bookDepth-{d.isoformat()}.zip"
    try:
        r = _sess.get(url, timeout=60)
        if r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        df = pd.read_csv(z.open(z.namelist()[0]))
        piv = df.pivot_table(index="timestamp", columns="percentage", values="notional", aggfunc="last")
        def imb(k):
            b, a = piv.get(-k), piv.get(k)
            if b is None or a is None: return np.nan
            return float(((b - a) / (b + a)).mean())
        return (imb(1), imb(2), imb(5), len(piv))
    except Exception:
        return None


def load_symbol(sym, days):
    """Cachea imbalance diario por símbolo. Devuelve DataFrame [imb1,imb2,imb5] indexado por fecha."""
    out = os.path.join(CACHE, f"{sym}.parquet")
    have = pd.read_parquet(out) if os.path.exists(out) else pd.DataFrame()
    have_dates = set(have.index) if len(have) else set()
    todo = [d for d in days if pd.Timestamp(d) not in have_dates]
    if todo:
        rows = {}
        with ThreadPoolExecutor(max_workers=16) as ex:
            for d, v in zip(todo, ex.map(lambda dd: _imb_day(sym, dd), todo)):
                if v is not None:
                    rows[pd.Timestamp(d)] = v
        if rows:
            add = pd.DataFrame.from_dict(rows, orient="index",
                                         columns=["imb1", "imb2", "imb5", "snaps"])
            have = pd.concat([have, add]).sort_index()
            have = have[~have.index.duplicated()]
            have.to_parquet(out)
    return have


def build_panels(C, syms, days):
    """Panels diarios de imbalance, reindexados al índice horario de C (ffill dentro del día)."""
    daily = {}
    for i, s in enumerate(syms, 1):
        df = load_symbol(s, days)
        n = len(df)
        print(f"  [{i:2d}/{len(syms)}] {s:10s} {n} días con book", flush=True)
        if n:
            daily[s] = df
    fields = ["imb1", "imb2", "imb5"]
    panels = {}
    cidx_date = pd.Index(C.index.tz_convert("UTC").normalize())
    for f in fields:
        wide = pd.DataFrame({s: daily[s][f] for s in daily})
        wide.index = pd.to_datetime(wide.index, utc=True)
        # ANTI-LOOK-AHEAD: el imbalance de un día es la MEDIA de TODO el día (incl. horas futuras
        # dentro del día). Rezagar 1 día → en cualquier barra del día D el score = imbalance del
        # día D-1 ya COMPLETO. Sin esto, hold=24 solapa con el propio día e infla el Sharpe.
        wide = wide.shift(1)
        aligned = wide.reindex(pd.to_datetime(sorted(set(cidx_date)), utc=True))
        aligned = aligned.reindex(cidx_date).set_axis(C.index)
        panels[f] = aligned.reindex(columns=C.columns)
    return panels, sorted(daily.keys())


def sh_isoos(r):
    r = r.dropna(); cut = int(len(r) * 0.6)
    f = lambda x: x.mean() / x.std() * np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0.0
    return f(r), f(r.iloc[:cut]), f(r.iloc[cut:])


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return (m.get("ann", float("nan")), L)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    a = sys.argv
    start = a[1] if len(a) > 1 else "2024-01-01"
    end = a[2] if len(a) > 2 else "2024-09-30"
    nsyms = int(a[3]) if len(a) > 3 else len(SYMS)
    syms = SYMS[:nsyms]
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]
    print(f"E23 — A2 paso 0: ¿order-book imbalance ⟂ 7 sleeves?")
    print(f"Ventana {start}→{end} ({len(days)}d) · {len(syms)} símbolos líquidos\n")

    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    print("Descargando/cacheando bookDepth (daily imbalance)...")
    t0 = time.time()
    panels, ok_syms = build_panels(C, syms, days)
    print(f"  listo en {time.time()-t0:.0f}s · {len(ok_syms)} símbolos con datos\n")

    cov = panels["imb1"].notna().any(axis=1)
    if cov.sum() == 0:
        print("Sin datos de bookDepth en la ventana. Abortando."); return
    first, last = C.index[cov][0], C.index[cov][-1]
    print(f"Overlap book: {first.date()} → {last.date()} ({cov.sum()} barras 1h)\n")

    # --- 7 sleeves base (toda su historia; se compara en el overlap) ---
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    P = load_panel(["volume", "taker_buy_volume"], C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    base_df = pd.concat(base, axis=1); base_df.columns = list(base); base_df = base_df.dropna()

    over = base_df[(base_df.index >= first) & (base_df.index <= last)]
    combo_over = (over * vol_parity_weights(over)).sum(axis=1)
    ann_ov, L_ov = anchored(combo_over)
    print(f"BASELINE 7 sleeves (overlap): Sharpe {metrics(combo_over)['sharpe']:.2f} · "
          f"@−10% {L_ov:.2f}x → {ann_ov/12:.2f}%/mes  ← comparar contra esto\n")

    # --- candidatos: imbalance a varios anchos y horizontes, + cambio (flujo) ---
    cands = {}
    for f in ["imb1", "imb2", "imb5"]:
        for hold in [24, 72, 120]:
            cands[f"{f}_h{hold}"] = (panels[f], hold)
        cands[f"{f}chg_h120"] = (panels[f].diff(24), 120)  # cambio diario del imbalance

    # ORIENTACIÓN del signo: el alpha puede ser momentum (+) o contrarian (−). Se elige la
    # dirección EN IS (sin look-ahead) y se confirma en OOS. Sleeve oriented = sign·s_ret.
    print("CANDIDATOS (oriented: dir elegida en IS · Sh/IS/OOS · corr máx vs 7 · Δ%/mes anclado):")
    print(f"  {'cand':14s} {'dir':>4s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>13s} "
          f"{'pasa':>5s} {'Δ%/mes':>7s}")
    best = []
    for name, (score, hold) in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
        except Exception as e:
            print(f"  {name:14s} ERROR {str(e)[:35]}"); continue
        s_ret = s_ret[(s_ret.index >= first) & (s_ret.index <= last)]
        if s_ret.dropna().shape[0] < 60 or s_ret.std() == 0:
            print(f"  {name:14s} insuf. datos ({s_ret.dropna().shape[0]})"); continue
        # elegir signo en IS (primer 60%), aplicar a toda la serie
        cut = int(s_ret.dropna().shape[0] * 0.6)
        sign = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        s_or = (s_ret * sign)
        j = pd.concat({**base, name: s_or}, axis=1); j.columns = list(base) + [name]; j = j.dropna()
        if len(j) < 60:
            print(f"  {name:14s} overlap corto ({len(j)})"); continue
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        sh, i, o = sh_isoos(j[name])
        # robusto = corr baja, IS>0 por construcción, y OOS MANTIENE el signo (no es overfit IS)
        passes = (o > 0.10 and cmax < 0.35)
        combo = (j * vol_parity_weights(j)).sum(axis=1)
        ann, _ = anchored(combo); dmes = (ann - ann_ov) / 12
        print(f"  {name:14s} {'+' if sign>0 else '−':>4s} {sh:6.2f} {i:6.2f} {o:6.2f} {cmax:6.2f} "
              f"{cwho:>13s} {'SÍ' if passes else 'no':>5s} {dmes:+7.2f}")
        if passes:
            best.append((name, sh, o, cmax, dmes))

    print("\nVEREDICTO (chequeo barato, ventana corta — NO es walk-forward):")
    if not best:
        print("  Ningún ancho/horizonte mantiene el edge OOS (>0.10) con corr<0.35. Sin look-ahead,")
        print("  el order-book imbalance NO aporta sobre los 7 sleeves en este subconjunto.")
        print("  NO bajar los 32 símbolos sin una variante mejor.")
    else:
        best.sort(key=lambda b: -b[4])
        print(f"  {len(best)} variante(s) con OOS>0.10 y corr<0.35 (mejores por Δ%/mes):")
        for n, sh, o, cm, dm in best[:5]:
            print(f"    {n:14s} Sh {sh:+.2f} · OOS {o:+.2f} · corr {cm:.2f} · Δ {dm:+.2f}%/mes")
        print("  PROMETEDOR → vale el download completo (32 símbolos × 3.4a) + walk-forward + estrés.")
        print("  (Δ%/mes de ventana corta NO es concluyente; orienta la decisión de invertir el download.)")
    print("\n  ⚠️ Caveats: ventana 2024 (1 régimen) · cross-section 12 símbolos · señal rezagada 1d ·")
    print("     turnover/costos reales NO modelados (xs_sleeve cobra solo maker plano).")


if __name__ == "__main__":
    main()
