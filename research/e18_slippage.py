"""
E18 — C1: SLIPPAGE REALISTA POR LIQUIDEZ (ROADMAP §C1). 2026-05-31.
El motor actual cobra un costo PLANO (turnover × MAKER_FEE 1.8bps) en los sleeves xs/carry,
y CERO costo en trend. Eso sobreestima el edge: los símbolos ilíquidos cuestan más al operar.
Objetivo (honestidad, no subir el número): modelar el costo por símbolo y ver cuánto baja el 1.94.

MODELO de costo one-way por símbolo i:   cost_i = MAKER_FEE + κ · (spread_i / 2)
  - spread_i = spread efectivo relativo, estimado de OHLC con Abdi-Ranaldo (2017):
        S² = 4·E[(c_t − η_t)(c_t − η_{t+1})],  c=ln(close), η=(ln(high)+ln(low))/2
    Robusto, separa spread de volatilidad. Símbolos ilíquidos → spread mayor.
  - κ = fracción del medio-spread que realmente se paga (maker-first paga < 1; se testea 0.5 y 1.0).
ADV (volumen USD/día, mediana) se reporta para ver el perfil de liquidez.

ESCENARIOS (para descomponer el efecto):
  1. MOTOR ACTUAL   : xs/carry maker plano, trend SIN costo  → debe reproducir el ~1.94.
  2. MAKER PLANO ∀  : maker plano también en trend (cierra el hueco de trend sin costo).
  3. +½SPREAD κ=0.5 : maker + medio-spread×0.5 por símbolo (central).
  4. +½SPREAD κ=1.0 : maker + medio-spread completo (conservador).

python -m research.e18_slippage
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, _weights_from_score, load_panel, carry_sleeve,
                           trend_sleeve, xs_sleeve, DRIVER, BETA_W, SLEEVES)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

MAKER = config.MAKER_FEE


# ─── estimadores de liquidez (de datos OHLC/volumen) ──────────────────────────
def abdi_ranaldo_spread(C, H, L):
    """Spread efectivo relativo por símbolo (Abdi-Ranaldo 2017). Devuelve Series por símbolo."""
    c = np.log(C); eta = (np.log(H) + np.log(L)) / 2.0
    x = (c - eta) * (c - eta.shift(-1))
    s2 = 4.0 * x.mean()
    return np.sqrt(s2.clip(lower=0.0))          # spread proporcional (fracción)


def adv_usd(QV):
    """ADV en USD/día (mediana del volumen-en-quote diario) por símbolo."""
    daily = QV.resample("1D").sum()
    return daily.median()


# ─── backtests que devuelven port BRUTO + turnover por símbolo (costo aparte) ──
def bt_xs(C, ret, beta, score_df, hold):
    """Mirror de engine.xs_sleeve pero SIN restar costo: devuelve (ts, port_gross, turn_df).
    turn_df = |Δw| por símbolo y |Δh| del driver en cada período de rebalanceo."""
    syms = [s for s in C.columns if s != DRIVER]
    R = ret[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold)); fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0
    pg = []; ts = []; turns = []
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        port = float((w * fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h * float(fwd_d.iloc[t] or 0)
        tr = (w - prev).abs(); tr[DRIVER] = abs(h - ph)
        pg.append(port); ts.append(C.index[t]); turns.append(tr); prev, ph = w, h
    turn_df = pd.DataFrame(turns, index=ts).fillna(0.0)
    return ts, np.array(pg), turn_df


def bt_carry(C, ret, beta):
    """Mirror de engine.carry_sleeve sin restar costo: (ts, port_gross, turn_df)."""
    fd = {}
    import glob
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns:
            continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    syms = [s for s in C.columns if s != DRIVER]
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    bet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)
    idx = range(91, len(F) - 6, 6); prev = pd.Series(0.0, index=syms); ph = 0.0
    pg = []; ts = []; turns = []
    for t in idx:
        w, h = alphas.carry_weights(F[syms].iloc[t], bet.iloc[t], config.MAX_WEIGHT_NORMAL)
        w = w.reindex(syms).fillna(0.0)
        fund = -float((w * F[syms].iloc[t+1:t+7].sum()).sum())
        px = float((w * (Cr[syms].iloc[t+6]/Cr[syms].iloc[t]-1)).sum()) + h*(Cr[DRIVER].iloc[t+6]/Cr[DRIVER].iloc[t]-1)
        tr = (w - prev).abs(); tr[DRIVER] = abs(h - ph)
        pg.append(fund + px); ts.append(F.index[t]); turns.append(tr); prev, ph = w, h
    turn_df = pd.DataFrame(turns, index=ts).fillna(0.0)
    return ts, np.array(pg), turn_df


def bt_trend(C):
    """Mirror de engine.trend_sleeve: devuelve (pnl_daily, turn_df_daily, lev_daily).
    OJO: el motor NO le cobra costo hoy → con slip=0 esto reproduce el motor."""
    px = C.resample("1D").last(); ret = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0)
    vol = ret.rolling(30).std()
    scal = (0.20/np.sqrt(365) / vol).clip(0, 3)
    pos = (sig.shift(1) * scal).fillna(0)
    pnl = (pos * ret).mean(axis=1)
    pv = pnl.rolling(30).std().shift(1); lev = (0.15/np.sqrt(365)/pv).clip(0, 4).fillna(1)
    turn = (pos - pos.shift(1)).abs().fillna(0.0)
    return pnl, turn, lev


def compound_daily(ts, net):
    s = pd.Series(net, index=ts)
    return (1 + s).cumprod().resample("1D").last().ffill().pct_change().dropna()


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m["sharpe"], m["ann"], L, m["maxdd"]


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E18 — C1 slippage realista por liquidez\n" + "="*60)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume", "quote_volume", "high", "low"], C)
    cols = list(C.columns)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h\n")

    # ── liquidez por símbolo ──────────────────────────────────────────────────
    # NOTA: el estimador de spread de OHLC (Abdi-Ranaldo) NO es fiable con barras de 1h
    # (el spread sub-bp queda bajo la vol intrahora → S² negativo → 0). Se reporta como
    # referencia pero el modelo de costo se basa en ADV, que SÍ es robusto.
    spread_ar = abdi_ranaldo_spread(C, P["high"], P["low"]).reindex(cols).fillna(0.0)
    adv = adv_usd(P["quote_volume"]).reindex(cols).fillna(0.0)
    adv_M = (adv/1e6).clip(lower=1.0)

    # Modelo de slippage por liquidez: slip_i = clip(K/√ADV_$M, floor, cap). Calibrado para que
    # BTC(~$13B)→~0.4bps y el más ilíquido (~$15M)→~13bps. K en bps·√($M).
    K_SLIP, FLOOR_BPS, CAP_BPS = 50.0, 0.5, 30.0
    def slip_adv(mult=1.0):
        s = (K_SLIP / np.sqrt(adv_M) * mult).clip(FLOOR_BPS, CAP_BPS) / 1e4
        return s.reindex(cols).fillna(FLOOR_BPS/1e4)

    s1 = slip_adv(1.0)
    liq = pd.DataFrame({"ADV_$M/día": adv/1e6, "slip_bps(K50)": s1*1e4, "spread_AR_bps(ref)": spread_ar*1e4})
    liq = liq.sort_values("ADV_$M/día")
    print("LIQUIDEZ y slippage modelado (one-way), ordenado por ADV ascendente:")
    print(liq.round(2).to_string())
    print(f"\n  MAKER_FEE plano actual = {MAKER*1e4:.2f} bps · slip modelado: mediana "
          f"{(s1*1e4).median():.2f} bps · máx {(s1*1e4).max():.2f} bps ({s1.idxmax()})")

    # ── precomputar cada sleeve UNA vez (bruto + turnover) ────────────────────
    print("\nPrecomputando sleeves (bruto + turnover por símbolo)...")
    XS = {}
    for name, typ, hold in SLEEVES:
        if typ == "xs_mom":   sc = alphas.xs_momentum_score(ret, hold)
        elif typ == "xs_rev": sc = alphas.xs_reversal_score(ret, hold)
        elif typ == "xs_lowvol": sc = alphas.xs_lowvol_score(ret, hold)
        elif typ == "xs_flow": sc = alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], hold)
        elif typ == "xs_hlpos": sc = alphas.xs_hlposition_score(C, hold)
        else: continue
        if typ != "carry" and typ != "trend":
            XS[name] = bt_xs(C, ret, beta, sc, hold)
    CARRY = bt_carry(C, ret, beta)
    TREND = bt_trend(C)

    # ── turnover anualizado por sleeve (contexto del peso de los costos) ───────
    yrs = (C.index[-1] - C.index[0]).days / 365.25
    print(f"\nTURNOVER anualizado por sleeve (× capital, one-way · muestra {yrs:.1f} años):")
    for name, (ts, pg, turn) in XS.items():
        print(f"  {name:<14s} {turn.values.sum()/yrs:6.1f}x")
    print(f"  {'carry':<14s} {CARRY[2].values.sum()/yrs:6.1f}x")
    print(f"  {'trend':<14s} {TREND[1].values.sum()/yrs:6.1f}x  (el motor hoy NO le cobra costo)")

    def sleeve_net(slip: pd.Series):
        """Series diarias netas de cada sleeve para un vector de costo `slip` (por símbolo)."""
        out = {}
        for name, (ts, pg, turn) in XS.items():
            cost = (turn * slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
            out[name] = compound_daily(ts, pg - cost)
        ts, pg, turn = CARRY
        cost = (turn * slip.reindex(turn.columns).fillna(0)).sum(axis=1).values
        out["carry"] = compound_daily(ts, pg - cost)
        return out

    def trend_net(slip_trend: pd.Series):
        pnl, turn, lev = TREND
        cost = (turn * slip_trend.reindex(turn.columns).fillna(0)).mean(axis=1)
        return ((pnl - cost) * lev).dropna()

    def build(slip_xscarry: pd.Series, slip_trend: pd.Series):
        d = sleeve_net(slip_xscarry)
        d["trend"] = trend_net(slip_trend)
        df = pd.concat(d, axis=1); df.columns = list(d.keys()); df = df.dropna()
        combo = (df * vol_parity_weights(df)).sum(axis=1)
        return anchored(combo), metrics(combo)["sharpe"]

    zero = pd.Series(0.0, index=cols)
    flat = pd.Series(MAKER, index=cols)
    def maker_plus(slip): return (pd.Series(MAKER, index=cols) + slip.reindex(cols).fillna(0))
    flat10 = pd.Series(MAKER + 10/1e4, index=cols)   # 10 bps plano a TODOS (estrés ciego a liquidez)

    scenarios = [
        ("1. MOTOR ACTUAL (trend sin costo)",      flat, zero),
        ("2. MAKER PLANO en TODOS",                flat, flat),
        ("3. + slip ADV K50 (central)",            maker_plus(slip_adv(1.0)), maker_plus(slip_adv(1.0))),
        ("4. + slip ADV ×3 (estrés liquidez)",     maker_plus(slip_adv(3.0)), maker_plus(slip_adv(3.0))),
        ("5. + 10 bps PLANO ∀ (estrés duro)",      flat10, flat10),
    ]
    print("\nRESULTADOS (combinado 7 sleeves al ancla maxDD −10%):")
    print(f"  {'escenario':<38s} {'Sharpe':>7s} {'lev':>6s} {'ann':>7s} {'%/mes':>6s} {'maxDD':>7s}")
    base_ann = None
    for label, sxc, str_ in scenarios:
        (sh, ann, L, dd), sh1x = build(sxc, str_)
        if base_ann is None: base_ann = ann
        print(f"  {label:<38s} {sh1x:7.2f} {L:6.2f} {ann:6.1f}% {ann/12:6.2f} {dd:6.1f}%  "
              f"(Δ{(ann-base_ann)/12:+.2f}%/mes)")

    print("\nSanity: escenario 1 reproduce el motor (1.94). Lectura: cuánto cae al modelar costo realista.")


if __name__ == "__main__":
    main()
