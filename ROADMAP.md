# KEPLER — ROADMAP de mejora (faro: Medallion / Renaissance)
> Estado congelado 2026-05-30. Sistema de **7 sleeves + ancla maxDD −10%** publicado en la VM (DEMO).
> Backtest: Sharpe 1.94 · ann 42.2% · maxDD −10% · β +0.03. **El 1.94 es de backtest; en vivo bajará.**
> Misión de este roadmap: subir el TECHO del backtest (más Sharpe robusto) para que lo que sobreviva
> al contacto con el mercado siga siendo de primer nivel. Copy-lead honesto de bajo drawdown.

---

# 🧭 RUTA MAESTRA 2026-06 — Operación → Producto → Escala  ← EMPEZAR AQUÍ
> **Reescrita 2026-06-02.** Cambio de fase: la **caza de alfa GRATIS está agotada** (verificado a fondo:
> precio/derivados/on-chain-CM/DefiLlama/sentiment/netflow/intradía/régimen → todo cosechado o descartado
> con números). La doctrina Medallion (muchas señales chicas uncorr) ya está aplicada; el techo de alfa
> nuevo gratis está tocado. **La PALANCA ahora NO es otro sleeve de +0.3%/mes — es OPERACIÓN + PRODUCTO +
> ESCALA.** Negocio = copy-lead (NO market-making tipo Hummingbot, el juego HFT que rechazamos).
> **🔑 PRINCIPIO CODE-FIRST (Oscar 2026-06-02): la IA es CARA y se comería el margen → todo lo que se pueda
> hacer con CÓDIGO determinístico (chequeos, alertas, reportes, anomalías por umbral/z-score) se hace con
> código. La IA se RESERVA solo para lo que el código no puede: clasificar una situación genuinamente
> NOVEDOSA que las reglas no contemplan (p.ej. un evento de mercado impredecible). Ni alfa (overfit) ni
> tareas codeables.** Ver memorias `kepler-news-ia-bots-decision`, `kepler-code-first-no-ia`.
> **Atacar EN ORDEN. Regla de oro sigue vigente:** nada a prod sin backtest/validación que confirme mejora.

## FASE 0 — EN CURSO (el FOSO REAL = tiempo; solo vigilar, no hay que "hacer")
- **F0.1 · Validación E1 (DEMO en el tiempo):** medir Sharpe/maxDD/β REALES vs backtest. Es el 80% del
  valor del producto (track record). Solo correr. Vigilar con MONITOREO.md.
- **F0.2 · Sombras → sleeve #8 (~2026-07-31):** tx_pxdiv + mvrv + blend acumulando en vivo. Cuando tengan
  60-90d → `python -m research.e33_shadow_tvl_analyze <db> <sleeve>` → promover si el Sharpe forward confirma.
  **Único "edge nuevo" en cola, y ya está montado/gratis.**
- **F0.3 · C3 slippage real:** telemetría ya limpia (winsor ZEC). Recalibrar el modelo de coste con fills
  reales cuando se acumulen (`e21_fill_slippage <db>`).

## FASE 1 — ROBUSTEZ OPERATIVA  ← PRIORIDAD ALTA (barato, protege TODO; el riesgo #1 hoy es operativo)
> Motivo: el incidente 2026-06-02 (VM sobre-apalancada 2.93x por backfill faltante) probó que el riesgo
> real ya NO es de alfa sino OPERATIVO. **TODO ESTO ES CÓDIGO DETERMINÍSTICO — CERO IA** (chequeos por
> umbral/banda/z-score, alertas ntfy, reportes templados). Diseño: un módulo único `kepler/checks.py`
> (librería de chequeos puros que devuelven severidad+mensaje), consumido pre-trade (orchestrator) y en
> heartbeat; `notify.py` manda el push; alertas con estado (solo en transición, no spam).
- **F1.1 · Guardas de sanity PRE-TRADE (`checks.py` + orchestrator):** antes de rebalancear, si leverage
  fuera de banda, datos viejos/panel truncado/cobertura < HIST_START, concentración > cap, o N posiciones
  ≠ esperado → BLOQUEAR el rebalanceo (mantener libro) + ntfy CRÍTICO. **Habría frenado el incidente de hoy.**
- **F1.2 · Health-check periódico + alertas ntfy (heartbeat):** datos frescos, sin huérfanas, CB OK, lev en
  rango, β en banda, slippage normal, equity sin saltos anómalos, ciclo corrió a horario. Código puro.
