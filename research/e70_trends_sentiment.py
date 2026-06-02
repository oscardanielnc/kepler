"""
E70 — SENTIMENT/SOCIAL vía GOOGLE TRENDS (gratis, keyless). (2026-06-02)
Familia nueva (Oscar): agotar sentiment/social gratis. Lo único keyless con histórico cross-seccional es
Google Trends (interés de búsqueda = atención/retail; factor académico). Santiment/LunarCrush/Dune exigen
API key (registro de Oscar). Caveats: semanal, ambigüedad de tickers (uso nombres limpios), normalización
cruzada vía ancla BTC.

CHEQUEO BARATO (método e22/e26): ¿el factor de atención es ORTOGONAL a los 7 sleeves (corr<0.35) y tiene
señal standalone? Si no → familia agotada. Si sí → profundizar (taker/LOO/sombra).

Pull cacheado en data/trends/ (no re-pegar a Google). python -m research.e70_trends_sentiment
"""
from __future__ import annotations
import os, sys, time
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, _weights_from_score, compute_target, DRIVER
from kepler.portfolio import metrics, leverage_robust

CACHE = os.path.join(config.DATA_DIR, "trends", "attention_weekly.parquet")
ANCHOR = "bitcoin"
TERMS = {"ETHUSDT":"ethereum","SOLUSDT":"solana","XRPUSDT":"xrp","DOGEUSDT":"dogecoin","ADAUSDT":"cardano",
 "AVAXUSDT":"avalanche","LINKUSDT":"chainlink","LTCUSDT":"litecoin","TRXUSDT":"tron","BCHUSDT":"bitcoin cash",
 "ETCUSDT":"ethereum classic","UNIUSDT":"uniswap","AAVEUSDT":"aave","ZECUSDT":"zcash","BNBUSDT":"binance coin",
 "DOTUSDT":"polkadot","ATOMUSDT":"cosmos","NEARUSDT":"near protocol","FILUSDT":"filecoin"}


