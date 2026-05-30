# KEPLER — Sistema cuantitativo multi-activo (cripto, Binance Futures)
**Hijo de Sentinel. Diseñado desde cero, dirigido por evidencia.**
Borrador de plan — v0.1 (2026-05-29). Para afinar con Oscar.

> **Nombre.** *Kepler*: las leyes del movimiento planetario predicen la órbita de un
> cuerpo a partir de la masa dominante. Metáfora exacta del sistema: BTC/ETH como
> masas dominantes cuya "gravedad" predice el movimiento de los alts (dominados).
> Alternativas si prefieres: **Lagrange** (puntos de equilibrio de dos cuerpos →
> evoca el punto óptimo riesgo/beneficio) · **Helios** (sol-céntrico). Renombrar = trivial.

---

## 1. Filosofía (los errores de v1 que NO repetimos)
1. **Evidencia antes que convicción.** Todo componente se valida en backtest honesto
   (costos, pesimista, IS/OOS/walk-forward) ANTES de entrar al sistema. Regla de oro.
2. **Capas desacopladas.** Alpha ≠ Portafolio ≠ Ejecución ≠ Riesgo. v1 fallaba porque
   el "torneo de candidato único" mezclaba todo y rechazaba ideas buenas por formato.
3. **Cartera de muchas posiciones**, no una. El edge fino por activo se vuelve Sharpe
   vía diversificación + neutralidad. Esto v1 no podía hacerlo estructuralmente.
4. **Métrica primaria = Sharpe (retorno/riesgo).** El %/mes y el riesgo son un DIAL
   (apalancamiento) sobre el Sharpe. Maximizamos Sharpe; el retorno absoluto se ajusta.
5. **Anclados en lo probado por instituciones** (ver §2), no en patrones inventados.

---

## 2. Fundamento institucional (qué hacen los fondos rentables — investigado 2026-05-29)
Anclamos en 4 familias probadas, de mayor a menor robustez:
- **A. Carry / cash-and-carry (funding):** long spot / short perp (o sesgo por funding).
  Cobra el funding de forma estructural. Sharpe histórico ~4.8, riesgo bajo. ANCLA.
- **B. Stat-arb market-neutral (cointegración/pares):** long el infravalorado / short el
  sobrevalorado de un par cointegrado; entrar ~2σ del spread, salir en convergencia.
  Sharpe ~2. Aquí entra **Ornstein-Uhlenbeck** (bandas óptimas + half-life).
- **C. Cross-sectional factor (long/short):** rankear universo por señal; long top 25% /
  short bottom 25%, market-neutral. Factores: momentum/trend, flow (CVD), reversión, carry.
- **D. Lead-lag BTC→alts (tu idea, documentada):** BTC/grandes LIDERAN a los chicos con
  retardo; operar la moneda dominada amplificada por la dominante. Granger unidireccional.

Fuentes: stat-arb crypto (Sharpe 2+, dollar-neutral ~31%/2025); lead-lag/seesaw BTC→alts
(Granger unidireccional, respuesta retardada de small-caps); cross-sectional momentum
factor (long top/short bottom, market-neutral); cash-and-carry Sharpe ~4.8.

---

## 3. Tus ideas, formalizadas (son el corazón del sistema)

### 3.1 Grafo de dominancia / lead-lag — "quién dirige a quién"
- Construir un **grafo dirigido** entre los N activos: lagged cross-correlation + Granger
  causality + transfer entropy. Arista A→B con (lag óptimo, beta de transmisión).
- BTC y ETH como drivers primarios; identificar para cada alt su(s) driver(s), el lag y
  la beta de amplificación. Re-estimado en ventana rodante (las relaciones cambian).

### 3.2 Operar la DOMINADA amplificada (beta-amplified lead-lag) — alpha estrella
- Cuando un driver (ETH) tiene un movimiento/predicción fuerte, operar el **follower de
  mayor beta** (DOGE sube ~β× lo de ETH) para amplificar el retorno por unidad de señal.
- **Salida CONDICIONADA al driver, no a precio fijo:** mantener DOGE mientras ETH/BTC
  sigan subiendo; **cerrar DOGE en cuanto el driver gira** (el TP es una *variable* =
  reversión del líder, no un nivel exacto). Esto es un trailing-exit condicionado al líder.
- Selección óptima del follower: maximizar `beta_transmisión × prob(driver sigue) / costo`.

### 3.3 Concentración por convicción (eventos)
- Por defecto la cartera se diversifica (pesos limitados por activo). Pero cuando una
  señal supera un umbral extremo (evento/noticia con expected-return muy alto), se
  **relaja el tope** y se permite concentrar hasta el 100% del capital en ese activo.
- Mecanismo: el optimizador de cartera (§5) ya concentra donde el Sharpe esperado es
  máximo; añadimos un "conviction override" que sube el cap por activo según la fuerza
  y fiabilidad de la señal. (Honesto: "seguro" no existe; concentramos por Sharpe esperado.)

