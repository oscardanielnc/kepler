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

# ─── Timezone ─────────────────────────────────────────────────────────────────
TZ_OFFSET_H = -5   # Lima
