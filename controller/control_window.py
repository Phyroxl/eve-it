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
        win.closeEvent = lambda e: (e.ignore(), win.hide())

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

        from PySide6.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QPen, QBrush, QFont

        class EveButton(QPushButton):
            """Botón de alta fidelidad con estética EVE Online (Sci-Fi/Tech)."""
            def __init__(self, text, base_color, icon_char, parent=None):
                super().__init__(parent)
                self.base_color = QColor(base_color)
                self.icon_char = icon_char
                self.setText(text) # Aplicar limpieza inmediata
                self.setMinimumHeight(100)
                self.setCursor(C.Qt.PointingHandCursor)
                self._is_hover = False
                self._is_pressed = False
                self._is_active = False # Para indicar si el módulo está ON

            def set_active(self, active: bool):
                if self._is_active != active:
                    self._is_active = active
                    self.update()

            def enterEvent(self, event):
                self._is_hover = True
                self.update()
                super().enterEvent(event)

            def leaveEvent(self, event):
                self._is_hover = False
                self.update()
                super().leaveEvent(event)

            def mousePressEvent(self, event):
                if event.button() == C.Qt.LeftButton:
                    self._is_pressed = True
                    self.update()
                super().mousePressEvent(event)

            def mouseReleaseEvent(self, event):
                self._is_pressed = False
                self.update()
                super().mouseReleaseEvent(event)

            def paintEvent(self, event):
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing)
                rect = self.rect().adjusted(2, 2, -2, -2)
                w, h = rect.width(), rect.height()
                bevel = 15
                path = QPainterPath()
                path.moveTo(bevel, 0)
                path.lineTo(w - bevel, 0); path.lineTo(w, bevel)
                path.lineTo(w, h - bevel); path.lineTo(w - bevel, h)
                path.lineTo(bevel, h); path.lineTo(0, h - bevel)
                path.lineTo(0, bevel); path.closeSubpath()

                # Brillo de estado Activo (Glow de fondo)
                if self._is_active:
                    p.setPen(C.Qt.NoPen)
                    p.setBrush(QBrush(QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 15)))
                    p.drawPath(path)

                bg_alpha = 50 if self._is_hover else 30
                if self._is_pressed: bg_alpha = 80
                p.setPen(C.Qt.NoPen)
                p.setBrush(QBrush(QColor(0, 0, 0, 220)))
                p.drawPath(path)
                grad = QLinearGradient(0, 0, 0, h)
                grad.setColorAt(0, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), bg_alpha))
                grad.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(grad)
                p.drawPath(path)

                # Scanlines
                p.setPen(QPen(QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 15), 1))
                for y in range(5, h, 4): p.drawLine(5, y, w-5, y)

                # Bordes Neón
                border_alpha = 200 if self._is_hover or self._is_active else 100
                if self._is_pressed: border_alpha = 255
                p.setPen(QPen(QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), border_alpha // 2), 1))
                p.drawPath(path)
                p.setPen(QPen(QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), border_alpha), 2))
                p.drawLine(0, bevel, bevel, 0) # Highlight superior izquierdo
                p.drawLine(w - bevel, h, w, h - bevel) # Highlight inferior derecho

                # Icono y Texto
                icon_rect = C.QRect(15, 0, 50, h)
                p.setFont(QFont("Segoe UI Symbol", 24))
                p.setPen(QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 255 if self._is_hover or self._is_active else 180))
                p.drawText(icon_rect, C.Qt.AlignCenter, self.icon_char)
                text_rect = C.QRect(70, 0, w - 80, h)
                f = QFont("Share Tech Mono", 12); f.setBold(True)
                p.setFont(f)
                p.setPen(QColor(255, 255, 255, 255 if self._is_hover else 200))
                p.drawText(text_rect, C.Qt.AlignLeft | C.Qt.AlignVCenter, self.text().upper())

                # Adorno lateral
                p.setBrush(QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), border_alpha))
                p.setPen(C.Qt.NoPen)
                p.drawEllipse(w-5, h//2 - 8, 3, 16)

            def setText(self, text):
                # Elimina cualquier cosa entre corchetes, iconos Unicode o saltos de línea
                import re
                clean = re.sub(r'\[.*?\]', '', text) # Quita [T], [H], etc
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
        self._timer.start(2000)
        self._ctrl.state.subscribe(lambda s: self._update_status())
        self._win = win

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
    def _on_scan_chars(self):
        try:
            W, C, G = _load_qt()
            chars = list(self._ctrl._tracker.sessions.keys()) if self._ctrl._tracker else []
            dlg = W.QDialog(self._win)
            dlg.setWindowFlags(
                dlg.windowFlags() |
                (C.Qt.WindowType.FramelessWindowHint if hasattr(C.Qt, 'WindowType') else C.Qt.FramelessWindowHint)
            )
            dlg.setMinimumWidth(300)
            dlg.setStyleSheet(
                "QDialog{background:#000000;border:1px solid rgba(0,180,255,0.3);}"
                "QLabel{color:rgba(200,230,255,0.9);font-size:11px;padding:2px 8px;}"
                "QPushButton{background:rgba(0,180,255,0.15);border:1px solid rgba(0,180,255,0.4);"
                "border-radius:4px;color:#00c8ff;padding:6px 16px;}"
            )
            lay = W.QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

            tb = W.QWidget(); tb.setFixedHeight(30)
            tb.setStyleSheet("QWidget{background:#000000;border-bottom:1px solid rgba(0,180,255,0.15);}")
            tb_lay = W.QHBoxLayout(tb); tb_lay.setContentsMargins(10, 0, 6, 0)
            tb_lbl = W.QLabel(t('gui_dlg_chars_title', self._lang))
            tb_lbl.setStyleSheet("color:rgba(0,180,255,0.6);font-size:9px;letter-spacing:2px;")
            tb_lay.addWidget(tb_lbl); tb_lay.addStretch()
            btn_x = W.QPushButton("✕"); btn_x.setFixedSize(24, 20)
            btn_x.setStyleSheet("QPushButton{background:transparent;border:none;color:rgba(200,230,255,0.4);}QPushButton:hover{color:#ff4444;}")
            btn_x.clicked.connect(dlg.accept); tb_lay.addWidget(btn_x)
            lay.addWidget(tb)

            dlg._dp = None
            def _mp(e): dlg._dp = e.globalPos() if hasattr(e,'globalPos') else e.globalPosition().toPoint()
            def _mm(e):
                if dlg._dp:
                    cur = e.globalPos() if hasattr(e,'globalPos') else e.globalPosition().toPoint()
                    dlg.move(dlg.pos()+cur-dlg._dp); dlg._dp = cur
            def _mr(e): dlg._dp = None
            tb.mousePressEvent=_mp; tb.mouseMoveEvent=_mm; tb.mouseReleaseEvent=_mr

            hint = W.QLabel(f"  {t('gui_dlg_chars_hint', self._lang)}")
            hint.setStyleSheet("color:rgba(0,180,255,0.5);font-size:8px;padding:6px 8px 2px;letter-spacing:1px;")
            lay.addWidget(hint)

            inner = W.QWidget(); inner_lay = W.QVBoxLayout(inner)
            inner_lay.setContentsMargins(8, 4, 8, 8); inner_lay.setSpacing(2)

            import json as _j
            _cfg = Path(__file__).resolve().parent.parent / "_main_char.json"
            try: _main = _j.loads(_cfg.read_text(encoding="utf-8")).get("main", "")
            except Exception: _main = ""
            _mref = [_main]

            if chars:
                for ch in chars:
                    star = " \u2605" if ch == _mref[0] else ""
                    lbl = W.QLabel("\u25cf " + ch + star)
                    lbl.setStyleSheet("color:#00ff9d;font-size:11px;padding:3px 8px;border-radius:3px;")
                    ctx_policy = (
                        C.Qt.ContextMenuPolicy.CustomContextMenu
                        if hasattr(C.Qt, "ContextMenuPolicy")
                        else C.Qt.CustomContextMenu
                    )
                    lbl.setContextMenuPolicy(ctx_policy)
                    def _on_ctx(pos, n=ch, l=lbl):
                        m = W.QMenu(dlg)
                        m.setStyleSheet(
                            "QMenu{background:#0a0a0a;border:1px solid rgba(0,180,255,0.4);"
                            "color:#00c8ff;font-size:10px;padding:4px;}"
                            "QMenu::item{padding:5px 16px;}"
                            "QMenu::item:selected{background:rgba(0,180,255,0.2);}"
                        )
                        t = m.addAction(f"\u00bfSeleccionar '{n}' como Main?"); t.setEnabled(False)
                        m.addSeparator()
                        a_yes = m.addAction("\u2705  SI, seleccionar como Main")
                        m.addAction("\u274c  NO, cancelar")
                        chosen = m.exec(l.mapToGlobal(pos))
                        if chosen == a_yes:
                            _mref[0] = n
                            try: _cfg.write_text(_j.dumps({"main": n}), encoding="utf-8")
                            except Exception: pass
                            for w in dlg.findChildren(W.QLabel):
                                t2 = w.text()
                                if " \u2605" in t2: w.setText(t2.replace(" \u2605", ""))
                            l.setText("\u25cf " + n + " \u2605")
                    lbl.customContextMenuRequested.connect(_on_ctx)
                    inner_lay.addWidget(lbl)
            else:
                inner_lay.addWidget(W.QLabel("  No se detectaron personajes."))

            inner_lay.addSpacing(6)
            btn_close = W.QPushButton("Cerrar"); btn_close.clicked.connect(dlg.accept)
            inner_lay.addWidget(btn_close)
            lay.addWidget(inner)
            dlg.exec() if hasattr(dlg, 'exec') else dlg.exec_()
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
            if self._tray and hasattr(self._tray, '_on_translator'):
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
            logger.info("Lanzando Replicator 2.0 (Pro Edition)")
            if self._tray:
                self._tray._on_replicator()
        except Exception as e:
            logger.error(f"replicator error: {e}")

    def _on_playpause(self):
        from datetime import datetime
        self._paused = not self._paused
        if self._paused:
            self._pause_time = datetime.now()
            self._btn_playpause.setText("▶\n" + t('gui_btn_resume', self._lang))
        else:
            if self._pause_time:
                self._pause_elapsed += int((datetime.now() - self._pause_time).total_seconds())
                self._pause_time = None
            if not self._ctrl.state.tracker_running:
                self._ctrl.start_tracker()
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

                per_char = summary.get('per_character', [])
                for cd in per_char:
                    ti = cd.get('tick_info', {})
                    if ti.get('countdown_str', '--:--') != '--:--':
                        break
            else:
                self._lbl_chars.setText(f"0 {t('gui_chars_suffix', self._lang)}")
                self._lbl_isk.setText("— " + t('gui_isk_total', self._lang))
                self._lbl_session.setText(f"{t('gui_session_time', self._lang)}: 00:00:00")
        except Exception:
            pass

        # Actualizar brillo de los módulos según su estado activo
        if hasattr(self._btn_overlay, 'set_active'):
            self._btn_overlay.set_active(state.overlay_active)
        if hasattr(self._btn_replicator, 'set_active'):
            self._btn_replicator.set_active(state.replicator_active)

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
