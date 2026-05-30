"""
E16f — Sleeve #8 desde FUENTE NUEVA: metrics de Binance (Open Interest + long/short ratios).
(2026-05-30). Continúa e16/b/c/d/e. La veta OHLCV está exprimida (sleeves #6 taker_flow, #7
hl_position). Esta es data de POSICIONAMIENTO, genuinamente ortogonal al precio.

Fuente: data.binance.vision/.../futures/um/{monthly,daily}/metrics/SYMBOL/...
Columnas: create_time, sum_open_interest, sum_open_interest_value,
          count_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio
Granularidad 5min → resample a 1h. Historia desde ~2023-01 (~3.4a; MENOS que los 4.4a de klines).

⚠️ CAVEAT: metrics empieza en 2023; el combinado con este sleeve se evalúa sobre el OVERLAP
(2023+). Reportamos el sleeve solo Y el combinado en su ventana común, sin mezclar peras y manzanas.

Candidatos (cross-seccional, β-neutral, criterio del ancla = Δretorno a maxDD −10%):
  - oi_mom_Nd      momentum del open interest (Δlog OI) → dinero nuevo entrando
  - oi_px_div      Δlog OI − ret_precio → OI sube con precio cayendo = shorts (bajista)
  - ls_crowd_rev   −z(count_long_short_ratio) → contrarian a la masa retail
  - toptrader_fol  +z(count_toptrader_long_short_ratio) → seguir al smart money

python -m research.e16f_metrics_sleeves
"""
from __future__ import annotations
import os, sys, io, zipfile, time
from datetime import datetime, timezone, timedelta, date
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, MIN_BARS
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

