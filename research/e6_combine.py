"""
E6 — COMBINACIÓN de sleeves validados (carry + stat-arb) en una cartera.
Resamplea cada sleeve a retornos diarios, mide la CORRELACIÓN entre ellos (clave de la
diversificación), combina con vol-parity (pesos por IS, sin lookahead) y reporta el
Sharpe del conjunto + curva de leverage (→ retorno mensual vs ancla de riesgo).

python research/e6_combine.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # research/
import config  # noqa: E402
import e4_carry, e5_statarb  # noqa: E402


def daily(series: pd.Series) -> pd.Series:
    """Equity en grid nativo → retornos diarios."""
    eq = (1 + series).cumprod()
    d = eq.resample("1D").last().ffill()
    return d.pct_change().dropna()


def carry_daily():
    F, Px = e4_carry.load_panels()
    r, _, _ = e4_carry.run(F, Px, step=6, cost_rate=config.MAKER_FEE,
                           cap=config.MAX_WEIGHT_NORMAL, smooth=1)
    return daily(r)


def statarb_daily():
    logp = e5_statarb.load_logp()
    logp.index = pd.to_datetime(logp.index, unit="ms", utc=True)
    cut = int(len(logp) * 0.70)
    pairs = e5_statarb.select_pairs(logp.iloc[:cut], pmax=0.01, min_corr=0.80)
    port = None
    for p in pairs:
        rr, tn = e5_statarb.backtest_pair(logp, p[1], p[2], p[3])
        net = rr - tn * config.MAKER_FEE
        port = net if port is None else port.add(net, fill_value=0)
    port /= max(len(pairs), 1)
    return daily(port), len(pairs)


def metrics(r, lev=1.0):
    r = (r * lev).dropna()
    if len(r) < 30:
        return None
    sh = r.mean() / r.std() * np.sqrt(365)
    ann = (1 + r.mean()) ** 365 - 1
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    return dict(sharpe=sh, ann=ann * 100, vol=r.std() * np.sqrt(365) * 100, dd=dd * 100,
                mo_med=m.median() * 100, mo_pos=(m > 0).mean() * 100, mo_worst=m.min() * 100)


def show(label, r):
    m = metrics(r)
    if not m:
        print(f"  {label:24s} insuf."); return
    cut = int(len(r) * 0.7); mi, mo = metrics(r.iloc[:cut]), metrics(r.iloc[cut:])
    print(f"  {label:24s} Sh={m['sharpe']:+5.2f} ann={m['ann']:+6.1f}% vol={m['vol']:4.1f}% "
          f"DD={m['dd']:6.1f}% mo_med={m['mo_med']:+5.2f}% | IS={mi['sharpe']:+.2f} OOS={mo['sharpe']:+.2f}")


def main():
    print("Construyendo sleeves diarios...")
    c = carry_daily()
    s, npairs = statarb_daily()
    df = pd.concat({"carry": c, "statarb": s}, axis=1).dropna()
    print(f"Días alineados: {len(df)}  | stat-arb pares: {npairs}\n")
    print("=" * 88)
    print("  E6 — COMBINACIÓN carry + stat-arb (vol-parity, pesos por IS)")
    print("=" * 88)
    show("carry (solo)", df["carry"])
    show("stat-arb (solo)", df["statarb"])
    corr = df["carry"].corr(df["statarb"])
    print(f"\n  CORRELACIÓN carry↔stat-arb: {corr:+.3f}  "
          f"({'baja → diversifica bien' if abs(corr) < 0.3 else 'alta → poca diversificación'})")

    # vol-parity con vol de IS (sin lookahead)
    cut = int(len(df) * 0.70)
    vc, vs = df["carry"].iloc[:cut].std(), df["statarb"].iloc[:cut].std()
    wc, ws = (1 / vc), (1 / vs)
    tot = wc + ws; wc, ws = wc / tot, ws / tot
    combo = wc * df["carry"] + ws * df["statarb"]
    print(f"  Pesos vol-parity: carry {wc:.2f} / stat-arb {ws:.2f}\n")
    show("COMBINADO (1x)", combo)

    print("\n  CURVA DE LEVERAGE (combinado) — retorno↔riesgo:")
    print(f"  {'lev':>4s} {'annRet%':>8s} {'vol%':>6s} {'maxDD%':>7s} {'mo_med%':>8s} {'mo+%':>5s} {'mo_worst%':>9s}")
    for L in (1, 2, 3, 4, 5):
        m = metrics(combo, lev=L)
        print(f"  {L:>3d}x {m['ann']:8.1f} {m['vol']:6.1f} {m['dd']:7.1f} {m['mo_med']:8.2f} {m['mo_pos']:5.0f} {m['mo_worst']:9.1f}")
    # leverage para ancla maxDD ~8%/mes ≈ buscar L donde mo_worst ~ -8%
    print("\n  Nota: el dial de leverage se fija para que el peor mes respete el ancla (~−8%).")
    print("=" * 88)


if __name__ == "__main__":
    main()
