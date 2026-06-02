"""
E56 — RECONCILIACIÓN DEL SHARPE (honestidad del 2.07). 2026-06-02. e15 destapó que el libro marcado a
diario daba Sharpe ~1.3 vs el motor 2.07. ¿El 2.07 está inflado?

HIPÓTESIS: el motor mide cada sleeve como serie RESAMPLEADA POR BLOQUE (retorno concentrado en el cierre
del bloque-hold, ceros en medio: `(1+rets).cumprod().resample('1D').ffill().pct_change()`). e42 mostró que
POR SLEEVE eso reconcilia con el MTM diario (corr 1.000). Pero al COMBINAR series dispersas, los saltos de
cada sleeve caen en días DISTINTOS (cada uno en su calendario de bloque) → baja la covarianza/vol diaria
combinada → SUBE el Sharpe. En la realidad TODAS las posiciones están expuestas CADA día → la vol diaria
real es mayor → Sharpe menor. Este script mide el Sharpe del libro de DOS formas con los MISMOS pesos:
  A) MOTOR  = combina las series block-resampled por vp (lo que reporta hoy → ~2.07).
  B) HONESTO = marca cada sleeve A DIARIO (mantenido sobre su bloque, e42), combina por vp → Sharpe real.
El gap B−A = el sesgo de la combinación de series dispersas. NO toca producción. python -m research.e56_sharpe_reconcile
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import (load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel,
                           _weights_from_score, CARRY_SMOOTH, DRIVER, BETA_W)
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor
from research.e42_hourly_backtester import hourly_mtm


def daily_from_hourly_mtm(C, beta, score, hold):
    """Retornos DIARIOS reales de un sleeve xs mantenido sobre su bloque (e42: buy-and-hold MTM horario)."""
    eqh, _ = hourly_mtm(C, beta, score, hold)
    return eqh.resample("1D").last().ffill().pct_change().dropna()


def carry_daily_marked(C, ret, beta):
    """Carry marcado A DIARIO: mantiene los pesos del bloque (48h) y marca el retorno de precio cada día +
    funding diario. Mirror de engine.carry_sleeve pero sin resamplear a saltos."""
    syms = [s for s in C.columns if s != DRIVER]
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns: continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True); fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    Fs = F.rolling(CARRY_SMOOTH, min_periods=1).mean()
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    bet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)
    Cd = C.resample("1D").last(); Rd = Cd.pct_change()           # precios diarios
    idx = range(91, len(F) - 6, 6); prev = pd.Series(0.0, index=syms); ph = 0.0
    rows = {}
    for t in idx:
        w, h = alphas.carry_weights(Fs[syms].iloc[t], bet.iloc[t], config.MAX_WEIGHT_NORMAL)
        w = w.reindex(syms).fillna(0.0)
        t0, t1 = F.index[t], F.index[min(t + 6, len(F) - 1)]      # ventana 48h del bloque
        days = Rd.index[(Rd.index > t0) & (Rd.index <= t1)]
        fund_day = -float((w * F[syms].iloc[t + 1:t + 7].sum()).sum()) / max(len(days), 1)
        turn = float((w - prev).abs().sum()) + abs(h - ph); prev, ph = w, h
        for di, day in enumerate(days):
            px = float((w * Rd[syms].loc[day]).sum()) + h * float(Rd[DRIVER].loc[day])
            c = turn * config.MAKER_FEE if di == 0 else 0.0       # coste al entrar al bloque
            rows[day] = rows.get(day, 0.0) + px + fund_day - c
    return pd.Series(rows).sort_index()


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E56 — reconciliación del Sharpe: ¿el 2.07 está inflado por combinar series dispersas?\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    panels = load_panel(["volume", "taker_buy_volume"], C)
    xs = {
        "mom_30d": (alphas.xs_momentum_score(ret, 720), 720),
        "rev_60d": (alphas.xs_reversal_score(ret, 1440), 1440),
        "lowvol_14d": (alphas.xs_lowvol_score(ret, 336), 336),
        "takerflow_5d": (alphas.xs_takerflow_score(panels["volume"], panels["taker_buy_volume"], 120), 120),
        "hlpos_14d": (alphas.xs_hlposition_score(C, 336), 336),
    }
    # series MOTOR (block-resampled) y HONESTA (diaria) por sleeve
    eng, hon = {}, {}
    print(f"  {'sleeve':12s} {'Sh MOTOR':>9s} {'Sh DIARIO':>10s} {'Δ':>6s}  (por-sleeve: deberían ≈, e42)")
    for name, (score, hold) in xs.items():
        eng[name], _ = xs_sleeve(C, ret, beta, score, hold)
        hon[name] = daily_from_hourly_mtm(C, beta, score, hold)
        print(f"  {name:12s} {metrics(eng[name])['sharpe']:9.2f} {metrics(hon[name])['sharpe']:10.2f} "
              f"{metrics(hon[name])['sharpe']-metrics(eng[name])['sharpe']:+6.2f}")
    eng["carry"], _ = carry_sleeve(C, ret, beta); hon["carry"] = carry_daily_marked(C, ret, beta)
    eng["trend"], _ = trend_sleeve(C); hon["trend"] = eng["trend"]          # trend YA es diario real
    print(f"  {'carry':12s} {metrics(eng['carry'])['sharpe']:9.2f} {metrics(hon['carry'])['sharpe']:10.2f} "
          f"{metrics(hon['carry'])['sharpe']-metrics(eng['carry'])['sharpe']:+6.2f}")
    print(f"  {'trend':12s} {metrics(eng['trend'])['sharpe']:9.2f} {metrics(hon['trend'])['sharpe']:10.2f}    0.00  (ya diario)")

    # combinar por vol-parity (misma vp para ambos, calculada sobre las series MOTOR como en producción)
    dfe = pd.concat(eng, axis=1).dropna(); vp = vol_parity_weights(dfe)
    dfh = pd.concat(hon, axis=1).dropna()
    combo_e = (dfe * vp).sum(axis=1)
    combo_h = (dfh * vp.reindex(dfh.columns)).sum(axis=1)
    me, mh = metrics(combo_e), metrics(combo_h)
    # correlación media entre sleeves en cada representación (la clave del sesgo)
    corr_e = dfe.corr().where(~np.eye(len(dfe.columns), dtype=bool)).stack().mean()
    corr_h = dfh.corr().where(~np.eye(len(dfh.columns), dtype=bool)).stack().mean()

    print(f"\n{'COMBINADO 7 sleeves (1x)':28s} {'Sharpe':>7s} {'maxDD':>7s} {'vol_an%':>8s} {'corr_media':>11s}")
    print(f"  {'A) MOTOR (block-resampled)':28s} {me['sharpe']:7.2f} {me['maxdd']:7.1f} {me['vol']:8.1f} {corr_e:11.3f}")
    print(f"  {'B) HONESTO (marcado diario)':28s} {mh['sharpe']:7.2f} {mh['maxdd']:7.1f} {mh['vol']:8.1f} {corr_h:11.3f}")
    le = min(leverage_for_maxdd_anchor(combo_e, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    lh = min(leverage_for_maxdd_anchor(combo_h, config.TARGET_MAXDD), config.MAX_STRAT_LEVERAGE)
    print(f"\n  Al ancla maxDD −10%:  MOTOR lev {le:.2f}x → {metrics(combo_e*le)['ann']/12:.2f}%/mes · "
          f"HONESTO lev {lh:.2f}x → {metrics(combo_h*lh)['ann']/12:.2f}%/mes")

    print("\nDIAGNÓSTICO:")
    print(f"  Por-sleeve el Sharpe ≈ (e42 ✔). El gap aparece al COMBINAR: la vol diaria real es mayor")
    print(f"  ({me['vol']:.0f}%→{mh['vol']:.0f}%) y la corr media sube ({corr_e:.2f}→{corr_h:.2f}) porque marcar a")
    print(f"  diario expone la covarianza que el block-resampling escondía (saltos en días distintos).")
    if mh["sharpe"] < me["sharpe"] - 0.3:
        print(f"  ⇒ el {me['sharpe']:.2f} del MOTOR está INFLADO por la combinación de series dispersas.")
        print(f"     Número HONESTO (marcado diario, mantenido sobre bloque) ≈ {mh['sharpe']:.2f}.")
        print(f"     (e15 daba ~1.3 pero SOBRE-rebalanceaba; esto mantiene sobre el bloque = más fiel.)")
    else:
        print(f"  ⇒ el {me['sharpe']:.2f} NO está significativamente inflado; el gap de e15 era el sobre-rebalanceo.")
    print("  El número REAL lo dará la DEMO (E1). Implicación: revisar si reportamos Sharpe sobre la serie")
    print("  diaria-marcada (honesto) en vez de la block-resampled. NO cambia el edge ni el ranking de sleeves.")


if __name__ == "__main__":
    main()
