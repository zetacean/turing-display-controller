#!/bin/bash
# clean_pi.sh - Borra TODO lo instalado por install_pi.sh.
#
# Borra:
#   - servicio systemd
#   - binarios en /opt/turing-display-controller/
#   - build cache en /opt/turing-build/
#   - configuracion en /etc/turing-display/
#   - datos persistentes en /var/lib/turing-display/
#   - regla udev del display
#   - usuario de servicio 'turing'
#
# NO borra:
#   - /home/orangepi/images/  (fotos del usuario)
#   - el repo clonado
#
# Ejecutar con sudo:
#   sudo bash scripts/clean_pi.sh

set -e

BUILD_DIR="/opt/turing-build/turing-display-controller"
DEPLOY_DIR="/opt/turing-display-controller"
CONFIG_DIR="/etc/turing-display"
VARLIB_DIR="/var/lib/turing-display"
SERVICE="/etc/systemd/system/turing-display.service"
UDEV="/etc/udev/rules.d/99-turing-display.rules"
SERVICE_USER="turing"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: ejecutar con sudo: sudo bash $0"
    exit 1
fi

echo "=== [1/8] Deteniendo servicio ==="
systemctl stop turing-display.service 2>/dev/null || true
systemctl disable turing-display.service 2>/dev/null || true

echo "=== [2/8] Borrando unit systemd ==="
rm -f "$SERVICE"
systemctl daemon-reload
systemctl reset-failed turing-display.service 2>/dev/null || true

echo "=== [3/8] Borrando binarios ==="
rm -rf "$DEPLOY_DIR"
rm -rf "$BUILD_DIR"

echo "=== [4/8] Borrando configuracion ==="
rm -rf "$CONFIG_DIR"

echo "=== [5/8] Borrando datos persistentes (/var/lib/turing-display) ==="
rm -rf "$VARLIB_DIR"

echo "=== [6/8] Borrando regla udev ==="
rm -f "$UDEV"
udevadm control --reload-rules

echo "=== [7/8] Borrando usuario de servicio ==="
if id "$SERVICE_USER" >/dev/null 2>&1; then
    userdel "$SERVICE_USER" 2>/dev/null || true
fi

echo "=== [8/8] Verificando que no queda nada ==="
remaining=()
[[ -d "$DEPLOY_DIR" ]] && remaining+=("$DEPLOY_DIR")
[[ -d "$BUILD_DIR" ]] && remaining+=("$BUILD_DIR")
[[ -d "$CONFIG_DIR" ]] && remaining+=("$CONFIG_DIR")
[[ -d "$VARLIB_DIR" ]] && remaining+=("$VARLIB_DIR")
[[ -f "$SERVICE" ]] && remaining+=("$SERVICE")
[[ -f "$UDEV" ]] && remaining+=("$UDEV")
id "$SERVICE_USER" >/dev/null 2>&1 && remaining+=("user:$SERVICE_USER")

if [[ ${#remaining[@]} -gt 0 ]]; then
    echo "ADVERTENCIA: aun queda:"
    printf '  - %s\n' "${remaining[@]}"
else
    echo "OK: nada queda en el sistema del Turing Display Controller."
fi

echo
echo "=== DESINSTALACION COMPLETA ==="
echo ""
echo "Conservado (datos del usuario):"
echo "  - /home/orangepi/images/        (fotos subidas)"
echo "  - El repo clonado"
echo ""
echo "Para borrarlos a mano:"
echo "  sudo rm -rf /home/orangepi/images"
echo "  cd ~ && rm -rf turing-display-controller"
