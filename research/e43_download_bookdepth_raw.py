"""
E43 — DESCARGA del bookDepth RAW (30s) para Fase 2 intradía (INTRADAY.md §4/§5). 2026-06-01.
e23/e24 bajaron los zips pero solo guardaron el imbalance DIARIO (media del día) → el edge intradía
se perdió. Aquí re-descargamos TODOS los zips (los ~11GB de transferencia) y guardamos el imbalance
a resolución NATIVA 30s por símbolo (compacto: timestamp + imb1/imb2/imb5 en float32 → nunca hay que
re-bajar). Es el insumo de la Fase 2: re-evaluar order-book a horizontes 1h–12h con el backtester
horario (e42) + el modelo de coste intradía (e44).

Incremental/reanudable (salta días ya cacheados). Pensado para correr en BACKGROUND (~horas).
python -m research.e43_download_bookdepth_raw
"""
from __future__ import annotations
import os, sys, io, zipfile, time
from datetime import date, timedelta, datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"
CACHE = os.path.join(config.DATA_DIR, "bookdepth_30s"); os.makedirs(CACHE, exist_ok=True)
START = "2023-01-01"
_sess = requests.Session()


def _imb_series_day(sym, d):
    """Descarga 1 día y devuelve DataFrame [imb1,imb2,imb5] a resolución 30s (índice=timestamp) o None."""
    url = f"{BASE}/{sym}/{sym}-bookDepth-{d.isoformat()}.zip"
    try:
        r = _sess.get(url, timeout=90)
        if r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        df = pd.read_csv(z.open(z.namelist()[0]))
        piv = df.pivot_table(index="timestamp", columns="percentage", values="notional", aggfunc="last")
        out = {}
        for k in (1, 2, 5):
            b, a = piv.get(-k), piv.get(k)
            if b is not None and a is not None:
                out[f"imb{k}"] = ((b - a) / (b + a)).astype("float32")
        if not out:
            return None
        res = pd.DataFrame(out)
        res.index = pd.to_datetime(res.index, utc=True, errors="coerce")
        return res[res.index.notna()]
    except Exception:
        return None


def download_symbol(sym, days, workers=16):
    out = os.path.join(CACHE, f"{sym}.parquet")
    have = pd.read_parquet(out) if os.path.exists(out) else pd.DataFrame()
    have_days = set(pd.Index(have.index).normalize().unique()) if len(have) else set()
    todo = [d for d in days if pd.Timestamp(d, tz="UTC") not in have_days]
    if not todo:
        return len(have), 0
    parts = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda dd: _imb_series_day(sym, dd), todo):
            if res is not None and len(res):
                parts.append(res)
    if parts:
        add = pd.concat(parts)
        have = pd.concat([have, add]) if len(have) else add
        have = have[~have.index.duplicated()].sort_index()
        have.to_parquet(out)
    return len(have), len(parts)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    d0 = date.fromisoformat(START); d1 = datetime.now(timezone.utc).date() - timedelta(days=2)
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]
    syms = config.UNIVERSE
    print(f"E43 — descarga bookDepth RAW 30s · {len(syms)} símbolos × {len(days)} días ({START}→{d1})")
    print(f"Cache: {CACHE}\n", flush=True)
    t0 = time.time()
    for i, s in enumerate(syms, 1):
        try:
            n_rows, n_new = download_symbol(s, days)
            sz = os.path.getsize(os.path.join(CACHE, f"{s}.parquet"))/1e6 if os.path.exists(os.path.join(CACHE, f"{s}.parquet")) else 0
            print(f"  [{i:2d}/{len(syms)}] {s:12s} {n_rows:>9,d} snaps 30s ({n_new} días nuevos) · "
                  f"{sz:.1f}MB · t+{time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            print(f"  [{i:2d}/{len(syms)}] {s:12s} ERROR {str(e)[:60]}", flush=True)
    print(f"\nLISTO en {time.time()-t0:.0f}s. Total cache: "
          f"{sum(os.path.getsize(os.path.join(CACHE,f)) for f in os.listdir(CACHE))/1e9:.2f} GB", flush=True)
    print("Siguiente (Fase 2): order-book a 1h–12h con e42 (backtester horario) + e44 (coste intradía).")


if __name__ == "__main__":
    main()
