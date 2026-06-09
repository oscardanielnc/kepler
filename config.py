"""
Kepler — configuración base (universo, rutas, supuestos).
Todo parametrizable. El sizing se expresa como % del 100% del capital.
"""
from __future__ import annotations
import os

# ─── Rutas ────────────────────────────────────────────────────────────────────
ROOT      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(ROOT, "data")          # parquet store
LOGS_DIR  = os.path.join(ROOT, "logs")          # reportes/logs diarios para descarga
DB_PATH   = os.path.join(ROOT, "kepler.db")     # SQLite — fuente de verdad y auditoría
for _d in (DATA_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

# ─── Universo inicial (20 perps USDT líquidos de Binance) ─────────────────────
# Mayormente listados largos (historia rica). Se escala más adelante.
# BTC y ETH son los DRIVERS primarios del grafo de dominancia.
# Universo LIMPIO: cripto-perps líquidos con >=2 años de historia (filtrado del top-60
# por volumen — excluidos tokenizados de acciones/commodities y listings nuevos).
# RETIRADAS 2026-06-02 (e53, Oscar): XLM/HBAR/LIT = finas con aporte de edge ~nulo/negativo y
# slippage alto (7.5-12.9 bps). Quitarlas sube el %/mes neto realista 2.24→2.96 (Sh 1.67→1.80) sin
# empeorar el OOS. ZEC se MANTIENE (su edge paga su slippage; es también el edge de liquidaciones e48).
UNIVERSE: list[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT",  "TRXUSDT", "BCHUSDT", "ETCUSDT", "ATOMUSDT",
    "NEARUSDT", "FILUSDT", "UNIUSDT", "AAVEUSDT", "ZECUSDT",
    "INJUSDT",  "FETUSDT", "SUIUSDT", "1000PEPEUSDT", "WLDUSDT",
    "ONDOUSDT", "TONUSDT", "ENAUSDT", "TAOUSDT",
]
DRIVERS: list[str] = ["BTCUSDT", "ETHUSDT"]   # masas dominantes (factor)

# Spot para carry cash-and-carry (solo donde tiene sentido al inicio).
SPOT_SYMBOLS: list[str] = ["BTCUSDT", "ETHUSDT"]

# ─── Rango de descarga ────────────────────────────────────────────────────────
# 1h para estudios (rápido, rico). 1m se baja aparte para backtest de ejecución.
HIST_START_MONTH = "2022-01"     # ~4+ años; por símbolo se baja lo disponible

# ─── Supuestos de costo (Binance — cuenta real de Oscar, pagando con BNB) ─────
# Futures con BNB:  maker 0.018% / taker 0.045%.  Sin BNB: 0.020% / 0.050%.
# Spot & Margin con BNB: 0.075% ambos (para cash-and-carry / pata spot).
MAKER_FEE = 0.00018    # Futures maker con BNB
TAKER_FEE = 0.00045    # Futures taker con BNB
SPOT_FEE  = 0.00075    # Spot/Margin con BNB (pata spot del carry)
SLIPPAGE  = 0.0002     # 2 bps en órdenes a mercado (conservador)

# ─── Riesgo / portafolio (dials — se calibran en backtest) ───────────────────
CAPITAL_USD        = 300.0     # REAL low-barrier — sub-cuenta Kepler, stress-test del PEOR CASO ($300).
                               # Con LOW_BARRIER_MODE el libro se adapta: a $300 ~9 patas baratas, todas ≥ min-notional
                               # (e78). Solo fallback/DRY: el equity en vivo sale de get_balance() real.
# TRACK RECORD — inicio de la VENTANA LIMPIA para las métricas realizadas (Sharpe/maxDD/β en vivo).
# Los días anteriores tuvieron bugs operativos (churn por reinicio, 06-02) y la equity era wallet,
# no MTM → contaminan el número. El reloj honesto arranca con la operación estable post-fixes.
# Regla ROADMAP §PRINCIPIO DE EVALUACIÓN CON BUGS: no se borra el pasado, se ETIQUETA y se excluye.
TRACK_INCEPTION    = "2026-06-09"   # REAL go-live low-barrier: sub-cuenta $300, DB reseteada a cero al desplegar.
                                    # DEMO (05-30→06-08) + intentos fallidos 06-08 quedan ARCHIVADOS, fuera del track.
                                    # Mover si el go-live real se retrasa.
MAX_WEIGHT_NORMAL  = 0.25      # tope normal por activo (por-sleeve, pre vol-parity)
# CAP de concentración del LIBRO COMBINADO (e69, Oscar 2026-06-02): el cap 0.25 es POR-SLEEVE; tras
# combinar (vp·Σ) + leverage, un nombre puede acumular de varios sleeves (incidente: TRX 23% del equity
# vía trend+carry+lowvol). Este tope recorta el target final para que NINGÚN nombre supere X% del equity.
# Conservador por construcción: el leverage se ancla sobre el libro SIN capar → recortar solo BAJA riesgo.
# e69: capar el peso combinado es neutral en Sharpe/maxDD/retorno (maxDD anclado). 0=desactiva.
MAX_POSITION_EQUITY = 0.15     # ningún activo > 15% del equity (recorte de concentración de 1 nombre)
MAX_WEIGHT_EVENT   = 1.00      # conviction override (evento/catalizador extremo)
TARGET_VOL_ANNUAL  = 0.10      # vol objetivo del portafolio (dial de riesgo)
MAX_GROSS          = 2.0       # exposición bruta máx (suma |pesos|)
NET_NEUTRAL_TOL    = 0.10      # |beta neta| tolerada (market-neutral por defecto)
# Ancla de riesgo del PRODUCTO (regla de Oscar 2026-05-30): el tier ESTABLE fija el maxDD
# del backtest en −TARGET_MAXDD y el leverage de estrategia se CALCULA para clavarlo ahí.
# Cada mejora del Sharpe → más retorno al mismo maxDD (no menos riesgo). El circuit breaker
# (−20%) sigue como red. Tope de leverage de estrategia para no inflar el gross sin control.
TARGET_MAXDD       = 0.10      # maxDD objetivo del tier ESTABLE (10%)
MAX_STRAT_LEVERAGE = 4.0       # tope duro del multiplicador de estrategia (seguridad)
# HAIRCUT de leverage (D0, e51): el ancla fija el leverage con el maxDD PASADO y sobre-apalanca
# cuando el futuro es más volátil → en walk-forward el maxDD OOS llegó a −13.5% vs −10% objetivo
# (el −10% PUEDE excederse en vivo). Este factor (≤1) recorta el leverage para que el maxDD vivo
# respete mejor el presupuesto. 1.0 = sin recorte (statu quo). Decisión de Oscar (e51 da el tradeoff).
LEVERAGE_HAIRCUT   = 0.95      # Oscar 2026-06-02 (e51, re-ajustado tras e52/e53): el libro limpio
                               # (sin finas + trend capado) ya respeta el −10% OOS sin recorte (maxDD OOS
                               # −7.1%); 0.95 deja un pequeño cojín. lev ~1.88x. 1.0=sin recorte. Era 0.85
                               # sobre el libro sucio (OOS −13.5%), ahora sobre-conservador.
# VOL-ANCHOR (e68, Oscar 2026-06-02): el maxDD-anchor es híper-sensible a la VENTANA de datos — si el
# histórico es corto/calmado (incidente: la VM sin 2022 corrió a 2.93x vs 2.16x → maxDD real −13%/−16%).
# El leverage robusto = min(maxdd_anchor, HAIRCUT·TARGET_VOL_ANCHOR/vol_realizada). La vol es estable
# entre ventanas (≈9% a 1x) → ancla el leverage aunque falte historia. Calibrado offline = vol_full ×
# ancla_raw_full (9.0% × 2.274). e68: mantiene maxDD real ≤9.5% en TODAS las ventanas, mismo retorno con
# historia completa (2.16x). 0=desactiva el vol-anchor (solo maxdd-anchor, statu quo viejo).
TARGET_VOL_ANCHOR  = 0.205     # vol anual operativa que clava el maxDD presupuestado en la referencia full

# ─── MODO LOW-BARRIER (copy-lead de baja barrera, e76/e77 2026-06-09) ─────────────────────────
# El min-notional Binance ($5 mayoría · $20 ETH-tier · $50 BTC) × Nº-posiciones = BARRERA DE ENTRADA del
# copiador. El libro full-20 necesita ~$7k para colocarse → mata el mercado copy-lead. SOLUCIÓN (idea Oscar,
# validada e77): NO operar los caros (BTC/ETH/BCH/ETC/LINK/LTC), sino el universo BARATO ($5) y re-neutralizar
# la β ENTRE esos coins (no shortear BTC). Resultado: Sharpe 1.46-1.47 (≈full 1.48), β≈−0.01, barrera ~$300-485,
# robusto a slip×3 y OOS. El CAPITAL decide cuántas patas (dropping adaptativo en execution): $300→~9, $1000+→~13.
LOW_BARRIER_MODE   = True      # True → engine usa kepler.lowbarrier; False → libro full-20 legacy.
# Universo barato operado: los 14 de $5-min MENOS ZEC (fina, arrastra por slippage en este universo; e77:
# quitarla sube el %/mes 1.56→1.92 manteniendo Sharpe 1.47 y β neutral). 13 coins líquidos de $5 min-notional.
LOW_BARRIER_UNIVERSE = ["AAVEUSDT", "ADAUSDT", "ATOMUSDT", "AVAXUSDT", "BNBUSDT", "DOGEUSDT", "DOTUSDT",
                        "FILUSDT", "NEARUSDT", "SOLUSDT", "TRXUSDT", "UNIUSDT", "XRPUSDT"]
# Min-notional por símbolo (fallback si exchangeInfo no responde). execution prefiere el LIVE de Binance.
MIN_NOTIONAL_FALLBACK = 5.0
# HORA del rebalanceo diario (ejecución, e54): la liquidez cripto sigue el reloj US/EU → pico 14-16 UTC
# (solape US-mañana/EU-tarde, 1.5× la media), zonas muertas 21-23 y 03-05 UTC. Fijar el rebalanceo a la
# hora más líquida baja ~21% el slippage (~0.1-0.15%/mes) sin añadir turnover ni β. Antes iba a la deriva
# (la hora del último deploy). None = comportamiento viejo (cada 24h desde el arranque, sin pinear).
REBALANCE_HOUR_UTC = 14        # 09h Lima · hora más líquida (e54). Ajustable.

# ─── Timezone (Lima, UTC-5) ──────────────────────────────────────────────────
# El sistema bucketea y MUESTRA los días/horas en hora de Lima (no UTC). Así "hoy" en el
# dashboard y en el log diario coincide con el día local de Oscar (evita el desfase que hacía
# que a las 19:00 Lima ya marcara el día siguiente UTC). El almacenamiento de ts sigue en epoch
# (TZ-agnóstico); la TZ solo se aplica al convertir epoch↔día/hora para bucketear o mostrar.
from datetime import datetime as _dt, timezone as _tz, timedelta as _td  # noqa: E402

TZ_OFFSET_H = -5                       # Lima
TZ = _tz(_td(hours=TZ_OFFSET_H))       # zona horaria local (Lima)


def now_local() -> "_dt":
    """Ahora en hora de Lima."""
    return _dt.now(TZ)


def today_local() -> str:
    """Día local (Lima) actual, 'YYYY-MM-DD'. Es el 'hoy' del dashboard y del log diario."""
    return now_local().strftime("%Y-%m-%d")


def fmt_local(ts_ms: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Formatea un epoch (ms) en hora de Lima."""
    return _dt.fromtimestamp(ts_ms / 1000, TZ).strftime(fmt)


def day_bounds_ms(day_str: str) -> tuple[int, int]:
    """[inicio, fin) en epoch ms del día LOCAL (Lima) 'YYYY-MM-DD'. Para filtrar el log del día."""
    d0 = _dt.strptime(day_str, "%Y-%m-%d").replace(tzinfo=TZ)
    s = int(d0.timestamp() * 1000)
    return s, s + 86_400_000
