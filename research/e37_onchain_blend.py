"""
E37 — FACTOR ON-CHAIN COMBINADO (doctrina Medallion: muchas señales pequeñas uncorr → blend robusto).
(2026-06-01). Individualmente marginales: TVL-pxdiv (+0.30 OOS, 4/6), stablecoin-pxdiv (+0.22, 3/6).
Tesis: su BLEND con una 3ª señal hermana (fees-pxdiv) puede cruzar el umbral de robustez (≥5/6 folds)
que ninguna logra sola. Todo on-chain, gratis sin key (DefiLlama), point-in-time vía sombra.

3 componentes (todos "X on-chain crece vs precio" = acumulación), cada uno cross-seccional β-neutral:
  tvl_pxdiv_14d   = Δlog(TVL cadena) − ret        (e26/e27)
  stbl_pxdiv_14d  = Δlog(stablecoin supply) − ret  (e36)
  fees_pxdiv_14d  = Δlog(fees cadena) − ret         (NUEVO, e37)

Se prueban dos formas de combinar (doctrina): (A) BLEND DE RETORNOS (vol-parity de 3 mini-sleeves),
(B) COMPOSITE DE SEÑAL (z-score y promediar scores → 1 sleeve). Cada uno: OOS purgado + CPCV.

python -m research.e37_onchain_blend
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, xs_sleeve
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.regime_lab import build_base_sleeves, get_regimes, evaluate, run_combo, deflation_bar
from research.e26_onchain_tvl_check import load_tvl_panel
from research.e36_stablecoin_supply import load_stbl_panel, CHAINS

CACHE = os.path.join(config.DATA_DIR, "defillama_fees"); os.makedirs(CACHE, exist_ok=True)
H = 14 * 24


def fetch_fees(chain):
    out = os.path.join(CACHE, f"{chain}.parquet")
    if os.path.exists(out):
        return pd.read_parquet(out)["fees"]
    try:
        r = requests.get(f"https://api.llama.fi/overview/fees/{chain}?dataType=dailyFees",
                         timeout=40, headers={"User-Agent": "kepler"})
        if r.status_code != 200:
            return None
        chart = r.json().get("totalDataChart", [])
        if not chart:
            return None
        s = pd.Series([x[1] for x in chart],
                      index=pd.to_datetime([x[0] for x in chart], unit="s", utc=True), name="fees")
        s = s[~s.index.duplicated()].sort_index()
        s.to_frame().to_parquet(out)
        return s
    except Exception:
        return None


def load_fees_panel(C):
    cols = {}
    for tok, ch in CHAINS.items():
        if tok not in C.columns:
            continue
        s = fetch_fees(ch)
        if s is None or s.replace(0, np.nan).dropna().shape[0] < 300:
            continue
        cols[tok] = np.log(s.replace(0, np.nan))
    wide = pd.DataFrame(cols)
    if wide.empty:
        return wide, []
    wide.index = wide.index.normalize()
    wide = wide[~wide.index.duplicated()].sort_index().shift(1)   # anti-look-ahead (EOD)
    cidx = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx)), utc=True)
    return wide.reindex(uniq).reindex(cidx).set_axis(C.index).reindex(columns=C.columns), list(cols)


def oriented_sleeve(C, ret, beta, score):
    s, _ = xs_sleeve(C, ret, beta, score, H)
    cut = int(s.dropna().shape[0]*0.6); sgn = 1.0 if s.dropna().iloc[:cut].mean() >= 0 else -1.0
    return s * sgn, sgn


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E37 — FACTOR ON-CHAIN COMBINADO (TVL + stablecoins + fees) · doctrina Medallion\n" + "="*68)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); retd = ret.reindex(columns=C.columns)

    logtvl, t1 = load_tvl_panel(C)
    logstbl, t2 = load_stbl_panel(C)
    logfees, t3 = load_fees_panel(C)
    print(f"Cobertura: TVL {len(t1)} · stablecoins {len(t2)} · fees {len(t3)} cadenas")

    comp_scores = {
        "tvl_pxdiv":  logtvl.diff(H)  - retd.rolling(H).sum(),
        "stbl_pxdiv": logstbl.diff(H) - retd.rolling(H).sum(),
        "fees_pxdiv": logfees.diff(H) - retd.rolling(H).sum(),
    }

    base = build_base_sleeves(); base_ref = evaluate(base, None, "7 base")
    nf = len(base_ref["folds"])
    print(f"\nBASELINE 7 (OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes · "
          f"CPCV {base_ref['fold_mean']:+.2f} ({nf} folds)\n")

    # ── componentes solos (contexto) ──
    print("── Componentes SOLOS (OOS purgado, añadido al libro) ──")
    sleeves = {}; signs = {}
    for name, score in comp_scores.items():
        sret, sgn = oriented_sleeve(C, ret, beta, score)
        sleeves[name] = sret; signs[name] = sgn
        r = evaluate(base, sret, name)
        fw = sum(a > b for a, b in zip(r["folds"], base_ref["folds"]))
        print(f"  {name:12s} (sgn {sgn:+.0f}) ΔSharpe {r['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · CPCV {fw}/{nf}")

    SL = pd.concat(sleeves, axis=1); SL.columns = list(sleeves); SL = SL.dropna()

    # ── (A) BLEND DE RETORNOS: vol-parity de los 3 mini-sleeves → 1 sleeve on-chain ──
    print("\n── (A) BLEND DE RETORNOS (vol-parity de los 3 mini-sleeves) ──")
    blend_ret = (SL * vol_parity_weights(SL)).sum(axis=1)
    rA = evaluate(base, blend_ret, "onchain_blend_ret")
    fwA = sum(a > b for a, b in zip(rA["folds"], base_ref["folds"]))
    print(f"  onchain_blend(ret): ΔSharpe {rA['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
          f"{rA['oos_mes']-base_ref['oos_mes']:+.2f}%/mes · CPCV {fwA}/{nf}")

    # ── (B) COMPOSITE DE SEÑAL: z-score cross-seccional, orientar, promediar → 1 score → 1 sleeve ──
    print("\n── (B) COMPOSITE DE SEÑAL (z-score xs, orientar, promediar) ──")
    def zrow(df):
        return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)
    zsum = None; cnt = None
    for name, score in comp_scores.items():
        z = zrow(score) * signs[name]                 # orientar con el signo del componente
        zsum = z if zsum is None else zsum.add(z, fill_value=0)
        c = z.notna().astype(float); cnt = c if cnt is None else cnt.add(c, fill_value=0)
    composite = (zsum / cnt.replace(0, np.nan)).reindex(columns=C.columns)
    blend_sig, _ = xs_sleeve(C, ret, beta, composite, H)
    rB = evaluate(base, blend_sig, "onchain_composite")
    fwB = sum(a > b for a, b in zip(rB["folds"], base_ref["folds"]))
    print(f"  onchain_composite(sig): ΔSharpe {rB['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
          f"{rB['oos_mes']-base_ref['oos_mes']:+.2f}%/mes · CPCV {fwB}/{nf}")

    # ── mejor blend → lente condicional ──
    best_ret, best_tag, best_fw = (blend_ret, "blend_ret", fwA) if rA["oos_sharpe"] >= rB["oos_sharpe"] else (blend_sig, "composite", fwB)
    best_r = rA if best_tag == "blend_ret" else rB
    print(f"\n── CONDICIONAL del mejor blend ({best_tag}) ──")
    R = get_regimes(); rows = []
    for rname, fav in [("mkt_bull", True), ("mkt_vol_high", False)]:
        if rname not in R.columns: continue
        rr = run_combo(base, base_ref, best_ret, R[rname], fav, f"blend×{rname}")
        rows.append(rr)
        print(f"  × {rname:13s}[{'T' if fav else 'F'}] ΔSharpe {rr['d_sharpe']:+.2f} · folds {rr['fold_wins']}/{rr['fold_n']}")

    print("\nVEREDICTO (doctrina: ¿el blend cruza el umbral que ninguna sola logra?):")
    dA = rA["oos_sharpe"]-base_ref["oos_sharpe"]; dB = rB["oos_sharpe"]-base_ref["oos_sharpe"]
    bestd = max(dA, dB); bestfw = max(fwA, fwB)
    if bestd > 0 and bestfw >= max(5, nf-1):
        print(f"  ✅ EL BLEND ES ROBUSTO (Δ {bestd:+.2f}, {bestfw}/{nf} folds) donde las señales solas NO (3-4/6).")
        print(f"     → Candidato a sleeve #8 ON-CHAIN COMBINADO (gratis). Estrés + coste taker + sombra.")
    elif bestd > 0 and bestfw >= 4:
        print(f"  🟡 El blend mejora la robustez (Δ {bestd:+.2f}, {bestfw}/{nf}) pero no llega a 5/6.")
        print(f"     Añadir más componentes uncorr (DEX volume, o descartados re-evaluados) podría cruzarlo.")
    else:
        print(f"  ⚠️ El blend no cruza el umbral (mejor Δ {bestd:+.2f}, {bestfw}/{nf}). Documentar y seguir")
        print(f"     con más componentes / re-evaluar descartados como piezas del blend.")


if __name__ == "__main__":
    main()
