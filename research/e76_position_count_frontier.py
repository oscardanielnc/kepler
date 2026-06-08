"""
E76 — FRONTERA Nº-DE-POSICIONES (2026-06-08). Decisión de PRODUCTO copy-lead.
=============================================================================
Pregunta (regla de oro): ¿cuál es el MÍNIMO de posiciones que preserva el edge? El nº de posiciones fija
A LA VEZ (a) nuestro capital floor y (b) la BARRERA DE ENTRADA del copiador (depende de nº-posiciones ×
min-notional Binance, NO de nuestro capital). Con 18 patas el copy-lead nace con techo ~$1000 de afiliados
permanente → choca con la misión de copy-lead masivo. Si una versión de ~10 patas conserva Sharpe/maxDD →
WIN de producto (barrera ~$400). Si lo cratea → la diversificación es el precio del edge.

MÉTODO (fiel a producción):
  1. Reconstruyo la matriz de pesos por-símbolo DIARIA del libro combinado, reusando la lógica EXACTA de
     cada sleeve (xs/carry/trend) — grabo los pesos en cada rebalanceo y los ffill a diario.
  2. Combino: W_comb = Σ vp_sleeve · W_sleeve  (vp = vol_parity_weights, igual que engine).
  3. Retorno del libro = Σ wᵢ·retᵢ (hold de ayer) − turnover×(maker+slip ADV K50). VALIDO contra baseline.
  4. FRONTERA: para N ∈ {6,8,...,20,full}: cada día quedarse con las top-N |w|, RENORMALIZAR a igual gross,
     y RE-ANCLAR el leverage a −10% maxDD (tier=presupuesto). Apples-to-apples: comparo RETORNO a igual maxDD.
  5. Métricas por N: Sharpe · %/mes · maxDD · β(realizada vs BTC) · IS/OOS Sharpe · nº-pos efectivo ·
     CAPITAL FLOOR (mín capital para que TODAS las patas superen su min-notional Binance: $5/$20/$50).

No toca producción. python -m research.e76_position_count_frontier
"""
from __future__ import annotations
import os, sys, json, urllib.request
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from kepler import alphas
from kepler.engine import (load, load_panel, _beta, _weights_from_score, DRIVER, BETA_W,
                           SLEEVES, CARRY_SMOOTH, trend_sleeve)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e18_slippage import adv_usd
from research.e53_thin_coins import slip_adv

MAKER = config.MAKER_FEE
HAIRCUT = config.LEVERAGE_HAIRCUT
TARGET_MAXDD = config.TARGET_MAXDD


# ── grabadores de pesos por sleeve (espejo EXACTO de engine, grabando W en cada rebalanceo) ──
def xs_weights(C, ret, beta, score_df, hold):
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
    series = pd.Series(rets, index=ts); series = (1 + series).cumprod().resample("1D").last().ffill().pct_change().dropna()
    return W, series


def carry_weights_mtx(C, ret):
    import glob
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns: continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True); fd[s] = f.resample("8h").sum()
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
    series = pd.Series(rets, index=ts); series = (1 + series).cumprod().resample("1D").last().ffill().pct_change().dropna()
    return W, series


def trend_weights_mtx(C):
    from kepler.engine import _cap_normalize
    px = C.resample("1D").last(); ret = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0); vol = ret.rolling(30).std()
    scal = (0.20 / np.sqrt(365) / vol).clip(0, 3); pos = (sig.shift(1) * scal).fillna(0)
    W = pos.copy()
    for i in range(len(pos)):
        W.iloc[i] = _cap_normalize(pos.iloc[i].values.astype(float), config.MAX_WEIGHT_NORMAL)
    series, _ = trend_sleeve(C)   # serie idéntica a engine (incl. lev interno, para vp)
    return W.reindex(columns=C.columns).fillna(0.0), series


