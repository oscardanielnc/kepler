"""
E48 — ESTRÉS del candidato liquidaciones diarias (e47 dio liq_imb_3d: +1.05%/mes, corr 0.11, OOS 1.21).
Antes de cantar sleeve #8, tres make-or-break (lecciones e16d/e17/e24/e45):
  Q1 COSTE TAKER — el que mató al order-book intradía (e45). ¿sobrevive a taker (+ADV)?
  Q2 CONCENTRACIÓN — e47 LOO: sin ZEC el aporte cae 1.05→0.11. ¿es solo ZEC? winsorize + cap peso +
     drop de los más finos. Un edge real debe repartirse (lección e17/AXS).
  Q3 HORIZONTE — ¿plateau o pico? 3d era el mejor; 1d negativo. Mapear holds/smoothing.

python -m research.e48_liquidations_stress
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel,
                           _weights_from_score, DRIVER, BETA_W)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import adv_usd
from research.e47_liquidations_check import load_liq_daily, to_hourly

MAKER, TAKER = config.MAKER_FEE, config.TAKER_FEE


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    return metrics(combo * L).get("ann", float("nan"))


def sleeve_fee(C, ret, beta, score_df, hold, fee_vec):
    """Réplica de xs_sleeve pero cobrando `fee_vec` (Series por símbolo, fracción one-way) en el turnover.
    Devuelve la serie diaria neta."""
    syms = [s for s in C.columns if s != DRIVER]
    R = ret[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold)); fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    fb = float(fee_vec.get(DRIVER, fee_vec.reindex(syms).median()))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0; rets = []; ts = []
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        port = float((w * fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h * float(fwd_d.iloc[t] or 0)
        cost = float((w - prev).abs().mul(fee_vec.reindex(syms).fillna(fb)).sum()) + abs(h - ph) * fb
        rets.append(port - cost); ts.append(C.index[t]); prev, ph = w, h
    s = pd.Series(rets, index=ts)
    return (1 + s).cumprod().resample("1D").last().ffill().pct_change().dropna()


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E48 — ESTRÉS liquidaciones diarias (taker · concentración · horizonte)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["quote_volume", "volume", "taker_buy_volume"], C)
    cols = list(C.columns); dvol = P["quote_volume"]
    Ld, Sd = load_liq_daily(cols)

    # vectores de coste por símbolo
    adv_M = (adv_usd(dvol).reindex(cols).fillna(0.0)/1e6).clip(lower=1.0)
    slip = (50.0/np.sqrt(adv_M)).clip(0.5, 30.0)/1e4
    fee_maker = pd.Series(MAKER, index=cols)
    fee_taker = pd.Series(TAKER, index=cols)
    fee_takeradv = TAKER + slip

    # baseline 7
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    bdf = pd.concat(base, axis=1); bdf.columns = list(base); bdf = bdf.dropna()
    ann0 = anchored((bdf * vol_parity_weights(bdf)).sum(axis=1))

    def add_delta(score_hourly, hold, sign, fee):
        s = sleeve_fee(C, ret, beta, score_hourly, hold, fee) * sign
        j = pd.concat({**base, "x": s}, axis=1); j.columns = list(base) + ["x"]; j = j.dropna()
        return (anchored((j * vol_parity_weights(j)).sum(axis=1)) - ann0) / 12, j["x"]

    imb_raw = (Ld - Sd) / (Ld + Sd).replace(0, np.nan)
    SIGN = -1.0   # auto-orientado en e47 (momentum: net long-liq → seguir corto)

    # Q3 HORIZONTE: smoothing × hold (maker, para mapear el edge bruto)
    print("Q3 HORIZONTE — Δ%/mes anclado (maker) por smoothing×hold:")
    print(f"  {'smooth':>7s} " + " ".join(f"h{h:>3d}" for h in (24,48,72,120)))
    for N in (1, 2, 3, 5, 7):
        imbN = imb_raw.rolling(N, min_periods=1).mean()
        row = []
        for h in (24, 48, 72, 120):
            d, _ = add_delta(to_hourly(imbN, C), h, SIGN, fee_maker); row.append(d)
        print(f"  {N:>5d}d  " + " ".join(f"{x:+5.2f}" for x in row))

    # Q1 COSTE: liq_imb_3d/h24 a maker / taker / taker+ADV
    print("\nQ1 COSTE — liq_imb_3d (h24) al ancla:")
    imb3 = to_hourly(imb_raw.rolling(3, min_periods=1).mean(), C)
    for label, fee in (("maker", fee_maker), ("taker", fee_taker), ("taker+ADV", fee_takeradv)):
        d, sx = add_delta(imb3, 24, SIGN, fee)
        print(f"    {label:10s} Δ {d:+.2f}%/mes · sleeve Sharpe {sh(sx):.2f}")

    # Q2 CONCENTRACIÓN: winsorize señal, cap peso, drop ZEC, drop 3 más finos (por ADV)
    print("\nQ2 CONCENTRACIÓN — Δ%/mes (taker+ADV, el coste real) bajo robustez:")
    thin = adv_M.reindex([c for c in cols if c != DRIVER]).nsmallest(3).index.tolist()
    variants = {
        "base (todos)":        imb_raw,
        "winsor ±0.8":         imb_raw.clip(-0.8, 0.8),
        "sin ZEC":             imb_raw.drop(columns=[c for c in ["ZECUSDT"] if c in imb_raw], errors="ignore"),
        f"sin 3 finos":        imb_raw.drop(columns=[c for c in thin if c in imb_raw], errors="ignore"),
    }
    for label, imbv in variants.items():
        sc = to_hourly(imbv.rolling(3, min_periods=1).mean(), C)
        d, sx = add_delta(sc, 24, SIGN, fee_takeradv)
        print(f"    {label:16s} Δ {d:+.2f}%/mes · Sharpe {sh(sx):.2f}  (finos={thin})" if label.startswith("sin 3") else
              f"    {label:16s} Δ {d:+.2f}%/mes · Sharpe {sh(sx):.2f}")

    print("\nLECTURA: si Δ taker+ADV sigue >+0.3%/mes Y la concentración no lo mata (sin ZEC / winsor "
          "aguanta) Y hay plateau (no solo h24/3d) → candidato sólido → walk-forward purgado (B1). Si el "
          "coste o ZEC lo tumban → liquidaciones diarias NO entran (rebote es intradía) → CME gap (#2).")


if __name__ == "__main__":
    main()
