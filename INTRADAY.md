# KEPLER — FRONTERA INTRADÍA (guía para el futuro)
> **Estado (2026-06-02): RUTA EJECUCIÓN ACTIVA; el resto sigue aparcado/descartado.** Oscar reabrió la
> frontera tras cerrar D0/D1/concentración/finas. Veredicto de la sesión (ver §7): para Kepler (β-neutral,
> diario, maker, bajo-DD, NO-HFT) el alfa intradía DIRECCIONAL es un callejón sin salida (coste×turnover,
> probado e19/e24/e45). Lo intradía ÚTIL aquí = **ejecución** (bajar coste) y **riesgo** (monitor), no alfa.
> En marcha: **timing del rebalanceo (e54)**. El resto del documento es el mapa histórico.

---

## 1. TESIS EN UNA FRASE
Hay **edge real en microestructura (order-book, y probablemente liquidaciones)**, pero vive a horizonte
**SUB-DIARIO**. A resolución diaria se diluye hasta ~0. Para monetizarlo hace falta **operar intradía**,
y eso exige primero una pieza que hoy NO tenemos: un **backtester horario fiable**. Esa pieza es la
**llave común** que abre: (a) sleeves de order-book intradía, (b) liquidaciones intradía, (c) el monitor
de riesgo intradía (e15). Sin ella, todo lo intradía está bloqueado.

---

## 2. LA EVIDENCIA (por qué creemos que el edge es intradía)

### 2.1 Order-book imbalance (e23 / e24, 2026-05-31)
Fuente: `bookDepth` de data.binance.vision (snapshots cada 30s, notional bid/ask a ±1..±5% del mid),
2023-01 → hoy. Señal probada: `imbalance = mean_t (bid − ask)/(bid+ask)`, contrarian.

- **Señal SIN rezagar (la media del día ve el propio día):** Sharpe **7–9 a horizonte 24h** en el
  chequeo barato. ⚠️ **ESTO ES LOOK-AHEAD, no un Sharpe operable** — la media diaria incluye horas
  futuras del día y solapa con el retorno forward. NO es un número limpio.
- **Lo que el look-ahead SÍ revela (la pista valiosa):** existe una **estructura contemporánea fuerte**
  entre el imbalance del libro y el retorno del MISMO día. Cuando se rezaga a limpio (usar el día D-1
  completo para predecir D), el Sharpe **se desploma a ~1.3** (diario) y al ancla maxDD −10% aporta
  **+0.00%/mes** a coste taker → DESCARTADO como sleeve diario (ver `research/e24_orderbook_sleeve.py`).
- **Lectura honesta:** el contraste 7–9 (contemporáneo) vs ~1.3 (diario rezagado) es la firma de un
  edge cuyo poder está en las **horas siguientes a la señal, no en el día siguiente**. El sistema diario
  lo deja casi todo sobre la mesa porque solo mira a 24h+.

### 2.2 Liquidaciones (2026-05-31)
- **Sin histórico gratis:** Binance retiró `allForceOrders` (REST = "out of maintenance") y
  `liquidationSnapshot` (data.binance.vision = bucket vacío). Solo se consigue:
  - **(a)** pagando un tercero (Coinglass / Coinalyze), o
  - **(b)** capturando el WS `@forceOrder` hacia adelante (hay que montar un colector; tarda meses en dar N).
- **Por qué importa para intradía:** las cascadas de liquidación son un evento de **minutos**, contrarian
  por naturaleza (forzar ventas hunde el precio → rebote). Su edge, igual que el order-book, es intradía.
  No tiene sentido perseguirlas hasta tener (1) el dato y (2) el backtester horario.

### 2.3 El intento previo de intradía (e15, 2026-05-30) — por qué falló
`research/e15_intraday_monitor.py` quiso evaluar un monitor de riesgo intradía. **Ninguna reconstrucción
HORARIA reprodujo el edge diario:** baseline horario ~**−0.28** vs **+1.04** diario. Marcar a mercado
hora-a-hora ≠ el retorno-forward-24h del motor. Conclusión: **no se puede evaluar nada intradía con
rigor sin un backtester horario que reproduzca el edge primero.** Es el cuello de botella, no un detalle.

---

## 3. EL PREREQUISITO: BACKTESTER HORARIO (lo que habría que construir)
Es un mini-proyecto, no un sleeve. Requisitos mínimos para que sea fiable:

1. **Panel de precios y señales a 1h (o más fino)** consistente, sin look-ahead, con el forward-return
   al horizonte correcto (no marcar a 24h una señal que se cierra en 4h).
