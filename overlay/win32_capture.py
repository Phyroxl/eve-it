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
        """Captura ultra-estable con priorización de rendimiento para evitar bloqueos."""
        if not hwnd or not user32.IsWindow(hwnd): return None
        
        # 1. Obtener dimensiones y estado de la ventana
        cl = wt.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(cl)): return None
        ww, wh = cl.right, cl.bottom
        if ww <= 0 or wh <= 0: return None

        # 2. Calcular coordenadas de la región
        rx, ry = int(region_rel['x'] * ww), int(region_rel['y'] * wh)
        rw, rh = int(region_rel['w'] * ww), int(region_rel['h'] * wh)
        if rw <= 0 or rh <= 0: return None

        hdc_window = None; mdc = None; bmp = None; hdc_screen = None; old_obj = None
        data = None
        
        try:
            # 3. Preparar DC de destino (memoria)
            hdc_window = user32.GetDC(hwnd)
            mdc = gdi32.CreateCompatibleDC(hdc_window)
            bmp = gdi32.CreateCompatibleBitmap(hdc_window, out_w, out_h)
            old_obj = gdi32.SelectObject(mdc, bmp)
            gdi32.SetStretchBltMode(mdc, 4) # STRETCH_HALFTONE

            # --- ESTRATEGIA DE CAPTURA DE ALTO RENDIMIENTO ---
            captured = False
            
            # A. Detectar si la ventana es la activa
            fg_hwnd = user32.GetForegroundWindow()
            is_foreground = (hwnd == fg_hwnd)
            
            # Si el foco está en el HUD, permitimos captura de pantalla solo si el juego está visible
            if not is_foreground and fg_hwnd:
                # Obtenemos el título de la ventana activa para ver si es nuestro HUD
                length = user32.GetWindowTextLengthW(fg_hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(fg_hwnd, buf, length + 1)
                    if "EVE Replica:" in buf.value or "Panel de control" in buf.value:
                        # El usuario está tocando la interfaz, el juego debería estar justo debajo
                        if not user32.IsIconic(hwnd):
                            is_foreground = True
            
            if is_foreground:
                hdc_screen = user32.GetDC(0)
                pt = wt.POINT(0, 0)
                user32.ClientToScreen(hwnd, ctypes.byref(pt))
                # Validar que la ventana está realmente en el área visible (no minimizada ni fuera)
                captured = gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, hdc_screen, pt.x + rx, pt.y + ry, rw, rh, SRCCOPY)
            
            # B. Si no está en primer plano, USAR CAPTURA INTERNA (BitBlt o PrintWindow)
            if not captured:
                captured = gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, hdc_window, rx, ry, rw, rh, SRCCOPY)
                
            # C. Fallback: Si sigue fallando (ventana oculta), usamos PrintWindow (con precaución)
            if not captured or gdi32.GetPixel(mdc, out_w//2, out_h//2) == 0:
                # Usar un DC intermedio para PrintWindow evita parpadeos y es más estable
                tmp_mdc = gdi32.CreateCompatibleDC(hdc_window)
                tmp_bmp = gdi32.CreateCompatibleBitmap(hdc_window, ww, wh)
                tmp_old = gdi32.SelectObject(tmp_mdc, tmp_bmp)
                
                # PW_CLIENTONLY = 1, PW_RENDERFULLCONTENT = 2 -> 0x3
                if user32.PrintWindow(hwnd, tmp_mdc, 0x3):
                    captured = gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, tmp_mdc, rx, ry, rw, rh, SRCCOPY)
                
                gdi32.SelectObject(tmp_mdc, tmp_old)
                gdi32.DeleteObject(tmp_bmp)
                gdi32.DeleteDC(tmp_mdc)

            # 4. Extraer bits
            if captured:
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = out_w
                bmi.bmiHeader.biHeight = -out_h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                buf = ctypes.create_string_buffer(out_w * out_h * 4)
                if gdi32.GetDIBits(mdc, bmp, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS):
                    # Forzar Alfa a 255 (Optimizado)
                    ba = bytearray(buf.raw)
                    ba[3::4] = b'\xff' * (len(ba) // 4)
                    data = bytes(ba)

        except Exception as e:
            logger.error(f"Error crítico en captura: {e}")
        finally:
            # LIMPIEZA TOTAL DE RECURSOS (Vital para evitar fugas y cuelgues)
            if old_obj: gdi32.SelectObject(mdc, old_obj)
            if bmp: gdi32.DeleteObject(bmp)
            if mdc: gdi32.DeleteDC(mdc)
            if hdc_window: user32.ReleaseDC(hwnd, hdc_window)
            if hdc_screen: user32.ReleaseDC(0, hdc_screen)
            
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