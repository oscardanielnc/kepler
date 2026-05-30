"""
Kepler — ORQUESTADOR. El loop de producción que une todo:
  1. refresca datos (fetch incremental)   2. lee equity   3. circuit breaker
  4. calcula portafolio objetivo (engine)  5. reconcile (target vs posiciones reales)
  6. rebalancea (execution maker)          7. loguea snapshot + auditoría en DB
Corre en bucle cada REBALANCE_HOURS, o una vez con --once.

DRY_RUN se controla en kepler/execution.py (default True = seguro).
python -m kepler.orchestrator [ESTABLE|BALANCEADO|GROWTH] [--once]
"""
from __future__ import annotations
import logging, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler import fetch, execution, circuit_breaker, notify
from kepler.engine import compute_target, TIERS
from kepler.db import DB

REBALANCE_HOURS = 24
HEARTBEAT_MIN = 15          # registra equity cada 15 min (curva viva) sin rebalancear
_log = logging.getLogger("kepler")


def heartbeat(db: DB):
    """Registra equity sin rebalancear — mantiene la curva y la tabla diaria al día."""
    equity = execution.get_balance() or config.CAPITAL_USD
    db.record_equity_tick(equity)
    db.upsert_equity_daily(equity)
    _log.info(f"[hb] equity={equity:.2f}")


def cycle(tier="ESTABLE", db: DB | None = None) -> dict:
    db = db or DB()
    t0 = time.time()
    # 1. datos
    n = fetch.update_universe("1h")
    _log.info(f"[orq] datos actualizados ({n} símbolos)")
    # 2. equity
    equity = execution.get_balance() or config.CAPITAL_USD
    # 3. circuit breaker
    operate = circuit_breaker.check(equity, db)
    # 4. target
    target, vp, df, port, asof = compute_target(tier)
    target = target[target.abs() > 0.005]
    if not operate:
        _log.warning("[orq] CIRCUIT BREAKER activo — aplanando (target=0)")
        target = target * 0.0
    # 5. reconcile
    current = execution.get_positions() if not execution.DRY_RUN else {}
    n_target = int((target.abs() > 0.005).sum())
    _log.info(f"[orq] equity={equity:.0f} target={n_target}pos gross={target.abs().sum():.2f} "
              f"posiciones_actuales={len(current)} cb={'OK' if operate else 'HALT'}")
    # 6. rebalanceo
    orders = execution.rebalance(target, equity)
    # 7. log
    db.snapshot_portfolio(equity=equity, gross=float(target.abs().sum()), net=float(target.sum()),
                          beta=0.0, n_positions=n_target,
                          detail={"tier": tier, "asof": str(asof), "cb": operate,
                                  "orders": len(orders) if orders else 0,
                                  "weights": target[target.abs() > 0.005].round(4).to_dict()})
    db.record_equity_tick(equity)      # punto en la curva
    db.upsert_equity_daily(equity)     # retorno del día
    db.audit("INFO", "orchestrator", f"Ciclo {tier} ok ({time.time()-t0:.0f}s)",
             detail={"equity": equity, "n_target": n_target, "operate": operate})
    db.export_daily_log()   # JSON descargable del día
    mode = "DRY_RUN" if execution.DRY_RUN else ("DEMO" if execution.USE_DEMO else "REAL")
    notify.alert_cycle(equity, n_target, float(target.abs().sum()), operate, mode)
    return {"equity": equity, "n_target": n_target, "operate": operate, "mode": mode}


def run(tier="ESTABLE", once=False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    db = DB()
    mode = "DRY_RUN" if execution.DRY_RUN else ("DEMO" if execution.USE_DEMO else "REAL")
    _log.info(f"════ KEPLER orquestador · tier {tier} · modo {mode} · rebal {REBALANCE_HOURS}h · hb {HEARTBEAT_MIN}min ════")
    last_rebal = 0.0
    while True:
        try:
            now = time.time()
            if now - last_rebal >= REBALANCE_HOURS * 3600:   # rebalanceo completo (cada 24h)
                r = cycle(tier, db); last_rebal = now
                _log.info(f"[orq] ciclo completo: {r}")
            else:                                            # heartbeat (solo equity)
                heartbeat(db)
        except Exception as e:
            _log.exception(f"[orq] error en ciclo: {e}")
            db.audit("ERROR", "orchestrator", f"Error: {e}")
            notify.alert_error(str(e)[:200])
        if once:
            break
        time.sleep(HEARTBEAT_MIN * 60)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    tier = next((a for a in args if a in TIERS), "ESTABLE")
    run(tier, once="--once" in args)
