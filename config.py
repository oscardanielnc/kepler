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
UNIVERSE: list[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT",  "TRXUSDT", "BCHUSDT", "ETCUSDT", "ATOMUSDT",
    "NEARUSDT", "FILUSDT", "UNIUSDT", "AAVEUSDT", "XLMUSDT",
    "ZECUSDT",  "HBARUSDT", "LITUSDT", "INJUSDT", "FETUSDT",
    "SUIUSDT",  "1000PEPEUSDT", "WLDUSDT", "ONDOUSDT", "TONUSDT",
    "ENAUSDT",  "TAOUSDT",
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
CAPITAL_USD        = 5000.0    # ejemplo demo; todo el sizing es % del 100%
MAX_WEIGHT_NORMAL  = 0.25      # tope normal por activo
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
