# KEPLER — Sistema cuantitativo multi-activo · Binance Futures
**Dueño:** Oscar Navarro (oscar@pairus.ai) · **Hijo de Sentinel** (proyecto previo en `C:\Users\LENOVO\btc`, ya retirado).

> Lee también: `SYSTEM.md` (validación del edge), `STATUS.md` (estado vivo + changelog + pendientes),
> `DEPLOY.md` (despliegue), `PLAN.md` / `INSTRUCTIONS.md` (diseño original).
> **Empieza cada sesión leyendo `STATUS.md`** — ahí está lo último y lo pendiente.

---

## QUÉ ES KEPLER (en una frase)
Un sistema **market-neutral** que rebalancea a diario una cartera de ~16 posiciones long/short
sobre 32 perps de Binance Futures, combinando **5 estrategias validadas** (walk-forward, costos reales),
con riesgo gestionado a nivel cartera (diversificación + circuit breaker, **sin SL/TP por trade**).

**Misión real:** convertirnos en **copy-lead honesto de bajo drawdown** → track record verificable →
AUM y comisiones. NO competimos por ROI llamativo (eso lo hacen los martingalas que revientan,
ver Brayan/Btc-Panda en `SYSTEM.md`). Competimos por **bajo maxDD, supervivencia, consistencia, transparencia**.

---

## EL EDGE (validado — no re-litigar sin backtest)
5 sleeves con correlación ~0 entre sí, combinados por vol-parity, β-neutralizados contra BTC:
1. **XS-Momentum 30d** · 2. **XS-Reversión 60d** · 3. **Low-vol 14d** · 4. **Carry (funding)** · 5. **Trend long-only (EMA20/100)**

**Motor live ESTABLE 1x (número de producción): Sharpe 1.13 · +15.7%/año (~1.2%/mes) · maxDD −11.6% · 67% meses+.**

### Tiers (palanca de "usar más capital" = más riesgo)
| Tier | Exposición gross | Retorno/mes* | maxDD* | ¿Choca circuit breaker −20%? |
|------|------------------|--------------|--------|------------------------------|
| **ESTABLE (1x)** ← actual | ~0.57x | ~+1.2% | −11.6% | No |
| BALANCEADO (2x) | ~1.14x | ~+2.3% | ~−23% | Sí, lo rozaría |
| GROWTH (3x) | ~1.70x | ~+3.4% | ~−35% | Sí, se pausaría seguido |
*backtest, no garantía. El leverage de la estrategia escala retorno Y drawdown por igual (Sharpe no cambia).

### DESCARTADO por walk-forward — NO resucitar sin nuevo backtest que lo justifique
stat-arb de pares, reversal corto, lead-lag/timing de BTC→alts, cash-and-carry absoluto,
copiar a Btc-Panda (martingala 20x = ruina), gate de régimen y carry-breadth (empeoraron maxDD),
Kelly fraccionario (N insuficiente). Gestión intradía de spikes (= el juego que pierde).

---

## REGLA DE ORO DEL FLUJO DE TRABAJO (crítica)
**Propuesta → backtest del sistema → se implementa SOLO si mejora rentabilidad Y/O reduce riesgo.
Nada a producción sin confirmar la mejora con números.** Si Oscar pide saltarse el backtest, adviértelo.

Otras constantes de Oscar:
- Quiere honestidad cruda, no optimismo vacío. Si algo no rinde, decirlo con números.
- "No me digas que es improbable; encontremos la forma de hacerlo posible."
- Explicar **conciso y concreto**, con tablas/gráficos cuando ayuden. Evitar muros de texto.
- Riesgo ancla: maxDD mensual bajo (~8-10%). ESTABLE cabe holgado bajo el circuit breaker.

---

