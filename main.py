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

# -- Redirección para pythonw --
if sys.executable.endswith("pythonw.exe"):
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

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
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(('127.0.0.1', SINGLETON_PORT)); s.send(b'FOCUS\n'); s.close()
        except: pass
    def release(self):
        if self._sock: self._sock.close()

_suite_window_ref = None

def _signal_focus():
    global _suite_window_ref
    if _suite_window_ref:
        try:
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
    log.info("--- ARRANQUE ELITE ---")

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from controller.app_controller import AppController
    controller = AppController()

    from controller.tray_manager import TrayManager
    tray = TrayManager(app, controller)

    from ui.desktop.main_suite_window import MainSuiteWindow
    suite_win = MainSuiteWindow(controller)

    global _suite_window_ref
    _suite_window_ref = suite_win
    tray.set_suite_window(suite_win)
    suite_win.set_tray_manager(tray)

    # PRIORIDAD 1: MOSTRAR VENTANA
    suite_win.show()
    suite_win.raise_()
    suite_win.activateWindow()

    # PRIORIDAD 2: AUTO-ARRANQUE
    try:
        from PySide6.QtCore import QSettings
        settings = QSettings("EVE_iT", "Suite")
        log_dir = settings.value("log_dir", "")
        skip_logs = settings.value("skip_logs", "true") == "true"
        controller.start_tracker(log_dir=log_dir, skip_existing=skip_logs)
    except:
        controller.start_tracker()

    exec_fn = getattr(app, 'exec', None) or app.exec_
    ret = exec_fn()

    controller.shutdown()
    lock.release()
    os._exit(ret)

if __name__ == '__main__':
    main()
