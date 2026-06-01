"""
E40 — BLEND con el nuevo componente uncorr LOTERÍA (max_60d). 2026-06-01.
e38: blend cross-family +0.34/4-6, limitado a que SOLO order-book era uncorr (TVL/OI/illiq cluster
~0.5) y arrastraba el punto ciego 2022 (order-book/OI son 2023+). e39 halló max_60d (lotería):
2º componente genuinamente uncorr (0.11) Y FULL-HISTORY 2022+. Tesis: un blend con DOS anclas uncorr
(lotería + order-book) puede cruzar 5/6; y un blend FULL-HISTORY {lotería + TVL + illiq} evita el
punto ciego 2022 (todos existen desde 2022).

  (A) FULL-HISTORY blend {lottery + tvl + illiq}  → evaluado 2022+ (sin blindspot) ← el premio
  (B) 2023+ blend {lottery + order-book + oi + tvl + illiq} (2 uncorr) → overlap

python -m research.e40_blend_with_lottery
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, xs_sleeve, load_panel
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.regime_lab import build_base_sleeves, evaluate
from research.e38_crossfamily_blend import oriented, evaluate_on
from research.e39_skew_lottery import daily_to_hourly
from research.e26_onchain_tvl_check import load_tvl_panel
from research.e24_orderbook_sleeve import load_ob_panels
from research.e16f_metrics_sleeves import load_metric_panel


def folds_wins(a, b):
    return sum(x > y for x, y in zip(a["folds"], b["folds"])), len(b["folds"])


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E40 — BLEND con LOTERÍA (max_60d, uncorr full-history)\n" + "="*64)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); retd = ret.reindex(columns=C.columns)
    dvol = load_panel(["quote_volume"], C)["quote_volume"]; absret = ret.abs(); H = 14*24
    rd = C.resample("1D").last().pct_change(); rd.index = rd.index.normalize()

    # componentes
    comp = {}
    comp["lottery"] = oriented(C, ret, beta, daily_to_hourly(rd.rolling(60).max(), C), 60*24)   # full-history
    logtvl, _ = load_tvl_panel(C)
    comp["tvl"]     = oriented(C, ret, beta, logtvl.diff(H) - retd.rolling(H).sum(), H)           # full-history
    comp["illiq"]   = oriented(C, ret, beta, np.log((absret/dvol.replace(0,np.nan)).rolling(H).mean().replace(0,np.nan)), H)  # full-history
    ob, _ = load_ob_panels(C)
    comp["ob"]      = oriented(C, ret, beta, -ob["imb1"], 5*24)                                   # 2023+
    lsr = load_metric_panel("count_long_short_ratio", C)
    comp["oi"]      = oriented(C, ret, beta, -((lsr - lsr.rolling(H).mean())/lsr.rolling(H).std()), H)  # 2023+

    base = build_base_sleeves(); nf = 6

    # ── (A) FULL-HISTORY blend {lottery, tvl, illiq} — sin punto ciego 2022 ──
    print("── (A) FULL-HISTORY blend {lottery + tvl + illiq} (evaluado 2022+, SIN punto ciego) ──")
    FH = pd.concat({k: comp[k] for k in ("lottery","tvl","illiq")}, axis=1)
    FH.columns = ["lottery","tvl","illiq"]; FH = FH.dropna()
    print("  corr entre componentes:")
    print("   " + FH.corr().round(2).to_string().replace("\n","\n   "))
    base_ref_full = evaluate(base, None, "7 base full")
    blend_fh = (FH * vol_parity_weights(FH)).sum(axis=1).rename("x")
    rFH = evaluate(base, blend_fh, "blendFH")
    fw, _ = folds_wins(rFH, base_ref_full)
    print(f"  baseline 7 (full OOS): Sharpe {base_ref_full['oos_sharpe']:.2f} · {base_ref_full['oos_mes']:.2f}%/mes · CPCV {base_ref_full['fold_mean']:+.2f}")
    print(f"  +blendFH: ΔSharpe {rFH['oos_sharpe']-base_ref_full['oos_sharpe']:+.2f} · "
          f"{rFH['oos_mes']-base_ref_full['oos_mes']:+.2f}%/mes · CPCV {fw}/{nf}")
    # lotería sola (referencia full-history)
    rlot = evaluate(base, comp["lottery"], "lottery"); fwl, _ = folds_wins(rlot, base_ref_full)
    print(f"  (lottery sola: ΔSharpe {rlot['oos_sharpe']-base_ref_full['oos_sharpe']:+.2f}, {fwl}/{nf})")

    # ── (B) 2023+ blend con las 5 (2 uncorr: lottery + ob) ──
    print("\n── (B) 2023+ blend {lottery + ob + oi + tvl + illiq} (2 anclas uncorr) ──")
    ob_start = C.index[ob["imb1"].notna().any(axis=1)][0].normalize()
    oi_start = C.index[lsr.notna().any(axis=1)][0].normalize()
    start = max(ob_start, oi_start)
    idx = base.index[base.index >= start]
    ALL = pd.concat(comp, axis=1); ALL.columns = list(comp); ALL = ALL.loc[ALL.index.isin(idx)].dropna()
    print("  corr entre los 5 componentes (overlap):")
    print("   " + ALL.corr().round(2).to_string().replace("\n","\n   "))
    base_ref_ov = evaluate_on(base, None, idx, "7 base ov")
    blend5 = (ALL * vol_parity_weights(ALL)).sum(axis=1).rename("x")
    r5 = evaluate_on(base, blend5, idx, "blend5")
    fw5, _ = folds_wins(r5, base_ref_ov)
    print(f"  baseline 7 (overlap OOS): Sharpe {base_ref_ov['oos_sharpe']:.2f} · CPCV {base_ref_ov['fold_mean']:+.2f}")
    print(f"  +blend5: ΔSharpe {r5['oos_sharpe']-base_ref_ov['oos_sharpe']:+.2f} · "
          f"{r5['oos_mes']-base_ref_ov['oos_mes']:+.2f}%/mes · CPCV {fw5}/{nf}")

    print("\nVEREDICTO:")
    dFH = rFH['oos_sharpe']-base_ref_full['oos_sharpe']; d5 = r5['oos_sharpe']-base_ref_ov['oos_sharpe']
    if dFH > 0 and fw >= max(5, nf-1):
        print(f"  ✅✅ BLEND FULL-HISTORY ROBUSTO (Δ {dFH:+.2f}, {fw}/{nf}) Y SIN punto ciego 2022.")
        print(f"      → sleeve #8 candidato REAL (full-history, gratis/datos propios+TVL). Estrés+taker+sombra.")
    elif d5 > 0 and fw5 >= max(5, nf-1):
        print(f"  ✅ Blend 2023+ robusto (Δ {d5:+.2f}, {fw5}/{nf}) pero arrastra el punto ciego 2022.")
    elif dFH > 0 and fw >= 5:
        print(f"  🟡 Full-history cerca (Δ {dFH:+.2f}, {fw}/{nf}). La lotería ayuda; falta poco.")
    else:
        print(f"  ⚠️ Aún no cruza (FH Δ {dFH:+.2f} {fw}/{nf} · 2023+ Δ {d5:+.2f} {fw5}/{nf}).")
        print(f"     La lotería es uncorr y full-history (mejor componente nuevo) pero el blend no es robusto aún.")


if __name__ == "__main__":
    main()
