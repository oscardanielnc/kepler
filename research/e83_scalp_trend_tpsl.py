"""
E83 — TEST HONESTO del scalp "estilo John" (idea de Oscar, 2026-06-22): identificar monedas EN TENDENCIA,
entrar a favor (long si sube / short si baja), tomar un TP chico y salir; STOP-LOSS obligatorio (John SÍ
corta). Pregunta decisiva (regla de oro): ¿la ESPERANZA POR OPERACIÓN, después de costos reales, es
POSITIVA — y bate a entradas de dirección ALEATORIA con el mismo TP/SL? (si no, el "+$1" solo reordena la
distribución y paga más costos; el edge tendría que venir de la entrada, no de la salida).

DISEÑO honesto:
  · Datos: OHLC HORARIO 2022-2026 (incluye bear 2022), universo low-barrier (13 coins baratos del producto).
  · Entrada: "en tendencia" = |retorno de las últimas L horas| > umbral → dirección = signo. Entra al OPEN
    de la vela SIGUIENTE (sin lookahead). Lateral (bajo umbral) = no opera (versión limpia).
  · Salida: TP (toca tp%) | SL (toca sl%) | time-stop (max_hold h). INTRABAR PESIMISTA: si una vela toca
    TP y SL a la vez, se asume SL primero (conservador).
  · Costos: taker ambos lados + slippage (un scalp agresivo NO llena con maker GTX). Round-trip ~12 bps.
  · Benchmark NULO: mismas señales/tiempos pero DIRECCIÓN ALEATORIA → aísla si la tendencia aporta algo.
  · Reporta: esperanza neta/op (bps, EL número), win%, payoff, ops/día, suma anual por coin, y por AÑO
    (sobre todo 2022), vs aleatorio. Si esperanza ≤ 0 o ≈ aleatorio → muerto, da igual el sizing.

No toca producción. python -m research.e83_scalp_trend_tpsl
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler.engine import load, load_panel

TAKER = 0.0004          # fee taker Binance futures (4 bps/lado) — el scalp cruza el spread
SLIP  = 0.0002          # slippage por lado (2 bps) en perps líquidos
COST  = TAKER + SLIP    # 6 bps/lado → 12 bps round-trip
RNG   = np.random.default_rng(0)


def simulate(close, high, low, opn, year, L, thr, tp, sl, max_hold, random_dir=False):
    """State machine por coin. Devuelve (net_rets, gross_rets, hold, years, dirs) por operación."""
    N = len(close)
    ret = np.full(N, 0.0)
    ret[L:] = close[L:] / close[:-L] - 1.0
    nets, grosses, holds, yrs = [], [], [], []
    i = L + 1
    while i < N - 1:
        s = 0
        if abs(ret[i]) > thr:
            s = 1 if ret[i] > 0 else -1
        if s == 0:
            i += 1; continue
        if random_dir:
            s = 1 if RNG.random() < 0.5 else -1
        ei = i + 1
        ep = opn[ei]
        if not np.isfinite(ep) or ep <= 0:
            i += 1; continue
        tp_p = ep * (1 + s * tp)
        sl_p = ep * (1 - s * sl)
        end = min(ei + max_hold, N - 1)
        exit_p = None; j = ei
        while j <= end:
            if s == 1:
                if low[j] <= sl_p: exit_p = sl_p; break       # SL primero (pesimista)
                if high[j] >= tp_p: exit_p = tp_p; break
            else:
                if high[j] >= sl_p: exit_p = sl_p; break       # short: SL arriba
                if low[j] <= tp_p: exit_p = tp_p; break
            j += 1
        if exit_p is None:
            j = end; exit_p = close[j]                          # time-stop al close
        gross = s * (exit_p / ep - 1.0)
        nets.append(gross - 2 * COST); grosses.append(gross); holds.append(j - ei); yrs.append(year[ei])
        i = j + 1
    return np.array(nets), np.array(grosses), np.array(holds), np.array(yrs)


def run_combo(panels_arr, years_arr, L, thr, tp, sl, max_hold):
    allnet = []; allgross = []; allhold = []; allyr = []; rndnet = []
    for sym, (cl, hi, lo, op) in panels_arr.items():
        yr = years_arr[sym]
        n, g, h, y = simulate(cl, hi, lo, op, yr, L, thr, tp, sl, max_hold)
        rn, _, _, _ = simulate(cl, hi, lo, op, yr, L, thr, tp, sl, max_hold, random_dir=True)
        allnet.append(n); allgross.append(g); allhold.append(h); allyr.append(y); rndnet.append(rn)
    net = np.concatenate(allnet); gross = np.concatenate(allgross)
    hold = np.concatenate(allhold); yr = np.concatenate(allyr); rnd = np.concatenate(rndnet)
    return net, gross, hold, yr, rnd


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    C = load()
    H = load_panel(["high"], C)["high"]; Lo = load_panel(["low"], C)["low"]; Op = load_panel(["open"], C)["open"]
    keep = [s for s in config.LOW_BARRIER_UNIVERSE if s in C.columns]
    span_days = (C.index[-1] - C.index[0]).days
    panels_arr = {s: (C[s].values, H[s].values, Lo[s].values, Op[s].values) for s in keep}
    years_arr = {s: C.index.year.values for s in keep}

    print("E83 — scalp tendencia + TP/SL · OHLC horario %s→%s · %d coins · costo RT %.0f bps\n"
          % (C.index[0].date(), C.index[-1].date(), len(keep), 2 * COST * 1e4))
    print("L=lookback h · thr=umbral tendencia · tp/sl/maxhold · esperanza NETA por op (EL número)\n")
    hdr = ("L  thr%  tp%  sl%  hold │ ops   ops/d  win%  payoff │ NETA/op(bps)  vs-ALEAT  │ Σneta/coin/año")
    print(hdr); print("-" * len(hdr))

    grid = [
        (12, 0.010, 0.005, 0.010, 24),
        (12, 0.010, 0.010, 0.015, 24),
        (12, 0.010, 0.010, 0.020, 48),
        (24, 0.015, 0.010, 0.020, 48),
        (24, 0.015, 0.020, 0.030, 48),
        (24, 0.020, 0.020, 0.030, 72),
        (6,  0.005, 0.005, 0.010, 12),
    ]
    results = []
    for (L, thr, tp, sl, mh) in grid:
        net, gross, hold, yr, rnd = run_combo(panels_arr, years_arr, L, thr, tp, sl, mh)
        if len(net) == 0:
            continue
        opsd = len(net) / span_days
        win = (net > 0).mean() * 100
        avgw = net[net > 0].mean() if (net > 0).any() else 0
        avgl = net[net < 0].mean() if (net < 0).any() else 0
        payoff = abs(avgw / avgl) if avgl != 0 else 0
        exp_bps = net.mean() * 1e4
        rnd_bps = rnd.mean() * 1e4
        # suma anual por coin: total net / n_coins / n_years
        n_years = max(span_days / 365.0, 1e-9)
        sum_coin_yr = net.sum() / len(panels_arr) / n_years * 100
        print("%-2d %4.1f %4.1f %4.1f %4d │ %5d %5.1f %5.1f %6.2f │ %+8.2f   %+7.2f  │ %+7.1f%%"
              % (L, thr*100, tp*100, sl*100, mh, len(net), opsd, win, payoff, exp_bps, rnd_bps, sum_coin_yr))
        results.append((L, thr, tp, sl, mh, net, yr, exp_bps, rnd_bps))

    # desglose por AÑO del mejor por esperanza neta
    best = max(results, key=lambda r: r[7]) if results else None
    if best:
        L, thr, tp, sl, mh, net, yr, eb, rb = best
        print("\nDESGLOSE POR AÑO del mejor combo (L%d thr%.1f%% tp%.1f%% sl%.1f%% hold%d) — esperanza neta/op (bps):"
              % (L, thr*100, tp*100, sl*100, mh))
        for y in sorted(set(yr.tolist())):
            m = yr == y
            print("   %d: %+6.2f bps/op   (%d ops, win %.0f%%)" % (y, net[m].mean()*1e4, m.sum(), (net[m]>0).mean()*100))

    print("\nVEREDICTO (criterio): el scalp tiene edge SOLO si esperanza NETA/op > 0 Y claramente > ALEATORIO")
    print("Y sobrevive 2022 con esperanza ≥ 0. Si NETA ≈ aleatorio → la tendencia intradía no aporta tras costos.")


if __name__ == "__main__":
    main()
