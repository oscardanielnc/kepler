"""
Kepler — SLEEVE EN MODO SOMBRA: on-chain TVL (DefiLlama, GRATIS). NO OPERA.
(2026-05-31). Validado en research e26/e27: `tvl_pxdiv_14d` (acumulación = el TVL on-chain de la
cadena sube más que el precio del token) es ortogonal (corr 0.11) y aporta +0.6%/mes taker al ancla,
con el edge en 2023+ (cobertura madura). PERO el TVL histórico de DefiLlama es RECONSTRUIDO → ningún
backtest puede descartar look-ahead por revisión de datos. La ÚNICA prueba válida es FORWARD:

  Cada ciclo (24h) este módulo calcula los pesos que el sleeve TVL TENDRÍA y los REGISTRA en la DB
  (tabla shadow_signal) SIN operar. Acumulando semanas de señal viva (que el futuro no puede revisar)
  se mide su retorno real → confirma o no el edge antes de promoverlo a producción.

NO toca el target que se opera. Se promueve a un sleeve real (alphas.py + engine.SLEEVES) solo si la
sombra confirma. python -m kepler.onchain   (corre una vez, imprime y loguea).
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

CACHE = os.path.join(config.DATA_DIR, "defillama"); os.makedirs(CACHE, exist_ok=True)
LOOKBACK_DAYS = 14
SLEEVE = "onchain_tvl_pxdiv_14d"
# Blend cross-family candidato a sleeve #8 (research e38/e40/e41): lotería(max_60d) + tvl_pxdiv +
# iliquidez(Amihud). Validado: OOS purgado +0.34 Sharpe / 6-6 folds, sobrevive taker (+1.55%/mes
# ADV central), full-history (sin punto ciego 2022). En SOMBRA por: TVL revisable + lotería 60d pico.
# Signos FIJOS de la validación (NO re-orientar cada ciclo): lotería −1, tvl −1, illiq +1.
BLEND_SLEEVE = "blend_lottery_tvl_illiq_v1"
BLEND_SIGNS = {"lottery": -1.0, "tvl": -1.0, "illiq": 1.0}
# token del universo → cadena (chain-TVL) o protocolo (protocol-TVL) en DefiLlama
CHAINS = {"ETHUSDT": "Ethereum", "BNBUSDT": "BSC", "SOLUSDT": "Solana", "AVAXUSDT": "Avalanche",
          "TRXUSDT": "Tron", "NEARUSDT": "Near", "ADAUSDT": "Cardano", "HBARUSDT": "Hedera",
          "FILUSDT": "Filecoin", "XLMUSDT": "Stellar"}
PROTOCOLS = {"AAVEUSDT": "aave", "UNIUSDT": "uniswap"}


def _fetch_series(url, key):
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return None
        d = r.json()
        arr = d.get("tvl", d) if isinstance(d, dict) else d
        if not isinstance(arr, list) or not arr:
            return None
        s = pd.Series([x[key] for x in arr],
                      index=pd.to_datetime([x["date"] for x in arr], unit="s", utc=True))
        return s[~s.index.duplicated()].sort_index()
    except Exception:
        return None


def update_tvl() -> int:
    """Refresca TVL diario (chain + protocol) de DefiLlama. Cachea un parquet por token. DefiLlama
    devuelve la historia completa en cada llamada (barato, ~12 requests) → se sobrescribe."""
    ok = 0
    for tok, ch in CHAINS.items():
        s = _fetch_series(f"https://api.llama.fi/v2/historicalChainTvl/{ch}", "tvl")
        if s is not None and s.replace(0, np.nan).dropna().shape[0] >= 300:
            s.rename("tvl").to_frame().to_parquet(os.path.join(CACHE, f"shadow_{tok}.parquet")); ok += 1
    for tok, slug in PROTOCOLS.items():
        s = _fetch_series(f"https://api.llama.fi/protocol/{slug}", "totalLiquidityUSD")
        if s is not None and s.replace(0, np.nan).dropna().shape[0] >= 300:
            s.rename("tvl").to_frame().to_parquet(os.path.join(CACHE, f"shadow_{tok}.parquet")); ok += 1
    return ok


def _daily_logtvl(symbols):
    cols = {}
    for tok in list(CHAINS) + list(PROTOCOLS):
        if tok not in symbols:
            continue
        p = os.path.join(CACHE, f"shadow_{tok}.parquet")
        if not os.path.exists(p):
            continue
        s = pd.read_parquet(p)["tvl"]
        cols[tok] = np.log(s.replace(0, np.nan))
    df = pd.DataFrame(cols)
    if df.empty:
        return df
    df.index = df.index.normalize()
    return df[~df.index.duplicated()].sort_index()


def _to_hourly(daily_df, C):
    """log-TVL diario → índice horario de C, REZAGADO 1 día (anti-look-ahead: usar el día D-1 completo).
    ffill al reindexar: DefiLlama publica con 1-2 días de retraso → si C es más fresco que el TVL, sin
    ffill las últimas filas quedaban NaN (score NaN → pesos 0 → sombra logueaba 0). El shift(1) ya evita
    el look-ahead; usar el último TVL conocido es lo point-in-time correcto."""
    d = daily_df.shift(1)
    cidx_date = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx_date)), utc=True)
    return d.reindex(uniq, method="ffill").reindex(cidx_date).set_axis(C.index).reindex(columns=C.columns)


def shadow_weights():
    """Pesos ACTUALES que el sleeve TVL tendría (β-neutral, vía la maquinaria del motor). NO opera."""
    from kepler.engine import load, _beta, xs_sleeve  # import diferido (evita ciclo)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    dl = _daily_logtvl(list(C.columns))
    if dl.empty:
        return None, None, C.index[-1]
    h = LOOKBACK_DAYS * 24
    logtvl = _to_hourly(dl, C)
    # SCORE = Δlog(TVL) − retorno (acumulación: TVL sube más que el precio). Long alto = acumulación.
    score = logtvl.diff(h) - ret.reindex(columns=C.columns).rolling(h).sum()
    _, w_now = xs_sleeve(C, ret, beta, score, h)          # pesos actuales β-neutral (incl. hedge BTC)
    score_now = score.iloc[-1]
    return w_now, score_now, C.index[-1]


def run_shadow(db=None) -> dict:
    """Calcula y REGISTRA (sin operar) los pesos del sleeve TVL de este ciclo. Idempotente/aislado."""
    from kepler.db import DB
    db = db or DB()
    update_tvl()
    w, score, asof = shadow_weights()
    if w is None:
        db.audit("WARNING", "shadow_onchain", "Sin datos TVL — sombra omitida")
        return {"logged": 0}
    n = 0
    for sym, wt in w.items():
        if abs(float(wt)) <= 1e-6:
            continue
        sc = float(score.get(sym, float("nan"))) if score is not None else None
        db.log_shadow(sleeve=SLEEVE, symbol=sym, weight=round(float(wt), 4),
                      score=(None if sc is None or np.isnan(sc) else round(sc, 6)),
                      detail={"asof": str(asof), "lookback_d": LOOKBACK_DAYS})
        n += 1
    db.audit("INFO", "shadow_onchain", f"Sombra TVL registrada ({n} posiciones)",
             detail={"sleeve": SLEEVE, "asof": str(asof)})
    return {"logged": n, "asof": str(asof)}


def _blend_target_weights():
    """Pesos combinados ACTUALES del blend {lotería + tvl + illiq} (vol-parity de los 3 mini-sleeves
    β-neutral, signos fijos de la validación). NO opera. Devuelve (pesos_por_símbolo, asof)."""
    from kepler.engine import load, _beta, xs_sleeve, load_panel
    from kepler.portfolio import vol_parity_weights
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); cols = list(C.columns)
    h = LOOKBACK_DAYS * 24
    # tvl_pxdiv (acumulación on-chain), signo fijo
    dl = _daily_logtvl(cols)
    if dl.empty:
        return None, C.index[-1]
    logtvl = _to_hourly(dl, C)
    tvl_score = (logtvl.diff(h) - ret.reindex(columns=cols).rolling(h).sum()) * BLEND_SIGNS["tvl"]
    s_tvl, w_tvl = xs_sleeve(C, ret, beta, tvl_score, h)
    # iliquidez de Amihud, signo fijo (long ilíquido)
    dvol = load_panel(["quote_volume"], C)["quote_volume"]
    ilq_score = np.log((ret.abs() / dvol.replace(0, np.nan)).rolling(h).mean().replace(0, np.nan)) * BLEND_SIGNS["illiq"]
    s_ilq, w_ilq = xs_sleeve(C, ret, beta, ilq_score, h)
    # lotería (max de retornos diarios 60d → short high-MAX), signo fijo
    rd = C.resample("1D").last().pct_change(); rd.index = rd.index.normalize()
    lot_score = _to_hourly(rd.rolling(60).max(), C) * BLEND_SIGNS["lottery"]
    s_lot, w_lot = xs_sleeve(C, ret, beta, lot_score, 60 * 24)
    # vol-parity de los 3 → pesos combinados por símbolo (incl. hedge BTC de cada componente)
    df = pd.concat({"lottery": s_lot, "tvl": s_tvl, "illiq": s_ilq}, axis=1).dropna()
    if df.empty:
        return None, C.index[-1]
    vp = vol_parity_weights(df)
    combined = pd.Series(0.0, index=cols)
    for name, w in (("lottery", w_lot), ("tvl", w_tvl), ("illiq", w_ilq)):
        combined = combined.add(float(vp[name]) * w.reindex(cols).fillna(0), fill_value=0)
    return combined, C.index[-1]


def run_blend_shadow(db=None) -> dict:
    """Registra (sin operar) los pesos del BLEND candidato a sleeve #8. Idempotente/aislado."""
    from kepler.db import DB
    db = db or DB()
    update_tvl()
    try:
        w, asof = _blend_target_weights()
    except Exception as e:
        db.audit("WARNING", "shadow_blend", f"Blend omitido: {str(e)[:80]}")
        return {"logged": 0}
    if w is None:
        db.audit("WARNING", "shadow_blend", "Sin datos para el blend — sombra omitida")
        return {"logged": 0}
    n = 0
    for sym, wt in w.items():
        if abs(float(wt)) <= 1e-6:
            continue
        db.log_shadow(sleeve=BLEND_SLEEVE, symbol=sym, weight=round(float(wt), 4),
                      score=None, detail={"asof": str(asof)})
        n += 1
    db.audit("INFO", "shadow_blend", f"Sombra BLEND registrada ({n} posiciones)",
             detail={"sleeve": BLEND_SLEEVE, "asof": str(asof)})
    return {"logged": n, "asof": str(asof)}


