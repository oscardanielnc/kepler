"""
E61 — ¿`tx_pxdiv_14d` es ORTOGONAL al blend #8 (lotería+TVL+iliquidez), o solapa con el TVL?
(2026-06-02). Cierra el lazo del on-chain: tx_pxdiv pasó el harness vs los 7 sleeves (e59/e60), pero el
TVL también es on-chain "actividad vs precio" → hay que ver si tx_pxdiv aporta info NUEVA al blend o es
redundante con el TVL que ya sombreamos. Construye los 3 componentes EXACTOS del blend (onchain.py) +
tx_pxdiv, saca la matriz de correlación, y prueba el blend 4-componentes vs 3. No toca producción.
python -m research.e61_onchain_vs_blend
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, xs_sleeve, load_panel, DRIVER
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from kepler.onchain import _daily_logtvl, _to_hourly, LOOKBACK_DAYS, BLEND_SIGNS
from research.e59_onchain_factor import load_onchain, to_hourly_score


def half(s):
    h = len(s) // 2
    return metrics(s.iloc[:h]).get("sharpe", float("nan")), metrics(s.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E61 — tx_pxdiv_14d vs blend #8 (¿ortogonal o solapa con el TVL?)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); cols = list(C.columns)
    Pd = C.resample("1D").last()
    h = LOOKBACK_DAYS * 24

    # ── 3 componentes EXACTOS del blend (onchain._blend_target_weights) ─────────
    dl = _daily_logtvl(cols)
    if dl.empty:
        print("⚠️ TVL no disponible (cache/DefiLlama) — no puedo comparar vs TVL."); return
    logtvl = _to_hourly(dl, C)
    tvl_score = (logtvl.diff(h) - ret.reindex(columns=cols).rolling(h).sum()) * BLEND_SIGNS["tvl"]
    s_tvl, _ = xs_sleeve(C, ret, beta, tvl_score, h)
    dvol = load_panel(["quote_volume"], C)["quote_volume"]
    ilq_score = np.log((ret.abs() / dvol.replace(0, np.nan)).rolling(h).mean().replace(0, np.nan)) * BLEND_SIGNS["illiq"]
    s_ilq, _ = xs_sleeve(C, ret, beta, ilq_score, h)
    rd = Pd.pct_change(); rd.index = rd.index.normalize()
    lot_score = _to_hourly(rd.rolling(60).max(), C) * BLEND_SIGNS["lottery"]
    s_lot, _ = xs_sleeve(C, ret, beta, lot_score, 60 * 24)

    # ── tx_pxdiv_14d (e59) ─────────────────────────────────────────────────────
    ADR, TX = load_onchain(Pd.index, cols)
    logtx = np.log(TX.replace(0, np.nan)); logp = np.log(Pd[TX.columns])
    s_tx, _ = xs_sleeve(C, ret, beta, to_hourly_score(logtx.diff(14) - logp.diff(14), C), 14 * 24)

    # blend 3-comp (como el shadow actual)
    df3 = pd.concat({"lottery": s_lot, "tvl": s_tvl, "illiq": s_ilq}, axis=1).dropna()
    blend3 = (df3 * vol_parity_weights(df3)).sum(axis=1)

    # ── MATRIZ DE CORRELACIÓN ──────────────────────────────────────────────────
    alls = pd.concat({"lottery": s_lot, "tvl": s_tvl, "illiq": s_ilq, "blend3": blend3, "tx_pxdiv": s_tx},
                     axis=1).dropna()
    print("Matriz de correlación (series de retorno de los mini-sleeves):")
    print(alls.corr().round(3).to_string())
    cm = alls.corr()
    print(f"\n  corr(tx_pxdiv, TVL)   = {cm.loc['tx_pxdiv','tvl']:+.3f}   ← la clave (ambos on-chain)")
    print(f"  corr(tx_pxdiv, blend) = {cm.loc['tx_pxdiv','blend3']:+.3f}")
    print(f"  corr(tx_pxdiv, lotería/iliq) = {cm.loc['tx_pxdiv','lottery']:+.3f} / {cm.loc['tx_pxdiv','illiq']:+.3f}")

    # ── blend 4-comp (añadir tx_pxdiv) vs 3-comp ───────────────────────────────
    df4 = pd.concat({"lottery": s_lot, "tvl": s_tvl, "illiq": s_ilq, "tx_pxdiv": s_tx}, axis=1).dropna()
    blend4 = (df4 * vol_parity_weights(df4)).sum(axis=1)
    m3, m4 = metrics(blend3), metrics(blend4)
    i3, o3 = half(blend3); i4, o4 = half(blend4)
    print(f"\nBLEND 3-comp (actual): Sharpe {m3['sharpe']:.2f} (IS {i3:.2f}/OOS {o3:.2f}) · maxDD {m3['maxdd']:.1f}%")
    print(f"BLEND 4-comp (+tx):    Sharpe {m4['sharpe']:.2f} (IS {i4:.2f}/OOS {o4:.2f}) · maxDD {m4['maxdd']:.1f}%")

    # también: ¿tx_pxdiv REEMPLAZANDO al TVL? (si solapan, quedarse con el mejor)
    dfR = pd.concat({"lottery": s_lot, "tx_pxdiv": s_tx, "illiq": s_ilq}, axis=1).dropna()
    blendR = (dfR * vol_parity_weights(dfR)).sum(axis=1); mR = metrics(blendR); iR, oR = half(blendR)
    print(f"BLEND tx-EN-LUGAR-de-TVL: Sharpe {mR['sharpe']:.2f} (IS {iR:.2f}/OOS {oR:.2f}) · maxDD {mR['maxdd']:.1f}%")

    print("\nVEREDICTO:")
    c_tvl = cm.loc['tx_pxdiv', 'tvl']
    if abs(c_tvl) < 0.35 and m4['sharpe'] > m3['sharpe'] + 0.05:
        print(f"  ✅ tx_pxdiv es ORTOGONAL al TVL (corr {c_tvl:+.2f}) y SUMA al blend ({m3['sharpe']:.2f}→{m4['sharpe']:.2f})")
        print("     → componente NUEVO del blend #8. Siguiente: re-validar 4-comp (CPCV) + a SOMBRA.")
    elif abs(c_tvl) >= 0.35:
        print(f"  ⚠️ tx_pxdiv SOLAPA con el TVL (corr {c_tvl:+.2f}) → no es independiente. Quedarse con el más")
        print(f"     fuerte: blend con tx-en-lugar-de-TVL da Sharpe {mR['sharpe']:.2f} vs 3-comp {m3['sharpe']:.2f}.")
    else:
        print(f"  ~ ortogonal (corr {c_tvl:+.2f}) pero no mejora claramente el blend 4-comp. Marginal.")


if __name__ == "__main__":
    main()
