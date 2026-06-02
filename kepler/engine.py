"""
Kepler — MOTOR LIVE. Calcula el PORTAFOLIO OBJETIVO actual desde los 5 sleeves validados,
lo combina por vol-parity, aplica el tier de leverage y lo persiste en la DB.

Salida: vector de pesos objetivo por activo (qué long/short y cuánto, % del capital),
β≈0, listo para que la capa de ejecución (order_manager) rebalancee a maker.

Tiers: ESTABLE 1x · BALANCEADO 2x · GROWTH 3x.
python -m kepler.engine [ESTABLE|BALANCEADO|GROWTH]
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler import alphas
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor, leverage_robust
from kepler.db import DB

DRIVER = "BTCUSDT"; BETA_W = 168; MIN_BARS = 34000
CARRY_SMOOTH = 21   # media móvil del funding-signal del carry: 7d (21×8h) → recorta turnover (e19)
# Tiers = PRESUPUESTO DE maxDD (regla Oscar 2026-05-30). El leverage de estrategia se CALCULA
# para que el maxDD del backtest = este valor. ESTABLE ancla a −10% (config.TARGET_MAXDD).
TIERS = {"ESTABLE": config.TARGET_MAXDD, "BALANCEADO": 0.20, "GROWTH": 0.30}
# Sleeves: (nombre, tipo, lookback_horas)
SLEEVES = [("mom_30d", "xs_mom", 720), ("rev_60d", "xs_rev", 1440),
           ("lowvol_14d", "xs_lowvol", 336), ("carry", "carry", None), ("trend", "trend", None),
           ("takerflow_5d", "xs_flow", 120), ("hlpos_14d", "xs_hlpos", 336)]


def load():
    cl = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        c = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
        if len(c) < MIN_BARS:
            continue
        cl[s] = c
    C = pd.DataFrame(cl).sort_index().dropna()
    C.index = pd.to_datetime(C.index, unit="ms", utc=True)
    return C


def load_panel(cols, like: pd.DataFrame):
    """Carga columnas extra (p.ej. volume, taker_buy_volume) del universo de historia larga,
    alineadas al índice/columnas de `like` (el panel de close). Para el sleeve de flujo."""
    data = {c: {} for c in cols}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        df = pd.read_parquet(p, columns=["open_time", *cols]).set_index("open_time")
        if len(df) < MIN_BARS:
            continue
        for c in cols:
            data[c][s] = df[c]
    out = {}
    for c in cols:
        P = pd.DataFrame(data[c]).sort_index()
        P.index = pd.to_datetime(P.index, unit="ms", utc=True)
        out[c] = P.reindex(index=like.index, columns=like.columns)
    return out


def _beta(ret):
    rd = ret[DRIVER]
    return ret.rolling(BETA_W).cov(rd).div(rd.rolling(BETA_W).var(), axis=0).clip(-3, 3)


def _weights_from_score(score_row, beta_row, syms, cap=config.MAX_WEIGHT_NORMAL):
    s = score_row.reindex(syms); b = beta_row.reindex(syms)
    v = s.notna() & b.notna()
    s = s[v] - s[v].mean()
    if s.abs().sum() == 0:
        return pd.Series(0.0, index=syms), 0.0
    w = (s / s.abs().sum()).clip(-cap, cap); w = w / w.abs().sum()
    wf = w.reindex(syms).fillna(0.0)
    h = -float((wf * b.reindex(syms).fillna(0)).sum())
    return wf, h


def xs_sleeve(C, ret, beta, score_df, hold):
    """Backtest diario (para vol-parity) + pesos ACTUALES (última barra)."""
    syms = [s for s in C.columns if s != DRIVER]
    R = ret[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold)); fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0; rets = []; ts = []
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        port = float((w * fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h * float(fwd_d.iloc[t] or 0)
        turn = float((w - prev).abs().sum()) + abs(h - ph)
        rets.append(port - turn * config.MAKER_FEE); ts.append(C.index[t]); prev, ph = w, h
    series = pd.Series(rets, index=ts); series = (1 + series).cumprod().resample("1D").last().ffill().pct_change().dropna()
    # pesos actuales (última barra con datos)
    w_now, h_now = _weights_from_score(score_df.iloc[-1], beta.iloc[-1], syms)
    full = w_now.copy(); full[DRIVER] = h_now
    return series, full


def _carry_universe(C):
    """Carry usa MÁS breadth: todas las monedas con funding+precio (universo completo),
    no solo las de historia larga → más diversificación (reconcilia con la investigación)."""
    cl = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        c = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
        cl[s] = c
    Cf = pd.DataFrame(cl).sort_index()
    Cf.index = pd.to_datetime(Cf.index, unit="ms", utc=True)
    return Cf.reindex(C.index.union(Cf.index)).ffill().reindex(
        pd.date_range(C.index[0], C.index[-1], freq="1h", tz="UTC"))


def carry_sleeve(C, ret, beta):
    """Carry diario + pesos actuales. Probado: más breadth (universo completo) SUBE Sharpe
    +0.02 pero EMPEORA maxDD (monedas nuevas volátiles) → NO se usa. Mejor perfil de riesgo
    con las monedas de historia larga (workflow: bajo DD > +0.02 Sharpe para copy-lead)."""
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns:
            continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    syms = [s for s in C.columns if s != DRIVER]
    # SEÑAL suavizada (media móvil 7d = 21 períodos de 8h). El funding persiste días; rankear sobre
    # la lectura instantánea disparaba el turnover a 199x/año → con costos reales el carry era
    # PERDEDOR (Sharpe −0.41). Suavizar a 7d: turnover 65x, carry +0.35, combinado +0.59%/mes plano
    # (+0.82 real). Validado e19_carry_turnover (estrés por cuartiles OK). La funding COBRADA usa F real.
    Fs = F.rolling(CARRY_SMOOTH, min_periods=1).mean()
    # serie: re-usar pesos por nivel de funding cada 48h, retorno = funding cobrado + price (≈0 neutral)
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    bet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)
    idx = range(91, len(F) - 6, 6); prev = pd.Series(0.0, index=syms); ph = 0.0; rets = []; ts = []
    for t in idx:
        w, h = alphas.carry_weights(Fs[syms].iloc[t], bet.iloc[t], config.MAX_WEIGHT_NORMAL)
        w = w.reindex(syms).fillna(0.0)
        fund = -float((w * F[syms].iloc[t+1:t+7].sum()).sum())
        px = float((w * (Cr[syms].iloc[t+6]/Cr[syms].iloc[t]-1)).sum()) + h*(Cr[DRIVER].iloc[t+6]/Cr[DRIVER].iloc[t]-1)
        turn = float((w-prev).abs().sum())+abs(h-ph)
        rets.append(fund+px-turn*config.MAKER_FEE); ts.append(F.index[t]); prev, ph = w, h
    series = pd.Series(rets, index=ts); series=(1+series).cumprod().resample("1D").last().ffill().pct_change().dropna()
    w_now, h_now = alphas.carry_weights(Fs[syms].iloc[-1], bet.iloc[-1], config.MAX_WEIGHT_NORMAL)
    full = w_now.reindex(syms).fillna(0.0); full[DRIVER] = h_now
    return series, full


def _cap_normalize(v: np.ndarray, cap: float) -> np.ndarray:
    """v ≥ 0 (long-only). Normaliza a suma 1 y redistribuye el exceso sobre `cap` hacia los no-topados
    (water-filling) hasta que cada peso ≤ cap. Devuelve pesos suma≈1 con tope `cap`."""
    s = v.sum()
    if s <= 0:
        return v
    w = v / s
    for _ in range(20):
        over = w > cap + 1e-9
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over; pool = w[under].sum()
        if pool <= 0:
            break
        w[under] += excess * w[under] / pool
    return w


def trend_sleeve(C):
    """Trend long-only EMA20/100 vol-target, por activo. Serie diaria + pesos actuales.
    CAP DE CONCENTRACIÓN (e52, Oscar 2026-06-02): cada día normaliza la cesta a gross 1 y capa cada
    coin a config.MAX_WEIGHT_NORMAL (0.25, el mismo tope que xs/carry). Antes (.mean de pos vol-scaled)
    el sleeve volcaba ~47% de su gross en la coin de menor vol en tendencia (TRX → top del libro ~20%).
    El cap baja la concentración de un nombre a la mitad (TRX 20%→~10%, HHI −34%) SIN tocar el Sharpe
    combinado (2.07) ni el maxDD, mejorando el balance IS/OOS. Riesgo↓ a coste ~nulo (regla de oro)."""
    px = C.resample("1D").last(); ret = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0)
    vol = ret.rolling(30).std()
    scal = (0.20/np.sqrt(365) / vol).clip(0, 3)
    pos = (sig.shift(1) * scal).fillna(0)
    # cesta normalizada-capada cada día (consistente backtest↔live)
    W = pos.copy()
    for i in range(len(pos)):
        W.iloc[i] = _cap_normalize(pos.iloc[i].values.astype(float), config.MAX_WEIGHT_NORMAL)
    # COSTO de turnover (trend rota ~57x/año). Maker plano, consistente con xs/carry (e18, contabilidad
    # uniforme). El return ahora es Σ wᵢ·retᵢ con la cesta capada (antes media de pos sin normalizar).
    turn = (W - W.shift(1)).abs().fillna(0.0)
    pnl = (W * ret).sum(axis=1) - (turn * config.MAKER_FEE).sum(axis=1)
    pv = pnl.rolling(30).std().shift(1); lev = (0.15/np.sqrt(365)/pv).clip(0, 4).fillna(1)
    series = (pnl*lev).dropna()
    return series, W.iloc[-1].reindex(C.columns).fillna(0.0)


def compute_target(tier="ESTABLE"):
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    series = {}; weights = {}
    for name, typ, hold in SLEEVES:
        if typ == "xs_mom":
            s, w = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, hold), hold)
        elif typ == "xs_rev":
            s, w = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, hold), hold)
        elif typ == "xs_lowvol":
            s, w = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, hold), hold)
        elif typ == "xs_flow":
            ex = load_panel(["volume", "taker_buy_volume"], C)
            score = alphas.xs_takerflow_score(ex["volume"], ex["taker_buy_volume"], hold)
            s, w = xs_sleeve(C, ret, beta, score, hold)
        elif typ == "xs_hlpos":
            s, w = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, hold), hold)
        elif typ == "carry":
            s, w = carry_sleeve(C, ret, beta)
        else:
            s, w = trend_sleeve(C)
        series[name] = s; weights[name] = w
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    # retorno del combinado a 1x (para anclar el maxDD)
    port_ret = (df * vp).sum(axis=1)
    # LEVERAGE = el que clava el maxDD del backtest en el presupuesto del tier (regla de Oscar).
    # Se auto-recalibra: cada sleeve nuevo que baja el maxDD a 1x → sube el leverage → más
    # retorno al MISMO maxDD. Cap de seguridad en config.MAX_STRAT_LEVERAGE.
    # HAIRCUT (D0, e51): recorta el leverage del ancla para que el maxDD vivo respete el presupuesto.
    # VOL-ANCHOR (e68): min(maxdd_anchor, vol_anchor) → robusto a la VENTANA de datos (el maxdd-anchor
    # solo sobre-apalanca con histórico corto/calmado: incidente VM sin 2022 → 2.93x vs 2.16x diseño).
    lev = leverage_robust(port_ret, TIERS[tier], config.LEVERAGE_HAIRCUT,
                          config.MAX_STRAT_LEVERAGE, config.TARGET_VOL_ANCHOR)
    # target neto por activo = Σ vp_i · w_i, escalado por el leverage anclado
    target = pd.Series(0.0, index=C.columns)
    for name in series:
        target = target.add(float(vp[name]) * weights[name].reindex(C.columns).fillna(0), fill_value=0)
    target = target.reindex(C.columns).fillna(0.0)
    # GATE DE RÉGIMEN: probado (vol-target de-risk) → EMPEORA el maxDD, NO se usa (workflow).
    # El control de riesgo efectivo es la diversificación (corr~0) + el dial de leverage anclado.
    target = (target * lev).round(4)
    # β MODELO de REGRESIÓN del libro = cov(combinado 1x, BTC diario)/var(BTC diario). Es la MISMA
    # métrica que el backtest (≈+0.05, market-neutral) y la que confirma la neutralidad en vivo (D1).
    # OJO: distinta de la β-DÓLAR instantánea (Σwβ), que la infla `trend` (long-only sin hedge).
    rd_d = np.expm1(ret[DRIVER].resample("1D").sum()).reindex(port_ret.index)
    _v = pd.concat([port_ret.rename("p"), rd_d.rename("b")], axis=1).dropna()
    beta_model = float(np.cov(_v["p"], _v["b"])[0, 1] / np.var(_v["b"])) if len(_v) > 30 and _v["b"].var() > 0 else 0.0
    # `weights` = pesos por sleeve (cada uno serie por símbolo) → para registrar en la DB el desglose
    # de cada decisión. `beta.iloc[-1]` = β por-símbolo vs BTC (BTC≈1) → para la β-dólar diagnóstica
    # del libro REAL en vivo. `beta_model` = la β de regresión (neutralidad, ≈+0.05) que va al snapshot.
    return target, vp, df, port_ret, C.index[-1], lev, weights, beta.iloc[-1], beta_model


def main():
    tier = sys.argv[1] if len(sys.argv) > 1 else "ESTABLE"
    for _s in (sys.stdout, sys.stderr):
        try: _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    target, vp, df, port_ret, asof, lev, _w, beta_last, beta_model = compute_target(tier)
    m1 = metrics(port_ret)                 # 1x (base)
    m = metrics(port_ret * lev)            # con leverage anclado
    print(f"KEPLER motor live · tier {tier} · maxDD objetivo −{TIERS[tier]*100:.0f}% · "
          f"leverage estrategia {lev:.2f}x · datos hasta {asof}")
    print(f"Combinado a 1x:  Sharpe {m1['sharpe']:.2f} · ann {m1['ann']:.1f}% · maxDD {m1['maxdd']:.1f}%")
    print(f"Combinado @{lev:.2f}x: ann {m['ann']:.1f}% (~{m['ann']/12:.2f}%/mes) · "
          f"maxDD {m['maxdd']:.1f}% · mo+ {m['mo_pos']:.0f}%  ← lo que se opera")
    print(f"\nPesos vol-parity por sleeve: {vp.round(2).to_dict()}")
    print(f"\nPORTAFOLIO OBJETIVO (β≈0, gross {target.abs().sum():.2f}):")
    t = target[target.abs() > 0.005].sort_values()
    for s, w in t.items():
        print(f"  {'SHORT' if w<0 else 'LONG ':5s} {s:12s} {w:+.3f}")
    # log a DB
    try:
        # β de REGRESIÓN del libro (neutralidad ≈+0.05) → ya no se hardcodea 0.0 (D1). β-dólar Σwβ aparte.
        beta_dollar = float((target.reindex(beta_last.index).fillna(0.0) * beta_last).sum())
        db = DB(); db.snapshot_portfolio(equity=None, gross=float(target.abs().sum()),
              net=float(target.sum()), beta=round(beta_model, 4), n_positions=int((target.abs()>0.005).sum()),
              detail={"tier": tier, "beta_dollar": round(beta_dollar, 4),
                      "weights": target[target.abs()>0.005].round(4).to_dict()})
        db.audit("INFO", "engine", f"Target portfolio {tier}", detail={"asof": str(asof)})
        print(f"\n→ Logueado en DB ({(target.abs()>0.005).sum()} posiciones)")
    except Exception as e:
        print(f"(DB log skip: {e})")


if __name__ == "__main__":
    main()
