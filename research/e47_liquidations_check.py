"""
E47 — ¿las LIQUIDACIONES diarias (Coinalyze, GRATIS) son un sleeve DIARIO ortogonal que aporta? (2026-06-01)
Ruta B intradía: el ángulo INTRADÍA de liquidaciones está bloqueado por dato (Coinalyze solo guarda
~2-3 meses rodantes <12h). Pero el histórico DIARIO es gratis y completo (e46: 32/32, 2023→hoy). Nunca
testeamos liquidaciones como sleeve. Aquí el chequeo barato (molde e30): ortogonalidad vs los 7 + criterio
del ancla (Δretorno a maxDD −10%) + estrés. Caveat honesto: el rebote de liquidación suele ser intradía,
así que a diario el edge puede salir débil.

SEÑAL (contrarian, cross-seccional, β-neutral; el signo se auto-orienta en IS como e26/e30):
  - liq_imb_Nd  = media_N( (long_liq − short_liq)/(long_liq+short_liq) )   [dirección de la presión]
      longs liquidados (forzados a vender) → precio cayó → contrarian LONG.
  - liq_net_Nd  = Σ_N(long_liq − short_liq) / Σ_N(quote_volume)            [presión neta escalada por $vol]
SIN LOOK-AHEAD: la liquidación del día D se conoce al cierre de D → se hace disponible en D+1 (shift 1d)
antes de difundir a horario. Hold diario (24/48/72h).

python -m research.e47_liquidations_check
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

LIQ_DIR = os.path.join(config.DATA_DIR, "liquidations_daily")


def sh(r):
    r = r.dropna(); return r.mean()/r.std()*np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), L, m.get("maxdd", float("nan"))


def load_liq_daily(cols):
    """Panel diario de long_liq y short_liq (USD) alineado a `cols`. Índice = día UTC (midnight)."""
    L, S = {}, {}
    for p in glob.glob(os.path.join(LIQ_DIR, "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in cols:
            continue
        df = pd.read_parquet(p).set_index("date")
        L[s] = df["long_liq"]; S[s] = df["short_liq"]
    Ld = pd.DataFrame(L).sort_index(); Sd = pd.DataFrame(S).sort_index()
    Ld.index = pd.to_datetime(Ld.index, utc=True).normalize()
    Sd.index = pd.to_datetime(Sd.index, utc=True).normalize()
    return Ld.reindex(columns=cols), Sd.reindex(columns=cols)


def to_hourly(daily_sig, like):
    """Difunde una señal DIARIA a horario SIN look-ahead: el día D se disponibiliza en D+1 (shift 1d)
    y se ffill-ea al índice horario de `like`."""
    avail = daily_sig.shift(1, freq="1D")
    return avail.reindex(like.index, method="ffill")


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E47 — ¿liquidaciones diarias (GRATIS) ortogonales y aportan sobre los 7 sleeves?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["quote_volume", "volume", "taker_buy_volume"], C)
    cols = list(C.columns)
    Ld, Sd = load_liq_daily(cols)
    cov = Ld.notna().mean().mean()
    print(f"Panel: {C.shape[1]} símbolos · {C.index[0].date()}→{C.index[-1].date()} · "
          f"liq diaria cobertura media {cov*100:.0f}% (desde 2023)\n")

    # 7 sleeves base
    base = {}
    base["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _      = carry_sleeve(C, ret, beta)
    base["trend"], _      = trend_sleeve(C)
    base["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    base["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    bdf = pd.concat(base, axis=1); bdf.columns = list(base); bdf = bdf.dropna()
    combo0 = (bdf * vol_parity_weights(bdf)).sum(axis=1)
    ann0, L0, dd0 = anchored(combo0)
    print(f"BASELINE 7 sleeves: Sharpe {metrics(combo0)['sharpe']:.2f} · @−10% {L0:.2f}x → "
          f"{ann0/12:.2f}%/mes (maxDD {dd0:.1f}%)\n")

    # señales diarias de liquidación
    imb = (Ld - Sd) / (Ld + Sd).replace(0, np.nan)        # [-1,1] dirección
    qv_d = P["quote_volume"].resample("1D").sum()         # $vol diario
    qv_d.index = qv_d.index.normalize()
    net = (Ld - Sd)
    cands = {}
    for N in (1, 3, 5):
        cands[f"liq_imb_{N}d"] = (to_hourly(imb.rolling(N, min_periods=1).mean(), C), 24)
    for N in (3, 5):
        netN = net.rolling(N, min_periods=1).sum() / qv_d.reindex(net.index).rolling(N, min_periods=1).sum().replace(0, np.nan)
        cands[f"liq_net_{N}d"] = (to_hourly(netN, C), 24)
    # holds más largos del mejor familia (imbalance 3d) por si el rebote tarda
    cands["liq_imb_3d_h48"] = (to_hourly(imb.rolling(3, min_periods=1).mean(), C), 48)
    cands["liq_imb_3d_h72"] = (to_hourly(imb.rolling(3, min_periods=1).mean(), C), 72)

    print("CANDIDATOS (Sh/IS/OOS · corr máx vs 7 · con quién · signo · Δ%/mes anclado):")
    print(f"  {'cand':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} {'(con)':>12s} {'sgn':>4s} {'Δ%/mes':>7s}")
    best = []
    for name, (score, hold) in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
        except Exception as e:
            print(f"  {name:16s} ERROR {str(e)[:35]}"); continue
        if s_ret.dropna().shape[0] < 100:
            print(f"  {name:16s} insuf ({s_ret.dropna().shape[0]})"); continue
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
              f"{cmax:6.2f} {cwho:>12s} {sign:+4.0f} {dmes:+7.2f}{'  <' if passes else ''}")
        if passes and dmes > 0.10:
            best.append((name, dmes, cmax, hold, sign, score))

    # ESTRÉS del mejor
    if best:
        bname, _, _, h, sign, score = max(best, key=lambda b: b[1])
        print(f"\nESTRÉS de {bname}:")
        sr_full, _ = xs_sleeve(C, ret, beta, score, h); sr_full = sr_full * sign
        j = pd.concat({**base, "x": sr_full}, axis=1); j.columns = list(base) + ["x"]; j = j.dropna()
        print("  Cuartiles temporales (Sharpe):  " +
              "  ".join(f"Q{i+1} {sh(seg(j['x'],a,b)):+.2f}"
                        for i,(a,b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)])))
        d_full = (anchored((j*vol_parity_weights(j)).sum(axis=1))[0]-ann0)/12
        print(f"  Δ%/mes al ancla (maker):  {d_full:+.2f}")
        syms = [s for s in C.columns if s != "BTCUSDT"]
        print("  LEAVE-ONE-OUT (Δ%/mes al quitar cada símbolo; CAE si baja >0.3):")
        loo = []
        for t in syms:
            sc = score.copy(); sc[t] = np.nan
            srt, _ = xs_sleeve(C, ret, beta, sc, h); srt = srt * sign
            jj = pd.concat({**base, "x": srt}, axis=1); jj.columns = list(base) + ["x"]; jj = jj.dropna()
            loo.append((t, (anchored((jj*vol_parity_weights(jj)).sum(axis=1))[0]-ann0)/12))
        for t, d_t in sorted(loo, key=lambda x: x[1])[:8]:
            print(f"    sin {t:10s} Δ {d_t:+.2f}%/mes  ({'CAE' if d_t < d_full-0.3 else 'ok'})")

    print("\nVEREDICTO:")
    if not best:
        print("  Ningún candidato de liquidaciones es ortogonal (corr<0.35) Y sube el retorno anclado (>+0.1%/mes).")
        print("  → liquidaciones a DIARIO no aportan (el rebote es intradía; lo captura takerflow/rev). Saltar a CME gap.")
    else:
        print(f"  PROMETEDOR: {[b[0] for b in best]} → si el estrés aguanta, candidato. Siguiente: e16e horizonte")
        print("  completo + coste TAKER explícito + walk-forward purgado (regime_lab) antes de cantar sleeve #8.")


if __name__ == "__main__":
    main()
