"""
E44 — MODELO DE EJECUCIÓN INTRADÍA (INTRADAY.md §3.2). 2026-06-01.
Fase 1 (e42) dio un MTM horario que reconcilia con el motor (corr bloque 1.000). Pero a horizonte
SUB-DIARIO el COSTE DOMINA (lección carry-instantáneo e19: 199x turnover → perdedor neto). Sin modelar
el cruce del spread, cualquier Sharpe intradía es ficción. Este módulo añade el coste realista por
rebalanceo (taker + slippage por liquidez ADV, por símbolo) al backtester horario, y expone la API que
la Fase 2 usará para evaluar el order-book a holds 1h–12h.

API: eval_intraday(C, beta, score, hold, cost_vec) → {sharpe, ann, turnover/año, serie diaria}.
DEMO: barre un sleeve a holds {1,2,4,6,12,24}h mostrando cómo el coste mata los horizontes cortos
(turnover explota) → valida que el modelo se comporta y deja claro el listón para Fase 2.

python -m research.e44_intraday_cost
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, _weights_from_score, load_panel, DRIVER, BETA_W
from kepler.portfolio import metrics, leverage_for_maxdd_anchor
from research.e18_slippage import adv_usd

MAKER, TAKER = config.MAKER_FEE, config.TAKER_FEE


def slip_adv(dvol, cols, mult=1.0):
    """Slippage por liquidez (e18): K/√ADV_$M, clip [0.5,30]bps. Series por símbolo (fracción)."""
    adv_M = (adv_usd(dvol).reindex(cols).fillna(0.0) / 1e6).clip(lower=1.0)
    return (50.0/np.sqrt(adv_M)*mult).clip(0.5, 30.0).div(1e4).reindex(cols).fillna(0.5/1e4)


def cost_vector(cols, dvol, mode="taker_adv"):
    """Coste one-way por símbolo (fracción de notional) según el modo de ejecución intradía."""
    if mode == "maker":
        return pd.Series(MAKER, index=cols)
    if mode == "taker":
        return pd.Series(TAKER, index=cols)
    if mode == "taker_adv":          # taker + slippage por liquidez (realista intradía)
        return TAKER + slip_adv(dvol, cols, 1.0)
    if mode == "taker_adv3":         # estrés
        return TAKER + slip_adv(dvol, cols, 3.0)
    raise ValueError(mode)


def eval_intraday(C, beta, score_df, hold, cost_vec):
    """MTM horario buy-and-hold (e42) con coste por símbolo al rebalancear. Devuelve dict de métricas.
    cost_vec: Series por símbolo (fracción one-way). El coste se cobra sobre |Δw_i| de cada símbolo."""
    syms = [s for s in C.columns if s != DRIVER]
    px = C[syms]; pxd = C[DRIVER]
    cb = float(cost_vec.get(DRIVER, cost_vec.reindex(syms).median()))
    idx = list(range(BETA_W + hold, len(C) - hold, hold))
    prevw = pd.Series(0.0, index=syms); prevh = 0.0
    eq = 1.0; ts = [C.index[idx[0]]]; curve = [eq]; tot_turn = 0.0
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        dcost = float((w - prevw).abs().mul(cost_vec.reindex(syms).fillna(cb)).sum()) + abs(h - prevh) * cb
        tot_turn += float((w - prevw).abs().sum()) + abs(h - prevh)
        p0 = px.iloc[t]; pd0 = pxd.iloc[t]; block_start = eq * (1 - dcost)
        for k in range(1, hold + 1):
            cr = (px.iloc[t + k] / p0 - 1.0).reindex(w.index).fillna(0.0)
            crd = pxd.iloc[t + k] / pd0 - 1.0
            curve.append(block_start * (1.0 + float((w * cr).sum()) + h * float(crd))); ts.append(C.index[t + k])
        eq = curve[-1]; prevw, prevh = w, h
    eqs = pd.Series(curve, index=ts)
    daily = eqs.resample("1D").last().ffill().pct_change().dropna()
    yrs = (ts[-1] - ts[0]).days / 365.25
    m = metrics(daily); L = leverage_for_maxdd_anchor(daily, config.TARGET_MAXDD)
    ann_anch = metrics(daily * L)["ann"]
    return {"sharpe": m["sharpe"], "ann": m["ann"], "turnover": tot_turn / yrs,
            "ann_anchored": ann_anch, "lev": L, "daily": daily}


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E44 — MODELO DE COSTE INTRADÍA (backtester horario + cruce de spread)\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); cols = list(C.columns)
    dvol = load_panel(["quote_volume"], C)["quote_volume"]
    cmaker = cost_vector(cols, dvol, "maker"); ctaker = cost_vector(cols, dvol, "taker_adv")
    print(f"Coste one-way: maker {MAKER*1e4:.1f}bps · taker {TAKER*1e4:.1f}bps + slip ADV "
          f"(mediana {slip_adv(dvol,cols).median()*1e4:.1f}bps, máx {slip_adv(dvol,cols).max()*1e4:.1f}bps)\n")

    # DEMO: momentum a varios holds → el coste mata los horizontes cortos
    score = alphas.xs_momentum_score(ret, 720)
    print("DEMO — mom_30d a varios holds (turnover/año · Sharpe@maker · Sharpe@taker+ADV · %/mes anclado):")
    print(f"  {'hold':>6s} {'turn/año':>9s} {'Sh maker':>9s} {'Sh tk+ADV':>10s} {'%/mes mk':>9s} {'%/mes tk':>9s}")
    for hold in (1, 2, 4, 6, 12, 24, 168, 720):
        try:
            rm = eval_intraday(C, beta, score, hold, cmaker)
            rt = eval_intraday(C, beta, score, hold, ctaker)
            print(f"  {hold:>5d}h {rm['turnover']:9.0f} {rm['sharpe']:9.2f} {rt['sharpe']:10.2f} "
                  f"{rm['ann_anchored']/12:9.2f} {rt['ann_anchored']/12:9.2f}")
        except Exception as e:
            print(f"  {hold:>5d}h ERROR {str(e)[:40]}")

    print("\nLECTURA: a holds cortos el turnover explota y el coste taker+slip hunde el Sharpe → confirma")
    print("que el modelo se comporta (e19/INTRADAY.md). La Fase 2 usará eval_intraday(C,beta,OB_score,hold,")
    print("cost_vector('taker_adv')) con el imbalance 30s→horario (e43) para ver si el order-book sobrevive")
    print("el coste a 1h–12h. Admisión: subir el retorno al maxDD fijo con coste real (no solo corr+IS/OOS).")


if __name__ == "__main__":
    main()