# ─── SOMBRA on-chain TX (Coin Metrics Community, GRATIS sin key) — candidato a sleeve #8 DIRECTO ──────
# tx_pxdiv_14d = Δlog(TxCnt,14d) − retorno(14d): actividad transaccional neta de precio. Validado e59/e60/
# e61: ortogonal a los 7 sleeves (corr −0.10) Y al blend (corr +0.09 vs TVL = NO solapa), sobrevive taker
# (Δ +1.46%/mes vs los 7), LOO robusto (no 1-coin), vivo 2022+. Más fuerte que el TVL. point-in-time LIMPIO
# (direcciones = cadena inmutable, no se revisa ≠ TVL). 12 coins operables. En SOMBRA: validar forward.
CM_BASE = "https://community-api.coinmetrics.io/v4"
CM_CACHE = os.path.join(config.DATA_DIR, "onchain_cm"); os.makedirs(CM_CACHE, exist_ok=True)
TX_SLEEVE = "onchain_tx_pxdiv_14d"
TX_LOOKBACK_D = 14
TX_SHIFT_D = 2     # lag point-in-time (el dato de Coin Metrics llega con 1-2d de retraso)
# 13 coins con AdrActCnt+TxCnt community-free (bnb/dot DESCARTADAS por stale, e58). CM id → ticker Binance.
CM2TKR = {"aave": "AAVEUSDT", "ada": "ADAUSDT", "bch": "BCHUSDT", "btc": "BTCUSDT", "doge": "DOGEUSDT",
          "etc": "ETCUSDT", "eth": "ETHUSDT", "link": "LINKUSDT", "ltc": "LTCUSDT", "trx": "TRXUSDT",
          "uni": "UNIUSDT", "xrp": "XRPUSDT", "zec": "ZECUSDT"}


