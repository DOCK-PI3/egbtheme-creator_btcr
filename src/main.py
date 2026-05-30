import sys
import os
import re
import darkdetect
import shutil
from typing import List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem,
    QGraphicsTextItem, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QSplitter, QPlainTextEdit, QDialog, QDialogButtonBox, QMessageBox,
    QFileDialog, QScrollArea, QInputDialog, QTextEdit, QToolButton,
    QStatusBar, QTreeView, QFileSystemModel, QMenu, QGridLayout, QFrame, QListView, QAbstractItemView,
    QProgressDialog, QProgressBar
)

from PySide6.QtGui import (
    QPixmap, QDrag, QPen, QColor, QBrush, QFont, QSyntaxHighlighter, QTransform,
    QTextCharFormat, QIcon, QUndoStack, QUndoCommand, QAction, QKeySequence, QPainter,
    QFontDatabase, QFontMetrics
)

from PySide6.QtCore import (
    Qt, QMimeData, QSize, QDir, QRectF, QPointF, QTimer, Signal, QSortFilterProxyModel,
    QTranslator, QLibraryInfo
)

from PySide6.QtSvg import QSvgRenderer

from core import (ThemeModel, ThemeView, ThemeElement, ThemeSet, export_theme, export_theme_set,
                  ThemeVariableResolver, validate_theme_xml, ConditionalValue, XmlNode)

from scripts.new_theme_basic import create_minimal_theme
from scripts.update_aplication import parse_changelog, comprobar_actualizaciones, show_changelog_if_new
from logger_config import setup_logger, install_global_hooks, ExceptionAwareApplication

# VERSIÓN DE LA APLICACIÓN
APP_VERSION = "0.9.0"


# Headless test mode
if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    def _headless_test():
        t = ThemeModel(name="headless_test", format_version=7)
        v = t.add_view("system")
        v.elements.append(ThemeElement("e_bg", "image", True,
                                       {"path": "./bg.jpg", "pos": "0.5 0.5", "size": "1.0 1.0"}))
        result = export_theme(t, os.path.join(os.getcwd(), "themes_export_headless"), "assets")
        return 0

    sys.exit(_headless_test())

# ---------------------------------------------------------------------------
# Ruta para coger los iconos y otros al empaquetarlo
# ---------------------------------------------------------------------------
def resource_path(relative_path):
    """Devuelve la ruta correcta tanto en desarrollo como en PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


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
            return  # ya insertado en el drop/add
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

    def redo(self):
        self.canvas.move_element(self.elem, self.new_pos, self.old_pos, push_undo=False)
        if self.refresh_fn:
            self.refresh_fn()

    def undo(self):
        self.canvas.move_element(self.elem, self.old_pos, self.new_pos, push_undo=False)
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
# Redimensionar elementos en el Canvas
# ---------------------------------------------------------------------------
class ResizeHandle(QGraphicsRectItem):
    def __init__(self, parent_elem, position, cursor_shape, canvas, size=10):
        super().__init__(-size//2, -size//2, size, size, parent_elem)
        self.parent_elem = parent_elem
        self.position = position
        self.canvas = canvas
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#1565C0"), 2))
        self.setCursor(cursor_shape)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self._start_size = None
        self._start_pos_norm = None

    def mousePressEvent(self, event):
        # Guardar rectángulo inicial en escena
        self._start_scene_rect = self.parent_elem.sceneBoundingRect()
        elem = self.parent_elem.elem

        # Determinar qué propiedad se va a modificar (prioridad size > minSize > maxSize)
        # Leer valores base (sin condiciones)
        if "size" in elem.properties:
            self._active_prop = "size"
            self._start_value = elem.get_base_value("size")
        elif "minSize" in elem.properties:
            self._active_prop = "minSize"
            self._start_value = elem.get_base_value("minSize")
        elif "maxSize" in elem.properties:
            self._active_prop = "maxSize"
            self._start_value = elem.get_base_value("maxSize")
        else:
            self._active_prop = "size"
            self._start_value = None

        self._start_pos_norm = elem.get_base_value("pos") or "0 0"
        self._start_min_size = elem.get_base_value("minSize") or ""
        self._start_max_size = elem.get_base_value("maxSize") or ""

        # Guardar tamaño normalizado actual (para limitar si se modifica size)
        canvas = self.parent_elem.get_canvas()
        if canvas:
            w = canvas.scene().width()
            h = canvas.scene().height()
            rect = self.parent_elem.rect()
            self._start_size_norm = (rect.width() / w, rect.height() / h)
        else:
            self._start_size_norm = None

        self.grabMouse()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        mouse_pos = event.scenePos()

        x1 = self._start_scene_rect.x()
        y1 = self._start_scene_rect.y()
        x2 = x1 + self._start_scene_rect.width()
        y2 = y1 + self._start_scene_rect.height()

        if 'l' in self.position:
            x1 = mouse_pos.x()
        if 'r' in self.position:
            x2 = mouse_pos.x()
        if 't' in self.position:
            y1 = mouse_pos.y()
        if 'b' in self.position:
            y2 = mouse_pos.y()

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        new_rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        if new_rect.width() < 10:
            new_rect.setWidth(10)
        if new_rect.height() < 10:
            new_rect.setHeight(10)

        canvas = self.parent_elem.scene().views()[0]
        w = canvas.scene().width()
        h = canvas.scene().height()

        # Si la propiedad activa es 'size', aplicar límites minSize y maxSize (si existen)
        if self._active_prop == "size":
            min_w = min_h = max_w = max_h = 0
            if self._start_min_size:
                mn_w, mn_h = _parse_pos(self._start_min_size)
                min_w = mn_w * w
                min_h = mn_h * h
            if self._start_max_size:
                mx_w, mx_h = _parse_pos(self._start_max_size)
                max_w = mx_w * w
                max_h = mx_h * h
            if min_w > 0 and new_rect.width() < min_w:
                new_rect.setWidth(min_w)
            if min_h > 0 and new_rect.height() < min_h:
                new_rect.setHeight(min_h)
            if max_w > 0 and new_rect.width() > max_w:
                new_rect.setWidth(max_w)
            if max_h > 0 and new_rect.height() > max_h:
                new_rect.setHeight(max_h)

        new_size = (new_rect.width() / w, new_rect.height() / h)
        new_size_str = f"{new_size[0]:.4f} {new_size[1]:.4f}"
        new_pos = self._start_pos_norm

        # Actualizar la propiedad activa
        if self._active_prop == "size":
            self.parent_elem.elem.set_base_value("size", new_size_str)
        elif self._active_prop == "minSize":
            self.parent_elem.elem.set_base_value("minSize", new_size_str)
        elif self._active_prop == "maxSize":
            self.parent_elem.elem.set_base_value("maxSize", new_size_str)
        self.parent_elem.elem.set_base_value("pos", new_pos)

        self.parent_elem.update_geometry()
        self.parent_elem.update_handles()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.ungrabMouse()
        new_value = self.parent_elem.elem.get_base_value(self._active_prop)
        new_pos = self.parent_elem.elem.get_base_value("pos") or "0 0"
        if new_value != self._start_value or new_pos != self._start_pos_norm:
            cmd = ResizeElemCmd(
                self.parent_elem.elem,
                self._active_prop,
                self._start_value,
                self._start_pos_norm,
                new_value,
                new_pos,
                self.canvas
            )
            self.canvas._undo_stack.push(cmd)
        super().mouseReleaseEvent(event)


class ResizeElemCmd(QUndoCommand):
    def __init__(self, elem, prop_name, old_value, old_pos, new_value, new_pos, canvas):
        super().__init__(f"Redimensionar '{elem.name}' ({prop_name})")
        self.elem = elem
        self.prop_name = prop_name
        self.old_value = old_value
        self.old_pos = old_pos
        self.new_value = new_value
        self.new_pos = new_pos
        self.canvas = canvas

    def redo(self):
        self._apply(self.new_value, self.new_pos)

    def undo(self):
        self._apply(self.old_value, self.old_pos)

    def _apply(self, value, pos):
        if value is None:
            # Eliminar la propiedad (opcional, cuidado con borrar condiciones)
            # Para simplificar, no borramos, solo establecemos cadena vacía
            self.elem.set_base_value(self.prop_name, "")
        else:
            self.elem.set_base_value(self.prop_name, value)
        self.elem.set_base_value("pos", pos)

        # Actualizar la representación visual
        for item in self.canvas._elem_items.values():
            if item.elem is self.elem:
                item.update_geometry()
                break
        self.canvas.element_selected.emit(self.elem)


# ---------------------------------------------------------------------------
# XML Editor Tab
# ---------------------------------------------------------------------------
class XMLEditorTab(QWidget):
    model_changed = Signal()
    file_loaded = Signal() # Archivo cargado

    def __init__(self, theme_model: ThemeModel):
        super().__init__()
        self.theme_model = theme_model
        self.current_root = ""
        self.current_file_path = None  # Ruta del archivo XML cargado actualmente
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Splitter principal con dos paneles (izquierdo: explorador, derecho: editor)
        splitter = QSplitter(Qt.Horizontal)

        # --- Panel izquierdo: explorador de archivos ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)

        # Barra de botones superior
        button_bar = QHBoxLayout()
        self.btn_create_folder = QPushButton("Crear carpeta")  # Guardar referencia
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = resource_path("iconos/new_folder.ico")
        if os.path.isfile(icon_path):
            self.btn_create_folder.setIcon(QIcon(icon_path))
            self.btn_create_folder.setIconSize(QSize(16, 16))
        self.btn_create_folder.setEnabled(False)  # Inicialmente deshabilitado
        self.btn_create_folder.clicked.connect(self._create_folder)
        button_bar.addWidget(self.btn_create_folder)
        button_bar.addStretch()  # Para separar del borde derecho
        left_layout.addLayout(button_bar)

        self.tree_view = QTreeView()
        self.tree_view.setIconSize(QSize(32, 32))  # Tamaño del icono (ancho, alto)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(10)
        self.tree_view.doubleClicked.connect(self.on_tree_double_click)
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath("")
        self.file_model.setFilter(QDir.Dirs | QDir.Files | QDir.NoDotAndDotDot)
        self.tree_view.setModel(self.file_model)
        # Ocultar columnas extra (tamaño, tipo, fecha)
        for col in range(1, self.file_model.columnCount()):
            self.tree_view.setColumnHidden(col, True)
        left_layout.addWidget(self.tree_view)

        splitter.addWidget(left_widget)

        # --- Panel central: editor de texto ---
        editor_widget = QWidget()
        ev = QVBoxLayout(editor_widget)
        ev.setContentsMargins(0, 0, 0, 0)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Monospace", 10))
        self.editor.setStyleSheet("background:#1e1e1e; color:#d4d4d4;")
        self.editor.setPlaceholderText("Selecciona un archivo XML del árbol izquierdo... (doble click)")
        XMLHighlighter(self.editor.document())
        ev.addWidget(self.editor)

        # Layout horizontal para mensaje de estado y botón aplicar
        bottom_bar = QHBoxLayout()
        self.status_lbl = QLabel("")
        bottom_bar.addWidget(self.status_lbl, 1)  # Se expande para ocupar espacio sobrante
        btn_apply = QPushButton("Validar XML y aplicar la vista")
        btn_apply.setStyleSheet("background:#2E7D32; color:white; font-weight:bold; padding:4px 12px;")
        btn_apply.clicked.connect(self._apply_to_model)
        bottom_bar.addWidget(btn_apply)  # Botón pegado a la derecha
        ev.addLayout(bottom_bar)

        splitter.addWidget(editor_widget)

        # Configurar anchos relativos
        splitter.setStretchFactor(0, 1)  # explorador
        splitter.setStretchFactor(1, 3)  # editor

        layout.addWidget(splitter)

    # -----------------------------------------------------------------------
    # Seleccionar la carpeta del theme a importar
    # -----------------------------------------------------------------------
    def select_theme_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta raíz del tema", QDir.rootPath())

        if folder:
            self.current_root = folder
            self.file_model.setRootPath(folder)
            self.tree_view.setRootIndex(self.file_model.index(folder))

            main_window = self.window()
            if hasattr(main_window, '_builder_tab'):
                # Actualizar assets en builder y preview
                main_window._assets_root = folder
                main_window._builder_tab.assets_root = folder
                main_window._builder_tab._canvas.assets_root = folder
                main_window._builder_tab.theme_assets_browser.set_root(folder)
                main_window._builder_tab._assets_path_lbl.setText(folder)
                main_window._builder_tab.assets_root_changed.emit(folder)
                main_window._preview_tab.set_assets_root(folder)

            # Cargar theme.xml como modelo principal si existe
            theme_xml_path = os.path.join(folder, 'theme.xml')
            if os.path.isfile(theme_xml_path):
                with open(theme_xml_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    new_model = ThemeModel.from_xml(content)
                    if new_model is None:
                        # Intentamos usar el nombre de la carpeta para el modelo actual
                        main_window.theme_model.name = os.path.basename(folder)
                        main_window._name_edit.setText(main_window.theme_model.name)
                    else:
                        # Forzar el nombre del tema al nombre de la carpeta seleccionada
                        new_model.name = os.path.basename(folder)
                        # Actualizar modelo global y todas las pestañas
                        main_window.theme_model = new_model
                        main_window._xml_tab.theme_model = new_model
                        main_window._xml_tab.refresh_from_model()
                        main_window._builder_tab.load_model(new_model)
                        main_window._preview_tab.theme_model = new_model
                        main_window._preview_tab.refresh()

                        # Actualizar barra de herramientas
                        main_window._name_edit.setText(new_model.name)
            else:
                # No existe theme.xml, pero aún así podemos usar el nombre de la carpeta
                main_window.theme_model.name = os.path.basename(folder)
                main_window._name_edit.setText(main_window.theme_model.name)

            self._update_create_folder_button_state() # Habilitar botón de crear carpeta
            main_window._update_actions_state()  # Habilitar guardado y nuevo xml
            main_window._update_undo_redo_state() # Conectar estado botones "Deshacer" y "Rehacer"

            # Resetear banderas de la opción "Guardar" y limpiar pila de cambios
            main_window._changes_unsaved = False
            main_window._update_save_action_state()
            main_window._builder_tab._undo_stack.clear()
            main_window._builder_tab._undo_stack.setClean()
            main_window._editing_system_from_set = None
            main_window._theme_set_modified = False
            main_window._saved_model_xml = main_window.theme_model.to_xml()

            self._show_status(f"Theme cargado: {folder}")
            self.file_loaded.emit()  # Emitir señal de archivo cargado

    def on_tree_double_click(self, index):
        file_path = self.file_model.filePath(index)
        if os.path.isfile(file_path) and file_path.endswith('.xml'):
            with open(file_path, 'r', encoding='utf-8') as f:
                self.editor.setPlainText(f.read())
                self.current_file_path = file_path
            self._show_status(f"Archivo cargado: {file_path}")
            if self._apply_to_model():  # si la aplicación fue exitosa
                self.file_loaded.emit()  # notificar que se ha cargado un nuevo archivo

    def refresh_from_model(self):
        if self.theme_model is None:
            self.editor.setPlainText("")
            self.status_lbl.setText("No hay ningún theme cargado. Importa o crea uno.")
            return
        self.editor.setPlainText(self.theme_model.to_xml())

    def _new_xml(self):
        # 1. Asegurar que hay una carpeta raíz seleccionada
        if not self.current_root or not os.path.isdir(self.current_root):
            # Si no hay carpeta, pedirla primero
            self.select_theme_folder()
            if not self.current_root:
                return  # Cancelado por el usuario

        # 2. Diálogo de guardado que permite elegir subcarpeta y nombre
        default_name = "nuevo.xml"
        start_dir = self.current_root
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Crear nuevo archivo XML",
            os.path.join(start_dir, default_name),
            "XML files (*.xml);;All files (*)"
        )
        if not file_path:
            return  # Cancelado

        # Asegurar extensión .xml
        if not file_path.lower().endswith(".xml"):
            file_path += ".xml"

        # 3. Evitar sobrescribir accidentalmente
        if os.path.exists(file_path):
            reply = QMessageBox.question(
                self, "Sobrescribir",
                f"El archivo '{file_path}' ya existe. ¿Sobrescribir?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 4. Contenido XML por defecto (igual que antes, pero se puede personalizar)
        default_xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                       '\n\n<theme>'
                       '\n\t<formatVersion>7</formatVersion>'
                       '\n</theme>')

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(default_xml)
            # 5. Cargar el archivo recién creado en el editor
            with open(file_path, "r", encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
            self._show_status(f"Archivo creado: {file_path}")
            self.current_file_path = file_path # Guardar ruta del nuevo XML

            # 6. Refrescar el árbol de archivos y seleccionar el nuevo archivo
            # Forzar actualización del modelo
            self.file_model.setRootPath(self.current_root)
            self.tree_view.setRootIndex(self.file_model.index(self.current_root))
            # Buscar el índice del nuevo archivo y seleccionarlo
            idx = self.file_model.index(file_path)
            if idx.isValid():
                self.tree_view.setCurrentIndex(idx)
                self.tree_view.scrollTo(idx)

            # 7. Aplicarlo al modelo automáticamente
            if self._apply_to_model():
                self.file_loaded.emit()  # Emitir señal de archivo cargado

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear el archivo:\n{str(e)}")

    def _save_file(self):
        """Guardar como... (solicita nueva ruta)"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar XML",
            self.current_file_path or os.path.join(os.getcwd(), "theme.xml"),
            "XML files (*.xml)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.editor.toPlainText())
                self.current_file_path = path  # <-- actualizar ruta actual
                self._show_status(f"Guardado: {path}")
            except Exception as e:
                self._show_status(f"Error: {e}")

    def save_current_file(self):
        """Guarda el contenido en el archivo actual (si existe), si no, llama a guardar como."""
        if self.current_file_path and os.path.exists(os.path.dirname(self.current_file_path)):
            try:
                with open(self.current_file_path, "w", encoding="utf-8") as f:
                    f.write(self.editor.toPlainText())
                self._show_status(f"Guardado: {self.current_file_path}")
            except Exception as e:
                self._show_status(f"Error al guardar: {e}")
        else:
            self._save_file()  # Si no hay ruta, hacer "Guardar como"

    def _apply_to_model(self) -> bool:
        xml = self.editor.toPlainText().strip()
        if not xml:
            self.status_lbl.setText("El editor está vacío.")
            self.status_lbl.setStyleSheet("color:#f88; padding:4px;")
            QMessageBox.warning(self, "Editor vacío", "No hay contenido XML para validar.")
            return False

        new_model = ThemeModel.from_xml(xml)
        if not new_model:
            return False

        if new_model is None:
            self.status_lbl.setText("XML inválido (error de sintaxis).")
            self.status_lbl.setStyleSheet("color:#f88; padding:4px;")
            QMessageBox.critical(self, "Error de sintaxis",
                                 "El XML no es válido.\nVerifica caracteres como &, <, >, o etiquetas mal cerradas.")
            return False

        # 1. Validación estructural del XML (texto suelto, etiquetas permitidas)
        xml_errors = validate_theme_xml(new_model)
        if xml_errors:
            self.status_lbl.setText("Estructura XML incorrecta.")
            self.status_lbl.setStyleSheet("color:#f88; padding:4px;")
            QMessageBox.warning(self, "Errores estructurales", "\n".join(xml_errors))
            return False

        # --- ACTUALIZAR MODELO EXISTENTE SIN ROMPER REFERENCIAS ---
        # Copiar atributos simples
        self.theme_model.includes = new_model.includes
        self.theme_model.format_version = new_model.format_version
        self.theme_model.variables = new_model.variables.copy()
        self.theme_model.subsets = new_model.subsets.copy()
        self.theme_model.root_attrib = new_model.root_attrib.copy()
        self.theme_model.xml_declaration = new_model.xml_declaration
        self.theme_model.raw_xml = new_model.raw_xml

        # Actualizar las vistas: reutilizar objetos existentes por nombre
        old_views_by_name = {v.name: v for v in self.theme_model.views}
        new_views_by_name = {v.name: v for v in new_model.views}

        # 1. Eliminar vistas que ya no existen en el nuevo modelo
        for name in list(old_views_by_name.keys()):
            if name not in new_views_by_name:
                self.theme_model.views.remove(old_views_by_name[name])

        # 2. Actualizar vistas existentes o añadir nuevas
        for name, new_view in new_views_by_name.items():
            if name in old_views_by_name:
                # Actualizar la vista existente (misma referencia)
                old_view = old_views_by_name[name]
                old_view.inherits = new_view.inherits
                old_view.is_custom = new_view.is_custom
                old_view.elements = new_view.elements  # Reemplaza la lista
            else:
                # Añadir vista nueva
                self.theme_model.views.append(new_view)

        self.status_lbl.setText("XML VALIDADO. Vista actualizada correctamente.")
        self.status_lbl.setStyleSheet("color:#8f8; padding:4px;")
        self.model_changed.emit()

        main_window = self.window()
        if hasattr(main_window, '_builder_tab'):
            main_window._builder_tab._undo_stack.clear()
            main_window._builder_tab._undo_stack.setClean()

        # Ventana informativa de éxito
        QMessageBox.information(self, "Validación exitosa", "El XML es correcto y se ha aplicado la vista.")

        # Actualizar barra de herramientas
        main_window = self.window()
        if hasattr(main_window, '_name_edit'):
            main_window._name_edit.setText(self.theme_model.name)

        return True

    def _create_folder(self):
        """Crea una nueva carpeta en el directorio actualmente seleccionado del árbol."""
        # Obtener el directorio base donde crear la carpeta
        idx = self.tree_view.currentIndex()
        if idx.isValid():
            base_path = self.file_model.filePath(idx)
            if os.path.isfile(base_path):
                base_path = os.path.dirname(base_path)
        else:
            base_path = self.current_root

        if not base_path or not os.path.isdir(base_path):
            QMessageBox.warning(self, "Sin carpeta base",
                                "No hay una carpeta seleccionada o raíz válida. Usa 'Seleccionar carpeta raíz' primero.")
            return

        # Pedir nombre de la nueva carpeta
        name, ok = QInputDialog.getText(self, "Nueva carpeta",
                                        "Nombre de la carpeta:", text="nueva_carpeta")
        if not ok or not name.strip():
            return

        folder_name = name.strip()
        folder_path = os.path.join(base_path, folder_name)

        if os.path.exists(folder_path):
            QMessageBox.warning(self, "Ya existe", f"La carpeta '{folder_name}' ya existe.")
            return

        try:
            os.makedirs(folder_path)
            # Refrescar el árbol: forzar actualización del modelo
            # Cambiar la raíz del modelo a la misma para refrescar
            self.file_model.setRootPath(self.current_root)
            self.tree_view.setRootIndex(self.file_model.index(self.current_root))
            # Seleccionar la nueva carpeta
            new_idx = self.file_model.index(folder_path)
            if new_idx.isValid():
                self.tree_view.setCurrentIndex(new_idx)
                self.tree_view.expand(new_idx)
            self._show_status(f"Carpeta creada: {folder_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta:\n{str(e)}")

    def _update_create_folder_button_state(self):
        """Habilita o deshabilita el botón de crear carpeta según si hay carpeta raíz válida."""
        enabled = bool(self.current_root and os.path.isdir(self.current_root))
        self.btn_create_folder.setEnabled(enabled)

    # ---------------------------------------------------------------
    # Mostrar mensajes en la status bar
    # ---------------------------------------------------------------
    def _show_status(self, msg: str, timeout: int = 3000):
        """Muestra un mensaje en la barra de estado de la ventana principal."""
        main_window = self.window()
        if main_window and hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage(msg, timeout)


