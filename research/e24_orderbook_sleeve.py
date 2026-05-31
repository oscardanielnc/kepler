"""
E24 — Sleeve #8 candidato: ORDER-BOOK IMBALANCE (contrarian). Validación SERIA.
(2026-05-31). e23 (chequeo barato, 12 símbolos, 2023-24) lo encontró: ortogonal (corr 0.06–0.23)
y con edge que aguanta IS→OOS sobre DOS regímenes. Aquí el build completo + estrés antes de prod
(regla de oro), con los 32 símbolos del universo y la historia completa de bookDepth (2023+).

Señal (cross-seccional, β-neutral):
  imbalance_k = mean_t (bid_notional@-k% − ask_notional@+k%)/(bid+ask)   ·  k ∈ {1,2,5}
  score = −imbalance   (CONTRARIAN: bids gruesos → el precio los fade; e23 dio signo − estable)
  REZAGADO 1 día (la media diaria ve el día completo → sin lag habría look-ahead).

Tests (molde e16e):
  T1 ANCHO × HORIZONTE × COSTO (maker/taker): el edge debe vivir en un rango, no en un punto.
  T2 TURNOVER (×capital/año): la trampa del carry (199x). Holds cortos = turnover alto = costos.
  T3 SUB-PERÍODOS (cuartiles temporales): no concentrado en un tramo.
  T4 COMBINADO 7→8 al ancla −10%, evaluado en OVERLAP 2023+ (book no existe en 2022).
  ⚠️ bookDepth empieza 2023 → añadir este sleeve cegaría el ancla al bear 2022 (LUNA/FTX).
     Mismo dilema que frenó ls_crowd_rev (e16f). Se decide con T4 + criterio de Oscar.

python -m research.e24_orderbook_sleeve
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel,
                           _weights_from_score, DRIVER, BETA_W)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

CACHE = os.path.join(config.DATA_DIR, "bookdepth_daily")


def load_ob_panels(C, widths=(1, 2, 5)):
    """Panels de imbalance diario (k%), rezagados 1 día, alineados al índice horario de C."""
    fld = {f"imb{k}": k for k in widths}
    daily = {}
    for s in C.columns:
        p = os.path.join(CACHE, f"{s}.parquet")
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p)
        if not set(fld).issubset(df.columns):
            continue
        daily[s] = df
    cidx_date = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx_date)), utc=True)
    panels = {}
    for f in fld:
        wide = pd.DataFrame({s: daily[s][f] for s in daily})
        wide.index = pd.to_datetime(wide.index, utc=True)
        wide = wide.shift(1)                       # ANTI-LOOK-AHEAD (usar día D-1 completo)
        aligned = wide.reindex(uniq).reindex(cidx_date).set_axis(C.index)
        panels[f] = aligned.reindex(columns=C.columns)
    return panels, sorted(daily.keys())


def sleeve_with_turnover(C, ret, beta, score_df, hold):
    """Igual que engine.xs_sleeve pero devuelve también el turnover anualizado (×capital/año).
    NO toca el código de prod; replica el loop para poder medir la trampa del turnover (e18/e19)."""
    syms = [s for s in C.columns if s != DRIVER]
    R = ret[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold)); fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0; rets = []; ts = []; tot_turn = 0.0
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        port = float((w * fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h * float(fwd_d.iloc[t] or 0)
        turn = float((w - prev).abs().sum()) + abs(h - ph)
        rets.append(port - turn * config.MAKER_FEE); ts.append(C.index[t]); prev, ph = w, h
        tot_turn += turn
    series = pd.Series(rets, index=ts)
    years = (ts[-1] - ts[0]).days / 365.25 if len(ts) > 1 else 1.0
    ann_turn = tot_turn / years if years > 0 else 0.0
    daily_s = (1 + series).cumprod().resample("1D").last().ffill().pct_change().dropna()
    return daily_s, ann_turn


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n * a):int(n * b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), L, m.get("maxdd", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E24 — Sleeve #8 ORDER-BOOK IMBALANCE (contrarian) · validación seria\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h")

    panels, ok = load_ob_panels(C)
    print(f"bookDepth disponible para {len(ok)}/{C.shape[1]} símbolos del universo")
    cov = panels["imb1"].notna().any(axis=1)
    first, last = C.index[cov][0], C.index[cov][-1]
    print(f"Overlap book: {first.date()} → {last.date()} ({cov.sum()} barras 1h)\n")

    # --- 7 sleeves base (historia completa; se comparan en el overlap) ---
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
    combo0 = (over * vol_parity_weights(over)).sum(axis=1)
    m0 = metrics(combo0); ann0, L0, dd0 = anchored(combo0)
    print(f"BASELINE 7 sleeves (overlap 2023+): Sharpe {m0['sharpe']:.2f} · @−10% {L0:.2f}x → "
          f"{ann0/12:.2f}%/mes  ← comparar contra esto\n")

    # --- T1+T2: ANCHO × HORIZONTE × COSTO + turnover ---
    print("T1+T2 — ANCHO × HORIZONTE (Sh/IS/OOS overlap · corr · turnover/año · combo@−10% maker/taker):")
    print(f"  {'cand':12s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} "
          f"{'turn/a':>7s} {'Δmk':>6s} {'Δtk':>6s}")
    store = {}
    for k in (1, 2, 5):
        pan = panels[f"imb{k}"]
        score = -pan                                  # CONTRARIAN
        for days in (1, 2, 3, 5, 7):
            hold = days * 24
            s_ret, turn = sleeve_with_turnover(C, ret, beta, score, hold)
            s_ret = s_ret[(s_ret.index >= first) & (s_ret.index <= last)]
            if s_ret.dropna().shape[0] < 120:
                continue
            name = f"imb{k}_{days}d"
            j = pd.concat({**base, name: s_ret}, axis=1); j.columns = list(base) + [name]; j = j.dropna()
            corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
            combo = (j * vol_parity_weights(j)).sum(axis=1)
            ann_mk, _, _ = anchored(combo)
            # taker bracket: penaliza el extra de fee por turnover (proxy e16e)
            s_tk = j[name] - (config.TAKER_FEE - config.MAKER_FEE) * turn / 365
            jt = j.copy(); jt[name] = s_tk
            ann_tk, _, _ = anchored((jt * vol_parity_weights(jt)).sum(axis=1))
            print(f"  {name:12s} {sh(j[name]):6.2f} {sh(seg(j[name],0,.6)):6.2f} {sh(seg(j[name],.6,1)):6.2f} "
                  f"{cmax:6.2f} {cwho:>12s} {turn:7.1f} {(ann_mk-ann0)/12:+6.2f} {(ann_tk-ann0)/12:+6.2f}")
            store[name] = (s_ret, turn, cmax)

    # --- elegir el mejor por Δ%/mes taker (robusto a costos), con OOS>0 y corr<0.35 ---
    def dmes_tk(nm):
        s_ret, turn, _ = store[nm]
        j = pd.concat({**base, nm: s_ret}, axis=1); j.columns = list(base) + [nm]; j = j.dropna()
        s_tk = j[nm] - (config.TAKER_FEE - config.MAKER_FEE) * turn / 365
        j[nm] = s_tk
        ann, _, _ = anchored((j * vol_parity_weights(j)).sum(axis=1)); return (ann - ann0) / 12
    cands_ok = [n for n, (sr, tn, cm) in store.items()
                if cm < 0.35 and sh(seg(pd.concat({**base, n: sr}, axis=1).dropna().iloc[:, -1], .6, 1)) > 0.10]
    if not cands_ok:
        print("\nVEREDICTO: ningún ancho/horizonte mantiene OOS>0.10 con corr<0.35. NO implementar.")
        return
    best = max(cands_ok, key=dmes_tk)
    s_best, turn_best, cmax_best = store[best]
    print(f"\nMEJOR (Δ%/mes taker, OOS>0.10, corr<0.35): {best}  "
          f"(turnover {turn_best:.0f}x/año, corr {cmax_best:.2f})")

    # --- T3: sub-períodos del mejor ---
    print(f"\nT3 — SUB-PERÍODOS del {best} (Sharpe por cuartil temporal):")
    for i, (a, b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)]):
        print(f"  Q{i+1}  Sharpe {sh(seg(s_best, a, b)):+.2f}")

    # --- T4: combinado 7→8 ---
    print(f"\nT4 — COMBINADO 8 sleeves ({best}) vs baseline 7 (overlap 2023+):")
    j = pd.concat({**base, f"orderbook_{best}": s_best}, axis=1)
    j.columns = list(base) + [f"orderbook_{best}"]; j = j.dropna()
    vp = vol_parity_weights(j); combo = (j * vp).sum(axis=1); m = metrics(combo)
    ann, L, dd = anchored(combo)
    s_tk = j.iloc[:, -1] - (config.TAKER_FEE - config.MAKER_FEE) * turn_best / 365
    jt = j.copy(); jt.iloc[:, -1] = s_tk
    ann_tk, L_tk, _ = anchored((jt * vol_parity_weights(jt)).sum(axis=1))
    print(f"  maker: Sharpe {m['sharpe']:.2f} (Δ{m['sharpe']-m0['sharpe']:+.2f}) · @−10% {L:.2f}x → "
          f"{ann/12:.2f}%/mes (Δ{(ann-ann0)/12:+.2f})")
    print(f"  taker: → {ann_tk/12:.2f}%/mes (Δ{(ann_tk-ann0)/12:+.2f})  ← peor caso de costos")
    print(f"  vp: { {k: round(v,2) for k,v in vp.items()} }")
    print("\nVEREDICTO: implementar si edge en RANGO de anchos/horizontes + sobrevive taker + 4")
    print("cuartiles ok + sube el retorno anclado material en overlap. Luego: e18 slippage real")
    print("+ decisión de Oscar sobre el blind-spot 2022 (book no existe pre-2023).")


if __name__ == "__main__":
    main()