def pull_trends():
    """Panel de atención RELATIVA a BTC (cada moneda / BTC en su mismo lote → escala común). Cacheado."""
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    from pytrends.request import TrendReq
    p = TrendReq(hl="en-US", tz=300)
    syms = list(TERMS); rel = {}
    for i in range(0, len(syms), 4):
        batch = syms[i:i+4]; terms = [ANCHOR] + [TERMS[s] for s in batch]
        for attempt in range(3):
            try:
                p.build_payload(terms, timeframe="2022-01-01 2026-05-31")
                d = p.interest_over_time()
                if "isPartial" in d: d = d.drop(columns="isPartial")
                btc = d[ANCHOR].replace(0, np.nan)
                for s in batch:
                    rel[s] = (d[TERMS[s]] / btc)          # atención relativa a BTC (escala común)
                print(f"  batch {i:2d} OK {d.shape}")
                break
            except Exception as e:
                print(f"  batch {i} retry {attempt}: {type(e).__name__}"); time.sleep(20)
        time.sleep(8)
    A = pd.DataFrame(rel)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True); A.to_parquet(CACHE)
    return A


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E70 — sentiment vía Google Trends: ¿factor de atención ORTOGONAL a los 7? (chequeo barato)\n")
    A = pull_trends()
    A.index = pd.to_datetime(A.index, utc=True)
    print(f"Panel atención: {A.shape[1]} monedas · {A.index[0].date()}->{A.index[-1].date()} ({len(A)} semanas)\n")

    # --- price panel diario + 7 sleeves (referencia de ortogonalidad) ---
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    _, vp, df, port_ret, *_ = compute_target("ESTABLE")     # df = 7 sleeve returns diarios; port_ret combinado
    days = df.index
    px = C.resample("1D").last().reindex(days); rD = px.pct_change()
    beta_d = beta.resample("1D").last().reindex(days).ffill()
    syms = [s for s in A.columns if s in C.columns and s != DRIVER]

    # atención diaria (ffill semanal→diario) + lag 1 semana (point-in-time)
    Ad = A[syms].reindex(A.index.union(days)).sort_index().ffill().reindex(days).shift(7)

    def factor_return(score, hold_d, sign):
        """β-neutral cross-seccional, rebalance cada hold_d (held), retorno diario marcado."""
        sc = (sign * score).reindex(days)
        W = pd.DataFrame(np.nan, index=days, columns=syms)
        for i in range(0, len(days), hold_d):
            d = days[i]
            if d not in sc.index or sc.loc[d].isna().all(): continue
            w, h = _weights_from_score(sc.loc[d], beta_d.loc[d], syms, cap=config.MAX_WEIGHT_NORMAL)
            W.loc[d] = w.reindex(syms).fillna(0.0)
        W = W.ffill().fillna(0.0)
        hedge = -(W * beta_d[syms]).sum(axis=1)
        fwd = rD[syms].shift(-1); fwd_btc = px[DRIVER].pct_change().shift(-1) if DRIVER in px else 0*rD.iloc[:,0]
        r = (W * fwd).sum(axis=1) + hedge * (px[DRIVER].pct_change().shift(-1))
        return r.dropna()

    # candidatos de factor (análogos a los on-chain ganadores)
    la = np.log(Ad.clip(lower=1e-6))
    cands = {}
    for n in (2, 4, 8):     # semanas de lookback
        cands[f"attn_mom_{n}w"]   = la.diff(n)                                  # atención subiendo (momentum)
        cands[f"attn_pxdiv_{n}w"] = la.diff(n) - np.log(px[syms]/px[syms].shift(n*7))  # atención − precio (divergencia, como tx_pxdiv)

    print(f"{'factor':18s} {'signo':>5s} │ {'Sharpe':>6s} {'%/mes':>6s} │ corr máx vs 7 sleeves (y cuál)")
    print("─"*88)
    sleeve_cols = list(df.columns)
    best = []
    for name, sc in cands.items():
        for sign in (+1, -1):
            r = factor_return(sc, 14, sign)
            if len(r) < 200: continue
            m = metrics(r)
            cм = {k: r.corr(df[k].reindex(r.index)) for k in sleeve_cols}
            cmax_k = max(cм, key=lambda k: abs(cм[k])); cmax = cм[cmax_k]
            cport = r.corr(port_ret.reindex(r.index))
            tag = "ORTO" if abs(cmax) < 0.35 else "solapa"
            print(f"{name:18s} {sign:+5d} │ {m.get('sharpe',0):6.2f} {m.get('ann',0)/12:6.2f} │ "
                  f"max |corr| {abs(cmax):.2f} ({cmax_k} {cmax:+.2f}) · vs combo {cport:+.2f}  [{tag}]")
            best.append((m.get('sharpe',0), abs(cmax), name, sign))
    # --- STRESS del mejor candidato: taker (turnover×TAKER_FEE) + IS/OOS por mitades ---
    def factor_return_cost(score, hold_d, sign, taker):
        sc = (sign * score).reindex(days)
        W = pd.DataFrame(np.nan, index=days, columns=syms)
        for i in range(0, len(days), hold_d):
            d = days[i]
            if d not in sc.index or sc.loc[d].isna().all(): continue
            w, h = _weights_from_score(sc.loc[d], beta_d.loc[d], syms, cap=config.MAX_WEIGHT_NORMAL)
            W.loc[d] = w.reindex(syms).fillna(0.0)
        W = W.ffill().fillna(0.0)
        hedge = -(W * beta_d[syms]).sum(axis=1)
        turn = (W.diff().abs().sum(axis=1) + hedge.diff().abs()).fillna(0.0)
        r = (W * rD[syms].shift(-1)).sum(axis=1) + hedge*(px[DRIVER].pct_change().shift(-1)) - turn*taker
        return r.dropna()

    print("\nSTRESS del mejor candidato (attn_pxdiv, contrarian) — taker + IS/OOS:")
    for n in (2, 4):
        sc = np.log(Ad.clip(lower=1e-6)).diff(n) - np.log(px[syms]/px[syms].shift(n*7))
        rk = factor_return(sc, 14, -1); rt = factor_return_cost(sc, 14, -1, config.TAKER_FEE)
        h = len(rk)//2
        is_s, oos_s = metrics(rk.iloc[:h]).get("sharpe",0), metrics(rk.iloc[h:]).get("sharpe",0)
        mk, mt = metrics(rk), metrics(rt)
        print(f"  attn_pxdiv_{n}w(-1): maker Sh {mk['sharpe']:.2f} ({mk['ann']/12:.2f}%/mes) · "
              f"TAKER Sh {mt['sharpe']:.2f} ({mt['ann']/12:+.2f}%/mes) · IS {is_s:.2f}/OOS {oos_s:.2f}")
    print("\nLECTURA: candidato vivo = sobrevive TAKER (>0) Y IS/OOS balanceado. Si muere a taker o es IS-only")
    print("→ atención Trends no es sleeve operable (familia sentiment-keyless agotada).")


if __name__ == "__main__":
    main()
