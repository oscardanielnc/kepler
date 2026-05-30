"""
E15 — ¿Sirve un MONITOR DE RIESGO INTRADÍA? (regla de oro: backtest antes de implementar)

⚠️ v1 INVÁLIDO (2026-05-30): este reconstruye el libro NETEANDO los pesos por activo antes de
   marcar a mercado (mom largo BTC + rev corto BTC se cancelan → libro chico dominado por ruido).
   Su baseline da Sharpe −0.23/maxDD −39%, que NO reproduce el edge validado (+1.13/−11.6%).
   Verificado: los 3 sleeves combinando RETORNOS por sleeve (no pesos) dan ~1.13.
   ⇒ NO usar los números de v1 como veredicto. ARREGLO: combinar la equity horaria de cada sleeve
   corrido por separado (gross=1), luego aplicar el monitor sobre la equity combinada.


Pregunta: Kepler rebalancea cada 24h y NO mira nada entre ciclos. ¿Des-riesgar
intradía cuando el equity cae X% (desde la apertura del día) reduce el maxDD sin
matar el Sharpe por costos de salir/re-entrar?

Diseño honesto (v1):
  - Reconstruye la cartera EN VIVO como la arma el motor: cada 24h calcula los pesos
    netos β-neutral de los 3 sleeves cross-secc (mom/rev/lowvol, vol-parity), con datos
    SOLO hasta t (sin lookahead). Esos sleeves dominan el riesgo intradía de precio.
    [Carry (funding, var. de precio intradía ≈0 por β-neutral) y trend (long-only diario)
     se omiten en v1 — se añadirán en v2 si el monitor muestra señal.]
  - Mantiene esos pesos durante 24h y construye la curva de equity HORARIA real
    (Σ wᵢ·rᵢ,hora + hedge·r_btc,hora).
  - BASELINE: sin monitor. VARIANTE: si el drawdown intradía (desde la apertura del día)
    cruza −X%, escala TODA la exposición ×f por lo que resta del día; paga costo de
    turnover (taker, conservador) al des-riesgar y al re-entrar al día siguiente.
  - Compara Sharpe/maxDD/mensual NETOS para una grilla de (X, f).

python -m research.e15_intraday_monitor
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load as load_C, _beta, _weights_from_score, xs_sleeve
from kepler.portfolio import vol_parity_weights

REBAL_H = 24            # rebalanceo cada 24h (igual que producción)
DERISK_COST = config.TAKER_FEE   # salida reactiva = taker (conservador)
BASE_COST = config.MAKER_FEE     # rebalanceo programado = maker


def build_weight_path(C, ret, beta):
    """Path histórico de pesos NETOS por activo (β-neutral, vol-parity de los 3 XS),
    recalculado cada REBAL_H con datos hasta t. Devuelve (W[días×syms], hedge[días])."""
    syms = [s for s in C.columns if s != "BTCUSDT"]
    sleeves = {
        "mom":    alphas.xs_momentum_score(ret, 720),
        "rev":    alphas.xs_reversal_score(ret, 1440),
        "lowvol": alphas.xs_lowvol_score(ret, 336),
    }
    # vol-parity entre sleeves (de su retorno diario histórico, como el motor)
    series = {}
    for name, score in sleeves.items():
        s, _ = xs_sleeve(C, ret, beta, score, REBAL_H)
        series[name] = s
    vp = vol_parity_weights(pd.concat(series, axis=1).dropna())

    start = 168 + 1440  # BETA_W + mayor lookback
    idx = list(range(start, len(C) - 1, REBAL_H))
    rows, hedges, ts = [], [], []
    for t in idx:
        net = pd.Series(0.0, index=syms); hedge = 0.0
        for name, score in sleeves.items():
            w, h = _weights_from_score(score.iloc[t], beta.iloc[t], syms)
            net = net.add(vp[name] * w, fill_value=0.0)
            hedge += vp[name] * h
        rows.append(net); hedges.append(hedge); ts.append(t)
    W = pd.DataFrame(rows, index=ts)
    return W, pd.Series(hedges, index=ts), syms, vp


def simulate(C, ret, W, hedge, syms, derisk_dd=None, derisk_f=0.0):
    """Curva de equity HORARIA. Si derisk_dd: al cruzar −derisk_dd intradía, escala ×derisk_f
    el resto del día. Devuelve serie de retornos horarios netos."""
    rh = ret[syms]; rb = ret["BTCUSDT"]
    out_r, out_t = [], []
    prev_w = pd.Series(0.0, index=syms); prev_h = 0.0
    day_starts = list(W.index)
    for k, t0 in enumerate(day_starts):
        w = W.loc[t0].reindex(syms).fillna(0.0)
        h = float(hedge.loc[t0])
        t1 = day_starts[k + 1] if k + 1 < len(day_starts) else min(t0 + REBAL_H, len(C) - 1)
        # costo del rebalanceo programado (maker) al entrar a la posición del día
        turn = float((w - prev_w).abs().sum()) + abs(h - prev_h)
        base_cost = turn * BASE_COST
        scale = 1.0; eq = 1.0; derisked = False
        hours = list(range(t0, t1))
        for j, hh in enumerate(hours):
            r_assets = float((w * rh.iloc[hh].reindex(syms).fillna(0.0)).sum())
            r = scale * (r_assets + h * float(rb.iloc[hh] if not np.isnan(rb.iloc[hh]) else 0.0))
            if j == 0:
                r -= base_cost            # cobra el costo de rebalanceo en la 1ª hora
            out_r.append(r); out_t.append(C.index[hh])
            eq *= (1 + r)
            # monitor intradía (sobre equity desde apertura del día)
            if derisk_dd is not None and not derisked and (eq - 1) <= -derisk_dd:
                # des-riesga: paga turnover taker sobre la exposición que recorta
                cut = (1 - derisk_f) * (float(w.abs().sum()) + abs(h))
                out_r[-1] -= cut * DERISK_COST
                scale = derisk_f; derisked = True
        prev_w, prev_h = (w * (scale if derisked else 1.0)), (h * (scale if derisked else 1.0))
    return pd.Series(out_r, index=pd.to_datetime(out_t, utc=True))


def metrics(r: pd.Series):
    r = r.dropna()
    if len(r) < 100 or r.std() == 0:
        return None
    ppy = 8760
    sh = r.mean() / r.std() * np.sqrt(ppy)
    ann = (1 + r.mean()) ** ppy - 1
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    return dict(sharpe=sh, ann=ann * 100, vol=r.std() * np.sqrt(ppy) * 100, maxdd=dd * 100,
                mo_med=m.median() * 100, mo_pos=(m > 0).mean() * 100, mo_worst=m.min() * 100,
                calmar=ann / abs(dd) if dd < 0 else 0.0)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("E15 — Monitor de riesgo intradía (3 XS sleeves, β-neutral, costos reales)\n")
    C = load_C(); ret = np.log(C).diff(); beta = _beta(ret)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h")
    W, hedge, syms, vp = build_weight_path(C, ret, beta)
    print(f"vol-parity sleeves: {vp.round(2).to_dict()} · {len(W)} rebalanceos\n")

    base = simulate(C, ret, W, hedge, syms)
    mb = metrics(base)
    print(f"{'config':>22s} {'Sharpe':>7s} {'annRet%':>8s} {'maxDD%':>7s} {'mo_med%':>8s} {'mo+%':>5s} {'peorMes%':>8s}")
    print(f"{'BASELINE (sin monitor)':>22s} {mb['sharpe']:7.2f} {mb['ann']:8.1f} {mb['maxdd']:7.1f} "
          f"{mb['mo_med']:8.2f} {mb['mo_pos']:5.0f} {mb['mo_worst']:8.1f}")
    print("-" * 72)
    for dd in (0.01, 0.015, 0.02, 0.03):
        for f in (0.0, 0.5):
            r = simulate(C, ret, W, hedge, syms, derisk_dd=dd, derisk_f=f)
            m = metrics(r)
            tag = f"X={dd*100:.1f}% f={f:.1f}"
            print(f"{tag:>22s} {m['sharpe']:7.2f} {m['ann']:8.1f} {m['maxdd']:7.1f} "
                  f"{m['mo_med']:8.2f} {m['mo_pos']:5.0f} {m['mo_worst']:8.1f}")
    print("\nLectura: el monitor SOLO se justifica si baja |maxDD| y/o peorMes SIN bajar "
          "el Sharpe (regla de oro). Si empeora el Sharpe → el ruido intradía nos saca en "
          "mínimos locales y pagamos costos = el juego que perdemos. v1: 3 XS sleeves.")


if __name__ == "__main__":
    main()
