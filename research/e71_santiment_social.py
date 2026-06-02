"""
E71 — SENTIMENT vía SANTIMENT (sanpy, key gratis). (2026-06-02)
Familia sentiment, fuente estable (≠ Google Trends frágil). CAVEAT del free tier: solo ~1 AÑO de historia
+ lag 30 días + 1000 calls/mes → chequeo EXPLORATORIO (no validación IS/OOS robusta; eso exigiría tier
pago o acumular sombra forward). Pregunta: ¿el factor social es ORTOGONAL a los 7 y tiene señal?

Pull cacheado en data/santiment/. python -m research.e71_santiment_social
"""
from __future__ import annotations
import os, sys, time
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, _weights_from_score, compute_target, DRIVER
from kepler.portfolio import metrics

CACHE = os.path.join(config.DATA_DIR, "santiment")
SLUG = {"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","BNBUSDT":"binance-coin","SOLUSDT":"solana","XRPUSDT":"xrp",
 "DOGEUSDT":"dogecoin","ADAUSDT":"cardano","AVAXUSDT":"avalanche","LINKUSDT":"chainlink","DOTUSDT":"polkadot",
 "LTCUSDT":"litecoin","TRXUSDT":"tron","BCHUSDT":"bitcoin-cash","ETCUSDT":"ethereum-classic","ATOMUSDT":"cosmos",
 "NEARUSDT":"near-protocol","FILUSDT":"filecoin","UNIUSDT":"uniswap","AAVEUSDT":"aave","ZECUSDT":"zcash"}


def pull(metric):
    """Panel diario {symbol: serie} de `metric`, cacheado por métrica."""
    fp = os.path.join(CACHE, f"{metric}.parquet")
    if os.path.exists(fp):
        return pd.read_parquet(fp)
    import san
    san.ApiConfig.api_key = open(os.path.join(config.DATA_DIR, ".santiment_key")).read().strip()
    out = {}
    for sym, slug in SLUG.items():
        try:
            d = san.get(f"{metric}/{slug}", from_date="2024-06-01", to_date="2026-06-02", interval="1d")
            if len(d): out[sym] = d["value"]
        except Exception as e:
            print(f"  {sym:9s} ({slug}) ERR {str(e)[:60]}")
        time.sleep(0.3)
    df = pd.DataFrame(out); os.makedirs(CACHE, exist_ok=True); df.to_parquet(fp)
    return df


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E71 — Santiment social: ¿factor ORTOGONAL a los 7? (EXPLORATORIO, ~1y free tier)\n")
    SV = pull("social_volume_total"); SB = pull("sentiment_balance_total")
    SV.index = pd.to_datetime(SV.index, utc=True); SB.index = pd.to_datetime(SB.index, utc=True)
    print(f"social_volume: {SV.shape[1]} monedas · {SV.index[0].date()}->{SV.index[-1].date()} ({len(SV)} días)\n")

    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    _, vp, df, port_ret, *_ = compute_target("ESTABLE")
    days = df.index
    px = C.resample("1D").last().reindex(days); rD = px.pct_change()
    beta_d = beta.resample("1D").last().reindex(days).ffill()
    syms = [s for s in SV.columns if s in C.columns and s != DRIVER]

    def to_daily(P): return P[syms].reindex(P.index.union(days)).sort_index().ffill().reindex(days).shift(2)
    SVd, SBd = to_daily(SV), to_daily(SB)

    def fret(score, hold_d, sign, taker=0.0):
        sc = (sign * score).reindex(days)
        W = pd.DataFrame(np.nan, index=days, columns=syms)
        for i in range(0, len(days), hold_d):
            d = days[i]
            if d not in sc.index or sc.loc[d].isna().all(): continue
            w, _ = _weights_from_score(sc.loc[d], beta_d.loc[d], syms, cap=config.MAX_WEIGHT_NORMAL)
            W.loc[d] = w.reindex(syms).fillna(0.0)
        W = W.ffill().fillna(0.0)
        hedge = -(W * beta_d[syms]).sum(axis=1)
        turn = (W.diff().abs().sum(axis=1) + hedge.diff().abs()).fillna(0.0)
        r = (W*rD[syms].shift(-1)).sum(axis=1) + hedge*(px[DRIVER].pct_change().shift(-1)) - turn*taker
        return r.dropna()

    lv = np.log(SVd.clip(lower=1)); lpx = np.log(px[syms])
    cands = {
        "socvol_mom_14":   lv.diff(14),                                  # atención subiendo
        "socvol_pxdiv_14": lv.diff(14) - (lpx - lpx.shift(14)),          # social − precio (como tx_pxdiv)
        "sentiment_lvl":   SBd,                                           # balance pos-neg (nivel)
        "sentiment_mom_14":SBd.diff(14),
    }
    sleeve_cols = list(df.columns)
    print(f"{'factor':18s} {'sg':>3s} │ {'Sharpe':>6s} {'%/mes':>6s} {'tkrSh':>6s} │ max|corr| vs 7 (cuál) · vs combo")
    print("─"*92)
    for name, sc in cands.items():
        for sign in (+1, -1):
            r = fret(sc, 14, sign); rt = fret(sc, 14, sign, config.TAKER_FEE)
            if len(r) < 120: continue
            m, mt = metrics(r), metrics(rt)
            cm = {k: r.corr(df[k].reindex(r.index)) for k in sleeve_cols}
            ck = max(cm, key=lambda k: abs(cm[k])); cmax = cm[ck]
            cport = r.corr(port_ret.reindex(r.index))
            tag = "ORTO" if abs(cmax) < 0.35 else "solapa"
            print(f"{name:18s} {sign:+3d} │ {m.get('sharpe',0):6.2f} {m.get('ann',0)/12:6.2f} {mt.get('sharpe',0):6.2f} │ "
                  f"{abs(cmax):.2f} ({ck} {cmax:+.2f}) · {cport:+.2f}  [{tag}]")
    print("\nCAVEAT: ~1 año de datos (free tier) → SIN IS/OOS robusto. Esto solo dice si HAY señal ortogonal.")
    print("Si prometedor → sombra forward (acumular) o tier pago (más historia). Si plano/solapa → agotado.")


if __name__ == "__main__":
    main()
