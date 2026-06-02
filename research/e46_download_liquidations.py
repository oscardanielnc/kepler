"""
E46 — DESCARGA de liquidaciones DIARIAS (Coinalyze, GRATIS con API key). 2026-06-01.
INTRADAY.md §2.2 / ruta B. Las liquidaciones INTRADÍA no tienen histórico gratis usable (Coinalyze
guarda solo 1500-2000 puntos rodantes a granularidad <12h, ~2-3 meses a 1h). Pero la granularidad
DIARIA NO se borra (histórico completo) → probamos liquidaciones como SLEEVE DIARIO cross-seccional
(rankear monedas por intensidad de liquidación → contrarian al rebote). Win gratis no testeado.

Endpoint: GET /v1/liquidation-history?symbols=&interval=daily&from=&to=&convert_to_usd=true
  - symbols: comma-sep, MÁX 20 por llamada (cada símbolo consume 1 call); formato `{COIN}USDT_PERP.A`
    (agregado entre exchanges). Rate limit 40 calls/min.
  - respuesta: [{symbol, history:[{t:unix_s, l:longs_liq, s:shorts_liq}]}]
API key: env COINALYZE_API_KEY o fichero data/.coinalyze_key (gitignored). Registro gratis en coinalyze.net.

  python -m research.e46_download_liquidations --probe   # valida key + cobertura + 1 muestra
  python -m research.e46_download_liquidations            # descarga completa 2023+ → data/liquidations_daily/
"""
from __future__ import annotations
import os, sys, time, json
from datetime import datetime, timezone
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

BASE = "https://api.coinalyze.net/v1"
CACHE = os.path.join(config.DATA_DIR, "liquidations_daily"); os.makedirs(CACHE, exist_ok=True)
START = "2023-01-01"
SUFFIX = "_PERP.A"               # agregado entre exchanges
_sess = requests.Session()


def _key():
    k = os.environ.get("COINALYZE_API_KEY")
    if not k:
        f = os.path.join(config.DATA_DIR, ".coinalyze_key")
        if os.path.exists(f):
            k = open(f).read().strip()
    if not k:
        sys.exit("FALTA API KEY. Registro gratis en coinalyze.net → API → genera key → "
                 "guárdala en data/.coinalyze_key o export COINALYZE_API_KEY=...")
    return k


def _get(path, params):
    params = {**params, "api_key": _key()}
    r = _sess.get(f"{BASE}{path}", params=params, timeout=60)
    if r.status_code == 429:
        time.sleep(20); r = _sess.get(f"{BASE}{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def target_symbols():
    """coin del universo (p.ej. BTCUSDT) → símbolo Coinalyze agregado (BTCUSDT_PERP.A)."""
    return {c: f"{c}{SUFFIX}" for c in config.UNIVERSE}


def fetch_liq(symbols, t0, t1):
    """Descarga liquidaciones diarias para una lista de símbolos Coinalyze (máx 20)."""
    data = _get("/liquidation-history", {
        "symbols": ",".join(symbols), "interval": "daily",
        "from": int(t0), "to": int(t1), "convert_to_usd": "true"})
    out = {}
    for row in data:
        h = row.get("history", [])
        if not h:
            continue
        df = pd.DataFrame(h)
        df["date"] = pd.to_datetime(df["t"], unit="s", utc=True)
        out[row["symbol"]] = df[["date", "l", "s"]].rename(columns={"l": "long_liq", "s": "short_liq"})
    return out


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    probe = "--probe" in sys.argv
    t0 = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp())
    t1 = int(datetime.now(timezone.utc).timestamp())
    smap = target_symbols(); inv = {v: k for k, v in smap.items()}
    syms = list(smap.values())
    print(f"E46 — liquidaciones DIARIAS Coinalyze · {len(syms)} símbolos · {START}→hoy")

    if probe:
        # 1) ¿la key sirve? cobertura de mercados; 2) una muestra real (BTC)
        try:
            mk = _get("/future-markets", {})
            avail = {m.get("symbol") for m in mk}
            hit = [s for s in syms if s in avail]
            print(f"  future-markets OK ({len(mk)} mercados). Coinciden exactos {len(hit)}/{len(syms)} "
                  f"con sufijo {SUFFIX}.")
            miss = [inv[s] for s in syms if s not in avail][:8]
            if miss: print(f"  sin match exacto (revisar formato): {miss} ...")
        except Exception as e:
            print(f"  future-markets ERROR: {str(e)[:80]}")
        sample = fetch_liq(syms[:1], t0, t1)
        for s, df in sample.items():
            print(f"  MUESTRA {s}: {len(df)} días, {df['date'].min().date()}→{df['date'].max().date()}, "
                  f"long_liq medio ${df['long_liq'].mean():,.0f}/día, short ${df['short_liq'].mean():,.0f}/día")
        if not sample:
            print("  ⚠️ muestra vacía: revisar formato de símbolo o rango.")
        print("\n  Si la muestra trae años de datos → corre sin --probe para la descarga completa.")
        return

    # descarga completa en lotes de 20 (respetando 40/min)
    saved = 0
    for i in range(0, len(syms), 20):
        batch = syms[i:i + 20]
        try:
            res = fetch_liq(batch, t0, t1)
        except Exception as e:
            print(f"  lote {i//20} ERROR: {str(e)[:80]}"); res = {}
        for s, df in res.items():
            coin = inv.get(s, s.replace(SUFFIX, ""))
            df.to_parquet(os.path.join(CACHE, f"{coin}.parquet"))
            saved += 1
            print(f"  [{saved:2d}] {coin:12s} {len(df):>4d} días "
                  f"{df['date'].min().date()}→{df['date'].max().date()}")
        if i + 20 < len(syms):
            time.sleep(62)        # respetar 40 calls/min
    tot = sum(os.path.getsize(os.path.join(CACHE, f)) for f in os.listdir(CACHE)) / 1e6
    print(f"\nLISTO. {saved}/{len(syms)} símbolos con datos · {tot:.1f}MB en {CACHE}")
    print("Siguiente: research/e47 (chequeo barato ortogonalidad + criterio del ancla).")


if __name__ == "__main__":
    main()
