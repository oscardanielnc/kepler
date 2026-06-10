"""
E79 — VALIDACIÓN sobre el libro LOW-BARRIER (el vivo) de los 2 overlays de PRODUCTO que Oscar aprobó
activar (2026-06-10): λ=0.25 dollar-neutral (e72) + vol-targeting sim-40d (e73).

POR QUÉ OTRO BACKTEST (regla de oro): e72/e73 se validaron sobre el libro FULL-20. El vivo es
LOW-BARRIER (13 coins de $5, β-neutralizado ENTRE coins, e77/e78) → hay que re-validar sobre la
ruta real antes de tocar producción. Además hay un hallazgo ESTRUCTURAL:

PARTE 1 — λ dollar-neutral: el libro low-barrier ya fuerza β-dólar Σwβ=0 CADA DÍA entre los coins
baratos (`lowbarrier._beta_neutralize`) → el λ de e72 (cancelar una fracción de Σwβ vía hedge) ya
está INCORPORADO Y SUPERADO por construcción (equivale a λ=1 sobre la β-dólar; por eso el β vivo es
−0.011 vs +0.19 del full). Lo único neutralizable que queda es el NET-$ puro (Σw ≠ 0 aunque Σwβ=0).
Esta parte (a) lo verifica con números, (b) prueba el ANÁLOGO restante: cancelar una fracción λnet
del net-$ ENTRE los coins baratos con una proyección que PRESERVA Σwβ=0, walk-forward.

PARTE 2 — vol-targeting sim-40d (Moreira-Muir lento, e73): camino de leverage L_t ∝ 1/vol_EWMA40
causal del libro low-barrier (costes reales maker+slip por liquidez), re-anclado a maxDD −10%.
Full-sample exploratorio + WALK-FORWARD (train 365d · embargo 14d · test 90d, s anclado SOLO en
train). Criterio e73: PASA como dial de robustez si OOS reduce el DESBORDAMIENTO del maxDD vs el
estático y mejora Sharpe/Calmar/mo+, con coste de retorno chico y lev realista. Extra producción:
rango del lev dinámico (para la banda de checks) y nº de patas a $300 en los cuantiles del lev.

No toca producción. python -m research.e79_lowbarrier_product_overlays
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import lowbarrier
from kepler.engine import load, load_panel, DRIVER
from kepler.portfolio import metrics
from research.e72_dollar_neutralization_wf import folds, TRAIN_D, EMBARGO_D, TEST_D  # noqa: F401
from research.e76_position_count_frontier import half_sh, beta_to_btc

H   = config.LEVERAGE_HAIRCUT      # 0.95
T   = config.TARGET_MAXDD          # 0.10
CAP = config.MAX_STRAT_LEVERAGE    # 4.0
SPAN = 40                          # sim-40d (el ganador de e73; rápidas 10/20d = whipsaw, descartadas)
LAMNETS = [0.0, 0.25, 0.50, 0.75, 1.0]


def _maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float(abs((eq / eq.cummax() - 1).min()))


def book_ret_path(W: pd.DataFrame, rd: pd.DataFrame, cost: pd.Series, L) -> pd.Series:
    """Retorno del libro W escalado por el camino de leverage L (escalar o Series por-día).
    Mismo accounting que lowbarrier._book_return (coste por símbolo); el turnover de AJUSTAR
    el leverage día a día CUENTA (positions = L_t·W_t)."""
    BL = W.mul(L, axis=0) if hasattr(L, "__len__") else W * L
    held = BL.shift(1).reindex(rd.index).fillna(0.0)
    turn = (BL - BL.shift(1)).abs().reindex(rd.index).fillna(0.0)
    c = (turn * cost.reindex(W.columns).fillna(cost.median())).sum(axis=1)
    return ((held * rd).sum(axis=1) - c).dropna()


def anchor_scalar(W, rd, cost, path) -> float:
    """Escalar s tal que maxDD del libro con L=clip(s·path,0,CAP) = −T (bisección, sin haircut;
    el haircut se aplica al usarlo, igual que producción)."""
    def dd(s):
        L = (path * s).clip(0, CAP) if hasattr(path, "clip") else min(max(path * s, 0), CAP)
        return _maxdd(book_ret_path(W, rd, cost, L))
    lo, hi = 0.01, CAP
    if dd(hi) < T:
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        if dd(mid) > T:
            hi = mid
        else:
            lo = mid
    return lo


def sim_path(r1: pd.Series, index, span=SPAN) -> pd.Series:
    """Camino simétrico 1/vol_EWMA(span), causal (shift 1), normalizado a media 1 (la
    normalización la absorbe el escalar de anclado; en producción se normaliza con la
    historia disponible = causal en el momento de decidir)."""
    vol = r1.ewm(span=span, min_periods=span).std().shift(1).reindex(index)
    vol = vol.replace(0, np.nan).ffill().bfill()
    inv = 1.0 / vol
    return inv / inv.mean()


# El transform vive en PRODUCCIÓN (lowbarrier._net_neutralize, validado aquí) — fuente única de verdad:
# e79 valida la MISMA función que corre el motor (patrón e78 "ejercita la ruta real").
dollar_neutralize_keepbeta = lowbarrier._net_neutralize


def describe(r: pd.Series, rd_btc: pd.Series, label: str, extra: str = ""):
    m = metrics(r)
    b = beta_to_btc(r, rd_btc)
    print(f"{label:14s}│ Sh {m.get('sharpe',0):5.2f}  maxDD {m.get('maxdd',0):6.1f}  "
          f"ann {m.get('ann',0):5.1f}% ({m.get('ann',0)/12:4.2f}%/mes)  Calmar {m.get('calmar',0):4.2f}  "
          f"mo+ {m.get('mo_pos',0):3.0f}%  β {b:+.3f} {extra}")
    return m


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E79 — overlays de PRODUCTO (λ + vol-targeting sim-40d) sobre el libro LOW-BARRIER vivo\n")

    # El experimento aplica λnet ÉL MISMO sobre el libro BASE (e77/e78) → anular el λ de config para
    # no neutralizar dos veces (tras e79, producción corre con LOW_BARRIER_NET_LAMBDA=0.25).
    config.LOW_BARRIER_NET_LAMBDA = 0.0

    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    Wlb, book_ret, df, vp, beta, last_w, rd = lowbarrier.low_barrier_book(C, panels)
    beta_daily = beta.resample("1D").last().reindex(Wlb.index).ffill().fillna(0.0)
    keep = [s for s in config.LOW_BARRIER_UNIVERSE if s in C.columns]
    adv = panels["quote_volume"].resample("1D").sum().mean()
    adv_M = (adv.reindex(C.columns).fillna(1.0) / 1e6).clip(lower=1.0)
    cost = pd.Series(config.MAKER_FEE, index=C.columns) + lowbarrier._slip(adv_M, list(C.columns))
    rd_btc = rd[DRIVER]
    idx = Wlb.index

    # ════ PARTE 1 — ¿queda algo que λ pueda neutralizar? ════
    print("══ PARTE 1 · λ dollar-neutral: ¿qué queda por neutralizar en el libro low-barrier? ══")
    bdol = (Wlb * beta_daily).sum(axis=1)          # β-dólar diaria (Σwβ) — debería ser ~0 por construcción
    net = Wlb.sum(axis=1)                          # net-$ puro (Σw)
    gross = Wlb.abs().sum(axis=1).replace(0, np.nan)
    print(f"β-dólar (Σwβ) diaria:  |mediana| {bdol.abs().median():.4f} · p95 {bdol.abs().quantile(0.95):.4f}"
          f"  ← e72 neutralizaba ESTO; el full-20 vivía en +0.24/+0.49")
    print(f"net-$    (Σw)  diaria:  mediana {net.median():+.4f} · p95 |{net.abs().quantile(0.95):.4f}|"
          f" · net/gross mediana {(net/gross).median():+.2%}")
    print("→ si Σwβ≈0: el λ de e72 YA está incorporado por construcción (equivale a λ=1 sobre β-dólar).")
    print("  Lo único restante = net-$. Probamos su análogo λnet (preserva Σwβ=0), walk-forward:\n")

    books = {lam: dollar_neutralize_keepbeta(Wlb, beta_daily, keep, lam) for lam in LAMNETS}
    fl = folds(idx)
    print(f"{len(fl)} folds OOS · {idx[0].date()} → {idx[-1].date()} · lev anclado SOLO en train (×haircut {H})")
    oos = {lam: [] for lam in LAMNETS}; fold_ann = {lam: [] for lam in LAMNETS}
    for tr, te in fl:
        for lam in LAMNETS:
            Wn = books[lam]
            s = anchor_scalar(Wn.loc[tr], rd.loc[tr], cost, 1.0)
            r_te = book_ret_path(Wn.loc[te], rd.loc[te], cost, min(s * H, CAP))
            oos[lam].append(r_te); fold_ann[lam].append(metrics(r_te).get("ann", float("nan")))
    base_ann = np.array(fold_ann[0.0])
    for lam in LAMNETS:
        r = pd.concat(oos[lam]).sort_index()
        win = float(np.nanmean(np.array(fold_ann[lam]) > base_ann)) * 100
        wtxt = "(baseline)" if lam == 0.0 else f"bate λnet0 en {win:.0f}% folds"
        nlast = books[lam].sum(axis=1).tail(252)
        s1, s2 = half_sh(r)
        describe(r, rd_btc, f"λnet={lam:.2f}", f"│ net~{nlast.median():+.3f} IS/OOS {s1:.2f}/{s2:.2f} {wtxt}")

    # stress slippage ×3 (molde e77) sobre baseline y candidatos — el hedge λnet añade turnover; ¿lo paga?
    print("\nSTRESS slippage ×3 (WF, mismos folds):")
    cost3 = pd.Series(config.MAKER_FEE, index=C.columns) + lowbarrier._slip(adv_M, list(C.columns), mult=3.0)
    for lam in LAMNETS:
        oos3 = []
        for tr, te in fl:
            s = anchor_scalar(books[lam].loc[tr], rd.loc[tr], cost3, 1.0)
            oos3.append(book_ret_path(books[lam].loc[te], rd.loc[te], cost3, min(s * H, CAP)))
        describe(pd.concat(oos3).sort_index(), rd_btc, f"λnet={lam:.2f} ×3")

    # patas a $300: el hedge λnet reparte Δ entre los 13 coins → ¿abre patas nuevas colocables?
    print("\nPATAS a $300 con lev estático del libro λnet (media últ. 252d, |w·lev·300| ≥ $5):")
    for lam in LAMNETS:
        s = anchor_scalar(books[lam], rd, cost, 1.0)
        lv = min(s * H, CAP)
        legs = (books[lam].tail(252).abs().mul(lv * 300) >= 5.0).sum(axis=1).mean()
        print(f"   λnet={lam:.2f} → lev {lv:.2f} → ~{legs:.0f} patas")

    # ════ PARTE 2 — vol-targeting sim-40d ════
    print("\n══ PARTE 2 · vol-targeting sim-40d (camino L_t ∝ 1/vol_EWMA40, re-anclado a −10%) ══")
    r1 = book_ret_path(Wlb, rd, cost, 1.0)
    paths = {"estatico": pd.Series(1.0, index=idx), f"sim_{SPAN}d": sim_path(r1, idx)}

    print("FULL-SAMPLE (exploratorio):")
    lev_full = {}
    for name, bp in paths.items():
        s = anchor_scalar(Wlb, rd, cost, bp)
        L = (bp * s * H).clip(0, CAP)
        lev_full[name] = L
        r = book_ret_path(Wlb, rd, cost, L)
        Lv = L.reindex(r.index)
        describe(r, rd_btc, name, f"│ lev μ{Lv.mean():.2f} [{Lv.quantile(0.05):.2f}–{Lv.quantile(0.95):.2f}] máx{Lv.max():.2f}")

    print("\nWALK-FORWARD (EL VEREDICTO — s anclado SOLO en train · 365d · embargo 14d · test 90d):")
    oos2 = {n: [] for n in paths}; fold_ann2 = {n: [] for n in paths}; lev_oos = {n: [] for n in paths}
    for tr, te in fl:
        for name, bp in paths.items():
            s = anchor_scalar(Wlb.loc[tr], rd.loc[tr], cost, bp.loc[tr])
            L_te = (bp.loc[te] * s * H).clip(0, CAP)
            r_te = book_ret_path(Wlb.loc[te], rd.loc[te], cost, L_te)
            oos2[name].append(r_te); fold_ann2[name].append(metrics(r_te).get("ann", float("nan")))
            lev_oos[name].append(L_te)
    base_ann2 = np.array(fold_ann2["estatico"])
    for name in paths:
        r = pd.concat(oos2[name]).sort_index()
        Lc = pd.concat(lev_oos[name]).sort_index()
        win = float(np.nanmean(np.array(fold_ann2[name]) > base_ann2)) * 100
        wtxt = "(baseline)" if name == "estatico" else f"bate estático {win:.0f}% folds"
        describe(r, rd_btc, name, f"│ lev μ{Lc.mean():.2f} [{Lc.quantile(0.05):.2f}–{Lc.quantile(0.95):.2f}] máx{Lc.max():.2f} {wtxt}")

    # ── extra de producción: rango del lev dinámico (banda checks) + patas a $300 ──
    Lsim = lev_full[f"sim_{SPAN}d"]
    print(f"\nRANGO DEL LEV sim-{SPAN}d (full, ×haircut): p01 {Lsim.quantile(0.01):.2f} · p05 {Lsim.quantile(0.05):.2f} · "
          f"p50 {Lsim.quantile(0.50):.2f} · p95 {Lsim.quantile(0.95):.2f} · p99 {Lsim.quantile(0.99):.2f}"
          f"  ← calibrar checks.LEV_BAND_LOW_BARRIER")
    W252 = Wlb.tail(252)
    print(f"PATAS a $300 (media últ. 252d, |w·lev·300| ≥ $5):")
    for q in [0.05, 0.50, 0.95]:
        lv = float(Lsim.quantile(q))
        legs = (W252.abs().mul(lv * 300) >= 5.0).sum(axis=1).mean()
        print(f"   lev p{int(q*100):02d} = {lv:.2f} → ~{legs:.0f} patas")

    print("\nVEREDICTO:")
    print("· PARTE 1: si Σwβ≈0 → λ=0.25 (e72) ya está DENTRO del low-barrier por construcción → no hay nada")
    print("  que activar; λnet solo se considera si mejora (o empata) retorno OOS bajando net-$ (lección e72:")
    print("  el net-long es prima de riesgo — lo esperable es que cueste retorno).")
    print("· PARTE 2: sim-40d PASA como dial de robustez/producto si OOS desborda MENOS el ancla −10% que el")
    print("  estático, con Calmar/mo+ iguales o mejores y coste de retorno chico (~e73: −6%). Si pasa → producción.")


if __name__ == "__main__":
    main()
