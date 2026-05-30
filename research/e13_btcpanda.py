"""
E13 — ¿Es viable el estilo de Btc Panda? Mean-reversion ETH 20x, con vs SIN stop de desastre.
Estilo: fadear extremos del rango (z-score), aguantar hasta reversión a la media (su 'win'),
SIN SL → liquidación si el movimiento adverso llega a 1/leverage (5% a 20x).
Variante: stop de desastre a d% adverso (acota la cola antes de la liquidación).

Sobre ETH 1h, 4.4 años (incluye crash 2022 y rallies 2024-25 = rupturas de rango reales).
Demuestra: (a) sin stop revienta cuando el rango rompe; (b) ¿el stop lo salva y queda +EV?

python research/e13_btcpanda.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa

LEV = 20
ZWIN = 72        # 3 días para la banda
ENTRY_Z = 2.0
FEE = config.TAKER_FEE   # entradas a mercado


def load_eth():
    df = pd.read_parquet(os.path.join(config.DATA_DIR, "futures_um", "1h", "ETHUSDT.parquet"),
                         columns=["open_time", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


def backtest(df, disaster_stop=None):
    """disaster_stop=None → estilo Btc Panda (sin SL, solo liquidación a 1/LEV).
    disaster_stop=d (ej 0.025) → SL estructural a d% adverso. Retorna lista de account-returns."""
    c = df["close"].values; h = df["high"].values; l = df["low"].values
    mean = df["close"].rolling(ZWIN).mean().values
    std = df["close"].rolling(ZWIN).std().values
    z = (c - mean) / std
    liq = 1.0 / LEV
    stop = disaster_stop if disaster_stop is not None else liq
    n = len(c); i = ZWIN + 1
    trades = []; events = []
    while i < n - 1:
        if np.isnan(z[i]):
            i += 1; continue
        direction = 0
        if z[i] > ENTRY_Z:
            direction = -1   # short el techo
        elif z[i] < -ENTRY_Z:
            direction = 1    # long el piso
        if direction == 0:
            i += 1; continue
        entry = c[i]
        j = i + 1
        outcome = None; exitp = entry
        while j < n:
            # excursión adversa intrabar (pesimista)
            if direction == 1:   # long: adverso = baja
                adverse = (l[j] - entry) / entry          # negativo
            else:                # short: adverso = sube
                adverse = (entry - h[j]) / entry
            if adverse <= -stop:
                exitp = entry * (1 - stop) if direction == 1 else entry * (1 + stop)
                outcome = "liq" if disaster_stop is None else "stop"
                break
            # reversión a la media (su 'win'): z cruza 0
            if (direction == 1 and z[j] >= 0) or (direction == -1 and z[j] <= 0):
                exitp = c[j]; outcome = "revert"; break
            j += 1
        if outcome is None:   # fin de datos
            exitp = c[-1]; outcome = "eod"; j = n - 1
        price_move = direction * (exitp - entry) / entry
        acc = price_move * LEV - 2 * FEE * LEV           # retorno sobre margen
        trades.append(acc); events.append((df.index[i], outcome, acc))
        i = j + 1
    return np.array(trades), events


def stats(trades, label):
    if len(trades) == 0:
        print(f"  {label}: sin trades"); return
    wr = (trades > 0).mean() * 100
    w = trades[trades > 0]; los = trades[trades <= 0]
    pf = w.sum() / abs(los.sum()) if len(los) and los.sum() != 0 else 9.99
    # equity compuesta (margen completo por trade, como martingala de copia)
    eq = np.cumprod(1 + trades)
    ruined = (eq <= 0.05).any()
    ruin_at = int(np.argmax(eq <= 0.05)) if ruined else -1
    exp = trades.mean()
    print(f"  {label:30s} n={len(trades):4d} WR={wr:5.1f}% exp={exp*100:+6.2f}%/trade PF={pf:.2f} "
          f"peor={trades.min()*100:+6.0f}% | {'RUINA en trade '+str(ruin_at) if ruined else 'sobrevive eq×'+format(eq[-1],'.2f')}")


def main():
    df = load_eth()
    print(f"ETH 1h: {len(df)} velas [{df.index[0].date()}→{df.index[-1].date()}]  "
          f"leverage {LEV}x · banda z{ENTRY_Z} ({ZWIN}h)\n")
    print("=" * 100)
    print("  E13 — ESTILO BTC PANDA: mean-reversion ETH 20x, ¿sobrevive 4.4 años?")
    print("=" * 100)
    tr, ev = backtest(df, disaster_stop=None)
    stats(tr, "SIN stop (estilo Brayan)")
    # liquidaciones
    liqs = [(t.date(), a) for t, o, a in ev if o == "liq"]
    print(f"    → liquidaciones (−100%): {len(liqs)}  fechas: {[str(d) for d,_ in liqs[:8]]}")
    print()
    for d in (0.015, 0.02, 0.03, 0.05):
        tr2, ev2 = backtest(df, disaster_stop=d)
        stats(tr2, f"CON stop desastre {d*100:.1f}%")
    print("=" * 100)


if __name__ == "__main__":
    main()
