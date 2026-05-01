import sys
import os
import re
import subprocess

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem,
    QGraphicsTextItem, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QSplitter, QPlainTextEdit, QDialog, QDialogButtonBox, QMessageBox,
    QFileDialog, QScrollArea, QGroupBox, QInputDialog, QTextEdit, QToolButton,
)
from PySide6.QtGui import (
    QPixmap, QDrag, QPainter, QPen, QColor, QBrush, QFont, QSyntaxHighlighter,
    QTextCharFormat, QAction, QIcon, QUndoStack, QUndoCommand, QPalette,
)
from PySide6.QtCore import Qt, QMimeData, Signal, QSize

from core import (ThemeModel, ThemeView, ThemeElement, ThemeSet,
                  scan_assets, validate_theme, export_theme, export_theme_set)

# Headless test mode
if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    def _headless_test():
        t = ThemeModel(name="headless_test", format_version=7)
        v = t.add_view("system")
        v.elements.append(ThemeElement("e_bg", "image", True,
                          {"path": "./bg.jpg", "pos": "0.5 0.5",
                           "size": "1.0 1.0", "origin": "0.5 0.5"}))
        result = export_theme(t, os.path.join(os.getcwd(), "themes_export_headless"), "assets")
        print("Headless export OK:", result)
        return 0
    sys.exit(_headless_test())


# ---------------------------------------------------------------------------
# XML Syntax Highlighter
# ---------------------------------------------------------------------------
class XMLHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self._tag_fmt = QTextCharFormat()
        self._tag_fmt.setForeground(QColor("#569cd6"))
        self._attr_fmt = QTextCharFormat()
        self._attr_fmt.setForeground(QColor("#9cdcfe"))
        self._val_fmt = QTextCharFormat()
        self._val_fmt.setForeground(QColor("#ce9178"))
        self._comment_fmt = QTextCharFormat()
        self._comment_fmt.setForeground(QColor("#6a9955"))
        self._tag_re = re.compile(r"</?[\w:.-]+|/>|>")
        self._attr_re = re.compile(r'\b[\w:.-]+=')
        self._val_re = re.compile(r'"[^"]*"')
        self._comment_re = re.compile(r'<!--.*?-->', re.DOTALL)

    def highlightBlock(self, text: str):
        for m in self._comment_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._comment_fmt)
        for m in self._tag_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._tag_fmt)
        for m in self._attr_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._attr_fmt)
        for m in self._val_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._val_fmt)


# ---------------------------------------------------------------------------
# Undo / Redo Commands
# ---------------------------------------------------------------------------
class AddElemCmd(QUndoCommand):
    def __init__(self, view: ThemeView, elem: ThemeElement,
                 canvas, refresh_fn=None):
        super().__init__(f"Añadir [{elem.element_type}] '{elem.name}'")
        self.view = view
        self.elem = elem
        self.canvas = canvas
        self.refresh_fn = refresh_fn
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return   # ya insertado en el drop/add
        if self.elem not in self.view.elements:
            self.view.elements.append(self.elem)
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()

    def undo(self):
        if self.elem in self.view.elements:
            self.view.elements.remove(self.elem)
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()


class DelElemCmd(QUndoCommand):
    def __init__(self, view: ThemeView, elem: ThemeElement,
                 canvas, refresh_fn=None):
        super().__init__(f"Eliminar [{elem.element_type}] '{elem.name}'")
        self.view = view
        self.elem = elem
        self.canvas = canvas
        self.refresh_fn = refresh_fn
        self.idx = view.elements.index(elem) if elem in view.elements else -1

    def redo(self):
        if self.elem in self.view.elements:
            self.idx = self.view.elements.index(self.elem)
            self.view.elements.remove(self.elem)
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()

    def undo(self):
        if self.elem not in self.view.elements:
            if self.idx >= 0:
                self.view.elements.insert(self.idx, self.elem)
            else:
                self.view.elements.append(self.elem)
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()


class MoveElemCmd(QUndoCommand):
    def __init__(self, elem: ThemeElement, old_pos: str, new_pos: str,
                 canvas, refresh_fn=None):
        super().__init__(f"Mover '{elem.name}'")
        self.elem = elem
        self.old_pos = old_pos
        self.new_pos = new_pos
        self.canvas = canvas
        self.refresh_fn = refresh_fn
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return
        self.elem.properties["pos"] = self.new_pos
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()

    def undo(self):
        self.elem.properties["pos"] = self.old_pos
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()


class PropsCmd(QUndoCommand):
    def __init__(self, elem: ThemeElement, old_state: dict, new_state: dict,
                 canvas, refresh_fn=None):
        super().__init__(f"Editar propiedades '{elem.name}'")
        self.elem = elem
        self.old_state = old_state
        self.new_state = new_state
        self.canvas = canvas
        self.refresh_fn = refresh_fn

    def _apply(self, state: dict):
        self.elem.name = state["name"]
        self.elem.extra = state["extra"]
        self.elem.properties = dict(state["properties"])
        self.canvas.rebuild()
        if self.refresh_fn:
            self.refresh_fn()

    def redo(self):
        self._apply(self.new_state)

    def undo(self):
        self._apply(self.old_state)


