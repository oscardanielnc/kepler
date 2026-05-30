"""
Kepler — REPORTE VISUAL. Genera un panel de gráficos para entender el sistema:
equity por sleeve y combinado, drawdown, correlaciones, retornos mensuales, portafolio
objetivo actual y Sharpe rodante. Guarda PNG en logs/.

python -m kepler.report
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa
from kepler.engine import compute_target, TIERS


def main():
    tier = "ESTABLE"
    target, vp, df, port, asof = compute_target(tier)
    eq = (1 + port).cumprod()
    fig, ax = plt.subplots(2, 3, figsize=(19, 10))
    fig.suptitle(f"KEPLER — Sistema de 5 sleeves (tier {tier} 1x) · datos hasta {str(asof)[:10]}",
                 fontsize=15, fontweight="bold")

    # 1. Equity combinado + por sleeve
    for c in df.columns:
        ax[0, 0].plot((1 + df[c]).cumprod(), lw=1, alpha=0.6, label=c)
    ax[0, 0].plot(eq, lw=2.5, color="black", label="COMBINADO")
    ax[0, 0].set_title("Equity acumulada (combinado vs cada sleeve)"); ax[0, 0].legend(fontsize=8)
    ax[0, 0].set_yscale("log"); ax[0, 0].grid(alpha=0.3)

    # 2. Drawdown del combinado
    dd = (eq / eq.cummax() - 1) * 100
    ax[0, 1].fill_between(dd.index, dd.values, 0, color="crimson", alpha=0.5)
    ax[0, 1].set_title(f"Drawdown combinado (maxDD {dd.min():.1f}%)"); ax[0, 1].grid(alpha=0.3)

    # 3. Correlaciones entre sleeves
    cor = df.corr()
    im = ax[0, 2].imshow(cor, cmap="RdBu_r", vmin=-1, vmax=1)
    ax[0, 2].set_xticks(range(len(cor))); ax[0, 2].set_xticklabels(cor.columns, rotation=45, ha="right", fontsize=8)
    ax[0, 2].set_yticks(range(len(cor))); ax[0, 2].set_yticklabels(cor.columns, fontsize=8)
    for i in range(len(cor)):
        for j in range(len(cor)):
            ax[0, 2].text(j, i, f"{cor.iloc[i,j]:.2f}", ha="center", va="center", fontsize=8)
    ax[0, 2].set_title("Correlación entre sleeves (~0 = diversifica)")
    plt.colorbar(im, ax=ax[0, 2], fraction=0.046)

    # 4. Retornos mensuales (heatmap año × mes)
    m = (1 + port).groupby([port.index.year, port.index.month]).prod() - 1
    mm = m.unstack() * 100
    im2 = ax[1, 0].imshow(mm, cmap="RdYlGn", vmin=-15, vmax=15, aspect="auto")
    ax[1, 0].set_xticks(range(12)); ax[1, 0].set_xticklabels(range(1, 13), fontsize=8)
    ax[1, 0].set_yticks(range(len(mm.index))); ax[1, 0].set_yticklabels(mm.index, fontsize=8)
    for i in range(len(mm.index)):
        for j in range(12):
            v = mm.iloc[i, j] if j < mm.shape[1] else np.nan
            if pd.notna(v):
                ax[1, 0].text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7)
    ax[1, 0].set_title("Retorno mensual % (verde=gana, rojo=pierde)")

    # 5. Portafolio objetivo actual
    t = target[target.abs() > 0.005].sort_values()
    colors = ["crimson" if v < 0 else "seagreen" for v in t.values]
    ax[1, 1].barh(range(len(t)), t.values * 100, color=colors)
    ax[1, 1].set_yticks(range(len(t))); ax[1, 1].set_yticklabels(t.index, fontsize=8)
    ax[1, 1].set_title("Portafolio OBJETIVO hoy (% capital · long=verde/short=rojo)")
    ax[1, 1].axvline(0, color="black", lw=0.8); ax[1, 1].grid(alpha=0.3, axis="x")

    # 6. Sharpe rodante 90d (consistencia)
    rs = port.rolling(90).mean() / port.rolling(90).std() * np.sqrt(365)
    ax[1, 2].plot(rs, color="navy"); ax[1, 2].axhline(0, color="red", lw=0.8, ls="--")
    ax[1, 2].axhline(rs.mean(), color="green", lw=1, ls=":", label=f"media {rs.mean():.2f}")
    ax[1, 2].set_title("Sharpe rodante 90d (¿consistente? ¿dónde sufre?)")
    ax[1, 2].legend(fontsize=8); ax[1, 2].grid(alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    out = os.path.join(config.LOGS_DIR, "kepler_report.png")
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print(f"Reporte guardado → {out}")
    # métricas resumen
    sh = port.mean()/port.std()*np.sqrt(365)
    print(f"Sharpe {sh:.2f} · ann {((1+port.mean())**365-1)*100:.1f}% · maxDD {dd.min():.1f}% · "
          f"meses+ {(m>0).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
