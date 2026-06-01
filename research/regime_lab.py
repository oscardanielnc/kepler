"""
REGIME LAB — R0 (protocolo) + R1 (laboratorio reutilizable). 2026-06-01.
Infraestructura para evaluar, CON DISCIPLINA, si condicionar un sleeve a un RÉGIMEN ex-ante mejora
el sistema OOS. Sirve dos usos (Oscar): (A) RESCATAR un candidato descartado activándolo solo en su
régimen favorable; (B) POTENCIAR un sleeve actual dándole más peso cuando el régimen está a su favor.
Ambos se reducen al MISMO mecanismo: añadir al libro un "satélite condicional" = (sleeve)·1{régimen}.
  - (A): el sleeve es un candidato descartado (order-book, OI, TVL, estacionalidad, iliquidez...).
  - (B): el sleeve es uno de los 7 base → en régimen favorable el libro tiene 2 unidades de ese
         sleeve (base + satélite) → vol-parity le sube el peso. = "más peso cuando el viento ayuda".

═══════════════════════════════════════════════════════════════════════════════════════════════
PROTOCOLO ANTI-OVERFIT (R0) — el guardián. Sin esto, N candidatos × M régimenes = máquina de
autoengaño (con suficientes combos SIEMPRE sale algo "bueno" in-sample; cicatrices e25/e28).
  1. MENÚ FIJO y PRE-REGISTRADO de régimenes (económicos, ex-ante, sin tunear umbrales).
  2. SIGNO/DIRECCIÓN pre-registrado por TEORÍA antes de mirar el resultado (se documenta en HYPOTHESES).
  3. Solo SHARPE en walk-forward PURGADO + CPCV (invariante al leverage → esquiva la trampa del ancla
     de e28, donde el "edge de régimen" era el mecanismo leverage-al-ancla, no timing real).
  4. DEFLACIÓN por multiple-testing: el listón sube con nº de combos probados (estilo DSR/López de
     Prado). Un ganador debe superar el MÁXIMO esperado bajo ruido de N pruebas.
  5. CONDICIONAMIENTO suave > ON/OFF duro cuando se pueda (menos turnover/overfit). Aquí empezamos
     con ON/OFF (binario) por simplicidad; el suave es extensión futura.
  6. Lo ya "espiado" sobre ESTA muestra (p.ej. iliquidez×vol) NO se valida aquí: solo en sombra/forward.
  7. Reglas duras de promoción: pasa OOS cronológico (ΔSharpe>0) + CPCV ≥5/6 folds + supera la
     barra deflactada. Si pasa → candidato; promoción real exige además demo/sombra (regla de oro).
═══════════════════════════════════════════════════════════════════════════════════════════════

python -m research.regime_lab            # self-test + menú + demo de validación (iliquidez×vol)
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel, DRIVER
from kepler.portfolio import vol_parity_weights, metrics, leverage_for_maxdd_anchor

EMBARGO_D, BLOCK_D, INIT_FRAC = 10, 21, 0.40
CACHE = os.path.join(config.DATA_DIR, "regime_lab"); os.makedirs(CACHE, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# R0 — MENÚ DE RÉGIMENES (ex-ante, pre-registrados). Cada uno devuelve una Series booleana DIARIA
# con el "estado base" (descrito en el nombre). La DIRECCIÓN (favorable = estado o su negación) se
# fija por hipótesis al testear. Umbral = mediana EXPANDING (solo-pasado) shift(1), SIN tunear.
# ─────────────────────────────────────────────────────────────────────────────
def _exante_high(x: pd.Series, minp=120) -> pd.Series:
    """True donde x supera su mediana expanding (solo-pasado, shift 1). Ex-ante por construcción."""
    thr = x.expanding(min_periods=minp).median().shift(1)
    return (x > thr)


def reg_mkt_vol_high(C):
    """Vol de mercado ALTA (BTC 30d realized vol > mediana pasada). risk-off / estrés."""
    v = C[DRIVER].resample("1D").last().pct_change().rolling(30).std()
    return _exante_high(v).rename("mkt_vol_high")


def reg_mkt_bull(C):
    """Tendencia BTC alcista (close > MA100, ex-ante shift 1). risk-on direccional."""
    p = C[DRIVER].resample("1D").last()
    ma = p.rolling(100).mean()
    return (p.shift(1) > ma.shift(1)).rename("mkt_bull")


def reg_xs_dispersion_high(C):
    """Dispersión cross-seccional ALTA: std entre símbolos del retorno 14d. Entorno 'stock-picking'."""
    r14 = C.resample("1D").last().pct_change(14)
    disp = r14.std(axis=1)
    return _exante_high(disp).rename("xs_disp_high")


def reg_funding_high(C):
    """Funding agregado ALTO (mediana cross-seccional del funding 8h, suavizado). Apalancamiento long
    crowded en el sistema. Ex-ante (mediana pasada)."""
    fd = {}
    for p in glob.glob(os.path.join(config.DATA_DIR, "funding", "*.parquet")):
        s = os.path.basename(p)[:-8]
        if s not in C.columns:
            continue
        f = pd.read_parquet(p).set_index("funding_time")["funding_rate"]
        f.index = pd.to_datetime(f.index, unit="ms", utc=True)
        fd[s] = f.resample("8h").sum()
    if not fd:
        return pd.Series(dtype=bool, name="funding_high")
    F = pd.DataFrame(fd).rolling(21, min_periods=1).mean()
    agg = F.median(axis=1).resample("1D").last()
    return _exante_high(agg).rename("funding_high")


def reg_breadth_high(C):
    """Breadth ALTA: fracción de símbolos sobre su MA50 propia. Mercado amplio al alza."""
    p = C.resample("1D").last()
    above = (p > p.rolling(50).mean()).mean(axis=1)
    return _exante_high(above).rename("breadth_high")


REGIME_MENU = {
    "mkt_vol_high":  reg_mkt_vol_high,
    "mkt_bull":      reg_mkt_bull,
    "xs_disp_high":  reg_xs_dispersion_high,
    "funding_high":  reg_funding_high,
    "breadth_high":  reg_breadth_high,
}

# HIPÓTESIS pre-registradas (signo por teoría). Documenta la DIRECCIÓN esperada para cada sleeve antes
# de testear. Formato: (sleeve, regime) -> favorable_state (True = el estado del menú; False = su negación).
# Se rellena en R2/R3 al pre-registrar cada test. Vacío aquí = se declara en cada experimento.
HYPOTHESES: dict[tuple[str, str], bool] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Construcción de sleeves (con cache: R2/R3 corren rápido)
# ─────────────────────────────────────────────────────────────────────────────
def build_base_sleeves(rebuild=False) -> pd.DataFrame:
    """Los 7 sleeves base (retornos diarios netos maker). Cacheado."""
    cf = os.path.join(CACHE, "base_sleeves.parquet")
    if os.path.exists(cf) and not rebuild:
        return pd.read_parquet(cf)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)
    s = {}
    s["mom_30d"], _      = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    s["rev_60d"], _      = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    s["lowvol_14d"], _   = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    s["carry"], _        = carry_sleeve(C, ret, beta)
    s["trend"], _        = trend_sleeve(C)
    s["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    s["hlpos_14d"], _    = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df = pd.concat(s, axis=1); df.columns = list(s); df = df.dropna()
    df.to_parquet(cf)
    return df


def build_illiq_sleeve() -> pd.Series:
    """Sleeve de iliquidez (Amihud 14d, signo orientado en IS). Para validar el lab contra e30c/d."""
    C = load(); ret = np.log(C).diff(); beta = _beta(ret); absret = ret.abs()
    dvol = load_panel(["quote_volume"], C)["quote_volume"]
    score = np.log((absret / dvol.replace(0, np.nan)).rolling(14*24).mean().replace(0, np.nan))
    il, _ = xs_sleeve(C, ret, beta, score, 14*24)
    cut = int(il.dropna().shape[0]*0.6)
    return (il * (1.0 if il.dropna().iloc[:cut].mean() >= 0 else -1.0)).rename("illiq_14d")


def get_regimes(rebuild=False) -> pd.DataFrame:
    """Panel diario booleano de todos los régimenes del menú. Cacheado."""
    cf = os.path.join(CACHE, "regimes.parquet")
    if os.path.exists(cf) and not rebuild:
        return pd.read_parquet(cf)
    C = load()
    cols = {}
    for name, fn in REGIME_MENU.items():
        try:
            cols[name] = fn(C)
        except Exception as e:
            print(f"(régimen {name} omitido: {e})")
    R = pd.concat(cols, axis=1); R.columns = list(cols)
    R.to_parquet(cf)
    return R


# ─────────────────────────────────────────────────────────────────────────────
# R1 — EVALUADOR (walk-forward purgado + CPCV) y DEFLACIÓN
# ─────────────────────────────────────────────────────────────────────────────
def _walk_forward_oos(df: pd.DataFrame) -> pd.Series:
    """Stitch OOS a 1x: vp ajustado SOLO con pasado (embargo), aplicado al bloque siguiente."""
    T = len(df); init = int(INIT_FRAC * T); parts = []; i = init
    while i < T:
        train = df.iloc[:max(1, i - EMBARGO_D)]; test = df.iloc[i:i + BLOCK_D]
        if len(train) >= 60 and len(test) > 0:
            vp = vol_parity_weights(train, is_frac=1.0)
            parts.append((test * vp).sum(axis=1))
        i += BLOCK_D
    return pd.concat(parts).sort_index()


def _cpcv_sharpes(df: pd.DataFrame, K=6) -> list[float]:
    T = len(df); folds = np.array_split(np.arange(T), K); out = []
    for te in folds:
        lo, hi = te[0], te[-1]
        mask = np.ones(T, bool); mask[max(0, lo - EMBARGO_D):hi + 1 + EMBARGO_D] = False
        tr = df.iloc[mask]
        if len(tr) < 60: continue
        vp = vol_parity_weights(tr, is_frac=1.0)
        out.append(metrics((df.iloc[lo:hi + 1] * vp).sum(axis=1)).get("sharpe", float("nan")))
    return [x for x in out if not np.isnan(x)]


def _anchored(oos: pd.Series):
    L = leverage_for_maxdd_anchor(oos, config.TARGET_MAXDD); m = metrics(oos * L)
    return m["sharpe"], m["ann"]/12, m["maxdd"]


def conditional(sleeve: pd.Series, regime: pd.Series, favorable_state=True) -> pd.Series:
    """Satélite condicional: el retorno del sleeve SOLO en régimen favorable (flat si no)."""
    reg = regime.reindex(sleeve.index, method="ffill").fillna(False).astype(bool)
    on = reg if favorable_state else ~reg
    return sleeve.where(on, 0.0)


def evaluate(base: pd.DataFrame, extra: pd.Series | None, label: str) -> dict:
    """Compara base vs base+extra en OOS purgado + CPCV. extra=None → solo base (referencia)."""
    df = base if extra is None else pd.concat([base, extra.rename("x")], axis=1).dropna()
    oos = _walk_forward_oos(df); s, mes, dd = _anchored(oos)
    folds = _cpcv_sharpes(df)
    return {"label": label, "oos_sharpe": s, "oos_mes": mes, "oos_maxdd": dd,
            "folds": folds, "fold_mean": float(np.mean(folds)) if folds else float("nan")}


def run_combo(base: pd.DataFrame, base_ref: dict, sleeve: pd.Series, regime: pd.Series,
              favorable_state: bool, name: str) -> dict:
    """Un test completo: añadir (sleeve · 1{régimen favorable}) al libro y medir el aporte OOS."""
    cond = conditional(sleeve, regime, favorable_state)
    r = evaluate(base, cond, name)
    f_base, f_cand = base_ref["folds"], r["folds"]
    n = min(len(f_base), len(f_cand))
    deltas = [f_cand[k] - f_base[k] for k in range(n)]
    r["d_sharpe"] = r["oos_sharpe"] - base_ref["oos_sharpe"]
    r["d_mes"] = r["oos_mes"] - base_ref["oos_mes"]
    r["fold_wins"] = sum(d > 0 for d in deltas); r["fold_n"] = n
    r["fold_dmean"] = float(np.mean(deltas)) if deltas else float("nan")
    r["pct_on"] = float(conditional(pd.Series(1.0, index=sleeve.index), regime, favorable_state).astype(bool).mean())
    return r


def deflation_bar(d_sharpes: list[float], n_trials: int) -> float:
    """Barra deflactada (López de Prado): máximo ΔSharpe esperado bajo ruido de N pruebas
    ≈ media + σ·√(2·ln N). Un ganador real debe SUPERARLA. σ = dispersión de los Δ observados."""
    if len(d_sharpes) < 2 or n_trials < 2:
        return float("inf")
    return float(np.mean(d_sharpes) + np.std(d_sharpes) * np.sqrt(2.0 * np.log(n_trials)))


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST / DEMO de validación
# ─────────────────────────────────────────────────────────────────────────────
def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    rebuild = "--rebuild" in sys.argv
    print("REGIME LAB — R0 (protocolo) + R1 (evaluador). Self-test.\n" + "="*64)

    base = build_base_sleeves(rebuild=rebuild)
    R = get_regimes(rebuild=rebuild)
    print(f"Base: 7 sleeves · {len(base)} días ({base.index[0].date()} → {base.index[-1].date()})")
    print(f"Régimenes en el menú: {list(R.columns)}\n")

    print("MENÚ DE RÉGIMENES (% del tiempo en estado 'True', alineado al período de los sleeves):")
    Ralign = R.reindex(base.index, method="ffill")
    for c in R.columns:
        print(f"  {c:16s} activo {Ralign[c].fillna(False).mean()*100:4.0f}% del tiempo")

    base_ref = evaluate(base, None, "7 base")
    print(f"\nBASELINE 7 sleeves (OOS purgado): Sharpe {base_ref['oos_sharpe']:.2f} · "
          f"{base_ref['oos_mes']:.2f}%/mes · maxDD {base_ref['oos_maxdd']:.1f}% · "
          f"CPCV media {base_ref['fold_mean']:+.2f} ({len(base_ref['folds'])} folds)")

    # VALIDACIÓN del lab: iliquidez × mkt_vol_high. e30d halló que illiq gana en ALTA vol (no baja);
    # condicionar a BAJA vol la empeoró. Aquí confirmamos que el lab reproduce ese hallazgo.
    print("\n── VALIDACIÓN (debe reproducir e30d): iliquidez condicionada a régimen de vol ──")
    il = build_illiq_sleeve()
    raw = evaluate(base, il, "8 raw (illiq sin condicionar)")
    print(f"  raw illiq:          ΔSharpe {raw['oos_sharpe']-base_ref['oos_sharpe']:+.2f} · "
          f"CPCV {sum(a>b for a,b in zip(raw['folds'], base_ref['folds']))}/{len(base_ref['folds'])}")
    # favorable=BAJA vol → ~mkt_vol_high (favorable_state=False); favorable=ALTA vol → favorable_state=True.
    for fav_high, tag in [(False, "BAJA-vol favorable (hipótesis e30d, refutada)"),
                          (True,  "ALTA-vol favorable (lo que el dato insinuó in-sample)")]:
        r = run_combo(base, base_ref, il, R["mkt_vol_high"], favorable_state=fav_high,
                      name=f"illiq×vol[{tag}]")
        print(f"  cond [{tag[:38]:38s}] ΔSharpe {r['d_sharpe']:+.2f} · "
              f"folds {r['fold_wins']}/{r['fold_n']} · activo {r['pct_on']*100:.0f}%")
    print("  (esperado: condicionar NO supera a raw de forma fiable → el régimen no salva a la iliquidez,")
    print("   y el lado ALTA-vol que se ve mejor es IN-SAMPLE/espiado → solo validable forward, no aquí.)")

    print("\n" + "="*64)
    print("R0+R1 listos. R2 = sweep de los 7 sleeves actuales × menú (¿potenciar?).")
    print("R3 = sweep de descartados × menú (¿rescatar?). Ambos con deflación por nº de combos.")


if __name__ == "__main__":
    main()
