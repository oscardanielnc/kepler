"""
E15 — ¿Sirve un MONITOR DE RIESGO INTRADÍA? (regla de oro: backtest antes de implementar)

Pregunta: Kepler rebalancea cada 24h y NO mira nada entre ciclos. ¿Des-riesgar
intradía cuando el equity cae X% (desde la apertura del día) reduce el maxDD sin
matar el Sharpe por costos de salir/re-entrar?

v2 (2026-05-30) — CORRIGE el bug de v1. v1 neteaba los pesos por activo entre sleeves
antes de marcar (mom largo BTC + rev corto BTC se cancelaban → libro chico de ruido,
baseline Sharpe −0.23). v2 corre CADA sleeve por separado a gross=1, combina sus
RETORNOS por vol-parity (igual que el motor → reproduce ~1.0+), y aplica el monitor
sobre la equity COMBINADA.

Diseño:
  - 3 sleeves XS β-neutral (mom 30d, rev 60d, lowvol 14d). Pesos recalculados cada 24h
    con datos SOLO hasta t (sin lookahead). [carry/trend omitidos en v1/v2: su PnL intradía
    de precio ≈0; añadirlos solo diluiría el efecto del monitor, no lo cambiaría de signo.]
  - Equity horaria de cada sleeve (Σ wᵢ·rᵢ,hora + hedge·r_btc,hora), gross=1.
  - Combinado horario = Σ vp_sleeve · ret_sleeve,hora.
  - BASELINE: sin monitor. VARIANTE: si el drawdown intradía (desde apertura del día) cruza
    −X%, escala TODO ×f el resto del día; paga turnover (taker) al des-riesgar y al re-entrar.
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
SLEEVES = {"mom": (alphas.xs_momentum_score, 720),
           "rev": (alphas.xs_reversal_score, 1440),
           "lowvol": (alphas.xs_lowvol_score, 336)}


def build_paths(C, ret, beta):
    """Para cada sleeve: path de (pesos, hedge) recalculado cada REBAL_H (sin lookahead) +
    su vol-parity weight (de su retorno diario histórico, como el motor)."""
    syms = [s for s in C.columns if s != "BTCUSDT"]
    scores = {n: f(ret, h) for n, (f, h) in SLEEVES.items()}
    daily = {}
    for n, sc in scores.items():
        s, _ = xs_sleeve(C, ret, beta, sc, REBAL_H)
        daily[n] = s
    vp = vol_parity_weights(pd.concat(daily, axis=1).dropna())

    start = 168 + 1440
    idx = list(range(start, len(C) - 1, REBAL_H))
    paths = {n: {"w": [], "h": []} for n in SLEEVES}
    for t in idx:
        for n, sc in scores.items():
            w, h = _weights_from_score(sc.iloc[t], beta.iloc[t], syms)
            paths[n]["w"].append(w); paths[n]["h"].append(h)
    for n in SLEEVES:
        paths[n]["W"] = pd.DataFrame(paths[n]["w"], index=idx)
        paths[n]["H"] = pd.Series(paths[n]["h"], index=idx)
    return paths, idx, syms, vp


def simulate(C, ret, paths, idx, syms, vp, derisk_dd=None, derisk_f=0.0):
    """Equity HORARIA combinada. Si derisk_dd: al cruzar −derisk_dd intradía, escala ×derisk_f
    el resto del día (sobre TODA la cartera). Devuelve retornos horarios netos."""
    rh = ret[syms]; rb = ret["BTCUSDT"]
    prev = {n: {"w": pd.Series(0.0, index=syms), "h": 0.0} for n in SLEEVES}
    out_r, out_t = [], []
    for k, t0 in enumerate(idx):
        t1 = idx[k + 1] if k + 1 < len(idx) else min(t0 + REBAL_H, len(C) - 1)
        # pesos del día por sleeve + costo de rebalanceo programado (maker), prorrateado por vp
        day = {}
        base_cost = 0.0
        for n in SLEEVES:
            w = paths[n]["W"].loc[t0].reindex(syms).fillna(0.0); h = float(paths[n]["H"].loc[t0])
            turn = float((w - prev[n]["w"]).abs().sum()) + abs(h - prev[n]["h"])
            base_cost += vp[n] * turn * BASE_COST
            day[n] = (w, h)
        scale = 1.0; eq = 1.0; derisked = False
        for j, hh in enumerate(range(t0, t1)):
            ra = float(rb.iloc[hh]) if not np.isnan(rb.iloc[hh]) else 0.0
            r_comb = 0.0
            for n in SLEEVES:
                w, h = day[n]
                r_sleeve = float((w * rh.iloc[hh].reindex(syms).fillna(0.0)).sum()) + h * ra
                r_comb += vp[n] * r_sleeve
            r = scale * r_comb
            if j == 0:
                r -= base_cost
            out_r.append(r); out_t.append(C.index[hh]); eq *= (1 + r)
            if derisk_dd is not None and not derisked and (eq - 1) <= -derisk_dd:
                gross = sum(vp[n] * (float(day[n][0].abs().sum()) + abs(day[n][1])) for n in SLEEVES)
                out_r[-1] -= (1 - derisk_f) * gross * DERISK_COST
                scale = derisk_f; derisked = True
        for n in SLEEVES:                       # estado de cierre (para turnover del próximo día)
            w, h = day[n]
            prev[n] = {"w": w * (scale if derisked else 1.0), "h": h * (scale if derisked else 1.0)}
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
    print("E15 v2 — Monitor de riesgo intradía (3 XS sleeves, equity combinada por vol-parity)\n")
    C = load_C(); ret = np.log(C).diff(); beta = _beta(ret)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h")
    paths, idx, syms, vp = build_paths(C, ret, beta)
    print(f"vol-parity sleeves: {vp.round(2).to_dict()} · {len(idx)} rebalanceos\n")

    base = simulate(C, ret, paths, idx, syms, vp)
    mb = metrics(base)
    hdr = f"{'config':>22s} {'Sharpe':>7s} {'annRet%':>8s} {'maxDD%':>7s} {'mo_med%':>8s} {'mo+%':>5s} {'peorMes%':>8s}"
    print(hdr)
    print(f"{'BASELINE (sin monitor)':>22s} {mb['sharpe']:7.2f} {mb['ann']:8.1f} {mb['maxdd']:7.1f} "
          f"{mb['mo_med']:8.2f} {mb['mo_pos']:5.0f} {mb['mo_worst']:8.1f}")
    print("-" * len(hdr))
    for dd in (0.01, 0.015, 0.02, 0.03):
        for f in (0.0, 0.5):
            r = simulate(C, ret, paths, idx, syms, vp, derisk_dd=dd, derisk_f=f)
            m = metrics(r)
            tag = f"X={dd*100:.1f}% f={f:.1f}"
            print(f"{tag:>22s} {m['sharpe']:7.2f} {m['ann']:8.1f} {m['maxdd']:7.1f} "
                  f"{m['mo_med']:8.2f} {m['mo_pos']:5.0f} {m['mo_worst']:8.1f}")
    print("\nVeredicto: el monitor SOLO se justifica si baja |maxDD| y/o peorMes SIN bajar el Sharpe.")
    print("Caveat: 3/5 sleeves (carry/trend no aportan swing intradía de precio).")


if __name__ == "__main__":
    main()
