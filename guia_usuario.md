# Guía de Usuario — egbtheme-creator_btcr

Creador visual de temas para **Batocera EmulationStation** (formato `theme.xml` v7).

---

## Índice

1. [Requisitos e instalación](#1-requisitos-e-instalación)
2. [Lanzar la aplicación](#2-lanzar-la-aplicación)
3. [Interfaz principal](#3-interfaz-principal)
4. [Tab 1 — Editor XML](#4-tab-1--editor-xml)
5. [Tab 2 — Editor Visual](#5-tab-2--constructor-visual)
6. [Tab 3 — Vista Previa](#6-tab-3--vista-previa)
7. [Tab 4 — Theme Set (multi-sistema)](#7-tab-4--theme-set-multi-sistema)
8. [Tab 5 — Empaquetar](#8-tab-5--empaquetar)
9. [Exportar e instalar en Batocera](#9-exportar-e-instalar-en-batocera)
10. [Estructura de un tema Batocera](#10-estructura-de-un-tema-batocera)
11. [Tipos de elementos soportados](#11-tipos-de-elementos-soportados)
12. [Flujo de trabajo recomendado](#12-flujo-de-trabajo-recomendado)
13. [Atajos de teclado](#13-atajos-de-teclado)
14. [Preguntas frecuentes](#14-preguntas-frecuentes)

---

## 1. Requisitos e instalación

| Requisito | Versión mínima |
|-----------|---------------|
| Python    | 3.11 o superior |
| PySide6   | 6.5 o superior  |

### Instalación rápida en Linux

```bash
# Instalar PySide6 (si no está disponible en python del sistema)
pip install PySide6

# O usando un Python local
~/.local/python3.13/bin/pip3 install PySide6
```

### Instalación en Windows

```powershell
pip install PySide6
```

### Dependencias del proyecto

```bash
pip install -r requirements.txt
```

---

## 2. Lanzar la aplicación

```bash
# Desde la carpeta raíz del proyecto
python3 src/main.py

# En Linux con servidor de pantalla explícito
DISPLAY=:0 python3 src/main.py

# Modo headless (test sin GUI)
QT_QPA_PLATFORM=offscreen python3 src/main.py
```

---

## 3. Interfaz principal

```
┌─────────────────────────────────────────────────────────────┐
│  [Nombre del tema] [formatVersion]  [Validar] [Exportar]    │  ← Toolbar
│  [Sistema activo: —]                                         │
├─────────────────────────────────────────────────────────────┤
│  Editor XML │ Editor Visual │ Vista Previa │ Theme Set │ Empaquetar │
│─────────────────────────────────────────────────────────────│
│                                                              │
│                    (contenido del tab activo)                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Toolbar superior

- **Nombre del tema**: edita el nombre del tema (carpeta de salida).
- **formatVersion**: versión del formato XML (por defecto `7`, no cambiar salvo necesidad).
- **Validar**: comprueba el modelo en memoria e indica errores (vistas vacías, elementos sin nombre, etc.).
- **Exportar**: exporta `theme.xml` + assets a la carpeta que elijas.

---

## 4. Tab 1 — Editor XML

Editor de texto con resaltado de sintaxis XML al estilo VS Code (oscuro).

### Panel izquierdo — Editor

| Botón | Acción |
|-------|--------|
| **Abrir XML** | Carga un `theme.xml` existente en el editor |
| **Guardar XML** | Guarda el contenido del editor a un archivo |
| **Generar desde modelo** | Convierte el modelo en memoria a XML y lo muestra |
| **Aplicar al modelo** | Parsea el XML del editor y actualiza el modelo en memoria |

> **Consejo**: Usa *Generar desde modelo* después de trabajar en el Editor Visual para ver el XML resultante. Usa *Aplicar al modelo* después de editar el XML a mano para reflejar los cambios en el Constructor.

### Panel derecho — `<include>`

Gestiona etiquetas `<include>` en el XML (para referenciar otros archivos XML del tema).

| Botón | Acción |
|-------|--------|
| **+** | Abre un diálogo para escribir la ruta del archivo a incluir |
| **−** | Elimina el `<include>` seleccionado |

Ejemplo de include generado:
```xml
<include>./colors.xml</include>
<include>./fonts.xml</include>
```

---

## 5. Tab 2 — Editor Visual

Editor drag & drop con canvas 1280×720 px que representa las coordenadas normalizadas de Batocera (0.0 a 1.0).

### Diseño del tab

```
┌────────────────┬────────────────────────────┬────────────────┐
│  Browser       │                            │  Inspector     │
│  de assets     │       Canvas 1280×720      │  de propiedades│
│                │                            │                │
│  ─────────     │   [elementos visuales]     │  ─────────     │
│  Lista de      │                            │  Lista de      │
│  elementos     │                            │  elementos     │
│  de la vista   │                            │  de la vista   │
└────────────────┴────────────────────────────┴────────────────┘
```

### Vistas

- **Selector de vista** (combo superior): cambia entre las vistas del tema (`system`, `basic`, `detailed`, etc.).
- **Nueva vista**: abre el diálogo para crear una vista nueva.
- **Eliminar vista**: borra la vista seleccionada (pide confirmación).

#### Diálogo "Nueva vista"

| Campo | Descripción |
|-------|-------------|
| Nombre | Nombre de la vista (p.ej. `detailed`) |
| ☑ customView | Si está marcado, genera `<customView>` en lugar de `<view>` |
| Hereda de | Solo para customView: nombre de la vista base (`inherits="..."`) |

Vista estándar → `<view name="detailed">…</view>`  
Vista customView → `<customView name="mi_vista" inherits="detailed">…</customView>`

### Añadir elementos

- **Botón "+ Añadir elemento"**: abre el diálogo con selector de tipo y propiedades por defecto.
- **Drag & drop desde el browser de assets**: arrastra un asset directamente al canvas para crear automáticamente un elemento `image` o `video` con la ruta del archivo.

#### Diálogo "Añadir elemento"

| Campo | Descripción |
|-------|-------------|
| Nombre | Identificador único del elemento (p.ej. `e_fondo`) |
| Tipo | `image`, `text`, `video`, `rating`, `datetime`, `helpsystem`, `textlist`, `gamecarousel` |
| ☑ extra="true" | Marca el elemento como extra (elementos personalizados fuera del estándar ES) |

### Mover elementos en el canvas

- **Clic y arrastrar** un elemento para reposicionarlo.
- La posición normalizada (`pos`) se actualiza automáticamente en tiempo real.
- El arrastre es **deshacible con Ctrl+Z**.

### Inspector de propiedades

Al seleccionar un elemento (clic en el canvas o en la lista):

- Se muestra un formulario con todas las propiedades del elemento.
- **Añadir propiedad**: escribe el nombre de la propiedad y su valor, luego pulsa "+".
- **Aplicar cambios**: guarda los valores editados en el modelo (también deshaciable).

Propiedades comunes por tipo → ver [Tipos de elementos](#11-tipos-de-elementos-soportados).

### Browser de assets

Panel izquierdo con los archivos en la carpeta `assets/` del proyecto.

- Muestra miniaturas para PNG, JPG, GIF, WEBP.
- **Doble clic** → copia la ruta relativa al portapapeles.
- **Drag & drop al canvas** → crea un elemento `image`/`video` en la vista activa.

### Lista de elementos de la vista

Panel inferior izquierdo con todos los elementos de la vista actual.

- **Clic** → selecciona el elemento en el canvas y en el inspector.
- **Botón "Eliminar"** → borra el elemento (deshaciable).

---

## 6. Tab 3 — Vista Previa

Muestra el canvas en **modo solo lectura** con el contenido de la vista seleccionada.

- Usa el selector de vista para cambiar entre vistas.
- Los elementos se muestran con sus colores y posiciones actuales.
- Si el elemento tiene un asset `path` asignado (PNG/JPG), se muestra una miniatura en el canvas.

---

## 7. Tab 4 — Theme Set (multi-sistema)

Gestiona un conjunto de temas para múltiples sistemas de Batocera.

### Panel izquierdo — Sistemas

Lista de sistemas añadidos al theme set.

| Botón | Acción |
|-------|--------|
| **+ Añadir sistema** | Muestra la lista de sistemas comunes de Batocera (snes, nes, megadrive, psx…) para añadir uno |
| **− Eliminar** | Elimina el sistema seleccionado del theme set |
| **Editar en constructor** | Carga el tema del sistema en el Editor Visual para editarlo |
| **Copiar tema actual → sistema** | Copia el modelo activo del Constructor al sistema seleccionado |

### Panel derecho — Vista previa XML

Muestra el `theme.xml` del sistema seleccionado.

### Exportar theme set

**Botón "Exportar theme set"**: exporta todos los sistemas a una carpeta con la estructura:

```
mi_theme_set/
├── theme.xml          ← tema raíz (opcional)
├── snes/
│   ├── theme.xml
│   └── assets/
├── nes/
│   ├── theme.xml
│   └── assets/
└── megadrive/
    ├── theme.xml
    └── assets/
```

### Sistemas comunes disponibles

`snes`, `nes`, `megadrive`, `gba`, `gbc`, `gb`, `psx`, `ps2`, `n64`, `nds`, `arcade`, `mame`, `fbneo`, `atari2600`, `atari7800`, `mastersystem`, `gamegear`, `pce`, `neogeo`, `cps1`, `cps2`, `cps3`, `dreamcast`, `saturn`, `segacd`, `virtualboy`, `ports`, `favorites`, `all`

---

## 8. Tab 5 — Empaquetar

Herramientas para distribuir la aplicación.

### AppImage (Linux)

Pulsa **"Construir AppImage"** para ejecutar el script `scripts/build_appimage.sh`.

Requisitos: `appimagetool` instalado en el sistema.

```bash
# Instalar appimagetool manualmente
wget https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool
```

### Script Windows

**"Copiar script Windows al portapapeles"**: copia el contenido de `scripts/build_windows.ps1` al portapapeles para ejecutarlo en PowerShell.

### Log de salida

El panel inferior muestra la salida del proceso de construcción en tiempo real.

---

## 9. Exportar e instalar en Batocera

### Exportar desde la app

1. Escribe el nombre del tema en la toolbar (p.ej. `mi_tema_oscuro`).
2. Pulsa **Exportar**.
3. Elige la carpeta destino.
4. Se generará: `carpeta_elegida/mi_tema_oscuro/theme.xml` + assets copiados.

### Instalar en Batocera Linux

```bash
# Copiar via red (Batocera tiene SSH activo por defecto)
scp -r mi_tema_oscuro/ root@IP_BATOCERA:/userdata/themes/

# O via USB: copia la carpeta a /userdata/themes/ del sistema de archivos
```

### Instalar en EmulationStation (Windows/Linux)

```
~/.emulationstation/themes/mi_tema_oscuro/theme.xml
# Windows:
%HOMEPATH%\.emulationstation\themes\mi_tema_oscuro\theme.xml
```

### Activar el tema en Batocera

1. Inicia Batocera.
2. `Inicio` → `Opciones de la interfaz de usuario` → `Tema`.
3. Selecciona `mi_tema_oscuro`.

---

## 10. Estructura de un tema Batocera

```xml
<theme>
    <formatVersion>7</formatVersion>

    <!-- Archivos incluidos (opcional) -->
    <include>./colors.xml</include>

    <!-- Vista estándar -->
    <view name="system">
        <image name="e_fondo" extra="true">
            <path>./bg.jpg</path>
            <pos>0.5 0.5</pos>
            <size>1.0 1.0</size>
            <origin>0.5 0.5</origin>
        </image>
        <text name="logoText">
            <pos>0.5 0.1</pos>
            <size>0.5 0.1</size>
            <color>ffffffff</color>
            <fontSize>0.05</fontSize>
            <alignment>center</alignment>
        </text>
    </view>

    <!-- Vista personalizada (hereda de otra) -->
    <customView name="mi_vista" inherits="detailed">
        <image name="e_overlay" extra="true">
            <path>./overlay.png</path>
            <pos>0 0</pos>
            <size>1.0 1.0</size>
            <origin>0 0</origin>
        </image>
    </customView>
</theme>
```

### Coordenadas normalizadas

Batocera usa valores de `0.0` a `1.0` (relativos a la pantalla):

| Valor | Significado |
|-------|-------------|
| `pos 0.5 0.5` | Centro de la pantalla |
| `pos 0 0` | Esquina superior izquierda |
| `size 1.0 1.0` | Pantalla completa |
| `size 0.5 0.5` | Mitad del ancho y alto |
| `origin 0.5 0.5` | Ancla en el centro del elemento |
| `origin 0 0` | Ancla en la esquina superior izquierda |

---

## 11. Tipos de elementos soportados

### `image`
```xml
<image name="e_bg" extra="true">
    <path>./fondo.jpg</path>
    <pos>0.5 0.5</pos>
    <size>1.0 1.0</size>
    <origin>0.5 0.5</origin>
    <color>ffffffff</color>   <!-- RRGGBBAA -->
    <opacity>1.0</opacity>
    <zIndex>0</zIndex>
    <tile>false</tile>
    <rotation>0</rotation>
</image>
```

### `text`
```xml
<text name="titulo">
    <text>Mi Texto</text>
    <pos>0.5 0.1</pos>
    <size>0.6 0.1</size>
    <origin>0.5 0</origin>
    <color>ffffffff</color>
    <fontSize>0.04</fontSize>
    <fontPath>./fuente.ttf</fontPath>
    <alignment>center</alignment>   <!-- left / center / right -->
    <zIndex>5</zIndex>
</text>
```

### `video`
```xml
<video name="e_video" extra="true">
    <path>./video.mp4</path>
    <pos>0.5 0.5</pos>
    <size>0.6 0.4</size>
    <origin>0.5 0.5</origin>
    <delay>2</delay>
    <loops>0</loops>   <!-- 0 = infinito -->
</video>
```

### `rating`
```xml
<rating name="md_rating">
    <pos>0.8 0.85</pos>
    <size>0.15 0.03</size>
    <origin>0.5 0.5</origin>
    <filledPath>./estrella_llena.png</filledPath>
    <unfilledPath>./estrella_vacia.png</unfilledPath>
    <color>ffffffff</color>
</rating>
```

### `datetime`
```xml
<datetime name="md_releasedate">
    <pos>0.5 0.9</pos>
    <size>0.3 0.05</size>
    <origin>0.5 0.5</origin>
    <color>aaaaaa</color>
    <fontSize>0.03</fontSize>
    <format>%Y-%m-%d</format>
</datetime>
```

### `helpsystem`
```xml
<helpsystem name="help">
    <pos>0.5 0.96</pos>
    <iconSize>0.04 0.04</iconSize>
    <textColor>777777</textColor>
    <iconColor>777777</iconColor>
</helpsystem>
```

### `textlist`
```xml
<textlist name="gamelist">
    <pos>0.02 0.1</pos>
    <size>0.4 0.8</size>
    <origin>0 0</origin>
    <primaryColor>dddddd</primaryColor>
    <secondaryColor>888888</secondaryColor>
    <selectedColor>ffffff</selectedColor>
    <selectorColor>0033a0</selectorColor>
    <fontSize>0.035</fontSize>
    <alignment>left</alignment>
</textlist>
```

### `gamecarousel`
```xml
<gamecarousel name="systemcarousel">
    <pos>0.5 0.5</pos>
    <size>1.0 0.33</size>
    <origin>0.5 0.5</origin>
    <logoSize>0.25 0.13</logoSize>
    <maxLogoCount>3</maxLogoCount>
    <color>00000000</color>
</gamecarousel>
```

---

## 12. Flujo de trabajo recomendado

### Crear un tema desde cero

```
1. Abrir la app
2. Escribir el nombre del tema en la toolbar
3. Editor Visual → "Nueva vista" → nombre: "system"
4. Añadir elemento → tipo: image → nombre: e_fondo → extra: ✓
5. En el Inspector: path = ./bg.jpg, pos = 0.5 0.5, size = 1.0 1.0, origin = 0.5 0.5
6. Arrastra el elemento en el canvas para reposicionarlo
7. Ctrl+Z para deshacer si te equivocas
8. Repetir para más elementos y vistas
9. Toolbar → Validar para comprobar errores
10. Toolbar → Exportar
```

### Editar un XML existente

```
1. Editor XML → "Abrir XML" → seleccionar theme.xml
2. Editar manualmente o pulsar "Aplicar al modelo"
3. Ir al Editor Visual para edición visual
4. Editor XML → "Generar desde modelo" para ver el resultado
5. Exportar
```

### Crear un theme set multi-sistema

```
1. Editor Visual → diseñar el tema para "system"
2. Theme Set → "+ Añadir sistema" → snes
3. Theme Set → "Copiar tema actual → sistema"
4. Theme Set → Seleccionar snes → "Editar en constructor"
5. Ajustar para snes → volver a Theme Set → "Copiar tema actual → sistema"
6. Repetir para cada sistema
7. Theme Set → "Exportar theme set"
```

---

## 13. Atajos de teclado

| Atajo | Acción |
|-------|--------|
| `Ctrl+Z` | Deshacer última acción en el Editor Visual |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Rehacer |
| `Supr` / `Delete` | Eliminar elemento seleccionado en el canvas |
| `Clic` en canvas | Seleccionar elemento |
| `Clic + arrastrar` | Mover elemento (registra undo al soltar) |
| Doble clic en asset | Copiar ruta al portapapeles |
| Arrastrar asset al canvas | Crear elemento image/video |

---

## 14. Preguntas frecuentes

**P: ¿Qué es `extra="true"`?**  
R: Indica que el elemento es personalizado (no forma parte del esquema estándar de EmulationStation). Los elementos del sistema como `md_description`, `md_rating` NO llevan `extra`. Los fondos y overlays personalizados SÍ.

**P: ¿Por qué mis cambios en el Constructor no aparecen en el Editor XML?**  
R: Pulsa **"Generar desde modelo"** en el tab Editor XML para sincronizar.

**P: ¿Puedo usar fuentes personalizadas?**  
R: Sí. Coloca el archivo `.ttf`/`.otf` en `assets/` y en la propiedad `fontPath` escribe `./tu_fuente.ttf`.

**P: ¿Qué diferencia hay entre `view` y `customView`?**  
R: `view` es una vista estándar de EmulationStation. `customView` permite crear vistas nuevas que heredan de una vista base, útil para temas con muchas variaciones.

**P: ¿El canvas de 1280×720 es la resolución final?**  
R: No. Es solo la representación visual. Batocera usa coordenadas normalizadas (0.0–1.0) que se adaptan a cualquier resolución. El canvas es proporcional a 16:9.

**P: ¿Cómo transfiero el tema a Batocera via red?**  
R: Batocera expone SSH (puerto 22) con usuario `root` sin contraseña por defecto:
```bash
scp -r mi_tema/ root@192.168.1.XXX:/userdata/themes/
```

**P: Error `No module named 'PySide6'`**  
R: Instala PySide6 con el mismo Python que ejecutas:
```bash
python3 -m pip install PySide6
```

**P: La app no arranca en Linux (error de display)**  
R: Añade `DISPLAY=:0` antes del comando:
```bash
DISPLAY=:0 python3 src/main.py
```

---

## Estructura del proyecto

```
egbtheme-creator_btcr/
├── src/
│   ├── main.py          ← Aplicación GUI (PySide6)
│   └── core.py          ← Modelo de datos y lógica de exportación
├── assets/              ← Assets del proyecto (imágenes, fuentes, iconos)
│   ├── iconos/
│   ├── fuentes/
│   └── sistemas/
├── scripts/
│   ├── build_appimage.sh     ← Script para construir AppImage
│   ├── build_windows.ps1     ← Script PowerShell para Windows
│   └── build_nsis.ps1        ← Script NSIS para instalador Windows
├── themes_export_headless/   ← Directorio de test headless
├── requirements.txt
├── guia_usuario.md           ← Esta guía
└── README.md
```

---

*egbtheme-creator_btcr — Herramienta creada para diseñar themes de Batocera EmulationStation*
