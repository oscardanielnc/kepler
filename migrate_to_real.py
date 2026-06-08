"""
Kepler — MIGRACIÓN DEMO → REAL (sub-cuenta $250).

Qué hace (idempotente y seguro):
  1. ARCHIVA la DB actual completa  → kepler_demo_archive_<YYYYMMDD_HHMM>.db  (nada se pierde).
  2. RESETEA a cero las tablas OPERATIVAS de la DB viva (curva, trades, reportes, auditoría)
     → el frontend arranca el track REAL desde $250, sin mezclar con el demo buggeado.
  3. CONSERVA intacta la tabla `shadow_signal` → el hilo de sombras sigue CONTINUO
     (clave para el análisis e33 ~31-jul, que necesita 60-90d seguidos).

Correr SOLO con el servicio kepler DETENIDO:
    sudo systemctl stop kepler
    /opt/kepler-app/venv/bin/python /opt/kepler-app/kepler/migrate_to_real.py --yes
    (sin --yes hace dry-run y solo muestra qué haría)

Reversible: el archivo demo queda como copia íntegra; si algo sale mal, se restaura con un cp.
"""
from __future__ import annotations
import os, sys, shutil, sqlite3, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa

# Tablas operativas que se VACÍAN para arrancar el track real desde cero.
CLEAR_TABLES = [
    "signals", "trades", "portfolio_snapshot",
    "equity_daily", "equity_tick", "daily_report", "audit_event",
]
# Tabla que se CONSERVA (sombras = independientes del broker, hilo continuo).
KEEP_TABLES = ["shadow_signal"]


def main(apply: bool):
    db = config.DB_PATH
    if not os.path.exists(db):
        print(f"✗ No existe la DB en {db} — nada que migrar.")
        sys.exit(1)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    archive = db.replace(".db", f"_demo_archive_{stamp}.db")

    con = sqlite3.connect(db)
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def count(t): return con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in have else 0

    print("── Estado actual de la DB ──")
    for t in CLEAR_TABLES + KEEP_TABLES:
        tag = "→ se VACÍA" if t in CLEAR_TABLES else "→ se CONSERVA"
        print(f"  {t:20s} {count(t):8d} filas   {tag}")
    print(f"\nArchivo demo (copia íntegra) → {archive}")

    if not apply:
        print("\n[DRY-RUN] No se ha tocado nada. Re-ejecuta con --yes para aplicar.")
        con.close(); return

    # 1) Archivar copia íntegra ANTES de tocar nada.
    con.close()
    shutil.copy2(db, archive)
    print(f"\n✓ Archivado: {archive}")

    # 2) Vaciar tablas operativas (conserva shadow_signal).
    con = sqlite3.connect(db)
    for t in CLEAR_TABLES:
        if t in have:
            con.execute(f"DELETE FROM {t}")
    con.commit()
    con.execute("VACUUM")
    con.commit()

    print("\n── DB viva tras el reseteo (track REAL desde cero) ──")
    for t in CLEAR_TABLES + KEEP_TABLES:
        print(f"  {t:20s} {count(t):8d} filas")
    con.close()
    print("\n✓ Migración OK. La curva real arrancará en $250 al primer ciclo. Sombras intactas.")
    print("  Siguiente: actualizar /etc/kepler.env (USE_DEMO=false, keys reales) y arrancar el servicio.")


if __name__ == "__main__":
    main(apply="--yes" in sys.argv)
