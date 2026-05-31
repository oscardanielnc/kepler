"""
E20 — B3: DEFLATED SHARPE RATIO (Bailey & López de Prado 2014). 2026-05-31.
El Sharpe del combinado (2.07 backtest) está sesgado al alza por SELECCIÓN: probamos muchas
configuraciones (horizontes, sleeves) y nos quedamos con la mejor. El DSR descuenta ese sesgo:
da la PROBABILIDAD de que el Sharpe verdadero sea > el benchmark esperado por puro azar de buscar N veces.

Fórmula (per-observación, diaria):
  SR0 = √V · [ (1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)) ]      ← Sharpe esperado MÁX bajo el null
  DSR = Φ( (SR̂ − SR0)·√(T−1) / √(1 − γ3·SR̂ + (γ4−1)/4·SR̂²) )
  N = nº de trials · V = var de los Sharpes de los trials · T = nº obs · γ3=skew · γ4=kurtosis · γ=Euler.

Trials = grilla realista de configs por sleeve (los horizontes/lookbacks que se exploraron).
DSR > 0.95 → el Sharpe sobrevive al multiple-testing (creíble). < 0.90 → ojo, podría ser suerte.

python -m research.e20_deflated_sharpe
"""
from __future__ import annotations
import os, sys, math
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from kepler import alphas
from kepler.engine import load, _beta, xs_sleeve, carry_sleeve, trend_sleeve, load_panel
from kepler.portfolio import vol_parity_weights

GAMMA = 0.5772156649015329   # Euler-Mascheroni


def norm_cdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p):
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2*math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p-0.5; r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2*math.log(1-p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def daily_sharpe(r):
    r = r.dropna()
    return r.mean()/r.std() if len(r) > 30 and r.std() > 0 else 0.0


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("E20 — B3: Deflated Sharpe Ratio\n" + "="*60)
    C = load(); ret = np.log(C).diff(); beta = _beta(ret)
    P = load_panel(["volume", "taker_buy_volume"], C)

    # ── combinado de producción (7 sleeves, vol-parity, 1x) ───────────────────
    prod = {}
    prod["mom_30d"], _    = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, 720), 720)
    prod["rev_60d"], _    = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, 1440), 1440)
    prod["lowvol_14d"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, 336), 336)
    prod["carry"], _      = carry_sleeve(C, ret, beta)
    prod["trend"], _      = trend_sleeve(C)
    prod["takerflow_5d"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], 120), 120)
    prod["hlpos_14d"], _  = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, 336), 336)
    df = pd.concat(prod, axis=1); df.columns = list(prod.keys()); df = df.dropna()
    combo = (df * vol_parity_weights(df)).sum(axis=1).dropna()
    SR = daily_sharpe(combo); T = len(combo)
    skew = combo.skew(); kurt = combo.kurt() + 3.0      # pandas da kurtosis EXCESO → +3 = γ4
    print(f"Combinado 7 sleeves: SR diario {SR:.4f} (anual {SR*np.sqrt(365):.2f}) · "
          f"T={T} días · skew {skew:.2f} · kurtosis {kurt:.2f}\n")

    # ── trials: grilla realista de configs exploradas por sleeve ──────────────
    trials = {}
    for h in (360, 540, 720, 1080, 1440):        # momentum lookbacks (15..60d)
        trials[f"mom_{h}"], _ = xs_sleeve(C, ret, beta, alphas.xs_momentum_score(ret, h), h)
    for h in (720, 1080, 1440, 2160):            # reversión (30..90d)
        trials[f"rev_{h}"], _ = xs_sleeve(C, ret, beta, alphas.xs_reversal_score(ret, h), h)
    for h in (168, 336, 504, 720):               # low-vol (7..30d)
        trials[f"lv_{h}"], _ = xs_sleeve(C, ret, beta, alphas.xs_lowvol_score(ret, h), h)
    for h in (72, 120, 168, 240):                # taker-flow (3..10d)
        trials[f"tf_{h}"], _ = xs_sleeve(C, ret, beta, alphas.xs_takerflow_score(P["volume"], P["taker_buy_volume"], h), h)
    for h in (168, 240, 336, 504, 720):          # hl-position (7..30d)
        trials[f"hl_{h}"], _ = xs_sleeve(C, ret, beta, alphas.xs_hlposition_score(C, h), h)
    trials["carry"] = prod["carry"]; trials["trend"] = prod["trend"]
    trial_sr = pd.Series({k: daily_sharpe(v) for k, v in trials.items()}).dropna()
    N = len(trial_sr); V = trial_sr.var(ddof=1)
    print(f"TRIALS: N={N} configs · Sharpe diario medio {trial_sr.mean():.4f} · "
          f"std {np.sqrt(V):.4f} (anual std {np.sqrt(V)*np.sqrt(365):.2f})")
    print(f"  rango trial Sharpe (anual): [{trial_sr.min()*np.sqrt(365):.2f}, {trial_sr.max()*np.sqrt(365):.2f}]\n")

    # ── DSR (con sensibilidad al nº de trials, porque N real ≥ grilla) ────────
    def dsr_for(n, v):
        sr0 = math.sqrt(v) * ((1-GAMMA)*norm_ppf(1 - 1.0/n) + GAMMA*norm_ppf(1 - 1.0/(n*math.e)))
        denom = math.sqrt(1 - skew*SR + (kurt-1)/4*SR**2)
        dsr = norm_cdf((SR - sr0)*math.sqrt(T-1)/denom)
        return sr0, dsr

    print("DEFLATED SHARPE (probabilidad de que el Sharpe sea REAL, no suerte de buscar):")
    print(f"  {'N trials':>9s} {'SR0 anual':>10s} {'DSR':>8s}")
    for mult, lbl in ((1, "grilla"), (2, "×2 (no registrados)"), (3, "×3 (conservador)"), (5, "×5 (muy conserv.)")):
        n = N*mult
        sr0, dsr = dsr_for(n, V)
        print(f"  {n:>6d} {lbl:<3s} {sr0*np.sqrt(365):9.2f} {dsr:8.3f}")

    sr0_1, dsr_1 = dsr_for(N, V)
    print(f"\nLectura: SR0 (benchmark de SUERTE buscando {N}×) ≈ {sr0_1*np.sqrt(365):.2f} anual; el observado "
          f"{SR*np.sqrt(365):.2f} lo supera con DSR={dsr_1:.3f}.")
    print("DSR>0.95 → el Sharpe sobrevive al multiple-testing (creíble). <0.90 → cuidado.")


if __name__ == "__main__":
    main()