# ---------------------------------------------------------------------------
# XML Editor Tab  (con gestión de <include>)
# ---------------------------------------------------------------------------
class XMLEditorTab(QWidget):
    model_changed = Signal()

    def __init__(self, theme_model: ThemeModel):
        super().__init__()
        self.theme_model = theme_model
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Barra de herramientas
        bar = QHBoxLayout()
        btn_new = QPushButton("Nuevo XML")
        btn_load = QPushButton("Abrir…")
        btn_save = QPushButton("Guardar…")
        btn_apply = QPushButton("Aplicar al modelo")
        for b, fn in ((btn_new, self._new_xml), (btn_load, self._load_file),
                      (btn_save, self._save_file), (btn_apply, self._apply_to_model)):
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch()
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)

        # Editor principal
        editor_widget = QWidget()
        ev = QVBoxLayout(editor_widget)
        ev.setContentsMargins(0, 0, 0, 0)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Monospace", 10))
        self.editor.setStyleSheet("background:#1e1e1e; color:#d4d4d4;")
        self.editor.setPlaceholderText("theme.xml de Batocera aquí...")
        XMLHighlighter(self.editor.document())
        ev.addWidget(self.editor)
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color:#f88; padding:4px;")
        ev.addWidget(self.status_lbl)
        splitter.addWidget(editor_widget)

        # Panel lateral: <include> tags
        inc_widget = QWidget()
        inc_widget.setMaximumWidth(280)
        iv = QVBoxLayout(inc_widget)
        iv.setContentsMargins(4, 4, 4, 4)
        iv.addWidget(QLabel("<b>Includes</b> (<include>)"))
        iv.addWidget(QLabel("Archivos XML incluidos por este tema:"))
        self._inc_list = QListWidget()
        iv.addWidget(self._inc_list)
        inc_bar = QHBoxLayout()
        btn_inc_add = QPushButton("+ Añadir include")
        btn_inc_del = QPushButton("- Eliminar")
        btn_inc_add.clicked.connect(self._add_include)
        btn_inc_del.clicked.connect(self._del_include)
        inc_bar.addWidget(btn_inc_add)
        inc_bar.addWidget(btn_inc_del)
        iv.addLayout(inc_bar)
        iv.addWidget(QLabel("Ruta relativa (ej: ./common.xml):"))
        self._inc_edit = QLineEdit()
        self._inc_edit.setPlaceholderText("./common.xml")
        iv.addWidget(self._inc_edit)
        iv.addStretch()
        splitter.addWidget(inc_widget)

        layout.addWidget(splitter)

    def _refresh_includes(self):
        self._inc_list.clear()
        for inc in self.theme_model.includes:
            self._inc_list.addItem(inc)

    def _add_include(self):
        path = self._inc_edit.text().strip()
        if path and path not in self.theme_model.includes:
            self.theme_model.includes.append(path)
            self._refresh_includes()
            self._inc_edit.clear()

    def _del_include(self):
        item = self._inc_list.currentItem()
        if item:
            self.theme_model.includes = [
                i for i in self.theme_model.includes if i != item.text()]
            self._refresh_includes()

    def refresh_from_model(self):
        self.editor.setPlainText(self.theme_model.to_xml())
        self._refresh_includes()

    def _new_xml(self):
        self.editor.setPlainText(
            "<theme>\n\t<formatVersion>7</formatVersion>\n"
            "\t<view name=\"system\">\n"
            "\t\t<image name=\"e_background\" extra=\"true\">\n"
            "\t\t\t<path>./bg.jpg</path>\n"
            "\t\t\t<pos>0.5 0.5</pos>\n"
            "\t\t\t<size>1.0 1.0</size>\n"
            "\t\t\t<origin>0.5 0.5</origin>\n"
            "\t\t</image>\n"
            "\t</view>\n</theme>"
        )

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir theme.xml", os.getcwd(), "XML files (*.xml);;All (*)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.editor.setPlainText(f.read())
                self.status_lbl.setText(f"Cargado: {path}")
            except Exception as e:
                self.status_lbl.setText(f"Error: {e}")

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar theme.xml",
            os.path.join(os.getcwd(), "theme.xml"), "XML files (*.xml)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.editor.toPlainText())
                self.status_lbl.setText(f"Guardado: {path}")
            except Exception as e:
                self.status_lbl.setText(f"Error: {e}")

    def _apply_to_model(self):
        xml = self.editor.toPlainText().strip()
        if not xml:
            self.status_lbl.setText("El editor está vacío.")
            return
        new_model = ThemeModel.from_xml(xml)
        if new_model is None:
            self.status_lbl.setText("XML inválido.")
            return
        self.theme_model.views = new_model.views
        self.theme_model.includes = new_model.includes
        self.theme_model.format_version = new_model.format_version
        self.theme_model.raw_xml = new_model.raw_xml
        self._refresh_includes()
        self.status_lbl.setText("Modelo actualizado.")
        self.model_changed.emit()


# ---------------------------------------------------------------------------
# Canvas (1280×720 coordenadas Batocera normalizadas 0-1)
# ---------------------------------------------------------------------------
CANVAS_W, CANVAS_H = 1280, 720

ELEM_COLORS = {
    "image":        QColor("#1565C0"),
    "video":        QColor("#6A1B9A"),
    "text":         QColor("#2E7D32"),
    "rating":       QColor("#E65100"),
    "datetime":     QColor("#00838F"),
    "helpsystem":   QColor("#AD1457"),
    "textlist":     QColor("#4E342E"),
    "gamecarousel": QColor("#283593"),
}


def _parse_pos(val: str):
    parts = val.strip().split()
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return 0.5, 0.5


def _elem_rect(elem: ThemeElement):
    pos = _parse_pos(elem.properties.get("pos", "0.5 0.5"))
    size = _parse_pos(elem.properties.get("size", "0.2 0.2"))
    origin = _parse_pos(elem.properties.get("origin", "0.5 0.5"))
    w_px = max(size[0] * CANVAS_W, 10)
    h_px = max(size[1] * CANVAS_H, 10)
    x_px = pos[0] * CANVAS_W - origin[0] * w_px
    y_px = pos[1] * CANVAS_H - origin[1] * h_px
    return x_px, y_px, w_px, h_px


