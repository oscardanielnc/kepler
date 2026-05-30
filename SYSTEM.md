# KEPLER — Sistema validado (v1) + posicionamiento copy-lead
2026-05-29. Validación: research/e14_more_sleeves.py (4.4 años, walk-forward, fees reales).

## Los 5 sleeves (correlaciones ~0 entre sí → diversifican)
| # | Sleeve | Señal | Sharpe solo | IS/OOS |
|---|--------|-------|-------------|--------|
| 1 | XS-Momentum 30d | +retorno pasado, β-neutral | 0.72 | +0.62/+0.89 |
| 2 | XS-Reversión 60d | −retorno pasado, β-neutral (anti-corr −0.5 c/momentum) | 0.56 | +0.58/+0.67 |
| 3 | Low-vol 14d | −volatilidad, β-neutral | 0.31 | +0.45/+0.31 |
| 4 | Carry | short funding alto/long bajo, rebal 48h | 0.64 | +0.59/+0.76 |
| 5 | Trend long-only | EMA20/100 direccional, vol-target | 0.52 | (overlay) |

Combinados (vol-parity): **Sharpe +1.34 (IS +1.34/OOS +1.48)**, vol 14%, maxDD −11% (1x).

## Niveles de riesgo (producto copy-lead)
**Regla 2026-05-30 (Oscar): el tier define un PRESUPUESTO DE maxDD; el leverage se CALCULA para
clavarlo.** ESTABLE = −10% fijo. Cada sleeve nuevo que baje el maxDD a 1x → sube el leverage → más
retorno al mismo riesgo. (`engine.TIERS` = {ESTABLE 0.10, BALANCEADO 0.20, GROWTH 0.30}; cap
`MAX_STRAT_LEVERAGE=4.0`.) Excepción: si subir el maxDD diera un salto desproporcionado, avisar a Oscar.

| Tier | maxDD objetivo | leverage* | ROI/año* | Mensual* |
|------|----------------|-----------|----------|----------|
| **ESTABLE** ← producción | **−10%** | ~1.92x | **+42.2%** | **+3.52%** |
| BALANCEADO | −20% | cap 4x | ~+85% | ~+7% |
| GROWTH | −30% | cap 4x | ~+85% | ~+7% |
*Con 7 sleeves (Sharpe 1.94), 2026-05-30. maxDD del BACKTEST (futuro puede ser peor; circuit
breaker −20% como red). Histórico 5 sleeves multiplicador fijo (referencia): ESTABLE 1x +21%/−11%,
BALANCEADO 2x +47%/−21%, GROWTH 3x +77%/−31%.

## Posicionamiento (research de foros)
NO competimos por ROI llamativo (eso lo hacen los martingalas que revientan). Competimos por
lo que el capital con criterio (pegajoso, tickets grandes) busca y casi nadie ofrece:
**bajo drawdown, supervivencia en crashes, consistencia, transparencia, longevidad.**
Tier BALANCEADO (47%/−21%) = ROI atractivo CON maxDD bajo el umbral (<30%) + honesto.
El foso = TIEMPO: cada mes que sobrevivimos mientras los Brayan revientan, componemos confianza/AUM.

## Universo / costos
32 perps líquidos (config.UNIVERSE); sleeves cross-secc usan los 23 con >=2a historia.
Fees Futures+BNB: maker 0.018%/taker 0.045%. Ejecución maker-first.

## DESCARTADO (no resucitar — walk-forward)
stat-arb pares, reversal corto, lead-lag timing, cash-and-carry absoluto, copiar a Btc-Panda
(martingala 20x = ruina, E13).

## Estado de implementación (2026-05-29)
CONSTRUIDO: data (fetch_1m), db (auditoría), alphas (5 sleeves), portfolio (vol-parity),
engine (motor live → portafolio objetivo), execution (rebalanceo maker, DRY_RUN), report (gráficos).
Motor live ESTABLE 1x: **Sharpe 1.13, ann +15.7%, maxDD −11.6%, 67% meses+** (número de producción).
Nota: intenté reconciliar a 1.34 (carry-breadth + gate de régimen) — AMBOS empeoraron el maxDD →
descartados (workflow). 1.13/−11.6% es el mejor perfil de riesgo para copy-lead de bajo DD.

## CHECKLIST PARA PRODUCCIÓN (estado al 2026-05-30 — ver STATUS.md para lo último)
1. [x] Precisión/min-notional por símbolo en execution (load_filters).
2. [x] Refresh de datos programado (fetch.update_universe antes de cada rebalanceo).
3. [x] Orquestador/scheduler (orchestrator.py: heartbeat 15min + rebalanceo 24h).
4. [x] Gestión de fills maker (re-colocar/perseguir, aceptar parciales).
5. [x] Circuit breaker de cartera (halt −20% del pico).
6. [x] Reconcile al arranque (execution.get_positions vs target).
7. [x] Track record: equity_tick + equity_daily + dashboard (rentabilidad total/diaria, posiciones reales+PnL).
8. [x] Monitoreo/alertas (notify.py ntfy: ciclo, error, halt).
9. [~] VALIDACIÓN EN DEMO: EN CURSO desde 2026-05-29. Dejar correr días/semanas. CRÍTICO antes de real.
+  [x] Apalancamiento conservador por símbolo (set_leverage 3x).
+  [x] β-neutralidad auditada 2026-05-30: β combinado realizado = +0.05 (<0.10 tol), Sharpe 1.13/maxDD
       −11.6% reproducidos. El libro es net-long en DÓLARES (~76%) pero β≈0 (longs bajo-beta + hedge
       BTC + trend overlay long-only). net-en-$ ≠ β-neutralidad. No es bug.
+  [ ] Monitor de riesgo intradía → BLOQUEADO: requiere backtester horario fiable (research/e15 no lo logra).
+  [x] Sleeve #6 `taker_flow` (flujo de órdenes, 5d=120h) VALIDADO + IMPLEMENTADO 2026-05-30
       (research/e16b+e16c; commit bf83594). corr 0.06.
+  [x] Sleeve #7 `hlpos_14d` (posición en el canal, 14d=336h) VALIDADO + IMPLEMENTADO 2026-05-30
       (research/e16d+e16e). corr 0.20, Sharpe propio 1.19 (IS/OOS 1.09/1.33).
+  [x] Ancla de maxDD −10% con leverage auto-calculado (regla Oscar; commit d0206b1).
       Motor 7 sleeves @−10%: lev 1.92x · Sharpe 1.94 · ann 42.2% (~3.52%/mes) · β +0.028. Falta DEMO.

## Loop de mejora diario (subir los números)
Añadir 1 sleeve uncorr/semana (validar walk-forward) → sube Sharpe → baja DD → mejores números.
A 1x es ~1.3%/mes; subir a tier 2x (47%/año, −21%DD) cuando haya track record.
