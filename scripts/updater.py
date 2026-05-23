import os
import sys
import tempfile
import subprocess

def main():
    if len(sys.argv) != 3:
        print("Uso: updater.exe <exe_actual> <exe_nuevo>")
        sys.exit(1)

    exe_actual = sys.argv[1]
    exe_nuevo = sys.argv[2]

    # Crear un script batch temporal
    bat_content = f'''@echo off
timeout /t 2 /nobreak > nul
move /Y "{exe_nuevo}" "{exe_actual}" > nul
if errorlevel 1 (
    echo Error: No se pudo reemplazar el archivo.
    pause
) else (
    start "" "{exe_actual}"
)
del "%~f0"
'''
    # Guardar el batch en la carpeta temporal
    bat_path = os.path.join(tempfile.gettempdir(), "update_script.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Ejecutar el batch de forma oculta (sin ventana)
    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

if __name__ == "__main__":
    main()