2. **Modelo de ejecución intradía realista:** maker GTX (no siempre llena), latencia, y sobre todo
   **costos de cruzar el spread** — a horizonte corto el coste DOMINA (el carry instantáneo a 199x
   turnover fue perdedor neto, e19; intradía es peor). Sin esto, cualquier Sharpe intradía es ficción.
3. **Turnover y capacidad:** intradía = turnover altísimo → modelar impacto vs ADV por símbolo (B4).
   La capacidad (cuánto AUM aguanta) cae fuerte al bajar de horizonte. Relevante para copy-lead.
4. **Reconciliación con el motor diario:** el backtester horario debe REPRODUCIR el resultado diario
   cuando se le pide horizonte 24h (test de sanidad; e15 falló justo aquí).
5. **Validación igual de brutal que el diario:** walk-forward IS/OOS, purga/embargo (B1), Deflated
   Sharpe (B3), estrés por cuartiles. El listón no baja por ser intradía — sube (más ruido, más coste).

⚠️ **Riesgo estratégico:** intradía empuja hacia el juego que CLAUDE.md dice NO jugar (gestión de spikes,
HFT). La línea: intradía está OK si es **señal lenta de horas con costos modelados**, NO si es latencia/
microsegundos/market-making. Mantener la misión: bajo maxDD, supervivencia, no ROI llamativo.

---

## 4. ACTIVOS DE DATOS YA EN DISCO (para no rebajar dos veces)
- **`data/bookdepth_daily/{SYM}.parquet`** — imbalance DIARIO (mean del día) de los 32 símbolos, 2023-01→
  2026-05. Útil como referencia, pero para intradía hace falta el RAW (ver abajo). Generado por
  `research/e23_orderbook_check.py::load_symbol`.
- **Para intradía real habría que bajar el RAW de `bookDepth`** (snapshots 30s, ~0.48MB/día/símbolo,
  ~11GB para 32 símbolos × 3.4a) y/o `aggTrades`. El downloader de e23 es adaptable (quitar la
  agregación diaria, guardar la serie 30s). Disponible 2023-01 → ~anteayer.
- **Otros datasets intradía en data.binance.vision** (`daily/`): `aggTrades`, `bookTicker`, `trades`,
  `markPriceKlines`, `premiumIndexKlines`. (NO existen: `liquidationSnapshot` — retirado.)

---

## 5. PLAN POR FASES (cuando se decida atacar intradía)
1. **Fase 0 — Decisión y alcance.** ✅ Oscar dio luz verde (2026-06-01); el blend cross-family mostró que
   la veta uncorr restante es microestructura (intradía) → justifica el backtester.
2. **Fase 1 — Backtester horario.** ✅ **HECHA (2026-06-01, `research/e42_hourly_backtester.py`).** MTM
   horario buy-and-hold (deja driftar dentro del bloque = forward del motor) **RECONCILIA con el motor
   diario: corr de bloque 1.000** en mom/rev/lowvol/hlpos, Sharpe ≈ motor. **Supera el fallo de e15.**
   (Falta sumar el modelo de ejecución intradía §3.2 — costo de cruzar el spread — antes de Fase 2.)
3. **Fase 2 — Re-evaluar order-book** a horizontes 1h–12h con costos reales. ✅ **HECHA (2026-06-01,
   `research/e45_intraday_orderbook.py`) → DESCARTADO (edge real pero el coste manda).**
   - **Datos:** `research/e43_download_bookdepth_raw.py` bajó el bookDepth a 30s (imb1/imb2/imb5) →
     `data/bookdepth_30s/{SYM}.parquet`. **COMPLETO (2.16GB, 32/32).** Panel horario cacheado en
     `data/bookdepth_30s/_hourly_{band}.parquet` (reusable).
   - **Motor de coste:** `research/e44_intraday_cost.py::eval_intraday(C,beta,score,hold,cost_vec)` = MTM
     horario reconciliado (e42) + coste por símbolo (taker + slippage ADV). `cost_vector('taker_adv')`.
   - **RESULTADO:** imbalance 30s→horario → score=±imb → `eval_intraday` a holds {1,2,4,6,12,24}h a coste
     real (taker+ADV mediana **8.6 bps**), ambos signos, 3 bandas, overlap 2023+. **TODAS las celdas
     negativas.** Mejor imb2 contrarian 24h = **Sharpe −0.89 / −0.24%/mes** (IS −1.03 / OOS −0.82, 4
     cuartiles <0). **El muro es coste×turnover** (24h→360x, 1h→4313x; drag taker ~370%/año a 1h),
     monótono con el hold. El único maker>0 es contrarian-24h (≈ caso diario ya rechazado, e24). El
     Sharpe 7-9 de e23 era contemporáneo (look-ahead), no operable. **No hay sleeve order-book intradía**
     para la estructura de coste de Kepler; monetizarlo exigiría maker-fills fiables (selección adversa)
     y/o costes HFT → fuera de la misión. Backtester horario queda montado/reusable.
