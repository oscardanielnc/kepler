"""
E34 — market cap para el factor SIZE (C1). 2026-06-01.
CoinGecko cerró su API pública (401 sin key). Vía GRATIS y SIN key que SÍ funciona: CoinPaprika
`/tickers` (un call, ~2000 coins) → market cap ACTUAL por moneda. El histórico de market cap se
APROXIMA con el ratio de precio de nuestras klines de Binance (4 años, ya en disco):

    mcap_hist[sym][t] = mcap_now[sym] · (close[sym][t] / close[sym][now])     (≡ supply_now · precio[t])

⚠️ APROXIMACIÓN: asume supply ~constante (ignora emisiones/unlocks). Válida para el RANK de SIZE
(dominado por diferencias de órdenes de magnitud: BTC/ETH enormes vs alts chicos; el drift de supply
no voltea el rank). Es un CHEQUEO DE VIABILIDAD barato y gratis; si el size promete, se justifica
market cap histórico limpio (CoinGecko demo key gratis / pago). Cachea data/marketcap/current_mcap.json.

USO:  python -m research.e34_fetch_marketcap [--force]
"""
from __future__ import annotations
import os, sys, json
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

CACHE = os.path.join(config.DATA_DIR, "marketcap"); os.makedirs(CACHE, exist_ok=True)
OUT = os.path.join(CACHE, "current_mcap.json")

# base-symbol (sin USDT / sin prefijo 1000) → pista para desambiguar colisiones de símbolo en CoinPaprika.
# El match general es por símbolo + menor rank; estos overrides fuerzan el id correcto (substring).
ID_HINT = {"LIT": "litentry", "PEPE": "pepe", "TON": "the-open-network", "UNI": "uniswap",
           "AAVE": "aave", "FET": "fetch", "NEAR": "near-protocol", "INJ": "injective"}

# EXCLUIR: símbolos cuyo market cap en CoinPaprika NO es fiable (verificado a mano). El sleeve de size
# simplemente no los rankea (los otros 6 sleeves los siguen operando). DOT: el único candidato símbolo
# "DOT" es 'dot-polkadot-token' rank 706 $0.02B (el Polkadot real no está en /tickers de esta fuente).
EXCLUDE = {"DOTUSDT"}


def base_symbol(sym: str) -> str:
    s = sym[:-4] if sym.endswith("USDT") else sym
    return s[4:] if s.startswith("1000") else s


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    force = "--force" in sys.argv
    if os.path.exists(OUT) and not force:
        print(f"Ya cacheado: {OUT} (usar --force para re-bajar)")
        d = json.load(open(OUT, encoding="utf-8"))
        print(f"  {len(d)} símbolos con market cap.")
        return
    print("E34 — market cap actual (CoinPaprika, sin key) para factor SIZE\n" + "="*60)
    r = requests.get("https://api.coinpaprika.com/v1/tickers", timeout=40, headers={"User-Agent": "kepler"})
    r.raise_for_status()
    tickers = r.json()
    by_sym: dict[str, list] = {}
    for t in tickers:
        by_sym.setdefault(t["symbol"], []).append(t)

    out = {}; fail = []
    for sym in config.UNIVERSE:
        if sym in EXCLUDE:
            print(f"  {sym:14s} — EXCLUIDO (market cap no fiable en la fuente)"); continue
        bs = base_symbol(sym)
        cands = by_sym.get(bs, [])
        if not cands:
            fail.append((sym, "símbolo no hallado")); continue
        hint = ID_HINT.get(bs)
        chosen = None
        if hint:
            hits = [c for c in cands if hint in c["id"]]
            if hits:
                chosen = min(hits, key=lambda c: c.get("rank") or 9999)
        if chosen is None:                       # match general: menor rank (más prominente)
            chosen = min(cands, key=lambda c: c.get("rank") or 9999)
        mc = chosen["quotes"]["USD"]["market_cap"]
        if not mc or mc <= 0:
            fail.append((sym, "mcap 0/nulo")); continue
        out[sym] = {"id": chosen["id"], "rank": chosen.get("rank"), "mcap": float(mc)}
        flag = "  ⚠️(colisión?)" if len(cands) > 1 and not hint else ""
        print(f"  {sym:14s} → {chosen['id']:30s} rank {str(chosen.get('rank')):>4s} · "
              f"${mc/1e9:7.2f}B{flag}")

    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"\n{len(out)}/{len(config.UNIVERSE)} con market cap → {OUT}")
    if fail:
        print("Fallos:", fail)


if __name__ == "__main__":
    main()
