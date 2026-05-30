"""
E10 — TREND-FOLLOWING DIRECCIONAL (Opción B). Time-series momentum.
Largo si tendencia alcista / corto si bajista (EMA rápida vs lenta), vol-target por activo,
corta pérdidas al voltear la tendencia (let-run/cut-fast), costos taker + funding.
Mide la matemática honesta: WR, payoff (avg win/loss), SKEW, Sharpe, maxDD, IS/OOS.

Direccional = exposición neta al mercado (más retorno, más riesgo) — eso busca Oscar.
python research/e10_trend.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa

VOL_WIN = 30        # días para vol-target
TARGET_ASSET_VOL = 0.20 / np.sqrt(365)   # ~20%/yr por activo (diario)


def load_daily():
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    cl = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        c = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
        c.index = pd.to_datetime(c.index, unit="ms", utc=True)
        cl[s] = c.resample("1D").last()
    px = pd.DataFrame(cl).sort_index()
    # funding diario (suma de 3 periodos 8h)
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("1D").sum()
    fund = pd.DataFrame(fd).reindex(px.index).fillna(0)
    return px, fund


def run(px, fund, fast, slow, allow_short=True, cost=config.TAKER_FEE, vt_total=0.15):
    ret = px.pct_change()
    ef = px.ewm(span=fast).mean(); es = px.ewm(span=slow).mean()
    sig = np.sign(ef - es)
    if not allow_short:
        sig = sig.clip(lower=0)
    sig = sig.shift(1)                                   # señal con datos hasta ayer (sin lookahead)
    vol = ret.rolling(VOL_WIN).std().shift(1)
    scal = (TARGET_ASSET_VOL / vol).clip(0, 3)
    pos = sig * scal                                    # posición por activo, vol-targeted
    # P&L diario por activo: precio + funding (largo paga funding+); costos por turnover
    pnl_px = pos * ret
    pnl_fund = -pos * fund                              # largo paga funding positivo
    turn = pos.diff().abs()
    pnl = (pnl_px + pnl_fund - turn * cost)
    port = pnl.mean(axis=1)                             # equal-weight activos presentes
    # vol-target del portafolio total
    pv = port.rolling(VOL_WIN).std().shift(1)
    lev = (vt_total/np.sqrt(365) / pv).clip(0, 4).fillna(1)
    port = (port * lev).dropna()
    return port, pos, ret


def trade_stats(pos, ret):
    """WR, payoff y skew a nivel de 'trade' (entrada→volteo) sobre el activo más líquido (BTC)."""
    s = pos["BTCUSDT"].fillna(0); r = ret["BTCUSDT"].fillna(0)
    trades = []; cur_sign = 0; pnl = 0
    for t in range(1, len(s)):
        if np.sign(s.iloc[t-1]) != 0:
            pnl += np.sign(s.iloc[t-1]) * r.iloc[t]
        if np.sign(s.iloc[t]) != np.sign(s.iloc[t-1]):
            if cur_sign != 0:
                trades.append(pnl)
            pnl = 0; cur_sign = np.sign(s.iloc[t])
    tr = pd.Series(trades)
    w = tr[tr > 0]; l = tr[tr <= 0]
    return dict(n=len(tr), wr=(tr > 0).mean()*100 if len(tr) else 0,
                avg_w=w.mean()*100 if len(w) else 0, avg_l=l.mean()*100 if len(l) else 0,
                payoff=(w.mean()/abs(l.mean())) if len(l) and l.mean() != 0 else 0)


def metrics(r):
    r = r.dropna()
    if len(r) < 60:
        return None
    sh = r.mean()/r.std()*np.sqrt(365)
    ann = (1+r.mean())**365 - 1
    eq = (1+r).cumprod(); dd = (eq/eq.cummax()-1).min()
    m = (1+r).groupby([r.index.year, r.index.month]).prod()-1
    return dict(sharpe=sh, ann=ann*100, vol=r.std()*np.sqrt(365)*100, dd=dd*100, skew=r.skew(),
                mo_med=m.median()*100, mo_pos=(m>0).mean()*100, calmar=ann/abs(dd) if dd < 0 else 0)


def main():
    px, fund = load_daily()
    print(f"{px.shape[1]} activos · {px.shape[0]} días [{px.index[0].date()}→{px.index[-1].date()}]\n")
    print("=" * 100)
    print("  E10 — TREND-FOLLOWING DIRECCIONAL (EMA fast/slow, vol-target 15%/yr, taker+funding)")
    print("=" * 100)
    print(f"  {'config':24s} {'Sharpe':>7s} {'ann%':>7s} {'vol%':>6s} {'maxDD%':>7s} {'Calmar':>7s} "
          f"{'skew':>6s} {'mo_med%':>8s} | {'IS':>5s} {'OOS':>5s}")
    best = None
    for fast, slow in [(10,30),(20,60),(20,100),(50,150)]:
        port, pos, ret = run(px, fund, fast, slow)
        m = metrics(port)
        if not m: continue
        cut = int(len(port)*0.7)
        mi, mo = metrics(port.iloc[:cut]), metrics(port.iloc[cut:])
        print(f"  EMA {fast}/{slow} L/S          {m['sharpe']:+7.2f} {m['ann']:+7.1f} {m['vol']:6.1f} "
              f"{m['dd']:7.1f} {m['calmar']:+7.2f} {m['skew']:+6.2f} {m['mo_med']:+8.2f} | "
              f"{mi['sharpe']:+5.2f} {mo['sharpe']:+5.2f}")
        if best is None or m['sharpe'] > best[1]['sharpe']:
            best = ((fast,slow), m, port, pos, ret)
    # long-only variante (sin shorts)
    port_lo, _, _ = run(px, fund, *best[0], allow_short=False)
    mlo = metrics(port_lo)
    print(f"  EMA {best[0][0]}/{best[0][1]} LONG-only     {mlo['sharpe']:+7.2f} {mlo['ann']:+7.1f} {mlo['vol']:6.1f} "
          f"{mlo['dd']:7.1f} {mlo['calmar']:+7.2f} {mlo['skew']:+6.2f} {mlo['mo_med']:+8.2f}")

    ts = trade_stats(best[3], best[4])
    print(f"\n  MATEMÁTICA DEL EDGE (BTC, EMA {best[0][0]}/{best[0][1]}): "
          f"{ts['n']} trades · WR {ts['wr']:.0f}% · avg_win {ts['avg_w']:+.1f}% · avg_loss {ts['avg_l']:+.1f}% "
          f"· payoff {ts['payoff']:.2f}x")
    print(f"  → skew positivo + payoff>1 = 'cortar pérdidas / dejar correr' confirmado" if ts['payoff'] > 1.3
          else "  → payoff bajo: el cut/run no compensa el WR")
    print("\n  CURVA DE LEVERAGE (mejor config) — direccional, más retorno/más riesgo:")
    bp = best[2]
    print(f"  {'lev':>4s} {'ann%':>7s} {'maxDD%':>7s} {'mo_med%':>8s}")
    for L in (1,2,3):
        m = metrics(bp*L)
        print(f"  {L:>3d}x {m['ann']:7.1f} {m['dd']:7.1f} {m['mo_med']:8.2f}")
    print("=" * 100)


if __name__ == "__main__":
    main()
