import os
import shutil
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Modelo de datos compatible con Batocera/EmulationStation
# ---------------------------------------------------------------------------

class ThemeElement:
    """Un elemento dentro de una vista: image, text, video, rating, etc."""

    TYPES = ["image", "text", "video", "rating", "datetime", "sound",
             "helpsystem", "container", "ninepatch", "textlist", "gamecarousel"]

    VIEW_ALLOWED_TYPES = {
        "system": ["carousel", "image", "video", "helpsystem", "text"],
        "basic": ["image", "helpsystem", "text", "textlist"],
        "detailed": ["image", "video", "datetime", "helpsystem", "text", "textlist", "rating"],
        "gamecarousel": ["image", "video", "helpsystem", "datetime", "rating", "text", "textlist"],  # vista tipo carrusel de juegos
        "grid": ["image", "imagegrid", "gridtile", "datetime", "helpsystem", "ninepatch", "rating", "text"],
        "video": ["image", "text", "textlist", "video", "rating", "datetime", "helpsystem"], # deprecado pero compatible
        # Para customView se calculará a partir de la vista de la que hereda
    }

    # Propiedades comunes por tipo para el inspector
    COMMON_PROPS = {
        "image": [
            "path", "default", "pos", "size", "minSize", "maxSize", "origin",
            "color", "colorEnd", "gradientType", "opacity", "zIndex", "tile",
            "visible", "rotation", "rotationOrigin", "reflexion", "reflexionOnFrame",
            "horizontalAlignment", "verticalAlignment", "flipX", "flipY"
        ],
        "video": [
            "path", "default", "pos", "size", "minSize", "maxSize", "origin",
            "opacity", "zIndex", "delay", "loops", "visible", "showSnapshotNoVideo"
        ],
        "text": [
            "text", "pos", "size", "origin", "color", "fontSize", "fontPath",
            "alignment", "forceUppercase", "lineSpacing", "zIndex", "visible"
        ],
        "rating": [
            "pos", "size", "origin", "filledPath", "unfilledPath", "color",
            "opacity", "zIndex", "visible"
        ],
        "datetime": [
            "pos", "size", "origin", "color", "fontSize", "fontPath", "format",
            "zIndex", "visible"
        ],
        "helpsystem": [
            "pos", "iconSize", "textColor", "iconColor", "fontPath", "visible"
        ],
        "textlist": [
            "pos", "size", "origin", "selectorColor", "selectorImagePath",
            "selectorImageTile", "selectedColor", "primaryColor", "secondaryColor",
            "fontPath", "fontSize", "alignment", "scrollbarColor", "scrollbarSize",
            "zIndex", "visible"
        ],
        "carousel": [
            "pos", "size", "origin", "color", "colorEnd", "type", "logoSize",
            "maxLogoCount", "logoPos", "logoAlignment", "logoScaleUp", "zIndex", "visible"
        ],
        "gamecarousel": [
            "pos", "size", "origin", "color", "colorEnd", "imageSource", "logoScale", "logoSize", "logoRotation",
            "logoRotationOrigin", "logoAlignment", "maxLogoCount", "scrollSound", "zIndex", "visible"
        ],
    }

    def __init__(self, name: str = "", element_type: str = "image",
                 extra: bool = False, properties: Optional[Dict[str, List[ConditionalValue]]] = None):
        self.name = name or ("e_" + str(uuid.uuid4())[:6])
        self.element_type = element_type
        self.extra = extra
        self.properties: Dict[str, List[ConditionalValue]] = properties or {}

    def get_base_value(self, prop_name: str) -> str:
        """Devuelve el valor de la propiedad sin condición (fallback)"""
        values = self.properties.get(prop_name, [])
        for cv in values:
            if cv.condition is None:
                return cv.value
        return ""

    def set_base_value(self, prop_name: str, new_value: str):
        """Establece o actualiza el valor sin condición. Mantiene los condicionales."""
        values = self.properties.get(prop_name, [])
        # Buscar si ya existe un valor sin condición
        for i, cv in enumerate(values):
            if cv.condition is None:
                values[i] = ConditionalValue(new_value, None)
                return
        # Si no existe, lo añadimos al principio
        values.insert(0, ConditionalValue(new_value, None))
        self.properties[prop_name] = values

    def get_resolved_value(self, prop_name: str, context: Dict[str, str]) -> str:
        """Evalúa las condiciones y devuelve el primer valor que coincide o el base."""
        values = self.properties.get(prop_name, [])
        for cv in values:
            if cv.condition is None:
                return cv.value
            if self._evaluate_condition(cv.condition, context):
                return cv.value
        return ""
    @staticmethod
    def _evaluate_condition(cond: str, context: Dict[str, str]) -> bool:
        """Evalúa una condición simple (solo ==, ||, etc.) - Implementación básica."""
        # Este es un ejemplo muy simplificado. Para un uso real, necesitarías un parser.
        # Aquí asumimos condiciones como "{system.theme} == 'neogeo'"
        import re
        pattern = r"\{([^}]+)\}\s*==\s*'([^']+)'"
        match = re.search(pattern, cond)
        if match:
            var = match.group(1)
            expected = match.group(2)
            return context.get(var, "") == expected
        # Soporte para OR (muy básico)
        if "||" in cond:
            parts = cond.split("||")
            return any(ThemeElement._evaluate_condition(p.strip(), context) for p in parts)
        return False

    def suggested_props(self) -> List[str]:
        return self.COMMON_PROPS.get(self.element_type, ["pos", "size"])

    def to_dict(self) -> Dict:
        props = {}
        for k, vlist in self.properties.items():
            props[k] = [cv.to_dict() for cv in vlist]
        return {
            "name": self.name,
            "element_type": self.element_type,
            "extra": self.extra,
            "properties": props,
        }

    @staticmethod
    def from_dict(d: Dict) -> 'ThemeElement':
        props = {}
        for k, vlist in d.get("properties", {}).items():
            props[k] = [ConditionalValue.from_dict(cv) for cv in vlist]
        return ThemeElement(
            name=d.get("name", ""),
            element_type=d.get("element_type", "image"),
            extra=bool(d.get("extra", False)),
            properties=props,
        )


