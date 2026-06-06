"""
E73 — VOL-TARGETING DINÁMICO del libro combinado (Oscar 2026-06-05, tras crash 06-02/05).

CONTEXTO: el crash reabrió la pregunta "¿reaccionar a la volatilidad para suavizar caídas?". Ya se
descartó el GATE DE RÉGIMEN binario (de-risk on/off → empeora maxDD por whipsaw, ver engine.py) y los
TILTS de régimen por sleeve (e31, no superan barra deflactada). Lo que NO se ha probado limpio es el
vol-targeting CONTINUO estilo Moreira-Muir (2017): escalar el leverage del libro día a día ∝ 1/vol
realizada reciente, en vez del ancla ESTÁTICA actual (leverage_robust/e68, fijo sobre toda la muestra).

HIPÓTESIS (no predice dirección, solo reacciona a la vol de AYER): la vol de cripto es persistente
(clustering) → si bajamos exposición cuando la vol sube, suavizamos el drawdown → al RE-ANCLAR a maxDD
−10% podemos correr más leverage de MEDIA → más retorno al MISMO riesgo (flywheel). El enemigo: (a) la
vol de cripto revierte rápido → llegas tarde y te pierdes el rebote; (b) ajustar el leverage a diario
añade TURNOVER sobre todo el gross → coste que puede comerse el beneficio. El backtest decide.

MÉTODO (comparación JUSTA a igual maxDD; lección e71/e72: full-sample explora, walk-forward manda):
  - r1 = retorno del libro combinado a 1x (con su turnover). vol_t = EWMA std de r1 (causal, shift 1).
  - Caminos de leverage: ESTÁTICO (cte) · SIMÉTRICO (s/vol) · ASIMÉTRICO (s/max(vol,ref), solo de-riskea).
  - Cada camino se ANCLA (escalar s) para clavar maxDD=−10%; se mide Sharpe/ann/Calmar y lev medio/máx
    + turnover (realismo: ¿respeta el cap 4x?). El turnover de ajustar el leverage está CONTABILIZADO.
  - WALK-FORWARD: s anclado SOLO en train (365d·embargo 14d·test 90d), aplicado a test, OOS concatenado.

No toca producción. python -m research.e73_vol_targeting
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from research.e72_dollar_neutralization_wf import build_book, folds, TRAIN_D, EMBARGO_D, TEST_D
from research.e60_concentration_cap_aggregate import _maxdd
from kepler.portfolio import metrics
from kepler.engine import DRIVER

TARGET = config.TARGET_MAXDD          # 0.10
LEV_CAP = 6.0                         # cap generoso para el estudio (monotonía del anclado); realismo: vs 4x prod
WINDOWS = [10, 20, 40]               # span EWMA de la vol (días)


def levered_returns(book_1x: pd.DataFrame, rd: pd.DataFrame, Lpath) -> pd.Series:
    """Retorno del libro escalado por el camino de leverage Lpath (escalar o Series por-día).
    El turnover de AJUSTAR el leverage cuenta (positions = L_t·book_t)."""
    BL = book_1x.mul(Lpath, axis=0) if hasattr(Lpath, "__len__") else book_1x * Lpath
    pnl = (BL.shift(1) * rd).sum(axis=1)
    turn = (BL - BL.shift(1)).abs().sum(axis=1).fillna(0.0)
    return (pnl - turn * config.MAKER_FEE).dropna()


def anchor_scalar(book_1x, rd, base_path):
    """Escalar s tal que maxDD(libro con L=clip(s·base_path,0,CAP))=−TARGET. base_path: 1.0 (estático) o Series."""
    def dd(s):
        L = (base_path * s)
        L = L.clip(0, LEV_CAP) if hasattr(L, "clip") else min(max(L, 0), LEV_CAP)
        return abs(_maxdd(levered_returns(book_1x, rd, L)))   # _maxdd (e60) viene con signo → abs
    lo, hi = 0.01, LEV_CAP
    if dd(hi) < TARGET:
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        if dd(mid) > TARGET:
            hi = mid
        else:
            lo = mid
    return lo


def make_paths(r1: pd.Series, index):
    """Devuelve {nombre: base_path}. base_path se multiplicará por el escalar de anclado.
    Estático = 1.0. Vol-target = 1/vol (simétrico) o 1/max(vol,ref) (asimétrico, solo de-riskea)."""
    paths = {"estatico": pd.Series(1.0, index=index)}
    for w in WINDOWS:
        vol = r1.ewm(span=w, min_periods=w).std().shift(1).reindex(index)
        vol = vol.replace(0, np.nan).ffill().bfill()
        ref = vol.expanding(min_periods=30).median().shift(1).ffill().bfill()  # pivote causal
        inv = (1.0 / vol)
        paths[f"sim_{w}d"]  = inv / inv.mean()                       # simétrico (sube y baja con la vol)
        capped = 1.0 / np.maximum(vol.values, ref.values)
        paths[f"asim_{w}d"] = pd.Series(capped, index=index) / np.nanmean(capped)  # solo de-riskea sobre ref
    return paths


def describe(book_1x, rd, base_path, s, label):
    L = (base_path * s).clip(0, LEV_CAP)
    r = levered_returns(book_1x, rd, L)
    m = metrics(r)
    Lv = L.reindex(r.index)
    turn = book_1x.mul(L, axis=0)
    turn = (turn - turn.shift(1)).abs().sum(axis=1).reindex(r.index)
    ann_turn = float(turn.mean() * 365)
    print(f"{label:12s}│ Sh {m.get('sharpe',0):.2f}  maxDD {m.get('maxdd',0):6.1f}  "
          f"ann {m.get('ann',0):5.1f}% ({m.get('ann',0)/12:4.2f}%/mes)  Calmar {m.get('calmar',0):.2f}  "
          f"mo+ {m.get('mo_pos',0):3.0f}% │ lev μ{Lv.mean():.2f} máx{Lv.max():.2f} (>4x {100*(Lv>4).mean():.0f}%) turn {ann_turn:.0f}x/a")
    return m


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E73 — vol-targeting dinámico (re-ancla a maxDD −10%; ¿más retorno a igual riesgo que el ancla estática?)\n")
    book_1x, beta_daily, rd = build_book()
    r1 = levered_returns(book_1x, rd, 1.0)               # libro a 1x (con turnover)
    idx = book_1x.index
    paths = make_paths(r1, idx)

    print("══ FULL-SAMPLE (exploratorio — NO concluyente, ver walk-forward abajo) ══")
    print(f"{'camino':12s}│ {'sistema @ maxDD −10% (turnover de ajustar lev incluido)':>0s}")
    print("─" * 132)
    full = {}
    for name, bp in paths.items():
        s = anchor_scalar(book_1x, rd, bp)
        full[name] = describe(book_1x, rd, bp, s, name)

    print("\n══ WALK-FORWARD (EL VEREDICTO — s anclado SOLO en train · 365d·embargo14d·test90d) ══")
    fl = folds(idx)
    print(f"{len(fl)} folds OOS · {idx[0].date()} → {idx[-1].date()}")
    rd_btc = rd[DRIVER]
    oos = {name: [] for name in paths}
    fold_ann = {name: [] for name in paths}
    for tr, te in fl:
        # recomputar caminos con info causal hasta el final de cada slice ya está en `paths` (vol es causal)
        for name, bp in paths.items():
            s = anchor_scalar(book_1x.loc[tr], rd.loc[tr], bp.loc[tr] if hasattr(bp, "loc") else bp)
            bpt = bp.loc[te] if hasattr(bp, "loc") else bp
            r_te = levered_returns(book_1x.loc[te], rd.loc[te], (bpt * s).clip(0, LEV_CAP))
            oos[name].append(r_te); fold_ann[name].append(metrics(r_te).get("ann", float("nan")))

    print(f"\n{'camino':12s}│ {'OOS concatenado (futuro nunca visto)':>0s}")
    print("─" * 110)
    base_ann = np.array(fold_ann["estatico"])
    for name in paths:
        r = pd.concat(oos[name]).sort_index(); m = metrics(r)
        ann_arr = np.array(fold_ann[name])
        win = np.nanmean(ann_arr > base_ann) * 100
        wtxt = "(baseline)" if name == "estatico" else f"bate estático {win:.0f}% folds"
        print(f"{name:12s}│ Sh {m.get('sharpe',0):.2f}  maxDD {m.get('maxdd',0):6.1f}  "
              f"ann {m.get('ann',0):5.1f}% ({m.get('ann',0)/12:4.2f}%/mes)  Calmar {m.get('calmar',0):.2f}  "
              f"mo+ {m.get('mo_pos',0):3.0f}% │ {wtxt}")

    print("\nLECTURA: vol-targeting SIRVE si en OOS bate al ESTÁTICO en Sharpe/Calmar a igual maxDD Y en")
    print(">50% de folds, con lev medio realista (cap 4x). Si no bate o solo gana full-sample → el ancla")
    print("estática ya captura la adaptación de riesgo defendible (coherente con el gate de régimen descartado).")


if __name__ == "__main__":
    main()
