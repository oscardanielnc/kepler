"""
E1b — LEAD-LAG SUB-HORA en 5m. ¿BTC/ETH lideran a los alts a 5-60 min?
(E1 mostró que a 1h todo es contemporáneo; el timing-edge, si existe, es sub-hora.)

Para cada (driver, follower): corr(r_f[t], r_driver[t-L]) con L=0..12 barras de 5m
(0-60 min). Si el mejor lag ≥1 y es estable IS/OOS → hay timing explotable.

python research/e1b_leadlag_5m.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

MAX_LAG = 12   # barras de 5m → 60 min


def load_returns():
    d = os.path.join(config.DATA_DIR, "futures_um", "5m")
    series = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        series[s] = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
    if not series:
        raise SystemExit(f"Sin datos 5m en {d}. Corre: python -m kepler.fetch 5m")
    px = pd.DataFrame(series).sort_index()
    return np.log(px).diff().dropna(how="all")


def main():
    ret = load_returns()
    syms = list(ret.columns); n = len(ret); cut = int(n * 0.70)
    print(f"Universo {len(syms)} · {n} barras 5m · lags 0-{MAX_LAG*5}min\n")
    rows = []
    for driver in config.DRIVERS:
        if driver not in ret:
            continue
        rd = ret[driver]
        print(f"  ── Driver {driver} ──")
        print(f"  {'follower':10s} {'lag*(min)':>9s} {'corr':>7s} {'contemp':>8s} "
              f"{'IScorr':>7s} {'OOScorr':>7s} {'estable':>7s}")
        for f in syms:
            if f == driver:
                continue
            rf = ret[f]
            contemp = rf.corr(rd)
            best_lag, best = 0, 0.0
            for L in range(1, MAX_LAG + 1):
                c = rf.corr(rd.shift(L))
                if abs(c) > abs(best):
                    best, best_lag = c, L
            isc = rf.iloc[:cut].corr(rd.shift(best_lag).iloc[:cut])
            oosc = rf.iloc[cut:].corr(rd.shift(best_lag).iloc[cut:])
            # ¿el lag>0 aporta sobre el contemporáneo? (timing real)
            stable = "✓" if (best_lag >= 1 and abs(best) > 0.04
                             and np.sign(isc) == np.sign(oosc) and abs(oosc) > 0.03) else ""
            print(f"  {f:10s} {best_lag*5:9d} {best:7.3f} {contemp:8.3f} {isc:7.3f} {oosc:7.3f} {stable:>7s}")
            if stable:
                rows.append((driver, f, best_lag*5, best, oosc))
    print("\n  RANKING lead-lag sub-hora explotable (lag≥5min, estable):")
    for d, f, lagmin, c, oosc in sorted(rows, key=lambda r: abs(r[4]), reverse=True):
        print(f"    {d}→{f:10s} lag={lagmin}min corr={c:.3f} OOS={oosc:.3f}")
    if not rows:
        print("    (ninguno — el co-movimiento es ~instantáneo incluso a 5m; el alpha")
        print("     amplificado sería contemporáneo/condicional al driver, no de timing)")


if __name__ == "__main__":
    main()
