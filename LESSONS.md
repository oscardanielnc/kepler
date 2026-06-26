# KEPLER — Retrospectivo y activos reutilizables
**Cerrado: 2026-06-26.** Dueño: Oscar Navarro. Hijo de Sentinel; hermano de tvindicators (vivo).
> Propósito de este doc: que el trabajo de KEPLER sea **base** de proyectos futuros, no esfuerzo perdido.
> Dos partes: (1) **qué reutilizar** (código + método), (2) **qué aprendimos** (técnico, estadístico, estratégico).

---

## 0. Epitafio en una frase
KEPLER fue un market-neutral multi-activo **técnicamente impecable** (7 sleeves validados, maxDD vivo −3.4% vs ancla −10%,
β≈0, 0 bugs en 18 días) que se archivó **no por fallo de ingeniería**, sino porque su modelo de negocio
(copy-lead de bajo drawdown a micro-capital) **no generaba retorno visible sin tiempo (6-18 meses) ni escala**, y
porque la única vía de mejora —sleeves nuevos— estaba **bloqueada estructuralmente** (ver §4). El sistema funcionó;
la tesis de producto no.

---

## 1. ACTIVOS REUTILIZABLES — código y arquitectura (lo más valioso)

### 1.1 Harness de validación (el oro — directamente portable)
Todo esto es agnóstico al edge y sirve para CUALQUIER estrategia cuantitativa futura:
- **Walk-forward con OOS purgado + embargo + CPCV** (combinatorial purged CV) — evita el leakage temporal que
  infla Sharpes. (`research/e72`, e37, e79.)
- **Costos reales en el backtest:** maker/taker con BNB (0.018%/0.045%), **slippage función de ADV**
  (`50/√ADV_M`, clip 0.5-30 bps), turnover × slip. Nada se promueve sin sobrevivir taker. (`research/e18_slippage`.)
- **Leave-One-Out (LOO):** quitar cada símbolo y medir Δ → detecta edges que dependen de 1 coin (frágiles).
  Mató/marcó varios candidatos. (`e66`.)
- **β-neutralización** (`Σwβ=0` exacta diaria) + **net-$ λ-neutralización** (proyección 2-restricciones que
  cancela parte del net preservando β=0). (`kepler/lowbarrier._net_neutralize`, `_beta_neutralize`.)
- **vol-parity combine** de sleeves uncorr + **`leverage_for_maxdd_anchor`** (calcula el lev para CLAVAR un maxDD
  objetivo, en vez de fijar un multiplicador). Esto es un framework de riesgo reutilizable: **el tier = presupuesto
  de maxDD**, el lev se deriva. (`kepler/portfolio.py`.)

### 1.2 Infraestructura de "sombras" (shadow signals) — patrón muy reusable
Registrar en vivo, cada ciclo y **point-in-time**, los pesos que un sleeve candidato TENDRÍA, **sin operarlo**
(tabla `shadow_signal`). Permite validación OOS honesta sobre datos que no se pueden re-pedir después
(el dato on-chain se revisa). Es la forma correcta de "probar antes de arriesgar". (`kepler/onchain.py`, `e33`.)

### 1.3 Arquitectura del motor (plantilla limpia para un bot autónomo)
```
config (universo/fees/límites) → fetch (binance.vision, refresh incremental) → db (SQLite = fuente de
verdad + auditoría + export JSON) → alphas (señales) → portfolio (combine/metrics/lev) → engine (cerebro:
target) → execution (maker GTX, no-fill mgmt, capital-aware drop) → circuit_breaker → orchestrator
(heartbeat 15min + rebalance 24h) → notify (ntfy) → report (matplotlib) → api (FastAPI + dashboard SPA)
```
Esta separación de capas aguantó meses de cambios sin romperse. **Reutilizable casi tal cual** para cualquier
bot de rebalanceo. El `orchestrator` (loop heartbeat/rebalance) y `execution` (maker, manejo de no-fills,
dropping adaptativo al capital) son especialmente sólidos.

