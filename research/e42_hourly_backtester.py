"""
E42 — BACKTESTER HORARIO · Fase 1 (INTRADAY.md §3/§5). 2026-06-01.
El cuello de botella de TODO lo intradía: e15 falló porque ninguna reconstrucción horaria reproducía
el edge diario (−0.28 horario vs +1.04 diario). Este es el SANITY GATE: un mark-to-market HORARIO
buy-and-hold que, al horizonte nativo del sleeve, REPRODUZCA el Sharpe del motor diario (engine.xs_sleeve).

Clave (por qué e15 falló): el motor aplica el retorno FORWARD del bloque a pesos FIJOS (buy-and-hold);
marcar hora-a-hora REBALANCEANDO a pesos fijos NO es lo mismo (drift). Aquí el MTM deja DRIFTAR las
posiciones dentro del bloque (buy-and-hold real) → el PnL al cierre del bloque = el forward del motor,
y la curva horaria intermedia es consistente. Si reconcilia (Sharpe ≈ motor) → la pieza base funciona.

python -m research.e42_hourly_backtester
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, _weights_from_score, xs_sleeve, DRIVER, BETA_W
from kepler.portfolio import metrics


def hourly_mtm(C, beta, score_df, hold):
    """MTM HORARIO buy-and-hold. Rebalancea cada `hold` h a pesos β-neutral; deja driftar dentro del
    bloque; marca cada hora. Devuelve (curva equity HORARIA, retornos por BLOQUE). Coste maker al rebal."""
    syms = [s for s in C.columns if s != DRIVER]
    px = C[syms]; pxd = C[DRIVER]
    idx = list(range(BETA_W + hold, len(C) - hold, hold))
    prevw = pd.Series(0.0, index=syms); prevh = 0.0
    eq = 1.0; ts = [C.index[idx[0]]]; curve = [eq]; block_rets = {}
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        turn = float((w - prevw).abs().sum()) + abs(h - prevh)
        cost = turn * config.MAKER_FEE
        p0 = px.iloc[t]; pd0 = pxd.iloc[t]
        block_start_eq = eq * (1 - cost)        # coste one-time al entrar al bloque
        for k in range(1, hold + 1):
            cr = (px.iloc[t + k] / p0 - 1.0).reindex(w.index).fillna(0.0)        # cumret buy-and-hold
            crd = pxd.iloc[t + k] / pd0 - 1.0
            pnl = float((w * cr).sum()) + h * float(crd)                          # PnL del bloque a hora k
            curve.append(block_start_eq * (1.0 + pnl)); ts.append(C.index[t + k])
        block_rets[C.index[t]] = curve[-1] / eq - 1.0     # retorno del bloque (incl. coste)
        eq = curve[-1]; prevw, prevh = w, h
    return pd.Series(curve, index=ts), pd.Series(block_rets)


def engine_block_rets(C, ret, beta, score_df, hold):
    """Retornos por BLOQUE del motor (réplica de engine.xs_sleeve ANTES del resample diario)."""
    syms = [s for s in C.columns if s != DRIVER]; R = ret[syms]; rd = ret[DRIVER]
    fwd = np.expm1(R.rolling(hold).sum().shift(-hold)); fwd_d = np.expm1(rd.rolling(hold).sum().shift(-hold))
    idx = range(BETA_W + hold, len(C) - hold, hold)
    prev = pd.Series(0.0, index=syms); ph = 0.0; out = {}
    for t in idx:
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        port = float((w * fwd.iloc[t].reindex(syms).fillna(0)).sum()) + h * float(fwd_d.iloc[t] or 0)
        turn = float((w - prev).abs().sum()) + abs(h - ph)
        out[C.index[t]] = port - turn * config.MAKER_FEE; prev, ph = w, h
    return pd.Series(out)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E42 — BACKTESTER HORARIO Fase 1 · sanity gate: ¿reproduce el edge diario?\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)

    # sleeves a reconciliar (los xs puros; carry/trend tienen su propio loop)
    cases = {
        "mom_30d":    (alphas.xs_momentum_score(ret, 720), 720),
        "rev_60d":    (alphas.xs_reversal_score(ret, 1440), 1440),
        "lowvol_14d": (alphas.xs_lowvol_score(ret, 336), 336),
        "hlpos_14d":  (alphas.xs_hlposition_score(C, 336), 336),
    }
    print(f"  {'sleeve':12s} {'Sh motor':>9s} {'Sh horario':>11s} {'Δ':>6s} {'corr BLOQUE':>12s} {'(N bloques)':>11s}")
    allgood = True
    for name, (score, hold) in cases.items():
        s_eng, _ = xs_sleeve(C, ret, beta, score, hold)
        sh_eng = metrics(s_eng)["sharpe"]
        eqh, blk_h = hourly_mtm(C, beta, score, hold)
        sh_h = metrics(eqh.resample("1D").last().ffill().pct_change().dropna())["sharpe"]
        blk_e = engine_block_rets(C, ret, beta, score, hold)
        j = pd.concat({"e": blk_e, "h": blk_h}, axis=1).dropna()
        cc = j["e"].corr(j["h"]) if len(j) > 5 else float("nan")
        allgood &= (abs(sh_h - sh_eng) < 0.25 and cc > 0.97)
        print(f"  {name:12s} {sh_eng:9.2f} {sh_h:11.2f} {sh_h-sh_eng:+6.2f} {cc:12.3f} {len(j):>11d}")

    print(f"\nGATE a nivel de BLOQUE (la comparación correcta; la diaria del motor es escasa/picuda):")
    if allgood:
        print("  ✅ RECONCILIA: Sharpe ≈ motor Y corr de bloque >0.97 → el MTM horario reproduce el edge.")
        print("     Supera el fallo de e15. BASE del backtester horario LISTA → Fase 2 (order-book 1h–12h).")
    else:
        print("  ⚠️ Revisar: aún no reconcilia limpio a nivel de bloque. Ajustar accounting antes de Fase 2.")
    print("  (Próximo Fase 2: bajar raw 30s de bookDepth, evaluar order-book a 1h–12h con costo de spread.)")


if __name__ == "__main__":
    main()
