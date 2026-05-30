"""
Kepler — LIBRERÍA DE ALPHAS VALIDADOS. Sistema FINAL de 5 sleeves (2026-05-29).
Cada sleeve es un generador de señal cross-seccional β-neutral (o el carry), combinado
por vol-parity en kepler/portfolio.py. SOLO entran los que pasan IS+OOS walk-forward.

SISTEMA VALIDADO (5 sleeves, correlaciones ~0, fees Futures+BNB maker 0.018%):
  1. XS-MOMENTUM 30d   score = +retorno_pasado_30d   (motor; el de mayor Sharpe)
  2. XS-REVERSIÓN 60d  score = −retorno_pasado_60d   (anti-corr −0.5 con momentum)
  3. LOW-VOL 14d        score = −vol_14d               (anomalía baja vol; defensivo)
  4. CARRY             short funding alto/long bajo, rebal 48h (estructural)
  5. TREND long-only   EMA20/100 direccional, vol-target (overlay, captura grandes trends)
COMBINADO: Sharpe +1.34 (IS +1.34/OOS +1.48), maxDD −11% (1x). Tiers por leverage:
  1x +21%/−11%DD · 2x +47%/−21%DD · 3x +77%/−31%DD. Validación: research/e14_more_sleeves.py.

DESCARTADOS por walk-forward (NO usar): stat-arb pares (cointegración decae, E8),
reversal corto, lead-lag timing, cash-and-carry absoluto. Ver memorias kepler-e8/e9/e13.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

# Parámetros validados (no tocar sin re-backtest — ver feedback_v2_workflow)
CARRY_REBAL_8H   = 6      # rebalanceo cada 6×8h = 48h
CARRY_SMOOTH     = 1      # EWMA del funding (1 = sin suavizar; 6 baja turnover)
STATARB_PMAX     = 0.01   # cointegración estricta (solo pares robustos)
STATARB_MIN_CORR = 0.80
STATARB_HL       = (12, 1440)   # half-life válido en horas (12h..60d)
STATARB_ZWIN     = 168          # ventana z-score (1 semana en 1h)
STATARB_ENTRY, STATARB_EXIT, STATARB_STOP = 2.0, 0.3, 4.0


# ─── CARRY ────────────────────────────────────────────────────────────────────

def carry_weights(funding_row: pd.Series, beta_row: pd.Series, cap: float) -> tuple[pd.Series, float]:
    """Pesos del sleeve carry en un instante: short funding alto / long bajo,
    dollar-neutral, gross=1, capado, + hedge BTC (β-neutral).
    Devuelve (pesos_por_activo, hedge_btc)."""
    v = funding_row.notna() & beta_row.notna()
    f, b = funding_row[v], beta_row[v]
    score = -(f - f.mean())
    if score.abs().sum() == 0:
        return pd.Series(dtype=float), 0.0
    w = (score / score.abs().sum()).clip(-cap, cap)
    w = w / w.abs().sum()
    hedge = -float((w * b).sum())
    return w, hedge


# ─── SLEEVES CROSS-SECCIONALES β-NEUTRAL (momentum / reversión / low-vol) ──────
# score por activo → pesos dollar-neutral + cap + hedge BTC (β-neutral) en el motor.

def xs_momentum_score(log_ret: pd.DataFrame, lookback_h: int = 720):
    """Momentum cross-seccional: +retorno pasado (validado 30d=720h)."""
    return log_ret.rolling(lookback_h).sum()


def xs_reversal_score(log_ret: pd.DataFrame, lookback_h: int = 1440):
    """Reversión de LARGO plazo: −retorno pasado (validado 60d=1440h; anti-corr con momentum)."""
    return -log_ret.rolling(lookback_h).sum()


def xs_lowvol_score(log_ret: pd.DataFrame, lookback_h: int = 336):
    """Low-vol anomaly: −volatilidad (long baja vol / short alta vol; validado 14d=336h)."""
    return -log_ret.rolling(lookback_h).std()


def xs_takerflow_score(volume: pd.DataFrame, taker_buy_volume: pd.DataFrame, lookback_h: int = 120):
    """Sleeve #6 — FLUJO DE ÓRDENES (validado 2026-05-30, research/e16b+e16c).
    Desbalance comprador = taker_buy/volume − 0.5, promediado en `lookback_h` (validado 5d=120h).
    Long los de presión compradora persistente / short los de presión vendedora. β-neutral en el
    motor. Fuente ORTOGONAL al precio → corr ~0.06 con los otros 5 sleeves (no es transformación
    de precio). Sube el combinado a Sharpe ~1.5 / maxDD ~−6%."""
    flow = (taker_buy_volume / volume.replace(0, np.nan)) - 0.5
    return flow.rolling(lookback_h).mean()


# ─── STAT-ARB (cointegración + OU) — DEPRECADO (no sobrevive walk-forward, ver E8) ─

def _half_life(spread: np.ndarray) -> float:
    s = spread[~np.isnan(spread)]
    if len(s) < 50:
        return np.inf
    ds = np.diff(s); lag = s[:-1]
    b = np.polyfit(lag, ds, 1)[0]
    return -np.log(2) / np.log(1 + b) if -1 < b < 0 else np.inf


def statarb_select(logp_is: pd.DataFrame, pmax=STATARB_PMAX, min_corr=STATARB_MIN_CORR,
                   hl=STATARB_HL, max_pairs=25) -> list[dict]:
    """Selecciona pares cointegrados ROBUSTOS sobre el período IS (sin lookahead).
    Devuelve [{a,b,beta,half_life,pval}]."""
    syms = list(logp_is.columns); corr = logp_is.corr(); out = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            if abs(corr.loc[a, b]) < min_corr:
                continue
            x, y = logp_is[a].values, logp_is[b].values
            try:
                p = coint(x, y)[1]
            except Exception:
                continue
            if p > pmax:
                continue
            beta = float(np.polyfit(y, x, 1)[0])
            h = _half_life(x - beta * y)
            if hl[0] <= h <= hl[1]:
                out.append({"a": a, "b": b, "beta": beta, "half_life": h, "pval": p})
    out.sort(key=lambda d: d["pval"])
    return out[:max_pairs]


def statarb_spread_z(logp: pd.DataFrame, a: str, b: str, beta: float, zwin=STATARB_ZWIN) -> pd.Series:
    spread = logp[a] - beta * logp[b]
    return (spread - spread.rolling(zwin).mean()) / spread.rolling(zwin).std()


def statarb_step(z_now: float, pos: float,
                 entry=STATARB_ENTRY, exit=STATARB_EXIT, stop=STATARB_STOP) -> float:
    """Máquina de estados del par: entra ±entry, sale |z|<exit o |z|>stop (divergencia)."""
    if np.isnan(z_now):
        return pos
    if pos == 0:
        if z_now > entry:
            return -1.0
        if z_now < -entry:
            return 1.0
        return 0.0
    return 0.0 if (abs(z_now) < exit or abs(z_now) > stop) else pos
