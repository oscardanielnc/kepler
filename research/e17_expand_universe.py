"""
E17 — ¿Ampliar el universo MEJORA el sistema? (2026-05-30, ROADMAP A1)
Validación HONESTA (advertencia de Oscar: más símbolos NO es automáticamente mejor; un perp
ruidoso puede diluir y destruir métricas). Un candidato solo se justifica si:
  (1) SUBE el retorno al maxDD anclado (−10%),  (2) NO empeora el OOS,  (3) NO recorta el panel
  (los XS sleeves necesitan historia ≥ MIN_BARS; un símbolo corto recortaría la ventana de TODOS).

Método: corre los 7 sleeves con universo BASE (32) vs +candidatos. Mide Sharpe, OOS, maxDD(1x) y
retorno@−10%. Greedy 1-a-1 para ver quién suma y quién resta. Subconjunto ganador con criterio.

python -m research.e17_expand_universe
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler import alphas
import kepler.engine as eng
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

CANDS = ["XMRUSDT","ALGOUSDT","STGUSDT","ICPUSDT","AXSUSDT","DASHUSDT","DYDXUSDT",
         "1000SHIBUSDT","CHZUSDT","IOTAUSDT","OPUSDT","VETUSDT","APEUSDT","ENSUSDT",
         "BATUSDT","ARUSDT","1000LUNCUSDT","XTZUSDT","CRVUSDT","SANDUSDT","LDOUSDT"]


def run_system(universe, min_bars):
    old, old_mb = config.UNIVERSE, eng.MIN_BARS
    config.UNIVERSE = universe; eng.MIN_BARS = min_bars
    try:
        C = eng.load(); ret = np.log(C).diff(); beta = eng._beta(ret)
        P = eng.load_panel(["volume", "taker_buy_volume"], C)
        series = {}
        for name, typ, hold in eng.SLEEVES:
            if typ == "xs_mom":   s, _ = eng.xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, hold), hold)
            elif typ == "xs_rev": s, _ = eng.xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, hold), hold)
            elif typ == "xs_lowvol": s, _ = eng.xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, hold), hold)
            elif typ == "xs_flow": s, _ = eng.xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], hold), hold)
            elif typ == "xs_hlpos": s, _ = eng.xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, hold), hold)
            elif typ == "carry": s, _ = eng.carry_sleeve(C, ret, beta)
            else: s, _ = eng.trend_sleeve(C)
            series[name] = s
        df = pd.concat(series, axis=1); df.columns = list(series.keys()); df = df.dropna()
        combo = (df * vol_parity_weights(df)).sum(axis=1)
        return combo, C.shape[1], C.index[0]
    finally:
        config.UNIVERSE = old; eng.MIN_BARS = old_mb


def report(combo, label):
    m = metrics(combo); cut = int(len(combo) * 0.6)
    oos = metrics(combo.iloc[cut:]) or {}
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD); mL = metrics(combo * L)
    return dict(label=label, sharpe=m["sharpe"], oos=oos.get("sharpe", 0),
                maxdd1x=m["maxdd"], lev=L, ann=mL["ann"], mes=mL["ann"]/12, n=len(combo))


def line(r):
    return (f"  {r['label']:24s} Sh={r['sharpe']:.2f} OOS={r['oos']:.2f} maxDD1x={r['maxdd1x']:5.1f}% "
            f"| @-10%: {r['lev']:.2f}x ann={r['ann']:5.1f}% ({r['mes']:.2f}%/mes)  obs={r['n']}")


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E17 — ¿Ampliar universo mejora? (criterio: retorno@−10%, sin recortar panel ni OOS)\n")
    d = os.path.join(config.DATA_DIR, "futures_um", "1h")
    avail = [s for s in CANDS if os.path.exists(os.path.join(d, f"{s}.parquet"))]
    print(f"Candidatos disponibles: {len(avail)}/{len(CANDS)}\n")

    MB = eng.MIN_BARS  # mismo MIN_BARS de producción (34000) → no recorta el panel
    base, nb, t0b = run_system(config.UNIVERSE, MB)
    rb = report(base, f"BASE ({nb} símb)")
    print(f"BASELINE (MIN_BARS={MB}, panel desde {t0b.date()}):"); print(line(rb)); print()

    full, nf, t0f = run_system(list(config.UNIVERSE) + avail, MB)
    rf = report(full, f"+TODOS ({nf})")
    print("AMPLIADO con TODOS los candidatos:"); print(line(rf))
    print(f"  Δ vs base: Sharpe {rf['sharpe']-rb['sharpe']:+.2f} · {rf['mes']-rb['mes']:+.2f}%/mes"
          f"{'  ⚠️ RECORTA PANEL' if t0f.date()>t0b.date() else ''}\n")

    print("APORTE INDIVIDUAL (candidato añadido solo al base, MIN_BARS producción):")
    print(f"  {'símbolo':14s} {'ΔSharpe':>8s} {'ΔOOS':>7s} {'Δ%/mes':>7s} {'maxDD1x':>8s} {'panel':>9s}")
    rows = []
    for s in avail:
        c, n, t0 = run_system(list(config.UNIVERSE) + [s], MB)
        r = report(c, s)
        chop = "RECORTA" if t0.date() > t0b.date() else "ok"
        rows.append((s, r["sharpe"]-rb["sharpe"], r["oos"]-rb["oos"], r["mes"]-rb["mes"], r["maxdd1x"], chop, n))
    for s, dsh, doos, dmes, dd, chop, n in sorted(rows, key=lambda x: -x[3]):
        print(f"  {s:14s} {dsh:+8.2f} {doos:+7.2f} {dmes:+7.2f} {dd:7.1f}% {chop:>9s}")

    win = [s for s, dsh, doos, dmes, dd, chop, n in rows if dmes > 0.03 and doos > -0.05 and chop == "ok"]
    print(f"\nSUBCONJUNTO GANADOR (Δ%/mes>+0.03, OOS no peor, no recorta): {win}")
    if win:
        wc, nw, t0w = run_system(list(config.UNIVERSE) + win, MB)
        rw = report(wc, f"+GANADORES ({nw})")
        print(line(rw))
        print(f"  Δ vs base: Sharpe {rw['sharpe']-rb['sharpe']:+.2f} · {rw['mes']-rb['mes']:+.2f}%/mes")
    print("\nLECTURA: ampliar SOLO si el subconjunto ganador sube %/mes de forma material. Discutir con Oscar.")


if __name__ == "__main__":
    main()
