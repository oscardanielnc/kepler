"""
E39 — Último intento de señal DIARIA uncorr: familia DISTRIBUCIÓN/COLA (skewness + lotería).
(2026-06-01). Las familias ya probadas se agrupan (precio/on-chain/positioning/liquidez ~0.5; solo
order-book uncorr pero intradía/2023+). La veta sin tocar = el 3er/4º momento de los retornos:

  - efecto LOTERÍA (Bali-Cakici-Whitelaw MAX): activos con payoff tipo lotería (MAX alto) están
    sobre-pagados → underperform. score = −max_Nd  (short lotería / long aburrido).
  - SKEWNESS: asimetría de la distribución. negativo (crash risk) demanda premium. Orientado en IS.
  - SEMIDESVIACIÓN (downside vol): vol solo de los días negativos (≠ vol total = lowvol).

Es DISTINTO de momentum (1er momento) y lowvol (2º momento) → posible nueva familia uncorr → potencial
componente del blend cross-family (e38). Molde e26: ortogonalidad + OOS purgado + corr vs el blend.

python -m research.e39_skew_lottery
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, xs_sleeve
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.regime_lab import build_base_sleeves, evaluate


def daily_to_hourly(daily_df, C):
    """score diario → índice horario de C, rezagado 1 día (anti-look-ahead)."""
    d = daily_df.shift(1)
    cidx = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx)), utc=True)
    return d.reindex(uniq).reindex(cidx).set_axis(C.index).reindex(columns=C.columns)


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD); return metrics(combo*L)["ann"], L


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E39 — señal diaria: familia DISTRIBUCIÓN/COLA (skewness + lotería)\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    rd = C.resample("1D").last().pct_change()      # retornos diarios
    rd.index = rd.index.normalize()

    base = build_base_sleeves(); base_ref = evaluate(base, None, "7 base"); nf = len(base_ref["folds"])
    combo0 = (base * vol_parity_weights(base)).sum(axis=1); ann0, L0 = anchored(combo0)
    print(f"BASELINE 7 (in-sample): Sharpe {metrics(combo0)['sharpe']:.2f} · @−10% {L0:.2f}x → {ann0/12:.2f}%/mes")
    print(f"BASELINE 7 (OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes\n")

    # candidatos de distribución (diarios → horarios)
    cands = {}
    for N in (30, 60):
        cands[f"skew_{N}d"] = rd.rolling(N).skew()
        cands[f"max_{N}d"]  = rd.rolling(N).max()                       # lotería (top-1)
        cands[f"dsemi_{N}d"]= rd.where(rd < 0).rolling(N).std()         # downside vol
    holds = {k: (int(k.split("_")[1].replace("d",""))*24) for k in cands}

    print("── Candidatos · Sh/IS/OOS · corr máx vs 7 · con quién · signo · Δ%/mes in-sample · OOS purgado ──")
    print(f"  {'cand':12s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} {'sgn':>4s} {'Δmes':>6s} {'ΔShOOS':>7s} {'folds':>6s}")
    keep = {}
    for name, dly in cands.items():
        score = daily_to_hourly(dly, C)
        s_ret, _ = xs_sleeve(C, ret, beta, score, holds[name])
        if s_ret.dropna().shape[0] < 100:
            print(f"  {name:12s} insuf"); continue
        cut = int(s_ret.dropna().shape[0]*0.6); sgn = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        s_or = (s_ret * sgn).rename("x")
        j = pd.concat({**{k: base[k] for k in base.columns}, name: s_or}, axis=1)
        j.columns = list(base.columns) + [name]; j = j.dropna()
        corr = j.corr()[name].drop(name).abs()
        if corr.notna().sum() == 0:
            print(f"  {name:12s} degenerado (corr NA)"); continue
        cmax = corr.max(); cwho = corr.idxmax()
        ann, _ = anchored((j*vol_parity_weights(j)).sum(axis=1)); dmes = (ann-ann0)/12
        r = evaluate(base, s_or, name); fw = sum(a > b for a, b in zip(r["folds"], base_ref["folds"]))
        d_oos = r["oos_sharpe"] - base_ref["oos_sharpe"]
        flag = "  <" if (cmax < 0.35 and d_oos > 0 and fw >= 4) else ""
        print(f"  {name:12s} {sh(j[name]):6.2f} {sh(seg(j[name],0,.6)):6.2f} {sh(seg(j[name],.6,1)):6.2f} "
              f"{cmax:6.2f} {cwho:>12s} {sgn:+4.0f} {dmes:+6.2f} {d_oos:+7.2f} {fw:>3d}/{nf}{flag}")
        if cmax < 0.35 and d_oos > 0:
            keep[name] = (s_or, d_oos, fw, cmax)

    print("\nVEREDICTO:")
    if not keep:
        print("  ⚠️ Ningún candidato de distribución es ortogonal (corr<0.35) Y aporta OOS (>0).")
        print("     La familia cola/skewness no aporta señal diaria nueva. BLOQUE DIARIO CERRADO.")
        return
    best = max(keep, key=lambda k: keep[k][1])
    so, d_oos, fw, cmax = keep[best]
    robust = fw >= max(5, nf-1)
    print(f"  {'✅' if robust else '🟡'} Mejor: {best} (ΔSharpe OOS {d_oos:+.2f}, {fw}/{nf}, corr {cmax:.2f}).")
    if robust:
        print("     Candidato a sleeve #8 / componente uncorr del blend. Estrés + coste taker + sombra.")
    else:
        print("     Marginal (no 5/6). Candidato a COMPONENTE del blend cross-family (familia nueva uncorr).")


if __name__ == "__main__":
    main()
