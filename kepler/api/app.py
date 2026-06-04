"""
Kepler — API del dashboard (FastAPI). Lee la DB y sirve el frontend.
Endpoints:
  GET /                  → dashboard.html (operativo)
  GET /track             → track.html (página de track-record presentable para inversor, F2.2)
  GET /api/track         → métricas de track-record del equity REAL en vivo (F2.1)
  GET /api/status        → estado del sistema (modo, equity, circuit breaker, último ciclo)
  GET /api/positions     → posiciones objetivo activas
  GET /api/health        → salud operativa (guardas checks.py: pre-trade + heartbeat, por severidad)
  GET /api/health/history→ severidad peor por día (franja-historial)
  GET /api/daily_report  → reporte diario templado (narrativa + métricas)
  GET /api/logs          → logs (decisiones + errores) de audit_event
  GET /api/equity        → curva de equity (snapshots)
  GET /api/download[/d]  → JSON diario descargable
Ejecutar: python -m kepler.api   (uvicorn en DASHBOARD_PORT, default 8080)
"""
from __future__ import annotations
import json, math, os, sys
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config  # noqa
from kepler.db import DB
from kepler import execution
from kepler import track as trackmod   # alias: el endpoint /api/track se llama track() y lo sombrearía

app = FastAPI(title="Kepler Dashboard")
_DB = DB()
_HTML = os.path.join(os.path.dirname(__file__), "dashboard.html")
_TRACK_HTML = os.path.join(os.path.dirname(__file__), "track.html")


def _q(sql, args=()):
    cur = _DB.conn.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.get("/", response_class=HTMLResponse)
def index():
    with open(_HTML, encoding="utf-8") as f:
        return f.read()


@app.get("/api/status")
def status():
    snap = _q("SELECT * FROM portfolio_snapshot ORDER BY ts DESC LIMIT 1")
    cb = _q("SELECT detail FROM audit_event WHERE category='circuit_breaker' ORDER BY ts DESC LIMIT 1")
    halted = json.loads(cb[0]["detail"]).get("halted", False) if cb else False
    cyc = _q("SELECT ts,title FROM audit_event WHERE category='orchestrator' ORDER BY ts DESC LIMIT 1")
    mode = "DRY_RUN" if execution.DRY_RUN else ("DEMO" if execution.USE_DEMO else "REAL")
    s = snap[0] if snap else {}
    det = json.loads(s.get("detail") or "{}")
    # equity vivo (último tick del heartbeat) y rentabilidad acumulada
    tick = _q("SELECT equity FROM equity_tick ORDER BY ts DESC LIMIT 1")
    live_eq = (tick[0]["equity"] if tick else s.get("equity")) or None
    base = _q("SELECT equity FROM equity_daily ORDER BY day ASC LIMIT 1")
    base_eq = base[0]["equity"] if base else live_eq
    total_ret = (live_eq / base_eq - 1) * 100 if (live_eq and base_eq) else 0.0
    today = _q("SELECT ret_pct FROM equity_daily ORDER BY day DESC LIMIT 1")
    today_ret = today[0]["ret_pct"] if today else 0.0
    # accounting acumulado (ledger de fills): comisiones y PnL realizado desde el inicio.
    # Balance neto = resultado REAL de la cuenta = equity actual − equity inicial (en $).
    cst = _q("SELECT COALESCE(SUM(fees_usd),0) f, COALESCE(SUM(pnl_usd),0) r "
             "FROM trades WHERE reason='rebalance_fill'")
    cum_fees = round(cst[0]["f"] or 0.0, 2)
    cum_realized = round(cst[0]["r"] or 0.0, 2)
    net_balance = round(live_eq - base_eq, 2) if (live_eq and base_eq) else None
    return {
        "mode": mode, "tier": det.get("tier", "—"),
        "equity": live_eq, "gross": s.get("gross"), "net": s.get("net"),
        "n_positions": s.get("n_positions", 0),
        "total_return": round(total_ret, 2), "today_return": round(today_ret, 2),
        "cum_fees": cum_fees, "cum_realized": cum_realized, "net_balance": net_balance,
        "cb_halted": halted,
        "last_cycle": config.fmt_local((cyc[0]["ts"] if cyc else (s.get("ts") or 0))) if (cyc or s) else None,
        # backtest real del último ciclo (lo guarda el orquestador con el leverage anclado);
        # fallback al sistema actual de 7 sleeves @maxDD−10% si el snapshot aún no lo trae.
        "backtest": det.get("backtest", {"sharpe": 2.07, "ann": 49.3, "maxdd": -10.0, "n_sleeves": 7}),
        "leverage": det.get("leverage"),                 # leverage de estrategia (ancla)
        "sleeves": det.get("vp", {}),                    # pesos vol-parity por sleeve (diversificación)
    }


