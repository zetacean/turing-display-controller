#!/bin/bash
# install_pi.sh - Instala Turing Display Controller en Orange Pi / Debian.
# Asume que ya hiciste `git clone` y estas en la raiz del repo.
# Todo se hace con sudo. El servicio corre como root, no usa venv.
#
# Uso:
#   cd turing-display-controller
#   sudo bash scripts/install_pi.sh

set -e

# --- rutas ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUILD_DIR="/opt/turing-build/turing-display-controller"
DEPLOY_DIR="/opt/turing-display-controller"
CONFIG_DIR="/etc/turing-display"
CONFIG="$CONFIG_DIR/config.ini"
SERVICE="/etc/systemd/system/turing-display.service"
UDEV="/etc/udev/rules.d/99-turing-display.rules"
SERVICE_USER="turing"

# --- requiere root ---
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: ejecutar con sudo: sudo bash $0"
    exit 1
fi

echo "=== [1/9] Instalar dependencias de sistema ==="
apt update
apt install -y -q git build-essential libusb-1.0-0-dev libudev-dev pkg-config

echo
echo "=== [2/9] Instalar uv (si falta) ==="
if ! command -v uv >/dev/null 2>&1; then
    # uv puede estar en ~/.local/bin del usuario original
    if [[ -n "$SUDO_USER" && -x "/home/$SUDO_USER/.local/bin/uv" ]]; then
        echo "  uv ya esta en /home/$SUDO_USER/.local/bin/uv"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # no se puede usar el path recien instalado porque ya somos root
    fi
fi
# Asegurar uv en PATH para este script
export PATH="$HOME/.local/bin:/home/${SUDO_USER:-root}/.local/bin:$PATH"
uv --version

echo
echo "=== [3/9] Copiar proyecto a $BUILD_DIR y compilar ==="
mkdir -p /opt/turing-build
# copiar excluyendo .git, caches, dist, etc.
rsync -a --delete \
    --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='dist' \
    --exclude='data' --exclude='images' --exclude='cache' \
    "$PROJECT_ROOT/" "$BUILD_DIR/"
chown -R "${SUDO_USER:-root}:${SUDO_USER:-root}" "$BUILD_DIR"

# uv sync + build como el usuario original (no root) si es posible
if [[ -n "$SUDO_USER" ]]; then
    sudo -u "$SUDO_USER" -H bash -c "
        export PATH=\"\$HOME/.local/bin:\$PATH\"
        cd '$BUILD_DIR'
        uv sync
        uv run python scripts/build.py
    "
else
    cd "$BUILD_DIR"
    uv sync
    uv run python scripts/build.py
fi

echo
echo "=== [4/9] Deploy del binario en $DEPLOY_DIR ==="
systemctl stop turing-display.service 2>/dev/null || true
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"
cp -r "$BUILD_DIR/dist/turing-display-controller/." "$DEPLOY_DIR/"
chmod +x "$DEPLOY_DIR/turing-display-controller"
echo "  -> $DEPLOY_DIR/turing-display-controller"

echo
echo "=== [5/9] Usuario de servicio '$SERVICE_USER' ==="
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --shell /usr/sbin/nologin \
        --home "$DEPLOY_DIR" "$SERVICE_USER"
fi

echo
echo "=== [6/9] Reglas udev (CH340/CH341) ==="
cat > "$UDEV" <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7522", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5722", MODE="0666"
EOF
udevadm control --reload-rules
udevadm trigger

echo
echo "=== [7/9] config.ini en $CONFIG_DIR ==="
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG" ]]; then
    if [[ -f "$PROJECT_ROOT/config.ini" ]]; then
        cp "$PROJECT_ROOT/config.ini" "$CONFIG"
    else
        # config minimo por defecto
        cat > "$CONFIG" <<'CFGEOF'
[display]
com_port = /dev/ttyUSB0
brightness = 70
orientation = portrait
reset_on_startup = false

[server]
host = 0.0.0.0
port = 8000

[paths]
# IMPORTANTE: ~/ se expande a /root cuando el servicio corre como root.
# Usa siempre rutas absolutas. /home/<user>/images permite al usuario
# subir fotos por SCP/SFTP sin sudo, y al servicio leerlas como root.
images_dir = /home/orangepi/images
phrases_db = /var/lib/turing-display/phrases.db

[spotify]
enabled = false
client_id =
redirect_uri = http://127.0.0.1:8000/api/spotify/callback
poll_interval_s = 5
CFGEOF
        # Crear la carpeta de imagenes con permisos para el usuario normal
        mkdir -p /home/orangepi/images
        chown -R orangepi:orangepi /home/orangepi/images
    fi
    chmod 644 "$CONFIG"
    chown root:"$SERVICE_USER" "$CONFIG"
    echo "  -> Creado $CONFIG (REVISAR y editar si hace falta)"
else
    echo "  -> Ya existe, sin tocar"
fi

echo
echo "=== [8/9] Unidad systemd ==="
cat > "$SERVICE" <<'EOF'
[Unit]
Description=Turing Smart Display Controller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/turing-display-controller
ExecStart=/opt/turing-display-controller/turing-display-controller
Environment=TD_CONFIG=/etc/turing-display/config.ini
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$SERVICE"
systemctl daemon-reload
systemctl enable turing-display.service

echo
echo "=== [9/9] Arrancar servicio ==="
systemctl restart turing-display.service
sleep 3
if systemctl is-active --quiet turing-display.service; then
    echo "  -> ACTIVO"
else
    echo "  -> FALLO al arrancar (revisar logs abajo)"
fi

echo
echo "=== Estado ==="
systemctl status turing-display.service --no-pager | head -25 || true
echo
echo "--- Logs (ultimas 30 lineas) ---"
journalctl -u turing-display.service -n 30 --no-pager || true

echo
echo "================================================================"
echo "INSTALACION COMPLETA"
echo "Dashboard: http://$(hostname -I | awk '{print $1}'):8000"
echo "Logs en vivo: sudo journalctl -u turing-display.service -f"
echo "Para desinstalar: sudo bash scripts/clean_pi.sh"
echo "================================================================"
