# KEPLER — Estado vivo · Changelog · Pendientes
> **Empieza cada sesión leyendo este archivo.** Última actualización: **2026-05-30** (tarde-4, hora Lima).
> **Roadmap de mejora del sistema: `ROADMAP.md`** (faro Medallion/RenTech).

---

## ESTADO ACTUAL
- ✅ Sistema **desplegado y operando en DEMO** en la VM (Oracle, `opc@oscar-cripto-sentinel-b26`).
- ✅ Servicios `kepler` y `kepler-api` **activos**. Dashboard live OK en http://213.35.121.9:8080
  (verificado 2026-05-30: equity vivo ~4933, 14 posiciones source="real" con PnL, heartbeats fluyendo).
- ✅ Circuit breaker activo (halt a −20% del pico). Alertas ntfy configuradas.
- ✅ **β-neutralidad auditada (2026-05-30): β combinado = +0.05.** El "76% net long en dólares" es
  esperado (longs bajo-beta + hedge BTC + trend overlay), NO un fallo.
- ✅ **7 sleeves** (+`takerflow_5d` +`hlpos_14d`) + **ancla de maxDD −10%** (leverage auto = 1.92x):
  motor da **ann 42.2% (~3.52%/mes) · maxDD −10.0% · Sharpe 1.94 · β +0.028 · 69% meses+**.
  Pendiente validar en DEMO.
- ✅ Cambios previos (leverage 3x + frontend) ya en origin/main. Falta confirmar `deploy.sh` en la VM.

---

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
- **0a. VM/demo viva:** en la VM `journalctl -u kepler -n 50 --no-pager` → buscar línea reciente con
  `lev=1.92x(maxDD-10%)` y `target=~19pos`. Confirma que los **7 sleeves + ancla** corren en vivo.
  (Hoy NO se verificó en logs — el dashboard mostraba aún el ciclo viejo de 5 sleeves al cerrar.)
- **0b. Dashboard:** http://213.35.121.9:8080 → el panel "backtest" debe decir **Sharpe 1.94 / maxDD −10**
  (no 1.13/−11.6). Si dice lo viejo, falta `deploy.sh` en la VM con commit `cde862f`+ (Oscar despliega).
- **0c. git:** repo limpio, `main`==`origin/main`. Último commit sesión 2026-05-30: **`e3d29d5`**.
- **0d. Estado esperado:** **32 perps · 7 sleeves · ancla −10% · lev ~1.92x**. NADA pendiente de
  implementar en código — lo de hoy ya está. Lo nuevo es research (C1).

### EN MARCHA (research puro, NO requiere tiempo de mercado — AHORA)
1. **C1 — Slippage realista por liquidez** (ROADMAP §C1): reemplazar el costo plano (~2bps) por uno
   función de la liquidez/ADV de cada símbolo. Re-evaluar los 7 sleeves. **Bajará el 1.94 → es lo
   que se busca: acercar el backtest al número real.** ← SIGUIENTE.
2. **B3 — Deflated Sharpe Ratio** (ROADMAP §B3): penalizar el Sharpe por el nº de configs probadas
   (~22 experimentos). Dice cuánto del 1.94 es señal vs suerte. Número creíble.
3. **A4 — Cross-exchange basis** (perp vs spot) como sleeve nuevo de fuente genuina (ROADMAP §A4).

### DEPENDE DE TIEMPO EN MERCADO (el foso real — track record)
4. **Dejar correr DEMO semanas** → medir Sharpe REAL vs 1.94 backtest. **El número honesto.**
5. Cuando demo confirme → evaluar paso a REAL con capital chico (decisión de Oscar).

### BLOQUEADO / DESCARTADO (no re-litigar sin algo nuevo)
- Monitor riesgo intradía → BLOQUEADO (e15: falta backtester horario que reproduzca el edge).
- Ampliar universo (e17/e17b), OHLCV derivados (e16), Open Interest/long-short (e16f) → no aportan.

### MENOR
- heartbeat a 5min si se quiere curva más fina (ahora 15min).
- Cuando haya track record real → evaluar tier BALANCEADO (decisión de Oscar).

### REGLA DE PROCESO (recordatorio para mí, Claude)
- No documentar/preguntar con números sin verificar (pasó varias veces hoy; las cancelaciones
  evitaron commitearlos). Completar el backtest ANTES de afirmar. Antes de cualquier deploy a la VM,
  listar cambios y esperar OK de Oscar. Ver memorias `kepler-verify-before-documenting`, `deploy-confirm-changes-first`.

## RECORDATORIO PERSISTENTE
- Oscar debe **retirar $1800 de Brayan / Btc-Panda** (martingala 20x, ruina probada en research/e13).
