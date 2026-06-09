# KEPLER — MONITOREO / BITÁCORA OPERATIVA
> **Documento vivo.** Para vigilar el avance del sistema en vivo (DEMO→REAL), detectar problemas/bugs,
> y registrar qué criterios afinar / eliminar / potenciar. Complementa `STATUS.md` (changelog de research)
> con la operación del día a día. **Lee también:** `ROADMAP.md` (plan), `INTRADAY.md` (frontera futura).
>
> Misión recordatorio: **copy-lead honesto de bajo drawdown**. Lo que se vigila aquí no es el ROID
> llamativo, sino **supervivencia, bajo maxDD, consistencia y ejecución limpia**.

---

## 1. EL REPORTE DIARIO (`daily_report`) — qué trae y cómo leerlo
Lo genera el orquestador cada ciclo (`orchestrator._save_daily_report`) y se descarga en el log diario
(botón "log de hoy") y en el histórico. Campos de `metrics` + cómo interpretarlos:

| Campo | Qué es | 🟢 sano | 🔴 alerta (investigar) |
|---|---|---|---|
| `today_return_pct` | retorno del día (wallet) | ruido ±1-2% | caída fuerte sin causa de mercado |
| `drawdown_pct` | dd desde el pico | > −6% | **< −10%** (acerca al ancla) · **< −20%** = CB |
| `n_positions` | posiciones objetivo | ~16-22 | < 10 (poca diversificación) |
| `gross` | exposición bruta (Σ\|w\|) | ~0.8-2.0 | > 2.0 (MAX_GROSS) |
| `net` | exposición neta en $ | net-long chico OK (β≈0) | net muy grande (revisar β) |
| `leverage` | leverage de estrategia (ancla) | ~2.0x (ESTABLE) | salto brusco sin cambio de tier |
| `top_position` | mayor posición | < 15% | **> 20%** (concentración 1 nombre) |
| `slippage_real` | slip de fills de hoy (C3) | mediana < 5 bps | **mediana > 10 bps** (ejecución cara) |
| `cycles_today` | nº de rebalanceos hoy | 1 (cadencia 24h) | **≥3** = tormenta de reinicios/deploys |
| `cb_operate` | circuit breaker | `true` | `false` = HALT (equity −20% del pico) |

**Narrativa**: una línea resumen legible (la misma info). Ej:
`DEMO ESTABLE · $4942 (+0.06% hoy, dd 0.00%) · 20 pos gross 1.85 net +0.41 lev 2.01x · slip med 1.5bps (peor ZEC 9.4) · 2 ciclos hoy · CB OK`

---

## 2. CRITERIOS A VIGILAR (watch-list operativa)
Cada uno: qué es, por qué importa, y qué hacer si se dispara.

1. **Concentración (top_position) — MITIGADA con cap 0.25 en trend (e52, 2026-06-02).** Antes TRX ~20%
   (78% era `trend` long-only). Ahora `engine.trend_sleeve` capa cada coin a `MAX_WEIGHT_NORMAL=0.25` →
   **TRX 20%→~10%, HHI −34%** (Sharpe combinado intacto). OJO: tras retirar finas + haircut 0.95 el lev
   subió a 2.16x y TRX rebotó a **~14%** (sigue <15%; el cap lo contiene). **Vigilar `top_position`:** si
   supera ~15-18% sostenido = apilamiento multi-sleeve (el cap es por-sleeve, no agregado) → evaluar cap
   AGREGADO al target o bajar el cap de trend. **Pendiente deploy.**
2. **Slippage real (C3).** 2 días: **mediana ≈ −1 a +1.5 bps (favorable/barato)**, media 1.3–3.3 (la
   inflan 3-4 thin coins). **Patrón firme: el coste vive en las monedas FINAS** (XLM hasta +51.8, HBAR
   +21.6, ZEC, LIT). **Acción:** acumular → `research/e21_fill_slippage` → recalibrar K de e18 → costo
   real. **Conexión estratégica:** alimenta la idea de Oscar de RETIRAR monedas — un coin fino que aporta
   poco edge pero cuesta 20-50 bps de slippage podría no compensar. Si la mediana global sube > 10 bps
   sostenido, la ejecución maker se degrada (revisar no-fills/GTX).