BASE = "https://data.binance.vision/data/futures/um"
METRICS_DIR = os.path.join(config.DATA_DIR, "metrics")
MCOLS = ["sum_open_interest", "sum_open_interest_value",
         "count_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


def _zip(url, retries=3):
    for a in range(retries):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404: return None
            r.raise_for_status(); return r.content
        except Exception:
            if a == retries - 1: return None
    return None


def download_metrics(symbol, start="2023-01-01", force=False):
    """metrics SOLO existe como daily (un zip/día, granularidad 5min). NO hay monthly (404)."""
    os.makedirs(METRICS_DIR, exist_ok=True)
    out = os.path.join(METRICS_DIR, f"{symbol}.parquet")
    if os.path.exists(out) and not force:
        return -1
    parts = []; misses = 0
    d = date.fromisoformat(start); today = datetime.now(timezone.utc).date()
    while d < today:
        c = _zip(f"{BASE}/daily/metrics/{symbol}/{symbol}-metrics-{d.isoformat()}.zip")
        d += timedelta(days=1)
        if not c:
            misses += 1
            if misses > 60 and not parts:   # nunca empezó: símbolo sin metrics → cortar pronto
                break
            continue
        misses = 0
        try:
            z = zipfile.ZipFile(io.BytesIO(c)); name = z.namelist()[0]
            parts.append(pd.read_csv(z.open(name)))
        except Exception:
            continue
    if not parts:
        return 0
    df = pd.concat(parts, ignore_index=True)
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.drop_duplicates("create_time").sort_values("create_time").set_index("create_time")
    keep = [c for c in MCOLS if c in df.columns]
    for c in keep:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df[keep].to_parquet(out)
    return len(df)


def load_metric_panel(metric, C):
    """Panel de un campo de metrics, resampleado a 1h (last), alineado a C."""
    cols = {}
    for s in C.columns:
        p = os.path.join(METRICS_DIR, f"{s}.parquet")
        if not os.path.exists(p): continue
        df = pd.read_parquet(p)
        if metric not in df.columns: continue
        cols[s] = df[metric].resample("1h").last()
    P = pd.DataFrame(cols)
    return P.reindex(index=C.index, columns=C.columns)


def sh_isoos(r):
    r = r.dropna(); cut = int(len(r) * 0.6)
    f = lambda x: x.mean() / x.std() * np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0.0
    return f(r), f(r.iloc[:cut]), f(r.iloc[cut:])


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    return metrics(combo * L)["ann"], L


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E16f — Sleeve #8 desde metrics (Open Interest + long/short ratios)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)

    # --- descarga (cacheada) ---
    print("Descargando metrics (monthly, cacheado)...")
    got = 0
    for s in C.columns:
        n = download_metrics(s)
        if n != 0: got += 1
    print(f"  metrics disponibles para {got}/{len(C.columns)} símbolos\n")

    oi = load_metric_panel("sum_open_interest", C)
    lsr = load_metric_panel("count_long_short_ratio", C)
    ttr = load_metric_panel("count_toptrader_long_short_ratio", C)
    cov = oi.notna().any(axis=1)
    if cov.sum() == 0:
        print("Sin datos de metrics. Abortando."); return
    first = C.index[cov][0]
    print(f"Overlap metrics: {first.date()} → {C.index[-1].date()} "
          f"({cov.sum()} barras 1h de {len(C)})\n")

    # sleeves base (en TODA la historia para sus propias series)
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    P = load_panel(["volume", "taker_buy_volume"], C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)

    base_df = pd.concat(base, axis=1); base_df.columns = list(base.keys()); base_df = base_df.dropna()
    # baseline en TODA su historia (referencia) y en el OVERLAP (comparación justa)
    combo_all = (base_df * vol_parity_weights(base_df)).sum(axis=1)
    m_all = metrics(combo_all); ann_all, L_all = anchored(combo_all)
    over = base_df[base_df.index >= first]
    combo_over = (over * vol_parity_weights(over)).sum(axis=1)
    m_ov = metrics(combo_over); ann_ov, L_ov = anchored(combo_over)
    print(f"BASELINE 7 sleeves (historia completa): Sharpe {m_all['sharpe']:.2f} · @−10% {L_all:.2f}x "
          f"→ {ann_all/12:.2f}%/mes")
    print(f"BASELINE 7 sleeves (solo overlap 2023+): Sharpe {m_ov['sharpe']:.2f} · @−10% {L_ov:.2f}x "
          f"→ {ann_ov/12:.2f}%/mes  ← comparar contra esto\n")

    # candidatos
    loi = np.log(oi.replace(0, np.nan))
    cands = {
        "oi_mom_5d":    loi.diff(120),
        "oi_mom_14d":   loi.diff(336),
        "oi_px_div_5d": loi.diff(120) - ret.rolling(120).sum(),
        "ls_crowd_rev": -((lsr - lsr.rolling(336).mean()) / lsr.rolling(336).std()),
        "toptrader_fol": (ttr - ttr.rolling(336).mean()) / ttr.rolling(336).std(),
    }
    holds = {"oi_mom_5d": 120, "oi_mom_14d": 336, "oi_px_div_5d": 120, "ls_crowd_rev": 336, "toptrader_fol": 336}

    print("CANDIDATOS (Sh/IS/OOS sobre overlap · corr · Δretorno anclado vs baseline-overlap):")
    print(f"  {'sleeve':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>13s} "
          f"{'filtro':>7s} {'Δ%/mes':>7s}")
    keep = {}
    for name, score in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score.reindex(index=C.index, columns=C.columns), holds[name])
        except Exception as e:
            print(f"  {name:16s} ERROR: {str(e)[:40]}"); continue
        s_ret = s_ret[s_ret.index >= first]
        if s_ret.std() == 0 or s_ret.dropna().shape[0] < 200:
            print(f"  {name:16s} insuf. datos"); continue
        j = pd.concat({**{k: v for k, v in base.items()}, name: s_ret}, axis=1)
        j.columns = list(base.keys()) + [name]; j = j.dropna()
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        sh, i, o = sh_isoos(j[name])
        passes = (i > 0.10 and o > 0.10 and cmax < 0.35)
        combo = (j * vol_parity_weights(j)).sum(axis=1)
        ann, L = anchored(combo); dmes = (ann - ann_ov) / 12
        print(f"  {name:16s} {sh:6.2f} {i:6.2f} {o:6.2f} {cmax:6.2f} {cwho:>13s} "
              f"{'SÍ' if passes else 'no':>7s} {dmes:+7.2f}")
        if passes and dmes > 0.10:
            keep[name] = (s_ret, dmes)

    if not keep:
        print("\n→ VEREDICTO: ningún candidato de metrics mejora el retorno anclado de forma material.")
        print("  La data de positioning no aporta sobre los 7 sleeves actuales (en el overlap 2023+).")
        print("  NO se añade. Honesto: el OI/LS ratio puede estar ya implícito en taker_flow + trend.")
        return
    print(f"\nIMPLEMENTABLES: {list(keep)}")
    for n, (_, d) in keep.items():
        print(f"  {n}: +{d:.2f}%/mes al maxDD −10% (sobre overlap 2023+)")
    print("\n  ⚠️ Si se implementa: el combinado en prod se evalúa sobre 2023+ (no 2022+).")
    print("  REGLA DE ORO: estrés (e16c/e-style) + validar OOS antes de tocar engine.")


if __name__ == "__main__":
    main()