class ThemeView:
    """Una vista de Batocera: system, basic, detailed, video, grid o customView."""

    STANDARD_VIEWS = ["system", "basic", "gamecarousel", "detailed", "video", "grid", "customView"]

    def __init__(self, name: str = "system", inherits: str = "",
                 is_custom: bool = False):
        self.name = name
        self.inherits = inherits    # solo para customView (<customView inherits="...")
        self.is_custom = is_custom  # True → emite <customView>, False → <view>
        self.elements: List[ThemeElement] = []

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "inherits": self.inherits,
            "is_custom": self.is_custom,
            "elements": [e.to_dict() for e in self.elements],
        }

    @staticmethod
    def from_dict(d: Dict) -> 'ThemeView':
        v = ThemeView(
            name=d.get("name", "system"),
            inherits=d.get("inherits", ""),
            is_custom=bool(d.get("is_custom", False)),
        )
        v.elements = [ThemeElement.from_dict(e) for e in d.get("elements", [])]
        return v


class ThemeModel:
    """Tema completo de Batocera EmulationStation."""

    def __init__(self, name: str = "nuevo_tema", format_version: int = 7):
        self.name = name
        self.format_version = format_version
        self.views: List[ThemeView] = []
        self.includes: List[str] = []
        self.subsets: Dict[str, List[Dict]] = {}
        self.raw_xml: str = ""

    # ------------------------------------------------------------------
    def get_view(self, view_name: str) -> Optional[ThemeView]:
        for v in self.views:
            if v.name == view_name:
                return v
        return None

    def add_view(self, view_name: str) -> ThemeView:
        existing = self.get_view(view_name)
        if existing:
            return existing
        v = ThemeView(name=view_name)
        self.views.append(v)
        return v

    def remove_view(self, view_name: str):
        self.views = [v for v in self.views if v.name != view_name]

    # ------------------------------------------------------------------
    def to_xml(self) -> str:
        root = ET.Element("theme")
        ET.SubElement(root, "formatVersion").text = str(self.format_version)

        for inc in self.includes:
            ET.SubElement(root, "include").text = inc

        for view in self.views:
            if view.is_custom:
                attrib: Dict[str, str] = {"name": view.name}
                if view.inherits:
                    attrib["inherits"] = view.inherits
                view_el = ET.SubElement(root, "customView", attrib=attrib)
            else:
                view_el = ET.SubElement(root, "view", attrib={"name": view.name})
            for elem in view.elements:
                attrib: Dict[str, str] = {"name": elem.name}
                if elem.extra:
                    attrib["extra"] = "true"
                elem_el = ET.SubElement(view_el, elem.element_type, attrib=attrib)
                for prop_name, cv_list in elem.properties.items():
                    for cv in cv_list:
                        prop_el = ET.SubElement(elem_el, prop_name)
                        if cv.condition:
                            prop_el.set("if", cv.condition)
                        prop_el.text = cv.value

        raw = ET.tostring(root, encoding="unicode")
        try:
            dom = minidom.parseString(raw)
            pretty = dom.toprettyxml(indent="\t", newl="\n")
            lines = pretty.split("\n")
            if lines[0].startswith("<?xml"):
                pretty = "\n".join(lines[1:])
            self.raw_xml = pretty
        except Exception:
            self.raw_xml = raw
        return self.raw_xml

    @staticmethod
    def from_xml(xml_str: str) -> Optional['ThemeModel']:
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None

        t = ThemeModel()
        fv = root.find("formatVersion")
        if fv is not None and fv.text:
            try:
                t.format_version = int(fv.text.strip())
            except ValueError:
                pass

        for inc in root.findall("include"):
            if inc.text:
                t.includes.append(inc.text.strip())

        def _parse_view_el(view_el, is_custom=False):
            view = ThemeView(
                name=view_el.attrib.get("name", "system"),
                inherits=view_el.attrib.get("inherits", ""),
                is_custom=is_custom,
            )

            for child in view_el:
                elem = ThemeElement(
                    name=child.attrib.get("name", ""),
                    element_type=child.tag,
                    extra=(child.attrib.get("extra", "false").lower() == "true"),
                    properties={},
                )
                # Procesar cada subetiqueta (path, pos, size, etc.)
                for sub in child:
                    prop_name = sub.tag
                    prop_val = sub.text or ""
                    condition = sub.attrib.get("if", None)
                    cv = ConditionalValue(prop_val, condition)
                    if prop_name not in elem.properties:
                        elem.properties[prop_name] = []
                    elem.properties[prop_name].append(cv)
                view.elements.append(elem)
            return view

        for view_el in root.findall("view"):
            t.views.append(_parse_view_el(view_el, is_custom=False))

        for view_el in root.findall("customView"):
            t.views.append(_parse_view_el(view_el, is_custom=True))

        t.raw_xml = xml_str
        return t


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_SUPPORTED_EXTS = {
    '.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp',
    '.mp4', '.mkv', '.avi', '.wav', '.ogg', '.mp3',
    '.ttf', '.TTF', '.otf', '.xml',
}


