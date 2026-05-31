"""
E22 — A4 (paso 0): ¿el BASIS (perp−spot) es ORTOGONAL al funding/carry, o redundante?
Antes de bajar 23 historias de spot para un sleeve cross-seccional de basis, chequear lo barato:
el basis y el funding están mecánicamente ligados (el funding arbitra el basis). Si el basis ≈ funding,
un sleeve de basis sólo duplicaría el carry (sleeve #4) → NO vale la pena (lección e16: señales
correladas no diversifican). Sólo tenemos spot de BTC/ETH → con eso medimos la correlación.

  basis_t = perp_close/spot_close − 1            (premium relativo del perp)
Tests:
  1. corr(basis, funding) por símbolo (nivel).
  2. corr(basis, funding FORWARD) — ¿el basis predice el funding que se cobra?
  3. cross-seccional (lo que usaría el sleeve): corr(basis_BTC−basis_ETH, funding_BTC−funding_ETH).

Veredicto: corr alta (>~0.6) → basis≈carry, NO seguir con A4. Baja → vale bajar spot del universo.
python -m research.e22_basis_check
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

SYMS = config.SPOT_SYMBOLS   # BTC, ETH


def load_sym(sym):
    perp = pd.read_parquet(os.path.join(config.DATA_DIR, "futures_um", "1h", f"{sym}.parquet"),
                           columns=["open_time", "close"]).set_index("open_time")["close"]
    spot = pd.read_parquet(os.path.join(config.DATA_DIR, "spot", "1h", f"{sym}.parquet"),
                           columns=["open_time", "close"]).set_index("open_time")["close"]
    fund = pd.read_parquet(os.path.join(config.DATA_DIR, "funding", f"{sym}.parquet")
                           ).set_index("funding_time")["funding_rate"]
    j = pd.concat({"perp": perp, "spot": spot}, axis=1).dropna()
    j["basis"] = j["perp"]/j["spot"] - 1.0
    j["funding"] = fund.reindex(j.index)
    return j[j["funding"].notna()].copy()       # grilla 8h alineada


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E22 — A4 paso 0: ¿basis ⟂ funding o redundante?\n" + "="*56)
    D = {s: load_sym(s) for s in SYMS}
    for s, df in D.items():
        print(f"{s}: {len(df)} marcas 8h · basis medio {df['basis'].mean()*1e4:+.1f}bps "
              f"(std {df['basis'].std()*1e4:.1f}) · funding medio {df['funding'].mean()*1e4:+.2f}bps")
    print()

    print("TEST 1+2 — correlación basis vs funding (por símbolo):")
    print(f"  {'sym':<8s} {'corr(basis,fund)':>16s} {'corr(basis,fund_fwd)':>20s}")
    for s, df in D.items():
        c_now = df["basis"].corr(df["funding"])
        c_fwd = df["basis"].corr(df["funding"].shift(-1))
        print(f"  {s:<8s} {c_now:16.2f} {c_fwd:20.2f}")

    # TEST 3 — cross-seccional (lo que de verdad usaría el sleeve): BTC vs ETH
    j = pd.concat({"b_btc": D["BTCUSDT"]["basis"], "b_eth": D["ETHUSDT"]["basis"],
                   "f_btc": D["BTCUSDT"]["funding"], "f_eth": D["ETHUSDT"]["funding"]}, axis=1).dropna()
    dbasis = j["b_btc"] - j["b_eth"]; dfund = j["f_btc"] - j["f_eth"]
    c_xs = dbasis.corr(dfund)
    print(f"\nTEST 3 — CROSS-SECCIONAL (BTC−ETH): corr(Δbasis, Δfunding) = {c_xs:.2f}")
    print(f"  (es la señal que rankearía el sleeve; alta = mismo orden que carry)")

    print("\nVEREDICTO:")
    cmax = max(abs(D['BTCUSDT']['basis'].corr(D['BTCUSDT']['funding'])),
               abs(D['ETHUSDT']['basis'].corr(D['ETHUSDT']['funding'])), abs(c_xs))
    if cmax > 0.6:
        print(f"  corr máx {cmax:.2f} ALTA → basis ≈ funding/carry. A4 duplicaría el sleeve #4.")
        print("  NO bajar spot del universo sin una variante que capture algo que el funding NO ve")
        print("  (p.ej. basis intradía/dislocaciones, no el nivel). Documentar y parar A4 aquí.")
    else:
        print(f"  corr máx {cmax:.2f} MODERADA/BAJA → hay info ortogonal. VALE bajar spot del universo")
        print("  (~23 símbolos, data.binance.vision) y construir el sleeve cross-seccional de basis.")


if __name__ == "__main__":
    main()
