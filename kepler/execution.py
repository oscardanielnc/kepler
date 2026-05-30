"""
Kepler — CAPA DE EJECUCIÓN. Rebalancea la cartera hacia el portafolio objetivo del motor
usando órdenes LÍMITE (maker-first). API de Binance Futures rescatada de Sentinel.

Modos (config_exec):
  DRY_RUN=True  → solo loguea las órdenes (no envía nada). DEFAULT seguro.
  USE_DEMO=True → demo-fapi.binance.com (cuenta demo).
  ambos False   → fapi.binance.com (real). SOLO tras validar en demo.

Flujo: engine.compute_target() → pesos objetivo → vs posiciones actuales → deltas →
órdenes límite maker por símbolo. El riesgo se gestiona a nivel CARTERA (sin SL por trade;
el rebalanceo ES la gestión — las posiciones cambian al cambiar las señales).
"""
from __future__ import annotations
import hashlib, hmac, logging, os, sys, time
from urllib.parse import urlencode
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa

# ─── Config de ejecución (por variables de entorno → no se pisa con git pull) ──
# KEPLER_DRY_RUN=false y KEPLER_USE_DEMO=true → opera en demo. Default seguro: DRY_RUN.
DRY_RUN  = os.environ.get("KEPLER_DRY_RUN", "true").lower() != "false"
USE_DEMO = os.environ.get("KEPLER_USE_DEMO", "true").lower() != "false"
API_KEY    = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
MIN_ORDER_USD = 5.0   # ignorar deltas menores (ruido/min-notional Binance)

_BASE_REAL = "https://fapi.binance.com"
_BASE_DEMO = "https://demo-fapi.binance.com"


def _base():
    return _BASE_DEMO if USE_DEMO else _BASE_REAL


def _sign(p):
    p["timestamp"] = int(time.time()*1000)
    p["signature"] = hmac.new(API_SECRET.encode(), urlencode(p).encode(), hashlib.sha256).hexdigest()
    return p


def _hdr():
    return {"X-MBX-APIKEY": API_KEY}


def _get(path, params):
    if DRY_RUN and "/account" not in path and "/positionRisk" not in path:
        pass
    try:
        r = requests.get(_base()+path, params=_sign(params), headers=_hdr(), timeout=10)
        r.raise_for_status(); return r.json()
    except Exception as e:
        logging.warning(f"[exec] GET {path}: {e}"); return None


def _post(path, params):
    if DRY_RUN:
        logging.info(f"[exec] DRY_RUN POST {path} {params}"); return {"dry_run": True}
    try:
        r = requests.post(_base()+path, params=_sign(params), headers=_hdr(), timeout=10)
        r.raise_for_status(); return r.json()
    except Exception as e:
        logging.warning(f"[exec] POST {path}: {e}"); return None


def _delete(path, params):
    if DRY_RUN:
        logging.info(f"[exec] DRY_RUN DELETE {path}"); return {"dry_run": True}
    try:
        r = requests.delete(_base()+path, params=_sign(params), headers=_hdr(), timeout=10)
        r.raise_for_status(); return r.json()
    except Exception as e:
        logging.warning(f"[exec] DELETE {path}: {e}"); return None


# ─── Estado de cuenta ─────────────────────────────────────────────────────────

def get_balance():
    if DRY_RUN:
        return config.CAPITAL_USD
    d = _get("/fapi/v2/account", {"recvWindow": 5000})
    return float(d.get("totalWalletBalance", 0)) if isinstance(d, dict) else None


def get_positions():
    """{symbol: positionAmt} de todas las posiciones abiertas."""
    if DRY_RUN:
        return {}
    d = _get("/fapi/v2/positionRisk", {})
    if not isinstance(d, list):
        return {}
    return {e["symbol"]: float(e["positionAmt"]) for e in d if float(e.get("positionAmt", 0)) != 0}


