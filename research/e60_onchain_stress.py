"""
E60 — TIER 1 ON-CHAIN: estrés de los candidatos que pasaron e59 (tx_pxdiv_14d, addr_mom_30d).
El Δ al ancla con coste MAKER puede ser ilusión (el coste recorta colas → el ancla sube leverage, patrón
e28/e48). Tests que mandan: (1) ¿el Δ sobrevive con coste TAKER realista (slip ADV)? (2) LOO por coin —
¿el edge depende de 1 nombre (precedente ZEC en liquidaciones)? Cross-section delgado (12).
No toca producción. python -m research.e60_onchain_stress
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
from research.e59_onchain_factor import load_onchain, to_hourly_score, CM2TKR, SHIFT

HC = config.LEVERAGE_HAIRCUT
MAKER = config.MAKER_FEE


def slip_adv(adv_M, cols, mult=1.0):
    return (50.0 / np.sqrt(adv_M) * mult).clip(0.5, 30.0).div(1e4).reindex(cols).fillna(0.5/1e4)


def cand_net(C, ret, beta, score, hold, slip):
    """Serie diaria NETA del candidato (bt_xs) con vector de coste `slip` por símbolo."""
    ts, pg, turn = bt_xs(C, ret, beta, score, hold)
    cost = (turn * slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
    return compound_daily(ts, pg - cost)


def anchored_mes(series: dict):
    df = pd.concat(series, axis=1).dropna()
    port = (df * vol_parity_weights(df)).sum(axis=1)
    lev = min(HC * leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return metrics(port * lev)["ann"] / 12


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E60 — estrés on-chain: ¿sobrevive TAKER? ¿depende de 1 coin (LOO)?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    Pd = C.resample("1D").last()
    ADR, TX = load_onchain(Pd.index, list(C.columns))
    cols = list(C.columns)
    adv_M = (adv_usd(P["quote_volume"]).reindex(cols).fillna(0.0) / 1e6).clip(lower=1.0)
    maker = pd.Series(MAKER, index=cols)
    taker = maker + slip_adv(adv_M, cols, 1.0)

    # 7 base (maker, como producción)
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

    logadr = np.log(ADR.replace(0, np.nan)); logtx = np.log(TX.replace(0, np.nan)); logp = np.log(Pd[ADR.columns])
    def score_of(kind, N, drop=None):
        A = ADR if kind.startswith("addr") else TX
        la = np.log(A.replace(0, np.nan))
        sd = la.diff(N) - logp.diff(N) if "pxdiv" in kind else la.diff(N)
        if drop and drop in sd.columns:
            sd = sd.drop(columns=[drop])
        return to_hourly_score(sd, C)

    cands = [("tx_pxdiv_14d", "tx_pxdiv", 14, 14*24), ("addr_mom_30d", "addr_mom", 30, 30*24)]
    onchain_coins = [c for c in ADR.columns if c != DRIVER and ADR[c].notna().sum() > 300]

    for name, kind, N, hold in cands:
        print(f"── {name} ──")
        sc = score_of(kind, N)
        s_mk = cand_net(C, ret, beta, sc, hold, maker)
        s_tk = cand_net(C, ret, beta, sc, hold, taker)
        print(f"  standalone: Sharpe maker {metrics(s_mk)['sharpe']:.2f} / taker {metrics(s_tk)['sharpe']:.2f} · "
              f"%/mes solo taker {metrics(s_tk)['ann']/12:.2f}")
        d_mk = anchored_mes({**base, name: s_mk}) - mes7
        d_tk = anchored_mes({**base, name: s_tk}) - mes7
        verdict = "SOBREVIVE taker" if d_tk > 0.03 else "MUERE a taker (era ilusión del ancla)"
        print(f"  Δ%/mes combinado: maker {d_mk:+.2f} → TAKER {d_tk:+.2f}  ⇒ {verdict}")
        # LOO por coin (con taker): quitar cada coin del cross-section
        print(f"  LOO (Δ%/mes combinado taker quitando cada coin):")
        loo = {}
        for coin in onchain_coins:
            sc_d = score_of(kind, N, drop=coin)
            s_d = cand_net(C, ret, beta, sc_d, hold, taker)
            loo[coin] = anchored_mes({**base, name: s_d}) - mes7
        loo_s = pd.Series(loo).sort_values()
        worst = loo_s.index[-1]   # quitarla SUBE más el Δ = era la que más estorbaba; el de abajo = la imprescindible
        best = loo_s.index[0]
        print(f"    rango Δ: {loo_s.min():+.2f} (sin {best}) … {loo_s.max():+.2f} (sin {worst}) · "
              f"mediana {loo_s.median():+.2f}")
        dep = "DEPENDE de 1 coin (frágil)" if (d_tk - loo_s.min()) > 0.5 * abs(d_tk) and d_tk > 0 else "repartido (robusto)"
        print(f"    quitar la más crítica ({best}) lleva el Δ a {loo_s.min():+.2f} ⇒ {dep}\n")

    print("LECTURA: admisión final = Δ taker > 0 Y no depender de 1 coin. Si pasa → blend #8 (con lotería+")
    print("TVL+iliquidez) en SOMBRA. Si muere a taker o depende de 1 coin → archivar (como liquidaciones/ZEC).")


if __name__ == "__main__":
    main()
