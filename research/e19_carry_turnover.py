"""
E19 — B: REDUCIR TURNOVER DE CARRY (ROADMAP §C2). 2026-05-31.
C1 (e18) reveló: carry rota ~199x/año (reordena el libro cada 48h por ranking de funding
INSTANTÁNEO de una sola lectura 8h, muy ruidoso) → con slippage realista se come −0.82%/mes.
El carry de funding PERSISTE días → no hace falta rankear sobre la lectura instantánea.

Palancas (sin romper el edge):
  - SUAVIZAR la señal: rankear sobre media móvil del funding (3d/7d/14d) en vez de la lectura 8h.
    (La FUNDING REALIZADA que se cobra sigue siendo la real; solo el SIGNAL se suaviza.)
  - REBALANCEAR menos seguido: holding 48h → 96h → 168h.

Criterio (regla de oro): la variante gana si, con SLIPPAGE REALISTA (modelo ADV de e18), sube el
%/mes del COMBINADO 7 sleeves al ancla −10%, sin romper maxDD ni la diversificación (corr<0.35).

python -m research.e19_carry_turnover
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, load_panel, DRIVER, SLEEVES
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import bt_xs, bt_trend, compound_daily, anchored, adv_usd

MAKER = config.MAKER_FEE


def bt_carry_v(C, ret, beta, smooth=1, step=6):
    """Carry parametrizado: smooth = períodos 8h de media móvil del funding-signal (1=instantáneo);
    step = holding en períodos 8h (6=48h). Devuelve (ts, port_gross, turn_df). La funding cobrada
    usa el funding REAL; solo el ranking usa el suavizado."""
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns:
            continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    Fs = F.rolling(smooth, min_periods=1).mean() if smooth > 1 else F
    syms = [s for s in C.columns if s != DRIVER]
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    bet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)
    idx = range(max(91, smooth + 1), len(F) - step - 1, step)
    prev = pd.Series(0.0, index=syms); ph = 0.0
    pg = []; ts = []; turns = []
    for t in idx:
        w, h = alphas.carry_weights(Fs[syms].iloc[t], bet.iloc[t], config.MAX_WEIGHT_NORMAL)
        w = w.reindex(syms).fillna(0.0)
        fund = -float((w * F[syms].iloc[t+1:t+1+step].sum()).sum())          # funding REAL cobrada
        px = float((w * (Cr[syms].iloc[t+step]/Cr[syms].iloc[t]-1)).sum()) \
            + h*(Cr[DRIVER].iloc[t+step]/Cr[DRIVER].iloc[t]-1)
        tr = (w - prev).abs(); tr[DRIVER] = abs(h - ph)
        pg.append(fund + px); ts.append(F.index[t]); turns.append(tr); prev, ph = w, h
    return ts, np.array(pg), pd.DataFrame(turns, index=ts).fillna(0.0)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E19 — B: reducir turnover de carry\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    cols = list(C.columns)
    yrs = (C.index[-1] - C.index[0]).days / 365.25

    # slippage central por ADV (idéntico a e18, K50)
    adv_M = (adv_usd(P["quote_volume"]).reindex(cols).fillna(0.0)/1e6).clip(lower=1.0)
    slip = (50.0/np.sqrt(adv_M)).clip(0.5, 30.0)/1e4
    slip = slip.reindex(cols).fillna(0.5/1e4)
    flat_xc = pd.Series(MAKER, index=cols)              # maker plano (xs/carry)
    flat_tr = pd.Series(0.0, index=cols)               # trend hoy sin costo
    real_all = pd.Series(MAKER, index=cols) + slip     # maker + slip realista (todos)

    # ── sleeves fijos (los 6 no-carry) precomputados una vez ──────────────────
    print(f"Universo {C.shape[1]} · {yrs:.1f} años · precomputando 6 sleeves no-carry...")
    XS = {}
    for name, typ, hold in SLEEVES:
        if typ == "xs_mom":   sc = alphas.xs_momentum_score(ret, hold)
        elif typ == "xs_rev": sc = alphas.xs_reversal_score(ret, hold)
        elif typ == "xs_lowvol": sc = alphas.xs_lowvol_score(ret, hold)
        elif typ == "xs_flow": sc = alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], hold)
        elif typ == "xs_hlpos": sc = alphas.xs_hlposition_score(C, hold)
        else: continue
        XS[name] = bt_xs(C, ret, beta, sc, hold)
    TREND = bt_trend(C)

    def net_series(slip_xc, slip_tr, carry):
        d = {}
        for name, (ts, pg, turn) in XS.items():
            d[name] = compound_daily(ts, pg - (turn*slip_xc.reindex(turn.columns).fillna(0)).sum(axis=1).values)
        ts, pg, turn = carry
        d["carry"] = compound_daily(ts, pg - (turn*slip_xc.reindex(turn.columns).fillna(0)).sum(axis=1).values)
        pnl, tu, lev = TREND
        d["trend"] = ((pnl - (tu*slip_tr.reindex(tu.columns).fillna(0)).mean(axis=1))*lev).dropna()
        df = pd.concat(d, axis=1); df.columns = list(d.keys())
        return df.dropna()

    def evaluate(carry, slip_xc, slip_tr):
        df = net_series(slip_xc, slip_tr, carry)
        combo = (df * vol_parity_weights(df)).sum(axis=1)
        sh, ann, L, dd = anchored(combo)
        corr = df.corr()["carry"].drop("carry").abs().max()
        csh = df["carry"].mean()/df["carry"].std()*np.sqrt(365) if df["carry"].std() > 0 else 0
        return ann, L, dd, corr, csh

    def turnover(carry): return carry[2].values.sum()/yrs

    # ── baseline = carry actual (instantáneo, 48h) ────────────────────────────
    base = bt_carry_v(C, ret, beta, smooth=1, step=6)
    print(f"\nCARRY ACTUAL: turnover {turnover(base):.0f}x/año")
    a_flat, *_ = evaluate(base, flat_xc, flat_tr)
    a_real, *_ = evaluate(base, real_all, real_all)
    print(f"  combinado @−10%:  flat {a_flat/12:.2f}%/mes  ·  slip-real {a_real/12:.2f}%/mes")

    print("\nVARIANTES (combinado 7 sleeves @−10%, métrica clave = %/mes con SLIP REAL):")
    print(f"  {'smooth':>7s} {'hold':>5s} {'turnov':>7s} {'carrySh':>7s} {'corr':>5s} "
          f"{'flat%/m':>8s} {'real%/m':>8s} {'Δreal':>7s}")
    grid = [(s, st) for s in (1, 9, 21, 42) for st in (6, 12, 21)]
    best = None
    for sm, st in grid:
        cv = bt_carry_v(C, ret, beta, smooth=sm, step=st)
        a_f, *_ = evaluate(cv, flat_xc, flat_tr)
        a_r, L, dd, corr, csh = evaluate(cv, real_all, real_all)
        tv = turnover(cv)
        smlbl = "inst" if sm == 1 else f"{sm*8//24}d"
        stlbl = f"{st*8}h"
        flag = ""
        if (best is None or a_r > best[0]):
            best = (a_r, sm, st, tv, corr, dd); flag = " *"
        print(f"  {smlbl:>7s} {stlbl:>5s} {tv:6.0f}x {csh:7.2f} {corr:5.2f} "
              f"{a_f/12:7.2f}% {a_r/12:7.2f}% {(a_r-a_real)/12:+6.2f}{flag}")

    # ── ESTRÉS por sub-períodos: la mejora debe estar REPARTIDA, no concentrada ──
    def quartile_sh(carry):
        df = net_series(real_all, real_all, carry)
        combo = (df * vol_parity_weights(df)).sum(axis=1)
        L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
        r = (combo*L).dropna(); n = len(r); out = []
        for a, b in [(0,.25),(.25,.5),(.5,.75),(.75,1.)]:
            seg = r.iloc[int(n*a):int(n*b)]
            out.append(seg.mean()/seg.std()*np.sqrt(365) if seg.std() > 0 else 0)
        return out

    print("\nESTRÉS — Sharpe del combinado (slip-real) por cuartil temporal:")
    cands = [("actual  inst/48h ", bt_carry_v(C, ret, beta, 1, 6)),
             ("inst/168h (spike?)", bt_carry_v(C, ret, beta, 1, 21)),
             ("7d/48h            ", bt_carry_v(C, ret, beta, 21, 6)),
             ("7d/168h           ", bt_carry_v(C, ret, beta, 21, 21))]
    print(f"  {'variante':<18s} {'Q1':>6s} {'Q2':>6s} {'Q3':>6s} {'Q4':>6s}")
    for lbl, cv in cands:
        q = quartile_sh(cv)
        print(f"  {lbl:<18s} " + " ".join(f"{x:6.2f}" for x in q))

    print("\nVEREDICTO: elegir la variante robusta (mejora repartida en los 4 cuartiles + corr<0.35 +")
    print("maxDD sano), NO el pico no-monótono. Implementar solo si pasa el estrés.")


if __name__ == "__main__":
    main()
