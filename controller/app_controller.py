"""
app_controller.py — Controlador central de EVE ISK Tracker.

Gestiona el ciclo de vida de todos los módulos:
  - Tracker de logs (file_watcher + session_tracker)
  - Servidor de datos del overlay (OverlayServer)
  - Proceso del dashboard Streamlit (subproceso sin CMD)
  - Overlay HUD (ventana Qt)
  - Replicador de ventanas (ventana Qt)

Es el único punto de verdad sobre el estado de la aplicación.
Thread-safe. No bloquea el hilo principal Qt.
"""

from __future__ import annotations
import logging
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

logger = logging.getLogger('eve.controller')

# Directorio raíz del proyecto (donde vive main.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AppState:
    """Estado global observable de la aplicación."""
    def __init__(self):
        self.tracker_running    = False
        self.dashboard_running  = False
        self.overlay_active     = False
        self.replicator_active  = False
        self.dashboard_url      = 'http://localhost:8501'
        self.language           = 'es'
        self._lock              = threading.Lock()
        self._listeners: list   = []

    def subscribe(self, fn):
        """Registrar callback que se llama cuando cambia el estado."""
        self._listeners.append(fn)

    def _notify(self):
        for fn in self._listeners:
            try:
                fn(self)
            except Exception as e:
                logger.warning(f"State listener error: {e}")

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        self._notify()


