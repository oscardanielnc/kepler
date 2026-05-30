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

CREATE TABLE IF NOT EXISTS daily_report (
    day TEXT PRIMARY KEY, ts INTEGER, metrics TEXT, narrative TEXT  -- JSON + texto (IA futura)
);

CREATE TABLE IF NOT EXISTS audit_event (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, level TEXT, category TEXT,
    symbol TEXT, title TEXT, detail TEXT             -- JSON
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_event(ts);
CREATE INDEX IF NOT EXISTS ix_audit_cat ON audit_event(category);
"""


def _now_ms() -> int:
    return int(time.time() * 1000)


class DB:
    def __init__(self, path: str = None):
        self.conn = sqlite3.connect(path or config.DB_PATH, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
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
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(config.LOGS_DIR, f"kepler_{day}.json")
        d0 = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
        d1 = d0 + 86_400_000
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


if __name__ == "__main__":
    db = DB()
    db.audit("INFO", "system", "Kepler DB inicializada")
    print(f"DB OK → {config.DB_PATH}")
    print("Tablas:", [r[0] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
