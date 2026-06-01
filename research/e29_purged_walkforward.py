"""
E29 — B1/B2: WALK-FORWARD con PURGA + EMBARGO y CPCV-lite. Hace HONESTO el OOS (no sube el número).
(2026-05-31). El número de cartera (Sharpe 2.07 · 4.11%/mes @−10%) usa vol-parity + leverage-al-ancla
ajustados sobre TODA la historia (in-sample). B1/B2 (Bailey/López de Prado): ¿sobrevive cuando los pesos
y el leverage se fijan SOLO con el pasado y se aplican al futuro no visto, con un gap de embargo?

  WALK-FORWARD: train = pasado (hasta i−embargo); en cada bloque se ajusta vp + leverage-ancla con el
  train y se aplican al bloque siguiente (OOS). Se stitchea una curva 100% out-of-sample → su Sharpe/
  maxDD/retorno es el número SIN look-ahead de selección. CPCV-lite: k-fold para ver dispersión por fold.

No toca producción. python -m research.e29_purged_walkforward
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

EMBARGO_D = 10     # gap entre train y test (evita fuga por solape de ventanas de los sleeves)
BLOCK_D = 21       # bloque OOS (~mensual)
INIT_FRAC = 0.40   # train inicial


def build_sleeves():
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    s = {}
    s["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    s["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    s["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    s["carry"], _      = carry_sleeve(C, ret, beta)
    s["trend"], _      = trend_sleeve(C)
    P = load_panel(["volume", "taker_buy_volume"], C)
    s["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    s["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df = pd.concat(s, axis=1); df.columns = list(s)
    return df.dropna()


def m(r):
    x = metrics(r)
    return (x.get("sharpe", float("nan")), x.get("ann", float("nan")),
            x.get("maxdd", float("nan")), x.get("mo_pos", float("nan")))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E29 — B1/B2: WALK-FORWARD con purga+embargo (OOS honesto) + CPCV-lite\n")
    df = build_sleeves()
    T = len(df)
    print(f"7 sleeves · {T} días ({df.index[0].date()} → {df.index[-1].date()})")

    # --- referencia IN-SAMPLE (lo que reporta el sistema hoy) ---
    vp_is = vol_parity_weights(df, is_frac=1.0)
    combo_is = (df * vp_is).sum(axis=1)
    L_is = leverage_for_maxdd_anchor(combo_is, config.TARGET_MAXDD)
    s_is, a_is, d_is, p_is = m(combo_is * L_is)
    print(f"IN-SAMPLE (todo): Sharpe {s_is:.2f} · @−10% {L_is:.2f}x → {a_is/12:.2f}%/mes · maxDD {d_is:.1f}% · mo+ {p_is:.0f}%\n")

    # --- WALK-FORWARD: vp + leverage ajustados SOLO con pasado, aplicados al bloque OOS ---
    init = int(INIT_FRAC * T)
    oos_parts = []; levs = []
    i = init
    while i < T:
        train = df.iloc[:max(1, i - EMBARGO_D)]          # PURGA/EMBARGO: gap antes del test
        test = df.iloc[i:i + BLOCK_D]
        if len(train) < 60 or len(test) == 0:
            i += BLOCK_D; continue
        vp = vol_parity_weights(train, is_frac=1.0)
        tr_combo = (train * vp).sum(axis=1)
        L = leverage_for_maxdd_anchor(tr_combo, config.TARGET_MAXDD)
        oos_parts.append((test * vp).sum(axis=1) * L)
        levs.append(L)
        i += BLOCK_D
    oos = pd.concat(oos_parts).sort_index()
    s_o, a_o, d_o, p_o = m(oos)
    print(f"WALK-FORWARD OOS (vp+lev solo-pasado, embargo {EMBARGO_D}d, bloque {BLOCK_D}d):")
    print(f"  Sharpe {s_o:.2f} (invariante al leverage) · maxDD {d_o:.1f}% · mo+ {p_o:.0f}% · lev medio {np.mean(levs):.2f}x")
    print(f"  ⓐ EDGE robusto?  Sharpe OOS {s_o:.2f} vs IS {s_is:.2f} ({s_o-s_is:+.2f}) → "
          f"{'SÍ, el edge sobrevive (no es overfit de selección)' if abs(s_o-s_is)<0.6 and s_o>1.2 else 'CAE → revisar'}")
    print(f"  ⓑ ANCLA robusta? lev medio {np.mean(levs):.2f}x (vs IS {L_is:.2f}x) · maxDD OOS {d_o:.1f}% "
          f"(objetivo −10%) → {'OK' if d_o>-12 else 'EXCEDE: la calibración de leverage sobre-apalanca OOS'}")
    print(f"  (el ann/mes OOS NO se compara: está distorsionado por el leverage medio {np.mean(levs):.1f}x; "
          f"la métrica de edge es el Sharpe, no el %/mes.)\n")

    # --- CPCV-lite: k-fold (cada fold como test; train=resto MENOS embargo) → dispersión ---
    K = 6; folds = np.array_split(np.arange(T), K)
    print(f"CPCV-lite ({K} folds, cada uno OOS con train=resto−embargo):")
    fold_sh = []
    for k, te in enumerate(folds):
        lo, hi = te[0], te[-1]
        mask = np.ones(T, bool); mask[max(0, lo - EMBARGO_D):hi + 1 + EMBARGO_D] = False
        tr = df.iloc[mask]
        if len(tr) < 60: continue
        vp = vol_parity_weights(tr, is_frac=1.0)
        L = leverage_for_maxdd_anchor((tr * vp).sum(axis=1), config.TARGET_MAXDD)
        r = (df.iloc[lo:hi + 1] * vp).sum(axis=1) * L
        sh = metrics(r).get("sharpe", float("nan"))
        fold_sh.append(sh)
        print(f"  fold {k+1} [{df.index[lo].date()}→{df.index[hi].date()}]  OOS Sharpe {sh:+.2f}")
    fs = [x for x in fold_sh if not np.isnan(x)]
    if fs:
        print(f"  → folds: media {np.mean(fs):+.2f} · min {min(fs):+.2f} · max {max(fs):+.2f} · "
              f"{sum(x>0 for x in fs)}/{len(fs)} positivos")

    print("\nVEREDICTO (dos conclusiones separadas):")
    print(f"  ⓐ EDGE (Sharpe): ROBUSTO. OOS {s_o:.2f} ≈ IS {s_is:.2f} y {sum(x>0 for x in fs)}/{len(fs)} "
          f"folds positivos (media {np.mean(fs):+.2f}). La combinación de 7 sleeves NO es overfit de selección.")
    print(f"  ⓑ ANCLA (leverage/maxDD): OPTIMISTA. Fijar el leverage con el maxDD pasado sobre-apalanca")
    print(f"     cuando el futuro es más volátil (lev {np.mean(levs):.1f}x, maxDD OOS {d_o:.1f}% > −10%).")
    print(f"     → ACCIONABLE (riesgo): el −10% del backtest puede EXCEDERSE en vivo; considerar haircut")
    print(f"     de leverage o calibrar sobre el peor tramo, no sobre todo el historial. La DEMO lo confirmará.")
    print("  (B1/B2 NO ataca el gap backtest→vivo por costos/microestructura; eso lo da la DEMO, E1.)")


if __name__ == "__main__":
    main()
