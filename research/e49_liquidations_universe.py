"""
E49 — LIQUIDACIONES: ¿el edge es robusto o depende de ZEC? + REGLA NUEVA de Oscar (universo por-sleeve).
e47/e48: liq_imb_3d real, ortogonal (corr 0.11), +1.05%/mes maker, sobrevive taker, PERO LOO mostró que
sin ZEC cae 1.05→0.11 (dependencia de un nombre fino). Oscar (2026-06-01) pide convertir en regla:
si un sleeve depende/falla por una moneda, probar el sleeve SIN esa moneda (universo por-sleeve), y
evaluar si el sistema puede desacoplarse o necesita todas las monedas.

DOS diagnósticos:
  A) Coins que ESTORBAN (quitarlos MEJORA Δ) → candidatos a excluir de ESE sleeve (regla literal de Oscar).
  B) Coins de los que se DEPENDE (quitarlos MATA Δ) → fragilidad: ¿edge estable IS/OOS o fluke?
Honestidad anti-overfit: la SELECCIÓN de coins a excluir se hace en IS (primer 60%) y se VALIDA en OOS
(quitar coins por su LOO full = mirar el futuro). Coste maker (el artefacto del ancla con taker, e48,
infla; el gate limpio es maker). Hold 24h, imbalance 3d (el mejor de e47).

python -m research.e49_liquidations_universe
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
from research.e47_liquidations_check import load_liq_daily, to_hourly

HOLD = 24


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    return metrics(combo * L).get("ann", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E49 — liquidaciones: robustez por moneda + universo por-sleeve (regla Oscar)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["quote_volume", "volume", "taker_buy_volume"], C)
    cols = list(C.columns)
    Ld, Sd = load_liq_daily(cols)
    imb_raw = (Ld - Sd) / (Ld + Sd).replace(0, np.nan)
    SIGN = -1.0

    # baseline 7
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    bdf = pd.concat(base, axis=1); bdf.columns = list(base); bdf = bdf.dropna()
    ann0 = anchored((bdf * vol_parity_weights(bdf)).sum(axis=1))

    def sleeve_series(exclude=()):
        imbv = imb_raw.drop(columns=[c for c in exclude if c in imb_raw.columns], errors="ignore")
        sc = to_hourly(imbv.rolling(3, min_periods=1).mean(), C)
        s, _ = xs_sleeve(C, ret, beta, sc, HOLD)
        return s * SIGN

    def delta_segment(s, a, b):
        """Δ%/mes al ancla en el sub-segmento [a,b] del histórico (combinado 7+x)."""
        j = pd.concat({**base, "x": s}, axis=1); j.columns = list(base) + ["x"]; j = j.dropna()
        full = (j * vol_parity_weights(j)).sum(axis=1)
        sub = seg(full, a, b)
        sub0 = seg((bdf * vol_parity_weights(bdf)).sum(axis=1), a, b)
        return (anchored(sub) - anchored(sub0)) / 12

    s_full = sleeve_series()
    d_full = delta_segment(s_full, 0, 1)
    print(f"BASE liq_imb_3d (todas): Δ {d_full:+.2f}%/mes · Sharpe {sh(s_full):.2f} · "
          f"IS {delta_segment(s_full,0,.6):+.2f} / OOS {delta_segment(s_full,.6,1):+.2f}\n")

    # ── A+B) CONTRIBUCIÓN POR MONEDA (LOO Δ full) ──
    syms = [c for c in cols if c != "BTCUSDT"]
    loo = []
    for t in syms:
        d = delta_segment(sleeve_series(exclude=[t]), 0, 1)
        loo.append((t, d))                         # d = Δ del sleeve SIN ese coin
    loo.sort(key=lambda x: x[1])
    print("CONTRIBUCIÓN por moneda (Δ del sleeve SIN ese coin; menor=el coin APORTA más):")
    print("  DEPENDE de (quitarlo MATA):    " + ", ".join(f"{t}({d:+.2f})" for t, d in loo[:5]))
    print("  ESTORBAN (quitarlo MEJORA>full): " +
          (", ".join(f"{t}({d:+.2f})" for t, d in loo if d > d_full + 0.05) or "ninguno"))

    # ── B) ¿ZEC estable IS/OOS o fluke? ──
    s_noZEC = sleeve_series(exclude=["ZECUSDT"])
    print(f"\n¿ZEC estable o fluke? full vs sin-ZEC por mitades:")
    print(f"  full     IS {delta_segment(s_full,0,.6):+.2f} / OOS {delta_segment(s_full,.6,1):+.2f}")
    print(f"  sin ZEC  IS {delta_segment(s_noZEC,0,.6):+.2f} / OOS {delta_segment(s_noZEC,.6,1):+.2f}")

    # ── REGLA Oscar: excluir ESTORBADORES seleccionados en IS, validar en OOS ──
    print(f"\nREGLA (universo por-sleeve): excluir en IS los que estorban → validar OOS:")
    loo_is = sorted(((t, delta_segment(sleeve_series(exclude=[t]), 0, .6)) for t in syms), key=lambda x: -x[1])
    d_is_full = delta_segment(s_full, 0, .6)
    drag_is = [t for t, d in loo_is if d > d_is_full + 0.05]      # quitarlos mejora EN IS
    print(f"  estorbadores en IS (quitarlos mejora IS): {drag_is or 'ninguno'}")
    if drag_is:
        s_ex = sleeve_series(exclude=drag_is)
        print(f"  sleeve SIN estorbadores-IS:  full Δ {delta_segment(s_ex,0,1):+.2f} · "
              f"IS {delta_segment(s_ex,0,.6):+.2f} / OOS {delta_segment(s_ex,.6,1):+.2f} "
              f"(vs full OOS {delta_segment(s_full,.6,1):+.2f})")
        print("  → si el OOS MEJORA o se mantiene con menos coins = la regla rescata/limpia el sleeve.")
        # TEST DECISIVO: ¿el sleeve de-dragged sigue dependiendo de ZEC?
        s_ex_noZEC = sleeve_series(exclude=drag_is + ["ZECUSDT"])
        print(f"  DECISIVO de-dragged SIN ZEC: full Δ {delta_segment(s_ex_noZEC,0,1):+.2f} · "
              f"IS {delta_segment(s_ex_noZEC,0,.6):+.2f} / OOS {delta_segment(s_ex_noZEC,.6,1):+.2f}")
        print("    → si colapsa = el edge ES ZEC aun tras la regla; si aguanta = sleeve robusto repartido.")
    else:
        print("  → no hay estorbadores claros en IS; el sleeve usa bien todas las monedas (no se desacopla por exclusión).")

    print("\nVEREDICTO (se imprime arriba con números). Interpretación:")
    print("  · Si sin-ZEC sigue >0 en AMBAS mitades → edge repartido, ZEC solo amplifica (robusto).")
    print("  · Si sin-ZEC ≈0 en ambas → el edge ES ZEC (concentrado); decidir si un edge de 1 coin es admisible.")
    print("  · Si la exclusión de estorbadores sube el OOS → REGLA útil (universo por-sleeve) → generalizar.")


if __name__ == "__main__":
    main()
