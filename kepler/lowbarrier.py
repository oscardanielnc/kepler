"""
Kepler — MODO LOW-BARRIER (copy-lead de baja barrera de entrada). Validado e76/e77 (2026-06-09).

PROBLEMA: el min-notional de Binance ($5 la mayoría · $20 ETH-tier · $50 BTC) × Nº-posiciones fija la
BARRERA DE ENTRADA del copiador. El libro full-20 necesita ~$7k para colocarse → mata el mercado copy-lead.

SOLUCIÓN (idea de Oscar, validada): NO operar los símbolos caros (BTC/ETH/BCH/ETC/LINK/LTC), sino el
universo BARATO ($5 min-notional), y RE-NEUTRALIZAR la β entre esos coins baratos (en vez de shortear BTC).
Resultado e77: Sharpe 1.46-1.47 (≈ full 1.48), β ≈ −0.01, barrera ~$300-485. Robusto a slippage ×3 y OOS.

Este módulo reconstruye la matriz de pesos diaria del libro combinado (misma lógica que engine, grabando
los pesos en cada rebalanceo), aplica las transformaciones low-barrier y ancla el leverage al maxDD del tier.
El CAPITAL decide cuántas patas (el dropping adaptativo vive en execution): a $300 ~9 patas, a $1000+ ~13.
"""
from __future__ import annotations
import os, glob
import numpy as np, pandas as pd
import config
from kepler import alphas
from kepler.engine import (load, load_panel, _beta, _weights_from_score, _cap_normalize,
                           trend_sleeve, DRIVER, BETA_W, SLEEVES, CARRY_SMOOTH, TIERS)
from kepler.portfolio import vol_parity_weights, metrics, leverage_robust

MAKER = config.MAKER_FEE


# ── slippage por liquidez (ADV K50, e18) — inline para no depender de research ──
def _slip(adv_M, cols, mult=1.0):
    s = (50.0 / np.sqrt(adv_M) * mult).clip(0.5, 30.0) / 1e4
    return s.reindex(cols).fillna(0.5 / 1e4)


# ── grabadores de pesos por sleeve (espejo de engine, grabando W en cada rebalanceo) ──
def _xs_weights(C, ret, beta, score_df, hold):
    syms = [s for s in C.columns if s != DRIVER]
    R = ret[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold)); fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0; rows = {}; rets = []; ts = []
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        full = w.copy(); full[DRIVER] = h; rows[C.index[t]] = full
        port = float((w * fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h * float(fwd_d.iloc[t] or 0)
        turn = float((w - prev).abs().sum()) + abs(h - ph)
        rets.append(port - turn * MAKER); ts.append(C.index[t]); prev, ph = w, h
    W = pd.DataFrame(rows).T.reindex(columns=C.columns).fillna(0.0)
    s = pd.Series(rets, index=ts); s = (1 + s).cumprod().resample("1D").last().ffill().pct_change().dropna()
    return W, s


def _carry_weights(C, ret):
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        sym = os.path.basename(p)[:-8]
        if sym not in C.columns: continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True); fd[sym] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    syms = [s for s in C.columns if s != DRIVER]
    Fs = F.rolling(CARRY_SMOOTH, min_periods=1).mean()
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    bet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)
    idx = range(91, len(F) - 6, 6); prev = pd.Series(0.0, index=syms); ph = 0.0; rows = {}; rets = []; ts = []
    for t in idx:
        w, h = alphas.carry_weights(Fs[syms].iloc[t], bet.iloc[t], config.MAX_WEIGHT_NORMAL)
        w = w.reindex(syms).fillna(0.0); full = w.copy(); full[DRIVER] = h; rows[F.index[t]] = full
        fund = -float((w * F[syms].iloc[t + 1:t + 7].sum()).sum())
        px = float((w * (Cr[syms].iloc[t + 6] / Cr[syms].iloc[t] - 1)).sum()) + h * (Cr[DRIVER].iloc[t + 6] / Cr[DRIVER].iloc[t] - 1)
        turn = float((w - prev).abs().sum()) + abs(h - ph)
        rets.append(fund + px - turn * MAKER); ts.append(F.index[t]); prev, ph = w, h
    W = pd.DataFrame(rows).T.reindex(columns=C.columns).fillna(0.0)
    s = pd.Series(rets, index=ts); s = (1 + s).cumprod().resample("1D").last().ffill().pct_change().dropna()
    return W, s


def _trend_weights(C):
    px = C.resample("1D").last(); rr = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0); vol = rr.rolling(30).std()
    scal = (0.20 / np.sqrt(365) / vol).clip(0, 3); pos = (sig.shift(1) * scal).fillna(0)
    W = pos.copy()
    for i in range(len(pos)):
        W.iloc[i] = _cap_normalize(pos.iloc[i].values.astype(float), config.MAX_WEIGHT_NORMAL)
    s, _ = trend_sleeve(C)
    return W.reindex(columns=C.columns).fillna(0.0), s


