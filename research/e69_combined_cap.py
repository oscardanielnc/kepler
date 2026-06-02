"""
E69 — CAP de concentración sobre el PESO COMBINADO (no solo por-sleeve). (2026-06-02)
Diagnóstico del incidente: el cap 0.25 de e52 controla SOLO el sleeve `trend`, pero carry+lowvol también
cargan TRX → el peso COMBINADO de TRX quedó en 23% del libro vivo. El cap por-sleeve no controla la
concentración agregada.

PREGUNTA (regla de oro): ¿un cap sobre el peso combinado |Σ vp·w| baja la concentración (top%/HHI) sin
degradar Sharpe/maxDD/%/mes del sistema?

MÉTODO: marcado DIARIO (validado en e56 ≈ engine). vp = vol-parity de las series de retorno de los 7
sleeves (idéntico al engine). Los pesos combinados por-día = Σ vp·w_sleeve(día); se capa |w|≤cap
(pre-leverage), se re-calcula el hedge BTC para β≈0, y se ancla el leverage con la regla ROBUSTA (e68).
Baseline (cap=None) y capado usan EL MISMO marco → comparación válida.

No toca producción. python -m research.e69_combined_cap
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel,
                           _weights_from_score, _cap_normalize, DRIVER, CARRY_SMOOTH, BETA_W)
from kepler.portfolio import vol_parity_weights, metrics, leverage_robust

HC, MWN = config.LEVERAGE_HAIRCUT, config.MAX_WEIGHT_NORMAL
TMD, CAP, TVA = config.TARGET_MAXDD, config.MAX_STRAT_LEVERAGE, config.TARGET_VOL_ANCHOR


def daily_xs_weights(score, beta_d, syms, days, hold_days):
    """Pesos diarios (alts) de un sleeve XS respetando el HOLD: recalcula cada `hold_days` y mantiene
    (ffill) el resto — reproduce el libro vivo (pesos persistentes), no el ruido del recálculo diario."""
    sc = score.resample("1D").last().reindex(days)
    W = pd.DataFrame(np.nan, index=days, columns=syms)
    for i in range(0, len(days), max(1, hold_days)):
        d = days[i]
        if sc.loc[d].isna().all():
            continue
        w, _ = _weights_from_score(sc.loc[d], beta_d.loc[d], syms, cap=MWN)
        W.loc[d] = w.reindex(syms).fillna(0.0)
    return W.ffill().fillna(0.0)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E69 — cap sobre el peso COMBINADO (¿baja concentración sin coste? regla de oro)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    syms = [s for s in C.columns if s != DRIVER]
    P = load_panel(["volume", "taker_buy_volume"], C)

    # --- 1) series de retorno de los 7 sleeves → vp (idéntico al engine) ---
    series, weights_now = {}, {}
    series["mom_30d"], weights_now["mom_30d"] = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    series["rev_60d"], weights_now["rev_60d"] = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    series["lowvol_14d"], weights_now["lowvol_14d"] = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    series["carry"], weights_now["carry"] = carry_sleeve(C, ret, beta)
    series["takerflow_5d"], weights_now["takerflow_5d"] = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    series["hlpos_14d"], weights_now["hlpos_14d"] = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    series["trend"], weights_now["trend"] = trend_sleeve(C)
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    days = df.index

    # --- 2) pesos diarios por sleeve (alts) ---
    beta_d = beta.resample("1D").last().reindex(days).ffill()
    SW = {}
    SW["mom_30d"]    = daily_xs_weights(alphas.xs_momentum_score(ret, 720), beta_d, syms, days, 30)
    SW["rev_60d"]    = daily_xs_weights(alphas.xs_reversal_score(ret, 1440), beta_d, syms, days, 60)
    SW["lowvol_14d"] = daily_xs_weights(alphas.xs_lowvol_score(ret, 336), beta_d, syms, days, 14)
    SW["takerflow_5d"] = daily_xs_weights(alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), beta_d, syms, days, 5)
    SW["hlpos_14d"]  = daily_xs_weights(alphas.xs_hlposition_score(C, 336), beta_d, syms, days, 14)
    # carry diario (funding suavizado)
    fd = {}
    for p_ in __import__("glob").glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p_)[:-8]
        if s not in C.columns: continue
        f = pd.read_parquet(p_).set_index("funding_time")["funding_rate"]; f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    Fs = F.rolling(CARRY_SMOOTH, min_periods=1).mean().resample("1D").last().reindex(days).ffill()
    CW = pd.DataFrame(np.nan, index=days, columns=syms)
    for i in range(0, len(days), 2):                              # carry rebalancea cada 48h (hold 2d)
        d = days[i]
        w, _ = alphas.carry_weights(Fs.loc[d].reindex(syms), beta_d.loc[d].reindex(syms), MWN)
        CW.loc[d] = w.reindex(syms).fillna(0.0)
    SW["carry"] = CW.ffill().fillna(0.0)
    # trend diario (cap 0.25 = engine.trend_sleeve)
    px = C.resample("1D").last().reindex(days); rD = px.pct_change()
    ef, es = px.ewm(span=20).mean(), px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0); vol = rD.rolling(30).std()
    pos = (sig.shift(1) * (0.20/np.sqrt(365)/vol).clip(0, 3)).fillna(0)
    TW = pd.DataFrame(0.0, index=days, columns=syms)
    for d in days:
        v = pos.loc[d].reindex(syms).fillna(0.0).values.astype(float)
        TW.loc[d] = _cap_normalize(v, MWN) if v.sum() > 0 else v
    SW["trend"] = TW

    # --- 3) combinado + cap + hedge + retorno diario ---
    comb = sum(float(vp[k]) * SW[k] for k in SW)                  # alts, pre-leverage
    fwd = rD.shift(-1)                                            # retorno del día siguiente
    fwd_btc = C[DRIVER].resample("1D").last().reindex(days).pct_change().shift(-1)
    beta_alts = beta_d[syms]

    def evaluate(cap, label):
        W = comb.clip(-cap, cap) if cap else comb.copy()
        hedge = -(W * beta_alts).sum(axis=1)                      # β≈0: hedge recalculado tras el cap
        turn = (W.diff().abs().sum(axis=1) + hedge.diff().abs()).fillna(0.0)
        port = (W * fwd[syms]).sum(axis=1) + hedge * fwd_btc - turn * config.MAKER_FEE
        port = port.dropna()
        lev = leverage_robust(port, TMD, HC, CAP, TVA)
        m = metrics(port * lev)
        # libro vivo: target combinado (último día con datos) escalado a leverage
        wlast = W.iloc[-1].copy();
        tgt = (wlast.abs() * lev)
        top = tgt.sort_values(ascending=False); topsym, topval = top.index[0], top.iloc[0]
        gross = float(wlast.abs().sum() * lev) + abs(float(hedge.iloc[-1]) * lev)
        hhi = float(((wlast.abs() / wlast.abs().sum()) ** 2).sum())
        h = len(port)//2
        sh1, sh2 = metrics(port.iloc[:h]).get("sharpe", float("nan")), metrics(port.iloc[h:]).get("sharpe", float("nan"))
        print(f"{label:16s} │ Sh {m['sharpe']:.2f} (IS {sh1:.2f}/OOS {sh2:.2f}) · maxDD {m['maxdd']:5.1f}% · "
              f"{m['ann']/12:4.2f}%/mes · lev {lev:.2f}x │ top {topsym.replace('USDT',''):4s} {topval*100:4.1f}% · HHI {hhi:.3f}")
        return m

    print(f"{'variante':16s} │ {'sistema combinado (marcado diario, ancla robusta)':>52s} │ concentración")
    print("─" * 116)
    evaluate(None, "SIN cap comb.")
    for cap in [0.12, 0.10, 0.08, 0.07, 0.06, 0.05]:
        evaluate(cap, f"cap comb {cap:.2f}")
    print("\nLECTURA: el cap combinado baja top%/HHI. Elegir el que mantiene Sharpe/%/mes y maxDD ≈ baseline")
    print("(regla de oro: menos riesgo de 1 nombre sin ceder retorno). El top% es PRE-leverage·lev = % de equity.")


if __name__ == "__main__":
    main()
