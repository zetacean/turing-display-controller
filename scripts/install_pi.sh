#!/bin/bash
# install_pi.sh - Instala Turing Display Controller en Orange Pi / Debian.
#
# Asume que ya hiciste `git clone` y estas en la raiz del repo.
# Todo se hace con sudo. El servicio corre como root, no usa venv.
#
# Instala:
#   - dependencias apt (build, libusb, libudev, pkg-config)
#   - fuentes TTF (fonts-liberation, fonts-dejavu-core)
#   - uv (si falta)
#   - compila el binario con PyInstaller
#   - deploya en /opt/turing-display-controller/
#   - usuario de servicio 'turing'
#   - regla udev CH340/CH341
#   - config.ini en /etc/turing-display/
#   - /var/lib/turing-display/ (datos persistentes: frases.db, tokens)
#   - /home/orangepi/images/ (carpeta para subir fotos por SCP)
#   - unidad systemd turing-display.service
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
VARLIB_DIR="/var/lib/turing-display"
CONFIG="$CONFIG_DIR/config.ini"
SERVICE="/etc/systemd/system/turing-display.service"
UDEV="/etc/udev/rules.d/99-turing-display.rules"
SERVICE_USER="turing"
USER_IMAGES="/home/orangepi/images"

# --- requiere root ---
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: ejecutar con sudo: sudo bash $0"
    exit 1
fi

echo "=== [1/11] Instalar dependencias de sistema (apt) ==="
apt update
apt install -y -q git build-essential libusb-1.0-0-dev libudev-dev pkg-config rsync

echo
echo "=== [2/11] Instalar fuentes TTF (Liberation + DejaVu) ==="
# Sin fuentes TTF, el binario cae a PIL default de 8x8 px (ilegible).
apt install -y -q fonts-liberation fonts-dejavu-core

echo
echo "=== [3/11] Instalar uv (si falta) ==="
if ! command -v uv >/dev/null 2>&1; then
    if [[ -n "$SUDO_USER" && -x "/home/$SUDO_USER/.local/bin/uv" ]]; then
        echo "  uv ya esta en /home/$SUDO_USER/.local/bin/uv"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
fi
export PATH="$HOME/.local/bin:/home/${SUDO_USER:-root}/.local/bin:$PATH"
uv --version

echo
echo "=== [4/11] Copiar proyecto a $BUILD_DIR y compilar ==="
mkdir -p /opt/turing-build
rsync -a --delete \
    --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='dist' \
    --exclude='data' --exclude='images' --exclude='cache' \
    "$PROJECT_ROOT/" "$BUILD_DIR/"
chown -R "${SUDO_USER:-root}:${SUDO_USER:-root}" "$BUILD_DIR"

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
echo "=== [5/11] Deploy del binario en $DEPLOY_DIR ==="
systemctl stop turing-display.service 2>/dev/null || true
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"
cp -r "$BUILD_DIR/dist/turing-display-controller/." "$DEPLOY_DIR/"
chmod +x "$DEPLOY_DIR/turing-display-controller"
echo "  -> $DEPLOY_DIR/turing-display-controller"

echo
echo "=== [6/11] Usuario de servicio '$SERVICE_USER' ==="
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --shell /usr/sbin/nologin \
        --home "$DEPLOY_DIR" "$SERVICE_USER"
fi

echo
echo "=== [7/11] Reglas udev (CH340/CH341) ==="
cat > "$UDEV" <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7522", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5722", MODE="0666"
EOF
udevadm control --reload-rules
udevadm trigger

echo
echo "=== [8/11] Carpetas de datos ==="
# Carpeta para fotos del usuario (accesible por SCP/SFTP sin sudo)
mkdir -p "$USER_IMAGES"
chown -R orangepi:orangepi "$USER_IMAGES" 2>/dev/null || true
chmod 755 "$USER_IMAGES"
# Carpeta para frases.db y spotify_tokens.db
mkdir -p "$VARLIB_DIR"
chown root:"$SERVICE_USER" "$VARLIB_DIR"
chmod 775 "$VARLIB_DIR"

echo
echo "=== [9/11] config.ini en $CONFIG_DIR ==="
mkdir -p "$CONFIG_DIR"

# REGLA: si el repo trae config.ini (con client_id de Spotify, etc.),
# SIEMPRE copiarlo a /etc/turing-display/config.ini. Solo usar el heredoc
# como fallback si el repo NO trae config.ini.
if [[ -f "$PROJECT_ROOT/config.ini" ]]; then
    cp "$PROJECT_ROOT/config.ini" "$CONFIG"
    chmod 644 "$CONFIG"
    chown root:"$SERVICE_USER" "$CONFIG"
    echo "  -> Copiado desde repo: $PROJECT_ROOT/config.ini"
    echo "     (incluye client_id de Spotify, com_port, etc.)"
else
    # Fallback: heredoc con valores por defecto. Rutas absolutas
    # (~/ se expande a /root cuando el servicio corre como root).
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
images_dir = /home/orangepi/images
phrases_db = /var/lib/turing-display/phrases.db

[spotify]
enabled = false
client_id =
redirect_uri = http://127.0.0.1:8000/api/spotify/callback
poll_interval_s = 5
CFGEOF
    chmod 644 "$CONFIG"
    chown root:"$SERVICE_USER" "$CONFIG"
    echo "  -> Creado config por defecto (repo no trae config.ini)"
    echo "     AVISO: client_id de Spotify vacio. Edita $CONFIG para anadirlo."
fi

echo
echo "=== [10/11] Unidad systemd ==="
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
echo "=== [11/11] Arrancar servicio y verificar ==="
systemctl restart turing-display.service
sleep 3
if systemctl is-active --quiet turing-display.service; then
    echo "  -> ACTIVO"
else
    echo "  -> FALLO al arrancar (revisar logs abajo)"
fi

echo
echo "=== Estado del servicio ==="
systemctl status turing-display.service --no-pager | head -25 || true
echo
echo "--- Logs (ultimas 20 lineas) ---"
journalctl -u turing-display.service -n 20 --no-pager || true

echo
echo "=== Resumen de paths clave ==="
printf '  Binario:       %s\n' "$DEPLOY_DIR/turing-display-controller"
printf '  Config:        %s\n' "$CONFIG"
printf '  Datos (DBs):   %s\n' "$VARLIB_DIR"
printf '  Fotos:         %s\n' "$USER_IMAGES"
printf '  Servicio:      %s\n' "$SERVICE"
printf '  Regla udev:    %s\n' "$UDEV"

echo
echo "================================================================"
echo "INSTALACION COMPLETA"
echo "Dashboard: http://$(hostname -I | awk '{print $1}'):8000"
echo "Para subir fotos: scp foto.jpg orangepi@$(hostname -I | awk '{print $1}'):/home/orangepi/images/"
echo "Logs en vivo: sudo journalctl -u turing-display.service -f"
echo "Para desinstalar: sudo bash scripts/clean_pi.sh"
echo "================================================================"
