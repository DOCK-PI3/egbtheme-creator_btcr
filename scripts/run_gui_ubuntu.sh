#!/usr/bin/env bash
set -euo pipefail

echo "[run] Preparing Ubuntu GUI environment for egbtheme-creator_btcr"

# Optional headless mode: ./scripts/run_gui_ubuntu.sh headless
if [ "${1-}" = "headless" ]; then
  echo "[run] Running in headless mode (no GUI) to validate export/logic."
  export QT_QPA_PLATFORM=offscreen
  python3 "$ROOT_DIR/src/main.py"
  exit 0
fi

# Determine repo root (one level up from this script's directory)
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
echo "[run] Repo root: $ROOT_DIR"

# 0) Setup Qt/XCB dependencies if possible
if [ -f "$ROOT_DIR/scripts/setup_qt_ubuntu.sh" ]; then
  echo "[run] Running Qt/XCB setup script..."
  sudo bash "$ROOT_DIR/scripts/setup_qt_ubuntu.sh" || true
fi

# 1) Install essential system dependencies for Qt/X11 (best effort)
DEPS=(libxcb1 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libxkbcommon0 libxkbcommon-x11-0)
EXTRA=(libxcb-dri3-0 libxcb-icccm4 libxcb-sync libxcb-xinput0 libxcb-render-util0 libxcb-randr0 libx11-6 libxrender1 libfontconfig1)
echo "[run] Installing system libraries (this may require sudo): ${DEPS[*]} ${EXTRA[*]}"
sudo apt-get update
sudo apt-get install -y "${DEPS[@]}" "${EXTRA[@]}" xvfb || true

# 2) Setup Python virtual environment and PySide6
if [ ! -d "$ROOT_DIR/venv" ]; then
  python3 -m venv "$ROOT_DIR/venv"
fi
source "$ROOT_DIR/venv/bin/activate"
python -m pip install --upgrade pip
pip install PySide6

# 3) Run the app (GUI if a display is available, otherwise headless via XVFB)
if [ -n "${DISPLAY:-}" ]; then
  echo "[run] Display detected: ${DISPLAY}. Launching GUI."
  export QT_QPA_PLATFORM=xcb
  python3 "$ROOT_DIR/src/main.py"
else
  echo "[run] No display available. Launching with XVFB to simulate a display."
  XVFB_CMD="xvfb-run -a --server-args='-screen 0 1024x768x24'"
  $XVFB_CMD python3 "$ROOT_DIR/src/main.py"
fi
