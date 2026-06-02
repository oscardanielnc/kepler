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
from kepler.portfolio import metrics as pf_metrics
from kepler.db import DB

REBALANCE_HOURS = 24
MIN_REBAL_HOURS = 18        # no rebalancear dos veces dentro de la ventana del mismo día
MAX_REBAL_HOURS = 30        # fallback: nunca dejar el libro >30h sin rebalancear (si se pierde la ventana)
HEARTBEAT_MIN = 15          # registra equity cada 15 min (curva viva) sin rebalancear
_log = logging.getLogger("kepler")


def heartbeat(db: DB):
    """Registra equity sin rebalancear — mantiene la curva y la tabla diaria al día.
    Si NO se puede leer el balance, se OMITE el punto (no se inventa un 5000 que mete
    escalones falsos en la curva y corrompe la rentabilidad). En DRY_RUN get_balance
    devuelve el capital configurado, así que esto solo afecta a DEMO/REAL con la API caída.

    CHEQUEO INTRADÍA DEL CIRCUIT BREAKER (e15): el CB ANCHO (−20%) hoy solo se evaluaba en el ciclo de
    24h → una catástrofe entre rebalanceos no se cortaba hasta ~24h después. Chequearlo cada heartbeat
    (15min) atrapa el cisne negro ~24h más rápido a coste ~0 (el −20% NUNCA dispara con ruido intradía:
    el peor DD intradía en 4 años fue −3.3%). NO es un halt fino (eso sería whipsaw, e15) — es el MISMO
    umbral ancho, solo evaluado más seguido. Al disparar, aplana el libro YA (no espera al ciclo)."""
    equity = execution.get_balance()
    if equity is None:
        _log.warning("[hb] balance ilegible — se omite este punto de la curva")
        return
    db.record_equity_tick(equity)
    db.upsert_equity_daily(equity)
    operate = circuit_breaker.check(equity, db)
    if not operate:
        _log.warning("[hb] CIRCUIT BREAKER intradía DISPARADO — aplanando el libro (no se espera al ciclo)")
        try:
            orders = execution.flatten(equity)
            if orders:
                db.audit("CRITICAL", "orchestrator", "Halt intradía: libro aplanado por el CB", detail={"equity": equity})
        except Exception as e:
            _log.exception(f"[hb] fallo al aplanar tras el CB: {e}")
            db.audit("ERROR", "orchestrator", f"Fallo al aplanar tras CB intradía: {e}")
    _log.info(f"[hb] equity={equity:.2f} cb={'OK' if operate else 'HALT'}")


def _log_signals(db: DB, target, vp, weights, lev, asof):
    """Registra la DECISIÓN del ciclo: una señal por símbolo (lado + peso final) con el
    desglose de qué sleeve la empuja. Es lo que faltaba para reconstruir el porqué de cada posición."""
    vp_d = {k: round(float(v), 4) for k, v in vp.items()}
    for sym in target.index:
        w = float(target[sym])
        breakdown = {}
        for name, wser in weights.items():
            try:
                sw = float(wser.reindex([sym]).fillna(0.0).iloc[0])
            except Exception:
                sw = 0.0
            if abs(sw) > 1e-6:
                breakdown[name] = round(sw, 4)
        db.log_signal(alpha="combined", symbol=sym,
                      direction="LONG" if w > 0 else "SHORT", score=round(w, 4),
                      features={"sleeves": breakdown, "vp": vp_d,
                                "leverage": round(float(lev), 3), "asof": str(asof)})


