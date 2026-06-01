"""
E45 — FASE 2 INTRADÍA: order-book imbalance a holds 1h–12h con COSTE REAL (INTRADAY.md §5). 2026-06-01.
El order-book diario rezagado (e24) daba Sharpe ~1.3 pero +0.00%/mes al ancla a coste taker → su edge
es SUB-DIARIO (firma look-ahead 7-9 contemporáneo vs 1.3 rezagado). Fase 1 (e42) dio un backtester
horario que RECONCILIA con el motor (corr bloque 1.000); e44 le añadió el coste de cruzar el spread.
Aquí cerramos el círculo: cargamos el imbalance NATIVO 30s (e43), lo resampleamos a horario, score=−imb
(contrarian) y lo evaluamos a holds {1,2,4,6,12,24}h con cost_vector('taker_adv').

Pregunta de admisión (la de siempre, e16d/e24): ¿sube el retorno al maxDD −10% con COSTE REAL? Si sí,
walk-forward IS/OOS honesto + estrés por cuartiles antes de cantar "primer sleeve intradía".

ALINEACIÓN (sin look-ahead): imbalance medio durante la barra [t,t+1h) → se decide al CIERRE de esa
barra (precio C.iloc[t]) → forward return desde t. Misma convención que los sleeves del motor.
VENTANA: bookDepth existe 2023+ → evaluamos en el overlap 2023+ (ciega 2022; caveat estructural e24).

python -m research.e45_intraday_orderbook [imb1|imb2|imb5]
"""
from __future__ import annotations
import os, sys, glob, time
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, _beta, load_panel, DRIVER, BETA_W
from kepler.portfolio import metrics
from research.e44_intraday_cost import eval_intraday, cost_vector, slip_adv

CACHE = os.path.join(config.DATA_DIR, "bookdepth_30s")
OVERLAP_START = "2023-01-01"


