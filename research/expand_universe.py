"""
Expande el universo: top-N perps USDT de Binance por volumen real (24h) y descarga
1h + funding de cada uno. Guarda la lista en data/universe.txt.
python research/expand_universe.py [N]
"""
from __future__ import annotations
import os, sys
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.fetch import download_klines, download_funding

# excluir stablecoins y tokens raros (no son pares de trading cripto reales)
EXCLUDE = {"USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT", "DAIUSDT", "USDPUSDT", "EURUSDT"}


def top_perps(n: int) -> list[str]:
    r = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=30)
    r.raise_for_status()
    data = [d for d in r.json()
            if d["symbol"].endswith("USDT") and d["symbol"] not in EXCLUDE
            and "_" not in d["symbol"]]
    data.sort(key=lambda d: float(d["quoteVolume"]), reverse=True)
    return [d["symbol"] for d in data[:n]]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    syms = top_perps(n)
    with open(os.path.join(config.DATA_DIR, "universe.txt"), "w") as f:
        f.write("\n".join(syms))
    print(f"Top {len(syms)} perps por volumen guardados en data/universe.txt")
    print("Descargando 1h + funding (reanudable)...")
    import time as _t; t0 = _t.time()
    for i, s in enumerate(syms, 1):
        nk = download_klines(s, "1h", config.HIST_START_MONTH)
        nf = download_funding(s)
        print(f"  [{i:2d}/{len(syms)}] {s:12s} klines={'ya' if nk==-1 else nk}  funding={'ya' if nf==-1 else nf}", flush=True)
    print(f"LISTO en {_t.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
