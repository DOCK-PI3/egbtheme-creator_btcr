import os
import re
import sys
import requests
import subprocess
import tempfile

from PySide6.QtCore import QThread, QObject, Signal, QStandardPaths, Qt

from PySide6.QtWidgets import QMessageBox, QProgressDialog, QApplication, QDialog, QVBoxLayout, QLabel, QPlainTextEdit, \
    QPushButton

from packaging import version

REPO = "DOCK-PI3/egbtheme-creator_btcr"

def get_latest_release():
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    version_remote = data["tag_name"].lstrip("v")

    # buscamos el exe correcto
    for asset in data["assets"]:
        if asset["name"].lower().endswith(".exe"):
            return version_remote, asset["browser_download_url"]

    raise RuntimeError("No se encontró ningún .exe en la release")


def hay_nueva_version(local, remoto):
    return version.parse(remoto) > version.parse(local)


#---------------------------------------------------------
# Comprobar si hay actualización de la aplicación
#---------------------------------------------------------
def comprobar_actualizaciones(parent=None, show_if_no_update=False, app_version="", updater_path=None):
    try:
        version_remota, url = get_latest_release()
        if not hay_nueva_version(app_version, version_remota):
            if show_if_no_update:
                QMessageBox.information(
                    parent,
                    "Sin actualizaciones",
                    f"Ya tienes la última versión ({app_version})."
                )
            return

        resp = QMessageBox.question(
            parent,
            "Actualización disponible",
            f"Hay una nueva versión disponible:\n\n"
            f"Actual: {app_version}\n"
            f"Nueva: {version_remota}\n\n"
            f"¿Quieres actualizar ahora?",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        # Archivo temporal
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
        temp_file.close()
        nuevo_exe = temp_file.name

        # Diálogo de progreso
        progress_dlg = QProgressDialog("Descargando actualización... Al finalizar la descarga, se cerrará el programa. "
                                       "\nTras la actualización, se volverá a ejecutar", "Cancelar", 0, 100, parent)
        progress_dlg.setWindowTitle("Actualizando")
        progress_dlg.setModal(True)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setAutoClose(False)
        progress_dlg.setAutoReset(False)
        progress_dlg.setMinimumSize(450, 180)
        progress_dlg.setStyleSheet("""
                    QProgressBar {
                        height: 28px;
                        border: 1px solid #555;
                        border-radius: 6px;
                        background-color: #1e1e1e;
                        text-align: center;
                        color: white;
                        font-weight: bold;
                    }
                    QProgressBar::chunk {
                        background-color: #1565C0;
                        border-radius: 5px;
                    }
                    QPushButton {
                        background-color: #d32f2f;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                    }
                    QPushButton:hover {
                        background-color: #f44336;
                    }
                """)

        # Hilo y worker
        thread = QThread()
        worker = DownloadWorker(url, nuevo_exe)
        worker.moveToThread(thread)

        # Conectar señales
        worker.progress.connect(progress_dlg.setValue)
        worker.finished.connect(progress_dlg.accept)
        worker.error.connect(progress_dlg.reject)
        thread.started.connect(worker.run)
        progress_dlg.canceled.connect(worker.cancel)
        progress_dlg.canceled.connect(thread.quit)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(progress_dlg.deleteLater)  # Eliminar diálogo al terminar

        thread.start()
        result = progress_dlg.exec()

        # Forzar la limpieza del hilo si aún está corriendo
        if thread.isRunning():
            thread.quit()
            thread.wait(1000)

        # Pequeña pausa para que la GUI se actualice
        QApplication.processEvents()

        if result == QDialog.Accepted:
            exe_actual = sys.executable
            updater = updater_path
            if not os.path.isfile(updater):
                QMessageBox.critical(parent, "Error", "No se encuentra updater.exe")
                return
            subprocess.Popen([updater, exe_actual, nuevo_exe],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            # Salir sin esperar
            QApplication.quit()  # En lugar de sys.exit(0), para una salida más limpia
            sys.exit(0)
        else:
            if os.path.exists(nuevo_exe):
                os.remove(nuevo_exe)

    except Exception as e:
        QMessageBox.warning(parent, "Error de actualización", "No se ha podido conectar con el servidor: \n\n" + str(e))


class DownloadWorker(QObject):
    progress = Signal(int)       # porcentaje 0-100
    finished = Signal(str)       # ruta del archivo descargado
    error = Signal(str)          # mensaje de error

    def __init__(self, url, dest_path):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            with open(self.dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._is_cancelled:
                        f.close()
                        os.remove(self.dest_path)
                        self.error.emit("Descarga cancelada")
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            percent = int(downloaded * 100 / total_size)
                            self.progress.emit(percent)
            self.finished.emit(self.dest_path)  # Siempre al final
        except Exception as e:
            self.error.emit(str(e))


#------------------------------------------------------------------------
# Mostrar changelog.md tras actualización del programa
#------------------------------------------------------------------------
def get_config_dir():
    """Devuelve el directorio de configuración de la aplicación (para guardar last_version.txt)."""
    if getattr(sys, 'frozen', False):
        # Entorno empaquetado: usar directorio de configuración del usuario
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        if not config_dir:
            config_dir = os.path.join(os.path.expanduser("~"), ".config", "egbtheme-creator")
    else:
        # Desarrollo: junto al script
        config_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def clean_changelog_block(raw_block: str) -> str:
    """
    Elimina los marcadores de bloque de código (```, ```bash, etc.)
    y convierte líneas que empiezan con '-' o '*' en viñetas '•'.
    """
    lines = raw_block.splitlines()
    cleaned = []
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        # Detectar inicio/fin de bloque de código
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            # Convertir guiones o asteriscos en viñetas
            if stripped.startswith('-') or stripped.startswith('*'):
                bullet_line = '• ' + stripped[1:].lstrip()
                cleaned.append(bullet_line)
            elif stripped.strip():
                cleaned.append(line)  # Conservar otras líneas (ej. texto normal)
        else:
            # Fuera de bloque de código, conservar tal cual (cabeceras, etc.)
            cleaned.append(line)
    return '\n'.join(cleaned)


def parse_changelog(changelog_text: str, from_version: str) -> str:
    """
    Parsea el changelog en formato markdown y devuelve el texto de las versiones
    superiores a from_version, limpiando los bloques de código.
    """
    lines = changelog_text.splitlines()
    result = []
    current_version = None
    current_content = []
    in_version_block = False
    header_line = ""

    # Patrón para detectar cabeceras de versión: ### v1.2.3 o ## [1.2.3]
    version_pattern = re.compile(r'^#{2,3}\s+[vV]?(\d+\.\d+\.\d+([-\w]*))')

    for line in lines:
        stripped = line.strip()
        m = version_pattern.match(stripped)
        if m:
            # Si ya estábamos acumulando una versión anterior, procesarla
            if current_version is not None and current_content:
                if version.parse(current_version) > version.parse(from_version):
                    cleaned = clean_changelog_block(''.join(current_content))
                    if cleaned:
                        result.append(header_line)   # Cabecera de la versión
                        result.append(cleaned)
            # Iniciar nueva versión
            current_version = m.group(1)
            header_line = line   # Guardar la línea original (con formato)
            current_content = []
            in_version_block = True
            continue

        if in_version_block:
            # Si encontramos otra cabecera de nivel 2 o 3 y no es de versión, terminar bloque
            if stripped.startswith('#') and not version_pattern.match(stripped):
                in_version_block = False
                continue
            current_content.append(line + '\n')

    # Último bloque
    if current_version is not None and current_content:
        if version.parse(current_version) > version.parse(from_version):
            cleaned = clean_changelog_block(''.join(current_content))
            if cleaned:
                result.append(header_line)
                result.append(cleaned)

    return '\n'.join(result).strip()


def show_changelog_if_new(app_version="", changelog_path=None):
    """Lee el changelog desde archivo empaquetado y muestra novedades si la versión actual es más reciente que la última mostrada."""
    changelog_file = changelog_path
    last_version_file = os.path.join(get_config_dir(), "last_version.txt")

    current_version = app_version

    # Leer última versión mostrada
    if os.path.exists(last_version_file):
        with open(last_version_file, "r", encoding="utf-8") as f:
            last_version = f.read().strip()
    else:
        last_version = "0.0.0"

    # Solo mostrar si la versión actual es mayor y el archivo changelog existe
    if version.parse(current_version) > version.parse(last_version) and os.path.exists(changelog_file):
        try:
            with open(changelog_file, "r", encoding="utf-8") as f:
                full_changelog = f.read()

            changelog_text = parse_changelog(full_changelog, last_version)
            if not changelog_text:
                changelog_text = "No se encontraron novedades para esta versión."
        except Exception as e:
            changelog_text = f"Error al leer el changelog: {e}"

        # Crear diálogo personalizado
        dlg = QDialog()
        dlg.setWindowTitle(f"Novedades - egbtheme-creator")
        dlg.resize(650, 500)
        layout = QVBoxLayout(dlg)

        header = QLabel(f"<h3>¡Se ha actualizado a la versión {current_version}!</h3>")
        header.setWordWrap(True)
        layout.addWidget(header)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(changelog_text)
        text_edit.setStyleSheet("""
            background: #2d2d2d;
            color: #f0f0f0;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 11px;
        """)
        layout.addWidget(text_edit)

        btn_close = QPushButton("Cerrar")
        btn_close.setStyleSheet(
            "padding: 6px 12px; background: #1565C0; color: white; border: none; border-radius: 4px;")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        dlg.exec()

        # Guardar la versión actual para no volver a mostrar
        with open(last_version_file, "w", encoding="utf-8") as f:
            f.write(current_version)