class CanvasElem(QGraphicsRectItem):
    def __init__(self, elem: ThemeElement, assets_root: str, undo_stack=None):
        x, y, w, h = _elem_rect(elem)
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.elem = elem
        self.assets_root = assets_root
        self._undo_stack = undo_stack
        self._drag_start_pos: str | None = None

        color = ELEM_COLORS.get(elem.element_type, QColor("#607D8B"))
        self.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 80)))
        self.setPen(QPen(color, 2))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        try:
            self.setZValue(float(elem.properties.get("zIndex", "0") or "0"))
        except ValueError:
            pass

        # Imagen de preview (solo raster)
        if elem.element_type in ("image", "video"):
            path_val = elem.properties.get("path", "")
            if path_val.startswith("./"):
                abs_path = os.path.join(assets_root, path_val[2:])
                ext = os.path.splitext(abs_path)[1].lower()
                if ext not in (".svg",):
                    pix = QPixmap(abs_path)
                    if not pix.isNull():
                        pix_item = QGraphicsPixmapItem(
                            pix.scaled(int(w), int(h), Qt.IgnoreAspectRatio,
                                       Qt.SmoothTransformation), self)
                        pix_item.setOpacity(0.75)

        lbl = QGraphicsTextItem(self)
        lbl.setPlainText(f"[{elem.element_type}]\n{elem.name}")
        lbl.setDefaultTextColor(QColor("#ffffff"))
        lbl.setFont(QFont("Sans", 9, QFont.Bold))
        lbl.setPos(4, 4)

    def mousePressEvent(self, event):
        self._drag_start_pos = self.elem.properties.get("pos", "0.5 0.5")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        new_pos = self.elem.properties.get("pos", "0.5 0.5")
        if (self._drag_start_pos is not None
                and self._drag_start_pos != new_pos
                and self._undo_stack is not None):
            canvas = (self.scene().views()[0]
                      if self.scene() and self.scene().views() else None)
            cmd = MoveElemCmd(self.elem, self._drag_start_pos, new_pos, canvas)
            self._undo_stack.push(cmd)
        self._drag_start_pos = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            sx_s = self.elem.properties.get("size", "0.2 0.2").split()
            sx = float(sx_s[0]) if sx_s else 0.2
            sy = float(sx_s[1]) if len(sx_s) > 1 else 0.2
            ox, oy = _parse_pos(self.elem.properties.get("origin", "0.5 0.5"))
            nx = (value.x() + ox * sx * CANVAS_W) / CANVAS_W
            ny = (value.y() + oy * sy * CANVAS_H) / CANVAS_H
            self.elem.properties["pos"] = f"{nx:.4f} {ny:.4f}"
        return super().itemChange(change, value)


