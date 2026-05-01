#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
echo "[run] App start: root=$ROOT_DIR"

# 0) Prepare log mechanism to capture errors and outputs
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/egbtheme_run_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
echo "[run] Logging to $LOG_FILE"
# Redirect stdout and stderr to log, while also keeping live output to console
exec > >(tee -a "$LOG_FILE") 2>&1

# 1) Install essential system dependencies for Qt/X11 (best effort)
DEPS=(libxcb1 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libxkbcommon0 libxkbcommon-x11-0)
EXTRA=(libxcb-dri3-0 libxcb-icccm4 libxcb-sync libxcb-xinput0 libxcb-render-util0 libxcb-randr0 libx11-6 libxrender1 libfontconfig1)
echo "[run] Installing system libraries: ${DEPS[*]} ${EXTRA[*]}"
sudo apt-get update
sudo apt-get install -y "${DEPS[@]}" "${EXTRA[@]}" xvfb || true

# 2) Setup Python virtual environment and PySide6
if [ ! -d "$ROOT_DIR/venv" ]; then
  python3 -m venv "$ROOT_DIR/venv"
fi
source "$ROOT_DIR/venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install --upgrade PySide6 || true

# 3) Ensure PySide6 import works
python - <<'PY'
import sys
try:
  import PySide6
  print("PySide6 OK inside script check")
except Exception as e:
  print("Import error for PySide6:", e)
  sys.exit(1)
PY

# 4) Run GUI if display available; else use XVFB
if [ -n "${DISPLAY:-}" ]; then
  echo "[run] Display ${DISPLAY} detected. Launching GUI"
  export QT_QPA_PLATFORM=xcb
  python3 "$ROOT_DIR/src/main.py"
else
  echo "[run] No display detected. Launching with XVFB"
  if ! command -v xvfb-run &> /dev/null; then
    echo "[run] Installing XVFB..."
    sudo apt-get update
    sudo apt-get install -y xvfb
  fi
  XVFB_CMD="xvfb-run -a --server-args='-screen 0 1024x768x24'"
  $XVFB_CMD python3 "$ROOT_DIR/src/main.py"
fi
