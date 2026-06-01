"""
E32 — R3: ¿el RÉGIMEN RESCATA un candidato DESCARTADO? (2026-06-01)
Idea de Oscar: algunos descartados lo fueron por comportamiento DEPENDIENTE DE RÉGIMEN (cuartiles
inconsistentes). Si su edge es real pero solo en cierto viento, activarlo solo ahí podría rescatarlo.

Candidatos (los más "de régimen" con datos cacheados):
  - ls_crowd_rev (e16f): −z(count_long_short_ratio 14d). Contrarian a la masa retail. DESCARTADO por
    cuartiles inconsistentes [−0.98,+1.88,−0.31,+2.13] = firma de dependencia de régimen. 2023+.
  - tvl_pxdiv_14d (e26/e27): Δlog(TVL)−ret (acumulación on-chain). REAL pero modesto (+0.6%/mes), hoy
    en MODO SOMBRA. Cobertura ~12 tokens.

Disciplina (aprendizaje de R2): NO sweep masivo (sube la barra deflactada y mata edges modestos).
Solo POCAS hipótesis PRE-REGISTRADAS por teoría → N chico → barra alcanzable. Comparación sobre el
OVERLAP del candidato, con baseline EMPAREJADO al mismo período. Métrica = Sharpe (walk-forward
purgado + CPCV del regime_lab). Coste = maker (B1/B2 no atacan costos; eso es e30b/demo).

python -m research.e32_regime_rescue_discards
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve
from research.regime_lab import (build_base_sleeves, get_regimes, evaluate, conditional, deflation_bar)
from research.e16f_metrics_sleeves import load_metric_panel
from research.e26_onchain_tvl_check import load_tvl_panel

# HIPÓTESIS PRE-REGISTRADAS por teoría (N chico). (candidato, regime, favorable_state, racional)
HYPOTHESES = [
    ("ls_crowd_rev", "xs_disp_high", True,  "contrarian rinde con alta dispersión (más reversión)"),
    ("ls_crowd_rev", "mkt_bull",     False, "contrarian sufre en bull fuerte (la masa acierta el trend)"),
    ("ls_crowd_rev", "mkt_vol_high", True,  "la masa se desarma en estrés → contrarian cobra"),
    ("tvl_pxdiv_14d", "mkt_bull",     True,  "fundamental/acumulación cunde en risk-on"),
    ("tvl_pxdiv_14d", "mkt_vol_high", False, "fundamental se rompe en crisis de liquidez"),
]


def _orient(series):
    cut = int(series.dropna().shape[0] * 0.6)
    return series * (1.0 if series.dropna().iloc[:cut].mean() >= 0 else -1.0)


def build_candidates(C, ret, beta):
    cands = {}
    # ls_crowd_rev (metrics, 2023+)
    lsr = load_metric_panel("count_long_short_ratio", C)
    score = -((lsr - lsr.rolling(336).mean()) / lsr.rolling(336).std())
    s, _ = xs_sleeve(C, ret, beta, score.reindex(index=C.index, columns=C.columns), 336)
    cands["ls_crowd_rev"] = _orient(s)
    # tvl_pxdiv_14d (defillama, ~12 tokens)
    logtvl, toks = load_tvl_panel(C)
    retd_h = ret.reindex(columns=C.columns)
    tscore = logtvl.diff(336) - retd_h.rolling(336).sum()
    s2, _ = xs_sleeve(C, ret, beta, tscore, 336)
    cands["tvl_pxdiv_14d"] = _orient(s2)
    print(f"  ls_crowd_rev: {cands['ls_crowd_rev'].dropna().shape[0]} días · "
          f"tvl_pxdiv_14d: {cands['tvl_pxdiv_14d'].dropna().shape[0]} días (TVL toks={len(toks)})")
    return cands


def eval_overlap(base, cand):
    """Baseline EMPAREJADO + raw-candidate sobre el overlap del candidato. Devuelve (base_ref, raw_ref, idx)."""
    df = pd.concat([base, cand.rename("x")], axis=1).dropna()
    idx = df.index
    base_ref = evaluate(base.loc[idx], None, "base(overlap)")
    raw_ref = evaluate(base.loc[idx], cand.loc[idx], "raw")
    return base_ref, raw_ref, idx


def folds_wins(a, b):
    n = min(len(a["folds"]), len(b["folds"]))
    return sum(b["folds"][k] > a["folds"][k] for k in range(n)), n


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E32 — R3: ¿el régimen rescata un descartado? (hipótesis pre-registradas, N chico)\n" + "="*70)
    base = build_base_sleeves(); R = get_regimes()
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    print("Construyendo candidatos descartados...")
    cands = build_candidates(C, ret, beta)

    N = len(HYPOTHESES)
    print(f"\n{N} hipótesis pre-registradas (N chico → barra deflactada alcanzable).\n")

    results = []
    for cname in ["ls_crowd_rev", "tvl_pxdiv_14d"]:
        cand = cands[cname]
        base_ref, raw_ref, idx = eval_overlap(base, cand)
        rw, rn = folds_wins(base_ref, raw_ref)
        print(f"── {cname} · overlap {idx[0].date()}→{idx[-1].date()} ({len(idx)} días) ──")
        print(f"  baseline(overlap): Sharpe {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes")
        print(f"  + RAW (sin régimen): ΔSharpe {raw_ref['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
              f"Δmes {raw_ref['oos_mes']-base_ref['oos_mes']:+.2f} · folds {rw}/{rn}")
        for cn, rname, fav, rationale in [h for h in HYPOTHESES if h[0] == cname]:
            if rname not in R.columns:
                print(f"  [{rname}] régimen ausente"); continue
            cond = conditional(cand, R[rname], fav)
            r = evaluate(base.loc[idx], cond.loc[idx], f"{cname}×{rname}")
            w, n = folds_wins(base_ref, r)
            d = r["oos_sharpe"] - base_ref["oos_sharpe"]
            on = conditional(pd.Series(1.0, index=cand.index), R[rname], fav).reindex(idx).fillna(0).astype(bool).mean()
            results.append({"name": f"{cname}×{rname}[{'T' if fav else 'F'}]", "d": d, "w": w, "n": n,
                            "dmes": r["oos_mes"]-base_ref["oos_mes"], "on": on, "rationale": rationale})
            print(f"  cond × {rname:14s}[{'T' if fav else 'F'}] ΔSharpe {d:+.2f} · Δmes "
                  f"{r['oos_mes']-base_ref['oos_mes']:+.2f} · folds {w}/{n} · activo {on*100:.0f}%  ({rationale})")
        print()

    bar = deflation_bar([x["d"] for x in results], N)
    print(f"Barra DEFLACTADA (máx esperado bajo ruido de {N} hipótesis): {bar:+.2f} ΔSharpe\n")
    surv = [x for x in results if x["d"] > bar and x["w"] >= max(5, x["n"]-1)]
    print("SUPERVIVIENTES (ΔSharpe > barra Y folds ≥5/6):")
    if not surv:
        print("  NINGUNO. El régimen NO rescata a ls_crowd_rev ni a tvl_pxdiv_14d sobre el overlap.")
        best = max(results, key=lambda x: x["d"]) if results else None
        if best:
            print(f"  (mejor intento: {best['name']} ΔSharpe {best['d']:+.2f}, folds {best['w']}/{best['n']} — "
                  f"no alcanza). APRENDIZAJE: ni con régimen pre-registrado se rescatan; el descarte aguanta.")
    else:
        for x in surv:
            print(f"  ✅ {x['name']}: ΔSharpe {x['d']:+.2f}, folds {x['w']}/{x['n']} ({x['rationale']})")
        print("  → Candidato a SLEEVE CONDICIONAL. Validar forward/sombra antes de prod (regla de oro;")
        print("    ⚠️ ls_crowd_rev es 2023+ → cegaría el ancla al bear 2022, considerar en la decisión).")


if __name__ == "__main__":
    main()
