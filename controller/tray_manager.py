"""
tray_manager.py — System tray icon y menú de la aplicación.

Gestiona la bandeja del sistema y coordina el lanzamiento de ventanas Qt
(overlay HUD y replicador) dentro del mismo proceso.

Requiere Qt (PySide6/PyQt6/PyQt5). Se instancia en el hilo principal Qt.
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from PySide6.QtCore import QTimer

if TYPE_CHECKING:
    from controller.app_controller import AppController

logger = logging.getLogger('eve.tray')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from utils.i18n import t


def _load_qt():
    """Importa Qt y retorna (Widgets, Core, Gui)."""
    import importlib
    for b in [
        ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
        ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
        ('PySide2', 'PySide2.QtWidgets', 'PySide2.QtCore', 'PySide2.QtGui'),
        ('PyQt5',   'PyQt5.QtWidgets',   'PyQt5.QtCore',   'PyQt5.QtGui'),
    ]:
        try:
            W = importlib.import_module(b[1])
            C = importlib.import_module(b[2])
            G = importlib.import_module(b[3])
            return W, C, G
        except ImportError:
            continue
    raise ImportError("No hay backend Qt disponible")


def _make_tray_icon(G):
    """
    Crea un QIcon para el tray.
    Si hay un archivo icon.png en el proyecto, lo usa.
    Si no, genera un ícono SVG programáticamente (rayo amarillo sobre fondo oscuro).
    """
    QPixmap = G.QPixmap
    QIcon   = G.QIcon
    QColor  = G.QColor
    QPainter= G.QPainter
    QPen    = G.QPen
    QFont   = G.QFont

    icon_path = PROJECT_ROOT / 'icon.png'
    if icon_path.exists():
        return QIcon(str(icon_path))

    # Generar ícono 32×32 programáticamente
    px = QPixmap(32, 32)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    rh = getattr(getattr(QPainter, 'RenderHint', QPainter), 'Antialiasing', 1)
    p.setRenderHint(rh)

    # Fondo circular oscuro
    p.setBrush(G.QBrush(QColor(8, 14, 26, 220)))
    p.setPen(QPen(QColor(0, 180, 255, 200), 1.5))
    p.drawEllipse(1, 1, 30, 30)

    # Rayo ⚡ (triángulo estilizado)
    p.setPen(QPen(QColor(255, 210, 0), 0))
    p.setBrush(G.QBrush(QColor(255, 210, 0)))
    try:
        C_mod = __import__('importlib').import_module('PySide6.QtCore' if 'PySide6' in str(type(p)) else
                           'PyQt6.QtCore' if 'PyQt6' in str(type(p)) else
                           'PyQt5.QtCore')
        path_cls = G.QPainterPath if hasattr(G, 'QPainterPath') else None
        if path_cls:
            path = path_cls()
            path.moveTo(18, 5)
            path.lineTo(11, 17)
            path.lineTo(16, 17)
            path.lineTo(14, 27)
            path.lineTo(21, 15)
            path.lineTo(16, 15)
            path.closeSubpath()
            p.drawPath(path)
    except Exception:
        p.setFont(QFont('Arial', 14, 75))
        p.setPen(QPen(QColor(255, 210, 0)))
        p.drawText(px.rect(), 4, '⚡')  # AlignCenter = 4

    p.end()
    return QIcon(px)


class TrayManager:
    """
    Gestiona el icono del system tray y el menú contextual.
    Se encarga de lanzar/ocultar las ventanas Qt en el hilo correcto.
    """

    def __init__(self, app, controller: 'AppController'):
        W, C, G = _load_qt()
        self._W   = W
        self._C   = C
        self._G   = G
        self._app = app
        self._ctrl = controller
        self._lang = controller.state.language if controller else 'es'

        QSysT = W.QSystemTrayIcon
        QMenu = W.QMenu

        # ── Icono del tray ────────────────────────────────────────────────────
        self._icon_normal = _make_tray_icon(G)
        self._tray = QSysT(self._icon_normal, app)
        self._tray.setToolTip("EVE ISK Tracker")

        # ── Menú ──────────────────────────────────────────────────────────────
        self._menu = QMenu()
        self._menu.setStyleSheet("""
            QMenu {
                background: #0a1628;
                border: 1px solid rgba(0,180,255,0.4);
                border-radius: 6px;
                padding: 4px;
                color: rgba(200,230,255,0.9);
                font-family: 'Share Tech Mono', Consolas, monospace;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background: rgba(0,180,255,0.2);
                color: #00c8ff;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(0,180,255,0.2);
                margin: 4px 8px;
            }
        """)

        def add_action(text, slot, checkable=False):
            act = self._menu.addAction(text)
            act.triggered.connect(slot)
            if checkable:
                act.setCheckable(True)
            return act

        self._act_title = add_action("⚡ EVE ISK TRACKER", lambda: None)
        self._act_title.setEnabled(False)
        self._menu.addSeparator()

        from utils.i18n import t
        self._act_suite   = add_action(t('tray_suite', self._lang), self._on_show_suite)
        self._act_panel   = add_action(t('tray_panel', self._lang), self._on_show_panel)
        self._menu.addSeparator()
        self._act_dash    = add_action(t('tray_dashboard', self._lang),   self._on_dashboard)
        self._menu.addSeparator()

        self._act_overlay = add_action(t('tray_overlay', self._lang), self._on_overlay, checkable=True)
        self._act_replic  = add_action(t('tray_replicator', self._lang), self._on_replicator, checkable=True)
        self._menu.addSeparator()

        self._act_tracker = add_action(t('tray_tracker', self._lang), self._on_tracker_toggle, checkable=True)
        self._act_tracker.setChecked(False)
        self._act_restart = add_action(t('tray_restart', self._lang), self._on_restart)
        self._menu.addSeparator()

        self._act_auto    = add_action(t('tray_autostart', self._lang), self._on_autostart, checkable=True)
        self._menu.addSeparator()

        self._act_quit    = add_action(t('tray_quit', self._lang), self._on_quit)
        self._menu.addSeparator()
        self._act_diag    = add_action("DEBUG: FORZAR SUITE", self._on_diag_force)

        self._tray.setContextMenu(self._menu)

        # Doble click → abrir dashboard
        self._tray.activated.connect(self._on_tray_activated)

        # Suscribirse a cambios de estado
        controller.state.subscribe(self._on_state_change)

        # Referencias a ventanas Qt (se crean lazy)
        self._overlay_win        = None
        self._replicator_dialog  = None
        self._replicator_overlays= []
        self._control_window     = None

        self._tray.show()
        logger.info("System tray inicializado")

    # ── Slots del menú ────────────────────────────────────────────────────────

    def hide(self):
        """Ocultar icono de la bandeja inmediatamente."""
        try:
            self._tray.setVisible(False)
        except Exception:
            pass

    def _on_show_suite(self):
        logger.info("DIAG: Intento manual de mostrar Suite desde el Tray.")
        if hasattr(self, '_suite_window') and self._suite_window:
            isVisible = self._suite_window.isVisible()
            isMin = self._suite_window.isMinimized()
            logger.info(f"DIAG: Estado Suite pre-show: Visible={isVisible}, Min={isMin}")
            
            self._suite_window.showNormal()
            self._suite_window.show()
            self._suite_window.raise_()
            self._suite_window.activateWindow()
            
            logger.info(f"DIAG: Estado Suite post-show: Visible={self._suite_window.isVisible()}, Geom={self._suite_window.geometry()}")
        else:
            logger.warning("DIAG: No se encontró referencia a _suite_window en el Tray.")

    def _on_diag_force(self):
        logger.info("DIAG: Ejecutando REFUERZO AGRESIVO DE VISIBILIDAD.")
        if hasattr(self, '_suite_window') and self._suite_window:
            self._suite_window.hide()
            QTimer.singleShot(500, lambda: self._on_show_suite())
        else:
            logger.error("DIAG: Error crítico - Suite no instanciada.")

    def _on_show_panel(self):
        if self._control_window:
            self._control_window.show()

    def _on_dashboard(self):
        if not self._ctrl.state.dashboard_running:
            self._ctrl.start_dashboard()
        else:
            self._ctrl.open_dashboard_browser()

    def _on_overlay(self):
        if not self._overlay_win:
            self._create_overlay_window()
        self._ctrl.toggle_overlay()

    def _on_replicator(self):
        # CARGA FORZADA: No comprobamos si ya está activo, intentamos lanzar el wizard siempre.
        # Esto soluciona bloqueos si el sistema cree erróneamente que ya se está ejecutando.
        logger.info("Activación forzada del replicador solicitada")
        self._launch_replicator_wizard()

    def _on_tracker_toggle(self):
        if self._ctrl.state.tracker_running:
            self._ctrl.stop_tracker()
        else:
            self._ctrl.start_tracker()

    def _on_restart(self):
        self._tray.showMessage("EVE ISK Tracker",
                               "Reiniciando tracker...",
                               self._W.QSystemTrayIcon.MessageIcon.Information
                               if hasattr(self._W.QSystemTrayIcon, 'MessageIcon')
                               else self._W.QSystemTrayIcon.Information, 2000)
        self._ctrl.restart_tracker()

    def _on_autostart(self):
        """Toggle autoarranque con Windows."""
        sender = self._menu.sender() if hasattr(self._menu, 'sender') else None
        enabled = sender.isChecked() if sender else False
        _toggle_autostart(enabled)

    def _on_quit(self):
        logger.info("Cerrando aplicación desde el Tray...")
        self.shutdown()
        self._ctrl.shutdown()
        self._app.quit()
        # Forzar salida si el event loop se queda colgado
        import os
        QTimer.singleShot(2000, lambda: os._exit(0))

    def shutdown(self):
        """Cierre de emergencia de todos los recursos de UI."""
        try:
            self.close_replicator_overlays()
            if self._overlay_win:
                self._overlay_win.close()
            if self._control_window:
                self._control_window.close()
            self._tray.hide()
            self._tray.deleteLater()
        except Exception as e:
            logger.warning(f"TrayManager shutdown error: {e}")

    def _on_tray_activated(self, reason):
        Trigger  = (self._W.QSystemTrayIcon.ActivationReason
                    if hasattr(self._W.QSystemTrayIcon, 'ActivationReason')
                    else self._W.QSystemTrayIcon)
        DblClick = getattr(Trigger, 'DoubleClick', None)
        Click    = getattr(Trigger, 'Trigger', None)
        if reason in (DblClick, Click):
            if hasattr(self, '_suite_window') and self._suite_window:
                self._on_show_suite()
            elif self._control_window:
                self._control_window.show()
            else:
                self._on_dashboard()

    # ── Creación de ventanas Qt ───────────────────────────────────────────────

    def close_replicator_overlays(self):
        """Cierra todos los overlays del replicador y el asistente de forma ultra-rápida."""
        try:
            if self._replicator_dialog:
                self._replicator_dialog.close()
                self._replicator_dialog = None
            
            # 1. Notificar apagado rápido a todos para que no bloqueen con stop() o save()
            overlays = list(self._replicator_overlays)
            for ov in overlays:
                ov._shutting_down = True
                
            # 2. Cierre masivo inmediato
            for ov in overlays:
                try:
                    ov.close()
                    ov.deleteLater()
                except Exception as e:
                    logger.warning(f"Error cerrando overlay: {e}")
            
            self._replicator_overlays.clear()

            # También cerrar el HUB global si existe
            try:
                from controller.replicator_wizard import _GLOBAL_HUB
                if _GLOBAL_HUB and hasattr(_GLOBAL_HUB, 'window'):
                    _GLOBAL_HUB.window.close()
            except Exception as e:
                logger.warning(f"Error cerrando HUB global: {e}")
        except Exception as e:
            logger.error(f"Error cerrando overlays del replicador: {e}")

    def _create_overlay_window(self):
        """Crea el overlay HUD Qt en el hilo principal."""
        try:
            from overlay.overlay_app import OverlayWindow
            self._overlay_win = OverlayWindow(self._ctrl)
            self._ctrl.overlay_window = self._overlay_win
            self._overlay_win.closed_signal = self._on_overlay_closed \
                if hasattr(self._overlay_win, 'closed_signal') else None
            logger.info("Ventana overlay HUD creada")
        except Exception as e:
            logger.error(f"Error creando overlay: {e}", exc_info=True)
            self._tray.showMessage("Error", f"No se pudo crear el overlay:\n{e}",
                                   self._W.QSystemTrayIcon.MessageIcon.Critical
                                   if hasattr(self._W.QSystemTrayIcon, 'MessageIcon')
                                   else self._W.QSystemTrayIcon.Critical, 4000)

    def _launch_replicator_wizard(self):
        """
        Lanza el wizard del replicador DIRECTAMENTE en el hilo Qt.
        """
        self._show_replicator_wizard()

    def _show_replicator_wizard(self):
        """
        Crea y muestra el wizard del replicador en el hilo Qt actual.
        """
        try:
            from overlay import replicator_config as cfg_mod
            cfg = cfg_mod.load_config()
            self._open_replicator_wizard_dialog(cfg, cfg_mod)
        except Exception as e:
            logger.error(f"Error en replicator: {e}", exc_info=True)
            self._tray.showMessage(
                "EVE ISK Tracker — Error",
                f"Error al iniciar el replicador: {e}",
                self._W.QSystemTrayIcon.MessageIcon.Critical
                if hasattr(self._W.QSystemTrayIcon, 'MessageIcon')
                else self._W.QSystemTrayIcon.Critical,
                5000
            )
            self._act_replic.setChecked(False)
            self._ctrl.state.update(replicator_active=False)

    def _restore_replicator_overlays(self, cfg, cfg_mod):
        """Crea overlays de replicación y los trae al frente."""
        try:
            from overlay.win32_capture import find_eve_windows
            from overlay.replication_overlay import ReplicationOverlay

            region = cfg.get('region')
            titles = cfg.get('selected_windows', [])

            if not region or not titles:
                logger.warning("Sin region o ventanas en cfg")
                return

            # Cerrar overlays anteriores
            self.close_replicator_overlays()

            # Resolver hwnds iniciales una sola vez (evita find_eve_windows N veces)
            try:
                initial_hwnds = {w['title']: w['hwnd'] for w in find_eve_windows()}
            except Exception:
                initial_hwnds = {}

            def make_hwnd_getter(win_title):
                def getter():
                    for w in find_eve_windows():
                        if w['title'] == win_title:
                            return w['hwnd']
                    return None
                return getter

            created = 0
            for i, title in enumerate(titles):
                try:
                    fps = cfg.get('global_fps', 30)
                    cfg.setdefault('overlays', {}).setdefault(title, {})['fps'] = fps
                    ov_region = region.copy() if region else {'x':0, 'y':0, 'w':1, 'h':1}

                    ov = ReplicationOverlay(
                        title        = title,
                        hwnd         = initial_hwnds.get(title),   # ← hwnd inicial para notify_active
                        hwnd_getter  = make_hwnd_getter(title),
                        region_rel   = ov_region,
                        cfg          = cfg,
                        save_callback= lambda *a, c=cfg, m=cfg_mod: m.save_overlay_state(c, *a),
                    )

                    try:
                        from PySide6.QtWidgets import QApplication
                        screen = QApplication.primaryScreen().geometry()
                        center_x = screen.x() + (screen.width() - 200) // 2
                        center_y = screen.y() + (screen.height() - 200) // 2
                        ov.resize(200, 200)
                        ov.move(center_x + i*20, center_y + i*20)
                    except Exception:
                        ov.resize(200, 200)
                        ov.move(400 + i*20, 300 + i*20)

                    def _on_closed(t, _ov=ov):
                        if _ov in self._replicator_overlays:
                            self._replicator_overlays.remove(_ov)
                    ov.closed.connect(_on_closed)
                    ov.selection_requested.connect(lambda _ov=ov: self._on_reselect_region(_ov))
                    ov.sync_triggered.connect(lambda rd, _ov=ov: self._on_sync_replicas(_ov, rd))
                    ov.show()
                    ov.raise_()
                    ov.activateWindow()
                    self._replicator_overlays.append(ov)
                    created += 1
                except Exception as e:
                    logger.error(f"Error overlay '{title}': {e}", exc_info=True)

            if created > 0:
                self._ctrl.state.update(replicator_active=True)
                self._act_replic.setChecked(True)
                logger.info(f"Replicador: {created} overlay(s) activos")

                # Inicializar borde activo tras breve settle (overlays recién creados)
                try:
                    from overlay.win32_capture import get_foreground_hwnd as _get_fg
                    from PySide6.QtCore import QTimer as _QTimer
                    def _init_active_border():
                        try:
                            fg = _get_fg()
                            if fg:
                                ReplicationOverlay.notify_active_client_changed(fg)
                        except Exception:
                            pass
                    _QTimer.singleShot(350, _init_active_border)
                except Exception:
                    pass
            else:
                self._act_replic.setChecked(False)

        except Exception as e:
            logger.error(f"Error _restore_replicator_overlays: {e}", exc_info=True)
            self._act_replic.setChecked(False)

    def _open_replicator_wizard_dialog(self, cfg, cfg_mod):
        """
        Crea el wizard refactorizado y lo muestra.
        """
        try:
            try:
                from controller.replicator_wizard import ReplicatorWizard
            except ImportError:
                from replicator_wizard import ReplicatorWizard
                
            self._replicator_wizard_inst = ReplicatorWizard(
                self._W, self._C, self._G, cfg, cfg_mod, 
                lang=self._lang, 
                suite_win=getattr(self, '_suite_win', None),
                callback=lambda c, m: self._restore_replicator_overlays(c, m)
            )
            self._replicator_wizard_inst.show()
            self._replicator_dialog = self._replicator_wizard_inst.dlg
            
        except Exception as e:
            import traceback
            err_stack = traceback.format_exc()
            logger.error(f"Error lanzando ReplicatorWizard: {e}\n{err_stack}")
            self._W.QMessageBox.critical(
                None, "Fallo Crítico: Replicador", 
                f"No se pudo iniciar el asistente del replicador.\n\nError: {e}\n\nDetalles técnicos:\n{err_stack}"
            )
            self._act_replic.setChecked(False)
            self._ctrl.state.update(replicator_active=False)

    def _on_state_change(self, state):
        """Actualiza el menú cuando cambia el estado del controlador."""
        if state.language != self._lang:
            self.retranslate_ui(state.language)
            if hasattr(self, '_replicator_wizard_inst') and hasattr(self._replicator_wizard_inst, 'retranslate_ui'):
                try:
                    self._replicator_wizard_inst.retranslate_ui(state.language)
                except Exception as e:
                    logger.warning(f"retranslate_ui error: {e}")
            
        self._act_overlay.setChecked(state.overlay_active)
        self._act_replic.setChecked(state.replicator_active)
        self._act_tracker.setChecked(state.tracker_running)

        parts = []
        if state.tracker_running:   parts.append("Tracker ✓")
        if state.dashboard_running: parts.append("Dashboard ✓")
        if state.overlay_active:    parts.append("Overlay ✓")
        if state.replicator_active: parts.append("Replicador ✓")
        tip = "EVE ISK Tracker\n" + " · ".join(parts) if parts else "EVE ISK Tracker"
        self._tray.setToolTip(tip)

    def retranslate_ui(self, lang: str):
        """Traduce los textos de los menús del Tray."""
        self._lang = lang
        self._act_suite.setText(t('tray_suite', lang))
        self._act_panel.setText(t('tray_panel', lang))
        self._act_dash.setText(t('tray_dashboard', lang))
        self._act_overlay.setText(t('tray_overlay', lang))
        self._act_replic.setText(t('tray_replicator', lang))
        self._act_tracker.setText(t('tray_tracker', lang))
        self._act_restart.setText(t('tray_restart', lang))
        self._act_auto.setText(t('tray_autostart', lang))
        self._act_quit.setText(t('tray_quit', lang))

    def _on_overlay_closed(self):
        self._ctrl.state.update(overlay_active=False)

    def _on_sync_replicas(self, source_ov, region_dict):
        """Sincroniza la región de todas las réplicas excepto la que originó el cambio."""
        for ov in self._replicator_overlays:
            if ov != source_ov:
                ov.apply_region(region_dict)

    def _on_reselect_region(self, overlay):
        """Abre el wizard para configurar región (pantalla única)."""
        if not self._replicator_dialog or not self._replicator_wizard_inst:
            self._launch_replicator_wizard()
        if self._replicator_wizard_inst:
            if hasattr(self._replicator_wizard_inst, "show_for_region_change"):
                self._replicator_wizard_inst.show_for_region_change(overlay)
            else:
                self._replicator_wizard_inst.show()

    def set_control_window(self, win):
        self._control_window = win

    def set_suite_window(self, win):
        self._suite_window = win

    def show_notification(self, title: str, msg: str, duration_ms: int = 3000):
        """Muestra una notificación del tray."""
        info = (self._W.QSystemTrayIcon.MessageIcon.Information
                if hasattr(self._W.QSystemTrayIcon, 'MessageIcon')
                else self._W.QSystemTrayIcon.Information)
        self._tray.showMessage(title, msg, info, duration_ms)


def _toggle_autostart(enable: bool):
    """Configura o elimina el autoarranque de Windows via registro."""
    import platform
    if platform.system() != 'Windows':
        return
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        app_name = "EVEISKTracker"
        exe_path = sys.executable
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
    except Exception as e:
        logger.error(f"Error configurando autoarranque: {e}")
