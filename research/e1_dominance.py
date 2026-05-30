"""
E1 — Estudio de DOMINANCIA / LEAD-LAG.  ¿Quién dirige a quién? ¿Se puede predecir
un alt desde su driver (BTC/ETH)? ¿Qué follower amplifica más?

Sobre 1h reales del universo. Para cada (driver, follower):
  - beta contemporánea + R² (cuánto del alt explica el driver)
  - lead-lag: corr(r_follower[t], r_driver[t-L]) para L=1..6h → mejor lag y su corr
  - dirección de liderazgo: compara driver→follower vs follower→driver
  - amplificación: pendiente de r_f[t] sobre r_driver[t-L*] (cuánto amplifica)
  - estabilidad IS/OOS (split 70/30)

python research/e1_dominance.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

MAX_LAG = 6   # horas


def load_returns():
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    series = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        sym = os.path.basename(p)[:-8]
        df = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
        series[sym] = df
    if not series:
        raise SystemExit(f"Sin datos en {d}. Corre primero: python -m kepler.fetch 1h")
    px = pd.DataFrame(series).sort_index()
    ret = np.log(px).diff()
    return ret.dropna(how="all")


def lead_lag(rf: pd.Series, rd: pd.Series, max_lag=MAX_LAG):
    """corr(rf[t], rd[t-L]) para L=0..max_lag. Devuelve (mejor_lag, corr, contemp_corr)."""
    best_lag, best = 0, 0.0
    contemp = rf.corr(rd)
    for L in range(0, max_lag + 1):
        c = rf.corr(rd.shift(L))
        if abs(c) > abs(best):
            best, best_lag = c, L
    return best_lag, best, contemp


def beta(rf: pd.Series, rd: pd.Series, lag=0):
    x = rd.shift(lag); df = pd.concat([rf, x], axis=1).dropna()
    if len(df) < 100 or df.iloc[:, 1].var() == 0:
        return np.nan, np.nan
    b = df.cov().iloc[0, 1] / df.iloc[:, 1].var()
    r2 = df.corr().iloc[0, 1] ** 2
    return b, r2


def main():
    ret = load_returns()
    syms = list(ret.columns)
    n = len(ret); cut = int(n * 0.70)
    print(f"Universo: {len(syms)} símbolos · {n} barras 1h alineadas\n")

    print("=" * 100)
    print("  E1 — DOMINANCIA / LEAD-LAG (drivers: BTC, ETH)")
    print("=" * 100)
    rows = []
    for driver in config.DRIVERS:
        if driver not in ret:
            continue
        rd = ret[driver]
        print(f"\n  ── Driver: {driver} ──")
        print(f"  {'follower':10s} {'β0':>6s} {'R²':>5s} {'lag*':>4s} {'corr_lag':>8s} "
              f"{'β@lag':>6s} {'IScorr':>7s} {'OOScorr':>7s} {'estable':>7s}")
        for f in syms:
            if f == driver:
                continue
            rf = ret[f]
            b0, r2 = beta(rf, rd, 0)
            lag, c, _ = lead_lag(rf, rd)
            blag, _ = beta(rf, rd, lag)
            # estabilidad: corr al mejor lag en IS vs OOS
            is_c = rf.iloc[:cut].corr(rd.shift(lag).iloc[:cut])
            oos_c = rf.iloc[cut:].corr(rd.shift(lag).iloc[cut:])
            stable = "✓" if (np.sign(is_c) == np.sign(oos_c) and abs(oos_c) > 0.05 and lag >= 1) else ""
            print(f"  {f:10s} {b0:6.2f} {r2:5.2f} {lag:4d} {c:8.3f} {blag:6.2f} "
                  f"{is_c:7.3f} {oos_c:7.3f} {stable:>7s}")
            if lag >= 1:
                rows.append((driver, f, lag, c, blag, is_c, oos_c, r2))

    print("\n" + "=" * 100)
    print("  RANKING — followers con LEAD-LAG real (lag≥1h, corr estable IS/OOS)")
    print("  → candidatos a 'operar la dominada amplificada' (mayor β@lag = más amplifica)")
    print("=" * 100)
    cand = [r for r in rows if np.sign(r[5]) == np.sign(r[6]) and abs(r[6]) > 0.05]
    cand.sort(key=lambda r: abs(r[6]) * abs(r[4]), reverse=True)
    print(f"  {'driver':8s} {'follower':10s} {'lag':>4s} {'corr':>7s} {'amplif β':>9s} "
          f"{'OOScorr':>7s}")
    for d, f, lag, c, blag, isc, oosc, r2 in cand[:15]:
        print(f"  {d:8s} {f:10s} {lag:4d}h {c:7.3f} {blag:9.2f} {oosc:7.3f}")
    if not cand:
        print("  (ninguno con lead-lag estable a 1h — probar lags sub-hora con 1m/5m)")

    # ¿Cuánto explica BTC al universo? (factor)
    print("\n  Factor BTC — R² contemporáneo medio del universo:")
    if "BTCUSDT" in ret:
        r2s = [beta(ret[f], ret["BTCUSDT"], 0)[1] for f in syms if f != "BTCUSDT"]
        r2s = [x for x in r2s if not np.isnan(x)]
        print(f"    R² medio={np.mean(r2s):.2f}  (BTC explica ~{np.mean(r2s)*100:.0f}% del retorno de un alt)")
    print("=" * 100)


if __name__ == "__main__":
    main()
