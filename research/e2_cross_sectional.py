"""
E2 — Descubrimiento de ALPHAS cross-seccionales (market-neutral).
Quita el factor BTC (residuo = r_i - β_i·r_BTC, β rolling) y mide qué señales
predicen el retorno RESIDUAL futuro (lo que captura una cartera beta-neutral).

Para cada señal × horizonte: IC (rank-corr señal vs fwd-residuo), IC_IR (estabilidad),
y el retorno del spread long-top/short-bottom (tercil). IS/OOS.

python research/e2_cross_sectional.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

BETA_W = 168   # ventana rolling de beta (1 semana en 1h)


def load():
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    close, tb, vol = {}, {}, {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        df = pd.read_parquet(p, columns=["open_time","close","volume","taker_buy_volume"]).set_index("open_time")
        close[s] = df["close"]; tb[s] = df["taker_buy_volume"]; vol[s] = df["volume"]
    C = pd.DataFrame(close).sort_index()
    TB = pd.DataFrame(tb).reindex_like(C); V = pd.DataFrame(vol).reindex_like(C)
    return C, TB, V


def residuals(ret: pd.DataFrame, driver="BTCUSDT"):
    rd = ret[driver]
    cov = ret.rolling(BETA_W).cov(rd)
    var = rd.rolling(BETA_W).var()
    beta = cov.div(var, axis=0).clip(-3, 3)            # β acotada (estabilidad)
    resid = (ret - beta.mul(rd, axis=0)).clip(-0.15, 0.15)  # winsorizar residuo (anti-outlier)
    return resid, beta


def ic_study(signal: pd.DataFrame, fwd: pd.DataFrame, step: int, cut: int):
    """IC por rebalanceo (spearman cross-seccional) + spread tercil. Devuelve dict IS/OOS."""
    idx = range(BETA_W + 1, len(signal) - step, step)
    res = {"IS": [], "OOS": [], "ls_IS": [], "ls_OOS": []}
    for t in idx:
        s = signal.iloc[t]; f = fwd.iloc[t]
        d = pd.concat([s, f], axis=1).dropna()
        if len(d) < 8:
            continue
        ic = d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank())
        # long-short tercil
        k = max(1, len(d) // 3)
        order = d.iloc[:, 0].sort_values()
        ls = d.loc[order.index[-k:], d.columns[1]].mean() - d.loc[order.index[:k], d.columns[1]].mean()
        tag = "IS" if t <= cut else "OOS"
        res[tag].append(ic); res["ls_" + tag].append(ls)
    def agg(a):
        a = [x for x in a if np.isfinite(x)]
        return (np.mean(a), np.mean(a)/ (np.std(a)+1e-9), len(a)) if a else (0,0,0)
    ic_is, icir_is, n_is = agg(res["IS"]); ic_oos, icir_oos, _ = agg(res["OOS"])
    ls_is = np.mean(res["ls_IS"]) if res["ls_IS"] else 0
    ls_oos = np.mean(res["ls_OOS"]) if res["ls_OOS"] else 0
    return dict(ic_is=ic_is, ic_oos=ic_oos, icir_is=icir_is, icir_oos=icir_oos,
                ls_is=ls_is*100, ls_oos=ls_oos*100, n=n_is)


def main():
    C, TB, V = load()
    ret = np.log(C).diff()
    resid, beta = residuals(ret, "BTCUSDT")
    cut = int(len(ret) * 0.70)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h · residuo vs BTC (β rolling {BETA_W}h)\n")

    cvd = (2 * TB - V).rolling(6).sum() / V.rolling(6).sum().replace(0, np.nan) * 100

    for step in (4, 24):
        # fwd residual return acumulado sobre el próximo `step`
        fwd = resid.rolling(step).sum().shift(-step)
        past_raw = ret.rolling(step).sum()
        past_res = resid.rolling(step).sum()
        signals = {
            "reversal_raw   (-ret pasado)":   -past_raw,
            "momentum_raw   (+ret pasado)":   +past_raw,
            "reversal_resid (-resid pasado)": -past_res,
            "momentum_resid (+resid pasado)": +past_res,
            "cvd_flow       (taker imbalance)": cvd,
            "neg_cvd        (-taker imbalance)": -cvd,
        }
        print("=" * 96)
        print(f"  HORIZONTE / REBALANCEO = {step}h   (fwd = retorno RESIDUAL próximas {step}h)")
        print("=" * 96)
        print(f"  {'señal':32s} {'IC_IS':>7s} {'IC_OOS':>7s} {'ICIR_OOS':>8s} "
              f"{'LS_IS%':>7s} {'LS_OOS%':>7s} {'estable':>7s}")
        for name, sig in signals.items():
            r = ic_study(sig, fwd, step, cut)
            stable = "✓" if (np.sign(r["ic_is"]) == np.sign(r["ic_oos"]) and abs(r["ic_oos"]) > 0.02
                             and np.sign(r["ls_is"]) == np.sign(r["ls_oos"])) else ""
            print(f"  {name:32s} {r['ic_is']:+7.3f} {r['ic_oos']:+7.3f} {r['icir_oos']:+8.2f} "
                  f"{r['ls_is']:+7.3f} {r['ls_oos']:+7.3f} {stable:>7s}")
        print()


if __name__ == "__main__":
    main()
