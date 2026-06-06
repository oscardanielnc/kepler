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

    # 2. Drawdown actual vs ancla −10% — sobre la PEOR de: snapshot del rebalanceo (drawdown_pct) y la
    #    curva MTM intradía del track limpio (live.maxdd_intraday). El snapshot va 1 paso por detrás (el
    #    libro sigue sangrando tras las 14 UTC), así que tomamos la más honesta de las dos.
    dd = metrics.get("drawdown_pct")
    dd_mtm = (live or {}).get("maxdd_intraday")
    cands = [x for x in (dd, dd_mtm) if x is not None]
    if cands:
        dd_eff = min(cands)
        det = f"{dd_eff:.2f}%"
        if dd is not None and dd_mtm is not None and abs(dd - dd_mtm) > 0.01:
            det = f"{dd_eff:.2f}% (snapshot {dd:.2f}% / MTM intradía {dd_mtm:.2f}%)"
        if dd_eff <= -10.0:
            add("CRIT", f"Drawdown {det} alcanzó/superó el ancla −10%")
        elif dd_eff <= -8.0:
            add("WARN", f"Drawdown {det} se acerca al ancla −10%")

    # 3. Ciclos del día: 0 = rebalanceo PERDIDO (balance ilegible/API caída, hallazgo 06-06); ≥3 = churn (06-02)
    cyc = metrics.get("cycles_today")
    if isinstance(cyc, int):
        if cyc == 0:
            add("CRIT", "0 ciclos hoy — el rebalanceo del día NO se ejecutó (¿balance ilegible / API caída?)")
        elif cyc >= 3:
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

    # (la antigua regla #8 "maxDD intradía del track" quedó SUBSUMIDA en la #2, que ya usa live.maxdd_intraday)

    sev = worst([f["sev"] for f in flags])
    summary = "✅ sin anomalías" if not flags else " · ".join(f"[{f['sev']}] {f['msg']}" for f in flags)
    return {"severity": sev, "flags": flags, "summary": summary}
