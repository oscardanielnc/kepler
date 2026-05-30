"""
E7 — CASH-AND-CARRY BASIS (long spot / short perp). Sleeve estructural de bajo riesgo.
Cobra el funding (el short perp recibe funding cuando es positivo) + la convergencia del
basis (perp-spot). Sin riesgo direccional (las patas se cancelan). Bajo turnover.

P&L por periodo 8h (por $1 base, long spot + short perp):
  price = spot_ret - perp_ret   (≈ −Δbasis, pequeño)
  funding = +funding_rate       (short perp recibe si funding>0)
Selectividad: mantener solo si funding > 0 (carry positivo); flat si ≤0 (no pagar).
Costos: spot 0.075% + perp maker 0.018% por lado, solo al entrar/salir.

python research/e7_basis.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

SYMS = config.SPOT_SYMBOLS   # BTC, ETH (donde tenemos spot)


def load_sym(sym):
    perp = pd.read_parquet(os.path.join(config.DATA_DIR, "futures_um", "1h", f"{sym}.parquet"),
                           columns=["open_time", "close"]).set_index("open_time")["close"]
    spot = pd.read_parquet(os.path.join(config.DATA_DIR, "spot", "1h", f"{sym}.parquet"),
                           columns=["open_time", "close"]).set_index("open_time")["close"]
    fund = pd.read_parquet(os.path.join(config.DATA_DIR, "funding", f"{sym}.parquet")
                           ).set_index("funding_time")["funding_rate"]
    # ALINEACIÓN EXACTA: inner-join perp+spot en open_time, luego mapear funding a esas barras
    j = pd.concat({"perp": perp, "spot": spot}, axis=1).dropna()
    j["funding"] = fund.reindex(j.index)               # funding solo en marcas 8h (NaN en el resto)
    return j[j["funding"].notna()]                     # quedarnos con la grilla 8h, todo alineado


def run_sym(df, sign_following=True, threshold=0.0):
    """Carry sign-following: w=+1 short perp/long spot si funding>0; w=−1 si funding<0
    → cobra |funding| siempre, hedgeado. (sign_following=False → solo carry clásico funding>0)."""
    cost = config.SPOT_FEE + config.MAKER_FEE
    perp_ret = df["perp"].pct_change().shift(-1)
    spot_ret = df["spot"].pct_change().shift(-1)
    fwd_fund = df["funding"].shift(-1)
    f = df["funding"]
    if sign_following:
        w = np.where(f > threshold, 1.0, np.where(f < -threshold, -1.0, 0.0))
    else:
        w = np.where(f > threshold, 1.0, 0.0)
    w = pd.Series(w, index=df.index)
    turn = w.diff().abs().fillna(w.abs())
    price_pnl = w * (spot_ret - perp_ret)              # long spot/short perp escalado por w
    fund_pnl = w * fwd_fund                             # w=+1 short perp cobra funding>0
    net = price_pnl + fund_pnl - turn * cost
    return net.dropna(), float(w.abs().mean()), float(turn.mean())


def metrics(r, ppy=3*365):
    r = r.dropna()
    if len(r) < 50 or r.std() == 0:
        return None
    sh = r.mean()/r.std()*np.sqrt(ppy)
    ann = (1+r.mean())**ppy - 1
    eq = (1+r).cumprod(); dd = (eq/eq.cummax()-1).min()
    m = (1+r).groupby([r.index.year, r.index.month]).prod()-1
    return dict(sharpe=sh, ann=ann*100, vol=r.std()*np.sqrt(ppy)*100, dd=dd*100,
                mo_med=m.median()*100, mo_pos=(m>0).mean()*100)


def show(label, r):
    m = metrics(r)
    if not m:
        print(f"  {label:34s} insuf."); return
    cut=int(len(r)*0.7); mi,mo=metrics(r.iloc[:cut]),metrics(r.iloc[cut:])
    print(f"  {label:34s} Sh={m['sharpe']:+5.2f} ann={m['ann']:+6.1f}% vol={m['vol']:4.1f}% "
          f"DD={m['dd']:6.1f}% mo_med={m['mo_med']:+5.2f}% mo+={m['mo_pos']:.0f}% "
          f"| IS={mi['sharpe']:+.2f} OOS={mo['sharpe']:+.2f}")


def main():
    print(f"Cash-and-carry sobre {SYMS}\n")
    print("=" * 96)
    print("  E7 — CASH-AND-CARRY (long spot / short perp). Periodo 8h. spot 0.075%+perp 0.018%")
    print("=" * 96)
    rets = {}
    for s in SYMS:
        df = load_sym(s)
        idx = pd.to_datetime(df.index, unit="ms", utc=True)
        for lbl, kw in (("clásico (funding>0)", dict(sign_following=False)),
                        ("sign-following", dict(sign_following=True)),
                        ("sign-following thr0.01%", dict(sign_following=True, threshold=0.0001))):
            r, expo, turn = run_sym(df, **kw)
            r.index = pd.to_datetime(df.index[:len(r)], unit="ms", utc=True)
            show(f"{s} {lbl} (expo {expo*100:.0f}% turn {turn:.3f})", r)
            if lbl == "sign-following":
                rets[s] = r
        print()
    # combinar BTC+ETH equal-weight
    if len(rets) == 2:
        combo = pd.concat(rets, axis=1).dropna()
        port = combo.mean(axis=1)
        print("=" * 96)
        show("BASIS combinado BTC+ETH (funding>0)", port)
        print(f"  correlación BTC-carry vs ETH-carry: {combo.corr().iloc[0,1]:+.3f}")
        print("=" * 96)
        # guardar para el combinador maestro
        out = os.path.join(config.DATA_DIR, "_sleeve_basis.parquet")
        port.to_frame("ret").to_parquet(out)
        print(f"  serie guardada → {os.path.basename(out)}")


if __name__ == "__main__":
    main()
