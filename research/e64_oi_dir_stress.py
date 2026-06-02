"""
E64 — estrés del único superviviente de e63: `oi_dir_7d(+)` = Δlog(OI,7d)·signo(ret_7d) (OI confirmando
momentum: posiciones construyen en la dirección del precio). Pasó el filtro inicial (corr −0.18, IS/OOS
0.98/1.20, Δ +0.75) PERO es señal RÁPIDA (7d) → el test que manda es TAKER (las rápidas mueren ahí, e45/
order-book) + LOO. (2026-06-02). No toca prod. python -m research.e64_oi_dir_stress
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import bt_xs, adv_usd, compound_daily
from research.e63_coinalyze_factors import load_cz, to_hourly

HC = config.LEVERAGE_HAIRCUT; MAKER = config.MAKER_FEE


def slip_adv(adv_M, cols, mult=1.0):
    return (50.0/np.sqrt(adv_M)*mult).clip(0.5, 30.0).div(1e4).reindex(cols).fillna(0.5/1e4)


def cand_net(C, ret, beta, score, hold, slip):
    ts, pg, turn = bt_xs(C, ret, beta, score, hold)
    cost = (turn * slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
    return compound_daily(ts, pg - cost), turn.values.sum() / ((C.index[-1]-C.index[0]).days/365.25)


def anchored_mes(series):
    df = pd.concat(series, axis=1).dropna(); port = (df*vol_parity_weights(df)).sum(axis=1)
    lev = min(HC*leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return metrics(port*lev)["ann"]/12


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E64 — estrés oi_dir_7d(+): ¿sobrevive TAKER? ¿LOO? ¿turnover?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C); cols = list(C.columns)
    Pd = C.resample("1D").last(); Pd.index = pd.to_datetime(Pd.index, utc=True).normalize()
    _, OI = load_cz(Pd.index, cols)
    adv_M = (adv_usd(P["quote_volume"]).reindex(cols).fillna(0.0)/1e6).clip(lower=1.0)
    maker = pd.Series(MAKER, index=cols); taker = maker + slip_adv(adv_M, cols, 1.0)

    base = {}
    base["mom_30d"], _ = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _ = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _ = carry_sleeve(C, ret, beta)
    base["trend"], _ = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    mes7 = anchored_mes(base)
    print(f"BASELINE 7 (maker): {mes7:.2f}%/mes\n")

    logoi = np.log(OI.replace(0, np.nan)); logp = np.log(Pd[OI.columns])
    oi_coins = [c for c in OI.columns if OI[c].notna().sum() > 300 and c != DRIVER]

    def score_of(N=7, drop=None):
        sd = logoi.diff(N) * np.sign(logp.diff(N))
        if drop and drop in sd.columns:
            sd = sd.drop(columns=[drop])
        return to_hourly(sd, C)

    sc = score_of()
    s_mk, turn = cand_net(C, ret, beta, sc, 168, maker)
    s_tk, _ = cand_net(C, ret, beta, sc, 168, taker)
    print(f"oi_dir_7d(+): turnover {turn:.0f}x/año · standalone Sharpe maker {metrics(s_mk)['sharpe']:.2f} / "
          f"taker {metrics(s_tk)['sharpe']:.2f} · %/mes solo taker {metrics(s_tk)['ann']/12:.2f}")
    d_mk = anchored_mes({**base, "oi_dir": s_mk}) - mes7
    d_tk = anchored_mes({**base, "oi_dir": s_tk}) - mes7
    verdict = "SOBREVIVE taker" if d_tk > 0.03 else "MUERE a taker"
    print(f"Δ%/mes combinado: maker {d_mk:+.2f} → TAKER {d_tk:+.2f}  ⇒ {verdict}\n")
    print("LOO (Δ%/mes combinado taker quitando cada coin):")
    loo = {}
    for coin in oi_coins:
        s_d, _ = cand_net(C, ret, beta, score_of(drop=coin), 168, taker)
        loo[coin] = anchored_mes({**base, "oi_dir": s_d}) - mes7
    loo_s = pd.Series(loo).sort_values()
    print(f"  rango Δ: {loo_s.min():+.2f} (sin {loo_s.index[0]}) … {loo_s.max():+.2f} (sin {loo_s.index[-1]}) · "
          f"mediana {loo_s.median():+.2f}")
    dep = "DEPENDE de 1 coin (frágil)" if d_tk > 0 and (d_tk - loo_s.min()) > 0.5*abs(d_tk) else "repartido"
    print(f"  ⇒ {dep}")
    print("\nVEREDICTO: admisión = Δ taker > 0 Y LOO robusto. Si pasa → sombra. Si muere a taker/1-coin →")
    print("Coinalyze Tier 2 cierra NEGATIVO (predicted-funding sin edge; OI redundante/frágil salvo este).")


if __name__ == "__main__":
    main()
