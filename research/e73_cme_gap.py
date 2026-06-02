"""
E73 — CME GAP (test honesto rápido de viabilidad). (2026-06-02)
Hipótesis: el movimiento de BTC durante el fin de semana (CME cerrado, Binance abierto) tiende a revertir
al reabrir CME (rellenar el gap). Proxy con data horaria 24/7 de Binance:
  gap = retorno BTC de viernes-cierre-CME (~21 UTC) a domingo-reapertura (~22 UTC).
  fade = entrar en domingo-22 con -sign(gap), salir a horizonte H (o al rellenar). ¿Gana tras taker?
CAVEAT: es BTC-direccional → NO puede ser sleeve β-neutral (solo overlay). Test = ¿hay edge explotable?

python -m research.e73_cme_gap
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from kepler.engine import load

def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    C = load(); btc = C["BTCUSDT"].dropna()
    idx = btc.index
    fri = btc[(idx.dayofweek == 4) & (idx.hour == 21)]   # viernes ~cierre CME (21 UTC)
    sun = btc[(idx.dayofweek == 6) & (idx.hour == 22)]    # domingo ~reapertura CME (22 UTC)
    # emparejar cada domingo con su viernes anterior (mismo fin de semana)
    fri_by_week = {(t.isocalendar().year, t.isocalendar().week): p for t, p in fri.items()}
    rows = []
    for t, ps in sun.items():
        key = (t.isocalendar().year, t.isocalendar().week)
        if key not in fri_by_week: continue
        pf = fri_by_week[key]
        gap = ps / pf - 1.0
        rows.append((t, pf, ps, gap))
    G = pd.DataFrame(rows, columns=["sun_t", "fri_px", "sun_px", "gap"]).set_index("sun_t")
    print(f"E73 — CME gap · {len(G)} fines de semana · {G.index[0].date()}->{G.index[-1].date()}")
    print(f"gap weekend: media {G.gap.mean()*100:+.2f}% · |gap| medio {G.gap.abs().mean()*100:.2f}% · "
          f"std {G.gap.std()*100:.2f}%\n")

    TAKER = config.TAKER_FEE
    print(f"{'horizonte':>9s} │ {'n':>3s} {'win%':>5s} {'ret/op':>7s} {'ret-cost':>8s} {'Sharpe':>6s} {'ann%':>6s} {'fill%':>5s}")
    print("─"*72)
    for H in (12, 24, 48, 72, 120):
        rr = []
        fills = 0
        for t, r in G.iterrows():
            loc = btc.index.get_indexer([t])[0]
            if loc < 0 or loc + H >= len(btc): continue
            entry = btc.iloc[loc]; exitp = btc.iloc[loc + H]
            fade = -np.sign(r.gap)
            ret = fade * (exitp / entry - 1.0) - 2 * TAKER       # entrada+salida taker
            rr.append(ret)
            # ¿se rellenó el gap (precio tocó fri_px) dentro de H?
            seg = btc.iloc[loc:loc + H + 1]
            if r.gap > 0 and (seg.min() <= r.fri_px): fills += 1
            elif r.gap < 0 and (seg.max() >= r.fri_px): fills += 1
        rr = pd.Series(rr); n = len(rr)
        if n < 20: continue
        sh = rr.mean() / rr.std() * np.sqrt(52) if rr.std() > 0 else 0
        print(f"{H:>7d}h │ {n:>3d} {(rr>0).mean()*100:>4.0f}% {rr.mean()*100:>6.2f}% "
              f"{rr.mean()*100:>7.2f}% {sh:>6.2f} {rr.mean()*52*100:>5.1f}% {fills/n*100:>4.0f}%")
    print("\nVEREDICTO: viable solo si el fade da Sharpe claramente >0 y ann% material TRAS costo. Si ~0 o")
    print("negativo → CME gap NO es edge explotable (la 'fill rate' alta puede ser solo mean-reversion trivial).")

if __name__ == "__main__":
    main()