3. **Ancla de leverage vs maxDD real (e29 → RESUELTO, e51+e52+e53).** El ancla sobre-apalancaba (walk-forward
   maxDD OOS −13.5% vs −10%). **Doble arreglo:** (a) `LEVERAGE_HAIRCUT` recorta el lev; (b) limpiar el libro
   (trend capado + sin finas) bajó el maxDD OOS a **−7.1%** de raíz → el haircut se relajó a **0.95** (lev
   vivo ~2.16x, maxDD IS −9.5%). **Vigilar `drawdown_pct` en vivo:** el lev vivo (2.16x) sale > el del
   backtest (1.88x) porque el ancla es sensible a la muestra (datos recientes calmos). Si en DEMO el maxDD
   real se acerca a −10% con holgura, endurecer el haircut; si queda cómodo, se puede subir. NO subir de tier aún.
4. **Tormenta de reinicios (cycles_today).** Cada reinicio del servicio dispara un ciclo inmediato →
   rebalanceo extra = turnover/costo extra. En días de deploy es normal (hoy 3 ciclos). **Acción si
   persiste sin deploys:** revisar por qué se reinicia `kepler.service` (journalctl).
5. **β real del libro (D1 resuelto, e51-sesión).** El snapshot ya reporta la **β de regresión**
   (modelo +0.025 hoy; pasa a **realizada** de la equity en vivo a ≥20 días) → confirma neutralidad
   ≈+0.05. Vigilar que la **realizada** se mantenga |β|<~0.15 cuando active. Diagnóstico **β-dólar**
   (`detail.beta_dollar`, ~+0.45): exposición direccional del notional, la genera `trend` long-only;
   si crece mucho = más beta-de-mercado latente (cruzar con la concentración de TRX).
6. **Equity ilegible / balance falso.** Ya blindado (heartbeat y ciclo OMITEN si el balance no se lee, no
   inventan 5000). Si ves escalones planos a 5000 exactos → regresión de ese fix.
   **✅ RESUELTO (2026-06-04, confirmado vivo 06-05):** la curva ya es **MTM** (`totalMarginBalance`, `5152e7e`).
   Verificado en el log 06-04→06-05: los ticks varían continuamente tras las 14 UTC (ya no plana a 7 decimales).
   El maxDD del heartbeat ya refleja el PnL no realizado → track honesto. (Histórico del bug: §bitácora 06-04.)
   ⚠️ **NUEVO (2026-06-06): `get_balance()` devuelve `None` de forma INTERMITENTE** → audit `Ciclo omitido:
   balance ilegible` (4× en el log 04→06, agrupado ~13:20-13:50 UTC, antes del rebal). El diseño OMITE+reintenta
   (sano, sin churn) y el 05-06 se recuperó; pero **(a)** es fragilidad de la API Demo de Binance y **(b)** el
   **monitor NO cuenta ciclos omitidos** = si la API queda ilegible toda la ventana, se pierde el rebalanceo del
   día EN SILENCIO. **✅ Fixes operativos IMPLEMENTADOS (2026-06-06, local, PENDIENTE push+deploy; Fase 1, sin
   backtest):** (1) `execution.get_balance(retries=3, backoff_s=1.0)` reintenta con backoff antes de `None`
   (absorbe el parpadeo); (2) `orchestrator.run` escala a `WARNING` "Rebalanceo en riesgo" + ntfy a
   `SKIP_ALERT_THRESHOLD=3` omisiones seguidas (~45min) y avisa al recuperar, + regla `cycles_today==0`→CRIT en
   `monitor.py` (tapa el rebalanceo perdido en silencio); (3) `checks.check_drawdown` corre en el HEARTBEAT (cada
   15min, `DD_WARN=8%/DD_CRIT=10%` sobre el equity MTM vivo, pico de `equity_daily`) → caza el acercamiento al
   ancla sin esperar al snapshot 14:00; `monitor.py` regla #2 ahora usa la PEOR de (snapshot, `live.maxdd_intraday`),
   la #8 quedó subsumida. **Al desplegar saltará UN ntfy WARN cuando la curva MTM cruce −8%** (hoy −7.97%) — deseado.
7. **Circuit breaker.** `cb_operate=false` = HALT por −20%. Debe ser rarísimo en ESTABLE. Si salta,
   investigar a fondo (no debería con maxDD objetivo −10%).

---

## 3. BITÁCORA (registro por día — el más nuevo arriba)

### 2026-06-09 (🟢 MODO LOW-BARRIER diseñado, validado y GO-LIVE en real $298)
- **Problema resuelto:** el min-notional × nº-posiciones era la barrera del copiador (~$7k full-20). e76 (frontera
  nº-pos) + e77 (universo barato + β-hedge entre coins, idea de Oscar) + e78 (validación ruta producción) →
  **universo de 13 coins de $5, β-neutralizado entre ellos, dropping adaptativo al capital. Sharpe 1.48 (=full-20),
  1.98%/mes, maxDD −9.5, β −0.01, barrera ~$300.**
