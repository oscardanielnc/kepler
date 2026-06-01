"""
E36 — Señal on-chain GRATIS sin key: STABLECOIN SUPPLY por cadena (DefiLlama). 2026-06-01.
El proxy gratis del NETFLOW que Oscar quería: stablecoins entrando a una cadena = pólvora seca /
poder de compra → análogo on-chain del "USDT entra al exchange". Cross-seccional por cadena, mismo
molde que el TVL (e26, que validó +0.6%/mes). Fuente: stablecoins.llama.fi/stablecoincharts/{chain}
(histórico diario, sin key). ¿Es ORTOGONAL (incl. vs el propio TVL) y aporta al ancla? + lente condicional.

  stbl_mom_Nd   = Δlog(stablecoin supply de la cadena)         (capital/pólvora entrando → ¿bullish?)
  stbl_pxdiv_Nd = Δlog(stbl supply) − retorno_precio           (pólvora crece más que el precio = acumulación)

python -m research.e36_stablecoin_supply
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.regime_lab import build_base_sleeves, get_regimes, evaluate, run_combo, deflation_bar

CACHE = os.path.join(config.DATA_DIR, "defillama_stbl"); os.makedirs(CACHE, exist_ok=True)
# token del universo → nombre de cadena en DefiLlama (mismo set que el TVL e26)
CHAINS = {"ETHUSDT": "Ethereum", "BNBUSDT": "BSC", "SOLUSDT": "Solana", "AVAXUSDT": "Avalanche",
          "TRXUSDT": "Tron", "NEARUSDT": "Near", "ADAUSDT": "Cardano", "HBARUSDT": "Hedera",
          "FILUSDT": "Filecoin", "XLMUSDT": "Stellar"}


def fetch_stbl(chain):
    out = os.path.join(CACHE, f"{chain}.parquet")
    if os.path.exists(out):
        return pd.read_parquet(out)["stbl"]
    try:
        r = requests.get(f"https://stablecoins.llama.fi/stablecoincharts/{chain}", timeout=40,
                         headers={"User-Agent": "kepler"})
        if r.status_code != 200:
            return None
        d = r.json()
        if not isinstance(d, list) or not d:
            return None
        vals, idx = [], []
        for x in d:
            tc = x.get("totalCirculatingUSD") or {}
            v = tc.get("peggedUSD") if isinstance(tc, dict) else None
            if v is None:
                continue
            vals.append(float(v)); idx.append(pd.to_datetime(int(x["date"]), unit="s", utc=True))
        if not vals:
            return None
        s = pd.Series(vals, index=idx, name="stbl")
        s = s[~s.index.duplicated()].sort_index()
        s.to_frame().to_parquet(out)
        return s
    except Exception:
        return None


def load_stbl_panel(C):
    cols = {}
    for tok, ch in CHAINS.items():
        if tok not in C.columns:
            continue
        s = fetch_stbl(ch)
        if s is None or s.replace(0, np.nan).dropna().shape[0] < 300:
            continue
        cols[tok] = np.log(s.replace(0, np.nan))
    wide = pd.DataFrame(cols)
    if wide.empty:
        return wide, []
    wide.index = wide.index.normalize()
    wide = wide[~wide.index.duplicated()].sort_index().shift(1)     # anti-look-ahead (EOD)
    cidx_date = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx_date)), utc=True)
    aligned = wide.reindex(uniq).reindex(cidx_date).set_axis(C.index)
    return aligned.reindex(columns=C.columns), list(cols)


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD); return metrics(combo*L)["ann"], L


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E36 — STABLECOIN SUPPLY por cadena (DefiLlama, gratis sin key) — proxy del netflow\n" + "="*68)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    logstbl, toks = load_stbl_panel(C)
    print(f"Cadenas con stablecoin supply usable: {len(toks)} → {toks}\n")
    if len(toks) < 4:
        print("Cobertura insuficiente. Abortando."); return

    base = build_base_sleeves(); base_ref = evaluate(base, None, "7 base")
    combo0 = (base * vol_parity_weights(base)).sum(axis=1); ann0, L0 = anchored(combo0)
    print(f"BASELINE 7 (in-sample): Sharpe {metrics(combo0)['sharpe']:.2f} · @−10% {L0:.2f}x → {ann0/12:.2f}%/mes")
    print(f"BASELINE 7 (OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · {base_ref['oos_mes']:.2f}%/mes\n")

    retd_h = ret.reindex(columns=C.columns)
    cands = {}
    for days in (7, 14, 30):
        h = days * 24
        cands[f"stbl_mom_{days}d"] = (logstbl.diff(h), h)
        cands[f"stbl_pxdiv_{days}d"] = (logstbl.diff(h) - retd_h.rolling(h).sum(), h)

    print("── 1. Candidatos (Sh/IS/OOS · corr máx vs 7 · con quién · signo · Δ%/mes in-sample) ──")
    print(f"  {'cand':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} {'sgn':>4s} {'Δ%/mes':>7s}")
    best = None
    for name, (score, hold) in cands.items():
        s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
        if s_ret.dropna().shape[0] < 100:
            print(f"  {name:16s} insuf"); continue
        cut = int(s_ret.dropna().shape[0]*0.6); sgn = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        s_or = s_ret * sgn
        j = pd.concat({**{k: base[k] for k in base.columns}, name: s_or}, axis=1)
        j.columns = list(base.columns) + [name]; j = j.dropna()
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        ann, _ = anchored((j*vol_parity_weights(j)).sum(axis=1)); dmes = (ann-ann0)/12
        passes = (sh(seg(j[name], .6, 1)) > 0.10 and cmax < 0.35)
        print(f"  {name:16s} {sh(j[name]):6.2f} {sh(seg(j[name],0,.6)):6.2f} {sh(seg(j[name],.6,1)):6.2f} "
              f"{cmax:6.2f} {cwho:>12s} {sgn:+4.0f} {dmes:+7.2f}{'  <' if passes else ''}")
        if passes and (best is None or dmes > best[1]):
            best = (name, dmes, s_or)

    if best is None:
        print("\nVEREDICTO: ningún candidato de stablecoin-supply es ortogonal (corr<0.35) Y aporta in-sample.")
        print("  → archivar; pasar a fees/revenue por cadena (e37) o DEX volume.")
        return

    bname, _, s_best = best
    print(f"\n  Mejor candidato in-sample: {bname}")

    # ── 2. OOS honesto + 3. lente condicional ──
    print("\n── 2. OOS HONESTO (walk-forward purgado + CPCV) ──")
    r8 = evaluate(base, s_best, f"8 (+{bname})")
    fw = sum(a > b for a, b in zip(r8["folds"], base_ref["folds"]))
    print(f"  +{bname}: Sharpe OOS {r8['oos_sharpe']:.2f} · ΔSharpe {r8['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
          f"CPCV {fw}/{len(base_ref['folds'])}")

    print("\n── 3. CONDICIONAL: × régimen (pre-registrado: pólvora seca paga en risk-on/bull) ──")
    R = get_regimes()
    rows = []
    for rname, fav, rat in [("mkt_bull", True, "capital entra/rota en risk-on"),
                            ("mkt_vol_high", False, "se rompe en estrés (favorable=baja vol)")]:
        if rname not in R.columns: continue
        rr = run_combo(base, base_ref, s_best, R[rname], fav, f"{bname}×{rname}")
        rows.append(rr)
        print(f"  × {rname:13s}[{'T' if fav else 'F'}] ΔSharpe {rr['d_sharpe']:+.2f} · folds {rr['fold_wins']}/{rr['fold_n']}  ({rat})")
    bar = deflation_bar([r8["oos_sharpe"]-base_ref["oos_sharpe"]]+[x["d_sharpe"] for x in rows], len(rows)+1)

    print("\nVEREDICTO:")
    d_raw = r8["oos_sharpe"]-base_ref["oos_sharpe"]
    if d_raw > 0 and fw >= max(5, len(base_ref['folds'])-1):
        print(f"  ✅ {bname} aporta OOS robusto (ΔSharpe {d_raw:+.2f}, {fw}/{len(base_ref['folds'])}). Candidato → estrés + coste taker + sombra.")
    elif rows and max(r['d_sharpe'] for r in rows) > bar:
        print(f"  🟡 solo condicional aporta. Satélite candidato (validar forward).")
    else:
        print(f"  ⚠️ no aporta OOS robusto (raw ΔSharpe {d_raw:+.2f}, {fw}/{len(base_ref['folds'])}). Archivar; siguiente: fees/DEX volume.")


if __name__ == "__main__":
    main()
