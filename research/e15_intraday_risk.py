"""
E15 — MONITOR DE RIESGO INTRADÍA (INTRADAY.md §7, 2026-06-02). Desbloqueado por el backtester horario
(e42 reconcilia, corr 1.000). El sistema rebalancea 1×/24h; entre rebalanceos el libro queda fijo y el
único control es el circuit breaker (hoy evaluado en el ciclo). PREGUNTAS (riesgo, NO alfa):
  1. ¿Existe el problema? Distribución de DRAWDOWNS INTRADÍA del libro (caída dentro del bloque de 24h) y
     ¿revierten antes del próximo rebalanceo? (β≈0 → el DD direccional debería ser raro.)
  2. ¿Un HARD-HALT más rápido (horario) reduce el maxDD realizado — NETO de whipsaw? Probar umbrales.
  3. La TRAMPA: en un libro market-neutral los DD intradía suelen REVERTIR → un halt rápido fija pérdidas
     en el fondo y pierde el rebote. Cuantificar: ¿los DD profundos CONTINÚAN (cola real) o revierten?
LÍNEA ROJA: solo HARD-HALT en extremos (rail de seguridad), NO de-risking por vol (gate de régimen = descartado).

Reconstruye el libro DIARIO real (pesos agregados de los 7 sleeves, rebal 24h, MTM horario buy-and-hold).
No toca producción. python -m research.e15_intraday_risk
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, _weights_from_score, load_panel, _cap_normalize,
                           compute_target, CARRY_SMOOTH, DRIVER, BETA_W)
from kepler.portfolio import metrics, leverage_for_maxdd_anchor

REBAL_H = 24   # cadencia del libro (1×/día)


def reconstruct_daily_weights(C, ret, beta, panels, vp, lev):
    """Pesos AGREGADOS del libro (×lev) en cada punto de rebalanceo (cada 24h), reconstruyendo los pesos
    de cada sleeve AL DÍA (como compute_target, que se llama a diario). Devuelve DataFrame (t × símbolo)."""
    syms = [s for s in C.columns if s != DRIVER]
    cols = list(C.columns)
    # scores xs (por día)
    scores = {
        "mom_30d": alphas.xs_momentum_score(ret, 720),
        "rev_60d": alphas.xs_reversal_score(ret, 1440),
        "lowvol_14d": alphas.xs_lowvol_score(ret, 336),
        "takerflow_5d": alphas.xs_takerflow_score(panels["volume"], panels["taker_buy_volume"], 120),
        "hlpos_14d": alphas.xs_hlposition_score(C, 336),
    }
    # trend: pesos diarios CAPADOS (mirror engine.trend_sleeve)
    px = C.resample("1D").last(); rtd = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0); vol = rtd.rolling(30).std()
    pos = (sig.shift(1) * (0.20/np.sqrt(365)/vol).clip(0, 3)).fillna(0)
    TW = pos.copy()
    for i in range(len(pos)):
        TW.iloc[i] = _cap_normalize(pos.iloc[i].values.astype(float), config.MAX_WEIGHT_NORMAL)
    # carry: pesos en grid 8h (mirror engine.carry_sleeve)
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns: continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True); fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    Fs = F.rolling(CARRY_SMOOTH, min_periods=1).mean()
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    cbet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)

    idx = list(range(BETA_W + 1440, len(C) - REBAL_H, REBAL_H))   # arranca tras el lookback más largo
    rows = {}
    for t in idx:
        ts = C.index[t]; W = pd.Series(0.0, index=cols)
        for name, sc in scores.items():
            w, h = _weights_from_score(sc.iloc[t], beta.iloc[t], syms)
            full = w.reindex(cols).fillna(0.0); full[DRIVER] = full.get(DRIVER, 0.0) + h
            W = W.add(float(vp[name]) * full, fill_value=0.0)
        # trend (día calendario ≤ ts)
        day = TW.index[TW.index <= ts]
        if len(day): W = W.add(float(vp["trend"]) * TW.loc[day[-1]].reindex(cols).fillna(0.0), fill_value=0.0)
        # carry (punto 8h ≤ ts)
        s8 = Fs.index[Fs.index <= ts]
        if len(s8):
            cw, ch = alphas.carry_weights(Fs[syms].loc[s8[-1]], cbet.loc[s8[-1]], config.MAX_WEIGHT_NORMAL)
            cfull = cw.reindex(cols).fillna(0.0); cfull[DRIVER] = cfull.get(DRIVER, 0.0) + ch
            W = W.add(float(vp["carry"]) * cfull, fill_value=0.0)
        rows[ts] = W * lev
    return pd.DataFrame(rows).T.reindex(columns=cols).fillna(0.0)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E15 — monitor de riesgo intradía: ¿DD intradía real y un hard-halt rápido ayuda?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    panels = load_panel(["volume", "taker_buy_volume"], C)
    _, vp, _, _, _, lev_prod, _, _, _ = compute_target("ESTABLE")

    # Construir el libro a 1x (pesos sin leverage) y MTM horario buy-and-hold
    W1 = reconstruct_daily_weights(C, ret, beta, panels, vp, 1.0)
    R = C.pct_change().reindex(C.index)
    Wh = W1.reindex(C.index, method="ffill")
    block_id = pd.Series(np.nan, index=C.index); block_id.loc[W1.index] = np.arange(len(W1))
    block_id = block_id.ffill()
    book_r1 = (Wh.shift(1) * R).sum(axis=1)
    turn = (W1 - W1.shift(1)).abs().sum(axis=1).fillna(0.0)
    cost = pd.Series(0.0, index=C.index); cost.loc[W1.index] = turn.values * config.MAKER_FEE
    book_r1 = (book_r1 - cost).reindex(C.index).fillna(0.0).loc[W1.index[0]:]
    block_id = block_id.loc[book_r1.index]

    # ── RECONCILIACIÓN (honesta): el libro DIARIO-rebalanceado mide retornos diarios REALES; difiere del
    #    motor (que mide por bloque-hold, serie diaria a saltos). Anclar el leverage sobre ESTA serie para
    #    que el baseline quede al maxDD objetivo (comparable a producción). ──────────────────────────────
    daily1 = (1 + book_r1).cumprod().resample("1D").last().ffill().pct_change().dropna()
    m1 = metrics(daily1)
    lev = min(config.LEVERAGE_HAIRCUT * leverage_for_maxdd_anchor(daily1, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    book_r = book_r1 * lev
    eq = (1 + book_r).cumprod()
    daily = (1 + book_r).cumprod().resample("1D").last().ffill().pct_change().dropna()
    m = metrics(daily)
    btc_d = C[DRIVER].resample("1D").last().pct_change().reindex(daily.index)
    j = pd.concat([daily, btc_d], axis=1).dropna(); j.columns = ["p", "b"]
    bbeta = float(np.cov(j["p"], j["b"])[0, 1] / np.var(j["b"]))
    print(f"vp={ {k: round(float(v),2) for k,v in vp.items()} }")
    print(f"RECONCILIACIÓN: libro diario-rebalanceado a 1x → Sharpe {m1['sharpe']:.2f} · maxDD {m1['maxdd']:.1f}%")
    print(f"  (motor hold-block 1x = Sharpe 2.07 / maxDD −5.1%; el diario-real es más ruidoso = honesto,")
    print(f"   mide retornos diarios reales no bloques a saltos). Anclado aquí a maxDD objetivo: lev {lev:.2f}x.")
    print(f"LIBRO @{lev:.2f}x: Sharpe {m['sharpe']:.2f} · maxDD {m['maxdd']:.1f}% · ann {m['ann']:.1f}% · β {bbeta:+.3f}\n")

    # ── 1) DISTRIBUCIÓN de DD INTRADÍA (dentro de cada bloque de 24h) ──────────
    intra_dd = []; recovered = 0; continued = 0
    for b, g in eq.groupby(block_id):
        if len(g) < 2: continue
        start = g.iloc[0]; mn = g.min(); end = g.iloc[-1]
        dd = mn/start - 1.0; intra_dd.append(dd)
        if dd < -0.01:                                   # bloques con DD intradía notable
            (recovered if end >= mn*1.002 else 0)        # placeholder
            if end > mn: recovered += 1
            else: continued += 1
    idd = pd.Series(intra_dd)
    print("1) DRAWDOWN INTRADÍA (mín dentro del bloque de 24h, vs inicio del bloque):")
    print(f"   bloques {len(idd)} · mediana {idd.median()*100:.2f}% · p10 {idd.quantile(.10)*100:.2f}% · "
          f"p01 {idd.quantile(.01)*100:.2f}% · PEOR {idd.min()*100:.2f}%")
    for thr in [0.01, 0.02, 0.03, 0.05]:
        n = int((idd < -thr).sum())
        print(f"   bloques con DD intradía < -{thr*100:.0f}%: {n} ({n/len(idd)*100:.1f}%)")
    print(f"   de los DD intradía notables (>1%): {recovered} RECUPERARON algo / {continued} siguieron al cierre "
          f"→ {'mayormente REVIERTEN (trampa de whipsaw)' if recovered>continued else 'tienden a CONTINUAR'}\n")

    # ── 2) HARD-HALT INTRADÍA vs baseline: maxDD y retorno por umbral ──────────
    def simulate(H):
        """Halt: si el DD desde el pico supera H en alguna hora, a CASH el resto del bloque; re-entra al
        siguiente rebalanceo. H=None → sin halt (baseline)."""
        e = 1.0; pk = 1.0; halted = False; prev_b = None; out = []
        br = book_r.values; bid = block_id.values
        for i in range(len(br)):
            if bid[i] != prev_b:
                halted = False; prev_b = bid[i]          # nuevo bloque: re-entra
            r = 0.0 if halted else br[i]
            e *= (1 + r); pk = max(pk, e); out.append(e)
            if H is not None and not halted and (e/pk - 1) < -H:
                halted = True
        s = pd.Series(out, index=book_r.index)
        d = s.resample("1D").last().ffill().pct_change().dropna()
        mm = metrics(d)
        return mm["sharpe"], mm["ann"], mm["maxdd"], (s.iloc[-1]-1)*100

    print("2) HARD-HALT intradía (a cash el resto del bloque si el DD desde el pico supera H):")
    print(f"   {'umbral H':>10s} {'Sharpe':>7s} {'ann%':>7s} {'maxDD%':>8s} {'retorno_tot%':>12s}")
    sh0, an0, dd0, tot0 = simulate(None)
    print(f"   {'BASELINE':>10s} {sh0:7.2f} {an0:7.1f} {dd0:8.1f} {tot0:12.1f}  (sin halt)")
    for H in [0.04, 0.06, 0.08, 0.12]:
        sh, an, dd, tot = simulate(H)
        better = "  ← maxDD↓" if dd > dd0 + 0.3 and an > an0 - 2 else ("  whipsaw" if an < an0 - 3 else "")
        print(f"   {('-'+str(int(H*100))+'%'):>10s} {sh:7.2f} {an:7.1f} {dd:8.1f} {tot:12.1f}{better}")

    print("\nLECTURA: si ningún H baja el maxDD sin matar el retorno → el CB diario (−20%) basta y el halt")
    print("intradía es whipsaw (esperado en β≈0). Si algún H baja el maxDD a coste pequeño → rail útil para")
    print("colas. El valor copy-lead es protección de cola DEMOSTRABLE, aunque dispare rarísimo.")


if __name__ == "__main__":
    main()