def update_cm_addresses() -> int:
    """Refresca AdrActCnt+TxCnt diarios (Coin Metrics Community, sin key) → parquet por coin. Overwrite
    (la API da la historia completa paginada; ~13 requests/ciclo). Blindado: si una falla, sigue."""
    ok = 0
    for cm in CM2TKR:
        try:
            rows = []; url = f"{CM_BASE}/timeseries/asset-metrics"
            params = {"assets": cm, "metrics": "AdrActCnt,TxCnt", "frequency": "1d",
                      "start_time": "2016-01-01", "page_size": 10000}
            for _ in range(30):
                r = requests.get(url, params=params, timeout=60)
                if r.status_code != 200:
                    break
                j = r.json(); rows += j.get("data", [])
                nxt = j.get("next_page_url")
                if not nxt:
                    break
                url = nxt; params = None
            if not rows:
                continue
            df = pd.DataFrame(rows); df["time"] = pd.to_datetime(df["time"])
            for c in ("AdrActCnt", "TxCnt"):
                if c in df:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df[["time", "AdrActCnt", "TxCnt"]].sort_values("time").to_parquet(os.path.join(CM_CACHE, f"{cm}.parquet"))
            ok += 1
        except Exception:
            continue
    return ok


def _daily_logtx(symbols):
    """Panel diario de log(TxCnt) para los coins cubiertos presentes en `symbols` (descarta stale)."""
    cols = {}
    for cm, tkr in CM2TKR.items():
        if tkr not in symbols:
            continue
        p = os.path.join(CM_CACHE, f"{cm}.parquet")
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p).set_index("time")
        s = d["TxCnt"].dropna() if "TxCnt" in d else pd.Series(dtype=float)
        if s.empty:
            continue
        cols[tkr] = np.log(s.replace(0, np.nan))
    df = pd.DataFrame(cols)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index, utc=True).normalize()
    return df[~df.index.duplicated()].sort_index()


