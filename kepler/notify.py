"""
Kepler — notificaciones push vía ntfy.sh (gratis, sin cuenta).
Topic en la variable de entorno KEPLER_NTFY_TOPIC (elige uno único, ej 'kepler-oscar-x7k2').
Suscríbete en el móvil con la app ntfy.sh a ese mismo topic.
"""
from __future__ import annotations
import logging, os
import requests

TOPIC = os.environ.get("KEPLER_NTFY_TOPIC", "")
URL = f"https://ntfy.sh/{TOPIC}" if TOPIC else ""


def send(title: str, message: str, priority: str = "default", tags: str = "") -> bool:
    """Envía un push. priority: min/low/default/high/urgent. tags: emojis ntfy separados por coma."""
    if not URL:
        return False
    try:
        requests.post(URL, data=message.encode("utf-8"),
                      headers={"Title": title.encode("utf-8"), "Priority": priority, "Tags": tags},
                      timeout=8)
        return True
    except Exception as e:
        logging.debug(f"[notify] error: {e}")
        return False


def alert_cycle(equity, n_pos, gross, operate, mode):
    send(f"Kepler ciclo — {mode}",
         f"Equity ${equity:,.0f} · {n_pos} posiciones · gross {gross:.2f} · "
         f"{'OPERANDO' if operate else '⛔ HALT'}",
         priority="low", tags="bar_chart")


def alert_error(msg):
    send("⚠️ Kepler ERROR", msg, priority="urgent", tags="warning,rotating_light")


def alert_halt(dd, equity):
    send("⛔ Kepler CIRCUIT BREAKER",
         f"Drawdown {dd*100:.1f}% — operación PAUSADA (equity ${equity:,.0f})",
         priority="urgent", tags="octagonal_sign")


def alert_checks_block(msg):
    """Guarda pre-trade CRÍTICA: el rebalanceo se bloqueó (libro intacto)."""
    send("⛔ Kepler REBALANCEO BLOQUEADO",
         f"Guarda pre-trade CRÍTICA — NO se operó (libro intacto, reintenta próximo ciclo):\n{msg}",
         priority="urgent", tags="octagonal_sign,no_entry")


def alert_checks_warn(msg):
    """Aviso de chequeos (operó, pero hay desviación a vigilar)."""
    send("🟡 Kepler aviso de chequeos", msg, priority="high", tags="warning")


def alert_checks_recover():
    send("✅ Kepler chequeos OK", "Los chequeos pre-trade volvieron a verde.",
         priority="default", tags="white_check_mark")
