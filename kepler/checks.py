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
import pandas as pd
import config

OK, WARN, CRIT = "OK", "WARN", "CRIT"
_RANK = {OK: 0, WARN: 1, CRIT: 2}

# ── Umbrales (tunables) ─────────────────────────────────────────────────────
COVERAGE_MARGIN_D   = 120     # el panel debe arrancar a <= HIST_START + este margen (warmup rev60d + listing)
FRESH_MAX_AGE_H     = 12.0    # última barra: CRIT si más vieja que esto (pipeline roto)
LEV_BAND            = (1.3, 2.9)   # banda WARN del leverage de estrategia (ESTABLE ~2.2)
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


def check_leverage(lev, prev_lev=None) -> CheckResult:
    """Banda absoluta (CRIT si extremo = ancla fallando) + salto vs ciclo previo (WARN)."""
    if lev is None or lev != lev:
        return _r("leverage", CRIT, "leverage None/NaN")
    if lev > LEV_CRIT_HI or lev < LEV_CRIT_LO:
        return _r("leverage", CRIT, f"leverage {lev:.2f}x fuera de [{LEV_CRIT_LO},{LEV_CRIT_HI}] — ancla anómala", lev)
    sev, msgs = OK, [f"{lev:.2f}x"]
    if not (LEV_BAND[0] <= lev <= LEV_BAND[1]):
        sev = WARN; msgs.append(f"fuera de banda {LEV_BAND}")
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


# ── Orquestación ────────────────────────────────────────────────────────────
def run_pretrade_checks(C, target, lev, beta_last, prev_lev=None, now=None) -> list[CheckResult]:
    """Conjunto de guardas PRE-TRADE. Si alguna es CRIT → el orchestrator NO debe operar."""
    return [
        check_data_coverage(C),
        check_data_freshness(C, now=now),
        check_leverage(lev, prev_lev),
        check_concentration(target),
        check_n_positions(target),
        check_beta_dollar(target, beta_last),
    ]


def worst(results) -> str:
    return max((r.severity for r in results), key=_RANK.get, default=OK)


def should_block(results) -> bool:
    return any(r.severity == CRIT for r in results)


def summarize(results) -> str:
    return " | ".join(str(r) for r in results if r.severity != OK) or "✅ todos los chequeos OK"
