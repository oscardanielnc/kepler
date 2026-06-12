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
import json, logging, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler import fetch, execution, circuit_breaker, notify, checks, track, monitor
from kepler.engine import compute_target, TIERS, load as load_panel_close
from kepler.portfolio import metrics as pf_metrics
from kepler.db import DB

REBALANCE_HOURS = 24
MIN_REBAL_HOURS = 18        # no rebalancear dos veces dentro de la ventana del mismo día
MAX_REBAL_HOURS = 30        # fallback: nunca dejar el libro >30h sin rebalancear (si se pierde la ventana)
HEARTBEAT_MIN = 15          # registra equity cada 15 min (curva viva) sin rebalancear
SKIP_ALERT_THRESHOLD = 3    # ciclos omitidos SEGUIDOS (balance ilegible) antes de escalar (≈45min) →
                            # tapa el punto ciego: un rebalanceo del día perdido EN SILENCIO (hallazgo 06-06)
SLIP_SANITY_BPS = 200.0     # |slip| > 2% = book_mid de referencia stale/corrupto (no es slippage real):
                            # un maker GTX nunca llena tan lejos del mid → se descarta del C3 (no ensucia)
# Flag de REBALANCEO MANUAL: si este fichero existe, el loop fuerza UN rebalanceo en el próximo heartbeat
# (≤15min) y lo borra. Es la vía segura de forzar sin reiniciar el servicio (un reinicio YA no rebalancea).
# Crear en la VM con:  touch /opt/kepler-app/.force_rebalance
FORCE_FLAG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".force_rebalance")
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
    prev_eq = _prev_equity_tick(db)        # ANTES de registrar el nuevo tick (para el chequeo de salto)
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
    # HEALTH-CHECK RUNTIME (Fase 1 paso 3, código puro): salto de equity, recencia de rebalanceo, huérfanas.
    # Solo AVISA (el CB es la red dura); ntfy en TRANSICIÓN (categoría 'checks_hb', sin spam).
    try:
        positions = execution.get_positions() if not execution.DRY_RUN else None
        # pico del equity MTM (incluye el tick recién registrado) → drawdown vs ancla en cada heartbeat
        prow = db.conn.execute("SELECT MAX(equity) FROM equity_daily WHERE equity IS NOT NULL").fetchone()
        peak_eq = float(prow[0]) if prow and prow[0] else None
        hb = checks.run_heartbeat_checks(prev_eq, equity, _last_rebal_ts(db), int(time.time() * 1000),
                                         MAX_REBAL_HOURS + checks.CYCLE_RECENCY_BUFFER_H,
                                         positions, set(config.UNIVERSE), peak=peak_eq)
        sev, prev_sev = checks.worst(hb), _last_check_severity(db, "checks_hb")
        if sev != checks.OK:
            db.audit("CRITICAL" if sev == checks.CRIT else "WARNING", "checks_hb", f"Heartbeat: {sev}",
                     detail={"severity": sev, "summary": checks.summarize(hb)})
            if sev != prev_sev:
                notify.alert_checks_warn("Heartbeat — " + checks.summarize(hb))
        elif prev_sev != checks.OK:        # recuperación
            db.audit("INFO", "checks_hb", "Heartbeat: OK", detail={"severity": "OK"})
            notify.alert_checks_recover()
    except Exception as e:
        _log.warning(f"[hb] health-check runtime omitido (no fatal): {e}")
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
        fill_px, slip_bps, fees_usd, pnl_usd = ref, None, None, None
        try:                                          # VWAP de los fills reales del ciclo (C3)
            tr = execution.get_user_trades(sym, t0_ms)
            num = sum(float(x["price"]) * float(x["qty"]) for x in tr)
            den = sum(float(x["qty"]) for x in tr)
            if den > 0 and ref > 0:
                fill_px = num / den
                slip_bps = (1 if d > 0 else -1) * (fill_px - ref) / ref * 1e4
                if abs(slip_bps) > SLIP_SANITY_BPS:   # ref book_mid corrupto → no es slippage real
                    fill_px, slip_bps = ref, None
            if tr:    # ACCOUNTING DE COSTES (gratis, mismos fills): comisión + PnL realizado de Binance
                fees_usd = round(sum(float(x.get("commission", 0) or 0) for x in tr), 4)
                pnl_usd = round(sum(float(x.get("realizedPnl", 0) or 0) for x in tr), 4)
        except Exception:
            pass
        db.log_fill(symbol=sym, direction="BUY" if d > 0 else "SELL", qty=abs(d), price=fill_px,
                    weight=round(float(target.get(sym, 0.0)), 4), leverage=float(lev),
                    prev_amt=b, new_amt=a, ref_px=ref, slip_bps=slip_bps,
                    fees_usd=fees_usd, pnl_usd=pnl_usd)


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
        "AND ABS(slip_bps) <= ? AND open_ts BETWEEN ? AND ?", (SLIP_SANITY_BPS, d0, d1)).fetchall()
    slip = {}
    if fills:
        v = sorted(f[1] for f in fills); n = len(v)
        worst = max(fills, key=lambda f: f[1])
        slip = {"n": n, "mean_bps": round(sum(v)/n, 2), "median_bps": round(v[n//2], 2),
                "worst_bps": round(worst[1], 2), "worst_sym": worst[0]}
    # ACCOUNTING DE COSTES del día (atribución de la pérdida): comisión + PnL realizado de los fills
    # (ya guardados por _log_fills) + funding (income, no está en los fills). Antes el ledger era null
    # → no se podía explicar el sangrado realizado. Ahora: fees=coste explícito, realized=mercado en
    # cierres, funding=carry pagado/cobrado. Blindado: si falla la lectura de income, funding=None.
    crow = db.conn.execute(
        "SELECT COALESCE(SUM(fees_usd),0.0), COALESCE(SUM(pnl_usd),0.0) FROM trades "
        "WHERE reason='rebalance_fill' AND open_ts BETWEEN ? AND ?", (d0, d1)).fetchone()
    try:
        funding_d = round(sum(float(x.get("income", 0) or 0)
                              for x in execution.get_income(d0, "FUNDING_FEE")), 2)
    except Exception:
        funding_d = None
    costs = {"fees": round(crow[0], 2), "funding": funding_d, "realized_pnl": round(crow[1], 2)}
    cycles = db.conn.execute(
        "SELECT COUNT(*) FROM audit_event WHERE category='orchestrator' AND title LIKE 'Ciclo%ok%' "
        "AND ts BETWEEN ? AND ?", (d0, d1)).fetchone()[0]
    top = None
    if target is not None and len(target) and target.abs().sum() > 0:
        sym = target.abs().idxmax(); top = {"symbol": sym, "weight": round(float(target[sym]), 4)}
    gross = float(target.abs().sum()) if target is not None else 0.0
    net = float(target.sum()) if target is not None else 0.0
    npos = int((target.abs() > 0.005).sum()) if target is not None else 0
    # POSICIONES REALMENTE ABIERTAS (≠ objetivo): el dropping adaptativo al capital suelta las patas
    # < min-notional (a $293, SOL/XRP/ATOM cayeron) → el libro objetivo (npos) puede ser > el vivo. Para
    # el copy-lead lo honesto es mostrar AMBOS. Se lee del último snapshot (escrito en este mismo ciclo);
    # en DRY/sin posiciones queda None y la narrativa cae al objetivo. Blindado: si falla, n_live=None.
    n_live = None
    try:
        srow = db.conn.execute("SELECT detail FROM portfolio_snapshot ORDER BY ts DESC LIMIT 1").fetchone()
        if srow and srow[0]:
            ps = json.loads(srow[0]).get("positions") or []
            if ps:
                n_live = len(ps)
    except Exception:
        n_live = None
    metrics = {"day": day, "mode": mode, "tier": tier, "equity": round(float(equity), 2),
               "today_return_pct": round(ret_pct, 3), "drawdown_pct": round(dd_pct, 3),
               "n_positions": npos, "n_positions_live": n_live, "gross": round(gross, 3), "net": round(net, 3),
               "leverage": round(float(lev), 3), "top_position": top, "cycles_today": int(cycles),
               "slippage_real": slip, "costs": costs, "cb_operate": bool(operate),
               "backtest": {"sharpe": round(bt.get("sharpe", 0), 2), "ann": round(bt.get("ann", 0), 1),
                            "maxdd": round(bt.get("maxdd", 0), 1)}}
    # MÉTRICAS DE TRACK REALIZADAS (A, ventana limpia + maxDD intradía MTM) — lo HONESTO, junto al backtest.
    # Blindado: si falla, el reporte sale igual (no es crítico para operar).
    live = None
    try:
        d_rows = db.conn.execute("SELECT day,equity,ret_pct,dd_pct FROM equity_daily ORDER BY day").fetchall()
        t_rows = db.conn.execute("SELECT ts,equity FROM equity_tick ORDER BY ts").fetchall()
        live = track.realized(d_rows, t_rows, config.TRACK_INCEPTION)
        metrics["live"] = live
    except Exception as e:
        _log.warning(f"[report] métricas de track omitidas (no fatal): {e}")
    # DIGEST DIARIO DE ANOMALÍAS (B) — vigila la watch-list, loguea y avisa en TRANSICIÓN.
    dig = None
    try:
        brow = db.conn.execute("SELECT beta FROM portfolio_snapshot ORDER BY ts DESC LIMIT 1").fetchone()
        dig = monitor.daily_digest(metrics, live, brow[0] if brow else None)
        metrics["monitor"] = dig
        lvl = {"CRIT": "CRITICAL", "WARN": "WARNING"}.get(dig["severity"], "INFO")
        db.audit(lvl, "monitor", f"Monitor diario: {dig['severity']}", detail=dig)
        if dig["severity"] in ("WARN", "CRIT") and dig["severity"] != _last_check_severity(db, "monitor"):
            notify.alert_checks_warn("Monitor diario — " + dig["summary"])
    except Exception as e:
        _log.warning(f"[report] monitor diario omitido (no fatal): {e}")
    live_txt = ""
    if live and live.get("days", 0) >= 1:
        sh = live.get("sharpe")
        sh_txt = (f"Sharpe {sh}" if sh is not None
                  else f"Sharpe n/d (<{live.get('min_days_ratios', 30)}d)")
        live_txt = (f"track {live['days']}d {sh_txt} maxDD {live.get('maxdd')}% "
                    f"(desde {live.get('inception')}) · ")
    pos_txt = f"{n_live}/{npos} pos" if (n_live is not None and n_live != npos) else f"{npos} pos"
    narr = (f"{mode} {tier} · ${float(equity):.0f} ({ret_pct:+.2f}% hoy, dd {dd_pct:.2f}%) · "
            f"{pos_txt} gross {gross:.2f} net {net:+.2f} lev {lev:.2f}x · "
            + (f"slip med {slip['median_bps']}bps (peor {slip['worst_sym']} {slip['worst_bps']}) · " if slip else "slip s/d · ")
            + f"coste fees ${costs['fees']:.2f}"
            + (f" funding ${costs['funding']:.2f}" if costs['funding'] is not None else "")
            + f" realizado ${costs['realized_pnl']:.2f} · "
            + (f"top {top['symbol']} {top['weight']*100:.0f}% · " if top else "")
            + live_txt
            + f"{cycles} ciclos hoy · CB {'OK' if operate else 'HALT'}"
            + (f" · 🩺 {dig['severity']}" if dig and dig["severity"] != "OK" else ""))
    db.save_daily_report(day, metrics, narr)
    return narr


def _last_leverage(db: DB):
    """Leverage del ciclo previo (del último snapshot) para el chequeo de salto. None si no hay."""
    row = db.conn.execute("SELECT detail FROM portfolio_snapshot ORDER BY ts DESC LIMIT 1").fetchone()
    if row and row[0]:
        try: return float(json.loads(row[0]).get("leverage"))
        except Exception: pass
    return None


def _last_check_severity(db: DB, category="checks"):
    """Severidad de los chequeos previos de esa categoría (para notificar solo en TRANSICIÓN, no spamear)."""
    row = db.conn.execute(
        "SELECT detail FROM audit_event WHERE category=? ORDER BY ts DESC LIMIT 1", (category,)).fetchone()
    if row and row[0]:
        try: return json.loads(row[0]).get("severity", "OK")
        except Exception: pass
    return "OK"


def _prev_equity_tick(db: DB):
    """Equity del tick anterior (para el chequeo de salto en el heartbeat)."""
    row = db.conn.execute("SELECT equity FROM equity_tick ORDER BY ts DESC LIMIT 1").fetchone()
    return float(row[0]) if row and row[0] else None


def _last_rebal_ts(db: DB):
    """ts (ms) del último rebalanceo OK (audit 'Ciclo ... ok') para el chequeo de recencia."""
    row = db.conn.execute(
        "SELECT ts FROM audit_event WHERE category='orchestrator' AND title LIKE 'Ciclo%ok%' "
        "ORDER BY ts DESC LIMIT 1").fetchone()
    return int(row[0]) if row and row[0] else None


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
    # 4b. GUARDA PRE-TRADE (Fase 1, robustez operativa): chequeos deterministas (datos/leverage/concentración).
    #     CRÍTICO ⇒ NO rebalancear (libro intacto, reintenta solo el próximo ciclo) — habría frenado el
    #     incidente 2026-06-02 (backfill faltante → ancla 2.93x). Un flatten por CB (operate=False) NO se
    #     bloquea (aplanar a 0 es seguro e independiente de la calidad del dato). Alertas en TRANSICIÓN.
    try:
        chk = checks.run_pretrade_checks(load_panel_close(), target, lev, beta_last,
                                         prev_lev=_last_leverage(db), sleeve_df=df)
        sev, prev_sev = checks.worst(chk), _last_check_severity(db)
        summary = checks.summarize(chk)
        db.audit("CRITICAL" if sev == checks.CRIT else ("WARNING" if sev == checks.WARN else "INFO"),
                 "checks", f"Chequeos pre-trade: {sev}",
                 detail={"severity": sev, "summary": summary,
                         "results": [{"name": r.name, "sev": r.severity, "msg": r.message} for r in chk]})
        if checks.should_block(chk) and operate:
            _log.error(f"[orq] ⛔ GUARDA PRE-TRADE CRÍTICA — rebalanceo BLOQUEADO: {summary}")
            notify.alert_checks_block(summary)
            db.record_equity_tick(equity); db.upsert_equity_daily(equity)   # mantener la curva
            db.audit("CRITICAL", "orchestrator", "Rebalanceo BLOQUEADO por guarda pre-trade",
                     detail={"equity": equity, "summary": summary})
            return {"equity": equity, "n_target": 0, "operate": False, "blocked": True, "mode": mode}
        if sev == checks.WARN and prev_sev != checks.WARN:
            notify.alert_checks_warn(summary)
        elif sev == checks.OK and prev_sev != checks.OK:
            notify.alert_checks_recover()
    except Exception as e:
        _log.warning(f"[orq] guarda pre-trade omitida (error no fatal): {e}")
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
        sh = onchain.run_shadow(db)         # TVL (e26/e27)
        shb = onchain.run_blend_shadow(db)  # blend candidato sleeve #8 (lotería+tvl+illiq, e40/e41)
        sht = onchain.run_tx_shadow(db)     # tx_pxdiv_14d (Coin Metrics, e59/e60/e61) — candidato directo
        shm = onchain.run_mvrv_shadow(db)   # mvrv_lvl (Coin Metrics, e65/e66) — valor, ortogonal a tx
        # UNA línea de confirmación por ciclo (antes 4 audit/ciclo = ~60% del log eran confirmaciones de
        # sombra que no validan nada). La validación real vive en la tabla shadow_signal (la analiza e33);
        # aquí solo dejamos un pulso de salud. Las WARNING por sombra fallida siguen saltando individualmente.
        summ = (f"TVL {sh.get('logged',0)} · BLEND {shb.get('logged',0)} · "
                f"tx {sht.get('logged',0)} · mvrv {shm.get('logged',0)}")
        _log.info(f"[orq] sombras registradas: {summ}")
        db.audit("INFO", "shadow", f"Sombras registradas: {summ}")
    except Exception as e:
        _log.warning(f"[orq] sombra on-chain omitida: {e}")
        db.audit("WARNING", "shadow", f"Sombras omitidas: {str(e)[:120]}")
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
    # Recuperar el ts del ÚLTIMO REBALANCEO REAL desde la DB (no arrancar en 0). Si arranca en 0,
    # `hrs = (now - 0)/3600` es enorme y el fallback `hrs >= MAX_REBAL_HOURS` dispara un rebalanceo
    # INMEDIATO en cada REINICIO del servicio — causa de la sobre-operación del 2026-06-02 (varios
    # deploys el mismo día → 6 rebalanceos → churn/coste → −1.38% del día). Recuperándolo, un reinicio
    # respeta la ventana y espera la hora líquida. Si no hay rebalanceo previo (DB nueva) → 0 → rebalancea
    # al inicio (correcto la 1ª vez). Un servicio caído >MAX_REBAL_HOURS sigue disparando el fallback (ok).
    _lr_ms = _last_rebal_ts(db)
    last_rebal = (_lr_ms / 1000.0) if _lr_ms else 0.0
    if _lr_ms:
        _log.info(f"[orq] último rebalanceo recuperado de la DB: hace {(time.time()-last_rebal)/3600:.1f}h "
                  f"→ un reinicio NO fuerza rebalanceo (se respeta la ventana de rebalanceo)")
    retry_blocked = False     # reanudación rápida: si un ciclo se bloqueó, reintenta cada heartbeat
    consecutive_skips = 0     # ciclos omitidos SEGUIDOS por balance ilegible → escala si se acumulan
    skip_alerted = False      # ntfy de omisión ya enviado (transición; se rearma al recuperar)
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
            # FORCE MANUAL: si existe el flag, fuerza un rebalanceo este ciclo y lo borra (one-shot).
            force = False
            try:
                if os.path.exists(FORCE_FLAG):
                    os.remove(FORCE_FLAG); force = True
                    _log.info("[orq] 🔧 FORCE_REBALANCE (flag manual) → rebalanceo forzado este ciclo")
                    db.audit("INFO", "orchestrator", "Rebalanceo FORZADO manualmente (flag .force_rebalance)")
            except Exception as e:
                _log.warning(f"[orq] no se pudo procesar el flag de force: {e}")
            # REANUDACIÓN RÁPIDA: un ciclo bloqueado/omitido NO consume la ventana → se reintenta cada
            # heartbeat (15min) hasta que los datos/condiciones se reparen (p.ej. backfill), sin esperar 24h.
            if due or retry_blocked or force:                # rebalanceo completo (1×/día, hora líquida)
                r = cycle(tier, db)
                if r.get("skipped"):     # balance ilegible → NO consumir la ventana; reintentar
                    retry_blocked = True
                    consecutive_skips += 1
                    _log.warning(f"[orq] ciclo omitido ({consecutive_skips} seguidos) — se reintenta en el próximo heartbeat")
                    # ESCALADA (hallazgo 06-06): varios omitidos seguidos = el rebalanceo del día está en
                    # riesgo de perderse EN SILENCIO → audit WARN + ntfy UNA vez (transición, sin spam).
                    if consecutive_skips >= SKIP_ALERT_THRESHOLD and not skip_alerted:
                        mins = consecutive_skips * HEARTBEAT_MIN
                        _log.warning(f"[orq] ⚠️ {consecutive_skips} ciclos omitidos seguidos (~{mins}min) — rebalanceo en riesgo")
                        db.audit("WARNING", "orchestrator", "Rebalanceo en riesgo: ciclos omitidos seguidos por balance ilegible",
                                 detail={"consecutive_skips": consecutive_skips, "mins": mins})
                        notify.alert_cycle_skips(consecutive_skips, mins)
                        skip_alerted = True
                elif r.get("blocked"):   # guarda crítica → NO consumir la ventana; reanudación rápida
                    retry_blocked = True
                    _log.warning("[orq] ciclo BLOQUEADO por guarda — reintenta en el próximo heartbeat (reanudación rápida)")
                else:
                    last_rebal = now
                    retry_blocked = False
                    if skip_alerted:     # recuperación tras una racha de omisiones que ya se había alertado
                        db.audit("INFO", "orchestrator", "Rebalanceo recuperado tras omisiones",
                                 detail={"skips_previos": consecutive_skips})
                        notify.alert_cycle_skips_recover(consecutive_skips)
                    consecutive_skips = 0
                    skip_alerted = False
                    _log.info(f"[orq] ciclo completo: {r}")
            else:                                            # heartbeat (solo equity + health-check)
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
