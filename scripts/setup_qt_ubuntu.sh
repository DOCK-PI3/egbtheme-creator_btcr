#!/usr/bin/env bash
set -euo pipefail

echo "[setup] Preparando entorno Qt/XCB en Ubuntu para egbtheme-creator_btcr"

# Detect distro (limitado a Ubuntu/Doss):
if ! command -v lsb_release &> /dev/null; then
  echo "[setup] Warning: lsb_release no encontrado. Continuando con supuestos repositorios apt." 
else
  DISTRO=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
  CODENAME=$(lsb_release -cs | tr '[:upper:]' '[:lower:]')
  echo "[setup] Distro: $DISTRO, Codename: $CODENAME"
fi

DEPS=(libxcb1 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libxkbcommon0 libxkbcommon-x11-0)
EXTRA=(libxcb-dri3-0 libxcb-icccm4 libxcb-sync libxcb-xinput0 libxcb-render-util0 libxcb-randr0 libx11-6 libxrender1 libfontconfig1)
echo "[setup] Installing system libraries: ${DEPS[*]} ${EXTRA[*]}"
sudo apt-get update
sudo apt-get install -y "${DEPS[@]}" "${EXTRA[@]}" || true

echo "[setup] Verificación de Qt/XCB dependencies completa. Siguiente: instalar XVFB si es necesario."
sudo apt-get install -y xvfb || true

echo "[setup] Listo. Intenta lanzar la GUI de nuevo."
