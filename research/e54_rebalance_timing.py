"""
E54 — EJECUCIÓN: ¿a qué HORA del día conviene rebalancear? (frontera intradía, ruta "ejecución", 2026-06-02).
NO es alfa: es BAJAR EL COSTE del rebalanceo diario eligiendo la ventana más líquida (sin añadir turnover
ni β). El modelo de coste e18 es slip ~ K/√ADV; el análogo intradía: el slip al ejecutar en la hora h
depende del VOLUMEN de esa hora, no del diario. Si una ventana es 2× más líquida → slip ~1/√2 ≈ −29%.

Mide, por hora-del-día (UTC) y por día-de-semana, el perfil de liquidez (quote_volume USD y nº trades)
del universo actual, identifica la ventana más barata, y estima el ahorro de slippage si fijamos el
rebalanceo ahí (hoy el orquestador rebalancea a la hora que cae el loop = a la deriva). Datos: 1h klines.

No toca producción. python -m research.e54_rebalance_timing
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402


def load_hourly():
    """quote_volume y count por hora para el universo actual. Devuelve dos DataFrames (hora index, coins col)."""
    qv, cnt = {}, {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in config.UNIVERSE:
            continue
        d = pd.read_parquet(p, columns=["open_time", "quote_volume", "count"]).set_index("open_time")
        d.index = pd.to_datetime(d.index, unit="ms", utc=True)
        qv[s] = d["quote_volume"]; cnt[s] = d["count"]
    return pd.DataFrame(qv).sort_index(), pd.DataFrame(cnt).sort_index()


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E54 — timing del rebalanceo: ¿qué hora UTC es la más barata para ejecutar?\n")
    QV, CNT = load_hourly()
    QV = QV.dropna(how="all");
    print(f"Universo {QV.shape[1]} coins · {QV.shape[0]} barras 1h ({QV.index[0].date()} → {QV.index[-1].date()})\n")

    hod = QV.index.hour
    # perfil por coin: volumen medio por hora, normalizado a su media diaria (quita el tamaño del coin)
    prof = QV.groupby(hod).mean()                      # hora × coin (volumen medio USD)
    prof_norm = prof / prof.mean(axis=0)               # relativo a la media de cada coin (1.0 = hora media)
    agg = prof_norm.mean(axis=1)                        # perfil del universo (media cross-coin, robusto)
    # slip relativo por hora ~ 1/√(liquidez relativa); normalizado a 1.0 en la hora MEDIA del día
    slip_rel = (1.0 / np.sqrt(agg)); slip_rel = slip_rel / slip_rel.mean()

    print("PERFIL DE LIQUIDEZ por hora UTC (universo; liq_rel 1.0 = hora media · slip_rel <1 = más barato):")
    print(f"  {'hUTC':>4s} {'hLima':>5s} {'liq_rel':>8s} {'slip_rel':>9s} {'trades_rel':>11s}")
    cnt_prof = CNT.groupby(hod).mean(); cnt_norm = (cnt_prof / cnt_prof.mean(axis=0)).mean(axis=1)
    for h in range(24):
        lima = (h - 5) % 24
        bar = "█" * int(round(agg[h] * 20))
        print(f"  {h:>4d} {lima:>4d}h {agg[h]:>8.2f} {slip_rel[h]:>9.3f} {cnt_norm[h]:>11.2f}  {bar}")

    # mejor ventana contigua de 1h, 2h, 3h (mayor liquidez media = menor slip)
    print("\nVENTANAS más baratas (mayor liquidez media):")
    for W in [1, 2, 3]:
        best_h, best_liq = None, -1
        for h0 in range(24):
            hs = [(h0 + k) % 24 for k in range(W)]
            liq = agg.reindex(hs).mean()
            if liq > best_liq:
                best_liq, best_h = liq, hs
        sr = slip_rel.reindex(best_h).mean()
        lima = [(h - 5) % 24 for h in best_h]
        print(f"  {W}h: UTC {best_h} (Lima {lima}) · liq_rel {best_liq:.2f} · slip_rel {sr:.3f}")

    # peor ventana (referencia) y deriva actual (hora cualquiera = la media)
    worst_h = int(agg.idxmin()); best1 = int(agg.idxmax())
    sr_best = float(slip_rel[best1]); sr_worst = float(slip_rel[worst_h]); sr_avg = 1.0
    print(f"\nMejor hora UTC {best1} (Lima {(best1-5)%24}h): slip_rel {sr_best:.3f} · "
          f"Peor UTC {worst_h} (Lima {(worst_h-5)%24}h): slip_rel {sr_worst:.3f}")
    print(f"AHORRO vs rebalancear a la hora MEDIA (deriva actual): {(1-sr_best/sr_avg)*100:+.1f}% del slippage")
    print(f"AHORRO vs caer en la PEOR hora:                        {(1-sr_best/sr_worst)*100:+.1f}% del slippage")

    # traducción a %/mes: el slippage realista del sistema ~0.6%/mes (e18 ADV central, diferencia
    # flat→realista). Un −X% del slippage = +X%·0.6 %/mes recuperado (orden de magnitud).
    slip_drag_mes = 0.60
    ahorro_avg = (1 - sr_best/sr_avg) * slip_drag_mes
    print(f"\nESTIMACIÓN gruesa: si el drag de slippage ≈ {slip_drag_mes:.2f}%/mes (e18), fijar el rebalanceo")
    print(f"en la mejor hora recupera ~{ahorro_avg:.2f}%/mes vs la deriva actual ({ahorro_avg/slip_drag_mes*100:.0f}% del drag).")

    # día de semana (¿el fin de semana es más fino? el rebal diario no lo evita, pero conviene saberlo)
    dow = QV.index.dayofweek
    dprof = (QV.groupby(dow).mean() / QV.mean(axis=0)).mean(axis=1)
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    print("\nLIQUIDEZ por día de semana (1.0 = media):  " +
          " · ".join(f"{dias[d]} {dprof[d]:.2f}" for d in range(7)))

    print("\nLECTURA: si hay una ventana claramente más líquida (slip_rel < ~0.9), fijar el rebalanceo ahí")
    print("baja el coste real del sistema sin añadir turnover ni β. Implementación = pinear la hora UTC del")
    print("rebalanceo en el orquestador (hoy va a la deriva). Validar con el slip real de DEMO (e21/C3).")


if __name__ == "__main__":
    main()
