"""
E3a — Motor de backtest de PORTAFOLIO (market-neutral) + baseline del reversal.

Pipeline honesto:
  scores de alpha (por activo) → pesos dollar-neutral, β-neutral (hedge BTC), gross-norm,
  cap por nombre → simulación con costos de TURNOVER → Sharpe/Calmar/maxDD/turnover NETOS.
  Sin lookahead: β rolling, score con datos hasta t, retorno realizado t→t+H.

El Sharpe es invariante al leverage → es el número que perseguimos. El retorno absoluto
sale de Sharpe × vol; un barrido de gross (leverage) da la curva retorno-vs-maxDD (punto óptimo).

python -m kepler.backtest_portfolio
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

BETA_W   = 168     # ventana β rolling (1 semana en 1h)
DRIVER   = "BTCUSDT"


def load_1h():
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    cl = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        cl[s] = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
    C = pd.DataFrame(cl).sort_index()
    ret = np.log(C).diff()
    return C, ret


def rolling_beta(ret: pd.DataFrame, driver=DRIVER):
    rd = ret[driver]
    beta = ret.rolling(BETA_W).cov(rd).div(rd.rolling(BETA_W).var(), axis=0)
    return beta.clip(-3, 3)


def simulate(ret: pd.DataFrame, beta: pd.DataFrame, lookback: int, hold: int,
             cost_rate: float, cap: float, alpha="reversal",
             top_k: int | None = None, band: float = 0.0, smooth_span: int = 0):
    """Serie de retornos NETOS por rebalanceo (gross=1) + turnover medio.
    Reductores de turnover: top_k (solo K nombres por lado), band (no-trade si el cambio
    de peso < band), smooth_span (EWMA del score en el tiempo)."""
    syms = [s for s in ret.columns if s != DRIVER]
    R = ret[syms]; B = beta[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold))
    fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    past = R.rolling(lookback).sum()
    if smooth_span:
        past = past.ewm(span=smooth_span).mean()

    idx = list(range(BETA_W + lookback, len(R) - hold, hold))
    prev_w = pd.Series(0.0, index=syms); prev_h = 0.0
    rets, ts, turns = [], [], []
    for t in idx:
        s = past.iloc[t]; b = B.iloc[t]
        valid = s.notna() & b.notna()
        if valid.sum() < 8:
            continue
        s = s[valid]; b = b[valid]
        score = (-s if alpha == "reversal" else s) - (-s if alpha == "reversal" else s).mean()
        if top_k:                                           # concentrar en los K extremos por lado
            keep = pd.concat([score.nlargest(top_k), score.nsmallest(top_k)])
            score = score.where(score.index.isin(keep.index), 0.0)
        if score.abs().sum() == 0:
            continue
        w = (score / score.abs().sum()).clip(-cap, cap)
        if w.abs().sum() > 0:
            w = w / w.abs().sum()
        w_full = w.reindex(syms).fillna(0.0)
        if band > 0:                                        # banda de no-trade
            mask = (w_full - prev_w).abs() < band
            w_full = w_full.where(~mask, prev_w)
        h = -float((w_full * B.iloc[t].reindex(syms).fillna(0)).sum())
        f = fwd.iloc[t].reindex(syms).fillna(0)
        port = float((w_full * f).sum()) + h * float(fwd_d.iloc[t] or 0.0)
        turn = float((w_full - prev_w).abs().sum()) + abs(h - prev_h)
        rets.append(port - turn * cost_rate); ts.append(R.index[t]); turns.append(turn)
        prev_w, prev_h = w_full, h
    return pd.Series(rets, index=pd.to_datetime(ts, unit="ms", utc=True)), float(np.mean(turns))


def metrics(net: pd.Series, hold_h: int, gross: float = 1.0):
    r = net * gross
    if len(r) < 10:
        return None
    ppy = 8760 / hold_h
    mean, sd = r.mean(), r.std()
    sharpe = mean / sd * np.sqrt(ppy) if sd > 0 else 0.0
    ann_ret = (1 + mean) ** ppy - 1
    ann_vol = sd * np.sqrt(ppy)
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    calmar = ann_ret / abs(dd) if dd < 0 else float("inf")
    # mensual
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    return dict(n=len(r), sharpe=sharpe, ann_ret=ann_ret*100, ann_vol=ann_vol*100,
                maxdd=dd*100, calmar=calmar, mo_med=m.median()*100,
                mo_pos=(m > 0).mean()*100, mo_worst=m.min()*100, mo_best=m.max()*100)


def main():
    C, ret = load_1h()
    beta = rolling_beta(ret)
    cut_frac = 0.70
    print(f"Universo {C.shape[1]} · {C.shape[0]} barras 1h · β-neutral vs {DRIVER}\n")
    print("=" * 100)
    print("  E3a — BASELINE REVERSAL cross-seccional (β-neutral, gross=1, costo maker 0.02%/turnover)")
    print("=" * 100)
    print(f"  {'L/hold':>8s} {'n':>5s} {'Sharpe':>7s} {'annRet%':>8s} {'annVol%':>8s} "
          f"{'maxDD%':>7s} {'Calmar':>7s} {'mo_med%':>8s} {'mo+%':>5s} {'turn':>5s}")
    best = None
    for H in (4, 8, 24, 48):
        net, turn = simulate(ret, beta, lookback=H, hold=H, cost_rate=config.MAKER_FEE, cap=config.MAX_WEIGHT_NORMAL)
        mt = metrics(net, H)
        if mt is None:
            continue
        print(f"  {H:>6d}h {mt['n']:5d} {mt['sharpe']:7.2f} {mt['ann_ret']:8.1f} {mt['ann_vol']:8.1f} "
              f"{mt['maxdd']:7.1f} {mt['calmar']:7.2f} {mt['mo_med']:8.2f} {mt['mo_pos']:5.0f} {turn:5.2f}")
        if best is None or mt["sharpe"] > best[1]["sharpe"]:
            best = (H, mt, net)

    H, mt, net = best
    print(f"\n  Mejor horizonte: {H}h (Sharpe {mt['sharpe']:.2f}). IS/OOS:")
    cut = int(len(net) * cut_frac)
    for tag, seg in (("IS ", net.iloc[:cut]), ("OOS", net.iloc[cut:])):
        m = metrics(seg, H)
        print(f"    {tag}: Sharpe {m['sharpe']:.2f}  annRet {m['ann_ret']:.1f}%  maxDD {m['maxdd']:.1f}%  mo_med {m['mo_med']:.2f}%")

    print(f"\n  CURVA DEL PUNTO ÓPTIMO — barrido de leverage (gross) en el horizonte {H}h:")
    print(f"  {'gross':>6s} {'annRet%':>8s} {'annVol%':>8s} {'maxDD%':>7s} {'mo_med%':>8s} {'mo+%':>5s}")
    for g in (1, 2, 3, 4, 5, 6):
        m = metrics(net, H, gross=g)
        print(f"  {g:>5d}x {m['ann_ret']:8.1f} {m['ann_vol']:8.1f} {m['maxdd']:7.1f} {m['mo_med']:8.2f} {m['mo_pos']:5.0f}")
    print("\n  Nota: Sharpe es invariante al leverage; el barrido muestra retorno↔riesgo.")
    print("  El dial de leverage se elige para que maxDD mensual respete el ancla (~8%/mes).")
    print("=" * 100)


if __name__ == "__main__":
    main()
