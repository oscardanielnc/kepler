"""
E53 — RETIRAR MONEDAS FINAS del universo GLOBAL (idea de Oscar; MONITOREO TODO). (2026-06-02).
XLM/HBAR/ZEC/LIT concentran el SLIPPAGE real (hasta ~52 bps en DEMO; e18 las modela como las de menor
ADV). Pregunta (regla de oro): **¿su aporte de edge PAGA su coste de ejecución?** Si quitarlas del
universo MEJORA el %/mes NETO de coste realista @ancla → retirar; si la pierde → su edge compensa.

Método: reúsa la maquinaria de e18 (backtests con turnover por-símbolo + modelo de slippage ADV K50).
Se reconstruye el sistema 7-sleeves (trend CAPADO 0.25 como en prod, leverage con HAIRCUT 0.85) para:
  • UNIVERSO COMPLETO (23 coins de historia larga) — baseline.
  • quitando CADA fina (LOO) y el GRUPO entero — bajo coste FLAT (solo edge) y REALISTA (edge−slip).
El Δ%/mes (reducido − completo) bajo coste REALISTA = beneficio NETO de retirar. >0 → retirar.

No toca producción. python -m research.e53_thin_coins
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, load_panel, _cap_normalize, DRIVER, SLEEVES
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import bt_xs, bt_carry, adv_usd, compound_daily

MAKER = config.MAKER_FEE
HAIRCUT = config.LEVERAGE_HAIRCUT
FINE = ["XLMUSDT", "HBARUSDT", "ZECUSDT", "LITUSDT"]


def bt_trend_capped(C):
    """trend CAPADO (como engine.trend_sleeve nuevo): cesta normalizada + cap 0.25. Devuelve
    (pnl_gross_daily, turn_df_daily, lev_daily) para aplicar el coste por-símbolo aparte."""
    px = C.resample("1D").last(); ret = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0)
    vol = ret.rolling(30).std()
    scal = (0.20/np.sqrt(365) / vol).clip(0, 3)
    pos = (sig.shift(1) * scal).fillna(0)
    W = pos.copy()
    for i in range(len(pos)):
        W.iloc[i] = _cap_normalize(pos.iloc[i].values.astype(float), config.MAX_WEIGHT_NORMAL)
    pnl = (W * ret).sum(axis=1)
    pv = pnl.rolling(30).std().shift(1); lev = (0.15/np.sqrt(365)/pv).clip(0, 4).fillna(1)
    turn = (W - W.shift(1)).abs().fillna(0.0)
    return pnl, turn, lev


def slip_adv(adv_M, cols, mult=1.0):
    """Modelo de slippage por liquidez (e18 K50): slip_i = clip(50/√ADV_$M, 0.5, 30) bps · mult."""
    s = (50.0 / np.sqrt(adv_M) * mult).clip(0.5, 30.0) / 1e4
    return s.reindex(cols).fillna(0.5/1e4)


def build_system(Cfull, panels, adv_M, drop=(), slip_mult=None):
    """Reconstruye el combinado 7-sleeves para el universo (Cfull menos `drop`). Si slip_mult=None →
    coste FLAT maker; si es número → maker + slip ADV×mult por-símbolo. Ancla con haircut. Devuelve dict."""
    keep = [c for c in Cfull.columns if c not in drop]
    C = Cfull[keep]
    ret = np.log(C).diff(); beta = _beta(ret)
    cols = list(C.columns)
    # coste por-símbolo
    if slip_mult is None:
        slip_xc = pd.Series(MAKER, index=cols); slip_tr = pd.Series(MAKER, index=cols)
    else:
        sl = slip_adv(adv_M, cols, slip_mult)
        slip_xc = pd.Series(MAKER, index=cols) + sl
        slip_tr = pd.Series(MAKER, index=cols) + sl
    # sleeves xs + carry (bruto + turnover) → neto
    series = {}
    for name, typ, hold in SLEEVES:
        if typ == "xs_mom":   sc = alphas.xs_momentum_score(ret, hold)
        elif typ == "xs_rev": sc = alphas.xs_reversal_score(ret, hold)
        elif typ == "xs_lowvol": sc = alphas.xs_lowvol_score(ret, hold)
        elif typ == "xs_flow": sc = alphas.xs_takerflow_score(panels["volume"][cols], panels["taker_buy_volume"][cols], hold)
        elif typ == "xs_hlpos": sc = alphas.xs_hlposition_score(C, hold)
        else: sc = None
        if typ in ("xs_mom", "xs_rev", "xs_lowvol", "xs_flow", "xs_hlpos"):
            ts, pg, turn = bt_xs(C, ret, beta, sc, hold)
            cost = (turn * slip_xc.reindex(turn.columns).fillna(0)).sum(axis=1).values
            series[name] = compound_daily(ts, pg - cost)
    ts, pg, turn = bt_carry(C, ret, beta)
    cost = (turn * slip_xc.reindex(turn.columns).fillna(0)).sum(axis=1).values
    series["carry"] = compound_daily(ts, pg - cost)
    pnl, turn, lev = bt_trend_capped(C)
    cost = (turn * slip_tr.reindex(turn.columns).fillna(0)).sum(axis=1)
    series["trend"] = ((pnl - cost) * lev).dropna()
    df = pd.concat(series, axis=1).dropna()
    combo = (df * vol_parity_weights(df)).sum(axis=1)
    L = min(HAIRCUT * leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    m = metrics(combo * L)
    return {"sharpe": m["sharpe"], "ann": m["ann"], "mes": m["ann"]/12, "maxdd": m["maxdd"], "lev": L,
            "n": len(cols), "combo": combo}


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E53 — ¿retirar monedas finas (XLM/HBAR/ZEC/LIT)? ¿su edge paga su slippage?\n")
    Cfull = load()
    panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], Cfull)
    adv = adv_usd(panels["quote_volume"]).reindex(Cfull.columns).fillna(0.0)
    adv_M = (adv/1e6).clip(lower=1.0)
    yrs = (Cfull.index[-1] - Cfull.index[0]).days / 365.25

    # perfil de liquidez de las finas + su drag anual de slippage (turnover×slip, todos los sleeves)
    sl_bps = (slip_adv(adv_M, list(Cfull.columns)) * 1e4)
    print("PERFIL de las finas (ADV y slippage modelado one-way):")
    prof = pd.DataFrame({"ADV_$M/día": (adv/1e6), "slip_bps": sl_bps})
    print(prof.loc[FINE].round(2).to_string())
    print(f"  (referencia: slip mediana universo {sl_bps.median():.1f} bps · máx {sl_bps.max():.1f} {sl_bps.idxmax()})\n")

    # baseline
    base_flat = build_system(Cfull, panels, adv_M, drop=(), slip_mult=None)
    base_real = build_system(Cfull, panels, adv_M, drop=(), slip_mult=1.0)
    base_str  = build_system(Cfull, panels, adv_M, drop=(), slip_mult=3.0)
    print(f"BASELINE universo completo ({base_flat['n']} coins):")
    print(f"  FLAT(solo maker): {base_flat['mes']:.2f}%/mes Sh {base_flat['sharpe']:.2f} maxDD {base_flat['maxdd']:.1f}")
    print(f"  REALISTA(ADV K50): {base_real['mes']:.2f}%/mes Sh {base_real['sharpe']:.2f} maxDD {base_real['maxdd']:.1f} ← número honesto")
    print(f"  ESTRÉS(ADV ×3):    {base_str['mes']:.2f}%/mes Sh {base_str['sharpe']:.2f}\n")

    def half_sh(combo):
        h = len(combo)//2
        return metrics(combo.iloc[:h]).get("sharpe", float("nan")), metrics(combo.iloc[h:]).get("sharpe", float("nan"))

    print("ABLACIÓN (Δ%/mes vs baseline; >0 = quitar MEJORA). FLAT=solo edge · REAL=edge−slip · ×3=estrés")
    print(f"{'quitar':>16s} │ {'FLAT Δ':>8s} {'REAL Δ':>8s} {'×3 Δ':>7s} │ {'REAL %/mes':>10s} {'Sh':>5s} {'IS/OOS':>11s} {'maxDD':>6s}")
    print("─" * 92)
    variants = [(f,) for f in FINE] + [
        ("XLMUSDT", "HBARUSDT"),              # par OOS-robusto (ambas mejoran OOS sueltas)
        ("XLMUSDT", "LITUSDT"),
        ("XLMUSDT", "HBARUSDT", "LITUSDT"),   # retirar todo MENOS ZEC (la que tiene edge)
        tuple(FINE),                          # grupo entero
    ]
    names = {("XLMUSDT","HBARUSDT"): "−XLM,HBAR",
             ("XLMUSDT","LITUSDT"): "−XLM,LIT",
             ("XLMUSDT","HBARUSDT","LITUSDT"): "−XLM,HBAR,LIT",
             tuple(FINE): "−GRUPO(4)"}
    for drop in variants:
        rf = build_system(Cfull, panels, adv_M, drop=drop, slip_mult=None)
        rr = build_system(Cfull, panels, adv_M, drop=drop, slip_mult=1.0)
        rs = build_system(Cfull, panels, adv_M, drop=drop, slip_mult=3.0)
        lbl = names.get(drop, "−" + drop[0].replace("USDT", ""))
        dflat = rf["mes"] - base_flat["mes"]; dreal = rr["mes"] - base_real["mes"]; dstr = rs["mes"] - base_str["mes"]
        s1, s2 = half_sh(rr["combo"])
        mark = "  ← retirar" if dreal > 0.05 else ("  ~neutral" if abs(dreal) <= 0.05 else "  ← MANTENER")
        print(f"{lbl:>16s} │ {dflat:>+7.2f}% {dreal:>+7.2f}% {dstr:>+6.2f}% │ {rr['mes']:>9.2f}% {rr['sharpe']:>5.2f} {s1:>5.2f}/{s2:<5.2f} {rr['maxdd']:>6.1f}{mark}")
    b1, b2 = half_sh(base_real["combo"])
    print(f"{'(baseline)':>16s} │ {'—':>7s}  {'—':>7s}  {'—':>6s}  │ {base_real['mes']:>9.2f}% {base_real['sharpe']:>5.2f} {b1:>5.2f}/{b2:<5.2f} {base_real['maxdd']:>6.1f}")

    print("\nLECTURA: FLAT Δ>0 = la coin DRAGA el edge (pierde antes de slippage). REAL Δ>0 = retirar mejora")
    print("el neto. ZEC tiene edge (quitarla daña) → el GRUPO entero es mala idea; retirar el subconjunto")
    print("correcto (lastres + slippage, conservando ZEC) es lo que mejora. Confirmar IS/OOS. Decisión Oscar.")


if __name__ == "__main__":
    main()
