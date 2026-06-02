"""
E55 — EJECUCIÓN: ¿vale la pena SLICING pasivo en la ventana 14-16 UTC? (refinamiento de e54, 2026-06-02).
El slicing (partir la orden en tramos a lo largo de la ventana) reduce el IMPACTO de mercado (ley raíz:
coste de impacto ∝ √participación). Pero el beneficio depende de la PARTICIPACIÓN = orden / volumen de la
hora; con maker pasivo y tamaño chico la participación es ~0 → impacto ~0 → slicing no ahorra nada. Crece
con el AUM. Este script cuantifica la participación y el cruce de AUM para decidir IMPLEMENTAR YA vs DIFERIR.

Cantidad robusta (sin calibrar): PARTICIPACIÓN. Regla de oro de microestructura: <~1% hora = inocuo;
~1-5% = impacto modesto; >10% = mueve el mercado. Slicing en 3 reduce la participación pico ~3×.

No toca producción. python -m research.e55_slicing
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

WINDOW = [14, 15, 16]   # ventana líquida UTC (e54)


def hourly_usd(sym):
    """Volumen USD medio por hora-del-día (UTC) de un símbolo."""
    p = glob.glob(os.path.join(config.DATA_DIR, "futures_um", "1h", f"{sym}.parquet"))
    if not p:
        return None
    d = pd.read_parquet(p[0], columns=["open_time", "quote_volume"]).set_index("open_time")
    d.index = pd.to_datetime(d.index, unit="ms", utc=True)
    return d["quote_volume"].groupby(d.index.hour).mean()


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E55 — ¿slicing pasivo en 14-16 UTC? (¿ahora o al escalar AUM?)\n")

    # coins representativos: líquido (BTC), medio (LINK), y el más fino que CONSERVAMOS (ZEC)
    reps = ["BTCUSDT", "LINKUSDT", "ZECUSDT"]
    vol = {s: hourly_usd(s) for s in reps}
    print("Volumen USD/hora en la ventana 14-16 UTC (medio):")
    for s in reps:
        v = vol[s]
        print(f"  {s:10s} 14h ${v[14]/1e6:7.1f}M · 15h ${v[15]/1e6:7.1f}M · 16h ${v[16]/1e6:7.1f}M")
    print()

    # participación = orden / volumen-hora. Orden = peso × AUM. Peso típico 5%, peor caso = cap 0.25.
    # single-shot = toda la orden en la hora pico (14). slice-3 = orden/3 en cada hora de la ventana.
    aums = [5e3, 1e5, 1e6, 5e6, 2e7]
    print("PARTICIPACIÓN (% del volumen de la hora) — single-shot @14UTC vs slice-3 (pico):")
    print("  Regla: <1% inocuo · 1-5% impacto modesto · >10% mueve el mercado. (peso de posición 5%)\n")
    print(f"  {'AUM':>8s} │ " + " │ ".join(f"{s.replace('USDT',''):>16s}" for s in reps))
    print("  " + "─" * 70)
    W = 0.05
    for A in aums:
        cells = []
        for s in reps:
            v = vol[s]
            order = W * A
            p_single = order / v[14] * 100
            # slice-3: orden/3 en cada hora; la participación PICO es en la hora menos líquida de la ventana
            p_slice = (order / 3) / min(v[h] for h in WINDOW) * 100
            cells.append(f"{p_single:6.2f}% → {p_slice:5.2f}%")
        label = f"${A/1e6:.2f}M" if A >= 1e6 else f"${A/1e3:.0f}k"
        print(f"  {label:>8s} │ " + " │ ".join(f"{c:>16s}" for c in cells))

    # peor caso: posición al cap 0.25 (TRX/ZEC pueden acercarse) en el coin más fino conservado (ZEC)
    print("\nPEOR CASO (posición al cap 25% en ZEC, el coin más fino que conservamos):")
    v = vol["ZECUSDT"]
    for A in aums:
        order = 0.25 * A
        p_single = order / v[14] * 100
        p_slice = (order / 3) / min(v[h] for h in WINDOW) * 100
        label = f"${A/1e6:.2f}M" if A >= 1e6 else f"${A/1e3:.0f}k"
        flag = "  ← slicing CRÍTICO" if p_single > 10 else ("  ← slicing ayuda" if p_single > 2 else "  (inocuo)")
        print(f"  {label:>8s}: single {p_single:6.2f}% → slice-3 {p_slice:6.2f}%{flag}")

    # cruce: AUM donde la participación single-shot en ZEC (pos 5%) supera 2% (impacto material)
    order_at = lambda A, w: w * A
    cross = None
    for A in np.logspace(4, 8, 400):
        if order_at(A, 0.05) / v[14] * 100 > 2.0:
            cross = A; break
    print(f"\nCRUCE: con posición 5%, la participación en ZEC supera 2% (impacto material) a partir de "
          f"~${cross/1e6:.1f}M de AUM." if cross else "\nCRUCE: no se alcanza 2% en el rango probado.")

    print("\nVEREDICTO: a tamaño DEMO (~$5k) la participación es ~0.00% → impacto nulo, maker pasivo llena a")
    print("mid → SLICING NO AHORRA NADA HOY. Es una feature de CAPACIDAD: empieza a importar al escalar AUM")
    print("(~$1M+ en coins finos, crítico >$10M). Recomendación: NO implementar slicing ahora (añade")
    print("complejidad de ejecución a cero beneficio); el pineo de hora (e54) ya captura el win gratis.")
    print("REVISAR cuando el AUM crezca (es justo el objetivo copy-lead) → entonces slicing + cap de tamaño")
    print("por liquidez (no solo por peso). Apuntado para el roadmap de capacidad (B4).")


if __name__ == "__main__":
    main()
