# egbtheme-creator_btcr

Este proyecto es una herramienta de edición de themes para Batocera EmulationStation, con PySide6 (Qt) y Python en backend. Soporta dos estructuras de theme iniciales (A y B), editor XML, drag & drop de assets y una vista previa MVP. El objetivo es generar temas compatibles para Batocera, empaquetados como binarios ejecutables en Windows y AppImage en Linux.

Notas de empaquetado rápidas:
- Linux: AppImage (con appimagetool) o similar a modo de distribución portable.
- Windows: ejecutable (.exe) con posible instalador NSIS más adelante.
- El proyecto ya incluye scripts para packaging: scripts/build_appimage.sh y scripts/build_windows.ps1.

Guía rápida de uso:
- Editor XML: crea o modifica theme.xml (estructura A o B).
- Drag & Drop: añade assets desde la carpeta assets/ hacia la zona de canvas; ajusta posición y tamaño desde el inspector.
- Vista previa: ventana de render simplificado para ver la composición.
- Exportar Tema: genera theme.xml en themes_export/nombre/ con assets copiados y README_export.md.
