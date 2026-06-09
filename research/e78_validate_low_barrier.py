"""
E78 — VALIDACIÓN del modo LOW-BARRIER en PRODUCCIÓN (2026-06-09).
Ejercita la ruta REAL (kepler.lowbarrier + execution._capital_aware_drop), NO la de research, para
confirmar antes de cualquier deploy (regla de oro): (1) reproduce e77, (2) el target vivo es del universo
barato y β≈0, (3) el dropping adaptativo coloca todo ≥ min-notional y el libro se adapta al capital.
python -m research.e78_validate_low_barrier
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from kepler import lowbarrier, execution
from kepler.engine import load, load_panel, DRIVER
from kepler.portfolio import metrics, leverage_for_maxdd_anchor
from research.e76_position_count_frontier import get_min_notionals, half_sh, beta_to_btc

H, T = config.LEVERAGE_HAIRCUT, config.TARGET_MAXDD


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E78 — VALIDACIÓN modo LOW-BARRIER (ruta de PRODUCCIÓN)\n")
    print(f"config.LOW_BARRIER_MODE = {config.LOW_BARRIER_MODE} · universo {len(config.LOW_BARRIER_UNIVERSE)} coins\n")

    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    minnot, _ = get_min_notionals(list(C.columns))

    # ── 1. libro low-barrier de PRODUCCIÓN, anclado a −10% ──
    Wlb, book_ret, df, vp, beta, last_w, rd = lowbarrier.low_barrier_book(C, panels)
    L = min(H * leverage_for_maxdd_anchor(book_ret, T), config.MAX_STRAT_LEVERAGE)
    m = metrics(book_ret * L); s1, s2 = half_sh(book_ret); b = beta_to_btc(book_ret, rd[DRIVER])
    print("1) LIBRO LOW-BARRIER (producción, anclado −10% maxDD):")
    print(f"   Sharpe {m['sharpe']:.2f} · {m['ann']/12:.2f}%/mes · maxDD {m['maxdd']:.1f} · β {b:+.3f} · "
          f"IS/OOS {s1:.2f}/{s2:.2f} · lev {L:.2f}x")
    print("   (esperado ≈ e77 cheap-13: Sharpe ~1.47 · ~1.9%/mes · β ~−0.01)\n")

    # ── 2. target VIVO (la llamada real del engine) ──
    target, vp2, df2, port, asof, lev, weights, beta_last, beta_model = lowbarrier.compute_low_barrier_target("ESTABLE")
    t = target[target.abs() > 1e-6]
    expensive_in = [s for s in t.index if minnot[s] > 5]
    print("2) TARGET VIVO (compute_low_barrier_target):")
    print(f"   {len(t)} posiciones · gross {t.abs().sum():.2f} · net {t.sum():+.2f} · lev {lev:.2f}x · β-modelo {beta_model:+.3f}")
    print(f"   símbolos caros ($20/$50) en el target: {expensive_in if expensive_in else 'NINGUNO ✓'}")
    print(f"   posiciones: {', '.join(s.replace('USDT','')+f'{w:+.2f}' for s,w in t.sort_values().items())}\n")

    # ── 3. dropping adaptativo al capital (función REAL de execution) ──
    filt = {s: {"minnot": minnot[s]} for s in C.columns}
    print("3) DROPPING ADAPTATIVO (execution._capital_aware_drop) — el libro se ajusta al capital:")
    print(f"   {'capital':>8s} │ {'patas':>5s} │ {'todas ≥ min-notional?':>22s} │ gross")
    for cap in [200, 300, 500, 1000, 1500]:
        ft, dropped = execution._capital_aware_drop(target, cap, filt)
        held = ft[ft.abs() > 1e-6]
        ok = all(abs(w) * cap >= minnot[s] - 1e-6 for s, w in held.items())
        print(f"   ${cap:>6d} │ {len(held):>5d} │ {'✓ sí' if ok else '✗ NO':>22s} │ {held.abs().sum():.2f}")

    # ── 4. simulación histórica del libro adaptado (Sharpe/β reales a cada capital) ──
    def constrain(W, L, cap):
        A = W.values.astype(float); cols = list(W.columns); mn = np.array([minnot[c] for c in cols]); out = np.zeros_like(A)
        for r in range(A.shape[0]):
            row = A[r]; keep = (np.abs(row) * L * cap) >= mn; kr = np.where(keep, row, 0.0)
            g0 = np.abs(row).sum(); g1 = np.abs(kr).sum()
            if g1 > 0: kr *= g0 / g1
            out[r] = kr
        return pd.DataFrame(out, index=W.index, columns=W.columns)
    rdf = rd
    adv = panels["quote_volume"].resample("1D").sum().mean()
    adv_M = (adv.reindex(C.columns).fillna(1.0) / 1e6).clip(lower=1.0)
    cost = pd.Series(config.MAKER_FEE, index=C.columns) + lowbarrier._slip(adv_M, list(C.columns))
    print("\n4) SIMULACIÓN HISTÓRICA del libro adaptado (lo que cada capital EXPERIMENTA, re-anclado −10%, slip real):")
    print(f"   {'capital':>8s} │ {'Sharpe':>6s} {'%/mes':>6s} {'maxDD':>6s} {'β':>7s} {'pos~':>5s}")
    for cap in [300, 500, 1000, 1500]:
        Wc = constrain(Wlb, L, cap)
        bret = lowbarrier._book_return(Wc, rdf, cost)
        Lc = min(H * leverage_for_maxdd_anchor(bret, T), config.MAX_STRAT_LEVERAGE)
        mc = metrics(bret * Lc); bc = beta_to_btc(bret, rdf[DRIVER])
        avg = (Wc.abs() > 1e-6).sum(axis=1).tail(252).mean()
        if mc:
            print(f"   ${cap:>6d} │ {mc['sharpe']:>6.2f} {mc['ann']/12:>5.2f}% {mc['maxdd']:>6.1f} {bc:>+7.3f} {avg:>5.0f}")

    print("\n✅ VEREDICTO: si (1)≈e77, (2) sin símbolos caros y β≈0, (3) todas las patas ≥min-notional a cada")
    print("   capital, y (4) Sharpe/β estables de $300 a $1500 → el modo low-barrier de PRODUCCIÓN es correcto.")


if __name__ == "__main__":
    main()
