# Creador y editor visual de themes para Batocera/Retrobat EmulationStation

## Changelog

### v0.9.0 Beta (2026-05-30)

```bash
- Añadido splash screen al iniciar la aplicación
- Añadida creación de archivo de log para detección de errores y seguimiento de eventos
- Optimización del código y mejoras de rendimiento
- Mejora en el sistema de actualizaciones
- Habilitación/deshabilitación de botones y su funcionamiento según el contexto 
  (Ej: no se puede guardar si no hay cambios)
- Añadido menú "Ayuda" con opciones Ver novedades, Buscar actualizaciones y Acerca de
- Mejoras en la identificación de etiquetas de los XML
- Añadido botón para eliminar el elemento seleccionado
- Añadida opción de borrar propiedades de un elemento
- Añadidas pestañas de "Theme Assets" e "Internal Assets" para mostrar los assets disponibles 
  en la aplicación y en el theme respectivamente
- FIXES:
  + Corrección logo => si no existe el logo del sistema de ejemplo .svg, carga el .png si existe
  + Corrección cálculo de tamaño para md_image cuando tiene minSize o maxSize. 
    Establecido ancho y alto en 320x240 para mejor orientación
  + Corrección de posicionamiento del elemento cuando no tiene <origin>
  + Mejora en el cálculo de la representación (rectángulo) de "md_video" cuando usa <size>
  + Al arrastrar un asset a la vista, ahora sí se aplica el cambio y se muestra en el listado
    "Elementos en la vista"
```

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