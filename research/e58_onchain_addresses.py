"""
E58 — TIER 1 ON-CHAIN: ingesta de actividad de direcciones (Coin Metrics Community, GRATIS sin key).
(2026-06-02). El "factor zoo" cripto lista las métricas blockchain-native (new-address-to-price) entre
los 2-3 factores más influyentes y ORTOGONALES. AdrNewCnt no es community-free, pero **AdrActCnt**
(direcciones activas) y **TxCnt** sí → proxy estándar de actividad on-chain. Análogo al TVL (e26/e27):
construir `addr_pxdiv` = Δlog(actividad) − retorno (actividad neta de precio = acumulación fundamental).

INVENTARIO (2026-06-02): AdrActCnt+TxCnt community-free para 15/29 coins del universo; **2 STALE
descartadas** (bnb se cortó 2019-04 = viejo ERC-20; dot 2022-06) → **13 usables**. Ventaja point-in-time:
las direcciones se computan de la cadena inmutable → NO se revisan (≠ backfill de TVL). Cross-section 13.

Este script SOLO descarga/cachea (ingesta). El backtest del factor + harness va aparte (siguiente).
No toca producción. python -m research.e58_onchain_addresses
"""
from __future__ import annotations
import os, sys, time
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

BASE = "https://community-api.coinmetrics.io/v4"
OUT = os.path.join(config.DATA_DIR, "onchain_cm")
METRICS = "AdrActCnt,TxCnt"
# 13 usables (sin bnb/dot por stale). Mapea ticker Binance → asset id de Coin Metrics.
COINS = ["aave", "ada", "bch", "btc", "doge", "etc", "eth", "link", "ltc", "trx", "uni", "xrp", "zec"]
STALE = {"bnb": "2019-04 (viejo ERC-20)", "dot": "2022-06 (cortado)"}   # NO usar


def fetch_asset(asset: str, start="2016-01-01") -> pd.DataFrame:
    """Serie diaria de AdrActCnt+TxCnt para `asset` (paginada). Read-only, JSON público sin key."""
    rows = []; url = f"{BASE}/timeseries/asset-metrics"
    params = {"assets": asset, "metrics": METRICS, "frequency": "1d", "start_time": start, "page_size": 10000}
    for _ in range(30):
        r = requests.get(url, params=params, timeout=60); r.raise_for_status()
        j = r.json(); rows += j.get("data", [])
        nxt = j.get("next_page_url")
        if not nxt:
            break
        url = nxt; params = None
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    for c in ("AdrActCnt", "TxCnt"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["time", "AdrActCnt", "TxCnt"]].sort_values("time").reset_index(drop=True)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    os.makedirs(OUT, exist_ok=True)
    print(f"E58 — ingesta on-chain (Coin Metrics Community) → {OUT}")
    print(f"Descartadas por STALE: {STALE}\n")
    print(f"  {'coin':6s} {'filas':>6s} {'desde':>11s} {'hasta':>11s}")
    tot = 0
    for c in COINS:
        df = fetch_asset(c)
        if df.empty:
            print(f"  {c:6s}  VACÍO"); continue
        df.to_parquet(os.path.join(OUT, f"{c}.parquet"))
        tot += len(df)
        print(f"  {c:6s} {len(df):>6d} {str(df['time'].iloc[0].date()):>11s} {str(df['time'].iloc[-1].date()):>11s}")
        time.sleep(0.1)
    print(f"\nTOTAL {tot} filas. Listo para el backtest del factor (addr_pxdiv) + harness.")


if __name__ == "__main__":
    main()