### 1.4 Patrones operativos que probaron su valor en incidentes reales
- **Balance ilegible → OMITIR ciclo, no operar con valor falso** (0 churn). Salvó la cuenta cuando el demo de
  Binance caducó de golpe. *"Mejor un hueco que una curva falsa."*
- **Alarma de escalada** ("rebalanceo en riesgo, N omisiones, M min") — detecta cuando el sistema se queda mudo.
- **Equity = MTM (`totalMarginBalance`), nunca wallet** — si no, el maxDD intradía se subestima (y el maxDD bajo
  ERA el argumento de venta).
- **Gate de madurez de ratios** (`TRACK_MIN_DAYS_RATIOS=30`): no publicar Sharpe/Sortino con N pequeño
  (N=4 → "Sharpe −26" = basura que espanta). Honestidad de producto.
- **circuit breaker** (halt si equity cae X% desde el pico, reanuda al recuperar) en el heartbeat intradía.

### 1.5 Edges validados (con costos, walk-forward) — reaprovechables si el universo encaja
7 sleeves con corr~0: XS-momentum 30d, XS-reversión 60d, low-vol 14d, carry (funding), trend EMA20/100,
taker-flow 5d, HL-position 14d. **MVRV (valor on-chain)** quedó validado standalone (Sharpe 0.71, sobrevive
taker) pero murió en el universo barato — **sirve en un universo amplio** (BTC/ETH/L1 grandes).

---

## 2. LECCIONES MÉTODO (cómo trabajar — transferible a TODO proyecto)

1. **REGLA DE ORO: nada a producción sin backtest que confirme mejora.** Repetidamente evitó desastres:
   refutó el scalp "+$1" (e83), el long-bias "verde constante" (e81), el sim-40d en low-barrier (e79),
   resucitar pares/stat-arb. **El instinto sin números casi siempre estaba equivocado.** Mantener en futuros.
2. **Gates PRE-REGISTRADOS:** decidir las reglas de continuar/parar ANTES de ver los datos → juzgar por reglas,
   no por frustración. (El gate 30/60d de seguridad vs el gate 6-18m de rentabilidad.)
3. **Honestidad estadística dura:** un Sharpe ~1.4 necesita **~6 meses para t-stat≥1** y **~2 años para p<0.05**.
   No se puede declarar un edge vivo NI muerto con semanas de datos. Saberlo evita tanto el pánico como el autoengaño.
4. **Separar pérdida REALIZADA (costes/churn) de MTM no realizada (mercado)** al diagnosticar. Varias veces el
   "está perdiendo" era ruido de mercado β-neutral, no un bug.
5. **La caza de alfa gratis se AGOTA.** Tras ~80 experimentos, los sleeves marginales ya no movían la aguja. Saber
   cuándo la frontera de research dejó de pagar y pivotar a operación/producto/escala.
6. **Etiquetar, no borrar, el pasado con bugs** (track inception limpio tras los fixes; datos viejos archivados).

---

## 3. LECCIONES TÉCNICAS

- **maxDD como presupuesto, no el leverage como dial.** Fija el riesgo, deriva el tamaño. Cada mejora de Sharpe →
  más retorno al MISMO maxDD (flywheel). Framework de riesgo limpio y reusable.
- **El ancla de maxDD reacciona a la vol reciente** → en un crash baja el lev (protege) y no "converge" al número
  de diseño. No es bug; es el ancla haciendo su trabajo. (No malinterpretar como leak — memoria `kepler-leverage-anchor-not-a-leak`.)
- **min-notional × nº-posiciones = barrera REAL** (de capital propio Y del copiador). Cuantificarla ANTES de fondear
  (casi shippean con barrera ~$7k para el copiador). Una estrategia de 18 patas tiene un techo de afiliados estructural.
- **Maker GTX llena casi sin slippage** (~1 bps mediana en rebalanceo incremental); el coste real está en armar el
  libro desde plano (one-off ~6 bps). El rebalanceo lento (24h) NO muere por costes; rebalancear rápido SÍ.

---

## 4. LA LECCIÓN ESTRATÉGICA GRANDE (la que mató al proyecto — no repetir)