- **F1.3 · Monitor de integridad de datos (parte de `checks.py`):** histórico cubre desde HIST_START, panel
  no se acorta, ningún símbolo stale, funding fresco. Es el chequeo que ataca directo el bug de hoy.
- **F1.4 · Reporte profesional diario (CÓDIGO, templado — NO IA):** mejorar `report.py`/`daily_report` con
  un resumen claro de métricas + ANOMALÍAS POR REGLA (umbral/z-score sobre retorno/lev/concentración/slip/β).
  Narrativa por plantilla, no IA.
- **F1.5 · Monitor de correlación entre sleeves (`checks.py`, ROADMAP D2):** si dos sleeves empiezan a
  correlacionar (diversificación rota) → ntfy. Control de riesgo nº1, por código.
- **(Reservado, NO ahora) IA de escalación:** solo si surge una situación NOVEDOSA que las reglas no
  clasifican (evento de mercado impredecible). Hook futuro, llamada rara/barata. No es parte de esta fase.

## FASE 2 — PRODUCTO / TRACK RECORD  ← capta AUM (depende de que Fase 0 acumule semanas)
- **F2.1 · Reporte de transparencia para inversor:** curva equity, maxDD, Sharpe, meses+, β, exposición.
  Auto-generado; **IA escribe el resumen mensual/semanal legible** (uso operativo válido de IA).
- **F2.2 · Track record verificable / presentable:** exponer el dashboard actual de forma pública/limpia
  (o página dedicada). Honestidad cruda = nuestro diferenciador vs los martingala (Btc-Panda/Flowerence).
- **F2.3 · Preparar copy-lead:** investigar requisitos de Binance/Bybit copy-trading (cómo se publica y
  verifica el track, profit-share, mínimos). Checklist para cuando el track real lo respalde. ← el negocio.

## FASE 3 — CAPITAL / ESCALA  ← cuando el track record real lo respalde (decisión de Oscar)
- **F3.1 · Tier ESTABLE→BALANCEADO:** subir el presupuesto de maxDD solo con track real que lo justifique.
- **F3.2 · Capacidad/AUM:** slicing pasivo (e55, diferido) + cap de tamaño por liquidez (ROADMAP B4)
  cuando el AUM lo exija (cruce ~$1-4M en coins finos). Hoy a tamaño DEMO no aporta.
- **F3.3 · Retirar $1800 de Brayan/Btc-Panda** (martingala, ruina probada e13). Recordatorio persistente.

## ⏸️ PARKED — requiere $ o meses (NO ahora, decisión consciente)
- **Datos de pago** (si se quiere más alfa): CryptoQuant netflow ~$99/mo (per-token limpio) · Santiment Pro
  ~$50/mo (social sin lag+historia). Pipeline Dune montado (`dune_util.py`) por si se retoma gratis.
- **Backtester horario / colector intradía:** solo si se decide invertir meses (dato intradía no existe gratis).

## ✅ CERRADO — NO re-litigar sin algo nuevo
Ampliar universo (e17) · order-book diario+intradía (e23/24/45) · liquidaciones (e46-49, =ZEC) · CME gap
(e73) · monitor intradía e15 · universo-limpio (e74, ya limpio) · basis (e22) · opciones (e25) ·
estacionalidad (e28) · OI/LS (e16f) · régimen condicional (R0-R3) · size (e34/35) · on-chain Coin Metrics
(agotado, 2 ganadores tx+mvrv en sombra) · sentiment gratis (Trends frágil / Santiment free limitado) ·
netflow Dune (parado por Oscar) · noticias/conviction-override (muerto por diseño) · IA-como-alfa · Hummingbot/MM.

---

## FILOSOFÍA (qué copiar de Medallion y qué NO)

Medallion (Renaissance) = ~39% neto/año, Sharpe ~2.5+, 30+ años. Cerrado a externos desde 1993.
NO es comparable directo (ellos: track real auditado; nosotros: backtest). Pero su MÉTODO sí inspira:

**Lo que SÍ aplica a Kepler (y debemos perseguir):**
1. **Muchas señales débiles descorrelacionadas** > pocas señales fuertes. RenTech corre cientos.
   Cada una con Sharpe bajo, pero su combinación cancela ruido → Sharpe del conjunto altísimo.
   *Nosotros: 7 sleeves. El camino es 15-30+ sleeves genuinamente ortogonales.*
