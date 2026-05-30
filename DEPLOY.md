# KEPLER — Despliegue (demo → producción)

El sistema corre el ciclo: **datos → 5 sleeves → portafolio objetivo → reconcile → circuit
breaker → rebalanceo maker → log**. Default **DRY_RUN** (no envía órdenes).

## 1. Probar local (DRY_RUN, sin riesgo)
```
pip install -r requirements.txt
python -m kepler.orchestrator ESTABLE --once     # un ciclo
python -m kepler.report                          # gráficos → logs/kepler_report.png
```

## 2. Desplegar en DEMO (track record + cazar bugs de ejecución)
1. Crear API keys en https://testnet.binancefuture.com (o demo-fapi) → exportar:
   ```
   $env:BINANCE_API_KEY="..."; $env:BINANCE_API_SECRET="..."
   ```
2. En `kepler/execution.py`: `DRY_RUN = False`, `USE_DEMO = True`.
3. Correr el loop (rebalancea cada 24h):
   ```
   python -m kepler.orchestrator ESTABLE
   ```
4. **Dejar correr días/semanas.** Verificar en la DB (`portfolio_snapshot`, `audit_event`) y en
   los JSON diarios (`logs/kepler_YYYY-MM-DD.json`) que: órdenes llenan, posiciones igualan el
   target, sin errores. ESTE es el paso crítico antes de dinero real.

## 3. Producción real (SOLO tras validar en demo con holgura)
- `kepler/execution.py`: `DRY_RUN=False`, `USE_DEMO=False`. Keys reales.
- Empezar con tier **ESTABLE (1x)** y capital pequeño. Subir a 2x cuando haya track record limpio.

## Servicio 24/7 (Linux VM — rescatar patrón de Sentinel)
`kepler.service` (systemd): correr el orquestador como servicio con reinicio automático.
Logs a journald + DB + JSON diario descargable para monitoreo.

## Parámetros clave
- Tier: ESTABLE 1x / BALANCEADO 2x / GROWTH 3x (en el argumento del orquestador).
- `REBALANCE_HOURS` (orchestrator.py): cada cuánto rebalancear (default 24h).
- `MAX_DD` (circuit_breaker.py): halt si equity cae 20% del pico.
- `MAX_WEIGHT_NORMAL` / `MAX_WEIGHT_EVENT` (config.py): topes por activo.

## Checklist antes de real (ver SYSTEM.md)
Precisión por símbolo ✓ (load_filters) · circuit breaker ✓ · reconcile ✓ · logging ✓ ·
PENDIENTE validar fills reales en demo · gestión de no-fills maker · monitoreo/alertas ntfy.
