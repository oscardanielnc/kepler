"""Helper Dune API (free tier): crear query pública -> ejecutar -> pollear por execution_id -> filas.
NO archiva en timeout (para recuperar resultados tardíos). Free tier encola, dar wait generoso."""
from __future__ import annotations
import os, sys, time, json, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_K = open(os.path.join(config.DATA_DIR, ".dune_key")).read().strip()
_H = {"X-Dune-API-Key": _K, "Content-Type": "application/json"}
_BASE = "https://api.dune.com/api/v1"


def execute(sql: str, name="kepler_q", perf="free"):   # free tier: performance DEBE ser 'free'
    """Crea query pública + lanza ejecución. Devuelve (query_id, execution_id)."""
    q = requests.post(f"{_BASE}/query", headers=_H,
                      data=json.dumps({"name": name, "query_sql": sql, "is_private": False}), timeout=60).json()
    qid = q.get("query_id")
    if not qid:
        return None, {"error": q}
    e = requests.post(f"{_BASE}/query/{qid}/execute", headers=_H,
                      data=json.dumps({"performance": perf}), timeout=60).json()
    return qid, e.get("execution_id")


def fetch(execution_id, wait=120, poll=6):
    """Pollea por execution_id. Devuelve filas (list) o dict de estado/error."""
    t0 = time.time()
    while time.time() - t0 < wait:
        r = requests.get(f"{_BASE}/execution/{execution_id}/results", headers=_H, timeout=60).json()
        st = r.get("state", "")
        if st == "QUERY_STATE_COMPLETED":
            return r["result"]["rows"]
        if "FAILED" in st or "CANCELLED" in st:
            return {"error": st, "detail": str(r)[:300]}
        time.sleep(poll)
    return {"error": "timeout", "execution_id": execution_id}


def archive(qid):
    try: requests.post(f"{_BASE}/query/{qid}/archive", headers=_H, timeout=30)
    except Exception: pass


def run_sql(sql, name="kepler_q", wait=120, perf="free"):
    qid, eid = execute(sql, name, perf)
    if not eid or isinstance(eid, dict):
        return {"error": "execute_failed", "detail": eid}
    rows = fetch(eid, wait=wait)
    if isinstance(rows, list):       # éxito → archivar para no acumular queries
        archive(qid)
    return rows


if __name__ == "__main__":
    print(run_sql("select 1 as x", wait=60))