def tx_shadow_weights():
    """Pesos ACTUALES que el sleeve tx_pxdiv_14d tendría (β-neutral, vía el motor). NO opera."""
    from kepler.engine import load, _beta, xs_sleeve
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    ltx = _daily_logtx(list(C.columns))
    if ltx.empty:
        return None, None, C.index[-1]
    Pd = C.resample("1D").last(); Pd.index = pd.to_datetime(Pd.index, utc=True).normalize()
    ltx = ltx.reindex(Pd.index)                          # grid diario común con el precio
    logp = np.log(Pd[ltx.columns])
    h = TX_LOOKBACK_D * 24
    # SCORE = Δlog(TxCnt,14d) − Δlog(precio,14d). Long alto = actividad crece más que el precio.
    score_daily = (ltx.diff(TX_LOOKBACK_D) - logp.diff(TX_LOOKBACK_D)).shift(TX_SHIFT_D)   # lag point-in-time
    score = score_daily.reindex(C.index, method="ffill").reindex(columns=C.columns)        # diario → horario
    _, w_now = xs_sleeve(C, ret, beta, score, h)
    return w_now, score.iloc[-1], C.index[-1]


def run_tx_shadow(db=None) -> dict:
    """Calcula y REGISTRA (sin operar) los pesos del candidato tx_pxdiv_14d de este ciclo. Aislado."""
    from kepler.db import DB
    db = db or DB()
    update_cm_addresses()
    try:
        w, score, asof = tx_shadow_weights()
    except Exception as e:
        db.audit("WARNING", "shadow_tx", f"Sombra tx omitida: {str(e)[:80]}")
        return {"logged": 0}
    if w is None:
        db.audit("WARNING", "shadow_tx", "Sin datos tx — sombra omitida")
        return {"logged": 0}
    n = 0
    for sym, wt in w.items():
        if abs(float(wt)) <= 1e-6:
            continue
        sc = float(score.get(sym, float("nan"))) if score is not None else None
        db.log_shadow(sleeve=TX_SLEEVE, symbol=sym, weight=round(float(wt), 4),
                      score=(None if sc is None or np.isnan(sc) else round(sc, 6)),
                      detail={"asof": str(asof), "lookback_d": TX_LOOKBACK_D})
        n += 1
    db.audit("INFO", "shadow_tx", f"Sombra tx_pxdiv registrada ({n} posiciones)",
             detail={"sleeve": TX_SLEEVE, "asof": str(asof)})
    return {"logged": n, "asof": str(asof)}


