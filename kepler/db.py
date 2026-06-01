"""
Kepler — capa de persistencia (SQLite). Fuente de verdad y auditoría desde el día 1.

Diseñada para: (a) reconstruir CUALQUIER decisión del sistema (por qué se abrió/cerró
cada trade, con qué features y señales), (b) reportes diarios descargables, (c) alimentar
a futuro la IA de análisis post-trade, (d) servir un frontend más adelante.

Tablas:
  signals            — cada señal de alpha generada (con snapshot de features en JSON)
  trades             — posiciones abiertas/cerradas (entrada, salida, pnl, R, costos, motivo)
  portfolio_snapshot — estado periódico (equity, gross/net, beta, nº posiciones)
  equity_daily       — curva de equity diaria (para métricas y frontend)
  daily_report       — resumen diario (métricas JSON + narrativa) para descarga/IA
  audit_event        — eventos del sistema (errores, decisiones, overrides) nivel+JSON
"""
from __future__ import annotations
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, alpha TEXT NOT NULL, symbol TEXT NOT NULL,
    direction TEXT, score REAL, expected_ret REAL, horizon_min INTEGER,
    regime TEXT, driver TEXT, features TEXT          -- JSON snapshot
);
CREATE INDEX IF NOT EXISTS ix_signals_ts ON signals(ts);
CREATE INDEX IF NOT EXISTS ix_signals_sym ON signals(symbol);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, alpha TEXT, direction TEXT,
    open_ts INTEGER, entry_px REAL, qty REAL, weight REAL, leverage REAL,
    stop REAL, take_profit REAL, driver TEXT,        -- driver para lead-lag (salida condicional)
    close_ts INTEGER, exit_px REAL, pnl_usd REAL, r_multiple REAL,
    fees_usd REAL, funding_usd REAL, reason TEXT, status TEXT DEFAULT 'open', notes TEXT
);
CREATE INDEX IF NOT EXISTS ix_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS ix_trades_open ON trades(open_ts);

