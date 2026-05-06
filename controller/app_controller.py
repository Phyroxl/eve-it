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
        self.translator_running = False
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
        self._lock           = threading.RLock()

        # Referencia a la ventana Qt del overlay (gestionada externamente)
        self.overlay_window  = None
        # Referencia al manager del replicador (gestionado externamente)
        self.replicator_mgr  = None

        # Configuración persistente
        self.log_directory = ""
        self.ess_retention = 1.0

    def set_log_directory(self, path: str):
        self.log_directory = path
        logger.info(f"Log directory set to: {path}")

    def set_ess_retention(self, val: float):
        self.ess_retention = val
        logger.info(f"ESS retention set to: {val}")

    # ══════════════════════════════════════════════════════════════════════════
    # Arranque y parada del tracker de logs
    # ══════════════════════════════════════════════════════════════════════════

    def start_tracker(self, log_dir: str = '', skip_existing: bool = True,
                      ess_retention: float = 0):
        """Inicia el tracker de logs y el servidor overlay en background."""
        # Usar valores guardados si no se pasan como argumento
        log_dir = log_dir or self.log_directory
        ess_retention = ess_retention or self.ess_retention
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
                    active_window_minutes = 1440, # Aumentado a 24h para que aparezcan aunque no hayan hecho ISK hoy
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
            import controller.control_window as _cw_mod
            ref = getattr(_cw_mod, '_control_window_ref', None)
            if ref:
                ref._on_playpause()
        elif cmd == 'RESET':
            import controller.control_window as _cw_mod
            ref = getattr(_cw_mod, '_control_window_ref', None)
            if ref:
                ref._on_reset()

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

    def toggle_tracker(self):
        """Alterna entre pausa y ejecución (usado por el HUD)."""
        with self._lock:
            if not self._tracker:
                self.start_tracker()
                return
            
            self._tracker.toggle_pause()
            
            # Sincronizar con la ventana de control si existe
            import controller.control_window as _cw_mod
            ref = getattr(_cw_mod, '_control_window_ref', None)
            if ref:
                ref._on_playpause(sync_from_ctrl=True)
            
            logger.info(f"Tracker {'pausado' if self._tracker.is_paused else 'reanudado'}")

    def reset_tracker(self):
        """Reinicia los contadores de la sesión actual."""
        import controller.control_window as _cw_mod
        ref = getattr(_cw_mod, '_control_window_ref', None)
        if ref:
            ref._on_reset()
        elif self._tracker:
            self._tracker.reset_all()

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
        """Inicia el hilo persistente de push de datos."""
        def _push_loop():
            while self.state.tracker_running:
                try:
                    self._push_overlay_data()
                except Exception as e:
                    logger.warning(f"DataPushThread error: {e}")
                time.sleep(1.5)

        thread = threading.Thread(target=_push_loop, daemon=True, name="DataPushThread")
        thread.start()

    def _push_overlay_data(self):
        """Envía datos del tracker al overlay server y al overlay HUD Qt."""
        if not self._tracker or not self._overlay_server:
            return
        try:
            from overlay.overlay_server import build_overlay_payload
            payload = build_overlay_payload(self._tracker)
            self._overlay_server.push(payload)
            # DataPoller recibe los datos del servidor via socket en hilo Qt (safe).
            # La llamada directa anterior causaba doble-actualización y race condition
            # entre el thread del tracker y _local_tick en el hilo principal.
        except Exception as e:
            logger.warning(f"_push_overlay_data error: {e}")

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
            self.state.update(translator_running=True)
        except Exception as e:
            import logging
            logging.getLogger('eve').error(f"start_translator error: {e}")

    def stop_translator(self):
        try:
            if getattr(self, '_translator_overlay', None):
                self._translator_overlay.stop()
                self._translator_overlay.close()
                self._translator_overlay = None
            self.state.update(translator_running=False)
        except Exception as e:
            logger.warning(f"stop_translator error: {e}")


    def stop_dashboard(self):
        with self._lock:
            if self._dashboard_proc:
                try:
                    pid = self._dashboard_proc.pid
                    self._dashboard_proc.terminate()
                    import subprocess
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
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
                # reveal() resetea _user_hidden para que auto-hide vuelva a funcionar
                if hasattr(self.overlay_window, 'reveal'):
                    self.overlay_window.reveal()
                else:
                    self.overlay_window.show()
                if hasattr(self.overlay_window, '_animate_restore'):
                    self.overlay_window._animate_restore()
                self.overlay_window.raise_()
                self.overlay_window.activateWindow()
                self.state.update(overlay_active=True)
                logger.info("Overlay HUD activado")
            except Exception as e:
                logger.error(f"Error mostrando overlay: {e}")

    def hide_overlay(self):
        if self.overlay_window:
            try:
                if hasattr(self.overlay_window, '_animate_to_dock'):
                    self.overlay_window._animate_to_dock()
                else:
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
        if hasattr(self, '_tray') and self._tray:
            try:
                self._tray.close_replicator_overlays()
            except Exception:
                pass
        self.state.update(replicator_active=False)
        logger.info("Replicador detenido")

    # ══════════════════════════════════════════════════════════════════════════
    # Shutdown completo
    # ══════════════════════════════════════════════════════════════════════════

    def shutdown(self):
        """Cierre limpio de todos los módulos. Idempotente — seguro llamarlo dos veces."""
        import time as _t
        if getattr(self, '_shutdown_done', False):
            return
        self._shutdown_done = True
        t0 = _t.perf_counter()
        logger.info("SHUTDOWN START")

        # 1. Detener servicios de datos y threads
        try:
            with self._lock:
                self._stop_tracker_internal()
        except Exception as e:
            logger.error(f"SHUTDOWN tracker error: {e}")

        # 2. Cerrar ventanas y módulos de UI
        try: self.stop_translator()
        except Exception as e: logger.error(f"SHUTDOWN translator error: {e}")

        try: self.hide_overlay()
        except Exception as e: logger.error(f"SHUTDOWN overlay error: {e}")

        try: self.stop_replicator()
        except Exception as e: logger.error(f"SHUTDOWN replicator error: {e}")

        # Ocultar icono de bandeja inmediatamente
        if hasattr(self, '_tray') and self._tray:
            try:
                self._tray.hide()
            except Exception as e:
                logger.warning(f"SHUTDOWN tray hide error: {e}")

        # 3. Detener dashboard (Streamlit)
        try: self.stop_dashboard()
        except Exception as e: logger.error(f"SHUTDOWN dashboard error: {e}")

        # 4. Limpieza final de recursos del sistema
        try:
            import os
            for f in ['.main.pid', '_main_char.json']:
                try:
                    (PROJECT_ROOT / f).unlink(missing_ok=True)
                except Exception as e:
                    logger.debug(f"No se pudo borrar {f}: {e}")
        except Exception as e:
            logger.warning(f"SHUTDOWN cleanup error: {e}")

        dt = int((_t.perf_counter() - t0) * 1000)
        logger.info(f"SHUTDOWN done ms={dt}")
