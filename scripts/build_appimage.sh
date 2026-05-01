#!/bin/bash
set -e

# Build an AppImage for Linux from the PySide6-based app (MVP).
# Requirements: PyInstaller, appimagetool (fallbacks via AppImageKit)

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)

# Activate the project venv so its pyinstaller (using system Python with --enable-shared)
# takes precedence over ~/.local/bin/pyinstaller (which uses a custom Python without shared lib).
VENV_DIR="$ROOT_DIR/.venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  echo "[Info] Activated project venv: $VENV_DIR"
else
  echo "[Warning] No .venv found at $VENV_DIR; using system Python."
fi

DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$DIST_DIR/build"
APPDIR="$ROOT_DIR/AppDir"
APPIMAGE_NAME="egbtheme-creator_btcr.AppImage"

echo "[Build] Packaging AppImage for egbtheme-creator_btcr (MVP)"

mkdir -p "$DIST_DIR"

# 0) Ensure PyInstaller is available
# Use the venv's pyinstaller if present; otherwise fall back to installing it into the venv.
if ! command -v pyinstaller &> /dev/null; then
  echo "[Info] PyInstaller not found. Trying to install into the active Python environment..."
  if command -v python3 &> /dev/null; then
    python3 -m pip install pyinstaller
  fi
fi

if ! command -v pyinstaller &> /dev/null; then
  echo "[Error] PyInstaller still not found. Aborting AppImage build."
  exit 1
fi

# 1) Crear ejecutable único con PyInstaller
pyinstaller --noconfirm --onefile --windowed --name "egbtheme-creator_btcr" --distpath "$DIST_DIR" --workpath "$BUILD_DIR" src/main.py
BIN_PATH="$DIST_DIR/egbtheme-creator_btcr"
if [ ! -f "$BIN_PATH" ]; then
  echo "[Error] No se encontró el binario generado por PyInstaller en $BIN_PATH" >&2
  exit 1
fi

# 2) Preparar AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp "$BIN_PATH" "$APPDIR/usr/bin/egbtheme-creator_btcr"

# AppRun script (ejecuta el binario desde /usr/bin)
cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
EXEC="$HERE/usr/bin/egbtheme-creator_btcr"
exec "$EXEC" "$@"
SH
chmod +x "$APPDIR/AppRun"

# Archivo .desktop (requerido por appimagetool)
cat > "$APPDIR/egbtheme-creator_btcr.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=EGB Theme Creator
Comment=Theme creator for Batocera/EmulationStation
Exec=egbtheme-creator_btcr
Icon=egbtheme-creator_btcr
Categories=Utility;
Terminal=false
DESKTOP

# Ícono en la raíz del AppDir (requerido por appimagetool)
ICON_SRC="$ROOT_DIR/assets/logo_BATOCERA_WIKI.png"
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$APPDIR/egbtheme-creator_btcr.png"
else
  # Fallback: crear un ícono mínimo de 1x1 px si no hay ninguno disponible
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' > "$APPDIR/egbtheme-creator_btcr.png"
fi

# Intentar descargar appimagetool si no está disponible
APPIMAGETOOL=""
if command -v appimagetool &> /dev/null; then
  APPIMAGETOOL="appimagetool"
else
  echo "[Info] appimagetool no encontrado. Intentando descargar AppImageKit..."
  if command -v curl &> /dev/null; then
    curl -L -o appimagetool.AppImage https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool.AppImage
    APPIMAGETOOL="./appimagetool.AppImage"
  fi
fi

if [ -n "$APPIMAGETOOL" ]; then
  echo "[Build] Generando AppImage..."
  OUTPUT="$ROOT_DIR/dist/$APPIMAGE_NAME"
  # APPIMAGE_EXTRACT_AND_RUN=1 evita requerir FUSE (libfuse.so.2) en el host
  APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" -n "$APPDIR" "$OUTPUT"
  echo "AppImage generado en: $OUTPUT"
else
  echo "[Warning] appimagetool no disponible. AppDir preparado pero no se generará AppImage en este paso."
fi
