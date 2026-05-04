import logging
import time
import threading
import weakref
from pathlib import Path

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
        for _n in ['QApplication', 'QWidget', 'QLabel', 'QMenu', 'QMessageBox', 'QDialog', 'QTextEdit', 'QVBoxLayout', 'QHBoxLayout', 'QPushButton', 'QStyle', 'QAction']:
            if hasattr(_w, _n): globals()[_n] = getattr(_w, _n)
        for _n in ['Qt', 'QTimer', 'QThread', 'Signal', 'Slot', 'QPoint', 'QRect', 'QSize', 'QRectF', 'QPointF']:
            if hasattr(_c, _n): globals()[_n] = getattr(_c, _n)
        for _n in ['QColor', 'QPainter', 'QPixmap', 'QImage', 'QFont', 'QCursor', 'QPen', 'QBrush', 'QPainterPath', 'QIcon']:
            if hasattr(_g, _n): globals()[_n] = getattr(_g, _n)
        _qt_ok = True
        break
    except ImportError:
        continue

if not _qt_ok:
    class QWidget: pass
    class QThread: pass
    class QMessageBox:
        @staticmethod
        def information(*args): pass
    class QDialog: pass
    class QStyle:
        class StandardPixmap: SP_MessageBoxInformation = 0
    def Signal(*args): pass
    def Slot(*args): pass

from overlay.win32_capture import (
    capture_window_region, IS_WINDOWS, resolve_eve_window_handle,
    set_no_activate, user32, focus_eve_window, get_foreground_hwnd,
    set_topmost, should_show_overlays, get_window_size,
)
from overlay.replicator_config import get_overlay_cfg, save_overlay_cfg
from overlay.replicator_settings_dialog import ReplicatorSettingsDialog

# Global weak registry so the settings dialog can reach all active overlays
_OVERLAY_REGISTRY: 'weakref.WeakSet' = weakref.WeakSet()

# Minimum pixel movement before a press is considered a drag (not a click)
_DRAG_THRESHOLD = 5

# ---------------------------------------------------------------------------
# WH_MOUSE_LL — global low-level mouse hook so wheel events reach overlays
# even when EVE Online has OS focus (WM_MOUSEWHEEL normally goes to the fg window).
#
# Win64 type rules:
#   LRESULT  = c_ssize_t (64-bit signed)  — NOT c_long (32-bit on Windows!)
#   WPARAM   = wintypes.WPARAM  (UINT_PTR, 64-bit)
#   LPARAM   = wintypes.LPARAM  (LONG_PTR, 64-bit)
# CallNextHookEx argtypes MUST be declared explicitly; without them ctypes
# defaults to c_int for lParam which overflows on every WM_MOUSEMOVE pointer.
# ---------------------------------------------------------------------------
_WH_MOUSE_LL   = 14
_WM_MOUSEWHEEL  = 0x020A
_WM_MOUSEHWHEEL = 0x020E
_mouse_hook_handle   = None
_mouse_hook_proc_ref = None   # keep CFUNCTYPE alive to prevent GC crash
_hook_error_count    = 0
_hook_error_ts       = 0.0

