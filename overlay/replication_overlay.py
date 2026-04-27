import logging
import time
import threading
from pathlib import Path
from typing import Optional

# Configuración de logs
logger = logging.getLogger('eve.overlay')

# Qt shim
_qt_ok = False
for _qt_try in [
    ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
    ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
]:
    try:
        import importlib
        _w = importlib.import_module(_qt_try[1])
        _c = importlib.import_module(_qt_try[2])
        _g = importlib.import_module(_qt_try[3])
        for _n in ['QApplication', 'QWidget', 'QLabel', 'QMenu']:
            if hasattr(_w, _n): globals()[_n] = getattr(_w, _n)
        for _n in ['Qt', 'QTimer', 'QThread', 'Signal', 'Slot', 'QPoint', 'QRect', 'QSize']:
            if hasattr(_c, _n): globals()[_n] = getattr(_c, _n)
        for _n in ['QColor', 'QPainter', 'QPixmap', 'QImage', 'QFont', 'QCursor', 'QPen', 'QAction']:
            if hasattr(_g, _n): globals()[_n] = getattr(_g, _n)
        _qt_ok = True
        break
    except ImportError: continue

if not _qt_ok:
    class QWidget: pass
    class QThread: pass
    def Signal(*args): pass
    def Slot(*args): pass

from overlay.win32_capture import capture_window_region, IS_WINDOWS, resolve_eve_window_handle, set_no_activate, user32

class CaptureThread(QThread):
    frame_ready = Signal(object, int, int) # (data, w, h)
    error_signal = Signal(str)

    def __init__(self, title, hwnd_getter, region, fps=30):
        super().__init__()
        self._title = title
        self._hwnd_getter = hwnd_getter if callable(hwnd_getter) else (lambda: hwnd_getter)
        self._hwnd = None
        self._region = region # Ref al dict
        self._fps = fps
        self._running = True
        self._out_w, self._out_h = 400, 300
        self._lock = threading.Lock()

    def set_output_size(self, w, h):
        with self._lock:
            self._out_w, self._out_h = max(10, w), max(10, h)

    def set_fps(self, fps):
        with self._lock:
            self._fps = max(1, min(120, fps))

    def stop(self):
        self._running = False
        self.wait(500)

    def run(self):
        while self._running:
            t_start = time.perf_counter()
            
            with self._lock:
                w, h = self._out_w, self._out_h
                fps = self._fps

            # Auto-recuperación de handle
            if not self._hwnd or not user32.IsWindow(self._hwnd):
                self._hwnd = self._hwnd_getter()

            # Captura con Supersampling (1.5x) para máxima nitidez en la capa de UI
            sw, sh = int(w * 1.5), int(h * 1.5)
            data = capture_window_region(self._hwnd, self._region, sw, sh)
            
            if data == b"MINIMIZED":
                self.frame_ready.emit(b"MINIMIZED", 0, 0)
            elif data:
                self.frame_ready.emit(data, sw, sh)
            else:
                # Si falla, intentar recuperar el handle (por si cambió el título)
                new_h = resolve_eve_window_handle(self._title)
                if new_h: self._hwnd = new_h
                self.frame_ready.emit(b"ERROR", 0, 0)

            # Control de FPS
            elapsed = time.perf_counter() - t_start
            sleep_time = max(0, (1.0 / fps) - elapsed)
            time.sleep(sleep_time)