def scan_assets(folder: str) -> List[str]:
    assets: List[str] = []
    if not os.path.isdir(folder):
        return assets
    for dirpath, _, files in os.walk(folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in _SUPPORTED_EXTS:
                rel = os.path.relpath(os.path.join(dirpath, f), folder)
                assets.append(rel.replace('\\', '/'))
    assets.sort()
    return assets


def export_theme(theme: ThemeModel, target_root: str,
                 assets_source_dir: str = "assets") -> str:
    """Exporta el tema a target_root/theme.name/ con estructura Batocera."""
    theme_dir = os.path.join(target_root, theme.name)
    os.makedirs(theme_dir, exist_ok=True)

    xml_str = theme.to_xml()
    with open(os.path.join(theme_dir, "theme.xml"), "w", encoding="utf-8") as f:
        f.write(xml_str)

    # Copiar assets referenciados (paths que empiezan con ./)
    for view in theme.views:
        for elem in view.elements:
            path_val = elem.properties.get("path", "")
            if path_val.startswith("./"):
                rel_asset = path_val[2:]
                src = os.path.join(assets_source_dir, rel_asset)
                dst = os.path.join(theme_dir, rel_asset)
                if os.path.isfile(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

    with open(os.path.join(theme_dir, "README_export.md"), "w", encoding="utf-8") as f:
        f.write(f"# Tema: {theme.name}\n\n")
        f.write(f"- formatVersion: {theme.format_version}\n")
        f.write(f"- Vistas: {', '.join(v.name for v in theme.views) or '(ninguna)'}\n\n")
        f.write("Exportado con **egbtheme-creator_btcr**.\n\n")
        f.write("## Instalación en Batocera\n")
        f.write(f"Copia la carpeta `{theme.name}/` a:\n")
        f.write("- Linux: `/userdata/themes/`\n")
        f.write("- Windows: `%HOMEPATH%\\.emulationstation\\themes\\`\n")

    return theme_dir


# ---------------------------------------------------------------------------
# Theme Set — colección multi-sistema
# ---------------------------------------------------------------------------

class ThemeSet:
    """Colección de temas por sistema para un theme set completo de Batocera."""

    COMMON_SYSTEMS = [
        "snes", "nes", "megadrive", "gba", "gbc", "gb", "psx", "ps2",
        "n64", "nds", "arcade", "mame", "fbneo", "atari2600", "atari7800",
        "mastersystem", "gamegear", "pce", "neogeo", "cps1", "cps2", "cps3",
        "dreamcast", "saturn", "segacd", "virtualboy", "ports", "favorites", "all",
    ]

    def __init__(self, name: str = "mi_theme_set"):
        self.name = name
        self.systems: Dict[str, ThemeModel] = {}
        self.default_theme: Optional[ThemeModel] = None   # theme.xml raíz

    def add_system(self, system_name: str) -> ThemeModel:
        if system_name not in self.systems:
            m = ThemeModel(name=system_name)
            self.systems[system_name] = m
        return self.systems[system_name]

    def remove_system(self, system_name: str):
        self.systems.pop(system_name, None)

    def system_names(self) -> List[str]:
        return sorted(self.systems.keys())


def export_theme_set(theme_set: ThemeSet, target_root: str,
                     assets_source_dir: str = "assets") -> str:
    """Exporta el theme set completo: target_root/theme_set.name/{sistema}/theme.xml"""
    set_dir = os.path.join(target_root, theme_set.name)
    os.makedirs(set_dir, exist_ok=True)

    # theme.xml raíz (default)
    if theme_set.default_theme is not None:
        xml_str = theme_set.default_theme.to_xml()
        with open(os.path.join(set_dir, "theme.xml"), "w", encoding="utf-8") as f:
            f.write(xml_str)

    # Por sistema
    for sys_name, model in theme_set.systems.items():
        sys_dir = os.path.join(set_dir, sys_name)
        os.makedirs(sys_dir, exist_ok=True)
        xml_str = model.to_xml()
        with open(os.path.join(sys_dir, "theme.xml"), "w", encoding="utf-8") as f:
            f.write(xml_str)
        # Copiar assets referenciados con ./
        for view in model.views:
            for elem in view.elements:
                path_val = elem.properties.get("path", "")
                if path_val.startswith("./"):
                    rel_asset = path_val[2:]
                    src = os.path.join(assets_source_dir, rel_asset)
                    dst = os.path.join(sys_dir, rel_asset)
                    if os.path.isfile(src):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)

    with open(os.path.join(set_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# Theme Set: {theme_set.name}\n\n")
        systems_str = ", ".join(theme_set.system_names()) or "(ninguno)"
        f.write(f"Sistemas incluidos: {systems_str}\n\n")
        f.write("## Instalación en Batocera\n")
        f.write(f"Copia la carpeta `{theme_set.name}/` a `/userdata/themes/`\n")
        f.write("y selecciónalo en **Ajustes UI → Tema**.\n")

    return set_dir

# ---------------------------------------------------------------------------
# VALIDAR XML
# ---------------------------------------------------------------------------
def validate_theme_xml(theme_model: ThemeModel, strict_tags: bool = False) -> List[str]:
    """
    Valida la estructura del XML del theme:
    - Sintaxis correcta
    - Sin texto suelto
    - Raíz <theme>
    - Opcionalmente (strict_tags=True) advierte de etiquetas no reconocidas
    """
    errors = []
    xml_str = theme_model.raw_xml
    if not xml_str:
        errors.append("No hay XML generado para validar.")
        return errors

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        errors.append(f"Error de sintaxis XML: {e}")
        return errors

    if root.tag != "theme":
        errors.append(f"La raíz debe ser <theme>, no '{root.tag}'.")

    # Conjunto de etiquetas conocidas en cualquier nivel (opcional para advertencias)
    KNOWN_TAGS = {
        "theme", "formatVersion", "include", "variables", "subset", "view", "customView",
        "image", "text", "video", "rating", "datetime", "sound", "helpsystem", "container",
        "ninepatch", "textlist", "gamecarousel", "carousel",
        # Extensiones de menú y pantalla
        "menuText", "menuTextSmall", "menuGroup", "menuBackground", "menuIcons", "menuTextEdit",
        "batteryIndicator", "controllerActivity"
    }

    # Detectar texto suelto
    for elem in root.iter():
        if len(elem) > 0 and elem.text and elem.text.strip():
            errors.append(f"Texto no permitido dentro de <{elem.tag}>: '{elem.text.strip()[:50]}'")
        if elem.tail and elem.tail.strip():
            errors.append(f"Texto suelto después de </{elem.tag}>: '{elem.tail.strip()[:50]}'")

        # Advertencia opcional de etiquetas desconocidas (solo si strict_tags)
        if strict_tags and elem.tag not in KNOWN_TAGS:
            # Permitir cualquier etiqueta dentro de <variables> (son nombres de variable libres)
            parent = elem.getparent() if hasattr(elem, 'getparent') else None
            if parent is None or parent.tag != "variables":
                errors.append(f"Etiqueta desconocida (puede ser válida pero no está en la lista oficial): <{elem.tag}>")

    return errors


# ---------------------------------------------------------------------------
# CARGA THEMES COMPLETOS CREADOS
# ---------------------------------------------------------------------------

class ThemeVariableResolver:
    """Resuelve variables como ${baseColor}, ${system.theme}, etc."""

    def __init__(self, variables: Dict[str, str], system_name: str = ""):
        self.variables = variables.copy()
        self.system_name = system_name
        # Añadir variables de sistema por defecto
        self.variables["system.theme"] = system_name

    def resolve(self, text: str) -> str:
        result = text
        for key, value in self.variables.items():
            result = result.replace(f"${{{key}}}", value)
        # Manejar <default> implícito
        if "default" in result and self.system_name:
            result = result.replace("default", self.system_name)
        return result


class ExtendedThemeModel(ThemeModel):
    """Extiende ThemeModel para soportar variables, subsets y includes condicionales."""

    def __init__(self, name: str = "nuevo_tema", format_version: int = 7):
        super().__init__(name, format_version)
        self.variables: Dict[str, str] = {}
        self.subsets: Dict[str, List[Dict]] = {}  # subsets: nombre -> lista de includes
        self.default_view: str = ""

    def resolve_property(self, prop_name: str, prop_value: str, system_name: str = "") -> str:
        """Resuelve variables en una propiedad."""
        resolver = ThemeVariableResolver(self.variables, system_name)
        return resolver.resolve(prop_value)

    @staticmethod
    def from_folder(system_folder: str, global_variables: Dict[str, str] = None) -> Optional['ExtendedThemeModel']:
        """Carga todos los archivos .xml de una carpeta y los combina en un ExtendedThemeModel."""
        xml_files = [f for f in os.listdir(system_folder) if f.endswith('.xml')]
        if not xml_files:
            return None

        combined = ExtendedThemeModel(name=os.path.basename(system_folder))

        # Cargar variables globales si se proporcionan
        if global_variables:
            combined.variables.update(global_variables)

        # Cargar todos los XML y fusionar vistas
        for xml_file in xml_files:
            path = os.path.join(system_folder, xml_file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                model = ExtendedThemeModel.from_xml(content)
                if model:
                    # Fusionar variables (las locales tienen prioridad)
                    combined.variables.update(model.variables)
                    # Fusionar vistas (evitando duplicados por nombre)
                    for view in model.views:
                        if not any(v.name == view.name for v in combined.views):
                            combined.views.append(view)
                    # Guardar default_view si no está definido
                    if model.default_view and not combined.default_view:
                        combined.default_view = model.default_view
        return combined

    @staticmethod
    def from_xml(xml_str: str, base_path: str = "", visited: set = None) -> Optional['ExtendedThemeModel']:
        """Parsea XML soportando includes, variables y subsets."""
        if visited is None:
            visited = set()

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None

        model = ExtendedThemeModel()

        # Leer defaultView del atributo raíz
        if 'defaultView' in root.attrib:
            model.default_view = root.attrib['defaultView']

        # Parsear formatVersion
        fv = root.find("formatVersion")
        if fv is not None and fv.text:
            try:
                model.format_version = int(fv.text.strip())
            except ValueError:
                pass

        # Parsear variables
        vars_elem = root.find("variables")
        if vars_elem is not None:
            for child in vars_elem:
                if child.text:
                    model.variables[child.tag] = child.text.strip()

        # Parsear includes (con soporte para condicionales y idiomas)
        for inc in root.findall("include"):
            inc_path = inc.text.strip() if inc.text else ""
            if inc_path:
                # Resolver ruta base
                full_path = os.path.join(base_path, inc_path)
                # Verificar condicionales (ifArch, lang, etc.)
                if ExtendedThemeModel._should_include(inc, full_path, visited):
                    if full_path not in visited and os.path.isfile(full_path):
                        visited.add(full_path)
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            sub_model = ExtendedThemeModel.from_xml(content, os.path.dirname(full_path), visited)
                            if sub_model:
                                model.variables.update(sub_model.variables)
                                model.views.extend(sub_model.views)

        # Parsear subsets
        for subset in root.findall("subset"):
            subset_name = subset.attrib.get("name", "")
            if subset_name:
                model.subsets[subset_name] = []
                for inc in subset.findall("include"):
                    inc_name = inc.attrib.get("name", "")
                    inc_display = inc.attrib.get("displayName", inc_name)
                    inc_path = inc.text.strip() if inc.text else ""
                    model.subsets[subset_name].append({
                        "name": inc_name,
                        "displayName": inc_display,
                        "path": inc_path
                    })

        # Parsear vistas (igual que antes)
        def _parse_view_el(view_el, is_custom=False):
            view = ThemeView(
                name=view_el.attrib.get("name", "system"),
                inherits=view_el.attrib.get("inherits", ""),
                is_custom=is_custom,
            )
            for child in view_el:
                elem = ThemeElement(
                    name=child.attrib.get("name", ""),
                    element_type=child.tag,
                    extra=(child.attrib.get("extra", "false").lower() == "true"),
                    properties={sub.tag: (sub.text or "") for sub in child},
                )
                view.elements.append(elem)
            return view

        for view_el in root.findall("view"):
            model.views.append(_parse_view_el(view_el, is_custom=False))

        for view_el in root.findall("customView"):
            model.views.append(_parse_view_el(view_el, is_custom=True))

        model.raw_xml = xml_str
        return model

    @staticmethod
    def _should_include(inc_elem, full_path: str, visited: set) -> bool:
        """Evalúa si un include debe ser cargado según condicionales."""
        # Verificar si ya fue incluido
        if full_path in visited:
            return False

        # Verificar ifArch
        if 'ifArch' in inc_elem.attrib:
            archs = inc_elem.attrib['ifArch'].split(',')
            # Por defecto, asumimos que estamos en Linux/x86_64
            current_arch = "x86_64"  # Podría detectarse con platform.machine()
            if current_arch not in archs:
                return False

        # Verificar lang (por ahora siempre true)
        # En el futuro, podríamos detectar el idioma del sistema

        return True


# ---------------------------------------------------------------------------
# DETECCIÓN DE CONDICIONALES EN ETIQUETAS
# ---------------------------------------------------------------------------
class ConditionalValue:
    def __init__(self, value: str, condition: Optional[str] = None):
        self.value = value
        self.condition = condition   # Ej: "{system.theme} == 'neogeo'"

    def to_dict(self):
        return {"value": self.value, "condition": self.condition}

    @staticmethod
    def from_dict(d):
        return ConditionalValue(d["value"], d.get("condition"))