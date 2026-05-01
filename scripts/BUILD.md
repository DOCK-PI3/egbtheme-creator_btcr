# Guía de compilación y ejecución

Instrucciones para ejecutar en desarrollo y generar binarios distribuibles (AppImage en Linux, .exe en Windows).

---

## Ejecución en desarrollo (sin compilar)

### Linux

1. Instala Python 3.10 o superior:
   ```bash
   sudo apt install python3 python3-pip   # Debian/Ubuntu/Mint
   ```

2. Crea un entorno virtual e instala dependencias:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Lanza la aplicación:
   ```bash
   python3 src/main.py
   ```

### Windows

1. Descarga e instala Python 3.10+ desde https://www.python.org/downloads/  
   Marca la opción **"Add Python to PATH"** durante la instalación.

2. Crea un entorno virtual e instala dependencias:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Lanza la aplicación:
   ```powershell
   python src\main.py
   ```

---

## Compilar a binario ejecutable

### Linux — AppImage

**Requisitos previos:**
```bash
pip install pyinstaller
sudo apt install fuse   # necesario para ejecutar AppImages
# appimagetool — el script lo descarga automáticamente si no está disponible
```

**Pasos:**
```bash
cd /ruta/al/proyecto
source .venv/bin/activate
chmod +x scripts/build_appimage.sh
bash scripts/build_appimage.sh
```

**Resultado:** `dist/egbtheme-creator_btcr.AppImage`

Para ejecutarlo en cualquier Linux:
```bash
chmod +x egbtheme-creator_btcr.AppImage
./egbtheme-creator_btcr.AppImage
```

> También puedes usar el botón **"Crear AppImage"** en el tab **Empaquetar** de la propia aplicación.

---

### Windows — Ejecutable .exe

**Requisitos previos:**
- Python 3.10+ instalado con pip
- PowerShell (incluido en Windows 10/11)

**Pasos:**

1. Instala las dependencias (si no lo has hecho):
   ```powershell
   pip install -r requirements.txt
   ```

2. Ejecuta el script de build desde la raíz del proyecto:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\scripts\build_windows.ps1
   ```

**Resultado:** `dist\egbtheme-creator_btcr.exe`

Haz doble clic en el `.exe` para ejecutarlo — no requiere tener Python instalado en el equipo destino.

> También puedes copiar el script al portapapeles usando el botón **"Copiar script build_windows.ps1"** en el tab **Empaquetar** de la aplicación y pegarlo directamente en PowerShell.

---

## Notas

- El ejecutable generado incluye Python y PySide6 embebidos (~80-120 MB es normal para apps PySide6).
- Los directorios `AppDir/` y `build/` son temporales; solo `dist/` contiene el binario final.
- Si PyInstaller falla por dependencias ocultas de Qt, añade estas opciones al comando:
  ```
  --hidden-import PySide6.QtSvg --hidden-import PySide6.QtXml
  ```
- Los themes exportados se guardan en la carpeta que elijas desde la UI — son completamente independientes del binario de la aplicación.
