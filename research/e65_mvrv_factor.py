"""
E65 — Coin Metrics ampliado: factor MVRV (valuación on-chain) + harness. (2026-06-02).
Barrido del catálogo community: el netflow (FlowInEx/OutEx) y exchange-supply son SOLO BTC/ETH community-
free → NO cross-seccional (muro market-wide, descartado). El lead usable = **MVRV (CapMVRVCur, 14 coins)**
= market cap / realized cap (precio vs coste base on-chain). Alto MVRV = sobrevalorado; bajo = infravalorado.
Es un factor de VALOR/fundamental, potencialmente ortogonal a momentum/trend. También mcap (size con dato
REAL, ≠ proxy de e35) y fees. Descarga + harness brutal (corr<0.35 + IS/OOS + Δ ancla + vivo 2022+).
No toca prod. python -m research.e65_mvrv_factor
"""
from __future__ import annotations
import os, sys, time
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

HC = config.LEVERAGE_HAIRCUT; SHIFT = 2
CM_BASE = "https://community-api.coinmetrics.io/v4"
CACHE = os.path.join(config.DATA_DIR, "onchain_cm_fund"); os.makedirs(CACHE, exist_ok=True)
CM2TKR = {"aave": "AAVEUSDT", "ada": "ADAUSDT", "bch": "BCHUSDT", "bnb": "BNBUSDT", "btc": "BTCUSDT",
          "doge": "DOGEUSDT", "dot": "DOTUSDT", "etc": "ETCUSDT", "eth": "ETHUSDT", "link": "LINKUSDT",
          "ltc": "LTCUSDT", "uni": "UNIUSDT", "xrp": "XRPUSDT", "zec": "ZECUSDT"}
METRICS = "CapMVRVCur,CapMrktCurUSD"


def download():
    n = 0
    for cm in CM2TKR:
        try:
            rows = []; url = f"{CM_BASE}/timeseries/asset-metrics"
            params = {"assets": cm, "metrics": METRICS, "frequency": "1d", "start_time": "2016-01-01", "page_size": 10000}
            for _ in range(30):
                r = requests.get(url, params=params, timeout=60)
                if r.status_code != 200: break
                j = r.json(); rows += j.get("data", [])
                if not j.get("next_page_url"): break
                url = j["next_page_url"]; params = None
            if not rows: continue
            df = pd.DataFrame(rows); df["time"] = pd.to_datetime(df["time"])
            for c in ("CapMVRVCur", "CapMrktCurUSD"):
                if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
            df.sort_values("time").to_parquet(os.path.join(CACHE, f"{cm}.parquet")); n += 1
        except Exception: continue
        time.sleep(0.1)
    return n


def load_fund(daily_idx, cols):
    mv, mc = {}, {}
    for cm, tkr in CM2TKR.items():
        if tkr not in cols: continue
        p = os.path.join(CACHE, f"{cm}.parquet")
        if not os.path.exists(p): continue
        d = pd.read_parquet(p).set_index("time")
        d.index = pd.to_datetime(d.index, utc=True).normalize()
        # descartar stale (última fecha > 30d vieja)
        if d.index.max() < pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=20):
            continue
        if "CapMVRVCur" in d: mv[tkr] = d["CapMVRVCur"]
        if "CapMrktCurUSD" in d: mc[tkr] = d["CapMrktCurUSD"]
    MV = pd.DataFrame(mv).reindex(daily_idx).astype(float)
    MC = pd.DataFrame(mc).reindex(daily_idx).astype(float)
    return MV, MC


