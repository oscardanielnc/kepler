# KEPLER — Estado vivo · Changelog · Pendientes
> **Empieza cada sesión leyendo este archivo.** Última actualización: **2026-06-01** (mañana, hora Lima).
> **Roadmap de mejora del sistema: `ROADMAP.md`** (faro Medallion/RenTech).

---

## ESTADO ACTUAL (2026-05-31)
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
- 🌓 **Sleeve on-chain TVL en MODO SOMBRA (noche-6, PENDIENTE DEPLOY):** `kepler/onchain.py` registra
  cada ciclo los pesos que tendría (sin operar) → validación forward del +0.6%/mes. No afecta lo que opera.
- 🔬 **B1/B2 (e29): edge ROBUSTO** (Sharpe OOS 2.29 ≈ IS 2.21, 6/6 folds+) pero **el ancla −10% es
  optimista** — en walk-forward el maxDD OOS llega a −13.5%; **el −10% puede excederse en vivo** (riesgo, ROADMAP D).

### Estado del código vs producción
- Commits de hoy (carry 2.07, costo trend, B3, C3, A4, dashboard explicativo) desplegados por Oscar.
- Claude NO hace push/pull ni deploy (memorias `kepler-no-git-push`, `kepler-claude-no-ssh-deploy`);
  Oscar pushea/despliega. Si hay un commit local de docs posterior, lo subirá la próxima vez.

---

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
- **0a. Demo viva con la versión nueva:** en la VM `journalctl -u kepler -n 50` → buscar
  `lev≈2.02x(maxDD-10%)`. Dashboard http://213.35.121.9:8080 panel backtest = **2.07 / −10** y deben
  verse los paneles nuevos (Cómo funciona, Drawdown, Diversificación, PnL por posición).
- **0b. Acumulación de datos:** ¿hay varios ciclos con fills y `slip_bps`? (para C3). Pedir a Oscar la
  `kepler.db` de la VM si ya pasaron días → correr `python -m research.e21_fill_slippage <ruta_db>`.
- **0c. Estado esperado:** **32 perps · 7 sleeves · ancla −10% · lev ~2.02x · carry suavizado 7d.**

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
2. **C1 — factores académicos nuevos** (datos propios/free): **size/market-cap** (⚠️ necesita fetch de
   market caps, ej. CoinGecko gratis) y **CTREND** (⚠️ chequear solape con mom/trend antes). Evaluar
   también su versión CONDICIONAL vía el lab (doctrina).
4. **Dune/Flipside netflow reconstruction** — proxy GRATIS antes de pagar CryptoQuant (proyecto data-eng).

### 📌 RECORDATORIO — MENÚ DE CONDICIONES (hacer DESPUÉS de #2 y #4) — vía `regime_lab`, con disciplina
> Pedido de Oscar (2026-06-01): mantener abierto el rescate por condición específica. Probar cada una
> con PRE-REGISTRO + deflación + walk-forward purgado + validación forward (no sweeps masivos).
- **CME gap** (gap del futuro CME de BTC fin de semana). ⚠️ Es BTC-direccional/intradía → choca con
  β-neutral (se hedgea BTC) y/o requiere el backtester horario; evaluable como overlay con ese caveat.
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
