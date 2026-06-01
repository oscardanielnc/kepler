"""
E33 — ANALIZADOR de la SOMBRA on-chain TVL (paso a de la decisión sleeve #8). 2026-06-01.
La VM registra cada ciclo (24h) los pesos que el sleeve `onchain_tvl_pxdiv_14d` TENDRÍA, SIN operar
(tabla shadow_signal, kepler/onchain.py). Esto mide su retorno FORWARD point-in-time (la única prueba
válida: el TVL de DefiLlama es reconstruido, pero los pesos logueados en vivo ya no se pueden revisar).

Este script lee shadow_signal + precios de klines (NO revisados) y calcula el retorno REAL del sleeve:
  retorno_día(d) = Σ_i  w_i(d) · (close_i(d_next)/close_i(d) − 1)     (w incluye el hedge BTC)
→ Sharpe / retorno realizado vs el backtest (e26/e27: standalone Sharpe ~0.94, corr 0.11, +0.6%/mes
taker al ancla). Decisión de promoción a sleeve #8 cuando haya muestra suficiente (≥~60-90 días).

USO:  python -m research.e33_shadow_tvl_analyze [ruta_a_kepler.db]
(la sombra corre en la VM → traer su kepler.db. Sin argumento usa la DB local, que puede estar vacía.)
"""
from __future__ import annotations
import os, sys, json, sqlite3
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load
from kepler.portfolio import metrics

SLEEVE = "onchain_tvl_pxdiv_14d"
MIN_DAYS_TENTATIVE = 60     # lectura tentativa
MIN_DAYS_DECISION = 120     # decisión de promoción


def read_shadow(db_path: str) -> pd.DataFrame:
    """Lee shadow_signal del sleeve TVL → DataFrame [day, symbol, weight]. day = día del `asof`."""
    if not os.path.exists(db_path):
        return pd.DataFrame()
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT ts, symbol, weight, score, detail FROM shadow_signal WHERE sleeve=? ORDER BY ts",
            (SLEEVE,)).fetchall()
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()
    recs = []
    for ts, sym, w, sc, detail in rows:
        asof = None
        try:
            asof = json.loads(detail or "{}").get("asof")
        except Exception:
            pass
        day = pd.to_datetime(asof, utc=True).normalize() if asof else \
              pd.to_datetime(ts, unit="ms", utc=True).normalize()
        recs.append((day, sym, float(w)))
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs, columns=["day", "symbol", "weight"])
    # dedup: si hubo varios ciclos el mismo día (reinicios), quedarse con el último snapshot del día
    last_ts = df.groupby("day").size()  # placeholder; ya viene ordenado por ts → tomamos el último set
    return df


def realized_returns(W: pd.DataFrame, closes: pd.DataFrame) -> pd.Series:
    """W = pesos por día (filas=día, cols=símbolo). Retorno realizado de mantener w(d) hasta el
    siguiente día de snapshot. Usa close diario (UTC)."""
    days = list(W.index)
    out = {}
    for k in range(len(days) - 1):
        d, dn = days[k], days[k + 1]
        w = W.loc[d].dropna()
        try:
            p0 = closes.loc[:d].iloc[-1]; p1 = closes.loc[:dn].iloc[-1]
        except Exception:
            continue
        r = (p1 / p0 - 1).reindex(w.index)
        valid = r.notna()
        if valid.sum() == 0:
            continue
        out[dn] = float((w[valid] * r[valid]).sum())
    return pd.Series(out).sort_index()


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    db_path = sys.argv[1] if len(sys.argv) > 1 else config.DB_PATH
    print(f"E33 — Analizador de sombra TVL · DB: {db_path}\n" + "="*64)

    sh = read_shadow(db_path)
    if sh.empty:
        print("No hay filas de shadow_signal para el sleeve TVL en esta DB.")
        print("→ La sombra corre en la VM. Traer su kepler.db y pasarla como argumento:")
        print("   python -m research.e33_shadow_tvl_analyze /ruta/a/kepler.db")
        print("\n(El script está LISTO; solo espera datos. Logging verificado suficiente: pesos+hedge+asof.)")
        return

    # matriz de pesos por día (último snapshot de cada día ya por orden de ts)
    W = sh.pivot_table(index="day", columns="symbol", values="weight", aggfunc="last")
    n_days = W.shape[0]
    syms = [c for c in W.columns]
    print(f"Sombra: {n_days} días de señal · {W.index[0].date()} → {W.index[-1].date()}")
    print(f"Símbolos tocados: {len(syms)} · gross medio {W.abs().sum(axis=1).mean():.2f} · "
          f"hedge BTC medio {W.get('BTCUSDT', pd.Series(0)).mean():+.3f}")

    C = load()
    closes = C.resample("1D").last()
    closes.index = closes.index.normalize()
    r = realized_returns(W, closes)
    r = r.dropna()
    if len(r) < 5:
        print(f"\nSolo {len(r)} retornos computables aún. Esperar más ciclos.")
        return

    m = metrics(r)
    ann = m.get("ann", float("nan"))
    print(f"\nRETORNO REALIZADO de la sombra ({len(r)} días, rebal diario, 1x sleeve):")
    print(f"  acumulado {(np.expm1(np.log1p(r).sum()))*100:+.2f}% · media diaria {r.mean()*1e4:+.1f} bps · "
          f"Sharpe {m.get('sharpe', float('nan')):.2f} · ann {ann:.1f}% (~{ann/12:.2f}%/mes)")
    print(f"  (BACKTEST de referencia e26/e27: standalone Sharpe ~0.94, corr 0.11, +0.6%/mes taker al ancla)")

    print("\nLECTURA:")
    if len(r) < MIN_DAYS_TENTATIVE:
        print(f"  ⏳ INSUFICIENTE para concluir ({len(r)} < {MIN_DAYS_TENTATIVE} días). La sombra sigue")
        print(f"     acumulando. Re-correr periódicamente. No decidir aún (ruido de muestra corta).")
    elif len(r) < MIN_DAYS_DECISION:
        print(f"  🟡 LECTURA TENTATIVA ({len(r)} días): comparar el SIGNO y orden de magnitud del Sharpe")
        print(f"     realizado vs el backtest. Si va alineado y positivo → encaminado; aún no promover.")
    else:
        print(f"  ✅ MUESTRA SUFICIENTE ({len(r)} días) para decidir. Si el Sharpe realizado es positivo y")
        print(f"     consistente con el backtest → promover a sleeve #8 (alphas.py + engine.SLEEVES) tras")
        print(f"     chequear coste taker (e30b-style) y β. Si es plano/negativo → mantener fuera (sombra honesta).")
    print("\n  Próximo: (b) coste taker del sleeve TVL · (c) decisión de promoción (regla de oro).")


if __name__ == "__main__":
    main()
