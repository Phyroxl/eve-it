import ctypes
import logging
import time
from ctypes import wintypes as wt
from typing import Optional, List, Dict

logger = logging.getLogger('eve.capture')

# Win32 Constants
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wt.DWORD),
        ('biWidth', wt.LONG),
        ('biHeight', wt.LONG),
        ('biPlanes', wt.WORD),
        ('biBitCount', wt.WORD),
        ('biCompression', wt.DWORD),
        ('biSizeImage', wt.DWORD),
        ('biXPelsPerMeter', wt.LONG),
        ('biYPelsPerMeter', wt.LONG),
        ('biClrUsed', wt.DWORD),
        ('biClrImportant', wt.DWORD),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wt.DWORD * 3)]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

IS_WINDOWS = True

def find_eve_windows() -> List[Dict]:
    """Busca ventanas de EVE Online filtrando por la clase técnica 'trinityWindow'."""
    result = []
    def enum_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        
        # Filtro por Clase (trinityWindow es la clase real del cliente de juego)
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        if class_buf.value != "trinityWindow":
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0: return True
        
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        
        if w > 100 and h > 100:
            result.append({
                'hwnd': hwnd,
                'title': title,
                'pid': pid.value,
                'size': (w, h),
                'rect': (rect.left, rect.top, rect.right, rect.bottom)
            })
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(enum_cb), 0)
    return result

def resolve_eve_window_handle(title_hint: str) -> Optional[int]:
    """Encuentra el HWND de una ventana de EVE por coincidencia de clase y título."""
    all_wins = find_eve_windows()
    # Limpiar el hint (quitar PID si existe)
    base_hint = title_hint.split(' [#')[0] if ' [#' in title_hint else title_hint
    
    # Intentar match exacto de título primero
    for w in all_wins:
        if base_hint in w['title']:
            return w['hwnd']
    return None

def capture_window_region(hwnd: int, region_rel: dict, out_w: int, out_h: int) -> Optional[bytes]:
    """Captura una región de la ventana usando PrintWindow (más lento pero evita congelamientos en EVE)."""
    if not hwnd or not user32.IsWindow(hwnd): return None
    if user32.IsIconic(hwnd): return b"MINIMIZED"

    # Obtener dimensiones de la ventana completa (necesario para PrintWindow)
    rect = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)): return None
    ww = rect.right - rect.left
    wh = rect.bottom - rect.top
    if ww <= 0 or wh <= 0: return None

    # Coordenadas relativas -> píxeles
    rx = int(max(0, min(1.0, region_rel.get('x', 0))) * ww)
    ry = int(max(0, min(1.0, region_rel.get('y', 0))) * wh)
    rw = int(max(0.01, min(1.0, region_rel.get('w', 0.1))) * ww)
    rh = int(max(0.01, min(1.0, region_rel.get('h', 0.1))) * wh)

    hdc_mem = None
    hbmp = None
    old_bmp = None
    data = None

    try:
        # Usamos el DC de la pantalla como referencia para compatibilidad de formato
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        
        # BMP intermedio para PrintWindow (tamaño completo de la ventana cliente)
        # EVE requiere capturar toda la ventana y luego recortar para que PrintWindow sea estable
        hbmp_full = gdi32.CreateCompatibleBitmap(hdc_screen, ww, wh)
        user32.ReleaseDC(0, hdc_screen)
        
        old_full = gdi32.SelectObject(hdc_mem, hbmp_full)
        
        # PW_RENDERFULLCONTENT = 2. Es CRÍTICO para evitar imágenes negras o congeladas en DX11.
        if user32.PrintWindow(hwnd, hdc_mem, 2):
            # Ahora escalamos el recorte al tamaño de salida deseado
            # Creamos el DC y BMP de salida
            hdc_final = gdi32.CreateCompatibleDC(hdc_mem)
            hbmp_final = gdi32.CreateCompatibleBitmap(hdc_mem, out_w, out_h)
            old_final = gdi32.SelectObject(hdc_final, hbmp_final)
            
            # Modo 3 = COLORONCOLOR. Es el más estable y compatible. 
            # El suavizado lo haremos en la capa de UI (Qt) para evitar pantallas negras.
            gdi32.SetStretchBltMode(hdc_final, 3)
            
            gdi32.StretchBlt(hdc_final, 0, 0, out_w, out_h, hdc_mem, rx, ry, rw, rh, SRCCOPY)
            
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = out_w
            bmi.bmiHeader.biHeight = -out_h
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            
            buf = ctypes.create_string_buffer(out_w * out_h * 4)
            if gdi32.GetDIBits(hdc_final, hbmp_final, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS):
                data = bytes(buf.raw)
            
            gdi32.SelectObject(hdc_final, old_final)
            gdi32.DeleteObject(hbmp_final)
            gdi32.DeleteDC(hdc_final)

        gdi32.SelectObject(hdc_mem, old_full)
        gdi32.DeleteObject(hbmp_full)
        gdi32.DeleteDC(hdc_mem)

    except Exception as e:
        logger.error(f"Capture error: {e}")

    return data

