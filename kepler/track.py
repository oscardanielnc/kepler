"""
Kepler — métricas de TRACK RECORD realizadas (en vivo, NO backtest). Code-first, cero IA.

Se calculan sobre el equity REAL de la cuenta (equity_daily / equity_tick), no el backtest.
Dos decisiones de HONESTIDAD (ver ROADMAP §PRINCIPIO DE EVALUACIÓN CON BUGS):
  1. VENTANA LIMPIA: se mide desde `inception` (config.TRACK_INCEPTION = inicio de la operación
     estable, post-fixes) para que los tramos con bugs (p.ej. el churn del 06-02) NO contaminen
     el número. Siempre etiquetado.
  2. maxDD INTRADÍA: el peor drawdown se mide con la curva de ticks MTM (no solo cierres diarios)
     → más conservador y honesto, que es el argumento del copy-lead.

Funciones PURAS (reciben filas, no tocan la DB) → reutilizables en /api/track y el reporte diario.
Cada fila `daily` = (day, equity, ret_pct, dd_pct); cada `tick` = (ts_ms, equity).
"""
from __future__ import annotations
import math

import config


def _inception_ms(inception: str | None) -> int:
    if not inception:
        return 0
    try:
        return config.day_bounds_ms(inception)[0]
    except Exception:
        return 0


def maxdd_from_ticks(ticks, inception: str | None = None) -> float:
    """Peor drawdown (%) de la curva intradía de ticks MTM (valor ≤ 0). 0.0 si no hay datos."""
    lo = _inception_ms(inception)
    peak = None
    mdd = 0.0
    for ts, eq in ticks or []:
        if eq is None or ts is None or ts < lo:
            continue
        eq = float(eq)
        peak = eq if peak is None else max(peak, eq)
        if peak and peak > 0:
            mdd = min(mdd, eq / peak - 1.0)
    return mdd * 100.0


def realized(daily, ticks=None, inception: str | None = None) -> dict:
    """Métricas realizadas de la VENTANA LIMPIA (días >= inception).

    `daily`: filas (day, equity, ret_pct, dd_pct) en orden cronológico.
    `ticks`: filas (ts_ms, equity) cronológicas (opcional; para el maxDD intradía honesto).
    """
    d = [r for r in (daily or []) if (not inception or (r[0] or "") >= inception)]
    if not d:
        return {"days": 0, "inception": inception}
    rets = [(r[2] or 0.0) / 100.0 for r in d]
    n = len(rets)
    mean = sum(rets) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / n) if n > 1 else 0.0
    downside = [x for x in rets if x < 0]
    dd_sd = math.sqrt(sum(x * x for x in downside) / len(downside)) if downside else 0.0
    eq0, eqN = (d[0][1] or 0.0), (d[-1][1] or 0.0)
    total = (eqN / eq0 - 1) * 100 if eq0 else 0.0
    ann = ((eqN / eq0) ** (365.0 / n) - 1) * 100 if (eq0 > 0 and eqN > 0) else 0.0
    sharpe = mean / sd * math.sqrt(365) if sd > 0 else 0.0
    sortino = mean / dd_sd * math.sqrt(365) if dd_sd > 0 else 0.0
    maxdd_daily = min((r[3] or 0.0) for r in d)
    maxdd_intra = maxdd_from_ticks(ticks, inception) if ticks else maxdd_daily
    maxdd = min(maxdd_daily, maxdd_intra)        # el más conservador (más negativo)
    bym: dict[str, float] = {}
    for r in d:                                   # orden cronológico → el dict conserva el orden
        m = (r[0] or "")[:7]
        bym[m] = bym.get(m, 1.0) * (1 + (r[2] or 0.0) / 100.0)
    monthly = [{"month": m, "return": round((v - 1) * 100, 2)} for m, v in bym.items()]
    pos_days = sum(1 for x in rets if x > 0) / n * 100
    pos_months = sum(1 for x in monthly if x["return"] > 0) / len(monthly) * 100 if monthly else 0.0
    return {
        "days": n, "inception": inception or d[0][0],
        "total_return": round(total, 2), "ann_return": round(ann, 2),
        "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "vol_ann": round(sd * math.sqrt(365) * 100, 2),
        "maxdd": round(maxdd, 2), "maxdd_daily": round(maxdd_daily, 2),
        "maxdd_intraday": round(maxdd_intra, 2),
        "pos_days": round(pos_days, 1), "pos_months": round(pos_months, 1),
        "monthly": monthly,
    }
