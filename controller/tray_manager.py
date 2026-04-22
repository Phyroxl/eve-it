"""
tray_manager.py — System tray icon y menú de la aplicación.
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from controller.app_controller import AppController

logger = logging.getLogger('eve.tray')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from utils.i18n import t

def _load_qt():
    import importlib
    for b in [
        ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
        ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
    ]:
        try:
            W = importlib.import_module(b[1])
            C = importlib.import_module(b[2])
            G = importlib.import_module(b[3])
            return W, C, G
        except ImportError: continue
    raise ImportError("No backend Qt")

def _make_tray_icon(G):
    icon_path = PROJECT_ROOT / 'icon.png'
    if icon_path.exists(): return G.QIcon(str(icon_path))
    px = G.QPixmap(32, 32); px.fill(G.QColor(0,0,0,0))
    p = G.QPainter(px); p.setBrush(G.QBrush(G.QColor(8,14,26)))
    p.drawEllipse(1, 1, 30, 30); p.end(); return G.QIcon(px)

class TrayManager:
    def __init__(self, app, controller: 'AppController'):
        W, C, G = _load_qt()
        self._W, self._C, self._G = W, C, G
        self._app, self._ctrl = app, controller
        self._lang = controller.state.language if controller else 'es'

        self._tray = W.QSystemTrayIcon(_make_tray_icon(G), app)
        self._menu = W.QMenu()
        self._menu.setStyleSheet("background: #0a1628; color: white; border: 1px solid #00c8ff;")

        def add_action(text, slot):
            act = self._menu.addAction(text); act.triggered.connect(slot); return act

        add_action("⚡ EVE ISK TRACKER", lambda: None).setEnabled(False)
        self._menu.addSeparator()
        
        self._act_suite = add_action(t('tray_suite', self._lang), self._on_show_suite)
        add_action(t('tray_dashboard', self._lang), self._on_dashboard)
        self._menu.addSeparator()
        
        add_action(t('tray_overlay', self._lang), self._on_overlay)
        add_action(t('tray_replicator', self._lang), self._on_replicator)
        self._menu.addSeparator()
        
        # ACCIÓN DE DIAGNÓSTICO
        add_action("DEBUG: FORZAR SUITE", self._on_diag_force)
        self._menu.addSeparator()
        
        add_action(t('tray_quit', self._lang), self._on_quit)

        self._tray.setContextMenu(self._menu)
        self._tray.show()
        logger.info("Tray instrumentado.")

    def _on_show_suite(self):
        logger.info("DIAG: Intento manual Suite.")
        if hasattr(self, '_suite_window') and self._suite_window:
            logger.info(f"DIAG: Pre-show: Visible={self._suite_window.isVisible()}, Min={self._suite_window.isMinimized()}")
            self._suite_window.showNormal()
            self._suite_window.show()
            self._suite_window.raise_()
            self._suite_window.activateWindow()
            logger.info(f"DIAG: Post-show: Visible={self._suite_window.isVisible()}, Geom={self._suite_window.geometry()}")
        else: logger.error("DIAG: Sin referencia a Suite.")

    def _on_diag_force(self):
        logger.info("DIAG: Ejecutando REFUERZO AGRESIVO.")
        if hasattr(self, '_suite_window') and self._suite_window:
            self._suite_window.hide()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._on_show_suite)
        else: logger.error("DIAG: Error crítico - Suite no instanciada.")

    def _on_dashboard(self): self._ctrl.open_dashboard_browser()
    def _on_overlay(self): self._ctrl.toggle_overlay()
    def _on_replicator(self): pass
    def _on_quit(self): self._app.quit()
    def set_control_window(self, win): self._control_window = win
    def set_suite_window(self, win): self._suite_window = win
