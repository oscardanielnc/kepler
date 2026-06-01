"""
E30d — ¿CONDICIONAR el sleeve de iliquidez a su RÉGIMEN favorable lo robustece OOS? (2026-06-01)
Idea de Oscar: la iliquidez da edge REAL pero DEPENDIENTE DEL RÉGIMEN (e30c: 3/6 folds, hueco Q2).
En vez de descartarla, activarla SOLO cuando el régimen está a su favor (conditional factor timing).

DISCIPLINA anti-overfit (cicatrices e25/e28):
- Régimen PRE-REGISTRADO por TEORÍA, no buscado: el premium de iliquidez se paga en mercados CALMOS
  y se destruye en estrés de liquidez → favorable = BAJA vol de mercado (BTC), desfavorable = ALTA vol.
- Umbral EX-ANTE: mediana EXPANDING de la vol (solo pasado), shift(1). NO se tunea para cazar Q2.
- Métrica = Sharpe (INVARIANTE al leverage) en purged walk-forward + CPCV → esquiva la trampa del
  ancla de e28 (donde el "edge de régimen" era el mecanismo leverage-al-ancla, no timing real).
- Se compara 7-base vs 8-raw vs 8-COND. Éxito = COND robustece los folds (3/6 → 5-6/6) Y mejora el
  OOS cronológico, SIN tunear. Si no → el régimen no salva a la iliquidez (y se archiva).

python -m research.e30d_illiquidity_regime
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

EMBARGO_D, BLOCK_D, INIT_FRAC = 10, 21, 0.40


def illiq_mean_score(absret, dvol, h):
    return np.log((absret / dvol.replace(0, np.nan)).rolling(h).mean().replace(0, np.nan))


def btc_vol_regime(C):
    """Régimen EX-ANTE de vol de mercado: vol 30d de BTC (diaria). favorable = BAJA vol
    (vol < mediana EXPANDING shift(1), solo pasado). Devuelve Series booleana diaria."""
    btc_d = C[DRIVER].resample("1D").last()
    vol = btc_d.pct_change().rolling(30).std()
    thr = vol.expanding(min_periods=120).median().shift(1)   # umbral solo-pasado, sin tunear
    return (vol < thr)                                        # True = régimen favorable (baja vol)


def build():
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); absret = ret.abs()
    P = load_panel(["volume", "taker_buy_volume", "quote_volume"], C); dvol = P["quote_volume"]
    s = {}
    s["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    s["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    s["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    s["carry"], _      = carry_sleeve(C, ret, beta)
    s["trend"], _      = trend_sleeve(C)
    s["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    s["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    il, _ = xs_sleeve(C, ret, beta, illiq_mean_score(absret, dvol, 14*24), 14*24)
    cut = int(il.dropna().shape[0]*0.6); il = il * (1.0 if il.dropna().iloc[:cut].mean() >= 0 else -1.0)
    base = pd.concat(s, axis=1); base.columns = list(s); base = base.dropna()
    # régimen ex-ante alineado al índice diario de los sleeves
    reg = btc_vol_regime(C).reindex(base.index, method="ffill").fillna(False)
    il = il.reindex(base.index)
    il_cond = il.where(reg, 0.0)        # iliquidez SOLO en régimen favorable (flat si desfavorable)
    return base, il, il_cond, reg


def walk_forward(df):
    T = len(df); init = int(INIT_FRAC * T); parts = []; i = init
    while i < T:
        train = df.iloc[:max(1, i - EMBARGO_D)]; test = df.iloc[i:i + BLOCK_D]
        if len(train) >= 60 and len(test) > 0:
            vp = vol_parity_weights(train, is_frac=1.0)
            parts.append((test * vp).sum(axis=1))
        i += BLOCK_D
    return pd.concat(parts).sort_index()


def anchored_stats(oos):
    L = leverage_for_maxdd_anchor(oos, config.TARGET_MAXDD); mm = metrics(oos * L)
    return mm["sharpe"], mm["ann"]/12, mm["maxdd"]


def cpcv(df, K=6):
    T = len(df); folds = np.array_split(np.arange(T), K); out = []
    for te in folds:
        lo, hi = te[0], te[-1]
        mask = np.ones(T, bool); mask[max(0, lo - EMBARGO_D):hi + 1 + EMBARGO_D] = False
        tr = df.iloc[mask]
        if len(tr) < 60: out.append(np.nan); continue
        vp = vol_parity_weights(tr, is_frac=1.0)
        out.append(metrics((df.iloc[lo:hi + 1] * vp).sum(axis=1)).get("sharpe", float("nan")))
    return out


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E30d — ¿condicionar iliquidez al régimen de vol (ex-ante) la robustece OOS?\n")
    base, il, il_cond, reg = build()
    df7  = base
    df8r = pd.concat([base, il.rename("illiq")], axis=1).dropna()
    df8c = pd.concat([base, il_cond.rename("illiq_cond")], axis=1).dropna()
    pct_on = float(reg.reindex(df8c.index).mean()) * 100
    print(f"{len(base)} días · régimen favorable (baja vol) activo {pct_on:.0f}% del tiempo\n")

    # sanity: ¿el régimen captura el hueco? Sharpe de illiq EN favorable vs desfavorable
    r = reg.reindex(il.index).fillna(False)
    def shp(x): x = x.dropna(); return x.mean()/x.std()*np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0.0
    print(f"SANITY (in-sample, solo para entender): illiq Sharpe en régimen FAVORABLE {shp(il[r]):+.2f} · "
          f"DESFAVORABLE {shp(il[~r]):+.2f}")
    print("  (si favorable >> desfavorable, el régimen pre-registrado SÍ separa; pero lo que decide es el OOS)\n")

    print("── IN-SAMPLE (@−10%) ──")
    for tag, d in [("7 base", df7), ("8 raw", df8r), ("8 COND", df8c)]:
        vp = vol_parity_weights(d, is_frac=1.0); c = (d * vp).sum(axis=1)
        L = leverage_for_maxdd_anchor(c, config.TARGET_MAXDD); mm = metrics(c * L)
        print(f"  {tag:<8s} Sharpe {mm['sharpe']:.2f} · @−10% {L:.2f}x → {mm['ann']/12:.2f}%/mes")

    print("\n── WALK-FORWARD OOS (re-anclado, Sharpe = métrica de edge) ──")
    res = {}
    for tag, d in [("7 base", df7), ("8 raw", df8r), ("8 COND", df8c)]:
        s_, mes_, dd_ = anchored_stats(walk_forward(d)); res[tag] = (s_, mes_, dd_)
        print(f"  {tag:<8s} Sharpe OOS {s_:.2f} · {mes_:.2f}%/mes · maxDD {dd_:.1f}%")
    print(f"  Δ raw  vs base: Sharpe {res['8 raw'][0]-res['7 base'][0]:+.2f}")
    print(f"  Δ COND vs base: Sharpe {res['8 COND'][0]-res['7 base'][0]:+.2f}  "
          f"(COND vs raw: {res['8 COND'][0]-res['8 raw'][0]:+.2f})")

    print("\n── CPCV (6 folds, OOS Sharpe a 1x) ──")
    f7, fr, fc = cpcv(df7), cpcv(df8r), cpcv(df8c)
    print(f"  {'fold':>5s} {'base':>7s} {'raw':>7s} {'COND':>7s} {'Δcond-base':>11s}")
    dr, dc = [], []
    for k in range(len(f7)):
        if any(np.isnan(x[k]) for x in (f7, fr, fc)): continue
        dr.append(fr[k]-f7[k]); dc.append(fc[k]-f7[k])
        print(f"  {k+1:>5d} {f7[k]:+7.2f} {fr[k]:+7.2f} {fc[k]:+7.2f} {fc[k]-f7[k]:+11.2f}")
    print(f"  raw  mejora base en {sum(d>0 for d in dr)}/{len(dr)} folds (Δ medio {np.mean(dr):+.2f})")
    print(f"  COND mejora base en {sum(d>0 for d in dc)}/{len(dc)} folds (Δ medio {np.mean(dc):+.2f})")

    print("\nVEREDICTO:")
    cond_better = res['8 COND'][0] > res['8 raw'][0] and sum(d>0 for d in dc) > sum(d>0 for d in dr)
    robust = sum(d>0 for d in dc) >= len(dc)*0.8 and res['8 COND'][0] > res['7 base'][0]
    if robust:
        print("  ✅ El régimen ROBUSTECE la iliquidez OOS (folds ≥80%+ y mejora cronológica). El conditional")
        print("     factor timing PRE-REGISTRADO funciona aquí → vale generalizarlo a otros sleeves (gran upside).")
    elif cond_better:
        print("  🟡 El régimen AYUDA (COND > raw) pero no llega a robusto. Señal de que la dirección es buena;")
        print("     evaluar otra variable de régimen pre-registrada o suavizar (reduce peso vs apagar).")
    else:
        print("  ⚠️ El régimen NO robustece la iliquidez OOS (COND no supera a raw de forma fiable).")
        print("     Confirma la cicatriz del sistema: el factor-timing de régimen no sobrevive honesto aquí.")
        print("     La iliquidez se archiva; pero el TEST de régimen queda montado para otros sleeves.")


if __name__ == "__main__":
    main()
