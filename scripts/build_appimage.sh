#!/bin/bash
set -e

# Build an AppImage for Linux from the PySide6-based app (MVP).
# Requirements: PyInstaller, appimagetool (fallbacks via AppImageKit)

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$DIST_DIR/build"
APPDIR="$ROOT_DIR/AppDir"
APPIMAGE_NAME="egbtheme-creator_btcr.AppImage"

echo "[Build] Packaging AppImage for egbtheme-creator_btcr (MVP)"

mkdir -p "$DIST_DIR"

# 0) Ensure PyInstaller is available (CI environments usually have it; fallback to install if possible)
if ! command -v pyinstaller &> /dev/null; then
  echo "[Info] PyInstaller not found. Trying to install in user space..."
  if command -v python3 &> /dev/null; then
    python3 -m pip install --user pyinstaller
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
EXEC="$APPDIR/usr/bin/egbtheme-creator_btcr"
exec "$EXEC" "$@"
SH
chmod +x "$APPDIR/AppRun"

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
  "$APPIMAGETOOL" "$APPDIR" -n -o "$OUTPUT"
  echo "AppImage generado en: $OUTPUT"
else
  echo "[Warning] appimagetool no disponible. AppDir preparado pero no se generará AppImage en este paso."
fi
