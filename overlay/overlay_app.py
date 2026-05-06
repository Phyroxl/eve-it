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

try:
    from importlib import import_module as _imp
    _anim_mod = _imp('PySide6.QtCore') if 'PySide6' in str(Path(__file__)) else None
except: _anim_mod = None

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
    'bg':       '#0a0f14',
    'bg_panel': '#0d1626',
    'border':   'rgba(0, 200, 255, 90)',
    'accent':   '#00c8ff',
    'green':    '#00ff9d',
    'gold':     '#ffd700',
    'red':      '#ff4444',
    'dim':      'rgba(200, 230, 255, 0.60)',
    'white':    'rgba(220, 240, 255, 0.95)',
}

SCALE = 1.0
def S(v): return int(round(v * SCALE))
FONT_MONO = 'Share Tech Mono, Consolas, Courier New, monospace'
FONT_HUD  = 'Orbitron, Rajdhani, Arial, sans-serif'

# ══════════════════════════════════════════════════════════════════════════════
# Widgets
# ── Presets ───────────────────────────────────────────────────────────────────
class HUDPreset:
    BALANCED = 'balanced' # Métrica principal + secundarias (Default)
    COMPACT  = 'compact'  # Todo pequeño en una fila
    FOCUS    = 'focus'    # Solo la métrica principal (Gigante)

    @staticmethod
    def get_config(preset):
        if preset == HUDPreset.COMPACT:
            return {'width': 320, 'height': 80, 'main_large': False, 'show_sec': True, 'sec_compact': True}
        if preset == HUDPreset.FOCUS:
            return {'width': 220, 'height': 100, 'main_large': True, 'show_sec': False, 'sec_compact': False}
        # BALANCED
        return {'width': 280, 'height': 180, 'main_large': True, 'show_sec': True, 'sec_compact': False}

# ══════════════════════════════════════════════════════════════════════════════

