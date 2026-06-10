"""
Kepler — CHEQUEOS DE ROBUSTEZ OPERATIVA (Fase 1, code-first, CERO IA).
Librería de chequeos PUROS y determinísticos (umbral/banda) que devuelven severidad + mensaje. Se consume
pre-trade (orchestrator: bloquea el rebalanceo si hay CRÍTICO) y en heartbeat (alerta). El push lo manda
notify.py. Motivado por el incidente 2026-06-02 (VM sobre-apalancada 2.93x por backfill faltante): una
guarda de cobertura de datos lo habría frenado.

Severidad: OK < WARN < CRIT. CRIT pre-trade ⇒ NO operar (mantener el libro) + avisar. WARN ⇒ operar + avisar.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
import config

OK, WARN, CRIT = "OK", "WARN", "CRIT"
_RANK = {OK: 0, WARN: 1, CRIT: 2}

# ── Umbrales (tunables) ─────────────────────────────────────────────────────
COVERAGE_MARGIN_D   = 120     # el panel debe arrancar a <= HIST_START + este margen (warmup rev60d + listing)
FRESH_MAX_AGE_H     = 12.0    # última barra: CRIT si más vieja que esto (pipeline roto)
# Banda WARN del leverage de la ESTRATEGIA. El ancla de maxDD −10% FIJA el leverage de diseño de cada
# modo, así que la banda se calibra a ESE punto: full-20 ESTABLE ~2.2x → (1.3, 2.9); LOW_BARRIER (universo
# barato $5, β-hedge entre coins) ~1.18x → (0.7, 1.6) (misma anchura relativa; e78 + go-live 06-09 validaron
# 1.18x). Sin esta separación, low-barrier disparaba un WARN espurio en CADA ciclo (1.18x < 1.3) → ruido en
# el canal de alertas. La banda se elige según config.LOW_BARRIER_MODE; los CRIT (suelo/techo duros) NO cambian.
LEV_BAND             = (1.3, 2.9)   # full-20 ESTABLE (~2.2x)
LEV_BAND_LOW_BARRIER = (0.7, 1.6)   # universo barato (~1.18x), e78/go-live 2026-06-09
LEV_CRIT_HI         = 3.2     # CRIT si lev por encima (ancla claramente fallando)
LEV_CRIT_LO         = 0.5     # CRIT si lev por debajo
LEV_JUMP_WARN       = 0.20    # |Δlev/lev_prev| que dispara WARN (cambio brusco vs ciclo previo)
CONC_TOL            = 0.01    # tolerancia sobre MAX_POSITION_EQUITY (redondeo)
NPOS_BAND           = (12, 24)     # nº posiciones esperado (universo largo ~20)
BETA_DOLLAR_BAND    = (-0.30, 1.00)  # β-dólar diagnóstica (net-long por trend ~+0.45)


@dataclass
class CheckResult:
    name: str
    severity: str
    message: str
    value: float | None = None
    def __str__(self):
        ic = {OK: "✅", WARN: "🟡", CRIT: "🔴"}[self.severity]
        return f"{ic} {self.name}: {self.message}"


def _r(name, sev, msg, val=None):
    return CheckResult(name, sev, msg, val)


# ── Chequeos individuales (puros) ───────────────────────────────────────────
def check_data_coverage(C) -> CheckResult:
    """El panel del motor DEBE arrancar cerca de HIST_START_MONTH. Si arranca mucho más tarde → falta
    histórico (backfill perdido) → el ancla de maxDD ve una ventana corta y sobre-apalanca (incidente 06-02)."""
    try:
        start = pd.Timestamp(config.HIST_START_MONTH + "-01", tz="UTC")
        ps = C.index[0]
        limit = start + pd.Timedelta(days=COVERAGE_MARGIN_D)
        gap = (ps - start).days
        if ps > limit:
            return _r("data_coverage", CRIT,
                      f"panel arranca {ps.date()} (esperado ≤{limit.date()}); falta histórico desde "
                      f"{config.HIST_START_MONTH} → ancla sobre-apalanca. ¿backfill? `python -m kepler.fetch 1h`", gap)
        return _r("data_coverage", OK, f"histórico OK desde {ps.date()}", gap)
    except Exception as e:
        return _r("data_coverage", CRIT, f"no se pudo evaluar cobertura: {e}")


def check_data_freshness(C, now=None) -> CheckResult:
    """La última barra del panel no puede ser vieja (pipeline de datos roto / símbolo congelado)."""
    try:
        now = now or pd.Timestamp.now(tz="UTC")
        age_h = (now - C.index[-1]).total_seconds() / 3600.0
        if age_h > FRESH_MAX_AGE_H:
            return _r("data_freshness", CRIT, f"última barra hace {age_h:.1f}h (>{FRESH_MAX_AGE_H}h) — datos congelados", age_h)
        if age_h > FRESH_MAX_AGE_H / 2:
            return _r("data_freshness", WARN, f"última barra hace {age_h:.1f}h", age_h)
        return _r("data_freshness", OK, f"datos frescos ({age_h:.1f}h)", age_h)
    except Exception as e:
        return _r("data_freshness", CRIT, f"no se pudo evaluar frescura: {e}")


def check_leverage(lev, prev_lev=None, band=None) -> CheckResult:
    """Banda absoluta (CRIT si extremo = ancla fallando) + salto vs ciclo previo (WARN). La banda WARN se
    elige según el modo (full vs low-barrier) salvo que se pase `band` explícita (tests)."""
    if lev is None or lev != lev:
        return _r("leverage", CRIT, "leverage None/NaN")
    if lev > LEV_CRIT_HI or lev < LEV_CRIT_LO:
        return _r("leverage", CRIT, f"leverage {lev:.2f}x fuera de [{LEV_CRIT_LO},{LEV_CRIT_HI}] — ancla anómala", lev)
    if band is None:
        band = LEV_BAND_LOW_BARRIER if getattr(config, "LOW_BARRIER_MODE", False) else LEV_BAND
    sev, msgs = OK, [f"{lev:.2f}x"]
    if not (band[0] <= lev <= band[1]):
        sev = WARN; msgs.append(f"fuera de banda {band}")
    if prev_lev and prev_lev > 0:
        jump = abs(lev / prev_lev - 1)
        if jump > LEV_JUMP_WARN:
            sev = max(sev, WARN, key=_RANK.get); msgs.append(f"salto {jump*100:+.0f}% vs {prev_lev:.2f}x")
    return _r("leverage", sev, "leverage " + " · ".join(msgs), lev)


def check_concentration(target) -> CheckResult:
    """Ningún nombre debe superar el cap de posición (el clip lo fuerza; si se excede = bug)."""
    cap = config.MAX_POSITION_EQUITY
    if not cap:
        return _r("concentration", OK, "cap desactivado")
    mx = float(target.abs().max()); sym = target.abs().idxmax()
    if mx > cap + CONC_TOL:
        return _r("concentration", WARN, f"top {sym} {mx*100:.1f}% > cap {cap*100:.0f}% (revisar clip)", mx)
    return _r("concentration", OK, f"top {sym} {mx*100:.1f}% ≤ cap {cap*100:.0f}%", mx)


def check_n_positions(target, thresh=1e-3) -> CheckResult:
    n = int((target.abs() > thresh).sum())
    if not (NPOS_BAND[0] <= n <= NPOS_BAND[1]):
        return _r("n_positions", WARN, f"{n} posiciones fuera de {NPOS_BAND}", n)
    return _r("n_positions", OK, f"{n} posiciones", n)


def check_beta_dollar(target, beta_last) -> CheckResult:
    """β-dólar diagnóstica = Σ w·β (exposición direccional neta del notional)."""
    try:
        bd = float((target * beta_last.reindex(target.index).fillna(0)).sum())
        if not (BETA_DOLLAR_BAND[0] <= bd <= BETA_DOLLAR_BAND[1]):
            return _r("beta_dollar", WARN, f"β-dólar {bd:+.2f} fuera de {BETA_DOLLAR_BAND}", bd)
        return _r("beta_dollar", OK, f"β-dólar {bd:+.2f}", bd)
    except Exception as e:
        return _r("beta_dollar", WARN, f"no evaluable: {e}")


SLEEVE_CORR_WINDOW_D = 180   # ventana larga (la corta es ruido: con 21 pares el MAX se sesga alto)
SLEEVE_CORR_WARN     = 0.35  # MEDIA de |corr| entre pares (calibrado e: full=0.065, p99(180d)=0.27 → 0.35 = colapso real)


def check_sleeve_correlation(sleeve_df, window=SLEEVE_CORR_WINDOW_D, thresh=SLEEVE_CORR_WARN) -> CheckResult:
    """Diversificación = control de riesgo nº1. Métrica robusta = MEDIA de |corr| entre todos los pares
    (NO el máximo, que con 21 pares y ventana corta se sesga alto → falsas alarmas). Ventana larga (180d).
    Si la media sube por encima del umbral → la diversificación colapsa (libro = apuesta concentrada). WARN."""
    try:
        if sleeve_df is None or sleeve_df.shape[1] < 2:
            return _r("sleeve_corr", OK, "n/a")
        sub = sleeve_df.dropna().tail(window)
        n = sub.shape[1]
        if len(sub) < max(40, window // 2):
            return _r("sleeve_corr", OK, f"histórico insuficiente ({len(sub)}d)")
        a = sub.corr().abs().to_numpy(copy=True)   # copia escribible (.corr() es read-only)
        np.fill_diagonal(a, 0.0)
        mean_c = float(a.sum() / (n * (n - 1)))
        i, j = np.unravel_index(a.argmax(), a.shape)
        top = f"{sub.columns[i]}~{sub.columns[j]} {a.max():.2f}"   # par más alto, solo contexto
        if mean_c > thresh:
            return _r("sleeve_corr", WARN, f"corr media {mean_c:.2f} > {thresh} ({window}d; top {top}) — diversificación COLAPSANDO", mean_c)
        return _r("sleeve_corr", OK, f"corr media {mean_c:.2f} ≤ {thresh} ({window}d; top {top})", mean_c)
    except Exception as e:
        return _r("sleeve_corr", OK, f"no evaluable: {e}")


# ── Orquestación ────────────────────────────────────────────────────────────
def run_pretrade_checks(C, target, lev, beta_last, prev_lev=None, now=None, sleeve_df=None) -> list[CheckResult]:
    """Conjunto de guardas PRE-TRADE. Si alguna es CRIT → el orchestrator NO debe operar."""
    res = [
        check_data_coverage(C),
        check_data_freshness(C, now=now),
        check_leverage(lev, prev_lev),
        check_concentration(target),
        check_n_positions(target),
        check_beta_dollar(target, beta_last),
    ]
    if sleeve_df is not None:
        res.append(check_sleeve_correlation(sleeve_df))
    return res


# ── Chequeos RUNTIME (heartbeat, entre rebalanceos) ─────────────────────────
EQUITY_GAP_WARN = 0.05   # caída entre ticks (15min) que avisa
EQUITY_GAP_CRIT = 0.10
CYCLE_RECENCY_BUFFER_H = 6   # si no hay rebalanceo OK en MAX_REBAL_HOURS + esto → orquestador atascado
DD_WARN = 0.08   # drawdown vs pico que avisa (acercándose al ancla −10%)
DD_CRIT = 0.10   # drawdown vs pico = ancla alcanzada (la red DURA es el CB −20%; esto avisa MUCHO antes)


def check_drawdown(equity, peak) -> CheckResult:
    """Drawdown del equity MTM VIVO vs el pico, evaluado en el HEARTBEAT (cada 15min). Caza el acercamiento
    al ancla −10% sobre la curva MTM real, sin esperar al snapshot del rebalanceo de las 14 UTC (que va 1
    paso por detrás: el libro sigue sangrando intradía). NO es un halt (eso es el CB −20%): solo AVISA."""
    if not peak or peak <= 0 or equity is None:
        return _r("drawdown", OK, "sin referencia de pico")
    dd = equity / peak - 1
    if dd <= -DD_CRIT:
        return _r("drawdown", CRIT, f"drawdown {dd*100:.1f}% alcanzó el ancla −{DD_CRIT*100:.0f}% (CB en −20%)", dd)
    if dd <= -DD_WARN:
        return _r("drawdown", WARN, f"drawdown {dd*100:.1f}% se acerca al ancla −{DD_CRIT*100:.0f}%", dd)
    return _r("drawdown", OK, f"drawdown {dd*100:.1f}%", dd)


def check_equity_gap(prev_eq, eq) -> CheckResult:
    """Caída brusca de equity entre dos ticks del heartbeat (el CB ancho −20% es la red dura; esto avisa antes)."""
    if not prev_eq or prev_eq <= 0 or eq is None:
        return _r("equity_gap", OK, "sin referencia previa")
    chg = eq / prev_eq - 1
    if chg <= -EQUITY_GAP_CRIT:
        return _r("equity_gap", CRIT, f"equity {chg*100:.1f}% entre ticks", chg)
    if chg <= -EQUITY_GAP_WARN:
        return _r("equity_gap", WARN, f"equity {chg*100:.1f}% entre ticks", chg)
    return _r("equity_gap", OK, f"equity Δ {chg*100:+.1f}%", chg)


def check_cycle_recency(last_ok_ts_ms, now_ms, max_h) -> CheckResult:
    """¿Hace cuánto del último rebalanceo OK? Si supera el máximo → el orquestador no está rebalanceando."""
    if not last_ok_ts_ms:
        return _r("cycle_recency", OK, "sin ciclos previos")
    age_h = (now_ms - last_ok_ts_ms) / 3.6e6
    if age_h > max_h:
        return _r("cycle_recency", WARN, f"último rebalanceo hace {age_h:.0f}h (>{max_h:.0f}h) — ¿atascado?", age_h)
    return _r("cycle_recency", OK, f"último rebalanceo hace {age_h:.0f}h", age_h)


def check_orphans(positions, universe) -> CheckResult:
    """Posiciones abiertas fuera del universo operado (deberían cerrarse solas; si persisten = aviso)."""
    if positions is None or universe is None:
        return _r("orphans", OK, "n/a")
    orph = [s for s in positions if s not in universe]
    if orph:
        return _r("orphans", WARN, f"posiciones fuera del universo: {orph}", len(orph))
    return _r("orphans", OK, "sin huérfanas", 0)


def run_heartbeat_checks(prev_eq, eq, last_ok_ts_ms, now_ms, max_cycle_h,
                         positions=None, universe=None, peak=None) -> list[CheckResult]:
    """Chequeos RUNTIME (entre rebalanceos). Solo avisan (no bloquean nada; el CB es la red dura)."""
    res = [check_equity_gap(prev_eq, eq), check_cycle_recency(last_ok_ts_ms, now_ms, max_cycle_h)]
    if peak is not None:
        res.append(check_drawdown(eq, peak))
    if positions is not None and universe is not None:
        res.append(check_orphans(positions, universe))
    return res


def data_healthy(C, now=None) -> bool:
    """True si los datos están sanos (cobertura + frescura) — para la REANUDACIÓN RÁPIDA tras un bloqueo."""
    return not should_block([check_data_coverage(C), check_data_freshness(C, now=now)])


def worst(results) -> str:
    return max((r.severity for r in results), key=_RANK.get, default=OK)


def should_block(results) -> bool:
    return any(r.severity == CRIT for r in results)


def summarize(results) -> str:
    return " | ".join(str(r) for r in results if r.severity != OK) or "✅ todos los chequeos OK"
