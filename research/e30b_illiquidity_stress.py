"""
E30b — ESTRÉS COMPLETO del factor de iliquidez de Amihud (sleeve #8 candidato). 2026-06-01.
e30 mostró illiq_mean_14d con Δ+0.98%/mes al ancla A COSTE MAKER PLANO, pero con banderas:
(1) IS≈0/OOS alto, (2) no es plateau de horizonte (7d negativo, 14d pico), (3) RIESGO ESTRUCTURAL:
un sleeve de iliquidez LONGea los nombres ilíquidos = donde el slippage muerde más.

Este script ataca las 3 con la maquinaria de e18 (port bruto + turnover por símbolo → costo por
liquidez ADV) y el molde de estrés de e16e:

  A. PLATEAU de horizonte (3..45d): ¿14d es robusto o un pico de suerte?
  B. TEST DECISIVO — coste por liquidez: 7-combo vs 8-combo bajo maker-plano / ADV-K50 / ADV×3 /
     10bps-plano. ¿El +0.98 sobrevive cuando el sleeve PAGA el coste real de tradear thin coins?
  C. DIAGNÓSTICO: turnover del sleeve, slip MEDIO que paga illiq vs los otros (¿es el más caro?),
     y qué nombres longea/shortea ahora (¿concentra el long en ilíquidos?).
  D. SUB-PERÍODOS / cuartiles del aporte bajo coste realista (no solo maker).

python -m research.e30b_illiquidity_stress
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, _weights_from_score, load_panel, DRIVER, BETA_W)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import bt_xs, bt_carry, bt_trend, compound_daily, adv_usd

MAKER = config.MAKER_FEE


def illiq_mean_score(absret, dvol, h):
    """log de Amihud clásico (media de |ret|/dvol) sobre h horas. Ilíquido = ALTO → longea ilíquido."""
    return np.log((absret / dvol.replace(0, np.nan)).rolling(h).mean().replace(0, np.nan))


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m["sharpe"], m["ann"], L, m["maxdd"]


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E30b — ESTRÉS COMPLETO factor de iliquidez (Amihud)\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); absret = ret.abs()
    P = load_panel(["volume", "taker_buy_volume", "quote_volume", "high", "low"], C)
    dvol = P["quote_volume"]; cols = list(C.columns)
    yrs = (C.index[-1] - C.index[0]).days / 365.25
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h · {yrs:.1f} años\n")

    # ── modelo de slippage por liquidez (idéntico a e18) ──────────────────────
    adv = adv_usd(dvol).reindex(cols).fillna(0.0); adv_M = (adv/1e6).clip(lower=1.0)
    K_SLIP, FLOOR_BPS, CAP_BPS = 50.0, 0.5, 30.0
    def slip_adv(mult=1.0):
        return (K_SLIP/np.sqrt(adv_M)*mult).clip(FLOOR_BPS, CAP_BPS).div(1e4).reindex(cols).fillna(FLOOR_BPS/1e4)

    # ── 7 sleeves base: bruto + turnover (una vez) ────────────────────────────
    print("Precomputando 7 sleeves base (bruto + turnover)...")
    XS = {}
    XS["mom_30d"]      = bt_xs(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    XS["rev_60d"]      = bt_xs(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    XS["lowvol_14d"]   = bt_xs(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    XS["takerflow_5d"] = bt_xs(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    XS["hlpos_14d"]    = bt_xs(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    CARRY = bt_carry(C, ret, beta); TREND = bt_trend(C)

    def sleeve_net_dict(slip):
        out = {}
        for name, (ts, pg, turn) in XS.items():
            cost = (turn * slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
            out[name] = compound_daily(ts, pg - cost)
        ts, pg, turn = CARRY
        out["carry"] = compound_daily(ts, pg - (turn*slip.reindex(turn.columns).fillna(0)).sum(axis=1).values)
        pnl, turn, lev = TREND
        out["trend"] = ((pnl - (turn*slip.reindex(turn.columns).fillna(0)).mean(axis=1)) * lev).dropna()
        return out

    def illiq_net(h, slip):
        ts, pg, turn = bt_xs(C, ret, beta, illiq_mean_score(absret, dvol, h), h)
        cost = (turn * slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
        return compound_daily(ts, pg - cost), turn

    def combo_anchored(d):
        df = pd.concat(d, axis=1); df.columns = list(d.keys()); df = df.dropna()
        return anchored((df * vol_parity_weights(df)).sum(axis=1))

    maker = pd.Series(MAKER, index=cols)
    def mk(slip): return maker + slip.reindex(cols).fillna(0)

    # ── A. PLATEAU de horizonte (coste maker, comparable a e30) ───────────────
    print("\n── A. PLATEAU de horizonte (Δ%/mes al ancla, coste MAKER plano) ──")
    base_m = sleeve_net_dict(maker); _, ann7_m, _, _ = combo_anchored(base_m)
    print(f"  baseline 7 (maker): {ann7_m/12:.2f}%/mes")
    print(f"  {'horizonte':>10s} {'illiqSh':>8s} {'IS':>6s} {'OOS':>6s} {'Δ%/mes':>8s}")
    for days in (3, 5, 7, 10, 14, 21, 30, 45):
        il, _ = illiq_net(days*24, maker)
        d8 = {**base_m, "illiq": il}; _, ann8, _, _ = combo_anchored(d8)
        print(f"  {days:>8d}d  {sh(il):8.2f} {sh(seg(il,0,.6)):6.2f} {sh(seg(il,.6,1)):6.2f} {(ann8-ann7_m)/12:+8.2f}")

    # ── B. TEST DECISIVO — coste por liquidez (7 vs 8) ────────────────────────
    print("\n── B. TEST DECISIVO: ¿aporta cuando PAGA el coste real de tradear thin coins? ──")
    print(f"  {'escenario':<28s} {'7-combo':>9s} {'8-combo':>9s} {'Δ illiq':>9s} {'lev8':>6s} {'maxDD8':>7s}")
    H = 14*24
    for label, slip in [("maker plano", maker),
                        ("+ ADV K50 (central)", mk(slip_adv(1.0))),
                        ("+ ADV ×3 (estrés)", mk(slip_adv(3.0))),
                        ("+ 10bps plano", pd.Series(MAKER+10/1e4, index=cols))]:
        b = sleeve_net_dict(slip); _, ann7, _, _ = combo_anchored(b)
        il, _ = illiq_net(H, slip)
        _, ann8, L8, dd8 = combo_anchored({**b, "illiq": il})
        print(f"  {label:<28s} {ann7/12:8.2f}% {ann8/12:8.2f}% {(ann8-ann7)/12:+8.2f}% {L8:6.2f} {dd8:6.1f}%")

    # ── C. DIAGNÓSTICO: ¿es el sleeve más caro? ¿longea ilíquidos? ────────────
    print("\n── C. DIAGNÓSTICO de coste/exposición ──")
    il_ts, il_pg, il_turn = bt_xs(C, ret, beta, illiq_mean_score(absret, dvol, H), H)
    s1 = slip_adv(1.0)
    def avg_slip_bps(turn):
        tot = turn.sum().sum()
        return float((turn * s1.reindex(turn.columns).fillna(0)).sum().sum() / tot * 1e4) if tot > 0 else 0.0
    print(f"  turnover illiq: {il_turn.values.sum()/yrs:.1f}x/año  (vs carry ~199x, takerflow ~83x)")
    print(f"  slip MEDIO ponderado-por-turnover que paga cada sleeve (K50, one-way):")
    rows = [("illiq_14d", il_turn)] + [(n, t) for n, (_, _, t) in XS.items()] + [("carry", CARRY[2])]
    for n, t in sorted(rows, key=lambda x: -avg_slip_bps(x[1])):
        print(f"    {n:<14s} {avg_slip_bps(t):5.2f} bps")
    # pesos actuales del sleeve illiq (¿long ilíquido / short líquido?)
    syms = [s for s in cols if s != DRIVER]
    w_now, _ = _weights_from_score(illiq_mean_score(absret, dvol, H).iloc[-1], beta.iloc[-1], syms)
    adv_rank = adv.reindex(syms)
    longs = w_now[w_now > 0].sort_values(ascending=False).head(5)
    shorts = w_now[w_now < 0].sort_values().head(5)
    print(f"  LONG (peso+, ADV $M):  " + ", ".join(f"{s.replace('USDT','')} {adv_rank[s]/1e6:.0f}" for s in longs.index))
    print(f"  SHORT(peso−, ADV $M):  " + ", ".join(f"{s.replace('USDT','')} {adv_rank[s]/1e6:.0f}" for s in shorts.index))

    # ── D. CUARTILES bajo coste realista (no solo maker) ──────────────────────
    print("\n── D. CUARTILES del aporte bajo coste ADV-K50 (¿repartido o clip?) ──")
    bK = sleeve_net_dict(mk(slip_adv(1.0))); ilK, _ = illiq_net(H, mk(slip_adv(1.0)))
    dfK = pd.concat({**bK, "illiq": ilK}, axis=1); dfK.columns = list(bK)+["illiq"]; dfK = dfK.dropna()
    print("  illiq Sharpe por cuartil temporal:  " +
          "  ".join(f"Q{i+1} {sh(seg(dfK['illiq'],a,b)):+.2f}"
                    for i,(a,b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)])))

    print("\n" + "="*64)


if __name__ == "__main__":
    main()
