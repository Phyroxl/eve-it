"""force_square_corners — DWM Win11 override to prevent OS-level corner rounding."""
import sys


def force_square_corners(hwnd: int) -> None:
    """Override Win11 DWM corner rounding for a window handle.

    Calls DwmSetWindowAttribute(DWMWA_WINDOW_CORNER_PREFERENCE=33, DWMWCP_DONOTROUND=1).
    No-op on non-Windows or when DWM is unavailable.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_DONOTROUND = 1
        pref = ctypes.c_int(DWMWCP_DONOTROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )
    except Exception:
        pass
