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
        """Busca ventanas de EVE Online con un filtro permisivo para máxima compatibilidad."""
        result = []
        titles_seen = {}
        
        # Primero enumeramos todas las ventanas
        all_windows = enum_windows()
        
        # ORDENAR DETERMINÍSTICAMENTE por HWND antes de procesar títulos
        # Esto asegura que si hay varias ventanas con el mismo título, 
        # siempre reciban el mismo identificador en cada tick de refresco.
        all_windows.sort(key=lambda x: x['hwnd'])
        
        for w in all_windows:
            t_orig = w['title']
            t_upper = t_orig.upper()
            
            # Filtro estricto para clientes de juego
            # EVE Online usa "EVE -" o "EVE —" seguido del nombre del personaje.
            is_eve = (t_upper.startswith('EVE -') or t_upper.startswith('EVE —'))
            
            # Excluir explícitamente nuestra propia aplicación, lanzadores y NAVEGADORES
            # Evita que el auto-recovery se confunda con pestañas de búsqueda o foros.
            EXCLUSIONS = ["EVE IT", "EVE IT -", "REPLICATOR", "OVERLAY", "LANZADOR", "EXPLORADOR", "CHROME", "FIREFOX", "EDGE", "BRAVE", "GOOGLE"]
            if any(exc in t_upper for exc in EXCLUSIONS):
                is_eve = False
            
            if not is_eve:
                continue
                
            if w['size'][0] < 200 or w['size'][1] < 200:
                continue
            
            # USAR SIEMPRE EL PID para garantizar unicidad absoluta y estabilidad total
            # Esto evita que el binding cambie si el orden de enumeración de Windows varía.
            # Mostramos el nombre limpio pero con el ID de proceso para que el Hub sea infalible.
            w['title'] = f"{t_orig} [#{w['pid']}]"
            
            hwnd = w['hwnd']
            cl = wt.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(cl)):
                pt = wt.POINT(0, 0)
                user32.ClientToScreen(hwnd, ctypes.byref(pt))
                w['client_rect'] = (pt.x, pt.y, pt.x + cl.right, pt.y + cl.bottom)
                w['client_size'] = (cl.right, cl.bottom)
            else:
                l, t_rect, r, b = w['rect']
                w['client_rect'] = (l, t_rect, r, b)
                w['client_size'] = (r - l, b - t_rect)
                
            result.append(w)
            
        # Ordenar por tamaño (descendente) para priorizar clientes principales
        result.sort(key=lambda x: x['size'][0] * x['size'][1], reverse=True)
        return result

    def resolve_eve_window_handle(display_title: str, preferred_hwnd: Optional[int] = None) -> Optional[int]:
        """
        Resuelve el handle de ventana de EVE de forma robusta.
        Prioriza el handle preferido si es válido, luego busca por títulos (exactos o normalizados).
        """
        # 1. Priorizar el handle preferido si sigue siendo una ventana válida
        if preferred_hwnd and user32.IsWindow(preferred_hwnd):
            # Podríamos validar el título aquí, pero confiamos en la validez del HWND
            return preferred_hwnd

        all_eve = find_eve_windows()
        if not all_eve:
            return None

        # Normalizar título buscado (quitar [#hwnd] si lo trae)
        search_norm = display_title.split(' [#')[0].strip() if ' [#' in display_title else display_title.strip()

        # 2. Intentar match exacto o normalizado
        candidates = []
        for w in all_eve:
            w_title = w['title']
            w_norm = w_title.split(' [#' )[0].strip() if ' [#' in w_title else w_title.strip()
            
            # Match exacto (incluyendo [#pid])
            if w_title == display_title:
                return w['hwnd']
            
            # Match normalizado (sin el sufijo de unicidad)
            if w_norm == search_norm:
                candidates.append(w)

        # 3. Si hay candidatos normalizados, devolver el primero
        if candidates:
            return candidates[0]['hwnd']

        # 4. Fallback final: si solo hay una ventana EVE abierta, la devolvemos
        # (Es mejor que nada si el personaje cambió de nombre o título)
        if len(all_eve) == 1:
            return all_eve[0]['hwnd']

        return None

    def capture_window_region(hwnd: int, region_rel: dict, out_w: int = 400, out_h: int = 300):
        """
        Captura de ventana EVE con endurecimiento de ruta.
        Flujo: Window DC → PrintWindow fallback.
        """
        if not hwnd or not user32.IsWindow(hwnd): return None
        if user32.IsIconic(hwnd): return None

        # 1. Dimensiones del cliente
        cl = wt.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(cl)): return None
        ww, wh = cl.right, cl.bottom
        if ww <= 0 or wh <= 0: return None

        # 2. Coordenadas ROI con clamping estricto
        rx = max(0, int(region_rel['x'] * ww))
        ry = max(0, int(region_rel['y'] * wh))
        rw = max(1, int(region_rel['w'] * ww))
        rh = max(1, int(region_rel['h'] * wh))
        
        # Clamping: nunca exceder los límites de la ventana
        if rx + rw > ww: rw = ww - rx
        if ry + rh > wh: rh = wh - ry
        if rw <= 0 or rh <= 0: return None

        hdc_screen = None; mdc = None; bmp = None; old_obj = None
        data = None
        
        try:
            hdc_screen = user32.GetDC(0)
            mdc = gdi32.CreateCompatibleDC(hdc_screen)
            bmp = gdi32.CreateCompatibleBitmap(hdc_screen, out_w, out_h)
            old_obj = gdi32.SelectObject(mdc, bmp)
            gdi32.SetStretchBltMode(mdc, 3) # COLORONCOLOR

            captured = False
            
            # --- RUTA 1: Window DC (Directo al cliente) ---
            hdc_window = user32.GetDC(hwnd)
            if hdc_window:
                if gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, hdc_window, rx, ry, rw, rh, SRCCOPY):
                    # Verificar que obtuvimos contenido real (al menos 1 píxel no-negro)
                                    if out_w < 80 or out_h < 80:
                                                            captured = True  # Guard: overlay muy pequeño, skip validacion pixel
                                    else:
                            points = [
                                (out_w//2, out_h//2),
                                (out_w//4, out_h//4),
                                (3*out_w//4, out_h//4),
                                (out_w//4, 3*out_h//4),
                                (3*out_w//4, 3*out_h//4)
                            ]
                            for px, py in points:
                                if gdi32.GetPixel(mdc, px, py) != 0:
                                    captured = True
                                    break
                user32.ReleaseDC(hwnd, hdc_window)

            # --- RUTA 2: PrintWindow (para ventanas tapadas u opacas) ---
            if not captured:
                tmp_mdc = gdi32.CreateCompatibleDC(hdc_screen)
                tmp_bmp = gdi32.CreateCompatibleBitmap(hdc_screen, ww, wh)
                tmp_old = gdi32.SelectObject(tmp_mdc, tmp_bmp)
                
                for flag in [3, 2, 0]:
                    if user32.PrintWindow(hwnd, tmp_mdc, flag):
                        gdi32.StretchBlt(mdc, 0, 0, out_w, out_h, tmp_mdc, rx, ry, rw, rh, SRCCOPY)
                        captured = True
                        break
                
                gdi32.SelectObject(tmp_mdc, tmp_old)
                gdi32.DeleteObject(tmp_bmp)
                gdi32.DeleteDC(tmp_mdc)

            # Extraer datos si capturamos algo
            if captured:
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = out_w
                bmi.bmiHeader.biHeight = -out_h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0
                
                buf = ctypes.create_string_buffer(out_w * out_h * 4)
                if gdi32.GetDIBits(mdc, bmp, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS):
                    data = bytes(buf.raw)

        except Exception as e:
            logger.debug(f"Error captura: {e}")
        finally:
            if old_obj: gdi32.SelectObject(mdc, old_obj)
            if bmp: gdi32.DeleteObject(bmp)
            if mdc: gdi32.DeleteDC(mdc)
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

    def set_window_stealth(hwnd: int):
        """Hace que la ventana sea invisible para capturas de pantalla/réplicas."""
        if not hwnd: return
        try:
            # WDA_EXCLUDEFROMCAPTURE = 0x00000011 (Windows 10+)
            user32.SetWindowDisplayAffinity(hwnd, 0x11)
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
    def resolve_eve_window_handle(display_title, preferred_hwnd=None): return None
    def capture_window_region(hwnd, r, w=400, h=300): return None
    def set_click_through(h, e): pass
    def set_no_activate(h): pass
    def bring_window_to_front(h): pass
