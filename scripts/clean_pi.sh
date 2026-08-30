#!/bin/bash
# clean_pi.sh - Borra TODO lo instalado por install_pi.sh
# NO borra frases.db ni tokens de Spotify (si los pusiste en /var/lib/turing-display).
#
# Uso:
#   sudo bash scripts/clean_pi.sh

set -e

BUILD_DIR="/opt/turing-build/turing-display-controller"
DEPLOY_DIR="/opt/turing-display-controller"
CONFIG_DIR="/etc/turing-display"
SERVICE="/etc/systemd/system/turing-display.service"
UDEV="/etc/udev/rules.d/99-turing-display.rules"
SERVICE_USER="turing"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: ejecutar con sudo: sudo bash $0"
    exit 1
fi

echo "=== Deteniendo servicio ==="
systemctl stop turing-display.service 2>/dev/null || true
systemctl disable turing-display.service 2>/dev/null || true

echo "=== Borrando unit systemd ==="
rm -f "$SERVICE"
systemctl daemon-reload

echo "=== Borrando binarios ==="
rm -rf "$DEPLOY_DIR" "$BUILD_DIR"

echo "=== Borrando configuracion ==="
rm -rf "$CONFIG_DIR"

echo "=== Borrando regla udev ==="
rm -f "$UDEV"
udevadm control --reload-rules

echo "=== Borrando usuario de servicio ==="
if id "$SERVICE_USER" >/dev/null 2>&1; then
    userdel "$SERVICE_USER" 2>/dev/null || true
fi

echo
echo "=== DESINSTALACION COMPLETA ==="
echo ""
echo "Quedan en la maquina (no se borran automaticamente):"
echo "  - /var/lib/turing-display/    (frases.db, spotify_tokens.db si los pusiste ahi)"
echo "  - El repo clonado (donde ejecutaste install_pi.sh)"
echo ""
echo "Para borrarlos a mano:"
echo "  sudo rm -rf /var/lib/turing-display"
echo "  cd ~ && rm -rf turing-display-controller"
