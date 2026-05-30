"""
E16d — Ronda 3 de sleeves ortogonales (2026-05-30). Continúa e16/e16b/e16c.
Lección previa: las señales de PRECIO salen correlacionadas; las de FLUJO/microestructura no
(taker_flow pasó). Aquí más señales de OHLC+count+flujo, buscando otra fuente que sume.

CRITERIO ACTUALIZADO (regla del ancla de maxDD): un candidato no basta con pasar corr<0.35 +
walk-forward IS/OOS>0.10; debe **mejorar el retorno al maxDD anclado (−10%)**. Con vol-parity,
añadir un sleeve de menor Sharpe puede DILUIR al combinado aunque sea ortogonal → menos retorno
al mismo riesgo. Por eso medimos ann@−10% antes/después.

python -m research.e16d_round3_sleeves
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


def sh_isoos(r):
    r = r.dropna(); cut = int(len(r) * 0.6)
    f = lambda x: x.mean() / x.std() * np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0.0
    return f(r), f(r.iloc[:cut]), f(r.iloc[cut:])


def anchored(combo):
    """ann% al maxDD objetivo (−10%) y leverage usado."""
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    return metrics(combo * L)["ann"], L


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E16d — Ronda 3 de sleeves ortogonales (criterio: mejorar el retorno al maxDD −10%)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"], C)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h\n")

    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta,
        alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base_df = pd.concat(base, axis=1); base_df.columns = list(base.keys()); base_df = base_df.dropna()
    combo0 = (base_df * vol_parity_weights(base_df)).sum(axis=1)
    m0 = metrics(combo0); ann0, L0 = anchored(combo0)
    print(f"BASELINE (6 sleeves): Sharpe {m0['sharpe']:.2f} · maxDD {m0['maxdd']:.1f}% (1x)")
    print(f"  @−10% maxDD: {L0:.2f}x → ann {ann0:.1f}% (~{ann0/12:.2f}%/mes)\n")

    hi, lo, cl = P["high"], P["low"], P["close"]
    rng = (hi - lo).replace(0, np.nan)
    flow = (P["taker_buy_volume"] / P["volume"].replace(0, np.nan)) - 0.5
    tsize = P["quote_volume"] / P["count"].replace(0, np.nan)
    cands = {
        "close_loc_5d":  (((cl - lo) / rng - 0.5).rolling(120).mean(), 120),
        "count_mom_5d":  (np.log(P["count"].replace(0, np.nan)).diff().rolling(120).sum(), 120),
        "tradesize_mom": (np.log(tsize).diff().rolling(120).sum(), 120),
        "range_lowvol":  (-(rng / cl).rolling(336).mean(), 336),
        "flow_accel":    (flow.rolling(120).mean() - flow.rolling(120).mean().shift(120), 120),
        "hl_position":   ((cl - cl.rolling(336).min()) / (cl.rolling(336).max() - cl.rolling(336).min()) - 0.5, 336),
    }

    print("CANDIDATOS — filtro (Sh/IS/OOS, corr) + aporte al retorno ANCLADO (−10%):")
    print(f"  {'sleeve':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} "
          f"{'filtro':>7s} {'ann@-10%':>9s} {'Δ%/mes':>7s}")
    keep = {}
    for name, (score, hold) in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score.reindex(index=C.index, columns=C.columns), hold)
        except Exception as e:
            print(f"  {name:16s} ERROR: {str(e)[:42]}"); continue
        j = pd.concat({**base, name: s_ret}, axis=1)
        j.columns = list(base.keys()) + [name]; j = j.dropna()
        if j[name].std() == 0:
            print(f"  {name:16s} constante/vacío"); continue
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        sh, i, o = sh_isoos(j[name])
        passes = (i > 0.10 and o > 0.10 and cmax < 0.35)
        combo = (j * vol_parity_weights(j)).sum(axis=1)
        ann, L = anchored(combo)
        dmes = (ann - ann0) / 12
        flag = "SÍ" if passes else "no"
        print(f"  {name:16s} {sh:6.2f} {i:6.2f} {o:6.2f} {cmax:6.2f} {cwho:>12s} "
              f"{flag:>7s} {ann:8.1f}% {dmes:+7.2f}")
        # IMPLEMENTABLE solo si pasa filtro Y mejora el retorno anclado de forma material (>+0.10%/mes)
        if passes and dmes > 0.10:
            keep[name] = (s_ret, dmes)

    if not keep:
        print("\n→ VEREDICTO: ningún candidato MEJORA el retorno al maxDD anclado de forma material")
        print("  (>+0.10%/mes). Varios pasan corr+walk-forward pero DILUYEN (menor Sharpe propio que")
        print("  takerflow → vol-parity baja el retorno al mismo riesgo). La veta OHLCV está agotada.")
        print("  PRÓXIMO SALTO: fuente de datos NUEVA — Open Interest / long-short ratio")
        print("  (data.binance.vision/.../futures/um/daily/metrics/) → extender kepler/fetch.py.")
        return

    print(f"\nIMPLEMENTABLES (pasan filtro Y suben el retorno anclado): {list(keep)}")
    for n, (_, d) in keep.items():
        print(f"  {n}: +{d:.2f}%/mes al maxDD −10%")
    print("\n  REGLA DE ORO: estrés (e16c-style) + validar OOS antes de implementar el ganador.")


if __name__ == "__main__":
    main()
