"""
E21 — C3: CALIBRAR SLIPPAGE CON FILLS REALES DE LA DEMO (ROADMAP §C3). 2026-05-31.
C1 (e18) asumió un modelo de slippage por ADV (K50, BTC 0.5bps→LIT 13bps). C3 reemplaza ESE SUPUESTO
por la MEDICIÓN real: el orquestador ya registra por fill `ref_px` (book_mid de referencia) y
`slip_bps` (VWAP de los fills reales de Binance vs la referencia, con signo adverso).

Este script lee la DB (trades con reason='rebalance_fill') y reporta el slippage realizado por símbolo
y agregado, comparándolo con lo que el modelo K50 de e18 asumía. Con eso se recalibra C1 con datos.

⚠️ GATED POR DATOS: necesita la DB de la VM (`/opt/kepler-app/kepler.db`) y VARIOS DÍAS de fills.
Hoy sólo hay ~1 ciclo → no concluyente. Correr cuando se acumulen días.

python -m research.e21_fill_slippage  [ruta_db_opcional]
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.db import DB


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    path = sys.argv[1] if len(sys.argv) > 1 else config.DB_PATH
    print("E21 — C3: slippage realizado de fills reales\n" + "="*60)
    print(f"DB: {path}\n")
    db = DB(path=path)
    q = ("SELECT symbol, direction, qty, entry_px, ref_px, slip_bps, open_ts "
         "FROM trades WHERE reason='rebalance_fill' ORDER BY open_ts")
    rows = [dict(zip([c[0] for c in cur.description], r))
            for cur in [db.conn.execute(q)] for r in cur.fetchall()]
    if not rows:
        print("Sin fills registrados todavía. Tras desplegar y dejar correr la demo unos días,\n"
              "traer la DB de la VM y volver a correr. (El logging de slip_bps ya está activo.)")
        return
    df = pd.DataFrame(rows)
    have = df["slip_bps"].notna().sum()
    print(f"Fills: {len(df)} · con slip_bps medido: {have} · "
          f"días: {pd.to_datetime(df['open_ts'], unit='ms').dt.date.nunique()}")
    if have == 0:
        print("\nAún no hay slip_bps medido (fills previos a la mejora de captura, o DRY_RUN).\n"
              "Necesita ciclos nuevos en DEMO con la captura activa.")
        return
    s = df.dropna(subset=["slip_bps"])
    print(f"\nSLIPPAGE REALIZADO (bps, + = adverso): media {s['slip_bps'].mean():.2f} · "
          f"mediana {s['slip_bps'].median():.2f} · p90 {s['slip_bps'].quantile(.9):.2f}")
    print("\nPor símbolo (n, slip medio bps) vs modelo K50 de e18:")
    adv_K50 = 50.0  # K del modelo e18 (referencia)
    g = s.groupby("symbol")["slip_bps"].agg(["count", "mean", "median"]).sort_values("mean", ascending=False)
    print(g.round(2).to_string())
    print("\nLectura: si el slip real medio << modelo (K50, mediana ~4bps) → el sistema es más barato "
          "de lo asumido (maker funciona). Si >> → recalibrar al alza el costo en e18/engine.")
    print("Acción: ajustar K (o usar el slip medido por símbolo) y re-correr e18 para el número honesto.")


if __name__ == "__main__":
    main()
