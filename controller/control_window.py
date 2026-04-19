"""
control_window.py — Ventana principal de control de EVE iT.
"""
from __future__ import annotations
import sys
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from controller.app_controller import AppController

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from utils.i18n import t

logger = logging.getLogger('eve.control_window')
ASSETS_DIR = PROJECT_ROOT / 'assets'

def _load_qt():
    import importlib
    for b in [
        ('PySide6',  'PySide6.QtWidgets',  'PySide6.QtCore',  'PySide6.QtGui'),
        ('PyQt6',    'PyQt6.QtWidgets',     'PyQt6.QtCore',    'PyQt6.QtGui'),
        ('PySide2',  'PySide2.QtWidgets',   'PySide2.QtCore',  'PySide2.QtGui'),
        ('PyQt5',    'PyQt5.QtWidgets',     'PyQt5.QtCore',    'PyQt5.QtGui'),
    ]:
        try:
            W = importlib.import_module(b[1])
            C = importlib.import_module(b[2])
            G = importlib.import_module(b[3])
            return W, C, G
        except ImportError:
            continue
    raise ImportError("Qt no disponible")

# Cargar Qt globalmente para permitir herencia de clases
try:
    W, C, G = _load_qt()
    QWidget = W.QWidget
    Qt = C.Qt
except Exception:
    pass

# Referencia global para que overlays externos puedan mandar comandos
_control_window_ref = None

STYLE = """
QWidget#main {
    background: #000000;
}
QWidget {
    background: transparent;
    color: rgba(200,230,255,0.9);
    font-family: 'Share Tech Mono', Consolas, monospace;
}
QLabel#app_title {
    color: #00c8ff;
    font-family: Orbitron, 'Share Tech Mono', Arial;
    font-size: 22px;
    font-weight: bold;
    letter-spacing: 4px;
}
QLabel#app_sub {
    color: rgba(0,180,255,0.5);
    font-size: 9px;
    letter-spacing: 3px;
}
QLabel#section {
    color: rgba(0,180,255,0.6);
    font-size: 9px;
    letter-spacing: 2px;
    padding: 0 0 4px 0;
}
QLabel#status_on  { color: #00ff9d; font-size: 9px; }
QLabel#status_off { color: rgba(200,230,255,0.3); font-size: 9px; }
QPushButton.main_btn {
    background: rgba(0,180,255,0.08);
    border: 1px solid rgba(0,180,255,0.25);
    border-radius: 6px;
    color: rgba(180,220,255,0.85);
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px;
    letter-spacing: 1px;
    padding: 10px 0;
    text-align: center;
}
QPushButton.main_btn:hover  { background: rgba(0,180,255,0.18); border-color: rgba(0,200,255,0.7); color: #00c8ff; }
QPushButton.main_btn:pressed { background: rgba(0,180,255,0.30); }
QPushButton#btn_close {
    background: rgba(255,50,50,0.08);
    border: 1px solid rgba(255,60,60,0.25);
    border-radius: 5px;
    color: rgba(255,120,120,0.7);
    font-size: 10px;
    padding: 8px 0;
}
QPushButton#btn_close:hover { background: rgba(255,50,50,0.22); border-color: #ff4444; color: #ff6666; }
QFrame#divider { background: rgba(0,180,255,0.12); max-height: 1px; border: none; }
QFrame#card    { background: rgba(5,5,5,0.95); border: 1px solid rgba(0,180,255,0.12); border-radius: 8px; }
"""

class DraggableWindow(QWidget):
    def __init__(self, W, C, G):
        super().__init__()
        self._W = W; self._C = C; self._G = G
        self._drag_pos = None
    
    def mousePressEvent(self, e):
        if e.button() == self._C.Qt.LeftButton:
            # RESTAURACIÓN V3: El arrastre solo funciona en la zona superior (Header)
            # Si el clic es en la zona inferior (donde están los botones), NO aceptamos el evento.
            if e.pos().y() > 140:
                return # Permitir que los botones de herramientas reciban el clic directo
            
            # En la zona superior, solo arrastramos si NO pinchamos en un botón (como Ajustes)
            child = self.childAt(e.pos())
            W = self._W
            if child and isinstance(child, (W.QPushButton, W.QComboBox, W.QToolButton)):
                return
            
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()
            
    def mouseMoveEvent(self, e):
        if self._C.Qt.LeftButton and self._drag_pos is not None:
            self.move(e.globalPos() - self._drag_pos)
            e.accept()

