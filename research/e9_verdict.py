"""
E9 — VEREDICTO. Prueba honesta (walk-forward / mecánico) de 3 vías:
  T1 stat-arb DIVERSIFICADO walk-forward (más pares, ¿la diversificación lo salva?)
  T2 CARRY con vol-target (¿se vuelve usable bajando el maxDD?)
  T3 TREND/momentum cross-seccional LENTO walk-forward (mecánico, sin selección)
Imprime el Sharpe IS/OOS de cada uno → ¿hay ALGÚN edge robusto?

python research/e9_verdict.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa
from kepler.alphas import statarb_select
import e8_statarb_rolling as e8
import e4_carry as e4
from kepler.backtest_portfolio import load_1h, rolling_beta, simulate, metrics as bt_metrics


def sh(r, ppy):
    r = r.dropna()
    return r.mean()/r.std()*np.sqrt(ppy) if len(r) > 20 and r.std() > 0 else 0.0


def t1_statarb_diversified():
    logp = e8.load_logp(); N = len(logp); rets = []; npl = []
    for seg in range(e8.TRAIN_H, N, e8.RESEL_H):
        lo, hi = seg, min(seg + e8.RESEL_H, N)
        train = logp.iloc[seg - e8.TRAIN_H:seg].dropna(axis=1, thresh=int(0.9*e8.TRAIN_H)).dropna()
        if train.shape[1] < 4:
            continue
        pairs = statarb_select(train, pmax=0.05, min_corr=0.60, max_pairs=40)  # MÁS pares
        npl.append(len(pairs))
        if not pairs:
            continue
        prs = [e8.pair_returns(logp, p["a"], p["b"], p["beta"], lo, hi) for p in pairs]
        rets.append(pd.concat(prs, axis=1).mean(axis=1))
    port = pd.concat(rets).sort_index()
    port.index = pd.to_datetime(port.index, unit="ms", utc=True)
    cut = int(len(port)*0.5)
    return dict(sharpe=sh(port, 8760), is_=sh(port.iloc[:cut], 8760), oos=sh(port.iloc[cut:], 8760),
                extra=f"pares med {int(np.median(npl))}")


def t2_carry_voltarget():
    F, Px = e4.load_panels()
    r, _, _ = e4.run(F, Px, step=6, cost_rate=config.MAKER_FEE, cap=config.MAX_WEIGHT_NORMAL)
    r.index = pd.to_datetime(F.index[:len(r)] if False else
                             pd.to_datetime(r.index)) if not isinstance(r.index, pd.DatetimeIndex) else r.index
    # vol-target: escala por vol trailing (20 periodos), sin lookahead
    tv = r.rolling(20).std().shift(1)
    target = r.std()                       # objetivo = vol media
    lev = (target / tv).clip(0, 3).fillna(1.0)
    rs = (r * lev).dropna()
    eq = (1+rs).cumprod(); dd = (eq/eq.cummax()-1).min()
    eq0 = (1+r).cumprod(); dd0 = (eq0/eq0.cummax()-1).min()
    cut = int(len(rs)*0.7)
    return dict(sharpe=sh(rs, 1095), is_=sh(rs.iloc[:cut], 1095), oos=sh(rs.iloc[cut:], 1095),
                extra=f"maxDD {dd*100:.0f}% (vs {dd0*100:.0f}% sin gate)")


def t3_trend_slow():
    C, ret = load_1h(); beta = rolling_beta(ret)
    best = None
    for H in (168, 336, 720):   # 1, 2, 4 semanas
        net, turn = simulate(ret, beta, lookback=H, hold=H, cost_rate=config.MAKER_FEE,
                             cap=config.MAX_WEIGHT_NORMAL, alpha="momentum")
        m = bt_metrics(net, H)
        if m is None:
            continue
        cut = int(len(net)*0.7)
        d = dict(H=H, sharpe=m["sharpe"], is_=bt_metrics(net.iloc[:cut], H)["sharpe"],
                 oos=bt_metrics(net.iloc[cut:], H)["sharpe"])
        if best is None or d["sharpe"] > best["sharpe"]:
            best = d
    best["extra"] = f"mejor lookback {best['H']}h"
    return best


def main():
    print("Corriendo veredicto (T1 stat-arb diversif. walk-fwd, T2 carry vol-target, T3 trend lento)...\n")
    rows = [("T1 stat-arb diversificado WF", t1_statarb_diversified()),
            ("T2 carry + vol-target",         t2_carry_voltarget()),
            ("T3 trend cross-seccional lento", t3_trend_slow())]
    print("=" * 84)
    print("  E9 — VEREDICTO: ¿hay algún edge ROBUSTO? (Sharpe IS vs OOS)")
    print("=" * 84)
    print(f"  {'vía':32s} {'Sharpe':>7s} {'IS':>6s} {'OOS':>6s}   detalle")
    for name, d in rows:
        print(f"  {name:32s} {d['sharpe']:+7.2f} {d['is_']:+6.2f} {d['oos']:+6.2f}   {d.get('extra','')}")
    print("=" * 84)


if __name__ == "__main__":
    main()
