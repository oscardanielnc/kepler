"""
E52 — CONCENTRACIÓN: cap por-activo en `trend` (MONITOREO §2.1). (2026-06-02). El diagnóstico mostró
que la posición top del libro (TRX ~20% del equity) es **78% `trend`**: el sleeve es long-only y
vol-target → vuelca ~47% de su gross en la coin de menor vol que esté en tendencia (TRX). Riesgo de un
solo nombre, contrario a la misión copy-lead de bajo-DD.

PREGUNTA (regla de oro): ¿poner un cap por-activo en `trend` MEJORA o al menos NO degrada los números
del SISTEMA (Sharpe / maxDD / %/mes @ancla con haircut) mientras baja la concentración?

Método: se reconstruyen los 6 sleeves no-trend una vez. Para cada variante de `trend` (producción vs
cap C) se recombina por vol-parity, se ancla el leverage con haircut, y se mide el combinado + el
`top_position` del libro live resultante. El cap se aplica CONSISTENTE en backtest y en pesos live
(normaliza a gross 1 cada día, capa cada coin a C, renormaliza). cap=None = trend de PRODUCCIÓN exacto.

No toca producción. python -m research.e52_trend_concentration_cap
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

HAIRCUT = config.LEVERAGE_HAIRCUT   # 0.85 (D0)


def _cap_normalize_row(v: np.ndarray, cap: float) -> np.ndarray:
    """v ≥ 0 (long-only). Normaliza a suma 1 y redistribuye el exceso sobre `cap` hacia los no-topados,
    iterando hasta que cada peso ≤ cap (clásico water-filling). Devuelve pesos suma≈1 con tope `cap`."""
    s = v.sum()
    if s <= 0:
        return v
    w = v / s
    for _ in range(20):
        over = w > cap + 1e-9
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over
        pool = w[under].sum()
        if pool <= 0:
            break
        w[under] += excess * w[under] / pool
    return w


def trend_capped(C, cap=None):
    """trend long-only EMA20/100 vol-target. cap=None → idéntico a engine.trend_sleeve (.mean de pos).
    cap=C → cada día normaliza pos a gross 1, capa cada coin a C, renormaliza; backtest y live usan
    la MISMA cesta (return = Σ wᵢ·retᵢ). Mismo overlay de vol-target y costo de turnover."""
    px = C.resample("1D").last(); ret = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0)
    vol = ret.rolling(30).std()
    scal = (0.20 / np.sqrt(365) / vol).clip(0, 3)
    pos = (sig.shift(1) * scal).fillna(0)
    if cap is None:
        # PRODUCCIÓN: pnl = media de pos·ret (sin normalizar) — reproduce engine.trend_sleeve
        turn = (pos - pos.shift(1)).abs().fillna(0.0)
        pnl = (pos * ret).mean(axis=1) - (turn * config.MAKER_FEE).mean(axis=1)
        pn = pos.iloc[-1]
        w_now = (pn / pn.abs().sum()) if pn.abs().sum() > 0 else pn
    else:
        # CAPPED: cesta normalizada-capada cada día (consistente backtest↔live)
        W = pos.copy()
        for i in range(len(pos)):
            W.iloc[i] = _cap_normalize_row(pos.iloc[i].values.astype(float), cap)
        turn = (W - W.shift(1)).abs().fillna(0.0)
        pnl = (W * ret).sum(axis=1) - (turn * config.MAKER_FEE).sum(axis=1)
        w_now = W.iloc[-1]
    pv = pnl.rolling(30).std().shift(1); lev = (0.15 / np.sqrt(365) / pv).clip(0, 4).fillna(1)
    series = (pnl * lev).dropna()
    return series, w_now.reindex(C.columns).fillna(0.0)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E52 — cap de concentración en `trend` (¿mejora el sistema y baja el riesgo de un nombre?)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)

    # 6 sleeves NO-trend (una vez): serie + pesos live
    P = load_panel(["volume", "taker_buy_volume"], C)
    base = {}
    base["mom_30d"]    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"]    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"] = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"]      = carry_sleeve(C, ret, beta)
    base["takerflow_5d"] = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"]  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)

    def evaluate(trend_series, trend_w, label, trend_sh, trend_dd):
        series = {k: v[0] for k, v in base.items()}; series["trend"] = trend_series
        weights = {k: v[1] for k, v in base.items()}; weights["trend"] = trend_w
        df = pd.concat(series, axis=1).dropna()
        vp = vol_parity_weights(df)
        port = (df * vp).sum(axis=1)
        lev = min(HAIRCUT * leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
        m = metrics(port * lev)
        # libro live + top_position (máx |peso| del target combinado, % de equity)
        target = pd.Series(0.0, index=C.columns)
        for name in series:
            target = target.add(float(vp[name]) * weights[name].reindex(C.columns).fillna(0), fill_value=0)
        target = (target * lev)
        top = target.abs().sort_values(ascending=False)
        topsym, topval = top.index[0], top.iloc[0]
        hhi = float(((target / target.abs().sum()) ** 2).sum())   # Herfindahl (concentración)
        # robustez: Sharpe IS/OOS por mitades (¿el cap rompe el edge en alguna mitad?)
        half = len(port) // 2
        sh1 = metrics(port.iloc[:half]).get("sharpe", float("nan"))
        sh2 = metrics(port.iloc[half:]).get("sharpe", float("nan"))
        print(f"{label:18s} │ trend Sh {trend_sh:+.2f} dd {trend_dd:5.1f} │ COMB Sh {m['sharpe']:.2f} "
              f"(IS {sh1:.2f}/OOS {sh2:.2f}) maxDD {m['maxdd']:5.1f} {m['ann']/12:5.2f}%/mes lev {lev:.2f}x │ "
              f"top {topsym.replace('USDT',''):5s} {topval*100:4.1f}% · HHI {hhi:.3f}")
        return m

    print(f"{'variante':18s} │ {'trend solo':>18s} │ {'sistema combinado (haircut '+str(HAIRCUT)+')':>42s} │ concentración")
    print("─" * 120)
    # BASELINE = trend de producción
    ts, tw = trend_capped(C, cap=None); tm = metrics(ts)
    evaluate(ts, tw, "PRODUCCIÓN (sin cap)", tm["sharpe"], tm["maxdd"])
    # normalizado sin cap (aísla el efecto de cambiar .mean→Σw, antes del cap)
    ts, tw = trend_capped(C, cap=1.0); tm = metrics(ts)
    evaluate(ts, tw, "normaliz. sin cap", tm["sharpe"], tm["maxdd"])
    for cap in [0.40, 0.30, 0.25, 0.20, 0.15]:
        ts, tw = trend_capped(C, cap=cap); tm = metrics(ts)
        evaluate(ts, tw, f"cap {cap:.2f}", tm["sharpe"], tm["maxdd"])

    print("\nLECTURA: buscar el cap que BAJA `top%`/HHI manteniendo (o subiendo) Sharpe/%/mes combinado y")
    print("maxDD ≤ baseline. Si ningún cap mejora sin coste → la concentración es el precio del edge de")
    print("`trend` (decisión de Oscar: aceptar el riesgo de 1 nombre vs ceder retorno). Regla de oro.")


if __name__ == "__main__":
    main()
