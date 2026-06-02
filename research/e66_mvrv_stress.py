"""
E66 — estrés de `mvrv_lvl` (e65): short high MVRV = long infravalorado / short sobrevalorado (valor on-chain).
Pasó el filtro (corr 0.28, IS/OOS 0.69/0.80, Δ +1.41, vivo 2022+). Es señal LENTA (level, 30d) → debería
sobrevivir taker; el riesgo es LOO (11 coins, ¿ZEC otra vez?). (2026-06-02). No toca prod.
python -m research.e66_mvrv_stress
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
from research.e65_mvrv_factor import load_fund, to_hourly

HC = config.LEVERAGE_HAIRCUT; MAKER = config.MAKER_FEE


def slip_adv(adv_M, cols, m=1.0):
    return (50.0/np.sqrt(adv_M)*m).clip(0.5, 30.0).div(1e4).reindex(cols).fillna(0.5/1e4)
def cand_net(C, ret, beta, score, hold, slip):
    ts, pg, turn = bt_xs(C, ret, beta, score, hold)
    cost = (turn*slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
    return compound_daily(ts, pg-cost), turn.values.sum()/((C.index[-1]-C.index[0]).days/365.25)
def ames(series):
    df = pd.concat(series, axis=1).dropna(); port = (df*vol_parity_weights(df)).sum(axis=1)
    lev = min(HC*leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return metrics(port*lev)["ann"]/12


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E66 — estrés mvrv_lvl: ¿sobrevive TAKER? ¿LOO?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C); cols = list(C.columns)
    Pd = C.resample("1D").last(); Pd.index = pd.to_datetime(Pd.index, utc=True).normalize()
    MV, _ = load_fund(Pd.index, cols)
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
    mes7 = ames(base); print(f"BASELINE 7 (maker): {mes7:.2f}%/mes\n")

    lmv = np.log(MV.replace(0, np.nan))
    mv_coins = [c for c in MV.columns if MV[c].notna().sum() > 300 and c != DRIVER]
    def score_of(drop=None):
        sd = -lmv
        if drop and drop in sd.columns: sd = sd.drop(columns=[drop])
        return to_hourly(sd, C)

    s_mk, turn = cand_net(C, ret, beta, score_of(), 720, maker)
    s_tk, _ = cand_net(C, ret, beta, score_of(), 720, taker)
    print(f"mvrv_lvl: turnover {turn:.0f}x/año · standalone Sharpe maker {metrics(s_mk)['sharpe']:.2f} / "
          f"taker {metrics(s_tk)['sharpe']:.2f} · %/mes solo taker {metrics(s_tk)['ann']/12:.2f}")
    d_mk = ames({**base, "mvrv": s_mk}) - mes7; d_tk = ames({**base, "mvrv": s_tk}) - mes7
    print(f"Δ%/mes combinado: maker {d_mk:+.2f} → TAKER {d_tk:+.2f}  ⇒ {'SOBREVIVE taker' if d_tk>0.03 else 'MUERE a taker'}\n")
    loo = {}
    for coin in mv_coins:
        s_d, _ = cand_net(C, ret, beta, score_of(drop=coin), 720, taker)
        loo[coin] = ames({**base, "mvrv": s_d}) - mes7
    loo_s = pd.Series(loo).sort_values()
    print(f"LOO (Δ%/mes taker quitando cada coin): rango {loo_s.min():+.2f} (sin {loo_s.index[0]}) … "
          f"{loo_s.max():+.2f} (sin {loo_s.index[-1]}) · mediana {loo_s.median():+.2f}")
    dep = "DEPENDE de 1 coin (frágil)" if d_tk > 0 and (d_tk-loo_s.min()) > 0.5*abs(d_tk) else "REPARTIDO (robusto)"
    print(f"  ⇒ {dep}")
    print(f"\nVEREDICTO: si Δ taker>0 Y LOO robusto → mvrv_lvl a SOMBRA (2º candidato on-chain, de VALOR,")
    print("complementa a tx_pxdiv que es de ACTIVIDAD). Si depende de 1 coin → archivar.")


if __name__ == "__main__":
    main()
