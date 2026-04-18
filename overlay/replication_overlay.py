"""
replication_overlay.py — Ventana overlay de replicación de una ventana EVE.

Captura una región relativa de una ventana EVE y la muestra como overlay
flotante always-on-top, actualizado N veces por segundo via QTimer.

Características:
  - Frameless + transparent + always-on-top
  - Drag con click izquierdo (en modo interactivo)
  - Resize desde bordes/esquinas
  - Toggle click-through (modo pasivo)
  - Controles flotantes que aparecen al pasar el ratón
  - Auto-guardado de posición/tamaño al mover/redimensionar
"""

from __future__ import annotations
import sys
import threading
from pathlib import Path
from typing import Optional, Callable

# Garantizar que el directorio raíz del proyecto esté en sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Qt shim
_qt_ok = False
for _qt_try in [
    ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
    ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
    ('PySide2', 'PySide2.QtWidgets', 'PySide2.QtCore', 'PySide2.QtGui'),
    ('PyQt5',   'PyQt5.QtWidgets',   'PyQt5.QtCore',   'PyQt5.QtGui'),
]:
    try:
        import importlib
        _w = importlib.import_module(_qt_try[1])
        _c = importlib.import_module(_qt_try[2])
        _g = importlib.import_module(_qt_try[3])
        for _n in ['QApplication', 'QWidget', 'QVBoxLayout', 'QHBoxLayout',
                   'QLabel', 'QPushButton', 'QSizePolicy', 'QSlider',
                   'QFrame', 'QSizeGrip']:
            if hasattr(_w, _n): globals()[_n] = getattr(_w, _n)
        for _n in ['Qt', 'QTimer', 'QThread', 'pyqtSignal', 'Signal',
                   'QPoint', 'QSize', 'QRect', 'QSettings']:
            if hasattr(_c, _n): globals()[_n] = getattr(_c, _n)
        for _n in ['QColor', 'QPainter', 'QBrush', 'QPen', 'QPixmap',
                   'QImage', 'QFont', 'QCursor', 'QIcon']:
            if hasattr(_g, _n): globals()[_n] = getattr(_g, _n)
        if 'Signal' not in globals() and 'pyqtSignal' in globals():
            Signal = pyqtSignal
        _qt_ok = True
        break
    except ImportError:
        continue

from overlay.win32_capture import capture_window_region, IS_WINDOWS


# ── Constantes de diseño ──────────────────────────────────────────────────────
BORDER_RESIZE_PX = 8    # píxeles en el borde para activar resize
CTRL_BAR_H       = 24   # altura de la barra de controles
C = {
    'bg':       QColor(4, 8, 16, 255),  # Fondo sólido y oscuro
    'border':   QColor(0, 180, 255, 120),
    'hover':    QColor(0, 255, 180, 200),
    'ctrl_bg':  QColor(13, 22, 38, 240),
    'text':     QColor(225, 235, 245, 255),
    'accent':   QColor(0, 200, 255, 255),
}


class CaptureThread(QThread):
    """
    Hilo de captura de frames. Thread-safe mediante Lock en set_output_size.
    """
    frame_ready = Signal(object)   # QImage

    def __init__(self, hwnd_getter: Callable[[], Optional[int]],
                 region_rel: dict, fps: int = 10):
        super().__init__()
        self._hwnd_getter = hwnd_getter
        self._region      = region_rel
        self._fps         = fps
        self._running     = True
        self._paused      = False
        self._out_w       = 400
        self._out_h       = 300
        import threading as _th
        self._size_lock   = _th.Lock()   # protege _out_w/_out_h

    def set_output_size(self, w: int, h: int):
        with self._size_lock:
            self._out_w = max(10, w)
            self._out_h = max(10, h)

    def _get_output_size(self):
        with self._size_lock:
            return self._out_w, self._out_h

    def pause(self):   self._paused = True
    def resume(self):  self._paused = False

    def stop(self):
        self._running = False
        self.wait(2000)  # esperar hasta 2s antes de forzar

    def run(self):
        import time
        interval = 1.0 / max(1, self._fps)
        while self._running:
            t0 = time.perf_counter()
            if not self._paused:
                try:
                    hwnd = self._hwnd_getter()
                    if hwnd:
                        out_w, out_h = self._get_output_size()
                        raw = capture_window_region(
                            hwnd, self._region, out_w, out_h
                        )
                        if raw:
                            img = QImage(raw, out_w, out_h,
                                         out_w * 4,
                                         QImage.Format.Format_RGB32
                                         if hasattr(QImage, 'Format') else QImage.Format_RGB32)
                            self.frame_ready.emit(img.copy())
                except Exception:
                    pass
            elapsed = time.perf_counter() - t0
            sleep_t = max(0, interval - elapsed)
            if sleep_t > 0:
                time.sleep(sleep_t)


