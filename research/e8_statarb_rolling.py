"""
E8 — STAT-ARB con RE-SELECCIÓN RODANTE (walk-forward).
Cada 90 días re-selecciona pares cointegrados sobre la ventana móvil previa de 1 año,
y los opera los siguientes 90 días. OOS por construcción (selección solo con datos
pasados). Adapta a pares que decaen y usa toda la historia (no trunca a los coins nuevos).

python research/e8_statarb_rolling.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.alphas import statarb_select, STATARB_ENTRY, STATARB_EXIT, STATARB_STOP, STATARB_ZWIN

TRAIN_H = 365 * 24    # ventana de selección (1 año)
RESEL_H = 90 * 24     # re-seleccionar cada 90 días


def load_logp():
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    cl = {}
    for p in glob.glob(os.path.join(d, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        cl[s] = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
    C = pd.DataFrame(cl).sort_index()           # NO dropna global (mantener historia por activo)
    return np.log(C)


def pair_returns(logp, a, b, beta, lo, hi):
    """Retornos netos del par en barras [lo,hi) usando z-score; cost maker en turnover."""
    sub = logp[[a, b]].iloc[max(0, lo - STATARB_ZWIN):hi]
    spread = sub[a] - beta * sub[b]
    z = (spread - spread.rolling(STATARB_ZWIN).mean()) / spread.rolling(STATARB_ZWIN).std()
    ra = sub[a].diff().values; rb = sub[b].diff().values
    zv = z.values; norm = 1 + abs(beta)
    idx = sub.index
    out = pd.Series(0.0, index=idx); pos = 0.0
    start_local = len(idx) - (hi - lo)          # primer índice local del segmento de trading
    for k in range(1, len(idx)):
        out.iloc[k] = pos * (ra[k] - beta * rb[k]) / norm
        zt = zv[k]
        if not np.isnan(zt):
            if pos == 0:
                if zt > STATARB_ENTRY: new = -1.0
                elif zt < -STATARB_ENTRY: new = 1.0
                else: new = 0.0
            else:
                new = 0.0 if (abs(zt) < STATARB_EXIT or abs(zt) > STATARB_STOP) else pos
        else:
            new = pos
        out.iloc[k] -= abs(new - pos) * config.MAKER_FEE
        pos = new
    return out.iloc[start_local:]               # solo el tramo de trading del segmento


def main():
    logp = load_logp()
    N = len(logp)
    print(f"{logp.shape[1]} símbolos · {N} barras 1h (historia completa, sin truncar)\n")
    seg_rets = []
    npairs_log = []
    for seg in range(TRAIN_H, N, RESEL_H):
        lo, hi = seg, min(seg + RESEL_H, N)
        train = logp.iloc[seg - TRAIN_H:seg]
        train = train.dropna(axis=1, thresh=int(0.9 * len(train))).dropna()
        if train.shape[1] < 4:
            continue
        pairs = statarb_select(train, pmax=0.01, min_corr=0.80)
        npairs_log.append(len(pairs))
        if not pairs:
            continue
        prs = [pair_returns(logp, p["a"], p["b"], p["beta"], lo, hi) for p in pairs]
        seg_ret = pd.concat(prs, axis=1).mean(axis=1)   # equal-weight pares activos
        seg_rets.append(seg_ret)
    port = pd.concat(seg_rets).sort_index()
    port.index = pd.to_datetime(port.index, unit="ms", utc=True)
    # guardar serie diaria para el combinador
    eq = (1 + port).cumprod(); dly = eq.resample("1D").last().ffill().pct_change().dropna()
    dly.to_frame("ret").to_parquet(os.path.join(config.DATA_DIR, "_sleeve_statarb_rolling.parquet"))

    ppy = 8760
    sh = port.mean() / port.std() * np.sqrt(ppy)
    ann = (1 + port.mean()) ** ppy - 1
    dd = (eq / eq.cummax() - 1).min()
    m = (1 + port).groupby([port.index.year, port.index.month]).prod() - 1
    cut = int(len(port) * 0.5)   # primera mitad vs segunda (todo es OOS por construcción)
    sh1 = port.iloc[:cut].mean()/port.iloc[:cut].std()*np.sqrt(ppy)
    sh2 = port.iloc[cut:].mean()/port.iloc[cut:].std()*np.sqrt(ppy)
    print("=" * 92)
    print("  E8 — STAT-ARB WALK-FORWARD (re-selección cada 90d, ventana 1a, OOS por construcción)")
    print("=" * 92)
    print(f"  pares activos por segmento: min {min(npairs_log)} / max {max(npairs_log)} / med {int(np.median(npairs_log))}")
    print(f"  Período operado: {port.index[0].date()} → {port.index[-1].date()}  ({len(port)} barras)")
    print(f"  Sharpe {sh:+.2f} | ann {ann*100:+.1f}% | vol {port.std()*np.sqrt(ppy)*100:.1f}% | "
          f"maxDD {dd*100:.1f}% | mo_med {m.median()*100:+.2f}% | mo+ {(m>0).mean()*100:.0f}%")
    print(f"  1ª mitad Sharpe {sh1:+.2f}  ·  2ª mitad Sharpe {sh2:+.2f}  (consistencia temporal)")
    print("=" * 92)


if __name__ == "__main__":
    main()
