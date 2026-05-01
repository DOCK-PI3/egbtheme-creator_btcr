#!/usr/bin/env bash
set -euo pipefail

echo "[diagnose] Ubuntu GUI environment for egbtheme-creator_btcr"

# 1) Ensure system X11/Qt deps (best-effort for common distros)
RECOMMENDED_DEPS=(libxcb1 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libxkbcommon0 libxkbcommon-x11-0)
echo "[diagnose] You may want to install system libs: ${RECOMMENDED_DEPS[*]}"
read -p "Proceed to install missing system libraries? (y/N) " ans
if [[ "$ans" =~ ^([yY][eE][sS]|[yY])$ ]]; then
  sudo apt update
  sudo apt install -y "${RECOMMENDED_DEPS[@]}" || true
fi

# 2) Setup Python venv and PySide6 if not present
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6 || true

# 3) Run GUI (prefer xcb; fallback to offscreen if display not available)
if [ -n "$DISPLAY" ]; then
  echo "[diagnose] Display detected: $DISPLAY. Attempting GUI launch with XCB plugin."
  export QT_QPA_PLATFORM=xcb
  python3 src/main.py || true
else
  echo "[diagnose] No display detected. Using headless mode for verification."
  export QT_QPA_PLATFORM=offscreen
  python3 src/main.py
fi
