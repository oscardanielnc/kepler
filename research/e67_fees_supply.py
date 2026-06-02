"""
E67 — Coin Metrics, CIERRE del barrido: fees + supply/issuance. (2026-06-02).
Últimas métricas community sin testear:
  • issuance = −Δlog(SplyCur,N) → tasa de emisión/inflación (alta dilución = bajista → short alta). 14 coins.
  • fee_pxdiv = Δlog(FeeTotNtv,N) − retorno(N) → actividad económica neta de precio. 9 coins (¿solapa con tx?).
Harness brutal. Si algo pasa → estrés taker+LOO. Si no → familia on-chain AGOTADA (quedan tx_pxdiv + mvrv).
No toca prod. python -m research.e67_fees_supply
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
CM2TKR = {"aave": "AAVEUSDT", "ada": "ADAUSDT", "bch": "BCHUSDT", "btc": "BTCUSDT", "doge": "DOGEUSDT",
          "etc": "ETCUSDT", "eth": "ETHUSDT", "link": "LINKUSDT", "ltc": "LTCUSDT", "uni": "UNIUSDT",
          "xrp": "XRPUSDT", "zec": "ZECUSDT"}
METRICS = "FeeTotNtv,SplyCur"


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
            for c in ("FeeTotNtv", "SplyCur"):
                if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
            df.sort_values("time").to_parquet(os.path.join(CACHE, f"fs_{cm}.parquet")); n += 1
        except Exception: pass
        time.sleep(0.1)
    return n


def load_fs(daily_idx, cols):
    fee, sply = {}, {}
    cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=20)
    for cm, tkr in CM2TKR.items():
        if tkr not in cols: continue
        p = os.path.join(CACHE, f"fs_{cm}.parquet")
        if not os.path.exists(p): continue
        d = pd.read_parquet(p).set_index("time"); d.index = pd.to_datetime(d.index, utc=True).normalize()
        if d.index.max() < cutoff: continue
        if "FeeTotNtv" in d and d["FeeTotNtv"].dropna().shape[0] > 300: fee[tkr] = d["FeeTotNtv"]
        if "SplyCur" in d and d["SplyCur"].dropna().shape[0] > 300: sply[tkr] = d["SplyCur"]
    return (pd.DataFrame(fee).reindex(daily_idx).astype(float),
            pd.DataFrame(sply).reindex(daily_idx).astype(float))


def th(sd, C): return sd.shift(SHIFT).reindex(C.index, method="ffill").reindex(columns=C.columns)
def comb(series):
    df = pd.concat(series, axis=1).dropna(); port = (df*vol_parity_weights(df)).sum(axis=1)
    lev = min(HC*leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return metrics(port*lev)
def half(s):
    h = len(s)//2; return metrics(s.iloc[:h]).get("sharpe", float("nan")), metrics(s.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E67 — CIERRE barrido Coin Metrics: fees + supply/issuance\n")
    print(f"descargando fees+supply... {download()} coins\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    Pd = C.resample("1D").last(); Pd.index = pd.to_datetime(Pd.index, utc=True).normalize()
    FEE, SPLY = load_fs(Pd.index, list(C.columns))
    print(f"fees: {[c for c in FEE.columns if FEE[c].notna().sum()>300]} ({FEE.shape[1]}) · "
          f"supply: {SPLY.shape[1]} coins\n")

    base = {}
    base["mom_30d"], _ = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _ = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _ = carry_sleeve(C, ret, beta)
    base["trend"], _ = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df7 = pd.concat(base, axis=1).dropna(); m7 = comb(base)
    print(f"BASELINE 7: Sharpe {m7['sharpe']:.2f} · {m7['ann']/12:.2f}%/mes\n")

    lfee = np.log(FEE.replace(0, np.nan)); lsply = np.log(SPLY.replace(0, np.nan)); logp = np.log(Pd)
    def mk(kind, N):
        if kind == "issuance":  return -lsply.diff(N)                                  # short alta emisión
        if kind == "fee_pxdiv": return lfee.diff(N) - logp[lfee.columns].diff(N)
        if kind == "fee_mom":   return lfee.diff(N)
        return None
    cands = [("issuance_30d", "issuance", 30, 30*24, 1), ("issuance_90d", "issuance", 90, 90*24, 1),
             ("issuance_30d(+)", "issuance", 30, 30*24, -1),
             ("fee_pxdiv_14d", "fee_pxdiv", 14, 14*24, 1), ("fee_pxdiv_30d", "fee_pxdiv", 30, 30*24, 1),
             ("fee_pxdiv_14d(−)", "fee_pxdiv", 14, 14*24, -1), ("fee_mom_14d", "fee_mom", 14, 14*24, 1)]
    print(f"{'candidato':17s} {'Sh':>6s} {'corr_max':>9s} {'(con)':>12s} {'IS/OOS':>11s} {'mes22+':>7s} │ {'Δ%/mes':>7s} adm")
    print("─" * 92)
    passers = []
    for name, kind, N, hold, sign in cands:
        sd = mk(kind, N) * sign
        s_c, _ = xs_sleeve(C, ret, beta, th(sd, C), hold); s_c = s_c.reindex(df7.index).dropna()
        if len(s_c) < 200: print(f"{name:17s} (insuf.)"); continue
        corrs = {kk: df7[kk].corr(s_c) for kk in df7.columns}; km = max(corrs, key=lambda k: abs(corrs[k])); cmax = corrs[km]
        is_, oos_ = half(s_c); s22 = s_c[s_c.index >= "2022-01-01"]; mes22 = metrics(s22)["ann"]/12 if len(s22)>200 else float("nan")
        m8 = comb({**base, name: s_c}); dmes = (m8["ann"]-m7["ann"])/12
        ok = abs(cmax) < 0.35 and is_ > 0.05 and oos_ > 0.05 and dmes > 0.05 and (np.isnan(mes22) or mes22 > 0)
        if ok: passers.append(name)
        flag = "  ✅" if ok else ("  ~" if dmes > 0 and abs(cmax) < 0.35 else "  ✗")
        print(f"{name:17s} {metrics(s_c)['sharpe']:6.2f} {cmax:9.2f} {km:>12s} {is_:5.2f}/{oos_:<5.2f} {mes22:7.2f} │ {dmes:+7.2f}{flag}")
    print(f"\nPASAN: {passers or 'NINGUNO'}")
    print("Si NINGUNO → familia on-chain AGOTADA (2 ganadores: tx_pxdiv + mvrv_lvl, ambos en sombra).")


if __name__ == "__main__":
    main()
