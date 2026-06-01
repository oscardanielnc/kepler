"""
E31 — R2: ¿se puede POTENCIAR alguno de los 7 sleeves ACTUALES con un régimen? (2026-06-01)
"Más peso a un sleeve base cuando el viento (régimen) está a su favor" = añadir al libro una COPIA
condicional de ese sleeve restringida al régimen → vol-parity le sube el peso en ese estado.

Barre 7 sleeves × 5 régimenes × 2 direcciones = 70 combos, con el laboratorio (regime_lab):
walk-forward purgado + CPCV, métrica = Sharpe (invariante al leverage). DEFLACIÓN por nº de combos
(López de Prado): un ganador debe superar el MÁXIMO ΔSharpe esperado bajo ruido de 70 pruebas.
Se marca además si el combo coincide con la HIPÓTESIS pre-registrada por teoría (más credible).

Regla de promoción: ΔSharpe OOS > barra deflactada Y CPCV ≥5/6 folds Y (idealmente) match teoría.
python -m research.e31_regime_sweep_current
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research.regime_lab import (build_base_sleeves, get_regimes, evaluate, run_combo,
                                 deflation_bar, REGIME_MENU)

# HIPÓTESIS pre-registradas (teoría) — dirección esperada favorable por sleeve.
# (sleeve, regime, favorable_state). favorable_state=True → el estado del menú; False → su negación.
PRIOR = {
    ("mom_30d",      "mkt_bull",     True),    # momentum cunde en tendencia alcista
    ("mom_30d",      "breadth_high", True),    # y con mercado amplio
    ("rev_60d",      "xs_disp_high", True),    # reversión: más oportunidad con alta dispersión
    ("rev_60d",      "mkt_bull",     False),   # reversión sufre en bull fuerte (momentum domina)
    ("lowvol_14d",   "mkt_vol_high", True),    # low-vol/defensivo brilla en estrés (alta vol)
    ("carry",        "funding_high", True),    # carry cobra más con funding alto
    ("trend",        "mkt_bull",     True),    # trend long-only cunde en bull
    ("trend",        "breadth_high", True),
    ("takerflow_5d", "mkt_vol_high", True),    # flujo informativo en alta vol
    ("hlpos_14d",    "mkt_bull",     True),    # momentum de canal en bull
}


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E31 — R2: ¿potenciar los 7 sleeves actuales con régimen? (sweep + deflación)\n" + "="*70)
    base = build_base_sleeves(); R = get_regimes()
    base_ref = evaluate(base, None, "7 base")
    nfolds = len(base_ref["folds"])
    print(f"Baseline 7 (OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes · "
          f"CPCV media {base_ref['fold_mean']:+.2f} ({nfolds} folds)\n")

    rows = []
    for sl in base.columns:
        sleeve = base[sl]
        for rname in REGIME_MENU:
            if rname not in R.columns: continue
            for fav in (True, False):
                r = run_combo(base, base_ref, sleeve, R[rname], fav, f"{sl}×{rname}[{'T' if fav else 'F'}]")
                r["sleeve"], r["regime"], r["fav"] = sl, rname, fav
                r["theory"] = (sl, rname, fav) in PRIOR
                rows.append(r)

    N = len(rows)
    bar = deflation_bar([x["d_sharpe"] for x in rows], N)
    print(f"{N} combos probados. Barra DEFLACTADA de ΔSharpe (máx esperado bajo ruido de {N}): {bar:+.2f}\n")

    # Top por ΔSharpe
    rows.sort(key=lambda x: -x["d_sharpe"])
    print("TOP 12 por ΔSharpe OOS (Δmes, folds ganados/total, % activo, ¿supera barra?, ¿match teoría?):")
    print(f"  {'combo':28s} {'ΔSh':>6s} {'Δmes':>6s} {'folds':>6s} {'on%':>5s} {'barra':>6s} {'teoría':>7s}")
    for x in rows[:12]:
        over = "SÍ" if x["d_sharpe"] > bar else "no"
        th = "✓teo" if x["theory"] else ""
        print(f"  {x['label']:28s} {x['d_sharpe']:+6.2f} {x['d_mes']:+6.2f} "
              f"{x['fold_wins']:>3d}/{x['fold_n']:<2d} {x['pct_on']*100:4.0f}% {over:>6s} {th:>7s}")

    # Pre-registrados (teoría) — su rendimiento, hayan ganado o no
    print("\nHIPÓTESIS PRE-REGISTRADAS (teoría) — ¿se confirman?:")
    print(f"  {'combo':28s} {'ΔSh':>6s} {'folds':>6s} {'¿supera barra?':>14s}")
    for x in sorted([r for r in rows if r["theory"]], key=lambda x: -x["d_sharpe"]):
        over = "SÍ" if x["d_sharpe"] > bar else "no"
        print(f"  {x['label']:28s} {x['d_sharpe']:+6.2f} {x['fold_wins']:>3d}/{x['fold_n']:<2d} {over:>14s}")

    # SUPERVIVIENTES: superan barra deflactada Y CPCV >=5/6
    surv = [x for x in rows if x["d_sharpe"] > bar and x["fold_wins"] >= max(5, nfolds-1)]
    print("\nSUPERVIVIENTES (ΔSharpe > barra deflactada Y folds ≥5/6):")
    if not surv:
        print("  NINGUNO. Potenciar los 7 sleeves actuales con régimen NO sobrevive el listón deflactado.")
        print("  → Coherente con la cicatriz del sistema: los 7 ya son robustos (6/6 folds); el gate")
        print("    discreto añade ruido/overfit, no edge. La versión continua (vol-parity + ancla) ya")
        print("    captura la adaptación de riesgo defendible. Pasamos a R3 (rescatar descartados).")
    else:
        for x in surv:
            print(f"  ✅ {x['label']}: ΔSharpe {x['d_sharpe']:+.2f}, folds {x['fold_wins']}/{x['fold_n']}, "
                  f"{'MATCH teoría' if x['theory'] else 'SIN teoría (sospechoso, validar forward)'}")
        print("  → Candidatos a tilt de régimen. Validar forward antes de producción (regla de oro).")


if __name__ == "__main__":
    main()
