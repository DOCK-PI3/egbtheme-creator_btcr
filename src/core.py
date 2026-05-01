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

    # Propiedades comunes por tipo para el inspector
    COMMON_PROPS = {
        "image":      ["path", "pos", "size", "origin", "color", "opacity", "zIndex",
                       "tile", "visible", "rotation"],
        "video":      ["path", "pos", "size", "origin", "opacity", "zIndex",
                       "delay", "loops", "visible"],
        "text":       ["text", "pos", "size", "origin", "color", "fontSize",
                       "fontPath", "alignment", "zIndex", "visible"],
        "rating":     ["pos", "size", "origin", "filledPath", "unfilledPath",
                       "color", "opacity", "zIndex", "visible"],
        "datetime":   ["pos", "size", "origin", "color", "fontSize",
                       "fontPath", "format", "zIndex", "visible"],
        "helpsystem": ["pos", "iconSize", "textColor", "iconColor",
                       "fontPath", "visible"],
        "textlist":   ["pos", "size", "origin", "selectorColor", "selectedColor",
                       "primaryColor", "secondaryColor", "fontPath", "fontSize",
                       "alignment", "zIndex", "visible"],
        "gamecarousel": ["pos", "size", "origin", "color", "colorEnd",
                         "logoSize", "maxLogoCount", "logoPos", "zIndex", "visible"],
    }

    def __init__(self, name: str = "", element_type: str = "image",
                 extra: bool = False, properties: Optional[Dict[str, str]] = None):
        self.name = name or ("e_" + str(uuid.uuid4())[:6])
        self.element_type = element_type
        self.extra = extra
        self.properties: Dict[str, str] = properties or {}

    def suggested_props(self) -> List[str]:
        return self.COMMON_PROPS.get(self.element_type, ["pos", "size", "path"])

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "element_type": self.element_type,
            "extra": self.extra,
            "properties": dict(self.properties),
        }

    @staticmethod
    def from_dict(d: Dict) -> 'ThemeElement':
        return ThemeElement(
            name=d.get("name", ""),
            element_type=d.get("element_type", "image"),
            extra=bool(d.get("extra", False)),
            properties=d.get("properties", {}),
        )


class ThemeView:
    """Una vista de Batocera: system, basic, detailed, video, grid o customView."""

    STANDARD_VIEWS = ["system", "basic", "detailed", "video", "grid"]

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
                for prop_name, prop_val in elem.properties.items():
                    ET.SubElement(elem_el, prop_name).text = str(prop_val)

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
                    properties={sub.tag: (sub.text or "") for sub in child},
                )
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
    '.ttf', '.otf', '.xml',
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


def validate_theme(theme: ThemeModel) -> tuple:
    errors: List[str] = []
    if not theme.name or not theme.name.strip():
        errors.append("El nombre del tema está vacío.")
    if not theme.views:
        errors.append("El tema no contiene ninguna vista (view).")
    for view in theme.views:
        if not view.name:
            errors.append("Una vista no tiene nombre.")
        for elem in view.elements:
            if not elem.name:
                errors.append(f"Elemento en vista '{view.name}' sin nombre.")
    return (len(errors) == 0, errors)


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
