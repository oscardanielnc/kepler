"""
E16b — Sleeves de FUENTE ORTOGONAL al precio (2026-05-30). Continuación de e16.
Ronda 1 (e16): todo candidato de PRECIO sale correlacionado con los sleeves existentes.
Ronda 2 (aquí): señales que NO son precio puro → mayor chance de corr~0 → bajan el maxDD.

Candidatos (cross-seccional, β-neutral, sin lookahead, vía engine.xs_sleeve):
  - taker_flow_3d   desbalance comprador = taker_buy/volume, momentum 3d (presión de órdenes)
  - taker_rev_3d    −(taker_flow) : reversión del flujo (lo opuesto, por si revierte)
  - illiq_amihud    iliquidez de Amihud |ret|/quote_vol, 14d → prima de iliquidez (long iliq)
  - attention_rev   −shock de volumen (vol/medias) 7d → short 'lotería'/atención (anti-burbuja)
  - trade_size      quote_volume/count (ticket medio) 7d → proxy de flujo institucional
  - funding_tsz     z-score TEMPORAL del funding por activo (anomalía propia, ≠ carry XS)

python -m research.e16b_orthogonal_sleeves
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, DRIVER, MIN_BARS
from kepler.portfolio import vol_parity_weights, metrics


def load_panels(cols):
    """Panels (close + extras) alineados al universo de historia larga (como engine.load)."""
    data = {c: {} for c in cols}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        df = pd.read_parquet(p, columns=["open_time", *cols]).set_index("open_time")
        if len(df) < MIN_BARS:
            continue
        for c in cols:
            data[c][s] = df[c]
    out = {}
    for c in cols:
        P = pd.DataFrame(data[c]).sort_index()
        P.index = pd.to_datetime(P.index, unit="ms", utc=True)
        out[c] = P
    # alinear todos al índice común de close (dropna en close)
    close = out["close"].dropna()
    idx = close.index
    for c in cols:
        out[c] = out[c].reindex(idx)
    return out


def load_funding(idx):
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f
    F = pd.DataFrame(fd).sort_index()
    return F.reindex(idx.union(F.index)).ffill().reindex(idx)


def sh_isoos(r):
    r = r.dropna(); cut = int(len(r) * 0.6)
    f = lambda x: x.mean() / x.std() * np.sqrt(365) if len(x) > 20 and x.std() > 0 else 0.0
    return f(r), f(r.iloc[:cut]), f(r.iloc[cut:])


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E16b — Sleeves de fuente ORTOGONAL (flujo/atención/iliquidez/funding-tsz)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panels(["close", "volume", "quote_volume", "count", "taker_buy_volume"])
    # asegurar mismas columnas/índice que C
    P = {k: v.reindex(index=C.index, columns=C.columns) for k, v in P.items()}
    F = load_funding(C.index).reindex(columns=C.columns)
    print(f"Universo {C.shape[1]} símbolos · {C.shape[0]} barras 1h\n")

    base = {}
    base["mom_30d"], _   = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    base["rev_60d"], _   = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    base["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    base["carry"], _     = carry_sleeve(C, ret, beta)
    base["trend"], _     = trend_sleeve(C)
    base_df = pd.concat(base, axis=1).dropna()
    vp0 = vol_parity_weights(base_df); combo0 = (base_df * vp0).sum(axis=1)
    m0 = metrics(combo0)
    print(f"BASELINE (5 sleeves): Sharpe {m0['sharpe']:.2f} · ann {m0['ann']:.1f}% · "
          f"maxDD {m0['maxdd']:.1f}% · mo_med {m0['mo_med']:.2f}%\n")

    # --- construir scores cross-seccionales (alineados a C) ---
    vol = P["volume"]; qv = P["quote_volume"]; cnt = P["count"]; tbv = P["taker_buy_volume"]
    flow = (tbv / vol.replace(0, np.nan) - 0.5)             # desbalance comprador
    amihud = (ret.abs() / qv.replace(0, np.nan))            # iliquidez
    vshock = vol / vol.rolling(168).mean()                  # shock de volumen 7d
    tsize = qv / cnt.replace(0, np.nan)                     # ticket medio
    f_tsz = (F - F.rolling(720).mean()) / F.rolling(720).std()  # z temporal funding 30d

    cands = {
        "taker_flow_3d":  (flow.rolling(72).mean(), 72),
        "taker_rev_3d":   (-flow.rolling(72).mean(), 72),
        "illiq_amihud":   (amihud.rolling(336).mean(), 336),
        "attention_rev":  (-vshock.rolling(168).mean(), 168),
        "trade_size":     (tsize.rolling(168).mean(), 168),
        "funding_tsz":    (-f_tsz, 6),   # short funding-z alto (anomalía propia), rebal 6h... usar 24h
    }
    # funding_tsz mejor a horizonte diario
    cands["funding_tsz"] = (-f_tsz, 24)

    print("CANDIDATOS (Sharpe full/IS/OOS · |corr| máx con los 5 base):")
    print(f"  {'sleeve':16s} {'Sh':>6s} {'IS':>6s} {'OOS':>6s} {'corrMax':>8s} {'(con)':>12s} {'¿pasa?':>7s}")
    survivors = {}
    for name, (score, hold) in cands.items():
        try:
            s_ret, _ = xs_sleeve(C, ret, beta, score.reindex(index=C.index, columns=C.columns), hold)
        except Exception as e:
            print(f"  {name:16s} ERROR: {str(e)[:40]}"); continue
        j = pd.concat({**base, name: s_ret}, axis=1).dropna()
        if name not in j or j[name].std() == 0:
            print(f"  {name:16s} vacío/constante"); continue
        corr = j.corr()[name].drop(name); cmax = corr.abs().max(); cwho = corr.abs().idxmax()
        sh, i, o = sh_isoos(j[name])
        ok = (i > 0.10 and o > 0.10 and cmax < 0.35)
        print(f"  {name:16s} {sh:6.2f} {i:6.2f} {o:6.2f} {cmax:8.2f} {cwho:>12s} {'SÍ' if ok else 'no':>7s}")
        if ok: survivors[name] = s_ret

    if not survivors:
        print("\n→ Ningún candidato ortogonal pasa. Documentar y proponer ronda 3 (otros horizontes/fuentes).")
        return

    print(f"\nSUPERVIVIENTES: {list(survivors)} → combinando con los 5 base (vol-parity):")
    new_df = pd.concat({**base, **survivors}, axis=1).dropna()
    vp = vol_parity_weights(new_df); combo = (new_df * vp).sum(axis=1)
    m = metrics(combo)
    print(f"  vol-parity: { {k: round(v,2) for k,v in vp.items()} }")
    print(f"  NUEVO COMBINADO: Sharpe {m['sharpe']:.2f} · ann {m['ann']:.1f}% · maxDD {m['maxdd']:.1f}% · "
          f"mo_med {m['mo_med']:.2f}% · mo+ {m['mo_pos']:.0f}%")
    print(f"  ΔSharpe {m['sharpe']-m0['sharpe']:+.2f} · ΔmaxDD {m['maxdd']-m0['maxdd']:+.1f}pp")
    L = abs(m0['maxdd']) / abs(m['maxdd']); mL = metrics(combo * L)
    print(f"\n  A IGUAL maxDD (−{abs(m0['maxdd']):.1f}%): leverage {L:.2f}x → ann {mL['ann']:.1f}% "
          f"(~{mL['ann']/12:.2f}%/mes) vs hoy ~{m0['ann']/12:.2f}%/mes")
    print("\n  REGLA DE ORO: backtest. Validar OOS estable antes de producción.")


if __name__ == "__main__":
    main()
