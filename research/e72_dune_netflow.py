"""
E72 — NETFLOW de exchanges vía Dune (key gratis en data/.dune_key). (2026-06-02)
Familia netflow on-chain (la veta más prometedora, antes solo de pago/CryptoQuant). Flipside murió →
Dune. Pipeline VALIDADO: crear query pública -> ejecutar (perf='free') -> leer (research/dune_util.py).

HALLAZGOS:
- CEX labels (`cex.addresses`) cubren MUCHAS cadenas: ethereum 4373, polygon, bnb, base, avalanche_c,
  litecoin 1110, bitcoin 761, ripple 377, solana 166, tron 151... → cubre BTC, ETH, BNB, SOL, XRP, AVAX,
  LTC, TRX + ERC-20 (LINK/UNI/AAVE) nativamente.
- Extracción de netflow VALIDADA (LINK ethereum, números sanos: inflow/outflow diario en millones, netflow ±).

CAVEAT DE ALCANCE: el netflow per-coin es CROSS-CHAIN → cada cadena tiene su tabla de transferencias
(erc20_ethereum.evt_Transfer, bitcoin.outputs, tron.*, solana.*, ripple.*, ...) → ~8 queries por-cadena,
cada una scan multi-año = build de varias sesiones + créditos del free tier (lento). Decisión de Oscar:
invertir las sesiones en el build Dune gratis vs CryptoQuant pago (netflow per-token limpio, instantáneo).

python -m research.e72_dune_netflow   (pulla el subset ERC-20 validado)
"""
from __future__ import annotations
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from research.dune_util import run_sql

CACHE = os.path.join(config.DATA_DIR, "dune")

# universo → (cadena, contrato/None si nativo). Lo que cex.addresses cubre.
ERC20_ETH = {  # ERC-20 en ethereum (vía erc20_ethereum.evt_Transfer + cex.addresses ethereum)
    "LINKUSDT": "0x514910771af9ca656af840dff83e8264ecf986ca",
    "UNIUSDT":  "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "AAVEUSDT": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
}
# NATIVOS/otras cadenas (pendiente, una query por cadena): BTC(bitcoin), ETH(ethereum native),
# BNB(bnb), SOL(solana), XRP(ripple), AVAX(avalanche_c), LTC(litecoin), TRX(tron).


def netflow_erc20(symbol_to_contract, days=1400):
    """Netflow diario (token units) hacia/desde CEX para ERC-20 en ethereum. Una query, varios contratos."""
    vals = ",".join(f"({c})" for c in symbol_to_contract.values())
    sql = f"""
    with t as (
      select date(evt_block_time) d, contract_address ca, "from" f, "to" tt, value/1e18 v
      from erc20_ethereum.evt_Transfer
      where contract_address in ({",".join(symbol_to_contract.values())})
        and evt_block_time > now() - interval '{days}' day
    )
    select to_hex(t.ca) contract, t.d,
      sum(case when ci.address is not null then v else 0 end)
      - sum(case when co.address is not null then v else 0 end) as netflow
    from t
    left join cex.addresses ci on ci.blockchain='ethereum' and ci.address=t.tt
    left join cex.addresses co on co.blockchain='ethereum' and co.address=t.f
    group by 1,2 order by 2,1
    """
    rows = run_sql(sql, name="kepler_netflow_erc20", wait=280)
    if not isinstance(rows, list):
        print("ERROR:", rows); return None
    df = pd.DataFrame(rows)
    # mapear contract->symbol
    inv = {c.lower().replace("0x",""): s for s, c in symbol_to_contract.items()}
    df["symbol"] = df["contract"].str.lower().map(inv)
    return df


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E72 — netflow Dune (subset ERC-20 validado)\n")
    df = netflow_erc20(ERC20_ETH)
    if df is None: return
    os.makedirs(CACHE, exist_ok=True)
    df.to_parquet(os.path.join(CACHE, "netflow_erc20_eth.parquet"))
    print(df.groupby("symbol")["netflow"].describe()[["count","mean","std"]].to_string())
    print("\nGuardado en data/dune/. Cross-section ERC-20 = 3 coins (muy fino para rankear). Para un test")
    print("real del factor netflow hace falta añadir BTC/ETH/BNB/SOL/XRP/AVAX/LTC/TRX (1 query por cadena).")


if __name__ == "__main__":
    main()
