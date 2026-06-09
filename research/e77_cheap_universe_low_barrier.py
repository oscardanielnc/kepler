"""
E77 — UNIVERSO BARATO / BARRERA BAJA (2026-06-09). PUNTO DE QUIEBRE del copy-lead.
==================================================================================
e76 mostró: reducir Nº-posiciones NO baja el floor por debajo de ~$1500 — lo CLAVAN los símbolos caros
(BTC $50, ETH-tier $20) cuando caen con peso chico. Idea de Oscar: NO operar esos símbolos, sino
correlacionados BARATOS ($5 min-notional) que se comporten igual. Objetivo: barrera ≤ $500 (idealmente menos)
sin perder edge ni neutralidad. Si NINGUNA variante lo logra → el proyecto no es viable y se cancela.

PRUEBAS:
  1. ¿Sobrevive el edge en los 14 símbolos de $5 (sin BTC/ETH/BCH/ETC/LINK/LTC)?
  2. Re-hedge de β DENTRO del universo barato (neutralizar Σwβ usando solo coins de $5, sin tocar BTC).
  3. SIMULACIÓN REAL a capital bajo: a $300/$500/$750/$1000, soltar las patas que no superan su min-notional,
     re-anclar a −10% maxDD, y medir Sharpe/maxDD/β/nº-pos REALES (lo que un copiador de $500 experimenta).
  4. Frontera Nº-pos sobre el universo barato (¿menos patas baratas baja aún más la barrera?).

Reusa la maquinaria validada de e76. No toca producción. python -m research.e77_cheap_universe_low_barrier
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
from research.e76_position_count_frontier import (build_book, book_return, truncate,
                                                  floor_capital, get_min_notionals, half_sh, beta_to_btc)

MAKER = config.MAKER_FEE; HAIRCUT = config.LEVERAGE_HAIRCUT; TMDD = config.TARGET_MAXDD


def renorm_gross(W, keep_cols):
    """Cero fuera de keep_cols; renormaliza cada fila para preservar el gross original (Σ|w| de las 20)."""
    g0 = W.abs().sum(axis=1)
    Wk = W.copy(); drop = [c for c in W.columns if c not in keep_cols]
    Wk[drop] = 0.0
    g1 = Wk.abs().sum(axis=1).replace(0, np.nan)
    return Wk.mul((g0 / g1).fillna(0.0), axis=0)


def beta_neutralize(W, beta_daily, keep_cols):
    """Neutraliza la β-dólar (Σ wᵢ βᵢ) usando SOLO las coins de keep_cols: wᵢ -= c·βᵢ con
    c = Σwβ/Σβ² (mínimo ajuste). Renormaliza al gross original. No usa BTC."""
    g0 = W.abs().sum(axis=1)
    B = beta_daily.reindex(W.index).reindex(columns=W.columns).fillna(0.0)
    mask = pd.Series(0.0, index=W.columns); mask[keep_cols] = 1.0
    Bk = B.mul(mask, axis=1)
    num = (W * Bk).sum(axis=1); den = (Bk * Bk).sum(axis=1).replace(0, np.nan)
    c = (num / den).fillna(0.0)
    Wn = W.sub(Bk.mul(c, axis=0))
    g1 = Wn.abs().sum(axis=1).replace(0, np.nan)
    return Wn.mul((g0 / g1).fillna(0.0), axis=0)


def constrain(W, minnot, L, capital):
    """Simula operar con `capital`: cada día suelta las patas cuyo notional (|w|·L·capital) < min_notional;
    renormaliza las que quedan al gross de ese día (redespliega el capital liberado = mejor caso copiador)."""
    A = W.values.astype(float); cols = list(W.columns)
    mn = np.array([minnot[c] for c in cols]); out = np.zeros_like(A)
    for r in range(A.shape[0]):
        row = A[r]; notion = np.abs(row) * L * capital
        keep = notion >= mn
        kr = np.where(keep, row, 0.0)
        g0 = np.abs(row).sum(); g1 = np.abs(kr).sum()
        if g1 > 0: kr *= (g0 / g1)
        out[r] = kr
    return pd.DataFrame(out, index=W.index, columns=W.columns)


def evalbook(W, rd, cost, minnot, rd_btc, tag=""):
    r = book_return(W, rd, cost)
    if len(r.dropna()) < 60: return None
    L = min(HAIRCUT * leverage_for_maxdd_anchor(r, TMDD), config.MAX_STRAT_LEVERAGE)
    m = metrics(r * L)
    if not m: return None
    s1, s2 = half_sh(r); b = beta_to_btc(r, rd_btc)
    avg = (W.abs() > 1e-6).sum(axis=1).tail(252).mean()
    Wlev = (W * L).clip(-config.MAX_POSITION_EQUITY, config.MAX_POSITION_EQUITY)
    f_med, f_p90, f_now = floor_capital(Wlev, minnot)
    return dict(sharpe=m["sharpe"], mes=m["ann"] / 12, maxdd=m["maxdd"], beta=b, s1=s1, s2=s2,
                avg=avg, f_med=f_med, f_p90=f_p90, f_now=f_now, L=L)


def line(N, d):
    return (f"{N:>16s} │ {d['sharpe']:>6.2f} {d['mes']:>5.2f}% {d['maxdd']:>6.1f} {d['beta']:>+6.3f} "
            f"{d['s1']:>5.2f}/{d['s2']:<5.2f} {d['avg']:>4.0f} │ ${d['f_med']:>7.0f} ${d['f_p90']:>7.0f}")


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E77 — UNIVERSO BARATO / BARRERA BAJA (punto de quiebre copy-lead)\n")
    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    ret = np.log(C).diff(); beta_daily = _beta(ret).resample("1D").last()
    adv = adv_usd(panels["quote_volume"]).reindex(C.columns).fillna(0.0); adv_M = (adv / 1e6).clip(lower=1.0)
    cost = pd.Series(MAKER, index=C.columns) + slip_adv(adv_M, list(C.columns), 1.0)
    minnot, src = get_min_notionals(list(C.columns))
    cheap = [c for c in C.columns if minnot[c] == 5]
    print(f"min-notional ({src}): cheap $5 ×{len(cheap)} · caros ×{len(C.columns)-len(cheap)} "
          f"(BTC$50, ETH/BCH/ETC/LINK/LTC $20)\n")

    W, df, vp = build_book(C, panels)
    rd = C.resample("1D").last().pct_change().reindex(W.index).fillna(0.0); rd_btc = rd[DRIVER]

    Wcheap = renorm_gross(W, cheap)
    Wcheap_h = beta_neutralize(Wcheap, beta_daily, cheap)

    print("PRUEBA 1+2 — ¿sobrevive el edge sin los caros? (cada uno re-anclado a −10% maxDD)")
    print(f"{'variante':>16s} │ {'Sharpe':>6s} {'%/mes':>6s} {'maxDD':>6s} {'beta':>6s} {'IS/OOS':>11s} {'pos':>4s} │ "
          f"{'floor_med':>8s} {'floor_p90':>8s}")
    print("─" * 96)
    for tag, Wx in [("FULL-20 (hoy)", W), ("CHEAP-14 raw", Wcheap), ("CHEAP-14 b-hedge", Wcheap_h)]:
        d = evalbook(Wx, rd, cost, minnot, rd_btc)
        if d: print(line(tag, d))

    print("\nPRUEBA 4 — frontera Nº-pos sobre CHEAP-14 b-hedge (¿menos patas baratas baja más la barrera?)")
    print(f"{'N (cheap)':>16s} │ {'Sharpe':>6s} {'%/mes':>6s} {'maxDD':>6s} {'beta':>6s} {'IS/OOS':>11s} {'pos':>4s} │ "
          f"{'floor_med':>8s} {'floor_p90':>8s}")
    print("─" * 96)
    for N in [6, 8, 10, 12, 14]:
        d = evalbook(truncate(Wcheap_h, N), rd, cost, minnot, rd_btc)
        if d: print(line(f"N={N}", d))

    print("\nPRUEBA 3 — SIMULACIÓN REAL a capital bajo (suelta patas < min-notional, re-ancla −10%):")
    print("  = lo que un copiador/lead de ese capital EXPERIMENTA de verdad.")
    Lref = evalbook(Wcheap_h, rd, cost, minnot, rd_btc)["L"]
    for uni_tag, Wbase in [("FULL-20", W), ("CHEAP-14 b-hedge", Wcheap_h)]:
        print(f"\n  ── universo {uni_tag} (L≈{evalbook(Wbase, rd, cost, minnot, rd_btc)['L']:.2f}x) ──")
        print(f"  {'capital':>8s} │ {'Sharpe':>6s} {'%/mes':>6s} {'maxDD':>6s} {'beta':>6s} {'pos_oper':>8s}")
        Lu = evalbook(Wbase, rd, cost, minnot, rd_btc)["L"]
        for cap in [300, 500, 750, 1000, 1500]:
            Wc = constrain(Wbase, minnot, Lu, cap)
            d = evalbook(Wc, rd, cost, minnot, rd_btc)
            if d:
                print(f"  ${cap:>6d} │ {d['sharpe']:>6.2f} {d['mes']:>5.2f}% {d['maxdd']:>6.1f} {d['beta']:>+6.3f} {d['avg']:>8.0f}")

    print("\nVEREDICTO: si CHEAP-14 conserva Sharpe~full Y β neutral, y la sim a $500 mantiene el edge con")
    print("nº-pos decente → barrera ≤$500 VIABLE → producto rescatado. Si el edge se cae sin BTC/ETH o la")
    print("sim a $500 colapsa (pocas patas, β alta, Sharpe malo) → no es viable a ese capital.")


if __name__ == "__main__":
    main()