class ReplicationOverlay(QWidget):
    selection_requested = Signal(object) # Signal para TrayManager
    closed = Signal(str) # Signal para TrayManager
    sync_triggered = Signal(dict) # Signal para sincronizar vistas
    
    def __init__(self, title, hwnd=None, region_rel=None, cfg=None, save_callback=None, hwnd_getter=None):
        super().__init__(None)
        self._title = title
        self._hwnd_getter = hwnd_getter if hwnd_getter else (lambda: hwnd)
        self._hwnd = hwnd
        self._region = region_rel if region_rel else {'x':0, 'y':0, 'w':1, 'h':1}
        self._cfg = cfg if cfg else {}
        self._save_callback = save_callback
        self._sync_active = False
        
        self._pixmap = None
        self._status = "CONECTANDO..."
        self._drag_pos = None
        self._is_resizing = False
        
        self._setup_ui()
        self._start_capture()

    def _setup_ui(self):
        # Flags de ventana: Sin bordes, siempre arriba, herramienta (no aparece en taskbar)
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool) \
                if hasattr(Qt, 'WindowType') else (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowFlags(flags)
        
        # WA_TranslucentBackground = False para rendimiento (queremos fondo negro opaco si no hay señal)
        self.setAttribute(Qt.WA_TranslucentBackground if hasattr(Qt, 'WA_TranslucentBackground') else 120, False)
        
        self.setMinimumSize(64, 64)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus) # Habilita foco al hacer click
        self.setWindowTitle(f"Replica - {self._title}")
        
        # Estilo premium
        self.setStyleSheet("background-color: #000;")
        
        set_no_activate(int(self.winId()))
        
        # Timer para mantener arriba (Nivel Win32)
        self._top_timer = QTimer(self)
        self._top_timer.timeout.connect(self._reassert_topmost)
        self._top_timer.start(2000)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #0a0a0a; border: 1px solid #00c8ff; color: #fff; padding: 5px; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background: #004466; }
        """)
        
        # Sincronización
        act_sync = menu.addAction("🔗 Sincronizar desde aquí")
        act_sync.setCheckable(True)
        act_sync.setChecked(self._sync_active)
        act_sync.triggered.connect(self._toggle_sync)

        # Submenú de FPS
        fps_menu = menu.addMenu("⚡ Fotogramas (FPS)")
        current_fps = self._thread._fps if hasattr(self, '_thread') else 30
        for val in [5, 10, 30, 60, 120]:
            label = f"{val} FPS"
            if val == current_fps:
                label = f"✓ {label}"
            act = fps_menu.addAction(label)
            act.triggered.connect(lambda _, v=val: self._set_fps(v))

        act_wizard = menu.addAction("🎯 Cambiar Zona")
        act_wizard.triggered.connect(self._relaunch_wizard)
        
        menu.addSeparator()
        
        act_close = menu.addAction("✕ Cerrar")
        act_close.triggered.connect(self.close)
        
        menu.exec(event.globalPos())

    def _reset_view(self):
        self._region['x'] = 0; self._region['y'] = 0
        self._region['w'] = 1.0; self._region['h'] = 1.0 
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)

    def _toggle_sync(self, state):
        self._sync_active = state

    def _set_fps(self, val):
        if hasattr(self, '_thread'):
            self._thread.set_fps(val)
        # Guardar en config si es necesario
        ov_cfg = self._cfg.setdefault('overlays', {}).setdefault(self._title, {})
        ov_cfg['fps'] = val

    def _relaunch_wizard(self):
        # Emitir señal para que TrayManager abra el selector de zona
        self.selection_requested.emit(self)

    def _reassert_topmost(self):
        import ctypes
        try:
            ctypes.windll.user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except: pass

    def _start_capture(self):
        fps = self._cfg.get('overlays', {}).get(self._title, {}).get('fps', 30)
        self._thread = CaptureThread(self._title, self._hwnd_getter, self._region, fps)
        self._thread.set_output_size(self.width(), self.height())
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.start()

    @Slot(object, int, int)
    def _on_frame(self, data, w, h):
        if data == b"MINIMIZED":
            self._status = "MINIMIZADO"
            self._pixmap = None
        elif data == b"ERROR":
            self._status = "SIN SEÑAL"
            self._pixmap = None
        else:
            self._status = ""
            # Format_ARGB32 es el estándar para buffers de 32 bits de GDI
            fmt = QImage.Format.Format_ARGB32 if hasattr(QImage, 'Format') else QImage.Format_ARGB32
            img = QImage(data, w, h, fmt)
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)
        self.update()

    def keyPressEvent(self, event):
        if not self.hasFocus(): return
        
        # Paso de movimiento reducido para máxima suavidad (0.2% normal, 1% rápido)
        step = 0.01 if event.modifiers() & Qt.ShiftModifier else 0.002
        k = event.key()
        
        # Zoom (Ctrl + Arriba/Abajo)
        if event.modifiers() & Qt.ControlModifier:
            if k == Qt.Key_Up:    self._zoom_roi(0.95)
            elif k == Qt.Key_Down:  self._zoom_roi(1.05)
            return

        # Movimiento (Flechas)
        if k == Qt.Key_Up:       self._region['y'] = max(0, self._region['y'] - step)
        elif k == Qt.Key_Down:   self._region['y'] = min(1.0 - self._region['h'], self._region['y'] + step)
        elif k == Qt.Key_Left:   self._region['x'] = max(0, self._region['x'] - step)
        elif k == Qt.Key_Right:  self._region['x'] = min(1.0 - self._region['w'], self._region['x'] + step)
        
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if not self.hasFocus(): return
        
        delta = event.angleDelta().y()
        mods = event.modifiers()
        
        # Obtener posición del ratón relativa a la ventana (0.0 a 1.0)
        pos = event.position() if hasattr(event, 'position') else event.pos()
        mx_rel = pos.x() / self.width()
        my_rel = pos.y() / self.height()

        # Factor de escala reducido (3%) para una transición mucho más suave y estética
        factor = 1.03 if delta > 0 else 0.97
        f_inv = 0.97 if delta > 0 else 1.03
        
        if mods & Qt.ShiftModifier:
            # Solo redimensionamos la ventana. La lógica en resizeEvent se encargará 
            # de "cosechar" más o menos región del juego automáticamente sin estirar.
            self.resize(self.width(), int(self.height() * factor))
        elif mods & Qt.ControlModifier:
            self.resize(int(self.width() * factor), self.height())
        else:
            # Zoom Interno (Lupa) - Aquí sí cambiamos el factor de escala interno
            f_inv_val = 0.97 if delta > 0 else 1.03
            self._zoom_roi_ex(f_inv_val, f_inv_val, mx_rel, my_rel)
            
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)
        event.accept()

    def _zoom_roi_ex(self, f_w, f_h, mx_rel=0.5, my_rel=0.5):
        """Zoom extendido con factores independientes para Ancho y Alto"""
        old_w, old_h = self._region['w'], self._region['h']
        new_w = max(0.01, min(1.0, old_w * f_w))
        new_h = max(0.01, min(1.0, old_h * f_h))
        
        # Punto exacto en el mundo real (coordenadas relativas de la ventana original)
        world_x = self._region['x'] + (mx_rel * old_w)
        world_y = self._region['y'] + (my_rel * old_h)
        
        # Ajustamos el nuevo X e Y para que world_x/world_y sigan bajo el ratón
        self._region['x'] = max(0, min(1.0 - new_w, world_x - (mx_rel * new_w)))
        self._region['y'] = max(0, min(1.0 - new_h, world_y - (my_rel * new_h)))
        self._region['w'], self._region['h'] = new_w, new_h
        
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)

    def apply_region(self, reg_dict):
        """Aplica una región externa (sincronización) y ajusta el tamaño de la ventana para evitar estiramiento."""
        old_w, old_h = self._region['w'], self._region['h']
        new_w, new_h = reg_dict['w'], reg_dict['h']
        
        self._region['x'] = reg_dict['x']
        self._region['y'] = reg_dict['y']
        self._region['w'] = new_w
        self._region['h'] = new_h
        
        # Redimensionar la ventana si la proporción cambió (para evitar el efecto "estirado" en los esclavos)
        if abs(new_w - old_w) > 0.001 or abs(new_h - old_h) > 0.001:
            self.resize(int(self.width() * (new_w / old_w)), int(self.height() * (new_h / old_h)))
            
        self.update()

    def resizeEvent(self, event):
        # Lógica OnTopReplica: "Cosechar" más área del juego al estirar la ventana en lugar de estirar la imagen.
        if hasattr(self, '_thread') and self._thread._running:
            # Calculamos cuánta área relativa del juego representa cada píxel de la ventana actual
            # para mantener la escala visual constante durante el redimensionado manual.
            if event.oldSize().width() > 0 and event.oldSize().height() > 0:
                rw = event.size().width() / event.oldSize().width()
                rh = event.size().height() / event.oldSize().height()
                
                # Ajustamos la región capturada para que crezca/mengue con la ventana
                # Esto evita el efecto "espagueti" al arrastrar los bordes.
                self._region['w'] = max(0.01, min(1.0, self._region['w'] * rw))
                self._region['h'] = max(0.01, min(1.0, self._region['h'] * rh))
                
            self._thread.set_output_size(self.width(), self.height())
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform if hasattr(QPainter.RenderHint, 'SmoothPixmapTransform') else QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing if hasattr(QPainter.RenderHint, 'Antialiasing') else QPainter.Antialiasing)
        
        p.fillRect(self.rect(), Qt.black)
        
        if self._pixmap:
            # Para evitar el estiramiento de un solo frame mientras llega el nuevo recorte:
            # Comprobamos si el pixmap actual coincide con la proporción de la ventana.
            pw, ph = self._pixmap.width(), self._pixmap.height()
            draw_w, draw_h = pw / 1.5, ph / 1.5
            
            # Si el tamaño es casi exacto, dibujamos normal.
            # Si no, dibujamos centrado (esto evita el efecto "espagueti" durante el resize)
            if abs(draw_w - self.width()) < 5 and abs(draw_h - self.height()) < 5:
                p.drawPixmap(self.rect(), self._pixmap)
            else:
                target_x = (self.width() - draw_w) // 2
                target_y = (self.height() - draw_h) // 2
                p.drawPixmap(int(target_x), int(target_y), int(draw_w), int(draw_h), self._pixmap)
        else:
            p.setPen(Qt.cyan)
            p.drawText(self.rect(), Qt.AlignCenter, self._status)

        # Borde de Selección (Verde Neón si tiene foco real de Qt)
        if self.hasFocus():
            p.setPen(QPen(QColor(0, 255, 100), 2))
            p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        else:
            # Borde sutil (Azul oscuro si no está seleccionada)
            p.setPen(QPen(QColor(0, 100, 200, 100), 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event):
        # Forzar foco y activación de ventana
        self.setFocus(Qt.FocusReason.MouseFocusReason if hasattr(Qt.FocusReason, 'MouseFocusReason') else Qt.MouseFocusReason)
        self.activateWindow()
        self.raise_()
        
        if event.button() == Qt.LeftButton:
            # [LÓGICA FINAL] Redimensionar ventana + Cosechar píxeles (Sin estirar)
            pos = event.pos()
            if pos.x() > self.width() - 25 and pos.y() > self.height() - 25:
                self._is_resizing = True
                return
                
            self._drag_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()

    def mouseMoveEvent(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.buttons() & left:
            if self._is_resizing:
                # Redimensionamos la ventana físicamente
                new_size = event.pos()
                self.resize(max(50, new_size.x()), max(50, new_size.y()))
                return

            if self._drag_pos:
                # Mover ventana
                g_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                delta = g_pos - self._drag_pos
                self.move(self.pos() + delta)
                self._drag_pos = g_pos
        else:
            # Cambiar cursor si está en la zona de redimensionado
            pos = event.pos()
            if pos.x() > self.width() - 20 and pos.y() > self.height() - 20:
                self.setCursor(Qt.SizeAllCursor if not IS_WINDOWS else Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._is_resizing = False
        if hasattr(self, '_save_callback') and self._save_callback:
            # La firma de save_overlay_state requiere: (title, x, y, w, h, opacity, click_through)
            self._save_callback(
                self._title, 
                self.x(), self.y(), 
                self.width(), self.height(),
                1.0,   # Opacidad por defecto
                False  # Click-through por defecto
            )
        self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        if hasattr(self, '_thread'):
            self._thread.set_output_size(self.width(), self.height())
        super().resizeEvent(event)

    def closeEvent(self, event):
        self.closed.emit(self._title)
        if hasattr(self, '_thread'):
            self._thread.stop()
        super().closeEvent(event)