## ARQUITECTURA (orden de lectura al modificar)
```
config.py              → universo (32 perps), drivers (BTC/ETH), fees, capital, límites
kepler/
  fetch.py             → descarga 1h+funding (data.binance.vision) + refresh incremental (update_universe)
  db.py                → SQLite: signals, trades, portfolio_snapshot, equity_daily, equity_tick,
                         daily_report, audit_event. Fuente de verdad + auditoría + export JSON diario
  alphas.py            → generadores de señal de los 5 sleeves (validados)
  portfolio.py         → vol_parity_weights, combine, metrics, leverage_for_target_vol
  engine.py            → EL CEREBRO: compute_target(tier) → portafolio objetivo (pesos)
  execution.py         → rebalanceo maker (LIMIT GTX), no-fill management, set_leverage(3x),
                         get_positions_detail. Modo por env: DRY_RUN / DEMO / REAL
  circuit_breaker.py   → halt si equity cae 20% desde el pico; reanuda al recuperar
  orchestrator.py      → EL LOOP: cada 15min heartbeat (equity) · cada 24h rebalanceo completo
  notify.py            → push ntfy.sh (ciclo, error, halt)
  report.py            → reporte matplotlib de 6 paneles → logs/kepler_report.png
  api/
    app.py             → FastAPI: /api/status, /positions, /daily, /equity, /logs, /download
    dashboard.html     → SPA dark, Chart.js, auto-refresh 10s
    __main__.py        → uvicorn (DASHBOARD_PORT, default 8080)
research/              → e1..e14 (experimentos de validación de cada edge)
deploy.sh / setup_vm.sh / *.service → despliegue
```

### Cómo funciona el ciclo (clave para entender el sistema)
- **Rebalanceo cada 24h** (`REBALANCE_HOURS`). NO opera intradía — los edges son lentos (días);
  rebalancear más rápido NO mejora (muere por costos, ya testeado).
- **Heartbeat cada 15min** (`HEARTBEAT_MIN`): solo registra equity → curva viva + tabla diaria.
- "Entrar/salir" = diferencia entre posiciones actuales y el nuevo objetivo. Una posición se
  mantiene días si su señal persiste; se reduce/invierte/cierra cuando la señal cambia.
- **Sin SL/TP por trade.** El riesgo es de cartera: diversificación + β≈0 + circuit breaker + tamaño chico.
- **Apalancamiento Binance = 3x por símbolo** (solo margen/buffer de liquidación; NO cambia el tamaño,
  que lo fijan los pesos). "ESTABLE 1x" es el multiplicador de la ESTRATEGIA, cosa distinta.

---

## PRODUCCIÓN (estado al 2026-05-29/30)
- **Desplegado en VM** (Oracle), operando en **DEMO**. Host `opc@oscar-cripto-sentinel-b26`.
- Repo GitHub: `github.com/oscardanielnc/kepler-b26` (rama `main`).
- Dir en VM: `/opt/kepler-app/` (venv) · código en `/opt/kepler-app/kepler/`.
- Config secreta: `/etc/kepler.env` (API keys demo, `KEPLER_DRY_RUN=false`, `KEPLER_USE_DEMO=true`,
  `KEPLER_NTFY_TOPIC`, `KEPLER_LEVERAGE=3`). **OJO: sin comentarios inline en las líneas de valores.**
- Servicios systemd: `kepler` (orquestador) y `kepler-api` (dashboard).
- **Dashboard:** http://213.35.121.9:8080
- **Deploy de cambios:** push a GitHub → en la VM `bash /opt/kepler-app/kepler/deploy.sh`.

### Operar / verificar
- Ver órdenes/posiciones: Binance app → **Trading Demo** → Futuros USDⓈ-M → Posiciones / Órdenes abiertas.
- Logs en vivo: `journalctl -u kepler -f`. Modo real del servicio: badge del dashboard o el banner del log.
- Alertas push: suscribirse al topic de `KEPLER_NTFY_TOPIC` en la app ntfy.sh.

---

## REGLAS DURAS
1. Nada a producción sin backtest que confirme mejora (regla de oro).
2. Validar SIEMPRE en demo antes que real. Hoy estamos en demo.
3. No resucitar edges descartados sin nuevo backtest.
4. Tier ESTABLE hasta tener track record real; subir de tier es decisión de Oscar.
5. Capital separado. RECORDATORIO PENDIENTE: Oscar debe **retirar $1800 de Brayan** (martingala, ruina probada).
6. Documentar cada sesión en `STATUS.md`.
