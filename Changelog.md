# Creador y editor visual de themes para Batocera/Retrobat EmulationStation

## Changelog

### v0.8.5 Beta (2026-05-24)

```bash
- Cambio de nombre de pestaña "Constructor Visual" a "Editor Visual"
- Añadidos menús, iconos y atajos de teclado para las acciones más comunes, iconos en la barra de herramientas
- Mejoras en el sistema de actualización del programa
- Mejorado el parseo de XML, así como del verificador de código XML, con mensajes de error si los hubiera
- Importar themes, crear theme desde cero, explorador de theme
- Mejoras en el canvas (redimensionamiento con raton, desplazamiento de elementos)
- Añadidas reglas para mejorar el posicionamiento y dimensión de los elementos en la vista, con opcion de 
  desactivarlas desde el menu "Ver"
- FIXED: bug arreglado que no añadía elementos a la vista
```

### v0.5.0 Beta (2026-05-01)

```bash
- GUI PySide6 con 5 tabs: Editor XML, Constructor Visual, Vista Previa, Theme Set, Empaquetar
- Constructor visual drag&drop con canvas 1280x720 (coordenadas normalizadas Batocera)
- Undo/Redo completo (Ctrl+Z/Ctrl+Y) con QUndoStack
- Soporte customView con herencia de vistas
- Panel de includes en editor XML
- Theme Set multi-sistema (snes, nes, megadrive, psx, etc.)
- Exportacion correcta a formato Batocera theme.xml v7
- Tab de empaquetado AppImage y Windows
- Resaltado de sintaxis XML
- Guia de usuario completa (guia_usuario.md)
- Añadido botón 📁 en Constructor Visual para cambiar la
  carpeta de assets en tiempo de ejecución (necesario en AppImage)
- Actualización automática del programa
```