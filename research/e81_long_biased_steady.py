"""
E81 — ¿Existe un variante "VERDE-CONSTANTE SEGURO" vendible como copy-lead? (Oscar, 2026-06-22)

CONTEXTO (decisión de producto): el market-neutral entrega un perfil PLANO con dientes — invendible
en cripto, donde el copiador quiere ganar cuando el mercado sube. Demo (full-20) y real (low-barrier)
dieron negativo en vivo. Oscar pide REFORMULAR hacia el perfil que él mismo copia: ~$1/día sobre $800,
verde casi cada día, maxDD bajo, retorno modesto OK. La métrica que manda aquí NO es el Sharpe ni el
retorno: es **% de DÍAS VERDES** (lo que el copiador ve) con **maxDD acotado** (seguridad).

PREGUNTA (regla de oro — backtest antes de tocar nada): ¿alguna construcción long-biased mejora el
% de días verdes SIN reventar el maxDD? Compara las DOS fuentes de beta que Oscar pidió:
  · Construcción A — DEJAR DE PELEAR LA BETA: dial θ que mezcla el libro neutral con su versión
    natural (net-long heredado del trend), sin _beta_neutralize. θ=0 neutral (baseline) → θ=1 natural.
  · Construcción B — BASE LARGA + OVERLAY: dial φ que mezcla el libro neutral con una cesta
    equal-weight LARGA de los 13 coins baratos. φ=0 neutral → φ=1 cesta 100% larga.

Cada construcción: leverage anclado a maxDD −10% (igual que producción), WALK-FORWARD
(train 365 · embargo 14 · test 90, ancla SOLO en train), costes reales (maker + slippage por liquidez).
Referencias: idle (plano) y el libro neutral de producción (baseline). Histórico 2022-2026 (incluye
el bear de 2022 → stress de crash honesto: un libro largo se destroza ahí y el ancla lo castiga).

NO toca producción. python -m research.e81_long_biased_steady
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import lowbarrier
from kepler.engine import load, load_panel, DRIVER
from kepler.portfolio import metrics
from research.e72_dollar_neutralization_wf import folds
from research.e76_position_count_frontier import beta_to_btc

H   = config.LEVERAGE_HAIRCUT      # 0.95
T   = config.TARGET_MAXDD          # 0.10
CAP = config.MAX_STRAT_LEVERAGE    # 4.0


def _maxdd(r):
    eq = (1 + r).cumprod()
    return float(abs((eq / eq.cummax() - 1).min()))


def gnorm(W):
    """Gross-normaliza cada fila a 1 (para mezclar libros en la misma escala; el ancla pone la escala real)."""
    g = W.abs().sum(axis=1).replace(0, np.nan)
    return W.div(g, axis=0).fillna(0.0)


def book_ret(W, rd, cost, L):
    """Retorno diario del libro W escalado por leverage L (escalar). Mismo accounting que producción."""
    BL = W * L
    held = BL.shift(1).reindex(rd.index).fillna(0.0)
    turn = (BL - BL.shift(1)).abs().reindex(rd.index).fillna(0.0)
    c = (turn * cost.reindex(W.columns).fillna(cost.median())).sum(axis=1)
    return ((held * rd).sum(axis=1) - c).dropna()


def anchor_lev(W, rd, cost):
    """Leverage estático tal que maxDD del libro = −T (bisección). Sin haircut (se aplica al usarlo)."""
    def dd(s):
        return _maxdd(book_ret(W, rd, cost, s))
    lo, hi = 0.05, CAP
    if dd(hi) < T:
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        if dd(mid) > T:
            hi = mid
        else:
            lo = mid
    return lo


def green_stats(r):
    """Métricas de CONSISTENCIA (lo que el copiador siente). green% es invariante al leverage (signo)."""
    r = r.dropna()
    if len(r) < 30:
        return {}
    green = (r > 0).mean() * 100
    # racha roja más larga (días consecutivos < 0)
    neg = (r < 0).astype(int).values
    streak = mx = 0
    for x in neg:
        streak = streak + 1 if x else 0
        mx = max(mx, streak)
    downside = r[r < 0].std()
    sortino = r.mean() / downside * np.sqrt(365) if downside > 0 else 0.0
    # % de ventanas rodantes de 30d positivas (¿"verde" a horizonte de un mes?)
    roll30 = (1 + r).rolling(30).apply(np.prod, raw=True) - 1
    pos30 = (roll30.dropna() > 0).mean() * 100
    return dict(green=green, red_streak=mx, sortino=sortino, pos30=pos30)


def describe(r, rd_btc, label, lev=None, extra=""):
    m = metrics(r); g = green_stats(r); b = beta_to_btc(r, rd_btc)
    lv = f"lev {lev:4.2f} │ " if lev is not None else ""
    print(f"{label:18s}│ {lv}DÍAS+ {g.get('green',0):4.1f}%  racha-roja {g.get('red_streak',0):2.0f}d  "
          f"30d+ {g.get('pos30',0):4.0f}%  Sortino {g.get('sortino',0):4.2f} ║ "
          f"%/mes {m.get('ann',0)/12:+5.2f}  maxDD {m.get('maxdd',0):6.1f}  Sh {m.get('sharpe',0):4.2f}  "
          f"β {b:+.2f} {extra}")
    return dict(label=label, green=g.get('green',0), red_streak=g.get('red_streak',0),
                pos30=g.get('pos30',0), sortino=g.get('sortino',0), mes=m.get('ann',0)/12,
                maxdd=m.get('maxdd',0), sharpe=m.get('sharpe',0), beta=b, lev=lev or 0.0)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E81 — ¿variante VERDE-CONSTANTE SEGURO? · objetivo: max %días-verdes con maxDD acotado\n")

    config.LOW_BARRIER_NET_LAMBDA = 0.25  # baseline = libro de producción vivo
    C = load(); panels = load_panel(["volume", "taker_buy_volume", "quote_volume"], C)
    Wlb, _, _, _, beta, _, rd = lowbarrier.low_barrier_book(C, panels)
    keep = [s for s in config.LOW_BARRIER_UNIVERSE if s in C.columns]
    beta_daily = beta.resample("1D").last().reindex(Wlb.index).ffill().fillna(0.0)

    # libro NATURAL (cheap universe, SIN β-neutralize ni net-neutralize): net-long heredado del trend
    Wc, _, _, _, _ = lowbarrier.build_combined_book(C, panels)
    didx = Wlb.index
    Wnat = gnorm(lowbarrier._renorm_gross(Wc, keep).reindex(didx).fillna(0.0))
    Bn = gnorm(Wlb)                                   # neutral, gross-1 (baseline de producción)
    # cesta LARGA equal-weight de los 13 baratos (gross 1, net +1)
    LongCore = pd.DataFrame(0.0, index=didx, columns=Wlb.columns)
    LongCore[keep] = 1.0 / len(keep)

    adv = panels["quote_volume"].resample("1D").sum().mean()
    adv_M = (adv.reindex(C.columns).fillna(1.0) / 1e6).clip(lower=1.0)
    cost = pd.Series(config.MAKER_FEE, index=C.columns) + lowbarrier._slip(adv_M, list(C.columns))
    rd_btc = rd[DRIVER]

    # diagnóstico de net/β por construcción
    print(f"Histórico {didx[0].date()} → {didx[-1].date()} · {len(didx)}d · 13 coins baratos · costes reales")
    print(f"net/gross diario:  neutral {Bn.sum(axis=1).median():+.3f} · natural {Wnat.sum(axis=1).median():+.3f}"
          f" · cesta-larga +1.000\n")

    THETAS = [0.0, 0.25, 0.50, 0.75, 1.0]    # A: neutral→natural
    PHIS   = [0.0, 0.20, 0.35, 0.50, 0.75, 1.0]  # B: neutral→cesta larga
    books = {}
    for th in THETAS:
        books[f"A θ={th:.2f}"] = gnorm((1 - th) * Bn + th * Wnat)
    for ph in PHIS:
        books[f"B φ={ph:.2f}"] = gnorm((1 - ph) * Bn + ph * LongCore)

    # ════ WALK-FORWARD (el veredicto) ════
    fl = folds(didx)
    print(f"══ WALK-FORWARD · {len(fl)} folds OOS · lev anclado a maxDD −{T*100:.0f}% SOLO en train (×haircut {H}) ══")
    print("   [DÍAS+ y racha-roja = lo que el copiador SIENTE; maxDD = seguridad; %/mes = lo que gana]\n")
    rows = []
    # baseline neutral (= A θ=0 = B φ=0)
    order = [f"A θ={th:.2f}" for th in THETAS] + [f"B φ={ph:.2f}" for ph in PHIS[1:]]
    lev_full = {}
    for name in order:
        W = books[name]
        oos = []; levs = []
        for tr, te in fl:
            lv = min(anchor_lev(W.loc[tr], rd.loc[tr], cost) * H, CAP)
            oos.append(book_ret(W.loc[te], rd.loc[te], cost, lv)); levs.append(lv)
        r = pd.concat(oos).sort_index()
        rows.append(describe(r, rd_btc, name, lev=float(np.mean(levs))))
        lev_full[name] = float(np.mean(levs))

    # ════ STRESS DE CRASH (full-sample, lev anclado full) — ¿aguanta el bear de 2022? ════
    print("\n══ STRESS DE CRASH · full-sample 2022-2026 (incluye bear 2022) · peor ventana 60d ══")
    for name in order:
        W = books[name]
        lv = min(anchor_lev(W, rd, cost) * H, CAP)
        r = book_ret(W, rd, cost, lv)
        roll60 = ((1 + r).rolling(60).apply(np.prod, raw=True) - 1).min() * 100
        # retorno en 2022 (año bear) aislado
        r22 = r[r.index.year == 2022]
        eq22 = (1 + r22).prod() - 1 if len(r22) else float("nan")
        print(f"{name:18s}│ lev {lv:4.2f}  maxDD-full {_maxdd(r)*100:6.1f}%  peor-60d {roll60:6.1f}%  "
              f"2022 {eq22*100:+6.1f}%")

    # ════ REFERENCIAS ════
    print("\n══ REFERENCIAS ══")
    print(f"{'idle (cash)':18s}│ DÍAS+   0% (plano)  maxDD 0%  %/mes +0.00   (un treasury ~+0.35%/mes)")
    print(f"{'benchmark Oscar':18s}│ ~$1/día sobre $800 ≈ +0.125%/día ≈ +3.75%/mes · cobra solo en máximos (HWM)")

    # ════ RESUMEN ORDENADO POR DÍAS-VERDES ════
    print("\n══ RANKING por DÍAS-VERDES (filtrado a maxDD-OOS ≤ 12%, el presupuesto de seguridad) ══")
    safe = [x for x in rows if abs(x["maxdd"]) <= 12.0]
    for x in sorted(safe, key=lambda z: -z["green"]):
        print(f"  {x['label']:14s}  DÍAS+ {x['green']:4.1f}%  maxDD {x['maxdd']:6.1f}  %/mes {x['mes']:+5.2f}  "
              f"Sortino {x['sortino']:4.2f}  β {x['beta']:+.2f}  lev {x['lev']:.2f}")
    risky = [x for x in rows if abs(x["maxdd"]) > 12.0]
    if risky:
        print("  — descartados por maxDD-OOS > 12% (no 'seguros'):")
        for x in sorted(risky, key=lambda z: z["maxdd"]):
            print(f"  {x['label']:14s}  DÍAS+ {x['green']:4.1f}%  maxDD {x['maxdd']:6.1f}  %/mes {x['mes']:+5.2f}  β {x['beta']:+.2f}")


if __name__ == "__main__":
    main()
