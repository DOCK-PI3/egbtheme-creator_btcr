# Build plan (AppImage + Windows)

- Prerequisitos:
- Linux: Python3, PyInstaller, appimagetool (opcional para AppImage)
- Windows: Python3, PyInstaller

- Pasos:
- 1) Instalar dependencias: pip install -r requirements.txt
- 2) Crear ejecutable con PyInstaller: python -m PyInstaller src/main.py --name egbtheme-creator_btcr --onefile
- 3) Para Linux, ejecutar build_appimage.sh para generar AppDir y opcionalmente AppImage
- 4) Para Windows, ejecutar build_windows.ps1 para generar exe
- 5) Verificar que la exportación de temas funcione: usa la UI para exportar y revisa themes_export

Notas:
- Este es un MVP de empaquetado. Ajustes de dependencias pueden requerir bundling de Qt runtimes.
- La ruta de salida puede ajustarse en el script de empaquetado; por ahora usa dist/ y AppDir/ para AppImage.
