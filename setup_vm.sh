#!/usr/bin/env bash
# setup_vm.sh — Instala Kepler en la VM (ejecutar UNA sola vez).
# Antes: git clone <repo> /opt/kepler-app/kepler
# Uso:   cd /opt/kepler-app/kepler && sudo bash setup_vm.sh
set -euo pipefail

APP_DIR="/opt/kepler-app"
GIT_DIR="${APP_DIR}/kepler"
VENV="${APP_DIR}/venv"
ENV_FILE="/etc/kepler.env"

echo "═══════════════════════════════════════════════════════"
echo "  KEPLER — SETUP VM (primera vez)"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "[1/6] Entorno virtual + dependencias..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$GIT_DIR/requirements.txt"
echo "  ✓ venv y dependencias instaladas"

echo ""
echo "[2/6] Archivo de entorno ($ENV_FILE)..."
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<'EOF'
# Credenciales Binance (demo/testnet o real)
BINANCE_API_KEY=REEMPLAZAR
BINANCE_API_SECRET=REEMPLAZAR
# Modo: DRY_RUN=true (no opera) · para demo poner false + USE_DEMO=true
KEPLER_DRY_RUN=true
KEPLER_USE_DEMO=true
DASHBOARD_PORT=8080
EOF
    chmod 600 "$ENV_FILE"
    echo "  ✓ Creado. EDITA $ENV_FILE con tus API keys."
else
    echo "  ✓ Ya existe (no se sobrescribe)"
fi

echo ""
echo "[3/6] Descargando datos históricos (1h + funding del universo)..."
cd "$GIT_DIR"
"$VENV/bin/python" -m kepler.fetch 1h
echo "  ✓ Datos en $GIT_DIR/data"

echo ""
echo "[4/6] Instalando servicios systemd..."
cp "$GIT_DIR/kepler.service" /etc/systemd/system/kepler.service
cp "$GIT_DIR/kepler-api.service" /etc/systemd/system/kepler-api.service
systemctl daemon-reload
systemctl enable kepler kepler-api
echo "  ✓ Servicios kepler y kepler-api habilitados"

echo ""
echo "[5/6] Abriendo puerto 8080 (dashboard)..."
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=8080/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi
echo "  ⚠ Abre también el 8080 en la consola del proveedor (Oracle VCN/Security List)"

echo ""
echo "[6/6] Arrancando..."
systemctl restart kepler kepler-api
sleep 2
IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo "<ip-vm>")

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SETUP COMPLETO"
echo "  kepler:     $(systemctl is-active kepler 2>/dev/null || echo '?')"
echo "  kepler-api: $(systemctl is-active kepler-api 2>/dev/null || echo '?')"
echo "  Dashboard:  http://${IP}:8080"
echo ""
echo "  1) Edita $ENV_FILE con tus API keys (y KEPLER_DRY_RUN=false para operar en demo)"
echo "  2) Futuros deploys: bash /opt/kepler-app/kepler/deploy.sh"
echo "═══════════════════════════════════════════════════════"