class AppController:
    """
    Controlador principal. Se instancia una vez y vive durante toda
    la ejecución de la aplicación.

    Diseño:
      - tracker_thread: lee logs en background
      - dashboard_proc: subproceso Streamlit sin CMD
      - overlay_server: socket que distribuye datos al overlay HUD Qt
      - overlay_window: ventana Qt del HUD (gestionada por TrayManager)
      - replicator:     wizard + overlays de replicación (gestionado por TrayManager)
    """

    def __init__(self):
        self.state           = AppState()
        self._tracker        = None        # MultiAccountTracker
        self._watcher        = None        # EVELogWatcher
        self._overlay_server = None        # OverlayServer
        self._dashboard_proc: Optional[subprocess.Popen] = None
        self._tracker_thread: Optional[threading.Thread] = None
        self._data_push_timer: Optional[threading.Timer]  = None
        self._lock           = threading.Lock()

        # Referencia a la ventana Qt del overlay (gestionada externamente)
        self.overlay_window  = None
        # Referencia al manager del replicador (gestionado externamente)
        self.replicator_mgr  = None

    # ══════════════════════════════════════════════════════════════════════════
    # Arranque y parada del tracker de logs
    # ══════════════════════════════════════════════════════════════════════════

    def start_tracker(self, log_dir: str = '', skip_existing: bool = True,
                      ess_retention: float = 1.0):
        """Inicia el tracker de logs y el servidor overlay en background."""
        with self._lock:
            if self.state.tracker_running:
                logger.info("Tracker ya activo — reiniciando")
                self._stop_tracker_internal()

            logger.info("Iniciando tracker de logs...")
            try:
                from core.session_tracker import MultiAccountTracker
                from core.file_watcher    import EVELogWatcher
                from overlay.overlay_server import OverlayServer

                self._tracker = MultiAccountTracker()
                self._watcher = EVELogWatcher(
                    tracker        = self._tracker,
                    log_dir        = log_dir or None,
                    poll_interval  = 1.0,
                    ess_retention  = ess_retention,
                    skip_existing  = skip_existing,
                    active_window_minutes = 480,
                )
                self._watcher.start()

                # Servidor overlay (socket TCP que distribuye datos al HUD)
                # Ahora acepta comandos del HUD (Pausa/Reset)
                self._overlay_server = OverlayServer(command_callback=self._on_overlay_command)
                self._overlay_server.start()

                self.state.update(tracker_running=True)
                logger.info("Tracker iniciado correctamente")

                # Iniciar loop de push de datos
                self._schedule_data_push()

            except Exception as e:
                logger.error(f"Error iniciando tracker: {e}", exc_info=True)

    def _on_overlay_command(self, cmd: str):
        """Maneja comandos recibidos desde el socket del HUD."""
        logger.info(f"Comando de overlay recibido: {cmd}")
        if cmd == 'PAUSE':
            if not self.state.tracker_running: return # no hacer nada si ya está parado
            # Obtener el estado de pausa actual para alternar
            # NOTA: En este sistema, Play/Pause se maneja via estado 'paused' interno
            # Si el controlador no tiene toggle_pause, usamos la lógica de control_window
            pass # (se implementará via señales si es necesario)
        elif cmd == 'TOGGLE_PAUSE':
            # Llamar a un futuro método toggle_pause o implementarlo aquí
            from controller.control_window import _control_window_ref
            if _control_window_ref:
                # Usar QTimer para invocar en el hilo principal si es necesario, 
                # pero los métodos del controlador suelen ser thread-safe
                _control_window_ref._on_playpause()
        elif cmd == 'RESET':
            from controller.control_window import _control_window_ref
            if _control_window_ref:
                _control_window_ref._on_reset()

    def stop_tracker(self):
        self.stop_translator()
        with self._lock:
            self._stop_tracker_internal()

    def restart_tracker(self):
        """Reinicia el tracker limpiamente sin cerrar la app."""
        logger.info("Reiniciando tracker...")
        with self._lock:
            self._stop_tracker_internal()
        time.sleep(0.5)
        self.start_tracker()

    def _stop_tracker_internal(self):
        """Llama sin lock externo."""
        if self._data_push_timer:
            self._data_push_timer.cancel()
            self._data_push_timer = None
        if self._watcher:
            try:
                self._watcher.stop()
            except Exception:
                pass
            self._watcher = None
        if self._overlay_server:
            try:
                self._overlay_server.stop()
            except Exception:
                pass
            self._overlay_server = None
        self._tracker = None
        self.state.update(tracker_running=False)
        logger.info("Tracker detenido")

    # ══════════════════════════════════════════════════════════════════════════
    # Push de datos al overlay HUD
    # ══════════════════════════════════════════════════════════════════════════

    def _schedule_data_push(self):
        """Programa el siguiente push de datos (cada 1.5s)."""
        self._push_overlay_data()
        if self.state.tracker_running:
            self._data_push_timer = threading.Timer(1.5, self._schedule_data_push)
            self._data_push_timer.daemon = True
            self._data_push_timer.start()

    def _push_overlay_data(self):
        """Envía datos del tracker al overlay server y al overlay HUD Qt."""
        if not self._tracker or not self._overlay_server:
            return
        try:
            from overlay.overlay_server import build_overlay_payload
            payload = build_overlay_payload(self._tracker)
            self._overlay_server.push(payload)

            # Si el overlay HUD Qt está activo, actualizar directamente via Signal
            if self.overlay_window and self.state.overlay_active:
                try:
                    self.overlay_window._on_data(payload)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Error en data push: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Dashboard Streamlit
    # ══════════════════════════════════════════════════════════════════════════

    def start_dashboard(self, port: int = 8501):
        """Lanza el servidor Streamlit en background sin CMD visible."""
        with self._lock:
            if self._dashboard_proc and self._dashboard_proc.poll() is None:
                logger.info("Dashboard ya activo")
                self.open_dashboard_browser()
                return

        app_script = PROJECT_ROOT / 'app.py'
        if not app_script.exists():
            logger.error(f"app.py no encontrado: {app_script}")
            return

        logger.info(f"Iniciando dashboard en puerto {port}...")
        cmd = [
            sys.executable, '-m', 'streamlit', 'run',
            str(app_script),
            '--server.port', str(port),
            '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false',
            '--server.fileWatcherType', 'none',
        ]

        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        try:
            self._dashboard_proc = subprocess.Popen(
                cmd,
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(PROJECT_ROOT),
            )
            self.state.update(
                dashboard_running=True,
                dashboard_url=f'http://localhost:{port}'
            )
            # Abrir navegador tras 2s (tiempo para que Streamlit arranque)
            threading.Timer(2.0, self.open_dashboard_browser).start()
            logger.info(f"Dashboard lanzado (PID {self._dashboard_proc.pid})")
        except Exception as e:
            logger.error(f"Error lanzando dashboard: {e}", exc_info=True)

    def start_translator(self):
        """Lanzar el overlay traductor de chat EVE."""
        try:
            if getattr(self, '_translator_overlay', None) and self._translator_overlay.isVisible():
                self._translator_overlay.raise_()
                return
            from translator.translator_config import TranslatorConfig
            from translator.chat_overlay import ChatOverlay
            cfg = TranslatorConfig.load()
            self._translator_overlay = ChatOverlay(cfg, controller=self)
            self._translator_overlay.start()
            self._translator_overlay.show()
        except Exception as e:
            import logging
            logging.getLogger('eve').error(f"start_translator error: {e}")

    def stop_translator(self):
        try:
            if getattr(self, '_translator_overlay', None):
                self._translator_overlay.stop()
                self._translator_overlay.close()
                self._translator_overlay = None
        except Exception: pass


    def stop_dashboard(self):
        with self._lock:
            if self._dashboard_proc:
                try:
                    self._dashboard_proc.terminate()
                    self._dashboard_proc.wait(timeout=5)
                except Exception:
                    try:
                        self._dashboard_proc.kill()
                    except Exception:
                        pass
                self._dashboard_proc = None
                self.state.update(dashboard_running=False)
                logger.info("Dashboard detenido")

    def open_dashboard_browser(self):
        """Abre el dashboard en el navegador predeterminado."""
        url = self.state.dashboard_url
        try:
            webbrowser.open(url)
            logger.info(f"Navegador abierto: {url}")
        except Exception as e:
            logger.warning(f"No se pudo abrir el navegador: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Overlay HUD
    # ══════════════════════════════════════════════════════════════════════════

    def toggle_overlay(self):
        """Activa o desactiva el overlay HUD."""
        if self.state.overlay_active:
            self.hide_overlay()
        else:
            self.show_overlay()

    def show_overlay(self):
        if self.overlay_window:
            try:
                self.overlay_window.show()
                self.overlay_window.bring_to_front()
                self.state.update(overlay_active=True)
                logger.info("Overlay HUD activado")
            except Exception as e:
                logger.error(f"Error mostrando overlay: {e}")

    def hide_overlay(self):
        if self.overlay_window:
            try:
                self.overlay_window.hide()
                self.state.update(overlay_active=False)
                logger.info("Overlay HUD ocultado")
            except Exception as e:
                logger.error(f"Error ocultando overlay: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Replicador
    # ══════════════════════════════════════════════════════════════════════════

    def toggle_replicator(self):
        if self.state.replicator_active:
            self.stop_replicator()
        else:
            self.start_replicator()

    def start_replicator(self):
        """Señal para que TrayManager lance el wizard del replicador."""
        # La ventana Qt del replicador se gestiona en TrayManager
        # porque requiere el hilo Qt principal
        self.state.update(replicator_active=True)
        logger.info("Replicador activado")

    def stop_replicator(self):
        if self.replicator_mgr:
            try:
                self.replicator_mgr.close_all()
            except Exception:
                pass
        self.state.update(replicator_active=False)
        logger.info("Replicador detenido")

    # ══════════════════════════════════════════════════════════════════════════
    # Shutdown completo
    # ══════════════════════════════════════════════════════════════════════════

    def shutdown(self):
        """Cierre limpio de todos los módulos."""
        logger.info("Apagando EVE ISK Tracker...")
        
        # 1. Detener servicios de datos y threads
        with self._lock:
            self._stop_tracker_internal()
        
        # 2. Cerrar ventanas y módulos de UI
        self.stop_translator()
        self.hide_overlay()
        self.stop_replicator()
        
        # Ocultar icono de bandeja inmediatamente para evitar "iconos fantasma"
        if hasattr(self, '_tray') and self._tray:
            try: self._tray.hide()
            except: pass
        
        # 3. Detener dashboard (Streamlit)
        self.stop_dashboard()
        # Matar todos los procesos python relacionados con la app
        try:
            import psutil, os, subprocess
            my_pid = os.getpid()
            keywords = ['server.py', 'server_launcher.py', 'main.py']
            for p in psutil.process_iter(['pid','name','cmdline']):
                try:
                    if p.pid == my_pid: continue
                    name = (p.info['name'] or '').lower()
                    if name in ('python.exe','pythonw.exe'):
                        cmd = ' '.join(p.info['cmdline'] or [])
                        if any(k in cmd for k in keywords):
                            p.kill()
                except: pass
        except Exception:
            pass
        logger.info("Apagado completo")