def set_no_activate(hwnd: int):
    if not hwnd: return
    ex_style = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, ex_style | 0x08000000)

def focus_eve_window(hwnd: int) -> bool:
    """Trae al frente el cliente EVE asociado al hwnd.
    Solo enfoca / restaura la ventana. NO envía clicks ni inputs al juego.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Restaurar si está minimizado
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Protocolo de foco: AttachThreadInput si otra ventana tiene el foco
        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd != hwnd:
            fore_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)
            curr_tid = kernel32.GetCurrentThreadId()
            attached = False
            if fore_tid and fore_tid != curr_tid:
                user32.AttachThreadInput(curr_tid, fore_tid, True)
                attached = True
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            if attached:
                user32.AttachThreadInput(curr_tid, fore_tid, False)
        user32.BringWindowToTop(hwnd)
        return True
    except Exception as e:
        logger.debug(f"focus_eve_window error: {e}")
        return False

def get_foreground_hwnd() -> int:
    """Devuelve el HWND de la ventana actualmente activa."""
    try:
        return user32.GetForegroundWindow()
    except Exception:
        return 0


def verify_foreground_window(hwnd: int, timeout_ms: int = 40, poll_ms: int = 2) -> tuple:
    """Poll GetForegroundWindow until it matches hwnd or timeout expires.

    Returns (verified, actual_hwnd, elapsed_ms).
    Zero overhead on success (typically 1-5 ms). Max wait = timeout_ms.
    """
    import time as _t
    if not hwnd:
        return False, 0, 0.0
    t0 = _t.perf_counter()
    deadline = t0 + timeout_ms / 1000.0
    sleep_s = max(0.0005, poll_ms / 1000.0)
    actual = 0
    try:
        while _t.perf_counter() < deadline:
            try:
                actual = user32.GetForegroundWindow()
            except Exception:
                break
            if actual == hwnd:
                return True, actual, (_t.perf_counter() - t0) * 1000
            _t.sleep(sleep_s)
    except Exception:
        pass
    return False, actual, (_t.perf_counter() - t0) * 1000

def is_hwnd_valid(hwnd: int) -> bool:
    """Check if window handle is still valid and visible."""
    if not hwnd: return False
    return bool(user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))

def focus_eve_window_fast(hwnd: int) -> bool:
    """Optimized focus with minimal checks for hotkey speed."""
    if not hwnd: return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9) # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


# SetWindowPos flags for non-blocking Z-order raise
# SWP_NOSIZE(0x0001) | SWP_NOMOVE(0x0002) | SWP_ASYNCWINDOWPOS(0x4000)
# SWP_ASYNCWINDOWPOS: posts the request to the target thread instead of
# blocking via SendMessage — eliminates 200-300 ms cross-process stall.
_SWP_ASYNC_RAISE = 0x4003
# HWND_TOP = 0  (raise above all non-topmost siblings, no topmost flag)
_HWND_TOP = 0


def focus_eve_window_perf(hwnd: int) -> tuple:
    """Non-blocking focus with per-subfase timing.

    Returns (ok: bool, perf_line: str) for compact perf logging.
    Key change vs focus_eve_window_fast: replaces BringWindowToTop
    (synchronous cross-process SendMessage, up to 300 ms) with
    SetWindowPos+SWP_ASYNCWINDOWPOS (posts to target queue, returns
    in < 1 ms regardless of EVE's render/message load).
    """
    if not hwnd:
        return False, 'hwnd=0'

    t0 = time.perf_counter()

    # 1. Restore minimized window (only when iconic, usually fast)
    restore_ms = 0.0
    try:
        if user32.IsIconic(hwnd):
            tr = time.perf_counter()
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            restore_ms = (time.perf_counter() - tr) * 1000
    except Exception:
        pass

    # 2. Async Z-order raise — posts to EVE's queue, returns immediately.
    #    Does NOT block waiting for EVE to process WM_WINDOWPOSCHANGING.
    t_bring = time.perf_counter()
    try:
        user32.SetWindowPos(hwnd, _HWND_TOP, 0, 0, 0, 0, _SWP_ASYNC_RAISE)
    except Exception:
        pass
    bring_ms = (time.perf_counter() - t_bring) * 1000

    # 3. SetForegroundWindow — hotkey thread already holds foreground rights
    #    (granted by Windows when WM_HOTKEY is dispatched to our thread).
    t_setfg = time.perf_counter()
    ok = False
    try:
        ok = bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        pass
    setfg_ms = (time.perf_counter() - t_setfg) * 1000

    total_ms = (time.perf_counter() - t0) * 1000
    perf_line = (
        f'hwnd={hwnd} restore={restore_ms:.1f} bring={bring_ms:.1f} '
        f'setfg={setfg_ms:.1f} total={total_ms:.1f} ok={ok}'
    )
    return ok, perf_line

def get_window_title(hwnd: int) -> str:
    """Devuelve el título de una ventana dado su HWND."""
    if not hwnd:
        return ""
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""

def set_topmost(hwnd: int, topmost: bool):
    """Establece o quita el flag TOPMOST (siempre encima) de una ventana."""
    if not hwnd:
        return
    try:
        # HWND_TOPMOST = -1, HWND_NOTOPMOST = -2
        flag = -1 if topmost else -2
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
    except Exception as e:
        logger.debug(f"set_topmost error: {e}")


def get_window_pid(hwnd: int) -> int:
    """Devuelve el PID del proceso dueño de una ventana."""
    if not hwnd:
        return 0
    try:
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0


def should_show_overlays(fg_hwnd: int, eve_hwnds: set) -> bool:
    """Devuelve True si los overlays deben estar visibles.

    Oculta solo cuando el foreground NO es:
    - una ventana EVE
    - una ventana del propio proceso (Salva Suite, replicas, menus Qt)
    """
    if not fg_hwnd:
        return True  # foreground desconocido → mantener visibles
    if fg_hwnd in eve_hwnds:
        return True
    # Ventana del propio proceso (Salva Suite, diálogos, overlays, menús Qt)
    try:
        import os
        return get_window_pid(fg_hwnd) == os.getpid()
    except Exception:
        return True  # safe default: no ocultar


def get_window_size(hwnd: int) -> tuple:
    """Returns (w, h) of a window in pixels, or (0, 0) on failure."""
    if not hwnd:
        return (0, 0)
    try:
        rect = wt.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (max(0, rect.right - rect.left), max(0, rect.bottom - rect.top))
    except Exception:
        pass
    return (0, 0)
