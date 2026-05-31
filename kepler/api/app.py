"""
Kepler — API del dashboard (FastAPI). Lee la DB y sirve el frontend.
Endpoints:
  GET /                  → dashboard.html
  GET /api/status        → estado del sistema (modo, equity, circuit breaker, último ciclo)
  GET /api/positions     → posiciones objetivo activas
  GET /api/logs          → logs (decisiones + errores) de audit_event
  GET /api/equity        → curva de equity (snapshots)
  GET /api/download[/d]  → JSON diario descargable
Ejecutar: python -m kepler.api   (uvicorn en DASHBOARD_PORT, default 8080)
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config  # noqa
from kepler.db import DB
from kepler import execution

app = FastAPI(title="Kepler Dashboard")
_DB = DB()
_HTML = os.path.join(os.path.dirname(__file__), "dashboard.html")


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
    return {
        "mode": mode, "tier": det.get("tier", "—"),
        "equity": live_eq, "gross": s.get("gross"), "net": s.get("net"),
        "n_positions": s.get("n_positions", 0),
        "total_return": round(total_ret, 2), "today_return": round(today_ret, 2),
        "cb_halted": halted,
        "last_cycle": datetime.fromtimestamp((cyc[0]["ts"] if cyc else (s.get("ts") or 0))/1000,
                                             tz=timezone.utc).isoformat() if (cyc or s) else None,
        # backtest real del último ciclo (lo guarda el orquestador con el leverage anclado);
        # fallback al sistema actual de 7 sleeves @maxDD−10% si el snapshot aún no lo trae.
        "backtest": det.get("backtest", {"sharpe": 1.94, "ann": 42.2, "maxdd": -10.0, "n_sleeves": 7}),
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


@app.get("/api/logs")
def logs(limit: int = 150, level: str = ""):
    sql = "SELECT ts,level,category,symbol,title,detail FROM audit_event "
    args = ()
    if level:
        sql += "WHERE level=? "; args = (level,)
    sql += "ORDER BY ts DESC LIMIT ?"; args = args + (limit,)
    rows = _q(sql, args)
    for r in rows:
        r["time"] = datetime.fromtimestamp(r["ts"]/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return rows


@app.get("/api/equity")
def equity():
    rows = _q("SELECT ts,equity FROM equity_tick ORDER BY ts ASC")
    if not rows:   # DB antigua sin ticks → usar snapshots
        rows = _q("SELECT ts,equity FROM portfolio_snapshot ORDER BY ts ASC")
    for r in rows:
        r["time"] = datetime.fromtimestamp(r["ts"]/1000, tz=timezone.utc).strftime("%m-%d %H:%M")
    return rows


@app.get("/api/download")
def download(date: str = "", start: str = "", end: str = "", full: bool = False):
    # full=1 (o un rango start/end) → export de ANÁLISIS con todo (señales, fills, snapshots
    # con posiciones+PnL, curva, audit). Sin parámetros → log del día (compat).
    if full or start or end:
        path = _DB.export_log(start or None, end or None)
    else:
        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = _DB.export_daily_log(date)
    if not os.path.exists(path):
        return JSONResponse({"error": "no hay log"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path), media_type="application/json")