def build_book(C, panels):
    """Devuelve W_comb (DataFrame diario, pesos 1x por símbolo) + sleeve-return df (para vp/validación)."""
    ret = np.log(C).diff(); beta = _beta(ret)
    Wmats = {}; series = {}
    for name, typ, hold in SLEEVES:
        if typ == "xs_mom":     W, s = xs_weights(C, ret, beta, alphas.xs_momentum_score(ret, hold), hold)
        elif typ == "xs_rev":   W, s = xs_weights(C, ret, beta, alphas.xs_reversal_score(ret, hold), hold)
        elif typ == "xs_lowvol":W, s = xs_weights(C, ret, beta, alphas.xs_lowvol_score(ret, hold), hold)
        elif typ == "xs_flow":  W, s = xs_weights(C, ret, beta, alphas.xs_takerflow_score(panels["volume"], panels["taker_buy_volume"], hold), hold)
        elif typ == "xs_hlpos": W, s = xs_weights(C, ret, beta, alphas.xs_hlposition_score(C, hold), hold)
        elif typ == "carry":    W, s = carry_weights_mtx(C, ret)
        else:                   W, s = trend_weights_mtx(C)
        Wmats[name] = W; series[name] = s
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    # rejilla diaria común
    didx = C.resample("1D").last().index
    Wc = pd.DataFrame(0.0, index=didx, columns=C.columns)
    for name in Wmats:
        Wd = Wmats[name].reindex(didx, method="ffill").fillna(0.0).reindex(columns=C.columns).fillna(0.0)
        Wc = Wc.add(float(vp[name]) * Wd, fill_value=0.0)
    return Wc.dropna(how="all").fillna(0.0), df, vp


def book_return(W, rd, cost):
    """Retorno 1x del libro: Σ wᵢ(ayer)·retᵢ − turnover×coste. W,rd alineados a diario."""
    held = W.shift(1).reindex(rd.index).fillna(0.0)
    gross_ret = (held * rd).sum(axis=1)
    turn = (W - W.shift(1)).abs().reindex(rd.index).fillna(0.0)
    c = (turn * cost.reindex(W.columns).fillna(cost.median())).sum(axis=1)
    return (gross_ret - c).dropna()


def truncate(W, N):
    A = W.values.astype(float); ab = np.abs(A); out = np.zeros_like(A)
    for r in range(A.shape[0]):
        row = A[r]; a = ab[r]; nz = (a > 1e-9).sum()
        if nz <= N: out[r] = row; continue
        idx = np.argpartition(a, -N)[-N:]
        keep = np.zeros_like(row); keep[idx] = row[idx]
        g0 = a.sum(); g1 = np.abs(keep).sum()
        if g1 > 0: keep *= (g0 / g1)
        out[r] = keep
    return pd.DataFrame(out, index=W.index, columns=W.columns)


def floor_capital(Wlev, minnot, lookback=252):
    """Capital floor por día = max_i(min_notional_i/|book_i|) sobre patas tenidas; resume med y p90 (último año)."""
    sub = Wlev.tail(lookback); fl = []
    mn = np.array([minnot[c] for c in Wlev.columns])
    for _, row in sub.iterrows():
        a = np.abs(row.values); held = a > 1e-6
        if held.sum() == 0: continue
        fl.append(float(np.max(mn[held] / a[held])))
    fl = np.array(fl) if fl else np.array([np.nan])
    last = np.abs(Wlev.iloc[-1].values); lh = last > 1e-6
    last_floor = float(np.max(mn[lh] / last[lh])) if lh.sum() else np.nan
    return np.nanmedian(fl), np.nanpercentile(fl, 90), last_floor