### 3.4 Horizonte por activo (nada estricto)
- Cada activo tiene su **timescale propio** (algunos reaccionan en minutos, otros en días).
- Estimar por activo: half-life de OU / autocorrelación → define su horizonte de señal y
  de holding. Todos los parámetros (lag, horizonte, bandas, stops) **ajustables por activo**.

### 3.5 Punto óptimo riesgo/beneficio — **PRINCIPIO CLAVE (apuntado)**
- Existe un punto donde subir el riesgo deja de aumentar el beneficio proporcionalmente
  (costos, capacidad, correlación, colas). Lo buscamos así:
  1. Correr el backtest del sistema a múltiples niveles de riesgo (exposición bruta /
     vol-target) → curva **retorno vs maxDD**.
  2. El óptimo = donde **Calmar (retorno/maxDD) se maximiza** (la "rodilla" de la curva).
  3. Operar en ese punto; el **apalancamiento** es un dial lineal aparte para fijar el
     riesgo absoluto deseado (si el óptimo es 20%riesgo@10x, bajamos a 5x → 10% riesgo).
- Entregable recurrente del backtest: la curva y el punto óptimo.

---

## 4. Arquitectura (flujo por capas)
```
1. DATOS        Binance perps (+spot para carry). OHLCV+taker+funding(+OI), N activos
                alineados. Anti-survivorship (incluir delisted en su período).
2. UNIVERSO     Top 20 por volumen al inicio → escalar. Filtros de liquidez/edad de listing.
3. FEATURES     Por activo: retornos, CVD, funding, vol(GARCH), RSI/trend, dist-VWAP.
                Cross-asset: beta a BTC/ETH (Kalman), residuos, grafo lead-lag, spreads
                cointegrados, factor de mercado (PCA / 1er componente).
4. ALPHAS       Modelos independientes → score (expected return) por activo/período:
                α1 carry(funding)  α2 stat-arb OU(pares)  α3 cross-sectional momentum/flow
                α4 lead-lag amplificado (§3.2)  α5 reversión de residuos.
                Cada uno validado por IC (information coefficient) y OOS antes de incluirse.
5. COMBINACIÓN  Mezcla de alphas válidos → vector de retorno esperado (IC-weighted simple).
6. PORTAFOLIO   Con matriz de COVARIANZA (correlaciones): mean-variance / risk-parity con
                restricción beta-neutral (β_cartera≈0). Conviction override (§3.3).
7. RIESGO       Vol-targeting (fija el dial), límites bruto/neto/por-cluster, circuit
                breaker de DD, half-the-capital reserve, kill-switch.
8. EJECUCIÓN    Maker-first (órdenes límite del diseño validado), fixes SL/TP de Sentinel.
9. BACKTEST     Honesto a nivel PORTAFOLIO: costos, slippage, funding, pesimista,
                IS/OOS/walk-forward; Sharpe/Calmar/maxDD/turnover/capacidad + curva óptima.
10. OPS         WS 24/7, db, notify, dashboard, reconcile (rescatados de Sentinel).
```

---

## 5. Métodos matemáticos (mapeados a propósito, no adorno)
- **Ornstein-Uhlenbeck** (Langevin) → bandas y half-life de pares cointegrados (α2).
- **Kalman** → beta dinámica alt↔driver y denoising de señales (α4, residuos).
- **PCA / eigen-portfolios** → extraer factor BTC/mercado, operar residuos (multivariable).
- **Cointegración (Engle-Granger / Johansen)** → hallar pares/canastas que revierten.
- **Granger / transfer entropy** → grafo de dominancia (§3.1).
- **GARCH** → pronóstico de volatilidad → vol-targeting y sizing (capa 7).
- **Markowitz / Kelly multivariado** → pesos de cartera con covarianza (capa 6).
- **Hawkes (auto-excitación)** → clustering de liquidaciones (avanzado, fase posterior).
Principio: empezar SIMPLE (lo simple probado funciona); subir complejidad solo si el
backtest muestra mejora real OOS.

---

## 6. Rescate desde Sentinel (/btc)
- Datos: `fetch_1m.py` + almacén parquet (extender a N activos).
- Cálculo: `indicators.py`, `kalman.py`, `ou_model.py`, `garch.py`, `hmm_regime.py`.
- Ejecución: `order_manager.py` (con fixes SL/TP + diseño de órdenes límite).
- Infra: WebSocket, `db.py`, `notify`, dashboard, reconcile, circuit_breaker, macro_filter.
- Backtest: filosofía/motor `engine_1m` → elevar a portafolio.
- Jubilado: torneo de candidato único, sizing-por-convicción, tácticas de patrón.

---

