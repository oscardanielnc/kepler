"""
Kepler — DIGEST DIARIO DE ANOMALÍAS (code-first, cero IA).

Formaliza la watch-list de MONITOREO.md §2 en reglas DETERMINISTAS evaluadas cada día sobre el
reporte diario. NO opera ni toca el edge: solo VIGILA y avisa. El orquestador lo loguea (audit
categoría 'monitor') y notifica en TRANSICIÓN (no spamea). Es la red de seguridad que habría
cazado solo el bug de churn del 06-02 (cycles_today=8).

Severidades: OK < INFO < WARN < CRIT. La del digest = la peor de sus banderas.
"""
from __future__ import annotations

_ORDER = {"OK": 0, "INFO": 1, "WARN": 2, "CRIT": 3}


def worst(sevs) -> str:
    return max(sevs, key=lambda s: _ORDER.get(s, 0)) if sevs else "OK"


def daily_digest(metrics: dict, live: dict | None = None, beta: float | None = None) -> dict:
    """Evalúa las reglas de vigilancia sobre `metrics` (daily_report) + `live` (track realizado).
    Devuelve {severity, flags:[{sev,msg}], summary}. Puro (sin efectos secundarios)."""
    flags: list[dict] = []

    def add(sev: str, msg: str):
        flags.append({"sev": sev, "msg": msg})

    # 1. Circuit breaker (lo más grave)
    if metrics.get("cb_operate") is False:
        add("CRIT", "Circuit breaker DISPARADO (equity −20% del pico) — operación pausada")

    # 2. Drawdown actual vs ancla −10%
    dd = metrics.get("drawdown_pct")
    if dd is not None:
        if dd <= -10.0:
            add("CRIT", f"Drawdown {dd:.2f}% alcanzó/superó el ancla −10%")
        elif dd <= -8.0:
            add("WARN", f"Drawdown {dd:.2f}% se acerca al ancla −10%")

    # 3. Tormenta de reinicios / churn (el bug del 06-02)
    cyc = metrics.get("cycles_today")
    if isinstance(cyc, int):
        if cyc >= 3:
            add("WARN", f"{cyc} ciclos hoy — posible tormenta de reinicios/churn (esperado 1)")
        elif cyc == 2:
            add("INFO", "2 ciclos hoy — posible reinicio/deploy (esperado 1; si no hubo deploy, revisar)")

    # 4. Slippage real caro
    slip = metrics.get("slippage_real") or {}
    med = slip.get("median_bps")
    if med is not None and med > 10:
        add("WARN", f"Slippage mediana {med}bps > 10 — ejecución maker degradada (revisar no-fills/GTX)")

    # 5. Concentración 1-nombre (cap por-sleeve no impide apilamiento multi-sleeve)
    top = metrics.get("top_position") or {}
    w = top.get("weight")
    if w is not None:
        if w > 0.18:
            add("WARN", f"Concentración {top.get('symbol')} {w*100:.0f}% > 18% (apilamiento multi-sleeve)")
        elif w > 0.15:
            add("INFO", f"Concentración {top.get('symbol')} {w*100:.0f}% > 15% — vigilar")

    # 6. Diversificación
    npos = metrics.get("n_positions")
    if isinstance(npos, int) and 0 < npos < 10:
        add("WARN", f"Solo {npos} posiciones (<10) — poca diversificación")

    # 7. Deriva de β (neutralidad del libro)
    if beta is not None and abs(beta) > 0.20:
        add("WARN", f"β {beta:+.2f} fuera de ±0.20 — revisar neutralidad del libro")

    # 8. maxDD intradía honesto del track limpio (solo con muestra mínima)
    if live and live.get("days", 0) >= 5:
        mdd = live.get("maxdd_intraday")
        if mdd is not None and mdd <= -10.0:
            add("WARN", f"maxDD intradía del track {mdd:.2f}% tocó el ancla −10%")

    sev = worst([f["sev"] for f in flags])
    summary = "✅ sin anomalías" if not flags else " · ".join(f"[{f['sev']}] {f['msg']}" for f in flags)
    return {"severity": sev, "flags": flags, "summary": summary}
