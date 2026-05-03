import logging
import time
import threading
import weakref

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
    set_topmost, should_show_overlays, get_window_size,
)
from overlay.replicator_config import get_overlay_cfg, save_overlay_cfg

# Global weak registry so the settings dialog can reach all active overlays
_OVERLAY_REGISTRY: 'weakref.WeakSet' = weakref.WeakSet()

# Minimum pixel movement before a press is considered a drag (not a click)
_DRAG_THRESHOLD = 5


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
    sync_resize_triggered = Signal(int, int)  # (w, h) broadcast to peers

    # Class-level EVE hwnd cache shared across all overlay instances (avoids N×find_eve_windows/s)
    _eve_hwnds_cache: set = set()
    _eve_hwnds_ts: float = 0.0

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

        # Per-overlay persistent config (merged with OVERLAY_DEFAULTS)
        self._ov_cfg = get_overlay_cfg(self._cfg, self._title)

        self._pixmap = None
        self._status = "CONECTANDO..."
        self._is_active_client = False
        self._applying_sync_resize = False  # guard: break sync-resize loops

        # Drag state — absolute-origin approach (fix for snap static bug)
        self._drag_start_global = None   # QPoint at press, never mutated during drag
        self._drag_start_pos = None      # widget pos at press, never mutated during drag
        self._drag_moved = False         # True once mouse exceeded _DRAG_THRESHOLD
        self._is_resizing = False

        _OVERLAY_REGISTRY.add(self)

        self._setup_ui()
        self._start_capture()

        # 300 ms debounced autosave
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._do_save)

        # 500 ms monitor: active-border + hide_when_inactive
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._monitor_focus)
        self._monitor_timer.start(500)

        # Fix 2: correct aspect ratio on first launch (when size is at defaults)
        self._fix_initial_aspect()

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

        # Restore saved position / size
        self.move(int(ov.get('x', 400)), int(ov.get('y', 300)))
        self.resize(int(ov.get('w', 280)), int(ov.get('h', 200)))

        # Apply always_on_top from config
        self.apply_always_on_top(bool(ov.get('always_on_top', True)))

        # Win32 topmost re-assertion belt-and-suspenders every 2 s
        self._top_timer = QTimer(self)
        self._top_timer.timeout.connect(self._reassert_topmost)
        self._top_timer.start(2000)

    # ------------------------------------------------------------------
    # Label extraction
    # ------------------------------------------------------------------

    def _extract_label(self) -> str:
        """'EVE — Nina Herrera' → 'Nina Herrera'. Falls back to the full title."""
        for sep in (' — ', ' - ', ' – '):
            if sep in self._title:
                return self._title.split(sep, 1)[-1].strip()
        return self._title

    # ------------------------------------------------------------------
    # Always-on-top
    # ------------------------------------------------------------------

    def apply_always_on_top(self, v: bool):
        try:
            set_topmost(int(self.winId()), v)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Class-level EVE hwnd cache (shared, refreshed every 2 s)
    # ------------------------------------------------------------------

    def _fix_initial_aspect(self):
        """Correct widget height to match region aspect ratio on first launch."""
        from overlay.replicator_config import OVERLAY_DEFAULTS
        # Only correct if using default dimensions (never been saved/positioned manually)
        if (self._ov_cfg.get('w') != OVERLAY_DEFAULTS['w'] or
                self._ov_cfg.get('h') != OVERLAY_DEFAULTS['h']):
            return
        if not self._hwnd:
            return
        try:
            ev_w, ev_h = get_window_size(self._hwnd)
            if ev_w > 0 and ev_h > 0:
                reg_w = self._region.get('w', 0.3) * ev_w
                reg_h = self._region.get('h', 0.2) * ev_h
                if reg_h > 0:
                    aspect = reg_w / reg_h
                    w = self.width()
                    correct_h = max(64, int(w / aspect))
                    if abs(correct_h - self.height()) > 8:
                        self.resize(w, correct_h)
        except Exception:
            pass

    @classmethod
    def _get_cached_eve_hwnds(cls) -> set:
        now = time.monotonic()
        if now - cls._eve_hwnds_ts > 2.0:
            try:
                from overlay.win32_capture import find_eve_windows
                cls._eve_hwnds_cache = {w['hwnd'] for w in find_eve_windows()}
            except Exception:
                pass
            cls._eve_hwnds_ts = now
        return cls._eve_hwnds_cache

    # ------------------------------------------------------------------
    # Monitor: active-border + hide_when_inactive (Fix #4)
    # ------------------------------------------------------------------

    def _monitor_focus(self):
        try:
            fg = get_foreground_hwnd()
            was_active = self._is_active_client
            self._is_active_client = bool(self._hwnd and fg == self._hwnd)

            if was_active != self._is_active_client:
                self.update()

            if self._ov_cfg.get('hide_when_inactive', False):
                eve_hwnds = self._get_cached_eve_hwnds()
                if should_show_overlays(fg, eve_hwnds):
                    if not self.isVisible():
                        self.show()
                else:
                    if self.isVisible():
                        self.hide()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sync-resize support
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
    # Autosave
    # ------------------------------------------------------------------

    def _schedule_autosave(self):
        self._autosave_timer.start(300)

    def _do_save(self):
        self._ov_cfg['x'] = self.x()
        self._ov_cfg['y'] = self.y()
        self._ov_cfg['w'] = self.width()
        self._ov_cfg['h'] = self.height()
        if hasattr(self, '_thread'):
            self._ov_cfg['fps'] = self._thread._fps
        save_overlay_cfg(self._cfg, self._title, self._ov_cfg)

    # ------------------------------------------------------------------
    # Apply settings from another overlay (apply-to-all feature)
    # ------------------------------------------------------------------

    def apply_settings_dict(self, settings: dict, persist: bool = True):
        """Absorb a batch of settings keys (from apply-to-all)."""
        self._ov_cfg.update(settings)
        self.apply_always_on_top(bool(self._ov_cfg.get('always_on_top', True)))
        if hasattr(self, '_thread'):
            self._thread.set_fps(int(self._ov_cfg.get('fps', 30)))
        self.update()
        if persist:
            self._schedule_autosave()

    def reload_overlay_config(self):
        """Reload _ov_cfg from the master cfg dict (used after apply_common_settings_to_all)."""
        self._ov_cfg = get_overlay_cfg(self._cfg, self._title)
        self.apply_always_on_top(bool(self._ov_cfg.get('always_on_top', True)))
        if hasattr(self, '_thread'):
            self._thread.set_fps(int(self._ov_cfg.get('fps', 30)))
        self.update()

    # ------------------------------------------------------------------
    # FPS helper
    # ------------------------------------------------------------------

    def _set_fps(self, val: int):
        if hasattr(self, '_thread'):
            self._thread.set_fps(val)
        self._ov_cfg['fps'] = val
        self._schedule_autosave()

    # ------------------------------------------------------------------
    # Snap-to-grid (Fix #2: compute from press origin, not running pos)
    # ------------------------------------------------------------------

    def _apply_snap(self, x: int, y: int) -> tuple:
        sx = max(1, int(self._ov_cfg.get('snap_x', 20)))
        sy = max(1, int(self._ov_cfg.get('snap_y', 20)))
        return (round(x / sx) * sx, round(y / sy) * sy)

    # ------------------------------------------------------------------
    # Context menu
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
    # Paint
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
            src_aspect = pw / ph if ph > 0 else 1.0
            dst_aspect = self.width() / self.height() if self.height() > 0 else 1.0

            if self._ov_cfg.get('maintain_aspect', True) and abs(src_aspect - dst_aspect) > 0.05:
                # Letterbox / pillarbox to preserve source aspect ratio
                if src_aspect > dst_aspect:
                    dw = self.width()
                    dh = max(1, int(dw / src_aspect))
                    ty = (self.height() - dh) // 2
                    p.drawPixmap(0, ty, dw, dh, self._pixmap)
                else:
                    dh = self.height()
                    dw = max(1, int(dh * src_aspect))
                    tx = (self.width() - dw) // 2
                    p.drawPixmap(tx, 0, dw, dh, self._pixmap)
            else:
                p.drawPixmap(self.rect(), self._pixmap)
        else:
            p.setPen(Qt.cyan)
            p.drawText(self.rect(), Qt.AlignCenter, self._status)

        ov = self._ov_cfg

        # Configurable border (active vs client color)
        if ov.get('border_visible', True):
            bw = max(1, int(ov.get('border_width', 2)))
            if ov.get('highlight_active', True) and self._is_active_client:
                hex_col = ov.get('active_border_color', '#00ff64')
            else:
                hex_col = ov.get('client_color', '#00c8ff')
            p.setPen(QPen(QColor(hex_col), bw))
            adj = bw // 2
            p.drawRect(self.rect().adjusted(adj, adj, -adj, -adj))

        # Overlay label
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
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        if event.button() == left:
            pos = event.pos()
            in_resize_corner = pos.x() > self.width() - 25 and pos.y() > self.height() - 25
            if in_resize_corner:
                self._is_resizing = True
                self._drag_start_global = None
                self._drag_moved = False
                return
            # Record drag origin (absolute approach — never mutated during drag)
            g = event.globalPosition().toPoint() \
                if hasattr(event, 'globalPosition') else event.globalPos()
            self._drag_start_global = g
            self._drag_start_pos = self.pos()
            self._drag_moved = False

        # Qt focus for keyboard events
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

            if self._drag_start_global is not None and not self._ov_cfg.get('locked', False):
                g_pos = event.globalPosition().toPoint() \
                    if hasattr(event, 'globalPosition') else event.globalPos()
                delta = g_pos - self._drag_start_global

                # Mark as drag once threshold exceeded
                if not self._drag_moved:
                    if abs(delta.x()) > _DRAG_THRESHOLD or abs(delta.y()) > _DRAG_THRESHOLD:
                        self._drag_moved = True

                # Absolute calculation from press origin — snap never freezes the overlay
                raw_x = self._drag_start_pos.x() + delta.x()
                raw_y = self._drag_start_pos.y() + delta.y()

                # ALT key temporarily bypasses snap
                mods = event.modifiers()
                alt_held = bool(mods & (Qt.AltModifier if hasattr(Qt, 'AltModifier') else 0x08000000))
                if self._ov_cfg.get('snap_enabled', False) and not alt_held:
                    raw_x, raw_y = self._apply_snap(raw_x, raw_y)

                self.move(raw_x, raw_y)
        else:
            pos = event.pos()
            if pos.x() > self.width() - 20 and pos.y() > self.height() - 20:
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        left = Qt.MouseButton.LeftButton if hasattr(Qt, 'MouseButton') else Qt.LeftButton
        was_resizing = self._is_resizing
        self._is_resizing = False
        self.setCursor(Qt.ArrowCursor)

        if event.button() == left:
            if not was_resizing and not self._drag_moved:
                # Fix #1: plain click (no drag, no resize) → focus the EVE client
                hwnd = self._hwnd_getter()
                if hwnd:
                    self._hwnd = hwnd
                ok = focus_eve_window(self._hwnd) if self._hwnd else False
                logger.debug(
                    f"[REPLICATOR FOCUS] title={self._title!r} "
                    f"hwnd={self._hwnd} success={ok}"
                )

            # Broadcast resize to synced peers after manual resize
            if was_resizing and self._sync_active and not self._applying_sync_resize:
                self.sync_resize_triggered.emit(self.width(), self.height())

        self._drag_start_global = None
        self._drag_start_pos = None
        self._drag_moved = False

        # Debounced save on every move/resize
        self._schedule_autosave()

    # ------------------------------------------------------------------
    # Resize event
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
        self._do_save()
        self.closed.emit(self._title)
        if hasattr(self, '_thread'):
            self._thread.stop()
        super().closeEvent(event)