def to_hourly(sd, C): return sd.shift(SHIFT).reindex(C.index, method="ffill").reindex(columns=C.columns)
def combine(series):
    df = pd.concat(series, axis=1).dropna(); port = (df*vol_parity_weights(df)).sum(axis=1)
    lev = min(HC*leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return metrics(port*lev)
def half(s):
    h = len(s)//2; return metrics(s.iloc[:h]).get("sharpe", float("nan")), metrics(s.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E65 — MVRV (valuación on-chain) + harness\n")
    print(f"descargando MVRV+mcap... {download()}/14 coins\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    Pd = C.resample("1D").last(); Pd.index = pd.to_datetime(Pd.index, utc=True).normalize()
    MV, MC = load_fund(Pd.index, list(C.columns))
    cov = [c for c in MV.columns if MV[c].notna().sum() > 300 and c != DRIVER]
    print(f"MVRV cubre {len(cov)} coins operables: {cov}\n")

    base = {}
    base["mom_30d"], _ = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _ = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _ = carry_sleeve(C, ret, beta)
    base["trend"], _ = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df7 = pd.concat(base, axis=1).dropna(); m7 = combine(base)
    print(f"BASELINE 7: Sharpe {m7['sharpe']:.2f} · {m7['ann']/12:.2f}%/mes\n")

    lmv = np.log(MV.replace(0, np.nan)); lmc = np.log(MC.replace(0, np.nan))
    def mk(kind, N):
        if kind == "mvrv_lvl":  return -lmv                        # short high MVRV (valor)
        if kind == "mvrv_mom":  return lmv.diff(N)                 # cambio de valuación
        if kind == "mvrv_z":    return -(lmv - lmv.rolling(N).mean())  # desviación de su media (mean-rev)
        if kind == "size":      return -lmc                        # size: long small-cap
        return None

    cands = [("mvrv_lvl", "mvrv_lvl", 0, 30*24), ("mvrv_lvl(+)", "mvrv_lvl_p", 0, 30*24),
             ("mvrv_mom_14d", "mvrv_mom", 14, 14*24), ("mvrv_mom_30d", "mvrv_mom", 30, 30*24),
             ("mvrv_z_30d", "mvrv_z", 30, 30*24), ("mvrv_z_90d", "mvrv_z", 90, 90*24),
             ("size", "size", 0, 30*24)]
    print(f"{'candidato':14s} {'Sh':>6s} {'corr_max':>9s} {'(con)':>12s} {'IS/OOS':>11s} {'mes22+':>7s} │ {'Δ%/mes':>7s} adm")
    print("─" * 92)
    passers = []
    for name, kind, N, hold in cands:
        k2 = kind.replace("_p", "")
        sd = mk(k2, N)
        if name.endswith("(+)"): sd = -sd
        s_c, _ = xs_sleeve(C, ret, beta, to_hourly(sd, C), hold)
        s_c = s_c.reindex(df7.index).dropna()
        if len(s_c) < 200:
            print(f"{name:14s} (insuf.)"); continue
        msolo = metrics(s_c)["sharpe"]
        corrs = {k: df7[k].corr(s_c) for k in df7.columns}; kmax = max(corrs, key=lambda k: abs(corrs[k])); cmax = corrs[kmax]
        is_, oos_ = half(s_c)
        s22 = s_c[s_c.index >= "2022-01-01"]; mes22 = metrics(s22)["ann"]/12 if len(s22) > 200 else float("nan")
        m8 = combine({**base, name: s_c}); dmes = (m8["ann"]-m7["ann"])/12
        ok = abs(cmax) < 0.35 and is_ > 0.05 and oos_ > 0.05 and dmes > 0.05 and (np.isnan(mes22) or mes22 > 0)
        if ok: passers.append(name)
        flag = "  ✅" if ok else ("  ~" if dmes > 0 and abs(cmax) < 0.35 else "  ✗")
        print(f"{name:14s} {msolo:6.2f} {cmax:9.2f} {kmax:>12s} {is_:5.2f}/{oos_:<5.2f} {mes22:7.2f} │ {dmes:+7.2f}{flag}")
    print(f"\nPASAN: {passers or 'NINGUNO'} → lo que pase: estrés taker + LOO (e60-style). 12-14 coins = delgado.")


if __name__ == "__main__":
    main()