2. **Disciplina de validación brutal:** walk-forward, costos reales, sin lookahead. Ya lo hacemos.
   Refuerzo: añadir purga/embargo y validación out-of-sample más estricta (ver §B).
3. **Reinversión y composición:** el edge compuesto en el tiempo es el motor. Nuestro ancla de maxDD
   fijo + leverage auto ya está alineado (mejora del Sharpe → más retorno al mismo riesgo).
4. **Neutralidad de mercado / factor:** RenTech no apuesta dirección. Nosotros β≈0 ya. Mantenerlo.
5. **Costos de transacción modelados al detalle:** ellos optimizan cada bp. Nosotros maker-first.
   Refuerzo: modelar slippage por liquidez del símbolo (ver §C).

**Lo que NO aplica (no perseguir, sería quemar recursos):**
- HFT / baja latencia en microsegundos: nuestra estrategia es LENTA (rebal 24h). Irrelevante.
- Market-making / rebates institucionales: no somos exchange.
- Apalancamiento extremo: es el juego que mata (Flowerence/Brayan). El ancla −10% es lo opuesto.

---

## EL FOSO REAL = TIEMPO (no se puede acelerar)
Medallion vale por 30 años probándolo, no por su Sharpe. **Nuestro track record real = 0.**
Esto solo se cierra dejando correr DEMO → REAL con disciplina. Es el 80% del valor del producto.
Todo lo demás (abajo) sube el techo; esto convierte el techo en confianza/AUM.

---

## ROADMAP PRIORIZADO (impacto × facilidad)

### A. MÁS SLEEVES DESCORRELACIONADOS  ← el corazón del método RenTech
Cada sleeve genuino con corr<0.35 y que mejore el retorno anclado sube el Sharpe del conjunto.
Criterio de admisión (ya validado en e16): **walk-forward IS/OOS>0.10 + corr<0.35 + Δretorno@−10%>+0.1%/mes + pasa estrés (horizonte/costos/sub-períodos).**
Fuentes por explorar (en orden de promesa, la OHLCV y positioning ya están agotadas):
- [x] ~~**A1. Ampliar el universo**~~ → DESCARTADO 2026-05-30 (e17/e17b): edge errático (peor en 2/4
      cuartiles), 85% de la "mejora" era leverage extra del ancla (1.92x→2.76x), y concentrada en AXS.
      Sistema se queda en 32 perps. Ver STATUS tarde-5.
- [x] ~~**A2. Order-book imbalance / profundidad**~~ → DESCARTADO como sleeve DIARIO 2026-05-31
      (e23/e24): real y ortogonal (corr 0.06–0.10), pero Δ al ancla maxDD −10% = **+0.00%/mes** (taker).
      Su edge genuino es **INTRADÍA** → movido a §F. Data en `data/bookdepth_daily/`. Ver STATUS noche.
- [x] ~~**A6. Opciones (Deribit / DVOL)**~~ → DESCARTADO 2026-05-31 (e25): Deribit solo BTC/ETH líquido
      → no cross-seccional (muro del basis); como overlay de timing es inestable (IS −1.15 / OOS +0.43%/mes)
      = gate de régimen ya descartado; DVOL 0.74 redundante con vol realizada (lowvol). VRP/short-vol sería
      otra estrategia (pila de opciones), no este sistema de perps. Ver STATUS noche-2.
- [x] **A3. On-chain** → **CERRADO 2026-05-31 (e26 chequeo + e27 build): edge REAL pero MODESTO.**
      GRATIS: TVL por cadena/protocolo (DefiLlama, 12 tokens). `tvl_pxdiv_14d` (acumulación = TVL sube más
      que precio): corr 0.11, OOS 1.27, **Δtaker +0.6%/mes** al ancla, turnover 42x. ✅ point-in-time PASA
      (edge en 2023+ Sharpe ~1.0, plano/neg en 2022 → no es backfill; clip no lo mata). ⚠️ banderas:
      horizonte estrecho (21d se va a −1.09), cross-section delgado (12 = techo de A3 aquí), neg en 2022.
      → REAL pero no slam-dunk; NO precipitar a prod. El free-TVL PRUEBA que el on-chain tiene edge →
      **justifica el netflow per-token de PAGO** (más limpio, point-in-time honesto, 32 nombres) en la
      lista "revisar información pagada". Decisión Oscar: (A) walk-forward+purga+demo del free-TVL, o (B) netflow pagado.