def load_imb_hourly(band, like):
    """Imbalance 30s → HORARIO (media de la barra), alineado a `like`. Procesa símbolo a símbolo
    (descarta el raw) → memoria contenida. Cachea el panel horario (rápido en re-runs)."""
    cache = os.path.join(CACHE, f"_hourly_{band}.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache).reindex(index=like.index, columns=like.columns)
    cols = {}
    for p in sorted(glob.glob(os.path.join(CACHE, "*.parquet"))):
        s = os.path.basename(p)[:-8]
        if s not in like.columns or s.startswith("_"):
            continue
        try:
            df = pd.read_parquet(p, columns=[band])
        except Exception:
            continue                                 # símbolo sin esa banda
        h = df[band].resample("1h").mean()          # media de los snaps 30s dentro de la hora
        cols[s] = h.astype("float32")
    P = pd.DataFrame(cols).sort_index()
    P.to_parquet(cache)
    return P.reindex(index=like.index, columns=like.columns)


def coverage(imb):
    """% de celdas no-NaN por año (sanity de cobertura del panel intradía)."""
    nn = imb.notna()
    by = nn.groupby(imb.index.year).mean().mean(axis=1)
    return by


def subperiod(daily, n):
    """Sharpe por sub-período (n cortes iguales) — estrés temporal estilo e16c/e24.
    Slicing por iloc para PRESERVAR el índice datetime (metrics lo necesita)."""
    out = []; L = len(daily)
    for i in range(n):
        c = daily.iloc[i * L // n:(i + 1) * L // n].dropna()
        out.append(metrics(c)["sharpe"] if len(c) > 10 else float("nan"))
    return out


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    band_arg = sys.argv[1] if len(sys.argv) > 1 else None
    print("E45 — FASE 2 INTRADÍA · order-book imbalance a 1h–12h con coste real\n" + "=" * 70)
    t0 = time.time()

    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    dvol = load_panel(["quote_volume"], C)["quote_volume"]
    cols = list(C.columns)
    cmaker = cost_vector(cols, dvol, "maker")
    ctkadv = cost_vector(cols, dvol, "taker_adv")
    ctk3   = cost_vector(cols, dvol, "taker_adv3")
    print(f"Panel precio: {C.shape[0]} barras 1h, {C.shape[1]} símbolos. "
          f"Coste taker+slipADV mediana {slip_adv(dvol,cols).median()*1e4+config.TAKER_FEE*1e4:.1f}bps. "
          f"t+{time.time()-t0:.0f}s")

    bands = [band_arg] if band_arg else ["imb1", "imb2", "imb5"]
    HOLDS = (1, 2, 4, 6, 12, 24)
    # SIGNO: e23/e24 hallaron contrarian a DIARIO, pero a horizonte sub-diario el flujo de órdenes suele
    # ser de CONTINUACIÓN (momentum). Probamos AMBOS signos: el de maker>0 indica el signo real del edge.
    SIGNS = {"contrarian(-imb)": -1.0, "momentum(+imb)": +1.0}
    mask = C.index >= pd.Timestamp(OVERLAP_START, tz="UTC")
    Cm, betam = C[mask], beta[mask]
    results = {}
    for band in bands:
        imb = load_imb_hourly(band, C)[mask]
        cov = coverage(imb)
        print(f"\n── BANDA {band} ── cobertura por año: " +
              " ".join(f"{int(y)}:{v*100:.0f}%" for y, v in cov.items()))
        for signame, sgn in SIGNS.items():
            score = sgn * imb
            print(f"  signo={signame}")
            print(f"    {'hold':>5s} {'turn/año':>9s} {'Sh maker':>9s} {'Sh tk+ADV':>10s} "
                  f"{'Sh tk×3':>8s} {'%/mes mk':>9s} {'%/mes tk':>9s} {'lev':>5s}")
            for hold in HOLDS:
                try:
                    rm = eval_intraday(Cm, betam, score, hold, cmaker)
                    rt = eval_intraday(Cm, betam, score, hold, ctkadv)
                    r3 = eval_intraday(Cm, betam, score, hold, ctk3)
                    results[(band, signame, hold)] = rt
                    print(f"    {hold:>4d}h {rm['turnover']:9.0f} {rm['sharpe']:9.2f} {rt['sharpe']:10.2f} "
                          f"{r3['sharpe']:8.2f} {rm['ann_anchored']/12:9.2f} {rt['ann_anchored']/12:9.2f} "
                          f"{rt['lev']:5.2f}")
                except Exception as e:
                    print(f"    {hold:>4d}h ERROR {str(e)[:50]}")

    # ── mejor configuración por Sharpe a coste taker+ADV ──
    if results:
        best = max(results.items(), key=lambda kv: kv[1]["sharpe"])
        (bb, bsig, bh), br = best
        print("\n" + "=" * 70)
        print(f"MEJOR @taker+ADV: {bb} {bsig} hold={bh}h → Sharpe {br['sharpe']:.2f} · "
              f"%/mes anclado {br['ann_anchored']/12:.2f} · turnover {br['turnover']:.0f}x · lev {br['lev']:.2f}")
        d = br["daily"]
        # walk-forward IS/OOS (mitades) + estrés por cuartiles
        half = len(d) // 2
        is_sh = metrics(d.iloc[:half])["sharpe"]; oos_sh = metrics(d.iloc[half:])["sharpe"]
        q = subperiod(d, 4)
        print(f"  WALK-FORWARD  IS {is_sh:+.2f} · OOS {oos_sh:+.2f}   "
              f"(OOS≈IS y >0 = no overfit de mitad)")
        print(f"  CUARTILES     " + " / ".join(f"{x:+.2f}" for x in q) +
              "   (todos >0 = robusto temporal)")
        print(f"\nADMISIÓN (e16d/e24): el sleeve entra SOLO si sube el retorno al maxDD −10% con coste\n"
              f"REAL (taker+ADV) Y aguanta OOS+cuartiles. Veredicto abajo según los números de arriba.")
    print(f"\nt+{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
