"""
E62 — DESCARGA Coinalyze Tier 2: predicted funding + open interest + funding (diario, cross-exchange).
(2026-06-02). Inventario (probe API): predicted-funding/funding/open-interest history = diario completo
(2020→hoy, OHLC), NO se borra. Oportunidades NUEVAS (no mapeadas): (1) predicted funding (carry FORWARD,
≠ funding realizado de Binance que usa el carry actual); (2) OI-delta/oi_pxdiv (flujo de posicionamiento,
≠ el ratio L/S que ya descartamos en e16f). NO hay endpoint de basis → ese ángulo no es testeable (sería
funding ≈ carry, redundante). Cachea `c` (cierre diario) de cada métrica por coin → data/coinalyze_daily/.
python -m research.e62_coinalyze_download
"""
from __future__ import annotations
import os, sys, time
from datetime import datetime, timezone
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research"))
from e46_download_liquidations import _get, SUFFIX  # reusa cliente (key + rate-limit)

CACHE = os.path.join(config.DATA_DIR, "coinalyze_daily"); os.makedirs(CACHE, exist_ok=True)
ENDPOINTS = {"pred_funding": "/predicted-funding-rate-history",
             "funding": "/funding-rate-history",
             "oi": "/open-interest-history"}


def fetch(path, symbols, t0, t1, field="c"):
    d = _get(path, {"symbols": ",".join(symbols), "interval": "daily", "from": int(t0), "to": int(t1)})
    out = {}
    for row in d:
        h = row.get("history", [])
        if not h:
            continue
        df = pd.DataFrame(h)
        df["date"] = pd.to_datetime(df["t"], unit="s", utc=True)
        out[row["symbol"]] = df.set_index("date")[field]
    return out


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    t0 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    t1 = int(datetime.now(timezone.utc).timestamp())
    smap = {c: f"{c}{SUFFIX}" for c in config.UNIVERSE}; inv = {v: k for k, v in smap.items()}
    syms = list(smap.values())
    print(f"E62 — Coinalyze: {list(ENDPOINTS)} · {len(syms)} símbolos · diario 2020→hoy\n")

    # acumula por métrica (lotes de 20, una llamada por endpoint×lote)
    data = {m: {} for m in ENDPOINTS}
    calls = 0
    for m, path in ENDPOINTS.items():
        for i in range(0, len(syms), 20):
            batch = syms[i:i + 20]
            try:
                res = fetch(path, batch, t0, t1); calls += 1
                for s, ser in res.items():
                    data[m][inv.get(s, s)] = ser
            except Exception as e:
                print(f"  {m} lote {i//20} ERROR: {str(e)[:70]}")
            if calls % 38 == 0:
                time.sleep(62)
            else:
                time.sleep(1.6)
        print(f"  {m:13s}: {len(data[m])} coins")

    # merge por coin → parquet con columnas pred_funding/funding/oi
    coins = set().union(*[set(d) for d in data.values()])
    saved = 0
    for coin in sorted(coins):
        cols = {m: data[m][coin] for m in ENDPOINTS if coin in data[m]}
        if not cols:
            continue
        df = pd.DataFrame(cols).sort_index()
        df.to_parquet(os.path.join(CACHE, f"{coin}.parquet")); saved += 1
    n_pf = sum(1 for c in coins if c in data["pred_funding"])
    print(f"\nLISTO. {saved} coins en {CACHE} · con predicted-funding: {n_pf}")
    print("Siguiente: research/e63 (factores predicted-funding + OI por el harness brutal).")


if __name__ == "__main__":
    main()
