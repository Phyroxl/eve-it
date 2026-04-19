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

import logging
logger = logging.getLogger('eve.overlay')


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
    selection_requested = Signal(object) # [NUEVO] para reabrir el selector de región

    def __init__(self, title: str, hwnd_getter: Callable[[], Optional[int]],
                 region_rel: dict, cfg: dict, save_callback: Callable):
        super().__init__()
        self._title        = title
        self._hwnd_getter  = hwnd_getter
        self._region       = region_rel
        self._cfg          = cfg
        self._save_cb      = save_callback
        self._frame_lock   = threading.Lock() # [NUEVO] Evitar crashes por concurrencia
        self._click_through = False
        self._interactive    = False  # [NUEVO] Modo portal (broadcasting)
        self._hovering     = False
        self._flash_pos    = None  # [NUEVO] Para feedback visual de click
        self._offset_calib = {'x': 0, 'y': 0} # [NUEVO] Calibración manual

        # Estado de drag/resize
        self._drag_pos    = None
        self._resize_dir  = ResizeHandle.NONE
        self._resize_origin_global = None
        self._resize_origin_geom   = None
        self._is_moving_or_resizing = False # [NUEVO] Para mantener borde visible
        
        # Modo compacto (oculta barra)
        self._is_compact = False
        
        self._restore_state()
        self._start_capture()
        
        self._setup_window()
        
        # Cargar calibración si existe
        ov_cfg = self._cfg.get('overlays', {}).get(self._title, {})
        self._offset_calib = ov_cfg.get('offset_calib', {'x': 0, 'y': 0})
        
        # UI de Controles (HUD flotante) - Al final para asegurar que esté encima
        self._setup_hud()

        # Timer de Persistencia Always-on-Top (Nivel Win32)
        import ctypes
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(1500)

    def _setup_hud(self):
        self._hud = QFrame(self)
        self._hud.setFixedHeight(CTRL_BAR_H)
        # Fondo ultra-minimalista sin bordes molestos
        self._hud.setStyleSheet("QFrame { background: rgba(0, 20, 40, 180); border: none; border-radius: 4px; }")
        self._hud.move(5, 5)
        self._hud.hide() # Solo se muestra al hacer hover
        
        hl = QHBoxLayout(self._hud)
        hl.setContentsMargins(5, 0, 5, 0); hl.setSpacing(8)
        
        # Título removido según solicitud del usuario
        hl.addStretch()
        
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
        
        # Botón Interactivo (Portal) [NUEVO]
        self._btn_interact = QPushButton("🔗", self._hud); self._btn_interact.setFixedSize(22, 22)
        self._btn_interact.setToolTip("Activar Modo Portal (Click-through al juego)")
        self._btn_interact.setStyleSheet("QPushButton { background: transparent; border: none; color: #888; font-size: 14px; }")
        self._btn_interact.clicked.connect(self._toggle_interactive)
        hl.addWidget(self._btn_interact)
        
        # Botón cerrar
        self._btn_close = QPushButton("\u00d7", self._hud); self._btn_close.setFixedSize(22, 22)
        self._btn_close.setStyleSheet("QPushButton { background: transparent; border: none; color: #ff6666; font-size: 18px; } QPushButton:hover { color: #ff0000; }")
        self._btn_close.clicked.connect(self.close)
        hl.addWidget(self._btn_close)
        
        self._hud.hide()
        self._hud.raise_() # Asegurar que esté encima de la pintura de fondo

        # [NUEVO] Marcador visual de redimensionado (Triángulo Neón)
        self._resizer_marker = QLabel(self)
        self._resizer_marker.setText("◢")
        self._resizer_marker.setStyleSheet("color: rgba(0, 200, 255, 0.7); font-size: 14px; background: transparent;")
        self._resizer_marker.setFixedSize(16, 16)
        # WA_TransparentForMouseEvents para que no bloquee el resize real
        self._resizer_marker.setAttribute(Qt.WA_TransparentForMouseEvents if hasattr(Qt, 'WA_TransparentForMouseEvents') else Qt.WidgetAttribute(0x4000000))
        self._resizer_marker.hide() # Solo se ve en hover

    def _toggle_interactive(self):
        self._interactive = not self._interactive
        logger.info(f"Portal [{self._title}]: {'ACTIVADO' if self._interactive else 'DESACTIVADO'}")
        color = "#00ff9d" if self._interactive else "#888"
        self._btn_interact.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: {color}; font-size: 14px; }}")
        # Cambiar el cursor si el modo está activo para dar feedback visual
        if self._interactive:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor if hasattr(Qt, 'CursorShape') else Qt.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor if hasattr(Qt, 'CursorShape') else Qt.ArrowCursor))
        self.update()

    def _clear_flash(self):
        self._flash_pos = None
        self.update()

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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground if hasattr(Qt, 'WidgetAttribute') else Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        
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

    def stop(self):
        """Detiene la captura y cierra el hilo."""
        if hasattr(self, '_capture'):
            try:
                self._capture.stop()
                self._capture.wait(500)
            except: pass
        self.close()

    def closeEvent(self, event):
        """Asegurar que el hilo se detiene al cerrar la ventana."""
        if hasattr(self, '_capture'):
            try:
                self._capture.stop()
                self._capture.wait(300)
            except: pass
        event.accept()

    def _start_capture(self):
        # PrintWindow es más lento que BitBlt — límite de 5fps por defecto
        fps = min(self._cfg.get('global', {}).get('capture_fps', 10), 10)
        self._capture = CaptureThread(self._hwnd_getter, self._region, fps)
        self._capture.set_output_size(self.width(), self.height())
        self._capture.frame_ready.connect(self._on_frame)
        self._capture.start()

    def _on_frame(self, img: 'QImage'):
        """Recibe frame del hilo de captura y fuerza redibujado."""
        with self._frame_lock:
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

        # Fondo sutil para asegurar que el widget reciba clicks (algunas GPUs ignoran clicks en 100% transparente)
        p.fillRect(r, QColor(0, 0, 0, 1))

        with self._frame_lock:
            if self._frame:
                # USAR STRETCH para permitir "libre ajuste" y que el mapeo de clicks sea 100% exacto
                # Dibujamos ocupando todo el rectángulo interior (ajustado por el borde de 1px)
                p.drawPixmap(r.adjusted(1, 1, -1, -1), self._frame)
            else:
                p.setPen(QPen(C['text']))
                p.setFont(QFont('Consolas', 9))
                align = Qt.AlignmentFlag.AlignCenter if hasattr(Qt, 'AlignmentFlag') else Qt.AlignCenter
                p.drawText(r, align, f"Buscando ventana...\n{self._title}")
        # Fin de zona crítica de frame_lock
        # Fin de zona crítica de frame_lock

        # Borde (se ve si hay hover O si estamos operando la ventana)
        if self._hovering or self._is_moving_or_resizing:
            border_color = C['hover']
            p.setPen(QPen(border_color, 2))
            p.drawRect(r.adjusted(0, 0, -1, -1))

        # Feedback de click
        if hasattr(self, '_flash_pos') and self._flash_pos:
            p.setPen(QPen(QColor(0, 255, 150, 200), 2))
            p.drawEllipse(self._flash_pos, 4, 4)

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
        # Si el click es sobre el HUD, dejar que Qt lo maneje normalmente (para los botones)
        if self._hud.isVisible() and self._hud.geometry().contains(event.pos()):
            super().mousePressEvent(event)
            return

        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.button() == left:
            # Si estamos en modo interactivo O se pulsa Shift (cambiado de Ctrl), enviamos el click al juego
            modifiers = QApplication.keyboardModifiers()
            shift = Qt.KeyboardModifier.ShiftModifier if hasattr(Qt, 'KeyboardModifier') else 0x02000000
            
            if self._interactive or (modifiers & shift):
                self._broadcast_click(event.pos())
                return

            self._is_moving_or_resizing = True
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

    def _broadcast_click(self, pos: QPoint):
        """Mapea y envía el click a la ventana original con máxima precisión."""
        hwnd = self._hwnd_getter()
        if not hwnd or not IS_WINDOWS: return
        
        try:
            import ctypes
            from ctypes import wintypes
            
            # 1. Obtener tamaño del cliente original en tiempo real para reajuste exacto
            rect = wintypes.RECT()
            ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
            w_src = rect.right - rect.left
            h_src = rect.bottom - rect.top
            if w_src <= 0 or h_src <= 0: return

            # 2. Mapeo de coordenadas locales del widget a coordenadas de la imagen
            # El overlay dibuja la imagen en rect().adjusted(1, 1, -1, -1)
            # Para un widget de width W, el área de dibujo es de x=1 a x=W-2 (inclusive)
            # El ancho de esa área es (W-2) píxeles.
            # Los índices de píxel van de 0 a (W-3).
            
            draw_w = self.width() - 2
            draw_h = self.height() - 2
            
            if draw_w <= 1 or draw_h <= 1: return # Evitar división por cero

            # Coordenadas relativas dentro del área de dibujo (0.0 a 1.0)
            # Restamos 1 porque el dibujo empieza en x=1
            rx = (pos.x() - 1) / (draw_w - 1)
            ry = (pos.y() - 1) / (draw_h - 1)
            
            # Clamp para asegurar que no salimos de la región
            rx = max(0.0, min(1.0, rx))
            ry = max(0.0, min(1.0, ry))

            # 3. Mapear a coordenadas de la ventana original
            # Usamos (w_src - 1) porque los índices de píxel van de 0 a Ancho-1
            tx = int((self._region['x'] + rx * self._region['w']) * (w_src - 1)) + self._offset_calib['x']
            ty = int((self._region['y'] + ry * self._region['h']) * (h_src - 1)) + self._offset_calib['y']

            # 4. Enviar el click mediante Win32
            lparam = (ty << 16) | (tx & 0xFFFF)
            WM_ACTIVATE    = 0x0006
            WA_ACTIVE      = 1
            WM_MOUSEMOVE   = 0x0200
            WM_LBUTTONDOWN = 0x0201
            WM_LBUTTONUP   = 0x0202
            MK_LBUTTON     = 0x0001
            
            # Enviar secuencia completa para asegurar que el juego procesa el click correctamente
            # Usamos SendMessage para el UP para asegurar que se procesa antes de volver
            ctypes.windll.user32.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0)
            ctypes.windll.user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
            ctypes.windll.user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            # Pequeña redundancia para asegurar el "Up" en juegos con lag de input
            ctypes.windll.user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
            ctypes.windll.user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
            
            # Feedback visual del click en el overlay
            self._flash_pos = pos
            QTimer.singleShot(150, self._clear_flash)
            self.update()
            
        except Exception as e:
            logger.error(f"Error en broadcast: {e}")

    def contextMenuEvent(self, event):
        """Menú de control de la zona replicada (Joystick y Zoom)."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #080e1a; border: 1px solid #00c8ff; color: #fff; padding: 5px; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background: rgba(0, 200, 255, 0.2); }
            QMenu::separator { height: 1px; background: rgba(0, 200, 255, 0.2); margin: 5px 0; }
        """)
        
        # Joystick de Movimiento
        move_up = menu.addAction("▲ Mover Arriba")
        move_dn = menu.addAction("▼ Mover Abajo")
        move_lf = menu.addAction("◀ Mover Izquierda")
        move_rg = menu.addAction("▶ Mover Derecha")
        
        menu.addSeparator()
        
        # Zoom
        zoom_in = menu.addAction("🔍 Acercar (Zoom +)")
        zoom_out = menu.addAction("🔍 Alejar (Zoom -)")
        
        menu.addSeparator()
        
        # Calibración Manual
        calib_menu = menu.addMenu("🎯 Calibración de Click")
        c_up = calib_menu.addAction("Mover Click Arriba")
        c_dn = calib_menu.addAction("Mover Click Abajo")
        c_lf = calib_menu.addAction("Mover Click Izquierda")
        c_rg = calib_menu.addAction("Mover Click Derecha")
        calib_menu.addSeparator()
        c_rs = calib_menu.addAction("Resetear Calibración")
        
        menu.addSeparator()
        
        # Reset
        restart_cap = menu.addAction("(Cambiar Zona)")
        reset_reg = menu.addAction("🔄 Resetear Zona (100%)")
        # Compacto eliminado según solicitud
        
        # Ejecutar menú
        action = menu.exec(event.globalPos())
        
        step = 0.005 # Reducido para máxima precisión (0.5% por click)
        if action == move_up:    self._move_region(0, -step)
        elif action == move_dn:  self._move_region(0, step)
        elif action == move_lf:  self._move_region(-step, 0)
        elif action == move_rg:  self._move_region(step, 0)
        elif action == zoom_in:  self._zoom_region(0.9)
        elif action == zoom_out: self._zoom_region(1.1)
        elif action == restart_cap: self.selection_requested.emit(self)
        elif action == reset_reg: self._reset_region()
        
        # Acciones de Calibración
        c_step = 5 # píxeles
        if action == c_up:    self._offset_calib['y'] -= c_step
        elif action == c_dn:  self._offset_calib['y'] += c_step
        elif action == c_lf:  self._offset_calib['x'] -= c_step
        elif action == c_rg:  self._offset_calib['x'] += c_step
        elif action == c_rs:  self._offset_calib.update({'x':0, 'y':0})
        if action in [c_up, c_dn, c_lf, c_rg, c_rs]:
            logger.info(f"Calibración manual: {self._offset_calib}")
            self._save_state()

    def _restart_capture_thread(self):
        """Detiene y reinicia el hilo de captura."""
        logger.info(f"Reiniciando captura para {self._title}")
        if hasattr(self, '_capture'):
            self._capture.stop()
            self._capture.wait(500)
        self._start_capture()
        self.update()

    def _move_region(self, dx, dy):
        self._region['x'] = max(0.0, min(1.0 - self._region['w'], self._region['x'] + dx))
        self._region['y'] = max(0.0, min(1.0 - self._region['h'], self._region['y'] + dy))
        self._save_state()

    def _zoom_region(self, factor):
        # Zoom centrado
        old_w, old_h = self._region['w'], self._region['h']
        new_w = max(0.01, min(1.0, old_w * factor))
        new_h = max(0.01, min(1.0, old_h * factor))
        
        # Ajustar x, y para que el zoom sea hacia el centro de la zona actual
        self._region['x'] += (old_w - new_w) / 2
        self._region['y'] += (old_h - new_h) / 2
        
        self._region['w'], self._region['h'] = new_w, new_h
        # Clamp final
        self._region['x'] = max(0.0, min(1.0 - new_w, self._region['x']))
        self._region['y'] = max(0.0, min(1.0 - new_h, self._region['y']))
        
        self._save_state()

    def _reset_region(self):
        self._region.update({'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 1.0})
        self._save_state()

    def keyPressEvent(self, event):
        """Atajos de teclado para mover la región con alta precisión."""
        step = 0.005 # Paso ultra-fino
        k = event.key()
        Key = Qt.Key if hasattr(Qt, 'Key') else Qt
        
        if k == getattr(Key, 'Key_Up', 0x01000013):    self._move_region(0, -step)
        elif k == getattr(Key, 'Key_Down', 0x01000015):  self._move_region(0, step)
        elif k == getattr(Key, 'Key_Left', 0x01000012):  self._move_region(-step, 0)
        elif k == getattr(Key, 'Key_Right', 0x01000014): self._move_region(step, 0)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Zoom con scroll del ratón."""
        # Detectar dirección del scroll
        delta = event.angleDelta().y() if hasattr(event, 'angleDelta') else event.delta()
        if delta > 0:
            self._zoom_region(0.95) # Acercar
        else:
            self._zoom_region(1.05) # Alejar
        event.accept()

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
        self._is_moving_or_resizing = False
        self._save_state()
        self.update()

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

        # ELIMINADO EL BLOQUEO DE ASPECTO PARA PERMITIR "LIBRE AJUSTE"

        nw = max(self.minimumWidth(),  nw)
        nh = max(self.minimumHeight(), nh)
        self.setGeometry(nx, ny, nw, nh)

    # ── Hover (controles) ─────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovering = True
        # Enfoque automático para permitir interacción con 1 solo click
        self.setFocus(Qt.MouseFocusReason if hasattr(Qt, 'MouseFocusReason') else Qt.OtherFocusReason)
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
        # Actualizar el hilo de captura si existe
        if hasattr(self, '_capture'):
            self._capture._region = self._region
            
        self._save_cb(
            self._title,
            self.x(), self.y(),
            self.width(), self.height(),
            self.windowOpacity(),
            False,   # click_through siempre False
        )
        # Guardar también la región específica y calibración
        if 'overlays' not in self._cfg: self._cfg['overlays'] = {}
        if self._title not in self._cfg['overlays']: self._cfg['overlays'][self._title] = {}
        self._cfg['overlays'][self._title]['region'] = self._region.copy()
        self._cfg['overlays'][self._title]['offset_calib'] = self._offset_calib.copy()

    # ── Cierre ────────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)

    def closeEvent(self, event):
        self._save_state()
        if hasattr(self, '_capture'):
            self._capture.stop()
        self.closed.emit(self._title)
        event.accept()
