"""
main.py — Punto de entrada único de EVE ISK Tracker.

Arquitectura:
  1. Singleton lock (puerto 47288) — evita múltiples instancias
  2. Logging a archivo con rotación
  3. QApplication en hilo principal
  4. AppController en background threads
  5. TrayManager gestiona el system tray y ventanas Qt
  6. Streamlit dashboard como subproceso sin CMD

Empaquetado:
  pyinstaller --onefile --noconsole --name "EVEISKTracker" main.py
"""

from __future__ import annotations
import logging
import logging.handlers
import os
import socket
import threading
import sys
from pathlib import Path

# ── Alta Densidad de Píxeles (DPI Awareness) ──────────────────────────────────
if os.name == 'nt':
    try:
        import ctypes
        # SetProcessDpiAwareness(1) -> PROCESS_SYSTEM_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ── sys.path — garantizar que el proyecto está accesible ──────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Directorio de datos de usuario ────────────────────────────────────────────
APP_DATA = Path(os.environ.get('APPDATA', Path.home())) / 'EVEISKTracker'
APP_DATA.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Logging profesional con rotación
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging():
    log_file = APP_DATA / 'eve_isk_tracker.log'
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s — %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Handler a archivo con rotación (5 MB × 3 archivos)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding='utf-8'
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Handler a consola (solo en modo debug / desarrollo)
    if '--debug' in sys.argv or os.environ.get('EVE_DEBUG'):
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)

    return logging.getLogger('eve.main')


# ══════════════════════════════════════════════════════════════════════════════
# Singleton — evitar múltiples instancias
# ══════════════════════════════════════════════════════════════════════════════

SINGLETON_PORT = 47288   # puerto reservado para el lock singleton

