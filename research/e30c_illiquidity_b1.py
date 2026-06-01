"""
E30c — B1 (walk-forward purgado + embargo + CPCV) sobre el sleeve de ILIQUIDEZ: ¿el aporte OOS es
HONESTO o artefacto del régimen reciente? (2026-06-01). e30/e30b: iliquidez = real, ortogonal,
barata (6x turnover), sobrevive coste realista en +0.18%/mes — pero IS<OOS (edge OOS-cargado) y
hueco en Q2. B1 es el test que decide: fija vp+leverage SOLO con el pasado (embargo 10d) y mide el
combo en el futuro no visto, comparando 7 vs 8 sleeves.

Pregunta concreta: ¿el 8-combo (con iliquidez) tiene MEJOR Sharpe/%/mes OOS que el 7-combo, de forma
robusta por folds? Si el aporte solo aparece in-sample o en 1-2 folds → es overfit/régimen → archivar.

Coste = MAKER (como e29; B1/B2 NO atacan el gap por costos — eso lo hizo e30b y la DEMO).
python -m research.e30c_illiquidity_b1
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

EMBARGO_D, BLOCK_D, INIT_FRAC = 10, 21, 0.40


def illiq_mean_score(absret, dvol, h):
    return np.log((absret / dvol.replace(0, np.nan)).rolling(h).mean().replace(0, np.nan))


def build_sleeves():
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
    # iliquidez (signo + = long ilíquido, premium de Amihud; orientado en IS por seguridad)
    il, _ = xs_sleeve(C, ret, beta, illiq_mean_score(absret, dvol, 14*24), 14*24)
    cut = int(il.dropna().shape[0]*0.6); il = il * (1.0 if il.dropna().iloc[:cut].mean() >= 0 else -1.0)
    s["illiq_14d"] = il
    df = pd.concat(s, axis=1); df.columns = list(s)
    return df.dropna()


def walk_forward(df):
    """Stitch OOS a 1x (vp solo-pasado, embargo). Devuelve (serie_oos_1x, lev_medio_anclado)."""
    T = len(df); init = int(INIT_FRAC * T); parts = []; levs = []; i = init
    while i < T:
        train = df.iloc[:max(1, i - EMBARGO_D)]; test = df.iloc[i:i + BLOCK_D]
        if len(train) >= 60 and len(test) > 0:
            vp = vol_parity_weights(train, is_frac=1.0)
            parts.append((test * vp).sum(axis=1))
            levs.append(leverage_for_maxdd_anchor((train * vp).sum(axis=1), config.TARGET_MAXDD))
        i += BLOCK_D
    return pd.concat(parts).sort_index(), float(np.mean(levs))


def anchored_stats(oos_1x):
    """Re-ancla la curva OOS a −10% y reporta (Sharpe, %/mes, maxDD, lev)."""
    L = leverage_for_maxdd_anchor(oos_1x, config.TARGET_MAXDD)
    mm = metrics(oos_1x * L)
    return mm["sharpe"], mm["ann"]/12, mm["maxdd"], L


def cpcv(df, K=6):
    T = len(df); folds = np.array_split(np.arange(T), K); out = []
    for te in folds:
        lo, hi = te[0], te[-1]
        mask = np.ones(T, bool); mask[max(0, lo - EMBARGO_D):hi + 1 + EMBARGO_D] = False
        tr = df.iloc[mask]
        if len(tr) < 60: out.append(np.nan); continue
        vp = vol_parity_weights(tr, is_frac=1.0)
        r = (df.iloc[lo:hi + 1] * vp).sum(axis=1)
        out.append(metrics(r).get("sharpe", float("nan")))
    return out


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E30c — B1 walk-forward purgado: ¿la iliquidez aporta OOS honesto? (7 vs 8 sleeves)\n")
    df8 = build_sleeves(); df7 = df8.drop(columns=["illiq_14d"])
    print(f"{len(df8)} días ({df8.index[0].date()} → {df8.index[-1].date()}) · embargo {EMBARGO_D}d · bloque {BLOCK_D}d\n")

    # ── IN-SAMPLE (referencia) ──
    print("── IN-SAMPLE (vp+lev sobre todo) ──")
    for tag, d in [("7 sleeves", df7), ("8 (+illiq)", df8)]:
        vp = vol_parity_weights(d, is_frac=1.0); c = (d * vp).sum(axis=1)
        L = leverage_for_maxdd_anchor(c, config.TARGET_MAXDD); mm = metrics(c * L)
        print(f"  {tag:<12s} Sharpe {mm['sharpe']:.2f} · @−10% {L:.2f}x → {mm['ann']/12:.2f}%/mes · maxDD {mm['maxdd']:.1f}%")

    # ── WALK-FORWARD OOS (re-anclado) ──
    print("\n── WALK-FORWARD OOS (vp+lev solo-pasado, re-anclado a −10%) ──")
    oos7, lev7 = walk_forward(df7); oos8, lev8 = walk_forward(df8)
    s7, mes7, dd7, L7 = anchored_stats(oos7); s8, mes8, dd8, L8 = anchored_stats(oos8)
    print(f"  {'7 sleeves':<12s} Sharpe OOS {s7:.2f} · {mes7:.2f}%/mes · maxDD {dd7:.1f}% · lev-medio-train {lev7:.2f}x")
    print(f"  {'8 (+illiq)':<12s} Sharpe OOS {s8:.2f} · {mes8:.2f}%/mes · maxDD {dd8:.1f}% · lev-medio-train {lev8:.2f}x")
    print(f"  Δ por añadir iliquidez:  Sharpe {s8-s7:+.2f} · {mes8-mes7:+.2f}%/mes · maxDD {dd8-dd7:+.1f}pp")

    # ── CPCV por fold (7 vs 8) ──
    print("\n── CPCV-lite (6 folds, OOS Sharpe a 1x) ──")
    f7, f8 = cpcv(df7), cpcv(df8)
    print(f"  {'fold':>6s} {'7':>7s} {'8':>7s} {'Δ':>7s}")
    deltas = []
    for k, (a, b) in enumerate(zip(f7, f8)):
        if np.isnan(a) or np.isnan(b): continue
        deltas.append(b - a); print(f"  {k+1:>6d} {a:+7.2f} {b:+7.2f} {b-a:+7.2f}")
    pos = sum(d > 0 for d in deltas)
    print(f"  → iliquidez mejora el Sharpe OOS en {pos}/{len(deltas)} folds · Δ medio {np.mean(deltas):+.2f}")

    # ── VEREDICTO ──
    print("\nVEREDICTO B1:")
    edge_ok = (s8 - s7) > 0.02 and mes8 > mes7 and pos >= len(deltas) * 0.6
    if edge_ok:
        print(f"  ✅ El aporte de iliquidez SOBREVIVE el walk-forward purgado: Sharpe OOS {s8-s7:+.2f}, "
              f"{mes8-mes7:+.2f}%/mes, {pos}/{len(deltas)} folds+. No es solo in-sample/régimen.")
        print(f"  → Candidato LEGÍTIMO a sleeve #8 (modesto pero real, barato, sin datos nuevos).")
    else:
        print(f"  ⚠️ El aporte NO es robusto OOS (Sharpe {s8-s7:+.2f}, {mes8-mes7:+.2f}%/mes, {pos}/{len(deltas)} folds+).")
        print(f"  → El +0.18 in-sample no se confirma honesto → archivar o modo sombra (no a producción).")
    print(f"  maxDD OOS 8-combo {dd8:.1f}% (objetivo −10%): {'añadir iliquidez no empeora el ancla' if dd8 >= dd7 - 0.5 else 'ojo, empeora la optimismo del ancla'}.")


if __name__ == "__main__":
    main()