@app.get("/api/positions")
def positions():
    # 1) posiciones REALES en Binance (lo que tienes abierto ahora)
    if not execution.DRY_RUN:
        try:
            real = execution.get_positions_detail()
        except Exception:
            real = []
        if real:
            for r in real:
                r["source"] = "real"
            return sorted(real, key=lambda x: -abs(x["notional"]))
    # 2) fallback: objetivo del último ciclo (DRY_RUN o sin fills aún)
    snap = _q("SELECT equity,detail FROM portfolio_snapshot ORDER BY ts DESC LIMIT 1")
    if not snap:
        return []
    det = json.loads(snap[0]["detail"] or "{}")
    eq = snap[0]["equity"] or config.CAPITAL_USD
    w = det.get("weights", {})
    out = [{"symbol": s, "side": "LONG" if v > 0 else "SHORT",
            "notional": round(v * eq, 1), "pnl": None, "source": "target"} for s, v in w.items()]
    return sorted(out, key=lambda x: -abs(x["notional"]))


@app.get("/api/daily")
def daily():
    return _q("SELECT day,equity,ret_pct,dd_pct FROM equity_daily ORDER BY day DESC")


_SEV_RANK = {"OK": 0, "WARN": 1, "CRIT": 2}
_SEV_INV = {0: "OK", 1: "WARN", 2: "CRIT"}


def _latest_checks(category):
    """Último audit de chequeos de esa categoría (severidad + resumen + resultados individuales)."""
    row = _q("SELECT ts,detail FROM audit_event WHERE category=? ORDER BY ts DESC LIMIT 1", (category,))
    if not row:
        return None
    det = json.loads(row[0]["detail"] or "{}")
    return {"ts": row[0]["ts"], "time": config.fmt_local(row[0]["ts"], "%Y-%m-%d %H:%M"),
            "severity": det.get("severity", "OK"), "summary": det.get("summary", ""),
            "results": det.get("results", [])}


@app.get("/api/health")
def health():
    """Salud operativa = las guardas de checks.py ya persistidas (pre-trade 'checks' + heartbeat 'checks_hb').
    No recalcula nada: surface lo que el orquestador audita cada ciclo."""
    pre, hb = _latest_checks("checks"), _latest_checks("checks_hb")
    sevs = [x["severity"] for x in (pre, hb) if x]
    overall = max(sevs, key=lambda s: _SEV_RANK.get(s, 0)) if sevs else "OK"
    return {"overall": overall, "pretrade": pre, "heartbeat": hb}


@app.get("/api/health/history")
def health_history(days: int = 30):
    """Severidad PEOR por día (hora Lima) de los últimos N días → franja-historial del dashboard."""
    since = int(datetime.now(timezone.utc).timestamp() * 1000) - days * 86_400_000
    rows = _q("SELECT ts,detail FROM audit_event WHERE category IN ('checks','checks_hb') AND ts>=? "
              "ORDER BY ts ASC", (since,))
    by_day = {}
    for r in rows:
        try:
            sev = json.loads(r["detail"] or "{}").get("severity", "OK")
        except Exception:
            sev = "OK"
        day = config.fmt_local(r["ts"], "%Y-%m-%d")
        by_day[day] = max(by_day.get(day, 0), _SEV_RANK.get(sev, 0))
    return [{"day": d, "severity": _SEV_INV[v]} for d, v in sorted(by_day.items())]


@app.get("/api/daily_report")
def daily_report(date: str = ""):
    """Reporte diario templado (narrativa + métricas) — el del día dado o el más reciente."""
    if date:
        row = _q("SELECT day,narrative,metrics FROM daily_report WHERE day=?", (date,))
    else:
        row = _q("SELECT day,narrative,metrics FROM daily_report ORDER BY day DESC LIMIT 1")
    if not row:
        return {}
    try:
        metrics = json.loads(row[0]["metrics"] or "{}")
    except Exception:
        metrics = {}
    return {"day": row[0]["day"], "narrative": row[0]["narrative"] or "", "metrics": metrics}


