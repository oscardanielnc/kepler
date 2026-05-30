"""
E14 — Buscar MÁS sleeves no correlacionados (subir el Sharpe del conjunto).
Prueba cross-seccional β-neutral sobre 4.4a (23 monedas establecidas):
  momentum multi-horizonte, reversión de LARGO plazo, low-vol anomaly.
Mide Sharpe IS/OOS + correlación con los existentes (carry, mom14d, trend).
Combina los SUPERVIVIENTES (positivos IS&OOS, baja corr) → Sharpe mejorado + 2 niveles de riesgo.

python research/e14_more_sleeves.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa
import e6_combine as e6
import e10_trend as e10
from kepler.portfolio import vol_parity_weights, combine, metrics

DRIVER = "BTCUSDT"; BETA_W = 168; MIN_BARS = 34000


def load_long():
    cl = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        c = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
        if len(c) < MIN_BARS:
            continue
        cl[s] = c
    C = pd.DataFrame(cl).sort_index().dropna()
    C.index = pd.to_datetime(C.index, unit="ms", utc=True)
    return C


def xs_sim(C, score_df, hold, cap=config.MAX_WEIGHT_NORMAL, cost=config.MAKER_FEE):
    ret = np.log(C).diff()
    syms = [s for s in C.columns if s != DRIVER]
    R = ret[syms]; rd = ret[DRIVER]
    beta = R.rolling(BETA_W).cov(rd).div(rd.rolling(BETA_W).var(), axis=0).clip(-3, 3)
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold))
    fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0; rets = []; ts = []
    for t in idx:
        s = score_df.iloc[t].reindex(syms); b = beta.iloc[t].reindex(syms)
        v = s.notna() & b.notna()
        if v.sum() < 6:
            continue
        s = (s[v] - s[v].mean())
        if s.abs().sum() == 0:
            continue
        w = (s/s.abs().sum()).clip(-cap, cap); w = w/w.abs().sum()
        wf = w.reindex(syms).fillna(0.0)
        h = -float((wf*b.reindex(syms).fillna(0)).sum())
        port = float((wf*fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h*float(fwd_d.iloc[t] or 0)
        turn = float((wf-prev).abs().sum())+abs(h-ph)
        rets.append(port - turn*cost); ts.append(C.index[t]); prev, ph = wf, h
    s = pd.Series(rets, index=ts)
    eq = (1+s).cumprod(); return eq.resample("1D").last().ffill().pct_change().dropna()


def sh_isoos(r):
    cut = int(len(r)*0.6)
    f = lambda x: x.mean()/x.std()*np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0
    return f(r), f(r.iloc[:cut]), f(r.iloc[cut:])


def main():
    C = load_long()
    ret = np.log(C).diff()
    print(f"Panel {C.shape[1]} monedas · {C.shape[0]} velas [{C.index[0].date()}→{C.index[-1].date()}]\n")
    past = lambda L: ret.rolling(L).sum()
    vol = lambda L: ret.rolling(L).std()

    cands = {
        "mom_7d":   (past(168),  168),
        "mom_14d":  (past(336),  336),
        "mom_21d":  (past(504),  504),
        "mom_30d":  (past(720),  720),
        "rev_30d":  (-past(720), 720),
        "rev_60d":  (-past(1440), 1440),
        "lowvol_14d": (-vol(336), 336),
    }
    print("=" * 90)
    print("  CANDIDATOS (cross-seccional β-neutral, 4.4a):  Sharpe / IS / OOS")
    print("=" * 90)
    series = {}
    for name, (score, hold) in cands.items():
        r = xs_sim(C, score, hold)
        s, i, o = sh_isoos(r)
        ok = "✓" if (i > 0.1 and o > 0.1) else ""
        print(f"  {name:12s} Sh={s:+5.2f}  IS={i:+5.2f}  OOS={o:+5.2f}  {ok}")
        series[name] = r

    # sleeves existentes
    series["carry"] = e6.carry_daily()
    px, fund = e10.load_daily(); tr, _, _ = e10.run(px, fund, 20, 100, allow_short=False)
    series["trend"] = tr

    # supervivientes: IS&OOS > 0.1
    surv = [n for n, r in series.items() if n not in ("carry", "trend")
            and all(x > 0.1 for x in sh_isoos(r)[1:])]
    surv = list(dict.fromkeys(surv + ["carry"]))   # carry siempre (estructural)
    # quitar momentum redundantes: quedarse con el mejor mom + reversiones/lowvol que sobrevivan
    print(f"\n  Supervivientes pre-selección: {surv}")

    df = pd.concat(series, axis=1).dropna()
    print(f"\n  CORRELACIONES (sleeves clave):")
    keys = [k for k in ["mom_14d","mom_30d","rev_60d","lowvol_14d","carry","trend"] if k in df]
    print(df[keys].corr().round(2).to_string())

    # cartera final: set diversificado fijo (momentum + reversión LP + low-vol + carry + trend)
    chosen = [k for k in ["mom_30d", "rev_60d", "lowvol_14d", "carry", "trend"] if k in df]
    print(f"\n  CARTERA FINAL elegida: {chosen}")
    sub = df[chosen]
    w = vol_parity_weights(sub); port = combine(sub, w)
    m = metrics(port); s, i, o = sh_isoos(port)
    print(f"\n  COMBINADO: Sharpe {m['sharpe']:+.2f} (IS {i:+.2f}/OOS {o:+.2f}) ann {m['ann']:+.1f}% "
          f"vol {m['vol']:.1f}% maxDD {m['maxdd']:.1f}% mo_med {m['mo_med']:+.2f}%")

    print("\n  DOS NIVELES DE RIESGO (producto copy-lead):")
    print(f"  {'tier':>20s} {'ann%':>7s} {'vol%':>6s} {'maxDD%':>7s} {'mo_med%':>8s} {'Calmar':>7s}")
    for L, name in ((1, "ESTABLE (1x)"), (2, "BALANCEADO (2x)"), (3, "GROWTH (3x)")):
        mm = metrics(port*L)
        print(f"  {name:>20s} {mm['ann']:7.1f} {mm['vol']:6.1f} {mm['maxdd']:7.1f} {mm['mo_med']:8.2f} {mm['calmar']:7.2f}")
    print("=" * 90)


if __name__ == "__main__":
    main()
