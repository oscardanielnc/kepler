"""
E38 — BLEND CROSS-FAMILY (doctrina Medallion, hecha bien). 2026-06-01.
e37 mostró que combinar 3 señales de la MISMA familia (on-chain pxdiv) NO diversifica (correladas
entre sí). La doctrina exige componentes de FAMILIAS distintas, uncorr entre sí. Aquí re-evaluamos
DESCARTADOS como COMPONENTES (idea de Oscar), uno por familia económica:

  on-chain     : tvl_pxdiv_14d        (e26/e27,  +0.30/4-6 solo)
  microestructura: orderbook imb1_5d  (e24, contrarian, +0.00 taker solo pero Sharpe ~1.3 standalone)
  positioning  : ls_crowd_rev_14d     (e16f, OI/long-short contrarian, +0.10/5-6 solo)
  liquidez     : illiq_14d            (e30, Amihud, +0.18/3-6 solo)

DIAGNÓSTICO HEADLINE: matriz de correlación entre los 4. Si son uncorr → el blend puede ser robusto
(≥5/6 folds) donde ninguno lo es solo. Si están correlados → la doctrina no aplica aquí tampoco.
⚠️ order-book y OI son 2023+ → se evalúa sobre el OVERLAP, con baseline emparejado. OOS purgado + CPCV.

python -m research.e38_crossfamily_blend
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, xs_sleeve, load_panel
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.regime_lab import build_base_sleeves, evaluate, _walk_forward_oos, _cpcv_sharpes, _anchored
from research.e26_onchain_tvl_check import load_tvl_panel
from research.e24_orderbook_sleeve import load_ob_panels
from research.e16f_metrics_sleeves import load_metric_panel


def oriented(C, ret, beta, score, hold):
    s, _ = xs_sleeve(C, ret, beta, score, hold)
    cut = int(s.dropna().shape[0]*0.6); sgn = 1.0 if s.dropna().iloc[:cut].mean() >= 0 else -1.0
    return (s * sgn).rename("x")


def evaluate_on(base, extra, idx, label):
    """evaluate restringido a un índice (overlap)."""
    b = base.loc[base.index.isin(idx)]
    e = extra.loc[extra.index.isin(idx)] if extra is not None else None
    return evaluate(b, e, label)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E38 — BLEND CROSS-FAMILY (4 familias, re-evaluando descartados como componentes)\n" + "="*70)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); retd = ret.reindex(columns=C.columns)
    dvol = load_panel(["quote_volume"], C)["quote_volume"]; absret = ret.abs()
    H = 14*24

    # ── construir los 4 componentes (mini-sleeves oriented) ──
    print("Construyendo 4 componentes cross-family...")
    logtvl, t_tvl = load_tvl_panel(C)
    comp = {}
    comp["onchain_tvl"]   = oriented(C, ret, beta, logtvl.diff(H) - retd.rolling(H).sum(), H)
    ob, t_ob = load_ob_panels(C)
    comp["microstr_ob"]   = oriented(C, ret, beta, -ob["imb1"], 5*24)
    lsr = load_metric_panel("count_long_short_ratio", C)
    comp["positioning_oi"]= oriented(C, ret, beta, -((lsr - lsr.rolling(H).mean())/lsr.rolling(H).std()), H)
    comp["liquidity_illq"]= oriented(C, ret, beta, np.log((absret/dvol.replace(0,np.nan)).rolling(H).mean().replace(0,np.nan)), H)
    print(f"  cobertura: TVL {len(t_tvl)} · order-book {len(t_ob)} cadenas/símbolos")

    # ── overlap: order-book y OI son 2023+ (los que mandan) ──
    ob_cov = ob["imb1"].notna().any(axis=1); ob_start = C.index[ob_cov][0].normalize()
    oi_cov = lsr.notna().any(axis=1); oi_start = C.index[oi_cov][0].normalize()
    start = max(ob_start, oi_start)
    base = build_base_sleeves()
    idx = base.index[base.index >= start]
    print(f"  overlap evaluación: {idx[0].date()} → {idx[-1].date()} ({len(idx)} días)\n")

    CM = pd.concat(comp, axis=1); CM.columns = list(comp)
    CM = CM.loc[CM.index.isin(idx)].dropna()

    # ── DIAGNÓSTICO HEADLINE: correlación entre componentes ──
    print("── MATRIZ DE CORRELACIÓN entre componentes (¿uncorr = doctrina aplica?) ──")
    corr = CM.corr()
    print(corr.round(2).to_string())
    offdiag = corr.where(~np.eye(len(corr), dtype=bool)).abs()
    print(f"  corr |media| fuera de diagonal: {np.nanmean(offdiag.values):.2f} · máx: {np.nanmax(offdiag.values):.2f}")
    print(f"  (uncorr <~0.2 → diversifican; altas → no aporta combinar, misma info)\n")

    # ── baseline emparejado al overlap ──
    base_ref = evaluate_on(base, None, idx, "7 base(overlap)")
    nf = len(base_ref["folds"])
    print(f"BASELINE 7 (overlap, OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · "
          f"{base_ref['oos_mes']:.2f}%/mes · CPCV {base_ref['fold_mean']:+.2f} ({nf} folds)\n")

    # ── componentes solos en el overlap ──
    print("── Componentes SOLOS (overlap, ΔSharpe OOS · folds) ──")
    for name in comp:
        r = evaluate_on(base, comp[name], idx, name)
        fw = sum(a > b for a, b in zip(r["folds"], base_ref["folds"]))
        print(f"  {name:16s} ΔSharpe {r['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · CPCV {fw}/{nf}")

    # ── (A) blend de retornos (vol-parity) · (B) composite de señal (z-avg de los retornos estandarizados) ──
    print("\n── BLEND de los 4 (cross-family) ──")
    blend_ret = (CM * vol_parity_weights(CM)).sum(axis=1).rename("x")
    rA = evaluate_on(base, blend_ret, idx, "blend4_ret")
    fwA = sum(a > b for a, b in zip(rA["folds"], base_ref["folds"]))
    print(f"  blend4 (vol-parity ret): ΔSharpe {rA['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
          f"{rA['oos_mes']-base_ref['oos_mes']:+.2f}%/mes · CPCV {fwA}/{nf}")

    # equal-weight también (por si vol-parity sobre-pondera el ruidoso)
    blend_ew = CM.div(CM.std()).mean(axis=1).rename("x")
    rEW = evaluate_on(base, blend_ew, idx, "blend4_ew")
    fwEW = sum(a > b for a, b in zip(rEW["folds"], base_ref["folds"]))
    print(f"  blend4 (equal-weight)  : ΔSharpe {rEW['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
          f"{rEW['oos_mes']-base_ref['oos_mes']:+.2f}%/mes · CPCV {fwEW}/{nf}")

    print("\nVEREDICTO (doctrina cross-family):")
    bestfw = max(fwA, fwEW); bestd = max(rA['oos_sharpe'], rEW['oos_sharpe']) - base_ref['oos_sharpe']
    avgcorr = np.nanmean(offdiag.values)
    if bestd > 0 and bestfw >= max(5, nf-1):
        print(f"  ✅ EL BLEND CROSS-FAMILY ES ROBUSTO (Δ {bestd:+.2f}, {bestfw}/{nf}) donde los solos no.")
        print(f"     corr media {avgcorr:.2f} → la diversificación cross-family funcionó. Candidato sleeve #8 (overlap 2023+).")
    elif avgcorr < 0.2 and bestd > 0:
        print(f"  🟡 Componentes uncorr (corr {avgcorr:.2f}) y blend positivo (Δ {bestd:+.2f}) pero {bestfw}/{nf} folds.")
        print(f"     Cerca; añadir más familias uncorr podría cruzarlo. Documentar el horizonte de componentes.")
    else:
        print(f"  ⚠️ El blend cross-family no cruza el umbral (Δ {bestd:+.2f}, {bestfw}/{nf}, corr media {avgcorr:.2f}).")
        print(f"     Aprendizaje honesto: ni mezclando familias el blend supera al núcleo robusto de 7.")


if __name__ == "__main__":
    main()
