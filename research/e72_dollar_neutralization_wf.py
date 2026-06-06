"""
E72 — VALIDACIÓN WALK-FORWARD de la dollar-neutralización parcial (Oscar 2026-06-05, confirma e71).

CONTEXTO: e71 mostró que λ≈0.25–0.50 mejora retorno y baja β-dólar al mismo maxDD −10%, PERO con una
bandera amarilla: el beneficio se apoyaba en la mitad OOS (IS bajaba con λ). Antes de fiarnos hay que
verlo walk-forward: ¿un λ FIJO gana OUT-OF-SAMPLE, fold a fold, sin lookahead?

MÉTODO (estándar anti-autoengaño, mismo molde de validación que el resto del repo):
  - Folds rodantes: train 365d → embargo 14d → test 90d, avanzando. El embargo evita fuga por los
    lookbacks de señal (hasta 60d).
  - El LEVERAGE se ancla a maxDD −10% SOLO con datos del TRAIN (sin lookahead), y se APLICA al test.
  - Para cada λ FIJO ∈ {0, 0.25, 0.5, 0.75, 1.0} se concatenan los retornos de TEST de todos los folds
    → serie OOS pura. Se mide Sharpe/ann/maxDD/β-reg OOS y el % de folds en que cada λ bate a λ=0.
  - λ=0 = baseline (sin neutralizar). El GANADOR debe batir a λ=0 en la serie OOS Y en mayoría de folds.

No toca producción. python -m research.e72_dollar_neutralization_wf
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel,
                           DRIVER, SLEEVES)
from research.e60_concentration_cap_aggregate import xs_panel, carry_panel, trend_panel, _maxdd
from research.e71_dollar_neutralization import neutralize, book_returns, anchor_lev, reg_beta
from kepler.portfolio import vol_parity_weights, metrics

TRAIN_D, EMBARGO_D, TEST_D = 365, 14, 90
LAMBDAS = [0.0, 0.25, 0.50, 0.75, 1.0]


def build_book():
    """Reconstruye book_1x diario + beta_daily + rd (idéntico a e71)."""
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    series, panels = {}, {}
    score_map = {
        "mom_30d":    (alphas.xs_momentum_score(ret, 720), 720),
        "rev_60d":    (alphas.xs_reversal_score(ret, 1440), 1440),
        "lowvol_14d": (alphas.xs_lowvol_score(ret, 336), 336),
        "takerflow_5d": (alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120),
        "hlpos_14d":  (alphas.xs_hlposition_score(C, 336), 336),
    }
    for name, typ, hold in SLEEVES:
        if name in score_map:
            sc, h = score_map[name]
            series[name] = xs_sleeve(C, ret, beta, sc, h)[0]
            panels[name] = xs_panel(C, ret, beta, sc, h)
        elif typ == "carry":
            series[name] = carry_sleeve(C, ret, beta)[0]
            panels[name] = carry_panel(C, ret)
        else:
            series[name] = trend_sleeve(C)[0]
            panels[name] = trend_panel(C)
    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    book_1x = pd.DataFrame(0.0, index=panels["trend"].index, columns=C.columns)
    for name in series:
        p = panels[name].reindex(book_1x.index).ffill().fillna(0.0)
        book_1x = book_1x.add(float(vp[name]) * p, fill_value=0.0)
    rd = C.resample("1D").last().reindex(book_1x.index).pct_change()
    beta_daily = beta.resample("1D").last().reindex(book_1x.index).ffill().fillna(0.0)
    return book_1x, beta_daily, rd


def folds(idx):
    """Genera (train_slice, test_slice) rodantes con embargo. idx = DatetimeIndex diario ordenado."""
    out = []
    n = len(idx); i = TRAIN_D
    while i + EMBARGO_D + TEST_D <= n:
        tr = idx[i - TRAIN_D:i]
        te = idx[i + EMBARGO_D:i + EMBARGO_D + TEST_D]
        out.append((tr, te))
        i += TEST_D
    return out


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E72 — walk-forward de la dollar-neutralización (train 365d · embargo 14d · test 90d · lev anclado en TRAIN)\n")
    book_1x, beta_daily, rd = build_book()
    rd_btc = rd[DRIVER]
    # neutralización es por-día independiente → precomputar el libro por cada λ
    books = {lam: neutralize(book_1x, beta_daily, lam) for lam in LAMBDAS}
    idx = book_1x.index
    fl = folds(idx)
    print(f"{len(fl)} folds OOS · {idx[0].date()} → {idx[-1].date()}\n")

    oos = {lam: [] for lam in LAMBDAS}           # retornos de test concatenados
    fold_ann = {lam: [] for lam in LAMBDAS}      # ann por fold (para win-rate)
    for k, (tr, te) in enumerate(fl):
        for lam in LAMBDAS:
            bn = books[lam]
            lev = anchor_lev(bn.loc[tr], rd.loc[tr])              # ancla SOLO con train (sin lookahead)
            r_te, _ = book_returns(bn.loc[te], rd.loc[te], lev)   # aplica al test
            oos[lam].append(r_te)
            fold_ann[lam].append(metrics(r_te).get("ann", float("nan")))

    print(f"{'λ FIJO':8s}│ {'OOS concatenado (futuro nunca visto)':>50s} │ {'robustez':>22s}")
    print("─" * 100)
    base_ann = np.array(fold_ann[0.0])
    for lam in LAMBDAS:
        r = pd.concat(oos[lam]).sort_index()
        m = metrics(r); rb = reg_beta(r, rd_btc)
        ann_arr = np.array(fold_ann[lam])
        win = float(np.mean(ann_arr > base_ann)) * 100 if lam != 0.0 else float("nan")
        wtxt = f"bate λ0 en {win:.0f}% folds" if lam != 0.0 else "(baseline)"
        print(f"λ={lam:.2f}  │ Sh {m.get('sharpe',0):.2f}  maxDD {m.get('maxdd',0):6.1f}  "
              f"ann {m.get('ann',0):5.1f}% ({m.get('ann',0)/12:4.2f}%/mes)  mo+ {m.get('mo_pos',0):3.0f}%  "
              f"βreg {rb:+.2f} │ {wtxt:>22s}")

    print("\nLECTURA: el GANADOR bate a λ=0 en la serie OOS concatenada (Sharpe/ann a maxDD −10%) Y en la")
    print("MAYORÍA de folds (>50%). Si solo gana en agregado pero pierde en la mitad de folds → frágil,")
    print("apoyado en pocos tramos (confirma la bandera amarilla de e71). Si gana consistente → candidato firme.")


if __name__ == "__main__":
    main()
