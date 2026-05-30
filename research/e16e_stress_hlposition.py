"""
E16e — ESTRÉS de hl_position (candidato a sleeve #7) antes de producción (2026-05-30).
e16d lo encontró: Sharpe 1.19 (IS 1.09/OOS 1.33), corr 0.20, y al ancla −10% sube el retorno
+0.87%/mes (2.65→~3.5). Antes de implementar (regla de oro), verificar que NO es cherry-pick:

  hl_position = (close − min_N) / (max_N − min_N) − 0.5   (posición del precio en su canal de N días)
  cross-seccional, β-neutral. Es momentum normalizado por rango → ortogonal-ish a mom (corr 0.20).

  TEST 1  HORIZONTE (7d..30d): el edge debe existir en un rango, no en un punto.
  TEST 2  COSTOS: maker vs taker (proxy de turnover).
  TEST 3  SUB-PERÍODOS: Sharpe por cuartil temporal (no concentrado en un tramo).
  TEST 4  Aporte al COMBINADO 6→7 al ancla −10%: ann/mes y maxDD estables.

python -m research.e16e_stress_hlposition
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor


def hl_score(C, win_h):
    mn = C.rolling(win_h).min(); mx = C.rolling(win_h).max()
    return (C - mn) / (mx - mn).replace(0, np.nan) - 0.5


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m["ann"], L, m["maxdd"]


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E16e — ESTRÉS de hl_position antes de producción\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    print(f"Universo {C.shape[1]} · {C.shape[0]} barras 1h\n")

    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta,
        alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base_df = pd.concat(base, axis=1); base_df.columns = list(base.keys()); base_df = base_df.dropna()
    combo0 = (base_df * vol_parity_weights(base_df)).sum(axis=1)
    m0 = metrics(combo0); ann0, L0, _ = anchored(combo0)
    print(f"BASELINE (6 sleeves): Sharpe {m0['sharpe']:.2f} · @−10%: {L0:.2f}x → ann {ann0:.1f}% "
          f"(~{ann0/12:.2f}%/mes)\n")

    print("TEST 1+2 — HORIZONTE × COSTOS (Sh/IS/OOS, corr, combo@−10%):")
    print(f"  {'horiz':>6s} {'cost':>6s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} "
          f"{'ann@-10%':>9s} {'Δ%/mes':>7s}")
    scores = {}
    for days in (7, 10, 14, 21, 30):
        hold = days * 24
        sc = hl_score(C, hold)
        for clabel, cost in (("maker", config.MAKER_FEE), ("taker", config.TAKER_FEE)):
            s_ret, _ = xs_sleeve(C, ret, beta, sc, hold)
            if clabel == "taker":
                s_ret = s_ret - (config.TAKER_FEE - config.MAKER_FEE) * (365 / days) / 365
            j = pd.concat({**base, "hl": s_ret}, axis=1); j.columns = list(base.keys()) + ["hl"]; j = j.dropna()
            corr = j.corr()["hl"].drop("hl").abs().max()
            combo = (j * vol_parity_weights(j)).sum(axis=1)
            ann, L, dd = anchored(combo)
            print(f"  {days:>5d}d {clabel:>6s} {sh(j['hl']):6.2f} {sh(seg(j['hl'],0,0.6)):6.2f} "
                  f"{sh(seg(j['hl'],0.6,1)):6.2f} {corr:6.2f} {ann:8.1f}% {(ann-ann0)/12:+7.2f}")
            if clabel == "maker":
                scores[days] = s_ret

    print("\nTEST 3 — SUB-PERÍODOS del candidato 14d (Sharpe por cuartil):")
    f14 = scores[14]
    for i, (a, b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)]):
        print(f"  Q{i+1}  Sharpe {sh(seg(f14,a,b)):+.2f}")

    print("\nTEST 4 — COMBINADO 7 sleeves (hl 14d, maker) vs baseline 6:")
    j = pd.concat({**base, "hl_position_14d": scores[14]}, axis=1)
    j.columns = list(base.keys()) + ["hl_position_14d"]; j = j.dropna()
    combo = (j * vol_parity_weights(j)).sum(axis=1); m = metrics(combo)
    ann, L, dd = anchored(combo)
    print(f"  Sharpe {m['sharpe']:.2f} (Δ{m['sharpe']-m0['sharpe']:+.2f}) · @−10%: {L:.2f}x → "
          f"ann {ann:.1f}% (~{ann/12:.2f}%/mes) vs baseline ~{ann0/12:.2f}%/mes (Δ{(ann-ann0)/12:+.2f}%/mes)")
    print(f"  vp: { {k: round(v,2) for k,v in vol_parity_weights(j).items()} }")
    print("\nVEREDICTO: implementar si edge en rango de horizontes + sobrevive taker + 4 cuartiles ok")
    print("+ sube el retorno anclado de forma material. Si algo falla → no a producción.")


if __name__ == "__main__":
    main()
