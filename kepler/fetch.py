"""
Kepler — descargador multi-activo desde data.binance.vision (gratis, oficial).
Reanudable (salta parquet existente). Guarda por símbolo/intervalo + funding.

Salida:
  data/<interval>/SYMBOL.parquet      (open_time, open, high, low, close, volume,
                                        quote_volume, count, taker_buy_volume)
  data/funding/SYMBOL.parquet         (funding_time, funding_rate)

Uso:
  python -m kepler.fetch 1h                # universo entero en 1h
  python -m kepler.fetch 1m BTCUSDT ETHUSDT
"""
from __future__ import annotations
import io
import os
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

BASE   = "https://data.binance.vision/data/futures/um"
SPOT   = "https://data.binance.vision/data/spot"
FAPI   = "https://fapi.binance.com"
_COLS  = ["open_time","open","high","low","close","volume","close_time",
          "quote_volume","count","taker_buy_volume","taker_buy_quote_volume","ignore"]
_KEEP  = ["open_time","open","high","low","close","volume","quote_volume","count","taker_buy_volume"]


def _months(start: str):
    y, m = map(int, start.split("-"))
    now = datetime.now(timezone.utc)
    while (y, m) <= (now.year, now.month):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m = 1; y += 1


def _zip(url: str, retries: int = 3) -> bytes | None:
    for a in range(retries):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception:
            if a == retries - 1:
                return None
            time.sleep(2)


def _parse(content: bytes) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(content)); name = z.namelist()[0]
    with z.open(name) as f:
        first = f.read(9)
    hdr = 0 if first == b"open_time" else None
    df = pd.read_csv(z.open(name), header=hdr, names=None if hdr == 0 else _COLS)
    if hdr is None:
        df.columns = _COLS
    df = df[_KEEP].copy()
    for c in _KEEP:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["open_time"] = df["open_time"].astype("int64")
    return df


