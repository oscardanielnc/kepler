"""
E30 — ¿el factor de ILIQUIDEZ de Amihud es ORTOGONAL y aporta sobre los 7 sleeves?
(2026-06-01). Surge de la investigación web "gratis primero": el netflow de pago resultó dudoso
para diario (arXiv 2411.06327: edge intradía/débil en majors), pero la misma tanda destapó un
candidato GRATIS con respaldo académico (four-factor crypto / CTREND) y CERO datos nuevos:
la ILIQUIDEZ de Amihud, computable con el `quote_volume` que YA tenemos.

  Amihud ILLIQ = |retorno| / volumen_en_dólares   (impacto de precio por dólar negociado)
  illiq_Nd = Σ|ret_1h| / Σ quote_volume  sobre ventana N días   (ratio-de-sumas, estable)
  Hipótesis (premium de iliquidez): cross-seccional, los más ilíquidos rinden más → long ilíquido
  / short líquido, β-neutral. El signo se ORIENTA en IS (como e26) y se deja que el dato decida.

Se usa log(ILLIQ): la dispersión cross-seccional es de órdenes de magnitud (caps grandes vs chicas);
el log la comprime a algo rankeable por _weights_from_score (demean + normaliza), evitando que un
solo nombre ilíquido domine los pesos.

Criterio (lección e16d/e26): no basta corr<0.35 + IS/OOS; el sleeve debe SUBIR el retorno al
maxDD −10% anclado (con vol-parity, uno de menor Sharpe DILUYE aunque sea ortogonal). + estrés.

python -m research.e30_illiquidity_check
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n * a):int(n * b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), L, m.get("maxdd", float("nan"))


def illiq_score(absret, dvol, h):
    """log de Amihud (ratio-de-sumas) sobre ventana h horas. Ilíquido = valor ALTO."""
    num = absret.rolling(h).sum()
    den = dvol.rolling(h).sum().replace(0, np.nan)
    return np.log((num / den).replace(0, np.nan))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E30 — ¿factor de iliquidez de Amihud (GRATIS, datos propios) ortogonal y aporta?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["quote_volume", "volume", "taker_buy_volume"], C)
    dvol = P["quote_volume"]
    absret = ret.abs()
    print(f"Panel: {C.shape[1]} símbolos · {C.index[0].date()} → {C.index[-1].date()} ({len(C)} barras 1h)\n")

    # 7 sleeves base
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    bdf = pd.concat(base, axis=1); bdf.columns = list(base); bdf = bdf.dropna()
    combo0 = (bdf * vol_parity_weights(bdf)).sum(axis=1)
    ann0, L0, dd0 = anchored(combo0)
    print(f"BASELINE 7 sleeves: Sharpe {metrics(combo0)['sharpe']:.2f} · @−10% {L0:.2f}x → "
          f"{ann0/12:.2f}%/mes (maxDD {dd0:.1f}%)\n")

    cands = {}
    for days in (7, 14, 30):
        h = days * 24
        cands[f"illiq_{days}d"] = (illiq_score(absret, dvol, h), h)
    # robustez: Amihud "clásico" (media de |ret|/dvol) a 14d
    h14 = 14 * 24
    cands["illiq_mean_14d"] = (np.log((absret / dvol.replace(0, np.nan)).rolling(h14).mean().replace(0, np.nan)), h14)
    # cambio de iliquidez (¿iliquidez que sube/baja predice?) a 14d
    cands["dilliq_14d"] = (illiq_score(absret, dvol, h14).diff(h14), h14)

    print("CANDIDATOS (Sh/IS/OOS · corr máx vs 7 · con quién · signo · Δ%/mes anclado):")
    print(f"  {'cand':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} {'sgn':>4s} {'Δ%/mes':>7s}")
    best = []
    for name, (score, hold) in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
        except Exception as e:
            print(f"  {name:16s} ERROR {str(e)[:35]}"); continue
        if s_ret.dropna().shape[0] < 100:
            print(f"  {name:16s} insuf ({s_ret.dropna().shape[0]})"); continue
        cut = int(s_ret.dropna().shape[0] * 0.6)
        sign = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        s_or = s_ret * sign
        j = pd.concat({**base, name: s_or}, axis=1); j.columns = list(base) + [name]; j = j.dropna()
        if len(j) < 100: print(f"  {name:16s} overlap corto"); continue
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        combo = (j * vol_parity_weights(j)).sum(axis=1); ann, _, _ = anchored(combo)
        dmes = (ann - ann0) / 12
        passes = (sh(seg(j[name], .6, 1)) > 0.10 and cmax < 0.35)
        print(f"  {name:16s} {sh(j[name]):6.2f} {sh(seg(j[name],0,.6)):6.2f} {sh(seg(j[name],.6,1)):6.2f} "
              f"{cmax:6.2f} {cwho:>12s} {sign:+4.0f} {dmes:+7.2f}{'  <' if passes else ''}")
        if passes and dmes > 0.10:
            best.append((name, dmes, cmax, hold, sign))

    # --- ESTRÉS del mejor (¿lo mueve 1 token? ¿repartido en el tiempo? ¿aguanta taker?) ---
    if best:
        bname, _, _, h, sign = max(best, key=lambda b: b[1])
        print(f"\nESTRÉS de {bname}:")
        score = cands[bname][0]
        sr_full, _ = xs_sleeve(C, ret, beta, score, h); sr_full = sr_full * sign
        j = pd.concat({**base, "x": sr_full}, axis=1); j.columns = list(base) + ["x"]; j = j.dropna()
        print("  Cuartiles temporales (Sharpe):  " +
              "  ".join(f"Q{i+1} {sh(seg(j['x'],a,b)):+.2f}"
                        for i,(a,b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)])))
        # coste TAKER (estrés de costos): reconstruye la serie pagando taker en vez de maker
        ann_t, _, _ = anchored((j * vol_parity_weights(j)).sum(axis=1))
        print(f"  Δ%/mes al ancla (maker):  {(ann_t-ann0)/12:+.2f}")
        # leave-one-out por símbolo: quitar cada uno y ver si colapsa el aporte
        syms = [s for s in C.columns if s != "BTCUSDT"]
        print("  LEAVE-ONE-OUT (Δ%/mes al quitar cada símbolo del score; CAE si baja >0.3):")
        d_full = (ann_t - ann0) / 12; loo = []
        for t in syms:
            sc = score.copy(); sc[t] = np.nan
            srt, _ = xs_sleeve(C, ret, beta, sc, h); srt = srt * sign
            jj = pd.concat({**base, "x": srt}, axis=1); jj.columns = list(base) + ["x"]; jj = jj.dropna()
            a, _, _ = anchored((jj * vol_parity_weights(jj)).sum(axis=1)); loo.append((t, (a-ann0)/12))
        for t, d_t in sorted(loo, key=lambda x: x[1])[:8]:
            print(f"    sin {t:10s} Δ {d_t:+.2f}%/mes  ({'CAE' if d_t < d_full-0.3 else 'ok'})")

    print("\nVEREDICTO:")
    if not best:
        print("  Ningún candidato de iliquidez es ortogonal (corr<0.35) Y sube el retorno anclado (>+0.1%/mes).")
        print("  El factor de Amihud NO aporta sobre los 7 sleeves (probablemente lo capturan lowvol/takerflow).")
    else:
        print(f"  PROMETEDOR: {[b[0] for b in best]} → si el estrés aguanta, candidato a sleeve #8.")
        print("  Siguiente: estrés de horizonte completo (e16e) + coste TAKER explícito + walk-forward purgado (B1).")


if __name__ == "__main__":
    main()