# ---------------------------------------------------------------------------
# Canvas (por defecto 1280×720 coordenadas EmulationStation normalizadas 0-1)
# ---------------------------------------------------------------------------
CANVAS_W, CANVAS_H = 1280, 720

ELEM_COLORS = {
    "image": QColor("#1565C0"),
    "video": QColor("#6A749A"),
    "text": QColor("#2E7D32"),
    "rating": QColor("#E65100"),
    "datetime": QColor("#00838F"),
    "helpsystem": QColor("#AD1457"),
    "textlist": QColor("#4E8100"),
    "gamecarousel": QColor("#4E8100"),
}


def _parse_pos(val: str):
    parts = val.strip().split()
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return 0, 0


class CanvasElem(QGraphicsRectItem):
    def __init__(self, elem: ThemeElement, assets_root: str, undo_stack=None, system_name: str = "",
                 variables: dict = None):
        # Obtener valores base (sin condiciones)
        pos_base = elem.get_base_value("pos") or "0 0"
        size_base = elem.get_base_value("size") or "0.5 0.5"
        origin_base = elem.get_base_value("origin") or "0 0"

        # Resolver variables en esos valores base
        resolver = ThemeVariableResolver(variables or {}, system_name)
        pos_str = resolver.resolve(pos_base)
        size_str = resolver.resolve(size_base)
        origin_str = resolver.resolve(origin_base)

        # Calcular rectángulo inicial (píxeles)
        self.assets_root = assets_root
        self.elem = elem
        self._undo_stack = undo_stack
        self._drag_start_pos_norm = None
        self._drag_start_pos_px = None

        w, h = CANVAS_W, CANVAS_H
        px, py = _parse_pos(pos_str)
        sx, sy = _parse_pos(size_str)
        ox, oy = _parse_pos(origin_str)
        w_px = max(sx * w, 10)
        h_px = max(sy * h, 10)
        x_px = px * w - ox * w_px
        y_px = py * h - oy * h_px

        super().__init__(0, 0, w_px, h_px)
        self.setPen(QPen(Qt.red, 2))
        self.setPos(x_px, y_px)

        # Color según tipo (con transparencia)
        color = ELEM_COLORS.get(elem.element_type, QColor("#607D8B"))
        self.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 80)))
        self.setPen(QPen(color, 2))
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.canvas_vars = variables or {}
        self.canvas_system = system_name
        self.pix_item = None

        # Asignar zIndex: si no existe, se le da un valor enorme para que vaya encima
        z_str = self._get_resolved_property("zIndex")
        try:
            z = float(z_str)
        except (ValueError, TypeError):
            z = 1e9
        self.setZValue(z)

        # Etiqueta de texto (tipo + nombre)
        self.label = QGraphicsTextItem(self)
        self.label.setPlainText(f"[{elem.element_type}]\n{elem.name}")
        self.label.setDefaultTextColor(QColor("#ffffff"))
        self.label.setFont(QFont("Sans", 9, QFont.Bold))
        self.label.setPos(4, 4)

        self._handles = []

    def _get_resolved_origin(self) -> str:
        """Devuelve el origin resuelto, con fallback específico para image/video."""
        if self.elem.element_type == "image":
            if self.elem.name == "logo":
                return self._get_resolved_property("origin", "0.5 0")
            elif self.elem.name == "md_image":
                return self._get_resolved_property("origin", "0.5 0.5")
            else:
                return self._get_resolved_property("origin", "0 0")
        elif self.elem.element_type == "video":
            return self._get_resolved_property("origin", "0.5 0.5")
        else:
            return self._get_resolved_property("origin", "0 0")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Guardar el valor base de 'pos' (sin condiciones) como string
            self._drag_start_pos_norm = self.elem.get_base_value("pos")
            if not self._drag_start_pos_norm:
                self._drag_start_pos_norm = "0 0"
            self._drag_start_pos_px = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.scenePos() - event.lastScenePos()
            new_pos = self.pos() + delta
            self.setPos(new_pos)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._drag_start_pos_px is None:
            return
        new_pos_px = self.pos()
        if new_pos_px == self._drag_start_pos_px:
            self._drag_start_pos_norm = None
            self._drag_start_pos_px = None
            return

        canvas = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if canvas is None:
            return

        w, h = canvas.scene().width(), canvas.scene().height()
        # Obtener tamaño actual del elemento
        rect = self.rect()
        w_px = rect.width()
        h_px = rect.height()
        origin_str = self._get_resolved_origin()
        ox, oy = _parse_pos(origin_str)

        new_norm_x = (new_pos_px.x() + ox * w_px) / w
        new_norm_y = (new_pos_px.y() + oy * h_px) / h
        new_norm_pos = f"{new_norm_x:.4f} {new_norm_y:.4f}"

        if new_norm_pos == self._drag_start_pos_norm:
            self._drag_start_pos_norm = None
            self._drag_start_pos_px = None
            return

        if hasattr(canvas, 'move_element'):
            canvas.move_element(self.elem, new_norm_pos, self._drag_start_pos_norm)

        self._drag_start_pos_norm = None
        self._drag_start_pos_px = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedChange:
            if value:
                self.create_handles()
            else:
                self.remove_handles()
        return super().itemChange(change, value)

    def create_handles(self):
        self.remove_handles()
        canvas = self.get_canvas()
        if not canvas:
            return
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        if w <= 0 or h <= 0:
            return
        positions = {
            'tl': (rect.left(), rect.top(), Qt.SizeFDiagCursor),
            'tm': (rect.center().x(), rect.top(), Qt.SizeVerCursor),
            'tr': (rect.right(), rect.top(), Qt.SizeBDiagCursor),
            'ml': (rect.left(), rect.center().y(), Qt.SizeHorCursor),
            'mr': (rect.right(), rect.center().y(), Qt.SizeHorCursor),
            'bl': (rect.left(), rect.bottom(), Qt.SizeBDiagCursor),
            'bm': (rect.center().x(), rect.bottom(), Qt.SizeVerCursor),
            'br': (rect.right(), rect.bottom(), Qt.SizeFDiagCursor)
        }
        for key, (x, y, cursor) in positions.items():
            handle = ResizeHandle(self, key, cursor, canvas)
            handle.setPos(x, y)
            self._handles.append(handle)
            self.scene().addItem(handle)

    def remove_handles(self):
        for h in self._handles:
            self.scene().removeItem(h)
        self._handles.clear()

    def update_handles(self):
        """Actualizar posiciones de los handles después de un resize/move"""
        if not self._handles:
            return
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        if w <= 0 or h <= 0:
            return
        pos_map = {
            'tl': (rect.left(), rect.top()),
            'tm': (rect.center().x(), rect.top()),
            'tr': (rect.right(), rect.top()),
            'ml': (rect.left(), rect.center().y()),
            'mr': (rect.right(), rect.center().y()),
            'bl': (rect.left(), rect.bottom()),
            'bm': (rect.center().x(), rect.bottom()),
            'br': (rect.right(), rect.bottom())
        }
        for handle in self._handles:
            x, y = pos_map[handle.position]
            handle.setPos(x, y)

    def _get_resolved_property(self, prop_name: str, default: str = "") -> str:
        context = {"system.theme": self.canvas_system}
        raw_value = self.elem.get_resolved_value(prop_name, context)
        if not raw_value:
            return default
        # Ahora resuelve variables ${...} dentro del valor
        resolver = ThemeVariableResolver(self.canvas_vars, self.canvas_system)
        return resolver.resolve(raw_value)

    def update_geometry(self):
        if not self.scene():
            return
        w_scene, h_scene = self.scene().width(), self.scene().height()

        # Propiedades básicas
        pos_str = self._get_resolved_property("pos", "0 0")
        size_str = self._get_resolved_property("size", "")
        min_size_str = self._get_resolved_property("minSize", "")
        max_size_str = self._get_resolved_property("maxSize", "")

        origin_str = self._get_resolved_origin()
        px, py = _parse_pos(pos_str)
        ox, oy = _parse_pos(origin_str)

        # Actualizar zIndex por si cambió
        z_str = self._get_resolved_property("zIndex")
        try:
            z = float(z_str)
        except (ValueError, TypeError):
            z = 1e9
        self.setZValue(z)

        # --- Convertir minSize y maxSize a píxeles ---
        min_w = min_h = max_w = max_h = 0
        if min_size_str:
            min_w_n, min_h_n = _parse_pos(min_size_str)
            min_w = min_w_n * w_scene
            min_h = min_h_n * h_scene
        if max_size_str:
            max_w_n, max_h_n = _parse_pos(max_size_str)
            max_w = max_w_n * w_scene
            max_h = max_h_n * h_scene

        # --- Determinar tamaño objetivo inicial ---
        if size_str:
            sx, sy = _parse_pos(size_str)
            target_w = max(sx * w_scene, 1)
            target_h = max(sy * h_scene, 1)
        else:
            target_w = None  # sin size → usaremos el tamaño natural del asset
            target_h = None

        # --- Para elementos de imagen/vídeo ---
        if self.elem.element_type in ("image", "video"):
            # Obtener lista de rutas .svg o .png
            paths = self._get_resolved_paths()
            pix = None
            for rel_path in paths:
                pix = self._load_asset_pixmap(rel_path, None, None)
                if pix is not None:
                    break

            # Si ninguna ruta funcionó, probar con "default"
            if pix is None:
                default_val = self._get_resolved_property("default", "")
                if default_val:
                    pix = self._load_asset_pixmap(default_val, None, None)

            if pix is not None:
                img_w, img_h = pix.width(), pix.height()

                if size_str:
                    # CASO CON size: elemento con tamaño fijo
                    target_w = max(sx * w_scene, 1)
                    target_h = max(sy * h_scene, 1)
                    final_rect_w, final_rect_h = target_w, target_h

                    # Calcular tamaño de la imagen (puede ser estirada o limitada por maxSize)
                    if max_w > 0 and max_h > 0:
                        # maxSize actúa como límite superior (contain)
                        scale_w = max_w / img_w
                        scale_h = max_h / img_h
                        scale = min(scale_w, scale_h)
                        new_w = img_w * scale
                        new_h = img_h * scale
                    else:
                        # Sin maxSize: la imagen se estira al tamaño del contenedor
                        new_w, new_h = target_w, target_h

                    # Aplicar minSize (cover) - si la imagen resultante es más pequeña que minSize, se escala hacia arriba
                    if min_w > 0 and min_h > 0:
                        # Calculamos la escala necesaria para cumplir minSize
                        scale_w = min_w / new_w
                        scale_h = min_h / new_h
                        scale = max(scale_w, scale_h)
                        new_w = new_w * scale
                        new_h = new_h * scale
                        # Asegurar que no excede el contenedor si no hay maxSize
                        if max_w == 0 or max_h == 0:
                            new_w = min(new_w, target_w)
                            new_h = min(new_h, target_h)

                    # Calcular offset para centrar la imagen dentro del contenedor
                    off_x = (target_w - new_w) / 2
                    off_y = (target_h - new_h) / 2
                else:
                    # CASO SIN size: el elemento toma el tamaño del asset limitado por min/max
                    if pix is not None:
                        img_w, img_h = pix.width(), pix.height()
                        # Aplicar maxSize (contain) y minSize (cover) manteniendo aspecto
                        new_w, new_h = img_w, img_h

                        # maxSize → escalar hacia abajo si es necesario
                        if max_w > 0 and max_h > 0:
                            scale_w = max_w / img_w
                            scale_h = max_h / img_h
                            scale = min(scale_w, scale_h)
                            new_w = img_w * scale
                            new_h = img_h * scale

                        # minSize → escalar hacia arriba si es necesario
                        if min_w > 0 and min_h > 0:
                            scale_w = min_w / new_w
                            scale_h = min_h / new_h
                            scale = max(scale_w, scale_h)
                            new_w = new_w * scale
                            new_h = new_h * scale

                        final_rect_w, final_rect_h = new_w, new_h
                        off_x, off_y = 0, 0

                        # Escalar la imagen al tamaño final (manteniendo aspecto)
                        scaled_pix = pix.scaled(int(new_w), int(new_h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        if hasattr(self, 'pix_item') and self.pix_item:
                            self.pix_item.setPixmap(scaled_pix)
                            self.pix_item.setPos(off_x, off_y)
                        else:
                            self.pix_item = QGraphicsPixmapItem(scaled_pix, self)
                            self.pix_item.setPos(off_x, off_y)
                    else:
                        # No se pudo cargar la imagen: rectángulo gris de 100x100
                        final_rect_w, final_rect_h = 100, 100
                        if hasattr(self, 'pix_item') and self.pix_item:
                            self.scene().removeItem(self.pix_item)
                            self.pix_item = None

                # Determinar modo de escalado
                if size_str and (max_w == 0 or max_h == 0):
                    # Con size y sin maxSize: estirar
                    scale_mode = Qt.IgnoreAspectRatio
                elif size_str and (max_w > 0 or max_h > 0):
                    # Con size y maxSize: contener (keep aspect)
                    scale_mode = Qt.KeepAspectRatio
                else:
                    # Sin size: la imagen ya está escalada a new_w/new_h manteniendo aspecto (cover o contain)
                    # Por tanto, podemos usar IgnoreAspectRatio porque no habrá distorsión
                    scale_mode = Qt.IgnoreAspectRatio

                scaled_pix = pix.scaled(int(new_w), int(new_h), scale_mode, Qt.SmoothTransformation)
                if hasattr(self, 'pix_item') and self.pix_item:
                    self.pix_item.setPixmap(scaled_pix)
                    self.pix_item.setPos(off_x, off_y)
                else:
                    self.pix_item = QGraphicsPixmapItem(scaled_pix, self)
                    self.pix_item.setPos(off_x, off_y)
            else:
                if self.elem.element_type == "video" and self.elem.name == "md_video":
                    # Tamaño natural por defecto para vídeos scrapeados de los juegos (md_video), asumimos 640x480
                    natural_w, natural_h = 640, 480
                    # Si existe 'size', se usa como factor de escala sobre el tamaño natural
                    if size_str:
                        # Modo size: el elemento ocupará exactamente size (en píxeles)
                        # El vídeo se estirará a esas dimensiones (se ignorará el aspecto)
                        sx, sy = _parse_pos(size_str)
                        natural_w = sx * w_scene
                        natural_h = sy * h_scene
                    else:
                        # Aplicar minSize/maxSize sobre este tamaño natural (modo contain/cover)
                        if max_w > 0 and max_h > 0:
                            scale = min(max_w / natural_w, max_h / natural_h)
                            natural_w *= scale
                            natural_h *= scale
                        if min_w > 0 and min_h > 0:
                            scale = max(min_w / natural_w, min_h / natural_h)
                            natural_w *= scale
                            natural_h *= scale
                    final_rect_w, final_rect_h = natural_w, natural_h
                elif self.elem.element_type == "image" and self.elem.name == "md_image":
                    # Tamaño natural por defecto para capturas scrapeadas de los juegos (md_image)
                    # Si el vídeo tiene un path, se podría intentar obtener metadatos, pero por ahora asumimos 320x240
                    natural_w, natural_h = 320, 240
                    # Aplicar minSize/maxSize sobre este tamaño natural (modo contain/cover)
                    if max_w > 0 and max_h > 0:
                        scale = min(max_w / natural_w, max_h / natural_h)
                        natural_w *= scale
                        natural_h *= scale
                    if min_w > 0 and min_h > 0:
                        scale = max(min_w / natural_w, min_h / natural_h)
                        natural_w *= scale
                        natural_h *= scale
                    final_rect_w, final_rect_h = natural_w, natural_h
                else:
                    # No se pudo cargar la imagen: rectángulo gris
                    if size_str:
                        final_rect_w, final_rect_h = target_w, target_h
                    else:
                        final_rect_w, final_rect_h = 100, 100
                    if hasattr(self, 'pix_item') and self.pix_item:
                        self.scene().removeItem(self.pix_item)
                        self.pix_item = None
        else:
            # Elementos no visuales (texto, rating, etc.)
            if target_w is None:
                target_w = 100
                target_h = 100
            final_rect_w = target_w
            final_rect_h = target_h
            if hasattr(self, 'pix_item') and self.pix_item:
                self.scene().removeItem(self.pix_item)
                self.pix_item = None

        # --- Posición final del elemento ---
        x_px = px * w_scene - ox * final_rect_w
        y_px = py * h_scene - oy * final_rect_h

        self.setRect(0, 0, final_rect_w, final_rect_h)
        self.setPos(x_px, y_px)

        # Actualizar etiqueta y handles
        self.label.setPlainText(f"[{self.elem.element_type}]\n{self.elem.name}")
        self.update_handles()

    def get_canvas(self):
        views = self.scene().views() if self.scene() else []
        return views[0] if views else None

    def _apply_min_max(self, img_w, img_h, target_w, target_h, min_w, min_h, max_w, max_h):
        """Calcula el tamaño final y el offset para la imagen según minSize y maxSize.
        Retorna: (new_w, new_h, offset_x, offset_y)"""
        # Evitar división por cero
        if img_w <= 0 or img_h <= 0:
            return target_w, target_h, 0, 0

        # Escala inicial para que quepa dentro de target_w x target_h (modo contain)
        scale_w = target_w / img_w if img_w > 0 else 1
        scale_h = target_h / img_h if img_h > 0 else 1
        scale = min(scale_w, scale_h)
        new_w = img_w * scale
        new_h = img_h * scale

        # Aplicar maxSize (contain) - si se especifica, limita el área máxima
        if max_w > 0 and max_h > 0:
            scale_max_w = max_w / img_w
            scale_max_h = max_h / img_h
            scale_max = min(scale_max_w, scale_max_h)
            new_w = min(new_w, img_w * scale_max)
            new_h = min(new_h, img_h * scale_max)

        # Aplicar minSize (cover) - fuerza a cubrir al menos el área mínima
        if min_w > 0 and min_h > 0:
            scale_min_w = min_w / img_w
            scale_min_h = min_h / img_h
            scale_min = max(scale_min_w, scale_min_h)
            new_w = max(new_w, img_w * scale_min)
            new_h = max(new_h, img_h * scale_min)

        # Calcular offset para centrar dentro del rectángulo final (según origin)
        off_x = (target_w - new_w) / 2
        off_y = (target_h - new_h) / 2
        return new_w, new_h, off_x, off_y

    def _get_resolved_paths(self) -> List[str]:
        """Devuelve la lista de rutas de imagen/video resueltas (con variables) en orden."""
        context = {"system.theme": self.canvas_system}
        # Añadir también las variables globales del tema
        context.update(self.canvas_vars)
        paths = self.elem.get_resolved_values("path", context)
        return paths

    def _load_asset_pixmap(self, rel_path, target_w=None, target_h=None):
        """Carga un QPixmap. Si target_w/target_h son None, carga tamaño original.
           Para SVG, si no se da tamaño, usa el tamaño por defecto del renderer."""
        if not rel_path:
            return None
        if rel_path.startswith("./"):
            abs_path = os.path.join(self.assets_root, rel_path[2:])
        else:
            abs_path = rel_path

        # Obtener el canvas y su caché
        canvas = self.get_canvas()
        cache = canvas._pixmap_cache if canvas else {}
        cache_key = (abs_path, target_w, target_h)
        if cache_key in cache:
            return cache[cache_key]

        ext = os.path.splitext(abs_path)[1].lower()
        if ext == '.svg':
            renderer = QSvgRenderer(abs_path)
            if renderer.isValid():
                default_size = renderer.defaultSize()
                w = int(target_w) if target_w is not None else default_size.width()
                h = int(target_h) if target_h is not None else default_size.height()
                if w <= 0 or h <= 0:
                    w, h = 100, 100
                pix = QPixmap(w, h)
                pix.fill(Qt.transparent)
                painter = QPainter(pix)
                renderer.render(painter)
                painter.end()
                cache[cache_key] = pix  # guardar en caché
                return pix
            return None
        else:
            pix = QPixmap(abs_path)
            if not pix.isNull():
                cache[cache_key] = pix
                return pix

        # Fallback (búsqueda en el mismo directorio) - opcional
        dirname = os.path.dirname(abs_path)
        if os.path.isdir(dirname):
            for f in os.listdir(dirname):
                f_lower = f.lower()
                if f_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                    fallback_path = os.path.join(dirname, f)
                    ext_f = os.path.splitext(f)[1].lower()
                    if ext_f == '.svg':
                        renderer = QSvgRenderer(fallback_path)
                        if renderer.isValid():
                            default_size = renderer.defaultSize()
                            w = int(target_w) if target_w is not None else default_size.width()
                            h = int(target_h) if target_h is not None else default_size.height()
                            if w <= 0 or h <= 0:
                                w, h = 100, 100
                            pix = QPixmap(w, h)
                            pix.fill(Qt.transparent)
                            painter = QPainter(pix)
                            renderer.render(painter)
                            painter.end()
                            return pix
                    else:
                        pix = QPixmap(fallback_path)
                        if not pix.isNull():
                            return pix

        if pix is not None and not pix.isNull():
            cache[cache_key] = pix
            return pix
        return None

class TextCanvasElem(CanvasElem):
    """Canvas item para elementos de texto (text, datetime) con representación real del texto."""

    def __init__(self, elem: ThemeElement, assets_root: str, undo_stack=None,
                 system_name: str = "", variables: dict = None):
        super().__init__(elem, assets_root, undo_stack, system_name, variables)
        # Forzar que el elemento sea seleccionable y movible
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        # Eliminar la etiqueta por defecto (no queremos ver "[text] nombre" encima del texto real)
        # Pero la etiqueta se crea en CanvasElem.__init__, así que la ocultamos o eliminamos
        if hasattr(self, 'label'):
            self.label.setVisible(False)  # Ocultar la etiqueta para no interferir

    def update_geometry(self):
        """Actualiza el rectángulo y posición según el texto real y fuentes."""
        if not self.scene():
            return

        # Tamaño de fuente (normalizado, porcentaje de altura de pantalla)
        font_size_str = self._get_resolved_property("fontSize", "0.04")
        try:
            font_size_norm = float(font_size_str)
        except ValueError:
            font_size_norm = 0.04

        # Texto a mostrar
        text_str = self._get_resolved_property("text", "")
        if not text_str and self.elem.element_type == "datetime":
            # Para datetime, podríamos poner un ejemplo, pero usaremos texto por defecto
            text_str = "01/01/2024 12:00"

        # Forzar mayúsculas?
        force_uppercase = self._get_resolved_property("forceUppercase", "false").lower() == "true"
        if force_uppercase:
            text_str = text_str.upper()

        # Ruta de fuente
        font_path_rel = self._get_resolved_property("fontPath", "")
        font_path_abs = ""
        if font_path_rel and font_path_rel.startswith("./"):
            font_path_abs = os.path.join(self.assets_root, font_path_rel[2:])
        elif font_path_rel:
            font_path_abs = os.path.join(self.assets_root, font_path_rel)

        # Alineación
        alignment_str = self._get_resolved_property("alignment", "left").lower()

        # Line spacing
        line_spacing_str = self._get_resolved_property("lineSpacing", "1.5")
        try:
            line_spacing = float(line_spacing_str)
        except ValueError:
            line_spacing = 1.5

        # Propiedades de tamaño y posición
        pos_str = self._get_resolved_property("pos", "0 0")
        size_str = self._get_resolved_property("size", "0 0")
        min_size_str = self._get_resolved_property("minSize", "")
        max_size_str = self._get_resolved_property("maxSize", "")
        origin_str = self._get_resolved_property("origin", "0 0")

        # Parsear valores normalizados
        px, py = _parse_pos(pos_str)
        sx, sy = _parse_pos(size_str)
        ox, oy = _parse_pos(origin_str)

        w_scene = self.scene().width()
        h_scene = self.scene().height()

        # Tamaño de fuente en píxeles
        font_pixel_size = max(1, h_scene * font_size_norm)

        # Crear fuente
        font = QFont()
        if font_path_abs and os.path.isfile(font_path_abs):
            font_id = QFontDatabase.addApplicationFont(font_path_abs)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    font.setFamily(families[0])
        font.setPointSizeF(font_pixel_size)
        font.setCapitalization(QFont.AllUppercase if force_uppercase else QFont.MixedCase)

        # Medir texto
        fm = QFontMetrics(font)

        # Determinar ancho y alto deseados según el modo de size
        # Si size es (0,0) -> tamaño automático (una línea, ancho según texto)
        # Si size es (w,0) -> ancho fijo, altura automática (word wrap)
        # Si size es (w,h) -> ancho y alto fijos, con truncamiento si es necesario

        if sx == 0 and sy == 0:
            # Modo automático: una línea, ancho según texto
            text_width_px = fm.horizontalAdvance(text_str)
            text_height_px = fm.height() * line_spacing
        elif sx > 0 and sy == 0:
            # Ancho fijo, altura automática (word wrap)
            max_width_px = sx * w_scene
            # Calcular el rectángulo que ocuparía el texto con ese ancho
            bounding_rect = fm.boundingRect(0, 0, max_width_px, 0, Qt.TextWordWrap, text_str)
            text_width_px = bounding_rect.width()
            text_height_px = bounding_rect.height() * line_spacing  # Ajuste por lineSpacing
        else:
            # Ancho y alto fijos (truncado si el texto no cabe)
            text_width_px = max(1, sx * w_scene)
            text_height_px = max(1, sy * h_scene)
            # No aplicamos word wrap automático aquí; ES truncaría con "..."
            # Para la representación visual, podemos dibujar el texto truncado más tarde

        # Aplicar minSize y maxSize (sobre el tamaño del elemento)
        if min_size_str:
            min_w, min_h = _parse_pos(min_size_str)
            min_w_px = min_w * w_scene
            min_h_px = min_h * h_scene
            text_width_px = max(text_width_px, min_w_px)
            text_height_px = max(text_height_px, min_h_px)

        if max_size_str:
            max_w, max_h = _parse_pos(max_size_str)
            max_w_px = max_w * w_scene
            max_h_px = max_h * h_scene
            text_width_px = min(text_width_px, max_w_px)
            text_height_px = min(text_height_px, max_h_px)

        # Posición final
        x_px = px * w_scene - ox * text_width_px
        y_px = py * h_scene - oy * text_height_px

        # Aplicar geometría
        self.setRect(0, 0, text_width_px, text_height_px)
        self.setPos(x_px, y_px)

        # Guardar datos para pintar
        self._cached_font = font
        self._cached_text = text_str
        self._cached_alignment = alignment_str
        self._cached_line_spacing = line_spacing
        self._cached_size_mode = (sx, sy)
        self._cached_w_scene = w_scene
        self._cached_h_scene = h_scene

        # Actualizar handles si está seleccionado
        if self.isSelected():
            self.update_handles()

        # Actualizar zIndex (importante para que respete el orden)
        z_str = self._get_resolved_property("zIndex")
        try:
            z = float(z_str)
        except (ValueError, TypeError):
            z = 1e9
        self.setZValue(z)

    def paint(self, painter: QPainter, option, widget=None):
        """Dibuja el texto real dentro del rectángulo."""
        # Primero dibujar el fondo semitransparente (estilo canvas)
        color = ELEM_COLORS.get(self.elem.element_type, QColor("#607D8B"))
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 80)))
        painter.setPen(QPen(color, 2))
        painter.drawRect(self.rect())

        # Si no hay texto o no tenemos caché, salir
        if not hasattr(self, '_cached_text') or not self._cached_text:
            # Dibujar un texto de placeholder
            painter.setPen(QColor("#ffffff"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Sin texto")
            return

        # Configurar fuente y color
        painter.setFont(self._cached_font)
        # Color del texto: de la propiedad "color" (por defecto blanco)
        color_str = self._get_resolved_property("color", "FFFFFF")
        try:
            if color_str.startswith("#"):
                color_hex = color_str[1:]
            else:
                color_hex = color_str
            r = int(color_hex[0:2], 16)
            g = int(color_hex[2:4], 16)
            b = int(color_hex[4:6], 16)
            painter.setPen(QColor(r, g, b))
        except:
            painter.setPen(QColor(255, 255, 255))

        # Determinar alineación Qt
        align = Qt.AlignLeft | Qt.AlignTop
        if self._cached_alignment == "center":
            align = Qt.AlignCenter
        elif self._cached_alignment == "right":
            align = Qt.AlignRight | Qt.AlignTop

        # Área de dibujo (rectángulo interior con márgenes opcionales? ES no tiene márgenes internos)
        text_rect = self.rect()

        # Modos de dibujo según size_mode
        sx, sy = self._cached_size_mode
        if sx == 0 and sy == 0:
            # Una línea, dibujar sin word wrap
            painter.drawText(text_rect, align, self._cached_text)
        elif sx > 0 and sy == 0:
            # Word wrap
            painter.drawText(text_rect, Qt.TextWordWrap | align, self._cached_text)
        else:
            # Ancho y alto fijos: truncar con "..." si es necesario
            # Usar el texto original y medir si cabe
            fm = painter.fontMetrics()
            # Calcular si el texto cabe en el rectángulo
            if sx > 0:
                # Necesitamos truncar por líneas
                # Esto es complejo; para simplificar, dibujamos con word wrap y si no cabe, se corta
                # ES añade "..." al final de la última línea visible.
                # Implementación simplificada: usar Qt.TextWordWrap y dejar que Qt corte,
                # pero no añadirá "...". Podemos mejorar después.
                painter.drawText(text_rect, Qt.TextWordWrap | align, self._cached_text)
            else:
                painter.drawText(text_rect, align, self._cached_text)

        # Opcional: dibujar un borde más fino para indicar selección
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffaa00"), 2, Qt.DashLine))
            painter.drawRect(self.rect())


class ThemeCanvas(QGraphicsView):
    element_selected = Signal(object)

    def __init__(self, assets_root: str, undo_stack=None, show_rulers: bool = True):
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
        self.setAcceptDrops(True)
        self.canvas_margin = 30   # margen en píxeles para el área de dibujo
        self._scene.selectionChanged.connect(self._on_sel_changed)
        self._current_view: ThemeView | None = None
        self._elem_items: dict = {}
        self._refresh_fn = None  # callback cuando drop añade elem
        self.current_system = ""
        self.current_variables = {}
        self._pixmap_cache = {}
        self.rulers_visible = show_rulers  # <- control de visibilidad

    # --------------------------------------------------------------
    # Reglas dibujadas en el viewport (paintEvent)
    # --------------------------------------------------------------
    def paintEvent(self, event):
        # Primero dibujar lo normal (escena, elementos, etc.)
        super().paintEvent(event)

        if not self.rulers_visible:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)

        view_rect = self.viewport().rect()
        scene_rect = self.sceneRect()
        transform = self.transform()
        top_left = transform.map(scene_rect.topLeft())
        bottom_right = transform.map(scene_rect.bottomRight())
        scene_in_view = QRectF(top_left, bottom_right).normalized()

        # Fondo semitransparente para las reglas
        #painter.fillRect(0, 0, view_rect.width(), 20, QColor(30, 30, 46, 200))
        #painter.fillRect(0, 0, 60, view_rect.height(), QColor(30, 30, 46, 200))

        pen = QPen(QColor(220, 220, 255), 1)
        painter.setPen(pen)
        font = QFont("Arial", 8)
        painter.setFont(font)

        # ---- Regla horizontal (superior) ----
        ruler_y = scene_in_view.top() - 2
        painter.drawLine(0, ruler_y, view_rect.width(), ruler_y)

        for i in range(21):
            x_scene = i * CANVAS_W * 0.05
            x_view = transform.map(QPointF(x_scene, 0)).x()
            painter.drawLine(x_view, ruler_y - 8, x_view, ruler_y + 4)
            text = f"{i * 0.05:.2f}"
            text_rect = painter.fontMetrics().boundingRect(text)
            painter.drawText(x_view - text_rect.width() // 2, ruler_y - 10, text)

        # ---- Regla vertical (izquierda) ----
        ruler_x = scene_in_view.left() - 2
        painter.drawLine(ruler_x, 0, ruler_x, view_rect.height())

        for i in range(21):
            y_scene = i * CANVAS_H * 0.05
            y_view = transform.map(QPointF(0, y_scene)).y()
            painter.drawLine(ruler_x - 8, y_view, ruler_x + 4, y_view)
            text = f"{i * 0.05:.2f}"
            text_rect = painter.fontMetrics().boundingRect(text)
            painter.drawText(ruler_x - text_rect.width() - 4, y_view + text_rect.height() // 2, text)

        # ---- Líneas centrales ----
        x_center_scene = CANVAS_W / 2
        x_center_view = transform.map(QPointF(x_center_scene, 0)).x()
        painter.setPen(QPen(QColor(200, 200, 255), 1, Qt.DashLine))
        painter.drawLine(x_center_view, ruler_y - 12, x_center_view, ruler_y + 6)

        y_center_scene = CANVAS_H / 2
        y_center_view = transform.map(QPointF(0, y_center_scene)).y()
        painter.drawLine(ruler_x - 12, y_center_view, ruler_x + 6, y_center_view)

    def set_rulers_visible(self, visible):
        self.rulers_visible = visible
        self.viewport().update()  # forzar repintado

    def set_view(self, view: ThemeView | None):
        self._current_view = view
        self.rebuild()

    def set_context(self, system_name: str, variables: dict):
        self.current_system = system_name
        self.current_variables = variables
        self.rebuild()

    def rebuild(self):
        for item in list(self._elem_items.values()):
            self._scene.removeItem(item)
        self._elem_items.clear()
        if self._current_view is None:
            return
        for elem in self._current_view.elements:
            if elem.element_type in ('text', 'datetime'):
                item = TextCanvasElem(elem, self.assets_root, self._undo_stack,
                                      system_name=self.current_system,
                                      variables=self.current_variables)
            else:
                item = CanvasElem(elem, self.assets_root, self._undo_stack,
                                  system_name=self.current_system,
                                  variables=self.current_variables)
            self._scene.addItem(item)
            # FORZAR ACTUALIZACIÓN DE GEOMETRÍA DESPUÉS DE AÑADIR A LA ESCENA
            item.update_geometry()
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
        margin = self.canvas_margin
        view_rect = self.viewport().rect()
        # Área disponible restando el margen
        available = view_rect.adjusted(margin, margin, -margin, -margin)
        # Si el área disponible es demasiado pequeña, evitar divisiones por cero
        if available.width() <= 0 or available.height() <= 0:
            return
        scene_rect = self.sceneRect()
        if scene_rect.width() <= 0 or scene_rect.height() <= 0:
            return
        # Calcular escala para que la escena quepa en el área disponible
        scale_x = available.width() / scene_rect.width()
        scale_y = available.height() / scene_rect.height()
        scale = min(scale_x, scale_y)
        # Tamaño escalado de la escena
        scaled_w = scene_rect.width() * scale
        scaled_h = scene_rect.height() * scale
        # Calcular desplazamiento para centrar dentro del área disponible
        offset_x = available.x() + (available.width() - scaled_w) / 2
        offset_y = available.y() + (available.height() - scaled_h) / 2
        # Aplicar la transformación
        transform = QTransform()
        transform.translate(offset_x, offset_y)
        transform.scale(scale, scale)
        self.setTransform(transform)

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

        # Crear las propiedades usando ConditionalValue (sin condición inicial)
        properties = {
            "path": [ConditionalValue(f"./{rel_path}", None)],
            "pos": [ConditionalValue(f"{sp.x() / CANVAS_W:.4f} {sp.y() / CANVAS_H:.4f}", None)],
            "size": [ConditionalValue("0.5 0.5", None)],
            "zIndex": [ConditionalValue("", None)],
        }

        elem = ThemeElement(
            name=f"e_{os.path.splitext(os.path.basename(rel_path))[0]}",
            tag=etype,
            extra=False,
            properties=properties,
        )
        self._current_view.elements.append(elem)
        item = CanvasElem(elem, self.assets_root, self._undo_stack,
                          system_name=self.current_system,
                          variables=self.current_variables)
        self._scene.addItem(item)
        item.update_geometry()
        self._elem_items[id(elem)] = item
        event.acceptProposedAction()
        self.element_selected.emit(elem)
        if self._undo_stack is not None:
            cmd = AddElemCmd(self._current_view, elem, self,
                             refresh_fn=self._refresh_fn)
            self._undo_stack.push(cmd)
            # Refrescar listado de "Elementos en la vista"
            if self._refresh_fn:
                self._refresh_fn()

    def move_element(self, elem: ThemeElement, new_pos_norm: str, old_pos_norm: str, push_undo=True):
        """Mueve un elemento visualmente y actualiza su propiedad 'pos'. Si push_undo es True, crea un comando."""
        item = self._elem_items.get(id(elem))
        if item is None:
            return

        # Registrar comando de deshacer (si se solicita)
        if push_undo and self._undo_stack is not None and old_pos_norm != new_pos_norm:
            cmd = MoveElemCmd(elem, old_pos_norm, new_pos_norm, self, refresh_fn=None)
            self._undo_stack.push(cmd)

        # Obtener el tamaño REAL del item (en píxeles)
        w_px = item.rect().width()
        h_px = item.rect().height()
        if w_px <= 0 or h_px <= 0:
            # Fallback a valores por defecto si el item aún no tiene geometría válida
            w_px, h_px = 100, 100

        # Calcular nueva posición en píxeles
        if hasattr(item, '_get_resolved_property'):
            origin_str = item._get_resolved_origin()
        else:
            # fallback
            if elem.element_type in ("image", "video"):
                origin_str = elem.get_base_value("origin") or "0.5 0"
            else:
                origin_str = elem.get_base_value("origin") or "0 0"
        ox, oy = _parse_pos(origin_str)

        w = self._scene.width()
        h = self._scene.height()

        nx, ny = _parse_pos(new_pos_norm)
        new_x = nx * w - ox * w_px
        new_y = ny * h - oy * h_px

        # Mover visualmente
        item.setPos(new_x, new_y)

        # Actualizar el modelo: solo el valor base de 'pos'
        elem.set_base_value("pos", new_pos_norm)

        # Notificar al inspector (si el elemento está seleccionado)
        self.element_selected.emit(elem)


# ---------------------------------------------------------------------------
# Propiedades del elemento (image, video, helpsystem...)
# ---------------------------------------------------------------------------
class PropertiesPanel(QWidget):
    properties_changed = Signal()

    def __init__(self, undo_stack=None):
        super().__init__()
        self._undo_stack = undo_stack
        self._refresh_elem_list = None # callback para refrescar la lista de elementos
        self._elem: ThemeElement | None = None
        self._rows: dict = {}
        self._canvas_ref = None
        layout = QVBoxLayout(self)

        lbl = QLabel("Propiedades del elemento")
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
        self._new_key = QComboBox()
        self._new_key.setEditable(True)  # permite escribir cualquier propiedad
        self._new_key.lineEdit().setPlaceholderText("Propiedad")
        self._new_key.setCurrentIndex(-1)  # Ningún ítem seleccionado al inicio
        self._new_val = QLineEdit()
        self._new_val.setPlaceholderText("Valor")
        self._new_val.setMaximumWidth(200)  # limita el ancho máximo del valor
        icon_agregar = QIcon(resource_path("iconos/agregar.ico"))
        btn_add = QPushButton(icon_agregar, "")
        btn_add.setFixedWidth(32)
        btn_add.clicked.connect(self._add_prop)
        add_bar.addWidget(self._new_key, 1)
        add_bar.addWidget(self._new_val, 0)
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
        # Limpiar el formulario (todas las filas)
        while self._form.rowCount():
            self._form.removeRow(0)

        if elem is None:
            self._name_edit.setText("")
            self._type_lbl.setText("Tipo: -")
            self._extra_cb.setChecked(False)
            self._new_key.clear()
            return

        self._name_edit.setText(elem.name)
        self._type_lbl.setText(f"Tipo: {elem.element_type}")
        self._extra_cb.setChecked(elem.extra)

        # Crear una fila por cada propiedad existente
        for prop, cv_list in elem.properties.items():
            base_val = elem.get_base_value(prop)

            # Widgets de la fila: QLineEdit + botón eliminar
            edit = QLineEdit(base_val)
            edit.setPlaceholderText(prop)
            icon_menos = QIcon(resource_path("iconos/menos.ico"))
            delete_btn = QPushButton(icon_menos, "")
            delete_btn.setFixedSize(24, 24)
            delete_btn.setToolTip(f"Eliminar propiedad '{prop}'")

            # Conectar el botón con la propiedad actual (usando lambda con argumento por defecto)
            delete_btn.clicked.connect(lambda checked, p=prop: self._delete_property(p))

            # Layout horizontal para alinear el edit y el botón
            row_layout = QHBoxLayout()
            row_layout.addWidget(edit, 1)   # el edit se expande
            row_layout.addWidget(delete_btn)

            # Añadir la fila al formulario
            self._form.addRow(prop + ":", row_layout)
            self._rows[prop] = edit

        self._update_combo_options()

    def set_refresh_callback(self, callback):
        self._refresh_elem_list = callback

    def _delete_property(self, prop_name: str):
        if not self._elem:
            return
        nodes = self._elem.get_property_nodes(prop_name)
        if not nodes:
            QMessageBox.warning(self, "Error", f"No se encontró la propiedad '{prop_name}' para eliminar.")
            return
        reply = QMessageBox.question(
            self, "Eliminar propiedad",
            f"¿Eliminar la propiedad '{prop_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        cmd = DeletePropCommand(self._elem, prop_name, self, self._canvas_ref, self._refresh_elem_list)
        if self._undo_stack:
            self._undo_stack.push(cmd)
        else:
            cmd.redo()

    def _update_combo_options(self):
        """Actualiza el QComboBox con las propiedades sugeridas que aún no tiene el elemento."""
        if not self._elem:
            self._new_key.clear()
            return
        existing = set(self._elem.properties.keys())
        suggested = self._elem.suggested_props()
        # Opciones disponibles = sugeridas - existentes
        available = sorted([p for p in suggested if p not in existing])
        self._new_key.blockSignals(True)
        self._new_key.clear()
        if available:
            self._new_key.addItems(available)
        # Dejar un ítem vacío o un placeholder visual (no es necesario añadir texto)
        self._new_key.setCurrentIndex(-1)
        self._new_key.blockSignals(False)

    def _add_prop(self):
        key = self._new_key.currentText().strip()
        val = self._new_val.text()
        if key and self._elem:
            # Si la clave ya existe, preguntar si sobrescribir
            if key in self._elem.properties:
                reply = QMessageBox.question(
                    self, "Propiedad existente",
                    f"La propiedad '{key}' ya existe.\n¿Deseas sobrescribir su valor?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            # Añadir o actualizar la propiedad correctamente
            self._elem.set_base_value(key, val)
            # Refrescar el panel y el canvas
            self.set_element(self._elem, self._canvas_ref)
            self.properties_changed.emit()
            self._new_val.clear()
            self._new_key.setCurrentIndex(-1)

    def _apply(self):
        if not self._elem:
            return
        # Guardar estado anterior (para deshacer, opcional)
        # Por ahora, simplemente aplicar cambios
        self._elem.name = self._name_edit.text().strip() or self._elem.name
        self._elem.extra = self._extra_cb.isChecked()
        for prop, edit in self._rows.items():
            new_val = edit.text().strip()
            if new_val:
                self._elem.set_base_value(prop, new_val)

        self.set_element(self._elem, self._canvas_ref)
        self.properties_changed.emit()
        self._update_combo_options()


class DeletePropCommand(QUndoCommand):
    def __init__(self, elem, prop_name, panel, canvas, refresh_elem_list):
        super().__init__(f"Eliminar propiedad '{prop_name}'")
        self.elem = elem
        self.prop_name = prop_name
        self.panel = panel
        self.canvas = canvas
        self.refresh_elem_list = refresh_elem_list
        # Guardar copia de los nodos eliminados (serializados a dict)
        self.old_nodes_data = [node.to_dict() for node in elem.get_property_nodes(prop_name)]

    def redo(self):
        self.elem.delete_property_nodes(self.prop_name)
        self._refresh()

    def undo(self):
        # Reconstruir nodos desde los datos guardados
        for node_data in self.old_nodes_data:
            node = XmlNode.from_dict(node_data)
            self.elem.children.append(node)
        self._refresh()

    def _refresh(self):
        # Actualizar el panel (recarga el elemento)
        self.panel.set_element(self.elem, self.canvas)
        self.panel.properties_changed.emit()
        # Actualizar el canvas visual
        self.canvas.rebuild()
        if self.refresh_elem_list:
            self.refresh_elem_list()


# ---------------------------------------------------------------------------
# Folder Asset Browser e Internal Asset Browser
# ---------------------------------------------------------------------------
class FolderAssetBrowser(QListView):
    def __init__(self, assets_root: str):
        super().__init__()
        # Normalizar desde el principio
        self.base_assets_root = os.path.normpath(os.path.abspath(assets_root))
        self.current_dir = self.base_assets_root

        self.setIconSize(QSize(48, 48))
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setGridSize(QSize(80, 80))
        self.setWordWrap(True)

        # Modelo con raíz base
        self.model = ThumbnailFileSystemModel()
        self.model.setRootPath(self.base_assets_root)
        self.model.setFilter(QDir.Dirs | QDir.Files | QDir.NoDotAndDotDot)

        self.proxy = AssetFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.setModel(self.proxy)

        self._update_root_index()
        self.doubleClicked.connect(self._on_double_click)

    def _normalize(self, path: str) -> str:
        """Convierte a ruta normalizada absoluta."""
        return os.path.normpath(os.path.abspath(path))

    def _update_root_index(self):
        """Actualiza el rootIndex de la vista según current_dir."""
        if not os.path.isdir(self.current_dir):
            return
        src_idx = self.model.index(self.current_dir)
        if not src_idx.isValid():
            # Forzar recarga del modelo
            self.model.setRootPath(self.base_assets_root)
            src_idx = self.model.index(self.current_dir)
        if src_idx.isValid():
            self.setRootIndex(self.proxy.mapFromSource(src_idx))
        else:
            # Fallback a la raíz base
            src_idx = self.model.index(self.base_assets_root)
            if src_idx.isValid():
                self.setRootIndex(self.proxy.mapFromSource(src_idx))

    def set_root(self, new_root: str):
        """Cambia la raíz BASE (cuando se cambia la carpeta de assets)."""
        self.base_assets_root = self._normalize(new_root)
        self.model.setRootPath(self.base_assets_root)
        self.current_dir = self.base_assets_root
        self._update_root_index()

    def go_up(self):
        """Subir al directorio padre (si no se sale de la raíz base)."""
        parent = os.path.dirname(self.current_dir)
        if not parent:
            return
        norm_parent = self._normalize(parent)
        norm_current = self._normalize(self.current_dir)
        norm_base = self.base_assets_root
        if norm_parent != norm_current:
            # Verificar que el padre sigue dentro de la base
            try:
                common = os.path.commonpath([norm_base, norm_parent])
                if common == norm_base:
                    self.current_dir = norm_parent
                    self._update_root_index()
            except ValueError:
                pass

    def go_root(self):
        """Volver a la raíz base."""
        self.current_dir = self.base_assets_root
        self._update_root_index()

    def refresh(self):
        """Refresca la vista recargando el modelo."""
        self.model.setRootPath(self.base_assets_root)
        self._update_root_index()

    def get_current_dir(self) -> str:
        return self.current_dir

    def add_item(self, button=None):
        current_dir = self.current_dir
        if not os.path.isdir(current_dir):
            QMessageBox.warning(self, "Sin directorio", "No se puede determinar el directorio actual.")
            return
        menu = QMenu(self)
        action_file = menu.addAction("Añadir archivo(s)")
        action_folder = menu.addAction("Añadir carpeta")
        pos = button.mapToGlobal(button.rect().bottomLeft()) if button else self.mapToGlobal(self.rect().bottomLeft())
        action = menu.exec(pos)
        if action == action_file:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Seleccionar archivos", "",
                "Todos los soportados (*.png *.jpg *.jpeg *.gif *.webp *.svg *.mp4 *.mkv *.avi *.wav *.ogg *.mp3 *.ttf *.otf);;"
                "Imágenes (*.png *.jpg *.jpeg *.gif *.webp);;"
                "Vídeos (*.mp4 *.mkv *.avi);;Audios (*.wav *.ogg *.mp3);;"
                "Fuentes (*.ttf *.TTF *.otf)"
            )
            if files:
                for src in files:
                    dst = os.path.join(current_dir, os.path.basename(src))
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                self.refresh()
        elif action == action_folder:
            name, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre de la carpeta:")
            if ok and name.strip():
                new_dir = os.path.join(current_dir, name.strip())
                if not os.path.exists(new_dir):
                    os.makedirs(new_dir)
                    self.refresh()
                else:
                    QMessageBox.warning(self, "Ya existe", f"La carpeta '{name}' ya existe.")

    def delete_item(self):
        selected = self.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "Sin selección", "Selecciona un elemento para borrar.")
            return
        idx = selected[0]
        src_idx = self.proxy.mapToSource(idx)
        path = self.model.filePath(src_idx)
        if not path:
            return
        reply = QMessageBox.question(self, "Confirmar borrado", f"¿Borrar '{os.path.basename(path)}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo borrar:\n{str(e)}")

    def _on_double_click(self, index):
        src_idx = self.proxy.mapToSource(index)
        path = self.model.filePath(src_idx)
        if os.path.isdir(path):
            self.current_dir = self._normalize(path)
            self._update_root_index()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and hasattr(self, '_drag_start_pos'):
            # Distancia mínima para iniciar el drag (evita falsos positivos)
            if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
                return
            # Iniciar el arrastre
            self.startDrag(Qt.CopyAction)
            # Limpiar estado
            del self._drag_start_pos
        super().mouseMoveEvent(event)

    def startDrag(self, supportedActions):
        selected = self.selectedIndexes()
        if not selected:
            return
        idx = selected[0]
        src_idx = self.proxy.mapToSource(idx)
        if not src_idx.isValid():
            return
        path = self.model.filePath(src_idx)
        if not os.path.isfile(path):
            return
        # Obtener ruta relativa desde la raíz de assets
        rel = os.path.relpath(path, self.base_assets_root).replace('\\', '/')
        mime = QMimeData()
        mime.setText(rel)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class AssetFilterProxyModel(QSortFilterProxyModel):
    """Proxy que muestra solo carpetas y archivos con extensiones soportadas."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Extensiones soportadas (igual que en FolderAssetBrowser)
        self.supported_extensions = {
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
            '.mp4', '.mkv', '.avi',
            '.wav', '.ogg', '.mp3',
            '.ttf', '.TTF', '.otf',
        }

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if not isinstance(model, QFileSystemModel):
            return True
        index = model.index(source_row, 0, source_parent)
        if model.isDir(index):
            return True   # Mostrar siempre las carpetas
        file_path = model.filePath(index)
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.supported_extensions


# ---------------------------------------------------------------------------
# Lista de propiedades de los elementos
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

        # Obtener lista de elementos con su zIndex base (sin condiciones)
        elems_with_z = []
        for elem in view.elements:
            z_str = elem.get_base_value("zIndex")
            try:
                # Si la cadena está vacía o no es un número, tratamos como infinito
                z = float(z_str) if z_str.strip() else float('inf')
            except ValueError:
                z = float('inf')
            elems_with_z.append((elem, z))

        # Ordenar descendente: mayor zIndex primero (los infinitos arriba)
        elems_with_z.sort(key=lambda x: x[1], reverse=True)

        # Guardar la lista ordenada y poblar el QListWidget
        self._elems = [elem for elem, _ in elems_with_z]
        for elem in self._elems:
            item = QListWidgetItem(f"[{elem.element_type}] {elem.name}")
            item.setForeground(ELEM_COLORS.get(elem.element_type, QColor("#607D8B")))
            self._list.addItem(item)

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
# Diálogo Añadir Elemento (con soporte customView y vistas)
# ---------------------------------------------------------------------------
class AddElementDialog(QDialog):
    def __init__(self, parent=None, allowed_types=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir Elemento")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit("e_nuevo")
        self.type_cb = QComboBox()
        # Si se proporciona una lista de tipos permitidos, úsala; si no, todos
        types = allowed_types if allowed_types else ThemeElement.TYPES
        self.type_cb.addItems(types)
        self.extra_cb = QCheckBox("extra=\"true\"")
        self.extra_cb.setChecked(False)
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
            "carousel": {"type": "vertical_wheel", "pos": "0 0", "size": "1 1",
                         "color": "FFFFFF00", "logoScale": "1.7", "logoSize": "0.1 0.05",
                         "logoRotation": "7", "logoRotationOrigin": "5.5 0.5", "logoAlignment": "center",
                         "maxLogoCount": "5", "defaultTransition": "instant", "zIndex": "1"},
            "image": {"path": "./", "pos": "0.5 0.5", "size": "0.5 0.5", "zIndex": "0"},
            "video": {"path": "./", "pos": "0.5 0.5", "size": "0.5 0.5", "zIndex": "1"},
            "text": {"pos": "0.5 0.5", "size": "0.5 0.1",
                     "color": "FFFFFF", "fontSize": "0.04", "text": ""},
            "rating": {"pos": "0.5 0.9", "size": "0.3 0.06",
                       "filledPath": "./", "unfilledPath": "./"},
            "datetime": {"pos": "0.5 0.1", "size": "0.3 0.05",
                         "color": "FFFFFF", "fontSize": "0.03", "format": "%Y-%m-%d"},
            "helpsystem": {"pos": "0.5 0.96",
                           "textColor": "FFFFFF", "iconColor": "FFFFFF"},
            "textlist": {"pos": "0.5 0.5", "size": "0.4 0.8",
                         "primaryColor": "FFFFFF", "secondaryColor": "AAAAAA",
                         "selectedColor": "FFFF00", "selectorColor": "333333"},
            "gamecarousel": {"type": "vertical_wheel", "pos": "0 0", "size": "1 1",
                             "logoScale": "1.5", "logoSize": "0.14 0.14", "logoRotation": "-6.5",
                             "logoRotationOrigin": "5.5 0.5", "logoAlingment": "center", "maxLogoCount": "7",
                             "imageSource": "marquee", "zIndex": "6"},
        }
        props = defaults.get(etype, {"pos": "0.5 0.5", "size": "0.3 0.3"}).copy()
        # Convertir cada valor a ConditionalValue
        converted_props = {}
        for key, value in props.items():
            converted_props[key] = [ConditionalValue(value, None)]
        return ThemeElement(
            name=self.name_edit.text().strip() or "e_nuevo",
            tag=etype,
            extra=self.extra_cb.isChecked(),
            properties=converted_props,
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
# Pestaña de assets internas de la aplicación
# ---------------------------------------------------------------------------
class InternalAssetsTree(QTreeView):
    """Árbol de assets internos (incluidos con la aplicación). Los botones de navegación están deshabilitados.
    Al hacer doble clic en un archivo o carpeta, emite la señal copy_requested con la ruta relativa y absoluta."""
    copy_requested = Signal(str, str)       # para archivos: (rel_path, full_path)
    copy_folder_requested = Signal(str, str)  # para carpetas: (rel_path, full_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setIndentation(10)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setIconSize(QSize(48, 48))  # Tamaño de miniatura

        internal_assets = resource_path("assets")
        if not os.path.isdir(internal_assets):
            internal_assets = ""

        self.model = ThumbnailFileSystemModel()
        self.model.setRootPath(internal_assets)
        self.model.setFilter(QDir.Dirs | QDir.Files | QDir.NoDotAndDotDot)
        self.setModel(self.model)
        if internal_assets:
            self.setRootIndex(self.model.index(internal_assets))

        # Ocultar columnas extra
        for col in range(1, self.model.columnCount()):
            self.setColumnHidden(col, True)

        self.doubleClicked.connect(self._on_double_click)

    def _on_double_click(self, index):
        file_path = self.model.filePath(index)
        if os.path.isdir(file_path):
            # Es una carpeta
            root_path = self.model.rootPath()
            if root_path and file_path.startswith(root_path):
                rel_path = os.path.relpath(file_path, root_path).replace('\\', '/')
                self.copy_folder_requested.emit(rel_path, file_path)
        elif os.path.isfile(file_path):
            root_path = self.model.rootPath()
            if root_path and file_path.startswith(root_path):
                rel_path = os.path.relpath(file_path, root_path).replace('\\', '/')
                self.copy_requested.emit(rel_path, file_path)


class ThumbnailFileSystemModel(QFileSystemModel):
    """Modelo de sistema de archivos que devuelve miniaturas para imágenes y SVGs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size = QSize(48, 48)
        self.thumb_cache = {}

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DecorationRole and index.column() == 0:
            file_path = self.filePath(index)
            if os.path.isfile(file_path):
                if file_path in self.thumb_cache:
                    return self.thumb_cache[file_path]
                icon = self._generate_thumbnail(file_path)
                if icon:
                    self.thumb_cache[file_path] = icon
                    return icon
        return super().data(index, role)

    def _generate_thumbnail(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
            pix = QPixmap(file_path)
            if not pix.isNull():
                return QIcon(pix.scaled(self.icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif ext == '.svg':
            renderer = QSvgRenderer(file_path)
            if renderer.isValid():
                pix = QPixmap(self.icon_size)
                pix.fill(Qt.transparent)
                painter = QPainter(pix)
                renderer.render(painter)
                painter.end()
                return QIcon(pix)
        return None


# ---------------------------------------------------------------------------
# Visual Builder Tab
# ---------------------------------------------------------------------------
class VisualBuilderTab(QWidget):
    assets_root_changed = Signal(str)  # emitida cuando el usuario cambia la carpeta
    model_changed = Signal()

    def __init__(self, theme_model: ThemeModel, assets_root: str):
        super().__init__()
        self.theme_model = theme_model
        self.assets_root = assets_root
        self.theme_assets_browser = None
        self.internal_assets_tree = None
        self._current_view: ThemeView | None = None
        self._undo_stack = QUndoStack(self)
        self._setup_ui()
        self._is_theme_loaded = False

    def set_rulers_visible(self, visible):
        if hasattr(self._canvas, 'set_rulers_visible'):
            self._canvas.set_rulers_visible(visible)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Cargar iconos desde la carpeta 'iconos'
        icon_agregar = QIcon(resource_path("iconos/agregar.ico"))
        icon_menos = QIcon(resource_path("iconos/menos.ico"))

        # Toolbar vistas + undo
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Vista:"))
        self._view_cb = QLabel()
        self._view_cb.setFixedWidth(270)
        self._view_cb.setMaximumHeight(30)
        self._view_cb.setWordWrap(True)
        self._view_cb.setStyleSheet("background: #1e1e1e; color: #d4d4d4; padding: 4px;")
        toolbar.addWidget(self._view_cb)

        self._btn_add_view = QPushButton(icon_agregar, " Vista")
        self._btn_add_view.setEnabled(False)
        self._btn_del_view = QPushButton(icon_menos, " Vista")
        self._btn_del_view.setEnabled(False)
        self._btn_add_elem = QPushButton(icon_agregar, " Elemento")
        self._btn_add_elem.setEnabled(False) # Deshabilitado por defecto
        btn_del_elem = QPushButton(icon_menos, " Elemento")
        btn_del_elem.setToolTip("Eliminar el elemento seleccionado")
        self._btn_add_view.clicked.connect(self._add_view)
        self._btn_del_view.clicked.connect(self._delete_view)
        self._btn_add_elem.clicked.connect(self._add_element)
        btn_del_elem.clicked.connect(self._delete_selected_element)
        for b in (self._btn_add_view, self._btn_del_view, self._btn_add_elem, btn_del_elem):
            toolbar.addWidget(b)

        self._btn_del_elem = btn_del_elem
        self._btn_del_elem.setEnabled(False) # inicialmente deshabilitado

        # Selector de sistema para resolver ${system.theme}
        toolbar.addWidget(QLabel("  Sistema de ejemplo:"))
        self._system_cb = QComboBox()
        self._system_cb.addItems(["arcade", "gba", "megadrive", "neogeo", "nes", "psx", "retrobat","snes"])
        self._system_cb.setCurrentText("snes")
        self._system_cb.currentTextChanged.connect(self._on_system_changed)
        toolbar.addWidget(self._system_cb)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        # Izquierda: assets + lista
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 10, 0)

        # Barra de ruta de assets
        assets_bar = QHBoxLayout()
        assets_bar.addWidget(QLabel("Assets disponibles:"))
        assets_bar.addStretch()
        btn_change_assets = QToolButton()
        btn_change_assets.setIcon(QIcon(resource_path("iconos/open.ico")))
        btn_change_assets.setToolTip("Cambiar carpeta de assets")
        btn_change_assets.clicked.connect(self._change_assets_root)
        assets_bar.addWidget(btn_change_assets)
        lv.addLayout(assets_bar)

        self._assets_path_lbl = QLabel(self.assets_root)
        self._assets_path_lbl.setStyleSheet("color:#aaa; font-size:10px; padding:0 2px;")
        self._assets_path_lbl.setWordWrap(True)
        lv.addWidget(self._assets_path_lbl)

        # Crear pestañas de assets
        self.assets_tabs = QTabWidget()

        # Pestaña 1: Theme Assets (con barra de navegación)
        self.theme_assets_browser = FolderAssetBrowser(self.assets_root)
        theme_panel = self._create_asset_panel(self.theme_assets_browser, show_nav=True)
        self.assets_tabs.addTab(theme_panel, "Theme Assets")

        # Pestaña 2: Internal Assets (sin barra de navegación, con miniaturas y mensaje)
        self.internal_assets_tree = InternalAssetsTree()
        self.internal_assets_tree.copy_requested.connect(self._copy_internal_asset)
        self.internal_assets_tree.copy_folder_requested.connect(self._copy_internal_folder)

        internal_panel = QWidget()
        internal_layout = QVBoxLayout(internal_panel)
        internal_layout.setContentsMargins(0, 0, 0, 0)

        info_label = QLabel(
            "📁 Haz doble clic en un elemento (archivo o carpeta) para copiarlo al directorio de assets del theme actual.\n\n"
            "• Archivos: se copian individualmente.\n"
            "• Carpetas: se copia todo su contenido (subcarpetas y archivos).")
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "background: #2d2d2d; color: #ffaa00; padding: 4px; border-radius: 4px; margin: 0 0 5px 0;")
        internal_layout.addWidget(info_label)

        internal_layout.addWidget(self.internal_assets_tree)
        self.assets_tabs.addTab(internal_panel, "Internal Assets")

        lv.addWidget(self.assets_tabs, 2)

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

        # Derecha: Propiedades del elemento
        self._inspector = PropertiesPanel(self._undo_stack)
        self._inspector.set_refresh_callback(self._refresh_elem_list)
        self._inspector.properties_changed.connect(self._on_props_changed)
        splitter.addWidget(self._inspector)

        splitter.setStretchFactor(0, 1)  # izquierda (assets)
        splitter.setStretchFactor(1, 4)  # centro (canvas)
        splitter.setStretchFactor(2, 1)  # derecha (propiedades del elemento)

        # ---- Añadir anchos mínimos ----
        splitter.widget(0).setMinimumWidth(300)  # assets browser
        splitter.widget(2).setMinimumWidth(300)  # propiedades del elemento
        main_layout.addWidget(splitter)

    # Creación de pestañas para los assets del theme e internos
    def _create_asset_panel(self, browser: FolderAssetBrowser, show_nav: bool = True) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        if show_nav:
            icon_up = QIcon(resource_path("iconos/subir.ico"))
            icon_home = QIcon(resource_path("iconos/home.ico"))
            icon_agregar = QIcon(resource_path("iconos/agregar.ico"))
            icon_delete = QIcon(resource_path("iconos/borrar.ico"))

            nav_layout = QGridLayout()
            nav_layout.setHorizontalSpacing(10)
            nav_layout.setVerticalSpacing(5)
            btn_up = QPushButton(icon_up, " Subir")
            btn_root = QPushButton(icon_home, " Raíz")
            btn_agregar = QPushButton(icon_agregar, " Añadir")
            btn_delete = QPushButton(icon_delete, " Borrar")
            btn_up.clicked.connect(browser.go_up)
            btn_root.clicked.connect(browser.go_root)
            btn_agregar.clicked.connect(lambda: browser.add_item(btn_agregar))
            btn_delete.clicked.connect(browser.delete_item)
            nav_layout.addWidget(btn_up, 0, 0)
            nav_layout.addWidget(btn_root, 0, 1)
            nav_layout.addWidget(btn_agregar, 1, 0)
            nav_layout.addWidget(btn_delete, 1, 1)
            nav_layout.setColumnStretch(0, 1)
            nav_layout.setColumnStretch(1, 1)
            layout.addLayout(nav_layout)
        layout.addWidget(browser)
        return panel

    # Copiar asset o carpeta interno al del theme cargado
    def _copy_internal_asset(self, rel_path: str, full_path: str):
        """Copia un asset interno al directorio de assets del theme actual."""
        if not self.assets_root or not os.path.isdir(self.assets_root):
            QMessageBox.warning(self, "Sin carpeta de assets", "Primero debes tener un theme con carpeta de assets.")
            return
        # Pedir carpeta de destino dentro de assets_root
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de destino en el theme",
            self.assets_root,
            options=QFileDialog.ShowDirsOnly
        )
        if not dest_dir:
            return
        dest_path = os.path.join(dest_dir, os.path.basename(full_path))
        if os.path.exists(dest_path):
            reply = QMessageBox.question(
                self, "Sobrescribir",
                f"El archivo '{os.path.basename(full_path)}' ya existe en el destino.\n¿Sobrescribir?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        try:
            shutil.copy2(full_path, dest_path)
            QMessageBox.information(self, "Copiado", f"Asset copiado a:\n{dest_path}")
            # Refrescar el navegador de assets del tema
            self.theme_assets_browser.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo copiar:\n{str(e)}")

    def _copy_internal_folder(self, rel_path: str, full_path: str):
        """Copia una carpeta entera (con todo su contenido) al directorio de assets del theme actual, mostrando progreso."""
        if not self.assets_root or not os.path.isdir(self.assets_root):
            QMessageBox.warning(self, "Sin carpeta de assets", "Primero debes tener un theme con carpeta de assets.")
            return

        # Pedir carpeta de destino dentro de assets_root
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de destino en el theme",
            self.assets_root,
            options=QFileDialog.ShowDirsOnly
        )
        if not dest_dir:
            return

        folder_name = os.path.basename(full_path)
        dest_path = os.path.join(dest_dir, folder_name)

        # Verificar si ya existe
        if os.path.exists(dest_path):
            reply = QMessageBox.question(
                self, "Sobrescribir",
                f"La carpeta '{folder_name}' ya existe en el destino.\n¿Sobrescribir su contenido?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            # Eliminar la carpeta destino existente para sobrescribir limpio
            shutil.rmtree(dest_path)

        # ---- Contar archivos totales a copiar ----
        total_files = 0
        for root, dirs, files in os.walk(full_path):
            total_files += len(files)

        if total_files == 0:
            QMessageBox.information(self, "Carpeta vacía", "La carpeta seleccionada no contiene archivos para copiar.")
            return

        # ---- Crear diálogo de progreso ----
        progress = QProgressDialog(f"Copiando carpeta '{folder_name}'...", "Cancelar", 0, total_files, self)
        progress.setWindowTitle("Copiando...")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)  # Muestra el diálogo inmediatamente
        progress.setMinimumSize(500, 100)
        progress.setValue(0)

        # Personalizar la barra de progreso
        bar = progress.findChild(QProgressBar)
        if bar:
            bar.setStyleSheet("""
                QProgressBar {
                    border: 2px solid #1565C0;
                    border-radius: 6px;
                    height: 20px;          /* Altura de la barra */
                    text-align: center;
                    font-weight: bold;
                    background-color: #1e1e1e;
                }
                QProgressBar::chunk {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2E7D32, stop:1 #2EA332);
                    border-radius: 5px;
                }
            """)

        copied_count = 0
        cancelado = False

        try:
            # Aseguramos que la carpeta destino existe
            os.makedirs(dest_path, exist_ok=True)
            for root, dirs, files in os.walk(full_path):
                # Crear subcarpetas en destino
                rel_root = os.path.relpath(root, full_path)
                dest_sub = os.path.join(dest_path, rel_root) if rel_root != '.' else dest_path
                os.makedirs(dest_sub, exist_ok=True)

                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(dest_sub, file)
                    if progress.wasCanceled():
                        cancelado = True
                        raise InterruptedError("Cancelado por el usuario")
                    shutil.copy2(src_file, dst_file)
                    copied_count += 1
                    progress.setValue(copied_count)
                    progress.setLabelText(f"Copiando {copied_count} de {total_files}\n{os.path.basename(src_file)}")
                    QApplication.processEvents()

            if not cancelado:
                progress.setValue(total_files)
                normalized_path = os.path.normpath(dest_path)
                QMessageBox.information(self, "Copia completada",
                                        f"Se copiaron {copied_count} archivos en:\n{normalized_path}")
                # Refrescar navegador de assets
                self.theme_assets_browser.refresh()

        except InterruptedError:
            # Si se canceló, eliminar la carpeta destino parcial
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path, ignore_errors=True)
            QMessageBox.warning(self, "Cancelado", "La copia fue cancelada. No se copió ningún archivo.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo copiar la carpeta:\n{str(e)}")
            # Limpiar archivos parciales
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path, ignore_errors=True)

    # Habilitar botón Añadir vista y Eliminar vista (si exite)
    def _update_buttons_state(self):
        has_views = self._is_theme_loaded and len(self.theme_model.views) > 0
        self._btn_add_view.setEnabled(self._is_theme_loaded)
        self._btn_del_view.setEnabled(has_views)

    def refresh_views(self):
        if self.theme_model is None:
            self._canvas.set_view(None)
            self._view_cb.setText("")
            return
        # Tomamos la primera vista por defecto, o la que esté activa
        elif self.theme_model.views:
            # Si ya hay una vista actual, la respetamos; si no, tomamos la primera
            if self._current_view is None or self._current_view not in self.theme_model.views:
                self._set_view(self.theme_model.views[0])
            else:
                self._set_view(self._current_view)
            # Actualizar el texto del QTextEdit
            view = self._current_view
            label = f"[customView] {view.name}" if view.is_custom else view.name
            self._view_cb.setText(label)
        else:
            self._set_view(None)
            self._view_cb.setText("")
        self._update_buttons_state()  # Habilitar botónes añadir vista y eliminar vista

    def load_model(self, model: ThemeModel):
        """Carga un modelo distinto en el builder (usado por ThemeSet)."""
        self.theme_model = model
        self._undo_stack.clear()
        self.refresh_views()
        # Habilitar botónes añadir vista y eliminar vista dependiendo de si el modelo tiene vistas
        self._is_theme_loaded = True
        self._update_buttons_state()

    def _set_view(self, view: ThemeView | None):
        self._current_view = view
        self._canvas.set_view(view)
        self._elem_list.refresh(view)
        self._inspector.set_element(None)

        # Habilitar o deshabilitar el botón "Añadir Elemento"
        self._btn_add_elem.setEnabled(view is not None)

        # Forzar la resolución del sistema actual (para media con ${system.theme]
        if view is not None:
            current_system = self._system_cb.currentText().strip()
            if current_system:
                self._canvas.set_context(current_system, getattr(self.theme_model, 'variables', {}))
            else:
                self._canvas.set_context("", {})

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
            self._update_buttons_state()  # Habilitar botónes añadir vista y eliminar vista

        self.model_changed.emit()

    def _delete_view(self):
        if self._current_view is None:
            return
        self.theme_model.remove_view(self._current_view.name)
        self.refresh_views()
        self._update_buttons_state()  # Habilitar botónes añadir vista y eliminar vista

        self.model_changed.emit()

    def _add_element(self):
        if self._current_view is None:
            QMessageBox.warning(self, "Sin vista", "Crea primero una vista.")
            return

        allowed = self._get_allowed_types_for_view(self._current_view)
        dlg = AddElementDialog(self, allowed_types=allowed)
        if dlg.exec() == QDialog.Accepted:
            elem = dlg.get_element()
            self._current_view.elements.append(elem)
            self._canvas.rebuild()
            self._elem_list.refresh(self._current_view)
            cmd = AddElemCmd(self._current_view, elem, self._canvas,
                             refresh_fn=self._refresh_elem_list)
            self._undo_stack.push(cmd)
            self._on_elem_from_list(elem)

        self.model_changed.emit()

    def _delete_selected_element(self):
        """Elimina el elemento actualmente seleccionado con confirmación."""
        elem = self._inspector._elem
        if not elem:
            QMessageBox.warning(self, "Sin selección", "No hay ningún elemento seleccionado.")
            return

        reply = QMessageBox.question(
            self, "Confirmar borrado",
            f"¿Eliminar el elemento '{elem.name}' (tipo: {elem.element_type})?\nEsta acción se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._on_elem_deleted(elem)

    def _get_allowed_types_for_view(self, view: ThemeView) -> List[str]:
        """Devuelve los tipos de elemento que se pueden añadir en la vista dada."""
        # Si es una customView y tiene herencia, usamos los tipos de la vista base
        if view.is_custom and view.inherits:
            base_view = view.inherits
            # Buscar si base_view es una vista estándar o otra customView
            # Por simplicidad, asumimos que solo puede heredar de vistas estándar
            allowed = ThemeElement.VIEW_ALLOWED_TYPES.get(base_view, ThemeElement.TYPES)
        else:
            # Vista estándar o custom sin herencia
            allowed = ThemeElement.VIEW_ALLOWED_TYPES.get(view.name, ThemeElement.TYPES)
        # Siempre se pueden añadir elementos extra (cualquier tipo)
        # Pero el filtro es orientativo, no restrictivo; el usuario podría querer añadir
        # un tipo no listado marcándolo como extra. Devolvemos la lista completa.
        # Si prefieres restringir, devuelve solo los permitidos.
        return allowed

    def _on_elem_from_list(self, elem: ThemeElement):
        self._inspector.set_element(elem, self._canvas)
        self._canvas.select_element(elem)
        self._btn_del_elem.setEnabled(True)

        self.model_changed.emit()

    def _on_elem_from_canvas(self, elem: ThemeElement | None):
        self._inspector.set_element(elem, self._canvas)
        if elem:
            self._elem_list.select_elem(elem)
        self._btn_del_elem.setEnabled(elem is not None)

    def _on_elem_deleted(self, elem: ThemeElement):
        if self._current_view:
            cmd = DelElemCmd(self._current_view, elem, self._canvas,
                             refresh_fn=self._refresh_elem_list)
            self._undo_stack.push(cmd)
            self._inspector.set_element(None)
            self._btn_del_elem.setEnabled(False)

    def _refresh_elem_list(self):
        self._elem_list.refresh(self._current_view)

    def _on_props_changed(self):
        self._canvas.rebuild()
        elem = self._inspector._elem
        if elem:
            self._canvas.select_element(elem)
            self._elem_list.refresh(self._current_view)
            self._elem_list.select_elem(elem)

        self.model_changed.emit()

    def _change_assets_root(self):
        new_root = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de assets", self.assets_root)
        if new_root and new_root != self.assets_root:
            self.assets_root = new_root
            self._canvas.assets_root = new_root
            self.theme_assets_browser.set_root(new_root)
            self._assets_path_lbl.setText(new_root)
            self.assets_root_changed.emit(new_root)

    def set_system_context(self, system_name: str):
        variables = getattr(self.theme_model, 'variables', {})
        self._canvas.set_context(system_name, variables)

    def _on_system_changed(self, system_name: str):
        if system_name.strip():
            variables = getattr(self.theme_model, 'variables', {})
            self._canvas.set_context(system_name, variables)
        else:
            # Si está vacío, no pasar sistema (o pasar cadena vacía)
            self._canvas.set_context("", {})


# ---------------------------------------------------------------------------
# Preview Tab
# ---------------------------------------------------------------------------
class PreviewTab(QWidget):
    def __init__(self, theme_model: ThemeModel, assets_root: str):
        super().__init__()
        self.theme_model = theme_model
        self.assets_root = assets_root
        self.current_system = ""
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self._view_cb = QLabel()
        self._view_cb.setFixedWidth(270)
        self._view_cb.setMaximumHeight(30)
        self._view_cb.setWordWrap(True)
        self._view_cb.setStyleSheet("background: #1e1e1e; color: #d4d4d4; padding: 4px;")
        bar.addWidget(QLabel("Vista:"))
        bar.addWidget(self._view_cb)

        # Selector de sistema
        bar.addWidget(QLabel("Sistema de ejemplo:"))
        self._system_cb = QComboBox()
        self._system_cb.addItems(["arcade", "gba", "megadrive", "neogeo", "nes", "psx", "retrobat","snes"])
        self._system_cb.setCurrentText("snes")
        self._system_cb.currentTextChanged.connect(self._on_system_changed)
        bar.addWidget(self._system_cb)

        bar.addStretch()
        layout.addLayout(bar)
        self._canvas = ThemeCanvas(assets_root, show_rulers=False)
        self._canvas.setDragMode(QGraphicsView.NoDrag)
        self._canvas.setAcceptDrops(False)
        layout.addWidget(self._canvas)

    def set_context(self, system_name: str):
        self.current_system = system_name
        variables = getattr(self.theme_model, 'variables', {})
        self._canvas.set_context(system_name, variables)
        # Sincronizar el combo si el sistema viene de fuera (ThemeSet)
        if system_name and system_name != self._system_cb.currentText():
            self._system_cb.blockSignals(True)
            self._system_cb.setCurrentText(system_name)
            self._system_cb.blockSignals(False)

    def _on_system_changed(self, system_name: str):
        if system_name.strip():
            self.set_context(system_name)
        else:
            self.set_context("")

    def set_assets_root(self, root: str):
        self.assets_root = root
        self._canvas.assets_root = root

    def refresh(self):
        if self.theme_model.views:
            # Obtener la vista actual desde el canvas (si existe y es válida)
            current = self._canvas._current_view
            if current is None or current not in self.theme_model.views:
                view = self.theme_model.views[0]
            else:
                view = current
            self._load_view(view)
            # Mostrar el nombre igual que en el editor visual
            label = f"[customView] {view.name}" if view.is_custom else view.name
            self._view_cb.setText(label)
        else:
            self._canvas.set_view(None)
            self._view_cb.setText("")

    def _load_view(self, view: ThemeView):
        if view:
            self._canvas.set_view(view)
            # actualizar contexto etc.
            current_system = self._system_cb.currentText().strip()
            if current_system:
                self._canvas.set_context(current_system, getattr(self.theme_model, 'variables', {}))
            else:
                self._canvas.set_context("", {})
        else:
            self._canvas.set_view(None)


# ---------------------------------------------------------------------------
# Theme Set Tab  (multi-sistema)
# ---------------------------------------------------------------------------
class ThemeSetTab(QWidget):
    # Emitido cuando el usuario quiere editar un sistema en el builder principal
    load_model_requested = Signal(object, str)  # (ThemeModel, system_name)

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

        btn_edit = QPushButton("Modificar en Editor Visual →")
        btn_edit.setStyleSheet("background:#1565C0; color:white; padding:8px; font-weight:bold;")
        btn_edit.setToolTip("Carga el tema de este sistema en el Editor Visual.")
        btn_edit.clicked.connect(self._edit_in_builder)
        rv.addWidget(btn_edit)

        btn_copy = QPushButton("Copiar tema actual → este sistema")
        btn_copy.setToolTip("Copia el tema del Editor Visual a este sistema.")
        btn_copy.clicked.connect(self._copy_from_current)
        rv.addWidget(btn_copy)

        rv.addWidget(QLabel("Vista previa theme.xml del sistema:"))
        self._xml_preview = QPlainTextEdit()
        self._xml_preview.setReadOnly(True)
        self._xml_preview.setFont(QFont("Monospace", 10))
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
# Ventana Principal
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"egbtheme-creator {APP_VERSION} (Beta) —  Batocera/Retrobat Theme Creator")
        self.resize(1700, 900) # Tamaño de la ventana de la aplicación por defecto
        self.center() # Centrada en el monitor

        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self._project_root = os.path.dirname(self._base_dir)
        self._assets_root = resource_path("assets")

        # Modelo activo (puede ser reemplazado por ThemeSet)
        self.theme_model = None
        self._active_system = None  # para indicar qué sistema se edita
        self._saved_model_xml = ""  # XML del último guardado

        # Theme Set
        self._theme_set = ThemeSet("mi_theme_set")

        # Barra de tareas
        self.create_action()
        self.create_menu()
        self._build_toolbar()

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # Opción de guardado si hay cambios
        self._changes_unsaved = False

        # Tab 1: Editor XML
        self._xml_tab = XMLEditorTab(self.theme_model)
        self._xml_tab.model_changed.connect(self._on_model_from_xml)
        self._xml_tab.model_changed.connect(self._on_current_model_changed)
        self._tabs.addTab(self._xml_tab, "Editor XML")

        # Detección de "Deshacer", "Rehacer" en el XML y archivo XML cargado
        self._xml_tab.editor.undoAvailable.connect(self._on_xml_undo_available)
        self._xml_tab.editor.redoAvailable.connect(self._on_xml_redo_available)
        self._xml_tab.file_loaded.connect(self._on_xml_file_loaded)

        # Detección de cambios sin guardar en el XML
        self._xml_tab.editor.document().modificationChanged.connect(self._update_unsaved_flag)

        # Tab 2: Editor Visual
        self._builder_tab = VisualBuilderTab(self.theme_model, self._assets_root)
        self._builder_tab.assets_root_changed.connect(self._on_assets_root_changed)
        self._builder_tab.model_changed.connect(self._on_current_model_changed)
        self._tabs.addTab(self._builder_tab, "Editor Visual")

        # Detección de "Deshacer" y "Rehacer"
        self._builder_tab._undo_stack.canUndoChanged.connect(self._on_builder_undo_available)
        self._builder_tab._undo_stack.canRedoChanged.connect(self._on_builder_redo_available)

        # Detección de cambios sin guardar en el "Editor visual"
        self._builder_tab._undo_stack.cleanChanged.connect(self._on_builder_clean_changed)

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

        self._editing_system_from_set = None  # Nombre del sistema que se está editando (si viene de ThemeSet)
        self._theme_set_modified = False  # Flag para saber si el modelo actual difiere del guardado en ThemeSet

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.installEventFilter(self)

        # Barra de estado (donde van los menús)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Aplicar tema inicial (modo oscuro o modo claro)
        self.apply_system_theme()

    # Función para detectar archivo XML cargado
    def _on_xml_file_loaded(self):
        """Se llama cuando se carga un archivo XML desde disco (nuevo o importado)."""
        if self.theme_model:
            self._saved_model_xml = self.theme_model.to_xml()
            self._changes_unsaved = False
            self._update_save_action_state()
            # También limpiamos la pila del editor visual para evitar comandos obsoletos
            self._builder_tab._undo_stack.clear()
            self._builder_tab._undo_stack.setClean()
            self._builder_tab._canvas._pixmap_cache.clear()

    # Funciones para activar "deshacer y rehacer"
    def _update_undo_redo_state(self):
        """Actualiza el estado de los botones Deshacer/Rehacer según la pestaña activa."""
        current = self._tabs.currentWidget()
        if current == self._xml_tab:
            self.undo_action.setEnabled(self._xml_tab.editor.document().isUndoAvailable())
            self.redo_action.setEnabled(self._xml_tab.editor.document().isRedoAvailable())
        elif current == self._builder_tab:
            self.undo_action.setEnabled(self._builder_tab._undo_stack.canUndo())
            self.redo_action.setEnabled(self._builder_tab._undo_stack.canRedo())
        else:
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)

    def _on_xml_undo_available(self, available: bool):
        if self._tabs.currentWidget() == self._xml_tab:
            self.undo_action.setEnabled(available)

    def _on_xml_redo_available(self, available: bool):
        if self._tabs.currentWidget() == self._xml_tab:
            self.redo_action.setEnabled(available)

    def _on_builder_undo_available(self, available: bool):
        # Solo actualiza si la pestaña activa es la del builder
        if self._tabs.currentWidget() == self._builder_tab:
            self.undo_action.setEnabled(available)

    def _on_builder_redo_available(self, available: bool):
        if self._tabs.currentWidget() == self._builder_tab:
            self.redo_action.setEnabled(available)

    # Habilitar botón de guardado
    def _on_xml_modification_changed(self, changed: bool):
        self._update_unsaved_flag()

    def _on_builder_clean_changed(self):
        self._update_unsaved_flag()

    def _update_save_action_state(self):
        """Habilita Guardar si el modelo tiene cambios sin guardar."""
        self.save_action.setEnabled(self.theme_model is not None and self._changes_unsaved)

    # Habilitar botón "Nuevo XML"
    def _update_actions_state(self):
        has_model = self.theme_model is not None
        self.new_action.setEnabled(has_model)

    # ------------------------------------------------------------------
    # Centrar la ventana de la aplicación al ejecutarse en el monitor
    # ------------------------------------------------------------------
    def center(self):
        """Centra la ventana en la pantalla donde se encuentra el cursor."""
        # Obtener el rectángulo de la pantalla principal (o la que contiene la ventana)
        screen = QApplication.primaryScreen().availableGeometry()
        # Si se quiere que se centre en la pantalla donde está el ratón:
        # screen = QApplication.screenAt(QCursor.pos()).availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    # ------------------------------------------------------------------
    # Eventos deshacer y rehacer
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.StandardKey.Undo):
                self.global_undo()
                return True
            elif event.matches(QKeySequence.StandardKey.Redo):
                self.global_redo()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Aplicar theme del sistema
    # ------------------------------------------------------------------
    def apply_system_theme(self):
        """Aplica el tema de la aplicación según el tema del sistema."""
        # Detecta el tema actual. darkdetect.theme() devuelve 'Dark' o 'Light'
        if darkdetect.isDark():
            theme = 'dark'
        else:
            theme = 'light'

        # Opcional: Guardar el tema actual para futuras comprobaciones
        self.current_theme = theme

    def start_theme_listener(self):
        """Inicia un listener que vigila los cambios de tema en el sistema."""

        def on_theme_change():
            # Esta función se llamará cuando el tema del sistema cambie
            self.apply_system_theme()

        # Configurar el listener de darkdetect (se ejecuta en un hilo separado)
        self.listener = darkdetect.Listener(on_theme_change)
        self.listener.start()  # Inicia la escucha

    # ------------------------------------------------------------------
    # Menús y opciones de los mismo en la barra de herramientas
    # ------------------------------------------------------------------
    def create_action(self):
        self.new_action = QAction(QIcon(resource_path("iconos/new.ico")), "Nuevo XML")
        self.new_action.setEnabled(False) # Deshabilitado al arrancar la aplicación
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.setStatusTip("Nuevo XML")
        self.new_action.triggered.connect(self.new)

        self.save_action = QAction(QIcon(resource_path("iconos/save.ico")), "Guardar XML")
        self.save_action.setEnabled(False) # Deshabilitado al arrancar la aplicación
        self.save_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_action.setStatusTip("Guardar archivo")
        self.save_action.triggered.connect(self.save)

        self.undo_action = QAction(QIcon(resource_path("iconos/deshacer.ico")), "Deshacer")
        self.undo_action.setEnabled(False) # Deshabilitado al arrancar la aplicación
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.setStatusTip("Deshacer cambio")
        self.undo_action.triggered.connect(self.global_undo)

        self.redo_action = QAction(QIcon(resource_path("iconos/rehacer.ico")), "Rehacer")
        self.redo_action.setEnabled(False) # Deshabilitado al arrancar la aplicación
        self.redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.redo_action.setStatusTip("Rehacer cambio")
        self.redo_action.triggered.connect(self.global_redo)

        self.import_theme_action = QAction(QIcon(resource_path("iconos/import.ico")), "Importar Theme Completo...")
        self.import_theme_action.setShortcut("Ctrl+I")
        self.import_theme_action.setStatusTip("Importar un theme existente desde carpeta")
        self.import_theme_action.triggered.connect(self.import_theme_set)

        self.new_theme_action = QAction(QIcon(resource_path("iconos/new_folder.ico")), "Nuevo Theme ...")
        self.new_theme_action.setStatusTip("Crear un theme nuevo")
        self.new_theme_action.triggered.connect(self.new_theme_set)

        self.view_changelog = QAction("Ver Changelog...")
        self.view_changelog.triggered.connect(self.show_changelog_dialog)
        self.update_program = QAction("Buscar actualizaciones...")
        self.update_program.triggered.connect(self.check_for_updates_manual)
        self.about_action = QAction("Acerca de")
        self.about_action.triggered.connect(self.show_about_dialog)

    def create_menu(self):
        menu_archivo = self.menuBar().addMenu("Archivo")
        menu_archivo.addAction(self.new_action)
        menu_archivo.addAction(self.new_theme_action)
        menu_archivo.addAction(self.save_action)
        menu_archivo.addSeparator()
        menu_archivo.addAction(self.import_theme_action)

        menu_editar = self.menuBar().addMenu("Editar")
        menu_editar.addAction(self.undo_action)
        menu_editar.addAction(self.redo_action)

        menu_ver = self.menuBar().addMenu("Ver")
        self.show_rulers_action = QAction("Reglas", self)
        self.show_rulers_action.setCheckable(True)
        self.show_rulers_action.setChecked(True)  # Por defecto visibles
        self.show_rulers_action.triggered.connect(self._toggle_rulers)
        menu_ver.addAction(self.show_rulers_action)

        menu_ayuda = self.menuBar().addMenu("Ayuda")
        menu_ayuda.addAction(self.view_changelog)
        menu_ayuda.addAction(self.update_program)
        menu_ayuda.addAction(self.about_action)

    def new(self):
        self._xml_tab._new_xml()

    def show_changelog_dialog(self):
        """Muestra el changelog completo (sin filtrar por versión)."""
        # Determinar ruta del archivo changelog (empaquetado o desarrollo)

        changelog_file = resource_path("Changelog.md")
        if not os.path.exists(changelog_file):
            QMessageBox.warning(self, "No encontrado", "No se encuentra el archivo de novedades.")
            return

        try:
            with open(changelog_file, "r", encoding="utf-8") as f:
                full_changelog = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer el changelog: {e}")
            return

        # Usar parse_changelog con versión base 0.0.0 para obtener el historial
        clean_text = parse_changelog(full_changelog, "0.0.0")
        if not clean_text:
            clean_text = "No hay contenido de novedades."

        # Diálogo personalizado
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Novedades - egbtheme-creator")
        dlg.resize(650, 500)
        layout = QVBoxLayout(dlg)

        header = QLabel("<h3>Historial de cambios</h3>")
        header.setWordWrap(True)
        layout.addWidget(header)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(clean_text)
        text_edit.setStyleSheet("background: #2d2d2d; color: #f0f0f0; font-family: Arial;font-size: 14px;")
        layout.addWidget(text_edit)

        btn_close = QPushButton("Cerrar")
        btn_close.setStyleSheet(
            "padding: 6px 12px; background: #1565C0; color: white; border: none; border-radius: 4px;")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        dlg.exec()

    def check_for_updates_manual(self):
        """Comprueba manualmente si hay actualizaciones y muestra mensaje si no hay."""
        comprobar_actualizaciones(self, show_if_no_update=True, app_version=APP_VERSION, updater_path=resource_path("updater.exe"))

    def show_about_dialog(self):
        """Muestra el diálogo 'Acerca de' con información del programa (estilo Notepad++)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Acerca de egbtheme-creator")
        dlg.setFixedSize(550, 450)

        layout = QHBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # Icono a la izquierda (más grande)
        icon_label = QLabel()
        icon_path = resource_path("es_theme_editor.ico")
        pixmap = QPixmap(icon_path) if os.path.isfile(icon_path) else QPixmap()
        if not pixmap.isNull():
            pixmap = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pixmap)
        else:
            icon_label.setText("🎨")
            icon_label.setFont(QFont("Segoe UI Emoji", 48))
        layout.addWidget(icon_label, alignment=Qt.AlignTop)

        # Panel derecho con toda la información
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Título
        title = QLabel("<b>egbtheme-creator</b>")
        title.setStyleSheet("font-size: 18px;")
        right_layout.addWidget(title)

        # Subtítulo
        subtitle = QLabel("Batocera/Retrobat Theme Creator")
        subtitle.setStyleSheet("color: #555; font-size: 12px; margin-bottom: 12px;")
        right_layout.addWidget(subtitle)

        # Línea separadora
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(line)

        # Área de texto con la información (versión, autores, copyright, licencia)
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setFrameShape(QFrame.NoFrame)
        info_text.setStyleSheet("background: transparent; color: #fff; font-size: 12px;")
        info_text.setPlainText(
            f"Versión {APP_VERSION}\n\n"
            "Creado por:\n"
            "  • Mabedeep\n"
            "  • Moriggy\n\n"
            "© 2025-2026 egbtheme-creator\n\n"
            "Este programa es software libre: puede redistribuirlo y/o modificarlo "
            "bajo los términos de la Licencia Pública General de GNU, versión 3 "
            "o cualquier versión posterior.\n\n"
            "Este programa se distribuye CON LA ESPERANZA DE QUE SEA ÚTIL, "
            "pero SIN NINGUNA GARANTÍA; sin siquiera la garantía implícita de "
            "COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR.\n\n"
            "Véase <https://www.gnu.org/licenses/> para más detalles."
        )
        info_text.setMinimumHeight(160)
        right_layout.addWidget(info_text)

        # Botón OK
        btn_ok = QPushButton("OK")
        btn_ok.setFixedWidth(80)
        btn_ok.clicked.connect(dlg.accept)
        right_layout.addWidget(btn_ok, alignment=Qt.AlignRight)

        layout.addWidget(right_widget, 1)
        dlg.exec()

    def save(self):
        """Guarda el tema actual (modelo) en theme.xml dentro de la carpeta raíz."""
        if not self._xml_tab.current_root:
            QMessageBox.warning(self, "Sin carpeta raíz", "Importa o crea un tema primero.")
            return
        theme_xml_path = os.path.join(self._xml_tab.current_root, self._xml_tab.current_file_path)

        # Usar el modelo actual, no el contenido del editor (que puede estar desactualizado)
        xml_content = self.theme_model.to_xml()
        try:
            with open(theme_xml_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            self.statusBar().showMessage(f"Archivo guardado en: {theme_xml_path}", 5000)

            # Sincronizar el editor XML inmediatamente después de guardar
            self._xml_tab.editor.blockSignals(True)
            self._xml_tab.editor.setPlainText(xml_content)
            self._xml_tab.editor.blockSignals(False)

            # Después de guardar correctamente:
            self._saved_model_xml = self.theme_model.to_xml()
            self._changes_unsaved = False
            self._update_save_action_state()
            # Marcar el documento XML como limpio
            self._xml_tab.editor.document().setModified(False)
            # Marcar la pila del builder como limpia
            self._builder_tab._undo_stack.setClean()
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e))

    # Importar theme
    def import_theme_set(self):
        """Llama al selector de carpeta del editor XML (mismo comportamiento que el botón)."""
        self._xml_tab.select_theme_folder()

    # Nuevo theme
    def new_theme_set(self):
        """Llama al selector de nuevo theme"""
        # 1. Seleccionar carpeta padre donde se creará el nuevo theme
        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta donde crear el nuevo theme",
            QDir.rootPath()
        )
        if not parent_dir:
            return

        # 2. Bucle para pedir nombre del tema (válido y no existente)
        while True:
            theme_name, ok = QInputDialog.getText(
                self,
                "Nuevo theme",
                "Nombre del theme (se usará como nombre de carpeta):"
            )
            if not ok or not theme_name.strip():
                return  # Cancelado o vacío, salir

            theme_name = theme_name.strip()
            theme_folder = os.path.join(parent_dir, theme_name)

            if os.path.exists(theme_folder):
                QMessageBox.warning(self, "Ya existe",
                                    f"La carpeta '{theme_name}' ya existe. Por favor, elige otro nombre.")
                continue  # Volver a pedir el nombre
            else:
                # Nombre válido y no existe
                break

        try:
            # 4. Crear la estructura básica
            assets_folder, ok = QInputDialog.getText(
                self,
                "Nuevo theme",
                "Nombre de la carpeta donde van a estar los assets (logos, fondos, etc.):"
            )

            messages = create_minimal_theme(theme_folder, assets_folder)

            # Mostrar mensaje/s de error al copiar asset/s si los hay
            if messages:
                QMessageBox.warning(self, "Advertencias al copiar assets", "\n".join(messages))

            # 6. (Opcional) Copiar un fondo por defecto si existe en recursos
            # Aquí podrías copiar un bg.jpg desde tus recursos a assets_folder

            QMessageBox.information(self, "Theme creado", f"Se ha creado el theme en:\n{theme_folder}")

            # 7. Cargar el nuevo tema en el editor
            # Primero, actualizamos la interfaz como cuando se selecciona una carpeta manualmente
            self._xml_tab.current_root = theme_folder
            self._xml_tab.file_model.setRootPath(theme_folder)
            self._xml_tab.tree_view.setRootIndex(self._xml_tab.file_model.index(theme_folder))

            # Cargar modelo desde theme.xml
            theme_xml_path = os.path.join(theme_folder, "theme.xml")
            with open(theme_xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
                new_model = ThemeModel.from_xml(content)
                if new_model:
                    new_model.name = theme_name
                    self.theme_model = new_model
                    self._name_edit.setText(theme_name)
                    # Activar en las pestañas
                    self._xml_tab.theme_model = new_model
                    self._xml_tab.refresh_from_model()
                    self._builder_tab.load_model(new_model)
                    self._preview_tab.theme_model = new_model
                    self._preview_tab.refresh()

            # 8. Actualizar assets: establecer la carpeta de assets recién creada
            self._assets_root = theme_folder
            self._builder_tab.assets_root = theme_folder
            self._builder_tab._canvas.assets_root = theme_folder
            self._builder_tab.theme_assets_browser.set_root(theme_folder)
            self._builder_tab._assets_path_lbl.setText(theme_folder)
            self._builder_tab.assets_root_changed.emit(theme_folder)
            self._preview_tab.set_assets_root(theme_folder)
            self._xml_tab._update_create_folder_button_state()  # Habilitar botón de crear carpeta
            self._update_actions_state() # Habilitar guardado
            self._update_undo_redo_state() # Conectar detección de habilitar "Deshacer" y "Rehacer"

            # Resetear bandera opción "Guardar" y resetear pila de cambios
            self._saved_model_xml = self.theme_model.to_xml()
            self._changes_unsaved = False
            self._update_save_action_state()
            self._builder_tab._undo_stack.clear()
            self._builder_tab._undo_stack.setClean()
            self._editing_system_from_set = None
            self._theme_set_modified = False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear el theme:\n{str(e)}")

    # Opciones del menú Ver
    def _toggle_rulers(self, checked):
        if hasattr(self, '_builder_tab'):
            self._builder_tab.set_rulers_visible(checked)

    # ------------------------------------------------------------------
    def global_undo(self):
        """Deshace según el widget que tenga el foco o la pestaña activa."""
        current_tab = self._tabs.currentWidget()
        if current_tab == self._xml_tab:
            self._xml_tab.editor.undo()
        elif current_tab == self._builder_tab:
            self._builder_tab._undo_stack.undo()

    def global_redo(self):
        """Rehace según el widget que tenga el foco o la pestaña activa."""
        current_tab = self._tabs.currentWidget()
        if current_tab == self._xml_tab:
            self._xml_tab.editor.redo()
        elif current_tab == self._builder_tab:
            self._builder_tab._undo_stack.redo()

    # ------------------------------------------------------------------
    def _colored_separator(self, color="#f3f4f7", width=3, height=20):
        sep = QWidget()
        sep.setFixedSize(width, height)
        sep.setStyleSheet(f"background: {color};")
        return sep


    # ------------------------------------------------------------------
    def _build_toolbar(self):
        tb = self.addToolBar("Principal")
        tb.setStyleSheet("""
            QToolBar {
                spacing: 5px;
                border-top: 1px solid #888888;
                spacing: 5px;
            }
            QToolBar QToolButton {
                border: none;
                background: transparent;
                margin-top: 5px;
                margin-bottom: 5px;
            }
            QToolBar QToolButton:hover {
                background: rgba(0,0,0,0.05);
            }
            QToolBar QToolButton:pressed {
                background: rgba(0,0,0,0.1);
            }
        """)
        tb.setMovable(False)

        tb.addWidget(QLabel("  Theme cargado: "))
        self._name_edit = QLineEdit("")
        self._name_edit.setFixedWidth(160)
        self._name_edit.textChanged.connect(
            lambda t: setattr(self.theme_model, "name", t or ""))
        self._name_edit.setReadOnly(True)
        tb.addWidget(self._name_edit)

        # Añadir acciones (que ya tienen icono definido)
        tb.addWidget(self._colored_separator("#f3f4f7", width=1, height=25))
        tb.addAction(self.new_action)
        tb.addAction(self.new_theme_action)
        tb.addAction(self.save_action)
        tb.addWidget(self._colored_separator("#f3f4f7", width=1, height=25))
        tb.addAction(self.import_theme_action)
        tb.addWidget(self._colored_separator("#f3f4f7", width=1, height=25))
        tb.addAction(self.undo_action)
        tb.addAction(self.redo_action)

        self._sys_lbl = QLabel("")
        self._sys_lbl.setStyleSheet("color:#9cdcfe; padding:0 8px;")
        tb.addWidget(self._sys_lbl)

        """btn_export = QPushButton("  Exportar Tema  ")
        btn_export.setStyleSheet(
            "background:#1565C0; color:white; font-weight:bold; padding:4px 12px;")
        btn_export.clicked.connect(self._export_theme)
        tb.addWidget(btn_export)

        btn_save_to_set = QPushButton("  Guardar en ThemeSet  ")
        btn_save_to_set.setStyleSheet("background:#2E7D32; color:white; font-weight:bold; padding:4px 12px;")
        btn_save_to_set.clicked.connect(self._save_current_to_theme_set)
        tb.addWidget(btn_save_to_set)"""

    def _on_assets_root_changed(self, new_root: str):
        """Propaga la nueva carpeta de assets a todos los componentes."""
        self._assets_root = new_root
        self._preview_tab.set_assets_root(new_root)
        self._set_tab.assets_root = new_root
        self._builder_tab.theme_assets_browser.set_root(new_root)
        self.statusBar().showMessage(f"Carpeta de assets: {new_root}", 6000)

    # ------------------------------------------------------------------
    def _on_tab_changed(self, idx: int):
        tab = self._tabs.widget(idx)

        # Manejar el caso sin theme cargado
        if self.theme_model is None:
            if tab is self._builder_tab:
                # Limpiar el builder
                self._builder_tab.theme_model = None
                self._builder_tab._canvas.set_view(None)
                self._builder_tab._elem_list.refresh(None)
                self._builder_tab._inspector.set_element(None)
                self._builder_tab._view_cb.setText("")
            elif tab is self._preview_tab:
                self._preview_tab.theme_model = None
                self._preview_tab._canvas.set_view(None)
                self._preview_tab._view_cb.setText("")
            elif tab is self._xml_tab:
                self._xml_tab.theme_model = None
                self._xml_tab.refresh_from_model()
            elif tab is self._set_tab:
                # ThemeSet no depende del modelo principal, no hacer nada especial
                pass
            # Actualizar estado de botones
            self._update_undo_redo_state()
            self._update_save_action_state()
            return

        # Hay theme cargado
        if tab is self._builder_tab:
            # No refrescar si ya tiene la vista correcta
            if self._builder_tab._current_view not in self.theme_model.views:
                self._builder_tab.refresh_views()
        elif tab is self._preview_tab:
            self._preview_tab.refresh()
        elif tab is self._xml_tab:
            # Solo actualizar el editor si el contenido externo ha cambiado
            if self._xml_tab.editor.toPlainText() != self.theme_model.to_xml():
                self._xml_tab.refresh_from_model()
        elif tab is self._set_tab:
            if not self._ask_update_theme_set():
                return  # no cambiar de pestaña realmente
            self._set_tab._refresh_list()

        # Actualizar el estado de los botones Undo/Redo y guardar
        self._update_undo_redo_state()
        self._update_save_action_state()

    def _on_model_from_xml(self):
        if self.theme_model is None:
            self._editing_system_from_set = None
            self._theme_set_modified = False
            self._sys_lbl.setText("")
            self._name_edit.setText("")
            self._builder_tab.refresh_views()
            self._update_actions_state()
            self._update_undo_redo_state()
            return

        # Código existente (cuando hay modelo)
        self._editing_system_from_set = None
        self._theme_set_modified = False
        self._sys_lbl.setText("")
        self._name_edit.setText(self.theme_model.name)
        self._builder_tab.refresh_views()
        self._update_actions_state()  # Habilitar guardado
        self._update_undo_redo_state()  # Conectar detección de habilitar "Deshacer" y "Rehacer"

    def _load_system_in_builder(self, model: ThemeModel, sys_name: str):
        """Carga el modelo de un sistema del ThemeSet en el builder."""
        # Guardar el modelo actual
        self.theme_model = model
        self._update_actions_state()  # Habilitar guardado
        self._active_system = sys_name
        self._editing_system_from_set = sys_name
        self._theme_set_modified = False

        # Actualizar barra de título
        self._name_edit.setText(model.name)
        self._sys_lbl.setText(f"[Sistema: {sys_name}]")

        # Sincronizar pestañas
        self._xml_tab.theme_model = model
        self._xml_tab.refresh_from_model()  # 🔁 Actualizar editor XML

        self._builder_tab.load_model(model)  # Ya existe, pero asegura que el builder se actualice
        self._builder_tab.set_system_context(sys_name)

        self._preview_tab.theme_model = model
        self._preview_tab.set_context(sys_name)
        self._preview_tab.refresh()  # 🔁 Refrescar vista previa

        # Resetear pila de cambios
        self._builder_tab._undo_stack.clear()
        self._builder_tab._undo_stack.setClean()

        # Cambiar a la pestaña del Editor Visual
        self._tabs.setCurrentWidget(self._builder_tab)
        self._update_undo_redo_state()  # Conectar detección de habilitar "Deshacer" y "Rehacer"
        self.statusBar().showMessage(
            f"Editando sistema: {sys_name} — usa 'Ctrl+S' o el botón 'Guardar en ThemeSet' para actualizar.", 5000)

        # Resetear bandera opción "Guardar"
        self._saved_model_xml = self.theme_model.to_xml()
        self._changes_unsaved = False
        self._update_save_action_state()

    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    def _ask_update_theme_set(self) -> bool:
        if not self._editing_system_from_set:
            return True

        msg = QMessageBox(self)
        msg.setWindowTitle("Actualizar Theme Set")
        msg.setText(f"El tema del sistema '{self._editing_system_from_set}' ha sido modificado.\n"
                    "¿Deseas actualizarlo en el Theme Set?")
        msg.setIcon(QMessageBox.Question)

        # Crear botones personalizados en español
        btn_yes = msg.addButton("Sí", QMessageBox.YesRole)
        btn_no = msg.addButton("No", QMessageBox.NoRole)
        btn_cancel = msg.addButton("Cancelar", QMessageBox.RejectRole)
        msg.setDefaultButton(btn_yes)

        reply = msg.exec()

        if msg.clickedButton() == btn_yes:
            # Actualizar el modelo en el ThemeSet
            self._theme_set.systems[self._editing_system_from_set] = self.theme_model
            self._theme_set_modified = False
            self._sys_lbl.setStyleSheet("color:#9cdcfe; padding:0 8px;")
            QMessageBox.information(self, "Actualizado",
                                    f"Sistema '{self._editing_system_from_set}' actualizado en el Theme Set.")
            return True
        elif msg.clickedButton() == btn_cancel:
            self._tabs.setCurrentWidget(self._builder_tab)
            return False
        else:  # No -> descartar cambios
            # Restaurar el modelo desde el ThemeSet
            original_model = self._theme_set.systems.get(self._editing_system_from_set)
            if original_model:
                self.theme_model = original_model
                self._update_actions_state()  # Habilitar guardado
                # Actualizar todas las pestañas
                self._xml_tab.theme_model = self.theme_model
                self._xml_tab.refresh_from_model()
                self._builder_tab.load_model(self.theme_model)
                self._preview_tab.theme_model = self.theme_model
                self._preview_tab.refresh()
                self._name_edit.setText(self.theme_model.name)
            # Limpiar estado
            self._editing_system_from_set = None
            self._theme_set_modified = False
            self._sys_lbl.setText("")
            return True  # permitir cambio de pestaña

    # ------------------------------------------------------------------
    def _on_current_model_changed(self):
        """Se llama cuando el modelo cambia por edición visual o XML."""
        if self._editing_system_from_set is not None:
            self._theme_set_modified = True
            self._sys_lbl.setStyleSheet("color:#ffaa00; padding:0 8px;")
        # Actualizar flag de cambios sin guardar
        self._update_unsaved_flag()

    def _has_xml_pending_changes(self) -> bool:
        if not self.theme_model:
            return False
        if self._xml_tab.editor.document().isModified():
            return self._xml_tab.editor.toPlainText() != self.theme_model.to_xml()
        return False

    def _update_unsaved_flag(self):
        if not self.theme_model:
            self._changes_unsaved = False
        else:
            # Cambios en el editor visual: la pila del builder no está limpia
            visual_changes = not self._builder_tab._undo_stack.isClean()
            # Cambios en el editor XML (texto modificado y diferente al modelo)
            xml_modified = self._xml_tab.editor.document().isModified()
            xml_differs = False
            if xml_modified:
                # Solo comparar si realmente hay cambios pendientes (evitar comparar si no es necesario)
                current_xml = self._xml_tab.editor.toPlainText()
                model_xml = self.theme_model.to_xml() if self.theme_model else ""
                xml_differs = (current_xml != model_xml)
            self._changes_unsaved = visual_changes or (xml_modified and xml_differs)
        self._update_save_action_state()

    # ------------------------------------------------------------------
    def _save_current_to_theme_set(self):
        if not self._editing_system_from_set:
            QMessageBox.warning(self, "No activo", "No hay ningún sistema de Theme Set siendo editado actualmente.")
            return
        self._theme_set.systems[self._editing_system_from_set] = self.theme_model
        self._theme_set_modified = False
        self._sys_lbl.setStyleSheet("color:#9cdcfe; padding:0 8px;")
        QMessageBox.information(self, "Guardado",
                                f"Sistema '{self._editing_system_from_set}' guardado en el Theme Set.")
        # Refrescar la lista en la pestaña ThemeSet para que muestre los cambios
        self._set_tab._refresh_list()


#---------------------------------------------------------------------------
# Splashscreen
#---------------------------------------------------------------------------
class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: #2d2d2d; border-radius: 15px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- LOGO ---
        logo_path = resource_path("egbtheme-creator.png")
        logo_pix = QPixmap(logo_path)
        if not logo_pix.isNull():
            logo_pix = logo_pix.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label = QLabel()
            logo_label.setPixmap(logo_pix)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        else:
            title_label = QLabel("egbtheme-creator")
            title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
            title_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(title_label)

        # --- NOMBRE DEL SOFTWARE (siempre visible debajo del logo) ---
        software_name = QLabel("egbtheme-creator")
        software_name.setAlignment(Qt.AlignCenter)
        software_name.setStyleSheet("font-size: 20px; font-weight: bold; color: white; margin-top: 10px;")
        layout.addWidget(software_name)

        # --- VERSIÓN (opcional) ---
        version_label = QLabel(f"Versión {APP_VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("font-size: 12px; color: #aaaaaa; margin-bottom: 15px;")
        layout.addWidget(version_label)

        # --- ESTADO ---
        self.status_label = QLabel("Iniciando...")
        self.status_label.setStyleSheet("color: #cccccc; font-size: 14px; padding: 10px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # --- BARRA DE PROGRESO ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                text-align: center;
                background-color: #1e1e1e;
                color: white;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #1565C0;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.setFixedSize(450, 550)

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        QApplication.processEvents()


# ---------------------------------------------------------------------------
def run_app():
    # Usar nuestra subclase que captura excepciones en eventos Qt
    app = ExceptionAwareApplication(sys.argv)

    # Crear el traductor
    translator = QTranslator(app)

    # Cargar la traducción de Qt para el idioma del sistema
    # Qt ya incluye archivos .qm para muchos idiomas
    translator.load("qt_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath))

    # Instalar el traductor en la aplicación
    app.installTranslator(translator)

    # Instalar hooks globales (importante después de crear app)
    install_global_hooks()

    # Establecer el icono de la aplicación (aparecerá en la barra de tareas y en la ventana)
    icon_path = resource_path("es_theme_editor.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Crear y mostrar el splash
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # Definir los pasos de carga
    steps = [
        (10, "Cargando módulos..."),
        (30, "Inicializando editor XML..."),
        (50, "Preparando editor visual..."),
        (70, "Cargando recursos gráficos..."),
        (90, "Verificando actualizaciones..."),
        (100, "¡Listo! Abriendo aplicación..."),
    ]
    step_index = 0

    def advance_loading():
        nonlocal step_index
        if step_index < len(steps):
            value, msg = steps[step_index]
            splash.update_progress(value, msg)
            step_index += 1
            QTimer.singleShot(400, advance_loading)
        else:
            w = MainWindow()
            splash.close()
            w.show()

            # Activar logger de registro de errores
            logger = setup_logger()
            logger.info("Aplicación iniciada")

            # COMPROBACIÓN AUTOMÁTICA ACTUALIZACIÓN
            QTimer.singleShot(
                1000,  # 2 segundos después de abrir la ventana
                lambda: comprobar_actualizaciones(w, show_if_no_update=False, app_version=APP_VERSION,
                                                  updater_path=resource_path("updater.exe"))
            )

            # Mostrar novedades si corresponde
            logger.debug(f"Llamando a show_changelog_if_new con ruta {resource_path('Changelog.md')}")
            show_changelog_if_new(app_version=APP_VERSION, changelog_path=resource_path("Changelog.md"))

    QTimer.singleShot(100, advance_loading)

    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
