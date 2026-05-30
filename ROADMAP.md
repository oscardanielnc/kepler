# KEPLER — ROADMAP de mejora (faro: Medallion / Renaissance)
> Estado congelado 2026-05-30. Sistema de **7 sleeves + ancla maxDD −10%** publicado en la VM (DEMO).
> Backtest: Sharpe 1.94 · ann 42.2% · maxDD −10% · β +0.03. **El 1.94 es de backtest; en vivo bajará.**
> Misión de este roadmap: subir el TECHO del backtest (más Sharpe robusto) para que lo que sobreviva
> al contacto con el mercado siga siendo de primer nivel. Copy-lead honesto de bajo drawdown.

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
- [ ] **A2. Order-book imbalance / profundidad** (bid-ask, depth). Requiere fuente nueva de datos.
- [ ] **A3. On-chain** (flujos de exchange, stablecoin supply, activos en wallets). Fuente nueva.
- [ ] **A4. Cross-exchange basis / spread** (perp vs spot, perp Binance vs otros).
- [ ] **A5. Estacionalidad / efectos calendario** (hora del día, día de semana, vencimientos).
- [x] ~~OHLCV derivados~~ agotado (e16: precio→correlado). ~~Open Interest / long-short~~ no aporta (e16f).

### B. ROBUSTEZ DE VALIDACIÓN  ← para que el backtest mienta MENOS
El objetivo no es subir el número, es que el número sea creíble (menos gap backtest↔vivo).
- [ ] **B1. Purga + embargo** en el walk-forward (gap entre train y test para evitar fuga por solापe
      de ventanas rolling). Hace el OOS más honesto.
- [ ] **B2. Validación combinatoria (CPCV)** o múltiples cortes IS/OOS, no uno solo. Reduce el riesgo
      de elegir un sleeve que funcionó por suerte en un corte.
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
- [ ] **D1. Validación del β en vivo** (no solo backtest): confirmar que el libro real mantiene β≈0.
- [ ] **D2. Monitor de correlación entre sleeves en vivo:** si dos sleeves empiezan a correlacionar
      (su diversificación se rompe), avisar. La diversificación es nuestro control de riesgo nº1.
- [x] ~~Monitor de riesgo intradía~~ BLOQUEADO (e15: necesita backtester horario que reproduzca el edge).

### E. PRODUCTO / TRACK RECORD
- [ ] **E1. Dejar correr DEMO semanas** y medir el Sharpe REAL vs el 1.94 de backtest. ← EL NÚMERO HONESTO.
- [ ] **E2. Reporte de track record verificable** (curva de equity, métricas mensuales) para AUM.
- [ ] **E3. Cuando demo confirme:** evaluar paso a REAL con capital chico. Decisión de Oscar.

---

## QUÉ SE PUEDE VALIDAR/IMPLEMENTAR AHORA MISMO (sin esperar a la demo)
Estos NO dependen de tiempo en mercado, son research puro sobre datos que ya tenemos o bajamos:
1. ~~**A1 — Ampliar universo**~~ → DESCARTADO (e17/e17b: edge errático + leverage frágil). ← hecho.
2. **C1 — Slippage por liquidez** en el backtest. Re-evaluar los 7 sleeves con costos realistas. ← SIGUIENTE.
3. **B1/B3 — Purga+embargo y Deflated Sharpe** en el harness. Hace honestos los números que ya tenemos.
4. **A4 — Cross-exchange basis** (perp vs spot): ya tenemos spot de BTC/ETH; ampliable.

Recomendación de orden: **C1 → B3 → A4**. (Costos honestos primero — acercan el número al real;
luego validación honesta; luego explorar un sleeve nuevo de fuente genuina.)

---
*Mantener este archivo vivo: marcar [x] lo hecho, mover a STATUS.md el detalle de cada sesión.*
