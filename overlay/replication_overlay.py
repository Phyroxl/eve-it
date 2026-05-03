import logging
import time
import threading

logger = logging.getLogger('eve.overlay')

# Qt shim — tries PySide6 first, PyQt6 as fallback
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
        for _n in ['QColor', 'QPainter', 'QPixmap', 'QImage', 'QFont', 'QCursor', 'QPen', 'QBrush']:
            if hasattr(_g, _n): globals()[_n] = getattr(_g, _n)
        _qt_ok = True
        break
    except ImportError:
        continue

if not _qt_ok:
    class QWidget: pass
    class QThread: pass
    def Signal(*args): pass
    def Slot(*args): pass

from overlay.win32_capture import (
    capture_window_region, IS_WINDOWS, resolve_eve_window_handle,
    set_no_activate, user32, focus_eve_window, get_foreground_hwnd,
    set_topmost,
)
from overlay.replicator_config import get_overlay_cfg, save_overlay_cfg


class CaptureThread(QThread):
    frame_ready = Signal(object, int, int)  # (data, w, h)
    error_signal = Signal(str)

    def __init__(self, title, hwnd_getter, region, fps=30):
        super().__init__()
        self._title = title
        self._hwnd_getter = hwnd_getter if callable(hwnd_getter) else (lambda: hwnd_getter)
        self._hwnd = None
        self._region = region
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

            # Auto-recover handle if lost
            if not self._hwnd or not user32.IsWindow(self._hwnd):
                self._hwnd = self._hwnd_getter()

            # Supersampling 1.5x for sharper rendering in Qt layer
            sw, sh = int(w * 1.5), int(h * 1.5)
            data = capture_window_region(self._hwnd, self._region, sw, sh)

            if data == b"MINIMIZED":
                self.frame_ready.emit(b"MINIMIZED", 0, 0)
            elif data:
                self.frame_ready.emit(data, sw, sh)
            else:
                new_h = resolve_eve_window_handle(self._title)
                if new_h:
                    self._hwnd = new_h
                self.frame_ready.emit(b"ERROR", 0, 0)

            elapsed = time.perf_counter() - t_start
            time.sleep(max(0, (1.0 / fps) - elapsed))