def _log_fills(db: DB, before: dict, after: dict, lev, target, t0_ms):
    """Registra los FILLS reales del ciclo = diferencia de posiciones antes vs después del
    rebalanceo. Honesto con los maker GTX que no siempre llenan: solo cuenta lo que SÍ cambió.
    C3: además mide el slippage realizado = VWAP de los fills reales (userTrades) vs la referencia
    book_mid, con signo adverso (caro al comprar / barato al vender). Blindado: si falla, slip=None."""
    for sym in set(before) | set(after):
        b, a = float(before.get(sym, 0.0)), float(after.get(sym, 0.0))
        d = a - b
        ref = execution.book_mid(sym) or 0.0
        if abs(d) * ref < execution.MIN_ORDER_USD:   # cambio insignificante / ruido
            continue
        fill_px, slip_bps = ref, None
        try:                                          # VWAP de los fills reales del ciclo (C3)
            tr = execution.get_user_trades(sym, t0_ms)
            num = sum(float(x["price"]) * float(x["qty"]) for x in tr)
            den = sum(float(x["qty"]) for x in tr)
            if den > 0 and ref > 0:
                fill_px = num / den
                slip_bps = (1 if d > 0 else -1) * (fill_px - ref) / ref * 1e4
        except Exception:
            pass
        db.log_fill(symbol=sym, direction="BUY" if d > 0 else "SELL", qty=abs(d), price=fill_px,
                    weight=round(float(target.get(sym, 0.0)), 4), leverage=float(lev),
                    prev_amt=b, new_amt=a, ref_px=ref, slip_bps=slip_bps)


def _beta_dollar(positions_detail, beta_last, equity, target):
    """β-DÓLAR instantánea del libro vs BTC = Σ (exposición_con_signo / equity)·βₛᵧₘ. Diagnóstico
    SECUNDARIO (no la neutralidad): mide la exposición direccional NETA del notional, dominada por
    `trend` (long-only sin hedge β). βₛᵧₘ = última barra del rolling β del motor (BTC≈1). Dos modos:
      • REAL (DEMO/REAL): sobre las posiciones reales (notional×signo) — lo que de verdad expone el libro.
      • MODELO (DRY_RUN): sobre los pesos del target. Devuelve (beta_dollar, fuente) o (None, 'n/d')."""
    if beta_last is None:
        return None, "n/d"
    if positions_detail and equity:
        b = sum(float(p["notional"]) * (1 if p["side"] == "LONG" else -1) *
                float(beta_last.get(p["symbol"], 0.0)) for p in positions_detail)
        return round(b / equity, 4), "real"
    bd = float((target.reindex(beta_last.index).fillna(0.0) * beta_last).sum())
    return round(bd, 4), "modelo"


def _beta_realized(db: DB, min_pts: int = 20):
    """β de REGRESIÓN REALIZADA del libro en vivo = regresión de los retornos diarios REALES (equity_daily)
    sobre el retorno diario de BTC. Es la confirmación honesta del β≈+0.05 una vez que la DEMO acumula
    historia. Devuelve None hasta tener ≥min_pts días (antes es ruido). BTC diario desde el parquet."""
    import glob, numpy as np, pandas as pd
    rows = db.conn.execute("SELECT day, ret_pct FROM equity_daily WHERE ret_pct IS NOT NULL ORDER BY day").fetchall()
    if len(rows) < min_pts:
        return None, len(rows)
    eq = pd.Series({r[0]: r[1] / 100.0 for r in rows})
    p = os.path.join(config.DATA_DIR, "futures_um", "1h", "BTCUSDT.parquet")
    g = glob.glob(p)
    if not g:
        return None, len(rows)
    c = pd.read_parquet(g[0], columns=["open_time", "close"]).set_index("open_time")["close"]
    # resamplear BTC por día LOCAL (Lima) para alinear con equity_daily, que bucketea por día local
    c.index = pd.to_datetime(c.index, unit="ms", utc=True).tz_convert(config.TZ)
    btc = c.resample("1D").last().pct_change().dropna()
    btc = pd.Series(btc.values, index=[t.strftime("%Y-%m-%d") for t in btc.index])
    v = pd.concat([eq.rename("e"), btc.rename("b")], axis=1).dropna()
    if len(v) < min_pts or v["b"].var() == 0:
        return None, len(v)
    return round(float(np.cov(v["e"], v["b"])[0, 1] / np.var(v["b"])), 4), len(v)


