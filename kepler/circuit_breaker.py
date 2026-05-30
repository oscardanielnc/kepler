"""
Kepler — CIRCUIT BREAKER de cartera. Halt si el equity cae más de MAX_DD desde el pico.
Estado persistido en la DB (audit_event categoría 'circuit_breaker').
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler.db import DB

MAX_DD = 0.20          # halt si equity < pico × (1 − 20%)
RESUME_RECOVER = 0.05  # reanudar cuando recupere a pico × (1 − 15%)


def _peak(db) -> float:
    row = db.conn.execute(
        "SELECT MAX(equity) FROM portfolio_snapshot WHERE equity IS NOT NULL").fetchone()
    return float(row[0]) if row and row[0] else 0.0


def is_halted(db) -> bool:
    row = db.conn.execute(
        "SELECT detail FROM audit_event WHERE category='circuit_breaker' ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if not row:
        return False
    import json
    return json.loads(row[0]).get("halted", False)


def check(equity: float, db: DB | None = None) -> bool:
    """Devuelve True si se debe OPERAR (no halted). Actualiza estado si cruza umbrales."""
    db = db or DB()
    peak = max(_peak(db), equity)
    halted = is_halted(db)
    dd = (equity / peak - 1) if peak > 0 else 0.0
    if not halted and dd <= -MAX_DD:
        db.audit("CRITICAL", "circuit_breaker", f"HALT — drawdown {dd*100:.1f}% (equity {equity:.0f}/pico {peak:.0f})",
                 detail={"halted": True, "dd": dd, "equity": equity, "peak": peak})
        try:
            from kepler import notify; notify.alert_halt(dd, equity)
        except Exception:
            pass
        return False
    if halted and dd >= -(MAX_DD - RESUME_RECOVER):
        db.audit("INFO", "circuit_breaker", f"REANUDA — recuperado a {dd*100:.1f}%",
                 detail={"halted": False, "dd": dd})
        return True
    return not halted


if __name__ == "__main__":
    db = DB()
    print(f"Pico equity: {_peak(db):.2f} | halted: {is_halted(db)}")
