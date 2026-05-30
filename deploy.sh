#!/usr/bin/env bash
# deploy.sh — Actualiza Kepler y reinicia los servicios. Un solo comando.
# Uso (desde la VM, desde cualquier directorio):
#   bash /opt/kepler-app/kepler/deploy.sh
set -euo pipefail

APP_DIR="/opt/kepler-app"
GIT_DIR="${APP_DIR}/kepler"
PYTHON="${APP_DIR}/venv/bin/python"

cd "$GIT_DIR"
git config --global --add safe.directory "$GIT_DIR" 2>/dev/null || true
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  KEPLER DEPLOY  —  $(date '+%Y-%m-%d %H:%M') UTC"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "[1/5] Sincronizando con GitHub..."
git pull
echo "  ✓ Código actualizado"

echo ""
echo "[2/5] Dependencias Python..."
$PYTHON -m pip install --quiet -r requirements.txt 2>/dev/null || true
echo "  ✓ Dependencias OK"

echo ""
echo "[3/5] Verificación rápida (import del paquete)..."
if $PYTHON -c "import config; from kepler import orchestrator, engine, execution, api" 2>/dev/null; then
    echo "  ✓ Paquete importa correctamente"
else
    echo "  ✗ Error de import — abortando deploy"; exit 1
fi

echo ""
echo "[4/5] Reiniciando orquestador (kepler)..."
sudo systemctl restart kepler && sleep 2
[ "$(systemctl is-active kepler 2>/dev/null)" = "active" ] \
    && echo "  ✓ kepler activo" \
    || echo "  ✗ kepler no arrancó — journalctl -u kepler -n 30"

echo ""
echo "[5/5] Reiniciando dashboard (kepler-api)..."
sudo systemctl restart kepler-api && sleep 2
if [ "$(systemctl is-active kepler-api 2>/dev/null)" = "active" ]; then
    IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo "<ip-vm>")
    echo "  ✓ kepler-api activo  →  Dashboard: http://${IP}:8080"
else
    echo "  ✗ kepler-api no arrancó — journalctl -u kepler-api -n 30"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  kepler:     $(systemctl is-active kepler     2>/dev/null || echo '?')  (modo: ${KEPLER_DRY_RUN:-?} dry / ${KEPLER_USE_DEMO:-?} demo)"
echo "  kepler-api: $(systemctl is-active kepler-api 2>/dev/null || echo '?')"
echo "═══════════════════════════════════════════════════════"
echo ""
