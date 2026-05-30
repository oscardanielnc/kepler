"""
E17b — ESTRÉS del universo ampliado (subconjunto ganador de e17) antes de implementar.
La mejora (Sharpe 1.94→~2.25, +~2.6%/mes) debe ser ROBUSTA, no de un solo tramo temporal.
Tests:
  1. Sharpe del combinado por CUARTIL temporal (base vs ampliado) — la mejora debe estar repartida.
  2. ¿Cuánto del +%/mes es EDGE (Sharpe) vs LEVERAGE (ancla sube por menor maxDD)? Desglose.
  3. Robustez del subconjunto: quitar el candidato top (AXS) — ¿se cae la mejora? (concentración)

python -m research.e17b_stress_universe
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from research.e17_expand_universe import run_system, report
from kepler.portfolio import metrics, leverage_for_maxdd_anchor
import kepler.engine as eng

WIN = ["XMRUSDT","ALGOUSDT","AXSUSDT","DYDXUSDT","CHZUSDT","IOTAUSDT","VETUSDT","XTZUSDT"]


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    MB = eng.MIN_BARS
    avail = [s for s in WIN if os.path.exists(os.path.join(config.DATA_DIR,"futures_um","1h",f"{s}.parquet"))]
    print(f"E17b — ESTRÉS universo ampliado. Ganadores disponibles: {avail}\n")

    base, nb, _ = run_system(config.UNIVERSE, MB)
    amp, na, _ = run_system(list(config.UNIVERSE) + avail, MB)

    print("TEST 1 — Sharpe por CUARTIL temporal (la mejora debe estar repartida, no en 1 tramo):")
    print(f"  {'cuartil':10s} {'base':>7s} {'ampliado':>9s} {'Δ':>7s}")
    for i, (a, b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1)]):
        sb, sa = sh(seg(base, a, b)), sh(seg(amp, a, b))
        print(f"  Q{i+1:<8d} {sb:7.2f} {sa:9.2f} {sa-sb:+7.2f}")

    print("\nTEST 2 — desglose EDGE vs LEVERAGE:")
    rb = report(base, "base"); ra = report(amp, "amp")
    print(f"  base:     Sharpe {rb['sharpe']:.2f} · maxDD1x {rb['maxdd1x']:.1f}% · lev {rb['lev']:.2f}x → {rb['mes']:.2f}%/mes")
    print(f"  ampliado: Sharpe {ra['sharpe']:.2f} · maxDD1x {ra['maxdd1x']:.1f}% · lev {ra['lev']:.2f}x → {ra['mes']:.2f}%/mes")
    # contrafactual: ampliado pero al MISMO leverage del base (aísla el edge puro)
    m_same = metrics(amp * rb['lev'])
    print(f"  ampliado @lev_base({rb['lev']:.2f}x): {m_same['ann']/12:.2f}%/mes maxDD {m_same['maxdd']:.1f}%")
    print(f"  → mejora por EDGE (mismo lev): {m_same['ann']/12 - rb['mes']:+.2f}%/mes")
    print(f"  → mejora por LEVERAGE extra : {ra['mes'] - m_same['ann']/12:+.2f}%/mes")

    print("\nTEST 3 — robustez: quitar el candidato top (AXS) del subconjunto:")
    no_axs = [s for s in avail if s != "AXSUSDT"]
    amp2, _, _ = run_system(list(config.UNIVERSE) + no_axs, MB)
    r2 = report(amp2, "sin AXS")
    print(f"  con AXS: {ra['sharpe']:.2f} Sharpe · {ra['mes']:.2f}%/mes")
    print(f"  sin AXS: {r2['sharpe']:.2f} Sharpe · {r2['mes']:.2f}%/mes  (Δ por AXS: {ra['mes']-r2['mes']:+.2f}%/mes)")
    print("  → si quitar AXS borra casi toda la mejora = concentración peligrosa.")

    print("\nVEREDICTO: implementar si la mejora está REPARTIDA (T1), es EDGE no solo leverage (T2),")
    print("y NO depende de un símbolo (T3). Reportar a Oscar.")


if __name__ == "__main__":
    main()