class ResizeHandle:
    """Helper para calcular la dirección de resize según posición del cursor."""
    NONE = 0
    LEFT = 1; RIGHT = 2; TOP = 4; BOTTOM = 8
    TL = TOP | LEFT; TR = TOP | RIGHT
    BL = BOTTOM | LEFT; BR = BOTTOM | RIGHT

    @staticmethod
    def detect(pos: QPoint, rect: QRect, margin: int) -> int:
        x, y = pos.x(), pos.y()
        w, h = rect.width(), rect.height()
        d = ResizeHandle.NONE
        if x < margin:          d |= ResizeHandle.LEFT
        elif x > w - margin:    d |= ResizeHandle.RIGHT
        if y < margin:          d |= ResizeHandle.TOP
        elif y > h - margin:    d |= ResizeHandle.BOTTOM
        return d

    @staticmethod
    def cursor(direction: int) -> 'Qt.CursorShape':
        CShape = Qt.CursorShape if hasattr(Qt, 'CursorShape') else Qt
        _map = {
            ResizeHandle.LEFT:  getattr(CShape, 'SizeHorCursor', 0),
            ResizeHandle.RIGHT: getattr(CShape, 'SizeHorCursor', 0),
            ResizeHandle.TOP:   getattr(CShape, 'SizeVerCursor', 0),
            ResizeHandle.BOTTOM:getattr(CShape, 'SizeVerCursor', 0),
            ResizeHandle.TL:    getattr(CShape, 'SizeFDiagCursor', 0),
            ResizeHandle.BR:    getattr(CShape, 'SizeFDiagCursor', 0),
            ResizeHandle.TR:    getattr(CShape, 'SizeBDiagCursor', 0),
            ResizeHandle.BL:    getattr(CShape, 'SizeBDiagCursor', 0),
        }
        return _map.get(direction,
                        getattr(CShape, 'ArrowCursor',
                                getattr(Qt, 'ArrowCursor', 0)))


