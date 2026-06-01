"""
E26 — A3 (paso 0): ¿el FLUJO DE TVL on-chain por cadena (DefiLlama, GRATIS) es ORTOGONAL y aporta?
(2026-05-31). Política gratis-primero: netflows de exchange por token = de pago (Glassnode/CryptoQuant)
→ anotados en "revisar información pagada". Lo GRATIS y per-símbolo que sí existe: **TVL por cadena**
(DefiLlama, API pública sin key, histórico largo). Tesis: capital entrando al DeFi de una L1 (TVL ↑)
podría predecir el retorno de su token cross-seccionalmente (fundamental on-chain, ortogonal al precio).

⚠️ LÍMITE: solo ~6-8 tokens del universo son cadenas con TVL significativo y largo (ETH, BNB, SOL, TRX,
AVAX, NEAR, ADA, HBAR; DOT/ETC ~$0, XLM corto). Cross-section DELGADO → gate de ortogonalidad, no prueba
final. Riesgo conocido (e16): TVL y precio se mueven juntos → puede salir correlado con momentum.

  tvl_mom_Nd   = Δlog(TVL) en N días              (inflow de capital → ¿bullish?)
  tvl_px_div   = Δlog(TVL) − retorno_precio        (TVL sube más que el precio = acumulación)
cross-seccional, β-neutral. corr<0.35 con los 7 + Δret@−10% → ¿vale bajar más on-chain?

python -m research.e26_onchain_tvl_check
"""
from __future__ import annotations
import os, sys, time
import datetime as dt
import numpy as np
import pandas as pd
import requests
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

CACHE = os.path.join(config.DATA_DIR, "defillama"); os.makedirs(CACHE, exist_ok=True)
CHAINS = {"ETHUSDT": "Ethereum", "BNBUSDT": "BSC", "SOLUSDT": "Solana", "AVAXUSDT": "Avalanche",
          "TRXUSDT": "Tron", "NEARUSDT": "Near", "DOTUSDT": "Polkadot", "ADAUSDT": "Cardano",
          "HBARUSDT": "Hedera", "INJUSDT": "Injective", "FILUSDT": "Filecoin", "XLMUSDT": "Stellar"}


def fetch_tvl(chain):
    out = os.path.join(CACHE, f"chain_{chain.replace(' ', '_')}.parquet")
    if os.path.exists(out):
        return pd.read_parquet(out)["tvl"]
    r = requests.get(f"https://api.llama.fi/v2/historicalChainTvl/{chain}", timeout=30)
    if r.status_code != 200:
        return None
    d = r.json()
    if not isinstance(d, list) or not d:
        return None
    s = pd.Series([x["tvl"] for x in d],
                  index=pd.to_datetime([x["date"] for x in d], unit="s", utc=True), name="tvl")
    s = s[~s.index.duplicated()].sort_index()
    s.to_frame().to_parquet(out)
    return s


