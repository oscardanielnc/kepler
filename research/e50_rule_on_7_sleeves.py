"""
E50 — Aplica la REGLA universo por-sleeve (kepler-per-sleeve-universe-rule, validada en e49) a los 7
sleeves OFICIALES. Pregunta de Oscar: ¿algún sleeve mejora (más retorno al MISMO maxDD) si excluye sus
monedas-estorbo? ¿deben estar todas las monedas en cada sleeve?

DISCIPLINA ANTI-OVERFIT (esto apunta a PRODUCCIÓN → regla de oro):
  - SELECCIÓN de estorbadores SOLO en IS (primer 60%); VALIDACIÓN solo en OOS (último 40%).
  - Estorbador = coin cuya EXCLUSIÓN sube el Δ%/mes anclado del COMBINADO en IS por > umbral.
  - Métrica primaria = Sharpe COMBINADO (independiente del leverage → evita el artefacto del ancla, e48);
    secundaria = %/mes anclado. Solo cuenta si el OOS mejora.
  - Cobertura: los 5 sleeves XS (score por-coin → NaN limpio). carry/trend tienen universo interno
    (funding / EMA long-only) → quedan fuera de este pase (requerirían refactor; se anota).
Resultado = lista de cambios CANDIDATOS; NINGUNO va a prod sin walk-forward purgado + deflación después.

python -m research.e50_rule_on_7_sleeves
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

THRESH_IS = 0.05      # mejora mínima en IS (%/mes) para marcar un coin como estorbo


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), m.get("maxdd", float("nan"))


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E50 — REGLA universo por-sleeve aplicada a los 7 oficiales (selección IS / validación OOS)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["quote_volume", "volume", "taker_buy_volume"], C)
    syms = [c for c in C.columns if c != "BTCUSDT"]

    # builders de score de los 5 XS sleeves (los que admiten exclusión por-coin limpia)
    builders = {
        "mom_30d":      (lambda ex: _mask(alphas.xs_momentum_score(ret, 720), ex), 720),
        "rev_60d":      (lambda ex: _mask(alphas.xs_reversal_score(ret, 1440), ex), 1440),
        "lowvol_14d":   (lambda ex: _mask(alphas.xs_lowvol_score(ret, 336), ex), 336),
        "takerflow_5d": (lambda ex: _mask(alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), ex), 120),
        "hlpos_14d":    (lambda ex: _mask(alphas.xs_hlposition_score(C, 336), ex), 336),
    }

    def _series(name, ex=()):
        b, hold = builders[name]
        s, _ = xs_sleeve(C, ret, beta, b(ex), hold); return s

    # 7 sleeves base (carry/trend fijos; los 5 XS reconstruibles)
    base = {n: _series(n) for n in builders}
    base["carry"], _ = carry_sleeve(C, ret, beta)
    base["trend"], _ = trend_sleeve(C)
    order = list(base)

    def combined(over=None):
        d = dict(base); d.update(over or {})
        bdf = pd.concat(d, axis=1); bdf.columns = list(d); bdf = bdf.dropna()
        return (bdf * vol_parity_weights(bdf)).sum(axis=1)

    c0 = combined()
    a_full, dd_full = anchored(c0); a_oos, _ = anchored(seg(c0, .6, 1))
    print(f"BASELINE 7 (todas las monedas): Sharpe {metrics(c0)['sharpe']:.2f} (OOS {sh(seg(c0,.6,1)):.2f}) · "
          f"@−10% {a_full/12:.2f}%/mes (OOS {a_oos/12:.2f}) · maxDD {dd_full:.1f}%\n")

    print("POR SLEEVE — estorbadores (selección IS) y efecto en OOS (Δ Sharpe combo · Δ%/mes anclado):")
    print(f"  {'sleeve':12s} {'#estorbo':>8s} {'ΔSh OOS':>8s} {'Δ%mes OOS':>10s}  estorbadores")
    keep_changes = {}
    for name in builders:
        # LOO por coin: Δ%/mes IS al EXCLUIR cada coin de este sleeve
        drag = []
        for c in syms:
            s_ex = _series(name, ex=[c])
            cis = seg(combined({name: s_ex}), 0, .6)
            d_is = (anchored(cis)[0] - anchored(seg(c0, 0, .6))[0]) / 12
            if d_is > THRESH_IS:
                drag.append((c, d_is))
        drag.sort(key=lambda x: -x[1]); drag_syms = [c for c, _ in drag]
        if not drag_syms:
            print(f"  {name:12s} {'0':>8s} {'—':>8s} {'—':>10s}  (usa bien todas)")
            continue
        s_dd = _series(name, ex=drag_syms); cc = combined({name: s_dd})
        dsh_oos = sh(seg(cc, .6, 1)) - sh(seg(c0, .6, 1))
        dme_oos = (anchored(seg(cc, .6, 1))[0] - anchored(seg(c0, .6, 1))[0]) / 12
        print(f"  {name:12s} {len(drag_syms):>8d} {dsh_oos:>+8.2f} {dme_oos:>+10.2f}  {drag_syms}")
        if dsh_oos > 0.02 and dme_oos > 0.05:          # validó OOS (Sharpe Y %/mes)
            keep_changes[name] = (s_dd, drag_syms)

    print("\ncarry / trend: NO cubiertos por este pase (universo interno funding/EMA) → requieren refactor.\n")

    # aplicar TODOS los cambios validados a la vez
    if keep_changes:
        over = {n: s for n, (s, _) in keep_changes.items()}
        cF = combined(over)
        aF, ddF = anchored(cF); aF_oos, _ = anchored(seg(cF, .6, 1))
        print(f"SISTEMA con TODOS los cambios validados ({list(keep_changes)}):")
        print(f"  Sharpe {metrics(cF)['sharpe']:.2f} (OOS {sh(seg(cF,.6,1)):.2f}) · @−10% {aF/12:.2f}%/mes "
              f"(OOS {aF_oos/12:.2f}) · maxDD {ddF:.1f}%")
        print(f"  vs baseline: ΔSharpe {metrics(cF)['sharpe']-metrics(c0)['sharpe']:+.2f} · "
              f"Δ%/mes full {(aF-a_full)/12:+.2f} · Δ%/mes OOS {(aF_oos-a_oos)/12:+.2f}")
        print("\n  CAMBIOS CANDIDATOS (excluir estos coins del score de cada sleeve):")
        for n, (_, ds) in keep_changes.items():
            print(f"    {n}: excluir {ds}")
        print("\n  ⚠️ NO ir a prod sin walk-forward purgado (regime_lab/B1) + deflación por la selección.")
    else:
        print("VEREDICTO: ningún sleeve mejora el OOS al excluir estorbadores (con disciplina IS→OOS).")
        print("Los 7 ya usan bien todas las monedas; la regla NO rescata mejora en los oficiales. (≠ liq=ZEC).")


def _mask(score, ex):
    if not ex: return score
    s = score.copy()
    for c in ex:
        if c in s.columns: s[c] = np.nan
    return s


if __name__ == "__main__":
    main()
