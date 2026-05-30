"""
E3b — ¿Se puede volver NET-POSITIVO el reversal bajando el turnover?
Prueba concentración (top_k), banda de no-trade y suavizado, vs baseline. IS/OOS.
python research/e3b_turnover.py
"""
from __future__ import annotations
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.backtest_portfolio import load_1h, rolling_beta, simulate, metrics


def line(label, net, turn, H):
    m = metrics(net, H)
    if m is None:
        print(f"  {label:38s} vacío"); return
    cut = int(len(net) * 0.70)
    mi, mo = metrics(net.iloc[:cut], H), metrics(net.iloc[cut:], H)
    print(f"  {label:38s} Sh={m['sharpe']:+5.2f} annRet={m['ann_ret']:+6.1f}% maxDD={m['maxdd']:6.1f}% "
          f"mo_med={m['mo_med']:+5.2f}% turn={turn:.2f} | IS_Sh={mi['sharpe']:+.2f} OOS_Sh={mo['sharpe']:+.2f}")


def main():
    C, ret = load_1h(); beta = rolling_beta(ret)
    cr = config.MAKER_FEE; cap = config.MAX_WEIGHT_NORMAL
    print(f"Universo {C.shape[1]} · costo maker {cr*100:.2f}%/turnover\n")
    for H in (24, 48):
        print("=" * 100)
        print(f"  HORIZONTE {H}h — reductores de turnover (objetivo: NET-POSITIVO estable)")
        print("=" * 100)
        line("baseline (todos los nombres)", *simulate(ret, beta, H, H, cr, cap), H)
        for k in (3, 5):
            line(f"top_k={k} (concentrado)", *simulate(ret, beta, H, H, cr, cap, top_k=k), H)
        for bnd in (0.03, 0.06):
            line(f"no-trade band={bnd}", *simulate(ret, beta, H, H, cr, cap, band=bnd), H)
        for sp in (3, 6):
            line(f"smooth EWMA span={sp}", *simulate(ret, beta, H, H, cr, cap, smooth_span=sp), H)
        # combos
        line("top_k=5 + band=0.06", *simulate(ret, beta, H, H, cr, cap, top_k=5, band=0.06), H)
        line("top_k=5 + smooth=6 + band=0.06",
             *simulate(ret, beta, H, H, cr, cap, top_k=5, band=0.06, smooth_span=6), H)
        print()
    # mejor combo: barrido fino de costo (maker rebate 0% vs 0.02% vs taker 0.04%)
    print("=" * 100)
    print("  SENSIBILIDAD A COSTO — top_k=5 + band=0.06 + smooth=6 @ 24h")
    print("=" * 100)
    for c, lbl in ((0.0, "maker rebate 0.00%"), (0.0002, "maker 0.02%"), (0.0004, "taker 0.04%")):
        line(lbl, *simulate(ret, beta, 24, 24, c, cap, top_k=5, band=0.06, smooth_span=6), 24)


if __name__ == "__main__":
    main()
