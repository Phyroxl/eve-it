"""
overlay_app.py — EVE ISK Tracker HUD overlay.
Versión LIMPIA y OPTIMIZADA con Controles de Sesión.
"""

import sys
import os
import json
import socket
import threading
import struct
from pathlib import Path

# Garantizar que el directorio raíz del proyecto esté en sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Ahora sí podemos importar utils
from utils.i18n import t

# Qt: intentar PySide6 → PyQt6 → PySide2 → PyQt5
_qt_ok = False
for _qt in [
    ('PySide6',  'PySide6.QtWidgets',  'PySide6.QtCore',  'PySide6.QtGui'),
    ('PyQt6',    'PyQt6.QtWidgets',    'PyQt6.QtCore',    'PyQt6.QtGui'),
    ('PySide2',  'PySide2.QtWidgets',  'PySide2.QtCore',  'PySide2.QtGui'),
    ('PyQt5',    'PyQt5.QtWidgets',    'PyQt5.QtCore',    'PyQt5.QtGui'),
]:
    try:
        import importlib
        _widgets = importlib.import_module(_qt[1])
        _core    = importlib.import_module(_qt[2])
        _gui     = importlib.import_module(_qt[3])
        # Exponer símbolos necesarios
        for _name in ['QApplication', 'QWidget', 'QVBoxLayout', 'QHBoxLayout',
                      'QLabel', 'QPushButton', 'QSizePolicy', 'QFrame']:
            globals()[_name] = getattr(_widgets, _name)
        for _name in ['Qt', 'QTimer', 'QThread', 'pyqtSignal', 'Signal',
                      'QPoint', 'QSize', 'QSettings']:
            if hasattr(_core, _name):
                globals()[_name] = getattr(_core, _name)
        for _name in ['QFont', 'QColor', 'QPainter', 'QPainterPath',
                      'QBrush', 'QPen', 'QCursor', 'QIcon', 'QFontDatabase', 'QGraphicsOpacityEffect']:
            if hasattr(_gui, _name):
                globals()[_name] = getattr(_gui, _name)
        # Signal compatible con PyQt/PySide
        if 'Signal' not in globals() and 'pyqtSignal' in globals():
            Signal = pyqtSignal
        _qt_ok = True
        _QT_BACKEND = _qt[0]
        break
    except ImportError:
        continue

if not _qt_ok:
    sys.exit(1)

# ── Constantes ────────────────────────────────────────────────────────────────
OVERLAY_PORT   = 47291
SINGLETON_PORT = 47290
SETTINGS_ORG   = "EVEISKTracker"
SETTINGS_APP   = "Overlay"

C = {
    'bg':       '#000000'          ,
    'bg_panel': '#0a0a0a'          ,
    'border':   'rgba(0, 180, 255, 60)',
    'accent':   '#00c8ff',
    'green':    '#00ff9d',
    'gold':     '#ffd700',
    'red':      '#ff4444',
    'dim':      'rgba(200, 230, 255, 0.45)',
    'white':    'rgba(220, 240, 255, 0.92)',
}

SCALE = 1.0
def S(v): return int(round(v * SCALE))
FONT_MONO = 'Share Tech Mono, Consolas, Courier New, monospace'
FONT_HUD  = 'Orbitron, Rajdhani, Arial, sans-serif'

# ══════════════════════════════════════════════════════════════════════════════
# Widgets
# ══════════════════════════════════════════════════════════════════════════════

class MetricBlock(QWidget):
    def __init__(self, key: str, value: str = '—', accent: str = C['accent'], parent=None):
        super().__init__(parent)
        self._key = key; self._lang = 'es'; self._accent = accent
        lay = QVBoxLayout(self); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(0)
        self._lbl = QLabel(t(self._key, self._lang).upper())
        self._lbl.setStyleSheet(f"color: {C['dim']}; font-family: {FONT_MONO}; font-size: 8px; letter-spacing: 1px;")
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color: {accent}; font-family: {FONT_HUD}; font-size: 15px; font-weight: bold; letter-spacing: 1px;")
        lay.addWidget(self._lbl); lay.addWidget(self._val)
        self.setStyleSheet(f"MetricBlock {{ background: {C['bg_panel']}; border: 1px solid {C['border']}; border-radius: 5px; }}")

    def set_value(self, v: str):
        if self._val.text() != v: self._val.setText(v)

    def retranslate_ui(self, lang: str):
        self._lang = lang
        self._lbl.setText(t(self._key, lang).upper())