# ─── SOMBRA on-chain MVRV (Coin Metrics) — 2º candidato a sleeve #8, de VALOR (≠ tx que es ACTIVIDAD) ──
# mvrv_lvl = short high MVRV (market cap / realized cap = precio vs coste base on-chain). Validado e65/e66:
# ortogonal a los 7 sleeves (corr 0.28 mom) Y a tx_pxdiv (corr +0.02), IS/OOS 0.69/0.80, turnover 6x/año →
# inmune al taker (Δ +1.41%/mes), LOO robusto (no 1-coin). Factor de VALOR fundamental. point-in-time
# limpio (realized cap = historia on-chain inmutable). 11 coins. En SOMBRA: validar forward.
MVRV_SLEEVE = "onchain_mvrv_lvl"
MVRV_HOLD_D = 30
FUND_CACHE = os.path.join(config.DATA_DIR, "onchain_cm_fund"); os.makedirs(FUND_CACHE, exist_ok=True)
# 14 coins con CapMVRVCur community-free (los stale se filtran en _daily_mvrv por fecha). CM id → ticker.
FUND2TKR = {"aave": "AAVEUSDT", "ada": "ADAUSDT", "bch": "BCHUSDT", "bnb": "BNBUSDT", "btc": "BTCUSDT",
            "doge": "DOGEUSDT", "dot": "DOTUSDT", "etc": "ETCUSDT", "eth": "ETHUSDT", "link": "LINKUSDT",
            "ltc": "LTCUSDT", "uni": "UNIUSDT", "xrp": "XRPUSDT", "zec": "ZECUSDT"}


def update_cm_fundamentals() -> int:
    """Refresca CapMVRVCur diario (Coin Metrics Community, sin key) → parquet por coin. Overwrite."""
    ok = 0
    for cm in FUND2TKR:
        try:
            rows = []; url = f"{CM_BASE}/timeseries/asset-metrics"
            params = {"assets": cm, "metrics": "CapMVRVCur", "frequency": "1d",
                      "start_time": "2016-01-01", "page_size": 10000}
            for _ in range(30):
                r = requests.get(url, params=params, timeout=60)
                if r.status_code != 200:
                    break
                j = r.json(); rows += j.get("data", [])
                if not j.get("next_page_url"):
                    break
                url = j["next_page_url"]; params = None
            if not rows:
                continue
            df = pd.DataFrame(rows); df["time"] = pd.to_datetime(df["time"])
            df["CapMVRVCur"] = pd.to_numeric(df.get("CapMVRVCur"), errors="coerce")
            df[["time", "CapMVRVCur"]].dropna().sort_values("time").to_parquet(os.path.join(FUND_CACHE, f"{cm}.parquet"))
            ok += 1
        except Exception:
            continue
    return ok