class SingletonLock:
    """
    Mantiene un socket en SINGLETON_PORT como lock de proceso.
    Si el puerto ya está ocupado → otra instancia está corriendo.
    """
    def __init__(self):
        self._sock = None

    def acquire(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            self._sock.bind(('127.0.0.1', SINGLETON_PORT))
            self._sock.listen(1)
            # Hilo que escucha señales de otras instancias
            t = threading.Thread(target=self._listen, daemon=True)
            t.start()
            return True
        except OSError:
            return False

    def _listen(self):
        """Escucha señales de activación de otras instancias."""
        while True:
            try:
                conn, _ = self._sock.accept()
                data = conn.recv(64).decode('utf-8', errors='ignore').strip()
                if data == 'FOCUS':
                    # Señalizar al tray que traiga la app al frente
                    _signal_focus()
                conn.close()
            except Exception:
                break

    def signal_existing(self):
        """Envía señal a la instancia ya activa."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(('127.0.0.1', SINGLETON_PORT))
            s.send(b'FOCUS\n')
            s.close()
        except Exception:
            pass

    def release(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass


_tray_manager_ref = None  # referencia global para señales inter-hilo

_control_window_ref = None

def _signal_focus():
    """Trae la ventana de control al frente cuando otra instancia intenta arrancar."""
    global _tray_manager_ref, _control_window_ref
    if _control_window_ref:
        try:
            _control_window_ref.show()
        except Exception:
            pass
    elif _tray_manager_ref:
        try:
            _tray_manager_ref.show_notification("EVE iT", "Ya está en ejecución.")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Verificar Qt disponible antes de continuar
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_qt() -> bool:
    for pkg in ['PySide6', 'PyQt6', 'PySide2', 'PyQt5']:
        try:
            __import__(pkg)
            return True
        except ImportError:
            continue
    return False


def _install_qt_and_restart():
    """Instala PySide6 y relanza la aplicación."""
    import subprocess
    print("Instalando PySide6...")
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', 'PySide6', '--quiet'])
    if r.returncode == 0:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "No se pudo instalar PySide6.\n\nEjecuta manualmente:\n  pip install PySide6",
                "EVE ISK Tracker — Error", 0x10
            )
        except Exception:
            print("ERROR: pip install PySide6")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():

    # Windows Job Object: mata todos los hijos cuando este proceso muere
    try:
        import ctypes, os as _os
        _pid_file = _os.path.join(_os.path.dirname(__file__), '.main.pid')
        with open(_pid_file, 'w') as _pf: _pf.write(str(_os.getpid()))
        kernel32 = ctypes.windll.kernel32
        _job = kernel32.CreateJobObjectW(None, None)
        _limit = ctypes.c_uint(0x2000)
        kernel32.SetInformationJobObject(_job, 9, ctypes.byref(_limit), ctypes.sizeof(_limit))
        kernel32.AssignProcessToJobObject(_job, kernel32.GetCurrentProcess())
    except Exception:
        pass

    log = setup_logging()
    log.info("=" * 60)
    log.info("EVE iT — Iniciando")
    log.info(f"Python: {sys.version}")
    log.info(f"Directorio: {PROJECT_ROOT}")
    log.info("=" * 60)

    # ── Singleton ─────────────────────────────────────────────────────────────
    lock = SingletonLock()
    if not lock.acquire():
        log.warning("Otra instancia ya está ejecutándose — enviando señal de foco")
        lock.signal_existing()
        sys.exit(0)

    # ── Verificar Qt ──────────────────────────────────────────────────────────
    if not _ensure_qt():
        log.warning("Qt no disponible — intentando instalar PySide6")
        _install_qt_and_restart()
        return  # no llegamos aquí si el install fue OK

    # ── Importar Qt ───────────────────────────────────────────────────────────
    import importlib
    _W = _C = _G = None
    for b in [
        ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
        ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
        ('PySide2', 'PySide2.QtWidgets', 'PySide2.QtCore', 'PySide2.QtGui'),
        ('PyQt5',   'PyQt5.QtWidgets',   'PyQt5.QtCore',   'PyQt5.QtGui'),
    ]:
        try:
            _W = importlib.import_module(b[1])
            _C = importlib.import_module(b[2])
            _G = importlib.import_module(b[3])
            log.info(f"Qt backend: {b[0]}")
            break
        except ImportError:
            continue

    # ── QApplication ──────────────────────────────────────────────────────────
    # setQuitOnLastWindowClosed=False para que la app siga en tray
    app = _W.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("EVE iT")
    app.setApplicationVersion("2.0")

    # Verificar que el sistema soporta system tray
    if not _W.QSystemTrayIcon.isSystemTrayAvailable():
        log.error("System tray no disponible en este sistema")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "El system tray no está disponible en este sistema.",
                "EVE ISK Tracker — Error", 0x10
            )
        except Exception:
            pass
        lock.release()
        sys.exit(1)

    # ── Controlador ───────────────────────────────────────────────────────────
    from controller.app_controller import AppController
    controller = AppController()

    # ── Tray Manager ──────────────────────────────────────────────────────────
    from controller.tray_manager import TrayManager
    global _tray_manager_ref
    tray = TrayManager(app, controller)
    _tray_manager_ref = tray

    # ── Ventana de control principal ─────────────────────────────────────────
    from controller.control_window import ControlWindow, save_icon_png
    ctrl_win = ControlWindow(app, controller, tray)

    # Guardar icon.png para que el tray lo use
    icon_path = PROJECT_ROOT / 'icon.png'
    if not icon_path.exists():
        try:
            save_icon_png(_G, str(icon_path))
        except Exception:
            pass

    # Pasar referencia al tray para toggle desde menú
    tray.set_control_window(ctrl_win)

    # Señal de focus → mostrar la ventana de control
    global _control_window_ref
    _control_window_ref = ctrl_win

    # ── Arranque automático del tracker ───────────────────────────────────────
    QTimer = _C.QTimer
    QTimer.singleShot(500, lambda: _auto_start(controller, tray, ctrl_win, log))

    # ── Manejo limpio de Ctrl+C en desarrollo ─────────────────────────────────
    import signal
    signal.signal(signal.SIGINT, lambda *_: _on_sigint(controller, app, lock))

    # ── Event loop Qt ─────────────────────────────────────────────────────────
    log.info("Event loop Qt iniciado")
    exec_fn = getattr(app, 'exec', None) or app.exec_
    ret = exec_fn()

    # ── Shutdown ──────────────────────────────────────────────────────────────
    try:
        if tray: 
            tray.hide()
            tray.shutdown()
    except Exception: pass
    
    # Nuclear Option: Iniciar un timer de seguridad para forzar el cierre si se queda colgado
    def _nuclear_exit():
        import time, os as _os
        time.sleep(3) # 3 segundos de gracia (suficiente para flush de logs)
        log.warning("NUCLEAR EXIT: Forzando os._exit")
        _os._exit(1)
    
    t_kill = threading.Thread(target=_nuclear_exit, daemon=True)
    t_kill.start()

    controller.shutdown()
    lock.release()
    log.info(f"EVE iT cerrado (código {ret})")

    # Forzar cierre completo de todos los procesos hijos residuales (Streamlit, etc.)
    try:
        import psutil, os as _os
        me = psutil.Process(_os.getpid())
        for ch in me.children(recursive=True):
            try: ch.kill()
            except: pass
    except Exception:
        # Fallback si no hay psutil: usar taskkill de Windows para matar hijos
        try:
            import subprocess
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(os.getpid())], capture_output=True)
        except: pass

    import os as _os
    _os._exit(ret)


def _auto_start(controller, tray, ctrl_win, log):
    """Acciones automáticas al arrancar."""
    log.info("Auto-start: iniciando tracker de logs")
    controller.start_tracker()
    # Mostrar la ventana de control al arrancar
    ctrl_win.show()


def _on_sigint(controller, app, lock):
    """Ctrl+C en modo desarrollo."""
    controller.shutdown()
    lock.release()
    app.quit()


if __name__ == '__main__':
    main()
