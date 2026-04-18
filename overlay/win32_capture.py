"""
win32_capture.py — Funciones de bajo nivel para captura de ventanas EVE mediante Win32 API.
"""

from __future__ import annotations
import platform
import logging
from typing import Optional

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
            ('biSize', ctypes.c_uint32),
            ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16),
            ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32),
            ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32)
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ('bmiHeader', BITMAPINFOHEADER),
            ('bmiColors', ctypes.c_uint32 * 3)
        ]

    def enum_windows():
        """Lista todas las ventanas visibles con título."""
        results = []
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def _cb(hwnd, _lp):
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
            
        user32.EnumWindows(_cb, 0)
        return results

    def find_eve_windows():
        """Busca ventanas que parezcan de EVE Online."""
        result = []
        for w in enum_windows():
            t = w['title']
            # Filtro por título y tamaño mínimo
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
            
        # Ordenar por tamaño (las más grandes primero)
        result.sort(key=lambda x: x['size'][0] * x['size'][1], reverse=True)
        return result

    def capture_window_region(hwnd, region_rel, out_w=400, out_h=300):
        """Captura optimizada: solo la región necesaria y escalado rápido."""
        # 1. Obtener dimensiones del área cliente
        cl = wt.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(cl)):
            return None
        ww, wh = cl.right, cl.bottom
        if ww <= 0 or wh <= 0: return None

        # 2. Calcular región absoluta en píxeles
        rx = int(region_rel['x'] * ww)
        ry = int(region_rel['y'] * wh)
        rw = int(region_rel['w'] * ww)
        rh = int(region_rel['h'] * wh)
        if rw <= 0 or rh <= 0: return None

        # 3. Preparación de DCs y Bitmaps (Captura nativa 1:1)
        sdc = user32.GetDC(hwnd) 
        if not sdc: return None
        
        try:
            mdc = gdi32.CreateCompatibleDC(sdc)
            bmp = gdi32.CreateCompatibleBitmap(sdc, out_w, out_h)
            old = gdi32.SelectObject(mdc, bmp)
            
            # 4. Captura y Escalado de ALTA FIDELIDAD
            gdi32.SetStretchBltMode(mdc, 4) 
            ok = gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, sdc, rx, ry, rw, rh, SRCCOPY)
            
            data = None
            if ok:
                # 5. Extraer bits
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = out_w
                bmi.bmiHeader.biHeight = -out_h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0
                
                buf = ctypes.create_string_buffer(out_w * out_h * 4)
                gdi32.GetDIBits(mdc, bmp, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
                data = bytes(buf)
            
            # Limpieza
            gdi32.SelectObject(mdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mdc)
        finally:
            user32.ReleaseDC(hwnd, sdc)
        
        return data

    def set_click_through(hwnd, enabled):
        """Habilita o deshabilita el modo click-through."""
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            ex_style |= (WS_EX_LAYERED | WS_EX_TRANSPARENT)
        else:
            ex_style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def set_no_activate(hwnd):
        """Evita que la ventana tome el foco al ser pulsada."""
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def bring_window_to_front(hwnd):
        """Trae la ventana al frente sin necesariamente darle el foco (topmost)."""
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)

else:
    # Fallbacks para otros sistemas (no funcional, solo para evitar errores de importación)
    def enum_windows(): return []
    def find_eve_windows(): return []
    def capture_window_region(hwnd, r, w=400, h=300): return None
    def set_click_through(h, e): pass
    def set_no_activate(h): pass
    def bring_window_to_front(h): pass