class MetricBlock(QWidget):
    def __init__(self, key: str, value: str = '—', accent: str = C['accent'], large=False, parent=None):
        super().__init__(parent)
        self._key = key; self._lang = 'es'; self._accent = accent
        lay = QVBoxLayout(self); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(0)
        
        lbl_size = 8 if not large else 9
        val_size = 15 if not large else 22
        
        self._lbl = QLabel(t(self._key, self._lang).upper())
        self._lbl.setStyleSheet(f"color: {C['dim']}; font-family: {FONT_MONO}; font-size: {lbl_size}px; letter-spacing: 1px;")
        
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color: {accent}; font-family: {FONT_HUD}; font-size: {val_size}px; font-weight: bold; letter-spacing: 1px;")
        
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
        self._val.setStyleSheet(f"color: {C['gold']}; font-family: {FONT_HUD}; font-size: 15px; font-weight: bold; letter-spacing: 1px;")
        lay.addWidget(self._lbl); lay.addWidget(self._val)
        self.setStyleSheet(f"CountdownBlock {{ background: {C['bg_panel']}; border: 1px solid {C['border']}; border-radius: 5px; }}")
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1000)

    def _tick(self):
        if self._secs_left > 0: self._secs_left -= 1; self._render()

    def _render(self):
        if hasattr(self, '_override_str') and self._override_str:
            txt = self._override_str
            color = C['gold'] if txt == '--:--' else ('#ffa040' if txt == 'Esperando...' else C['dim'])
        else:
            secs = self._secs_left
            txt = '--:--' if secs < 0 else f"{secs//60:02d}:{secs%60:02d}"
            color = C['red'] if 0 <= secs <= 60 else ('#ffa040' if secs <= 300 else C['gold'])
            
        if self._val.text() != txt: self._val.setText(txt)
        if color not in self._val.styleSheet():
            self._val.setStyleSheet(f"color: {color}; font-family: {FONT_HUD}; font-size: 15px; font-weight: bold; letter-spacing: 1px;")

    def update_countdown(self, secs: int, text_str: str = '--:--'):
        self._secs_left = secs
        if secs < 0:
            self._override_str = text_str
        else:
            self._override_str = None
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
        self._sock = None
    def stop(self): self._stop_event.set()
    def _send_command(self, cmd: str):
        if self._sock:
            try:
                self._sock.sendall((cmd + '\n').encode('utf-8'))
            except Exception:
                pass
    def run(self):
        import time
        connected = False
        while not self._stop_event.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0); s.connect(('127.0.0.1', OVERLAY_PORT))
                    self._sock = s
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
        self._all_chars = []; self._current_main = self._load_saved_main()
        self._last_server_secs = 0; self._local_secs = 0; self._is_paused = False
        
        # Sistema de Presets
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._current_preset = s.value('preset', HUDPreset.BALANCED)
        
        self._root_lay = QVBoxLayout(self)
        self._root_lay.setContentsMargins(0, 0, 0, 0)
        
        self._setup_window(); self._build_ui(); self._restore_position(); self._setup_poller()
        self._interp_timer = QTimer(self); self._interp_timer.timeout.connect(self._local_tick); self._interp_timer.start(1000)
        if self._ctrl: self._ctrl.state.subscribe(self._on_state_change)

    def _load_saved_main(self) -> str:
        """Lee el main character guardado en _main_char.json."""
        import json as _json
        cfg = Path(__file__).resolve().parent.parent / '_main_char.json'
        try:
            return _json.loads(cfg.read_text(encoding='utf-8')).get('main', '')
        except Exception:
            return ''

    def _setup_window(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setMinimumSize(250, 150); self.resize(280, 180); self.setWindowOpacity(1.0)
        self.setStyleSheet(f"QWidget {{ background: {C['bg']}; color: {C['white']}; font-family: {FONT_MONO}; }}")
        self._user_hidden = False
        self._auto_hidden = False
        self._fg_hide_count = 0
        self._eve_fg_timer = QTimer(self)
        self._eve_fg_timer.timeout.connect(self._check_eve_foreground)
        self._eve_fg_timer.start(75)  # 75 ms — matches replicator speed

    def reveal(self):
        """Mostrar desde trigger externo (tray). Resetea _user_hidden para que auto-hide funcione."""
        self._user_hidden = False
        self._auto_hidden = False
        self.show()

    def _check_eve_foreground(self):
        """Auto-hide when user switches to an external non-EVE, non-app window.

        Uses should_show_overlays() (PID-based check) from win32_capture so all
        Salva Suite Qt windows (replicas, chat overlay, menus, dialogs) are
        correctly treated as 'own'. Debounced 2 ticks × 75 ms = ~150 ms.
        """
        try:
            import sys as _sys
            if _sys.platform != 'win32':
                return
            from overlay.win32_capture import should_show_overlays, get_foreground_hwnd_cached, find_eve_windows_cached
            import ctypes as _ct
            hwnd = get_foreground_hwnd_cached()
            if not hwnd:
                return
            # Module-level cached find_eve_windows (shared with replicas and chat overlay)
            eve_hwnds = {w['hwnd'] for w in find_eve_windows_cached()}
            keep = should_show_overlays(hwnd, eve_hwnds)

            # Throttled debug logging every ~5 s
            _now_log = __import__('time').monotonic()
            if _now_log - getattr(self, '_hud_log_ts', 0.0) > 5.0:
                self._hud_log_ts = _now_log
                try:
                    _buf = _ct.create_unicode_buffer(256)
                    _ct.windll.user32.GetWindowTextW(hwnd, _buf, 256)
                    _title = _buf.value[:50]
                    _pid_dw = _ct.wintypes.DWORD()
                    _ct.windll.user32.GetWindowThreadProcessId(hwnd, _ct.byref(_pid_dw))
                    import os as _os
                    import logging as _lg2
                    _lg2.getLogger('eve.overlay').debug(
                        f"HUD VIS CHECK fg=0x{hwnd:x} title={_title!r} "
                        f"pid={_pid_dw.value} own={_os.getpid()} "
                        f"keep={keep} user_hidden={self._user_hidden} auto_hidden={self._auto_hidden}"
                    )
                except Exception:
                    pass

            if keep:
                self._fg_hide_count = 0
                if self._auto_hidden and not self._user_hidden:
                    self._auto_hidden = False
                    import logging as _lg
                    _lg.getLogger('eve.overlay').debug("HUD SHOW eve_or_app")
                    self.show()
            else:
                self._fg_hide_count += 1
                if self._fg_hide_count >= 2 and self.isVisible() and not self._user_hidden:
                    self._auto_hidden = True
                    import logging as _lg
                    _lg.getLogger('eve.overlay').debug("HUD HIDE external_window")
                    self.hide()
        except Exception as _exc:
            import logging as _lg
            _lg.getLogger('eve.overlay').debug(f"HUD FG check error: {_exc}")

    def showEvent(self, event):
        super().showEvent(event)
        try:
            from ui.common.window_shape import force_square_corners
            force_square_corners(int(self.winId()))
        except Exception:
            pass

    def _build_ui(self):
        # Limpiar contenedor previo si existe para evitar duplicados al cambiar de preset
        if hasattr(self, '_container') and self._container:
            self._container.deleteLater()
            self._root_lay.removeWidget(self._container)
            self._container = None

        self._container = QWidget(self)
        self._container.setStyleSheet(f"QWidget {{ background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 0px; }}")
        self._root_lay.addWidget(self._container)
        
        main_lay = QVBoxLayout(self._container); main_lay.setContentsMargins(10, 8, 10, 8); main_lay.setSpacing(6)

        title_row = QHBoxLayout()
        # StatusDot pequeño para conexión
        self._dot = StatusDot(); self._dot.setFixedSize(8, 8); title_row.addWidget(self._dot)

        # Título de la funcionalidad
        self._lbl_title = QLabel(t('hud_title', self._lang))
        self._lbl_title.setStyleSheet("color: rgba(0,180,255,0.7); font-size: 10px; font-weight: bold; margin-left: 2px;")
        title_row.addWidget(self._lbl_title)

        # Botón selector de Main Character (Icono de Personaje)
        self._btn_main = QPushButton("👤")
        self._btn_main.setFixedSize(24, 24)
        self._btn_main.setToolTip(f"Main: {self._current_main}" if self._current_main else "Seleccionar personaje Main")
        self._btn_main.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                color: #ffffff;
                font-size: 14px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                border-color: #ffffff;
            }
        """)
        self._btn_main.clicked.connect(self._show_main_selector)
        title_row.addWidget(self._btn_main, 1)  # stretch factor 1 para que ocupe espacio

        title_row.setSpacing(5)
        
        # Estilo canónico idéntico a la ventana principal (main_suite_window._TitleBar)
        BTN_NEON_STYLE = """
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 3px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #1e293b;
                color: #e2e8f0;
            }
        """
        BTN_RED_STYLE = """
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 3px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.2);
                border-color: #ef4444;
                color: #ef4444;
            }
        """

        # Botones de sesión
        self._btn_playpause = QPushButton("\u23ef") # ⏯
        self._btn_playpause.setFixedSize(24, 24); self._btn_playpause.setStyleSheet(BTN_NEON_STYLE)
        self._btn_playpause.setToolTip("Pausar/Reanudar")
        self._btn_playpause.clicked.connect(self._do_pause)
        title_row.addWidget(self._btn_playpause)

        self._btn_reset_hud = QPushButton("\u21bb") # 🔄
        self._btn_reset_hud.setFixedSize(24, 24); self._btn_reset_hud.setStyleSheet(BTN_NEON_STYLE)
        self._btn_reset_hud.setToolTip("Resetear Sesión")
        self._btn_reset_hud.clicked.connect(self._do_reset)
        title_row.addWidget(self._btn_reset_hud)

        sep_tool = QFrame(); sep_tool.setFixedSize(1, 14); sep_tool.setStyleSheet("background: rgba(0,180,255,0.25);")
        title_row.addWidget(sep_tool)

        self._btn_compact = QPushButton("\u2212") # −
        self._btn_compact.setFixedSize(24, 24); self._btn_compact.setStyleSheet(BTN_NEON_STYLE)
        self._btn_compact.setToolTip("Minimizar")
        self._btn_compact.clicked.connect(self._do_minimize)
        title_row.addWidget(self._btn_compact)
        
        btn_close = QPushButton("\u00d7") # ×
        btn_close.setFixedSize(24, 24); btn_close.setStyleSheet(BTN_RED_STYLE)
        btn_close.clicked.connect(lambda: (setattr(self, '_user_hidden', True), self.hide()))
        title_row.addWidget(btn_close)
        
        main_lay.addLayout(title_row)
        
        self._lbl_title.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu if hasattr(Qt.ContextMenuPolicy, 'CustomContextMenu') else Qt.CustomContextMenu)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu if hasattr(Qt.ContextMenuPolicy, 'CustomContextMenu') else Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_preset_menu)

        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet(f"background: {C['border']};")
        main_lay.addWidget(sep)

        cfg = HUDPreset.get_config(self._current_preset)
        self.resize(cfg['width'], cfg['height'])

        self._full_panel = QWidget(); full_lay = QVBoxLayout(self._full_panel); full_lay.setContentsMargins(0, 0, 0, 0); full_lay.setSpacing(6)
        
        # Métrica Principal: ISK Total (posición intercambiada con ISK/h)
        self._m_isks = MetricBlock('hud_isk_total', accent=C['green'], large=cfg['main_large'])
        full_lay.addWidget(self._m_isks)

        # Métricas Secundarias
        self._sec_container = QWidget()
        sec_lay = QHBoxLayout(self._sec_container) if not cfg['sec_compact'] else QVBoxLayout(self._sec_container)
        sec_lay.setContentsMargins(0, 0, 0, 0); sec_lay.setSpacing(4)

        if cfg['sec_compact']: # Si es compacto, van en una fila horizontal dentro del main_lay
            full_lay.removeWidget(self._m_isks)
            h_row = QHBoxLayout(); h_row.setSpacing(4)
            h_row.addWidget(self._m_isks)
            self._m_total = MetricBlock('hud_isk_h_session', accent=C['accent'])
            self._m_cd = CountdownBlock()
            self._m_sess = MetricBlock('hud_session')
            h_row.addWidget(self._m_total); h_row.addWidget(self._m_cd); h_row.addWidget(self._m_sess)
            full_lay.addLayout(h_row)
            self._sec_container.hide()
        else:
            self._m_total = MetricBlock('hud_isk_h_session', accent=C['accent'])
            self._m_cd = CountdownBlock()
            self._m_sess = MetricBlock('hud_session')
            r2 = QHBoxLayout(); r2.setSpacing(4)
            r2.addWidget(self._m_total); r2.addWidget(self._m_cd); r2.addWidget(self._m_sess)
            full_lay.addLayout(r2)
            self._sec_container.setVisible(cfg['show_sec'])

        # m_iskh y m_chars ocultos pero mantenidos para compatibilidad
        self._m_iskh = MetricBlock('hud_isk_h_rolling'); self._m_iskh.hide()
        self._m_chars = MetricBlock('hud_characters'); self._m_chars.hide()
        main_lay.addWidget(self._full_panel)

        self._compact_panel = QWidget(); self._compact_panel.hide()
        c_lay = QHBoxLayout(self._compact_panel)
        self._c_iskh = QLabel("0 ISK/h"); self._c_iskh.setStyleSheet(f"color: {C['green']}; font-family: {FONT_HUD}; font-size: 16px; font-weight: bold;")
        self._c_tick = QLabel("--:--"); self._c_tick.setStyleSheet(f"color: {C['gold']}; font-family: {FONT_HUD}; font-size: 16px; font-weight: bold;")
        c_lay.addWidget(self._c_iskh); c_lay.addStretch(); c_lay.addWidget(self._c_tick)
        main_lay.addWidget(self._compact_panel)

    def _do_pause(self):
        if self._ctrl:
            self._ctrl.toggle_tracker()
            # Cambiar icono visualmente según el nuevo estado
            is_paused = getattr(self._ctrl, '_paused', False)
            self._btn_playpause.setText("▶" if is_paused else "⏸")
        else:
            try:
                import controller.control_window as _cw_mod
                ref = getattr(_cw_mod, '_control_window_ref', None)
                if ref:
                    ref._on_playpause()
                    is_paused = getattr(ref, '_paused', False)
                    self._btn_playpause.setText("▶" if is_paused else "⏸")
            except Exception as e:
                import logging; logging.getLogger('eve.overlay').warning(f"playpause error: {e}")

    def _do_reset(self):
        if self._ctrl:
            self._ctrl.reset_tracker()
        else:
            try:
                import controller.control_window as _cw_mod
                ref = getattr(_cw_mod, '_control_window_ref', None)
                if ref:
                    ref._on_reset()
            except Exception as e:
                import logging; logging.getLogger('eve.overlay').warning(f"reset error: {e}")

    def _show_preset_menu(self, pos):
        """Muestra menú de presets al hacer click derecho."""
        from importlib import import_module
        try:
            _w = import_module(_QT_BACKEND + '.QtWidgets')
            QMenu = _w.QMenu
        except: return
        
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: #0d0d0d; border: 1px solid {C['accent']}; color: white; }} QMenu::item:selected {{ background: {C['accent']}; }}")
        
        for p in [HUDPreset.BALANCED, HUDPreset.COMPACT, HUDPreset.FOCUS]:
            act = menu.addAction(p.upper())
            act.setCheckable(True)
            act.setChecked(self._current_preset == p)
            act.triggered.connect(lambda checked, mode=p: self._apply_preset(mode))
        
        menu.exec(self.mapToGlobal(pos))

    def _apply_preset(self, mode):
        """Cambia el preset y reconstruye parte de la UI de forma segura."""
        self._current_preset = mode
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        s.setValue('preset', mode)
        
        # Reconstruir UI sin re-inicializar el objeto QWidget (evita RuntimeError)
        self._build_ui()

    def _send_command(self, cmd: str):
        """Envía comando al servidor vía el poller."""
        if hasattr(self, '_poller'):
            self._poller._send_command(cmd)

    def _show_main_selector(self):
        """Muestra un menú popup para seleccionar el personaje Main."""
        from importlib import import_module
        try:
            _w = import_module(_QT_BACKEND + '.QtWidgets')
            QMenu = _w.QMenu
            QAction = _gui.QAction if hasattr(_gui, 'QAction') else _w.QAction
        except Exception:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: #0d0d0d;
                border: 1px solid rgba(0, 180, 255, 0.5);
                border-radius: 4px;
                padding: 4px 0;
                color: {C['white']};
                font-family: {FONT_MONO};
                font-size: 10px;
            }}
            QMenu::item {{
                padding: 5px 16px;
            }}
            QMenu::item:selected {{
                background: rgba(0, 200, 255, 0.25);
            }}
            QMenu::item:checked {{
                color: #00ff9d;
                font-weight: bold;
            }}
        """)
        if not self._all_chars:
            act = menu.addAction("Sin personajes")
            act.setEnabled(False)
        else:
            for name in self._all_chars:
                act = menu.addAction(("✓ " if name == self._current_main else "   ") + name)
                act.setData(name)
                act.triggered.connect(lambda checked, n=name: self._set_main(n))
        menu.exec(self._btn_main.mapToGlobal(self._btn_main.rect().bottomLeft()))

    def _set_main(self, name: str):
        """Guarda el main character seleccionado en _main_char.json."""
        import json as _json
        cfg = Path(__file__).resolve().parent.parent / '_main_char.json'
        try:
            cfg.write_text(_json.dumps({'main': name}), encoding='utf-8')
            self._current_main = name
            self._btn_main.setToolTip(f"Main: {name}")
        except Exception:
            pass

    def _local_tick(self):
        """Timer local de 1s para interpolar suavemente. Solo actúa si hay datos frescos."""
        if self._is_paused:
            return
        # No incrementar si no hemos recibido datos del servidor en los últimos 8s
        import time as _t
        if _t.monotonic() - getattr(self, '_last_data_ts', 0.0) > 8.0:
            return
        self._local_secs += 1
        self._m_sess.set_value(self._fmt_dur(self._local_secs))

    def _on_data(self, data):
        # Sincronización automática de Preset desde Settings
        remote_preset = data.get('hud_preset')
        if remote_preset and remote_preset != self._current_preset:
            self._apply_preset(remote_preset)
            return

        # Sincronización de visibilidad granular
        if hasattr(self, '_m_total'): self._m_total.setVisible(data.get('show_total', True))
        if hasattr(self, '_m_cd'): self._m_cd.setVisible(data.get('show_tick', True))
        if hasattr(self, '_m_sess'): self._m_sess.setVisible(data.get('show_dur', True))

        self._m_iskh.set_value(self._fmt(data.get('isk_h_rolling', 0)))
        self._m_isks.set_value(self._fmt(data.get('total_isk', 0)))
        # Sincronizar el contador local con el servidor
        import time as _t
        self._last_data_ts = _t.monotonic()
        server_secs = data.get('session_secs', 0)
        self._local_secs = server_secs
        self._m_sess.set_value(self._fmt_dur(server_secs))
        self._m_total.set_value(self._fmt(data.get('isk_h_session', 0)))
        self._m_chars.set_value(str(data.get('char_count', 0)))
        self._c_iskh.setText(self._fmt(data.get('isk_h_rolling', 0)) + " ISK/h")
        self._m_cd.update_countdown(
            data.get('secs_until_next', -1),
            data.get('countdown', '--:--')
        )
        self._c_tick.setText(data.get('countdown', '--:--'))
        # Actualizar lista de personajes y main actual
        self._all_chars = data.get('all_char_names', [])
        new_main = data.get('main_char', '')
        # Solo actualizar si el servidor envía un main válido Y nosotros no tenemos uno guardado ya
        if new_main and new_main != self._current_main:
            self._current_main = new_main
            self._btn_main.setToolTip(f"Main: {new_main}")

        self._is_paused = data.get('is_paused', False)
        self._btn_playpause.setText("▶" if self._is_paused else "⏸")

    def _fmt(self, v):
        if v >= 1e9: return f"{v/1e9:.2f}B"
        if v >= 1e6: return f"{v/1e6:.1f}M"
        if v >= 1e3: return f"{v/1e3:.0f}K"
        return str(v)

    def _fmt_dur(self, s):
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    def _on_connected(self): self._dot.set_status('connected')
    def _on_disconnected(self): self._dot.set_status('disconnected')

    def _on_state_change(self, state):
        if state.language != self._lang: self.retranslate_ui(state.language)

    def retranslate_ui(self, lang):
        self._lang = lang
        if hasattr(self, '_lbl_title'):
            self._lbl_title.setText(t('hud_title', lang))
        for m in [self._m_iskh, self._m_isks, self._m_sess, self._m_total, self._m_chars, self._m_cd]:
            m.retranslate_ui(lang)

    def _do_minimize(self):
        """Minimiza el HUD con animación de deslizamiento hacia el dock."""
        self._animate_to_dock()

    def _animate_to_dock(self):
        """Anima la ventana deslizándose y encogiéndose hacia la posición del dock."""
        try:
            _c = __import__('importlib').import_module(_QT_BACKEND + '.QtCore')
            QPropertyAnimation = _c.QPropertyAnimation
            QEasingCurve = _c.QEasingCurve
            QRect = _c.QRect
            QParallelAnimationGroup = _c.QParallelAnimationGroup

            # Guardar geometría ANTES de animar
            self._saved_geo = self.geometry()

            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    end_x = tg.x() + tg.width() // 2 - 60
                    end_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                end_x = sg.x() + sg.width() // 2 - 60
                end_y = sg.y() + sg.height() - 50
            end_geo = QRect(end_x, end_y, 120, 30)

            group = QParallelAnimationGroup(self)

            anim_geo = QPropertyAnimation(self, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(self._saved_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.InCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.InCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(self, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(1.0)
            anim_op.setEndValue(0.0)
            group.addAnimation(anim_op)

            def _on_finished():
                # Restaurar geometría y opacidad ANTES de ocultar
                self.setWindowOpacity(1.0)
                self.setGeometry(self._saved_geo)
                self.hide()

            group.finished.connect(_on_finished)
            group.start()
            self._anim_group = group
        except Exception:
            self.hide()

    def _animate_restore(self):
        """Anima la ventana desde el dock hacia su posición original."""
        try:
            if not hasattr(self, '_saved_geo'): return
            _c = __import__('importlib').import_module(_QT_BACKEND + '.QtCore')
            QPropertyAnimation = _c.QPropertyAnimation
            QEasingCurve = _c.QEasingCurve
            QRect = _c.QRect
            QParallelAnimationGroup = _c.QParallelAnimationGroup

            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    start_x = tg.x() + tg.width() // 2 - 60
                    start_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                from PySide6.QtWidgets import QApplication
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                start_x = sg.x() + sg.width() // 2 - 60
                start_y = sg.y() + sg.height() - 50
            
            start_geo = QRect(start_x, start_y, 120, 30)
            end_geo = self._saved_geo

            self.setGeometry(start_geo)
            self.setWindowOpacity(0.0)

            group = QParallelAnimationGroup(self)

            anim_geo = QPropertyAnimation(self, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(start_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.OutCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.OutCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(self, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(0.0)
            anim_op.setEndValue(1.0)
            group.addAnimation(anim_op)

            group.start()
            self._anim_group = group
        except Exception:
            pass

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
