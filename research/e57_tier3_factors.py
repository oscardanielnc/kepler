"""
E57 — QUICK WINS Tier 3: factores nuevos sobre data que YA tenemos (barrido de recetas, 2026-06-02).
El "factor zoo" cripto (ScienceDirect S1057521926000645) lista entre sus top factores dos que NO tenemos:
**turnover-volatility** y métricas on-chain. Aquí testeo los que se computan con NUESTRA data, por el
harness brutal (corr<0.35 con los 7 sleeves + IS/OOS>0.10 + sube el retorno al ancla maxDD −10%):
  1. turnover-volatility   = vol del log(quote_volume) → ¿iliquidez/incertidumbre cross-seccional?
  2. low-price (nominal)    = −log(precio) → anomalía de precio nominal bajo (¿o proxy de size/lotería?)
  3. residual-momentum      = momentum del retorno IDIOSINCRÁTICO (ret − βᵢ·retBTC) → ¿≠ momentum crudo?
Ambos signos. Es TRIAJE barato: lo que pase, va al estrés taker (e53-style) después. No toca producción.
python -m research.e57_tier3_factors
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

HC = config.LEVERAGE_HAIRCUT


def combine(series: dict):
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    port = (df * vp).sum(axis=1)
    lev = min(HC * leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    m = metrics(port * lev)
    return port, m, lev


def half(s):
    h = len(s) // 2
    return metrics(s.iloc[:h]).get("sharpe", float("nan")), metrics(s.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E57 — quick wins Tier 3 (factores sobre data propia, harness brutal)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)

    # ── 7 sleeves base ─────────────────────────────────────────────────────────
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    port7, m7, lev7 = combine(base)
    df7 = pd.concat(base, axis=1).dropna()
    print(f"BASELINE 7 sleeves: Sharpe {m7['sharpe']:.2f} · {m7['ann']/12:.2f}%/mes @ lev {lev7:.2f}x · maxDD {m7['maxdd']:.1f}%\n")

    # ── scores candidatos ──────────────────────────────────────────────────────
    QV = P["quote_volume"].replace(0, np.nan)
    sc_tv = -np.log(QV).rolling(336).std()                       # turnover-vol 14d (signo + = short alta vol)
    sc_lp = -np.log(C)                                            # low-price nominal
    resid = ret.sub(beta.mul(ret[DRIVER], axis=0))               # retorno idiosincrático (ret − β·retBTC)
    sc_rm = resid.rolling(720).sum()                             # residual-momentum 30d

    cands = [
        ("turnover_vol_14d (+)", sc_tv, 336),
        ("turnover_vol_14d (−)", -sc_tv, 336),
        ("low_price (+)", sc_lp, 720),
        ("low_price (−)", -sc_lp, 720),
        ("resid_mom_30d (+)", sc_rm, 720),
        ("resid_mom_30d (−)", -sc_rm, 720),
    ]

    print(f"{'candidato':22s} {'Sh solo':>8s} {'corr_max':>9s} {'(con)':>12s} {'IS/OOS':>11s} │ "
          f"{'ΔSharpe':>8s} {'Δ%/mes':>7s}  admisión")
    print("─" * 100)
    for name, score, hold in cands:
        s_c, _ = xs_sleeve(C, ret, beta, score, hold)
        s_c = s_c.reindex(df7.index).dropna()
        if len(s_c) < 100:
            print(f"{name:22s}  (datos insuficientes)"); continue
        msolo = metrics(s_c)["sharpe"]
        corrs = {k: df7[k].corr(s_c) for k in df7.columns}
        kmax = max(corrs, key=lambda k: abs(corrs[k])); cmax = corrs[kmax]
        is_, oos_ = half(s_c)
        # 8 sleeves
        b8 = dict(base); b8[name] = s_c
        port8, m8, lev8 = combine(b8)
        dsh = m8["sharpe"] - m7["sharpe"]; dmes = (m8["ann"] - m7["ann"]) / 12
        ok = (abs(cmax) < 0.35 and is_ > 0.10 and oos_ > 0.10 and dmes > 0.03)
        flag = "  ✅ PASA→estrés taker" if ok else ("  ~marginal" if dmes > 0 else "  ✗")
        print(f"{name:22s} {msolo:8.2f} {cmax:9.2f} {kmax:>12s} {is_:5.2f}/{oos_:<5.2f} │ "
              f"{dsh:+8.2f} {dmes:+7.2f}{flag}")

    print("\nLECTURA: admisión = corr<0.35 + IS y OOS >0.10 + Δ%/mes>0.03 al ancla. Lo que pase NO es prod aún")
    print("→ estrés taker (slip ADV, e53-style) + walk-forward purgado. El signo correcto es el que pase limpio.")
    print("Recordatorio honesto (factor zoo): se espera que casi todo sea redundante; basta 1 ortogonal real.")


if __name__ == "__main__":
    main()