def get_min_notionals(cols):
    try:
        d = json.load(urllib.request.urlopen("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=25))
        mn = {}
        for s in d["symbols"]:
            if s["symbol"] in cols:
                for f in s["filters"]:
                    if f["filterType"] == "MIN_NOTIONAL": mn[s["symbol"]] = float(f["notional"])
        return {c: mn.get(c, 5.0) for c in cols}, "Binance live"
    except Exception:
        return {c: (50.0 if c == "BTCUSDT" else 20.0 if c == "ETHUSDT" else 5.0) for c in cols}, "fallback"


def half_sh(r):
    h = len(r) // 2
    return metrics(r.iloc[:h]).get("sharpe", float("nan")), metrics(r.iloc[h:]).get("sharpe", float("nan"))


def beta_to_btc(port, rd_btc):
    v = pd.concat([port.rename("p"), rd_btc.rename("b")], axis=1).dropna()
    if len(v) < 30 or v["b"].var() == 0: return float("nan")
    return float(np.cov(v["p"], v["b"])[0, 1] / np.var(v["b"]))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E76 — FRONTERA Nº-DE-POSICIONES (decisión de producto copy-lead)\n")
    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    adv = adv_usd(panels["quote_volume"]).reindex(C.columns).fillna(0.0)
    adv_M = (adv / 1e6).clip(lower=1.0)
    cost = pd.Series(MAKER, index=C.columns) + slip_adv(adv_M, list(C.columns), 1.0)
    minnot, mn_src = get_min_notionals(list(C.columns))
    n5 = sum(v == 5 for v in minnot.values()); n20 = sum(v == 20 for v in minnot.values()); n50 = sum(v >= 50 for v in minnot.values())
    print(f"min-notional ({mn_src}): $5×{n5} · $20×{n20} · $50×{n50}  | universo {len(C.columns)} símbolos · {C.index[0].date()}→{C.index[-1].date()}\n")

    print("Reconstruyendo libro combinado (7 sleeves)...")
    W, df, vp = build_book(C, panels)
    rd = C.resample("1D").last().pct_change().reindex(W.index).fillna(0.0)
    rd_btc = rd[DRIVER]

    # VALIDACIÓN: el libro reconstruido vs el oficial (sleeve-return). Ancla a −10% ambos.
    base_ret = book_return(W, rd, cost)
    Lb = min(HAIRCUT * leverage_for_maxdd_anchor(base_ret, TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    mb = metrics(base_ret * Lb)
    off = (df * vp).sum(axis=1); Lo = min(HAIRCUT * leverage_for_maxdd_anchor(off, TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    mo = metrics(off * Lo)
    avgpos_full = int((W.abs() > 1e-6).sum(axis=1).tail(252).mean())
    print(f"  VALIDACIÓN — libro reconstruido (lo que se OPERA): Sharpe {mb['sharpe']:.2f} · {mb['ann']/12:.2f}%/mes · "
          f"maxDD {mb['maxdd']:.1f} · lev {Lb:.2f}x · ~{avgpos_full} pos")
    print(f"  (ref. oficial sleeve-return @anchor: Sharpe {mo['sharpe']:.2f} · {mo['ann']/12:.2f}%/mes · maxDD {mo['maxdd']:.1f})")
    print(f"  β libro completo vs BTC: {beta_to_btc(base_ret, rd_btc):+.3f}\n")

    Ns = [6, 8, 10, 12, 14, 16, 18, 20, len(C.columns)]
    print("FRONTERA (cada N re-anclado a −10% maxDD; comparas RETORNO a igual riesgo):")
    print(f"{'N':>4s} │ {'Sharpe':>6s} {'%/mes':>6s} {'maxDD':>6s} {'β':>6s} {'IS/OOS':>11s} {'pos~':>4s} │ "
          f"{'floor_med':>9s} {'floor_p90':>9s} {'floor_now':>9s}")
    print("─" * 96)
    rows = []
    for N in Ns:
        Wt = truncate(W, N) if N < len(C.columns) else W.copy()
        r = book_return(Wt, rd, cost)
        L = min(HAIRCUT * leverage_for_maxdd_anchor(r, TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
        m = metrics(r * L); s1, s2 = half_sh(r)
        b = beta_to_btc(r, rd_btc)
        avgpos = (Wt.abs() > 1e-6).sum(axis=1).tail(252).mean()
        Wlev = (Wt * L).clip(-config.MAX_POSITION_EQUITY, config.MAX_POSITION_EQUITY)
        f_med, f_p90, f_now = floor_capital(Wlev, minnot)
        tag = "  ← producción actual" if N == 18 else ("  (universo completo)" if N == len(C.columns) else "")
        rows.append((N, m, b, s1, s2, avgpos, f_med, f_p90, f_now))
        print(f"{N:>4d} │ {m['sharpe']:>6.2f} {m['ann']/12:>5.2f}% {m['maxdd']:>6.1f} {b:>+6.3f} {s1:>5.2f}/{s2:<5.2f} "
              f"{avgpos:>4.0f} │ ${f_med:>8.0f} ${f_p90:>8.0f} ${f_now:>8.0f}{tag}")

    print("\nLECTURA:")
    print("  • Sharpe ~plano al bajar N = la diversificación marginal de las patas chicas aporta poco → PODEMOS")
    print("    reducir posiciones SIN perder edge → baja la barrera del copiador (floor) = WIN de producto.")
    print("  • Sharpe cae fuerte al bajar N = la diversificación ES el edge → se asume el floor alto.")
    print("  • Vigilar β: si truncar dispara la β (rompe neutralidad) esa N no es el mismo producto.")
    print("  • floor_p90 ≈ capital para colocar el libro completo el 90% de los días (barrera realista copiador+lead).")


if __name__ == "__main__":
    main()