class ReplicationOverlay(QWidget):
    selection_requested = Signal(object)
    closed = Signal(str)
    sync_triggered = Signal(dict)
    sync_resize_triggered = Signal(int, int)  # Task 2: (w, h) broadcast to peers

    def __init__(self, title, hwnd=None, region_rel=None, cfg=None,
                 save_callback=None, hwnd_getter=None):
        super().__init__(None)
        self._title = title
        self._hwnd_getter = hwnd_getter if hwnd_getter else (lambda: hwnd)
        self._hwnd = hwnd
        self._region = region_rel if region_rel else {'x': 0, 'y': 0, 'w': 1, 'h': 1}
        self._cfg = cfg if cfg else {}
        self._save_callback = save_callback
        self._sync_active = False

        # Task 3: per-overlay persistent config (merged with OVERLAY_DEFAULTS)
        self._ov_cfg = get_overlay_cfg(self._cfg, self._title)

        self._pixmap = None
        self._status = "CONECTANDO..."
        self._drag_pos = None
        self._is_resizing = False
        self._is_active_client = False
        # Task 2: guard flag to break sync-resize signal loops
        self._applying_sync_resize = False

        self._setup_ui()
        self._start_capture()

        # Task 3: 300 ms debounced autosave
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._do_save)

        # Task 4: 500 ms monitor for active-border + hide_when_inactive
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._monitor_focus)
        self._monitor_timer.start(500)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        ov = self._ov_cfg
        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        ) if hasattr(Qt, 'WindowType') else (
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(
            Qt.WA_TranslucentBackground if hasattr(Qt, 'WA_TranslucentBackground') else 120,
            False,
        )
        self.setMinimumSize(64, 64)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setWindowTitle(f"Replica - {self._title}")
        self.setStyleSheet("background-color: #000;")
        set_no_activate(int(self.winId()))

        # Task 3: restore saved position / size
        self.move(int(ov.get('x', 400)), int(ov.get('y', 300)))
        self.resize(int(ov.get('w', 280)), int(ov.get('h', 200)))

        # Task 4: apply always_on_top from config
        self.apply_always_on_top(bool(ov.get('always_on_top', True)))

        # Win32 topmost re-assertion every 2 s (belt-and-suspenders)
        self._top_timer = QTimer(self)
        self._top_timer.timeout.connect(self._reassert_topmost)
        self._top_timer.start(2000)

    # ------------------------------------------------------------------
    # Task 6: label text extraction
    # ------------------------------------------------------------------

    def _extract_label(self) -> str:
        """'EVE — Nina Herrera' → 'Nina Herrera'. Falls back to the full title."""
        for sep in (' — ', ' - ', ' – '):
            if sep in self._title:
                return self._title.split(sep, 1)[-1].strip()
        return self._title

    # ------------------------------------------------------------------
    # Task 4: always-on-top + hide-when-inactive
    # ------------------------------------------------------------------

    def apply_always_on_top(self, v: bool):
        """Set or clear the Win32 TOPMOST flag."""
        try:
            set_topmost(int(self.winId()), v)
        except Exception:
            pass

    def _monitor_focus(self):
        """Poll foreground window every 500 ms to update active-border state."""
        try:
            fg = get_foreground_hwnd()
            was_active = self._is_active_client
            self._is_active_client = bool(self._hwnd and fg == self._hwnd)

            if was_active != self._is_active_client:
                self.update()

            if self._ov_cfg.get('hide_when_inactive', False):
                from overlay.win32_capture import find_eve_windows
                eve_hwnds = {w['hwnd'] for w in find_eve_windows()}
                if fg not in eve_hwnds:
                    if self.isVisible():
                        self.hide()
                else:
                    if not self.isVisible():
                        self.show()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Task 2: sync-resize support
    # ------------------------------------------------------------------

    def apply_size(self, w: int, h: int):
        """Called by peer overlays to broadcast a resize."""
        if self._applying_sync_resize:
            return
        self._applying_sync_resize = True
        try:
            self.resize(max(50, w), max(50, h))
        finally:
            self._applying_sync_resize = False

    # ------------------------------------------------------------------
    # Task 3: autosave
    # ------------------------------------------------------------------

    def _schedule_autosave(self):
        self._autosave_timer.start(300)

    def _do_save(self):
        """Persist current position / size / FPS to replicator.json."""
        self._ov_cfg['x'] = self.x()
        self._ov_cfg['y'] = self.y()
        self._ov_cfg['w'] = self.width()
        self._ov_cfg['h'] = self.height()
        if hasattr(self, '_thread'):
            self._ov_cfg['fps'] = self._thread._fps
        save_overlay_cfg(self._cfg, self._title, self._ov_cfg)

    # ------------------------------------------------------------------
    # FPS helper (used by context menu + settings dialog)
    # ------------------------------------------------------------------

    def _set_fps(self, val: int):
        if hasattr(self, '_thread'):
            self._thread.set_fps(val)
        self._ov_cfg['fps'] = val
        self._schedule_autosave()

    # ------------------------------------------------------------------
    # Task 5: snap-to-grid
    # ------------------------------------------------------------------

    def _apply_snap(self, x: int, y: int):
        sx = max(1, int(self._ov_cfg.get('snap_x', 20)))
        sy = max(1, int(self._ov_cfg.get('snap_y', 20)))
        return (round(x / sx) * sx, round(y / sy) * sy)

    # ------------------------------------------------------------------
    # Context menu  (Task 9: adds ⚙ Ajustes)
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #0a0a0a; border: 1px solid #00c8ff; color: #fff; padding: 5px; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background: #004466; }
        """)

        act_sync = menu.addAction("🔗 Sincronizar desde aquí")
        act_sync.setCheckable(True)
        act_sync.setChecked(self._sync_active)
        act_sync.triggered.connect(self._toggle_sync)

        fps_menu = menu.addMenu("⚡ Fotogramas (FPS)")
        cur_fps = self._thread._fps if hasattr(self, '_thread') else 30
        for val in [5, 10, 15, 30, 60, 120]:
            label = f"✓ {val} FPS" if val == cur_fps else f"{val} FPS"
            act = fps_menu.addAction(label)
            act.triggered.connect(lambda _, v=val: self._set_fps(v))

        act_wizard = menu.addAction("🎯 Cambiar Zona")
        act_wizard.triggered.connect(self._relaunch_wizard)

        menu.addSeparator()

        act_settings = menu.addAction("⚙ Ajustes")
        act_settings.triggered.connect(self._open_settings)

        menu.addSeparator()

        act_close = menu.addAction("✕ Cerrar")
        act_close.triggered.connect(self.close)

        menu.exec(event.globalPos())

    def _open_settings(self):
        """Task 9: open per-replica settings dialog."""
        try:
            from overlay.replicator_settings_dialog import ReplicatorSettingsDialog
            dlg = ReplicatorSettingsDialog(self)
            dlg.exec()
        except Exception as e:
            logger.error(f"Error abriendo ajustes: {e}")

    def _reset_view(self):
        self._region['x'] = 0
        self._region['y'] = 0
        self._region['w'] = 1.0
        self._region['h'] = 1.0
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)

    def _toggle_sync(self, state):
        self._sync_active = state

    def _relaunch_wizard(self):
        self.selection_requested.emit(self)

    def _reassert_topmost(self):
        if self._ov_cfg.get('always_on_top', True):
            import ctypes
            try:
                ctypes.windll.user32.SetWindowPos(
                    int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010
                )
            except Exception:
                pass

    def _start_capture(self):
        fps = self._ov_cfg.get('fps', 30)
        self._thread = CaptureThread(self._title, self._hwnd_getter, self._region, fps)
        self._thread.set_output_size(self.width(), self.height())
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.start()

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

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
            fmt = QImage.Format.Format_ARGB32 if hasattr(QImage, 'Format') else QImage.Format_ARGB32
            img = QImage(data, w, h, fmt)
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)
        self.update()

    # ------------------------------------------------------------------
    # Keyboard / wheel
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        if not self.hasFocus():
            return
        step = 0.01 if event.modifiers() & Qt.ShiftModifier else 0.002
        k = event.key()
        if event.modifiers() & Qt.ControlModifier:
            if k == Qt.Key_Up:    self._zoom_roi(0.95)
            elif k == Qt.Key_Down: self._zoom_roi(1.05)
            return
        if k == Qt.Key_Up:      self._region['y'] = max(0, self._region['y'] - step)
        elif k == Qt.Key_Down:  self._region['y'] = min(1.0 - self._region['h'], self._region['y'] + step)
        elif k == Qt.Key_Left:  self._region['x'] = max(0, self._region['x'] - step)
        elif k == Qt.Key_Right: self._region['x'] = min(1.0 - self._region['w'], self._region['x'] + step)
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if not self.hasFocus():
            return
        delta = event.angleDelta().y()
        mods = event.modifiers()
        pos = event.position() if hasattr(event, 'position') else event.pos()
        mx_rel = pos.x() / self.width()
        my_rel = pos.y() / self.height()
        factor = 1.03 if delta > 0 else 0.97
        if mods & Qt.ShiftModifier:
            self.resize(self.width(), int(self.height() * factor))
        elif mods & Qt.ControlModifier:
            self.resize(int(self.width() * factor), self.height())
        else:
            f_inv = 0.97 if delta > 0 else 1.03
            self._zoom_roi_ex(f_inv, f_inv, mx_rel, my_rel)
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)
        event.accept()

    def _zoom_roi_ex(self, f_w, f_h, mx_rel=0.5, my_rel=0.5):
        old_w, old_h = self._region['w'], self._region['h']
        new_w = max(0.01, min(1.0, old_w * f_w))
        new_h = max(0.01, min(1.0, old_h * f_h))
        world_x = self._region['x'] + mx_rel * old_w
        world_y = self._region['y'] + my_rel * old_h
        self._region['x'] = max(0, min(1.0 - new_w, world_x - mx_rel * new_w))
        self._region['y'] = max(0, min(1.0 - new_h, world_y - my_rel * new_h))
        self._region['w'], self._region['h'] = new_w, new_h
        self.update()
        if self._sync_active:
            self.sync_triggered.emit(self._region)

    def apply_region(self, reg_dict):
        """Apply an external region change (pan/zoom sync from peer)."""
        old_w, old_h = self._region['w'], self._region['h']
        new_w, new_h = reg_dict['w'], reg_dict['h']
        self._region.update(reg_dict)
        if abs(new_w - old_w) > 0.001 or abs(new_h - old_h) > 0.001:
            self.resize(
                int(self.width() * (new_w / old_w)),
                int(self.height() * (new_h / old_h)),
            )
        self.update()

    # ------------------------------------------------------------------
    # Paint  (Task 6: label, Task 7: border)
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        rh_smooth = QPainter.RenderHint.SmoothPixmapTransform \
            if hasattr(QPainter.RenderHint, 'SmoothPixmapTransform') \
            else QPainter.SmoothPixmapTransform
        rh_aa = QPainter.RenderHint.Antialiasing \
            if hasattr(QPainter.RenderHint, 'Antialiasing') \
            else QPainter.Antialiasing
        p.setRenderHint(rh_smooth)
        p.setRenderHint(rh_aa)

        p.fillRect(self.rect(), Qt.black)

        if self._pixmap:
            pw, ph = self._pixmap.width(), self._pixmap.height()
            draw_w, draw_h = pw / 1.5, ph / 1.5
            if abs(draw_w - self.width()) < 5 and abs(draw_h - self.height()) < 5:
                p.drawPixmap(self.rect(), self._pixmap)
            else:
                tx = (self.width() - draw_w) // 2
                ty = (self.height() - draw_h) // 2
                p.drawPixmap(int(tx), int(ty), int(draw_w), int(draw_h), self._pixmap)
        else:
            p.setPen(Qt.cyan)
            p.drawText(self.rect(), Qt.AlignCenter, self._status)

        ov = self._ov_cfg

        # Task 7: configurable border (active vs client color)
        if ov.get('border_visible', True):
            bw = max(1, int(ov.get('border_width', 2)))
            if ov.get('highlight_active', True) and self._is_active_client:
                hex_col = ov.get('active_border_color', '#00ff64')
            else:
                hex_col = ov.get('client_color', '#00c8ff')
            p.setPen(QPen(QColor(hex_col), bw))
            adj = bw // 2
            p.drawRect(self.rect().adjusted(adj, adj, -adj, -adj))

        # Task 6: overlay label
        if ov.get('label_visible', True):
            label_text = self._extract_label()
            fs = max(6, int(ov.get('label_font_size', 10)))
            pad = max(0, int(ov.get('label_padding', 4)))

            font = QFont()
            font.setPointSize(fs)
            p.setFont(font)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label_text) \
                if hasattr(fm, 'horizontalAdvance') else fm.width(label_text)
            th = fm.height()
            lw, lh = tw + pad * 2, th + pad * 2

            pos_key = ov.get('label_pos', 'top_left')
            if 'right' in pos_key:
                lx = self.width() - lw - 2
            elif 'center' in pos_key:
                lx = (self.width() - lw) // 2
            else:
                lx = 2
            ly = (self.height() - lh - 2) if 'bottom' in pos_key else 2

            if ov.get('label_bg', True):
                bg = QColor(ov.get('label_bg_color', '#000000'))
                bg.setAlphaF(max(0.0, min(1.0, float(ov.get('label_bg_opacity', 0.65)))))
                p.fillRect(lx, ly, lw, lh, bg)

            p.setPen(QColor(ov.get('label_color', '#ffffff')))
            p.drawText(lx + pad, ly + pad + fm.ascent(), label_text)

    # ------------------------------------------------------------------
    # Mouse events  (Task 1: focus EVE, Task 2: sync-resize, Task 5: snap)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.button() == left:
            pos = event.pos()
            in_resize_corner = pos.x() > self.width() - 25 and pos.y() > self.height() - 25
            if in_resize_corner:
                self._is_resizing = True
                return
            # Task 1: focus the EVE client (Win32 only, no input injection)
            if self._hwnd:
                focus_eve_window(self._hwnd)
            self._drag_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, 'globalPosition') else event.globalPos()
            )
        # Qt focus so keyboard events still work
        self.setFocus(
            Qt.FocusReason.MouseFocusReason
            if hasattr(Qt.FocusReason, 'MouseFocusReason') else Qt.MouseFocusReason
        )
        self.activateWindow()
        self.raise_()

    def mouseMoveEvent(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.buttons() & left:
            if self._is_resizing:
                pos = event.pos()
                self.resize(max(50, pos.x()), max(50, pos.y()))
                return
            if self._drag_pos and not self._ov_cfg.get('locked', False):
                g_pos = (
                    event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition') else event.globalPos()
                )
                delta = g_pos - self._drag_pos
                new_x = self.pos().x() + delta.x()
                new_y = self.pos().y() + delta.y()
                # Task 5: snap to grid
                if self._ov_cfg.get('snap_enabled', False):
                    new_x, new_y = self._apply_snap(new_x, new_y)
                self.move(new_x, new_y)
                self._drag_pos = g_pos
        else:
            pos = event.pos()
            if pos.x() > self.width() - 20 and pos.y() > self.height() - 20:
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        was_resizing = self._is_resizing
        self._drag_pos = None
        self._is_resizing = False
        self.setCursor(Qt.ArrowCursor)

        # Task 2: broadcast new size to synced peers after manual resize
        if was_resizing and self._sync_active and not self._applying_sync_resize:
            self.sync_resize_triggered.emit(self.width(), self.height())

        # Task 3: debounced save on every move/resize
        self._schedule_autosave()

    # ------------------------------------------------------------------
    # Resize event (single, combined — fixes duplicate from original file)
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        if hasattr(self, '_thread') and self._thread._running:
            if event.oldSize().width() > 0 and event.oldSize().height() > 0:
                rw = event.size().width() / event.oldSize().width()
                rh = event.size().height() / event.oldSize().height()
                self._region['w'] = max(0.01, min(1.0, self._region['w'] * rw))
                self._region['h'] = max(0.01, min(1.0, self._region['h'] * rh))
            self._thread.set_output_size(self.width(), self.height())
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if hasattr(self, '_monitor_timer'):
            self._monitor_timer.stop()
        if hasattr(self, '_autosave_timer'):
            self._autosave_timer.stop()
        self._do_save()  # final flush
        self.closed.emit(self._title)
        if hasattr(self, '_thread'):
            self._thread.stop()
        super().closeEvent(event)