def download_klines(symbol: str, interval: str, start: str, market: str = "futures",
                    force: bool = False) -> int:
    sub = "futures_um" if market == "futures" else "spot"
    out_dir = os.path.join(config.DATA_DIR, sub, interval)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{symbol}.parquet")
    if os.path.exists(out) and not force:
        return -1   # ya existe
    base = BASE if market == "futures" else SPOT
    parts = []
    for ym in _months(start):
        c = _zip(f"{base}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{ym}.zip")
        if c:
            parts.append(_parse(c))
    # días sueltos del mes en curso
    d = datetime.now(timezone.utc).date().replace(day=1)
    today = datetime.now(timezone.utc).date()
    while d < today:
        c = _zip(f"{base}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{d.isoformat()}.zip")
        if c:
            parts.append(_parse(c))
        d += timedelta(days=1)
    if not parts:
        return 0
    df = pd.concat(parts, ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
    df.reset_index(drop=True).to_parquet(out, index=False)
    return len(df)


def download_funding(symbol: str, force: bool = False) -> int:
    out_dir = os.path.join(config.DATA_DIR, "funding"); os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{symbol}.parquet")
    if os.path.exists(out) and not force:
        return -1
    # Paginación robusta: fundingRate devuelve >= startTime en orden ascendente.
    # Avanzar por el último fundingTime hasta que no haya progreso (NO romper en len<1000).
    rows = []; start_ms = 1_500_000_000_000   # ~2017-07, antes de cualquier perp
    while True:
        try:
            r = requests.get(f"{FAPI}/fapi/v1/fundingRate",
                             params={"symbol": symbol, "startTime": start_ms, "limit": 1000}, timeout=30)
            r.raise_for_status(); batch = r.json()
        except Exception:
            break
        if not batch:
            break
        rows.extend(batch)
        nxt = batch[-1]["fundingTime"] + 1
        if nxt <= start_ms:
            break
        start_ms = nxt; time.sleep(0.15)
    if not rows:
        return 0
    df = pd.DataFrame(rows).rename(columns={"fundingTime": "funding_time", "fundingRate": "funding_rate"})
    df["funding_time"] = df["funding_time"].astype("int64")
    df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
    df[["funding_time","funding_rate"]].drop_duplicates("funding_time").to_parquet(out, index=False)
    return len(df)


# ─── Actualización INCREMENTAL (para el orquestador en vivo) ──────────────────

def _live_klines(symbol, interval, limit=1000):
    try:
        r = requests.get(f"{FAPI}/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=15)
        r.raise_for_status()
        df = pd.DataFrame(r.json(), columns=_COLS)
        df = df[_KEEP].copy()
        for c in _KEEP:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["open_time"] = df["open_time"].astype("int64")
        return df
    except Exception:
        return None


def update_klines(symbol, interval):
    """Fetch reciente (live REST) y mergea al parquet existente (dedupe). Para el loop en vivo."""
    new = _live_klines(symbol, interval)
    if new is None or new.empty:
        return 0
    path = os.path.join(config.DATA_DIR, "futures_um", interval, f"{symbol}.parquet")
    if os.path.exists(path):
        old = pd.read_parquet(path)
        df = pd.concat([old, new], ignore_index=True)
    else:
        df = new
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    df.to_parquet(path, index=False)
    return len(new)


def update_funding(symbol):
    try:
        r = requests.get(f"{FAPI}/fapi/v1/fundingRate",
                         params={"symbol": symbol, "limit": 100}, timeout=15)
        r.raise_for_status(); batch = r.json()
    except Exception:
        return 0
    if not batch:
        return 0
    new = pd.DataFrame(batch).rename(columns={"fundingTime": "funding_time", "fundingRate": "funding_rate"})
    new["funding_time"] = new["funding_time"].astype("int64")
    new["funding_rate"] = pd.to_numeric(new["funding_rate"], errors="coerce")
    new = new[["funding_time", "funding_rate"]]
    path = os.path.join(config.DATA_DIR, "funding", f"{symbol}.parquet")
    if os.path.exists(path):
        new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
    new.drop_duplicates("funding_time").sort_values("funding_time").to_parquet(path, index=False)
    return len(batch)


def update_universe(interval="1h"):
    """Actualiza klines + funding de todo el universo (incremental). Llamado antes de cada rebalanceo."""
    ok = 0
    for s in config.UNIVERSE:
        if update_klines(s, interval) > 0:
            ok += 1
        update_funding(s)
        time.sleep(0.05)
    return ok


def _span(symbol, interval):
    p = os.path.join(config.DATA_DIR, "futures_um", interval, f"{symbol}.parquet")
    if not os.path.exists(p):
        return "—"
    df = pd.read_parquet(p, columns=["open_time"])
    a = datetime.fromtimestamp(df.open_time.iloc[0]/1000, tz=timezone.utc).strftime("%Y-%m")
    b = datetime.fromtimestamp(df.open_time.iloc[-1]/1000, tz=timezone.utc).strftime("%Y-%m")
    return f"{len(df):>7,} velas [{a}→{b}]"


def main():
    interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
    syms = sys.argv[2:] if len(sys.argv) > 2 else config.UNIVERSE
    print(f"Descargando {interval} de {len(syms)} símbolos desde {config.HIST_START_MONTH}...")
    t0 = time.time()
    for i, s in enumerate(syms, 1):
        n = download_klines(s, interval, config.HIST_START_MONTH)
        f = download_funding(s)
        tag = "(ya existía)" if n == -1 else f"{_span(s, interval)}  funding={f if f>=0 else 'ok'}"
        print(f"  [{i:2d}/{len(syms)}] {s:10s} {tag}")
    # spot para carry
    for s in config.SPOT_SYMBOLS:
        n = download_klines(s, interval, config.HIST_START_MONTH, market="spot")
        print(f"  [spot] {s:10s} {'(ya existía)' if n == -1 else f'{n:,} velas'}")
    print(f"LISTO en {time.time()-t0:.0f}s → {config.DATA_DIR}")


if __name__ == "__main__":
    main()
