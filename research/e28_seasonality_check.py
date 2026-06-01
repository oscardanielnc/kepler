"""
E28 — A5 (paso 0): ¿hay ESTACIONALIDAD / efectos de CALENDARIO explotables? (GRATIS, del panel)
(2026-05-31). Último ítem del menú diario barato. No necesita datos nuevos.

LÍMITE estructural (igual que DVOL): los efectos de calendario son market-wide → solo servirían como
OVERLAY de timing (de-risk/risk-on ciertos días), que es la clase del gate de régimen YA descartada.
Lo cross-seccional (un coin que rinda distinto cierto día) suele ser ruido. Aun así se mide:

  T1 DÍA-DE-SEMANA: ¿el COMBINADO 7 sleeves (o BTC) rinde distinto por weekday? IS vs OOS (¿estable?).
  T2 TURN-OF-MONTH: ¿fin/inicio de mes distinto? (efecto turn-of-month clásico).
  T3 VENCIMIENTO: ¿la ventana del último viernes (expiry mensual de opciones/futuros) es distinta?
  T4 OVERLAYS: skip/de-risk el peor bucket → ¿sube el retorno al ancla −10%? (con prueba IS/OOS).

Veredicto: si ningún efecto es ESTABLE IS→OOS y ningún overlay mejora el ancla → DESCARTAR A5.
python -m research.e28_seasonality_check
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

WD = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def sh(r):
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if len(r) > 20 and r.std() > 0 else 0.0


def seg(r, a, b):
    r = r.dropna(); n = len(r); return r.iloc[int(n * a):int(n * b)]


def anchored(combo):
    L = leverage_for_maxdd_anchor(combo, config.TARGET_MAXDD)
    m = metrics(combo * L)
    return m.get("ann", float("nan")), L


def last_friday_window_w(idx, wdays=1):
    """True si la barra cae en la ventana del último viernes del mes (±wdays) = expiry mensual."""
    out = pd.Series(False, index=idx)
    for (y, m), grp in idx.to_series().groupby([idx.year, idx.month]):
        fris = [d for d in grp if d.dayofweek == 4]
        if not fris: continue
        lf = max(fris)
        out[(idx >= lf - pd.Timedelta(days=wdays)) & (idx <= lf + pd.Timedelta(days=wdays))] = True
    return out


def last_friday_window(idx):
    return last_friday_window_w(idx, 1)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E28 — A5 paso 0: ¿estacionalidad / calendario explotable? (GRATIS)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)

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
    btc = C["BTCUSDT"].resample("1D").last().pct_change().reindex(combo.index)
    ann0, L0 = anchored(combo)
    print(f"BASELINE 7 sleeves: Sharpe {metrics(combo)['sharpe']:.2f} · @−10% {L0:.2f}x → {ann0/12:.2f}%/mes")
    print(f"({combo.index[0].date()} → {combo.index[-1].date()}, {len(combo)} días)\n")

    # T1 — DÍA DE SEMANA (combinado y BTC), media diaria en bps, IS vs OOS
    dw = combo.index.dayofweek
    print("T1 — DÍA DE SEMANA · retorno medio (bps/día) COMBINADO [full | IS | OOS] · y BTC full:")
    n = len(combo); isf, oosf = combo.iloc[:int(n*.6)], combo.iloc[int(n*.6):]
    for d in range(7):
        full = combo[dw == d].mean()*1e4
        i = isf[isf.index.dayofweek == d].mean()*1e4
        o = oosf[oosf.index.dayofweek == d].mean()*1e4
        b = btc[btc.index.dayofweek == d].mean()*1e4
        flag = "  ⟵ IS/OOS mismo signo" if (np.sign(i) == np.sign(o) and abs(i) > 2 and abs(o) > 2) else ""
        print(f"  {WD[d]}  combo {full:+6.1f} [{i:+6.1f}|{o:+6.1f}]  · BTC {b:+6.1f}{flag}")

    # T2 — TURN OF MONTH
    dom = combo.index.day
    eom = combo[(dom >= 28) | (dom <= 2)]; mid = combo[(dom > 2) & (dom < 28)]
    print(f"\nT2 — TURN-OF-MONTH (combinado): fin/inicio (d≥28 o ≤2) {eom.mean()*1e4:+.1f}bps "
          f"(Sh {sh(eom):+.2f}) · resto {mid.mean()*1e4:+.1f}bps (Sh {sh(mid):+.2f})")

    # T3 — VENCIMIENTO mensual (ventana último viernes ±1d)
    exp = last_friday_window(combo.index)
    print(f"T3 — VENCIMIENTO (últ. viernes ±1d): dentro {combo[exp].mean()*1e4:+.1f}bps "
          f"(Sh {sh(combo[exp]):+.2f}, n={exp.sum()}) · fuera {combo[~exp].mean()*1e4:+.1f}bps "
          f"(Sh {sh(combo[~exp]):+.2f})")

    # T4 — OVERLAYS: skip el peor weekday (IS) / de-risk turn-of-month → ¿mejora el ancla?
    print("\nT4 — OVERLAYS de calendario (@ancla −10%, peor bucket elegido EN IS):")
    print(f"  {'overlay':30s} {'Sharpe':>7s} {'%/mes':>7s} {'Δ%/mes':>7s} {'OOSΔ':>7s}")
    print(f"  {'(baseline)':30s} {sh(combo):7.2f} {ann0/12:7.2f} {0.0:+7.2f} {'':>7s}")
    worst_wd = int(np.argmin([isf[isf.index.dayofweek == d].mean() for d in range(7)]))
    overlays = {
        f"skip {WD[worst_wd]} (peor IS)": (combo.index.dayofweek != worst_wd).astype(float),
        "de-risk turn-of-month (0.5x)":   pd.Series(np.where((dom >= 28) | (dom <= 2), 0.5, 1.0), index=combo.index),
        "de-risk vencimiento (0.5x)":     pd.Series(np.where(exp, 0.5, 1.0), index=combo.index),
    }
    for name, mult in overlays.items():
        r = combo * mult
        ann, L = anchored(r)
        # robustez: Δ del overlay solo en OOS
        ro, co = seg(r, .6, 1), seg(combo, .6, 1)
        ao, _ = anchored(ro); ac, _ = anchored(co)
        print(f"  {name:30s} {sh(r):7.2f} {ann/12:7.2f} {(ann-ann0)/12:+7.2f} {(ao-ac)/12:+7.2f}")

    # T5 — ROBUSTEZ del de-risk VENCIMIENTO/TURN (¿sobrevive a parámetros, cuartiles y coste de turnover?)
    print("\nT5 — ROBUSTEZ del de-risk (sensibilidad de parámetros · Δ%/mes full | OOS):")
    def overlay_dmes(mask, factor):
        mult = pd.Series(np.where(mask, factor, 1.0), index=combo.index)
        r = combo * mult; ann, _ = anchored(r); d_full = (ann - ann0) / 12
        ao, _ = anchored(seg(r, .6, 1)); ac, _ = anchored(seg(combo, .6, 1))
        return d_full, (ao - ac) / 12
    # ventanas de vencimiento ±0/±1/±2 d y factores 0.5/0.7
    for wdays in (0, 1, 2):
        msk = last_friday_window_w(combo.index, wdays)
        for f in (0.5, 0.7):
            df, do = overlay_dmes(msk.values, f)
            print(f"  vencimiento ±{wdays}d  {f:.1f}x   Δfull {df:+.2f}  ΔOOS {do:+.2f}  (n={int(msk.sum())})")
    for f in (0.5, 0.7):
        df, do = overlay_dmes(((dom >= 28) | (dom <= 2)), f)
        print(f"  turn-of-month       {f:.1f}x   Δfull {df:+.2f}  ΔOOS {do:+.2f}")
    # cuartiles del beneficio del de-risk vencimiento 0.5x (¿repartido o 1-2 eventos?)
    rexp = combo * pd.Series(np.where(exp, 0.5, 1.0), index=combo.index)
    print("  cuartiles Δ (venc 0.5x, Sharpe del overlay − baseline por cuartil):")
    for i, (a, b) in enumerate([(0,.25),(.25,.5),(.5,.75),(.75,1.)]):
        print(f"    Q{i+1}  Δsh {sh(seg(rexp,a,b))-sh(seg(combo,a,b)):+.2f}")
    # coste de turnover del de-risk (NO modelado arriba): bajar a 0.5x y volver = 1.0 gross/evento
    turn_yr = float(pd.Series(np.where(exp,0.5,1.0),index=combo.index).diff().abs().sum()) / ((combo.index[-1]-combo.index[0]).days/365.25)
    print(f"  ⚠️ coste NO modelado: el de-risk añade ~{turn_yr:.0f}x turnover/año del MULTIPLICADOR "
          f"(×gross×fee) — bajar y restaurar posiciones cuesta; recorta el Δ real.")

    print("\nVEREDICTO (chequeo barato):")
    print("  Si ningún día/bucket es ESTABLE IS→OOS y ningún overlay sube el ancla en AMBOS (full y OOS)")
    print("  → DESCARTAR A5 (calendario = market-wide → gate de régimen ya descartado; cross-sec = ruido).")
    print("  Cierra el menú diario barato. Lo que queda: netflow pagado (on-chain) o backtester horario.")


if __name__ == "__main__":
    main()