if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes as _wt

    # Correct Win64 types
    _LRESULT  = ctypes.c_ssize_t
    _WPARAM   = _wt.WPARAM
    _LPARAM   = _wt.LPARAM
    _HHOOK    = _wt.HHOOK

    # Declare argtypes/restype on the user32 functions we use from the hook
    # so ctypes marshals 64-bit values correctly.
    _u32h = ctypes.windll.user32
    _u32h.CallNextHookEx.restype   = _LRESULT
    _u32h.CallNextHookEx.argtypes  = [_HHOOK, ctypes.c_int, _WPARAM, _LPARAM]
    _u32h.SetWindowsHookExW.restype  = _HHOOK
    _u32h.SetWindowsHookExW.argtypes = [
        ctypes.c_int, ctypes.c_void_p, _wt.HINSTANCE, _wt.DWORD,
    ]
    _u32h.UnhookWindowsHookEx.restype  = _wt.BOOL
    _u32h.UnhookWindowsHookEx.argtypes = [_HHOOK]

    _HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, _WPARAM, _LPARAM)

    class _MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ('pt',          _wt.POINT),
            ('mouseData',   _wt.DWORD),
            ('flags',       _wt.DWORD),
            ('time',        _wt.DWORD),
            ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
        ]

    def _mouse_ll_hook_proc(nCode, wParam, lParam):
        # ── Fast-path: pass through everything that is not a wheel event ──────
        # WM_MOUSEMOVE fires hundreds of times/second; any work here causes lag.
        if nCode < 0 or wParam not in (_WM_MOUSEWHEEL, _WM_MOUSEHWHEEL):
            return _u32h.CallNextHookEx(_mouse_hook_handle, nCode, wParam, lParam)

        # ── Wheel event: decode delta and route to the hovered overlay ─────────
        global _hook_error_count, _hook_error_ts
        try:
            ms    = ctypes.cast(lParam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            delta = ctypes.c_short(ms.mouseData >> 16).value
            ov    = ReplicationOverlay._hover_overlay
            if ov is not None:
                _ov_ref = weakref.ref(ov)
                QTimer.singleShot(0, lambda d=delta, r=_ov_ref: _deliver_hook_wheel(r, d))
        except Exception as e:
            _hook_error_count += 1
            _now = time.monotonic()
            if _now - _hook_error_ts > 30.0:   # log at most once per 30 s
                _hook_error_ts = _now
                logger.warning(f"[MOUSE HOOK] wheel proc error (#{_hook_error_count}): {e}")
                if _hook_error_count >= 5:
                    # Too many errors: self-disable to protect app performance
                    logger.warning("[MOUSE HOOK] auto-disabling after repeated errors")
                    _uninstall_global_mouse_hook()
                    return 0

        return _u32h.CallNextHookEx(_mouse_hook_handle, nCode, wParam, lParam)

    def _deliver_hook_wheel(ov_ref, delta):
        o = ov_ref()
        if o is not None:
            try:
                o._do_hover_wheel(delta)
            except Exception:
                pass


def _install_global_mouse_hook():
    global _mouse_hook_handle, _mouse_hook_proc_ref
    if not IS_WINDOWS or _mouse_hook_handle:
        return
    try:
        proc = _HOOKPROC(_mouse_ll_hook_proc)
        _mouse_hook_proc_ref = proc
        _mouse_hook_handle = _u32h.SetWindowsHookExW(_WH_MOUSE_LL, proc, None, 0)
        if _mouse_hook_handle:
            logger.info(f"[MOUSE HOOK] WH_MOUSE_LL installed handle={_mouse_hook_handle}")
            _log_hook_event("installed ok", f"handle={_mouse_hook_handle}")
        else:
            logger.warning("[MOUSE HOOK] SetWindowsHookExW returned NULL")
            _log_hook_event("install failed", "handle=NULL")
    except Exception as e:
        logger.warning(f"[MOUSE HOOK] Failed to install: {e}")
        _log_hook_event("install error", str(e))


def _uninstall_global_mouse_hook():
    global _mouse_hook_handle
    if _mouse_hook_handle and IS_WINDOWS:
        try:
            ok = _u32h.UnhookWindowsHookEx(_mouse_hook_handle)
            logger.info(f"[MOUSE HOOK] uninstalled ok={bool(ok)}")
            _log_hook_event("uninstalled", f"ok={bool(ok)}")
        except Exception as e:
            logger.warning(f"[MOUSE HOOK] uninstall error: {e}")
        _mouse_hook_handle = None


def _log_hook_event(event: str, detail: str = ""):
    """Write a single line to logs/replicator_mouse_hook_debug.log."""
    try:
        import datetime
        from utils.paths import ROOT_DIR
        lp = ROOT_DIR / 'logs' / 'replicator_mouse_hook_debug.log'
        lp.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        with open(lp, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] [MOUSE HOOK] {event} {detail}\n")
    except Exception:
        pass


def _log_hide_show_event(action: str, title: str, detail: str = ""):
    """Write hide/show geometry events to logs/replicator_hide_debug.log."""
    try:
        import datetime
        from utils.paths import ROOT_DIR
        lp = ROOT_DIR / 'logs' / 'replicator_hide_debug.log'
        lp.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        with open(lp, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] [{action}] title='{title}' {detail}\n")
    except Exception:
        pass


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
        self._fast_stop = False

    def set_fast_stop(self, enabled=True):
        self._fast_stop = enabled

    def set_output_size(self, w, h):
        with self._lock:
            self._out_w, self._out_h = max(10, w), max(10, h)

    def set_fps(self, fps):
        with self._lock:
            self._fps = max(1, min(120, fps))

    def stop(self):
        self._running = False
        if not self._fast_stop:
            self.wait(500)

    def run(self):
        # Cache module reference once — avoids repeated import overhead per frame
        _hk_mod = None
        try:
            import overlay.replicator_hotkeys as _hk_mod
        except Exception:
            pass

        while self._running:
            t_start = time.perf_counter()

            with self._lock:
                w, h = self._out_w, self._out_h
                fps = self._fps

            # Skip one frame while a hotkey cycle is in progress.
            # Reduces capture-thread competition with Win32 SetForegroundWindow.
            if _hk_mod is not None:
                try:
                    if time.monotonic() < _hk_mod._capture_suspended_until:
                        time.sleep(max(0.0, (1.0 / fps) - (time.perf_counter() - t_start)))
                        continue
                except Exception:
                    pass

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
    geometryChanged = Signal(int, int, int, int) # (x, y, w, h)

    # Class-level EVE hwnd cache shared across all overlay instances (avoids N×find_eve_windows/s)
    _eve_hwnds_cache: set = set()
    _eve_hwnds_ts: float = 0.0

    # Settle period after programmatic focus change — prevents monitor timer from undoing F14/click
    _active_hwnd_override: int = 0
    _active_hwnd_override_until: float = 0.0

    # Overlay currently under the mouse cursor — used by the WH_MOUSE_LL hook to route wheel events
    _hover_overlay: 'ReplicationOverlay | None' = None

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
        self._debug_visual_layers = False  # toggled by diagnostics dialog only
        self._shutting_down = False

        _OVERLAY_REGISTRY.add(self)

        # Install the global mouse hook on first overlay creation so scroll
        # events are delivered even when EVE has OS focus.
        if not _mouse_hook_handle:
            _install_global_mouse_hook()

        # Native region state (populated by _apply_native_window_region)
        self._last_native_region_status = 'not_called'
        self._last_native_region_kind   = 'none'
        self._last_native_region_shape  = 'square'
        self._last_native_region_hwnd   = 0
        self._last_native_region_size   = (0, 0)
        self._last_native_region_error  = None

        # DWM chrome suppression state (populated by _apply_dwm_chrome_suppression)
        self._last_dwm_chrome_status       = 'not_called'
        self._last_dwm_corner_pref_status  = 'not_called'
        self._last_dwm_border_color_status = 'not_called'
        self._last_dwm_error               = None
        self._last_dwm_hwnd                = 0

        self._setup_ui()
        self._start_capture()

        # 300 ms debounced autosave
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._do_save)

        # 75 ms monitor: fast hide/show + active-border (early-exit cache prevents excess Win32 calls)
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._monitor_focus)
        self._monitor_timer.start(75)

        # Fix 2: correct aspect ratio on first launch (when size is at defaults)
        self._fix_initial_aspect()

        # Fix 3: initial active border detection (detect foreground client on start)
        QTimer.singleShot(100, self._init_active_check)

    def _init_active_check(self):
        try:
            # Eagerly resolve hwnd if not set (covers _restore_replicator_overlays path
            # where hwnd_getter is provided but hwnd=None was passed)
            if not self._hwnd and callable(self._hwnd_getter):
                self._hwnd = self._hwnd_getter()
            fg = get_foreground_hwnd()
            if fg and self._hwnd and fg == self._hwnd:
                self._is_active_client = True
                self.update()
                logger.info(f"[REPLICATOR ACTIVE INIT] title={self._title!r} is_active=True")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        ov = self._ov_cfg
        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint
        ) if hasattr(Qt, 'WindowType') else (
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
            Qt.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(
            Qt.WA_TranslucentBackground if hasattr(Qt, 'WA_TranslucentBackground') else 120,
            True,
        )
        self.setAttribute(
            Qt.WA_NoSystemBackground if hasattr(Qt, 'WA_NoSystemBackground') else 9,
            True,
        )
        self.setAutoFillBackground(False) # Asegura que Qt no pinte fondo por defecto
        self.setMinimumSize(20, 20)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if hasattr(Qt, 'FocusPolicy') else Qt.StrongFocus)
        self.setWindowTitle(f"Replica - {self._title}")
        # Forzar transparencia absoluta y quitar bordes en el root widget
        self.setStyleSheet("background: transparent; border: none; outline: none;")
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
                    correct_h = max(20, int(w / aspect))
                    if abs(correct_h - self.height()) > 8:
                        self.resize(w, correct_h)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Window shape mask (pill / rounded → setMask so OS clips to shape)
    # ------------------------------------------------------------------

    def _apply_window_shape_mask(self):
        """Apply QBitmap mask + Win32 SetWindowRgn + DWM chrome suppression.
        square → clear both,  pill/rounded → set both.
        DWM suppression always runs so corners/borders are always suppressed."""
        if getattr(self, '_shutting_down', False):
            return
        shape = self._ov_cfg.get('border_shape', 'square')

        if shape == 'square':
            self.clearMask()
            self._apply_native_window_region()  # clears SetWindowRgn too
        else:
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                # --- Qt QBitmap mask (fallback / extra layer) ---
                try:
                    try:
                        from PySide6.QtGui import QBitmap
                    except ImportError:
                        from PyQt6.QtGui import QBitmap

                    bmp = QBitmap(w, h)
                    c0 = Qt.GlobalColor.color0 if hasattr(Qt, 'GlobalColor') else Qt.color0
                    c1 = Qt.GlobalColor.color1 if hasattr(Qt, 'GlobalColor') else Qt.color1
                    bmp.fill(c0)  # all transparent / masked-out

                    painter = QPainter(bmp)
                    rh_aa = (QPainter.RenderHint.Antialiasing
                             if hasattr(QPainter, 'RenderHint')
                             else QPainter.Antialiasing)
                    painter.setRenderHint(rh_aa)
                    painter.setBrush(c1)   # visible area
                    no_pen = (Qt.PenStyle.NoPen if hasattr(Qt, 'PenStyle') else Qt.NoPen)
                    painter.setPen(no_pen)

                    path = QPainterPath()
                    radius = min(w, h) / 2.0 if shape == 'pill' else 10.0
                    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
                    painter.drawPath(path)
                    painter.end()

                    self.setMask(bmp)
                    logger.debug(
                        "[REPLICATOR MASK] title=%r  shape=%s  size=%dx%d  r=%.1f",
                        self._title, shape, w, h, radius,
                    )
                except Exception as e:
                    logger.debug("[REPLICATOR MASK] error: %s", e)

                # --- Win32 SetWindowRgn (primary / authoritative layer) ---
                self._apply_native_window_region()

        # --- DWM chrome suppression (both paths) ---
        self._apply_dwm_chrome_suppression()

    def _apply_native_window_region(self):
        """Apply Win32 SetWindowRgn so DWM clips the window at the OS level.
        This is the authoritative clip; setMask is kept as a Qt-layer fallback."""
        try:
            import sys
            if sys.platform != 'win32':
                self._last_native_region_status = 'not_win32'
                return
            import ctypes
            _gdi32  = ctypes.windll.gdi32
            _user32 = ctypes.windll.user32

            # Explicit restype/argtypes avoid wrong calling convention on Win64
            _user32.SetWindowRgn.restype      = ctypes.c_int
            _user32.SetWindowRgn.argtypes     = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            _gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
            _gdi32.CreateEllipticRgn.restype  = ctypes.c_void_p
            _gdi32.DeleteObject.argtypes      = [ctypes.c_void_p]

            hwnd = int(self.winId())
            if not hwnd:
                self._last_native_region_status = 'no_hwnd'
                return

            shape = self._ov_cfg.get('border_shape', 'square')
            w, h  = self.width(), self.height()

            self._last_native_region_shape = shape
            self._last_native_region_hwnd  = hwnd
            self._last_native_region_size  = (w, h)
            self._last_native_region_error = None

            if shape == 'square' or w <= 0 or h <= 0:
                _user32.SetWindowRgn(hwnd, None, True)
                self._last_native_region_status = 'cleared'
                self._last_native_region_kind   = 'none'
                logger.debug("[REPLICATOR REGION] hwnd=%d square → region cleared", hwnd)
                return

            hrgn = None
            kind = 'unknown'
            if shape == 'pill':
                if abs(w - h) <= 2:
                    # Near-square pill → true ellipse for pixel-perfect circle
                    hrgn = _gdi32.CreateEllipticRgn(0, 0, w + 1, h + 1)
                    kind = 'ellipse'
                else:
                    radius = min(w, h)
                    hrgn = _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
                    kind = 'pill_roundrect'
            elif shape == 'rounded':
                hrgn = _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, 20, 20)
                kind = 'rounded'

            self._last_native_region_kind = kind

            if hrgn:
                ok = _user32.SetWindowRgn(hwnd, hrgn, True)
                if ok:
                    # Windows owns hrgn on success — do NOT DeleteObject
                    self._last_native_region_status = 'applied'
                    logger.debug(
                        "[REPLICATOR REGION] hwnd=%d shape=%s kind=%s size=%dx%d status=applied",
                        hwnd, shape, kind, w, h,
                    )
                else:
                    err = ctypes.GetLastError()
                    self._last_native_region_status = 'failed'
                    self._last_native_region_error  = err
                    _gdi32.DeleteObject(hrgn)
                    logger.debug(
                        "[REPLICATOR REGION] hwnd=%d shape=%s SetWindowRgn FAILED err=%d",
                        hwnd, shape, err,
                    )
            else:
                self._last_native_region_status = 'null_hrgn'
                logger.debug(
                    "[REPLICATOR REGION] hwnd=%d shape=%s CreateRgn returned NULL",
                    hwnd, shape,
                )
        except Exception as e:
            self._last_native_region_status = 'exception'
            self._last_native_region_error  = str(e)
            logger.debug("[REPLICATOR REGION] error: %s", e)

    def _apply_dwm_chrome_suppression(self) -> None:
        """Suppress native DWM border and corner rounding via DwmSetWindowAttribute.
        Windows 11+ only for corner pref / border color; best-effort, never raises."""
        try:
            import sys
            if sys.platform != 'win32':
                self._last_dwm_chrome_status = 'not_win32'
                return
            import ctypes

            hwnd = int(self.winId())
            if not hwnd:
                self._last_dwm_chrome_status = 'no_hwnd'
                return

            self._last_dwm_hwnd  = hwnd
            self._last_dwm_error = None

            _dwmapi = ctypes.windll.dwmapi
            _dwmapi.DwmSetWindowAttribute.restype  = ctypes.c_long
            _dwmapi.DwmSetWindowAttribute.argtypes = [
                ctypes.c_void_p,   # hwnd
                ctypes.c_uint,     # dwAttribute
                ctypes.c_void_p,   # pvAttribute
                ctypes.c_uint,     # cbAttribute
            ]

            # A) Disable DWM corner rounding — DWMWA_WINDOW_CORNER_PREFERENCE=33
            #    DWMWCP_DONOTROUND=1  (Windows 11+, silently ignored on Win10)
            corner_val = ctypes.c_int(1)
            hr_corner  = _dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(corner_val), ctypes.sizeof(corner_val),
            )
            self._last_dwm_corner_pref_status = (
                f"ok:0x{hr_corner & 0xFFFFFFFF:08x}" if hr_corner == 0
                else f"failed:0x{hr_corner & 0xFFFFFFFF:08x}"
            )

            # B) Remove native border — DWMWA_BORDER_COLOR=34
            #    DWMWA_COLOR_NONE=0xFFFFFFFE  (Windows 11+)
            border_val = ctypes.c_uint(0xFFFFFFFE)
            hr_border  = _dwmapi.DwmSetWindowAttribute(
                hwnd, 34, ctypes.byref(border_val), ctypes.sizeof(border_val),
            )
            self._last_dwm_border_color_status = (
                f"ok:0x{hr_border & 0xFFFFFFFF:08x}" if hr_border == 0
                else f"failed:0x{hr_border & 0xFFFFFFFF:08x}"
            )

            ok_count = sum([hr_corner == 0, hr_border == 0])
            self._last_dwm_chrome_status = (
                'applied' if ok_count == 2 else
                'partial' if ok_count == 1 else
                'failed'
            )
            logger.debug(
                "[REPLICATOR DWM] hwnd=%d corner=%s border=%s status=%s",
                hwnd,
                self._last_dwm_corner_pref_status,
                self._last_dwm_border_color_status,
                self._last_dwm_chrome_status,
            )
        except Exception as e:
            self._last_dwm_chrome_status = 'exception'
            self._last_dwm_error         = str(e)
            logger.debug("[REPLICATOR DWM] error: %s", e)

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

    def _monitor_focus(self):
        try:
            # Lazily resolve hwnd for overlays created without explicit hwnd (restore path)
            if not self._hwnd and callable(self._hwnd_getter):
                self._hwnd = self._hwnd_getter()

            fg = get_foreground_hwnd()
            # Honour settle period: if F14 or click just changed focus programmatically,
            # use the intended hwnd instead of the real (possibly lagging) Windows fg.
            if time.perf_counter() < ReplicationOverlay._active_hwnd_override_until:
                fg = ReplicationOverlay._active_hwnd_override
            # If nothing changed, skip update to save CPU (most ticks hit this early-exit)
            if fg == getattr(self, '_last_monitor_fg', 0):
                return
            self._last_monitor_fg = fg

            was_active = self._is_active_client
            self._is_active_client = bool(self._hwnd and fg == self._hwnd)

            if was_active != self._is_active_client:
                ReplicationOverlay.notify_active_client_changed(fg)

            if self._ov_cfg.get('hide_when_inactive', False):
                eve_hwnds = self._get_cached_eve_hwnds()
                # Belt-and-suspenders: include every overlay's target hwnd even if
                # find_eve_windows() missed it (e.g., client just launched or borderless mode)
                _extra = {ov._hwnd for ov in list(_OVERLAY_REGISTRY) if ov._hwnd}
                if _extra - eve_hwnds:
                    eve_hwnds = eve_hwnds | _extra
                _context_ok = should_show_overlays(fg, eve_hwnds)
                if _context_ok:
                    if not self.isVisible():
                        # Restore geometry as plain ints (not QRect) to survive Qt's show() dance
                        saved = getattr(self, '_last_visible_geom', None)
                        if saved:
                            sx, sy, sw, sh = saved
                        self.show()
                        if saved:
                            # Apply immediately + deferred (DWM compositing can shift window)
                            self.setGeometry(sx, sy, sw, sh)
                            QTimer.singleShot(0,  lambda x=sx,y=sy,w=sw,h=sh: self.setGeometry(x,y,w,h))
                            QTimer.singleShot(60, lambda x=sx,y=sy,w=sw,h=sh: self._restore_and_verify(x,y,w,h))
                        _log_hide_show_event('SHOW', self._title,
                                             f"restore_geometry=x={sx} y={sy} w={sw} h={sh}" if saved else "no_saved_geom")
                        logger.debug(f"[HIDE FILTER] fg={fg} context=eve/app action=show title={self._title!r}")
                else:
                    if self.isVisible():
                        g = self.geometry()
                        # Store as a plain tuple — avoids QRect lifetime issues
                        self._last_visible_geom = (g.x(), g.y(), g.width(), g.height())
                        _log_hide_show_event('HIDE', self._title,
                                             f"save_geometry=x={g.x()} y={g.y()} w={g.width()} h={g.height()}")
                        self.hide()
                        logger.debug(f"[HIDE FILTER] fg={fg} context=external action=hide title={self._title!r}")
        except Exception:
            pass

    @staticmethod
    def notify_active_client_changed(active_hwnd: int):
        """Instant update of active border for all overlays. Single source of truth."""
        t0 = time.perf_counter()
        # 300ms settle: prevents the 500ms monitor timer from undoing programmatic focus changes
        ReplicationOverlay._active_hwnd_override = active_hwnd
        ReplicationOverlay._active_hwnd_override_until = t0 + 0.3
        count = 0
        for ov in list(_OVERLAY_REGISTRY):
            was_active = ov._is_active_client
            ov._is_active_client = bool(ov._hwnd and active_hwnd == ov._hwnd)
            if was_active != ov._is_active_client:
                ov.update()
                count += 1
        dt = (time.perf_counter() - t0) * 1000
        logger.info(f"[REPLICATOR ACTIVE BORDER] target_hwnd={active_hwnd} updated={count} ms={dt:.2f}")

    # ------------------------------------------------------------------
    # Monitor: active-border + hide_when_inactive (Fix #4)
    # ------------------------------------------------------------------
    # Sync-resize support
    # ------------------------------------------------------------------

    def apply_size(self, w: int, h: int):
        """Called by peer overlays to broadcast a resize."""
        if self._applying_sync_resize:
            return
        self._applying_sync_resize = True
        try:
            self.resize(max(20, w), max(20, h))
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
        # Save current replicated region (ROI)
        self._ov_cfg['region_x'] = self._region.get('x', 0.0)
        self._ov_cfg['region_y'] = self._region.get('y', 0.0)
        self._ov_cfg['region_w'] = self._region.get('w', 1.0)
        self._ov_cfg['region_h'] = self._region.get('h', 1.0)
        
        if hasattr(self, '_thread'):
            self._ov_cfg['fps'] = self._thread._fps
        save_overlay_cfg(self._cfg, self._title, self._ov_cfg)

    # ------------------------------------------------------------------
    # Apply settings from another overlay (apply-to-all feature)
    # ------------------------------------------------------------------

    def apply_settings_dict(self, settings: dict, persist: bool = True):
        """Absorb a batch of settings keys (from apply-to-all)."""
        self._ov_cfg.update(settings)
        
        # Apply region if present
        if 'region_x' in settings:
            self._region['x'] = settings['region_x']
            self._region['y'] = settings.get('region_y', self._region['y'])
            self._region['w'] = settings.get('region_w', self._region['w'])
            self._region['h'] = settings.get('region_h', self._region['h'])
            
        self.apply_always_on_top(bool(self._ov_cfg.get('always_on_top', True)))
        if hasattr(self, '_thread'):
            self._ov_cfg['fps'] = int(self._ov_cfg.get('fps', 30))
            self._thread.set_fps(self._ov_cfg['fps'])
            
        if 'border_shape' in settings:
            self._apply_window_shape_mask()
        self.update()
        if persist:
            self._schedule_autosave()

    def reload_overlay_config(self):
        """Reload _ov_cfg from the master cfg dict (used after apply_common_settings_to_all)."""
        self._ov_cfg = get_overlay_cfg(self._cfg, self._title)
        self.apply_always_on_top(bool(self._ov_cfg.get('always_on_top', True)))
        if hasattr(self, '_thread'):
            self._thread.set_fps(int(self._ov_cfg.get('fps', 30)))
        self._apply_window_shape_mask()
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

    def _get_asset_icon(self, name: str) -> QIcon:
        """Helper para cargar iconos personalizados desde el directorio assets."""
        try:
            from utils.paths import get_resource_path
            icon_file = get_resource_path(f"assets/{name}.png")
            if icon_file.exists():
                return QIcon(str(icon_file))
        except Exception:
            pass
        return QIcon() # Fallback vacío

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #0a0a0a; border: 1px solid #00c8ff; color: #fff; padding: 5px; }
            QMenu::item { padding: 5px 25px; }
            QMenu::item:selected { background: #004466; }
        """)

        style = self.style()
        # Placeholder transparente para alineación perfecta
        transparent = QPixmap(16, 16)
        transparent.fill(Qt.GlobalColor.transparent if hasattr(Qt, 'GlobalColor') else Qt.transparent)
        placeholder = QIcon(transparent)
        
        # 1. Sincronizar
        icon_sync = self._get_asset_icon("sincronizar")
        act_sync = menu.addAction(icon_sync, "Sincronizar réplicas")
        act_sync.setCheckable(True)
        act_sync.setChecked(self._sync_active)
        act_sync.triggered.connect(self._toggle_sync)

        # 2. FPS
        fps_menu = menu.addMenu(self._get_asset_icon("fps"), "Fotogramas (FPS)")
        cur_fps = self._thread._fps if hasattr(self, '_thread') else 30
        for val in [1, 5, 10, 15, 30, 60, 120]:
            label = f"✓ {val} FPS" if val == cur_fps else f"{val} FPS"
            act = fps_menu.addAction(placeholder, label)
            act.triggered.connect(lambda _, v=val: self._set_fps(v))

        # 3. Zona
        icon_zone = self._get_asset_icon("region")
        act_wizard = menu.addAction(icon_zone, "Cambiar Zona")
        act_wizard.triggered.connect(lambda: self._relaunch_wizard())

        menu.addSeparator()

        # 4. Ajustes
        icon_settings = self._get_asset_icon("ajuste")
        act_settings = menu.addAction(icon_settings, "Ajustes")
        act_settings.triggered.connect(lambda: QTimer.singleShot(0, self._open_settings))

        menu.addSeparator()

        # 5. Información
        icon_info = self._get_asset_icon("informacion")
        act_info = menu.addAction(icon_info, "Información")
        act_info.triggered.connect(lambda: self._show_info_dialog())

        menu.addSeparator()

        # 6. Cerrar
        icon_close = style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton if hasattr(QStyle.StandardPixmap, 'SP_TitleBarCloseButton') else QStyle.SP_TitleBarCloseButton)
        act_close = menu.addAction(icon_close, "Cerrar")
        act_close.triggered.connect(self.close)

        menu.exec(event.globalPos())

    def _open_settings(self, _checked=False):
        """Abre o trae al frente el diálogo de ajustes del Replicador."""
        logger.info(f"[REPLICATOR MENU] _open_settings called for {self._title}")

        # 1. Reutilizar si ya existe (visible u oculto) — evita crear múltiples instancias
        # y el bug donde destroyed() del diálogo viejo nulifica la referencia al nuevo.
        if hasattr(self, "_settings_dialog") and self._settings_dialog is not None:
            try:
                is_visible = self._settings_dialog.isVisible()
                if not is_visible:
                    logger.info("[REPLICATOR MENU] Diálogo existente oculto, mostrando")
                    self._settings_dialog.show()
                else:
                    logger.info("[REPLICATOR MENU] Diálogo existente visible, activando")
                self._settings_dialog.raise_()
                self._settings_dialog.activateWindow()
                return
            except (RuntimeError, ReferenceError):
                logger.info("[REPLICATOR MENU] Referencia muerta detectada, limpiando")
                self._settings_dialog = None

        # 2. Crear nueva instancia
        try:
            logger.info(f"[REPLICATOR MENU] Creando nueva instancia de ReplicatorSettingsDialog")
            dlg = ReplicatorSettingsDialog(self)

            # Persistencia de referencia
            self._settings_dialog = dlg

            # Limpiar referencia solo al destruir (no al ocultar con accept/reject)
            dlg.destroyed.connect(self._on_settings_destroyed)

            # Configuración de ventana (No Modal)
            dlg.setModal(False)
            dlg.setWindowModality(Qt.WindowModality.NonModal if hasattr(Qt, 'WindowModality') else Qt.NonModal)

            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

            # Refuerzo topmost
            try:
                from overlay.dialog_utils import make_replicator_dialog_topmost
                make_replicator_dialog_topmost(dlg, modal=False)
            except Exception as e:
                logger.debug(f"Topmost reinforcement error: {e}")

            logger.info("[REPLICATOR MENU] Diálogo abierto con éxito")

        except Exception as e:
            import traceback
            try:
                log_path = Path(__file__).parent.parent / 'logs' / 'replicator_settings_debug.log'
                log_path.parent.mkdir(exist_ok=True)
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n[{self._title}] {traceback.format_exc()}\n")
            except Exception:
                pass
            logger.exception(f"[REPLICATOR MENU] Error crítico instanciando Ajustes: {e}")

    def _on_settings_destroyed(self):
        """Callback cuando el diálogo es destruido por Qt."""
        logger.info(f"[REPLICATOR MENU] Diálogo de ajustes destruido para {self._title}")
        self._settings_dialog = None

    def _show_info_dialog(self):
        if hasattr(self, "_info_dialog") and self._info_dialog and self._info_dialog.isVisible():
            self._info_dialog.raise_()
            self._info_dialog.activateWindow()
            return

        from overlay.dialog_utils import REPLICATOR_STYLE, make_replicator_dialog_topmost
        
        dlg = QDialog(None) # Parent=None para evitar que bloquee al overlay padre de forma modal implícita
        dlg.setWindowTitle("Información de la réplica")
        dlg.setMinimumSize(320, 380)
        dlg.setStyleSheet(REPLICATOR_STYLE)
        
        # Flags para que se comporte como ventana de herramientas flotante
        flags = (Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint) if hasattr(Qt, 'WindowType') else (Qt.Tool | Qt.WindowStaysOnTopHint)
        dlg.setWindowFlags(flags)
        
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(15, 15, 15, 15)
        
        lbl_title = QLabel("GUÍA RÁPIDA DE COMANDOS")
        lbl_title.setObjectName("section")
        lay.addWidget(lbl_title)
        
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFrameStyle(0) # No border
        txt.setStyleSheet("background: transparent; color: #e2e8f0; font-size: 11px;")
        
        guide_text = (
            "<b>Interacciones del Ratón:</b><br>"
            "• <b>Click izquierdo:</b> Enfocar cliente EVE.<br>"
            "• <b>Click derecho:</b> Abrir menú de opciones.<br>"
            "• <b>Rueda ratón:</b> Zoom +/- del área (ROI).<br>"
            "• <b>Ctrl + Rueda:</b> Ajustar ancho de ventana.<br>"
            "• <b>Shift + Rueda:</b> Ajustar alto de ventana.<br><br>"
            "<b>Teclado (Foco en réplica):</b><br>"
            "• <b>Flechas:</b> Desplazar vista capturada.<br>"
            "• <b>Shift + Flechas:</b> Desplazamiento rápido.<br>"
            "• <b>Ctrl + Arriba/Abajo:</b> Zoom preciso.<br><br>"
            "<b>Configuración:</b><br>"
            "• <b>Ajustes:</b> Personaliza bordes, etiquetas y hotkeys.<br>"
            "• <b>Sincronizar réplicas:</b> Copia el layout actual a todas las demás ventanas activas."
        )
        txt.setHtml(guide_text)
        lay.addWidget(txt)
        
        btn_close = QPushButton("Entendido")
        btn_close.clicked.connect(dlg.close)
        lay.addWidget(btn_close)
        
        self._info_dialog = dlg
        make_replicator_dialog_topmost(dlg)
        dlg.show()

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
        # Accept keys when this widget has Qt focus OR the mouse is currently hovering over it
        if not self.hasFocus() and not self.underMouse():
            super().keyPressEvent(event)
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
        # No hasFocus() check — wheel events arrive at the widget under the cursor regardless of focus
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

    def _zoom_roi(self, factor):
        """Wrapper de compatibilidad para zoom uniforme."""
        return self._zoom_roi_ex(factor, factor)

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
        # [CORRECCIÓN] Sincronizar solo el transform de vista interno.
        # NO debemos llamar a self.resize() aquí para evitar que el zoom 
        # redimensione las ventanas de los peers.
        self._region.update(reg_dict)
        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def _build_visual_shape_path(self) -> QPainterPath:
        """Full-widget clip path matching the Win32 region and bitmap mask."""
        shape = self._ov_cfg.get('border_shape', 'square')
        path  = QPainterPath()
        r     = QRectF(self.rect())
        w, h  = self.width(), self.height()
        if shape == 'pill':
            if abs(w - h) <= 2:
                path.addEllipse(r)
            else:
                radius = min(w, h) / 2.0
                path.addRoundedRect(r, radius, radius)
        elif shape == 'rounded':
            path.addRoundedRect(r, 20.0, 20.0)
        else:
            path.addRect(r)
        return path

    def _get_shape_path(self, rect: QRectF, shape: str, bw: float) -> QPainterPath:
        path = QPainterPath()
        if shape == 'pill':
            radius = min(rect.width(), rect.height()) / 2.0
            path.addRoundedRect(rect, radius, radius)
        elif shape == 'rounded':
            path.addRoundedRect(rect, 8, 8)
        else:
            path.addRect(rect)
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        rh_smooth = (QPainter.RenderHint.SmoothPixmapTransform
                     if hasattr(QPainter, 'RenderHint')
                     else QPainter.SmoothPixmapTransform)
        rh_aa = (QPainter.RenderHint.Antialiasing
                 if hasattr(QPainter, 'RenderHint')
                 else QPainter.Antialiasing)
        p.setRenderHint(rh_smooth)
        p.setRenderHint(rh_aa)

        ov    = self._ov_cfg
        bw    = max(1, int(ov.get('border_width', 2))) if ov.get('border_visible', True) else 0
        shape = ov.get('border_shape', 'square')
        if shape not in ('square', 'rounded', 'pill'):
            shape = 'rounded' if shape == 'glow' else 'square'

        # 1) Clear backing buffer to fully transparent.
        # CompositionMode_Source writes alpha=0 everywhere regardless of destination,
        # so stale pixels from previous frames outside the shape are erased.
        # This MUST happen before setClipPath — otherwise corners stay dirty.
        cm_src  = (QPainter.CompositionMode.CompositionMode_Source
                   if hasattr(QPainter, 'CompositionMode')
                   else QPainter.CompositionMode_Source)
        cm_over = (QPainter.CompositionMode.CompositionMode_SourceOver
                   if hasattr(QPainter, 'CompositionMode')
                   else QPainter.CompositionMode_SourceOver)
        _transparent = (Qt.GlobalColor.transparent
                        if hasattr(Qt, 'GlobalColor') else Qt.transparent)
        p.setCompositionMode(cm_src)
        p.fillRect(self.rect(), _transparent)
        p.setCompositionMode(cm_over)

        # 2) Set the outer shape clip BEFORE any save()/restore() block.
        # After p.save() the clip is preserved in the saved state, so p.restore()
        # returns to this clip — keeping label, border and debug layers inside the shape.
        shape_path = self._build_visual_shape_path()
        if shape != 'square':
            p.setClipPath(shape_path)

        # 3) Optional gray frame — square only; never draw a rectangular frame on
        # pill/rounded because it would leak outside the clipped shape.
        if shape == 'square' and ov.get('show_gray_frame', True):
            p.fillRect(self.rect(), Qt.black)
            p.setPen(QPen(QColor(100, 100, 100, 40), 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Border and content rects (computed once, shared by all paint stages)
        adj          = bw / 2.0
        border_rect  = QRectF(self.rect()).adjusted(adj, adj, -adj, -adj)
        content_rect = self.rect().adjusted(bw, bw, -bw, -bw)

        # 4) Captured frame
        if self._pixmap:
            p.save()
            if shape in ('rounded', 'pill'):
                # Tighter inner clip for content area (excludes the border strip).
                # setClipPath inside save() overrides to inner_path; p.restore()
                # returns us to the outer shape_path clip automatically.
                inner_path = self._get_shape_path(
                    QRectF(self.rect()).adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2),
                    shape, bw,
                )
                p.fillPath(inner_path, Qt.black)
                p.setClipPath(inner_path)

            pw, ph     = self._pixmap.width(), self._pixmap.height()
            src_aspect = pw / ph if ph > 0 else 1.0
            dst_aspect = (content_rect.width() / content_rect.height()
                          if content_rect.height() > 0 else 1.0)

            if ov.get('maintain_aspect', True):
                # "Cover" mode: Scale to cover the entire content_rect and crop excess
                # This avoids black bars on the sides when the container ratio changes.
                scale = max(content_rect.width() / pw, content_rect.height() / ph)
                final_w = pw * scale
                final_h = ph * scale
                tx = content_rect.left() + (content_rect.width() - final_w) / 2.0
                ty = content_rect.top() + (content_rect.height() - final_h) / 2.0
                p.drawPixmap(QRectF(tx, ty, final_w, final_h).toRect(), self._pixmap)
            else:
                p.drawPixmap(content_rect, self._pixmap)
            p.restore()
            # After restore, the outer shape_path clip is active again.
        else:
            p.setPen(Qt.cyan)
            p.drawText(self.rect(), Qt.AlignCenter, self._status)

        # 5) Main border (cyan / green active) — within shape_path clip
        if ov.get('border_visible', True):
            hex_col = (ov.get('active_border_color', '#00ff64')
                       if ov.get('highlight_active', True) and self._is_active_client
                       else ov.get('client_color', '#00c8ff'))
            p.setPen(QPen(QColor(hex_col), bw))
            if shape in ('rounded', 'pill'):
                p.drawPath(self._get_shape_path(border_rect, shape, bw))
            else:
                p.drawRect(border_rect)

        # 6) Label — within shape_path clip (clipped to circle if it falls in a corner)
        if ov.get('label_visible', True):
            label_text = self._extract_label()
            fs  = max(6, int(ov.get('label_font_size', 10)))
            pad = max(0, int(ov.get('label_padding', 4)))
            font = QFont()
            font.setPointSize(fs)
            p.setFont(font)
            fm = p.fontMetrics()
            tw = (fm.horizontalAdvance(label_text)
                  if hasattr(fm, 'horizontalAdvance') else fm.width(label_text))
            th  = fm.height()
            lw, lh = tw + pad * 2, th + pad * 2

            pos_key = ov.get('label_pos', 'top_left')
            lx = (self.width() - lw - 2  if 'right'  in pos_key else
                  (self.width() - lw) // 2 if 'center' in pos_key else 2)
            ly = (self.height() - lh - 2) if 'bottom' in pos_key else 2

            if ov.get('label_bg', True):
                bg = QColor(ov.get('label_bg_color', '#000000'))
                bg.setAlphaF(max(0.0, min(1.0, float(ov.get('label_bg_opacity', 0.65)))))
                p.fillRect(lx, ly, lw, lh, bg)

            p.setPen(QColor(ov.get('label_color', '#ffffff')))
            p.drawText(lx + pad, ly + pad + fm.ascent(), label_text)

        # 7) Debug visual layers (diagnostics dialog only) — within shape_path clip
        if self._debug_visual_layers:
            try:
                p.save()
                p.fillRect(self.rect(), QColor(255, 255, 0, 18))
                p.setPen(QPen(QColor(255, 220, 0, 200), 1))
                p.drawRect(self.rect().adjusted(0, 0, -1, -1))
                p.setPen(QPen(QColor(255, 60, 60, 200), 1))
                br_int = border_rect.toRect() if hasattr(border_rect, 'toRect') else border_rect
                p.drawRect(br_int)
                p.fillRect(content_rect, QColor(0, 80, 255, 22))
                p.setPen(QPen(QColor(0, 100, 255, 200), 1))
                p.drawRect(content_rect)
                if shape in ('rounded', 'pill'):
                    p.setPen(QPen(QColor(0, 255, 100, 200), 1))
                    p.drawPath(self._get_shape_path(border_rect, shape, bw))
                p.restore()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Geometry events for real-time sync with settings
    # ------------------------------------------------------------------
    def moveEvent(self, event):
        super().moveEvent(event)
        self.geometryChanged.emit(self.x(), self.y(), self.width(), self.height())
        # Keep _last_visible_geom current so hide/show restores the latest position
        if self.isVisible():
            self._last_visible_geom = (self.x(), self.y(), self.width(), self.height())

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
                self.resize(max(20, pos.x()), max(20, pos.y()))
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

    def enterEvent(self, event):
        """Mejorar responsividad: tomar foco al entrar el ratón."""
        ReplicationOverlay._hover_overlay = self
        if not self.hasFocus():
            self.setFocus(Qt.FocusReason.MouseFocusReason if hasattr(Qt.FocusReason, 'MouseFocusReason') else Qt.MouseFocusReason)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if ReplicationOverlay._hover_overlay is self:
            ReplicationOverlay._hover_overlay = None
        super().leaveEvent(event)

    def _restore_and_verify(self, x: int, y: int, w: int, h: int):
        """Deferred geometry restore with mismatch logging (called ~60 ms after show)."""
        if getattr(self, '_shutting_down', False):
            return
        try:
            self.setGeometry(x, y, w, h)
            g = self.geometry()
            if g.x() != x or g.y() != y or g.width() != w or g.height() != h:
                _log_hide_show_event('SHOW VERIFY WARN', self._title,
                                     f"expected=x={x} y={y} w={w} h={h} "
                                     f"actual=x={g.x()} y={g.y()} w={g.width()} h={g.height()}")
                # One final forced correction
                self.setGeometry(x, y, w, h)
        except Exception:
            pass

    def _do_hover_wheel(self, delta: int):
        """Deliver a synthesized wheel event from the WH_MOUSE_LL hook (EVE has OS focus)."""
        try:
            import ctypes
            import ctypes.wintypes
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            local = self.mapFromGlobal(QPoint(pt.x, pt.y))
            mx_rel = local.x() / self.width()  if self.width()  > 0 else 0.5
            my_rel = local.y() / self.height() if self.height() > 0 else 0.5
            shift = ctypes.windll.user32.GetKeyState(0x10) & 0x8000  # VK_SHIFT
            ctrl  = ctypes.windll.user32.GetKeyState(0x11) & 0x8000  # VK_CONTROL
            factor = 1.03 if delta > 0 else 0.97
            if shift:
                self.resize(self.width(), max(20, int(self.height() * factor)))
            elif ctrl:
                self.resize(max(20, int(self.width() * factor)), self.height())
            else:
                f_inv = 0.97 if delta > 0 else 1.03
                self._zoom_roi_ex(f_inv, f_inv, mx_rel, my_rel)
            self.update()
            if self._sync_active:
                self.sync_triggered.emit(self._region)
        except Exception:
            pass

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
                if ok:
                    ReplicationOverlay.notify_active_client_changed(self._hwnd)
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
        self.geometryChanged.emit(self.x(), self.y(), self.width(), self.height())
        self._apply_window_shape_mask()

    def showEvent(self, event):
        super().showEvent(event)
        # Re-apply mask after show(): setWindowFlags + show() can reset the mask on Windows.
        # Extra deferred shots cover DWM re-compositing that happens after the initial show.
        self._apply_window_shape_mask()
        QTimer.singleShot(50,  self._apply_window_shape_mask)
        QTimer.singleShot(250, self._apply_window_shape_mask)
        self.update()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        for _attr in ('_monitor_timer', '_autosave_timer', '_top_timer'):
            if hasattr(self, _attr):
                getattr(self, _attr).stop()

        # Skip per-overlay save during global shutdown (TrayManager handles the final write)
        if not self._shutting_down:
            self._do_save()

        self.closed.emit(self._title)
        if hasattr(self, '_thread'):
            if self._shutting_down:
                self._thread.set_fast_stop(True)
            self._thread.stop()
        super().closeEvent(event)