- [x] ~~**A4. Cross-exchange basis** (perp vs spot)~~ → PARADO 2026-05-31 (e22): basis ≈ funding/carry
      (corr 0.74 nivel · 0.53 cross-seccional · 0.70 predice funding) → duplicaría el sleeve #4, no
      diversifica. NO bajar spot del universo. Único ángulo vivo: el RESIDUAL (dislocaciones que el
      funding no ve), especulativo + necesita spot del universo. Ver STATUS tarde-2.
- [x] ~~**A5. Estacionalidad / efectos calendario**~~ → DESCARTADO 2026-05-31 (e28): día-de-semana falla
      OOS (overfit); turn-of-month/vencimiento PARECÍAN pasar OOS pero es ARTEFACTO del ancla (de-risk →
      clip drawdown → más leverage), no estacionalidad — smoking gun: vencimiento ±0d = +0.04 (nada), solo
      crece al ensanchar la ventana. = gate de régimen ya descartado. **Con esto el menú diario gratis queda AGOTADO.**
- [x] ~~OHLCV derivados~~ agotado (e16: precio→correlado). ~~Open Interest / long-short~~ no aporta (e16f).

### B. ROBUSTEZ DE VALIDACIÓN  ← para que el backtest mienta MENOS
El objetivo no es subir el número, es que el número sea creíble (menos gap backtest↔vivo).
- [x] **B1. Purga + embargo** en el walk-forward → HECHO 2026-05-31 (e29). vp+leverage ajustados
      solo-pasado con embargo 10d, curva 100% OOS. **Resultado: edge ROBUSTO** (Sharpe OOS 2.29 ≈ IS 2.21).
- [x] **B2. CPCV-lite** (6 folds) → HECHO (e29): **6/6 folds OOS positivos** (media +2.08, min +1.19).
      El Sharpe del sistema NO es overfit de selección de pesos.
- [ ] **B3. Deflated Sharpe Ratio** — penalizar el Sharpe por el nº de configuraciones probadas
      (evita el sesgo de "probé 100 cosas y elegí la mejor"). Honestidad estadística pura RenTech.
- [ ] **B4. Test de capacidad:** ¿cuánto capital aguanta cada sleeve antes de mover el mercado?
      Relevante al escalar AUM. Modelar impacto vs ADV (volumen diario) por símbolo.

### C. EJECUCIÓN Y COSTOS  ← cerrar el gap backtest↔vivo por el lado de los costos
- [ ] **C1. Modelar slippage por liquidez** del símbolo (no un 2bps plano). Los símbolos chicos
      cuestan más; el backtest debe penalizarlos para no sobreestimar.
- [ ] **C2. Optimización de turnover** a nivel cartera: hoy cada sleeve rebalancea por su cuenta;
      netear órdenes entre sleeves antes de ejecutar reduce costos reales.
- [ ] **C3. Análisis de fills reales en DEMO** vs target: medir el slippage REAL y recalibrar C1.

### D. GESTIÓN DE RIESGO / RÉGIMEN
- [ ] **D0. Ancla de leverage robusta (NUEVO, hallazgo e29 2026-05-31).** El walk-forward mostró que
      fijar el leverage con el maxDD pasado SOBRE-APALANCA out-of-sample (lev 3.0x, maxDD OOS −13.5% vs
      −10% objetivo) → **el −10% del backtest puede excederse en vivo.** Opciones: haircut de leverage,
      calibrar sobre el peor tramo histórico (no todo), o usar un cuantil conservador del maxDD. La DEMO
      lo confirmará (E1). Es lo opuesto a la misión bajo-DD → atacar antes de subir de tier.
- [ ] **D1. Validación del β en vivo** (no solo backtest): confirmar que el libro real mantiene β≈0.
- [ ] **D2. Monitor de correlación entre sleeves en vivo:** si dos sleeves empiezan a correlacionar
      (su diversificación se rompe), avisar. La diversificación es nuestro control de riesgo nº1.
- [x] ~~Monitor de riesgo intradía~~ BLOQUEADO (e15: necesita backtester horario). Movido a §F (F4) — el
      backtester horario es la llave común con order-book/liquidaciones intradía. Ver `INTRADAY.md`.