def book_mid(symbol):
    d = _get("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
    if isinstance(d, dict):
        return (float(d["bidPrice"]) + float(d["askPrice"])) / 2
    return None


# ─── Filtros de precisión por símbolo (exchangeInfo) ──────────────────────────
_FILTERS: dict = {}

def load_filters():
    global _FILTERS
    if _FILTERS:
        return _FILTERS
    d = requests.get(_base()+"/fapi/v1/exchangeInfo", timeout=15).json()
    for s in d.get("symbols", []):
        qp = pp = 0; minq = 0.0; minnot = 5.0
        for f in s["filters"]:
            if f["filterType"] == "LOT_SIZE":
                step = f["stepSize"]; qp = max(0, len(step.rstrip("0").split(".")[1]) if "." in step.rstrip("0") else 0); minq = float(f["minQty"])
            if f["filterType"] == "PRICE_FILTER":
                tick = f["tickSize"]; pp = max(0, len(tick.rstrip("0").split(".")[1]) if "." in tick.rstrip("0") else 0)
            if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
                minnot = float(f.get("notional", f.get("minNotional", 5.0)))
        _FILTERS[s["symbol"]] = dict(qp=qp, pp=pp, minq=minq, minnot=minnot)
    return _FILTERS


# ─── Órdenes ──────────────────────────────────────────────────────────────────

def place_limit_maker(symbol, side, qty, price, qp, pp):
    return _post("/fapi/v1/order", {
        "symbol": symbol, "side": side, "type": "LIMIT", "timeInForce": "GTX",  # post-only = maker
        "quantity": f"{qty:.{qp}f}", "price": f"{price:.{pp}f}",
    })


def cancel_all(symbol):
    return _delete("/fapi/v1/allOpenOrders", {"symbol": symbol})


# ─── Rebalanceo ───────────────────────────────────────────────────────────────

def rebalance(target_weights, equity=None):
    """target_weights: Series pesos objetivo (signed, % del capital, ya con leverage).
    Calcula deltas vs posiciones actuales y coloca órdenes límite maker."""
    equity = equity or get_balance() or config.CAPITAL_USD
    filt = {} if DRY_RUN else load_filters()
    current = get_positions()
    orders = []
    for sym, w in target_weights.items():
        if abs(w) < 1e-4:
            target_notional = 0.0
        else:
            target_notional = w * equity
        price = book_mid(sym) if not DRY_RUN else None
        if price is None and DRY_RUN:
            price = 1.0   # placeholder en dry_run (no se envía)
        target_qty = target_notional / price if price else 0.0
        cur_qty = current.get(sym, 0.0)
        delta = target_qty - cur_qty
        delta_usd = abs(delta) * (price or 0)
        if DRY_RUN:
            if abs(w) > 1e-3:
                logging.info(f"[exec] DRY target {sym}: w={w:+.3f} notional={target_notional:+.0f}USD")
            continue
        if delta_usd < MIN_ORDER_USD or sym not in filt:
            continue
        f = filt[sym]; side = "BUY" if delta > 0 else "SELL"
        # límite ligeramente pasivo para ser maker (post-only rechaza si cruzaría)
        px = price * (1 - 0.0002) if side == "BUY" else price * (1 + 0.0002)
        r = place_limit_maker(sym, side, abs(delta), px, f["qp"], f["pp"])
        orders.append((sym, side, round(abs(delta), f["qp"]), r is not None))
    return orders


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from kepler.engine import compute_target
    target, vp, df, port, asof = compute_target("ESTABLE")
    target = target[target.abs() > 0.005]
    print(f"Modo: {'DRY_RUN' if DRY_RUN else ('DEMO' if USE_DEMO else 'REAL')} · "
          f"objetivo {len(target)} posiciones · datos hasta {str(asof)[:10]}")
    orders = rebalance(target)
    if DRY_RUN:
        print("DRY_RUN — órdenes simuladas (ver log). Sin envíos reales.")
    else:
        for o in orders:
            print(f"  {o[1]} {o[0]} {o[2]}  {'ok' if o[3] else 'FALLO'}")


if __name__ == "__main__":
    main()