- **Implementado en producción:** `config.LOW_BARRIER_MODE=True` · `kepler/lowbarrier.py` · branch en `engine` ·
  `execution._capital_aware_drop` (suelta patas < min-notional al capital vivo, renormaliza a igual gross → libro
  adaptativo: $300→~10 patas · $1000→12 · $1500→13). El drop corre ANTES del DRY → el papel previsualiza el libro real.
- **GO-LIVE 15:26 UTC (proceso disciplinado):** DRY_RUN en VM primero (cero riesgo) → REAL. Sub-cuenta $298,
  `migrate_to_real` (baseline limpio, 980 sombras conservadas), force rebal. **1er ciclo: 12-pos cheap, órdenes LLENAN
  sin −4164/−401, β −0.011, lev 1.18x, huérfanas (BTC/BCH/ZEC/XRP) cerradas, CB OK. Track real arranca 2026-06-09.**
- **🟡 PUNTO A VIGILAR (mañana):** slippage 1ª build **6.5bps med · peor NEAR 31.15** = coste one-off de armar el libro
  desde plano (cruza spreads). Debe BAJAR a ~4bps en ciclos incrementales. Si persiste alto en coins líquidos → investigar
  (no-fills/GTX, o que el universo barato tenga peor microestructura de lo modelado). β-dólar snapshot 0.24 (net-long inicial).
- **🟢 Adaptación del producto al capital confirmada en vivo:** a $298 operó 10 patas, todas ≥ min-notional, sin error.

### 2026-06-08 (🔴 CAÍDA DEL DEMO + migración a REAL + PAUSA por decisión de producto)
- **INCIDENTE EXTERNO — la cuenta Demo de Binance caducó.** Desde **06-08 02:32 UTC**, `get_balance()` → `None`
  sostenido. Raíz: `GET /fapi/v2/account` → HTTP 400 **`{"code":-1109,"msg":"Invalid account"}`**. La key se reconoce
  (key basura da -2015), pero la **cuenta demo ya no existe** del lado de Binance (las cuentas Demo Trading caducan/se
  resetean). Reloj VM OK (deriva 39ms). Mismo -1109 desde 2 IPs → no es la VM. **Reactivar demo + regenerar keys NO
  lo arregló** (-1109 persistente). **Nuevo modo de fallo, distinto del parpadeo `None` intermitente: es un rechazo
  DURO y persistente.**