### E. PRODUCTO / TRACK RECORD
- [ ] **E1. Dejar correr DEMO semanas** y medir el Sharpe REAL vs el 1.94 de backtest. ← EL NÚMERO HONESTO.
- [ ] **E2. Reporte de track record verificable** (curva de equity, métricas mensuales) para AUM.
- [ ] **E3. Cuando demo confirme:** evaluar paso a REAL con capital chico. Decisión de Oscar.

### F. FRONTERA INTRADÍA  ← APARCADO a propósito (futuro, cuando el proyecto crezca)
Hoy Kepler es SOLO diario (rebal 24h). Hay evidencia de **edge real en microestructura a horizonte
SUB-DIARIO** (order-book, liquidaciones) que el sistema diario deja sobre la mesa. **Guía completa:
`INTRADAY.md`.** No es trabajo inmediato; el menú DIARIO (§A) sigue siendo el foco.
- **Llave común:** todo lo intradía está bloqueado por la falta de un **backtester horario fiable**
  (mismo cuello de botella que el monitor de riesgo, e15). Es un mini-proyecto, no un sleeve.
- [ ] **F1. Backtester horario** (requisitos en `INTRADAY.md` §3: forward-return correcto, coste de
      spread, turnover/capacidad, reconciliación con el diario @24h, validación brutal).
- [ ] **F2. Order-book intradía** (re-evaluar e23/e24 a 1h–12h con coste de spread real; bajar raw 30s).
- [ ] **F3. Liquidaciones intradía** (montar colector WS `@forceOrder` o Coinglass — sin histórico gratis).
- [ ] **F4. Monitor de riesgo intradía** (e15, sobre el mismo backtester).
- ⚠️ Línea roja: intradía = **señal lenta de horas con costos modelados**, NO HFT/market-making/latencia
  (fuera de la misión, CLAUDE.md). Mantener bajo maxDD y supervivencia, no ROI llamativo.

---

## QUÉ SE PUEDE VALIDAR/IMPLEMENTAR AHORA MISMO (sin esperar a la demo)
Estos NO dependen de tiempo en mercado, son research puro sobre datos que ya tenemos o bajamos.
**Hecho (2026-05-30/31):** ~~A1 universo~~, ~~C1 slippage (e18)~~, ~~B3 Deflated Sharpe (e20)~~,
~~A4 basis (e22)~~, ~~A2 order-book diario (e23/e24)~~. Todas las vetas baratas DIARIAS de PRECIO/
microestructura están agotadas o descartadas.

**Foco DIARIO vivo (orden sugerido), cada uno con chequeo de ortogonalidad barato ANTES de bajar histórico:**
1. ~~A6 Opciones (Deribit)~~ → DESCARTADO (e25: BTC/ETH-only + timing inestable). 
2. **A3 — On-chain:** flujos exchange POR ACTIVO, stablecoin supply. **Única con potencial cross-seccional**;
   ⚠️ histórico gratis dudoso (Glassnode/CryptoQuant de pago) → el chequeo barato empieza por "¿hay dato gratis?".
3. **A5 — Estacionalidad / calendario:** barato, no necesita datos nuevos; incierto.
4. **B1/B2 — Purga+embargo / CPCV** en el walk-forward: no sube el número, lo hace más creíble.

**Lección de la tanda 2026-05-31 (acota la búsqueda):** fuentes BTC/ETH-only (basis e22, opciones e25)
NO sirven (no cross-seccional); señales market-wide caen en el gate-de-régimen descartado; sleeves orto
pero débiles (order-book e24, Sharpe ~1.3) DILUYEN al ancla. Lo que queda debe ser **per-símbolo del
universo + ortogonal + lo bastante fuerte para subir el retorno al maxDD fijo con costos taker**.

⚠️ **Recordar el criterio (e16d/e24):** corr<0.35 + IS/OOS>0.10 **NO basta** — el sleeve debe subir el
retorno al **maxDD fijo con costos taker**. Un Sharpe orto pero bajo (~1.3) solo DILUYE el combinado.

**Frontera INTRADÍA (§F, `INTRADAY.md`):** aparcada a propósito; requiere el backtester horario. No ahora.

---
*Mantener este archivo vivo: marcar [x] lo hecho, mover a STATUS.md el detalle de cada sesión.*