@app.get("/api/track")
def track():
    """F2.1 — métricas de TRACK RECORD para inversor, calculadas del equity REAL en vivo (no backtest).
    Code-first, cero IA: Sharpe/Sortino/maxDD/vol/% meses+ realizados + retornos mensuales + narrativa
    templada honesta. El backtest se devuelve aparte y SIEMPRE etiquetado como referencia."""
    rows = _q("SELECT day,equity,ret_pct,dd_pct FROM equity_daily ORDER BY day ASC")
    ticks = _q("SELECT ts,equity FROM equity_tick ORDER BY ts ASC")
    snap = _q("SELECT beta,gross,net,n_positions,detail FROM portfolio_snapshot ORDER BY ts DESC LIMIT 1")
    det = json.loads(snap[0]["detail"] or "{}") if snap else {}
    bt = det.get("backtest", {"sharpe": 2.07, "ann": 49.3, "maxdd": -10.0})
    beta = snap[0]["beta"] if snap else None
    if not rows:
        return {"days": 0, "inception": None, "backtest": bt, "beta": beta, "monthly": [],
                "equity_curve": [], "narrative": "Track en construcción — la DEMO aún no registra días."}
    # Métricas HONESTAS sobre la VENTANA LIMPIA (desde config.TRACK_INCEPTION, post-fixes) + maxDD
    # INTRADÍA de los ticks MTM. Si la ventana limpia aún no tiene días, cae a todo el historial (etiquetado).
    daily_rows = [(r["day"], r["equity"], r["ret_pct"], r["dd_pct"]) for r in rows]
    tick_rows = [(t["ts"], t["equity"]) for t in ticks]
    m = trackmod.realized(daily_rows, tick_rows, config.TRACK_INCEPTION)
    clean = m.get("days", 0) > 0
    if not clean:
        m = trackmod.realized(daily_rows, tick_rows, None)
    narrative = (f"DEMO · {m['days']} día(s) en vivo desde {m['inception']}"
                 f"{' (ventana limpia post-fixes)' if clean else ' (historial completo; ventana limpia aún vacía)'} · "
                 f"retorno total {m['total_return']:+.2f}% · Sharpe realizado {m['sharpe']:.2f} "
                 f"(referencia backtest {bt.get('sharpe')}) · maxDD {m['maxdd']:.2f}% "
                 f"(intradía {m['maxdd_intraday']:.2f}%, presupuesto −10%) · {m['pos_months']:.0f}% meses+ · "
                 f"β {('%+.2f' % beta) if beta is not None else '—'}. "
                 f"Track en construcción — el número honesto se consolida con semanas, no con días.")
    return {"days": m["days"], "days_all": len(rows), "inception": m["inception"], "clean_window": clean,
            "total_return": m["total_return"], "ann_return": m["ann_return"],
            "sharpe": m["sharpe"], "sortino": m["sortino"], "vol_ann": m["vol_ann"],
            "maxdd": m["maxdd"], "maxdd_intraday": m["maxdd_intraday"], "maxdd_daily": m["maxdd_daily"],
            "pos_days": m["pos_days"], "pos_months": m["pos_months"],
            "beta": beta, "gross": snap[0]["gross"] if snap else None,
            "net": snap[0]["net"] if snap else None,
            "n_positions": snap[0]["n_positions"] if snap else None,
            "monthly": m["monthly"], "backtest": bt,
            "equity_curve": [{"day": r["day"], "equity": r["equity"]} for r in rows],
            "narrative": narrative}


@app.get("/track", response_class=HTMLResponse)
def track_page():
    with open(_TRACK_HTML, encoding="utf-8") as f:
        return f.read()


@app.get("/api/logs")
def logs(limit: int = 300, level: str = "", start: str = "", end: str = ""):
    # filtro por nivel y por RANGO DE FECHAS (días LOCALES Lima → bounds en epoch ms, TZ-correcto).
    sql = "SELECT ts,level,category,symbol,title,detail FROM audit_event WHERE 1=1 "
    args = []
    if level:
        sql += "AND level=? "; args.append(level)
    if start:
        sql += "AND ts>=? "; args.append(config.day_bounds_ms(start)[0])
    if end:
        sql += "AND ts<? "; args.append(config.day_bounds_ms(end)[1])
    sql += "ORDER BY ts DESC LIMIT ?"; args.append(limit)
    rows = _q(sql, tuple(args))
    for r in rows:
        r["time"] = config.fmt_local(r["ts"], "%Y-%m-%d %H:%M:%S")   # hora Lima
    return rows


@app.get("/api/equity")
def equity():
    rows = _q("SELECT ts,equity FROM equity_tick ORDER BY ts ASC")
    if not rows:   # DB antigua sin ticks → usar snapshots
        rows = _q("SELECT ts,equity FROM portfolio_snapshot ORDER BY ts ASC")
    for r in rows:
        r["time"] = config.fmt_local(r["ts"], "%m-%d %H:%M")        # hora Lima
    return rows


@app.get("/api/download")
def download(date: str = "", start: str = "", end: str = "", full: bool = False):
    # full=1 (o un rango start/end) → export de ANÁLISIS con todo (señales, fills, snapshots
    # con posiciones+PnL, curva, audit). Sin parámetros → log del día (compat).
    if full or start or end:
        path = _DB.export_log(start or None, end or None)
    else:
        date = date or config.today_local()     # "hoy" en hora de Lima (no UTC)
        path = _DB.export_daily_log(date)
    if not os.path.exists(path):
        return JSONResponse({"error": "no hay log"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path), media_type="application/json")
