import os
import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from controller.app_controller import AppController
from controller.tray_manager import TrayManager
from controller.control_window import ControlWindow
from ui.desktop.main_suite_window import MainSuiteWindow

def setup_logging():
    log_dir = Path(os.environ.get('APPDATA', '')) / 'EVEISKTracker'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'eve_isk_tracker.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('eve')

def main():
    log = setup_logging()
    log.info("--- INICIO DE APLICACIÓN (MODO ESTÁNDAR) ---")
    
    # Singleton check simple
    import socket
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(('127.0.0.1', 47288))
    except:
        log.warning("Ya existe una instancia de EVE iT ejecutándose.")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = AppController()
    tray = TrayManager(app, controller)
    ctrl_win = ControlWindow(app, controller, tray)
    suite_win = MainSuiteWindow(controller)

    # Registro de referencias
    global _suite_window_ref
    _suite_window_ref = suite_win
    
    tray.set_control_window(ctrl_win)
    tray.set_suite_window(suite_win)
    suite_win.set_tray_manager(tray)

    log.info("Desplegando Suite Principal...")
    suite_win.show()
    suite_win.raise_()
    suite_win.activateWindow()

    # Auto-start con persistencia completa
    try:
        _auto_start(controller, tray, suite_win, ctrl_win, log)
    except Exception as e:
        log.error(f"Error en auto-start: {e}")

    import signal
    signal.signal(signal.SIGINT, lambda *_: _on_sigint(controller, app, lock))

    exec_fn = getattr(app, 'exec', None) or app.exec_
    ret = exec_fn()

    controller.shutdown()
    lock.release()
    os._exit(ret)

def _auto_start(controller, tray, suite_win, ctrl_win, log):
    from PySide6.QtCore import QSettings
    s = QSettings("EVE_iT", "Suite")
    
    # 1. Cargar Log Dir si existe
    saved_log_dir = s.value("log_dir", "")
    if saved_log_dir and os.path.exists(saved_log_dir):
        log.info(f"Auto-start: Configurando log_dir: {saved_log_dir}")
        controller.set_log_directory(saved_log_dir)
    
    # 2. Iniciar Tracker si hay dir
    if controller.log_directory:
        skip = s.value("skip_logs", "true") == "true"
        log.info(f"Auto-start: Iniciando tracker (skip={skip})")
        controller.start_tracker(skip_existing=skip)

def _on_sigint(controller, app, lock):
    logging.info("SIGINT recibido. Cerrando...")
    controller.shutdown()
    lock.release()
    app.quit()

if __name__ == "__main__":
    main()