class ReplicationOverlay(QWidget):
    """
    Overlay individual que replica una región de una ventana EVE.

    Ciclo de vida:
      1. Creación con hwnd + región + config
      2. CaptureThread captura frames y los envía via Signal
      3. paintEvent dibuja el frame + borde + controles (si hover)
      4. Al cerrar, emite closed(title) para que el manager limpie
    """
    closed = Signal(str)      # emite el título al cerrarse

    def __init__(self, title: str, hwnd_getter: Callable[[], Optional[int]],
                 region_rel: dict, cfg: dict, save_callback: Callable):
        super().__init__()
        self._title        = title
        self._hwnd_getter  = hwnd_getter
        self._region       = region_rel
        self._cfg          = cfg
        self._save_cb      = save_callback
        self._frame        = None       # QPixmap actual
        self._click_through = False
        self._hovering     = False

        # Estado de drag/resize
        self._drag_pos    = None
        self._resize_dir  = ResizeHandle.NONE
        self._resize_origin_global = None
        self._resize_origin_geom   = None
        
        # Modo compacto (oculta barra)
        self._is_compact = False
        
        # UI de Controles (HUD flotante)
        self._setup_hud()

        self._setup_window()
        self._restore_state()
        self._start_capture()

        # Timer de Persistencia Always-on-Top (Nivel Win32)
        import ctypes
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(1500)

    def _setup_hud(self):
        self._hud = QFrame(self)
        self._hud.setFixedHeight(CTRL_BAR_H)
        # Borde y fondo estilo neón
        self._hud.setStyleSheet(f"QFrame {{ background: rgba(13, 22, 38, 220); border: 1px solid rgba(0, 180, 255, 120); border-radius: 4px; }}")
        self._hud.move(5, 5)
        self._hud.hide() # Solo se muestra al hacer hover
        
        hl = QHBoxLayout(self._hud)
        hl.setContentsMargins(5, 0, 5, 0); hl.setSpacing(8)
        
        # Título corto
        lbl = QLabel(self._title[:15] + "...")
        lbl.setStyleSheet(f"color: #00c8ff; font-size: 10px; font-weight: bold; border:none; background:transparent;")
        hl.addWidget(lbl)
        
        hl.addStretch()
        
        btn_style = "QPushButton { background: transparent; border: none; color: #fff; font-size: 12px; font-weight: bold; } QPushButton:hover { color: #00ff9d; }"
        
        # Controles de opacidad
        BTN_STYLE = "QPushButton { background: transparent; border: none; color: #fff; font-size: 12px; font-weight: bold; } QPushButton:hover { color: #00ff9d; }"
        
        self._btn_op_up = QPushButton("+", self._hud); self._btn_op_up.setFixedSize(22, 22)
        self._btn_op_up.setStyleSheet(BTN_STYLE); self._btn_op_up.clicked.connect(lambda: self._adj_opacity(0.1))
        hl.addWidget(self._btn_op_up)
        
        self._btn_op_down = QPushButton("-", self._hud); self._btn_op_down.setFixedSize(22, 22)
        self._btn_op_down.setStyleSheet(BTN_STYLE); self._btn_op_down.clicked.connect(lambda: self._adj_opacity(-0.1))
        hl.addWidget(self._btn_op_down)
        
        hl.addStretch()
        
        # Botón cerrar
        self._btn_close = QPushButton("\u00d7", self._hud); self._btn_close.setFixedSize(22, 22)
        self._btn_close.setStyleSheet("QPushButton { background: transparent; border: none; color: #ff6666; font-size: 18px; } QPushButton:hover { color: #ff0000; }")
        self._btn_close.clicked.connect(self.close)
        hl.addWidget(self._btn_close)
        
        self._hud.hide()

        # [NUEVO] Marcador visual de redimensionado (Triángulo Neón)
        self._resizer_marker = QLabel(self)
        self._resizer_marker.setText("◢")
        self._resizer_marker.setStyleSheet("color: rgba(0, 200, 255, 0.7); font-size: 14px; background: transparent;")
        self._resizer_marker.setFixedSize(16, 16)
        # WA_TransparentForMouseEvents para que no bloquee el resize real
        self._resizer_marker.setAttribute(Qt.WA_TransparentForMouseEvents if hasattr(Qt, 'WA_TransparentForMouseEvents') else Qt.WidgetAttribute(0x4000000))
        self._resizer_marker.hide() # Solo se ve en hover

    def _toggle_compact(self):
        self._is_compact = not self._is_compact
        self.update()

    def _reassert_topmost(self):
        try:
            import ctypes
            hwnd = int(self.winId())
            # HWND_TOPMOST = -1, SWP_NOMOVE = 2, SWP_NOSIZE = 1, SWP_NOACTIVATE = 0x10
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except: pass

    def _setup_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        ) if hasattr(Qt, 'WindowType') else (
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setWindowFlags(flags)
        self.setMinimumSize(30, 30)
        self.setMouseTracking(True)
        self.setWindowTitle(f"EVE Replica: {self._title}")
        self.setStyleSheet("background-color: rgb(8, 14, 26); border-radius: 0px;")
        
        try:
            import ctypes
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_DONOTROUND = 1
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), DWMWA_WINDOW_CORNER_PREFERENCE, 
                ctypes.byref(ctypes.c_int(DWMWCP_DONOTROUND)), 4
            )
        except: pass

    def _restore_state(self):
        state = self._cfg.get('overlays', {}).get(self._title)
        glob  = self._cfg.get('global', {})
        if state:
            self.move(state.get('x', 100), state.get('y', 100))
            w, h = state.get('w', 400), state.get('h', 300)
        else:
            w, h = glob.get('default_size', [400, 300])
        
        ratio = self._region['w'] / max(0.01, self._region['h'])
        if w / h > ratio: w = h * ratio
        else: h = w / ratio
        
        self.resize(int(w), int(h))
        self.setWindowOpacity(1.0)

    # ── Captura ───────────────────────────────────────────────────────────────

    def _start_capture(self):
        # PrintWindow es más lento que BitBlt — límite de 5fps por defecto
        fps = min(self._cfg.get('global', {}).get('capture_fps', 10), 10)
        self._capture = CaptureThread(self._hwnd_getter, self._region, fps)
        self._capture.set_output_size(self.width(), self.height())
        self._capture.frame_ready.connect(self._on_frame)
        self._capture.start()

    def _on_frame(self, img: 'QImage'):
        """Recibe frame del hilo de captura y fuerza redibujado."""
        self._frame = QPixmap.fromImage(img)
        self.update()

    # ── Pintura ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(
            QPainter.RenderHint.Antialiasing
            if hasattr(QPainter, 'RenderHint') else QPainter.Antialiasing
        )

        r = self.rect()

        # Fondo sólido siempre (evita transparencia aunque el frame tenga alpha=0)
        p.fillRect(r, C['bg'])

        if self._frame:
            # Dibujar manteniendo relación de aspecto para evitar deformación
            target = r.adjusted(1, 1, -1, -1)
            scaled = self._frame.scaled(target.size(), 
                                        Qt.AspectRatioMode.KeepAspectRatio 
                                        if hasattr(Qt, 'AspectRatioMode') else Qt.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation
                                        if hasattr(Qt, 'TransformationMode') else Qt.SmoothTransformation)
            
            # Centrar la imagen en la ventana
            offset_x = (target.width() - scaled.width()) // 2
            offset_y = (target.height() - scaled.height()) // 2
            p.drawPixmap(target.left() + offset_x, target.top() + offset_y, scaled)
        else:
            p.setPen(QPen(C['text']))
            p.setFont(QFont('Consolas', 9))
            align = Qt.AlignmentFlag.AlignCenter if hasattr(Qt, 'AlignmentFlag') else Qt.AlignCenter
            p.drawText(r, align, f"Buscando ventana...\n{self._title}")

        # Borde (solo se ve si no es compacto o si hay hover)
        if not self._is_compact or self._hovering:
            border_color = C['hover'] if self._hovering else C['border']
            p.setPen(QPen(border_color, 1))
            p.drawRect(r.adjusted(0, 0, -1, -1))

    def resizeEvent(self, event):
        # Actualizar tamaño de captura (thread-safe via Lock)
        if hasattr(self, '_capture'):
            # El área de captura ahora es la ventana completa
            self._capture.set_output_size(self.width(), self.height())
        
        # Posicionar marcador de resizer
        if hasattr(self, '_resizer_marker'):
            self._resizer_marker.move(self.width() - 14, self.height() - 14)
            
        self._save_state()

    # ── Controles ─────────────────────────────────────────────────────────────

    # ── Drag desde la barra de título ─────────────────────────────────────────

    def _ctrl_bar_press(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.button() == left:
            self._drag_pos = (event.globalPosition().toPoint()
                              if hasattr(event, 'globalPosition') else event.globalPos())

    def _ctrl_bar_move(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.buttons() & left and self._drag_pos:
            gp = (event.globalPosition().toPoint()
                  if hasattr(event, 'globalPosition') else event.globalPos())
            self.move(self.pos() + gp - self._drag_pos)
            self._drag_pos = gp

    def _ctrl_bar_release(self, event):
        self._drag_pos = None
        self._save_state()

    def _adj_opacity(self, delta: float):
        op = max(0.2, min(1.0, self.windowOpacity() + delta))
        self.setWindowOpacity(op)
        self._save_state()

    # ── Drag & resize ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.button() == left:
            pos = event.pos()
            dir = ResizeHandle.detect(pos, self.rect(), BORDER_RESIZE_PX)
            if dir != ResizeHandle.NONE:
                self._resize_dir = dir
                self._resize_origin_global = (
                    event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition') else event.globalPos()
                )
                self._resize_origin_geom = self.geometry()
            else:
                self._drag_pos = (
                    event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition') else event.globalPos()
                )

    def mouseMoveEvent(self, event):
        pos = event.pos()
        gpos = (event.globalPosition().toPoint()
                if hasattr(event, 'globalPosition') else event.globalPos())
        btn = event.buttons()
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton

        if btn & left:
            if self._resize_dir != ResizeHandle.NONE:
                self._do_resize(gpos)
            elif self._drag_pos:
                self.move(self.pos() + gpos - self._drag_pos)
                self._drag_pos = gpos
        else:
            # Solo hover → actualizar cursor
            dir = ResizeHandle.detect(pos, self.rect(), BORDER_RESIZE_PX)
            self.setCursor(QCursor(ResizeHandle.cursor(dir)))

    def mouseReleaseEvent(self, event):
        self._drag_pos        = None
        self._resize_dir      = ResizeHandle.NONE
        self._resize_origin_global = None
        self._resize_origin_geom   = None
        self._save_state()

    def _do_resize(self, gpos: QPoint):
        if not self._resize_origin_global:
            return
        dx = gpos.x() - self._resize_origin_global.x()
        dy = gpos.y() - self._resize_origin_global.y()
        g  = self._resize_origin_geom
        R  = ResizeHandle
        d  = self._resize_dir
        nx, ny, nw, nh = g.x(), g.y(), g.width(), g.height()

        if d & R.LEFT:   nx += dx; nw -= dx
        if d & R.RIGHT:  nw += dx
        if d & R.TOP:    ny += dy; nh -= dy
        if d & R.BOTTOM: nh += dy

        # MANTENER RELACIÓN DE ASPECTO
        ratio = self._region['w'] / max(0.01, self._region['h'])
        if d & (R.LEFT | R.RIGHT):
            nh = nw / ratio
        elif d & (R.TOP | R.BOTTOM):
            nw = nh * ratio

        nw = max(self.minimumWidth(),  nw)
        nh = max(self.minimumHeight(), nh)
        self.setGeometry(nx, ny, nw, nh)

    # ── Hover (controles) ─────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovering = True
        if hasattr(self, '_hud'): self._hud.show()
        if hasattr(self, '_resizer_marker'): self._resizer_marker.show()
        self.update()

    def leaveEvent(self, event):
        self._hovering = False
        if hasattr(self, '_hud'): self._hud.hide()
        if hasattr(self, '_resizer_marker'): self._resizer_marker.hide()
        self.update()

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _save_state(self):
        self._save_cb(
            self._title,
            self.x(), self.y(),
            self.width(), self.height(),
            self.windowOpacity(),
            False,   # click_through siempre False
        )

    # ── Cierre ────────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)

    def closeEvent(self, event):
        self._save_state()
        if hasattr(self, '_capture'):
            self._capture.stop()
        self.closed.emit(self._title)
        event.accept()