class ControlWindow:
    def __init__(self, app, controller: 'AppController', tray_manager):
        self._W = W; self._C = C; self._G = G
        self._app  = app
        self._ctrl = controller
        self._tray = tray_manager
        self._win  = None
        self._paused       = False
        self._pause_time   = None
        self._pause_elapsed = 0
        self._session_start = None
        self._lang = 'es'
        
        global _control_window_ref
        _control_window_ref = self
        
        self._build()

    def _build(self):
        W, C, G = self._W, self._C, self._G
        QWidget      = W.QWidget
        QVBoxLayout  = W.QVBoxLayout
        QHBoxLayout  = W.QHBoxLayout
        QLabel       = W.QLabel
        QPushButton  = W.QPushButton
        QFrame       = W.QFrame
        QGridLayout  = W.QGridLayout
        Qt           = C.Qt
        QTimer       = C.QTimer
        QColor       = G.QColor
        QPainter     = G.QPainter
        QPixmap      = G.QPixmap
        QIcon        = G.QIcon
        QPen         = G.QPen
        QBrush       = G.QBrush
        QFont        = G.QFont

        # ── Ventana (SIN MARCO) ──────────────────────────────────────────────────
        win = DraggableWindow(W, C, G)
        win.setObjectName("main")
        win.setWindowTitle("EVE iT")
        win.setMinimumSize(390, 560) # Un poco más alto para la nueva barra
        win.setStyleSheet(STYLE)
        win.setWindowIcon(_make_icon(G))
        
        flags = Qt.FramelessWindowHint if hasattr(Qt, 'FramelessWindowHint') else Qt.WindowFlags(0x00000800)
        win.setWindowFlags(flags | Qt.Window)
        win.setAttribute(Qt.WA_TranslucentBackground, False) # Negro sólido
        
        def _on_close(e):
            try:
                from PySide6.QtCore import QSettings
                QSettings("EVE_iT", "ControlWindow").setValue("geometry", win.saveGeometry())
            except: pass
            e.ignore()
            win.hide()
        win.closeEvent = _on_close

        root = QVBoxLayout(win)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barra de Título Custom (Frameless) ──────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(30)
        title_bar.setStyleSheet("background: #000000; border-bottom: 1px solid rgba(0,180,255,0.1);")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(10, 0, 10, 0)
        tb_lay.setSpacing(8)
        
        tb_ico = QLabel(); tb_ico.setPixmap(_make_icon_pixmap(G, 16)); tb_lay.addWidget(tb_ico)
        tb_ttl = QLabel("EVE iT"); tb_ttl.setStyleSheet("color:rgba(0,180,255,0.8); font-size:10px; font-weight:bold; letter-spacing:1px;")
        tb_lay.addWidget(tb_ttl); tb_lay.addStretch()
        
        # Botones sincronizados con ChatOverlay
        BTN_MIN_STYLE = (
            "QPushButton{background:rgba(0,180,255,0.15);border:1px solid rgba(0,180,255,0.4);"
            "border-radius:3px;color:#00c8ff;font-size:10px;}QPushButton:hover{background:rgba(0,180,255,0.35);}"
        )
        BTN_CLS_STYLE = (
            "QPushButton{background:rgba(255,50,50,0.15);border:1px solid rgba(255,50,50,0.4);"
            "border-radius:3px;color:#ff6666;font-size:10px;}QPushButton:hover{background:rgba(255,50,50,0.35);}"
        )
        
        btn_min = QPushButton("\u2212"); btn_min.setFixedSize(18, 18); btn_min.setStyleSheet(BTN_MIN_STYLE)
        btn_min.clicked.connect(win.showMinimized); tb_lay.addWidget(btn_min)
        
        btn_cls = QPushButton("\u00d7"); btn_cls.setFixedSize(18, 18); btn_cls.setStyleSheet(BTN_CLS_STYLE)
        btn_cls.clicked.connect(win.hide); tb_lay.addWidget(btn_cls)
        
        root.addWidget(title_bar)

        # ── Cabecera (Contenido Principal) ────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(0,0,0,255), stop:1 rgba(0,0,0,255));
                border-bottom: 1px solid rgba(0,180,255,0.2);
            }
        """)
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(24, 20, 24, 18)
        h_lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_make_icon_pixmap(G, 28))
        title_row.addWidget(icon_lbl)
        title_lbl = QLabel("EVE iT")
        title_lbl.setObjectName("app_title")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        # Botones cabecera derecha (antes del dot)
        _btn_style = ("QPushButton{background:transparent;border:1px solid rgba(0,180,255,0.2);"
                      "border-radius:3px;font-size:11px;padding:0;color:rgba(200,230,255,0.7);}"
                      "QPushButton:hover{background:rgba(0,180,255,0.15);border-color:rgba(0,180,255,0.5);}")
        self._btn_refresh = QPushButton("🔄")
        self._btn_refresh.setFixedSize(26, 22)
        self._btn_refresh.setToolTip(t('tray_restart', self._lang))
        self._btn_refresh.setStyleSheet(_btn_style)
        title_row.addWidget(self._btn_refresh)

        self._btn_dashboard_hdr = QPushButton("📊")
        self._btn_dashboard_hdr.setFixedSize(26, 22)
        self._btn_dashboard_hdr.setToolTip("Abrir Dashboard")
        self._btn_dashboard_hdr.setStyleSheet(_btn_style)
        title_row.addWidget(self._btn_dashboard_hdr)

        self._btn_lang_es = QPushButton()
        self._btn_lang_es.setFixedSize(32, 22)
        self._btn_lang_es.setToolTip("Idioma / Language")
        self._btn_lang_es.setStyleSheet(_btn_style)
        _flag = ASSETS_DIR / f"flag_{getattr(self, '_lang', 'es')}.png"
        if _flag.exists():
            self._btn_lang_es.setIcon(G.QIcon(str(_flag)))
            self._btn_lang_es.setIconSize(C.QSize(22, 16))
        title_row.addWidget(self._btn_lang_es)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #ffd700; font-size: 10px;")
        self._status_dot.setToolTip(t('gui_dlg_lang_title', self._lang))
        title_row.addWidget(self._status_dot)
        h_lay.addLayout(title_row)
        self._lbl_app_sub = QLabel(t('welcome_subtitle', self._lang))
        self._lbl_app_sub.setObjectName("app_sub")
        h_lay.addWidget(self._lbl_app_sub)
        root.addWidget(header)

        # ── Cuerpo ────────────────────────────────────────────────────────────
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(10)

        # ── Sección Tracker ───────────────────────────────────────────────────
        self._lbl_sec_tracker = QLabel(t('gui_section_tracker', self._lang))
        self._lbl_sec_tracker.setObjectName("section")
        body_lay.addWidget(self._lbl_sec_tracker)

        card1 = QFrame(); card1.setObjectName("card")
        c1_lay = QVBoxLayout(card1)
        c1_lay.setContentsMargins(14, 12, 14, 12)
        c1_lay.setSpacing(6)

        tracker_row = QHBoxLayout()
        self._lbl_tracker = QLabel("● Tracker inactivo")
        self._lbl_tracker.setObjectName("status_off")
        tracker_row.addWidget(self._lbl_tracker)
        tracker_row.addStretch()
        self._lbl_chars = QLabel("0 personajes")
        self._lbl_chars.setStyleSheet(
            "color: rgba(0,200,255,0.8); font-size: 9px; text-decoration: underline;"
        )
        self._lbl_chars.setToolTip("Click para ver personajes detectados")
        cursor_attr = (
            Qt.CursorShape.PointingHandCursor
            if hasattr(Qt, 'CursorShape')
            else Qt.PointingHandCursor
        )
        self._lbl_chars.setCursor(cursor_attr)
        self._lbl_chars.mousePressEvent = lambda e: self._on_scan_chars()
        tracker_row.addWidget(self._lbl_chars)
        c1_lay.addLayout(tracker_row)

        isk_row = QHBoxLayout()
        self._lbl_isk = QLabel("— ISK Total")
        self._lbl_isk.setStyleSheet("color: #00ff9d; font-size: 13px; font-weight: bold;")
        isk_row.addWidget(self._lbl_isk)
        isk_row.addStretch()
        self._lbl_session = QLabel("sesión: 00:00:00")
        self._lbl_session.setStyleSheet("color: rgba(200,230,255,0.5); font-size: 9px;")
        isk_row.addWidget(self._lbl_session)
        c1_lay.addLayout(isk_row)
        body_lay.addWidget(card1)

        # ── Separador ─────────────────────────────────────────────────────────
        body_lay.addWidget(self._divider(W))

        # ── Sección Herramientas (NUEVO DISEÑO 2x2) ──────────────────────────
        self._lbl_sec_tools = QLabel(t('gui_section_tools', self._lang))
        self._lbl_sec_tools.setObjectName("section")
        body_lay.addWidget(self._lbl_sec_tools)

        class EveButton(QPushButton):
            """Botón de alta fidelidad con estética EVE Online (Sci-Fi/Tech)."""
            def __init__(self, text, base_color, icon_char, parent=None):
                super().__init__(parent)
                # Usar G (QtGui) para los colores y dibujo
                self.base_color = G.QColor(base_color)
                self.icon_char = icon_char
                self.setText(text)
                self.setMinimumHeight(100)
                self.setCursor(C.Qt.PointingHandCursor)
                self._is_hover = False
                self._is_pressed = False
                self._is_active = False
                self._is_minimized = False

            def set_active(self, active: bool, minimized: bool = False):
                self._is_active = active
                self._is_minimized = minimized
                self.update()

            def paintEvent(self, event):
                p = G.QPainter(self)
                p.setRenderHint(G.QPainter.Antialiasing)
                rect = self.rect().adjusted(2, 2, -2, -2)
                w, h = rect.width(), rect.height()
                bevel = 15
                path = G.QPainterPath()
                path.moveTo(bevel, 0); path.lineTo(w - bevel, 0); path.lineTo(w, bevel)
                path.lineTo(w, h - bevel); path.lineTo(w - bevel, h); path.lineTo(bevel, h)
                path.lineTo(0, h - bevel); path.lineTo(0, bevel); path.closeSubpath()

                # Fondo y Brillo
                bg_alpha = 50 if self._is_hover else (40 if self._is_active else 20)
                p.setPen(C.Qt.NoPen)
                p.setBrush(G.QBrush(G.QColor(0, 0, 0, 220)))
                p.drawPath(path)
                
                grad = G.QLinearGradient(0, 0, 0, h)
                c = self.base_color
                grad.setColorAt(0, G.QColor(c.red(), c.green(), c.blue(), bg_alpha))
                grad.setColorAt(1, G.QColor(0, 0, 0, 0))
                p.setBrush(grad); p.drawPath(path)

                # Indicador de MINIMIZADO (Punto latente)
                if self._is_minimized:
                    p.setBrush(G.QBrush(G.QColor(c.red(), c.green(), c.blue(), 200)))
                    p.drawEllipse(w - 20, 10, 8, 8)
                    p.setPen(G.QPen(G.QColor(c.red(), c.green(), c.blue(), 100), 1))
                    p.drawEllipse(w - 23, 7, 14, 14)

                # Bordes Neón
                border_alpha = 200 if self._is_hover or self._is_active else 80
                p.setPen(G.QPen(G.QColor(c.red(), c.green(), c.blue(), border_alpha), 1 if not self._is_active else 2))
                p.drawPath(path)

                # Icono y Texto
                p.setFont(G.QFont("Segoe UI Symbol", 24))
                p.setPen(G.QColor(c.red(), c.green(), c.blue(), 255 if self._is_active else 150))
                p.drawText(C.QRect(15, 0, 50, h), C.Qt.AlignCenter, self.icon_char)
                
                f = G.QFont("Share Tech Mono", 11); f.setBold(True)
                p.setFont(f); p.setPen(G.QColor(255, 255, 255, 255 if self._is_hover or self._is_active else 150))
                p.drawText(C.QRect(70, 0, w - 80, h), C.Qt.AlignLeft | C.Qt.AlignVCenter, self.text().upper())

            def enterEvent(self, event): self._is_hover = True; self.update(); super().enterEvent(event)
            def leaveEvent(self, event): self._is_hover = False; self.update(); super().leaveEvent(event)
            def mousePressEvent(self, event): 
                if event.button() == C.Qt.LeftButton: self._is_pressed = True; self.update()
                super().mousePressEvent(event)
            def mouseReleaseEvent(self, event): self._is_pressed = False; self.update(); super().mouseReleaseEvent(event)

            def setText(self, text):
                import re
                clean = re.sub(r'\[.*?\]', '', text)
                clean = clean.replace('\n', ' ').replace('📡', '').replace('👁️', '').replace('🧬', '').replace('⏻', '').strip()
                super().setText(clean)

        L = self._lang
        self._btn_translator = EveButton(t('gui_btn_translator', L), "#00c8ff", "📡")
        self._btn_overlay    = EveButton(t('gui_btn_overlay', L),    "#32ff96", "👁️")
        self._btn_replicator = EveButton(t('gui_btn_replicator', L), "#b464ff", "🧬")
        self._btn_quit       = EveButton(t('gui_btn_close', L),      "#ff3232", "⏻")

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(self._btn_translator, 0, 0)
        grid.addWidget(self._btn_overlay,    0, 1)
        grid.addWidget(self._btn_replicator, 1, 0)
        grid.addWidget(self._btn_quit,       1, 1)
        body_lay.addLayout(grid)
        body_lay.addStretch()
        root.addWidget(body)

        # ── Barra de Acoplamiento (NUEVA) ─────────────────────────────────────
        self._dock_widget = QWidget()
        self._dock_widget.setFixedHeight(40)
        self._dock_widget.setStyleSheet("background: rgba(0,20,40,0.8); border-top: 1px solid rgba(0,180,255,0.2);")
        self._dock_lay = QHBoxLayout(self._dock_widget)
        self._dock_lay.setContentsMargins(10, 0, 10, 0); self._dock_lay.setSpacing(5)
        self._dock_lay.addStretch() # Empujar iconos a la derecha o mantener centrados
        
        # Etiqueta de Dock
        self._lbl_dock = QLabel("ACTIVOS:")
        self._lbl_dock.setStyleSheet("color:rgba(0,180,255,0.4); font-size:8px; font-weight:bold;")
        self._dock_lay.insertWidget(0, self._lbl_dock)
        
        root.addWidget(self._dock_widget)
        self._dock_buttons = {} # Cache de botones de dock

        # ── Conexiones ────────────────────────────────────────────────────────
        self._btn_refresh.clicked.connect(self._on_restart_tracker)
        self._btn_dashboard_hdr.clicked.connect(self._on_dashboard)
        self._btn_lang_es.clicked.connect(self._on_language)
        self._btn_translator.clicked.connect(self._on_translator)
        self._btn_overlay.clicked.connect(self._on_overlay)
        self._btn_replicator.clicked.connect(self._on_replicator)
        self._btn_quit.clicked.connect(self._on_quit)

        # ── Timer estado ──────────────────────────────────────────────────────
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_status)
        self._timer.start(500)
        self._ctrl.state.subscribe(lambda s: self._update_status())
        self._win = win

        from PySide6.QtCore import QSettings
        saved_geo = QSettings("EVE_iT", "ControlWindow").value("geometry")
        if saved_geo:
            win.restoreGeometry(saved_geo)
        else:
            screen = self._app.primaryScreen()
            sg = screen.geometry()
            win.move(
                sg.left() + (sg.width()  - win.width())  // 2,
                sg.top()  + (sg.height() - win.height()) // 2,
            )

    def _divider(self, W):
        d = W.QFrame(); d.setObjectName("divider")
        return d

    def retranslate_ui(self):
        """Actualiza todos los textos de la interfaz al idioma actual."""
        L = self._lang
        self._win.setWindowTitle("EVE iT")
        self._lbl_app_sub.setText(t('welcome_subtitle', L))
        self._lbl_sec_tracker.setText(t('gui_section_tracker', L))
        self._lbl_sec_tools.setText(t('gui_section_tools', L))
        
        self._btn_translator.setText(t('gui_btn_translator', L))
        self._btn_overlay.setText(t('gui_btn_overlay', L))
        self._btn_replicator.setText(t('gui_btn_replicator', L))
        
        self._btn_quit.setText(t('gui_btn_close', L))
        self._update_status() # fuerza actualización de etiquetas de estado

    # ── Diálogo personajes detectados ─────────────────────────────────────────
    # ── Diálogo personajes detectados ─────────────────────────────────────────
    def _on_scan_chars(self):
        try:
            W, C, G = _load_qt()
            chars = list(self._ctrl._tracker.sessions.keys()) if self._ctrl._tracker else []
            dlg = W.QDialog(self._win)
            
            # Flags de ventana: Frameless + AlwaysOnTop + Tool
            flags = (C.Qt.WindowType.FramelessWindowHint | C.Qt.WindowType.WindowStaysOnTopHint | C.Qt.WindowType.Tool) \
                    if hasattr(C.Qt, 'WindowType') else \
                    (C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint | C.Qt.Tool)
            dlg.setWindowFlags(flags)
            
            # Forzar TopMost via Win32 API
            try:
                import ctypes
                hwnd = int(dlg.winId())
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            except: pass

            dlg.setMinimumWidth(350); dlg.setMinimumHeight(400)
            dlg.setStyleSheet("QDialog{background:#000000; border:1px solid rgba(0,180,255,0.4); border-radius:10px;}")
            
            lay = W.QVBoxLayout(dlg); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
            
            # Header (Barra superior)
            tb = W.QWidget(); tb.setFixedHeight(40); tb.setStyleSheet("background:rgba(0,180,255,0.08); border-bottom:1px solid rgba(0,180,255,0.2);")
            tb_lay = W.QHBoxLayout(tb); tb_lay.setContentsMargins(15, 0, 10, 0)
            tb_lbl = W.QLabel(t('gui_dlg_chars_title', self._lang))
            tb_lbl.setStyleSheet("color:#00c8ff; font-weight:bold; letter-spacing:1px; font-size:11px;")
            tb_lay.addWidget(tb_lbl); tb_lay.addStretch()
            btn_x = W.QPushButton("✕"); btn_x.setFixedSize(24, 24)
            btn_x.setStyleSheet("QPushButton{background:transparent; border:none; color:rgba(200,230,255,0.4); font-size:16px;} QPushButton:hover{color:#ff4444;}")
            btn_x.clicked.connect(dlg.accept); tb_lay.addWidget(btn_x)
            lay.addWidget(tb)

            # Lógica de Arrastre para el Header (tb)
            dlg._dp = None
            def _mp(e): dlg._dp = e.globalPos() if hasattr(e,'globalPos') else e.globalPosition().toPoint()
            def _mm(e):
                if dlg._dp:
                    cur = e.globalPos() if hasattr(e,'globalPos') else e.globalPosition().toPoint()
                    dlg.move(dlg.pos() + cur - dlg._dp); dlg._dp = cur
            def _mr(e): dlg._dp = None
            tb.mousePressEvent = _mp; tb.mouseMoveEvent = _mm; tb.mouseReleaseEvent = _mr

            # Scroll Area
            scroll = W.QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("border:none; background:transparent;")
            scroll_content = W.QWidget(); scroll_lay = W.QVBoxLayout(scroll_content)
            scroll_lay.setContentsMargins(15, 15, 15, 15); scroll_lay.setSpacing(10)
            
            import json as _j
            _cfg_file = Path(__file__).resolve().parent.parent / "_main_char.json"
            try: _main = _j.loads(_cfg_file.read_text(encoding="utf-8")).get("main", "")
            except: _main = ""

            if chars:
                for ch in chars:
                    # Marco de Personaje (Tarjeta)
                    card = W.QFrame()
                    card.setCursor(C.Qt.PointingHandCursor)
                    is_main = (ch == _main)
                    border_color = "#00ff9d" if is_main else "rgba(0,180,255,0.3)"
                    card.setStyleSheet(f"QFrame {{ background:rgba(0,180,255,0.05); border:1px solid {border_color}; border-radius:6px; }} QFrame:hover {{ background:rgba(0,180,255,0.1); border-color:#00c8ff; }}")
                    
                    # Convertir TODA la tarjeta en link a zKillboard
                    import webbrowser
                    card.mouseReleaseEvent = lambda e, n=ch: webbrowser.open(f"https://zkillboard.com/search/{n}/") if e.button() == C.Qt.LeftButton else None
                    
                    cl = W.QHBoxLayout(card); cl.setContentsMargins(10, 8, 12, 8); cl.setSpacing(12)
                    
                    # Retrato del Personaje
                    pic = W.QLabel()
                    pic.setFixedSize(42, 42)
                    pic.setStyleSheet("border: 1px solid rgba(0,180,255,0.2); border-radius: 4px; background: #050a10;")
                    
                    # Motor de Red Nativo de Qt (Mucho más robusto)
                    from PySide6 import QtNetwork as N
                    
                    if not hasattr(dlg, '_network_mgr'):
                        dlg._network_mgr = N.QNetworkAccessManager(dlg)
                    
                    def _do_load(name, label):
                        url_search = f"https://esi.evetech.net/latest/search/?categories=character&search={name.replace(' ', '%20')}&strict=true"
                        req = N.QNetworkRequest(C.QUrl(url_search))
                        req.setRawHeader(b"User-Agent", b"EVE-iT-App")
                        
                        def _on_search_finished(reply):
                            try:
                                no_err = getattr(N.QNetworkReply, 'NoError', None) or getattr(N.QNetworkReply, 'NetworkError', {}).get('NoError', 0)
                                if reply.error() == 0:  # NoError = 0
                                    import json as _j
                                    res = _j.loads(reply.readAll().data().decode())
                                    ids = res.get('character', [])
                                    if ids:
                                        char_id = ids[0]
                                        img_url = f"https://images.evetech.net/characters/{char_id}/portrait?size=64"
                                        img_req = N.QNetworkRequest(C.QUrl(img_url))
                                        
                                        def _on_img_finished(img_reply):
                                            try:
                                                if img_reply.error() == 0:  # NoError
                                                    pix = G.QPixmap()
                                                    if pix.loadFromData(img_reply.readAll().data()):
                                                        scaled = pix.scaled(42, 42, C.Qt.AspectRatioMode.KeepAspectRatio if hasattr(C.Qt, 'AspectRatioMode') else C.Qt.KeepAspectRatio, C.Qt.TransformationMode.SmoothTransformation if hasattr(C.Qt, 'TransformationMode') else C.Qt.SmoothTransformation)
                                                        label.setPixmap(scaled)
                                            except Exception as e:
                                                logger.warning(f"Error cargando imagen para {name}: {e}")
                                            finally:
                                                img_reply.deleteLater()
                                        
                                        img_reply = dlg._network_mgr.get(img_req)
                                        img_reply.finished.connect(lambda: _on_img_finished(img_reply))
                            except Exception as e:
                                logger.error(f"Excepción en _on_search_finished: {e}")
                            finally:
                                reply.deleteLater()

                        reply = dlg._network_mgr.get(req)
                        reply.finished.connect(lambda: _on_search_finished(reply))

                    _do_load(ch, pic)
                    cl.addWidget(pic)

                    # Info
                    info_lay = W.QVBoxLayout(); info_lay.setSpacing(2)
                    name_lbl = W.QLabel(ch)
                    name_lbl.setStyleSheet("border:none; color:white; font-weight:bold; font-size:12px; background:transparent;")
                    info_lay.addWidget(name_lbl)
                    if is_main:
                        star = W.QLabel("\u2605 MAIN")
                        star.setStyleSheet("border:none; color:#00ff9d; font-size:9px; font-weight:bold; background:transparent;")
                        info_lay.addWidget(star)
                    cl.addLayout(info_lay); cl.addStretch()

                    # Menú contextual para Main
                    card.setContextMenuPolicy(C.Qt.CustomContextMenu)
                    def _on_ctx(pos, n=ch, c=card):
                        m = W.QMenu(dlg)
                        m.setStyleSheet("QMenu{background:#0a0a0a; border:1px solid #00c8ff; color:#00c8ff; font-size:11px; padding:5px;} QMenu::item:selected{background:rgba(0,180,255,0.2);}")
                        
                        # Título y pregunta NO seleccionables (usando QWidgetAction con QLabel)
                        from PySide6.QtWidgets import QWidgetAction as _QA
                        q_lbl = W.QLabel(f" ¿HACER PRINCIPAL A {n.upper()}? ")
                        q_lbl.setStyleSheet("color: #00c8ff; font-weight: bold; font-size: 10px; padding: 10px 5px; background: rgba(0,200,255,0.05); border-radius: 4px;")
                        q_act = _QA(m)
                        q_act.setDefaultWidget(q_lbl)
                        m.addAction(q_act)
                        m.addSeparator()
                        
                        a_yes = m.addAction("\u2705 SÍ, ESTABLECER")
                        a_no  = m.addAction("\u274C NO, CANCELAR")
                        
                        res = m.exec(c.mapToGlobal(pos))
                        if res == a_yes:
                            try:
                                _cfg_file.write_text(_j.dumps({"main": n}), encoding="utf-8")
                                dlg.accept()
                                self._on_scan_chars() # Recargar para ver cambios
                            except: pass
                    
                    card.customContextMenuRequested.connect(_on_ctx)
                    scroll_lay.addWidget(card)
            else:
                scroll_lay.addWidget(W.QLabel("No se han detectado personajes activos."))

            scroll_lay.addStretch()
            scroll.setWidget(scroll_content)
            lay.addWidget(scroll)
            
            # Footer
            footer = W.QWidget(); footer.setFixedHeight(40)
            fl = W.QHBoxLayout(footer); fl.setContentsMargins(15, 0, 15, 0)
            hint = W.QLabel("Clic derecho para establecer como Main")
            hint.setStyleSheet("color:rgba(255,255,255,0.85); font-size:12px; font-style:italic;")
            fl.addWidget(hint); fl.addStretch()
            lay.addWidget(footer)

            dlg.exec() if hasattr(dlg, 'exec') else dlg.exec_()
        except Exception as e:
            logger.error(f"scan_chars error: {e}")
        except Exception as e:
            logger.error(f"scan_chars error: {e}")

    # ── Acciones ──────────────────────────────────────────────────────────────
    def _on_dashboard(self):
        try:
            if not self._ctrl.state.dashboard_running: self._ctrl.start_dashboard()
            else: self._ctrl.open_dashboard_browser()
        except Exception as e: logger.error(f"dashboard error: {e}")

    def _on_restart_tracker(self):
        try: self._ctrl.restart_tracker()
        except Exception as e: logger.error(f"restart error: {e}")

    def _on_language(self):
        try:
            W, C, G = _load_qt()
            langs = [
                (ASSETS_DIR / "flag_es.png", "Español",    "es"),
                (ASSETS_DIR / "flag_en.png", "English",    "en"),
                (ASSETS_DIR / "flag_zh.png", "中文",      "zh"),
                (ASSETS_DIR / "flag_ru.png", "Русский",    "ru"),
                (ASSETS_DIR / "flag_fr.png", "Français",   "fr"),
                (ASSETS_DIR / "flag_de.png", "Deutsch",    "de"),
                (ASSETS_DIR / "flag_pt.png", "Português",  "pt"),
                (ASSETS_DIR / "flag_it.png", "Italiano",   "it"),
            ]
            dlg = W.QDialog(self._win)
            dlg.setWindowFlags(C.Qt.WindowType.FramelessWindowHint | C.Qt.WindowType.Popup if hasattr(C.Qt,'WindowType') else C.Qt.FramelessWindowHint | C.Qt.Popup)
            dlg.setFixedWidth(260)
            dlg.setStyleSheet("QDialog{background:#0d1117;border:1px solid rgba(0,180,255,0.3);border-radius:8px;}")
            vlay = W.QVBoxLayout(dlg); vlay.setContentsMargins(0,0,0,8); vlay.setSpacing(0)
            # Header
            hdr = W.QWidget(); hdr.setFixedHeight(36)
            hdr.setStyleSheet("QWidget{background:#0d1117;border-bottom:1px solid rgba(0,180,255,0.15);border-radius:8px 8px 0 0;}")
            hlay = W.QHBoxLayout(hdr); hlay.setContentsMargins(10,0,8,0)
            hdr_lbl = W.QLabel("🌐  Idioma / Language")
            hdr_lbl.setStyleSheet("color:rgba(200,230,255,0.6);font-size:9px;letter-spacing:1px;")
            hlay.addWidget(hdr_lbl); hlay.addStretch()
            btn_x = W.QPushButton("✕"); btn_x.setFixedSize(20,20)
            btn_x.setStyleSheet("QPushButton{background:transparent;border:none;color:rgba(200,230,255,0.4);font-size:10px;}QPushButton:hover{color:#ff4444;}")
            btn_x.clicked.connect(dlg.reject); hlay.addWidget(btn_x)
            vlay.addWidget(hdr)
            # Lista de idiomas
            try: _cur = getattr(self, '_lang', 'es')
            except: _cur = 'es'
            for f_path, name, code in langs:
                btn = W.QPushButton(f"  {name}")
                if f_path.exists():
                    btn.setIcon(G.QIcon(str(f_path)))
                    btn.setIconSize(C.QSize(20, 14))
                btn.setFixedHeight(40)
                is_sel = (code == _cur)
                sel_style = ("QPushButton{background:rgba(0,180,255,0.15);border:none;border-left:3px solid #00c8ff;"
                             "color:#00c8ff;font-size:11px;text-align:left;padding-left:10px;}"
                             "QPushButton:hover{background:rgba(0,180,255,0.2);}")
                nor_style = ("QPushButton{background:transparent;border:none;border-left:3px solid transparent;"
                             "color:rgba(200,230,255,0.75);font-size:11px;text-align:left;padding-left:10px;}"
                             "QPushButton:hover{background:rgba(255,255,255,0.05);color:white;}")
                btn.setStyleSheet(sel_style if is_sel else nor_style)
                def _pick(checked=False, c2=code, f2=f_path):
                    self._lang = c2
                    self._ctrl.state.update(language=c2)
                    self._btn_lang_es.setIcon(G.QIcon(str(f2)))
                    logger.info(f"Language: {c2}")
                    self.retranslate_ui()
                    dlg.accept()
                btn.clicked.connect(_pick)
                vlay.addWidget(btn)
            # Posicionar bajo el botón
            pos = self._btn_lang_es.mapToGlobal(self._btn_lang_es.rect().bottomLeft())
            dlg.move(pos.x() - 10, pos.y() + 4)
            dlg.exec() if hasattr(dlg,'exec') else dlg.exec_()
        except Exception as e: logger.error(f"language error: {e}")

    def _on_translator(self):
        try:
            trans_ov = getattr(self._ctrl, '_translator_overlay', None)
            if trans_ov:
                if not trans_ov.isVisible() or trans_ov.isMinimized():
                    trans_ov.showNormal()
                trans_ov.show()
                if hasattr(trans_ov, '_animate_restore'):
                    trans_ov._animate_restore()
                else:
                    trans_ov.raise_()
                    trans_ov.activateWindow()
            elif self._tray and hasattr(self._tray, '_on_translator'):
                self._tray._on_translator()
            else:
                self._ctrl.start_translator()
        except Exception as e:
            logger.error(f"translator error: {e}")

    def _on_overlay(self):
        try:
            if self._tray: self._tray._on_overlay()
        except Exception as e:
            logger.error(f"overlay error: {e}")

    def _on_replicator(self):
        try:
            # Si el HUB ya existe, restaurarlo
            from controller.replicator_wizard import _GLOBAL_HUB
            if _GLOBAL_HUB and hasattr(_GLOBAL_HUB, 'window') and not getattr(_GLOBAL_HUB, '_is_closed', False):
                _GLOBAL_HUB.window.showNormal()
                _GLOBAL_HUB.window.show()
                if hasattr(_GLOBAL_HUB, '_animate_restore_hub'):
                    _GLOBAL_HUB._animate_restore_hub()
                else:
                    _GLOBAL_HUB.window.raise_()
                    _GLOBAL_HUB.window.activateWindow()
                return

            logger.info("Lanzando Replicator HUB")
            if self._tray:
                self._tray._on_replicator()
        except Exception as e:
            logger.error(f"replicator error: {e}")

    def _on_playpause(self, sync_from_ctrl=False):
        from datetime import datetime
        if not sync_from_ctrl:
            self._ctrl.toggle_tracker()
            return

        # Si llegamos aquí, el tracker ya cambió su estado, solo actualizamos UI
        self._paused = self._ctrl._tracker.is_paused if self._ctrl._tracker else False
        
        if self._paused:
            self._pause_time = datetime.now()
            self._btn_playpause.setText("▶\n" + t('gui_btn_resume', self._lang))
        else:
            if self._pause_time:
                self._pause_elapsed += int((datetime.now() - self._pause_time).total_seconds())
                self._pause_time = None
            
            if self._session_start is None:
                self._session_start = datetime.now()
            self._btn_playpause.setText("⏸\n" + t('gui_btn_pause', self._lang))

    def _on_reset(self):
        try:
            if self._ctrl._tracker:
                self._ctrl._tracker.reset_all()
            self._session_start  = None
            self._pause_elapsed  = 0
            self._pause_time     = None
            self._paused         = True
            self._btn_playpause.setText("▶\n" + t('gui_btn_resume', self._lang))
            self._ctrl.restart_tracker()
        except Exception as e:
            logger.error(f"reset error: {e}")

    def _on_quit(self):
        if self._tray:
            self._tray._on_quit()
        else:
            self._ctrl.shutdown()
            self._app.quit()

    # ── Estado ────────────────────────────────────────────────────────────────
    def _update_status(self):
        state = self._ctrl.state
        if state.tracker_running:
            self._status_dot.setStyleSheet("color: #00ff9d; font-size: 10px;")
            self._lbl_tracker.setText("● " + t('gui_status_active', self._lang))
            self._lbl_tracker.setStyleSheet("color: #00ff9d; font-size: 9px;")
        else:
            self._status_dot.setStyleSheet("color: #ffd700; font-size: 10px;")
            self._lbl_tracker.setText("● " + t('gui_status_inactive', self._lang))
            self._lbl_tracker.setStyleSheet("color: rgba(200,230,255,0.3); font-size: 9px;")

        try:
            if self._ctrl._tracker:
                summary = self._ctrl._tracker.get_summary()
                chars   = summary.get('character_count', 0)
                total   = summary.get('total_isk', 0)
                sess    = summary.get('session_secs', 0)

                self._lbl_chars.setText(f"{chars} {t('gui_chars_suffix', self._lang)}")

                def fmt(v):
                    if v >= 1e9: return f"{v/1e9:.2f}B"
                    if v >= 1e6: return f"{v/1e6:.2f}M"
                    if v >= 1e3: return f"{v/1e3:.1f}K"
                    return "—"

                self._lbl_isk.setText(fmt(total) + " " + t('gui_isk_total', self._lang))
                h = sess // 3600; m = (sess % 3600) // 60; s = sess % 60
                self._lbl_session.setText(f"{t('gui_session_time', self._lang)}: {h:02d}:{m:02d}:{s:02d}")

                # (Tick info se maneja en el overlay_server.py)
            else:
                self._lbl_chars.setText(f"0 {t('gui_chars_suffix', self._lang)}")
                self._lbl_isk.setText("— " + t('gui_isk_total', self._lang))
                self._lbl_session.setText(f"{t('gui_session_time', self._lang)}: 00:00:00")
        except Exception:
            pass

        # Actualizar brillo de los módulos según su estado activo y minimizado
        is_repl_min = False
        try:
            from controller.replicator_wizard import _GLOBAL_HUB
            if _GLOBAL_HUB and hasattr(_GLOBAL_HUB, 'window') and _GLOBAL_HUB.window.isVisible():
                is_repl_min = _GLOBAL_HUB.window.isMinimized()
        except Exception: pass

        if hasattr(self._btn_overlay, 'set_active'):
            self._btn_overlay.set_active(state.overlay_active)
        if hasattr(self._btn_replicator, 'set_active'):
            self._btn_replicator.set_active(state.replicator_active, is_repl_min)

        # GESTIÓN DEL DOCK (Pestañas de herramientas minimizadas)
        
        # 1. HUD Overlay
        is_hud_docked = False
        try:
            hud_ov = self._ctrl.overlay_window
            if hud_ov:
                if not hud_ov.isVisible() or hud_ov.isMinimized():
                    is_hud_docked = True
        except Exception: pass
        self._sync_dock_button("HUD", is_hud_docked, "#32ff96", "👁️", self._on_overlay)

        # 2. Replicator Hub (oculto = docked)
        is_repl_docked = False
        try:
            from controller.replicator_wizard import _GLOBAL_HUB
            if _GLOBAL_HUB and hasattr(_GLOBAL_HUB, 'window') and not getattr(_GLOBAL_HUB, '_is_closed', False):
                if not _GLOBAL_HUB.window.isVisible():
                    is_repl_docked = True
        except Exception: pass
        self._sync_dock_button("REPLICATOR", is_repl_docked, "#b464ff", "🧬", self._on_replicator)

        # 3. Chat Translator (oculto o minimizado = docked)
        is_trans_docked = False
        try:
            trans_ov = getattr(self._ctrl, '_translator_overlay', None)
            if trans_ov:
                if not trans_ov.isVisible() or trans_ov.isMinimized():
                    is_trans_docked = True
        except Exception: pass
        self._sync_dock_button("TRANSLATOR", is_trans_docked, "#00c8ff", "📡", self._on_translator)

    def _sync_dock_button(self, key, is_minimized, color, icon, callback):
        """Añade o quita botones de la barra de acoplamiento inferior."""
        if is_minimized and key not in self._dock_buttons:
            # Crear botón de pestaña para el dock
            btn = self._W.QPushButton(f"{icon} {key}")
            btn.setFixedSize(110, 28)
            style = (f"QPushButton{{background:rgba(0,180,255,0.1); border:1px solid {color}; "
                     f"border-radius:3px; color:{color}; font-size:9px; font-weight:bold;}}"
                     f"QPushButton:hover{{background:rgba(0,180,255,0.2);}}")
            btn.setStyleSheet(style)
            btn.clicked.connect(callback)
            self._dock_lay.insertWidget(self._dock_lay.count()-1, btn)
            self._dock_buttons[key] = btn
        elif not is_minimized and key in self._dock_buttons:
            # Quitar botón si ya no está minimizado
            btn = self._dock_buttons.pop(key)
            self._dock_lay.removeWidget(btn)
            btn.deleteLater()

    # ── Mostrar/ocultar ───────────────────────────────────────────────────────
    def show(self):
        if self._win: self._win.show(); self._win.raise_(); self._win.activateWindow()

    def hide(self):
        if self._win: self._win.hide()

    def toggle(self):
        if self._win and self._win.isVisible(): self._win.hide()
        else: self.show()

    @property
    def window(self): return self._win


# ── Icono ─────────────────────────────────────────────────────────────────────
def _make_icon_pixmap(G, size: int = 32):
    QPixmap  = G.QPixmap; QColor = G.QColor; QPainter = G.QPainter
    QPen     = G.QPen;    QBrush = G.QBrush
    px = QPixmap(size, size); px.fill(QColor(0,0,0,0))
    p  = QPainter(px)
    rh = getattr(getattr(QPainter,'RenderHint',QPainter),'Antialiasing',1)
    p.setRenderHint(rh)
    p.setBrush(QBrush(QColor(8,14,26,240)))
    p.setPen(QPen(QColor(0,180,255,200), max(1,size//16)))
    p.drawEllipse(1,1,size-2,size-2)
    p.setPen(QPen(QColor(255,210,0),0)); p.setBrush(QBrush(QColor(255,210,0)))
    try:
        if hasattr(G,'QPainterPath'):
            path = G.QPainterPath(); s = size
            path.moveTo(s*0.56,s*0.08); path.lineTo(s*0.30,s*0.50)
            path.lineTo(s*0.48,s*0.50); path.lineTo(s*0.44,s*0.92)
            path.lineTo(s*0.70,s*0.46); path.lineTo(s*0.52,s*0.46)
            path.closeSubpath(); p.drawPath(path)
    except Exception: pass
    p.end(); return px

def _make_icon(G):
    return G.QIcon(_make_icon_pixmap(G, 32))

def save_icon_png(G, path: str):
    _make_icon_pixmap(G, 256).save(path, "PNG")
