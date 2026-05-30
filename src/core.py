import os
import shutil
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Modelo de datos compatible con Batocera/EmulationStation
# ---------------------------------------------------------------------------
class XmlNode:
    """Nodo genérico que representa cualquier elemento XML."""
    def __init__(self, tag: str, attrib: Dict[str, str] = None, text: str = ""):
        self.tag = tag
        self.attrib = attrib or {}
        self.text = text
        self.children: List['XmlNode'] = []

    def find_child(self, tag: str) -> Optional['XmlNode']:
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def to_xml_element(self) -> ET.Element:
        elem = ET.Element(self.tag, self.attrib)
        if self.text:
            elem.text = self.text
        for child in self.children:
            elem.append(child.to_xml_element())
        return elem

    def to_dict(self) -> Dict:
        """Convierte el nodo y sus hijos a un diccionario serializable."""
        return {
            "tag": self.tag,
            "attrib": self.attrib.copy(),
            "text": self.text,
            "children": [child.to_dict() for child in self.children]
        }

    @staticmethod
    def from_dict(d: Dict) -> 'XmlNode':
        node = XmlNode(d["tag"], d.get("attrib", {}), d.get("text", ""))
        for child_data in d.get("children", []):
            node.children.append(XmlNode.from_dict(child_data))
        return node


