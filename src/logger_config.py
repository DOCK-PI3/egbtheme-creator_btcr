import logging
import os
import sys
import traceback
import threading

from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from PySide6.QtWidgets import QMessageBox, QApplication


def setup_logger(log_dir=None):
    if log_dir is None:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, "logs")

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.txt")  # base, pero con rotación diaria se añadirá fecha

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Rotación diaria, conserva 7 días de backup
        handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8")
        handler.suffix = "_%Y-%m-%d"  # para que el archivo rotado tenga la fecha
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        # También consola si quieres
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)

    logger.info(f"=== Inicio de sesión {datetime.now()} ===")
    return logger

# ------------------------------------------------------------
# MANEJADOR GLOBAL DE EXCEPCIONES
# ------------------------------------------------------------
def global_exception_handler(exc_type, exc_value, exc_tb):
    """
    Manejador para excepciones no capturadas en el hilo principal.
    """
    # Evitar manejar KeyboardInterrupt (cierre normal)
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    # Formatear el traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    tb_text = ''.join(tb_lines)

    # Obtener el logger (si ya existe, si no, crear uno básico)
    logger = logging.getLogger()
    if not logger.handlers:
        # Configuración mínima por si el logger no se había inicializado
        setup_logger()
        logger = logging.getLogger()

    logger.critical("🔴 EXCEPCIÓN NO CAPTURADA:\n%s", tb_text)

    # Opcional: mostrar un diálogo al usuario (solo si la aplicación Qt está corriendo)
    try:
        # Intentar obtener la aplicación activa
        app = QApplication.instance()
        if app and app.activeWindow():
            QMessageBox.critical(
                app.activeWindow(),
                "Error inesperado",
                f"Ha ocurrido un error interno.\n\n"
                f"Por favor, reporta este problema enviando el archivo de log (carpeta 'logs').\n\n"
                f"Detalles:\n{tb_text.splitlines()[-1]}"
            )
    except Exception:
        pass  # Si falla mostrar el diálogo, al menos queda en el log


def thread_exception_handler(args):
    """
    Manejador para excepciones no capturadas en hilos (Python 3.8+).
    """
    global_exception_handler(args.exc_type, args.exc_value, args.exc_tb)


class ExceptionAwareApplication(QApplication):
    """
    Subclase de QApplication que captura excepciones lanzadas en eventos (slots, etc.)
    """
    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception as e:
            # Capturar cualquier excepción que ocurra durante el procesamiento de eventos
            exc_type, exc_value, exc_tb = sys.exc_info()
            global_exception_handler(exc_type, exc_value, exc_tb)
            # Opcional: retornar False para indicar que el evento no fue manejado
            return False


def install_global_hooks():
    """
    Instala los hooks globales para capturar todas las excepciones no controladas.
    Debe llamarse justo después de crear la QApplication (o antes, pero mejor después).
    """
    # Hook para el hilo principal
    sys.excepthook = global_exception_handler

    # Hook para hilos (Python 3.8+)
    if hasattr(threading, 'excepthook'):
        threading.excepthook = thread_exception_handler