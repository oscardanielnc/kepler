"""
E82 — RE-VALIDACIÓN de λnet sobre DATOS VIVOS (2026-06-22): el óptimo se movió 0.25 → 0.50.

POR QUÉ (regla de oro): e79 (2026-06-10) eligió λnet=0.25 sobre el net-$ del libro low-barrier cuando
el net-$ vivía en ~+0.09 (gross-norm). En la auditoría del 2026-06-22 el snapshot vivo mostró net +0.27
(target pre-drop) — el sleeve de TREND se cargó de largos con el rally de alts → el net-$ RAW creció a
+0.34. Con un net tan grande, ¿sigue siendo 0.25 el óptimo, o conviene cancelar más?

RESULTADO (WALK-FORWARD 13 folds · train 365 · embargo 14 · test 90 · lev anclado −10% SOLO en train ·
costes reales maker+slippage por liquidez · histórico 2022-01-01 → 2026-06-22, corrido en la VM):

  λnet  net-now  Sh-OOS  %/mes   maxDD   DÍAS+   folds>base   slip×3 (Sh / %mes / maxDD)
  0.00  +0.344   1.38    +2.13   −14.2   50.4%   (base)       —
  0.25  +0.272   1.48    +2.54   −12.6   50.8%   77%          1.18 / +1.78 / −12.2   ← producción previa
  0.35  +0.240   1.50    +2.67   −11.5   50.9%   77%          1.20 / +1.90 / −11.3
  0.50  +0.190   1.50    +2.84   −10.1   52.5%   77%          1.21 / +2.02 /  −9.7   ← NUEVO óptimo
  0.75  +0.097   1.42    +2.68   −10.4   51.5%   46%          (degrada → 0.50 es el borde del plató)

DISCREPANCIA DE AÑADA (clave para la decisión): re-corrido sobre datos LOCALES (hasta 06-03, net raw
+0.14) vs VM (hasta 06-22, net raw +0.34). En retorno/Sharpe/días-verdes λ=0.50 gana en AMBAS. PERO el
maxDD bajo slip×3 de λ=0.50 es INESTABLE entre añadas: −9.7 (VM fresco) vs −12.1 (local viejo). λ=0.35
da maxDD ESTABLE en todo (base −10.1/−11.5 · ×3 −10.0/−11.3) y bate al 0.25 en las dos añadas y los dos
niveles de coste (más retorno, maxDD ≤, más días-verdes, misma robustez 69-77% folds).

VEREDICTO: cuando la métrica de RIESGO de un parámetro cambia de signo según 19 días de datos, la
elección robusta es el vecino estable → producción: **0.25 → 0.35** (mejora dominante y estable a la
añada). λ=0.50 queda como CANDIDATO si el net elevado (+0.34) persiste varias semanas (re-validar
entonces). 0.75 cae a 46% de folds (over-cancela: el net-long ES prima de riesgo, e72).

Caveat honesto: NO es un salto de régimen; es mover el dial un paso dentro del plató ya validado (e79
documentó 0.25-0.50 como pico interior). El efecto vivo: net pre-drop ~+0.27→~+0.24, lev ≈ igual
(anclado a maxDD), 1 rebalanceo con algo más de turnover (re-pesado λ, one-off). No toca el edge ni
los sleeves — solo la fracción de net-$ que se cancela. β sigue ≈0 por construcción (Σwβ=0 preservada).

No toca producción al correr. python -m research.e82_net_lambda_revalidate
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import lowbarrier
from kepler.engine import load, load_panel, DRIVER
from kepler.portfolio import metrics
from research.e72_dollar_neutralization_wf import folds

H, T, CAP = config.LEVERAGE_HAIRCUT, config.TARGET_MAXDD, config.MAX_STRAT_LEVERAGE
LAMS = [0.0, 0.25, 0.35, 0.50, 0.75]


def _maxdd(r):
    eq = (1 + r).cumprod(); return float(abs((eq / eq.cummax() - 1).min()))


def bret(W, rds, cost, L):
    BL = W * L
    held = BL.shift(1).reindex(rds.index).fillna(0.0)
    turn = (BL - BL.shift(1)).abs().reindex(rds.index).fillna(0.0)
    c = (turn * cost.reindex(W.columns).fillna(cost.median())).sum(axis=1)
    return ((held * rds).sum(axis=1) - c).dropna()


def anchor(W, rds, cost):
    def dd(s): return _maxdd(bret(W, rds, cost, s))
    lo, hi = 0.05, CAP
    if dd(hi) < T: return hi
    for _ in range(50):
        m = (lo + hi) / 2
        if dd(m) > T: hi = m
        else: lo = m
    return lo


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    config.LOW_BARRIER_NET_LAMBDA = 0.0  # base sin neutralizar; el grid lo aplica
    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    Wlb, _, _, _, beta, _, rd = lowbarrier.low_barrier_book(C, panels)
    keep = [s for s in config.LOW_BARRIER_UNIVERSE if s in C.columns]
    bd = beta.resample("1D").last().reindex(Wlb.index).ffill().fillna(0.0)
    adv = panels["quote_volume"].resample("1D").sum().mean()
    adv_M = (adv.reindex(C.columns).fillna(1.0) / 1e6).clip(lower=1.0)
    fl = folds(Wlb.index)

    print("E82 — re-validación λnet · %s → %s · %d folds WF\n" % (Wlb.index[0].date(), Wlb.index[-1].date(), len(fl)))
    for mult in [1.0, 3.0]:
        cost = pd.Series(config.MAKER_FEE, index=C.columns) + lowbarrier._slip(adv_M, list(C.columns), mult=mult)
        print("── slippage ×%.0f ──  λ    net    Sh    %%/mes   maxDD  DÍAS+  folds>base" % mult)
        base = None
        for lam in LAMS:
            W = lowbarrier._net_neutralize(Wlb, bd, keep, lam)
            net = W.iloc[-1].sum() / W.iloc[-1].abs().sum()
            oos = []; anns = []
            for tr, te in fl:
                lv = min(anchor(W.loc[tr], rd.loc[tr], cost) * H, CAP)
                r = bret(W.loc[te], rd.loc[te], cost, lv); oos.append(r); anns.append(metrics(r).get("ann", np.nan))
            r = pd.concat(oos).sort_index(); m = metrics(r); anns = np.array(anns)
            if base is None: base = anns; win = "(base)"
            else: win = "%.0f%%" % (np.nanmean(anns > base) * 100)
            print("              %.2f  %+.3f  %4.2f  %+5.2f  %6.1f  %4.1f%%  %s" %
                  (lam, net, m["sharpe"], m["ann"] / 12, m["maxdd"], (r > 0).mean() * 100, win))
        print()
    print("VEREDICTO: λnet=0.35 bate al 0.25 estable a la añada (base y ×3) → producción 0.25→0.35.")
    print("           0.50 gana en retorno pero su maxDD ×3 es inestable entre añadas → candidato si el net persiste.")


if __name__ == "__main__":
    main()
