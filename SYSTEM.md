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
| Tier | ROI/año | maxDD | Mensual | Calmar |
|------|---------|-------|---------|--------|
| ESTABLE (1x) | +21% | −11% | +0.8% | 1.89 |
| **BALANCEADO (2x)** | **+47%** | **−21%** | +1.5% | 2.18 |
| GROWTH (3x) | +77% | −31% | +2.1% | 2.52 |

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

## CHECKLIST PARA PRODUCCIÓN (qué falta ajustar)
1. [ ] Precisión/min-notional por símbolo en execution (load_filters) — validar vs demo exchangeInfo.
2. [ ] Refresh de datos programado (fetch 1h+funding antes de cada rebalanceo).
3. [ ] Orquestador/scheduler (cron: fetch→engine→execution cada N horas) — rescatar supervisor de Sentinel.
4. [ ] Gestión de fills maker (re-colocar/perseguir si no llena; aceptar parciales).
5. [ ] Circuit breaker de cartera (halt si equity cae X%; límites gross/posición) — rescatar de Sentinel.
6. [ ] Reconcile al arranque (DB target vs posiciones Binance reales).
7. [ ] Track record: loguear fills reales + equity diaria + PnL → curva verificable.
8. [ ] Monitoreo/alertas (ntfy en errores, rebalanceos, movimientos grandes).
9. [ ] VALIDACIÓN EN DEMO: correr el loop completo con API keys demo días/semanas → confirmar
       fills, que posiciones igualan target, sin bugs. CRÍTICO antes de real.

## Loop de mejora diario (subir los números)
Añadir 1 sleeve uncorr/semana (validar walk-forward) → sube Sharpe → baja DD → mejores números.
A 1x es ~1.3%/mes; subir a tier 2x (47%/año, −21%DD) cuando haya track record.
