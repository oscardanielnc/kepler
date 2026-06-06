"""
E71 — DOLLAR-NEUTRALIZACIÓN PARCIAL del libro combinado (Oscar 2026-06-05, tras crash 06-02/05).

CONTEXTO: el crash dejó claro que la pérdida es MTM vía el tilt NET-LONG en dólares. El libro es
β-MODELO ≈0 (neutralidad de regresión) pero β-DÓLAR +0.24 (Σ wᵢ·βᵢ), que genera `trend` long-only
sin hedge. En un selloff broad, los largos caen más de lo que los cortos ganan → drawdown.

PREGUNTA DE OSCAR (NO es market timing; es estructural, no predice nada): si añadimos un hedge en BTC
que cancela una fracción λ de la β-dólar CADA rebalanceo, ¿baja el maxDD lo suficiente como para
RE-anclar más leverage (flywheel, regla de oro) y dar IGUAL o MÁS retorno al MISMO maxDD −10%?
  - Si algún λ mejora el retorno a igual riesgo → candidato real (validar OOS, luego Oscar decide).
  - Si neutralizar SIEMPRE cuesta retorno a igual maxDD → el net-long es el PRECIO del edge de trend
    (igual que la concentración en e60); aceptarlo, el control de riesgo es el dial de leverage.

MÉTODO (honesto, a nivel de NOMBRE, mismo molde que e60):
  1. Reconstruye el panel DIARIO de pesos de cada sleeve tal como el motor arma el `target` vivo y los
     combina por vol-parity → `book_1x` (β-hedge por-sleeve ya incluido vía DRIVER).
  2. OVERLAY: para cada λ, cada día calcula β-dólar_t = Σ wᵢ·βᵢ (β = beta por-símbolo vs BTC, β_BTC=1)
     y añade al DRIVER un hedge −λ·β-dólar_t → la β-dólar resultante queda en (1−λ)·β-dólar_t.
  3. RE-ANCLA el leverage por bisección para clavar maxDD=−10% sobre el libro neutralizado (flywheel),
     aplicando el cap por-nombre de producción a los NO-DRIVER (el hedge en BTC va exento, es deliberado).
  4. Mide Sharpe (IS/OOS), ann/mes, maxDD, mo+, y la β-dólar / β-regresión resultantes.

No toca producción. python -m research.e71_dollar_neutralization
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas, engine
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel,
                           DRIVER, SLEEVES)
from research.e60_concentration_cap_aggregate import (xs_panel, carry_panel, trend_panel, _to_daily,
                                                      _maxdd)
from kepler.portfolio import vol_parity_weights, metrics

TARGET = config.TARGET_MAXDD          # 0.10
HAIRCUT = config.LEVERAGE_HAIRCUT     # 0.95
LEV_CAP = config.MAX_STRAT_LEVERAGE   # 4.0
CAP = config.MAX_POSITION_EQUITY      # cap por-nombre de prod (e69), se aplica a NO-DRIVER


def neutralize(book_1x: pd.DataFrame, beta_daily: pd.DataFrame, lam: float) -> pd.DataFrame:
    """Añade al DRIVER un hedge −λ·β-dólar (β-dólar = Σ wᵢ·βᵢ, β_BTC=1). Como β_BTC=1, la β-dólar
    resultante queda en (1−λ)·β-dólar. λ=0 → libro original; λ=1 → dollar-neutral total."""
    if lam == 0:
        return book_1x.copy()
    b = book_1x.copy()
    bd = (b * beta_daily.reindex(b.index).reindex(columns=b.columns).fillna(0.0)).sum(axis=1)
    b[DRIVER] = b[DRIVER] - lam * bd
    return b


def book_returns(book_neutral_1x: pd.DataFrame, rd: pd.DataFrame, lev: float):
    """Libro neutralizado ×lev, cap por-nombre a NO-DRIVER (hedge BTC exento), retorno neto de costes."""
    bl = book_neutral_1x * lev
    nd = [c for c in bl.columns if c != DRIVER]
    bl[nd] = bl[nd].clip(-CAP, CAP)
    pnl = (bl.shift(1) * rd).sum(axis=1)
    turn = (bl - bl.shift(1)).abs().sum(axis=1).fillna(0.0)
    r = (pnl - turn * config.MAKER_FEE).dropna()
    return r, bl


def anchor_lev(book_neutral_1x, rd):
    """Bisección: leverage que clava maxDD=−TARGET. Si ni con LEV_CAP se alcanza → LEV_CAP·haircut."""
    lo, hi = 0.05, LEV_CAP
    if abs(_maxdd(book_returns(book_neutral_1x, rd, hi)[0])) < TARGET:
        return hi * HAIRCUT
    for _ in range(50):
        mid = (lo + hi) / 2
        dd = abs(_maxdd(book_returns(book_neutral_1x, rd, mid)[0]))
        if dd > TARGET:
            hi = mid
        else:
            lo = mid
    return lo * HAIRCUT


def reg_beta(r: pd.Series, rd_btc: pd.Series) -> float:
    v = pd.concat([r.rename("p"), rd_btc.rename("b")], axis=1).dropna()
    if len(v) < 30 or v["b"].var() == 0:
        return float("nan")
    return float(np.cov(v["p"], v["b"])[0, 1] / np.var(v["b"]))


def evaluate(book_1x, beta_daily, rd, rd_btc, lam):
    bn = neutralize(book_1x, beta_daily, lam)
    lev = anchor_lev(bn, rd)
    r, bl = book_returns(bn, rd, lev)
    m = metrics(r)
    half = len(r) // 2
    sh1 = metrics(r.iloc[:half]).get("sharpe", float("nan"))
    sh2 = metrics(r.iloc[half:]).get("sharpe", float("nan"))
    last = bl.iloc[-1]
    bd_last = float((last * beta_daily.iloc[-1].reindex(last.index).fillna(0.0)).sum())
    net = float(last.sum()); gross = float(last.abs().sum())
    bhedge = float(last.get(DRIVER, 0.0))
    rb = reg_beta(r, rd_btc)
    print(f"λ={lam:.2f} │ lev {lev:4.2f}x │ Sh {m.get('sharpe',0):.2f} (IS {sh1:.2f}/OOS {sh2:.2f}) "
          f"maxDD {m.get('maxdd',0):6.1f} ann {m.get('ann',0):5.1f}% ({m.get('ann',0)/12:4.2f}%/mes) "
          f"mo+ {m.get('mo_pos',0):3.0f}% │ β$ {bd_last:+.2f} βreg {rb:+.2f} net {net:+.2f} "
          f"BTC {bhedge:+.2f} gross {gross:.2f}")
    return m, bd_last


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E71 — dollar-neutralización parcial (flywheel: re-ancla lev a maxDD −10%, compara retorno a igual riesgo)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)

    series, panels = {}, {}
    score_map = {
        "mom_30d":    (alphas.xs_momentum_score(ret, 720), 720),
        "rev_60d":    (alphas.xs_reversal_score(ret, 1440), 1440),
        "lowvol_14d": (alphas.xs_lowvol_score(ret, 336), 336),
        "takerflow_5d": (alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120),
        "hlpos_14d":  (alphas.xs_hlposition_score(C, 336), 336),
    }
    for name, typ, hold in SLEEVES:
        if name in score_map:
            sc, h = score_map[name]
            series[name] = xs_sleeve(C, ret, beta, sc, h)[0]
            panels[name] = xs_panel(C, ret, beta, sc, h)
        elif typ == "carry":
            series[name] = carry_sleeve(C, ret, beta)[0]
            panels[name] = carry_panel(C, ret)
        else:
            series[name] = trend_sleeve(C)[0]
            panels[name] = trend_panel(C)

    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    print(f"vol-parity: {vp.round(3).to_dict()}\n")

    book_1x = pd.DataFrame(0.0, index=panels["trend"].index, columns=C.columns)
    for name in series:
        p = panels[name].reindex(book_1x.index).ffill().fillna(0.0)
        book_1x = book_1x.add(float(vp[name]) * p, fill_value=0.0)
    rd = C.resample("1D").last().reindex(book_1x.index).pct_change()
    rd_btc = rd[DRIVER]
    beta_daily = beta.resample("1D").last().reindex(book_1x.index).ffill().fillna(0.0)

    # reconciliación de la β-dólar a 1x del último día con el motor (sanity)
    tgt_eng, _, _, _, _, lev_eng, _, beta_last, _ = engine.compute_target("ESTABLE")
    bd_eng = float((tgt_eng.reindex(beta_last.index).fillna(0.0) * beta_last).sum())
    print(f"motor: lev {lev_eng:.2f}x · β-dólar vivo {bd_eng:+.3f} (lo que reporta el snapshot)\n")

    print(f"{'overlay':10s}{'':2s}{'sistema combinado @ maxDD −10% (haircut '+str(HAIRCUT)+')':>62s}")
    print("─" * 130)
    for lam in [0.0, 0.25, 0.50, 0.75, 1.0]:
        evaluate(book_1x, beta_daily, rd, rd_btc, lam)

    print("\nLECTURA (regla de oro / flywheel): el GANADOR sube (o iguala) ann%/mes a maxDD −10% bajando")
    print("la β-dólar, con IS≈OOS. Si neutralizar SIEMPRE cuesta retorno a igual maxDD → el net-long es el")
    print("precio del edge de trend (como la concentración en e60); el dial de leverage ya controla el riesgo.")
    print("β$ = β-dólar (Σwβ) del último día · βreg = β de regresión realizada · net = Σw · BTC = hedge en driver.")


if __name__ == "__main__":
    main()
