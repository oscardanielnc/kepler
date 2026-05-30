"""
E5 — STAT-ARB de pares (cointegración + Ornstein-Uhlenbeck).
Selección (SOLO en IS, sin lookahead): pares cointegrados (Engle-Granger p<0.05) con
half-life OU razonable. Backtest: spread z-score, entrar ±Z, salir ~0, stop si diverge.
Bajo turnover, poco correlacionado con carry → 2º sleeve para apilar.

python research/e5_statarb.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

ENTRY, EXIT, STOP = 2.0, 0.3, 4.0
ZWIN = 168   # ventana z-score (1 semana en 1h)


def load_logp():
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    cl = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:        # solo universo limpio
            continue
        cl[s] = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
    C = pd.DataFrame(cl).sort_index().dropna()
    return np.log(C)


def half_life(spread: np.ndarray) -> float:
    s = spread[~np.isnan(spread)]
    ds = np.diff(s); lag = s[:-1]
    b = np.polyfit(lag, ds, 1)[0]      # Δs = a + b·s
    return -np.log(2) / np.log(1 + b) if -1 < b < 0 else np.inf


def select_pairs(logp_is: pd.DataFrame, max_pairs=25, min_corr=0.5, pmax=0.05,
                 hl_lo=12, hl_hi=1440):
    syms = list(logp_is.columns)
    corr = logp_is.corr()
    cands = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            if abs(corr.loc[a, b]) < min_corr:    # pre-filtro de correlación en nivel
                continue
            x, y = logp_is[a].values, logp_is[b].values
            try:
                pval = coint(x, y)[1]
            except Exception:
                continue
            if pval > pmax:
                continue
            beta = np.polyfit(y, x, 1)[0]
            hl = half_life(x - beta * y)
            if not (hl_lo <= hl <= hl_hi):        # half-life 12h..60d
                continue
            cands.append((pval, a, b, beta, hl))
    cands.sort(key=lambda c: c[0])
    return cands[:max_pairs]


def backtest_pair(logp, a, b, beta):
    x = logp[a].values; y = logp[b].values
    spread = pd.Series(x - beta * y, index=logp.index)
    z = (spread - spread.rolling(ZWIN).mean()) / spread.rolling(ZWIN).std()
    rx = logp[a].diff().values; ry = logp[b].diff().values
    norm = 1 + abs(beta)
    n = len(z); pos = np.zeros(n); ret = np.zeros(n); turn = np.zeros(n)
    cur = 0.0
    zv = z.values
    for t in range(1, n):
        # P&L de mantener `cur` desde t-1
        ret[t] = cur * (rx[t] - beta * ry[t]) / norm
        new = cur
        if np.isnan(zv[t]):
            new = cur
        elif cur == 0:
            if zv[t] > ENTRY: new = -1.0       # spread alto → short spread
            elif zv[t] < -ENTRY: new = 1.0     # spread bajo → long spread
        else:                                   # en posición: salir si revirtió o divergió
            if abs(zv[t]) < EXIT or abs(zv[t]) > STOP:
                new = 0.0
        turn[t] = abs(new - cur)
        pos[t] = new; cur = new
    return pd.Series(ret, index=logp.index), pd.Series(turn, index=logp.index)


def metrics(r, label=""):
    r = r.dropna()
    if r.std() == 0 or len(r) < 100:
        return None
    ppy = 8760
    sh = r.mean()/r.std()*np.sqrt(ppy)
    eq = (1+r).cumprod(); dd = (eq/eq.cummax()-1).min()
    ann = (1+r.mean())**ppy - 1
    m = (1+r).groupby([r.index.year, r.index.month]).prod()-1
    return dict(sharpe=sh, ann=ann*100, vol=r.std()*np.sqrt(ppy)*100, dd=dd*100,
                mo_med=m.median()*100, mo_pos=(m>0).mean()*100)


def main():
    logp = load_logp()
    logp.index = pd.to_datetime(logp.index, unit="ms", utc=True)
    cut = int(len(logp)*0.70)
    is_, oos = logp.iloc[:cut], logp.iloc[cut:]
    print(f"{logp.shape[1]} símbolos · {logp.shape[0]} barras 1h\n")
    print("Seleccionando pares cointegrados en IS (Engle-Granger p<0.05, half-life 6h-30d)...")
    pairs = select_pairs(is_, pmax=0.01, min_corr=0.80)   # estricto: solo pares robustos
    print(f"Pares seleccionados: {len(pairs)}")
    for pval, a, b, beta, hl in pairs:
        print(f"  {a:9s}~{b:9s} p={pval:.4f} β={beta:+.2f} half-life={hl:5.0f}h")
    if not pairs:
        print("Sin pares cointegrados estables."); return

    cost = config.MAKER_FEE
    port_ret = None; port_turn = None
    for pval, a, b, beta in [(p[0], p[1], p[2], p[3]) for p in pairs]:
        r, tn = backtest_pair(logp, a, b, beta)
        r_net = r - tn * cost
        port_ret = r_net if port_ret is None else port_ret.add(r_net, fill_value=0)
        port_turn = tn if port_turn is None else port_turn.add(tn, fill_value=0)
    k = len(pairs)
    port_ret /= k; port_turn /= k   # equal-weight

    print("\n" + "=" * 92)
    print(f"  E5 — STAT-ARB cartera de {k} pares (z-entry {ENTRY}, exit {EXIT}, stop {STOP}, maker 0.02%)")
    print("=" * 92)
    cutp = int(len(port_ret)*0.70)
    for tag, seg in (("FULL", port_ret), ("IS  ", port_ret.iloc[:cutp]), ("OOS ", port_ret.iloc[cutp:])):
        m = metrics(seg)
        if m:
            print(f"  {tag}: Sharpe {m['sharpe']:+5.2f}  ann {m['ann']:+6.1f}%  vol {m['vol']:4.1f}%  "
                  f"maxDD {m['dd']:6.1f}%  mo_med {m['mo_med']:+5.2f}%  mo+ {m['mo_pos']:.0f}%")
    print(f"  turnover medio/barra: {port_turn.mean():.4f}  (exposición media: {(port_ret!=0).mean()*100:.0f}% del tiempo)")
    print("=" * 92)


if __name__ == "__main__":
    main()
