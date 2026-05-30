"""
E4 — CARRY / funding harvest (market-neutral, bajo turnover).
Short los perps de funding ALTO / long los de funding BAJO (o negativo) → cobra el
spread de funding. β-neutral (hedge BTC). El funding es 'sticky' → turnover bajo.

P&L por periodo de 8h = price_pnl (≈0 si neutral) + funding cobrado − costos.
funding_pnl = -Σ wᵢ·fundingᵢ  (short funding+ cobra; long funding- cobra).
Sin lookahead: pesos con funding en t, funding cobrado en t+1 (sticky).

python research/e4_carry.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

DRIVER = "BTCUSDT"; BETA_W = 90   # 90 periodos de 8h ≈ 30 días


def load_panels():
    fdir = os.path.join(config.DATA_DIR, "funding")
    cdir = os.path.join(config.DATA_DIR, "futures_um", "1h")
    F, C = {}, {}
    for p in glob.glob(os.path.join(fdir, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        F[s] = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
    Fp = pd.DataFrame(F).sort_index()
    Fp = Fp[Fp.index >= Fp[DRIVER].first_valid_index()]
    for p in glob.glob(os.path.join(cdir, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        C[s] = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
    Cp = pd.DataFrame(C).sort_index()
    # precio en los timestamps de funding (ffill desde 1h)
    Px = Cp.reindex(Fp.index.union(Cp.index)).ffill().reindex(Fp.index)
    return Fp[sorted(Fp.columns)], Px[sorted(Fp.columns)]


def run(F, Px, step, cost_rate, cap, smooth=1, signal="raw", ts_win=90):
    syms = [s for s in F.columns if s != DRIVER]
    pr = Px.pct_change()                       # retorno 8h
    rd = pr[DRIVER]
    beta = pr.rolling(BETA_W).cov(rd).div(rd.rolling(BETA_W).var(), axis=0).clip(-3, 3)
    base = F[syms].ewm(span=smooth).mean() if smooth > 1 else F[syms]
    if signal == "ts_z":                       # z-score temporal por activo (anomalía propia)
        Fsig = (base - base.rolling(ts_win).mean()) / base.rolling(ts_win).std()
    else:
        Fsig = base
    _xs_z = (signal == "xs_z")

    idx = list(range(BETA_W + 1, len(F) - step, step))
    prev = pd.Series(0.0, index=syms); prev_h = 0.0
    rets, ts, turns, fcontrib = [], [], [], []
    for t in idx:
        f = Fsig.iloc[t]; b = beta[syms].iloc[t]
        v = f.notna() & b.notna()
        if v.sum() < 8:
            continue
        f, b = f[v], b[v]
        score = -(f - f.mean())                # short funding alto (anomalía)
        if _xs_z and f.std() > 0:
            score = score / f.std()            # z-score cross-seccional
        if score.abs().sum() == 0:
            continue
        w = (score / score.abs().sum()).clip(-cap, cap)
        w = w / w.abs().sum()
        wf = w.reindex(syms).fillna(0.0)
        h = -float((wf * beta[syms].iloc[t].reindex(syms).fillna(0)).sum())
        # funding cobrado en los próximos `step` periodos
        fwd_fund = F[syms].iloc[t+1:t+1+step].sum().reindex(syms).fillna(0)
        funding_pnl = -float((wf * fwd_fund).sum())
        # price pnl
        fwd_px = (Px[syms].iloc[t+step] / Px[syms].iloc[t] - 1).reindex(syms).fillna(0)
        fwd_d = (Px[DRIVER].iloc[t+step] / Px[DRIVER].iloc[t] - 1)
        price_pnl = float((wf * fwd_px).sum()) + h * float(fwd_d)
        turn = float((wf - prev).abs().sum()) + abs(h - prev_h)
        net = price_pnl + funding_pnl - turn * cost_rate
        rets.append(net); ts.append(F.index[t]); turns.append(turn); fcontrib.append(funding_pnl)
        prev, prev_h = wf, h
    s = pd.Series(rets, index=pd.to_datetime(ts, unit="ms", utc=True))
    return s, float(np.mean(turns)), float(np.mean(fcontrib))


def metrics(r, step_8h):
    if len(r) < 10:
        return None
    ppy = (3 * 365) / step_8h
    mean, sd = r.mean(), r.std()
    sharpe = mean / sd * np.sqrt(ppy) if sd > 0 else 0
    ann = (1 + mean) ** ppy - 1
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    return dict(n=len(r), sharpe=sharpe, ann=ann*100, vol=sd*np.sqrt(ppy)*100, dd=dd*100,
                mo_med=m.median()*100, mo_pos=(m > 0).mean()*100, calmar=ann/abs(dd) if dd < 0 else 0)


def line(label, r, turn, fc, step):
    m = metrics(r, step)
    if not m:
        print(f"  {label:30s} vacío"); return
    cut = int(len(r)*0.7)
    mi, mo = metrics(r.iloc[:cut], step), metrics(r.iloc[cut:], step)
    print(f"  {label:30s} Sh={m['sharpe']:+5.2f} ann={m['ann']:+7.1f}% vol={m['vol']:5.1f}% "
          f"DD={m['dd']:6.1f}% Cal={m['calmar']:+5.1f} mo_med={m['mo_med']:+5.2f}% turn={turn:.2f} "
          f"| IS={mi['sharpe']:+.2f} OOS={mo['sharpe']:+.2f}")


def main():
    F, Px = load_panels()
    print(f"Panel funding {F.shape[0]} periodos 8h × {F.shape[1]} símbolos "
          f"[{F.index[0]}..{F.index[-1]}]\n")
    print("=" * 104)
    print("  E4 — CARRY HARVEST (β-neutral, short funding alto / long bajo). gross=1, maker 0.02%/turn")
    print("=" * 104)
    for step in (1, 3, 6):   # 8h, 24h, 48h
        line(f"rebal {step*8}h", *run(F, Px, step, config.MAKER_FEE, config.MAX_WEIGHT_NORMAL), step)
    print("\n  Con suavizado del funding (menos turnover):")
    for sm in (3, 6):
        line(f"rebal 24h smooth={sm}", *run(F, Px, 3, config.MAKER_FEE, config.MAX_WEIGHT_NORMAL, smooth=sm), 3)
    print("\n  Descomposición y costo (rebal 24h):")
    for c, lbl in ((0.0,"rebate 0%"),(0.0002,"maker 0.02%"),(0.0004,"taker 0.04%")):
        line(lbl, *run(F, Px, 3, c, config.MAX_WEIGHT_NORMAL), 3)
    print("=" * 104)


if __name__ == "__main__":
    main()
