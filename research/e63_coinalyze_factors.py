"""
E63 — Coinalyze Tier 2: factores de OPEN INTEREST (+ diagnóstico predicted-funding) por el harness brutal.
(2026-06-02). Datos e62 (data/coinalyze_daily/, 29 coins, diario cross-exchange). Oportunidad NUEVA real
= flujo de posicionamiento vía OI-delta (≠ el ratio L/S que descartamos en e16f):
  • oi_pxdiv_Nd = Δlog(OI,N) − retorno(N)     (posiciones crecen más/menos que el precio)
  • oi_mom_Nd   = Δlog(OI,N)                  (momentum de interés abierto)
  • oi_dir_Nd   = Δlog(OI,N) · signo(ret_N)   (direccional: longs construyen en subida / shorts en bajada)
Ambos signos. Predicted-funding: el harness mide PRECIO, no funding cobrado → para el carry haría falta
la maquinaria de funding; aquí solo DIAGNÓSTICO (¿corr con el funding realizado? ¿señal de precio?).
Harness: corr<0.35 con los 7 sleeves + IS/OOS + Δ al ancla + vivo 2022+. No toca prod.
python -m research.e63_coinalyze_factors
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

HC = config.LEVERAGE_HAIRCUT
SHIFT = 1
CACHE = os.path.join(config.DATA_DIR, "coinalyze_daily")


def load_cz(daily_idx, cols):
    pf, oi = {}, {}
    for coin in cols:
        p = os.path.join(CACHE, f"{coin}.parquet")
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index, utc=True).normalize()
        if "pred_funding" in d: pf[coin] = d["pred_funding"]
        if "oi" in d: oi[coin] = d["oi"]
    PF = pd.DataFrame(pf).reindex(daily_idx).astype(float)
    OI = pd.DataFrame(oi).reindex(daily_idx).astype(float)
    return PF, OI


def to_hourly(score_daily, C):
    return score_daily.shift(SHIFT).reindex(C.index, method="ffill").reindex(columns=C.columns)


def combine(series):
    df = pd.concat(series, axis=1).dropna(); vp = vol_parity_weights(df)
    port = (df * vp).sum(axis=1)
    lev = min(HC * leverage_for_maxdd_anchor(port, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    return metrics(port * lev)


def half(s):
    h = len(s)//2
    return metrics(s.iloc[:h]).get("sharpe", float("nan")), metrics(s.iloc[h:]).get("sharpe", float("nan"))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E63 — Coinalyze OI + predicted-funding · harness brutal\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    Pd = C.resample("1D").last(); Pd.index = pd.to_datetime(Pd.index, utc=True).normalize()
    PF, OI = load_cz(Pd.index, list(C.columns))
    oi_cov = [c for c in OI.columns if OI[c].notna().sum() > 300 and c != DRIVER]
    print(f"OI cubre {len(oi_cov)} coins operables · predicted-funding {PF.notna().any().sum()} coins\n")

    base = {}
    base["mom_30d"], _ = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _ = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _ = carry_sleeve(C, ret, beta)
    base["trend"], _ = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df7 = pd.concat(base, axis=1).dropna()
    m7 = combine(base)
    print(f"BASELINE 7: Sharpe {m7['sharpe']:.2f} · {m7['ann']/12:.2f}%/mes\n")

    logoi = np.log(OI.replace(0, np.nan)); logp = np.log(Pd[OI.columns])
    rN = lambda N: logp.diff(N)
    def mk(kind, N):
        if kind == "oi_pxdiv": return logoi.diff(N) - rN(N)
        if kind == "oi_mom":   return logoi.diff(N)
        if kind == "oi_dir":   return logoi.diff(N) * np.sign(rN(N))
        return None

    cands = []
    for kind in ("oi_pxdiv", "oi_mom", "oi_dir"):
        for N in (7, 14, 30):
            for sgn in (1, -1):
                cands.append((f"{kind}_{N}d({'+' if sgn>0 else '−'})", kind, N, sgn, N*24))

    print(f"{'candidato':18s} {'Sh':>6s} {'corr_max':>9s} {'(con)':>12s} {'IS/OOS':>11s} {'mes22+':>7s} │ {'Δ%/mes':>7s} adm")
    print("─" * 95)
    passers = []
    for name, kind, N, sgn, hold in cands:
        sd = mk(kind, N) * sgn
        s_c, _ = xs_sleeve(C, ret, beta, to_hourly(sd, C), hold)
        s_c = s_c.reindex(df7.index).dropna()
        if len(s_c) < 200:
            print(f"{name:18s} (insuf.)"); continue
        msolo = metrics(s_c)["sharpe"]
        corrs = {k: df7[k].corr(s_c) for k in df7.columns}
        kmax = max(corrs, key=lambda k: abs(corrs[k])); cmax = corrs[kmax]
        is_, oos_ = half(s_c)
        s22 = s_c[s_c.index >= "2022-01-01"]; mes22 = metrics(s22)["ann"]/12 if len(s22) > 200 else float("nan")
        m8 = combine({**base, name: s_c}); dmes = (m8["ann"] - m7["ann"]) / 12
        ok = abs(cmax) < 0.35 and is_ > 0.05 and oos_ > 0.05 and dmes > 0.05 and (np.isnan(mes22) or mes22 > 0)
        flag = "  ✅" if ok else ("  ~" if dmes > 0 and abs(cmax) < 0.35 else "  ✗")
        if ok: passers.append(name)
        print(f"{name:18s} {msolo:6.2f} {cmax:9.2f} {kmax:>12s} {is_:5.2f}/{oos_:<5.2f} {mes22:7.2f} │ {dmes:+7.2f}{flag}")

    # diagnóstico predicted-funding: ¿corr cross-seccional con el funding realizado (Binance, vía carry)?
    print(f"\nPASAN: {passers or 'NINGUNO'}")
    print("\nDIAGNÓSTICO predicted-funding: el harness mide PRECIO, no funding cobrado. Como SEÑAL DE PRECIO")
    print("(short high pred-funding = crowding):")
    pf_score = -PF                                          # short high predicted funding
    s_pf, _ = xs_sleeve(C, ret, beta, to_hourly(pf_score, C), 72)
    s_pf = s_pf.reindex(df7.index).dropna()
    if len(s_pf) > 200:
        cpf = {k: df7[k].corr(s_pf) for k in df7.columns}; kpf = max(cpf, key=lambda k: abs(cpf[k]))
        ipf, opf = half(s_pf); mpf = combine({**base, "pf": s_pf})
        print(f"  pf_price(short high): Sh {metrics(s_pf)['sharpe']:.2f} · corr_max {cpf[kpf]:+.2f}({kpf}) · "
              f"IS/OOS {ipf:.2f}/{opf:.2f} · Δ%/mes {(mpf['ann']-m7['ann'])/12:+.2f}")
    print("  (Para usar predicted-funding como MEJOR CARRY haría falta la maquinaria de funding cobrado —")
    print("   swap del ranking en carry_sleeve. Si el corr pf↔funding-realizado es ~1, no aporta sobre el carry.)")
    print("\nLo que pase → estrés taker + LOO (e60-style). Cross-section OI casi completo (≠ on-chain delgado).")


if __name__ == "__main__":
    main()