class CountdownBlock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._secs_left = -1; self._lang = 'es'
        lay = QVBoxLayout(self); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(0)
        self._lbl = QLabel(t('hud_next_tick', self._lang))
        self._lbl.setStyleSheet(f"color: {C['dim']}; font-family: {FONT_MONO}; font-size: 8px; letter-spacing: 1px;")
        self._val = QLabel("--:--")
        self._val.setStyleSheet(f"color: {C['gold']}; font-family: {FONT_HUD}; font-size: 18px; font-weight: bold; letter-spacing: 2px;")
        lay.addWidget(self._lbl); lay.addWidget(self._val)
        self.setStyleSheet(f"CountdownBlock {{ background: {C['bg_panel']}; border: 1px solid {C['border']}; border-radius: 5px; }}")
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1000)

    def _tick(self):
        if self._secs_left > 0: self._secs_left -= 1; self._render()

    def _render(self):
        secs = self._secs_left
        txt = '--:--' if secs < 0 else f"{secs//60:02d}:{secs%60:02d}"
        color = C['red'] if 0 <= secs <= 60 else ('#ffa040' if secs <= 300 else C['gold'])
        if self._val.text() != txt: self._val.setText(txt)
        if color not in self._val.styleSheet():
            self._val.setStyleSheet(f"color: {color}; font-family: {FONT_HUD}; font-size: 18px; font-weight: bold; letter-spacing: 2px;")

    def update_countdown(self, secs: int):
        if secs > 0: self._secs_left = secs
        self._render()

    def retranslate_ui(self, lang: str):
        self._lang = lang
        self._lbl.setText(t('hud_next_tick', lang))

class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(12, 12)
        self._color = QColor('#888888')
    def set_status(self, status: str):
        colors = {'connected': '#00ff9d', 'waiting': '#ffd700', 'disconnected': '#ff4444'}
        self._color = QColor(colors.get(status, '#888888')); self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self._color); p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self.width(), self.height())

# ══════════════════════════════════════════════════════════════════════════════
# Singleton y Data Poller
# ══════════════════════════════════════════════════════════════════════════════

