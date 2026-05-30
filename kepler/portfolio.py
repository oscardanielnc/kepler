"""
Kepler — CONSTRUCTOR DE PORTAFOLIO (validado en E6, research/e6_combine.py).
Combina los sleeves validados (kepler/alphas.py) con vol-parity, aplica el dial de
leverage y mide el riesgo contra el ancla. Es la lógica de combinación lista para
producción; el motor de ejecución en vivo la consumirá.

Validado 2026-05-29: carry + stat-arb, correlación ~0 → combinado Sharpe +1.18
(IS +1.12 / OOS +1.33), vol 15.7%, maxDD −14.3% a 1x. Diversificación confirmada.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def vol_parity_weights(sleeve_rets: pd.DataFrame, is_frac: float = 0.70) -> pd.Series:
    """Pesos inversamente proporcionales a la vol de cada sleeve (medida en IS, sin lookahead)."""
    cut = int(len(sleeve_rets) * is_frac)
    vol = sleeve_rets.iloc[:cut].std().replace(0, np.nan)
    w = (1.0 / vol).fillna(0.0)
    return w / w.sum() if w.sum() > 0 else w


def combine(sleeve_rets: pd.DataFrame, weights: pd.Series | None = None,
            leverage: float = 1.0) -> pd.Series:
    """Retorno del portafolio combinado = Σ wᵢ·rᵢ × leverage."""
    if weights is None:
        weights = vol_parity_weights(sleeve_rets)
    return sleeve_rets.mul(weights, axis=1).sum(axis=1) * leverage


def metrics(r: pd.Series, ppy: int = 365) -> dict:
    r = r.dropna()
    if len(r) < 30 or r.std() == 0:
        return {}
    sh = r.mean() / r.std() * np.sqrt(ppy)
    ann = (1 + r.mean()) ** ppy - 1
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    return dict(sharpe=sh, ann=ann * 100, vol=r.std() * np.sqrt(ppy) * 100, maxdd=dd * 100,
                mo_med=m.median() * 100, mo_pos=(m > 0).mean() * 100, mo_worst=m.min() * 100,
                calmar=ann / abs(dd) if dd < 0 else 0.0)


def leverage_for_target_vol(r: pd.Series, target_vol_annual: float, ppy: int = 365) -> float:
    v = r.std() * np.sqrt(ppy)
    return target_vol_annual / v if v > 0 else 1.0


def leverage_for_monthly_dd_anchor(r: pd.Series, max_monthly_dd: float = 0.08,
                                   ppy: int = 365) -> float:
    """Mayor leverage tal que el peor mes histórico no supere max_monthly_dd."""
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    worst = m.min()
    return abs(max_monthly_dd / worst) if worst < 0 else 5.0


def _maxdd(r: pd.Series, lev: float) -> float:
    """|maxDD| de la curva de equity compuesta con leverage `lev` (valor positivo)."""
    eq = (1 + r * lev).cumprod()
    return float(abs((eq / eq.cummax() - 1).min()))


def leverage_for_maxdd_anchor(r: pd.Series, target_maxdd: float = 0.10,
                              lo: float = 0.05, hi: float = 4.0, iters: int = 60) -> float:
    """Leverage de estrategia tal que el maxDD del backtest = target_maxdd.
    Regla de producto (Oscar 2026-05-30): el maxDD es el ancla fija; el leverage se calcula
    para clavarlo. El maxDD crece monótono con el leverage → bisección. Si ni con `hi` se
    alcanza el target (curva demasiado suave), devuelve `hi` (cap de seguridad)."""
    r = r.dropna()
    if len(r) < 30 or r.std() == 0:
        return 1.0
    if _maxdd(r, hi) < target_maxdd:
        return hi
    if _maxdd(r, lo) > target_maxdd:
        return lo
    for _ in range(iters):
        mid = (lo + hi) / 2
        if _maxdd(r, mid) < target_maxdd:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research"))
    import e6_combine as e6  # reusa los builders de sleeves diarios
    c = e6.carry_daily(); s, npairs = e6.statarb_daily()
    df = pd.concat({"carry": c, "statarb": s}, axis=1).dropna()
    w = vol_parity_weights(df)
    combo = combine(df, w)
    m = metrics(combo)
    print(f"Sleeves: {list(df.columns)} pesos={w.round(2).to_dict()} | pares stat-arb={npairs}")
    print(f"Combinado 1x: Sharpe {m['sharpe']:.2f} ann {m['ann']:.1f}% vol {m['vol']:.1f}% "
          f"maxDD {m['maxdd']:.1f}% mo_med {m['mo_med']:.2f}%")
    L = leverage_for_monthly_dd_anchor(combo, 0.08)
    mL = metrics(combo * 0 + combine(df, w, L))
    print(f"Leverage para ancla maxDD mensual −8%: {L:.2f}x → ann {mL['ann']:.1f}% "
          f"mo_med {mL['mo_med']:.2f}% mo_worst {mL['mo_worst']:.1f}%")
