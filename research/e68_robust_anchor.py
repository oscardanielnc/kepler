"""
e68 — ANCLA DE LEVERAGE ROBUSTA A LA VENTANA DE DATOS
Motivado por el incidente 2026-06-02: la VM corría a 2.929x (vs 2.16x diseño) porque su histórico
empezaba ~2023 (sin la caída de abril-2022) → el maxDD-anchor vio un mercado calmado y sobre-apalancó.

Pregunta: ¿qué política de leverage mantiene el maxDD REAL ≤ presupuesto aunque la ventana de datos
sea corta/calmada, sin sacrificar retorno cuando la ventana es completa?

Métrica clave de robustez: el leverage se ELIGE sobre la ventana disponible, pero el riesgo REAL se
mide como el maxDD sobre la historia COMPLETA a ese leverage (lo que de verdad pasaría).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
import config
from kepler.engine import compute_target
from kepler.portfolio import _maxdd, metrics, leverage_for_maxdd_anchor

TARGET = config.TARGET_MAXDD          # 0.10
HC     = config.LEVERAGE_HAIRCUT      # 0.95
CAP    = config.MAX_STRAT_LEVERAGE    # 4.0
PPY    = 365

# ---- serie base: combinado 1x de los 7 sleeves (historia completa local) ----
_,_,_, port, asof, _,_,_,_ = compute_target("ESTABLE")
port = port.dropna()
print(f"Combinado 1x · {port.index[0].date()} -> {port.index[-1].date()} · {len(port)} días · asof {asof}")
vol_full = port.std()*np.sqrt(PPY)
raw_full = leverage_for_maxdd_anchor(port, TARGET)
print(f"FULL: vol 1x={vol_full*100:.1f}% · raw maxdd-anchor={raw_full:.3f} · maxDD@raw={_maxdd(port,raw_full)*100:.2f}%")

# TARGET_VOL = la vol operativa que produce el maxDD presupuestado en la historia completa de referencia.
# Es la constante del vol-anchor (se fija OFFLINE una vez; en vivo no depende de la ventana).
TARGET_VOL = vol_full * raw_full
print(f"vol-anchor: TARGET_VOL fijo = {TARGET_VOL*100:.1f}% ann (= vol_full × raw_full)\n")

def lev_status_quo(r):                      # A: lo que hay hoy
    return min(HC * leverage_for_maxdd_anchor(r, TARGET), CAP)

def lev_vol(r):                             # B: vol-anchor (constante TARGET_VOL / vol de la ventana)
    v = r.std()*np.sqrt(PPY)
    return min(HC * (TARGET_VOL / v) if v>0 else CAP, CAP)

def lev_hybrid(r):                          # C: el MÁS conservador de los dos (cinturón + tirantes)
    return min(lev_status_quo(r), lev_vol(r))

POLICIES = {"A_statusquo": lev_status_quo, "B_volanchor": lev_vol, "C_hibrido_min": lev_hybrid}

# ---- TEST 1: fragilidad ante ventana corta ----
# Para cada fecha de inicio, elegir lev sobre port[start:] y medir el maxDD REAL sobre la historia COMPLETA.
starts = ["2022-03-15","2022-07-01","2023-01-01","2023-07-01","2024-01-01","2024-06-01","2025-01-01","2025-06-01"]
print("="*92)
print("FRAGILIDAD: leverage elegido en ventana corta → maxDD REAL sobre historia completa (objetivo ≤10%)")
print(f"{'desde':>11} {'win_d':>6} {'win_dd1x':>8} | " + " | ".join(f'{k:>22}' for k in POLICIES))
print(f"{'':>11} {'':>6} {'':>8} | " + " | ".join(f'{"lev / maxDD_real":>22}' for _ in POLICIES))
print("-"*92)
for s in starts:
    w = port[port.index >= s]
    if len(w) < 90: continue
    dd1x = _maxdd(w, 1.0)*100
    cells = []
    for k,f in POLICIES.items():
        L = f(w)
        real_dd = _maxdd(port, L)*100          # riesgo real = maxDD sobre TODA la historia a ese lev
        cells.append(f"{L:>5.2f}x /{real_dd:>7.2f}%")
    print(f"{s:>11} {len(w):>6} {dd1x:>7.2f}% | " + " | ".join(f'{c:>22}' for c in cells))

# ---- TEST 2: ¿sacrifica retorno con datos completos? (no debe empeorar el caso bueno) ----
print("\n"+"="*92)
print("CON HISTORIA COMPLETA (no debe perder retorno vs status quo):")
for k,f in POLICIES.items():
    L = f(port); m = metrics(port*L)
    print(f"  {k:>14}: lev {L:.3f}x · ann {m['ann']:.1f}% (~{m['ann']/12:.2f}%/mes) · "
          f"maxDD {m['maxdd']:.2f}% · Sharpe {m['sharpe']:.2f}")
