# KEPLER — Estado vivo · Changelog · Pendientes
> **Empieza cada sesión leyendo este archivo.** Última actualización: **2026-05-30** (mañana, hora Lima).

---

## ESTADO ACTUAL
- ✅ Sistema **desplegado y operando en DEMO** en la VM (Oracle, `opc@oscar-cripto-sentinel-b26`).
- ✅ Servicios `kepler` y `kepler-api` **activos**. Dashboard visible en http://213.35.121.9:8080
- ✅ Primer ciclo ejecutado: colocó ~15 órdenes límite maker en la cuenta demo (modo DEMO confirmado).
- ✅ Circuit breaker activo (halt a −20% del pico). Alertas ntfy configuradas.
- ⚠️ **PENDIENTE INMEDIATO: hacer push de los cambios locales de hoy + `deploy.sh`** (ver changelog abajo).
  Los cambios de hoy (leverage 3x + mejoras de frontend) **están en local, aún NO en la VM.**

---

## CHANGELOG 2026-05-30 (mañana — análisis + backtest monitor intradía)

### Verificación de estado real vs docs
- El push de la sesión previa **YA estaba hecho** (commit `front` en `origin/main`, árbol limpio).
  El pendiente #1 "push" estaba desactualizado. Lo que SÍ falta: confirmar en la VM que corrió
  `deploy.sh` con el último commit, que el dashboard se puebla, que demo llena, y **por qué el
  equity sale plano = 5000.0** en los logs (¿flat real o `get_balance()` cayendo al fallback?).
- Repo limpio: `.gitignore` OK, `kepler.db`/`data/`/`logs/` no trackeados ✅.

### E15 — Monitor de riesgo intradía: BACKTEST EN CURSO (v1 con BUG → INCONCLUSIVO)
- `research/e15_intraday_monitor.py` (v1). Reconstruye equity horaria y aplica un monitor que
  des-riesga ×f cuando el equity intradía cae −X%.
- **BUG metodológico detectado:** v1 **netea los pesos por activo** antes de marcar (mom largo BTC +
  rev corto BTC se cancelan → libro chico dominado por ruido). Su baseline da Sharpe −0.23/maxDD −39%,
  que **NO reproduce el edge validado** (+1.13/−11.6%). Verificado: los 3 sleeves a nivel diario,
  combinando RETORNOS por sleeve (no pesos), dan Sharpe ~1.13. ⇒ cualquier veredicto del monitor
  desde v1 es inválido. **Pendiente #3 SIGUE ABIERTO.**
- **Arreglo pendiente:** construir la equity horaria combinando la equity de cada sleeve corrido por
  separado (gross=1), no neteando pesos; luego aplicar el monitor sobre la equity combinada.

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
1. **[HACER PRIMERO]** Push de los cambios de hoy + `bash /opt/kepler-app/kepler/deploy.sh` en la VM.
   Verificar dashboard: rentabilidad total/diaria poblándose y posiciones reales con PnL.
2. **Dejar correr en demo varios días** y revisar logs: que las posiciones igualen el objetivo,
   que los maker llenen, sin errores. (Validación demo = CRÍTICA antes de pensar en real.)
3. **Monitor de riesgo intradía** (pendiente de backtest VÁLIDO): v1 (`research/e15`) tiene bug
   metodológico (netea pesos). Arreglar (combinar equity por sleeve) → backtestear → números antes
   de implementar. Hipótesis a confirmar/refutar: "gestión intradía = el juego que pierde".
4. **Loop de mejora diario**: añadir 1 sleeve no-correlacionado/semana, validado walk-forward,
   para subir Sharpe / bajar maxDD (ver `SYSTEM.md`).
5. Revisar `heartbeat` a 5 min si Oscar quiere la curva más fina (ahora 15 min).
6. Cuando haya track record real → evaluar subir a tier BALANCEADO (decisión de Oscar).

## RECORDATORIO PERSISTENTE
- Oscar debe **retirar $1800 de Brayan / Btc-Panda** (martingala 20x, ruina probada en research/e13).
