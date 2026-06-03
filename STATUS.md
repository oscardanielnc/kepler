# KEPLER — Estado vivo · Changelog · Pendientes
> **Empieza cada sesión leyendo este archivo.** Última actualización: **2026-06-03** (cierre de sesión: frontend Stitch + 2 bugs operativos corregidos + accounting de costes + ruta copy-lead acordada, hora Lima).
>
> **🧭 PLAN A SEGUIR = `ROADMAP.md` §RUTA MAESTRA 2026-06 (Operación → Producto → Escala).** Cambio de
> fase: la caza de alfa GRATIS está AGOTADA (verificado a fondo); la palanca ahora es OPERACIÓN + PRODUCTO
> + ESCALA, no más sleeves marginales. Atacar EN ORDEN: Fase 0 (correr DEMO/sombras = tiempo) · **Fase 1
> ROBUSTEZ OPERATIVA (prioridad, el incidente de hoy probó que es el riesgo #1)** · Fase 2 producto/track
> · Fase 3 escala. IA = herramienta operativa, NO alfa. Negocio = copy-lead. (Memorias `kepler-news-ia-bots-decision`.)
>
> **⏭️ PRÓXIMA EJECUCIÓN (tras cierre 2026-06-03):**
>   1. **PUSH + DEPLOY (Oscar)** de los commits locales de hoy (4: `2034e74` frontend+robustez · `c009226`
>      telemetría · `7609b9f` docs ruta · + el de cierre). En la VM tras desplegar: `journalctl -u kepler` →
>      al reiniciar debe decir `último rebalanceo recuperado de la DB … no fuerza rebalanceo` (fix churn);
>      ciclo con `checks: OK`, heartbeat OK; abrir `/` y `/track` con el estilo nuevo; la limpieza de slippage
>      basura corre sola al instanciar la DB.
>   2. **FASE 0 = DEMO LIMPIO ~3-4 semanas** (reloj limpio desde **2026-06-04**, post-fixes). Gate de salida:
>      0 incidentes operativos en 30d + slippage/fees reales ≈ backtest + β≈0/maxDD dentro de presupuesto.
>      **CADENCIA acordada: Oscar trae los logs CADA DÍA** → verificar estado, vigilar que no reaparezcan
>      bugs, medir el edge en vivo (Sharpe/maxDD/β) con el PRINCIPIO DE EVALUACIÓN CON BUGS (`ROADMAP.md`).
>   3. **Luego: Binance capital PROPIO chico** (arranca el track real) → **copy-lead** modesto → escala.
>      Ruta completa + gates en `ROADMAP.md §RUTA DE SALIDA`; mecánica de cuenta lead en `COPYLEAD.md`.
>   En paralelo corre solo: sombras→sleeve #8 (~2026-07-31) + C3 slippage real.
>
> **ESTADO FASES (2026-06-03):** **Fase 1 (robustez) CERRADA** (pasos 1-5, verificados). **Fase 2 núcleo
> HECHO** (F2.1 `/api/track` + F2.2 `/track` + F2.3 research copy-lead `COPYLEAD.md` + **rediseño Stitch YA
> hecho** + ruta de salida acordada/documentada); queda solo **acumular track real** y activar copy-lead.
> **TODO en commits locales — PENDIENTE PUSH+DEPLOY (Oscar);
> hasta desplegar, las guardas NO protegen el vivo y el frontend nuevo no se ve.** C2 cerrado (ya hecho por
> construcción; banda no-trade diferida a AUM). USDC aparcado (solo maker + promo, no game-changer).
>
> **Estado del sistema en PRODUCCIÓN (DESPLEGADO y verificado en vivo 2026-06-02 tarde):** 7 sleeves · ancla
> −10% · **lev 2.23x** (vol-anchor e68, tras incidente sobre-leverage 2.93x→2.23x) · haircut 0.95 · **cap
> 15%/nombre** (e69) · trend cap 0.25 · universo 20 long (−XLM/HBAR/LIT) · rebal 14 UTC · CB en heartbeat ·
> slippage telemetría limpia (e70 winsor). 4 sombras registrando (tx/mvrv/tvl/blend).
> ⚠️ **La Fase 1 (guardas/checks) está en commits locales, NO en la VM todavía** (≠ el bloque de arriba que sí está vivo).
> **⏰ RECORDATORIO ~2026-07-31:** cerrar ciclo sombras (≥60-90d → `e33_shadow_tvl_analyze` → ¿sleeve #8?).

---

## ESTADO ACTUAL (2026-06-03)
- 🎨 **SESIÓN FRONTEND (2026-06-03): rediseño Stitch integrado en `dashboard.html` + `track.html`.**
  Tomadas las 2 pantallas del proyecto Stitch *Kepler Institutional Design System* (vía MCP) y reescritas
  ambas páginas con su sistema de diseño (tema CLARO institucional ivory/navy, tarjetas hairline, **Source
  Serif 4** titulares + **Inter** cuerpo + **JetBrains Mono** tabular en cifras; color solo semántico:
  teal=ganancia, rojo=pérdida, oro=aviso). **Doctrina respetada** (`kepler-design-doctrine`): premium, NO casino.
  - **Cableado de datos VIVO intacto:** mismos `id`, mismo bucle fetch + auto-refresh, mismas gráficas Chart.js
    (equity, drawdown, doughnut 7 sleeves, PnL, heatmap mensual) — solo re-estilizadas a los tokens. Endpoints
    sin tocar (`/api/status|health|daily_report|positions|daily|equity|logs|track`).
  - **Aparté del mock de Stitch** (por §Notas de `DESIGN_BRIEF.md` + honestidad): quité sidebar/nav falsa
    (Strategies/Compliance/etc.), claim "Member FINRA/SIPC", botón "Trade", tarjeta "Platinum Quant" y fotos
    decorativas. Quité la dependencia de icon-font Material Symbols (fallaba mostrando el nombre del icono como
    texto) → glifos simples (✓ ⚠ ●). Dependencia nueva: **Tailwind por CDN** (+ Chart.js que ya estaba).
  - **Verificado sin bugs:** levanté la API local y rendericé `/` y `/track` en Chrome headless → ambas cargan,
    fetchean datos reales y dibujan todas las gráficas sin errores JS. Archivos siguen autocontenidos (1 .html).
  - **PENDIENTE (Oscar):** PUSH+DEPLOY y mirar `/` y `/track` en la VM. Futuro (anotado, no urgente): ampliar
    el bloque "cómo se gestiona el riesgo" y algún contenido más en `/track`.
- 🐛 **BUG OPERATIVO ENCONTRADO Y CORREGIDO (2026-06-03): reinicio del servicio forzaba rebalanceo inmediato → churn.**
  Diagnóstico de la "pérdida" que preocupaba a Oscar (equity 4939→4860 = **−1.61% en 5 días**):
  - **El "hoy 0%" es CORRECTO** — el 06-03 la equity quedó plana (+0.004%). No es bug del frontend.
  - **Toda la pérdida es UN evento:** el 06-02 cayó −1.38% en un escalón de **−$63 a las 15:35 UTC**, justo en un
    rebalanceo. Ese día el sistema rebalanceó **6 veces** (01,14,15,18,19,23h) cuando debe ser **1×/24h**.
  - **Causa raíz (`orchestrator.run`):** `last_rebal` arrancaba en `0.0` en memoria → tras cualquier REINICIO,
    `hrs=(now-0)/3600` es enorme → el fallback `hrs>=MAX_REBAL_HOURS` dispara rebalanceo INMEDIATO. El 06-02
    hubo varios deploys (fix de leverage 2.93→2.23 + cambios exec) → cada reinicio forzó un rebalanceo → churn.
  - **Fix:** `last_rebal` ahora se recupera del último "Ciclo ok" en la DB (`_last_rebal_ts`, helper que ya
    existía pero no se usaba para esto). Verificado por simulación: reinicio 2h tras rebal → ya NO rebalancea;
    ventana 14h y fallback >30h siguen funcionando; DB nueva rebalancea al inicio (correcto). `py_compile` OK.
    **Es fix de robustez operativa (no toca el edge ni el sizing; acerca el vivo al supuesto del backtest
    de 1 rebal/día) → no requiere backtest.** Commit local pendiente PUSH+DEPLOY (Oscar).
  - **Reconciliación verde/rojo:** el libro ABIERTO ahora está en **+$87 no realizado** (11 verdes +$204 / 6
    rojas −$117), pero la cuenta está −$79 → la diferencia (~−$166) es **pérdida YA REALIZADA en rebalanceos
    pasados** (sobre todo el churn del 06-02). Por eso "muchas verdes" y aun así pérdida: las verdes son del
    libro vivo; el sangrado está en lo ya cerrado.
- ✅ **ACCOUNTING DE COSTES MONTADO (2026-06-03, gap #1 cerrado):** el ledger `trades` ahora registra
  `fees_usd` (comisión real) y `pnl_usd` (PnL realizado de Binance) por fill — **gratis**, sacados del mismo
  `userTrades` que ya se pedía para el slippage (`_log_fills`). El reporte diario gana un bloque `costs`
  {fees, funding, realized_pnl} (funding vía `execution.get_income` FUNDING_FEE, nuevo helper read-only) y el
  dashboard lo muestra en la tarjeta "Reporte del día" (Fees / Funding / Realizado). Así CADA pérdida se
  podrá atribuir a coste-vs-mercado. Sumas verificadas con datos mock. (Datos viejos → "s/d" hasta el 1er ciclo nuevo.)
- ✅ **REBALANCEO MANUAL FORZADO (flag-file):** `orchestrator.run` revisa `.force_rebalance` (repo root →
  `/opt/kepler-app/.force_rebalance`) cada heartbeat; si existe, fuerza UN rebalanceo y lo borra. Vía segura
  de forzar SIN reiniciar (el reinicio ya no rebalancea). Forzar en VM: `touch /opt/kepler-app/.force_rebalance`
  (o `python -m kepler.orchestrator --once` para un ciclo suelto inmediato). En `.gitignore`.
- ✨ **MEJORAS FRONTEND adicionales (2026-06-03):**
  - **"Posiciones activas ahora"** reestructurado: grupo **Exposición** (Long/Short/Net con sub-etiquetas
    "comprado/en corto/dirección neta β≈0" + tooltips) y grupo **Resultado** (Ganancias/Pérdidas/PnL no
    realizado + Comisiones acum. + **Balance neto desde inicio**). `/api/status` ahora expone
    `cum_fees`/`cum_realized`/`net_balance`. Deja clara la lección verde-libro vs cuenta-roja.
  - **🐛 fix latente:** en modo OBJETIVO los notional vienen con signo → el Short salía negativo y el Net
    sumaba en vez de restar (+$4,169 en vez de +$1,676). Corregido con `Math.abs` (correcto en DEMO y objetivo).
  - **"Rentabilidad por día" → CALENDARIO** mensual (reemplaza la tabla): cada día muestra el **retorno %**
    destacado (verde/rojo por signo+magnitud) y, en tenue, equity de cierre + drawdown; hoy recuadrado;
    navegación ‹ › por meses (defecto mes actual, límites = 1er día con datos … mes actual); responsivo
    (oculta el sub-texto en móvil). Solo usa `/api/daily`, sin datos nuevos.
  - **Logs del sistema** mejorado: (a) el botón de nivel seleccionado ahora se **resalta** (`.active`);
    (b) **filtro por rango de fechas** (Desde/Hasta, defecto día actual en hora Lima) — `/api/logs` acepta
    `start`/`end` y filtra por bounds del día local; (c) **descarga movida del header a la sección de logs**:
    "⬇ Descargar rango" (día concreto o rango, vía `/api/download?start&end`) + "⬇ Todo" (histórico). El
    header queda limpio (solo Track record). Resuelve el descargar logs de un día/rango específico.
- ✅ **SLIPPAGE BASURA + RUIDO DE LOG limpiados (2026-06-03):**
  - **Slippage −742bps:** era LEGADO (fills previos al winsor e70). El winsor en vivo (`SLIP_SANITY_BPS=200`)
    ya lo evita; añadí **limpieza idempotente en `DB.__init__`** que anula `slip_bps` con `|slip|>200` (one-shot
    al desplegar). Verificado: −742→NULL, 12.5 y −199 intactos.
  - **Ruido de log:** las 4 audit INFO de sombra por ciclo ("Sombra X registrada (N pos)") = ~60% del log y
    NO validan nada (la validación vive en la tabla `shadow_signal`, la analiza e33). Quitadas de `onchain.py`;
    el orquestador deja **UNA** línea/ciclo de pulso (`Sombras registradas: TVL.. BLEND.. tx.. mvrv..`). Las
    WARNING por sombra fallida (omitida/sin datos) **permanecen** (son banderas reales). Log ahora = ciclos +
    checks + engine + 1 pulso de sombra + errores/avisos. Sin perder datos (shadow_signal intacta).
- 🛣️ **RUTA DE SALIDA A COPY-LEAD acordada (2026-06-03) → documentada en `ROADMAP.md §RUTA DE SALIDA` +
  `COPYLEAD.md §Mecánica de cuenta lead`.** Resumen: DEMO limpio ~3-4 sem (gate = 0 incidentes 30d + costes≈
  backtest + β≈0/DD ok) → Binance capital PROPIO chico (aquí arranca el track real, ~4-8 sem) → copy-lead
  modesto → escalar. El reloj de credibilidad corre en REAL, no en DEMO → no alargar la DEMO. Una sola
  plataforma al inicio (Binance; el track no se transfiere entre exchanges).
- 📐 **PRINCIPIO DE EVALUACIÓN CON BUGS (acordado, no eliminar/ocultar nada):** los tramos con bug quedan como
  aprendizaje. **PENDIENTE de implementar cuando Oscar pida analizar las 3-4 sem:** marcador de inicio limpio
  (`2026-06-04`, post-fix churn) y/o exclusión de rangos con bug en `/api/track`, SIEMPRE etiquetado ("desde
  operación estable"). Sharpe con <30-60d = ruido; el −9.69 del tramo 06-02 no juzga el edge. Detalle en
  `ROADMAP.md §PRINCIPIO DE EVALUACIÓN CON BUGS`.
- ❗ **PENDIENTE de housekeeping:** `.mcp.json` y `DESIGN_BRIEF.md` siguen sin commitear (untracked).

## ESTADO ACTUAL (2026-06-02)
- 🟢 **SESIÓN DE RIESGO/CALIDAD (2026-06-02): D0 + D1 + concentración TRX + monedas finas — TODO cerrado.**
  Resultado neto: libro **más limpio, más barato, menos concentrado Y con mejor número honesto.**
  Config final: **haircut 0.95 · trend cap 0.25 · universo −{XLM,HBAR,LIT}**. Motor vivo: **lev 2.16x ·
  ~4.47%/mes flat (~3.4%/mes realista) · maxDD IS −9.5% · mo+ 73% · TRX 14.1%** (cap lo contiene).
  - **D0 (ancla):** haircut wired (`config.LEVERAGE_HAIRCUT`). Clave: e52/e53 **arreglaron el sobre-apalancamiento
    de raíz** — el maxDD OOS del walk-forward cayó −13.5%→**−7.1%** (libro limpio) → el haircut se relajó
    0.85→**0.95** (recupera retorno, deja cojín). El −10% se respeta con margen.
  - **D1 (β real):** snapshot reporta β de regresión (modelo +0.025 → realizada a ≥20d) + β-dólar diagnóstica.
  - **Concentración TRX (e52):** cap 0.25 en `trend` (= MAX_WEIGHT_NORMAL) → TRX 20%→~10-14%, HHI −34%, Sharpe intacto.
  - **Monedas finas (e53):** retiradas XLM/HBAR/LIT (edge ~nulo + slippage 7.5-12.9bps); **ZEC se mantiene**
    (tiene edge real, e48). Neto realista 2.24→2.96%/mes @haircut-0.85, sin empeorar OOS.
  ✅ **DESPLEGADO 2026-06-02 (Oscar)** — 2 commits: `e2f0505` (riesgo: haircut 0.95, β real, cap 0.25,
  universo −{XLM,HBAR,LIT}, fix ffill sombra) + `55a429a` (ejecución: pin rebal 14 UTC e54, chequeo CB
  intradía en heartbeat e15). **🔎 AHORA: validar el sizing en DEMO** (que el maxDD real quede cómodo
  bajo −10%; el lev 2.16x sale del ancla sobre datos recientes calmos).
  - ⚠️ **NUEVO cambio de prod pendiente de deploy:** `execution.rebalance` ahora **cierra automáticamente
    posiciones huérfanas** (coins fuera del target/universo, p.ej. XLM/HBAR/LIT). Al desplegar esto, se
    cierran solas en el primer ciclo — ya no hay que cerrarlas a mano. (Commits locales post-deploy:
    `edfd33d` docs, `81797d7` e56, + este fix de huérfanas + e56 research.)
- ❌ **FASE 2 INTRADÍA order-book → DESCARTADO (e45):** a coste real (taker+ADV 8.6bps) TODAS las celdas
  negativas; el muro es coste×turnover (1h→4313x), no la señal. Rama order-book intradía CERRADA. Detalle
  en changelog tarde-3 e `INTRADAY.md §5`. Backtester horario queda montado/reusable para las otras ramas.
- ✅ Sistema **desplegado y operando en DEMO** en la VM (Oracle, `opc@oscar-cripto-sentinel-b26`).
  Dashboard http://213.35.121.9:8080. Circuit breaker −20% activo. Alertas ntfy OK.
- ✅ **7 sleeves + ancla maxDD −10%.** Tras mejoras de hoy (carry suavizado 7d):
  **Sharpe 2.07 · ann 49.3% (~4.11%/mes) · maxDD −10% · lev 2.02x · 71% meses+** (BACKTEST; en vivo bajará).
- ✅ **β-neutral auditado: β ≈ +0.05** (net-long en $ es esperado, no fallo). Ver memoria.
- ✅ **Honestidad estadística:** Deflated Sharpe **0.951–0.995** (e20) → el 2.07 no es suerte de buscar.
- ✅ **Costos:** contabilidad uniforme en los 7 sleeves (trend ya paga). C1 (e18) mostró que con slip
  realista el honesto baja a ~2.7-3.5%/mes; C3 (medición de slippage real) montada, esperando datos.
- ✅ **Telemetría completa:** señales (con desglose por sleeve), fills reales, posiciones+PnL, export
  de análisis (histórico completo). Curva de equity full-width.
- ✅ **DESPLEGADO Y CORRIENDO (Oscar confirmó 2026-05-31 ~09:28 Lima):** la versión actual está en la
  VM operando en DEMO, se deja corriendo. **Confirmar al arrancar** (ver "VERIFICAR AL ARRANCAR").
- 🌓 **4 SOMBRAS (no operan, validación forward):** (1) TVL `onchain_tvl_pxdiv_14d` + (2) BLEND
  `blend_lottery_tvl_illiq_v1` (registrando desde 06-01); (3) **TX `onchain_tx_pxdiv_14d`** (actividad,
  +1.46%/mes) + (4) **MVRV `onchain_mvrv_lvl`** (valor, +1.41%/mes, turnover 6x) — implementadas 06-02,
  registran tras el deploy. tx y mvrv son **ortogonales entre sí (corr +0.02)** y a los 7 → 2 edges
  on-chain independientes. ⏰ **Reloj 60-90d (~2026-07-31) → `e33`-style → ¿promover a sleeve #8?**
  (tx/mvrv como directos; blend como conjunto). PENDIENTE DEPLOY de las sombras tx+mvrv.
- ✅ **B1/B2 (e29) + D0 RESUELTO:** el edge es ROBUSTO (Sharpe OOS 2.29 ≈ IS 2.21, 6/6 folds). El ancla
  sobre-apalancaba (maxDD OOS −13.5%) pero **se arregló** (haircut 0.95 + libro limpio → maxDD OOS −7.1%).
  El −10% se respeta con margen. Validar en DEMO el maxDD real.

### 🗂️ INVENTARIO DE SLEEVES (referencia rápida)
**OFICIALES (7, todos DIARIOS · rebal 24h · `engine.SLEEVES`):** 1.`mom_30d` (720h) · 2.`rev_60d` (1440h) ·
3.`lowvol_14d` (336h) · 4.`carry` (funding suav.7d, hold 48h) · 5.`trend` (EMA20/100 long-only) ·
6.`takerflow_5d` (120h) · 7.`hlpos_14d` (336h). Combinado: Sharpe 2.07 · maxDD −10% · 4.1%/mes · β +0.05.
**EN SOMBRA (candidatos #8, DIARIOS, no operan):** `onchain_tvl_pxdiv_14d` + `blend_lottery_tvl_illiq_v1`
(lotería+TVL+iliquidez) registrando desde 06-01; **`onchain_tx_pxdiv_14d`** (Coin Metrics, el más fuerte:
+1.46%/mes vs los 7, ortogonal a todo) implementado 06-02, registra tras deploy. Acumular 60-90d → e33.
**INTRADÍA:** ninguno operable. Order-book DESCARTADO (e45). Backtester horario (e42/e44) montado.
**Frecuencia del sistema HOY = 100% diaria.** No hay sleeve intradía en producción ni en sombra
(la sombra solo registra señales diarias cada ciclo; lo intradía no es sombreable en el sistema diario).

### Estado del código vs producción
- Commits de hoy (carry 2.07, costo trend, B3, C3, A4, dashboard explicativo) desplegados por Oscar.
- Claude NO hace push/pull ni deploy (memorias `kepler-no-git-push`, `kepler-claude-no-ssh-deploy`);
  Oscar pushea/despliega. Si hay un commit local de docs posterior, lo subirá la próxima vez.

---

## CHANGELOG 2026-06-03 (mañana-5 — Rediseño frontend: Stitch MCP configurado + design briefs)
Oscar quiere rediseñar el frontend con Google Stitch (sus diseños le gustan). Verificado: el MCP de Stitch
existe e integra con Claude Code (`@_davideast/stitch-mcp`, community de David East; tools `build_site`/
`get_screen_code`/`get_screen_image`). Decisión de flujo: **Oscar+Stitch hacen el diseño/estética; Claude
integra el HTML en las páginas VIVAS y cablea los datos** (Stitch da el cascarón, no sabe de `/api` ni Chart.js).
- **`.mcp.json`** creado (servidor stitch, API key por `${STITCH_API_KEY}` — NO en el repo). **Key de Oscar
  configurada por Claude** (persistida como var de entorno de USUARIO en Windows, no en el repo) y **VERIFICADA**:
  `npx @_davideast/stitch-mcp doctor` → "API Key Detected + Stitch API Healthy (200), All checks passed".
  Pendiente Oscar: **reiniciar Claude Code** para que cargue el `.mcp.json` y aprobar el server → `/mcp` healthy.
- **`DESIGN_BRIEF.md`** creado: 3 prompts listos para pegar en Stitch (§0 sistema de diseño → DESIGN.md;
  §1 dashboard operativo; §2 track record) + notas de integración.
- **🔑 Doctrina de diseño (memoria `kepler-design-doctrine`) — ACTUALIZADA (Oscar 2026-06-03):** NO tiene que
  ser oscuro; **claro U oscuro**, lo que prime es **elegante/premium que inspire confianza a inversores de ALTO
  CAPITAL** (estética banca privada / gestión de patrimonio). Sigue: NO casino, sobriedad, maxDD con tanto
  orgullo como el retorno. Briefs actualizados a esa dirección (track tiende a premium en variante clara).
- PENDIENTE: ejecutar el rediseño cuando Oscar tenga los diseños de Stitch (próxima sesión de frontend, "con calma").

## CHANGELOG 2026-06-03 (mañana-4 — FASE 2 / F2.1+F2.2: página de TRACK RECORD presentable → Fase 2 núcleo HECHO)
Implementado lo que quedaba de Fase 2 (Oscar: USDC se aparca, no encaja/promocional). Code-first, cero IA.
- **F2.1 · `/api/track`** (en `api/app.py`): métricas de track-record del **equity REAL en vivo** (no backtest):
  retorno total, anualizado, Sharpe/Sortino realizados, vol, maxDD, % días+ / meses+, β (del snapshot),
  gross/net/nº posiciones, **serie de retornos mensuales** y **curva de equity diaria** + narrativa templada
  honesta. El backtest se devuelve aparte y SIEMPRE etiquetado "referencia". Hook IA (resumen legible) dejado
  para futuro (F2.1 lo permite), no implementado ahora (code-first).
- **F2.2 · `/track` + `track.html`** (nuevo): página dedicada presentable para inversor, SEPARADA del
  dashboard operativo (sin logs ni internals). KPIs (retorno/Sharpe/maxDD/meses+/β/días), curva de equity,
  métricas secundarias, tabla de retornos mensuales y un bloque "cómo se gestiona el riesgo" + disclaimer
  honesto (DEMO, sin SL/TP, circuit breaker, track corto=ruidoso, backtest=referencia). Enlace desde el dashboard.
- **Verificado:** import OK, rutas `/api/track` y `/track` registradas; TestClient 200 con datos reales
  (4 días en vivo, Sharpe realizado 0.08 (muestra ínfima), maxDD −1.22%, β +0.02, 17 pos, tabla mensual);
  JS `node --check` OK. **PENDIENTE PUSH+DEPLOY + pulido visual (con calma, próxima sesión de frontend).**
  → **Núcleo de Fase 2 HECHO** (F2.1+F2.2+F2.3). Falta solo activar copy-lead cuando el track real lo respalde (F2.3 checklist).

## CHANGELOG 2026-06-03 (mañana-3 — USDC 0% (verdad parcial) + C2 turnover (ya hecho por construcción))
Dos preguntas de Oscar. Respuestas con números:
- **USDC 0% comisión — REAL pero PARCIAL y promocional (no game-changer).** Términos oficiales Binance
  (promo desde 2025-12-10, "until further notice", ya extendida): **maker 0.0000%** todos los niveles ·
  **taker SIGUE ~0.0400%** (regular; 0.0094% VIP9). El "0%" que ve Oscar = el MAKER. Trampa real = **liquidez**:
  los libros USDC-M son más finos → más SLIPPAGE, que es el coste DOMINANTE de Kepler (slip~K/√vol), no el fee.
  + cobertura parcial (finas como ZEC casi sin USDC-M) + funding USDC-M ≠ USDT-M (afecta carry).
  - **¿Resucita lo descartado? NO.** Kepler ya es maker-first (~2bps en USDT) → el USDC solo raspa ~2bps en
    majors líquidos. Lo intradía/order-book (e45) murió a **taker+slippage 8.6bps**; el taker sigue ~4bps en
    USDC y el slippage es PEOR en libros finos → el muro coste×turnover sigue en pie. Único uso legítimo:
    optimización opcional = rutar fills maker de majors líquidos por USDC-M (~2bps), si la profundidad USDC-M
    es comparable (verificable con maquinaria e54). Ítem menor serie C, NO se persigue ahora. Memoria `kepler-usdc-fees`.
- **C2 (netear turnover entre sleeves) — YA HECHO por construcción.** `engine.compute_target` combina a
  **target neto por símbolo** (Σ vpᵢ·wᵢ); `execution._place_deltas` solo manda el delta neto vs posición real
  (piso MIN_ORDER_USD=$5). No hay órdenes por-sleeve que netear. La descripción del ROADMAP asumía un diseño
  que no es el real. **Lo único que queda = banda de no-trade** (`simulate(band=)` ya la soporta en el
  backtester): a tamaño DEMO ahorro chico (e55: slippage ~0; solo maker 2bps × turnover), misma categoría que
  e55 slicing (escala con AUM, ~nulo hoy). Validarla exige construir backtester del sistema combinado.
  - **DECISIÓN OSCAR: DIFERIR C2 como e55** → C2-literal marcado "hecho por construcción"; la banda de
    no-trade va al workstream de capacidad/AUM (revisar al escalar, junto a slicing e55 y cap de tamaño B4).
    Hoy payoff ~nulo a tamaño DEMO. C2 CERRADO por ahora.

## CHANGELOG 2026-06-03 (mañana-2 — FASE 2 / F2.3: research copy-lead → `COPYLEAD.md`)
Tras cerrar Fase 1, Oscar pidió recomendación de rentabilidad. Encuadre honesto: la palanca grande NO es
más alfa (gratis agotada; a $5k de DEMO un +3.5%/mes son ~$175) sino el **NEGOCIO = profit-share copy-lead
sobre AUM** → requiere track real (tiempo) + producto. Oscar eligió arrancar **F2.3 (investigar copy-lead)**.
- **Research hecho (web, 2026-06-03) → `COPYLEAD.md`** (entregable checklist):
  - **Encaje EXCELENTE:** el bajo-maxDD es premiado en descubrimiento Y profit-share en todas (Bybit rankea
    por maxDD/consistencia; Binance da 15% si maxDD 90d ≤25%). Nuestro diferenciador = su eje de pago.
  - **Mecánica:** libro market-neutral multi-símbolo (long unos / short otros) **ES copiable** (one-way
    proporcional; NO es hedge-mode del mismo símbolo). Mínimos de lead triviales (~500-1000 USDT).
  - **2 cautelas:** (1) fragmentación de margen en seguidores chicos replicando ~20 posiciones (mínimo
    notional por orden) → usar Fixed Ratio / variante "lite"; (2) turnover diario + fills taker del seguidor
    → su retorno < track publicado (comunicar el gap con honestidad). HWM (Bybit Pro/Binance) = aliado bajo-DD.
  - **Plataformas:** Binance (liquidez, 10→15%), Bybit (Pro hasta 30%+HWM, ranking por riesgo), Bitget
    (comunidad mayor, hasta 20%), OKX (hasta 30%). Detalle + checklist en `COPYLEAD.md`.
  - **Cuello de botella NO es elegibilidad** sino track real (Fase 0) + diseñar libro copiable-limpio.
- **Recomendación de rentabilidad (registrada):** Tier1 = negocio (F2.3 ✓ + F2.1/2.2 producto); Tier2 =
  retorno gratis estrategia (C2 netear turnover, sleeve #8, C1/C3 costes); Tier3 = pago (CryptoQuant/Santiment,
  prematuro a este AUM) o subir tier (duplica retorno pero traiciona bajo-DD sin track → Fase 3).

## CHANGELOG 2026-06-03 (mañana — FASE 1 PASO 5 / F1.4: salud + reporte diario en el DASHBOARD → Fase 1 CERRADA)
Cierre del último paso de Fase 1. **Decisión de Oscar: interactivo en el frontend, NO PDF/texto** (el PDF
profesional es outbound = Fase 2/track-record; hoy lo que protege es el panel que él vigila a diario).
- **Hallazgo clave: cero lógica nueva.** Toda la data ya estaba persistida por los pasos 1-4: los checks de
  `checks.py` se auditan cada ciclo en `audit_event` (categorías `checks` pre-trade con `results` por chequeo,
  y `checks_hb` heartbeat), y la narrativa+métricas templadas ya viven en `daily_report`. F1.4 = **exponer +
  pintar**, code-first, CERO IA.
- **API (`kepler/api/app.py`), 3 endpoints nuevos:** `/api/health` (último pre-trade + heartbeat, severidad
  por chequeo OK/WARN/CRIT + overall), `/api/health/history?days=30` (severidad PEOR por día Lima → franja),
  `/api/daily_report` (narrativa + métricas del día más reciente o por fecha).
- **Dashboard (`dashboard.html`), 2 tarjetas:** "Salud del sistema" (badge global + lista de chequeos con
  ✅/🟡/🔴 y mensaje + franja-historial 30d + sello de hora) y "Reporte del día" (narrativa templada en mono +
  8 métricas resaltadas: retorno, dd, lev, posiciones, top, slippage mediana, ciclos, CB). Auto-refresh 10s.
- **Verificado:** `app.py` compila+importa, 3 rutas registradas; TestClient devuelve 200 con datos reales
  (health overall OK, todos los chequeos verdes; daily_report con narrativa+métricas). JS `node --check` OK.
  **PENDIENTE PUSH+DEPLOY + revisión visual en http://213.35.121.9:8080.** Con esto **Fase 1 queda CERRADA**
  (pasos 1-5); siguiente fase real = Fase 2 (producto/track) cuando la DEMO acumule semanas.

## CHANGELOG 2026-06-02 (noche-2 — FASE 1 robustez: guardas pre-trade (checks.py) wired al orchestrator)
Arranque de la Fase 1 (ROADMAP §RUTA MAESTRA), CODE-FIRST cero IA. Pasos 1 y 2 hechos:
- **Paso 1 — `kepler/checks.py`** (módulo nuevo, chequeos puros): data_coverage (caza el incidente de hoy:
  panel arranca tarde → CRIT), data_freshness, leverage (banda+salto), concentración, n_posiciones,
  β-dólar. Severidad OK<WARN<CRIT. Test `research/e75_checks_test.py`: 6 casos, **el incidente reproducido
  (datos desde 2023) BLOQUEA** ✅; todos los asserts pasan.
- **Paso 2 — wired al orchestrator (`cycle`):** guarda PRE-TRADE entre target y rebalanceo. **CRÍTICO +
  operate ⇒ NO rebalancea** (libro intacto, reintenta solo próximo ciclo = opción (a) de Oscar), ntfy
  urgente, audit CRITICAL. Un flatten por CB NO se bloquea (aplanar es seguro). WARN ⇒ opera + ntfy en
  TRANSICIÓN (no spam, via `_last_check_severity`). `prev_lev` del último snapshot para el salto.
  Alertas nuevas en `notify.py` (block/warn/recover). Verificado: ciclo DRY_RUN completo, guarda OK,
  audit `checks` registrado, NO falso-bloqueo del caso sano. **PENDIENTE PUSH+DEPLOY (toca loop vivo).**
- **Paso 3 — health-check RUNTIME en heartbeat (F1.2) + REANUDACIÓN RÁPIDA:** `checks.run_heartbeat_checks`
  (salto de equity, recencia de rebalanceo=¿atascado?, huérfanas) corre cada heartbeat (15min); solo AVISA
  (el CB es la red dura), ntfy en transición (categoría `checks_hb`, sin spam ni audit en estado sano).
  **Reanudación rápida:** un ciclo bloqueado/omitido NO consume la ventana (`retry_blocked`) → reintenta
  cada 15min hasta que los datos se reparen (p.ej. backfill), sin esperar 24h. Verificado en DRY_RUN
  (heartbeat limpio; chequeos sintéticos: caída equity/rebal 40h/huérfana → WARN). **PENDIENTE DEPLOY.**
- **Paso 4 — monitor de correlación entre sleeves (F1.5), en la guarda pre-trade:** métrica robusta =
  MEDIA de |corr| entre pares (NO el máximo: con 21 pares y ventana corta el max se sesga alto → falsas
  alarmas; calibrado: full=0.065, p99(180d)=0.27) sobre ventana 180d, WARN si >0.35 (colapso real). Verif:
  real OK (media 0.11), colapso total → WARN. **🐛 BUG cazado y corregido:** `np.fill_diagonal` sobre el
  array read-only de `.corr()` (→ copia escribible) + recalibración del umbral. Barrido de bugs: todo el
  paquete compila/importa/corre; e75 pasa; ciclo DRY_RUN limpio. **PENDIENTE DEPLOY.**
- **SIGUE (Fase 1):** **solo queda paso 5 = reporte profesional templado (F1.4)**, código puro. Tras eso,
  Fase 1 cerrada → Fase 2 (producto/track) cuando la DEMO acumule semanas.

## CHANGELOG 2026-06-02 (noche — RUTA MAESTRA: cambio de fase a Operación→Producto→Escala)
Tras agotar la caza de alfa gratis, Oscar pidió consolidar TODO lo que sí aporta valor en una ruta
ordenada. Evaluadas y respondidas sus preguntas (memoria `kepler-news-ia-bots-decision`):
- **Plan base (noticias/IA/Medallion):** módulo noticias+conviction-override NUNCA se construyó y está
  MUERTO POR DISEÑO (apostaba 100% a 1 nombre → choca con bajo-DD; hoy capamos 15%). IA = "auxiliar, no
  núcleo" (PLAN §9.5): como ALFA no (overfit/alucina), como OPERATIVA sí (anomalías/integridad/reportes).
  Medallion = sin métrica secreta; doctrina ya aplicada (muchas señales uncorr, neutralidad, Deflated Sharpe).
- **Hummingbot / bots:** Hummingbot = market-making/HFT = el juego que rechazamos (e45). Ni estrategia ni
  infra ni negocio nos sirve. Grid/DCA SaaS = primos del martingala. **Negocio real = copy-lead** (Binance/
  Bybit), que ya es la misión → el trabajo es producto/track-record/operación, no un bot.
- **→ ESCRITA `ROADMAP.md` §RUTA MAESTRA 2026-06** (Fase 0 tiempo · Fase 1 robustez operativa ← prioridad ·
  Fase 2 producto/track · Fase 3 escala · Parked pago/intradía · Cerrado). **Es el plan a seguir en orden.**

## CHANGELOG 2026-06-02 (tarde-8 — UNIVERSO LIMPIO barrido LOO (e74) → universo YA limpio, NO retirar)
Barrido LOO sistemático sobre las 20 coins operadas (reúsa e53: turnover + slippage ADV + ancla haircut).
Baseline 20 coins: REAL 3.52%/mes · Sh 1.87 · IS/OOS 2.09/1.69 · maxDD −9.5%.
- Marca 3 "retirables" (mejoran REAL+OOS por single-LOO): LTC +0.40, SOL +0.36, ADA +0.12%/mes.
- **PERO son majors LÍQUIDAS (slippage 1.2-3.5 bps, de las más baratas) y su FLAT Δ es positivo** → no es
  drag de costo, es que las señales no ganaron en ellas in-sample = **curvar el universo al P&L pasado**
  (la trampa que e50 ya advirtió: excluir por retorno pasado empeora OOS en agregado; 19 pruebas → 2-3
  falsos positivos esperables; Δ chicos ≈ ruido deflactado).
- **Confirmación:** las coins de slippage ALTO (ZEC 9.0, TRX 6.0, ATOM 5.8, UNI 5.6) son TODAS MANTENER
  (su edge paga su costo). Por el lado defendible (costo), el universo YA está limpio (e53 retiró las finas).
- **VEREDICTO: NO retirar nada.** Universo ya limpio; quitar líquidas = overfit. Workstream "universo
  limpio" CERRADO (evaluado → sin acción). e74 queda como diagnóstico reusable.

## CHANGELOG 2026-06-02 (tarde-7 — CME gap (e73) DESCARTADO + limpieza de pendientes)
- **CME GAP → DESCARTADO con números (e73).** Fade del gap de fin de semana (BTC, 228 weekends 2022-2026,
  proxy vie-21UTC→dom-22UTC): **pierde en TODOS los horizontes** (12-120h): Sharpe −0.58 a −1.59, ann −22%
  a −32%, win ~50%. La "fill rate" sube 32%→73% con el horizonte pero es trivial (mean-reversion banal, no
  rentable). + choca con β-neutral (BTC-direccional). Rama CME CERRADA. No re-litigar.
- **Limpieza de pendientes:** sacados de la cola CME gap (e73, ✗) y monitor de riesgo intradía e15 (ya
  evaluado/NEGATIVO: DD intradía diminuto, hard-halt=whipsaw; única mejora barata=CB en heartbeat YA
  desplegada). Ruta B intradía: order-book ✗, liquidaciones ✗, CME ✗, e15 ✗ → **solo queda "universo
  limpio" (diario, no intradía)** como workstream barato y vivo.

## CHANGELOG 2026-06-02 (tarde-6 — NETFLOW Dune (e72): pipeline VALIDADO, build cross-chain = decisión)
Key Dune gratis (`data/.dune_key`). Pipeline funcional (`research/dune_util.py`: crear query pública →
ejecutar **perf='free'** ← OJO el bug: 'medium' es inválido en free tier y falla silencioso → leer por
execution_id). Free tier: 0 queries privadas (solo públicas), créditos limitados, ejecuciones lentas.
- **CEX labels (`cex.addresses`) cobertura amplia:** ethereum 4373, polygon, bnb, base, avalanche_c,
  litecoin 1110, bitcoin 761, ripple 377, solana 166, tron 151 → cubre BTC/ETH/BNB/SOL/XRP/AVAX/LTC/TRX
  + ERC-20 (LINK/UNI/AAVE) nativamente. Mejor de lo esperado.
- **Extracción netflow VALIDADA** (e72, LINK ethereum: inflow/outflow diario en millones de tokens,
  netflow ± sano). `erc20_ethereum.evt_Transfer` ⋈ `cex.addresses`. Subset ERC-20 cacheado.
- **CAVEAT DE ALCANCE (decisión Oscar):** netflow per-coin es CROSS-CHAIN → ~8 queries por-cadena
  (bitcoin/litecoin/ripple/tron/solana/bnb/avax + eth), cada una scan multi-año en free tier lento/credit-
  limitado = build de **varias sesiones**. ERC-20 solo = 3 coins (muy fino para rankear). Pregunta: invertir
  sesiones en el build Dune gratis vs **CryptoQuant pago** (~$99/mo, netflow per-token limpio instantáneo).
  Dado que on-chain ya dio 2 ganadores (tx, mvrv) y netflow es la misma familia, evaluar ROI esfuerzo.
- **DECISIÓN OSCAR (2026-06-02): PARAR netflow.** La familia on-chain ya rinde (tx+mvrv en sombra) y
  netflow = más de lo mismo. Pipeline Dune queda montado/reusable (`dune_util.py` + `e72`) por si se
  retoma o se va a CryptoQuant pago. **FOCO ahora: validar lo que hay (sombras → sleeve #8 ~jul-31).**
- **🏁 CIERRE FUENTES GRATIS:** sentiment (Trends frágil / Santiment free 1y+lag) y netflow (Dune cross-chain
  pesado) → explorados. Lo gratis-fácil está AGOTADO. Saltos reales restantes = PAGO (Santiment Pro ~$50/mo,
  CryptoQuant ~$99/mo) o ruta B intradía (CME gap / universo limpio, no necesita fuentes nuevas).

## CHANGELOG 2026-06-02 (tarde-5 — SANTIMENT social (e71) + Flipside MUERTO → Dune para netflow)
Oscar consiguió API key de Santiment (gratis, en `data/.santiment_key`). Probada y funcional (`sanpy`).
- **e71 (chequeo EXPLORATORIO, social_volume + sentiment_balance, 18 monedas):** el social es **muy
  ortogonal** a los 7 (max |corr| 0.04–0.10, < que Trends). Señales débiles que sobreviven taker:
  `sentiment_lvl`(−1)="comprar miedo" (Sh 0.53, taker 0.51) y `socvol_mom_14`(+1)=atención↑→long
  (Sh 0.42, taker 0.39).
- **BLOQUEO del free tier:** solo **~1 año de historia + lag 30 días** → (1) NO se puede validar IS/OOS
  con 1y; (2) el lag de 30d hace la señal viva siempre 1 mes vieja → inservible en producción. El free
  tier sirve solo para confirmar ortogonalidad (✓), no para actuar. **→ Santiment social va a la lista
  PAGADA** (Pro ~$50/mo quita el lag + da historia) junto a CryptoQuant. Memoria `kepler-sentiment-trends-marginal`.
- **FLIPSIDE MUERTO:** vendió su negocio de datos a SonarX; Flipspace se apaga 2026-06-17 → no hay sign-up.
  **Para netflow → Dune** (sigue activo). Pendiente: Oscar registra en Dune (key gratis) → yo escribo el
  SQL de netflow per-token. Flipside descartado como fuente.

## CHANGELOG 2026-06-02 (tarde-4 — SENTIMENT vía Google Trends (e70): edge marginal-real pero FUENTE frágil)
Familia nueva (Oscar): agotar sentiment/social gratis + netflow Dune/Flipside. Hallazgos:
- **Acceso:** lo único gratis+keyless+cross-seccional+con histórico es **Google Trends** (pytrends; ojo bug
  urllib3: NO pasar `retries`). LunarCrush free = sin API/sin social. Santiment free = key (registro Oscar)
  + solo 2y + excluye 30d + 1000 calls/mes. Fear&Greed = market-wide (gate-de-régimen, descartado).
  Netflow Dune/Flipside = key (registro) + SQL cross-chain pesado → NO ejecutable autónomo esta sesión.
- **e70 (chequeo barato, 19 monedas, atención relativa a BTC, 2022-2026 semanal, cache data/trends/):** la
  atención ES **ortogonal** a los 7 (max |corr| 0.18, carry). Factor ganador `attn_pxdiv_4w`(−1) = fade del
  hype (búsqueda sube más que precio→short): **maker Sh 0.54, TAKER Sh 0.46 (+1.12%/mes), IS/OOS 0.52/0.57
  balanceado** → pasa ortogonalidad+taker+IS/OOS (los filtros que mataron a otros). Marginal-real.
- **VEREDICTO: edge real pero NO production-ready por la FUENTE.** (1) Google Trends rate-limita/429 desde
  IPs cloud → una sombra en la VM se rompería (la VM es más bloqueada que local). (2) semanal + lag 1sem
  = lento. (3) best-of-12 variantes, signo post-hoc → falta deflación + LOO. **Camino limpio si se quiere
  sentiment = Santiment (API estable, needs key Oscar) > Trends.** Memoria `kepler-sentiment-trends-marginal`.
  PENDIENTE (si Oscar lo prioriza): LOO + deflación; o evaluar Santiment/Dune con keys que cree Oscar.

## CHANGELOG 2026-06-02 (tarde-3 — cap de concentración combinado (e69) + fix telemetría slippage)
Dos cierres pedidos por Oscar tras el incidente:
- **CAP DE CONCENTRACIÓN COMBINADO (e69):** el cap 0.25 de e52 es POR-SLEEVE; tras combinar+leverage un
  nombre apila de varios sleeves (TRX 23% del equity vía trend+carry+lowvol). Nuevo `config.MAX_POSITION_EQUITY
  = 0.15`: recorta el target final para que **ningún nombre supere 15% del equity**. Conservador por
  construcción (el leverage se ancla sobre el libro SIN capar → recortar solo baja riesgo). e69 (marcado
  diario consistente) confirma que capar el peso combinado es **neutral en Sharpe/maxDD/retorno** (maxDD
  anclado; OOS hasta mejora) → regla de oro ✓. Implementado en `engine.compute_target` (clip post-leverage).
  Verificado: engine métricas idénticas (Sh 2.20, maxDD −9.5%); el clip muerde (prueba cap 0.10 → top=0.10).
  En la VM hoy recortará TRX 23→15, NEAR 19→15, BTC 17→15 (top-5 82%→~68%). Caveat honesto: e69 corre a
  leverage más bajo que el engine (retornos diarios más ruidosos) → no dimensiona el 23% vivo, pero la
  conclusión RELATIVA (cap = neutral) es sólida. **PENDIENTE PUSH+DEPLOY.**
- **FIX TELEMETRÍA SLIPPAGE (C3):** el `slip_bps` se mide vs `book_mid`; cuando el mid viene stale (ZEC: ref
  621 vs fill 575 = −742bps) ensuciaba la MEDIA del reporte (−15.94 vs mediana real 2.72). Nuevo
  `SLIP_SANITY_BPS=200`: al calcular, |slip|>2% = ref corrupto → se descarta (no entra a la DB); al agregar,
  se excluye del reporte (`ABS(slip_bps)<=200`). Simulado sobre hoy: media **−15.94 → 3.71bps** (= mediana).
  **PENDIENTE PUSH+DEPLOY.**

## CHANGELOG 2026-06-02 (tarde-2 — 🔴 INCIDENTE: VM sobre-apalancada 2.93x → ancla robusta (e68))
**Oscar reportó caídas fuertes** (1 día +0.09, 2 rojos, hoy −1.52%). Análisis del log diario (DEMO):
- **CAUSA RAÍZ:** la VM corría a **2.929x** (log: `"leverage": 2.929`, TRX 23%) vs **2.16x de diseño**
  (motor local, mismo código). Diferencia = la **VENTANA DE DATOS**: el motor local ve 2022-03→ (peor
  maxDD −4.50% el 2022-04-18) → 2.16x; la VM arranca **~2023** (sin la caída de abril-2022) → maxDD a 1x
  ~−3.2% → el `leverage_for_maxdd_anchor` cree que puede apalancar más → **3.06x**. `HIST_START_MONTH=2022-01`
  es correcto; la VM **no tenía el backfill completo**. El sobre-leverage (~+36%) amplificó el tilt
  net-long (β-dólar +0.45) en un mercado a la baja (BTC −1.3% hoy) y consume el presupuesto −10% un 36%
  más rápido. **NO era estrategia rota.** Memoria `kepler-anchor-window-overleverage`.
- **Hallazgos 2º:** concentración alta (TRX 23%/NEAR 19%/BTC 17%; el cap 0.25 aplica a `trend` pero
  carry+lowvol también cargan TRX → combinado 23%); slippage telemetría contaminada por 1 trade ZEC
  −742bps (ref_px stale; real = mediana 2.72bps, OK); 4 ciclos hoy = reinicios por deploys (churn extra).
- **FIX INMEDIATO (Oscar en VM):** `python -m kepler.fetch 1h` (backfill 2022+) → `python -m kepler.engine
  ESTABLE` debe dar ~2.16x.
- **FIX DE FONDO — ANCLA ROBUSTA (e68, backtest ✓, regla de oro):** `leverage_robust = min(maxdd_anchor,
  HAIRCUT·TARGET_VOL_ANCHOR/vol)`. La vol es estable entre ventanas → ancla el lev aunque falte historia.
  e68: status quo da maxDD real −13%/−16% con ventana corta; el híbrido lo mantiene **≤9.5% en TODAS las
  ventanas** y **mismo retorno con historia completa** (2.16x · 4.47%/mes · Sharpe 2.20). Implementado:
  `config.TARGET_VOL_ANCHOR=0.205` + `portfolio.leverage_robust` + `engine.compute_target`. Verificado
  (2.158x full; 6.5–9.2% maxDD real en ventanas cortas).
- ✅ **DESPLEGADO Y VERIFICADO EN VM (2026-06-02 ~18:30 UTC):** deploy OK + backfill forzado del histórico
  2022 (`download_klines force=True`, 38.712 velas/símbolo). **Leverage vivo 2.93x → 2.23x.** Diagnóstico
  clave: con datos completos el **maxDD-anchor sigue dando 3.083x** (el peor drawdown del combinado es
  genuinamente suave, −3.31% a 1x) → **es el vol-anchor (2.35) el que ata** → el fix de código era
  IMPRESCINDIBLE (solo backfill habría dejado 2.93x). maxDD real esperado a 2.23x ≈ **−7.4%** (cómodo
  bajo −10%). Funding fresco (carry OK). El `port` combinado termina ~Feb-21 = horizonte de retorno
  forward del sleeve rev_60d (NO bug, sin look-ahead; los pesos vivos sí usan datos de hoy).
  Memorias: `kepler-anchor-window-overleverage`, `oscar-vm-one-line-commands`.

## CHANGELOG 2026-06-02 (tarde — CIERRE barrido on-chain: fees+issuance ✗ → familia AGOTADA, 2 ganadores)
`research/e67_fees_supply.py`. Últimas métricas community: **issuance** (−Δlog supply = inflación) corr
−0.63 con momentum (anti-mom) + IS/OOS inestable (1.39/−0.63) → ✗. **fees** (fee_pxdiv/fee_mom) solapan
con actividad (tx) y lowvol, standalone ~0 → ✗. **NINGUNO pasa.**
- **🏁 BARRIDO COIN METRICS / ON-CHAIN AGOTADO.** Balance de la familia: **2 GANADORES** (`tx_pxdiv_14d`
  actividad + `mvrv_lvl` valor, ortogonales entre sí, ambos en SOMBRA). Descartados: addr variants, netflow
  (BTC/ETH-only), MVRV mom/z, size, fees, issuance. **La familia on-chain rindió 2 edges** — la mejor de
  todas (derivados/Coinalyze = 0). Confirma: el edge ortogonal vive en FUNDAMENTALES on-chain, no en precio
  ni posicionamiento. Próxima familia de datos (siguiente sesión): sentiment/social o netflow vía Dune (BTC/ETH-only en CM).

## CHANGELOG 2026-06-02 (tarde — COIN METRICS ampliado: `mvrv_lvl` PASA → 2ª sombra on-chain 🎯)
Barrido del catálogo Coin Metrics community (e65/e66). 31 métricas; las fundamentales nuevas:
- **Netflow de exchanges** (`FlowInExUSD/FlowOutExUSD`) — el netflow que creíamos de pago (CryptoQuant)
  está GRATIS… pero **SOLO BTC/ETH** community-free → NO cross-seccional (muro market-wide) → ✗ muerto.
  Igual `SplyExNtv` (exchange supply). Honesto: la cobertura mata el lead más emocionante.
- **GANADOR: `mvrv_lvl`** (short high MVRV = market cap / realized cap; long infravalorado). Factor de
  VALOR on-chain. Pasa TODO (e66): corr 0.28 (mom) / **+0.02 con tx_pxdiv** (¡ortogonales entre sí!),
  IS/OOS 0.69/0.80, **turnover 6x/año → inmune al taker** (Δ +1.41%/mes maker=taker), **LOO robusto**
  (sin ZEC aún +1.08, NO 1-coin). point-in-time limpio (realized cap = historia inmutable). 11 coins.
- Descartados: mvrv_mom/mvrv_z (corr alta con mom/hlpos), size (corr 0.66 mom; reconfirma e35).
- **IMPLEMENTADA SOMBRA `onchain_mvrv_lvl`** (`onchain.py` + orchestrator): update_cm_fundamentals +
  mvrv_shadow_weights + run_mvrv_shadow. Verificado: 12 posiciones β-neutral (short ZEC/ETH, long UNI/ADA).
  **PENDIENTE DEPLOY.** Ahora **4 sombras** (TVL, BLEND, tx_pxdiv, mvrv_lvl) → reloj forward.
- **DOS edges on-chain ortogonales:** tx_pxdiv (ACTIVIDAD) + mvrv_lvl (VALOR), corr +0.02 → la doctrina de
  muchas señales chicas materializándose. La familia on-chain SIGUE produciendo (≠ derivados, agotada).

## CHANGELOG 2026-06-02 (tarde — COINALYZE Tier 2: predicted-funding + OI → NEGATIVO (familia agotada))
Inventario API (e62) + harness (e63) + estrés (e64). Coinalyze diario cross-exchange (2020→hoy): predicted
funding, funding, OI, L/S — todos OHLC, histórico completo. **NO hay endpoint de basis** → ese ángulo (e22)
no es testeable vía API (sería funding≈carry).
- **Predicted funding: SIN edge nuevo.** Como señal de precio (short high pred-funding) Sh 0.07, corr 0.28
  con carry, Δ −1.66. Conceptualmente ≈ funding realizado → no aporta sobre el carry. (Usarlo como "mejor
  carry" exigiría swap del ranking en `carry_sleeve` con funding cobrado; el diagnóstico no lo justifica.)
- **OI (flujo de posicionamiento, ≠ ratio L/S de e16f): redundante o frágil.** 18 variantes (oi_pxdiv/
  oi_mom/oi_dir × {7,14,30d} × signo): casi todas corr alta (hlpos/mom/rev) o IS/OOS con saltos de signo
  (inestable). Único superviviente del filtro: `oi_dir_7d(+)` (OI confirmando momentum) — sobrevive taker
  (Δ +0.60) PERO **LOO: depende de ZEC** (sin ZEC Δ→−0.33). Mismo patrón que liquidaciones (1-coin/ZEC) → ✗.
- **VEREDICTO: Coinalyze Tier 2 NEGATIVO.** La familia DERIVADOS/POSICIONAMIENTO está ya agotada a fondo:
  L/S ratio (e16f) ✗, liquidaciones (e46-49, ZEC) ✗, OI-delta/dir (e63/64, ZEC) ✗, predicted-funding (≈carry)
  ✗, basis (n/a). **Contraste claro:** el edge ortogonal nuevo vino de ON-CHAIN (tx_pxdiv, fundamental), NO
  de posicionamiento (que solapa con momentum/crowding o se concentra en ZEC). ZEC = el 1-coin espurio recurrente.

## CHANGELOG 2026-06-02 (tarde — SOMBRA `tx_pxdiv_14d` IMPLEMENTADA → lista para deploy)
Decisión de Oscar: poner YA en sombra todo lo validado (el reloj forward corre desde el deploy → antes
validamos → antes a real/copytrading, el objetivo). `kepler/onchain.py` + `orchestrator.py`:
- **`update_cm_addresses()`** (fetcher Coin Metrics Community, sin key, 13 coins AdrActCnt+TxCnt, overwrite),
  **`tx_shadow_weights()`** (pesos β-neutral de tx_pxdiv_14d), **`run_tx_shadow()`** (loguea `shadow_signal`
  sleeve=`onchain_tx_pxdiv_14d`), cableado al ciclo (junto a las sombras TVL y BLEND). NO opera.
- Verificado end-to-end: 13 posiciones β-neutral (long DOGE/BCH, short UNI/ZEC, hedge BTC +0.26), fetcher
  13/13, loguea 13. **PENDIENTE DEPLOY.** Tras desplegar → reloj 60-90d → `e33`-style → promover a sleeve #8.
- **3 sombras corriendo tras deploy:** TVL (`onchain_tvl_pxdiv_14d`), BLEND (`blend_lottery_tvl_illiq_v1`),
  TX (`onchain_tx_pxdiv_14d`, el más fuerte). Todas no-operativas (validación forward).

## CHANGELOG 2026-06-02 (tarde — ON-CHAIN: `tx_pxdiv_14d` ORTOGONAL al blend → cierra el lazo 🎯)
`research/e61_onchain_vs_blend.py`. ¿tx_pxdiv solapa con el TVL (ambos on-chain) o es nuevo?
- **corr(tx_pxdiv, TVL) = +0.09** → ORTOGONAL pese a ser ambos on-chain (tx = actividad transaccional ≠
  TVL = valor bloqueado). corr con lotería −0.01, iliquidez +0.18, blend +0.15. Genuinamente nuevo.
- **Añadir al blend mejora todo** (modesto, doctrina de muchas señales): 3-comp Sharpe 0.98 (OOS 0.97)
  → **4-comp +tx Sharpe 1.01 (OOS 1.00), maxDD −12.4→−11.8%**. NO reemplaza al TVL (complementarios;
  tx-en-lugar-de-TVL cae a 0.66). 
- **CLAVE estratégica:** contra el blend débil tx aporta poco (+0.03), pero contra los **7 sleeves
  principales dio +1.46%/mes** (e60) → **tx_pxdiv es más fuerte como sleeve #8 DIRECTO que como componente
  del blend.** Candidato más sólido desde taker_flow/hlpos.
- **SIGUIENTE:** llevar `tx_pxdiv_14d` a SOMBRA (forward, como TVL/blend; añadir a `onchain.run_shadow`) →
  acumular 60-90d → decidir promoción a sleeve #8 (directo) vs sumarlo al blend. Caveat: 12 coins = techo.
  NADA en prod aún (la sombra es no-operativa).

## CHANGELOG 2026-06-02 (tarde — TIER 1 ON-CHAIN: factor `tx_pxdiv_14d` PASA el harness completo 🎯)
Backtest del factor on-chain (`e59` construcción + harness, `e60` estrés taker + LOO) sobre las 12 coins
operables (Coin Metrics, e58). Probé addr_pxdiv / tx_pxdiv / addr_mom × {7,14,30d}, lag point-in-time 2d.
- **GANADOR: `tx_pxdiv_14d`** (Δlog tx-count − retorno, 14d). Pasa TODO: corr **−0.10** con los 7 sleeves
  (ortogonal), IS/OOS **0.33/0.50** (balanceado), vivo 2022+ (**+1.18%/mes**, no backfill), standalone taker
  **+0.99%/mes**, **Δ combinado taker +1.46%/mes** (sobrevive), **LOO robusto** (sin TRX aún +0.85; mediana
  +1.26 → NO depende de 1 coin). Pasa los filtros que tumbaron liquidaciones (ZEC/1-coin) y order-book
  (muere a taker). **Más fuerte que el TVL** (+1.46 vs +0.6%/mes). Primer candidato ortogonal real del Tier 1.
- **`addr_mom_30d`** (secundario): sobrevive taker (+1.00) y LOO, PERO corr 0.32 con momentum + IS/OOS
  desbalanceado (0.11/1.30, sesgo reciente) → probable proxy de momentum con tilt de régimen. Cautela.
- **Resto descartado:** addr_pxdiv (corr alta con hlpos o mom; sólo el 14d marginal), tx_pxdiv_7d/30d (muere).
- **Caveat honesto:** cross-section delgado (12 coins) = techo de breadth/capacidad. Falta verificar
  ortogonalidad vs los componentes del BLEND #8 (lotería+TVL+iliquidez) — el TVL también es on-chain, puede
  solapar. **SIGUIENTE:** (1) corr de `tx_pxdiv_14d` vs TVL/lotería/iliquidez; si ortogonal → (2) añadir al
  blend, re-validar, y a SOMBRA (forward, como el TVL). NADA en prod aún.

## CHANGELOG 2026-06-02 (tarde — TIER 1 ON-CHAIN: inventario + ingesta Coin Metrics (gratis))
Tras el Tier 3 negativo (edge nuevo = dato nuevo), arranque del Tier 1: actividad de direcciones on-chain
(el factor zoo lo lista entre los top ortogonales). `research/e58_onchain_addresses.py`.
- **Coin Metrics Community API** (`community-api.coinmetrics.io/v4`, **GRATIS sin key**): `AdrActCnt`
  (direcciones activas) + `TxCnt` community-free. `AdrNewCnt`/valor-transferido NO son community.
- **Inventario:** 15/29 coins con dato; **2 STALE descartadas** (bnb cortado 2019-04 = viejo ERC-20;
  dot 2022-06) → **13 usables** (aave,ada,bch,btc,doge,etc,eth,link,ltc,trx,uni,xrp,zec), histórico
  2016-2020→2026-06-01 (fresco). Cross-section delgado (13, como TVL 12) pero viable.
- **Ventaja point-in-time:** las direcciones se computan de la cadena INMUTABLE → no se revisan (≠ backfill
  de TVL) = dato más honesto. **Ingesta hecha** (44k filas en `data/onchain_cm/`, no trackeado).
- **SIGUIENTE:** construir `addr_pxdiv` (Δlog actividad − retorno, análogo al TVL que dio +0.6%/mes) +
  variantes (tx-count, addr-momentum) → harness brutal (corr<0.35, IS/OOS purgado, ancla, **taker**) +
  ataque point-in-time → si pasa, candidato al **blend #8**. (Aún NADA en prod.)

## CHANGELOG 2026-06-02 (tarde — barrido de recetas de factores: Tier 3 (data propia) → todo redundante)
Tras el barrido web (factor zoo cripto + GitHub + Coinalyze), Oscar dio luz verde a probar los factores
computables con NUESTRA data (`research/e57_tier3_factors.py`), por el harness brutal (corr<0.35 + IS/OOS):
- **turnover-volatility** (vol del log-volumen): corr **0.48 con hlpos** → ya lo captura el sleeve de
  posición-en-canal; además signo inestable IS/OOS. ✗
- **low-price (nominal)**: standalone ~0, no generaliza OOS (0.28/0.01) → proxy estático de size. ✗
- **residual-momentum** (ret − β·retBTC): standalone bueno (Sh 0.81) PERO **corr 0.98 con mom_30d** →
  ES nuestro momentum. CONFIRMA que la β-neutralización ya residualiza el momentum (operamos el
  idiosincrático). ✗ como sleeve nuevo (pero buena señal de que el motor está bien construido).
- **VEREDICTO:** los 7 sleeves YA cubren el espacio de factores precio/volumen (consistente con el factor
  zoo: 2-3 factores capturan la sección cruzada). El edge nuevo exige **DATO NUEVO** → siguiente = **Tier 1
  on-chain (new-address-to-price, Coin Metrics Community gratis)** + Coinalyze (predicted funding, basis).

## CHANGELOG 2026-06-02 (mañana — SESIÓN RIESGO/CALIDAD: D0 + D1 + concentración TRX + monedas finas)
Oscar pidió cerrar D0 y D1 (riesgos prioritarios de MONITOREO §4), luego concentración TRX, luego finas.
Resultado: libro más limpio/barato/menos concentrado y mejor número honesto. **Config final: haircut 0.95,
trend cap 0.25, universo −{XLM,HBAR,LIT}.** (Las 4 piezas interactúan vía el ancla — leer las 4 secciones.)

### EJECUCIÓN — timing del rebalanceo diario (`research/e54_rebalance_timing.py`) → pinear a 14 UTC
Arranque de la frontera intradía por la ruta CORRECTA para Kepler (bajar COSTE, no buscar alfa: el alfa
intradía direccional muere en coste×turnover, probado e19/e24/e45). e54 mide el perfil de liquidez por
hora-del-día del universo (quote_volume de 1h klines; el modelo de coste es slip~K/√volumen):
- **La liquidez sigue el reloj US/EU:** pico **14-16 UTC** (09-11h Lima, 1.5× la media), zonas muertas
  21-23 y 03-05 UTC (~0.78×). Fines de semana finos (Sáb 0.77/Dom 0.81; el rebal diario no los evita).
- **Fijar el rebalanceo a las 14 UTC ahorra ~21% del slippage** vs la deriva actual (~29% vs la peor hora)
  = **~0.13%/mes recuperado, GRATIS** (sin turnover, sin β). Hoy el orquestador rebalancea a la deriva
  (la hora del último deploy) → si cayó en zona muerta paga lo peor.
- **Implementado:** `config.REBALANCE_HOUR_UTC=14` + disparo pineado en `orchestrator.run` (rebalancea en
  esa hora UTC tras MIN_REBAL_HOURS=18, fallback MAX=30h; None=comportamiento viejo). Verificado (7/7
  escenarios del disparo). **PENDIENTE DEPLOY** (cambia CUÁNDO se rebalancea; validar slip real en DEMO).
- **Slicing pasivo (e55) → DIFERIDO a capacidad.** Cuantificado: a tamaño DEMO la participación es ~0.00%
  → impacto nulo, maker llena a mid → slicing NO ahorra nada hoy. Es feature de CAPACIDAD: importa ~$1M+
  AUM en coins finos, crítico >$10M (cruce ~$4.6M para pos 5% en ZEC). NO implementar ahora; revisar al
  escalar AUM con cap de tamaño por liquidez (roadmap B4). El pineo de hora ya captura el win gratis.
- **Monitor de riesgo intradía (e15) → EVALUADO, resultado NEGATIVO útil** (`research/e15_intraday_risk.py`):
  reconstruí el libro diario real (pesos agregados 7 sleeves, MTM horario) y medí el DD INTRADÍA: es
  diminuto (peor −3.3% en 4 años; 99% de bloques >−1.6%; β≈0 como se esperaba) y **mayormente revierte**.
  **Un hard-halt intradía es WHIPSAW** a cualquier umbral útil (−4% baja ann +12.8→−1.3% sin casi mejorar
  el maxDD); el maxDD se forma en DÍAS (dispersión cross-seccional), no en spikes intradía → un halt rápido
  no lo ataca. **CONCLUSIÓN: el CB diario basta; NO añadir halt intradía.** ÚNICA mejora barata: chequear el
  CB ANCHO existente (−20%) en el heartbeat (15min) — hoy solo se evalúa en el ciclo 24h — = rail de
  catástrofe ~24h más rápido a coste histórico CERO (nunca dispara con ruido). Pendiente de tu OK para implementar.
  - Nota honesta → **RESUELTA (e56):** el Sharpe ~1.3 de e15 era artefacto de SOBRE-rebalanceo (re-formaba
    el target a diario, lo que el libro vivo NO hace). Marcando a diario pero MANTENIENDO sobre el bloque
    (e42), el combinado honesto da **Sharpe 2.34 ≥ motor 2.20** → **el 2.07 NO está inflado.** Matiz fino:
    el marcado diario da maxDD-a-1x un pelín peor (−5.1 vs −4.5) → el motor sub-apalanca... perdón, el ancla
    apalancaría de más (2.27 vs 1.98x) = exactamente el sobre-apalancamiento que **valida el haircut 0.95 (D0).**


### MONEDAS FINAS — retirar del universo global (`research/e53_thin_coins.py`) → −{XLM,HBAR,LIT}, ZEC se queda
Reúsa la maquinaria de e18 (turnover por-símbolo + slippage ADV K50) con el trend capado + haircut. Mide,
bajo coste FLAT (solo edge) y REALISTA (edge−slip), el Δ%/mes de quitar cada fina:
| quitar | FLAT Δ | REAL Δ | REAL %/mes | Sharpe | IS/OOS |
|---|---|---|---|---|---|
| baseline (23) | — | — | 2.24% | 1.67 | 1.85/1.57 |
| −ZEC | −0.34 | −0.28 | 1.96% | 1.35 | 1.87/**1.07** |
| −XLM,HBAR,LIT | +0.93 | +0.72 | **2.96%** | 1.80 | 2.09/1.56 |
| −GRUPO(4) | −0.26 | −0.15 | 2.09% | 1.75 | 2.15/1.25 |
- **VEREDICTO: retirar el grupo de 4 sería ERROR — ZEC tiene edge** (quitarla daña, OOS 1.57→1.07; es
  también el edge de liquidaciones e48). LIT es lastre puro (FLAT +0.85 = pierde sin slippage) + peor
  ejecución (12.9bps); XLM/HBAR ~nulos + slippage alto. **Retirar {XLM,HBAR,LIT}, conservar ZEC** sube el
  neto realista 2.24→2.96%/mes (Sh 1.67→1.80) **sin empeorar OOS** (1.57→1.56). Honesto: el salto es
  mayormente IS (OOS plano); la ganancia CIERTA = libro limpio + menos drag de slippage, cero downside OOS.
- **DECISIÓN DE OSCAR: retirar XLM/HBAR/LIT** de `config.UNIVERSE` (29 global / 20 largo). Verificado en vivo.
- **⚡ EFECTO COLATERAL CLAVE (re-corrido e51 sobre el libro limpio):** el maxDD OOS del walk-forward cayó
  **−13.5%→−7.1%** — e52+e53 **arreglaron el sobre-apalancamiento de D0 de raíz** (las finas causaban
  drawdowns de cola en folds tempranos). El haircut 0.85 quedó sobre-conservador → **Oscar lo relajó a 0.95**
  (lev vivo ~2.16x, recupera retorno, deja cojín; maxDD IS −9.5% = diseño 0.95×10%). El −10% se respeta.

### CONCENTRACIÓN TRX — cap por-activo en `trend` (`research/e52_trend_concentration_cap.py`) → cap 0.25
Diagnóstico: la top del libro (TRX ~20% del equity) es **78% `trend`** (long-only vol-target → vuelca ~47%
de su gross en la coin de menor vol en tendencia). e52 prueba el cap recombinando el sistema (vol-parity +
ancla con haircut) y midiendo el combinado + el `top_position` resultante. El cap normaliza la cesta de
trend a gross 1 y capa cada coin (consistente backtest↔live):
| variante | Sharpe comb (IS/OOS) | %/mes | maxDD | top TRX | HHI |
|---|---|---|---|---|---|
| producción (sin cap) | 2.07 (1.94/2.21) | 3.38% | −8.6% | **19.5%** | 0.124 |
| **cap 0.25 (elegido)** | **2.06 (1.83/2.28)** | **3.30%** | −8.6% | **9.6%** | 0.082 |
- **VEREDICTO: mejora el RIESGO a coste ~nulo** (regla de oro ✓). Concentración de un nombre **a la mitad**
  (TRX 20%→9.6%, HHI −34%), Sharpe combinado intacto (~2.07), maxDD idéntico (−8.6, lo clava el ancla),
  %/mes −1%/año. Además **equilibra IS/OOS** (OOS 2.21→2.28) = más robusto, no overfit. Es exactamente la
  misión copy-lead de bajo-DD (menos riesgo idiosincrático).
- **DECISIÓN DE OSCAR: cap 0.25** = el mismo `config.MAX_WEIGHT_NORMAL` que ya usan xs/carry → tope por-activo
  UNIFICADO en todo el sistema. Implementado en `engine.trend_sleeve` (cesta normalizada + `_cap_normalize`
  water-filling). Verificado en vivo: TRX 0.195→**0.096**, lev 1.59x, 3.30%/mes, maxDD −8.6%. **PENDIENTE DEPLOY.**



### D0 — CALIBRACIÓN ROBUSTA DEL ANCLA (`research/e51_leverage_robust.py`) → haircut 0.85
e29 halló que fijar el leverage con el maxDD PASADO sobre-apalanca: walk-forward maxDD OOS −13.5% vs
−10% objetivo (rompería la promesa de bajo-DD). e51 reúsa los 7 sleeves + el mismo walk-forward purgado
y mide el tradeoff de cerrar el gap (Sharpe/edge es invariante; lo que cambia es lev → maxDD y %/mes):
| haircut | lev vivo | %/mes vivo | maxDD OOS |
|---|---|---|---|
| 1.00 (antes) | 2.02x | ~4.1% | **−13.5%** |
| **0.85 (elegido)** | **1.72x** | **~3.4%** | **−11.5%** |
| 0.75 | 1.52x | ~3.1% | −10.2% |
- **Política "peor-tramo" DESCARTADA:** da lev MAYOR (las ventanas tienen menos DD que el global) → empuja
  al lado equivocado. El haircut plano es el más transparente para copy-lead.
- **DECISIÓN DE OSCAR: haircut 0.85** inicialmente (sobre el libro sucio) → **RE-AJUSTADO a 0.95** al final
  de la sesión: e52+e53 limpiaron el libro y el maxDD OOS bajó −13.5%→−7.1% (ver sección monedas finas) →
  el 0.85 quedó sobre-conservador. `config.LEVERAGE_HAIRCUT=0.95` (default 1.0=statu quo).
- **Implementado:** `engine.compute_target` aplica `LEVERAGE_HAIRCUT × leverage_for_maxdd_anchor`.
  Verificado en la config final: lev vivo ~2.16x, maxDD IS −9.5% (diseño 0.95×10%). **PENDIENTE DEPLOY.**

### D1 — β REAL DEL LIBRO EN VIVO (`engine` + `orchestrator`) → ya no se hardcodea 0.0
Al destripar el cálculo: hay **dos β distintas**. (a) **β de REGRESIÓN** (combinado vs BTC) = **+0.025** =
la neutralidad real (confirma el ≈+0.05 validado). (b) **β-DÓLAR** (Σwβ) = +0.45, exposición direccional
del notional **dominada por `trend`** (long-only sin hedge; los 5 xs están Σwβ≈0, carry +0.04). Reportar la
β-dólar como "la β del libro" habría sido alarmante y falso → se reporta la de REGRESIÓN.
- **`engine.compute_target`** devuelve ahora 9-tupla (+`beta.iloc[-1]` por-símbolo, +`beta_model` regresión).
  Callers actualizados (orchestrator/engine.main/execution.main/report.py).
- **Snapshot:** `beta` = β de regresión **realizada** de la equity en vivo (≥20 días; `_beta_realized`,
  regresa retornos diarios de `equity_daily` sobre BTC diario en tz Lima) y si no, la **modelo** (+0.025).
  `detail.beta_dollar` = diagnóstico Σwβ de las posiciones REALES (en DRY_RUN, del target). Todo blindado.
- Verificado: 9-tupla OK, β-dólar real con posiciones sintéticas −0.09 (sensata), realizada None<20d→cae a
  modelo, imports OK, sin cambio de comportamiento del trading. **PENDIENTE DEPLOY** (solo telemetría).

## CHANGELOG 2026-06-01 (noche-2 — FIX sombra TVL (ffill) → ⚠️ ÚNICO cambio de prod pendiente de deploy)
Al verificar deploy-readiness cacé un bug en la sombra: la TVL standalone logueaba **0** (antes 13)
mientras el BLEND daba 23. Causa: `onchain._to_hourly` reindexaba el TVL diario **sin ffill**; DefiLlama
publica con 1-2 días de retraso → cuando el panel de precios `C` es más fresco que el TVL, las últimas
filas quedaban NaN → score NaN → pesos 0 → sombra 0. El blend lo enmascaraba (lo cargan lotería+iliquidez),
pero su componente TVL también se anulaba esos días → **afectaba la fidelidad de la sombra que valida en 60d**.
- **FIX (1 línea):** `_to_hourly` reindexar con `method="ffill"` (usar el último TVL conocido; el shift(1)
  ya evita look-ahead = point-in-time correcto). Verificado: TVL 0→**13**, BLEND 23, ciclo orquestador
  DRY_RUN limpio. **Solo toca la ruta de SOMBRA** (no el trading; engine.compute_target no usa onchain).
- ⚠️ **ESTE es el único cambio de PRODUCCIÓN de la sesión** (`kepler/onchain.py`) → **pendiente de deploy
  (Oscar)**. El resto de la sesión fue research/docs. Confirmar antes de desplegar (regla).

## CHANGELOG 2026-06-01 (noche — RUTA B intradía: LIQUIDACIONES descartadas (edge=ZEC) + REGLA universo por-sleeve)
Arranque de la ruta B (intradía). #1 = liquidaciones (Coinalyze, gratis con API key en `data/.coinalyze_key`).
- **Intradía bloqueado por dato** (e46): Coinalyze guarda solo 1500-2000 puntos rodantes a <12h → ~2-3
  meses a 1h, nunca multi-año. Para intradía real = colector hacia adelante (meses). Confirma INTRADAY.md §2.2.
- **Diario gratis y completo** (e46: 32/32, 2023→hoy, `data/liquidations_daily/`). Probado como sleeve
  cross-seccional (e47): `liq_imb_3d` = media_3d((long−short)/(suma)), signo −1 (momentum; el rebote
  contrarian es intradía). Parecía bueno: Sharpe 1.11, corr **0.11** (ortogonal), **+1.05%/mes** maker,
  y **sobrevive taker** (≠ order-book).
- **DESCARTADO — el edge ES ZEC (1 coin fino)** (e48/e49). LOO: sin ZEC 1.05→0.11. Por mitades full
  −0.59 IS / +2.00 OOS (todo reciente); sin ZEC −0.83/−0.16; de-dragged sin ZEC **+0.01 (OOS −1.16)**.
  Edge de 1 nombre ≠ sleeve (precedente e17/AXS). No entra a prod. Memoria `kepler-liquidations-descartado`.
- ⚠️ **Artefacto cazado (e48):** a taker+ADV el Δ/Sharpe SUBÍAN → el coste recorta colas de liquidación
  extrema, baja maxDD, el ancla sube leverage. NO es mejora real (gate limpio = maker). Patrón de e28.
- 🟢 **REGLA NUEVA de Oscar → memoria `kepler-per-sleeve-universe-rule` (molde e49):** si un sleeve es
  bueno pero depende/falla por 1 moneda, diagnosticar contribución POR coin y usar **universo por-sleeve**
  (excluir estorbadores con selección-IS/validación-OOS; rechazar lo que dependa de 1 coin). Validada:
  de-draggear liq_imb_3d pasó −0.59/+2.00 → **+1.91/+1.47** (equilibrado entre mitades) = mejora REAL de
  robustez. Aquí no rescató liquidaciones (lo que quedaba era ZEC) pero **como técnica general es sólida**.
- ✅ **REGLA aplicada a los 7 oficiales (e50) → NINGÚN cambio necesario.** Con disciplina IS→OOS (selección
  de estorbadores en IS, validación en OOS; métrica Sharpe combinado anti-artefacto + %/mes anclado):
  excluir coins EMPEORA el OOS en todos (mom ΔOOS −1.35%/mes, rev −2.67; lowvol/takerflow/hlpos marginal y
  MIXTO = ruido). **Los 7 sleeves YA usan bien todas las monedas** (los "estorbadores" de IS no generalizan).
  Respuesta a Oscar (¿deben estar todas?): **SÍ para los 7 oficiales.** Doble validación: la regla rescató
  liquidaciones-de-dragged (+1.91/+1.47 IS/OOS) y RECHAZA aquí → su disciplina IS→OOS funciona. carry/trend
  no cubiertos (universo interno funding/EMA; refactor pendiente si se quisiera). Idea abierta de Oscar:
  RETIRAR monedas del universo GLOBAL (ampliar ya se descartó, e17) sigue menos explorado.
- Archivos: `research/e46_download_liquidations.py` (downloader Coinalyze), `e47_liquidations_check.py`
  (chequeo barato), `e48_liquidations_stress.py` (taker/concentración/horizonte), `e49_liquidations_universe.py`
  (regla universo por-sleeve). Datos en `data/liquidations_daily/` (no trackeado).

## CHANGELOG 2026-06-01 (tarde-3 — FASE 2 INTRADÍA order-book: edge REAL pero COSTE manda → DESCARTADO)
`research/e45_intraday_orderbook.py`. Primera aplicación real del backtester horario (e42) + motor de
coste (e44): imbalance NATIVO 30s (e43) → horario → score=±imb → `eval_intraday` a holds {1,2,4,6,12,24}h
con `cost_vector('taker_adv')`. Ventana overlap 2023+ (bookDepth no existe antes; cobertura 96-100%/año,
23 símbolos de historia larga). Probé **ambos signos** (contrarian −imb y momentum +imb) y 3 bandas
(imb1/imb2/imb5). Caché del panel horario en `data/bookdepth_30s/_hourly_{band}.parquet` (reusable).
- **VEREDICTO: NO hay sleeve intradía de order-book operable. DESCARTADO.** A coste real (taker+ADV,
  mediana **8.6 bps**) **TODAS** las celdas (banda × signo × hold) son **negativas**. Mejor = imb2
  contrarian 24h → **Sharpe −0.89 · −0.24%/mes** anclado; walk-forward **IS −1.03 / OOS −0.82**, los 4
  cuartiles negativos (−1.58/−0.66/−0.41/−1.23) → perdedor ROBUSTO, no ruido.
- **El muro es el COSTE × turnover, no la señal.** Turnover explota al acortar el hold: 24h→360x,
  1h→4313x. Drag maker (1.8bps) ya es ~78%/año a 1h; taker+ADV (~4.8× maker) ~370%/año. Monótono:
  cuanto más corto el hold (donde vive el edge de microestructura), más brutal el coste. = tesis
  `INTRADAY.md §1` + e19 (coste domina holds cortos) + e24 (+0.00 al ancla a diario).
- **Signo (matiz honesto):** el ÚNICO Sharpe maker positivo es **contrarian a 24h** (imb2 +0.52 /
  +0.42%/mes maker) = básicamente el caso DIARIO ya rechazado (e24). A holds cortos el coste maker ya
  domina → ambos signos negativos incluso a maker (no se distingue el signo bruto). No hay momentum
  intradía explotable. El Sharpe 7-9 de e23 era estructura CONTEMPORÁNEA (look-ahead), no operable —
  confirmado: rezagado limpio al horizonte de decisión, el edge operable es débil y caro.
- **Para monetizarlo haría falta** fills MAKER que llenen con fiabilidad contra la presión del libro
  (dudoso por selección adversa) y/o costes HFT → fuera de la misión (CLAUDE.md). **No se toca prod.**
- **CIERRE de la rama order-book intradía.** El backtester horario (e42/e44/e45) queda montado y
  reusable. Lo que sigue en intradía (`INTRADAY.md §5`): liquidaciones (Coinalyze, gated por dato) y el
  monitor de riesgo e15 — ramas separadas, NO desbloqueadas por este resultado.

## CHANGELOG 2026-06-01 (tarde — DOCTRINA MEDALLION + BLEND cross-family validado → sombra (mejor candidato))
Doctrina nueva (Oscar): Medallion gana con **muchas señales pequeñas uncorr combinadas**, no un edge grande.
Memorias: `kepler-many-small-signals-blend`, `kepler-conditional-signals-open`.
- **Vías gratis NO agotadas:** familia DefiLlama (sin key) tiene más que TVL. `e36` stablecoin supply
  (proxy del netflow) → `stbl_pxdiv_14d` ortogonal (0.12), IS/OOS balanceado, +0.22 OOS/3-6. `e37` fees
  por cadena → muerto. Blend MISMA-familia (TVL+stbl+fees) NO diversifica (correlados entre sí ~0.5).
- **`e38` blend CROSS-FAMILY** (TVL+order-book+OI+iliquidez, re-evaluando descartados como COMPONENTES):
  +0.34 Sharpe pero 4/6 + 2023+. Matriz corr: solo order-book uncorr (~0); TVL/OI/illiq cluster ~0.5.
- **`e39` señal diaria, 1 intento más → GANÓ:** familia DISTRIBUCIÓN/COLA. **`max_60d` (efecto lotería**,
  short high-MAX) **ORTOGONAL (corr 0.11), Sharpe 1.14, IS 1.40/OOS 1.06, full-history.** El 2º componente
  uncorr (tras order-book) y SIN punto ciego 2022. ⚠️ es pico a 60d (no plateau) → posible leve overfit.
- **`e40` BLEND FULL-HISTORY {lotería+tvl+illiq}: +0.34 Sharpe OOS · 6-6 folds · SIN blindspot 2022.**
  La lotería (uncorr) era el ancla que faltaba. Primer candidato robusto (6/6) de la sesión. La versión
  2023+ de 5 componentes daba +0.46 pero solo 3/6 → la de 3 full-history es MEJOR.
- **`e41` VALIDACIÓN:** TAKER +1.55%/mes (ADV central, sobrevive fuerte) · cuartiles parejos (sin hueco) ·
  LOO robusto (lotería imprescindible para 6/6; illiq el menos crítico). Bandera: lotería-60d window-specific.
- **`e34/e35` C1 SIZE archivado** (universo comprimido + solapa lowvol; CoinGecko cerró API → CoinPaprika gratis).
- **→ SOMBRA:** `onchain.run_blend_shadow` (sleeve `blend_lottery_tvl_illiq_v1`) montado + wired al orquestador
  + `e33` generalizado. **PENDIENTE DEPLOY (Oscar).** Acumular ~60-90d → `e33` → decidir promoción a sleeve #8.

## CHANGELOG 2026-06-01 (tarde-2 — BACKTESTER HORARIO desbloqueado + Fase 2 intradía PREPARADA)
- **🔓 `e42` Backtester horario Fase 1 — RECONCILIA con el motor (corr de bloque 1.000)** en mom/rev/
  lowvol/hlpos, Sharpe ≈ motor. MTM buy-and-hold (deja driftar dentro del bloque = forward del motor).
  **Supera el fallo de e15** (que daba −0.28 vs +1.04). Base intradía LISTA. `INTRADAY.md` §5 Fase 0+1 ✅.
- **`e44` modelo de coste intradía** (`eval_intraday`): MTM horario + coste por símbolo (taker+slip ADV).
  Validado: mom a 1h → Sh maker 0.59 / taker+ADV **−0.59** (coste destruye holds cortos), recupera al
  alargar (24h +0.52, 168h +0.86). Confirma e19. Motor de Fase 2 listo.
- **`e43` descarga bookDepth 30s** (imb1/imb2/imb5 nativo 30s por símbolo) → `data/bookdepth_30s/`.
  ✅ **COMPLETA (2026-06-01, 2.16GB, 32/32 símbolos, ~92min).** Integridad verificada: 0% NaN, resamplea a
  horario limpio, alinea con el panel C (2023-01→2026-05, 29.9k barras 1h). Coins nuevos desde su listing.
  Incremental/reanudable. **Insumo de Fase 2 LISTO.**
- **PRÓXIMA SESIÓN = Fase 2:** cuando termine la descarga → imbalance 30s→horario → score=−imb → `eval_intraday`
  a holds {1,2,4,6,12}h con `cost_vector('taker_adv')` → ¿sube el retorno al maxDD −10% con coste real? +
  walk-forward purgado + estrés. Si sí → primer sleeve INTRADÍA. Receta completa en `INTRADAY.md` §5 Fase 2.

## CHANGELOG 2026-06-01 (mañana — investigación web GRATIS + iliquidez ARCHIVADA + LABORATORIO DE RÉGIMEN)
Directiva de Oscar: agotar vías GRATIS (foros/blogs/datasets públicos) antes de pagar; y explorar
**condicionar sleeves por RÉGIMEN** (idea de Oscar, estilo Sentinel) para rescatar descartados / potenciar actuales.

### 1) Investigación web "gratis primero" — el netflow de PAGO quedó MENOS justificado
- **Hallazgo que cambia prioridad:** paper arXiv 2411.06327 → el poder predictivo del **netflow on-chain es
  intradía/débil en majors** (BTC no; ETH mixto; la señal fuerte USDT→mercado es market-wide = gate de régimen
  descartado). ⇒ CryptoQuant (~$99/mo) **baja de prioridad**; antes hay que validar el proxy GRATIS.
- **Rutas GRATIS identificadas** (no agotadas): **Dune Analytics** (SQL público forkeable de CEX inflow/outflow;
  metodología de CryptoQuant es pública, el "secreto" es el etiquetado de wallets, cada vez más abierto) y
  **Flipside** (SQL/API gratis). Reconstruir netflow per-token nosotros = point-in-time honesto (como TVL).
  ⚠️ Ingeniería pesada (universo cross-chain). **Coinalyze** liquidaciones: gratis, diario retenido, pero edge intradía.
- **Candidato académico GRATIS destapado:** factor de **iliquidez de Amihud** (datos propios) → se evaluó (abajo).

### 2) Factor de iliquidez (Amihud) — REAL pero MARGINAL → **ARCHIVADO** (e30/e30b/e30c/e30d)
- e30 (chequeo): `illiq_mean_14d` Sharpe 0.50, corr 0.25 (lowvol), **+0.98%/mes @−10% MAKER**, signo + (premium académico).
- e30b (estrés/coste): turnover 6x (baratísimo, slip más bajo del sistema) PERO con **coste realista ADV el aporte
  cae a +0.18%/mes** (positivo, no muere; el +0.98 era ilusión de maker). Q2 negativo. Plateau 14–45d, acantilado <14d.
- e30c (B1 walk-forward purgado): Sharpe OOS +0.14 (= IS) pero **CPCV solo 3/6 folds**, un fold −0.43 = dependiente de régimen.
- e30d (régimen pre-registrado): hipótesis (premium en calma) **REFUTADA** — illiq gana en ALTA vol; el gate ON/OFF
  **empeora** OOS. No se invierte el signo sobre la misma muestra (= trampa e25). **VEREDICTO: archivado** (más débil
  que el TVL, que sigue en sombra). Sistema **sigue 7 sleeves** (no toca prod).

### 3) 🌀 LABORATORIO DE RÉGIMEN (R0+R1) — montado, validado, reutilizable (`research/regime_lab.py`)
- **R0 protocolo anti-overfit:** menú FIJO de 5 régimenes ex-ante (vol mercado, tendencia BTC, dispersión XS, funding,
  breadth); umbral mediana-expanding solo-pasado SIN tunear; **solo Sharpe en walk-forward purgado + CPCV** (esquiva
  trampa del ancla e28); **deflación por multiple-testing**; lo espiado se valida forward, no aquí.
- **R1 evaluador** reutilizable + cache. **VALIDADO:** reproduce baseline OOS 2.27/6-folds y raw-illiq +0.14/3-folds; y
  **RECHAZA en OOS la señal alta-vol que e30d insinuó in-sample** (−0.09) → el harness tiene integridad.
- **R2 (e31): ¿potenciar los 7 actuales con régimen? → NINGÚN superviviente.** 70 combos, barra deflactada +0.67;
  mejor `trend×breadth` +0.42 (match teoría) pero no supera barra ni folds. Los 7 ya son robustos (6/6).
- **📚 APRENDIZAJE:** barrer 70 combos sube la barra deflactada → destruye la detección de edges modestos. La vía
  correcta = **POCAS hipótesis pre-registradas** (N chico). Se aplica en R3.
- **R3 (e32): ¿rescatar DESCARTADOS con régimen? → NINGUNO se rescata.** Hipótesis pre-registradas sobre
  `ls_crowd_rev` (OI/LS, el descartado "por régimen") y `tvl_pxdiv_14d` (on-chain). Hallazgo independiente de la
  barra: **condicionar NUNCA superó al raw** (ls_crowd raw +0.10/5-6 → con régimen −0.12/−0.39/−0.22; TVL raw
  +0.30/4-6 = lo mejor). **CONCLUSIÓN workstream régimen** (3 confirmaciones: e30d illiq, R2 actuales, R3
  descartados): el **conditional factor timing DISCRETO no sobrevive OOS honesto aquí** = callejón sin salida,
  probado a fondo. **Lab montado para futuros candidatos con split limpio.**
- 🎁 **BONUS (no-régimen):** `tvl_pxdiv_14d` RAW **sobrevive el walk-forward purgado** (+0.30 Sharpe OOS, 4/6
  folds; 6/6 condicionado-bull) → **refuerza al TVL (ya en SOMBRA) como candidato a sleeve #8**, más sólido que
  la iliquidez. Caveat: a coste maker (+2.74%/mes inflado); el real era +0.6%/mes taker (e27). Falta confirmar sombra+taker.
- **PENDIENTE (ruta):** **C1** = factores académicos nuevos (size/market-cap, CTREND multi-horizonte) sobre datos
  propios; y decidir sobre el TVL (sombra→sleeve #8) cuando acumule validación forward.


- **Análisis de los logs del 31 (DEMO):** 3 ciclos (=reinicios por deploys; carry-suavizado confirmado
  en vivo, leverage 1.905→2.006), equity 4939→4942 (+0.06%, sano), **primeros slippage reales (C3):
  media ~1.3 bps / mediana ~1.5** (< e18 ~4 bps → ejecución barata; peor en thin coins ZEC/XLM),
  concentración TRX ~18% vía trend, β-hedge funcionando, fix TZ confirmado en vivo, sin errores ni CB.
- **Reporte diario WIRED:** `orchestrator._save_daily_report` (se llama cada ciclo) → `daily_report`
  con metrics (retorno/dd, exposición, leverage, **top posición**, **slippage real del día**, **nº
  ciclos**, CB) + narrativa. Arregla el `report:[]` que veíamos vacío. Probado end-to-end.
- **`shadow_signal` añadido al export DIARIO** (antes solo en el histórico).
- **`MONITOREO.md` creado** (bitácora operativa persistente, pedido de Oscar): cómo leer el reporte
  diario + umbrales de alerta, criterios a vigilar (concentración, slippage, ancla/maxDD e29, reinicios,
  β), bitácora por día (sembrada con el 31), bugs/TODOs, y qué afinar/eliminar/potenciar. En CLAUDE.md.
- PENDIENTE DEPLOY (Oscar): estos cambios + sombra + TZ van juntos.

## CHANGELOG 2026-05-31 (noche-7 — FIX zona horaria: días/horas en Lima, no UTC)
Bug reportado por Oscar: el dashboard marcaba el **día siguiente** (01-jun) a las ~19:00 Lima y el
"log de hoy" descargaba un día vacío (UTC), porque el bucketing de día usaba UTC. **Fix de raíz:**
- `config.py`: zona `TZ` (Lima UTC-5) + helpers `now_local`/`today_local`/`fmt_local`/`day_bounds_ms`.
- `db.py`: `upsert_equity_daily` y `export_daily_log`/`export_log` bucketean por **día LOCAL (Lima)**.
- `api/app.py`: `/api/download` "hoy" = día Lima; `/api/logs`, `/api/equity`, `last_cycle` formatean en Lima.
- `fetch.py` se deja en UTC a propósito (los datos de Binance son UTC). Verificado: a las 23:05 Lima del
  31, `today_local=2026-05-31`, el tick de ahora bucketea al **31** y el export "de hoy" trae el día 31.
- ⚠️ Tras deploy puede quedar una fila `equity_daily` "2026-06-01" creada ANTES del fix (UTC); es
  cosmética, se puede ignorar/borrar. **PENDIENTE DEPLOY (Oscar)** junto con el resto.

## CHANGELOG 2026-05-31 (noche-6 — TRABAJO GRATIS: sleeve TVL en SOMBRA + B1/B2 walk-forward)
Avance de lo gratis-hoy (instrucción de Oscar): dejar correr la demo + B1/B2 + free-TVL en modo sombra.

### 🌓 Free-TVL `tvl_pxdiv_14d` en MODO SOMBRA (no opera) — `kepler/onchain.py`
La única forma de despejar el riesgo point-in-time del TVL (DefiLlama reconstruye su histórico) es
validación FORWARD. Implementado SIN tocar lo que opera:
- `kepler/onchain.py`: fetcher DefiLlama (chain+protocol TVL, 12 tokens) + `shadow_weights()` (pesos
  β-neutral del sleeve vía la maquinaria del motor) + `run_shadow()` (registra, no opera).
- `db.py`: tabla `shadow_signal` (migración idempotente) + `log_shadow()`; incluida en `export_log`.
- `orchestrator.cycle`: hook AISLADO (try/except) tras el snapshot → cada ciclo 24h registra los pesos
  que el sleeve TVL tendría. **NO afecta el target que se opera.** Probado end-to-end (12 señales,
  β-neutral, gross 1.12). Acumulando semanas → se mide su retorno real point-in-time honesto.
- **PENDIENTE DEPLOY (Oscar):** al desplegar, el ciclo empezará a loguear `shadow_signal`. Promoverlo a
  sleeve #8 real (alphas.py + engine.SLEEVES) SOLO si la sombra confirma el +0.6%/mes en vivo.

### 🔬 B1/B2 walk-forward con purga+embargo + CPCV-lite — `research/e29_purged_walkforward.py`
Dos conclusiones HONESTAS (no suben el número, lo hacen creíble):
- **ⓐ EDGE ROBUSTO:** Sharpe OOS (vp+leverage ajustados solo-pasado, embargo 10d) **2.29 ≈ IS 2.21**;
  CPCV **6/6 folds positivos** (media +2.08, min +1.19). La combinación de 7 sleeves NO es overfit de
  selección de pesos. El número de Sharpe sobrevive el walk-forward honesto.
- **ⓑ ANCLA OPTIMISTA (hallazgo accionable de RIESGO):** fijar el leverage con el maxDD pasado
  **sobre-apalanca** cuando el futuro es más volátil → en el walk-forward lev medio 3.0x y **maxDD OOS
  −13.5% (excede el −10% objetivo)**. ⇒ **el −10% del backtest PUEDE EXCEDERSE en vivo.** Acción:
  considerar haircut de leverage o calibrar sobre el peor tramo (no todo el historial). → ROADMAP D.
  (B1/B2 NO ataca el gap por costos/microestructura; eso lo da la DEMO, E1.)

### Demo: sigue corriendo (E1). El foso real = tiempo. Nada que codear; medir periódicamente.

## CHANGELOG 2026-05-31 (noche-5 — A5 ESTACIONALIDAD: DESCARTADO (artefacto del ancla) + menú diario AGOTADO)
`research/e28_seasonality_check.py`. Último ítem barato del menú (gratis, del panel). Día-de-semana,
turn-of-month, vencimiento (último viernes), + overlays al ancla.
- **Día de semana:** el combinado gana más Jue/Lun/Mié, pero el overlay "skip peor día" FALLA OOS
  (skip Mar: full +0.30 / **OOS −0.21**) → overfit. ✗
- **Turn-of-month / vencimiento:** el de-risk PARECÍA pasar OOS (Δfull +0.57/+1.41, OOS +1.06/+2.96)
  → escrutado con T5 (sensibilidad + cuartiles): **es ARTEFACTO del ancla, no estacionalidad.**
  - **Smoking gun:** vencimiento **±0d (el viernes) = Δ+0.04 (nada)**; solo crece al ensanchar la ventana
    (±1d +1.41, ±2d +2.08 sobre 17% de la muestra). El "edge" escala con CUÁNTO de-riskeas, no con la
    cercanía al vencimiento → es recortar drawdown para que el ancla suba el leverage (= gate de régimen).
  - Cuartiles del de-risk: +0.04 / −0.18 / +0.02 / +0.03 → no repartido, clip de 1-2 eventos.
  - Coste de turnover del de-risk (~12x/año × gross × fee) ni siquiera modelado → recortaría más.
- **VEREDICTO: A5 DESCARTADO.** Calendario = market-wide → gate de régimen ya descartado; lo que parecía
  edge era el mecanismo leverage-al-ancla clipeando drawdowns. No se toca prod.
- **🏁 MENÚ DIARIO BARATO AGOTADO.** Recorrido completo (todas las vetas gratis de señal diaria):
  precio/OHLCV ✗, positioning ✗, basis ✗, universo ✗, order-book diario ✗ (edge intradía), opciones ✗
  (BTC/ETH-only), on-chain TVL ~ (real pero modesto +0.6%/mes), estacionalidad ✗. **Lo que queda NO es
  gratis-diario:** (1) netflow on-chain de PAGO (justificado), (2) backtester horario (intradía), (3)
  endurecer validación B1/B2, (4) **dejar correr la DEMO = el foso real (E1).** Ver FOCO actualizado.

## CHANGELOG 2026-05-31 (noche-3 — A3 ON-CHAIN TVL (DefiLlama, GRATIS): PROMETEDOR, pasa estrés)
`research/e26_onchain_tvl_check.py`. Política gratis-primero (instrucción de Oscar): sondeé varias
fuentes; netflows de exchange POR TOKEN son de pago (Glassnode/CryptoQuant/Santiment) → a "revisar
información pagada". Lo GRATIS y per-símbolo que sí existe: **TVL por cadena** (DefiLlama API pública).
- Cobertura: 10 tokens del universo que son cadenas con TVL largo (ETH/BNB/SOL/AVAX/TRX/NEAR/ADA/HBAR/
  FIL/XLM). Cross-section DELGADO. Señal: Δlog(TVL) y Δlog(TVL)−retorno (acumulación, neto de precio).
- **GANADOR: `tvl_pxdiv_14d`** (TVL sube más que el precio = acumulación, contrarian/fundamental):
  Sharpe 0.94 (**IS 0.63 / OOS 1.27** → aguanta OOS), corr **0.10** (máx, con hlpos), **Δ+1.03%/mes** al ancla.
  - **Estrés PASA (≠ e17):** leave-one-out robusto (quitar cualquier token deja Δ **+0.78..+1.24%/mes**,
    NO concentrado en 1 nombre); cuartiles Q1 −0.34 / Q2 +1.32 / Q3 +1.42 / Q4 +1.41 (3/4 fuertes; débil
    solo el arranque 2022). `tvl_mom_7d` marginal (+0.10); el resto no pasa.
### BUILD SERIO `research/e27_onchain_tvl_build.py` (CIERRE de A3) — edge REAL pero MODESTO/frágil
Cobertura ampliada a **12 tokens** (10 chain-TVL + protocol-TVL AAVE/UNI). Rango horizontes + coste
(maker/taker) + turnover + ataque point-in-time (clip de saltos por alta de protocolos + split 2022/2023+).
- **Candidato de registro: `tvl_pxdiv_14d`** (raw): corr **0.11**, OOS 1.27, **Δtaker +0.63%/mes**, turnover 42x.
- ✅ **POINT-IN-TIME (la duda clave) — PASA:** el edge vive en **2023+ (Sharpe +0.97/+1.11**, cobertura
  madura) y es plano/negativo en 2022 → NO es artefacto de backfill. El CLIP (±15%/día) no lo mata,
  lo mejora levemente → no son saltos artificiales. Era mi mayor preocupación y la supera.
- ⚠️ **Banderas amarillas (no es slam-dunk como taker_flow/hlpos):** (1) horizonte ESTRECHO — 10-14d bien,
  **21d se va a −1.09**, 30d flojo (no es plateau ancho); (2) cuartiles desiguales (Q dispares); (3) el 10d
  está concentrado en pocas chains chicas (TRX/NEAR/HBAR en LOO; el 14d más robusto); (4) **negativo en
  2022** (no ayuda en el peor régimen); (5) cross-section delgado (12) = techo estructural de A3 aquí.
- **T4 combinado 8 sleeves: Sharpe 2.07→2.14 · Δtaker +0.64%/mes** (peso vp ~0.10). El 7d daba más (+0.77)
  pero descartado (turnover alto + AAVE-dependiente).
- **VEREDICTO A3:** edge on-chain **REAL, ortogonal y +0.6%/mes taker** (el mejor de la sesión; ≠ order-book
  +0.00 / Deribit nada), pero **modesto y con suficientes banderas para NO precipitar a producción.** El
  free-TVL es un PROXY: prueba que el on-chain TIENE edge → **justifica evaluar el netflow per-token de PAGO**
  (más limpio, point-in-time honesto, cubre los 32). Dos caminos (decisión de Oscar): (A) validar el
  free-TVL 14d con walk-forward+purga (B1) + demo antes de prod; (B) saltar al netflow pagado (ahora justificado).

> 📋 Las fuentes de PAGO descubiertas hoy (netflows per-token, liquidaciones) están en la lista viva
> **"REVISAR INFORMACIÓN PAGADA"** de la sección PENDIENTES (con costo, prioridad y dónde retomar).

## CHANGELOG 2026-05-31 (noche-2 — A6 OPCIONES Deribit/DVOL: DESCARTADO, BTC/ETH-only + gate régimen)
`research/e25_deribit_check.py`. Chequeo barato de la siguiente fuente del menú diario (opciones).
DVOL (índice de vol implícita de Deribit, gratis API pública, BTC/ETH 2021-03→hoy).
- **Muro estructural:** Deribit solo tiene opciones líquidas de **BTC/ETH** → una señal de opciones NO
  puede ser cross-seccional (no rankea los 32 alts). Mismo muro que el basis (e22). Único uso posible:
  overlay de timing de mercado — y los gates de régimen YA están descartados (empeoran maxDD, CLAUDE.md).
- **T1 redundancia:** corr(DVOL, vol realizada 30d BTC) = **0.74** → el 74% ya lo ve lowvol.
- **T2 overlays:** el mejor (de-risk cuando la vol sube) daba +0.21%/mes PERO con Sharpe 2.07→1.93
  (sube vía leverage del ancla, no por mejor ride). **T2b IS/OOS lo mata: IS −1.15%/mes · OOS +0.43**
  → cambia de signo entre mitades = ruido, no edge. Reconfirma la fragilidad del gate de régimen.
- **T3:** corr(DVOL, retorno fwd del combinado) = +0.05 (no predice dirección).
- **VEREDICTO: DESCARTADO** para el sistema diario. La info genuina de opciones (VRP/short-vol) sería
  OTRA estrategia (pila de opciones), no este sistema de perps. No se toca prod.
- **LECCIÓN DE FONDO (acota el menú):** toda fuente BTC/ETH-only (basis, opciones) choca con el mismo
  muro (no cross-seccional); toda señal market-wide cae en el gate-de-régimen descartado. Lo que queda
  viable en el menú diario debe ser **(a) per-símbolo del universo Y (b) ortogonal** → **A3 on-chain**
  (flujos exchange por activo) es la única con potencial cross-seccional; A5 estacionalidad (barato/incierto).

## CHANGELOG 2026-05-31 (noche — A2 ORDER-BOOK: real+ortogonal pero NO aporta al ancla → DESCARTADO)
Foco de Oscar: nuevas fuentes de datos. **Liquidaciones (la candidata #1) NO tiene histórico gratis:**
`allForceOrders` REST = "out of maintenance"; `liquidationSnapshot` en data.binance.vision = vacío
(retirado). Solo se consigue pagando (Coinglass) o capturando el WS `@forceOrder` hacia adelante
(lento). → pivote a **A2 order-book** (`bookDepth` SÍ está, 2023+, misma infra que metrics).

### e23 (chequeo barato) → PROMETÍA · e24 (validación seria) → NO aporta
- `research/e23_orderbook_check.py`: 12 símbolos líquidos, imbalance = mean_t(bid−ask)/(bid+ask) a
  ±1/2/5% del mid. **Bug que cacé y corregí:** la media diaria ve el día completo → look-ahead;
  rezagar 1 día desinfló Sharpe de 7–9 (falsos) a ~1–2. Con 2 regímenes (2023-24): ortogonal
  (corr 0.06–0.23), contrarian estable, OOS positivo en 7/12 → luz verde al download completo.
- **Download completo** bookDepth 32 símbolos × 2023-01→2026-05 (cache `data/bookdepth_daily/`, ~97min).
- `research/e24_orderbook_sleeve.py` (molde e16e): ANCHO×HORIZONTE×coste + turnover + cuartiles + 7→8.
  | | baseline 7 (overlap 2023+) | +order-book (mejor imb1_5d) |
  |---|---|---|
  | Sharpe | 2.17 | 2.33 (+0.16) |
  | %/mes @−10% maker | 5.11 | 5.19 (+0.09) |
  | %/mes @−10% **taker** | 5.11 | **5.11 (+0.00)** |
  - El sleeve es REAL: imb1/imb2 a 2d–7d Sharpe 1.1–1.4, IS/OOS consistentes, 4 cuartiles + (+1.65/
    +1.16/+1.05/+1.37), turnover sano 35–50x. PERO **todas las variantes dan Δ≤0 a coste taker.**
  - **Lección e16d reconfirmada:** con el ancla, corr~0 + IS/OOS NO basta — el sleeve debe subir el
    retorno a maxDD fijo. Standalone Sharpe ~1.3 < combinado 2.17 → vía vol-parity solo DILUYE. El
    +0.16 de Sharpe es ride más suave, pero el retorno al maxDD −10% no se mueve.
  - Clavos extra: (1) baseline 5.11%/mes es el del overlap 2023+ (excluye 2022, optimista) y aun así
    no aporta; (2) bookDepth no existe pre-2023 → cegaría el ancla al bear 2022 (como ls_crowd_rev e16f).
  - NO se corre e18 (slippage ADV): el bracket taker ya lleva el Δ a +0.00; ADV sobre ilíquidos solo
    lo haría negativo. **DESCARTADO como sleeve diario. No se toca prod.**
- **CONCLUSIÓN DE FONDO (reordena el roadmap):** el order-book imbalance sin-lag daba Sharpe 7–9 a 24h
  → su edge genuino es **INTRADÍA**, que el sistema HOY no opera (rebal 24h; monitor intradía BLOQUEADO
  e15 por falta de backtester horario). **La ruta para monetizar microestructura (order-book, y lo que
  liquidaciones habría sido) pasa por construir el BACKTESTER HORARIO, no por otro sleeve diario.**
  Data bajada y reutilizable si algún día se ataca el intradía. Sistema sigue 7 sleeves / 32 perps.
  **HALLAZGOS INTRADÍA DOCUMENTADOS en `INTRADAY.md`** (guía futura; Oscar pidió aparcar intradía y
  seguir con el menú diario). ROADMAP §F creado. Próximo DIARIO vivo: opciones Deribit (A6).

## CHANGELOG 2026-05-31 (mediodía — C1 slippage realista: el 1.94 estaba inflado por turnover)
`research/e18_slippage.py`. El motor cobra costo PLANO (turnover×MAKER_FEE 1.8bps) en xs/carry y
**CERO en trend** → subestima costos. C1 modela slippage por liquidez (ADV; el estimador de spread
Abdi-Ranaldo NO sirve con barras 1h → spread sub-bp enterrado bajo vol intrahora). Sanity: escenario
flat reproduce el 1.94 exacto.
- **TURNOVER anualizado (× capital/año, one-way):** carry **198.9x** (⚠️ reordena el libro cada 48h por
  ranking de funding), takerflow 82.9x, trend 56.8x (¡paga 0!), hlpos 38.8x, lowvol 21.5x, mom 20x, rev 9.7x.
- **Resultado al ancla −10% con slip realista (BTC 0.5bps→LIT 13bps, mediana 4bps):**
  | escenario | Sharpe | lev | %/mes |
  |---|---|---|---|
  | motor actual | 1.94 | 1.92 | 3.52 |
  | + slip ADV central (~4bps) | **1.67** | 1.77 | **2.70** (−0.82) |
  | + slip ADV ×3 (estrés) | 1.18 | 1.22 | 1.21 |
  | + 10bps plano (estrés duro) | 1.34 | 1.37 | 1.57 |
- **CONCLUSIÓN:** el número honesto es **~1.67 / 2.7%/mes** (no 3.5%); el 1.94 estaba inflado por
  subestimar costos. El lever es el TURNOVER, sobre todo **carry (199x)** y **trend sin costo**. No se
  tocó el motor (cambiarlo bajaría el leverage del ancla = decisión de Oscar).
- **Próximo (decidido por Oscar): B — reducir turnover de carry** (ROADMAP C2): suavizar/umbralizar sus
  pesos; puede recuperar buena parte del −0.82%/mes → posible MEJORA real. Luego cobrar costo a trend
  y calibrar slippage con fills reales de DEMO (C3).

## CHANGELOG 2026-05-31 (tarde-3 — dashboard explicativo + estado/pendientes actualizados)
Dashboard mejorado para transparencia (misión copy-lead). `api/dashboard.html` + `api/app.py`:
- Panel **"¿Cómo funciona Kepler?"** (market-neutral, 7 sleeves, rebal 24h, sin SL, circuit breaker;
  con aviso de que Sharpe/maxDD son BACKTEST).
- **Drawdown** (caída desde el pico) bajo la curva de equity — clave para el pitch de bajo-DD.
- **Diversificación por estrategia** (doughnut de pesos vol-parity de los 7 sleeves).
- **PnL por posición** (barras verde/rojo, de posiciones reales) + chips **Long/Short/Net $**.
- Métrica **leverage estrategia** añadida; fallback backtest a 2.07/49.3.
- `/api/status` ahora expone `leverage` y `sleeves` (vp). Smoke test con TestClient OK.
- Cabecera de STATUS (ESTADO ACTUAL) y sección PENDIENTES reescritas a la realidad de hoy.

## CHANGELOG 2026-05-31 (tarde-2 — A4 cross-exchange basis: PARADO, basis ≈ carry)
`research/e22_basis_check.py`. Antes de bajar 23 historias de spot para un sleeve cross-seccional de
basis, chequeo barato con BTC/ETH (lo único con spot): **el basis (perp/spot−1) ≈ funding/carry**.
- corr(basis, funding) = **0.74** (BTC y ETH, nivel) · forward 0.70 (el basis ES el funding de mañana)
- cross-seccional corr(Δbasis, Δfunding) BTC−ETH = **0.53** (la señal que rankearía el sleeve)
- **Veredicto: duplicaría el sleeve #4 (carry), no diversifica** (corr > umbral 0.35) → diluiría
  (lección e16d). NO bajar spot del universo. Único ángulo ortogonal posible: el RESIDUAL (dislocaciones
  perp-spot que el funding no explica), especulativo + necesita spot del universo → no se hace ahora.
- **Conclusión de fondo:** las vetas de research SIN datos nuevos están agotadas (universo ✗, OHLCV ✗,
  positioning ✗, basis ≈ carry). Lo ortogonal que queda exige FUENTES NUEVAS (A2 order-book, A3 on-chain)
  o, lo más valioso, dejar correr la DEMO (el foso real = tiempo, E1).

## CHANGELOG 2026-05-31 (tarde — B3 Deflated Sharpe (resultado) + C3 medición de slippage (montado))
### B3 — Deflated Sharpe Ratio (`research/e20_deflated_sharpe.py`) — RESULTADO
DSR = prob. de que el Sharpe 2.07 sea real y no suerte de buscar N configs (Bailey & López de Prado).
| Nº trials asumido | SR0 (benchmark suerte) | DSR |
|---|---|---|
| 24 (grilla) | 1.12 | **0.995** |
| 72 (×3) | 1.36 | 0.973 |
| 120 (×5, muy conserv.) | 1.46 | **0.951** |
- **El 2.07 sobrevive al multiple-testing** (DSR>0.95 incluso a 120 trials). NO es artefacto de buscar.
- ⚠️ Caveats: serie diaria muy no-normal (skew 7.6/kurt 122 por contabilización a "picos" → el número
  exacto es blando) y el DSR ataca SELECCIÓN, no el gap backtest→vivo. El número vivo seguirá menor.

### C3 — Medición de slippage real (montado; GATED por datos)
No da números hoy (1 ciclo de fills + DB en la VM + faltaba capturar el fill real). MONTADA la medición:
- `execution.get_user_trades(sym, start_ms)` (read-only, blindado) → fills reales de Binance.
- `orchestrator._log_fills` calcula **VWAP real vs ref book_mid → slip_bps** (signo adverso) por fill.
- `db`: migración idempotente cols `ref_px`, `slip_bps` en trades; `log_fill` los guarda.
- `research/e21_fill_slippage.py`: analizador que agrega slip real por símbolo vs el modelo K50 de e18.
- **PENDIENTE (gated):** desplegar → dejar correr DEMO varios días → traer `kepler.db` de la VM →
  correr e21 → recalibrar K (o usar slip por símbolo) → re-correr e18 = número de costo HONESTO real.

## CHANGELOG 2026-05-31 (mediodía-3 — costo a trend (honestidad) + workflow: Claude no hace push)
- **Costo a `trend` IMPLEMENTADO:** `engine.trend_sleeve` ahora resta `MAKER_FEE` plano sobre su
  turnover (antes pagaba 0; rota ~57x/año). Contabilidad de costos ya UNIFORME en los 7 sleeves.
  Impacto insignificante (e18 lo predijo): Sharpe **2.07** · %/mes **4.11** · lev **2.02x** · maxDD −10%
  (idéntico a 2 decimales). Honestidad, no daño.
- **WORKFLOW (preferencia de Oscar):** Claude NO ejecuta `git push/pull/fetch` (cada uno le pide a
  Oscar confirmar cuenta GitHub). Claude hace SOLO commits locales; Oscar pushea/despliega cuando
  quiere subir versión. Ver memoria `kepler-no-git-push`.
- **PENDIENTE PUSH+DEPLOY (Oscar):** commits de hoy aún en local algunos. Próximo: validar B en demo,
  C3 (calibrar slippage con fills reales), B3 (Deflated Sharpe), A4 (cross-exchange basis).

## CHANGELOG 2026-05-31 (mediodía-2 — B: suavizar funding de carry = WIN limpio, pendiente implementar)
`research/e19_carry_turnover.py`. El carry rankeaba sobre funding INSTANTÁNEO (1 lectura 8h, ruidoso)
→ 199x turnover → con costos reales Sharpe NETO **−0.41** (perdedor). El funding persiste días, así
que se puede suavizar la señal sin perder el edge (la funding cobrada sigue siendo la real).
- **Estrés por cuartiles:** el carry actual tiene un AGUJERO en Q3 (Sharpe 0.37); las variantes
  suavizadas lo tapan y reparten la mejora en los 4 cuartiles. El "mejor" bruto (inst/168h, 3.96) era
  ARTEFACTO no monótono → descartado por el estrés.
- **GANADOR robusto: suavizar funding a 7d (media móvil 21×8h), holding 48h igual.**
  | métrica | actual | 7d/48h |
  |---|---|---|
  | turnover | 199x | 65x |
  | carry Sharpe (neto real) | −0.41 | +0.35 |
  | combinado %/mes (costo plano motor) | 3.52 | **4.11** |
  | combinado %/mes (slip real) | 2.70 | **3.51** |
  | corr con otros / maxDD | 0.15 / −10% | 0.08 / −10% |
- **Mejora bajo AMBOS modelos de costo** (plano +0.59, real +0.82) → pasa la regla de oro (mejora
  rentabilidad incluso con la contabilidad actual del motor). Cambio mínimo: 1 línea en
  `engine.carry_sleeve` (rankear sobre `F.rolling(21).mean()` en vez de la lectura instantánea).
- **IMPLEMENTADO (Oscar OK, opción 1 = 7d/48h):** `engine.CARRY_SMOOTH=21` + `carry_sleeve` rankea
  sobre `F.rolling(21).mean()` (funding cobrada sigue real). Verificado `engine.main ESTABLE`:
  **Sharpe 1.94→2.07 · %/mes(plano) 3.52→4.11 · leverage 1.92→2.02x · maxDD −10% · mo+ 71%.**
  PENDIENTE: deploy a DEMO (Oscar corre `deploy.sh`) + validar. El dashboard mostrará 2.07/49.3/−10
  desde el próximo ciclo (snapshot recalcula). Alternativa descartada: 7d/168h (42x, 3.42%/mes).

## CHANGELOG 2026-05-31 (mañana — FIX logging de señales/trades + export de análisis + gráfico)
**Motivo:** Oscar descargó "log de hoy" del dashboard y salió vacío (`trades/signals/audit/report` = []).
Diagnóstico (2 causas):
1. El export era **por día UTC** y solo 4 tablas; hoy aún no había corrido el ciclo de 24h (último
   May 30 18:02, próximo ~May 31 18:02) y los heartbeats solo escriben `equity_tick` → vacío legítimo.
2. **Hueco real:** `signals` y `trades` NUNCA se persistían — los métodos existían en `db.py` pero no
   se llamaban desde ningún sitio. Solo se guardaba snapshot/equity/audit.

**Implementado (validado en DRY_RUN end-to-end + test DB aislado):**
- `engine.compute_target` ahora devuelve también `weights` (pesos por sleeve) → 7-tupla. Callers
  actualizados (orchestrator, engine.main, execution.main, report.py).
- `orchestrator.cycle`: registra **señales** (1 por símbolo: lado + peso final + **desglose por sleeve**
  en `features`) vía `_log_signals`; registra **trades/fills reales** = diff de posiciones antes/después
  del rebalanceo vía `_log_fills` (honesto con maker GTX que no siempre llenan; solo cuenta lo que cambió).
- `db.log_fill` nuevo (cada fila = un cambio de tamaño; status closed si la posición queda en 0).
- `portfolio_snapshot.detail` ahora incluye `vp` (pesos por sleeve) y `positions` (posiciones reales
  + PnL del ciclo) → histórico de holdings con PnL sin tabla nueva.
- `db.export_log(start,end)` nuevo: export de ANÁLISIS con rango o histórico completo, incluyendo
  signals/trades/portfolio_snapshot/equity_tick/equity_daily/audit/daily_report en un archivo.
- `api/app.py` `/api/download` acepta `?full=1` y `?start=&end=`. Frontend: botón nuevo
  **"Histórico completo (análisis)"** junto al de hoy.
- Dashboard: **curva de equity a todo el ancho y horizontal** (300px, movida bajo las métricas);
  posiciones pasan a ancho completo debajo.
- ⚠️ NOTA: `r_multiple`/`exit_px` quedan null (el sistema es rebalanceo rodante, sin ciclo open→close
  clásico; el ciclo de vida completo de trade sería otro proyecto). Los fills + snapshots ya permiten
  analizar el comportamiento.

**FIX balance ilegible (sale del análisis de los 2 días):** antes `get_balance() or CAPITAL_USD`
metía un **5000 falso** cuando la API no respondía (los 2 primeros ciclos del 05-30 marcaron 5000.0
exacto en 16s = fallback; el balance real era ~4933). Ahora: `heartbeat` OMITE el punto si el balance
es ilegible (no inventa); `cycle` OMITE el rebalanceo (no sizar el libro con valor falso) y NO consume
la ventana de 24h → reintenta en el próximo heartbeat (15min). En DRY_RUN no cambia nada
(`get_balance` devuelve el capital configurado).

**Análisis de los ~31h en demo (curva wallet + audit, hecho 2026-05-31):** equity PLANO 4933→4939
(+0.11%), maxDD wallet ≈ −0.01%, funding casi neutral (−0.06 USD a 00/08h UTC). El "5000→4933" NO
fue pérdida = artefacto del fallback (ver fix). 8 ciclos el 05-30 = reinicios del servicio (dev/deploy),
no cadencia 24h; próximo rebal real ≈18:03 UTC. **Conclusión: operativamente sano; de edge no se
concluye nada (1 período de tenencia + wallet no ve PnL no realizado).** Es el E1 del ROADMAP (tiempo).
- **DEPLOY HECHO + VERIFICADO EN PRODUCCIÓN (2026-05-31 12:05 UTC):** commit `d87eed3` desplegado.
  El ciclo del reinicio registró 21 señales (con desglose por sleeve), 13 fills reales y snapshot con
  22 posiciones + PnL. El export "Histórico completo" trae todo. **Logging confirmado funcionando.**
  - **Primer análisis con datos finos:** PnL no realizado del libro = **+$9.92 (+0.20%)** (el wallet no
    lo veía). Ganadores TRX +9.11 / BNB +7.4; mayor lastre NEAR −10.02 / ATOM −3.49. Net ≈ cero-positivo
    = ruido de 1 día (esperado, market-neutral). **Concentración en TRX** ($720 notional ≈15%, la empuja
    `trend`). **Tracking error visible:** BTC target SHORT pero libro aún LONG (maker GTX no llenó el giro).
    backtest auto bajó a Sharpe 1.89/ann 41.2 (datos nuevos). Edge aún NO concluible (E1: tiempo).
  - Posible mejora futura: `beta` del snapshot está hardcodeado a 0.0 → calcular β real del libro (ROADMAP D1).

## CHANGELOG 2026-05-30 (tarde-5 — A1 ampliar universo: VALIDADO con estrés → NO conviene)
- `research/e17_expand_universe.py` (greedy 1-a-1, criterio: retorno@−10% + OOS + no recorta panel)
  + `research/e17b_stress_universe.py` (estrés del subconjunto ganador). Descargué 20 candidatos
  reales de historia ≥2022 (XMR,ALGO,ICP,AXS,DASH,DYDX,OP,APE,ENS,CRV,VET,IOTA,CHZ,XTZ,SAND,...).
- **Resultado: NO ampliar.** El subconjunto "ganador" (8 símbolos) parecía +2.6%/mes (Sharpe
  1.94→2.25, OOS 2.06→2.94) pero el ESTRÉS lo tumba:
  - T1 cuartiles: mejora ERRÁTICA — PEOR en Q1/Q2, casi todo viene de Q3. No repartida = no robusta.
  - T2 desglose: solo **+0.38%/mes es EDGE**; **+2.23%/mes es LEVERAGE** extra (ancla 1.92x→2.76x).
  - T3 robustez: quitar AXS borra +0.96%/mes → concentración frágil en 1 símbolo.
  - Conclusión: apalancar 2.76x sobre edge errático = frágil al gap backtest↔vivo. Oscar decidió NO.
- **Lección: la veta "más símbolos" está agotada** (como OHLCV y positioning). Las mejoras reales que
  quedan NO suben el número de fantasía sino que lo acercan al real: **C1 (costos realistas)** y
  **B3 (Deflated Sharpe)**. ← próximo. Sistema sigue 32 perps / 7 sleeves. Datos candidatos en data/.

## CHANGELOG 2026-05-30 (tarde-4 — congelar estado + ROADMAP Medallion-inspired)
- **Estado CONGELADO y publicado en la VM (DEMO):** 7 sleeves + ancla maxDD −10% (Sharpe 1.94 backtest).
  Oscar consciente: **el 1.94 es backtest, en vivo bajará** — por eso el plan es subir el TECHO.
- **`ROADMAP.md` creado** (faro Medallion/RenTech): qué copiar (muchas señales débiles uncorr,
  validación brutal, composición, β-neutral, costos modelados) y qué NO (HFT, market-making, leverage
  extremo). Roadmap priorizado A-E. **El foso real = TIEMPO (track record), no se acelera.**
- **Dashboard fix (commit cde862f):** el backtest mostrado ya NO está hardcodeado — el orquestador
  guarda las métricas reales (con leverage anclado) en el snapshot cada ciclo; `api/app.py` las lee.
  Se auto-actualiza con cada sleeve futuro. Verificado: snapshot trae {1.94, 42.2, −10.0, 7 sleeves}.
- **Accionable AHORA (sin esperar demo):** A1 ampliar universo → C1 slippage realista → B3 deflated
  Sharpe → A4 cross-exchange basis. Ver STATUS pendientes + ROADMAP.

## CHANGELOG 2026-05-30 (tarde-3 — sleeve #8 metrics: DESCARTADO con datos)

### Open Interest / long-short ratio NO aportan → sistema se queda en 7 sleeves
Fuente nueva: Binance `metrics` (data.binance.vision/.../daily/metrics, desde 2023, 5min→1h).
Descargada para los 23 símbolos (`research/e16f_download_metrics.py`, paralelo). Backtest
`research/e16f_metrics_sleeves.py` con criterio del ancla (Δretorno a maxDD −10%, sobre overlap 2023+):
- Candidatos: oi_mom (5d/14d), oi_px_div, ls_crowd_rev (contrarian retail), toptrader_fol.
- Solo `ls_crowd_rev` (z-score invertido del count_long_short_ratio) pasó el filtro corr+IS/OOS,
  pero **DESCARTADO**: (1) **OOS frágil** — cuartiles inconsistentes en el estrés de horizonte
  (7d: [−0.98,+1.88,−0.31,+2.13]), señal de ruido no edge; (2) aporte marginal **+0.24%/mes** vs
  +0.87 de hl_position; (3) **mal trade estructural**: metrics solo existe desde 2023 → añadirlo
  cegaría el ancla de maxDD al peor año cripto (**2022: LUNA/FTX**). No vale renunciar al stress de
  2022 por +0.24%/mes. (Probé implementación con código + ancla híbrida; Oscar decidió NO. Revertido.)
- `toptrader_fol` (seguir "smart money") da Sharpe **−0.70** → seguir el ratio de top traders PIERDE.
- **HALLAZGO (negativo pero valioso): la data de posicionamiento (OI, L/S ratio) NO aporta sobre los
  7 sleeves** — el flujo (`taker_flow`) + `trend` ya capturan esa información. **Sistema = 7 sleeves.**
- Data en `data/metrics/` (no trackeada, .gitignore *.parquet). Reutilizable para futuras ideas.

## CHANGELOG 2026-05-30 (tarde-2 — ancla maxDD −10% + ronda 3 sleeves)

### 🟢 ANCLA de maxDD −10% con leverage auto-calculado (regla de Oscar) — commit d0206b1
A pedido de Oscar: el tier ESTABLE fija el **maxDD del backtest en −10%** y el **leverage de
estrategia se CALCULA** para clavarlo (no es múltiplo fijo). Cada mejora del Sharpe → más retorno
al MISMO maxDD (flywheel), no menos riesgo. Excepción a reportar: si subir el maxDD diera un salto
de beneficio desproporcionado, avisar a Oscar.
- `config.TARGET_MAXDD=0.10` · `MAX_STRAT_LEVERAGE=4.0` (cap). `portfolio.leverage_for_maxdd_anchor`
  (bisección, maxDD compuesto monótono en L). `engine.TIERS` = presupuesto de maxDD
  {ESTABLE 0.10, BALANCEADO 0.20, GROWTH 0.30}. `compute_target` devuelve `lev` (6-tupla);
  callers actualizados (orchestrator loguea lev+maxdd_target; report, execution, main).
- **VERIFICADO (engine + orquestador dry-run): 6 sleeves → lev 1.62x → maxDD −10.0% · ann 31.8%
  (~2.65%/mes) · 69% meses+.** (vs ESTABLE viejo 1x: +15.7%/−11.6%.) Gross sube a ~0.82 (< MAX_GROSS=2).
- ⚠️ El −10% es del BACKTEST; el futuro puede ser peor. Circuit breaker (−20%) sigue como red.

### 🟢 SLEEVE #7 `hlpos_14d` (posición en el canal) VALIDADO + IMPLEMENTADO
Ronda 3 (`research/e16d`) con criterio NUEVO: no basta pasar corr<0.35 + walk-forward; debe
**subir el retorno al maxDD −10%** (con vol-parity, un sleeve de menor Sharpe DILUYE aunque sea
ortogonal). De 6 candidatos OHLC/count/flujo, el ganador:
- **`hl_position`** = (close−min_N)/(max_N−min_N)−0.5, 14d=336h. Momentum normalizado por rango.
  Sharpe 1.19 (IS 1.09/OOS 1.33), corr 0.20, **+0.87%/mes al ancla −10%.**
- Estrés (`research/e16e`) PASA: 14d es el óptimo (7/10d flojos, 21d se degrada, 30d colapsa
  corr 0.84 → el edge está en 14d, no es plateau ancho pero los demás tests lo sostienen);
  sobrevive taker (+0.83%/mes); sub-períodos Q1-Q4 todos +0.9..+1.5 (robusto).
- Descartados: `close_loc_5d` (pasa filtro pero DILUYE −0.12%/mes); `range_lowvol` (corr 0.95 con
  lowvol); `count_mom`/`tradesize_mom`/`flow_accel` (fallan walk-forward).
- **IMPLEMENTADO:** `alphas.xs_hlposition_score` + `engine.SLEEVES` (`hlpos_14d`, 336h). Motor 7
  sleeves verificado: **Sharpe 1.94 · maxDD −5.3% (1x) · @−10% lev 1.92x → ann 42.2% (~3.52%/mes)
  · β +0.028 · 19 pos limpias.**
- **LECCIÓN clave (en e16d): con el ancla, el test real de un sleeve es Δretorno a maxDD fijo**
  (corr+IS/OOS es necesario, no suficiente). Próximas fuentes (la veta OHLCV se acerca a su
  límite): **Open Interest / long-short ratio** (data.binance.vision/.../metrics/, extender fetch.py).

## CHANGELOG 2026-05-30 (tarde — NUEVO SLEEVE validado: taker_flow)

### 🟢 HALLAZGO: sleeve #6 `taker_flow` pasa walk-forward + estrés → mejora material
Loop de mejora (pendiente #2). Research en `research/e16` (precio), `e16b` (fuentes ortogonales),
`e16c` (estrés). **Lección e16:** todo candidato derivado de PRECIO sale correlacionado con los
sleeves actuales (accel Sh 1.10 pero corr 0.84 con mom) → no diversifica. **e16b:** señales que NO
son precio. Ganador:
- **`taker_flow`** = desbalance comprador (`taker_buy_volume/volume`), cross-seccional, β-neutral.
  Mide flujo de órdenes → ortogonal al precio. corr máx con los 5 base = **0.06**.
- Estrés (e16c) PASA los 4 tests:
  - Horizonte: edge en PLATEAU (3d/5d/7d todos Sh 0.86–0.97), no un pico. 1d = ruido.
  - Costos: sobrevive TAKER (combinado 1.30/−9.0% peor caso).
  - Sub-períodos: Sharpe por cuartil +0.27/+0.66/+1.16/+1.30 (positivo en los 4, creciente).
  - Combinado 5→6 sleeves: **Sharpe 1.13→1.36 · maxDD −11.6%→−8.6% · mo_med 0.93%→1.06%.**
- **Traducción producto:** o maxDD −8.6% a 1x (menos riesgo), o 1.35x a igual maxDD → **+22%/año
  (~1.86%/mes) vs 1.31%/mes hoy** (+42% retorno sin subir DD). RECOMENDADO horizonte **5d**
  (≈ Sharpe, menos turnover que 3d, IS/OOS más parejo 1.03/0.88).
- **IMPLEMENTADO 2026-05-30** (commit bf83594): `alphas.xs_takerflow_score` + `engine.SLEEVES`
  (`takerflow_5d`, 120h) + `engine.load_panel` (carga volume/taker_buy_volume). Motor 6 sleeves
  verificado end-to-end: **Sharpe 1.54 · ann 18.6% · maxDD −6.3% · β realizado +0.035** (neutral OK).
  Target limpio (13 posiciones, todas activos reales). Ciclo orquestador dry-run sin errores.
  Encoding: `engine.main`/`orchestrator.run` reconfiguran stdout a UTF-8 (consola Windows).
- PENDIENTE: push + `deploy.sh` en la VM → validar en DEMO que el sleeve #6 opera bien varios días
  (regla de oro: backtest ✓, código ✓, falta validación demo antes de llamarlo producción).

## CHANGELOG 2026-05-30 (mañana — auditoría de beta-neutralidad + estado VM)

### ✅ AUDITORÍA: el sistema SÍ es β-neutral (β=+0.05). No hay bug. (FALSA ALARMA corregida)
Durante la sesión salté a una conclusión errónea y la documenté a medias dos veces (commits
`a8c4021`/`8ae1575`): vi que el libro live está **76% NET LONG en dólares** (LONG ~$2.5k / SHORT
~$0.3k, concentrado TRX+BTC) y lo llamé "no market-neutral". **Era confundir dos métricas distintas.**
- Lo que importa para "sobrevivir crashes" NO es el net en dólares sino el **β contra BTC**.
- β REALIZADO (regresión de retornos diarios vs BTC, 4.4a): mom +0.005 · rev −0.015 · lowvol +0.003 ·
  carry +0.005 · trend +0.160 · **COMBINADO 1x = +0.051** (corr BTC +0.20) → dentro de ±0.10 (`NET_NEUTRAL_TOL`).
- El combinado reproduce EXACTO lo validado: **Sharpe 1.13 · ann 15.7% · maxDD −11.6% · 67% meses+.**
- Por qué net-long en $ con β≈0: los longs son de BAJO beta (TRX β=0.13, el long más grande), el
  hedge BTC compensa, y `trend` es long-only POR DISEÑO (overlay #5, ya en e14). Todo coherente.
- (El `Σ w·β=+0.32` que calculé y me asustó usa el β rolling de la ÚLTIMA barra, ruidoso; el β
  realizado de 4.4a es +0.05. La verdad de largo plazo es la segunda.) **NO se toca nada de prod.**
- LECCIÓN: net-en-dólares ≠ β-neutralidad. No volver a confundirlas.

### Estado verificado (todo OK)
- Push de la sesión previa YA estaba hecho (commit `front` en origin/main). Pendiente #1 cerrado.
- **"equity plano = 5000" era artefacto de logs LOCALES viejos.** La VM (dashboard live) muestra
  equity VIVO ~4933, heartbeats moviéndose, posiciones source="real" con PnL. Falso problema.
- Repo limpio: `.gitignore` OK, `kepler.db`/`data/`/`logs/` no trackeados ✅.

### E15 — Monitor de riesgo intradía: BLOQUEADO (necesita backtester horario)
- `research/e15_intraday_monitor.py` (v1 y v2). v1 neteaba pesos (bug); v2 lo corrige combinando
  retornos por sleeve. **Pero NINGUNA reconstrucción HORARIA reproduce el edge diario** (baseline
  horario ~−0.28 vs +1.04 diario): marcar a mercado hora-a-hora ≠ el retorno-forward-24h del motor.
- ⇒ Para evaluar el monitor con rigor hace falta **primero un backtester horario fiable**
  (mini-proyecto). Pendiente #3 BLOQUEADO por eso. La teoría ya lo desaconseja (CLAUDE.md).

## CHANGELOG 2026-05-29/30 (sesión previa)

### Arranque en demo (resuelto)
- Bug `KEPLER_DRY_RUN` con **comentario inline** en `/etc/kepler.env`: systemd no separa el `#`, así
  que el valor era `"false   # ..."` ≠ `"false"` → seguía en DRY_RUN. **Fix:** `execution._envstr()`
  limpia comentarios/comillas; y se limpió el `.env`. Lección: **NO poner comentarios inline en el .env**.
- Bug git "dubious ownership" en deploy: repo de root, deploy como `opc`. **Fix:** `deploy.sh` y
  `setup_vm.sh` ahora añaden `safe.directory` y hacen `chown` al usuario de sudo.

### Apalancamiento 20x → 3x (seguridad, NO toca rentabilidad)
- Binance dejaba 20x por defecto por símbolo. **Fix:** `execution.set_leverage(sym, LEVERAGE_SETTING=3)`
  se llama al inicio del rebalanceo. Solo cambia margen/buffer de liquidación; el tamaño lo fijan los pesos.
  Configurable por env `KEPLER_LEVERAGE` (default 3).

### Mejoras de frontend (a partir de fallas que reportó Oscar)
- **Heartbeat cada 15 min** en `orchestrator.py` (`HEARTBEAT_MIN`): registra equity sin rebalancear →
  la curva del dashboard ahora crece (antes solo 1 punto/24h). Tabla nueva `equity_tick` en `db.py`.
- **Rentabilidad total + Hoy**: métricas nuevas en el header (coloreadas). `db.upsert_equity_daily()`
  calcula retorno del día vs día previo + drawdown. Endpoint `/api/daily`.
- **Tabla "Rentabilidad por día"**: Día · Equity cierre · Retorno (verde/rojo) · Drawdown.
- **Tabla de posiciones = REALES de Binance** (no el objetivo): Activo · LONG/SHORT · USD sin lev ·
  PnL en vivo, vía `execution.get_positions_detail()`. Si aún no hay fills, muestra el objetivo con aviso.
- Gráfico **actualiza en sitio** (sin parpadeo), página refresca cada 10s, curva +1 punto/15min.

### Archivos tocados hoy (para el commit)
`kepler/execution.py`, `kepler/db.py`, `kepler/orchestrator.py`, `kepler/api/app.py`,
`kepler/api/dashboard.html`, `deploy.sh`, `setup_vm.sh`. (CLAUDE.md y STATUS.md nuevos.)

---

## PENDIENTES (próximas sesiones, en orden)
> Roadmap completo en `ROADMAP.md`. Empezar la próxima sesión leyendo este STATUS + ROADMAP.

### ⚠️ VERIFICAR AL ARRANCAR (antes de tocar nada)
- **0a. Demo viva con la versión nueva (desplegada 2026-06-02):** en la VM `journalctl -u kepler -n 50` →
  buscar `lev≈2.16x(maxDD-10%)`, β real en el snapshot, heartbeat `cb=OK`, rebalanceo a las 14 UTC.
  Dashboard http://213.35.121.9:8080. Confirmar que NO hay XLM/HBAR/LIT y que ZEC sí está.
- **0b. Acumulación de datos:** ¿hay varios ciclos con fills y `slip_bps`? (para C3). Pedir a Oscar la
  `kepler.db` de la VM si ya pasaron días → correr `python -m research.e21_fill_slippage <ruta_db>`.
- **0c. Estado esperado:** **29 perps · 7 sleeves · ancla −10% · lev ~2.16x · haircut 0.95 · trend cap 0.25
  · carry suavizado 7d · rebal 14 UTC · CB en heartbeat.** maxDD a vigilar (validación en curso).

### 🧭 RUTA ACORDADA (2026-06-01, orden de evaluación) — reemplaza el "menú agotado" de abajo
> Workstream de régimen CERRADO a fondo (R0+R1 lab + R2 actuales + R3 descartados → el conditional
> timing DISCRETO no sobrevive OOS honesto aquí; lab `research/regime_lab.py` queda reutilizable).
> Doctrina permanente (memoria `kepler-conditional-signals-open`): **núcleo fijo + satélites
> condicionales**; evaluar SIEMPRE la versión condicional de cada candidato nuevo, con disciplina.

1. **TVL → decisión sleeve #8** (lo más maduro). Analizador **LISTO**: `research/e33_shadow_tvl_analyze.py`.
   Logging de sombra **verificado suficiente** (pesos+hedge BTC+asof; nada que implementar en la VM).
   → Cuando Oscar traiga la `kepler.db` de la VM con **≥60-90 días** de sombra: `python -m
   research.e33_shadow_tvl_analyze <ruta_db>` → (b) chequear coste taker (e30b-style) → (c) promover a
   sleeve #8 (alphas.py + engine.SLEEVES) SOLO si el Sharpe realizado confirma. Bonus e32: el TVL raw
   sobrevive el walk-forward purgado (+0.30 Sharpe OOS) → más sólido que la iliquidez.
2. **C1 — factores académicos** → **AGOTADO (2026-06-01).** **SIZE archivado** (e34/e35): universo de
   perps líquidos comprime la dispersión de tamaño (premium SMB vive en microcaps que no operamos) +
   solapa con lowvol (corr 0.61) → OOS purgado ΔSharpe −0.50, 1/6 folds; el régimen no lo rescata.
   **CTREND desaconsejado** (28 indicadores precio/volumen + ML = "más precio", alto solape con
   mom/trend/hlpos, overfit). 📚 **Aprendizaje:** los factores de precio/mcap ya están cubiertos; el
   edge nuevo exige FUENTES nuevas (on-chain), no más precio. (Datos: CoinGecko cerró API pública sin
   key; se usó CoinPaprika gratis sin key + aproximación mcap·ratio-de-precio.)
2b. **BLEND on-chain+cola+liquidez → MEJOR CANDIDATO, en SOMBRA (2026-06-01).** {lotería+tvl+illiq}:
   OOS +0.34/6-6, taker +1.55%/mes, full-history, validado (e40/e41). Montado en sombra (`run_blend_shadow`,
   PENDIENTE DEPLOY). → Acumular ≥60-90d → `python -m research.e33_shadow_tvl_analyze <db> blend_lottery_tvl_illiq_v1`
   → si el Sharpe forward confirma (y la lotería-60d no fue overfit) → promover a sleeve #8.
4. **Dune/Flipside netflow reconstruction** — proxy GRATIS (signup key) antes de pagar CryptoQuant. DESPRIORIZADO:
   el blend on-chain ya captura buena parte del edge on-chain gratis y sin la ingeniería cross-chain.
5. **🌃 RUTA B INTRADÍA — avance 2026-06-01 noche (backtester horario e42/e44 MONTADO y aplicado):**
   - ✅ **Order-book intradía → DESCARTADO** (e45): edge real pero coste×turnover lo mata a todo hold/
     signo/banda (mejor −0.89 Sharpe a taker+ADV). Rama cerrada con números.
   - ✅ **Liquidaciones → DESCARTADO** (e46-49, Coinalyze gratis): intradía bloqueado por dato; diario
     gratis completo pero el edge era **ZEC (1 coin)** → sin ZEC nada (precedente e17/AXS). Rama cerrada.
   - ✅ **Regla universo por-sleeve aplicada a los 7** (e50) → **ningún cambio** (los 7 ya usan bien todas
     las monedas; excluir empeora OOS). Regla queda como diagnóstico permanente (`kepler-per-sleeve-universe-rule`).
   - **Ruta B intradía — TODO lo evaluable está CERRADO:** order-book ✗ (e45), liquidaciones ✗ (e46-49),
     CME gap ✗ (e73), monitor e15 ✗ (evaluado, CB en heartbeat ya desplegado). NADA pendiente intradía.
   - **"UNIVERSO LIMPIO" → CERRADO (e74):** barrido LOO sobre las 20 coins → el universo YA está limpio por
     el lado del costo (las de slippage alto tienen edge que lo paga). Las "retirables" (LTC/SOL/ADA) son
     majors líquidas = overfit de P&L pasado → NO retirar. Sin acción.
   - **⇒ RUTA B INTRADÍA COMPLETAMENTE AGOTADA.** order-book✗ liquidaciones✗ CME✗ e15✗ universo-limpio✗.
   - (Parado, NO pendiente activo) Colector intradía hacia adelante (liquidaciones 1h/WS) — solo si se
     decide invertir meses en acumular dato intradía inexistente gratis.

### 📌 RECORDATORIO — MENÚ DE CONDICIONES (hacer DESPUÉS de #2 y #4) — vía `regime_lab`, con disciplina
> Pedido de Oscar (2026-06-01): mantener abierto el rescate por condición específica. Probar cada una
> con PRE-REGISTRO + deflación + walk-forward purgado + validación forward (no sweeps masivos).
- ~~CME gap~~ → **DESCARTADO (e73):** el fade pierde en todos los horizontes (Sharpe<0). No re-litigar.
- **Fechas macro** (FOMC/CPI), **funding extremo**, **vencimiento de opciones** (ojo: e28 ya lo halló artefacto).
- Cualquier "pista" nueva de señal que rinda **solo en condiciones específicas** → directo al lab.

5. **Backtester horario** — AL FINAL, cuando no quede nada en el nivel diario (decisión de Oscar). Llave
   común de intradía: order-book (e24), liquidaciones (Coinalyze, gated), CME gap, monitor de riesgo (e15).


### 📋 REVISAR INFORMACIÓN PAGADA (lista viva — política Oscar 2026-05-31)
> Regla (memoria `kepler-free-data-first-policy`): NO descartar una fuente prometedora por ser de pago.
> Primero agotar lo gratis (sondear varios sitios, registrarse si hace falta); si la única vía es pago,
> registrar aquí CON dónde nos quedamos y qué falta, para retomar sin re-investigar. Priorizar por aporte/costo.

| Fuente | Qué da (edge) | Vía gratis (agotada) | Proveedor pago | Costo aprox | Dónde retomar / qué falta | Prioridad |
|---|---|---|---|---|---|---|
| **Netflows exchange por token** | on-chain cross-seccional ideal: cuánto de cada alt entra/sale de exchanges. **Edge on-chain CONFIRMADO** por el proxy TVL gratis (e26/e27: +0.6%/mes taker, ortogonal, sólido 2023+) | DefiLlama TVL = proxy parcial (solo 12 cadenas/protocolos, point-in-time imperfecto). Netflow directo NO hay gratis | **CryptoQuant Pro ~$99/mo (anual)** = mejor fit (Data API 24H incl.) · Santiment Pro ~$50/mo · Glassnode $999/mo+API = overkill | **~$99/mo** (verificado may-2026) | Suscribir CryptoQuant Pro → netflow per-token (32 nombres) → sleeve cross-seccional como e26/e27 con dato limpio (point-in-time honesto). **BONUS:** la sub abre un menú entero (reservas, ballenas, SOPR, stablecoins, mineros…) = varios candidatos a sleeve (camino RenTech §A) | **ALTA** (la veta diaria viva más prometedora; ROI alto si valida) |
| **Liquidaciones** | cascadas de liquidación → señal contrarian/mean-reversion | Binance retiró `allForceOrders`+`liquidationSnapshot`. **⚠️ NO agotado lo gratis: Coinalyze tiene API gratis con histórico de liquidaciones** — CHEQUEAR profundidad histórica antes de marcar pago | Coinglass (si Coinalyze gratis no alcanza) | ~$29-79/mo Coinglass | (1) probar Coinalyze gratis a fondo; (2) su edge es **intradía** → requiere backtester horario (`INTRADAY.md`) igual | MEDIA (gated por intradía; quizá gratis) |

### 🎯 FOCO PRÓXIMA SESIÓN: el MENÚ DIARIO BARATO está AGOTADO → 4 caminos (decisión de Oscar)
Directiva de Oscar (2026-05-31): "más fuentes para mejorar rentabilidad." **Recorrido COMPLETO esta
sesión** — todas las vetas de señal DIARIA gratis evaluadas: precio/OHLCV ✗, positioning ✗, basis ✗
(e22), universo ✗ (e17), **order-book diario ✗ (e24, edge intradía)**, **opciones Deribit ✗ (e25,
BTC/ETH-only)**, **on-chain TVL ~ (e26/e27: real pero modesto +0.6%/mes)**, **estacionalidad ✗ (e28)**.
No queda fruta diaria barata. Los 4 caminos REALES que quedan:

1. **Netflow on-chain de PAGO** (Glassnode/CryptoQuant) — JUSTIFICADO: el TVL gratis probó que el on-chain
   tiene edge (+0.6%/mes ortogonal); el netflow sería más limpio (point-in-time honesto) y para los 32
   nombres. Requiere suscripción de Oscar. Ver lista "REVISAR INFORMACIÓN PAGADA" arriba. ← mayor upside diario.
2. **Backtester horario (intradía)** — mini-proyecto que desbloquea order-book intradía (Sharpe 7-9 sin-lag),
   liquidaciones intradía y el monitor de riesgo (e15). Llave común. Ver `INTRADAY.md`. ← mayor upside total.
3. **A3 free-TVL a producción** — validar `tvl_pxdiv_14d` con walk-forward+purga (B1) + demo y, si aguanta,
   meterlo como sleeve #8 (+0.6%/mes). Es modesto pero real y GRATIS. ← el upside seguro/barato.
4. **B1/B2 endurecer validación + dejar correr la DEMO (E1)** — no suben el número pero lo hacen creíble;
   la demo es el foso real (tiempo). ← lo que más valor de producto da aunque no sea "nuevo edge".

*LECCIONES de la tanda (criba para futuras fuentes): fuentes BTC/ETH-only (basis, opciones) NO sirven
(no cross-seccional); señales market-wide caen en el gate-de-régimen descartado (DVOL, estacionalidad);
sleeves orto pero débiles (order-book Sharpe 1.3) DILUYEN al ancla. Lo viable = per-símbolo del universo
+ ortogonal + fuerte para subir el retorno a maxDD fijo con costos taker. Chequeo barato de ortogonalidad
(e22/e23/e25/e26/e28) ANTES de bajar histórico. Y siempre: gratis primero, pago a la lista (no descartar).*

### EN PARALELO — DEJAR CORRER LA DEMO (el foso real = tiempo, E1)
- Validar en vivo que el carry suavizado baja el turnover; medir Sharpe REAL vs 2.07; alimentar C3.
- **B1/B2 — Purga+embargo / CPCV** en el walk-forward: hace el OOS más honesto (no sube el número).

### BLOQUEADO / DESCARTADO (no re-litigar sin algo nuevo)
- Monitor riesgo intradía → BLOQUEADO (e15: falta backtester horario). **Mismo prerequisito que
  desbloquearía el order-book/liquidaciones intradía** → el backtester horario es la llave común.
- Ampliar universo (e17/e17b), OHLCV derivados (e16), OI/long-short (e16f), **basis≈carry (e22)**,
  **order-book diario (e23/e24)**, **opciones Deribit (e25)**, **estacionalidad (e28)** → no aportan al
  ancla. Liquidaciones → sin histórico gratis. On-chain TVL (e26/e27) → real pero modesto (+0.6%/mes).

### MENOR
- heartbeat a 5min si se quiere curva más fina (ahora 15min).
- Cuando haya track record real → evaluar tier BALANCEADO (decisión de Oscar).

### REGLA DE PROCESO (recordatorio para mí, Claude)
- No documentar/preguntar con números sin verificar (pasó varias veces hoy; las cancelaciones
  evitaron commitearlos). Completar el backtest ANTES de afirmar. Antes de cualquier deploy a la VM,
  listar cambios y esperar OK de Oscar. Ver memorias `kepler-verify-before-documenting`, `deploy-confirm-changes-first`.

## RECORDATORIO PERSISTENTE
- Oscar debe **retirar $1800 de Brayan / Btc-Panda** (martingala 20x, ruina probada en research/e13).
