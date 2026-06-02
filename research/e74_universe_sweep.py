"""
E74 — BARRIDO SISTEMÁTICO DE UNIVERSO LIMPIO (LOO por moneda). (2026-06-02)
Generaliza e53 (que probó solo las finas hardcodeadas) a TODO el universo operado (20 coins de historia
larga). Pregunta (regla de oro): ¿hay MÁS monedas cuya retirada MEJORA el %/mes neto de coste realista
Y el OOS, sin perder edge? (achicar a universo limpio; ampliar ya se descartó e17).

Método: reúsa e53.build_system (7-sleeves, trend capado, ancla+haircut, slippage ADV por-símbolo).
Para cada coin: drop LOO bajo coste FLAT (solo edge) y REALISTA (edge−slip). Δ>0 = retirar mejora.
Disciplina e50: una coin se retira solo si mejora REAL **y** no empeora OOS (los "estorbadores" de IS
no generalizan). No toca producción. python -m research.e74_universe_sweep
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from kepler.engine import load, load_panel, DRIVER
from kepler.portfolio import metrics
from research.e18_slippage import adv_usd
from research.e53_thin_coins import build_system, slip_adv


def half_sh(combo):
    h = len(combo)//2
    return metrics(combo.iloc[:h]).get("sharpe", float("nan")), metrics(combo.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E74 — barrido LOO de universo limpio (¿qué moneda conviene retirar?)\n")
    Cfull = load()
    panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], Cfull)
    adv = adv_usd(panels["quote_volume"]).reindex(Cfull.columns).fillna(0.0)
    adv_M = (adv/1e6).clip(lower=1.0)
    sl_bps = (slip_adv(adv_M, list(Cfull.columns)) * 1e4)
    coins = [c for c in Cfull.columns if c != DRIVER]   # no quitar BTC (driver/hedge)

    base_f = build_system(Cfull, panels, adv_M, drop=(), slip_mult=None)
    base_r = build_system(Cfull, panels, adv_M, drop=(), slip_mult=1.0)
    b1, b2 = half_sh(base_r["combo"])
    print(f"BASELINE ({base_f['n']} coins · {Cfull.index[0].date()}->{Cfull.index[-1].date()}):")
    print(f"  REAL {base_r['mes']:.2f}%/mes · Sh {base_r['sharpe']:.2f} · IS/OOS {b1:.2f}/{b2:.2f} · maxDD {base_r['maxdd']:.1f}\n")

    print("LOO por moneda (Δ%/mes vs baseline; >0 = quitar MEJORA). slip = bps modelado del símbolo.")
    print(f"{'quitar':>10s} {'slip':>5s} │ {'FLAT Δ':>7s} {'REAL Δ':>7s} │ {'REAL %/mes':>10s} {'Sh':>5s} {'IS/OOS':>11s} {'maxDD':>6s}  veredicto")
    print("─"*100)
    res = []
    for c in coins:
        rf = build_system(Cfull, panels, adv_M, drop=(c,), slip_mult=None)
        rr = build_system(Cfull, panels, adv_M, drop=(c,), slip_mult=1.0)
        df_, dr = rf["mes"]-base_f["mes"], rr["mes"]-base_r["mes"]
        s1, s2 = half_sh(rr["combo"])
        # retirar SOLO si mejora REAL y no daña OOS (vs baseline OOS)
        if dr > 0.05 and s2 >= b2 - 0.02:
            verd = "← RETIRAR (mejora real+OOS)"
        elif dr > 0.05:
            verd = "~ mejora IS, OOS peor (cuidado)"
        elif abs(dr) <= 0.05:
            verd = "neutral"
        else:
            verd = "MANTENER (aporta)"
        res.append((dr, c))
        print(f"{c.replace('USDT',''):>10s} {sl_bps[c]:>4.1f} │ {df_:>+6.2f}% {dr:>+6.2f}% │ {rr['mes']:>9.2f}% {rr['sharpe']:>5.2f} {s1:>5.2f}/{s2:<5.2f} {rr['maxdd']:>6.1f}  {verd}")

    res.sort(reverse=True)
    top = ", ".join("%s%+.2f" % (c.replace("USDT", ""), d) for d, c in res[:5])
    print("\nTOP candidatos a retirar (mayor Δ REAL): " + top)
    print("REGLA (e50): retirar solo si Δreal>0 Y OOS no empeora. Si nada cumple → universo ya está limpio.")


if __name__ == "__main__":
    main()