def _save_daily_report(db: DB, tier, mode, equity, target, lev, bt, operate):
    """Genera el REPORTE DIARIO (metrics JSON + narrativa) para monitoreo y descarga. Pensado para
    vigilar avance y detectar problemas: retorno/dd del día, exposición, leverage, CONCENTRACIÓN
    (top posición), SLIPPAGE REAL del día (C3), nº de ciclos (detecta tormentas de reinicios) y CB.
    Ver `MONITOREO.md` para cómo leerlo y los umbrales de alerta."""
    day = config.today_local()
    d0, d1 = config.day_bounds_ms(day)
    row = db.conn.execute("SELECT ret_pct,dd_pct FROM equity_daily WHERE day=?", (day,)).fetchone()
    ret_pct, dd_pct = (row[0] or 0.0, row[1] or 0.0) if row else (0.0, 0.0)
    # slippage REAL de los fills de hoy (C3)
    fills = db.conn.execute(
        "SELECT symbol,slip_bps FROM trades WHERE reason='rebalance_fill' AND slip_bps IS NOT NULL "
        "AND open_ts BETWEEN ? AND ?", (d0, d1)).fetchall()
    slip = {}
    if fills:
        v = sorted(f[1] for f in fills); n = len(v)
        worst = max(fills, key=lambda f: f[1])
        slip = {"n": n, "mean_bps": round(sum(v)/n, 2), "median_bps": round(v[n//2], 2),
                "worst_bps": round(worst[1], 2), "worst_sym": worst[0]}
    cycles = db.conn.execute(
        "SELECT COUNT(*) FROM audit_event WHERE category='orchestrator' AND title LIKE 'Ciclo%ok%' "
        "AND ts BETWEEN ? AND ?", (d0, d1)).fetchone()[0]
    top = None
    if target is not None and len(target) and target.abs().sum() > 0:
        sym = target.abs().idxmax(); top = {"symbol": sym, "weight": round(float(target[sym]), 4)}
    gross = float(target.abs().sum()) if target is not None else 0.0
    net = float(target.sum()) if target is not None else 0.0
    npos = int((target.abs() > 0.005).sum()) if target is not None else 0
    metrics = {"day": day, "mode": mode, "tier": tier, "equity": round(float(equity), 2),
               "today_return_pct": round(ret_pct, 3), "drawdown_pct": round(dd_pct, 3),
               "n_positions": npos, "gross": round(gross, 3), "net": round(net, 3),
               "leverage": round(float(lev), 3), "top_position": top, "cycles_today": int(cycles),
               "slippage_real": slip, "cb_operate": bool(operate),
               "backtest": {"sharpe": round(bt.get("sharpe", 0), 2), "ann": round(bt.get("ann", 0), 1),
                            "maxdd": round(bt.get("maxdd", 0), 1)}}
    narr = (f"{mode} {tier} · ${float(equity):.0f} ({ret_pct:+.2f}% hoy, dd {dd_pct:.2f}%) · "
            f"{npos} pos gross {gross:.2f} net {net:+.2f} lev {lev:.2f}x · "
            + (f"slip med {slip['median_bps']}bps (peor {slip['worst_sym']} {slip['worst_bps']}) · " if slip else "slip s/d · ")
            + (f"top {top['symbol']} {top['weight']*100:.0f}% · " if top else "")
            + f"{cycles} ciclos hoy · CB {'OK' if operate else 'HALT'}")
    db.save_daily_report(day, metrics, narr)
    return narr


def cycle(tier="ESTABLE", db: DB | None = None) -> dict:
    db = db or DB()
    t0 = time.time()
    mode = "DRY_RUN" if execution.DRY_RUN else ("DEMO" if execution.USE_DEMO else "REAL")
    # 1. datos
    n = fetch.update_universe("1h")
    _log.info(f"[orq] datos actualizados ({n} símbolos)")
    # 2. equity — si NO se puede leer, se OMITE el ciclo (no se rebalancea el libro entero
    #    con un valor inventado; mejor reintentar en el próximo heartbeat).
    equity = execution.get_balance()
    if equity is None:
        _log.warning("[orq] balance ilegible — ciclo OMITIDO (no se rebalancea con valor falso)")
        db.audit("WARNING", "orchestrator", "Ciclo omitido: balance ilegible")
        return {"equity": None, "n_target": 0, "operate": None, "mode": mode, "skipped": True}
    # 3. circuit breaker
    operate = circuit_breaker.check(equity, db)
    # 4. target (leverage anclado al maxDD objetivo del tier — ver engine.compute_target)
    target, vp, df, port, asof, lev, weights, beta_last, beta_model = compute_target(tier)
    bt = pf_metrics(port * lev)   # métricas del backtest CON el leverage anclado (lo que se opera)
    target = target[target.abs() > 0.005]
    if not operate:
        _log.warning("[orq] CIRCUIT BREAKER activo — aplanando (target=0)")
        target = target * 0.0
    # 5. reconcile (posiciones reales ANTES del rebalanceo, para medir los fills)
    current = execution.get_positions() if not execution.DRY_RUN else {}
    n_target = int((target.abs() > 0.005).sum())
    _log.info(f"[orq] equity={equity:.0f} target={n_target}pos gross={target.abs().sum():.2f} "
              f"lev={lev:.2f}x(maxDD-{TIERS[tier]*100:.0f}%) "
              f"posiciones_actuales={len(current)} cb={'OK' if operate else 'HALT'}")
    # 5b. registrar la DECISIÓN (señales por símbolo + desglose por sleeve)
    try:
        _log_signals(db, target[target.abs() > 0.005], vp, weights, lev, asof)
    except Exception as e:
        _log.warning(f"[orq] no se pudieron loguear señales: {e}")
    # 6. rebalanceo
    orders = execution.rebalance(target, equity)
    # 6b. registrar FILLS reales (diff posiciones) + leer posiciones reales con PnL
    positions_detail = []
    if not execution.DRY_RUN:
        try:
            after = execution.get_positions()
            positions_detail = execution.get_positions_detail()
            _log_fills(db, current, after, lev, target, int(t0 * 1000))
        except Exception as e:
            _log.warning(f"[orq] no se pudieron loguear trades/posiciones: {e}")
    # 7. log — β del libro (D1, ya no se hardcodea 0.0). PRIMARIA = β de REGRESIÓN (neutralidad ≈+0.05):
    #    realizada de la equity en vivo cuando hay ≥20 días; si no, la modelo (del backtest del mix actual).
    #    Además se guarda la β-DÓLAR (Σwβ, exposición direccional neta, la infla `trend`) como diagnóstico.
    beta_real, n_days = _beta_realized(db)
    beta_dollar, bd_src = _beta_dollar(positions_detail, beta_last, equity, target)
    beta_book = beta_real if beta_real is not None else round(float(beta_model), 4)
    beta_src = f"realizada({n_days}d)" if beta_real is not None else "modelo"
    _log.info(f"[orq] β regresión ({beta_src})={beta_book} · β-dólar({bd_src})={beta_dollar}")
    db.snapshot_portfolio(equity=equity, gross=float(target.abs().sum()), net=float(target.sum()),
                          beta=beta_book, n_positions=n_target,
                          detail={"tier": tier, "asof": str(asof), "cb": operate, "leverage": lev,
                                  "beta_source": beta_src, "beta_dollar": beta_dollar,
                                  "beta_model": round(float(beta_model), 4),
                                  "maxdd_target": TIERS[tier],
                                  "backtest": {"sharpe": round(bt.get("sharpe", 0), 2),
                                               "ann": round(bt.get("ann", 0), 1),
                                               "maxdd": round(bt.get("maxdd", 0), 1),
                                               "n_sleeves": df.shape[1]},
                                  "orders": len(orders) if orders else 0,
                                  "vp": {k: round(float(v), 4) for k, v in vp.items()},
                                  "positions": positions_detail,   # posiciones reales + PnL del ciclo
                                  "weights": target[target.abs() > 0.005].round(4).to_dict()})
    db.record_equity_tick(equity)      # punto en la curva
    db.upsert_equity_daily(equity)     # retorno del día
    db.audit("INFO", "orchestrator", f"Ciclo {tier} ok ({time.time()-t0:.0f}s)",
             detail={"equity": equity, "n_target": n_target, "operate": operate})
    # 7b. REPORTE DIARIO (metrics + narrativa) para monitoreo/descarga (ver MONITOREO.md)
    try:
        narr = _save_daily_report(db, tier, mode, equity, target, lev, bt, operate)
        _log.info(f"[orq] reporte diario: {narr}")
    except Exception as e:
        _log.warning(f"[orq] no se pudo guardar el reporte diario: {e}")
    db.export_daily_log()   # JSON descargable del día (incluye el reporte recién guardado)
    # 8. SOMBRA: registra la señal del sleeve on-chain TVL SIN operar (validación forward
    #    point-in-time, e26/e27). Totalmente aislado: si falla, no afecta el ciclo que opera.
    try:
        from kepler import onchain
        sh = onchain.run_shadow(db)
        _log.info(f"[orq] sombra on-chain TVL: {sh.get('logged', 0)} señales registradas")
        # blend candidato a sleeve #8 (lotería+tvl+illiq, e40/e41): valida forward antes de promover
        shb = onchain.run_blend_shadow(db)
        _log.info(f"[orq] sombra BLEND: {shb.get('logged', 0)} señales registradas")
    except Exception as e:
        _log.warning(f"[orq] sombra on-chain omitida: {e}")
    notify.alert_cycle(equity, n_target, float(target.abs().sum()), operate, mode)
    return {"equity": equity, "n_target": n_target, "operate": operate, "mode": mode}


def run(tier="ESTABLE", once=False):
    for _s in (sys.stdout, sys.stderr):
        try: _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    db = DB()
    mode = "DRY_RUN" if execution.DRY_RUN else ("DEMO" if execution.USE_DEMO else "REAL")
    _log.info(f"════ KEPLER orquestador · tier {tier} · modo {mode} · rebal {REBALANCE_HOURS}h · hb {HEARTBEAT_MIN}min ════")
    last_rebal = 0.0
    while True:
        try:
            now = time.time()
            # Disparo del rebalanceo: PINEADO a la hora más líquida (config.REBALANCE_HOUR_UTC, e54) para
            # abaratar la ejecución → rebalancea cuando estamos en esa hora UTC y ya pasó MIN_REBAL_HOURS;
            # con fallback a MAX_REBAL_HOURS por si se pierde la ventana (servicio caído). Si la hora es
            # None, vuelve al comportamiento viejo (cada REBALANCE_HOURS desde el arranque, a la deriva).
            hrs = (now - last_rebal) / 3600
            target_h = getattr(config, "REBALANCE_HOUR_UTC", None)
            if target_h is None:
                due = hrs >= REBALANCE_HOURS
            else:
                utc_hour = datetime.now(timezone.utc).hour
                due = (hrs >= MIN_REBAL_HOURS and utc_hour == int(target_h)) or hrs >= MAX_REBAL_HOURS
            if due:                                          # rebalanceo completo (1×/día, hora líquida)
                r = cycle(tier, db)
                if r.get("skipped"):     # balance ilegible → NO consumir la ventana; reintentar
                    _log.warning("[orq] ciclo omitido — se reintenta en el próximo heartbeat")
                else:
                    last_rebal = now
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