CREATE TABLE IF NOT EXISTS portfolio_snapshot (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, equity REAL, gross REAL, net REAL,
    beta REAL, n_positions INTEGER, target_vol REAL, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_psnap_ts ON portfolio_snapshot(ts);

CREATE TABLE IF NOT EXISTS equity_daily (
    day TEXT PRIMARY KEY, equity REAL, ret_pct REAL, dd_pct REAL,
    sharpe_30d REAL, n_trades INTEGER
);

CREATE TABLE IF NOT EXISTS equity_tick (    -- equity frecuente (heartbeat) para la curva
    ts INTEGER PRIMARY KEY, equity REAL
);

CREATE TABLE IF NOT EXISTS daily_report (
    day TEXT PRIMARY KEY, ts INTEGER, metrics TEXT, narrative TEXT  -- JSON + texto (IA futura)
);

CREATE TABLE IF NOT EXISTS audit_event (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, level TEXT, category TEXT,
    symbol TEXT, title TEXT, detail TEXT             -- JSON
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_event(ts);
CREATE INDEX IF NOT EXISTS ix_audit_cat ON audit_event(category);

CREATE TABLE IF NOT EXISTS shadow_signal (   -- sleeve en MODO SOMBRA (NO opera): registra la señal
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, sleeve TEXT NOT NULL, symbol TEXT NOT NULL,
    weight REAL, score REAL, detail TEXT      -- validación FORWARD point-in-time (p.ej. on-chain TVL)
);
CREATE INDEX IF NOT EXISTS ix_shadow_ts ON shadow_signal(ts);
CREATE INDEX IF NOT EXISTS ix_shadow_sleeve ON shadow_signal(sleeve);
"""


def _now_ms() -> int:
    return int(time.time() * 1000)


class DB:
    def __init__(self, path: str = None):
        self.conn = sqlite3.connect(path or config.DB_PATH, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        # migración idempotente: columnas para medir slippage REAL de fills (C3)
        for col in ("ref_px REAL", "slip_bps REAL"):
            try: self.conn.execute(f"ALTER TABLE trades ADD COLUMN {col}")
            except Exception: pass
        self.conn.commit()

    # ── escritura ──────────────────────────────────────────────────────────
    def log_signal(self, alpha, symbol, direction=None, score=None, expected_ret=None,
                   horizon_min=None, regime=None, driver=None, features: dict | None = None,
                   ts: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO signals (ts,alpha,symbol,direction,score,expected_ret,horizon_min,"
            "regime,driver,features) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ts or _now_ms(), alpha, symbol, direction, score, expected_ret, horizon_min,
             regime, driver, json.dumps(features or {})))
        self.conn.commit(); return cur.lastrowid

    def open_trade(self, symbol, alpha, direction, entry_px, qty, weight, leverage,
                   stop=None, take_profit=None, driver=None, open_ts=None, notes=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO trades (symbol,alpha,direction,open_ts,entry_px,qty,weight,leverage,"
            "stop,take_profit,driver,status,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'open', ?)",
            (symbol, alpha, direction, open_ts or _now_ms(), entry_px, qty, weight, leverage,
             stop, take_profit, driver, notes))
        self.conn.commit(); return cur.lastrowid

    def close_trade(self, trade_id, exit_px, pnl_usd, r_multiple, fees_usd=0.0,
                    funding_usd=0.0, reason="", close_ts=None):
        self.conn.execute(
            "UPDATE trades SET close_ts=?, exit_px=?, pnl_usd=?, r_multiple=?, fees_usd=?,"
            "funding_usd=?, reason=?, status='closed' WHERE id=?",
            (close_ts or _now_ms(), exit_px, pnl_usd, r_multiple, fees_usd, funding_usd, reason, trade_id))
        self.conn.commit()

    def log_fill(self, symbol, direction, qty, price, weight=None, leverage=None,
                 prev_amt=None, new_amt=None, ts=None, ref_px=None, slip_bps=None) -> int:
        """Registra un FILL del rebalanceo (cambio real de posición en un ciclo). El sistema
        es de rebalanceo rodante (sin entrada/salida discretas): cada fila = un cambio de tamaño.
        status='closed' si la posición resultante quedó en 0, si no 'open'. r_multiple/exit_px no
        aplican aquí (no hay ciclo de vida open→close clásico; eso sería otro proyecto).
        ref_px/slip_bps (C3): precio de referencia y slippage realizado (fill vs ref) para calibrar costos."""
        status = "closed" if (new_amt is not None and abs(new_amt) < 1e-12) else "open"
        notes = (f"{prev_amt:+.6f}->{new_amt:+.6f}"
                 if (prev_amt is not None and new_amt is not None) else None)
        cur = self.conn.execute(
            "INSERT INTO trades (symbol,alpha,direction,open_ts,entry_px,qty,weight,leverage,"
            "reason,status,notes,ref_px,slip_bps) VALUES (?,?,?,?,?,?,?,?, 'rebalance_fill', ?, ?, ?, ?)",
            (symbol, "rebalance", direction, ts or _now_ms(), price, qty, weight, leverage,
             status, notes, ref_px, slip_bps))
        self.conn.commit(); return cur.lastrowid

    def append_note(self, trade_id, note: str):
        row = self.conn.execute("SELECT notes FROM trades WHERE id=?", (trade_id,)).fetchone()
        prev = (row[0] + " | ") if row and row[0] else ""
        self.conn.execute("UPDATE trades SET notes=? WHERE id=?", (prev + note, trade_id))
        self.conn.commit()

    def snapshot_portfolio(self, equity, gross, net, beta, n_positions, target_vol=None, detail=None):
        self.conn.execute(
            "INSERT INTO portfolio_snapshot (ts,equity,gross,net,beta,n_positions,target_vol,detail)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (_now_ms(), equity, gross, net, beta, n_positions, target_vol, json.dumps(detail or {})))
        self.conn.commit()

    def record_equity_tick(self, equity):
        """Punto de equity frecuente (heartbeat) — alimenta la curva del frontend."""
        if equity is None:
            return
        self.conn.execute("INSERT OR REPLACE INTO equity_tick (ts,equity) VALUES (?,?)",
                          (_now_ms(), float(equity)))
        self.conn.commit()

    def upsert_equity_daily(self, equity):
        """Actualiza la fila del día: equity de cierre, retorno vs día previo, drawdown."""
        if equity is None:
            return
        equity = float(equity)
        day = config.today_local()      # día LOCAL (Lima), no UTC → "hoy" coincide con Oscar
        prev = self.conn.execute(
            "SELECT equity FROM equity_daily WHERE day<? ORDER BY day DESC LIMIT 1", (day,)).fetchone()
        prev_eq = prev[0] if prev and prev[0] else equity
        ret = (equity / prev_eq - 1) * 100 if prev_eq else 0.0
        pk = self.conn.execute("SELECT MAX(equity) FROM equity_daily").fetchone()[0] or equity
        peak = max(pk, equity)
        dd = (equity / peak - 1) * 100 if peak else 0.0
        self.conn.execute(
            "INSERT INTO equity_daily (day,equity,ret_pct,dd_pct) VALUES (?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET equity=excluded.equity, ret_pct=excluded.ret_pct, dd_pct=excluded.dd_pct",
            (day, equity, ret, dd))
        self.conn.commit()

    def log_shadow(self, sleeve, symbol, weight, score=None, detail: dict | None = None,
                   ts: int | None = None) -> int:
        """Registra el peso que un sleeve en MODO SOMBRA tendría (sin operar). Para validación
        FORWARD point-in-time: cada ciclo guarda la señal viva → luego se mide su retorno real."""
        cur = self.conn.execute(
            "INSERT INTO shadow_signal (ts,sleeve,symbol,weight,score,detail) VALUES (?,?,?,?,?,?)",
            (ts or _now_ms(), sleeve, symbol, weight, score, json.dumps(detail or {})))
        self.conn.commit(); return cur.lastrowid

    def audit(self, level, category, title, symbol=None, detail: dict | None = None):
        self.conn.execute(
            "INSERT INTO audit_event (ts,level,category,symbol,title,detail) VALUES (?,?,?,?,?,?)",
            (_now_ms(), level, category, symbol, title, json.dumps(detail or {})))
        self.conn.commit()

    def save_daily_report(self, day: str, metrics: dict, narrative: str = ""):
        self.conn.execute(
            "INSERT INTO daily_report (day,ts,metrics,narrative) VALUES (?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET ts=excluded.ts, metrics=excluded.metrics, narrative=excluded.narrative",
            (day, _now_ms(), json.dumps(metrics), narrative))
        self.conn.commit()

    # ── exportación de log diario (descargable) ──────────────────────────────
    def export_daily_log(self, day: str | None = None) -> str:
        day = day or config.today_local()          # "hoy" en hora de Lima (no UTC)
        path = os.path.join(config.LOGS_DIR, f"kepler_{day}.json")
        d0, d1 = config.day_bounds_ms(day)         # fronteras del día LOCAL (Lima)
        def rows(q, a): return [dict(zip([c[0] for c in cur.description], r))
                                for cur in [self.conn.execute(q, a)] for r in cur.fetchall()]
        payload = {
            "day": day,
            "trades":  rows("SELECT * FROM trades WHERE (close_ts BETWEEN ? AND ?) OR (open_ts BETWEEN ? AND ?)", (d0,d1,d0,d1)),
            "signals": rows("SELECT * FROM signals WHERE ts BETWEEN ? AND ?", (d0,d1)),
            "audit":   rows("SELECT * FROM audit_event WHERE ts BETWEEN ? AND ?", (d0,d1)),
            "report":  rows("SELECT * FROM daily_report WHERE day=?", (day,)),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def export_log(self, start: str | None = None, end: str | None = None) -> str:
        """Export para ANÁLISIS: rango de días (o histórico completo si start/end=None).
        Incluye TODO lo que se persiste — señales, fills, snapshots de cartera (con posiciones
        y PnL), curva de equity (ticks + diaria), auditoría y reportes. Un solo archivo."""
        d0 = config.day_bounds_ms(start)[0] if start else 0       # rango en días LOCALES (Lima)
        d1 = config.day_bounds_ms(end)[1] if end else _now_ms() + 86_400_000
        tag = f"{start or 'inicio'}_a_{end or 'ahora'}"
        path = os.path.join(config.LOGS_DIR, f"kepler_{tag}.json")
        def rows(q, a=()): return [dict(zip([c[0] for c in cur.description], r))
                                   for cur in [self.conn.execute(q, a)] for r in cur.fetchall()]
        payload = {
            "range": {"start": start, "end": end},
            "generated": datetime.now(timezone.utc).isoformat(),
            "signals":            rows("SELECT * FROM signals WHERE ts BETWEEN ? AND ? ORDER BY ts", (d0,d1)),
            "trades":             rows("SELECT * FROM trades WHERE COALESCE(open_ts,close_ts) BETWEEN ? AND ? ORDER BY open_ts", (d0,d1)),
            "portfolio_snapshot": rows("SELECT * FROM portfolio_snapshot WHERE ts BETWEEN ? AND ? ORDER BY ts", (d0,d1)),
            "equity_tick":        rows("SELECT * FROM equity_tick WHERE ts BETWEEN ? AND ? ORDER BY ts", (d0,d1)),
            "equity_daily":       rows("SELECT * FROM equity_daily ORDER BY day"),
            "shadow_signal":      rows("SELECT * FROM shadow_signal WHERE ts BETWEEN ? AND ? ORDER BY ts", (d0,d1)),
            "audit":              rows("SELECT * FROM audit_event WHERE ts BETWEEN ? AND ? ORDER BY ts", (d0,d1)),
            "daily_report":       rows("SELECT * FROM daily_report ORDER BY day"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path


if __name__ == "__main__":
    db = DB()
    db.audit("INFO", "system", "Kepler DB inicializada")
    print(f"DB OK → {config.DB_PATH}")
    print("Tablas:", [r[0] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