def build_combined_book(C, panels):
    """Matriz de pesos diaria del libro COMBINADO full (Σ vp·W_sleeve) + df sleeve-ret + vp + pesos por sleeve."""
    ret = np.log(C).diff(); beta = _beta(ret)
    Wmats = {}; series = {}
    for name, typ, hold in SLEEVES:
        if typ == "xs_mom":      W, s = _xs_weights(C, ret, beta, alphas.xs_momentum_score(ret, hold), hold)
        elif typ == "xs_rev":    W, s = _xs_weights(C, ret, beta, alphas.xs_reversal_score(ret, hold), hold)
        elif typ == "xs_lowvol": W, s = _xs_weights(C, ret, beta, alphas.xs_lowvol_score(ret, hold), hold)
        elif typ == "xs_flow":   W, s = _xs_weights(C, ret, beta, alphas.xs_takerflow_score(panels["volume"], panels["taker_buy_volume"], hold), hold)
        elif typ == "xs_hlpos":  W, s = _xs_weights(C, ret, beta, alphas.xs_hlposition_score(C, hold), hold)
        elif typ == "carry":     W, s = _carry_weights(C, ret)
        else:                    W, s = _trend_weights(C)
        Wmats[name] = W; series[name] = s
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    didx = C.resample("1D").last().index
    Wc = pd.DataFrame(0.0, index=didx, columns=C.columns)
    for name in Wmats:
        Wd = Wmats[name].reindex(didx, method="ffill").fillna(0.0).reindex(columns=C.columns).fillna(0.0)
        Wc = Wc.add(float(vp[name]) * Wd, fill_value=0.0)
    last_w = {n: Wmats[n].iloc[-1].reindex(C.columns).fillna(0.0) for n in Wmats}
    return Wc.fillna(0.0), df, vp, beta, last_w


# ── transformaciones low-barrier (validadas e77) ──
def _renorm_gross(W, keep):
    g0 = W.abs().sum(axis=1); Wk = W.copy()
    Wk[[c for c in W.columns if c not in keep]] = 0.0
    g1 = Wk.abs().sum(axis=1).replace(0, np.nan)
    return Wk.mul((g0 / g1).fillna(0.0), axis=0)


def _beta_neutralize(W, beta_daily, keep):
    """Neutraliza Σwβ usando SOLO los coins de `keep` (wᵢ -= c·βᵢ, c=Σwβ/Σβ²). Sin tocar BTC."""
    g0 = W.abs().sum(axis=1)
    B = beta_daily.reindex(W.index).reindex(columns=W.columns).fillna(0.0)
    mask = pd.Series(0.0, index=W.columns); mask[keep] = 1.0
    Bk = B.mul(mask, axis=1)
    c = ((W * Bk).sum(axis=1) / (Bk * Bk).sum(axis=1).replace(0, np.nan)).fillna(0.0)
    Wn = W.sub(Bk.mul(c, axis=0))
    g1 = Wn.abs().sum(axis=1).replace(0, np.nan)
    return Wn.mul((g0 / g1).fillna(0.0), axis=0)


def _book_return(W, rd, cost):
    held = W.shift(1).reindex(rd.index).fillna(0.0)
    turn = (W - W.shift(1)).abs().reindex(rd.index).fillna(0.0)
    c = (turn * cost.reindex(W.columns).fillna(cost.median())).sum(axis=1)
    return ((held * rd).sum(axis=1) - c).dropna()


def low_barrier_book(C, panels):
    """Construye el libro low-barrier diario (1x), su retorno y la β diaria. Núcleo reusable (engine+validación)."""
    Wc, df, vp, beta, last_w = build_combined_book(C, panels)
    beta_daily = beta.resample("1D").last()
    keep = [s for s in config.LOW_BARRIER_UNIVERSE if s in C.columns]
    Wlb = _beta_neutralize(_renorm_gross(Wc, keep), beta_daily, keep)
    rd = C.resample("1D").last().pct_change().reindex(Wlb.index).fillna(0.0)
    # ADV = volumen-$ medio DIARIO por símbolo (quote_volume es horario → resample a 1D y promediar).
    adv = panels["quote_volume"].resample("1D").sum().mean()
    adv_M = (adv.reindex(C.columns).fillna(1.0) / 1e6).clip(lower=1.0)
    cost = pd.Series(MAKER, index=C.columns) + _slip(adv_M, list(C.columns))
    book_ret = _book_return(Wlb, rd, cost)
    return Wlb, book_ret, df, vp, beta, last_w, rd


def compute_low_barrier_target(tier="ESTABLE"):
    """Misma firma que engine.compute_target → (target, vp, df, port_ret, asof, lev, weights, beta_last, beta_model).
    target = libro low-barrier (universo barato, β-neutralizado) escalado por el leverage anclado al maxDD del tier."""
    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    Wlb, book_ret, df, vp, beta, last_w, rd = low_barrier_book(C, panels)
    lev = leverage_robust(book_ret, TIERS[tier], config.LEVERAGE_HAIRCUT,
                          config.MAX_STRAT_LEVERAGE, config.TARGET_VOL_ANCHOR)
    target = (Wlb.iloc[-1] * lev)
    if config.MAX_POSITION_EQUITY:
        target = target.clip(-config.MAX_POSITION_EQUITY, config.MAX_POSITION_EQUITY)
    target = target.reindex(C.columns).fillna(0.0).round(4)
    # β-modelo de regresión del libro low-barrier (neutralidad)
    rd_btc = rd[DRIVER]
    v = pd.concat([book_ret.rename("p"), rd_btc.rename("b")], axis=1).dropna()
    beta_model = float(np.cov(v["p"], v["b"])[0, 1] / np.var(v["b"])) if len(v) > 30 and v["b"].var() > 0 else 0.0
    return target, vp, df, book_ret, C.index[-1], lev, last_w, beta.iloc[-1], beta_model
