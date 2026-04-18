"""
win32_capture.py — Funciones de bajo nivel para captura de ventanas EVE mediante Win32 API.
"""

from __future__ import annotations
import platform
import logging
from typing import Optional, List, Dict

logger = logging.getLogger('eve.win32_capture')

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes as wt
    
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    
    SRCCOPY = 0x00CC0020
    DIB_RGB_COLORS = 0
    PW_RENDERFULLCONTENT = 0x00000002
    
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000

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
            ('biClrImportant', wt.DWORD)
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wt.DWORD * 3)]

    def enum_windows() -> List[Dict]:
        """Enumera todas las ventanas visibles en el sistema."""
        results = []
        def _cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            
            length = user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            
            if not title:
                return True
                
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            
            if w <= 0 or h <= 0:
                return True
                
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            results.append({
                'hwnd': hwnd,
                'title': title,
                'pid': pid.value,
                'rect': (rect.left, rect.top, rect.right, rect.bottom),
                'size': (w, h)
            })
            return True
            
        user32.EnumWindows(ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(_cb), 0)
        return results

    def find_eve_windows() -> List[Dict]:
        """Busca ventanas que parezcan de EVE Online."""
        result = []
        for w in enum_windows():
            t = w['title']
            if not (('EVE —' in t or 'EVE - ' in t or t.upper() == 'EVE ONLINE') and 
                    w['size'][0] > 400 and w['size'][1] > 300):
                continue
            
            hwnd = w['hwnd']
            cl = wt.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(cl)):
                pt = wt.POINT(0, 0)
                user32.ClientToScreen(hwnd, ctypes.byref(pt))
                w['client_rect'] = (pt.x, pt.y, pt.x + cl.right, pt.y + cl.bottom)
                w['client_size'] = (cl.right, cl.bottom)
            else:
                l, t, r, b = w['rect']
                w['client_rect'] = (l, t, r, b)
                w['client_size'] = (r - l, b - t)
                
            result.append(w)
            
        result.sort(key=lambda x: x['size'][0] * x['size'][1], reverse=True)
        return result

    def capture_window_region(hwnd: int, region_rel: dict, out_w: int = 400, out_h: int = 300):
        """Captura robusta con fallback de PrintWindow."""
        if not hwnd or not user32.IsWindow(hwnd): return None
        
        cl = wt.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(cl)): return None
        ww, wh = cl.right, cl.bottom
        if ww <= 0 or wh <= 0: return None

        rx = int(region_rel['x'] * ww)
        ry = int(region_rel['y'] * wh)
        rw = int(region_rel['w'] * ww)
        rh = int(region_rel['h'] * wh)
        if rw <= 0 or rh <= 0: return None

        hdc_window = user32.GetDC(hwnd)
        if not hdc_window: return None
        
        mdc = gdi32.CreateCompatibleDC(hdc_window)
        bmp = gdi32.CreateCompatibleBitmap(hdc_window, out_w, out_h)
        old = gdi32.SelectObject(mdc, bmp)
        
        data = None
        ok = False
        try:
            gdi32.SetStretchBltMode(mdc, 4)
            full_mdc = gdi32.CreateCompatibleDC(hdc_window)
            full_bmp = gdi32.CreateCompatibleBitmap(hdc_window, ww, wh)
            f_old = gdi32.SelectObject(full_mdc, full_bmp)
            if user32.PrintWindow(hwnd, full_mdc, 0x3):
                gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, full_mdc, rx, ry, rw, rh, SRCCOPY)
                ok = True
            gdi32.SelectObject(full_mdc, f_old)
            gdi32.DeleteObject(full_bmp)
            gdi32.DeleteDC(full_mdc)

            if not ok:
                ok = gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, hdc_window, rx, ry, rw, rh, SRCCOPY)

            if ok:
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = out_w
                bmi.bmiHeader.biHeight = -out_h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0
                buf = ctypes.create_string_buffer(out_w * out_h * 4)
                gdi32.GetDIBits(mdc, bmp, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
                
                raw_bytes = buf.raw
                is_black = True
                for i in range(0, min(len(raw_bytes), 1000), 4):
                    if raw_bytes[i] != 0 or raw_bytes[i+1] != 0 or raw_bytes[i+2] != 0:
                        is_black = False
                        break
                
                if is_black:
                    foreground = user32.GetForegroundWindow()
                    if hwnd == foreground:
                        hdc_screen = user32.GetDC(0)
                        pt = wt.POINT(0, 0)
                        user32.ClientToScreen(hwnd, ctypes.byref(pt))
                        gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, hdc_screen, pt.x + rx, pt.y + ry, rw, rh, SRCCOPY)
                        user32.ReleaseDC(0, hdc_screen)
                        gdi32.GetDIBits(mdc, bmp, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
                        data = buf.raw
                    else:
                        data = raw_bytes
                else:
                    data = raw_bytes
            else:
                data = None
                    
        except Exception as e:
            logger.error(f"Error en captura: {e}")
        finally:
            gdi32.SelectObject(mdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mdc)
            user32.ReleaseDC(hwnd, hdc_window)
        return data

    def set_click_through(hwnd: int, enabled: bool):
        """Habilita o deshabilita el modo click-through."""
        if not hwnd: return
        try:
            ex_style = user32.GetWindowLongW(hwnd, -20)
            if enabled:
                user32.SetWindowLongW(hwnd, -20, ex_style | 0x00000020 | 0x00080000)
            else:
                user32.SetWindowLongW(hwnd, -20, ex_style & ~0x00000020 & ~0x00080000)
        except: pass

    def set_no_activate(hwnd: int):
        """Evita que la ventana tome el foco al ser pulsada."""
        if not hwnd: return
        try:
            ex_style = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, ex_style | 0x08000000)
        except: pass

    def bring_window_to_front(hwnd: int):
        """Trae la ventana al frente (topmost)."""
        if not hwnd: return
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)

else:
    def enum_windows(): return []
    def find_eve_windows(): return []
    def capture_window_region(hwnd, r, w=400, h=300): return None
    def set_click_through(h, e): pass
    def set_no_activate(h): pass
    def bring_window_to_front(h): pass