- **El sistema aguantó perfecto:** balance ilegible → ciclos omitidos (0 churn, libro intacto) → alarma de escalada
  disparó a los 45min (Fix #1/#2 del 06-06 funcionando en un caso real). PERO: ~14h sin rebalancear y el monitor diario
  NO lo gritó (solo la escalada). **Punto ciego confirmado** (ver §4 BUGS).
- **Síntoma que vio Oscar:** dashboard mostraba métricas del domingo estando lunes = no se generó `daily_report` del
  lunes (el rebal nunca corrió) → la UI se congela en el último día bueno. **Lección de lectura: "UI atrasada un día"
  casi siempre = el rebalanceo de hoy no corrió, no un bug de fecha.**
- **Migración a REAL:** sub-cuenta Binance dedicada ($ aislado), keys reales (Futuros ON / retiros OFF / IP-whitelist),
  `USE_DEMO=false`, `CAPITAL_USD`→1200, `TRACK_INCEPTION=2026-06-08`. `migrate_to_real.py` archivó el demo y reseteó la
  DB operativa conservando sombras. Pelea de permisos: faltaba **"Enable Futures"** en la key (leía pero no operaba, 401).
- **🟡 HALLAZGO QUE PARÓ TODO — min-notional Binance:** `-4164 "notional ≥ 20"`. Mínimos: **$5 (23 símbolos) · $20 (5,
  incl. ETH) · $50 (BTC)**. A $250 las 18 patas no entran → libro concentrado. Floor libro completo ≈ **$1000-1500**.
  **Oscar señaló el problema de producto:** ese floor = **barrera de entrada del copiador** (depende de nº-posiciones,
  no de nuestro capital) → 18 patas = techo de afiliados ~$1000 permanente. **DECISIÓN: no fondear; backtestear el nº
  mínimo de posiciones que preserva el edge.** Servicio PARADO, posiciones parciales cerradas (no cuentan).

### 2026-06-05 (DEMO — revisión diaria: las 4 verificaciones cerraron; crash continúa, sistema sano)
- **✅ POST-DEPLOY 06-04 VERIFICADO AL 100%** (log 06-04→06-05): `cycles_today`=**1** (churn cerrado),
  bloque `costs` poblado (fees $0.33 · funding $1.77 · realizado −$31.61), `monitor` severity **OK** (flags []),
  curva **MTM viva** (ticks varían continuamente tras 14 UTC; ya no plana). Checks/concentración/CB todos OK.
- **📉 maxDD −7.5% desde pico** (4943.69 05-31 → 4571 06-05). Caída 06-04 −$206 = **~−$34 realizado (17%) +
  ~−$172 MTM (83%)** → **mercado, no avería**. Y **dentro del backtest** (maxdd −7.3/−10): drawdown de tamaño
  normal, llegó rápido por coincidir con el crash. Dentro de presupuesto −10%, lejos del CB −20%.
- **🎯 Causa = tilt net-long** (β-dólar +0.24, β-modelo ≈0): longs de trend NEAR/BCH/TRX/ZEC/BTC ~−188 USD vs
  shorts juntos ~+92. Los shorts SÍ funcionan; el peso net-long es el que muerde. (estructural, ya documentado).
- **⚠️ Slippage: un fill feo BCH SELL +185 bps** (245.06 vs ref 249.69) = grueso del realizado −$31.61; mediana
  sana −1.37 bps. Patrón conocido (coste en momentos ilíquidos/finos). Un dato; si se repite en crashes → banda no-trade.
- **🛑 PREGUNTA OSCAR: "¿detectar el crash y shortear en auto?"** = market timing → **DESCARTADO** (gate régimen/
  carry-breadth empeoraron maxDD; timing discreto falló 3x). Falla por shortear tarde + rebote en V. Kepler es
  β-neutral por diseño. Palanca legítima ≠ timing: **reducir β-dólar**.
- **🔴 e71+e72 DOLLAR-NEUTRALIZACIÓN — NO DESPLEGAR (e71 fue falso positivo; el walk-forward e72 lo revirtió):**
  cancelar λ de la β-dólar con hedge BTC + re-anclar a −10%. e71 (split simple + lev sobre toda la muestra =
  lookahead) decía "λ≈0.5 mejora retorno"; **e72 walk-forward (train 365d · embargo 14d · test 90d · lev anclado en
  train) gana λ=0**: Sharpe 1.77/3.11%/mes vs λ=0.5 1.66/2.85% (−8%). Neutralizar SOLO baja la β (+0.19→+0.09), CUESTA
  retorno. **El net-long es prima de riesgo = precio del edge (como la concentración, e60); no se toca.** Salida viva:
  λ=0.25 como palanca de PRODUCTO (β casi gratis) si Oscar quiere menos-β para copy-lead; aparcada. Detalle en
  `STATUS.md §2026-06-05`. **Lección: exigir walk-forward con lev anclado en train (split simple engaña).**
- **🟡 e73 VOL-TARGETING DINÁMICO — NO mejora retorno, pero rescata un dial de robustez (candidato PRODUCTO, NO
  desplegado):** escalar lev ∝ 1/vol realizada vs ancla estática (e68), walk-forward. Estático gana retorno OOS
  (3.42 vs ~3.0-3.2%/mes); pero `sim-40d` (lento) da mejor Sharpe (1.89), Calmar (3.20), menos maxDD (−13.9→−12.0),
  meses más consistentes, lev realista (máx 2.3x). Reduce el DESBORDAMIENTO del maxDD OOS (el estático se pasa a
  −13.9 vs −10 objetivo = sobre-apalancamiento de e29). Distinto del gate binario descartado (ese empeoraba maxDD).
  Win-rate por fold ≤46%. Detalle `STATUS.md §2026-06-05`. **VIGILAR si se despliega:** que el maxDD real OOS quede
  ≤ ancla y el turnover por ajuste de lev no dispare costes.

### 2026-06-04 (DEMO — FIX DE CHURN VERIFICADO EN VIVO + hallazgo equity-wallet)
- **VM confirmada en `HEAD c009226`** (incluye `2034e74` fix churn). El fix se desplegó ~16 UTC del 06-03.
- **✅ FIX DE CHURN FUNCIONA:** log del 06-04 (04:31–10:32 UTC) = **solo heartbeats, 0 ciclos** (`signals`,
  `portfolio_snapshot`, `audit`, `shadow` vacíos → aún no llega el rebal de 14 UTC). En ~18h post-deploy,
  **incluido el reinicio del propio deploy, NO se forzó ningún rebalanceo** (pre-fix habría disparado uno).
  `cycles_today`: **8 (06-02) → 2 (06-03 pre-fix) → 0 (06-04 post-fix hasta 14 UTC)**. Equity plana/+ (4868.08
  → 4869.86), sin escalones de churn. **PENDIENTE:** log post-14 UTC para ver el rebalanceo programado limpio.
- **🔴 HALLAZGO: `equity_tick` = wallet/realizado, no MTM** (ver §4, bug nuevo). Curva plana a 7 decimales por
  horas, escalones ~funding (00/08/16 UTC). maxDD intradía subestimado → arreglar antes del track real.
  **→ CORREGIDO Y DESPLEGADO mismo día** (`5152e7e`, `totalMarginBalance`). Al activarse destapó el dd real
  **−4.5% MTM** (la curva wallet escondía −$140 no realizado del crash). NO es pérdida nueva; es honestidad.
- **Reloj limpio del copy-lead arranca HOY (2026-06-04), post-fixes.** Gate: 0 incidentes 30d + costes≈backtest.
- **🌓 SOMBRAS (cadencia SEMANAL, code-first):** correr `e33` cada semana sobre la DB viva y comparar el Sharpe
  realizado (cuando ≥5-8 días; fiable ≥60) vs baseline (tx +1.46%/mes, mvrv +1.41%, tvl +0.6%). Comando VM:
  `source /opt/kepler-app/venv/bin/activate && cd /opt/kepler-app/kepler && D=$(python -c "import config;print(config.DB_PATH)") && for s in onchain_tvl_pxdiv_14d onchain_tx_pxdiv_14d onchain_mvrv_lvl blend_lottery_tvl_illiq_v1; do echo "== $s =="; python -m research.e33_shadow_tvl_analyze "$D" $s; done`
  Estado 06-04: 4 sombras al día, β-neutral, 2-4 días → SIN conclusión (esperado). Promoción a sleeve #8 no antes de ~8-12 sem.

### 2026-06-03 (DEMO — crash global cripto, día PRE-fix de churn)
- **🌍 CRASH GLOBAL:** BTC −22% intrasemana, ~$2.000M liquidaciones (≈$1.500M longs). **Kepler lo absorbió por
  β≈0:** equity de 4943 (pico 05-31) a 4860 (06-02) = **−1.7% maxDD**, ya recuperando (+0.17% el 06-03). El
  libro quedó **net-verde no realizado** (NEAR +$110, ZEC +$53 vs BCH −$72). El crash NO fue el problema.
- **⚠️ LA PÉRDIDA FUE CHURN, NO MERCADO:** el grueso del −1.7% es REALIZADO por sobre-rebalanceo del 06-02
  (8 ciclos por deploys del crash, fix aún no desplegado). El libro abierto está verde; el sangrado está en lo
  ya cerrado. **No confundir MTM no realizado (verde) con la pérdida en cuenta (realizada).**
- **2 ciclos (13:00 y 14:00 UTC), PRE-fix** (el de 13:00 es espurio, firma del bug). El deploy del fix fue
  después (~16 UTC), así que estos 2 ciclos NO testean el fix. Slippage limpio el 06-02 (mediana 0.65 bps).
- **Concentración:** TRX 15% (cap), NEAR 14.6%, ZEC 11.1% = ~41% del gross en 3 longs de trend. Vigilar.

### 2026-06-02 (DEPLOY del bundle riesgo/calidad + ejecución — VALIDACIÓN PENDIENTE)
Desplegados 2 commits (`e2f0505` + `55a429a`). Cambia el SIZING y CUÁNDO se rebalancea → el primer ciclo y
los siguientes días son de **validación**. **Checklist a verificar en los primeros ciclos en vivo** (aún sin
datos; rellenar al revisar logs):
- [ ] Universo: NO aparecen XLM/HBAR/LIT en señales/posiciones; ZEC sí. (El fix de huérfanas — nuevo,
      pendiente deploy — las cierra solas en el primer ciclo; hasta desplegarlo, cerrar a mano si molestan.)
- [ ] Leverage ~2.16x (sube vs 2.02x: haircut 0.95 sobre libro limpio). maxDD objetivo −10%.
- [ ] `top_position` (TRX) ~12-14% (cap 0.25 lo contiene; antes ~20%). Vigilar que no pase 15%.
- [ ] `beta` del snapshot = valor REAL (regresión, ~+0.025 modelo hasta ≥20d de equity; luego realizada).
- [ ] Rebalanceo se reordena a **14 UTC (09h Lima)** tras el ciclo de arranque (que va a la hora del deploy).
- [ ] Heartbeat loguea `cb=OK` (chequeo del CB cada 15min ahora activo; NO debe disparar con ruido).
- [ ] Sin errores, sin halts, sombras (TVL+BLEND) siguen registrando.
- **CLAVE a vigilar varios días:** que el **maxDD real** quede cómodo bajo −10% (el lev 2.16x sale del ancla
  sobre datos recientes calmos; e29 advierte que puede excederse). Si se acerca a −10% → endurecer haircut.

### 2026-06-01 (DEMO — sombras YA registrando en prod + slippage favorable)
- **2 ciclos** (20:15 y 23:16 UTC = 15:15/18:16 Lima) = reinicios por el **deploy de hoy** (sombras), no
  cadencia 24h. Ambos `Ciclo ESTABLE ok` (112s / 109s). Sin errores, CB OK, sin halts ni alertas.
- **🌓 SOMBRAS FUNCIONANDO EN VIVO (lo más importante):** TVL **13** + BLEND **23** posiciones registradas
  en AMBOS ciclos → **el reloj de los 60 días ya corre de verdad** (recordatorio ~2026-07-31). El BLEND
  loguea su libro β-neutral completo (BTC 0.113, ZEC −0.074, NEAR +0.014…). Acumulando para `e33`.
- **Equity −0.27% día:** 4944.06 → 4930.45 (dd −0.27%). Ruido de 1 día market-neutral, sano.
- **Leverage 2.006x** (carry-7d), 21 pos, gross 0.757, net +0.357 (net-long chico = β-neutral OK).
- **🎯 SLIPPAGE REAL (C3), 2º día con datos:** n=21, **mediana −0.99 bps (FAVORABLE), media 3.29**, peor
  **XLM +51.8 / HBAR +21.6 / BNB +17.5**, favorables BCH −18.7 / AAVE −4.4. La mediana negativa = la
  mayoría de fills maker entran a mid o mejor; la media la inflan 3-4 thin coins. **Patrón claro: el coste
  real vive en las monedas FINAS** (XLM/HBAR/ZEC/LIT). Calibra e18 y **conecta con la idea de retirar
  monedas** (¿su edge paga su slippage?). Acumular → `e21_fill_slippage`.
- **Concentración TRX 20.25%** (top), vía `trend` (score trend 0.45). Recurrente, en el borde del umbral
  (>20%); dentro del cap 0.25. Vigilar.
- **Backtest del snapshot:** Sharpe 2.02 / ann 48.1 / maxDD −10 (recalcula con datos nuevos; ~2.07 motor).
- ⚠️ **Bug ffill de sombra (noche-2) NO se manifestó hoy** (TVL logueó 13 ambos ciclos porque a 20/23h el
  panel y DefiLlama estaban alineados). El fix endurece el **edge de día-boundary** (cuando C es más fresco
  que DefiLlama → TVL logueaba 0). **Pendiente deploy**; no es outage activo, es robustez.

### 2026-05-31 (DEMO, primer análisis fino de logs)
- **3 ciclos** (07:00, 09:00, 23:00 Lima) = reinicios por **deploys del día**, no cadencia 24h.
- **Deploy carry-suavizado confirmado EN VIVO:** leverage saltó **1.905 → 2.006** entre ciclo 1 y 2
  (y `carry` vp 0.154→0.165). Es la versión 7-sleeves/carry-7d operando.
- **Equity plano/levemente +:** 4939.08 → 4941.94 (+0.06%). dd ≈ 0. Sano para 1 día market-neutral.
- **🎯 PRIMEROS SLIPPAGE REALES (C3):** ciclo 2 capturó `slip_bps`. **Media ~1.3 bps · mediana ~1.5**,
  peor ZEC +9.4 / XLM +7.5 (thin), favorables SOL −7.9 / AVAX −2.8. Menor que e18 (~4 bps) → ejecución
  maker barata. **1 ciclo, no concluyente** — acumular.
- **Concentración TRX ~18%** vía `trend` (score trend 0.458). Conocida; vigilar.
- **β-hedge funcionando:** BTC pasó SHORT→LONG entre ciclos ajustando neutralidad.
- **FIX zona horaria CONFIRMADO en vivo:** el export "del 31" incluyó correctamente el ciclo de las
  23:00 Lima (dato `asof 2026-06-01 04:00 UTC`). Antes se habría ido a un archivo "01-jun".
- **Sin errores** (0 ERROR en audit), **CB OK** todo el día, sin alertas ntfy. Ciclo 3 cerró bien
  (apareció incompleto en una descarga por ser mid-ciclo).
- **Implementado hoy:** reporte diario (`save_daily_report` wired) + `shadow_signal` en export diario +
  sleeve on-chain TVL en sombra (pendiente deploy) + B1/B2 (e29).

---

## 4. BUGS / ISSUES CONOCIDOS · TODOs
- [ ] **🔴 NUEVO (2026-06-08) — `execution._get/_post/_delete` se tragan el CUERPO del error de Binance.** Solo
      loguean `str(e)` = la línea HTTP (`400 Bad Request for url ...`), no el `{"code","msg"}` del body. El 06-08
      esto retrasó horas el diagnóstico del demo caído (el `code:-1109` solo se vio pidiendo el body a mano con curl).
      **Fix (Fase 1, sin tocar edge → sin backtest):** capturar `e.response.text`/`.json()` y loguearlo. Trivial y
      de alto valor diagnóstico. Igual conviene un helper que mapee codes comunes (-1109 cuenta inválida, -2015 key/IP,
      -1022 firma, -1021 reloj, -4164 min-notional, -4014/-1111 precisión).
- [ ] **🔴 NUEVO (2026-06-08) — el monitor NO vigila "rebalanceo perdido N horas".** El 06-08 estuvimos ~14h sin
      rebalancear (cuenta demo caída) y el digest diario no lo elevó a crítico; solo avisó la escalada de omisiones
      (1 push). **Fix:** check en `monitor.py` que eleve a CRÍTICO si `now - last_rebal_ok > ~26h`. (Ya señalado como
      punto ciego el 06-06; el 06-08 se materializó de verdad.)
- [ ] **🟡 NUEVO (2026-06-08) — capital floor vs barrera de entrada (DECISIÓN DE PRODUCTO, requiere backtest).**
      Min-notional Binance ($5/$20/$50) × 18 posiciones → floor ~$1000-1500 para libro completo, que es también la
      barrera del copiador. **Backtest pendiente:** nº mínimo de posiciones / universo $5-min que preserve Sharpe/maxDD.
      Si una variante de ~10 patas conserva el edge → baja la barrera ~$400 (win de producto). Ver `STATUS.md §PRÓXIMA EJECUCIÓN`.
- [ ] **🟢 NOTA (2026-06-08) — redondeo a 0 en símbolos caros con poco capital.** A $250, BTC (15%=$37 / $63k) redondeó
      `qty=0.000` → orden inválida. Síntoma de capital chico, no bug de fondo; a $1200 BTC=$180 entra. Vigilar si reaparece
      con el capital final: si una pata legítima redondea a 0, saltarla explícitamente (no enviar) en `execution`.
- [x] ~~**D0 (riesgo, prioritario):** el ancla de leverage puede exceder el −10% en vivo (e29)~~ →
      **RESUELTO 2026-06-02 (e51):** `config.LEVERAGE_HAIRCUT=0.85` (decisión de Oscar) recorta el lev
      vivo 2.02x→**1.72x** → maxDD OOS ~−11.5% (cierra el grueso del gap del ancla cediendo ~14% de
      retorno → ~3.4%/mes). Mecanismo en `engine.compute_target`. **PENDIENTE DEPLOY.** Reevaluar el
      factor cuando la DEMO dé maxDD real (puede relajarse si el sobre-tiro vivo es menor al pesimista).
- [x] ~~**D1:** `beta` del snapshot está hardcodeado a 0.0~~ → **RESUELTO 2026-06-02:** el snapshot
      reporta la **β de REGRESIÓN** (neutralidad ≈+0.05): realizada de la equity en vivo a ≥20 días, si
      no la modelo (hoy +0.025). Diagnóstico extra **β-dólar** (Σwβ, exposición direccional del notional,
      la infla `trend`). **PENDIENTE DEPLOY.**
- [x] ~~**Concentración trend/TRX:** evaluar cap por activo en trend~~ → **HECHO (e52, 2026-06-02):** cap
      0.25 en `engine.trend_sleeve` (TRX 20%→9.6%, Sharpe intacto). Pendiente deploy. Si reaparece >15% =
      apilamiento multi-sleeve → cap AGREGADO al target (no testeado aún).
- [x] ~~**🔴 NUEVO (2026-06-04) — `equity_tick` muestrea wallet/realizado, no MTM.**~~ → **CORREGIDO (local,
      commit `5152e7e`, PENDIENTE DEPLOY).** `execution.get_balance()` leía `totalWalletBalance` (sin PnL no
      realizado) → curva plana entre fundings (escalones cada 8h) → **maxDD intradía SUBESTIMADO** (crítico
      para el copy-lead). Ahora lee **`totalMarginBalance`** (NAV = wallet + unrealized) en la única fuente
      (heartbeat, ciclo y sizing). Robusto: None si falta el campo → omite el punto. Distinto del fix viejo
      "no inventar 5000" (ahí no se leía; aquí se leía el campo equivocado). **Verificar tras deploy:** la
      curva deja de ser plana entre ciclos. **Salvedad:** 1er tick MTM salta una vez por el PnL no realizado
      acumulado (~+$87) → escalón cosmético.
- [x] ~~**Churn por reinicio (cycles_today ≥3 sin causa):**~~ → **RESUELTO Y VERIFICADO EN VIVO (2026-06-04).**
      Fix `2034e74` (recupera `last_rebal` de la DB en vez de 0). Prueba: 06-04 = 0 ciclos espurios en ~18h
      post-deploy incl. reinicio del deploy (cycles_today 8→2→0). Falta solo confirmar el rebal programado
      limpio en el log post-14 UTC del 06-04.
- [ ] **`r_multiple`/`exit_px` quedan null** (sistema de rebalanceo rodante, sin ciclo open→close clásico).
      El ciclo de vida de trade completo sería otro proyecto. Los fills+snapshots ya permiten analizar.
- [ ] **Deploy del fix ffill de sombra (noche-2):** `kepler/onchain.py` — endurece el día-boundary (TVL
      logueaba 0 cuando C > fecha DefiLlama). No es outage (hoy logueó 13), pero conviene desplegar.
- [x] ~~**EVALUAR retirar monedas finas del universo**~~ → **HECHO (e53, 2026-06-02):** retiradas
      **XLM/HBAR/LIT** (edge ~nulo/negativo + slippage 7.5-12.9bps); **ZEC se MANTIENE** (su edge paga el
      coste, e48). Neto realista 2.24→2.96%/mes sin empeorar OOS. Bonus: limpió el maxDD OOS (−13.5%→−7.1%)
      → permitió relajar el haircut a 0.95. Pendiente deploy. Universo ahora 29 global / 20 largo.
- [x] ~~**Shadow on-chain TVL:** pendiente deploy~~ → **DESPLEGADO y registrando** (2026-06-01: TVL 13 +
      BLEND 23 por ciclo). Reloj 60d corriendo; tras ≥60-90d correr `e33` y decidir sleeve #8.
- [x] ~~`report:[]` (narrativo diario no se llamaba)~~ → ARREGLADO 2026-05-31 (wired en el ciclo).
- [x] ~~shadow no salía en el log diario~~ → ARREGLADO 2026-05-31 (añadido a `export_daily_log`).
- [x] ~~Desfase UTC vs Lima en días/horas~~ → ARREGLADO 2026-05-31 (config.TZ + helpers).

---

## 5. CRITERIOS A AFINAR / ELIMINAR / POTENCIAR (meta-evolución del sistema)
- **POTENCIAR:** acumular DEMO (E1, el foso real = tiempo) → medir Sharpe REAL vs 2.07 backtest. Es el
  80% del valor. · C3 slippage real → costos honestos. · netflow on-chain de pago (CryptoQuant ~$99/mo)
  si on-chain confirma (abre menú de varios sleeves, camino RenTech).
- **AFINAR:** la regla del ancla (D0) — leverage robusto a régimen, sin exceder el maxDD en vivo. ·
  cap de concentración en trend. · cálculo de β en vivo (D1).
- **ELIMINAR / NO RESUCITAR:** gates de régimen / overlays de timing (DVOL e25, estacionalidad e28 = se
  veían bien pero son artefacto del ancla). · sleeves ortogonales pero débiles que diluyen (order-book
  diario e24). · fuentes BTC/ETH-only no cross-seccionales (basis e22, opciones e25). · martingalas.
- **CRITERIO DE ADMISIÓN (recordatorio):** un sleeve entra solo si corr<0.35 + IS/OOS>0.10 + **sube el
  retorno al maxDD fijo con costos taker** + pasa estrés. Y siempre: gratis primero, pago a la lista.
