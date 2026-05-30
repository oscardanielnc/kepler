"""
E16c — ESTRÉS de taker_flow (candidato a sleeve #6) antes de producción (2026-05-30).
e16b lo encontró: Sharpe 0.91 (IS 0.68/OOS 1.18), corr<0.06, combinado 5→6 sleeves
sube Sharpe 1.13→1.36 y baja maxDD −11.6%→−8.6%. Antes de implementar (regla de oro),
verificar que NO es cherry-pick:

  TEST 1  Barrido de HORIZONTE (1d..7d): el edge debe existir en un rango, no en un punto.
  TEST 2  COSTOS: maker vs taker — ¿sobrevive el peor caso de ejecución?
  TEST 3  SUB-PERÍODOS OOS: partir el OOS en mitades — el edge no debe venir de un solo tramo.
  TEST 4  Aporte al COMBINADO por horizonte: ΔSharpe / ΔmaxDD estables.

python -m research.e16c_stress_takerflow
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, MIN_BARS
from kepler.portfolio import vol_parity_weights, metrics


def load_flow(C):
    vol = {}; tbv = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        df = pd.read_parquet(p, columns=["open_time", "volume", "taker_buy_volume"]).set_index("open_time")
        if len(df) < MIN_BARS:
            continue
        vol[s] = df["volume"]; tbv[s] = df["taker_buy_volume"]
    V = pd.DataFrame(vol).sort_index(); T = pd.DataFrame(tbv).sort_index()
    for X in (V, T): X.index = pd.to_datetime(X.index, unit="ms", utc=True)
    V = V.reindex(index=C.index, columns=C.columns); T = T.reindex(index=C.index, columns=C.columns)
    return (T / V.replace(0, np.nan) - 0.5)     # desbalance comprador


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n*a):int(n*b)]


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E16c — ESTRÉS de taker_flow antes de producción\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    flow = load_flow(C)
    print(f"Universo {C.shape[1]} · {C.shape[0]} barras 1h\n")

    base = {}
    base["mom_30d"], _   = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _   = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _     = carry_sleeve(C, ret, beta)
    base["trend"], _     = trend_sleeve(C)
    base_df = pd.concat(base, axis=1).dropna()
    m0 = metrics((base_df * vol_parity_weights(base_df)).sum(axis=1))
    print(f"BASELINE (5): Sharpe {m0['sharpe']:.2f} · maxDD {m0['maxdd']:.1f}% · mo_med {m0['mo_med']:.2f}%\n")

    print("TEST 1+2 — HORIZONTE × COSTOS (Sharpe full/IS/OOS, corr, y aporte al combinado):")
    print(f"  {'horiz':>6s} {'cost':>6s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corr':>6s} "
          f"{'comboSh':>8s} {'comboDD%':>9s}")
    flows = {}
    for days in (1, 2, 3, 5, 7):
        hold = days * 24
        score = flow.rolling(hold).mean()
        for cost_label, cost in (("maker", config.MAKER_FEE), ("taker", config.TAKER_FEE)):
            # xs_sleeve usa config.MAKER_FEE internamente; para el test de taker reusamos pero
            # restamos un proxy de costo extra por turnover. Aproximación conservadora:
            s_ret, _ = xs_sleeve(C, ret, beta, score, hold)
            if cost_label == "taker":
                # penaliza ~ (taker-maker) sobre turnover medio estimado (1 rebalanceo/hold)
                pen = (config.TAKER_FEE - config.MAKER_FEE) * (365 / days) / 365
                s_ret = s_ret - pen
            j = pd.concat({**base, "flow": s_ret}, axis=1).dropna()
            corr = j.corr()["flow"].drop("flow").abs().max()
            combo = (j * vol_parity_weights(j)).sum(axis=1); mc = metrics(combo)
            print(f"  {days:>5d}d {cost_label:>6s} {sh(j['flow']):6.2f} {sh(seg(j['flow'],0,0.6)):6.2f} "
                  f"{sh(seg(j['flow'],0.6,1)):6.2f} {corr:6.2f} {mc['sharpe']:8.2f} {mc['maxdd']:9.1f}")
            if cost_label == "maker":
                flows[days] = s_ret

    print("\nTEST 3 — SUB-PERÍODOS del candidato 3d (Sharpe por cuartil temporal):")
    f3 = flows[3]
    for i, (a, b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)]):
        print(f"  Q{i+1} [{a:.2f}-{b:.2f}]  Sharpe {sh(seg(f3,a,b)):+.2f}")
    print("  → el edge debe ser positivo en la mayoría de cuartiles, no concentrado en uno.")

    print("\nTEST 4 — COMBINADO 6 sleeves (flow 3d, maker) vs baseline:")
    j = pd.concat({**base, "taker_flow_3d": flows[3]}, axis=1).dropna()
    vp = vol_parity_weights(j); combo = (j * vp).sum(axis=1); m = metrics(combo)
    print(f"  Sharpe {m['sharpe']:.2f} (Δ{m['sharpe']-m0['sharpe']:+.2f}) · maxDD {m['maxdd']:.1f}% "
          f"(Δ{m['maxdd']-m0['maxdd']:+.1f}pp) · mo_med {m['mo_med']:.2f}% · mo+ {m['mo_pos']:.0f}%")
    L = abs(m0['maxdd'])/abs(m['maxdd']); mL = metrics(combo*L)
    print(f"  A igual maxDD (−{abs(m0['maxdd']):.1f}%): {L:.2f}x → {mL['ann']:.1f}%/año (~{mL['ann']/12:.2f}%/mes) "
          f"vs hoy ~{m0['ann']/12:.2f}%/mes")
    print("\nVEREDICTO: implementar SOLO si TEST1 muestra edge en rango de horizontes, TEST2 sobrevive")
    print("taker, y TEST3 no depende de un solo cuartil. Si algo falla → no a producción.")


if __name__ == "__main__":
    main()
