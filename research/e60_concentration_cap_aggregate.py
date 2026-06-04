"""
E60 — CAP DE CONCENTRACIÓN AGREGADO del libro combinado (Oscar 2026-06-04, tras el crash 06-02/03).

CONTEXTO: el crash dejó claro que el riesgo nº1 del libro es la concentración COMBINADA en pocos
largos de trend (06-04: TRX 15% + NEAR 14.6% + ZEC 11.1% ≈ 41% del gross). El cap por-nombre actual
(`config.MAX_POSITION_EQUITY`, e69) ya capa cada nombre del TARGET VIVO, pero:
  (a) el leverage se ancla sobre el libro SIN capar → el cap solo recorta riesgo, no se "premia" con lev;
  (b) no hay tope a la suma del top-N (la concentración combinada).

PREGUNTA (regla de oro / flywheel de Oscar): ¿un cap por-nombre más ajustado, y/o un tope al top-N
combinado, BAJA el maxDD lo suficiente como para RE-anclar más leverage y dar IGUAL o MÁS retorno al
MISMO presupuesto de maxDD (−10%), reduciendo la concentración? Si ningún esquema mejora el retorno al
mismo maxDD → la concentración es el precio del edge (decisión de Oscar: aceptar riesgo de N nombres).

MÉTODO (honesto, a nivel de NOMBRE, sobre el libro que se TENDRÍA vivo):
  1. Reconstruye el panel DIARIO de pesos de cada sleeve tal como el motor arma el `target` vivo
     (xs/_weights_from_score, carry/carry_weights, trend/cesta capada) y los combina por vol-parity
     → `book_1x` (el libro a 1x, β-hedge incluido vía DRIVER).
  2. RECONCILIA el último día de `book_1x·lev` (capado) contra engine.compute_target → si casan, el
     backtest es fiel (se imprime el desajuste máximo).
  3. Para cada esquema de cap: RE-ANCLA el leverage por bisección para clavar maxDD=−10% sobre el libro
     CAPADO (flywheel), y mide ann/mes, Sharpe, y la concentración resultante (top1/top3/HHI).

No toca producción. python -m research.e60_concentration_cap_aggregate
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas, engine
from kepler.engine import (load, _beta, _weights_from_score, _cap_normalize, xs_sleeve, carry_sleeve,
                           trend_sleeve, load_panel, DRIVER, BETA_W, CARRY_SMOOTH, SLEEVES)
from kepler.portfolio import vol_parity_weights, metrics

TARGET = config.TARGET_MAXDD          # 0.10
HAIRCUT = config.LEVERAGE_HAIRCUT     # 0.95
LEV_CAP = config.MAX_STRAT_LEVERAGE   # 4.0


# ── paneles DIARIOS de pesos por sleeve (réplica fiel de la construcción del target vivo) ────────────
def _to_daily(panel: pd.DataFrame) -> pd.DataFrame:
    """Rebal-rows → mantener entre rebalanceos (ffill) → cierre diario."""
    return panel.ffill().fillna(0.0).resample("1D").last().ffill().fillna(0.0)


def xs_panel(C, ret, beta, score_df, hold):
    syms = [s for s in C.columns if s != DRIVER]
    panel = pd.DataFrame(np.nan, index=C.index, columns=C.columns)
    for t in range(BETA_W + hold, len(C) - hold, hold):
        w, h = _weights_from_score(score_df.iloc[t], beta.iloc[t], syms)
        row = w.reindex(C.columns).fillna(0.0); row[DRIVER] = h
        panel.iloc[t] = row.values
    return _to_daily(panel)


def carry_panel(C, ret):
    """Réplica de engine.carry_sleeve a nivel de panel de pesos (incluye hedge en DRIVER)."""
    import glob
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns:
            continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("8h").sum()
    F = pd.DataFrame(fd).reindex(pd.date_range(C.index[0], C.index[-1], freq="8h", tz="UTC")).fillna(0)
    syms = [s for s in C.columns if s != DRIVER]
    Fs = F.rolling(CARRY_SMOOTH, min_periods=1).mean()
    Cr = C.reindex(F.index, method="ffill"); pr = Cr.pct_change()
    bet = pr[syms].rolling(90).cov(pr[DRIVER]).div(pr[DRIVER].rolling(90).var(), axis=0).clip(-3, 3)
    panel = pd.DataFrame(np.nan, index=F.index, columns=C.columns)
    for t in range(91, len(F) - 6, 6):
        w, h = alphas.carry_weights(Fs[syms].iloc[t], bet.iloc[t], config.MAX_WEIGHT_NORMAL)
        row = w.reindex(C.columns).fillna(0.0); row[DRIVER] = h
        panel.iloc[t] = row.values
    return _to_daily(panel)


def trend_panel(C):
    px = C.resample("1D").last(); ret = px.pct_change()
    ef = px.ewm(span=20).mean(); es = px.ewm(span=100).mean()
    sig = np.sign(ef - es).clip(lower=0)
    vol = ret.rolling(30).std()
    scal = (0.20 / np.sqrt(365) / vol).clip(0, 3)
    pos = (sig.shift(1) * scal).fillna(0)
    W = pos.copy()
    for i in range(len(pos)):
        W.iloc[i] = _cap_normalize(pos.iloc[i].values.astype(float), config.MAX_WEIGHT_NORMAL)
    return W.reindex(columns=C.columns).fillna(0.0)


# ── esquemas de cap sobre el target diario (en unidades de EQUITY, tras ×lev) ────────────────────────
def apply_cap(book_lev: pd.DataFrame, per_name: float | None, topn: int | None, topn_cap: float | None):
    """book_lev: pesos por nombre ×lev (equity). Devuelve el libro tras el/los cap(s).
    per_name: tope |peso| por nombre. topn/topn_cap: tope a la SUMA de los topn |pesos| largos."""
    b = book_lev
    if per_name:
        b = b.clip(-per_name, per_name)
    if topn and topn_cap:
        # si la suma de los topn largos supera topn_cap, escala SOLO esos largos para respetarlo
        b = b.copy()
        longs = b.where(b > 0, 0.0)
        order = longs.rank(axis=1, ascending=False, method="first")
        topmask = order <= topn
        topsum = (longs * topmask).sum(axis=1)
        scale = (topn_cap / topsum).clip(upper=1.0).replace([np.inf, np.nan], 1.0)
        adj = longs * topmask * (1 - scale.values[:, None])     # exceso a quitar de los top largos
        b = b - adj
    return b


def book_returns(book_1x: pd.DataFrame, rd: pd.DataFrame, lev: float, cap_kw: dict):
    bl = apply_cap(book_1x * lev, **cap_kw)
    gross = bl.abs().sum(axis=1)
    pnl = (bl.shift(1) * rd).sum(axis=1)
    turn = (bl - bl.shift(1)).abs().sum(axis=1).fillna(0.0)
    r = (pnl - turn * config.MAKER_FEE).dropna()
    return r, bl, gross


def _maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def anchor_lev(book_1x, rd, cap_kw):
    """Bisección: leverage que clava maxDD=−TARGET sobre el libro CAPADO. Si ni con LEV_CAP se alcanza
    (el cap limita el riesgo) → LEV_CAP. maxDD crece ~monótono con lev hasta saturar el cap."""
    lo, hi = 0.05, LEV_CAP
    if abs(_maxdd(book_returns(book_1x, rd, hi, cap_kw)[0])) < TARGET:
        return hi * HAIRCUT
    for _ in range(50):
        mid = (lo + hi) / 2
        dd = abs(_maxdd(book_returns(book_1x, rd, mid, cap_kw)[0]))
        if dd > TARGET:
            hi = mid
        else:
            lo = mid
    return lo * HAIRCUT


def evaluate(book_1x, rd, label, cap_kw):
    lev = anchor_lev(book_1x, rd, cap_kw)
    r, bl, gross = book_returns(book_1x, rd, lev, cap_kw)
    m = metrics(r)
    last = bl.iloc[-1].abs().sort_values(ascending=False)
    top1 = last.iloc[0]; top3 = last.iloc[:3].sum()
    g = last.sum()
    hhi = float(((last / g) ** 2).sum()) if g > 0 else 0.0
    half = len(r) // 2
    sh1 = metrics(r.iloc[:half]).get("sharpe", float("nan"))
    sh2 = metrics(r.iloc[half:]).get("sharpe", float("nan"))
    print(f"{label:26s} │ lev {lev:4.2f}x │ Sh {m.get('sharpe',0):.2f} (IS {sh1:.2f}/OOS {sh2:.2f}) "
          f"maxDD {m.get('maxdd',0):6.1f} ann {m.get('ann',0):5.1f}% ({m.get('ann',0)/12:4.2f}%/mes) "
          f"mo+ {m.get('mo_pos',0):3.0f}% │ top1 {top1*100:4.1f}% top3 {top3*100:4.1f}% gross {gross.iloc[-1]:.2f} HHI {hhi:.3f}")
    return m, top1, top3


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E60 — cap de concentración AGREGADO (flywheel: re-ancla lev a maxDD −10%, compara retorno a igual riesgo)\n")
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)

    # series por sleeve (autoritativas para vol-parity) + paneles de pesos diarios
    series, panels = {}, {}
    score_map = {
        "mom_30d":    (alphas.xs_momentum_score(ret, 720), 720),
        "rev_60d":    (alphas.xs_reversal_score(ret, 1440), 1440),
        "lowvol_14d": (alphas.xs_lowvol_score(ret, 336), 336),
        "takerflow_5d": (alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120),
        "hlpos_14d":  (alphas.xs_hlposition_score(C, 336), 336),
    }
    for name, typ, hold in SLEEVES:
        if name in score_map:
            sc, h = score_map[name]
            series[name] = xs_sleeve(C, ret, beta, sc, h)[0]
            panels[name] = xs_panel(C, ret, beta, sc, h)
        elif typ == "carry":
            series[name] = carry_sleeve(C, ret, beta)[0]
            panels[name] = carry_panel(C, ret)
        else:
            series[name] = trend_sleeve(C)[0]
            panels[name] = trend_panel(C)

    df = pd.concat(series, axis=1).dropna()
    vp = vol_parity_weights(df)
    print(f"vol-parity: {vp.round(3).to_dict()}\n")

    # libro 1x combinado, diario, alineado
    didx = _to_daily(panels["trend"].reindex(C.index)).index if False else panels["trend"].index
    book_1x = pd.DataFrame(0.0, index=panels["trend"].index, columns=C.columns)
    for name in series:
        p = panels[name].reindex(book_1x.index).ffill().fillna(0.0)
        book_1x = book_1x.add(float(vp[name]) * p, fill_value=0.0)
    rd = C.resample("1D").last().reindex(book_1x.index).pct_change()

    # ── RECONCILIACIÓN con el motor vivo (¿el último día casa con engine.compute_target?) ─────────────
    tgt_eng, _, _, _, _, lev_eng, _, _, _ = engine.compute_target("ESTABLE")
    base_kw = dict(per_name=config.MAX_POSITION_EQUITY, topn=None, topn_cap=None)
    _, bl_recon, _ = book_returns(book_1x, rd, lev_eng, base_kw)
    recon = bl_recon.iloc[-1].reindex(tgt_eng.index).fillna(0.0)
    diff = (recon - tgt_eng).abs()
    print(f"RECONCILIACIÓN último día (lev motor {lev_eng:.2f}x): desajuste máx {diff.max():.4f} "
          f"en {diff.idxmax()} · gross recon {recon.abs().sum():.3f} vs motor {tgt_eng.abs().sum():.3f}")
    print("(desajuste pequeño = la reconstrucción es fiel; difs por convención multi-horizonte de los sleeves)\n")

    print(f"{'esquema de cap':26s} │ {'lev':>4s} │ {'sistema combinado @ maxDD −10% (haircut '+str(HAIRCUT)+')':>52s} │ concentración")
    print("─" * 140)
    # BASELINE = producción (cap por-nombre actual)
    evaluate(book_1x, rd, f"PROD cap/nombre {config.MAX_POSITION_EQUITY:.2f}", base_kw)
    print("· sin cap (referencia):")
    evaluate(book_1x, rd, "sin cap", dict(per_name=None, topn=None, topn_cap=None))
    print("· barrido cap por-nombre:")
    for c in [0.20, 0.13, 0.12, 0.10, 0.08]:
        evaluate(book_1x, rd, f"cap/nombre {c:.2f}", dict(per_name=c, topn=None, topn_cap=None))
    print("· cap por-nombre 0.15 + tope al top-3 largos combinado:")
    for tc in [0.35, 0.30, 0.25]:
        evaluate(book_1x, rd, f"cap 0.15 + top3≤{tc:.2f}", dict(per_name=0.15, topn=3, topn_cap=tc))

    print("\nLECTURA (regla de oro / flywheel): el GANADOR baja top1/top3/HHI manteniendo o SUBIENDO el")
    print("ann%/mes a maxDD −10%, con IS≈OOS (no rompe el edge en ninguna mitad). Si ninguno mejora el")
    print("retorno a igual maxDD → la concentración es el precio del edge; decisión de Oscar si recortarla")
    print("igual (menos retorno por menos riesgo de 1-nombre) o aceptarla. NADA a prod sin esto. ")


if __name__ == "__main__":
    main()
