"""
E27 — A3 build serio: sleeve on-chain TVL (DefiLlama, GRATIS). Cierre de A3.
(2026-05-31). e26 (chequeo barato) encontró `tvl_pxdiv_14d` (acumulación = TVL sube más que el precio):
corr 0.10, OOS 1.27, Δ+1.03%/mes, leave-one-out robusto. Aquí el build serio antes de cualquier veredicto:
  1) AMPLIAR cobertura: + protocol-TVL (AAVE, UNI) a los 10 chain-TVL → ~12 nombres.
  2) RANGO de horizontes (7/10/14/21/30d) + COSTE (maker/taker) + turnover.
  3) POINT-IN-TIME (el riesgo clave): el TVL histórico de DefiLlama es RECONSTRUIDO; al añadir protocolos
     el TVL pasado se revisa al alza → saltos artificiales. Mitigación: CLIP del Δlog(TVL) diario (flujo
     real es suave; un alta de protocolo es un salto discreto). Comparar raw vs clipped + edge 2022 vs 2023+.
  4) COMBINADO 7→8 al ancla −10% (maker/taker) + cuartiles + leave-one-out con la cobertura ampliada.

python -m research.e27_onchain_tvl_build
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
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e24_orderbook_sleeve import sleeve_with_turnover
from research.e26_onchain_tvl_check import fetch_tvl, CHAINS

CACHE = os.path.join(config.DATA_DIR, "defillama")
PROTOCOLS = {"AAVEUSDT": "aave", "UNIUSDT": "uniswap"}   # tokens del universo que son protocolos DeFi


def fetch_protocol_tvl(slug):
    out = os.path.join(CACHE, f"protocol_{slug}.parquet")
    if os.path.exists(out):
        return pd.read_parquet(out)["tvl"]
    r = requests.get(f"https://api.llama.fi/protocol/{slug}", timeout=30)
    tvl = r.json().get("tvl", [])
    if not tvl:
        return None
    s = pd.Series([x["totalLiquidityUSD"] for x in tvl],
                  index=pd.to_datetime([x["date"] for x in tvl], unit="s", utc=True), name="tvl")
    s = s[~s.index.duplicated()].sort_index()
    s.to_frame().to_parquet(out)
    return s


def daily_logtvl(C):
    """log-TVL diario por token (chain + protocol). Devuelve DataFrame diario (índice fecha UTC)."""
    cols = {}
    for tok, ch in CHAINS.items():
        if tok not in C.columns: continue
        s = fetch_tvl(ch)
        if s is not None and s.replace(0, np.nan).dropna().shape[0] >= 300:
            cols[tok] = np.log(s.replace(0, np.nan))
    for tok, slug in PROTOCOLS.items():
        if tok not in C.columns: continue
        s = fetch_protocol_tvl(slug)
        if s is not None and s.replace(0, np.nan).dropna().shape[0] >= 300:
            cols[tok] = np.log(s.replace(0, np.nan))
    df = pd.DataFrame(cols)
    df.index = df.index.normalize()
    return df[~df.index.duplicated()].sort_index()


def to_hourly(daily_df, C, clip=None):
    """Alinea un panel DIARIO al índice horario de C (shift 1d anti-look-ahead). Si clip: winsoriza
    el Δlog diario a ±clip ANTES de reconstruir (mata saltos artificiales de altas de protocolo)."""
    d = daily_df
    if clip is not None:
        d = daily_df.diff().clip(-clip, clip).cumsum()
    d = d.shift(1)                                  # usar el día D-1 completo
    cidx_date = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx_date)), utc=True)
    aligned = d.reindex(uniq).reindex(cidx_date).set_axis(C.index)
    return aligned.reindex(columns=C.columns)


def sh(r):
    r = r.dropna()
    return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo*L)
    return m.get("ann", float("nan")), L, m.get("maxdd", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E27 — A3 build serio: sleeve on-chain TVL (DefiLlama). Cierre de A3.\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    retsum = lambda h: ret.reindex(columns=C.columns).rolling(h).sum()
    dl = daily_logtvl(C)
    toks = list(dl.columns)
    print(f"Cobertura TVL ampliada: {len(toks)} tokens → {toks}\n")

    # 7 sleeves base
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    P = load_panel(["volume", "taker_buy_volume"], C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    bdf = pd.concat(base, axis=1); bdf.columns = list(base); bdf = bdf.dropna()

    # overlap = donde hay TVL
    htvl = to_hourly(dl, C)
    cov = htvl.notna().any(axis=1); first, last = C.index[cov][0], C.index[cov][-1]
    over = bdf[(bdf.index >= first) & (bdf.index <= last)]
    ann0, L0, _ = anchored((over*vol_parity_weights(over)).sum(axis=1))
    print(f"BASELINE 7 (overlap {first.date()}→{last.date()}): @−10% {L0:.2f}x → {ann0/12:.2f}%/mes\n")

    def evalcand(score, hold, name):
        s_ret, turn = sleeve_with_turnover(C, ret, beta, score, hold)
        s_ret = s_ret[(s_ret.index >= first) & (s_ret.index <= last)]
        if s_ret.dropna().shape[0] < 100: return None
        cut = int(s_ret.dropna().shape[0]*0.6)
        sgn = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        j = pd.concat({**base, name: s_ret*sgn}, axis=1); j.columns = list(base)+[name]; j = j.dropna()
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        ann_mk, _, _ = anchored((j*vol_parity_weights(j)).sum(axis=1))
        jt = j.copy(); jt[name] = j[name] - (config.TAKER_FEE-config.MAKER_FEE)*turn/365
        ann_tk, _, _ = anchored((jt*vol_parity_weights(jt)).sum(axis=1))
        return dict(sh=sh(j[name]), is_=sh(seg(j[name],0,.6)), oos=sh(seg(j[name],.6,1)), cmax=cmax,
                    cwho=cwho, turn=turn, dmk=(ann_mk-ann0)/12, dtk=(ann_tk-ann0)/12, sr=j[name], sgn=sgn)

    # T1 — RANGO de horizontes × RAW vs CLIPPED (point-in-time)
    print("T1 — tvl_pxdiv por horizonte · RAW vs CLIPPED(±15%/día) (Sh/IS/OOS·corr·turn·Δmk·Δtk):")
    print(f"  {'variante':16s} {'Sh':>5s} {'IS':>5s} {'OOS':>5s} {'corr':>5s} {'turn':>5s} {'Δmk':>6s} {'Δtk':>6s}")
    panels = {"raw": to_hourly(dl, C), "clip": to_hourly(dl, C, clip=0.15)}
    keep = {}
    for tag, htv in panels.items():
        for days in (10, 14, 21, 30):   # 7d excluido: turnover alto + concentrado en 1 token (AAVE)
            h = days*24
            score = htv.diff(h) - retsum(h)
            r = evalcand(score, h, f"{tag}_{days}d")
            if r is None: continue
            print(f"  pxdiv_{tag}_{days:<2d}d   {r['sh']:5.2f} {r['is_']:5.2f} {r['oos']:5.2f} {r['cmax']:5.2f} "
                  f"{r['turn']:5.0f} {r['dmk']:+6.2f} {r['dtk']:+6.2f}")
            keep[f"{tag}_{days}d"] = r

    # elegir mejor por Δtk con OOS>0.1 y corr<0.35
    elig = {k: v for k, v in keep.items() if v['oos'] > 0.10 and v['cmax'] < 0.35}
    if not elig:
        print("\nVEREDICTO: ninguna variante mantiene OOS>0.10 con corr<0.35 a coste taker. A3 NO aporta.")
        return
    bk = max(elig, key=lambda k: elig[k]['dtk']); bv = elig[bk]
    print(f"\nMEJOR (Δtk, OOS>0.1, corr<0.35): pxdiv_{bk}  "
          f"(Δmaker {bv['dmk']:+.2f} · Δtaker {bv['dtk']:+.2f} · corr {bv['cmax']:.2f} con {bv['cwho']})")

    # T2 — POINT-IN-TIME: edge 2022 vs 2023+ (¿vive donde la cobertura DefiLlama ya era madura?)
    srb = bv['sr']
    pre = srb[srb.index < pd.Timestamp("2023-01-01", tz="UTC")]
    post = srb[srb.index >= pd.Timestamp("2023-01-01", tz="UTC")]
    print(f"\nT2 — POINT-IN-TIME (Sharpe del sleeve): 2022 {sh(pre):+.2f} · 2023+ {sh(post):+.2f}")
    print(f"  (clip ya aplicado si el mejor es 'clip'. Si 2023+ ≥ 2022 → edge vive en cobertura madura, "
          f"menos contaminado por backfill.)")

    # T3 — cuartiles + leave-one-out con cobertura ampliada
    print(f"\nT3 — cuartiles: " + "  ".join(f"Q{i+1} {sh(seg(srb,a,b)):+.2f}"
          for i,(a,b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)])))
    tag = bk.split("_")[0]; days = int(bk.split("_")[1].replace("d","")); h = days*24
    htv = panels[tag]
    print("  leave-one-out (Δtaker al quitar cada token):")
    loo = []
    for t in toks:
        sc = (htv[[x for x in toks if x != t]].diff(h) - retsum(h)).reindex(columns=C.columns)
        r = evalcand(sc, h, "x")
        if r: loo.append((t, r['dtk']))
    for t, d in sorted(loo, key=lambda x: x[1]):
        print(f"    sin {t:10s} Δtk {d:+.2f}  ({'CAE' if d < bv['dtk']-0.3 else 'ok'})")

    # T4 — combinado 8 sleeves
    j = pd.concat({**base, f"onchain_tvl_{bk}": srb*1.0}, axis=1)
    j.columns = list(base)+[f"onchain_tvl_{bk}"]; j = j.dropna()
    vp = vol_parity_weights(j); m = metrics((j*vp).sum(axis=1))
    print(f"\nT4 — COMBINADO 8 sleeves: Sharpe {m['sharpe']:.2f} · @−10% → maker {ann0/12+bv['dmk']:.2f}%/mes "
          f"(Δ{bv['dmk']:+.2f}) · taker {ann0/12+bv['dtk']:.2f} (Δ{bv['dtk']:+.2f})")
    print(f"  vp: {{'onchain': {vp[f'onchain_tvl_{bk}']:.2f}}} · peso del sleeve nuevo")
    print("\nVEREDICTO: implementable si Δtaker material + OOS + 2023+ sólido + LOO robusto + cuartiles ok.")
    print("Residual: point-in-time NO se elimina del todo sin snapshots; el clip mitiga, y la DEMO/vivo")
    print("es el test final. Cross-section delgado (~12) = límite estructural de A3 para este universo.")


if __name__ == "__main__":
    main()