4. **Fase 3 — Liquidaciones:** montar colector WS `@forceOrder` (o evaluar Coinglass) → señal de cascada.
5. **Fase 4 — Monitor de riesgo intradía (e15)** sobre el mismo backtester.

---

## 6. QUÉ NO HACER (para no repetir errores)
- **No declarar un Sharpe intradía sin modelar el coste de cruzar el spread.** A horizonte corto el
  coste manda; un Sharpe bruto bonito es casi siempre mentira (lección carry-instantáneo e19).
- **No confundir estructura contemporánea (look-ahead) con edge operable.** El 7–9 del order-book NO es
  operable; rezagado limpio da ~1.3. Siempre rezagar al horizonte de decisión real.
- **No perseguir liquidaciones hasta tener dato + backtester.** Sin ambos es trabajo muerto.
- **No deslizarse a HFT/market-making.** Fuera de la misión (CLAUDE.md). Intradía = horas, no microsegundos.
- **Recordar el ancla:** aunque sea intradía, el criterio de admisión sigue siendo subir el retorno al
  **maxDD fijo** con costos reales (no solo corr~0 + IS/OOS). Lección e16d/e24.

---
## 7. EVALUACIÓN DE RUTAS (2026-06-02) — cuáles encajan en Kepler y cuáles no
Marco: 3 pruebas (e19 carry-inst, e24 OB-diario +0.00, e45 OB-intradía todo negativo) confirman que el
alfa intradía DIRECCIONAL muere en coste×turnover con nuestra estructura de coste. ⇒ lo intradía útil es
**ejecución (bajar coste)** y **riesgo (monitor)**, NO alfa. Veredicto por ruta:

| Ruta | Veredicto | Razón |
|---|---|---|
| **Timing del rebalanceo** (e54) | 🟢 **ACTIVA** | Baja el slippage ~21% pineando a la hora líquida (14 UTC). Sin turnover ni β. Implementada (pendiente deploy). |
| Slicing pasivo en la ventana | 🟡 DIFERIDO a capacidad (e55) | Cuantificado: a tamaño DEMO participación ~0.00% → ahorro CERO. Empieza a importar ~$1M+ AUM en coins finos, crítico >$10M. NO implementar ahora; revisar al escalar AUM (con cap de tamaño por liquidez). |
| Capacidad/impacto (B4) | 🟡 útil, no urgente (e55) | Datos intradía → techo de AUM antes de degradar el edge. Cruce ~$4.6M (pos 5% en ZEC supera 2% participación). Relevante copy-lead. No es alfa. |
| Monitor de riesgo intradía (e15) | 🟢→🔴 EVALUADO 2026-06-02 | **Hard-halt intradía = whipsaw, NO sirve** (β≈0: DD intradía diminuto y revierte; peor −3.3% en 4a, 99% bloques >−1.6%; cualquier umbral mata el retorno). El maxDD se forma en DÍAS, no intradía. **ÚNICA acción útil:** chequear el CB ANCHO existente (−20%) en el heartbeat (15min) en vez de solo en el ciclo 24h = rail de catástrofe más rápido a coste histórico CERO (nunca dispara con ruido). |
| Order-book intradía | 🔴 descartado (e45) | Todo negativo a coste real. No resucitar sin ángulo nuevo. |
| Liquidaciones intradía | 🔴 bloqueado/aparcar | Coinalyze no da histórico (colector meses); edge diario = solo ZEC. |
| **CME gap** | 🔴 **descartar de raíz** | Timing direccional de BTC market-wide → inyecta β en un libro β-neutral; cae en gates-de-régimen ya descartados (e25/e28/R2/R3). Empeoraría lo que nos define. |
| Vol-scaling intradía del gross | 🔴 descartar | Overlay de régimen/vol-target = dead end conocido (empeora maxDD). |
| Efectos de sesión (Asia/US) cross-sec | 🔴 muy escéptico | Mismo muro coste×turnover + sabor a estacionalidad (e28). |
| Funding-timing del carry | 🟡 marginal | Podría capturar algo de funding pero añade turnover al sleeve que suavizamos (e19). Baja prioridad. |

*Relacionado: `STATUS.md` (changelog 2026-05-31 noche A2 order-book, 2026-06-02 ejecución), `ROADMAP.md`
§A2/§D/§F, `research/e54_rebalance_timing.py`, `e23/e24_orderbook`, `e45_intraday_orderbook`, `e15_intraday_monitor`.*
