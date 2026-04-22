"""
main.py — Punto de entrada único de EVE ISK Tracker.
"""

from __future__ import annotations
import logging
import logging.handlers
import os
import socket
import threading
import sys
from pathlib import Path

# -- DPI Awareness --
if os.name == 'nt':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# -- Redirección para pythonw (Headless) --
if sys.executable.endswith("pythonw.exe"):
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
    except: pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_DATA = Path(os.environ.get('APPDATA', Path.home())) / 'EVEISKTracker'
APP_DATA.mkdir(parents=True, exist_ok=True)

def setup_logging():
    log_file = APP_DATA / 'eve_isk_tracker.log'
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s — %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except: pass
    return logging.getLogger('eve.main')

SINGLETON_PORT = 47288
class SingletonLock:
    def __init__(self): self._sock = None
    def acquire(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            self._sock.bind(('127.0.0.1', SINGLETON_PORT))
            self._sock.listen(1)
            t = threading.Thread(target=self._listen, daemon=True)
            t.start()
            return True
        except: return False
    def _listen(self):
        while True:
            try:
                conn, _ = self._sock.accept()
                data = conn.recv(64).decode('utf-8', errors='ignore').strip()
                if data == 'FOCUS': _signal_focus()
                conn.close()
            except: break
    def signal_existing(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1.0)
            s.connect(('127.0.0.1', SINGLETON_PORT)); s.send(b'FOCUS\n'); s.close()
        except: pass
    def release(self):
        if self._sock: self._sock.close()

_suite_window_ref = None

def _signal_focus():
    global _suite_window_ref
    if _suite_window_ref:
        try:
            _suite_window_ref.showNormal()
            _suite_window_ref.show()
            _suite_window_ref.raise_()
            _suite_window_ref.activateWindow()
        except: pass

def main():
    lock = SingletonLock()
    if not lock.acquire():
        lock.signal_existing()
        sys.exit(0)

    log = setup_logging()
    log.info("--- INICIANDO EVE iT ELITE ---")

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from controller.app_controller import AppController
    from controller.tray_manager import TrayManager
    from controller.control_window import ControlWindow
    from ui.desktop.main_suite_window import MainSuiteWindow

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
        
        # Cargar retención si existe
        retention = float(s.value("ess_retention", 1.0))
        controller.set_ess_retention(retention)
    
    # 2. Iniciar Tracker si hay dir
    if controller.log_directory:
        skip = s.value("skip_logs", "true") == "true"
        log.info(f"Auto-start: Iniciando tracker (skip={skip})")
        controller.start_tracker(skip_existing=skip)

def _on_sigint(controller, app, lock):
    controller.shutdown(); lock.release(); app.quit()

if __name__ == '__main__':
    main()