class ThemeElement(XmlNode):
    """Un elemento dentro de una vista: image, text, video, rating, etc."""

    TYPES = ["image", "text", "video", "rating", "datetime", "sound",
             "helpsystem", "container", "ninepatch", "textlist", "gamecarousel",
             "carousel", "imagegrid", "gridtile", "menuText", "menuGroup",
             "batteryIndicator", "controllerActivity"]

    VIEW_ALLOWED_TYPES = {
        "system": ["carousel", "image", "video", "helpsystem", "text"],
        "basic": ["image", "helpsystem", "text", "textlist"],
        "detailed": ["image", "video", "datetime", "helpsystem", "text", "textlist", "rating"],
        "gamecarousel": ["image", "video", "gamecarousel", "helpsystem", "datetime", "rating", "text", "textlist"],  # vista tipo carrusel de juegos
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
            "pos", "size", "origin", "type", "defaultTransition", "logoSize", "logoScale", "logoRotation",
            "logoRotationOrigin", "logoAlignment", "maxLogoCount", "color", "colorEnd",
            "zIndex", "visible"
        ],
        "gamecarousel": [
            "pos", "size", "origin", "type", "logoSize", "logoScale", "logoRotation",
            "logoRotationOrigin", "logoAlignment", "maxLogoCount", "imageSource",
            "scrollSound", "color", "colorEnd", "zIndex", "visible"
        ],
    }

    def __init__(self, tag: str = "image", name: str = "", extra: bool = False,
                 properties: Optional[Dict[str, List['ConditionalValue']]] = None):
        # Inicializar el nodo XML con la etiqueta adecuada
        attrib = {}
        if name:
            attrib["name"] = name
        if extra:
            attrib["extra"] = "true"
        super().__init__(tag, attrib)
        self.element_type = tag   # alias
        self.name = name
        self.extra = extra

        # Si se proporcionan propiedades antiguas (plano), las convertimos a hijos hoja
        if properties:
            for prop_name, cv_list in properties.items():
                for cv in cv_list:
                    child = XmlNode(prop_name, text=cv.value)
                    if cv.condition:
                        child.attrib["if"] = cv.condition
                    self.children.append(child)

    def get_base_value(self, prop_name: str) -> str:
        """Devuelve el valor de la propiedad sin condición (fallback)."""
        for child in self.children:
            if child.tag == prop_name and not child.children and "if" not in child.attrib:
                return child.text
        return ""

    def set_base_value(self, prop_name: str, new_value: str):
        """Establece o actualiza el valor sin condición. Mantiene los condicionales."""
        # Buscar si ya existe un hijo hoja sin condición
        for child in self.children:
            if child.tag == prop_name and not child.children and "if" not in child.attrib:
                child.text = new_value
                return
        # No existe, lo añadimos
        new_child = XmlNode(prop_name, text=new_value)
        self.children.append(new_child)

    def get_resolved_value(self, prop_name: str, context: Dict[str, str]) -> str:
        """Evalúa las condiciones y devuelve el primer valor que coincide o el base."""
        for child in self.children:
            if child.tag != prop_name:
                continue
            condition = child.attrib.get("if")
            if condition is None:
                return child.text
            if self._evaluate_condition(condition, context):
                return child.text
        return ""

    def get_resolved_values(self, prop_name: str, context: Dict[str, str]) -> List[str]:
        """Devuelve una lista de valores resueltos (variables expandidas) para la propiedad prop_name,
        en el orden de aparición de los nodos hijos, evaluando condiciones."""
        values = []
        for child in self.children:
            if child.tag != prop_name:
                continue
            condition = child.attrib.get("if")
            if condition is None or self._evaluate_condition(condition, context):
                # Resolver variables dentro del texto
                resolver = ThemeVariableResolver(context, context.get("system.theme", ""))
                resolved = resolver.resolve(child.text)
                values.append(resolved)
        return values

    @property
    def properties(self) -> Dict[str, List[ConditionalValue]]:
        """Compatibilidad: devuelve los hijos hoja como propiedades."""
        props = {}
        for child in self.children:
            if not child.children:  # es hoja
                cv = ConditionalValue(child.text, child.attrib.get("if"))
                props.setdefault(child.tag, []).append(cv)
        return props

    def suggested_props(self) -> List[str]:
        return self.COMMON_PROPS.get(self.element_type, ["pos", "size"])

    # to_dict y from_dict se pueden mantener pero usando la nueva estructura
    def to_dict(self) -> Dict:
        children_data = []
        for child in self.children:
            children_data.append({
                "tag": child.tag,
                "attrib": child.attrib,
                "text": child.text,
                "children": [c.to_dict() for c in child.children]  # recursivo
            })
        return {
            "name": self.name,
            "element_type": self.element_type,
            "extra": self.extra,
            "attrib": self.attrib,
            "children": children_data,
        }

    @staticmethod
    def from_dict(d: Dict) -> 'ThemeElement':
        elem = ThemeElement(
            tag=d.get("element_type", "image"),
            name=d.get("name", ""),
            extra=d.get("extra", False)
        )
        # Recuperar los hijos guardados recursivamente
        for child_data in d.get("children", []):
            child = XmlNode(child_data["tag"], child_data.get("attrib", {}), child_data.get("text", ""))
            for sub in child_data.get("children", []):
                child.children.append(XmlNode.from_dict(sub))
            elem.children.append(child)
        return elem

    # Método estático de evaluación de condiciones (copiado del original)
    @staticmethod
    def _evaluate_condition(cond: str, context: Dict[str, str]) -> bool:
        import re
        pattern = r"\{([^}]+)\}\s*==\s*'([^']+)'"
        match = re.search(pattern, cond)
        if match:
            var = match.group(1)
            expected = match.group(2)
            return context.get(var, "") == expected
        if "||" in cond:
            parts = cond.split("||")
            return any(ThemeElement._evaluate_condition(p.strip(), context) for p in parts)
        return False

    # Dentro de la clase ThemeElement
    def get_property_nodes(self, prop_name: str) -> list:
        """Devuelve todos los nodos hijos que tienen la etiqueta prop_name."""
        return [child for child in self.children if child.tag == prop_name]

    def delete_property_nodes(self, prop_name: str):
        """Elimina todos los nodos hijos con la etiqueta prop_name."""
        self.children = [child for child in self.children if child.tag != prop_name]