def load_tvl_panel(C):
    """log-TVL diario por token (mapeado a su cadena), alineado al índice horario de C, rezagado 1 día."""
    cols = {}
    for tok, ch in CHAINS.items():
        if tok not in C.columns:
            continue
        s = fetch_tvl(ch)
        if s is None or s.replace(0, np.nan).dropna().shape[0] < 300:
            continue
        cols[tok] = np.log(s.replace(0, np.nan))
    wide = pd.DataFrame(cols)
    wide = wide.shift(1, freq="D")                      # anti-look-ahead (TVL de DefiLlama es EOD)
    cidx_date = pd.Index(C.index.tz_convert("UTC").normalize())
    uniq = pd.to_datetime(sorted(set(cidx_date)), utc=True)
    aligned = wide.reindex(uniq).reindex(cidx_date).set_axis(C.index)
    return aligned.reindex(columns=C.columns), list(cols)


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n * a):int(n * b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), L, m.get("maxdd", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E26 — A3 paso 0: ¿flujo de TVL por cadena (DefiLlama, GRATIS) es ortogonal y aporta?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    logtvl, toks = load_tvl_panel(C)
    print(f"Tokens con TVL usable: {len(toks)} → {toks}")
    cov = logtvl.notna().any(axis=1)
    first, last = C.index[cov][0], C.index[cov][-1]
    print(f"Overlap TVL: {first.date()} → {last.date()} ({cov.sum()} barras 1h)\n")

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
    over = bdf[(bdf.index >= first) & (bdf.index <= last)]
    combo0 = (over * vol_parity_weights(over)).sum(axis=1)
    ann0, L0, _ = anchored(combo0)
    print(f"BASELINE 7 sleeves (overlap): Sharpe {metrics(combo0)['sharpe']:.2f} · @−10% {L0:.2f}x → "
          f"{ann0/12:.2f}%/mes\n")

    retd_h = ret.reindex(columns=C.columns)
    cands = {}
    for days in (7, 14, 30):
        h = days * 24
        cands[f"tvl_mom_{days}d"] = (logtvl.diff(h), h)
        cands[f"tvl_pxdiv_{days}d"] = (logtvl.diff(h) - retd_h.rolling(h).sum(), h)

    print("CANDIDATOS (Sh/IS/OOS overlap · corr máx vs 7 · con quién · Δ%/mes anclado):")
    print(f"  {'cand':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} {'Δ%/mes':>7s}")
    best = []
    for name, (score, hold) in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
        except Exception as e:
            print(f"  {name:16s} ERROR {str(e)[:35]}"); continue
        s_ret = s_ret[(s_ret.index >= first) & (s_ret.index <= last)]
        if s_ret.dropna().shape[0] < 100:
            print(f"  {name:16s} insuf ({s_ret.dropna().shape[0]})"); continue
        # orientar signo en IS
        cut = int(s_ret.dropna().shape[0] * 0.6)
        sign = 1.0 if s_ret.dropna().iloc[:cut].mean() >= 0 else -1.0
        s_or = s_ret * sign
        j = pd.concat({**base, name: s_or}, axis=1); j.columns = list(base) + [name]; j = j.dropna()
        if len(j) < 100: print(f"  {name:16s} overlap corto"); continue
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        combo = (j * vol_parity_weights(j)).sum(axis=1); ann, _, _ = anchored(combo)
        dmes = (ann - ann0) / 12
        passes = (sh(seg(j[name], .6, 1)) > 0.10 and cmax < 0.35)
        print(f"  {name:16s} {sh(j[name]):6.2f} {sh(seg(j[name],0,.6)):6.2f} {sh(seg(j[name],.6,1)):6.2f} "
              f"{cmax:6.2f} {cwho:>12s} {dmes:+7.2f}{'  <' if passes else ''}")
        if passes and dmes > 0.10:
            best.append((name, dmes, cmax))

    # --- ESTRÉS del mejor candidato (lección e17: ¿lo mueve 1 token? ¿está repartido en el tiempo?) ---
    if best:
        bname = max(best, key=lambda b: b[1])[0]
        days = int(bname.split("_")[-1].replace("d", "")); h = days * 24
        is_div = "pxdiv" in bname
        def build_score(cols):
            lt = logtvl[cols]
            sc = lt.diff(h) - (retd_h[cols].rolling(h).sum() if is_div else 0)
            return sc.reindex(columns=C.columns)
        def dmes_of(score):
            sr, _ = xs_sleeve(C, ret, beta, score, h)
            sr = sr[(sr.index >= first) & (sr.index <= last)]
            cut = int(sr.dropna().shape[0]*0.6); sgn = 1.0 if sr.dropna().iloc[:cut].mean() >= 0 else -1.0
            j = pd.concat({**base, "x": sr*sgn}, axis=1); j.columns = list(base)+["x"]; j = j.dropna()
            ann, _, _ = anchored((j*vol_parity_weights(j)).sum(axis=1)); return (ann-ann0)/12, j["x"]
        d_full, sr_full = dmes_of(build_score(toks))
        print(f"\nESTRÉS de {bname} (Δ full {d_full:+.2f}%/mes):")
        print("  Cuartiles temporales (Sharpe):  " +
              "  ".join(f"Q{i+1} {sh(seg(sr_full,a,b)):+.2f}"
                        for i,(a,b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)])))
        print("  LEAVE-ONE-OUT (Δ%/mes al quitar cada token; si colapsa = concentrado/frágil):")
        loo = []
        for t in toks:
            d_t, _ = dmes_of(build_score([x for x in toks if x != t]))
            loo.append((t, d_t))
        for t, d_t in sorted(loo, key=lambda x: x[1]):
            print(f"    sin {t:10s} Δ {d_t:+.2f}%/mes  ({'CAE' if d_t < d_full-0.3 else 'ok'})")

    print("\nVEREDICTO (chequeo barato, cross-section delgado ~8 nombres):")
    if not best:
        print("  Ningún candidato de TVL es ortogonal (corr<0.35) Y sube el retorno anclado (>+0.1%/mes).")
        print("  La veta GRATIS de on-chain (TVL por cadena) NO aporta sobre los 7 sleeves.")
        print("  → Anotar netflows per-token (de PAGO: Glassnode/CryptoQuant/Santiment) en 'revisar")
        print("    información pagada' por si la veta on-chain merece el costo más adelante.")
    else:
        print(f"  PROMETEDOR: {[b[0] for b in best]} → ampliar cobertura (protocol-TVL de AAVE/UNI/ONDO/ENA)")
        print("  + estrés (e16e/e24) + Δret@−10% con costos taker antes de cualquier cosa.")


if __name__ == "__main__":
    main()
