"""
E75 — test de kepler/checks.py (Fase 1, guardas pre-trade). Casos: normal + incidente reproducido + fallos
sintéticos. python -m research.e75_checks_test
"""
from __future__ import annotations
import os, sys
import pandas as pd
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from kepler.engine import load, compute_target
from kepler import checks


def show(title, results):
    blk = checks.should_block(results)
    print(f"\n=== {title} ===  worst={checks.worst(results)}  BLOQUEA={'SÍ 🔴' if blk else 'no'}")
    for r in results:
        print("   " + str(r))
    return blk


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E75 — test de guardas pre-trade (checks.py)")
    C = load()
    target, vp, df, port_ret, asof, lev, weights, beta_last, beta_model = compute_target("ESTABLE")

    # now de producción = justo tras el fetch (la última barra ~1h vieja). Local la data está parada.
    now_prod = C.index[-1] + pd.Timedelta(hours=1)

    # 1) NORMAL (salida real del motor) → NO debe bloquear
    r = checks.run_pretrade_checks(C, target, lev, beta_last, prev_lev=lev, now=now_prod)
    assert not show("1) NORMAL (motor real, now=post-fetch)", r), "FALLO: normal no debería bloquear"

    # 2) INCIDENTE REPRODUCIDO: panel arranca ~2023 (backfill faltante) → data_coverage CRIT → BLOQUEA
    C_short = C[C.index >= "2023-01-01"]
    now_short = C_short.index[-1] + pd.Timedelta(hours=1)
    r = checks.run_pretrade_checks(C_short, target, lev, beta_last, prev_lev=lev, now=now_short)
    assert show("2) INCIDENTE (datos desde 2023, backfill faltante)", r), "FALLO: debería bloquear"
    assert any(x.name == "data_coverage" and x.severity == checks.CRIT for x in r)

    # 3) DATOS CONGELADOS: última barra vieja → freshness CRIT → BLOQUEA
    r = checks.run_pretrade_checks(C, target, lev, beta_last, now=now_prod + pd.Timedelta(days=3))
    assert show("3) DATOS CONGELADOS (última barra +3d vieja)", r), "FALLO: debería bloquear"

    # 4) LEVERAGE DISPARADO: lev 3.4x → CRIT → BLOQUEA
    r = checks.run_pretrade_checks(C, target, 3.4, beta_last, prev_lev=lev, now=now_prod)
    assert show("4) LEVERAGE 3.4x (ancla anómala)", r), "FALLO: debería bloquear"

    # 5) LEVERAGE SALTO tipo incidente (2.16→2.93): banda WARN + salto WARN → NO bloquea (data_coverage es la red dura)
    r = checks.run_pretrade_checks(C, target, 2.93, beta_last, prev_lev=2.16, now=now_prod)
    show("5) LEVERAGE 2.93x salto +36% (incidente sin la red de datos)", r)

    # 6) CONCENTRACIÓN excedida (bug del clip): un peso a 0.30 → WARN (no bloquea)
    t2 = target.copy(); t2.iloc[0] = 0.30
    r = checks.run_pretrade_checks(C, t2, lev, beta_last, prev_lev=lev, now=now_prod)
    show("6) CONCENTRACIÓN 30% (clip roto)", r)

    print("\n✅ TODOS LOS ASSERTS PASARON — las guardas críticas bloquean lo que deben.")


if __name__ == "__main__":
    main()
