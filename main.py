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
    except Exception:
        pass

from utils.paths import ROOT_DIR, get_resource_path
PROJECT_ROOT = ROOT_DIR

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
    except Exception as e:
        print(f"[WARN] No se pudo inicializar el log en archivo: {e}", file=sys.__stderr__)
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
            except Exception:
                break
    def signal_existing(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1.0)
            s.connect(('127.0.0.1', SINGLETON_PORT)); s.send(b'FOCUS\n'); s.close()
        except Exception:
            pass
    def release(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

_suite_window_ref = None

def _signal_focus():
    global _suite_window_ref
    if _suite_window_ref:
        try:
            _suite_window_ref.showNormal()
            _suite_window_ref.show()
            _suite_window_ref.raise_()
            _suite_window_ref.activateWindow()
        except Exception as e:
            logging.getLogger('eve.main').warning(f"_signal_focus error: {e}")

_audio_refs = []

def _play_sound(name):
    """Reproduce un sonido táctico usando el motor nativo de Windows (MCI)."""
    try:
        import ctypes
        path = PROJECT_ROOT / 'assets' / f"{name}.mp3"
        if not path.exists(): return
        
        # Usamos mciSendString para máxima compatibilidad en Windows sin dependencias de QtMultimedia
        mci = ctypes.windll.winmm.mciSendStringW
        alias = f"sound_{name}"
        
        # Cerrar si ya estaba abierto (por si acaso)
        mci(f"close {alias}", None, 0, 0)
        # Abrir y reproducir
        mci(f'open "{str(path)}" type mpegvideo alias {alias}', None, 0, 0)
        mci(f"play {alias}", None, 0, 0)
        
        # Guardamos en log para diagnóstico
        logging.getLogger('eve.main').info(f"Audio: {name}.mp3 reproducido.")
    except Exception as e:
        logging.getLogger('eve.main').warning(f"Error de audio nativo: {e}")

def main():
    lock = SingletonLock()
    if not lock.acquire():
        lock.signal_existing()
        sys.exit(0)

    log = setup_logging()
    log.info("--- INICIANDO SALVA SUITE ---")

    from PySide6.QtWidgets import QApplication, QSplashScreen
    from PySide6.QtGui import QPixmap, QColor
    from PySide6.QtCore import Qt
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # [NUEVO] Icono de Aplicación y Taskbar ID
    from PySide6.QtGui import QIcon
    icon_path = str(PROJECT_ROOT / 'assets' / 'icon.png')
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

    if os.name == 'nt':
        import ctypes
        myappid = 'SalvaSuite.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # --- Pantalla de Carga (Splash) ---
    splash_pix = QPixmap(str(PROJECT_ROOT / 'assets' / 'fondo_pantalla.png'))
    if splash_pix.isNull():
        splash_pix = QPixmap(600, 400)
        splash_pix.fill(QColor("#000000"))

    if not splash_pix.isNull():
        orig_w = splash_pix.width()
        orig_h = splash_pix.height()
        splash_pix = splash_pix.scaled(
            int(orig_w * 0.3), int(orig_h * 0.3),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.show()
    
    # Sonido de inicio táctico (Reproducción inmediata)
    _play_sound("login")
    
    splash.showMessage("INICIALIZANDO PUENTE DE MANDO...", Qt.AlignBottom | Qt.AlignCenter, QColor("#00c8ff"))
    app.processEvents()

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

    splash.showMessage("CARGANDO TELEMETRÍA...", Qt.AlignBottom | Qt.AlignCenter, QColor("#00c8ff"))
    app.processEvents()

    t_ui = __import__('time').perf_counter()
    log.info(f"STARTUP PHASE name=show_main_window ms=0")
    suite_win.show()
    suite_win.raise_()
    # [NUEVO] Modo Sigilo: Evitar que la propia Suite se vea en las réplicas
    try:
        from overlay.win32_capture import set_window_stealth
        set_window_stealth(int(suite_win.winId()))
        if ctrl_win: set_window_stealth(int(ctrl_win.winId()))
    except Exception as e:
        log.warning(f"No se pudo activar Modo Sigilo: {e}")

    # Finalizar splash
    splash.finish(suite_win)

    # Diferir auto-start para que la UI sea visible antes de hacer I/O pesado
    from PySide6.QtCore import QTimer
    def _deferred_auto_start():
        try:
            _auto_start(controller, tray, suite_win, ctrl_win, log)
        except Exception as e:
            log.error(f"Error en auto-start: {e}")
    QTimer.singleShot(150, _deferred_auto_start)

    import signal
    signal.signal(signal.SIGINT, lambda *_: _on_sigint(controller, app, lock))

    exec_fn = getattr(app, 'exec', None) or app.exec_
    ret = exec_fn()

    # Secuencia de Logoff Optimizada
    if _suite_window_ref:
        _suite_window_ref.showMinimized()
    
    log.info("Cerrando Salva Suite...")
    _play_sound("logoff")
    
    # [NUEVO] Secuencia de apagado ultra-rápida
    try:
        # 1. Notificar apagado global a todos los módulos
        controller.shutdown()
        
        # 2. Reset de sesión del Replicador — conserva perfiles, hotkeys y tamaños de ventana
        repl_cfg = PROJECT_ROOT / 'config' / 'replicator.json'
        if repl_cfg.exists():
            try:
                import json as _json
                _existing = _json.loads(repl_cfg.read_text(encoding='utf-8'))
                _reset = {
                    'global':  _existing.get('global',  {"capture_fps": 30, "current_profile": "Default"}),
                    'regions': _existing.get('regions', {"Default": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3}}),
                    'selected_windows': [],   # Reset intencional: no auto-lanzar réplicas al reiniciar
                    'overlays': {},
                    'region':  _existing.get('region',  {"x": 0, "y": 0, "w": 0.1, "h": 0.1}),
                }
                # Preservar configuraciones de usuario que deben persistir entre sesiones
                for _key in ('layout_profiles', 'active_layout_profile', 'hotkeys', 'sizes', 'overlays'):
                    if _key in _existing:
                        _reset[_key] = _existing[_key]
                repl_cfg.write_text(_json.dumps(_reset, indent=2, ensure_ascii=False), encoding='utf-8')
                _n_profiles = len(_existing.get('layout_profiles', {}))
                log.info(f"Replicador: sesión reseteada, {_n_profiles} perfil(es) preservado(s).")
            except Exception as _e:
                log.warning(f"Error en reset de config replicador: {_e}")
    except Exception as e:
        log.warning(f"Error en secuencia de cierre: {e}")

    lock.release()
    os._exit(ret)

def _auto_start(controller, tray, suite_win, ctrl_win, log):
    import time as _t
    t0 = _t.perf_counter()
    from PySide6.QtCore import QSettings
    s = QSettings("SalvaSuite", "Suite")

    log.info("STARTUP PHASE name=auto_start ms=0")

    # 1. Cargar Log Dir guardado si existe y es válido
    saved_log_dir = s.value("log_dir", "")
    if saved_log_dir and os.path.exists(saved_log_dir):
        log.info(f"STARTUP PHASE name=log_dir_load ms={int((_t.perf_counter()-t0)*1000)}")
        controller.set_log_directory(saved_log_dir)
    else:
        # Auto-detección: buscar directorios de logs de EVE en el sistema
        try:
            t1 = _t.perf_counter()
            from core.log_parser import find_all_log_dirs
            dirs = find_all_log_dirs()
            log.info(f"STARTUP PHASE name=find_log_dirs ms={int((_t.perf_counter()-t1)*1000)}")
            gamelogs = dirs.get('Gamelogs', [])
            if gamelogs:
                detected = str(gamelogs[0])
                log.info(f"Auto-start: Directorio detectado automáticamente: {detected}")
                controller.set_log_directory(detected)
                s.setValue("log_dir", detected)
                if suite_win and getattr(suite_win, 'edit_log_dir', None):
                    suite_win.edit_log_dir.setText(detected)
            else:
                log.info("Auto-start: No se encontraron logs de EVE. Tracker iniciará en modo auto-scan.")
        except Exception as e:
            log.warning(f"Auto-start: Error en auto-detección de logs: {e}")

    # 2. Cargar retención ESS
    retention = float(s.value("ess_retention", 1.0))
    controller.set_ess_retention(retention)

    # 3. skip_existing=True por defecto — evita procesar ISK histórico como sesión nueva.
    # El usuario puede cambiarlo desde la UI. Solo leer "false" si fue guardado explícitamente.
    skip = s.value("skip_logs", "true") == "true"
    log.info(f"STARTUP PHASE name=tracker_start ms={int((_t.perf_counter()-t0)*1000)}")
    controller.start_tracker(skip_existing=skip)

    # 4. Restaurar sesión ESI en background (no bloquear el arranque)
    def _restore_esi():
        try:
            from core.auth_manager import AuthManager
            AuthManager.instance().try_restore_session()
        except Exception as e:
            log.warning(f"Auto-start: Error restaurando sesión ESI: {e}")
    import threading
    threading.Thread(target=_restore_esi, daemon=True, name='ESIRestore').start()

    log.info(f"STARTUP PHASE name=auto_start_done ms={int((_t.perf_counter()-t0)*1000)} skip={skip} log_dir={controller.log_directory!r}")

def _on_sigint(controller, app, lock):
    controller.shutdown(); lock.release(); app.quit()

if __name__ == '__main__':
    main()
