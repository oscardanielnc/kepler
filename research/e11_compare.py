"""
E11 — COMPARACIÓN para decidir: Trend long-only (B) vs Neutral (A) vs Síntesis (A+B).
A = carry + momentum cross-seccional semanal (market-neutral, robustos).
B = trend long-only direccional (vol-target, skew positivo).
Presenta Sharpe/ann/vol/maxDD/skew/mensual + IS/OOS + correlaciones + curva de leverage.

python research/e11_compare.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa
import e6_combine as e6
import e10_trend as e10
from kepler.backtest_portfolio import load_1h, rolling_beta, simulate
from kepler.portfolio import vol_parity_weights, combine, metrics


def to_daily(net):
    eq = (1 + net).cumprod()
    return eq.resample("1D").last().ffill().pct_change().dropna()


def build_sleeves():
    carry = e6.carry_daily()
    C, ret = load_1h(); beta = rolling_beta(ret)
    net, _ = simulate(ret, beta, 168, 168, config.MAKER_FEE, config.MAX_WEIGHT_NORMAL, alpha="momentum")
    xsmom = to_daily(net)
    px, fund = e10.load_daily()
    trend, _, _ = e10.run(px, fund, 20, 100, allow_short=False)
    return carry, xsmom, trend


def line(label, r):
    m = metrics(r)
    if not m:
        print(f"  {label:26s} insuf."); return
    cut = int(len(r)*0.7); mi, mo = metrics(r.iloc[:cut]), metrics(r.iloc[cut:])
    sk = r.dropna().skew()
    print(f"  {label:26s} Sh={m['sharpe']:+5.2f} ann={m['ann']:+6.1f}% vol={m['vol']:4.1f}% "
          f"DD={m['maxdd']:6.1f}% skew={sk:+5.2f} mo_med={m['mo_med']:+5.2f}% mo+={m['mo_pos']:3.0f}% "
          f"| IS={mi['sharpe']:+.2f} OOS={mo['sharpe']:+.2f}")


def main():
    carry, xsmom, trend = build_sleeves()
    df = pd.concat({"carry": carry, "xsmom": xsmom, "trend": trend}, axis=1).dropna()
    print(f"Días alineados: {len(df)}  [{df.index[0].date()}→{df.index[-1].date()}]\n")

    # A = neutral (carry + xsmom)
    wA = vol_parity_weights(df[["carry", "xsmom"]])
    A = combine(df[["carry", "xsmom"]], wA)
    B = df["trend"]
    AB_df = pd.concat({"A": A, "B": B}, axis=1).dropna()
    wAB = vol_parity_weights(AB_df)
    AB = combine(AB_df, wAB)

    print("=" * 104)
    print("  E11 — DECISIÓN: componentes y carteras")
    print("=" * 104)
    line("carry", df["carry"])
    line("xs-momentum (neutral)", df["xsmom"])
    line("trend long-only (B)", B)
    print("  " + "-"*100)
    line("A = NEUTRAL (carry+xsmom)", A)
    line("A+B = SÍNTESIS", AB)

    print("\n  CORRELACIONES:")
    cc = pd.concat({"carry": df["carry"], "xsmom": df["xsmom"], "trend": B}, axis=1).corr()
    print(cc.round(2).to_string())

    print(f"\n  Pesos vol-parity → A: {wA.round(2).to_dict()} | A+B: {wAB.round(2).to_dict()}")

    print("\n  CURVA DE LEVERAGE (ann% / maxDD% / mo_med%):")
    print(f"  {'lev':>4s} | {'TREND B':>22s} | {'A NEUTRAL':>22s} | {'A+B SÍNTESIS':>22s}")
    for L in (1, 2, 3):
        def fmt(r):
            m = metrics(r*L); return f"{m['ann']:+6.1f}/{m['maxdd']:6.1f}/{m['mo_med']:+5.2f}"
        print(f"  {L:>3d}x | {fmt(B):>22s} | {fmt(A):>22s} | {fmt(AB):>22s}")

    # math del edge trend (BTC)
    px, fund = e10.load_daily()
    _, pos, ret = e10.run(px, fund, 20, 100, allow_short=False)
    ts = e10.trade_stats(pos, ret)
    print(f"\n  Math edge trend (BTC long-only): {ts['n']} trades · WR {ts['wr']:.0f}% · "
          f"payoff {ts['payoff']:.2f}x · avg_win {ts['avg_w']:+.1f}% / avg_loss {ts['avg_l']:+.1f}%")
    print("=" * 104)


if __name__ == "__main__":
    main()
