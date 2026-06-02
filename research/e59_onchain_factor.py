"""
E59 — TIER 1 ON-CHAIN: backtest del factor de actividad de direcciones + harness. (2026-06-02).
Datos: `data/onchain_cm/` (e58, Coin Metrics Community, 13 coins AdrActCnt+TxCnt). Construye, análogo al
TVL (e27, que dio +0.6%/mes taker):
  • addr_pxdiv_Nd = Δlog(AdrActCnt,N) − retorno(N)   (actividad neta de precio = acumulación fundamental)
  • tx_pxdiv_Nd   = Δlog(TxCnt,N)     − retorno(N)
  • addr_mom_Nd   = Δlog(AdrActCnt,N)  (momentum de actividad crudo)
Lag point-in-time (SHIFT días, el dato llega con 1-2d retraso). Harness brutal: corr<0.35 con los 7
sleeves + IS/OOS + Δ al ancla maxDD −10%. Lo que pase → estrés taker + split point-in-time → blend #8.
No toca producción. python -m research.e59_onchain_factor
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

HC = config.LEVERAGE_HAIRCUT
SHIFT = 2   # lag point-in-time (días): el dato on-chain llega con 1-2d → usar hasta t−SHIFT
CM2TKR = {"aave": "AAVEUSDT", "ada": "ADAUSDT", "bch": "BCHUSDT", "btc": "BTCUSDT", "doge": "DOGEUSDT",
          "etc": "ETCUSDT", "eth": "ETHUSDT", "link": "LINKUSDT", "ltc": "LTCUSDT", "trx": "TRXUSDT",
          "uni": "UNIUSDT", "xrp": "XRPUSDT", "zec": "ZECUSDT"}


def load_onchain(daily_idx, cols):
    """Paneles diarios AdrActCnt y TxCnt alineados a `daily_idx`, columnas = tickers presentes en `cols`."""
    adr, tx = {}, {}
    for cm, tkr in CM2TKR.items():
        if tkr not in cols:
            continue
        p = os.path.join(config.DATA_DIR, "onchain_cm", f"{cm}.parquet")
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p).set_index("time")
        adr[tkr] = d["AdrActCnt"]; tx[tkr] = d["TxCnt"]
    ADR = pd.DataFrame(adr).reindex(daily_idx).astype(float)
    TX = pd.DataFrame(tx).reindex(daily_idx).astype(float)
    return ADR, TX


def to_hourly_score(score_daily, C):
    """Score diario → DataFrame horario alineado a C (ffill), columnas = C.columns (NaN fuera del set)."""
    s = score_daily.shift(SHIFT)                          # lag point-in-time
    sh = s.reindex(C.index, method="ffill")
    return sh.reindex(columns=C.columns)


def combine(series: dict):
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df); port = (df * vp).sum(axis=1)
    lev = min(HC * leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return port, metrics(port * lev)


def half(s):
    h = len(s) // 2
    return metrics(s.iloc[:h]).get("sharpe", float("nan")), metrics(s.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E59 — factor on-chain (direcciones activas) · harness brutal\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    Pd = C.resample("1D").last()
    ADR, TX = load_onchain(Pd.index, list(C.columns))
    covered = [c for c in ADR.columns if ADR[c].notna().sum() > 300]
    trad = [c for c in covered if c != DRIVER]
    print(f"on-chain cubre {len(covered)} coins ({len(trad)} operables, BTC=driver excluido): {trad}\n")

    # 7 sleeves base
    base = {}
    base["mom_30d"], _ = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _ = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _ = carry_sleeve(C, ret, beta)
    base["trend"], _ = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df7 = pd.concat(base, axis=1).dropna()
    _, m7 = combine(base)
    print(f"BASELINE 7: Sharpe {m7['sharpe']:.2f} · {m7['ann']/12:.2f}%/mes · maxDD {m7['maxdd']:.1f}%\n")

    logadr = np.log(ADR.replace(0, np.nan)); logtx = np.log(TX.replace(0, np.nan)); logp = np.log(Pd[ADR.columns])

    def mk(kind, N):
        if kind == "addr_pxdiv": sd = logadr.diff(N) - logp.diff(N)
        elif kind == "tx_pxdiv": sd = logtx.diff(N) - logp.diff(N)
        elif kind == "addr_mom": sd = logadr.diff(N)
        else: sd = -(logadr.diff(N) - logp.diff(N))
        return sd

    cands = []
    for kind in ("addr_pxdiv", "tx_pxdiv", "addr_mom"):
        for N in (7, 14, 30):
            cands.append((f"{kind}_{N}d", kind, N, N * 24))

    print(f"{'candidato':16s} {'Sh':>6s} {'corr_max':>9s} {'(con)':>11s} {'IS/OOS':>11s} {'mes22+':>7s} │ {'Δ%/mes':>7s}  adm")
    print("─" * 92)
    res = []
    for name, kind, N, hold in cands:
        sd = mk(kind, N)
        score = to_hourly_score(sd, C)
        s_c, _ = xs_sleeve(C, ret, beta, score, hold)
        s_c = s_c.reindex(df7.index).dropna()
        if len(s_c) < 200:
            print(f"{name:16s}  (insuf.)"); continue
        msolo = metrics(s_c)["sharpe"]
        corrs = {k: df7[k].corr(s_c) for k in df7.columns}
        kmax = max(corrs, key=lambda k: abs(corrs[k])); cmax = corrs[kmax]
        is_, oos_ = half(s_c)
        # contribución 2022+ (point-in-time: ¿el edge vive en la era madura, no en backfill?)
        s22 = s_c[s_c.index >= "2022-01-01"]; mes22 = metrics(s22)["ann"] / 12 if len(s22) > 200 else float("nan")
        b8 = dict(base); b8[name] = s_c; _, m8 = combine(b8)
        dmes = (m8["ann"] - m7["ann"]) / 12
        ok = abs(cmax) < 0.35 and is_ > 0.05 and oos_ > 0.05 and dmes > 0.03
        flag = "  ✅" if ok else ("  ~" if dmes > 0 and abs(cmax) < 0.35 else "  ✗")
        print(f"{name:16s} {msolo:6.2f} {cmax:9.2f} {kmax:>11s} {is_:5.2f}/{oos_:<5.2f} {mes22:7.2f} │ {dmes:+7.2f}{flag}")
        res.append((name, abs(cmax), is_, oos_, dmes, ok))

    passers = [r for r in res if r[5]]
    print(f"\nPASAN el filtro inicial: {[r[0] for r in passers] or 'NINGUNO'}")
    print("LECTURA: corr<0.35 + IS/OOS>0.05 + Δ%/mes>0.03 + edge vivo 2022+ (no backfill). Lo que pase →")
    print("estrés taker (slip ADV) + LOO por coin (cross-section delgado: cuidado con depender de 1 nombre).")
    print("Honesto: 12 coins es delgado; si nada pasa limpio, el on-chain de direcciones no aporta cross-sec aquí.")


if __name__ == "__main__":
    main()
