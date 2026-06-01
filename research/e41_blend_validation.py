"""
E41 — VALIDACIÓN del blend FULL-HISTORY {loteria + tvl + illiq} (candidato sleeve #8). 2026-06-01.
e40: +0.34 Sharpe OOS, 6/6 folds, sin punto ciego 2022 (a coste MAKER). Antes de promover (regla de
oro) falta: (1) COSTE TAKER/slippage real (e30b-style: el blend longea illiquidos en illiq y shortea
lotería en small-caps → exposición a slippage), (2) ESTRÉS (horizonte de la lotería, cuartiles, LOO).

python -m research.e41_blend_validation
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, load_panel
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import bt_xs, bt_carry, bt_trend, compound_daily, adv_usd
from research.regime_lab import build_base_sleeves, evaluate, _walk_forward_oos, _cpcv_sharpes, _anchored
from research.e38_crossfamily_blend import oriented
from research.e39_skew_lottery import daily_to_hourly
from research.e26_onchain_tvl_check import load_tvl_panel

MAKER = config.MAKER_FEE
H = 14 * 24


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(c):
    L = leverage_for_maxdd_anchor(c, config.TARGET_MAXDD); m = metrics(c*L); return m["sharpe"], m["ann"], L, m["maxdd"]


def get_sign(C, ret, beta, score, hold):
    s, _ = xs_sleeve(C, ret, beta, score, hold)
    cut = int(s.dropna().shape[0]*0.6); return 1.0 if s.dropna().iloc[:cut].mean() >= 0 else -1.0


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E41 — VALIDACIÓN del blend {loteria+tvl+illiq}: TAKER + ESTRÉS\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); retd = ret.reindex(columns=C.columns)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C); dvol = P["quote_volume"]; absret = ret.abs()
    cols = list(C.columns)
    rd = C.resample("1D").last().pct_change(); rd.index = rd.index.normalize()
    logtvl, _ = load_tvl_panel(C)

    # scores crudos + signo (dirección rentable)
    lot_raw = daily_to_hourly(rd.rolling(60).max(), C)
    tvl_raw = logtvl.diff(H) - retd.rolling(H).sum()
    ilq_raw = np.log((absret/dvol.replace(0, np.nan)).rolling(H).mean().replace(0, np.nan))
    comps = {"lottery": (lot_raw, 60*24), "tvl": (tvl_raw, H), "illiq": (ilq_raw, H)}
    signs = {n: get_sign(C, ret, beta, sc, h) for n, (sc, h) in comps.items()}
    print(f"signos (dirección rentable): { {k: int(v) for k,v in signs.items()} }\n")

    # ── modelo de slippage por liquidez (idéntico e18/e30b) ──
    adv = adv_usd(dvol).reindex(cols).fillna(0.0); adv_M = (adv/1e6).clip(lower=1.0)
    def slip_adv(mult=1.0):
        return (50.0/np.sqrt(adv_M)*mult).clip(0.5, 30.0).div(1e4).reindex(cols).fillna(0.5/1e4)

    # ── componentes del blend: bruto + turnover (bt_xs con score dirigido) ──
    COMP = {n: bt_xs(C, ret, beta, signs[n]*sc, h) for n, (sc, h) in comps.items()}
    # ── 7 sleeves base: bruto + turnover ──
    XS = {}
    XS["mom_30d"]      = bt_xs(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    XS["rev_60d"]      = bt_xs(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    XS["lowvol_14d"]   = bt_xs(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    XS["takerflow_5d"] = bt_xs(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    XS["hlpos_14d"]    = bt_xs(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    CARRY = bt_carry(C, ret, beta); TREND = bt_trend(C)

    def base_net(slip):
        out = {}
        for name, (ts, pg, turn) in XS.items():
            out[name] = compound_daily(ts, pg - (turn*slip.reindex(turn.columns).fillna(0)).sum(axis=1).values)
        ts, pg, turn = CARRY
        out["carry"] = compound_daily(ts, pg - (turn*slip.reindex(turn.columns).fillna(0)).sum(axis=1).values)
        pnl, turn, lev = TREND
        out["trend"] = ((pnl - (turn*slip.reindex(turn.columns).fillna(0)).mean(axis=1))*lev).dropna()
        return out

    def blend_net(slip):
        d = {}
        for n, (ts, pg, turn) in COMP.items():
            d[n] = compound_daily(ts, pg - (turn*slip.reindex(turn.columns).fillna(0)).sum(axis=1).values)
        B = pd.concat(d, axis=1); B.columns = list(d); B = B.dropna()
        return (B * vol_parity_weights(B)).sum(axis=1)

    maker = pd.Series(MAKER, index=cols)
    def mk(slip): return maker + slip.reindex(cols).fillna(0)

    # ── 1. COSTE: 7 vs 8 (con blend) bajo maker / ADV-K50 / ADV×3 / 10bps ──
    print("── 1. COSTE TAKER/slippage: ¿el +0.34 sobrevive? (7 vs 8 al ancla −10%) ──")
    print(f"  {'escenario':<26s} {'7-combo':>9s} {'8-combo':>9s} {'Δ blend':>9s} {'maxDD8':>7s}")
    turn_blend = sum(COMP[n][2].values.sum() for n in COMP)
    yrs = (C.index[-1]-C.index[0]).days/365.25
    for label, slip in [("maker plano", maker), ("+ ADV K50 (central)", mk(slip_adv(1.0))),
                        ("+ ADV ×3 (estrés)", mk(slip_adv(3.0))), ("+ 10bps plano", pd.Series(MAKER+10/1e4, index=cols))]:
        bn = base_net(slip); df7 = pd.concat(bn, axis=1).dropna()
        s7, a7, L7, _ = anchored((df7*vol_parity_weights(df7)).sum(axis=1))
        bl = blend_net(slip); df8 = pd.concat({**bn, "blend": bl}, axis=1).dropna()
        s8, a8, L8, dd8 = anchored((df8*vol_parity_weights(df8)).sum(axis=1))
        print(f"  {label:<26s} {a7/12:8.2f}% {a8/12:8.2f}% {(a8-a7)/12:+8.2f}% {dd8:6.1f}%")
    print(f"  turnover del blend: {turn_blend/yrs:.1f}x/año (los 3 componentes son lentos)")

    # ── 2. ESTRÉS ──
    print("\n── 2a. HORIZONTE de la lotería (¿60d es plateau o pico de suerte?) ──")
    base = build_base_sleeves()
    for N in (30, 45, 60, 90, 120):
        sc = daily_to_hourly(rd.rolling(N).max(), C)
        sg = get_sign(C, ret, beta, sc, N*24)
        sr, _ = xs_sleeve(C, ret, beta, sg*sc, N*24)
        j = pd.concat({**{k: base[k] for k in base.columns}, "x": sr}, axis=1).dropna()
        cmax = j.corr()["x"].drop("x").abs().max()
        print(f"  max_{N}d  Sharpe {sh(sr):+.2f} · IS {sh(seg(sr,0,.6)):+.2f} · OOS {sh(seg(sr,.6,1)):+.2f} · corr {cmax:.2f} · sgn {int(sg):+d}")

    # blend maker (oriented) para cuartiles + LOO
    M = {n: oriented(C, ret, beta, comps[n][0], comps[n][1]) for n in comps}
    MB = pd.concat(M, axis=1); MB.columns = list(M); MB = MB.dropna()
    base_ref = evaluate(base, None, "base"); nf = len(base_ref["folds"])
    blend_maker = (MB * vol_parity_weights(MB)).sum(axis=1).rename("x")

    print("\n── 2b. CUARTILES temporales del blend (Sharpe) ──")
    print("  " + "  ".join(f"Q{i+1} {sh(seg(blend_maker,a,b)):+.2f}" for i,(a,b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)])))

    print("\n── 2c. LEAVE-ONE-OUT (quitar cada componente; ¿colapsa la robustez 6/6?) ──")
    full = evaluate(base, blend_maker, "full"); fwF = sum(a>b for a,b in zip(full["folds"], base_ref["folds"]))
    print(f"  blend completo (3): ΔSharpe {full['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · {fwF}/{nf} folds")
    for drop in M:
        keep = [k for k in M if k != drop]
        sub = MB[keep]; bsub = (sub*vol_parity_weights(sub)).sum(axis=1).rename("x")
        r = evaluate(base, bsub, f"-{drop}"); fw = sum(a>b for a,b in zip(r["folds"], base_ref["folds"]))
        print(f"  sin {drop:8s} ({'+'.join(keep)}): ΔSharpe {r['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · {fw}/{nf}")

    print("\nVEREDICTO: ver coste (¿Δ>0 a ADV-K50?) + horizonte (¿plateau?) + cuartiles (¿repartido?) + LOO")
    print("(¿algún componente imprescindible o se sostiene?). Si todo OK → sleeve #8 (sombra/taker) — regla de oro.")


if __name__ == "__main__":
    main()
