"""
E35 — Factor SIZE (small-minus-big), C1. 2026-06-01. Factor canónico que falta (Liu-Tsyvinski-Wu:
mercado+size+momentum). Construcción Fama-French cross-seccional: long small-cap / short large-cap,
β-neutral. Market cap APROXIMADO = mcap_now (CoinPaprika, e34) · precio[t]/precio_now (klines Binance).
⚠️ aproxima supply constante; válido para el RANK de size (chequeo de viabilidad gratis). DOT excluido.

Tests (molde e26/e30 + lente condicional regime_lab, doctrina núcleo+satélite):
  1. Ortogonalidad: corr<0.35 vs los 7, IS/OOS, Δ%/mes al ancla (raw, in-sample).
  2. OOS honesto: walk-forward purgado + CPCV (regime_lab.evaluate) — ¿aporta sin look-ahead de selección?
  3. CONDICIONAL: ¿size potenciado por régimen? (pre-registrado: premium en bull/breadth/risk-on).

python -m research.e35_size_factor
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.regime_lab import (build_base_sleeves, get_regimes, evaluate, run_combo, deflation_bar)

MCAP_JSON = os.path.join(config.DATA_DIR, "marketcap", "current_mcap.json")


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    return metrics(combo * L)["ann"], L


def build_size_score(C):
    """log(market cap) aprox por símbolo, alineado a C. mcap_hist = mcap_now · close/close_now."""
    mc = json.load(open(MCAP_JSON, encoding="utf-8"))
    cols = {}
    for sym, info in mc.items():
        if sym not in C.columns:
            continue
        px = C[sym].dropna()
        if px.empty:
            continue
        cols[sym] = np.log(info["mcap"] * (C[sym] / px.iloc[-1]))   # log market cap aprox
    logmcap = pd.DataFrame(cols).reindex(index=C.index, columns=C.columns)
    return logmcap


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E35 — Factor SIZE (small-minus-big), C1\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    logmcap = build_size_score(C)
    n_cov = logmcap.iloc[-1].notna().sum()
    print(f"Cobertura de market cap: {n_cov} símbolos · {C.index[0].date()}→{C.index[-1].date()}\n")

    base = build_base_sleeves()
    base_ref = evaluate(base, None, "7 base")
    combo0 = (base * vol_parity_weights(base)).sum(axis=1)
    ann0, L0 = anchored(combo0)
    print(f"BASELINE 7 (in-sample): Sharpe {metrics(combo0)['sharpe']:.2f} · @−10% {L0:.2f}x → {ann0/12:.2f}%/mes")
    print(f"BASELINE 7 (OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes · "
          f"CPCV media {base_ref['fold_mean']:+.2f}\n")

    # ── 1. Ortogonalidad + ancla in-sample, varios holds ──
    print("── 1. Candidato SIZE (varios holds) · Sh/IS/OOS · corr · signo · Δ%/mes in-sample ──")
    print(f"  {'hold':>6s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} {'sgn':>4s} {'Δ%/mes':>7s}")
    best = None
    for days in (7, 14, 30, 60):
        h = days * 24
        # score = −log(mcap) → long small (premium SMB). Orientado en IS por seguridad.
        s_ret, _ = xs_sleeve(C, ret, beta, -logmcap, h)
        cut = int(s_ret.dropna().shape[0]*0.6); sgn = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        s_or = s_ret * sgn
        j = pd.concat({**{k: base[k] for k in base.columns}, "size": s_or}, axis=1)
        j.columns = list(base.columns) + ["size"]; j = j.dropna()
        corr = j.corr()["size"].drop("size"); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        ann, _ = anchored((j * vol_parity_weights(j)).sum(axis=1)); dmes = (ann - ann0)/12
        passes = (sh(seg(j["size"], .6, 1)) > 0.10 and cmax < 0.35)
        print(f"  {days:>4d}d  {sh(j['size']):6.2f} {sh(seg(j['size'],0,.6)):6.2f} {sh(seg(j['size'],.6,1)):6.2f} "
              f"{cmax:6.2f} {cwho:>12s} {sgn:+4.0f} {dmes:+7.2f}{'  <' if passes else ''}")
        if best is None or dmes > best[1]:
            best = (h, dmes, s_or, sgn)

    h, _, size_best, sgn = best
    print(f"\n  (signo {'+1 = LONG SMALL (premium SMB académico)' if sgn>0 else '−1 = LONG BIG (large-caps ganan, régimen reciente)'})")

    # ── 2. OOS honesto (walk-forward purgado + CPCV) ──
    print("\n── 2. OOS HONESTO: añadir SIZE al libro (walk-forward purgado + CPCV) ──")
    r8 = evaluate(base, size_best, "8 (+size)")
    fw = sum(a > b for a, b in zip(r8["folds"], base_ref["folds"]))
    print(f"  7 base : Sharpe OOS {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes")
    print(f"  8 +size: Sharpe OOS {r8['oos_sharpe']:.2f} · {r8['oos_mes']:.2f}%/mes · "
          f"ΔSharpe {r8['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · CPCV {fw}/{len(base_ref['folds'])}")

    # ── 3. CONDICIONAL (doctrina): ¿régimen potencia el size? pre-registrado ──
    print("\n── 3. CONDICIONAL: size × régimen (pre-registrado: premium en bull/breadth/risk-on) ──")
    R = get_regimes()
    hyps = [("mkt_bull", True, "SMB paga en risk-on/bull"),
            ("breadth_high", True, "premium con mercado amplio"),
            ("mkt_vol_high", False, "SMB sufre en estrés/flight-to-quality (favorable=baja vol)")]
    rows = []
    for rname, fav, rat in hyps:
        if rname not in R.columns: continue
        rr = run_combo(base, base_ref, size_best, R[rname], fav, f"size×{rname}")
        rows.append(rr)
        print(f"  size × {rname:13s}[{'T' if fav else 'F'}] ΔSharpe {rr['d_sharpe']:+.2f} · "
              f"folds {rr['fold_wins']}/{rr['fold_n']} · activo {rr['pct_on']*100:.0f}%  ({rat})")
    bar = deflation_bar([r8["oos_sharpe"]-base_ref["oos_sharpe"]] + [x["d_sharpe"] for x in rows], len(rows)+1)
    print(f"  barra deflactada ({len(rows)+1} pruebas): {bar:+.2f} ΔSharpe")

    # ── VEREDICTO ──
    print("\nVEREDICTO:")
    d_raw = r8["oos_sharpe"] - base_ref["oos_sharpe"]
    best_cond = max(rows, key=lambda x: x["d_sharpe"]) if rows else None
    raw_ok = d_raw > 0 and fw >= max(5, len(base_ref['folds'])-1)
    cond_ok = best_cond and best_cond["d_sharpe"] > bar and best_cond["fold_wins"] >= max(5, best_cond["fold_n"]-1)
    if raw_ok:
        print(f"  ✅ SIZE raw aporta OOS robusto (ΔSharpe {d_raw:+.2f}, {fw}/{len(base_ref['folds'])} folds). Candidato a sleeve #8.")
    elif cond_ok:
        print(f"  🟡 SIZE solo CONDICIONAL aporta robusto ({best_cond['name']} {best_cond['d_sharpe']:+.2f}). Satélite candidato.")
    else:
        print(f"  ⚠️ SIZE no aporta robusto OOS (raw ΔSharpe {d_raw:+.2f}, {fw}/{len(base_ref['folds'])}; "
              f"mejor cond {best_cond['d_sharpe']:+.2f} si lo hay).")
        print(f"     Probable causa: universo de 32 perps LÍQUIDOS comprime la dispersión de tamaño (el premium")
        print(f"     vive en microcaps que no operamos) y/o solapa con lowvol. APRENDIZAJE: archivar size aquí.")


if __name__ == "__main__":
    main()
