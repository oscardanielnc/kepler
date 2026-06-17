"""
E80 — RE-NEUTRALIZAR EL LIBRO TRAS EL CAPITAL-DROP (2026-06-17). Drift β-dólar en producción.
==============================================================================================
SÍNTOMA (log 06-12→06-17, REAL $292): el β-DÓLAR del libro VIVO derivó a −0.075 (era ~0), mientras el
β-MODELO seguía ~0. Bleed −2.1% dominado por el short book en un rally de alts. El engine ENVÍA un libro
β-neutral (Σwβ=0) y net-cancelado (λ=0.25, e79) — pero `execution._capital_aware_drop` suelta las patas
sub-min-notional y **solo renormaliza el GROSS**, sin re-neutralizar β ni net. A $292 las patas soltadas
son las LARGAS chicas (SOL $2.7, ADA $2.2) → el libro real queda net-SHORT / β≠0. La neutralidad que e77/e79
construyeron se PIERDE en el último paso, justo en el libro que el copiador opera.

HIPÓTESIS: re-aplicar β-neutralize (+ net-neutralize λ) SOBRE LAS PATAS SUPERVIVIENTES, después del drop,
restaura la neutralidad del libro real sin cambiar el universo ni el edge → menos β/net residual = menos
sangrado direccional en rallies, sin coste de Sharpe.

PRUEBA (walk-forward IS/OOS, costes+slippage reales, re-ancla cada variante a −10% maxDD → compara a MISMO
riesgo, lógica flywheel de CLAUDE.md). Para cada capital {300,500,750,1000} y cada política de drop:
  A · gross-only   = status quo (`_capital_aware_drop` actual): drop → renorm gross.
  B · β-aware      = drop → β-neutralize supervivientes → renorm gross.
  C · β+net (0.25) = drop → β-neutralize → net-neutralize(λ=0.25) supervivientes → renorm gross.
Métricas: Sharpe, %/mes, maxDD, β-to-BTC, IS/OOS, nº-pos, y los DOS residuales que miden el drift:
  net-$ residual = media |Σw|/gross   ·   β-$ residual = media |Σwβ|/gross   (en la cola 252d).

Reusa la maquinaria de e76/e77. NO toca producción. python -m research.e80_capital_drop_neutrality
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from kepler.engine import load, load_panel, _beta, DRIVER
from kepler.portfolio import metrics, leverage_for_maxdd_anchor
from research.e18_slippage import adv_usd
from research.e53_thin_coins import slip_adv
from research.e76_position_count_frontier import (build_book, book_return,
                                                  floor_capital, get_min_notionals, half_sh, beta_to_btc)
from research.e77_cheap_universe_low_barrier import renorm_gross, beta_neutralize

MAKER = config.MAKER_FEE; HAIRCUT = config.LEVERAGE_HAIRCUT; TMDD = config.TARGET_MAXDD
LAM = config.LOW_BARRIER_NET_LAMBDA


def net_neutralize(W, beta_daily, keep_cols, lam):
    """Cancela una fracción λ del NET-$ (Σw) repartida ENTRE keep_cols, preservando Σwβ=0 (e79).
    Espejo de lowbarrier._net_neutralize pero con keep_cols como argumento (set fijo)."""
    if not lam:
        return W.copy()
    B = beta_daily.reindex(W.index).reindex(columns=W.columns).fillna(0.0)
    cols = list(W.columns); kidx = np.array([cols.index(c) for c in keep_cols if c in cols])
    A = W.values.astype(float).copy(); Bv = B.values.astype(float); ones = np.ones(len(kidx))
    for i in range(len(A)):
        w = A[i]; bk = Bv[i][kidx]
        M = np.array([[bk @ bk, bk @ ones], [bk @ ones, float(len(kidx))]])
        try:
            x = np.linalg.solve(M, np.array([0.0, lam * float(w.sum())]))
        except np.linalg.LinAlgError:
            continue
        wn = w.copy(); wn[kidx] -= bk * x[0] + ones * x[1]
        g0 = np.abs(w).sum(); g1 = np.abs(wn).sum()
        if g1 > 0:
            A[i] = wn * (g0 / g1)
    return pd.DataFrame(A, index=W.index, columns=W.columns)


def constrain_gross(W, minnot, L, capital):
    """A · STATUS QUO. Cada día suelta las patas |w|·L·capital < min-notional; renorm GROSS (idéntico a
    execution._capital_aware_drop y a e77.constrain). Mejor caso copiador: redespliega el capital liberado."""
    A = W.values.astype(float); cols = list(W.columns)
    mn = np.array([minnot[c] for c in cols]); out = np.zeros_like(A)
    for r in range(A.shape[0]):
        row = A[r]; keep = (np.abs(row) * L * capital) >= mn
        kr = np.where(keep, row, 0.0)
        g0 = np.abs(row).sum(); g1 = np.abs(kr).sum()
        if g1 > 0: kr *= (g0 / g1)
        out[r] = kr
    return pd.DataFrame(out, index=W.index, columns=W.columns)


def constrain_reneut(W, beta_daily, minnot, L, capital, lam=0.0):
    """B/C · RE-NEUTRALIZA tras el drop. Suelta patas sub-min-notional y re-aplica β-neutralize (y, si
    lam>0, net-neutralize λ) SOBRE LAS SUPERVIVIENTES de ESE día (keep varía por fila), luego renorm gross.
    Esto es lo que haría un `_capital_aware_drop` β/net-aware en execution."""
    B = beta_daily.reindex(W.index).reindex(columns=W.columns).fillna(0.0)
    A = W.values.astype(float); Bv = B.values.astype(float); cols = list(W.columns)
    mn = np.array([minnot[c] for c in cols]); out = np.zeros_like(A)
    for r in range(A.shape[0]):
        row = A[r]; g0 = np.abs(row).sum()
        keepm = (np.abs(row) * L * capital) >= mn
        kr = np.where(keepm, row, 0.0)
        kidx = np.where(keepm)[0]
        if len(kidx) == 0 or g0 == 0:
            continue
        bk = Bv[r][kidx]; wk = kr[kidx]
        # 1) β-neutralize sobre supervivientes (Σwβ=0)
        den = float(bk @ bk)
        if den > 0:
            wk = wk - bk * (float(wk @ bk) / den)
        # 2) net-neutralize λ sobre supervivientes (preserva Σwβ=0)
        if lam:
            ones = np.ones(len(kidx))
            M = np.array([[bk @ bk, bk @ ones], [bk @ ones, float(len(kidx))]])
            try:
                x = np.linalg.solve(M, np.array([0.0, lam * float(wk.sum())]))
                wk = wk - (bk * x[0] + ones * x[1])
            except np.linalg.LinAlgError:
                pass
        kr[:] = 0.0; kr[kidx] = wk
        g1 = np.abs(kr).sum()
        if g1 > 0: kr *= (g0 / g1)
        out[r] = kr
    return pd.DataFrame(out, index=W.index, columns=W.columns)


def residuals(W, beta_daily):
    """Drift residual del libro (cola 252d): media |Σw|/gross (net-$) y media |Σwβ|/gross (β-$)."""
    B = beta_daily.reindex(W.index).reindex(columns=W.columns).fillna(0.0)
    g = W.abs().sum(axis=1); m = g > 1e-9
    net = (W.sum(axis=1).abs() / g)[m].tail(252).mean()
    bdol = ((W * B).sum(axis=1).abs() / g)[m].tail(252).mean()
    return float(net), float(bdol)


def evalbook(W, rd, cost, minnot, rd_btc, beta_daily):
    r = book_return(W, rd, cost)
    if len(r.dropna()) < 60: return None
    L = min(HAIRCUT * leverage_for_maxdd_anchor(r, TMDD), config.MAX_STRAT_LEVERAGE)
    m = metrics(r * L)
    if not m: return None
    s1, s2 = half_sh(r); b = beta_to_btc(r, rd_btc)
    avg = (W.abs() > 1e-6).sum(axis=1).tail(252).mean()
    net, bdol = residuals(W, beta_daily)
    return dict(sharpe=m["sharpe"], mes=m["ann"] / 12, maxdd=m["maxdd"], beta=b, s1=s1, s2=s2,
                avg=avg, net=net, bdol=bdol, L=L)


def row(tag, d):
    return (f"{tag:>18s} │ {d['sharpe']:>6.2f} {d['mes']:>5.2f}% {d['maxdd']:>6.1f} {d['beta']:>+6.3f} "
            f"{d['s1']:>5.2f}/{d['s2']:<5.2f} {d['avg']:>4.0f} │ {d['net']:>6.3f} {d['bdol']:>6.3f}")


HDR = (f"{'variante':>18s} │ {'Sharpe':>6s} {'%/mes':>6s} {'maxDD':>6s} {'beta':>6s} {'IS/OOS':>11s} "
       f"{'pos':>4s} │ {'net-$':>6s} {'β-$':>6s}")


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E80 — RE-NEUTRALIZAR EL LIBRO TRAS EL CAPITAL-DROP (drift β-dólar en producción)\n")
    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    ret = np.log(C).diff(); beta_daily = _beta(ret).resample("1D").last()
    adv = adv_usd(panels["quote_volume"]).reindex(C.columns).fillna(0.0); adv_M = (adv / 1e6).clip(lower=1.0)
    cost = pd.Series(MAKER, index=C.columns) + slip_adv(adv_M, list(C.columns), 1.0)
    minnot, src = get_min_notionals(list(C.columns))
    cheap = [c for c in config.LOW_BARRIER_UNIVERSE if c in C.columns]

    # BASE = libro low-barrier que el ENGINE envía: renorm_gross → β-neutralize → net-neutralize(λ=0.25)
    W, df, vp = build_book(C, panels)
    rd = C.resample("1D").last().pct_change().reindex(W.index).fillna(0.0); rd_btc = rd[DRIVER]
    base = net_neutralize(beta_neutralize(renorm_gross(W, cheap), beta_daily, cheap), beta_daily, cheap, LAM)
    beta_daily = beta_daily.reindex(base.index).reindex(columns=C.columns).fillna(0.0)

    print(f"min-notional ({src}) · universo low-barrier ×{len(cheap)} · λnet={LAM}")
    d0 = evalbook(base, rd, cost, minnot, rd_btc, beta_daily)
    print("\nBASE — libro que el ENGINE envía (sin capital-drop), re-anclado a −10% maxDD:")
    print(HDR); print("─" * 86); print(row("ENGINE base", d0))
    L = d0["L"]

    print(f"\nSIMULACIÓN REAL por capital — leverage base L≈{L:.2f}x · 3 políticas de drop")
    print("  net-$ / β-$ = residual de neutralidad del libro REAL (↓ mejor; status quo los rompe).")
    for cap in [300, 500, 750, 1000]:
        print(f"\n  ── capital ${cap} ──"); print(HDR); print("─" * 86)
        WA = constrain_gross(base, minnot, L, cap)
        WB = constrain_reneut(base, beta_daily, minnot, L, cap, lam=0.0)
        WC = constrain_reneut(base, beta_daily, minnot, L, cap, lam=LAM)
        for tag, Wx in [("A gross-only(hoy)", WA), ("B β-aware", WB), (f"C β+net({LAM})", WC)]:
            d = evalbook(Wx, rd, cost, minnot, rd_btc, beta_daily)
            if d: print(row(tag, d))

    print("\nVEREDICTO: si B/C bajan net-$ y β-$ residual a ~0 (vs A que los deja altos) SIN perder Sharpe ni")
    print("empeorar maxDD a $300-500 → re-neutralizar tras el drop es mejora pura → cambiar _capital_aware_drop.")
    print("Si B/C no mejoran el riesgo o cuestan Sharpe → el drift es cosmético y NO se toca producción.")


if __name__ == "__main__":
    main()
