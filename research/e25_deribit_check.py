"""
E25 — A6 (paso 0): ¿las OPCIONES de Deribit (DVOL/IV) aportan algo ORTOGONAL y usable al sistema?
(2026-05-31). Chequeo barato (estilo e22/e23) ANTES de invertir en ingesta de opciones.

LIMITACIÓN ESTRUCTURAL (clave): Deribit solo tiene opciones LÍQUIDAS de BTC y ETH (no de los 32 alts).
→ una señal de opciones NO puede ser cross-seccional (no rankea el universo). Solo puede ser:
  (a) un OVERLAY de timing/régimen de mercado  — pero los gates de régimen/vol-target ya fueron
      DESCARTADOS por empeorar el maxDD (CLAUDE.md, engine.compute_target nota "GATE DE RÉGIMEN").
  (b) una estrategia de opciones aparte (short-vol/VRP) — otra pila de ejecución, NO el sistema actual
      (perp, cross-seccional). Fuera de alcance hoy.

Aun así, lo TESTEAMOS con números (no a mano):
  DVOL = índice de vol implícita de Deribit (BTC/ETH), diario, gratis (API pública, 2021-03→hoy).
  T1 REDUNDANCIA: corr(DVOL, vol REALIZADA de BTC) → ¿cuánto es info nueva vs lo que lowvol ya usa?
  T2 TIMING: overlays DVOL (de-risk vol alta/subiendo, risk-on vol baja) sobre el COMBINADO 7 sleeves
     → ¿mejora el retorno al ancla maxDD −10%? (si no, reconfirma el descarte del gate de régimen).
  T3 PREDICCIÓN: ¿DVOL/ΔDVOL predice el retorno FORWARD del combinado o su vol? (corr).

python -m research.e25_deribit_check
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

CACHE = os.path.join(config.DATA_DIR, "deribit"); os.makedirs(CACHE, exist_ok=True)
DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"


def fetch_dvol(ccy):
    """DVOL diario completo (paginado hacia atrás; cacheado)."""
    out = os.path.join(CACHE, f"dvol_{ccy}.parquet")
    if os.path.exists(out):
        return pd.read_parquet(out)["dvol"]
    end = int(time.time() * 1000); parts = []
    for _ in range(12):
        r = requests.get(DVOL_URL, params={"currency": ccy, "start_timestamp": int(dt.datetime(2019, 1, 1).timestamp()*1000),
                                            "end_timestamp": end, "resolution": "1D"}, timeout=30)
        d = r.json().get("result", {}).get("data", [])
        if not d:
            break
        parts.append(pd.DataFrame(d, columns=["ts", "o", "h", "l", "c"]))
        new_end = int(d[0][0]) - 86400000
        if new_end >= end:
            break
        end = new_end
        if len(d) < 1000:
            break
    df = pd.concat(parts, ignore_index=True).drop_duplicates("ts").sort_values("ts")
    s = pd.Series(df["c"].values, index=pd.to_datetime(df["ts"], unit="ms", utc=True), name="dvol")
    s = s[~s.index.duplicated()]
    s.to_frame().to_parquet(out)
    return s


def daily(s):
    return s.resample("1D").last()


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), L, m.get("maxdd", float("nan"))


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E25 — A6 paso 0: ¿opciones Deribit (DVOL) aportan algo ortogonal y usable?\n")
    print("LÍMITE ESTRUCTURAL: Deribit solo BTC/ETH → NO cross-seccional. Solo overlay de timing")
    print("(clase ya descartada: gate de régimen empeoró maxDD). Se confirma con números.\n")

    # --- DVOL ---
    dv_btc = fetch_dvol("BTC"); dv_eth = fetch_dvol("ETH")
    print(f"DVOL BTC: {len(dv_btc)} días {dv_btc.index[0].date()}→{dv_btc.index[-1].date()} "
          f"(media {dv_btc.mean():.0f}, rango {dv_btc.min():.0f}-{dv_btc.max():.0f})")
    print(f"DVOL ETH: {len(dv_eth)} días\n")

    # --- precios + vol realizada de BTC ---
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    btc_d = daily(C["BTCUSDT"]).pct_change()
    rvol = btc_d.rolling(30).std() * np.sqrt(365) * 100      # vol realizada anualizada %
    dvb = daily(dv_btc).reindex(rvol.index).ffill(limit=2)

    # T1 — REDUNDANCIA con vol realizada
    j1 = pd.concat({"dvol": dvb, "rvol30": rvol}, axis=1).dropna()
    c_lvl = j1["dvol"].corr(j1["rvol30"])
    vrp = (j1["dvol"] - j1["rvol30"])                          # variance risk premium proxy
    print("T1 — REDUNDANCIA DVOL vs vol REALIZADA de BTC:")
    print(f"  corr(DVOL, rvol30) = {c_lvl:.2f}  (alto = DVOL ≈ lo que lowvol ya ve)")
    print(f"  VRP = DVOL−rvol: media {vrp.mean():+.1f}pp (implícita suele > realizada), std {vrp.std():.1f}\n")

    # --- combinado 7 sleeves ---
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
    combo = (bdf * vol_parity_weights(bdf)).sum(axis=1)

    # alinear DVOL al índice del combinado (overlap)
    dvd = daily(dv_btc).reindex(combo.index).ffill(limit=2)
    ov = combo[dvd.notna()]
    first = ov.index[0]
    ann0, L0, dd0 = anchored(ov)
    print(f"BASELINE 7 sleeves (overlap DVOL {first.date()}→{ov.index[-1].date()}, {len(ov)}d): "
          f"Sharpe {sh(ov):.2f} · @−10% {L0:.2f}x → {ann0/12:.2f}%/mes\n")

    # señales DVOL (conocidas en t, escalan el retorno t→t+1; sin look-ahead)
    z = ((dvd - dvd.rolling(60).mean()) / dvd.rolling(60).std())
    dchg = dvd.diff(5)
    sigs = {
        "de-risk vol ALTA (z>1→0.5x)":   (z.shift(1) > 1).map({True: 0.5, False: 1.0}),
        "de-risk vol SUBIENDO (Δ5>0)":   (dchg.shift(1) > 0).map({True: 0.7, False: 1.0}),
        "risk-ON vol BAJA (z<−0.5→1.3x)":(z.shift(1) < -0.5).map({True: 1.3, False: 1.0}),
        "vol-target inverso a DVOL":      (dvd.shift(1).median() / dvd.shift(1)).clip(0.4, 1.6),
    }
    print("T2 — OVERLAYS de timing DVOL sobre el combinado (@ancla −10%):")
    print(f"  {'overlay':32s} {'Sharpe':>7s} {'@-10%x':>7s} {'%/mes':>7s} {'Δ%/mes':>7s}")
    print(f"  {'(baseline)':32s} {sh(ov):7.2f} {L0:7.2f} {ann0/12:7.2f} {0.0:+7.2f}")
    for name, mult in sigs.items():
        m = mult.reindex(ov.index).fillna(1.0)
        r = ov * m
        ann, L, dd = anchored(r)
        print(f"  {name:32s} {sh(r):7.2f} {L:7.2f} {ann/12:7.2f} {(ann-ann0)/12:+7.2f}")

    # T2b — ¿el Δ del mejor overlay es ROBUSTO o solo del bear 2022? (IS/OOS por mitades)
    print("\nT2b — ROBUSTEZ del mejor overlay (de-risk vol SUBIENDO) IS vs OOS:")
    mbest = sigs["de-risk vol SUBIENDO (Δ5>0)"].reindex(ov.index).fillna(1.0)
    for lbl, a, b in [("IS (1ª mitad, incl. 2022)", 0.0, 0.5), ("OOS (2ª mitad)", 0.5, 1.0)]:
        seg = ov.iloc[int(len(ov)*a):int(len(ov)*b)]
        segm = mbest.iloc[int(len(ov)*a):int(len(ov)*b)]
        a0, _, _ = anchored(seg); a1, _, _ = anchored(seg * segm)
        print(f"  {lbl:28s} {seg.index[0].date()}→{seg.index[-1].date()}  "
              f"baseline {a0/12:+5.2f}%/mes · overlay {a1/12:+5.2f} · Δ {(a1-a0)/12:+.2f}")

    # T3 — ¿DVOL predice el forward del combinado o su vol?
    fwd = ov.shift(-1)                       # retorno del día siguiente
    fvol = ov.shift(-1).rolling(10).std()    # vol futura aprox
    zz = z.reindex(ov.index)
    print("\nT3 — PREDICCIÓN (señal en t vs forward del combinado):")
    print(f"  corr(z_DVOL, ret_fwd)        = {zz.corr(fwd):+.3f}  (≈0 → no predice dirección del PnL)")
    print(f"  corr(z_DVOL, |ret|_fwd/vol)  = {zz.corr(fvol):+.3f}  (>0 → DVOL alto anticipa más vol)")

    print("\nVEREDICTO (chequeo barato):")
    print("  Estructural: opciones = solo BTC/ETH → no cross-seccional. Único uso = overlay de timing.")
    print("  Si ningún overlay sube el retorno anclado y DVOL es redundante con la vol realizada →")
    print("  DESCARTAR para el sistema diario actual (reconfirma el descarte del gate de régimen).")
    print("  La info de opciones (VRP/short-vol) sería otra ESTRATEGIA (pila de opciones), no este sistema.")


if __name__ == "__main__":
    main()
