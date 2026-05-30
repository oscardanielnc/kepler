"""
E12 — Validación del XS-MOMENTUM sobre historia larga (4+ años).
El panel de 32 se truncaba a ~2a por los coins nuevos. Aquí uso solo activos con
historia larga (>=3.9a) → panel ~4.4a. Mide Sharpe/skew/maxDD, IS/OOS y Sharpe POR AÑO
(consistencia), y compara contra incluir los explosivos (¿el edge era tail/lotería?).

python research/e12_xsmom_validate.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler.backtest_portfolio import rolling_beta, simulate, metrics

MIN_BARS_LONG = 34000   # ~3.9 años


def load_subset(long_only=True):
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    cl = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        df = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
        if long_only and len(df) < MIN_BARS_LONG:
            continue
        cl[s] = df
    C = pd.DataFrame(cl).sort_index().dropna()
    return C, np.log(C).diff()


def per_year_sharpe(net):
    s = net.copy(); s.index = pd.to_datetime(s.index, utc=True)
    out = {}
    for y, g in s.groupby(s.index.year):
        if len(g) > 20 and g.std() > 0:
            out[y] = g.mean()/g.std()*np.sqrt(len(g)/((g.index[-1]-g.index[0]).days/365+1e-9))
    return out


def report(tag, ret, beta, alpha, H):
    net, turn = simulate(ret, beta, H, H, config.MAKER_FEE, config.MAX_WEIGHT_NORMAL, alpha=alpha)
    m = metrics(net, H)
    if not m:
        print(f"  {tag:34s} insuf."); return
    cut = int(len(net)*0.6)
    mi, mo = metrics(net.iloc[:cut], H), metrics(net.iloc[cut:], H)
    sk = net.dropna().skew()
    py = per_year_sharpe(net)
    pys = " ".join(f"{y}:{v:+.1f}" for y, v in py.items())
    print(f"  {tag:34s} Sh={m['sharpe']:+5.2f} ann={m['ann_ret']:+6.0f}% DD={m['maxdd']:6.0f}% "
          f"skew={sk:+5.1f} | IS={mi['sharpe']:+.2f} OOS={mo['sharpe']:+.2f} | x año [{pys}]")


def main():
    Cl, retl = load_subset(long_only=True)
    Cf, retf = load_subset(long_only=False)
    print(f"Panel LARGO: {Cl.shape[1]} activos · {Cl.shape[0]} barras "
          f"[{pd.to_datetime(Cl.index[0],unit='ms').date()}→{pd.to_datetime(Cl.index[-1],unit='ms').date()}]")
    print(f"Panel COMPLETO (con nuevos): {Cf.shape[1]} activos · {Cf.shape[0]} barras\n")
    bl = rolling_beta(retl); bf = rolling_beta(retf)

    print("=" * 112)
    print("  XS-MOMENTUM — PANEL LARGO (~4.4a, solo monedas establecidas, SIN memecoins nuevos)")
    print("=" * 112)
    for H in (168, 336, 720):
        report(f"momentum {H}h ({H//24}d)", retl, bl, "momentum", H)
    print("  (contraste) reversal:")
    for H in (168, 336):
        report(f"reversal {H}h", retl, bl, "reversal", H)

    print("\n" + "=" * 112)
    print("  XS-MOMENTUM — PANEL COMPLETO (~2a, INCLUYE explosivos) — ¿cuánto era tail/lotería?")
    print("=" * 112)
    for H in (168, 336):
        report(f"momentum {H}h (con nuevos)", retf, bf, "momentum", H)
    print("=" * 112)


if __name__ == "__main__":
    main()