class ThemeCanvas(QGraphicsView):
    element_selected = Signal(object)

    def __init__(self, assets_root: str, undo_stack=None):
        super().__init__()
        self.assets_root = assets_root
        self._undo_stack = undo_stack
        self._scene = QGraphicsScene(0, 0, CANVAS_W, CANVAS_H)
        self.setScene(self._scene)
        self._scene.setBackgroundBrush(QBrush(QColor("#1a1a2e")))
        self._scene.addRect(0, 0, CANVAS_W, CANVAS_H,
                            QPen(QColor("#555"), 2),
                            QBrush(Qt.transparent)).setZValue(-100)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setMinimumSize(640, 360)
        self.fitInView(0, 0, CANVAS_W, CANVAS_H, Qt.KeepAspectRatio)
        self.setAcceptDrops(True)
        self._scene.selectionChanged.connect(self._on_sel_changed)
        self._current_view: ThemeView | None = None
        self._elem_items: dict = {}
        self._refresh_fn = None   # callback cuando drop añade elem

    def set_view(self, view: ThemeView | None):
        self._current_view = view
        self.rebuild()

    def rebuild(self):
        for item in list(self._elem_items.values()):
            self._scene.removeItem(item)
        self._elem_items.clear()
        if self._current_view is None:
            return
        for elem in self._current_view.elements:
            item = CanvasElem(elem, self.assets_root, self._undo_stack)
            self._scene.addItem(item)
            self._elem_items[id(elem)] = item

    def select_element(self, elem: ThemeElement):
        for key, item in self._elem_items.items():
            item.setSelected(item.elem is elem)

    def _on_sel_changed(self):
        items = self._scene.selectedItems()
        if items and isinstance(items[0], CanvasElem):
            self.element_selected.emit(items[0].elem)
        else:
            self.element_selected.emit(None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(0, 0, CANVAS_W, CANVAS_H, Qt.KeepAspectRatio)

    # Drag & drop desde asset browser
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasText() or self._current_view is None:
            super().dropEvent(event)
            return
        rel_path = event.mimeData().text()
        sp = self.mapToScene(event.position().toPoint())
        ext = os.path.splitext(rel_path)[1].lower()
        etype = "video" if ext in (".mp4", ".mkv", ".avi") else "image"
        elem = ThemeElement(
            name=f"e_{os.path.splitext(os.path.basename(rel_path))[0]}",
            element_type=etype,
            extra=True,
            properties={
                "path": f"./{rel_path}",
                "pos": f"{sp.x() / CANVAS_W:.4f} {sp.y() / CANVAS_H:.4f}",
                "size": "0.3 0.3",
                "origin": "0.5 0.5",
            },
        )
        self._current_view.elements.append(elem)
        item = CanvasElem(elem, self.assets_root, self._undo_stack)
        self._scene.addItem(item)
        self._elem_items[id(elem)] = item
        event.acceptProposedAction()
        self.element_selected.emit(elem)
        if self._undo_stack is not None:
            cmd = AddElemCmd(self._current_view, elem, self,
                             refresh_fn=self._refresh_fn)
            self._undo_stack.push(cmd)


# ---------------------------------------------------------------------------
# Inspector de propiedades
# ---------------------------------------------------------------------------
class PropertiesPanel(QWidget):
    properties_changed = Signal()

    def __init__(self, undo_stack=None):
        super().__init__()
        self._undo_stack = undo_stack
        self._elem: ThemeElement | None = None
        self._rows: dict = {}
        self._canvas_ref = None
        layout = QVBoxLayout(self)

        lbl = QLabel("Inspector")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:4px;")
        layout.addWidget(lbl)
        self._name_edit = QLineEdit()
        self._type_lbl = QLabel("Tipo: -")
        self._extra_cb = QCheckBox("extra=\"true\"")
        layout.addWidget(QLabel("Nombre:"))
        layout.addWidget(self._name_edit)
        layout.addWidget(self._type_lbl)
        layout.addWidget(self._extra_cb)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._form_widget = QWidget()
        self._form = QFormLayout(self._form_widget)
        self._form.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(self._form_widget)
        layout.addWidget(scroll)

        add_bar = QHBoxLayout()
        self._new_key = QLineEdit()
        self._new_key.setPlaceholderText("propiedad")
        self._new_val = QLineEdit()
        self._new_val.setPlaceholderText("valor")
        btn_add = QPushButton("+")
        btn_add.setFixedWidth(32)
        btn_add.clicked.connect(self._add_prop)
        add_bar.addWidget(self._new_key)
        add_bar.addWidget(self._new_val)
        add_bar.addWidget(btn_add)
        layout.addLayout(add_bar)

        btn_apply = QPushButton("Aplicar cambios")
        btn_apply.setStyleSheet("background:#1565C0; color:white;")
        btn_apply.clicked.connect(self._apply)
        layout.addWidget(btn_apply)
        self.setMinimumWidth(220)

    def set_element(self, elem: ThemeElement | None, canvas=None):
        self._elem = elem
        self._canvas_ref = canvas
        self._rows.clear()
        while self._form.rowCount():
            self._form.removeRow(0)
        if elem is None:
            self._name_edit.setText("")
            self._type_lbl.setText("Tipo: -")
            self._extra_cb.setChecked(False)
            return
        self._name_edit.setText(elem.name)
        self._type_lbl.setText(f"Tipo: {elem.element_type}")
        self._extra_cb.setChecked(elem.extra)
        shown: list[str] = []
        for p in elem.suggested_props():
            if p not in shown:
                shown.append(p)
        for p in elem.properties.keys():
            if p not in shown:
                shown.append(p)
        for prop in shown:
            edit = QLineEdit(elem.properties.get(prop, ""))
            edit.setPlaceholderText(prop)
            self._form.addRow(prop + ":", edit)
            self._rows[prop] = edit

    def _add_prop(self):
        key = self._new_key.text().strip()
        val = self._new_val.text()
        if key and self._elem:
            self._elem.properties[key] = val
            self.set_element(self._elem, self._canvas_ref)
            self._new_key.clear()
            self._new_val.clear()

    def _apply(self):
        if not self._elem:
            return
        old_state = {
            "name": self._elem.name,
            "extra": self._elem.extra,
            "properties": dict(self._elem.properties),
        }
        new_props = {p: e.text() for p, e in self._rows.items()}
        new_state = {
            "name": self._name_edit.text().strip() or self._elem.name,
            "extra": self._extra_cb.isChecked(),
            "properties": new_props,
        }
        if old_state == new_state:
            return
        if self._undo_stack and self._canvas_ref:
            cmd = PropsCmd(self._elem, old_state, new_state,
                           self._canvas_ref,
                           refresh_fn=lambda: self.properties_changed.emit())
            self._undo_stack.push(cmd)
        else:
            self._elem.name = new_state["name"]
            self._elem.extra = new_state["extra"]
            self._elem.properties = new_props
            self.properties_changed.emit()


# ---------------------------------------------------------------------------
# Asset Browser
# ---------------------------------------------------------------------------
class AssetBrowser(QListWidget):
    def __init__(self, assets_root: str):
        super().__init__()
        self.assets_root = assets_root
        self.setDragEnabled(True)
        self.setIconSize(QSize(32, 32))
        self.setToolTip("Arrastra un asset al canvas para añadirlo")
        self.refresh()

    def refresh(self):
        self.clear()
        for rel in scan_assets(self.assets_root):
            item = QListWidgetItem(rel)
            item.setData(Qt.UserRole, rel)
            ext = os.path.splitext(rel)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                pix = QPixmap(os.path.join(self.assets_root, rel))
                if not pix.isNull():
                    item.setIcon(QIcon(pix.scaled(
                        32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.addItem(item)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        mime = QMimeData()
        mime.setText(item.data(Qt.UserRole))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


# ---------------------------------------------------------------------------
# Lista de elementos
# ---------------------------------------------------------------------------
class ElementListPanel(QWidget):
    element_selected = Signal(object)
    element_deleted = Signal(object)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Elementos en la vista")
        lbl.setStyleSheet("font-weight:bold; padding:4px;")
        layout.addWidget(lbl)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_click)
        layout.addWidget(self._list)
        btn_del = QPushButton("Eliminar seleccionado")
        btn_del.setStyleSheet("color:#f44;")
        btn_del.clicked.connect(self._delete)
        layout.addWidget(btn_del)
        self._elems: list = []

    def refresh(self, view: ThemeView | None):
        self._list.clear()
        self._elems = []
        if view is None:
            return
        for elem in view.elements:
            item = QListWidgetItem(f"[{elem.element_type}] {elem.name}")
            item.setForeground(ELEM_COLORS.get(elem.element_type, QColor("#607D8B")))
            self._list.addItem(item)
            self._elems.append(elem)

    def select_elem(self, elem: ThemeElement):
        for i, e in enumerate(self._elems):
            if e is elem:
                self._list.setCurrentRow(i)
                break

    def _on_click(self, item):
        row = self._list.row(item)
        if 0 <= row < len(self._elems):
            self.element_selected.emit(self._elems[row])

    def _delete(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._elems):
            self.element_deleted.emit(self._elems[row])


# ---------------------------------------------------------------------------
# Diálogo Añadir Elemento  (con soporte customView y vistas)
# ---------------------------------------------------------------------------
class AddElementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir Elemento")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit("e_nuevo")
        self.type_cb = QComboBox()
        self.type_cb.addItems(ThemeElement.TYPES)
        self.extra_cb = QCheckBox("extra=\"true\"")
        self.extra_cb.setChecked(True)
        layout.addRow("Nombre:", self.name_edit)
        layout.addRow("Tipo:", self.type_cb)
        layout.addRow("", self.extra_cb)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_element(self) -> ThemeElement:
        etype = self.type_cb.currentText()
        defaults = {
            "image":      {"path": "./", "pos": "0.5 0.5", "size": "0.5 0.5", "origin": "0.5 0.5"},
            "video":      {"path": "./", "pos": "0.5 0.5", "size": "0.5 0.5", "origin": "0.5 0.5"},
            "text":       {"pos": "0.5 0.5", "size": "0.5 0.1", "origin": "0.5 0.5",
                           "color": "FFFFFF", "fontSize": "0.04", "text": ""},
            "rating":     {"pos": "0.5 0.9", "size": "0.3 0.06", "origin": "0.5 0.5",
                           "filledPath": "./", "unfilledPath": "./"},
            "datetime":   {"pos": "0.5 0.1", "size": "0.3 0.05", "origin": "0.5 0.5",
                           "color": "FFFFFF", "fontSize": "0.03", "format": "%Y-%m-%d"},
            "helpsystem": {"pos": "0.5 0.96", "origin": "0.5 0.5",
                           "textColor": "FFFFFF", "iconColor": "FFFFFF"},
            "textlist":   {"pos": "0.5 0.5", "size": "0.4 0.8", "origin": "0.5 0.5",
                           "primaryColor": "FFFFFF", "secondaryColor": "AAAAAA",
                           "selectedColor": "FFFF00", "selectorColor": "333333"},
            "gamecarousel": {"pos": "0.5 0.4", "size": "1.0 0.4", "origin": "0.5 0.5",
                             "color": "FFFFFF", "logoSize": "0.25 0.25"},
        }
        return ThemeElement(
            name=self.name_edit.text().strip() or "e_nuevo",
            element_type=etype,
            extra=self.extra_cb.isChecked(),
            properties=dict(defaults.get(etype, {"pos": "0.5 0.5", "size": "0.3 0.3", "origin": "0.5 0.5"})),
        )


class AddViewDialog(QDialog):
    """Añadir vista normal o customView."""

    def __init__(self, existing: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir Vista")
        layout = QFormLayout(self)
        self.name_cb = QComboBox()
        candidates = [v for v in ThemeView.STANDARD_VIEWS if v not in existing]
        self.name_cb.addItems(candidates or ["custom"])
        self.name_cb.setEditable(True)
        self.is_custom_cb = QCheckBox("customView (hereda de otra)")
        self.is_custom_cb.toggled.connect(self._on_custom_toggled)
        self.inherits_edit = QLineEdit()
        self.inherits_edit.setPlaceholderText("Vista base, ej: detailed")
        self.inherits_edit.setEnabled(False)
        layout.addRow("Nombre:", self.name_cb)
        layout.addRow("", self.is_custom_cb)
        layout.addRow("Hereda de:", self.inherits_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_custom_toggled(self, checked: bool):
        self.inherits_edit.setEnabled(checked)

    def get_view(self) -> ThemeView:
        return ThemeView(
            name=self.name_cb.currentText().strip() or "custom",
            inherits=self.inherits_edit.text().strip(),
            is_custom=self.is_custom_cb.isChecked(),
        )


# ---------------------------------------------------------------------------
# Visual Builder Tab
# ---------------------------------------------------------------------------
class VisualBuilderTab(QWidget):
    def __init__(self, theme_model: ThemeModel, assets_root: str):
        super().__init__()
        self.theme_model = theme_model
        self.assets_root = assets_root
        self._current_view: ThemeView | None = None
        self._undo_stack = QUndoStack(self)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Toolbar vistas + undo
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Vista:"))
        self._view_cb = QComboBox()
        self._view_cb.setMinimumWidth(150)
        self._view_cb.currentIndexChanged.connect(self._on_view_changed)
        toolbar.addWidget(self._view_cb)

        btn_add_view = QPushButton("+ Vista")
        btn_del_view = QPushButton("- Vista")
        btn_add_elem = QPushButton("+ Elemento")
        btn_add_view.clicked.connect(self._add_view)
        btn_del_view.clicked.connect(self._delete_view)
        btn_add_elem.clicked.connect(self._add_element)
        for b in (btn_add_view, btn_del_view, btn_add_elem):
            toolbar.addWidget(b)

        toolbar.addWidget(QLabel("  "))  # separador visual

        undo_action = self._undo_stack.createUndoAction(self, "Deshacer")
        undo_action.setShortcut("Ctrl+Z")
        redo_action = self._undo_stack.createRedoAction(self, "Rehacer")
        redo_action.setShortcut("Ctrl+Y")
        btn_undo = QToolButton()
        btn_undo.setDefaultAction(undo_action)
        btn_undo.setText("↩ Deshacer")
        btn_undo.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_redo = QToolButton()
        btn_redo.setDefaultAction(redo_action)
        btn_redo.setText("↪ Rehacer")
        btn_redo.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toolbar.addWidget(btn_undo)
        toolbar.addWidget(btn_redo)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        # Izquierda: assets + lista
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("Assets disponibles:"))
        self._asset_browser = AssetBrowser(self.assets_root)
        lv.addWidget(self._asset_browser, 2)
        self._elem_list = ElementListPanel()
        self._elem_list.element_selected.connect(self._on_elem_from_list)
        self._elem_list.element_deleted.connect(self._on_elem_deleted)
        lv.addWidget(self._elem_list, 1)
        left.setMinimumWidth(200)
        splitter.addWidget(left)

        # Centro: canvas
        self._canvas = ThemeCanvas(self.assets_root, self._undo_stack)
        self._canvas._refresh_fn = self._refresh_elem_list
        self._canvas.element_selected.connect(self._on_elem_from_canvas)
        splitter.addWidget(self._canvas)

        # Derecha: inspector
        self._inspector = PropertiesPanel(self._undo_stack)
        self._inspector.properties_changed.connect(self._on_props_changed)
        splitter.addWidget(self._inspector)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)
        main_layout.addWidget(splitter)

    def refresh_views(self):
        self._view_cb.blockSignals(True)
        self._view_cb.clear()
        for v in self.theme_model.views:
            label = f"[customView] {v.name}" if v.is_custom else v.name
            self._view_cb.addItem(label)
        self._view_cb.blockSignals(False)
        if self.theme_model.views:
            self._view_cb.setCurrentIndex(0)
            self._set_view(self.theme_model.views[0])
        else:
            self._set_view(None)

    def load_model(self, model: ThemeModel):
        """Carga un modelo distinto en el builder (usado por ThemeSet)."""
        self.theme_model = model
        self._undo_stack.clear()
        self.refresh_views()

    def _set_view(self, view: ThemeView | None):
        self._current_view = view
        self._canvas.set_view(view)
        self._elem_list.refresh(view)
        self._inspector.set_element(None)

    def _on_view_changed(self, idx: int):
        if 0 <= idx < len(self.theme_model.views):
            self._set_view(self.theme_model.views[idx])
        else:
            self._set_view(None)

    def _add_view(self):
        existing = [v.name for v in self.theme_model.views]
        dlg = AddViewDialog(existing, self)
        if dlg.exec() == QDialog.Accepted:
            view = dlg.get_view()
            if view.name in existing:
                QMessageBox.warning(self, "Duplicado", f"La vista '{view.name}' ya existe.")
                return
            self.theme_model.views.append(view)
            self.refresh_views()
            idx = len(self.theme_model.views) - 1
            self._view_cb.setCurrentIndex(idx)

    def _delete_view(self):
        if self._current_view is None:
            return
        self.theme_model.remove_view(self._current_view.name)
        self.refresh_views()

    def _add_element(self):
        if self._current_view is None:
            QMessageBox.warning(self, "Sin vista", "Crea primero una vista.")
            return
        dlg = AddElementDialog(self)
        if dlg.exec() == QDialog.Accepted:
            elem = dlg.get_element()
            self._current_view.elements.append(elem)
            self._canvas.rebuild()
            self._elem_list.refresh(self._current_view)
            cmd = AddElemCmd(self._current_view, elem, self._canvas,
                             refresh_fn=self._refresh_elem_list)
            self._undo_stack.push(cmd)
            self._on_elem_from_list(elem)

    def _on_elem_from_list(self, elem: ThemeElement):
        self._inspector.set_element(elem, self._canvas)
        self._canvas.select_element(elem)

    def _on_elem_from_canvas(self, elem: ThemeElement | None):
        self._inspector.set_element(elem, self._canvas)
        if elem:
            self._elem_list.select_elem(elem)

    def _on_elem_deleted(self, elem: ThemeElement):
        if self._current_view:
            cmd = DelElemCmd(self._current_view, elem, self._canvas,
                             refresh_fn=self._refresh_elem_list)
            self._undo_stack.push(cmd)
            self._inspector.set_element(None)

    def _refresh_elem_list(self):
        self._elem_list.refresh(self._current_view)

    def _on_props_changed(self):
        self._canvas.rebuild()
        elem = self._inspector._elem
        if elem:
            self._canvas.select_element(elem)
            self._elem_list.refresh(self._current_view)
            self._elem_list.select_elem(elem)


# ---------------------------------------------------------------------------
# Preview Tab
# ---------------------------------------------------------------------------
class PreviewTab(QWidget):
    def __init__(self, theme_model: ThemeModel, assets_root: str):
        super().__init__()
        self.theme_model = theme_model
        self.assets_root = assets_root
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self._view_cb = QComboBox()
        self._view_cb.currentIndexChanged.connect(self._on_view_changed)
        btn_refresh = QPushButton("Actualizar")
        btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(QLabel("Vista:"))
        bar.addWidget(self._view_cb)
        bar.addWidget(btn_refresh)
        bar.addStretch()
        layout.addLayout(bar)
        self._canvas = ThemeCanvas(assets_root)
        self._canvas.setDragMode(QGraphicsView.NoDrag)
        self._canvas.setAcceptDrops(False)
        layout.addWidget(self._canvas)

    def set_assets_root(self, root: str):
        self.assets_root = root
        self._canvas.assets_root = root

    def refresh(self):
        cur = self._view_cb.currentText()
        self._view_cb.blockSignals(True)
        self._view_cb.clear()
        for v in self.theme_model.views:
            self._view_cb.addItem(v.name)
        idx = next((i for i, v in enumerate(self.theme_model.views)
                    if v.name == cur), 0)
        self._view_cb.setCurrentIndex(idx)
        self._view_cb.blockSignals(False)
        self._load_view(idx)

    def _load_view(self, idx: int):
        if 0 <= idx < len(self.theme_model.views):
            self._canvas.set_view(self.theme_model.views[idx])
        else:
            self._canvas.set_view(None)

    def _on_view_changed(self, idx: int):
        self._load_view(idx)


# ---------------------------------------------------------------------------
# Theme Set Tab  (multi-sistema)
# ---------------------------------------------------------------------------
class ThemeSetTab(QWidget):
    # Emitido cuando el usuario quiere editar un sistema en el builder principal
    load_model_requested = Signal(object, str)   # (ThemeModel, system_name)

    def __init__(self, theme_set: ThemeSet, get_current_model_fn, assets_root: str):
        super().__init__()
        self.theme_set = theme_set
        self.get_current_model_fn = get_current_model_fn
        self.assets_root = assets_root
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)

        # ---- Panel izquierdo: gestión de sistemas ----
        left = QWidget()
        left.setMaximumWidth(280)
        lv = QVBoxLayout(left)

        lv.addWidget(QLabel("<b>Theme Set</b>"))
        lv.addWidget(QLabel("Nombre:"))
        self._set_name = QLineEdit(self.theme_set.name)
        self._set_name.textChanged.connect(
            lambda t: setattr(self.theme_set, "name", t or "mi_theme_set"))
        lv.addWidget(self._set_name)

        lv.addWidget(QLabel("Sistemas:"))
        self._sys_list = QListWidget()
        self._sys_list.currentItemChanged.connect(self._on_sys_selected)
        lv.addWidget(self._sys_list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Sistema")
        btn_del = QPushButton("- Sistema")
        btn_add.clicked.connect(self._add_system)
        btn_del.clicked.connect(self._del_system)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        lv.addLayout(btn_row)

        btn_common = QPushButton("Añadir sistemas comunes (10)")
        btn_common.setToolTip("Añade snes, nes, megadrive, gba, psx, n64, etc.")
        btn_common.clicked.connect(self._add_common)
        lv.addWidget(btn_common)
        lv.addStretch()
        layout.addWidget(left)

        # ---- Panel derecho: info + acciones ----
        right = QWidget()
        rv = QVBoxLayout(right)

        self._info_lbl = QLabel("Selecciona un sistema de la lista.")
        self._info_lbl.setWordWrap(True)
        rv.addWidget(self._info_lbl)

        btn_edit = QPushButton("Editar en Constructor Visual →")
        btn_edit.setStyleSheet("background:#1565C0; color:white; padding:8px; font-weight:bold;")
        btn_edit.setToolTip("Carga el tema de este sistema en el Constructor Visual.")
        btn_edit.clicked.connect(self._edit_in_builder)
        rv.addWidget(btn_edit)

        btn_copy = QPushButton("Copiar tema actual → este sistema")
        btn_copy.setToolTip("Copia el tema del Constructor Visual a este sistema.")
        btn_copy.clicked.connect(self._copy_from_current)
        rv.addWidget(btn_copy)

        rv.addWidget(QLabel("Vista previa theme.xml del sistema:"))
        self._xml_preview = QPlainTextEdit()
        self._xml_preview.setReadOnly(True)
        self._xml_preview.setFont(QFont("Monospace", 9))
        self._xml_preview.setStyleSheet("background:#1e1e1e; color:#d4d4d4;")
        XMLHighlighter(self._xml_preview.document())
        rv.addWidget(self._xml_preview)

        btn_export_set = QPushButton("Exportar Theme Set completo")
        btn_export_set.setStyleSheet("background:#2E7D32; color:white; padding:8px; font-weight:bold;")
        btn_export_set.clicked.connect(self._export_set)
        rv.addWidget(btn_export_set)

        layout.addWidget(right, 1)
        self._refresh_list()

    def _refresh_list(self):
        cur = (self._sys_list.currentItem().data(Qt.UserRole)
               if self._sys_list.currentItem() else None)
        self._sys_list.clear()
        for sys_name in self.theme_set.system_names():
            model = self.theme_set.systems[sys_name]
            n_v = len(model.views)
            n_e = sum(len(v.elements) for v in model.views)
            item = QListWidgetItem(f"{sys_name}  ({n_v} vistas, {n_e} elem.)")
            item.setData(Qt.UserRole, sys_name)
            self._sys_list.addItem(item)
        # Re-seleccionar
        if cur:
            for i in range(self._sys_list.count()):
                if self._sys_list.item(i).data(Qt.UserRole) == cur:
                    self._sys_list.setCurrentRow(i)
                    break

    def _on_sys_selected(self, item, _=None):
        if item is None:
            self._info_lbl.setText("Selecciona un sistema.")
            self._xml_preview.setPlainText("")
            return
        sys_name = item.data(Qt.UserRole)
        model = self.theme_set.systems.get(sys_name)
        if model:
            info = (f"<b>{sys_name}</b><br>"
                    f"Vistas: {', '.join(v.name for v in model.views) or '(ninguna)'}")
            self._info_lbl.setText(info)
            self._xml_preview.setPlainText(model.to_xml())

    def _add_system(self):
        name, ok = QInputDialog.getText(self, "Nuevo Sistema",
                                        "Nombre del sistema (ej: snes):")
        if ok and name.strip():
            self.theme_set.add_system(name.strip())
            self._refresh_list()

    def _del_system(self):
        item = self._sys_list.currentItem()
        if item:
            self.theme_set.remove_system(item.data(Qt.UserRole))
            self._refresh_list()

    def _add_common(self):
        for sys in ThemeSet.COMMON_SYSTEMS[:10]:
            self.theme_set.add_system(sys)
        self._refresh_list()

    def _edit_in_builder(self):
        item = self._sys_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Sin selección", "Selecciona un sistema.")
            return
        sys_name = item.data(Qt.UserRole)
        model = self.theme_set.systems[sys_name]
        self.load_model_requested.emit(model, sys_name)

    def _copy_from_current(self):
        item = self._sys_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Sin selección", "Selecciona un sistema.")
            return
        sys_name = item.data(Qt.UserRole)
        current = self.get_current_model_fn()
        xml = current.to_xml()
        new_model = ThemeModel.from_xml(xml) or ThemeModel(name=sys_name)
        new_model.name = sys_name
        self.theme_set.systems[sys_name] = new_model
        self._refresh_list()
        self._on_sys_selected(item)

    def _export_set(self):
        out_dir = QFileDialog.getExistingDirectory(
            self, "Carpeta de exportación del Theme Set", os.getcwd())
        if not out_dir:
            return
        try:
            result = export_theme_set(self.theme_set, out_dir, self.assets_root)
            QMessageBox.information(
                self, "Theme Set Exportado",
                f"Exportado en:\n{result}\n\n"
                f"Copia la carpeta '{self.theme_set.name}/' a /userdata/themes/ en Batocera.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ---------------------------------------------------------------------------
# Package Tab  (crear AppImage / exe)
# ---------------------------------------------------------------------------
class PackageTab(QWidget):
    def __init__(self, project_root: str):
        super().__init__()
        self.project_root = project_root
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Empaquetado del creador de themes</b>"))
        layout.addWidget(QLabel(
            "Genera un ejecutable distribuible de esta herramienta."))

        # Linux
        grp_linux = QGroupBox("Linux — AppImage")
        gll = QVBoxLayout(grp_linux)
        gll.addWidget(QLabel("Requisitos: appimagetool, python3, PySide6, PyInstaller."))
        btn_appimage = QPushButton("Crear AppImage")
        btn_appimage.setStyleSheet(
            "background:#1565C0; color:white; padding:6px;")
        btn_appimage.clicked.connect(self._build_appimage)
        gll.addWidget(btn_appimage)
        layout.addWidget(grp_linux)

        # Windows
        grp_win = QGroupBox("Windows — Ejecutable .exe")
        glw = QVBoxLayout(grp_win)
        glw.addWidget(QLabel(
            "Requiere Windows con Python3 + PySide6 + PyInstaller.\n"
            "Ejecuta build_windows.ps1 en PowerShell como administrador."))
        btn_win = QPushButton("Copiar script build_windows.ps1 al portapapeles")
        btn_win.clicked.connect(self._copy_win_script)
        glw.addWidget(btn_win)
        layout.addWidget(grp_win)

        # Log
        layout.addWidget(QLabel("Salida del proceso:"))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Monospace", 9))
        self._log.setStyleSheet("background:#1e1e1e; color:#d4d4d4;")
        layout.addWidget(self._log)

    def _log_append(self, text: str):
        self._log.append(text)

    def _build_appimage(self):
        script = os.path.join(self.project_root, "scripts", "build_appimage.sh")
        if not os.path.isfile(script):
            self._log_append("ERROR: no se encontró scripts/build_appimage.sh")
            return
        self._log_append("▶ Iniciando build AppImage…")
        try:
            proc = subprocess.Popen(
                ["bash", script],
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            out, _ = proc.communicate(timeout=180)
            self._log_append(out)
            if proc.returncode == 0:
                self._log_append("✓ AppImage creado correctamente.")
            else:
                self._log_append(f"✗ Error (código {proc.returncode}).")
        except subprocess.TimeoutExpired:
            self._log_append("Timeout: el proceso tardó más de 3 minutos.")
        except Exception as e:
            self._log_append(f"Error: {e}")

    def _copy_win_script(self):
        path = os.path.join(self.project_root, "scripts", "build_windows.ps1")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            QApplication.clipboard().setText(content)
            self._log_append("Script build_windows.ps1 copiado al portapapeles.")
        except Exception as e:
            self._log_append(f"Error: {e}")


# ---------------------------------------------------------------------------
# Ventana Principal
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("egbtheme-creator  —  Batocera Theme Creator")
        self.resize(1400, 850)

        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self._project_root = os.path.dirname(self._base_dir)
        self._assets_root = os.path.join(self._project_root, "assets")

        # Modelo activo (puede ser reemplazado por ThemeSet)
        self.theme_model = ThemeModel(name="mi_tema", format_version=7)
        self._active_system: str | None = None   # para indicar qué sistema se edita

        # Theme Set
        self._theme_set = ThemeSet("mi_theme_set")

        self._build_toolbar()

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # Tab 1: Editor XML
        self._xml_tab = XMLEditorTab(self.theme_model)
        self._xml_tab.model_changed.connect(self._on_model_from_xml)
        self._tabs.addTab(self._xml_tab, "Editor XML")

        # Tab 2: Constructor Visual
        self._builder_tab = VisualBuilderTab(self.theme_model, self._assets_root)
        self._tabs.addTab(self._builder_tab, "Constructor Visual")

        # Tab 3: Vista Previa
        self._preview_tab = PreviewTab(self.theme_model, self._assets_root)
        self._tabs.addTab(self._preview_tab, "Vista Previa")

        # Tab 4: Theme Set multi-sistema
        self._set_tab = ThemeSetTab(
            self._theme_set,
            get_current_model_fn=lambda: self.theme_model,
            assets_root=self._assets_root,
        )
        self._set_tab.load_model_requested.connect(self._load_system_in_builder)
        self._tabs.addTab(self._set_tab, "Theme Set (multi-sistema)")

        # Tab 5: Empaquetar
        self._pkg_tab = PackageTab(self._project_root)
        self._tabs.addTab(self._pkg_tab, "Empaquetar")

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.statusBar().showMessage("Listo — Batocera Theme Creator")

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        tb = self.addToolBar("Principal")
        tb.setMovable(False)

        tb.addWidget(QLabel("  Tema: "))
        self._name_edit = QLineEdit("mi_tema")
        self._name_edit.setFixedWidth(160)
        self._name_edit.textChanged.connect(
            lambda t: setattr(self.theme_model, "name", t or "mi_tema"))
        tb.addWidget(self._name_edit)

        tb.addWidget(QLabel("  formatVersion: "))
        self._fv_edit = QLineEdit("7")
        self._fv_edit.setFixedWidth(36)
        self._fv_edit.textChanged.connect(self._on_fv_changed)
        tb.addWidget(self._fv_edit)

        self._sys_lbl = QLabel("")
        self._sys_lbl.setStyleSheet("color:#9cdcfe; padding:0 8px;")
        tb.addWidget(self._sys_lbl)

        btn_validate = QPushButton("Validar")
        btn_validate.clicked.connect(self._validate)
        tb.addWidget(btn_validate)

        btn_export = QPushButton("  Exportar Tema  ")
        btn_export.setStyleSheet(
            "background:#1565C0; color:white; font-weight:bold; padding:4px 12px;")
        btn_export.clicked.connect(self._export_theme)
        tb.addWidget(btn_export)

    def _on_fv_changed(self, text: str):
        try:
            self.theme_model.format_version = int(text)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    def _on_tab_changed(self, idx: int):
        tab = self._tabs.widget(idx)
        if tab is self._builder_tab:
            self._builder_tab.refresh_views()
        elif tab is self._preview_tab:
            self._preview_tab.refresh()
        elif tab is self._xml_tab:
            self._xml_tab.refresh_from_model()
        elif tab is self._set_tab:
            self._set_tab._refresh_list()

    def _on_model_from_xml(self):
        self._name_edit.setText(self.theme_model.name)
        self._fv_edit.setText(str(self.theme_model.format_version))
        self._builder_tab.refresh_views()

    def _load_system_in_builder(self, model: ThemeModel, sys_name: str):
        """Carga el modelo de un sistema del ThemeSet en el builder."""
        self.theme_model = model
        self._active_system = sys_name
        self._name_edit.setText(model.name)
        self._fv_edit.setText(str(model.format_version))
        self._sys_lbl.setText(f"[Sistema: {sys_name}]")
        # Actualizar referencias
        self._xml_tab.theme_model = model
        self._builder_tab.load_model(model)
        self._preview_tab.theme_model = model
        self._tabs.setCurrentWidget(self._builder_tab)
        self.statusBar().showMessage(
            f"Editando sistema: {sys_name} — recuerda 'Copiar tema actual → este sistema' al terminar.", 8000)

    # ------------------------------------------------------------------
    def _validate(self):
        ok, errors = validate_theme(self.theme_model)
        if ok:
            QMessageBox.information(self, "Validación OK",
                                    "El tema es válido para Batocera.")
        else:
            QMessageBox.warning(self, "Errores de validación", "\n".join(errors))

    def _export_theme(self):
        self.theme_model.name = self._name_edit.text().strip() or "mi_tema"
        out_dir = QFileDialog.getExistingDirectory(
            self, "Carpeta de exportación",
            os.path.join(self._project_root, "themes_export"))
        if not out_dir:
            return
        try:
            result = export_theme(self.theme_model, out_dir, self._assets_root)
            QMessageBox.information(
                self, "Tema Exportado",
                f"Exportado en:\n{result}\n\n"
                f"Copia la carpeta '{self.theme_model.name}/' a /userdata/themes/ en Batocera.")
            self.statusBar().showMessage(f"Exportado: {result}", 8000)
        except Exception as e:
            QMessageBox.critical(self, "Error exportando", str(e))


# ---------------------------------------------------------------------------
def run_app():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#2b2b2b"))
    palette.setColor(QPalette.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Base, QColor("#1e1e1e"))
    palette.setColor(QPalette.AlternateBase, QColor("#2b2b2b"))
    palette.setColor(QPalette.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.Button, QColor("#3c3c3c"))
    palette.setColor(QPalette.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Highlight, QColor("#1565C0"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