**El modelo de negocio y la fuente de alfa deben ser COMPATIBLES desde el día 1. Verificarlo es tan crítico como validar el edge.**

KEPLER tuvo DOS conflictos estructurales que ningún Sharpe podía resolver:

1. **Negocio ⊥ research.** El producto (copy-lead → coins BARATOS para que el copiador pueda permitírselo,
   "low-barrier") **mató la cantera de research** (toda on-chain: TVL/MVRV/direcciones, datos que solo existen
   para coins CAROS: BTC/ETH/BCH/LTC). MVRV daba +2.15%/mes en universo amplio y **−0.40%/mes** restringido a los
   coins baratos. → *Toda sombra on-chain estaba condenada a morir al tocar el universo del libro.* Esto no se
   descubrió hasta el final. **Lección: mapear "¿mi fuente de alfa cubre el universo que mi negocio me obliga a operar?" ANTES de construir.**

2. **Producto ⊥ psicología del mercado.** Un market-neutral de bajo drawdown es **"invendible" como copy-lead en
   cripto** — nadie copia una curva plana con dientes rojos; el mercado persigue ROI llamativo (los martingalas 20x
   que revientan). La virtud (supervivencia, bajo maxDD) no es lo que el copiador compra. → A micro-capital, sin
   retorno visible, **no puede atraer a los copiadores que necesita para tener AUM**. Pez que se muerde la cola.

3. **Micro-capital sin escala = sin sentido económico.** A $293, aun clavando +3.5%/mes son ~$10/mes. **El único
   valor era el track verificable → AUM**, y eso requería 6-18 meses que Oscar (legítimamente) no quiso financiar
   sin señal de vida. La palanca de magnitud (tier GROWTH, +11%/mes backtest) existía y estaba validada, pero seguía
   montada sobre el mismo Sharpe sin confirmar → más retorno Y más riesgo, no más certeza.

---

## 5. QUÉ NO REPETIR (trampas catalogadas)
- Construir la cantera de research sobre un dato **incompatible con el universo de despliegue**.
- Elegir un producto cuya propuesta de valor **pelea contra la psicología del mercado** al que apunta.
- No cuantificar la **barrera de entrada del cliente/copiador** antes de fondear.
- Confundir **ruido de muestra corta** con muerte/vida del edge (gates pre-registrados lo evitan).
- Las firmas **short-vol / martingala / average-down** (TP chico, hold-hasta-revertir, promediar a perdedores):
  ganan casi siempre y revientan una vez. Refutadas con backtest (e83). NO son edge, son cobrar prima de cola.
  (Memoria `kepler-pivotes-scalp-tradfi-refutados`.)
- "Verde cada día" no es estrategia, es estructura de comisión (high-water-mark). (Memoria `kepler-longbias-refuted-green-is-fee`.)

---

## 6. PUENTE A FUTUROS PROYECTOS
- **tvindicators (vivo, direccional, corr~0 con KEPLER):** hereda el harness de validación, la disciplina de la
  regla de oro, los gates pre-registrados, y la infra de ejecución/auditoría. Su edge (WR 42% **dejando correr
  ganadores** con ATR-stop) es lo OPUESTO al scalp refutado — coherente con lo aprendido.
- **Si vuelve un market-neutral cripto:** operar el universo AMPLIO (incluir BTC/ETH/L1 grandes) para que el
  on-chain (MVRV especialmente) y la diversificación funcionen; aceptar una barrera de copia mayor, o NO atarlo
  a copy-lead. El edge MVRV está listo para resucitar ahí.
- **Reutilizar directamente:** `research/` (harness completo), `kepler/portfolio.py` (riesgo), `kepler/execution.py`
  (ejecución maker robusta), `kepler/db.py` (auditoría + sombras), arquitectura orchestrator/circuit_breaker.
- **DB final archivada:** `archive_final_2026-06-26/kepler_final.db` (track real 18d + 1988 sombras + auditoría) —
  evidencia y datos OOS para cualquier re-análisis futuro.