class SingletonLock:
    def __init__(self): self._sock = None
    def acquire(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            self._sock.bind(('127.0.0.1', SINGLETON_PORT))
            self._sock.listen(1)
            return True
        except OSError: return False
    def signal_existing(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', SINGLETON_PORT))
            s.send(b'FOCUS\n'); s.close()
        except Exception: pass
    def release(self):
        if self._sock: self._sock.close()
    def listen_for_signals(self, callback):
        def _run():
            while True:
                try:
                    conn, _ = self._sock.accept()
                    if conn.recv(64).strip() == b'FOCUS': callback()
                    conn.close()
                except Exception: break
        threading.Thread(target=_run, daemon=True).start()

class DataPoller(QThread):
    data_received = Signal(dict)
    connection_lost = Signal()
    connection_ok   = Signal()
    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
    def stop(self): self._stop_event.set()
    def run(self):
        import time
        connected = False
        while not self._stop_event.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0); s.connect(('127.0.0.1', OVERLAY_PORT))
                    if not connected:
                        connected = True; self.connection_ok.emit()
                    buf = b''
                    while not self._stop_event.is_set():
                        chunk = s.recv(4096)
                        if not chunk: break
                        buf += chunk
                        while b'\n' in buf:
                            line, buf = buf.split(b'\n', 1)
                            try: self.data_received.emit(json.loads(line.decode('utf-8')))
                            except Exception: pass
            except Exception:
                if connected: connected = False; self.connection_lost.emit()
                time.sleep(2.0)

# ══════════════════════════════════════════════════════════════════════════════
# OverlayWindow
# ══════════════════════════════════════════════════════════════════════════════

class OverlayWindow(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self._ctrl = controller
        self._lang = controller.state.language if controller else 'es'
        self._drag_pos = None; self._compact = False
        self._setup_window(); self._build_ui(); self._restore_position(); self._setup_poller()
        if self._ctrl: self._ctrl.state.subscribe(self._on_state_change)

    def _setup_window(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setMinimumSize(250, 130); self.resize(280, 160); self.setWindowOpacity(1.0)
        self.setStyleSheet(f"QWidget {{ background: {C['bg']}; color: {C['white']}; font-family: {FONT_MONO}; }}")

    def _build_ui(self):
        self._container = QWidget(self)
        self._container.setStyleSheet(f"QWidget {{ background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 8px; }}")
        root_lay = QVBoxLayout(self); root_lay.setContentsMargins(0, 0, 0, 0); root_lay.addWidget(self._container)
        main_lay = QVBoxLayout(self._container); main_lay.setContentsMargins(10, 8, 10, 8); main_lay.setSpacing(6)

        title_row = QHBoxLayout()
        self._dot = StatusDot(); self._dot.setFixedSize(10, 10); title_row.addWidget(self._dot)
        self._title_lbl = QLabel("⚡ " + t('hud_isk_total', self._lang).upper())
        self._title_lbl.setStyleSheet(f"color: {C['accent']}; font-family: {FONT_HUD}; font-size: 10px; font-weight: bold; letter-spacing: 1.5px;")
        title_row.addWidget(self._title_lbl)
        
        title_row.addStretch()
        title_row.setSpacing(5)
        
        BTN_MIN_STYLE = "QPushButton{background:rgba(0,180,255,0.15);border:1px solid rgba(0,180,255,0.4);border-radius:3px;color:#00c8ff;font-size:10px;padding:0;margin:0;}QPushButton:hover{background:rgba(0,180,255,0.35);}"
        BTN_CLS_STYLE = "QPushButton{background:rgba(255,50,50,0.15);border:1px solid rgba(255,50,50,0.4);border-radius:3px;color:#ff6666;font-size:10px;padding:0;margin:0;}QPushButton:hover{background:rgba(255,50,50,0.35);}"

        # Botones de sesión
        self._btn_playpause = QPushButton("\u23ef") # ⏯
        self._btn_playpause.setFixedSize(18, 18); self._btn_playpause.setStyleSheet(BTN_MIN_STYLE)
        self._btn_playpause.setToolTip("Pausar/Reanudar")
        self._btn_playpause.clicked.connect(self._do_pause)
        title_row.addWidget(self._btn_playpause)

        self._btn_reset_hud = QPushButton("\u21bb") # 🔄
        self._btn_reset_hud.setFixedSize(18, 18); self._btn_reset_hud.setStyleSheet(BTN_MIN_STYLE)
        self._btn_reset_hud.setToolTip("Resetear Sesión")
        self._btn_reset_hud.clicked.connect(self._do_reset)
        title_row.addWidget(self._btn_reset_hud)

        sep_tool = QFrame(); sep_tool.setFixedSize(1, 14); sep_tool.setStyleSheet("background: rgba(0,180,255,0.25);")
        title_row.addWidget(sep_tool)

        self._btn_compact = QPushButton("\u2212") # −
        self._btn_compact.setFixedSize(18, 18); self._btn_compact.setStyleSheet(BTN_MIN_STYLE)
        self._btn_compact.clicked.connect(self._toggle_compact)
        title_row.addWidget(self._btn_compact)
        
        btn_close = QPushButton("\u00d7") # ×
        btn_close.setFixedSize(18, 18); btn_close.setStyleSheet(BTN_CLS_STYLE)
        btn_close.clicked.connect(self.hide)
        title_row.addWidget(btn_close)
        
        main_lay.addLayout(title_row)

        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet(f"background: {C['border']};")
        main_lay.addWidget(sep)

        self._full_panel = QWidget(); full_lay = QVBoxLayout(self._full_panel); full_lay.setContentsMargins(0, 0, 0, 0); full_lay.setSpacing(4)
        r1 = QHBoxLayout(); self._m_iskh = MetricBlock('hud_isk_h_rolling'); self._m_isks = MetricBlock('hud_isk_h_session')
        r1.addWidget(self._m_iskh); r1.addWidget(self._m_isks); full_lay.addLayout(r1)
        r2 = QHBoxLayout(); self._m_cd = CountdownBlock(); self._m_sess = MetricBlock('hud_session')
        r2.addWidget(self._m_cd); r2.addWidget(self._m_sess); full_lay.addLayout(r2)
        r3 = QHBoxLayout(); self._m_total = MetricBlock('hud_isk_total'); self._m_chars = MetricBlock('hud_characters')
        r3.addWidget(self._m_total); r3.addWidget(self._m_chars); full_lay.addLayout(r3)
        main_lay.addWidget(self._full_panel)

        self._compact_panel = QWidget(); self._compact_panel.hide()
        c_lay = QHBoxLayout(self._compact_panel)
        self._c_iskh = QLabel("0 ISK/h"); self._c_iskh.setStyleSheet(f"color: {C['green']}; font-family: {FONT_HUD}; font-size: 16px; font-weight: bold;")
        self._c_tick = QLabel("--:--"); self._c_tick.setStyleSheet(f"color: {C['gold']}; font-family: {FONT_HUD}; font-size: 16px; font-weight: bold;")
        c_lay.addWidget(self._c_iskh); c_lay.addStretch(); c_lay.addWidget(self._c_tick)
        main_lay.addWidget(self._compact_panel)

    def _do_pause(self):
        try:
            from controller.control_window import _control_window_ref
            if _control_window_ref: _control_window_ref._on_playpause()
        except: pass

    def _do_reset(self):
        try:
            from controller.control_window import _control_window_ref
            if _control_window_ref: _control_window_ref._on_reset()
        except: pass

    def _send_command(self, cmd: str):
        """Mantenido por compatibilidad legacy."""
        pass

    def _on_data(self, data):
        self._m_iskh.set_value(self._fmt(data.get('isk_h_rolling', 0)))
        self._m_isks.set_value(self._fmt(data.get('isk_h_session', 0)))
        self._m_sess.set_value(self._fmt_dur(data.get('session_secs', 0)))
        self._m_total.set_value(self._fmt(data.get('total_isk', 0)))
        self._m_chars.set_value(str(data.get('char_count', 0)))
        self._c_iskh.setText(self._fmt(data.get('isk_h_rolling', 0)) + " ISK/h")
        self._m_cd.update_countdown(data.get('secs_until_next', -1))
        self._c_tick.setText(data.get('countdown', '--:--'))

    def _fmt(self, v):
        if v >= 1e9: return f"{v/1e9:.2f}B"
        if v >= 1e6: return f"{v/1e6:.1f}M"
        if v >= 1e3: return f"{v/1e3:.0f}K"
        return str(v)

    def _fmt_dur(self, s):
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    def _on_connected(self): self._dot.set_status('connected'); self._status_lbl.setText(t('hud_live', self._lang))
    def _on_disconnected(self): self._dot.set_status('disconnected'); self._status_lbl.setText(t('hud_connecting', self._lang))

    def _on_state_change(self, state):
        if state.language != self._lang: self.retranslate_ui(state.language)

    def retranslate_ui(self, lang):
        self._lang = lang
        self._title_lbl.setText("⚡ " + t('hud_isk_total', lang).upper())
        self._status_lbl.setText(t('hud_live', lang) if self._dot._color.name() == '#00ff9d' else t('hud_connecting', lang))
        for m in [self._m_iskh, self._m_isks, self._m_sess, self._m_total, self._m_chars, self._m_cd]:
            m.retranslate_ui(lang)

    def _toggle_compact(self):
        self._compact = not self._compact
        self._full_panel.setVisible(not self._compact); self._compact_panel.setVisible(self._compact)
        self.resize(360, 100 if self._compact else 220)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            s = QSettings(SETTINGS_ORG, SETTINGS_APP)
            s.setValue('pos_x', self.x()); s.setValue('pos_y', self.y())
            event.accept()

    def _setup_poller(self):
        self._poller = DataPoller(); self._poller.data_received.connect(self._on_data)
        self._poller.connection_ok.connect(self._on_connected); self._poller.connection_lost.connect(self._on_disconnected)
        self._poller.start()

    def _restore_position(self):
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.move(int(s.value('pos_x', 100)), int(s.value('pos_y', 100)))

    def closeEvent(self, _):
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        s.setValue('pos_x', self.x()); s.setValue('pos_y', self.y())
        self._poller.stop(); self._poller.wait()

def main():
    app = QApplication(sys.argv)
    lock = SingletonLock()
    if not lock.acquire(): lock.signal_existing(); sys.exit(0)
    win = OverlayWindow(); win.show(); lock.listen_for_signals(win.show)
    sys.exit(app.exec())

if __name__ == "__main__": main()