## 7. Etapas de construcción (cada una: validar → implementar)
- **E0 — Datos:** bajar 1m de 20 perps líquidos + funding (+spot BTC/ETH para carry).
- **E1 — Estudio de dominancia/lead-lag:** β, lag y Granger BTC/ETH→alts. ¿Cuánto se
  predice un alt desde su driver? ¿Qué follower amplifica más? (responde tu pregunta).
- **E2 — Descubrimiento de alphas:** IC IS/OOS de α1..α5 en el universo. Quedarnos con
  los estables.
- **E3 — Motor de backtest de portafolio:** covarianza, optimización, vol-target, costos,
  curva del punto óptimo (§3.5).
- **E4 — Ensamblar el sistema:** alphas válidos + cartera neutral + ejecución maker +
  conviction override. Walk-forward.
- **E5 — Paper/demo multi-activo** ($5000 demo, todo como % del 100%); ajustar el dial.

---

## 8. Preguntas abiertas para afinar
1. Neutralidad: ¿market-neutral estricto (β≈0) por defecto, con permiso de sesgo net-long
   cuando el factor BTC es claramente alcista? (recomiendo neutral + override).
2. ¿Incluimos spot de Binance para el carry cash-and-carry (mayor Sharpe), o solo perps?
3. Rebalanceo: continuo vs en grilla (cada X min/horas) — afecta turnover/costos.
4. Límite de concentración normal por activo (p.ej. 15-25%) antes del conviction override.

**Meta:** Sharpe lo más alto posible → en el punto óptimo de la curva → leverage al riesgo
que toleres. 20%/5% (Calmar 4) es el norte; perseguimos el máximo real, sin promesas vacías.

---

## 9. Decisiones de diseño (discusión 2026-05-29)

### 9.1 Combinar alphas es el camino (no carry-only)
Sharpe de cartera de edges INDEPENDIENTES ≈ √(ΣSharpeᵢ²). Combinar 3 sleeves de Sharpe~1.5
no correlacionados → ~2.6, mejor que cualquiera solo. Carry tiene el mayor Sharpe individual
PERO: capacidad limitada (crowding comprime el spread), riesgo de cola (pata short del perp
en rallies, dislocación de basis), su edge direccional decae (Fase 2: murió OOS 2025-26),
retorno absoluto modesto sin leverage agresivo. → **Carry = sleeve ANCLA de bajo riesgo,
NO el sistema entero.**

### 9.2 Rol de cada sleeve
- **Carry/funding** → ancla de bajo riesgo (Sharpe alto, poco direccional).
- **Cross-sectional factor** (long top/short bottom) → **el chasis** market-neutral (β≈0 =
  bajo riesgo), diversificado, edge documentado; aloja los demás como factores.
- **Stat-arb pares (OU)** → sleeve de reversión (riesgo: ruptura de cointegración).
- **Lead-lag amplificado** → sleeve de alto octanaje, integrado como factor cross-seccional
  ("rank por catch-up al driver") con salida condicionada al líder; NO se corre solo
  (riesgo: relaciones inestables → β dinámica/Kalman; colas del follower volátil).
El optimizador de cartera (capa 6) los pondera por Sharpe esperado y covarianza.

### 9.3 Optimización multivariable ("picos/cimas de la superficie")
Confirmado como núcleo: el optimizador busca el **pico de la superficie de Sharpe** sobre el
espacio de pesos = optimización convexa cuadrática con la matriz de covarianza (Markowitz /
Kelly). El "punto óptimo de riesgo" (§3.5) es el mismo concepto a nivel agregado: barrer la
curva retorno-vs-maxDD y operar en la rodilla (Calmar máx), luego leverage como dial lineal.

### 9.4 Frecuencia por capas (todo ajustable)
- Riesgo/salidas (stops, reversión driver, circuit breaker): tiempo real ~1m/tick (WS).
- Señales: por alpha y por activo según timescale (lead-lag 1-5m; momentum 1h; carry horas).
- Rebalanceo de cartera: grilla lenta + disparadores por evento.

### 9.5 IA — auxiliar, no núcleo
Usos válidos: NLP noticias/sentimiento, clasificación de régimen, detección de anomalías,
analítica post-trade. NO como núcleo de alpha (caja-negra = sobreajuste, no validable OOS;
LLMs alucinan). La IA asiste y analiza; las órdenes las decide el motor transparente.

### 9.6 Módulo de catalizadores/noticias
News API / RSS / social → detecta eventos por moneda → input del conviction override (§3.3).
No backtesteable con histórico limpio → overlay FORWARD-validado en demo, no en el backtest
histórico. Se deja preparado (interfaz), se activa cuando el core funcione.

### 9.7 Confirmado por Oscar
Incluir SPOT (para carry cash-and-carry). Rebalanceo en grilla. Concentración normal 15-25%
por activo pero MUY variable, hasta 100% en casos extraordinarios (evento/catalizador).
