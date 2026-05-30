# KEPLER — Estado vivo · Changelog · Pendientes
> **Empieza cada sesión leyendo este archivo.** Última actualización: **2026-05-30** (mañana, hora Lima).

---

## ESTADO ACTUAL
- ✅ Sistema **desplegado y operando en DEMO** en la VM (Oracle, `opc@oscar-cripto-sentinel-b26`).
- ✅ Servicios `kepler` y `kepler-api` **activos**. Dashboard live OK en http://213.35.121.9:8080
  (verificado 2026-05-30: equity vivo ~4933, 14 posiciones source="real" con PnL, heartbeats fluyendo).
- ✅ Circuit breaker activo (halt a −20% del pico). Alertas ntfy configuradas.
- ✅ **β-neutralidad auditada (2026-05-30): β combinado = +0.05, Sharpe 1.13 / maxDD −11.6% reproducidos.**
  El "76% net long en dólares" es esperado (longs bajo-beta + hedge BTC + trend overlay), NO un fallo.
- ✅ Cambios previos (leverage 3x + frontend) ya en origin/main. Falta confirmar `deploy.sh` en la VM.

---

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
- PENDIENTE: implementar en `alphas.py` + `engine.SLEEVES` (confirmar β≈0) → validar en DEMO
  antes de considerarlo producción (regla de oro: backtest ✓, falta demo).

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
1. **Confirmar `deploy.sh` en la VM** con el último commit y dejar **correr en demo varios días**:
   posiciones = objetivo, maker llenan, sin errores. (Validación demo = CRÍTICA antes de real.)
2. **[LISTO PARA IMPLEMENTAR] Integrar sleeve #6 `taker_flow` (5d).** Backtest ✓ (e16b/e16c):
   Sharpe 1.13→1.36, maxDD −11.6→−8.6%. Falta: añadir a `alphas.py` (`xs_takerflow_score`) +
   `engine.SLEEVES`, cargar volume/taker_buy_volume en `engine.load`, confirmar β≈0, validar DEMO.
   Más adelante: seguir el loop (1 sleeve uncorr/semana). Próxima fuente a probar: order-book/OI.
3. **Monitor de riesgo intradía** → BLOQUEADO: requiere primero un BACKTESTER HORARIO fiable
   (`research/e15` v1/v2 no reproducen el edge diario). La teoría ya lo desaconseja (CLAUDE.md:
   "gestión intradía = el juego que pierde"). El riesgo intradía lo cubren circuit breaker +
   diversificación + β≈0. No retomar sin construir antes el motor horario.
4. Revisar `heartbeat` a 5 min si Oscar quiere la curva más fina (ahora 15 min).
5. Cuando haya track record real → evaluar subir a tier BALANCEADO (decisión de Oscar).

## RECORDATORIO PERSISTENTE
- Oscar debe **retirar $1800 de Brayan / Btc-Panda** (martingala 20x, ruina probada en research/e13).
