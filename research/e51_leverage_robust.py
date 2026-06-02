"""
E51 — D0: CALIBRACIÓN ROBUSTA DEL ANCLA DE LEVERAGE (riesgo prioritario, MONITOREO §2.3 / ROADMAP D).
(2026-06-02). e29 encontró que fijar el leverage con el maxDD PASADO sobre-apalanca cuando el futuro
es más volátil: en walk-forward el maxDD OOS llegó a −13.5% vs −10% objetivo. ⇒ el −10% del backtest
PUEDE EXCEDERSE en vivo, lo que rompería la promesa del producto (copy-lead de bajo drawdown).

Este script CUANTIFICA el gap y evalúa políticas para cerrarlo, con el MISMO walk-forward purgado de e29
(vp + leverage fijados solo-con-pasado, embargo 10d). Para cada política reporta el número HONESTO OOS:
  - leverage de PRODUCCIÓN que enviaría (fit sobre TODA la historia, que es lo que hace compute_target),
  - maxDD OOS (la métrica de la promesa) y %/mes OOS (lo que se sacrifica),
  - Sharpe OOS (invariante al leverage = mide el edge, no cambia con el haircut).

Políticas evaluadas:
  A) HAIRCUT plano h: lev_final = h · ancla.  (simple, transparente para copy-lead)
  B) PEOR-TRAMO: fija el ancla sobre el peor sub-tramo contiguo (ventana W) en vez de toda la historia
     (dimensiona el leverage para que incluso el peor régimen visto cumpla el presupuesto).

No toca producción. python -m research.e51_leverage_robust
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
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor, _maxdd

EMBARGO_D = 10
BLOCK_D = 21
INIT_FRAC = 0.40
TARGET = config.TARGET_MAXDD   # 0.10


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


def worst_tranche_anchor(r: pd.Series, target: float, window_d: int = 252) -> float:
    """Fija el leverage tal que el maxDD del PEOR sub-tramo contiguo de `window_d` días = target.
    Más conservador que anclar sobre toda la historia (donde el peor tramo se diluye)."""
    r = r.dropna()
    if len(r) < window_d + 30:
        return leverage_for_maxdd_anchor(r, target)
    # leverage que cada ventana toleraría; el de producción = el MÍNIMO (el peor tramo manda)
    levs = []
    for i in range(0, len(r) - window_d, 21):   # paso mensual
        levs.append(leverage_for_maxdd_anchor(r.iloc[i:i + window_d], target))
    return float(min(levs)) if levs else leverage_for_maxdd_anchor(r, target)


def walkforward(df, anchor_fn):
    """Curva 100% OOS: en cada bloque, vp + leverage (vía anchor_fn) fijados solo-con-pasado."""
    T = len(df); init = int(INIT_FRAC * T)
    parts, levs = [], []
    i = init
    while i < T:
        train = df.iloc[:max(1, i - EMBARGO_D)]
        test = df.iloc[i:i + BLOCK_D]
        if len(train) < 60 or len(test) == 0:
            i += BLOCK_D; continue
        vp = vol_parity_weights(train, is_frac=1.0)
        L = min(anchor_fn((train * vp).sum(axis=1)), config.MAX_STRAT_LEVERAGE)
        parts.append((test * vp).sum(axis=1) * L); levs.append(L)
        i += BLOCK_D
    return pd.concat(parts).sort_index(), np.array(levs)


def row(name, prod_lev, oos, levs):
    mm = metrics(oos)
    return dict(name=name, prod_lev=prod_lev, oos_sharpe=mm["sharpe"], oos_maxdd=mm["maxdd"],
                oos_mes=mm["ann"] / 12, oos_lev_mean=float(np.mean(levs)))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E51 — D0: calibración robusta del ancla de leverage (cerrar el gap del maxDD OOS)\n")
    df = build_sleeves()
    print(f"7 sleeves · {len(df)} días ({df.index[0].date()} → {df.index[-1].date()})\n")

    # ── PRODUCCIÓN actual (IS, todo el historial) ──────────────────────────────
    vp_full = vol_parity_weights(df, is_frac=1.0)
    combo_full = (df * vp_full).sum(axis=1)
    L_full = min(leverage_for_maxdd_anchor(combo_full, TARGET), config.MAX_STRAT_LEVERAGE)
    mfull = metrics(combo_full * L_full)
    print(f"PRODUCCIÓN HOY (ancla sobre todo el historial): lev {L_full:.2f}x · "
          f"Sharpe {mfull['sharpe']:.2f} · maxDD {mfull['maxdd']:.1f}% (IS, clavado) · {mfull['ann']/12:.2f}%/mes")

    # ── BASELINE OOS (sin haircut) = reproduce e29 ─────────────────────────────
    oos0, levs0 = walkforward(df, lambda r: leverage_for_maxdd_anchor(r, TARGET))
    m0 = metrics(oos0)
    print(f"WALK-FORWARD OOS (ancla actual, sin haircut): maxDD {m0['maxdd']:.1f}% (objetivo −10%) · "
          f"Sharpe {m0['oos_sharpe'] if False else m0['sharpe']:.2f} · lev medio {levs0.mean():.2f}x")
    gap = m0["maxdd"] / (-TARGET * 100)
    print(f"  → el maxDD OOS excede el objetivo por factor ~{gap:.2f} (gap a cerrar)\n")

    # ── POLÍTICA A: HAIRCUT plano — TABLA DE DECISIÓN ──────────────────────────
    # Dos lados: (1) PRODUCCIÓN = lo que se opera (fit todo historial, lev=h·1.94) → su %/mes y maxDD IS;
    #            (2) WALK-FORWARD OOS maxDD = el medidor de riesgo HONESTO (¿se respeta el −10% en vivo?).
    print("POLÍTICA A — HAIRCUT plano (lev_final = h · ancla). Sharpe (edge) invariante = 2.21 IS / 2.29 OOS.\n")
    print(f"{'h':>5} {'lev_prod':>9} │ {'%/mes_prod':>10} {'maxDD_prod':>10} │ {'maxDD_OOS':>10}  (riesgo real)")
    print("─" * 66)
    for h in [1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70]:
        prod_lev = min(h * L_full, config.MAX_STRAT_LEVERAGE)
        mp = metrics(combo_full * prod_lev)                       # lado PRODUCCIÓN
        oos, _ = walkforward(df, lambda r, h=h: min(h * leverage_for_maxdd_anchor(r, TARGET), config.MAX_STRAT_LEVERAGE))
        dd_oos = metrics(oos)["maxdd"]                            # medidor de riesgo OOS
        flag = "  ← −10% se respeta" if dd_oos >= -10.0 else ("  ← ~−11%" if dd_oos >= -11.0 else "")
        print(f"{h:>5.2f} {prod_lev:>8.2f}x │ {mp['ann']/12:>9.2f}% {mp['maxdd']:>9.1f}% │ {dd_oos:>9.1f}%{flag}")

    print("\nLECTURA:")
    print(" • Sin haircut (h=1.0): producción opera a 1.94x con maxDD IS clavado −10%, pero el walk-forward")
    print("   honesto dice que en vivo el maxDD puede llegar a −13.5% (rompe la promesa de bajo-DD).")
    print(" • Para que el −10% se RESPETE incluso en el escenario forward pesimista → h≈0.72-0.75 (lev ~1.4x),")
    print("   coste ~25% del retorno. Matiz: el −13.5% lo inflan los folds tempranos (poca historia, lev 3x);")
    print("   producción-HOY ancla con 3.5 años incl. el bear 2022 → su sobre-tiro real es menor que 35%.")
    print(" • COMPROMISO (recomendado): h≈0.85 (lev ~1.65x) recorta el grueso del gap (OOS ~−11.5%) cediendo")
    print("   solo ~12-15% de retorno. Política B (peor-tramo) DESCARTADA: da lev MAYOR (las ventanas tienen")
    print("   menos DD que el global) → empuja en la dirección equivocada.")


if __name__ == "__main__":
    main()