class ThemeView:
    """Una vista de Batocera: system, basic, detailed, video, grid o customView."""

    STANDARD_VIEWS = ["system", "basic", "detailed", "gamecarousel", "grid"]

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
        self.includes: List[Dict[str, str]] = []  # cada dict: {"path": "...", "ifArch": "...", "lang": "..."}
        self.variables: Dict[str, str] = {}
        self.subsets: List[XmlNode] = []  # nodos <subset>
        self.root_attrib: Dict[str, str] = {}  # atributos de la raíz <theme>
        self.raw_xml: str = ""
        self.xml_declaration: bool = False

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
        root = ET.Element("theme", self.root_attrib)
        ET.SubElement(root, "formatVersion").text = str(self.format_version)

        # Variables
        if self.variables:
            vars_elem = ET.SubElement(root, "variables")
            for k, v in self.variables.items():
                ET.SubElement(vars_elem, k).text = v

        # Includes (con atributos ifArch, lang, etc.)
        for inc in self.includes:
            attrib = {}
            if "ifArch" in inc:
                attrib["ifArch"] = inc["ifArch"]
            if "lang" in inc:
                attrib["lang"] = inc["lang"]
            # Puedes añadir más según necesites
            inc_elem = ET.SubElement(root, "include", attrib)
            inc_elem.text = inc.get("path", "")

        # Subsets
        for subset_node in self.subsets:
            root.append(subset_node.to_xml_element())

        # Vistas
        for view in self.views:
            if view.is_custom:
                view_elem = ET.SubElement(root, "customView", attrib={"name": view.name})
                if view.inherits:
                    view_elem.set("inherits", view.inherits)
            else:
                view_elem = ET.SubElement(root, "view", attrib={"name": view.name})
            for elem in view.elements:
                # Aquí usamos el método to_xml_element de ThemeElement (hereda de XmlNode)
                view_elem.append(elem.to_xml_element())

        # Generar string bonito
        raw = ET.tostring(root, encoding="unicode")
        try:
            dom = minidom.parseString(raw)
            pretty = dom.toprettyxml(indent="\t", newl="\n")
            lines = pretty.split("\n")
            if lines[0].startswith("<?xml"):
                pretty = "\n".join(lines[1:])
            result = pretty
        except Exception:
            result = raw

        if self.xml_declaration:
            result = '<?xml version="1.0" encoding="UTF-8"?>\n\n' + result
        self.raw_xml = result
        return result

    @staticmethod
    def _parse_node_to_xmlnode(elem: ET.Element) -> XmlNode:
        """Convierte recursivamente un elemento XML en un XmlNode."""
        node = XmlNode(elem.tag, dict(elem.attrib), elem.text or "")
        for child in elem:
            node.children.append(ThemeModel._parse_node_to_xmlnode(child))
        return node

    @staticmethod
    def from_xml(xml_str: str) -> Optional['ThemeModel']:
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None

        model = ThemeModel()
        model.raw_xml = xml_str
        # Detectar declaración XML
        if xml_str.lstrip().startswith('<?xml'):
            model.xml_declaration = True
        model.root_attrib = dict(root.attrib)

        # formatVersion
        fv = root.find("formatVersion")
        if fv is not None and fv.text:
            try:
                model.format_version = int(fv.text.strip())
            except ValueError:
                pass

        # Variables
        vars_elem = root.find("variables")
        if vars_elem is not None:
            for child in vars_elem:
                if child.text:
                    model.variables[child.tag] = child.text.strip()

        # Includes
        for inc in root.findall("include"):
            inc_data = {"path": inc.text.strip() if inc.text else ""}
            if "ifArch" in inc.attrib:
                inc_data["ifArch"] = inc.attrib["ifArch"]
            if "lang" in inc.attrib:
                inc_data["lang"] = inc.attrib["lang"]
            model.includes.append(inc_data)

        # Subsets
        for subset_el in root.findall("subset"):
            subset_node = XmlNode("subset", dict(subset_el.attrib))
            for inc_el in subset_el.findall("include"):
                inc_node = XmlNode("include", dict(inc_el.attrib), inc_el.text or "")
                subset_node.children.append(inc_node)
            model.subsets.append(subset_node)

        # Views
        def parse_view(view_el, is_custom):
            view = ThemeView(
                name=view_el.attrib.get("name", "system"),
                inherits=view_el.attrib.get("inherits", ""),
                is_custom=is_custom
            )
            for child_el in view_el:
                elem = ThemeElement(
                    tag=child_el.tag,
                    name=child_el.attrib.get("name", ""),
                    extra=child_el.attrib.get("extra", "false").lower() == "true"
                )
                # Añadir todos los hijos (propiedades y subelementos) de forma recursiva
                for sub_el in child_el:
                    elem.children.append(ThemeModel._parse_node_to_xmlnode(sub_el))
                view.elements.append(elem)
            return view

        for view_el in root.findall("view"):
            model.views.append(parse_view(view_el, is_custom=False))
        for view_el in root.findall("customView"):
            model.views.append(parse_view(view_el, is_custom=True))

        return model


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