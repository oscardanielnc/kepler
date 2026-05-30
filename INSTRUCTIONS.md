# KEPLER — Instrucciones base del proyecto
**Sistema cuantitativo multi-activo · Binance · hijo de Sentinel · dirigido por evidencia**
Documento constitucional. v0.1 (2026-05-29). Se refina con cada decisión de diseño.

---

## Misión
Maximizar el **Sharpe** (retorno por unidad de riesgo) de una cartera multi-activo de
cripto en Binance, combinando varios edges no correlacionados, market-neutral por defecto,
con el riesgo absoluto fijado por un dial de apalancamiento. Norte: Calmar alto
(p.ej. 20% retorno / 5% maxDD), persiguiendo el máximo real sin promesas vacías.

## Principios (no negociables)
1. **Evidencia antes que convicción.** Nada entra al sistema sin backtest honesto que
   muestre mejora en rentabilidad Y riesgo (IS/OOS/walk-forward, costos, pesimista).
2. **Combinar edges no correlacionados** (Sharpe se suma en cuadratura). Ningún sleeve solo.
3. **Capas desacopladas:** Datos → Features → Alphas → Combinación → Portafolio → Riesgo
   → Ejecución. Cada capa se valida y se prueba aislada.
4. **Sharpe es la métrica; el retorno/riesgo absoluto es un DIAL** (apalancamiento sobre
   el punto óptimo de la curva retorno-vs-maxDD).
5. **Simple y probado primero.** La matemática compleja entra solo si mejora OOS.
6. **IA asiste y analiza; no manda.** El núcleo de alpha es transparente y validable.

## Arquitectura (capas)
1. **Datos** — Binance perps + spot (carry). OHLCV+taker+funding+OI, N activos alineados,
   anti-survivorship. (rescatar fetch de Sentinel)
2. **Universo** — top 20 por volumen al inicio → escalar. Filtros de liquidez/edad.
3. **Features** — por activo (retornos, CVD, funding, vol/GARCH, trend, dist-VWAP) y
   cross-asset (β a BTC/ETH vía Kalman, residuos, grafo lead-lag, cointegración, factor PCA).
4. **Alphas** (independientes, cada uno → expected-return por activo, validado por IC OOS):
   - **Carry** (funding / cash-and-carry) — ancla de bajo riesgo.
   - **Cross-sectional factor** (long top / short bottom) — chasis market-neutral.
   - **Stat-arb pares** (OU sobre spreads cointegrados).
   - **Lead-lag amplificado** (operar la dominada de mayor β; salida condicionada al driver).
   - **Reversión de residuos** / momentum / flow como factores del chasis.
5. **Combinación** — mezcla IC-weighted simple de alphas válidos → vector de retorno esperado.
6. **Portafolio** — optimización convexa (Markowitz/Kelly) con matriz de COVARIANZA →
   pico de la superficie de Sharpe; restricción β≈0; **conviction override** (concentrar
   hasta 100% en eventos extremos). Tope normal por activo 15-25%, muy variable.
7. **Riesgo** — vol-targeting (dial), límites bruto/neto/por-cluster correlacionado,
   circuit breaker DD, reserva de capital, kill-switch.
8. **Ejecución** — maker-first (órdenes límite validadas), fixes SL/TP de Sentinel.
9. **Backtest** — honesto a nivel portafolio; curva del punto óptimo (Calmar máx).
10. **Ops** — WS 24/7, db, notify, dashboard, reconcile. IA auxiliar + módulo de noticias.

## Flujo de trabajo (obligatorio para todo cambio)
Propuesta → backtest del sistema → implementar SOLO si mejora rentabilidad Y reduce/iguala
riesgo → nada a producción sin confirmarlo. Reportar el número, no la intuición.

## Frecuencia (por capas, todo ajustable)
- Riesgo/salidas: tiempo real (~1m / tick, WS).
- Señales: por alpha y por activo según su timescale (lead-lag 1-5m; momentum 1h; carry horas).
- Rebalanceo de cartera: grilla lenta + disparadores por evento.

## Capas futuras (documentadas, activables cuando el core funcione)
- **IA auxiliar:** NLP noticias/sentimiento, clasificación de régimen, detección de
  anomalías, analítica post-trade. NUNCA como núcleo de decisión de órdenes.
- **Módulo de catalizadores/noticias:** detecta eventos por moneda → input de convicción.
  No backtesteable con histórico limpio → overlay forward-validado en demo.

## Convenciones
- Todo el sizing como **% del 100% del capital** (no $ fijos). Capital demo ejemplo: $5000.
- Datos y parámetros **por activo** (horizontes, lags, bandas, stops) — nada estricto global.
- Métrica primaria de reporte: expectativa/IC + Sharpe/Calmar/maxDD/turnover/capacidad.
- Rescate desde /btc (Sentinel): fetch_1m, indicators, kalman, ou_model, garch, hmm_regime,
  order_manager (con fixes), db, notify, dashboard, reconcile, circuit_breaker, engine_1m.
