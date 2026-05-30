"""Descarga paralela de metrics (daily, 5min) para el universo. Un parquet por símbolo."""
import os, sys, io, zipfile
from datetime import date, datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd, requests
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "C:/Users/LENOVO/kepler")
import config
from kepler.engine import load

BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
OUT = os.path.join(config.DATA_DIR, "metrics"); os.makedirs(OUT, exist_ok=True)
KEEP = ["sum_open_interest", "sum_open_interest_value",
        "count_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]
_sess = requests.Session()

def fetch_day(sym, d):
    try:
        r = _sess.get(f"{BASE}/{sym}/{sym}-metrics-{d.isoformat()}.zip", timeout=30)
        if r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        return pd.read_csv(z.open(z.namelist()[0]))
    except Exception:
        return None

def download_symbol(sym):
    out = os.path.join(OUT, f"{sym}.parquet")
    if os.path.exists(out):
        return sym, -1
    days = []
    d = date(2023, 1, 1); today = datetime.now(timezone.utc).date()
    while d < today:
        days.append(d); d += timedelta(days=1)
    parts = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for df in ex.map(lambda dd: fetch_day(sym, dd), days):
            if df is not None:
                parts.append(df)
    if not parts:
        return sym, 0
    m = pd.concat(parts, ignore_index=True)
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.drop_duplicates("create_time").sort_values("create_time").set_index("create_time")
    keep = [c for c in KEEP if c in m.columns]
    for c in keep:
        m[c] = pd.to_numeric(m[c], errors="coerce")
    m[keep].to_parquet(out)
    return sym, len(m)

if __name__ == "__main__":
    C = load()
    syms = list(C.columns)
    print(f"Descargando metrics de {len(syms)} simbolos (paralelo)...", flush=True)
    t0 = datetime.now()
    for i, s in enumerate(syms, 1):
        sym, n = download_symbol(s)
        tag = "(ya existia)" if n == -1 else (f"{n} filas" if n > 0 else "SIN DATOS")
        print(f"  [{i:2d}/{len(syms)}] {sym:12s} {tag}", flush=True)
    print(f"LISTO en {(datetime.now()-t0).seconds}s", flush=True)