def _daily_mvrv(symbols):
    """Panel diario de log(MVRV) para los coins cubiertos y FRESCOS (descarta stale: última fecha >20d)."""
    cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=20)
    cols = {}
    for cm, tkr in FUND2TKR.items():
        if tkr not in symbols:
            continue
        p = os.path.join(FUND_CACHE, f"{cm}.parquet")
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p).set_index("time")
        d.index = pd.to_datetime(d.index, utc=True).normalize()
        s = d["CapMVRVCur"].dropna() if "CapMVRVCur" in d else pd.Series(dtype=float)
        if s.empty or s.index.max() < cutoff:           # descartar stale (bnb 2019, dot 2022)
            continue
        cols[tkr] = np.log(s.replace(0, np.nan))
    df = pd.DataFrame(cols)
    if df.empty:
        return df
    return df[~df.index.duplicated()].sort_index()


def mvrv_shadow_weights():
    """Pesos ACTUALES que el sleeve mvrv_lvl tendría (β-neutral). NO opera."""
    from kepler.engine import load, _beta, xs_sleeve
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    lmv = _daily_mvrv(list(C.columns))
    if lmv.empty:
        return None, None, C.index[-1]
    # SCORE = −log(MVRV) (short high MVRV = sobrevalorado; long bajo = infravalorado), lag point-in-time.
    score_daily = (-lmv).shift(TX_SHIFT_D)
    score = score_daily.reindex(C.index, method="ffill").reindex(columns=C.columns)
    _, w_now = xs_sleeve(C, ret, beta, score, MVRV_HOLD_D * 24)
    return w_now, score.iloc[-1], C.index[-1]


def run_mvrv_shadow(db=None) -> dict:
    """Calcula y REGISTRA (sin operar) los pesos del candidato mvrv_lvl de este ciclo. Aislado."""
    from kepler.db import DB
    db = db or DB()
    update_cm_fundamentals()
    try:
        w, score, asof = mvrv_shadow_weights()
    except Exception as e:
        db.audit("WARNING", "shadow_mvrv", f"Sombra mvrv omitida: {str(e)[:80]}")
        return {"logged": 0}
    if w is None:
        db.audit("WARNING", "shadow_mvrv", "Sin datos mvrv — sombra omitida")
        return {"logged": 0}
    n = 0
    for sym, wt in w.items():
        if abs(float(wt)) <= 1e-6:
            continue
        sc = float(score.get(sym, float("nan"))) if score is not None else None
        db.log_shadow(sleeve=MVRV_SLEEVE, symbol=sym, weight=round(float(wt), 4),
                      score=(None if sc is None or np.isnan(sc) else round(sc, 6)),
                      detail={"asof": str(asof), "hold_d": MVRV_HOLD_D})
        n += 1
    db.audit("INFO", "shadow_mvrv", f"Sombra mvrv_lvl registrada ({n} posiciones)",
             detail={"sleeve": MVRV_SLEEVE, "asof": str(asof)})
    return {"logged": n, "asof": str(asof)}


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    r = run_shadow()
    print(f"Sombra on-chain TVL registrada: {r}")
    rb = run_blend_shadow()
    print(f"Sombra BLEND registrada: {rb}")
    rt = run_tx_shadow()
    print(f"Sombra tx_pxdiv registrada: {rt}")
    rm = run_mvrv_shadow()
    print(f"Sombra mvrv_lvl registrada: {rm}")
