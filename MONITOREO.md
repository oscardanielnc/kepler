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

1. **Concentración (top_position).** Hoy **TRX ~18%** empujado por el sleeve `trend` (long-only). No es
   bug, pero es el riesgo de un solo nombre. **Acción si >20-25% sostenido:** revisar si trend domina;
   evaluar cap por activo más estricto en trend (con backtest, regla de oro). Vigilar también que TRX no
   arrastre el β.
2. **Slippage real (C3).** Primer dato (2026-05-31): **mediana ~1.5 bps, media ~1.3** — menor que el
   modelo e18 (~4 bps central). Peor en thin coins (ZEC, XLM). **Acción:** acumular varios días → correr
   `research/e21_fill_slippage` → recalibrar K de e18 → re-correr e18 = costo HONESTO real. Si la mediana
   sube > 10 bps de forma sostenida, la ejecución maker se está degradando (revisar no-fills/GTX).
3. **Ancla de leverage vs maxDD real (hallazgo e29).** El leverage se fija con el maxDD PASADO →
   **sobre-apalanca OOS** (en walk-forward el maxDD llegó a −13.5% vs −10% objetivo). **El −10% PUEDE
   excederse en vivo.** Vigilar `drawdown_pct`: si supera −10% con holgura, confirma e29 → priorizar
   **ROADMAP D0** (haircut de leverage / calibrar sobre el peor tramo). NO subir de tier hasta resolverlo.
4. **Tormenta de reinicios (cycles_today).** Cada reinicio del servicio dispara un ciclo inmediato →
   rebalanceo extra = turnover/costo extra. En días de deploy es normal (hoy 3 ciclos). **Acción si
   persiste sin deploys:** revisar por qué se reinicia `kepler.service` (journalctl).
5. **β real del libro.** Hoy el snapshot guarda `beta=0.0` HARDCODEADO (no se calcula en vivo) →
   ROADMAP D1. Mientras tanto, vigilar `net` y la coherencia long/short. El β validado en backtest es
   ≈+0.05; confirmar en vivo cuando D1 esté.
6. **Equity ilegible / balance falso.** Ya blindado (heartbeat y ciclo OMITEN si el balance no se lee, no
   inventan 5000). Si ves escalones planos a 5000 exactos → regresión de ese fix.
7. **Circuit breaker.** `cb_operate=false` = HALT por −20%. Debe ser rarísimo en ESTABLE. Si salta,
   investigar a fondo (no debería con maxDD objetivo −10%).

---

## 3. BITÁCORA (registro por día — el más nuevo arriba)

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
- [ ] **D0 (riesgo, prioritario):** el ancla de leverage puede exceder el −10% en vivo (e29). Diseñar
      haircut / calibración robusta + backtest. **Antes de subir de tier.**
- [ ] **D1:** `beta` del snapshot está hardcodeado a 0.0 → calcular β real del libro en vivo.
- [ ] **Concentración trend/TRX:** evaluar cap por activo en trend (con backtest) si supera ~20-25%.
- [ ] **`r_multiple`/`exit_px` quedan null** (sistema de rebalanceo rodante, sin ciclo open→close clásico).
      El ciclo de vida de trade completo sería otro proyecto. Los fills+snapshots ya permiten analizar.
- [ ] **Shadow on-chain TVL:** pendiente deploy; tras semanas, medir su retorno point-in-time real y
      decidir promover a sleeve #8 (o no).
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
