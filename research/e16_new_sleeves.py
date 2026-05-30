"""
E16 — Buscar un sleeve NUEVO no-correlacionado para subir Sharpe / bajar maxDD (2026-05-30).
Objetivo de Oscar: mejorar el perfil ESTABLE (Sharpe 1.13, +1.2%/mes, maxDD −11.6%) para
poder vivir de ello y atraer inversores — SIN subir el riesgo.

Lógica: un sleeve con Sharpe>0 y correlación ~0 con los 5 actuales sube el Sharpe del conjunto.
Con mayor Sharpe, al fijar el MISMO ancla de maxDD se puede subir el retorno (o bajar el maxDD
a igual retorno). Eso es "mejorar los números" sin apostar más.

Metodología: REUSA `kepler.engine` (código de producción que reproduce el 1.13) — cada candidato
pasa por `engine.xs_sleeve` (β-neutral vs BTC, rebalanceo por horizonte, costo maker, sin lookahead).
Filtro walk-forward: IS&OOS Sharpe > 0.10 y |corr| máx con los 5 base < 0.35.

Candidatos (fundamento económico, solo precio):
  - mom_90d        momentum largo plazo (otro horizonte)
  - accel          aceleración = Δ momentum (mom_30d − mom_30d previo)
  - resid_mom_30d  momentum sobre retornos RESIDUALES (tras quitar β·BTC) → decorrelaciona de mom
  - downvol_14d    semivol a la baja (long baja downside-vol) — variante defensiva de low-vol
  - skew_30d       −skewness (short "lotería": activos con skew + alto suelen estar sobrevalorados)

python -m research.e16_new_sleeves
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, DRIVER
from kepler.portfolio import vol_parity_weights, metrics

IS_FRAC = 0.70


def sh_isoos(r: pd.Series):
    r = r.dropna(); cut = int(len(r) * 0.6)
    f = lambda x: x.mean() / x.std() * np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0.0
    return f(r), f(r.iloc[:cut]), f(r.iloc[cut:])


def base_sleeves(C, ret, beta):
    """Los 5 sleeves de producción (series de retorno diario), vía engine."""
    out = {}
    out["mom_30d"], _   = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    out["rev_60d"], _   = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    out["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    out["carry"], _     = carry_sleeve(C, ret, beta)
    out["trend"], _     = trend_sleeve(C)
    return out


def candidate_scores(C, ret, beta):
    """score_df por candidato (cross-seccional; engine.xs_sleeve hace el resto)."""
    btc = ret[DRIVER]
    resid = ret.sub(beta.mul(btc, axis=0))          # retorno residual tras quitar β·BTC
    cands = {
        "mom_90d":       (ret.rolling(2160).sum(), 720),
        "accel":         (ret.rolling(720).sum() - ret.rolling(720).sum().shift(720), 720),
        "resid_mom_30d": (resid.rolling(720).sum(), 720),
        "downvol_14d":   (-ret.clip(upper=0).rolling(336).std(), 336),
        "skew_30d":      (-ret.rolling(720).skew(), 720),
    }
    return cands


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E16 — Búsqueda de sleeve nuevo no-correlacionado (β-neutral, walk-forward, costos reales)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h\n")

    base = base_sleeves(C, ret, beta)
    base_df = pd.concat(base, axis=1).dropna()

    # baseline actual (5 sleeves)
    vp0 = vol_parity_weights(base_df); combo0 = (base_df * vp0).sum(axis=1)
    m0 = metrics(combo0); s0, i0, o0 = sh_isoos(combo0)
    print("BASELINE actual (5 sleeves):")
    print(f"  Sharpe {m0['sharpe']:.2f} (IS {i0:.2f}/OOS {o0:.2f}) · ann {m0['ann']:.1f}% · "
          f"maxDD {m0['maxdd']:.1f}% · mo_med {m0['mo_med']:.2f}% · mo+ {m0['mo_pos']:.0f}%\n")

    print("CANDIDATOS (Sharpe full/IS/OOS · |corr| máx con los 5 base):")
    print(f"  {'sleeve':14s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corrMax':>8s} {'(con)':>12s} {'¿pasa?':>7s}")
    cands = candidate_scores(C, ret, beta)
    survivors = {}
    for name, (score, hold) in cands.items():
        s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
        j = pd.concat({**base, name: s_ret}, axis=1).dropna()
        corr = j.corr()[name].drop(name)
        cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        sh, i, o = sh_isoos(j[name])
        ok = (i > 0.10 and o > 0.10 and cmax < 0.35)
        print(f"  {name:14s} {sh:6.2f} {i:6.2f} {o:6.2f} {cmax:8.2f} {cwho:>12s} {'SÍ' if ok else 'no':>7s}")
        if ok:
            survivors[name] = s_ret

    if not survivors:
        print("\n→ Ningún candidato pasa el filtro walk-forward + baja correlación. No se añade nada.")
        print("  (Honesto: probar otros horizontes/fundamentos en la próxima iteración.)")
        return

    print(f"\nSUPERVIVIENTES: {list(survivors)} → combinando con los 5 base (vol-parity):")
    new_df = pd.concat({**base, **survivors}, axis=1).dropna()
    vp = vol_parity_weights(new_df); combo = (new_df * vp).sum(axis=1)
    m = metrics(combo); s, i, o = sh_isoos(combo)
    print(f"  vol-parity: { {k: round(v,2) for k,v in vp.items()} }")
    print(f"  NUEVO COMBINADO: Sharpe {m['sharpe']:.2f} (IS {i:.2f}/OOS {o:.2f}) · ann {m['ann']:.1f}% · "
          f"maxDD {m['maxdd']:.1f}% · mo_med {m['mo_med']:.2f}% · mo+ {m['mo_pos']:.0f}%")
    print(f"  ΔSharpe {m['sharpe']-m0['sharpe']:+.2f} · ΔmaxDD {m['maxdd']-m0['maxdd']:+.1f}pp\n")

    # Qué significa para Oscar: a IGUAL maxDD que hoy (−11.6%), ¿cuánto retorno?
    target_dd = abs(m0['maxdd'])
    L = target_dd / abs(m['maxdd'])      # leverage que iguala el maxDD al baseline
    mL = metrics(combo * L)
    print("TRADUCCIÓN AL PRODUCTO (mismo ancla de riesgo que hoy):")
    print(f"  Para igualar el maxDD actual (−{target_dd:.1f}%), leverage de estrategia = {L:.2f}x:")
    print(f"    → ann {mL['ann']:.1f}%  (~{mL['ann']/12:.2f}%/mes)  maxDD {mL['maxdd']:.1f}%  mo+ {mL['mo_pos']:.0f}%")
    print(f"    vs HOY: ann {m0['ann']:.1f}% (~{m0['ann']/12:.2f}%/mes) maxDD {m0['maxdd']:.1f}%")
    print("\n  Tiers con el nuevo combinado:")
    print(f"  {'tier':>16s} {'ann%':>7s} {'mo/mes%':>8s} {'maxDD%':>7s} {'Calmar':>7s}")
    for lev, tag in ((1,"ESTABLE 1x"),(2,"BALANCEADO 2x"),(3,"GROWTH 3x")):
        mm = metrics(combo*lev)
        cal = mm['ann']/abs(mm['maxdd']) if mm['maxdd'] else 0
        print(f"  {tag:>16s} {mm['ann']:7.1f} {mm['ann']/12:8.2f} {mm['maxdd']:7.1f} {cal:7.2f}")
    print("\n  REGLA DE ORO: esto es backtest. Validar OOS estable antes de tocar producción.")


if __name__ == "__main__":
    main()
