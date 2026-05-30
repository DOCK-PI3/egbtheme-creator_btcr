import os
import sys
import tempfile
import subprocess
import zipfile

def main():
    if len(sys.argv) != 3:
        print("Uso: updater.exe <exe_actual> <zip_descargado>")
        sys.exit(1)

    exe_actual = sys.argv[1]
    zip_path = sys.argv[2]

    install_dir = os.path.dirname(exe_actual)
    temp_extract_dir = tempfile.mkdtemp(prefix="egb_update_")

    try:
        # 1. Extraer ZIP en carpeta temporal
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_extract_dir)

        # 2. Detectar si el ZIP tiene una única carpeta raíz (problema de estructura)
        items = os.listdir(temp_extract_dir)
        if len(items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, items[0])):
            source_dir = os.path.join(temp_extract_dir, items[0])
        else:
            source_dir = temp_extract_dir

        # 3. Crear script batch temporal
        bat_content = f'''@echo off
:: Esperar a que el proceso original libere los archivos
timeout /t 3 /nobreak > nul

:: Copiar todo el contenido (sobrescribiendo)
xcopy /E /I /Y "{source_dir}\\*" "{install_dir}\\"

:: Si xcopy falla, reintentar con robocopy (más robusto)
if errorlevel 1 (
    robocopy "{source_dir}" "{install_dir}" /E /IS /IT /R:5 /W:2
)

:: Lanzar la aplicación actualizada
start "" "{exe_actual}"

:: Limpiar carpeta temporal del ZIP
rmdir /S /Q "{temp_extract_dir}" 2>nul
:: Eliminar el propio script batch
del "%~f0"
'''
        # Guardar batch en la carpeta temporal del sistema
        bat_path = os.path.join(tempfile.gettempdir(), "update_script.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # 4. Ejecutar el batch de forma oculta
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )

        # 5. Salir inmediatamente (el batch continuará en segundo plano)
        sys.exit(0)

    except Exception as e:
        # Registrar error en log
        with open(os.path.join(tempfile.gettempdir(), "updater_error.log"), "w") as f:
            f.write(str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()