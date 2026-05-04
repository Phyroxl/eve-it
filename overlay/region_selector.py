"""
region_selector.py — Selector de región tipo snipping tool.

PROBLEMA RESUELTO:
  EVE Online (DirectX) captura el foco del teclado, así que keyPressEvent
  no recibe Enter. La solución es:
    1. Botón flotante "✓ CONFIRMAR" siempre visible en pantalla
    2. Doble-click también confirma
    3. Click derecho cancela
    4. Enter/Escape como alternativa (cuando el foco sí está disponible)

La selección se guarda nada más soltar el ratón — el botón solo confirma.

Retorna: {'x': float, 'y': float, 'w': float, 'h': float} en [0.0, 1.0]
o None si el usuario cancela.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

# Garantizar que el directorio raíz del proyecto esté en sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Qt shim
_qt_ok = False
_QApp = _QWidget = _Qt = _QRect = _QPoint = _QColor = None
_QPainter = _QPen = _QBrush = _QFont = _QPixmap = _QCursor = None

for _qt_try in [
    ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
    ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
    ('PySide2', 'PySide2.QtWidgets', 'PySide2.QtCore', 'PySide2.QtGui'),
    ('PyQt5',   'PyQt5.QtWidgets',   'PyQt5.QtCore',   'PyQt5.QtGui'),
]:
    try:
        import importlib
        _w = importlib.import_module(_qt_try[1])
        _c = importlib.import_module(_qt_try[2])
        _g = importlib.import_module(_qt_try[3])
        _QApp     = _w.QApplication
        _QWidget  = _w.QWidget
        _Qt       = _c.Qt
        _QRect    = _c.QRect
        _QPoint   = _c.QPoint
        _QColor   = _g.QColor
        _QPainter = _g.QPainter
        _QPen     = _g.QPen
        _QFont    = _g.QFont
        _QPixmap  = _g.QPixmap
        _QCursor  = _g.QCursor
        _qt_ok = True
        break
    except ImportError:
        continue


class RegionSelectorWidget(_QWidget if _qt_ok else object):
    """
    Ventana de pantalla completa para seleccionar una región.

    Flujo:
      1. Aparece cubriendo toda la pantalla con fondo semitransparente
      2. Usuario hace click+drag para seleccionar
      3. Al soltar el ratón, aparece botón "✓ CONFIRMAR" y dimensiones
      4. Click en CONFIRMAR o doble-click sobre la selección → confirma
      5. Escape o click derecho → cancela
    """

    def __init__(self, ref_rect: tuple, screenshot=None):
        super().__init__()
        self._ref_rect   = ref_rect
        self._screenshot = screenshot
        self._start      = None
        self._end        = None
        self._selection  = None   # QRect final
        self._confirmed  = False
        self._hovering_btn = False   # cursor encima del botón confirmar

        self._setup_window()

    def _setup_window(self):
        Qt = _Qt
        flags_list = []
        for fname in ['FramelessWindowHint', 'WindowStaysOnTopHint']:
            flag = getattr(getattr(Qt, 'WindowType', Qt), fname,
                           getattr(Qt, fname, None))
            if flag is not None:
                flags_list.append(flag)

        if flags_list:
            flags = flags_list[0]
            for f in flags_list[1:]:
                flags = flags | f
            self.setWindowFlags(flags)

        wa_trans = getattr(getattr(Qt, 'WidgetAttribute', Qt),
                           'WA_TranslucentBackground',
                           getattr(Qt, 'WA_TranslucentBackground', None))
        if wa_trans:
            self.setAttribute(wa_trans)

        # [NUEVO] Refuerzo topmost Win32
        try:
            import ctypes
            hwnd = int(self.winId())
            if hwnd:
                # HWND_TOPMOST = -1, SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        except Exception:
            pass

        cross = getattr(getattr(Qt, 'CursorShape', Qt), 'CrossCursor',
                        getattr(Qt, 'CrossCursor', 2))
        self.setCursor(_QCursor(cross))

        focus_pol = getattr(getattr(Qt, 'FocusPolicy', Qt), 'StrongFocus',
                            getattr(Qt, 'StrongFocus', 11))
        self.setFocusPolicy(focus_pol)

        screen = _QApp.primaryScreen()
        geom   = screen.geometry()
        self.setGeometry(geom)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ── Botón confirmar ───────────────────────────────────────────────────────

    def _btn_rect(self):
        """Botón CONFIRMAR y CANCELAR en una sola fila compacta."""
        if not self._selection: return None
        sel = self._selection
        # Dimensiones de los botones (más pequeños y proporcionales)
        bw_ok, bw_can, bh = 110, 85, 28
        total_w = bw_ok + bw_can + 8
        
        # Centrar el bloque de botones debajo de la selección (o dentro si no hay espacio)
        bx = sel.left() + (sel.width() - total_w) // 2
        by = sel.bottom() + 6
        
        # Si se sale por abajo de la pantalla, ponerlo dentro de la selección arriba
        if by + bh > self.height() - 40:
            by = sel.bottom() - bh - 6
        # Si la selección es muy pequeña verticalmente, ponerlo encima
        if sel.height() < 60:
            by = sel.top() - bh - 6
            
        # Clamp a bordes de pantalla
        bx = max(10, min(bx, self.width() - total_w - 10))
        by = max(10, min(by, self.height() - bh - 10))
        
        return _QRect(bx, by, bw_ok, bh)

    def _cancel_btn_rect(self):
        br = self._btn_rect()
        if not br: return None
        return _QRect(br.right() + 8, br.top(), 85, br.height())

    # ── Pintura ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        Qt = _Qt
        p = _QPainter(self)
        rh = getattr(getattr(_QPainter, 'RenderHint', _QPainter),
                     'Antialiasing', 1)
        p.setRenderHint(rh)

        # Fondo
        if self._screenshot:
            p.drawPixmap(self.rect(), self._screenshot)
            p.fillRect(self.rect(), _QColor(0, 0, 0, 100))
        else:
            p.fillRect(self.rect(), _QColor(0, 0, 0, 150))

        # Borde de ventana EVE referencia
        if self._ref_rect:
            l, t, r, b = self._ref_rect
            rr = _QRect(_QPoint(l, t), _QPoint(r, b))
            dash = getattr(getattr(Qt, 'PenStyle', Qt), 'DashLine',
                           getattr(Qt, 'DashLine', 2))
            p.setPen(_QPen(_QColor(0, 200, 255, 160), 2, dash))
            p.drawRect(rr)

        # Zona seleccionada
        if self._start and self._end:
            sel = _QRect(self._start, self._end).normalized()

            # Zona oscurecida exterior (efecto "recorte")
            p.fillRect(_QRect(0, 0, self.width(), sel.top()),
                       _QColor(0, 0, 0, 80))
            p.fillRect(_QRect(0, sel.bottom(), self.width(), self.height()),
                       _QColor(0, 0, 0, 80))
            p.fillRect(_QRect(0, sel.top(), sel.left(), sel.height()),
                       _QColor(0, 0, 0, 80))
            p.fillRect(_QRect(sel.right(), sel.top(),
                              self.width() - sel.right(), sel.height()),
                       _QColor(0, 0, 0, 80))

            # Interior iluminado
            p.fillRect(sel, _QColor(255, 255, 255, 15))
            p.setPen(_QPen(_QColor(255, 255, 255), 2))
            p.drawRect(sel)

            # Asas en esquinas
            cs = 10
            for cx, cy in [(sel.left(), sel.top()), (sel.right(), sel.top()),
                           (sel.left(), sel.bottom()), (sel.right(), sel.bottom())]:
                p.fillRect(cx - cs//2, cy - cs//2, cs, cs, _QColor(255, 255, 255))

            # Dimensiones
            p.setPen(_QPen(_QColor(220, 255, 255)))
            p.setFont(_QFont('Consolas', 10))
            p.drawText(sel.left() + 4, sel.top() - 6,
                       f"  {sel.width()} × {sel.height()} px")

        # Botón CONFIRMAR (solo si hay selección completada)
        if self._selection:
            br = self._btn_rect()
            if br:
                # Fondo del botón
                btn_bg = _QColor(0, 180, 80, 230) if self._hovering_btn \
                         else _QColor(0, 140, 60, 210)
                p.fillRect(br, btn_bg)
                p.setPen(_QPen(_QColor(0, 255, 140), 2))
                p.drawRect(br)
                p.setPen(_QPen(_QColor(255, 255, 255, 240)))
                p.setFont(_QFont('Arial', 11, 75))  # Bold
                align = (getattr(getattr(Qt, 'AlignmentFlag', Qt),
                                 'AlignCenter', None) or
                         getattr(Qt, 'AlignCenter', 4))
                p.drawText(br, align, "✓ OK")


            # Botón CANCELAR
            cr = self._cancel_btn_rect()
            if cr:
                p.fillRect(cr, _QColor(160, 40, 40, 200))
                p.setPen(_QPen(_QColor(255, 100, 100), 1))
                p.drawRect(cr)
                p.setPen(_QPen(_QColor(255, 200, 200)))
                p.setFont(_QFont('Arial', 10))
                align = (getattr(getattr(Qt, 'AlignmentFlag', Qt),
                                 'AlignCenter', None) or
                         getattr(Qt, 'AlignCenter', 4))
                p.drawText(cr, align, "✕ Cancelar")

        # Instrucciones
        Qt = _Qt
        p.setPen(_QPen(_QColor(220, 240, 255, 200)))
        p.setFont(_QFont('Consolas', 10))
        if not self._selection:
            hint = "  Arrastra para seleccionar   •   Clic derecho / Escape para cancelar  "
        else:
            hint = "  Clic en CONFIRMAR  o  doble-clic sobre la selección  •  Escape cancela  "

        hint_bg = _QRect(0, self.height() - 36, self.width(), 36)
        p.fillRect(hint_bg, _QColor(0, 0, 0, 160))
        align_bot = (
            getattr(getattr(Qt, 'AlignmentFlag', Qt), 'AlignVCenter', None)
            or getattr(Qt, 'AlignVCenter', 32)
        )
        align_ctr = (
            getattr(getattr(Qt, 'AlignmentFlag', Qt), 'AlignHCenter', None)
            or getattr(Qt, 'AlignHCenter', 4)
        )
        p.drawText(hint_bg, align_bot | align_ctr, hint)

    # ── Ratón ─────────────────────────────────────────────────────────────────

    def _global_pos(self, event):
        if hasattr(event, 'globalPosition'):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def mousePressEvent(self, event):
        Qt = _Qt
        left  = getattr(getattr(Qt, 'MouseButton', Qt), 'LeftButton',
                        getattr(Qt, 'LeftButton', 1))
        right = getattr(getattr(Qt, 'MouseButton', Qt), 'RightButton',
                        getattr(Qt, 'RightButton', 2))
        btn = event.button()

        if btn == right:
            self._cancel()
            return

        if btn == left:
            gp = self._global_pos(event)
            # ¿Clic en el botón CONFIRMAR?
            if self._selection:
                br = self._btn_rect()
                if br and br.contains(gp):
                    self._confirm()
                    return
                cr = self._cancel_btn_rect()
                if cr and cr.contains(gp):
                    self._cancel()
                    return
            # Nuevo drag
            self._selection = None
            self._start = gp
            self._end   = gp
            self.update()

    def mouseMoveEvent(self, event):
        gp = self._global_pos(event)
        Qt = _Qt
        left = getattr(getattr(Qt, 'MouseButton', Qt), 'LeftButton',
                       getattr(Qt, 'LeftButton', 1))

        if event.buttons() & left and self._start:
            self._end = gp
            self.update()
        else:
            # Hover sobre botón confirmar
            if self._selection:
                br = self._btn_rect()
                new_hover = bool(br and br.contains(gp))
                if new_hover != self._hovering_btn:
                    self._hovering_btn = new_hover
                    arrow = getattr(getattr(Qt, 'CursorShape', Qt),
                                    'PointingHandCursor' if new_hover else 'CrossCursor',
                                    getattr(Qt, 'PointingHandCursor' if new_hover else 'CrossCursor',
                                            13 if new_hover else 2))
                    self.setCursor(_QCursor(arrow))
                    self.update()

    def mouseReleaseEvent(self, event):
        Qt = _Qt
        left = getattr(getattr(Qt, 'MouseButton', Qt), 'LeftButton',
                       getattr(Qt, 'LeftButton', 1))
        if event.button() == left and self._start and self._end:
            sel = _QRect(self._start, self._end).normalized()
            if sel.width() > 10 and sel.height() > 10:
                self._selection = sel   # guardar selección → mostrará botón
            else:
                self._selection = None
            self.update()

    def mouseDoubleClickEvent(self, event):
        """Doble-click dentro de la selección = confirmar."""
        Qt = _Qt
        left = getattr(getattr(Qt, 'MouseButton', Qt), 'LeftButton',
                       getattr(Qt, 'LeftButton', 1))
        if event.button() == left and self._selection:
            gp = self._global_pos(event)
            if self._selection.contains(gp):
                self._confirm()

    # ── Teclado ───────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        Qt = _Qt
        Key = getattr(Qt, 'Key', Qt)
        k   = event.key()
        ESC    = getattr(Key, 'Key_Escape', 0x01000000)
        ENTER  = getattr(Key, 'Key_Return', 0x01000005)
        ENTER2 = getattr(Key, 'Key_Enter',  0x01000006)
        SPACE  = getattr(Key, 'Key_Space',  0x00000020)

        if k == ESC:
            self._cancel()
        elif k in (ENTER, ENTER2, SPACE):
            if self._selection:
                self._confirm()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _confirm(self):
        if self._selection:
            self._confirmed = True
            self.close()

    def _cancel(self):
        self._selection = None
        self._confirmed = False
        self.close()

    # ── Resultado ─────────────────────────────────────────────────────────────

    def get_relative_region(self) -> Optional[dict]:
        """
        Retorna la región seleccionada normalizada al tamaño de la ventana
        EVE de referencia. Valores en [0.0, 1.0].
        """
        if not self._confirmed or not self._selection:
            return None

        l, t, r, b = self._ref_rect
        ref_w = max(1, r - l)
        ref_h = max(1, b - t)
        sel   = self._selection

        rx = (sel.left()  - l) / ref_w
        ry = (sel.top()   - t) / ref_h
        rw = sel.width()       / ref_w
        rh = sel.height()      / ref_h

        rx = max(0.0, min(1.0, rx))
        ry = max(0.0, min(1.0, ry))
        rw = max(0.01, min(1.0 - rx, rw))
        rh = max(0.01, min(1.0 - ry, rh))

        return {'x': rx, 'y': ry, 'w': rw, 'h': rh}


# ══════════════════════════════════════════════════════════════════════════════


def _get_ref_rect_qt(reference_window: dict, screen) -> tuple:
    """
    Obtiene el rectángulo de la ventana EVE en coordenadas LÓGICAS Qt.

    Problema: Win32 GetWindowRect devuelve píxeles físicos.
              Qt globalPosition devuelve píxeles lógicos (DPI-scaled).
              Con DPI>100%, son diferentes → error en la normalización.

    Solución:
      1. Intentar obtener la geometría via QWindow.fromWinId() → coords Qt.
      2. Si falla, calcular el factor DPI y ajustar el rect Win32.
      3. Si todo falla, usar la pantalla completa (siempre consistente con Qt).
    """
    hwnd = reference_window.get('hwnd')
    win32_rect = reference_window.get('rect')  # coords físicas Win32

    # Intento 1: via QWindow (coords Qt lógicas directamente)
    if hwnd:
        try:
            import importlib
            for pkg in ['PySide6.QtGui', 'PyQt6.QtGui', 'PySide2.QtGui', 'PyQt5.QtGui']:
                try:
                    _g = importlib.import_module(pkg)
                    if hasattr(_g, 'QWindow'):
                        qwin = _g.QWindow.fromWinId(int(hwnd))
                        if qwin:
                            geo = qwin.geometry()
                            if geo.width() > 0 and geo.height() > 0:
                                return (geo.left(), geo.top(),
                                        geo.left() + geo.width(),
                                        geo.top() + geo.height())
                except Exception:
                    continue
        except Exception:
            pass

    # Intento 2: ajustar coords Win32 por factor DPI
    if win32_rect:
        try:
            sg = screen.geometry()
            # Calcular factor DPI comparando geometría Qt con resolución nativa
            native = screen.size()  # puede ser diferente de sg si hay DPI scaling
            phys_w = screen.physicalSize().width()  # mm
            # Usar devicePixelRatio como factor de escala
            dpr = screen.devicePixelRatio()
            if dpr and dpr != 1.0:
                l, t, r, b = win32_rect
                # Convertir de coords físicas a lógicas
                l = int(l / dpr); t = int(t / dpr)
                r = int(r / dpr); b = int(b / dpr)
                # Verificar que el resultado tiene sentido
                sw, sh = sg.width(), sg.height()
                if 0 <= l < sw and 0 <= t < sh and r > l and b > t:
                    return (l, t, r, b)
        except Exception:
            pass

    # Intento 3: usar coords Win32 tal cual (si DPI=100%, son correctas)
    if win32_rect:
        l, t, r, b = win32_rect
        sg = screen.geometry()
        sw, sh = sg.width(), sg.height()
        # Sanity check: ¿están dentro de la pantalla?
        if 0 <= l < sw and 0 <= t < sh and r > l and b > t:
            return win32_rect

    # Fallback: usar pantalla completa (siempre en coords Qt correctas)
    sg = screen.geometry()
    return (sg.left(), sg.top(), sg.left() + sg.width(), sg.top() + sg.height())


def select_region(reference_window: dict) -> Optional[dict]:
    """
    Muestra el selector de región y bloquea hasta que el usuario confirma.

    reference_window: dict con 'hwnd' y 'rect' (l,t,r,b) de la ventana EVE.
    Retorna región relativa {x,y,w,h} relativa a la ventana, o None.
    """
    if not _qt_ok:
        print("[region_selector] Qt no disponible")
        return None

    app = _QApp.instance() or _QApp(sys.argv)
    screen = app.primaryScreen()

    # Capturar screenshot del escritorio como fondo
    screenshot = None
    try:
        screenshot = screen.grabWindow(0)
    except Exception:
        pass

    # CRÍTICO: Obtener ref_rect en coordenadas LÓGICAS Qt (no Win32 físicas).
    # Win32 GetWindowRect devuelve coords físicas; Qt usa coords lógicas.
    # Con DPI scaling (125%, 150%), son diferentes → error en la normalización.
    #
    # Estrategia: intentar obtener la geometría de la ventana EVE via Qt,
    # que ya está en coordenadas lógicas. Si no, usar la pantalla completa
    # como referencia (siempre en coords Qt = siempre correcto).
    # Usar client_rect (área sin barra de título) si está disponible
    # El usuario selecciona sobre el contenido visible, no sobre la barra
    if 'client_rect' in reference_window:
        ref_win_for_qt = dict(reference_window)
        ref_win_for_qt['rect'] = reference_window['client_rect']
    else:
        ref_win_for_qt = reference_window
    ref_rect = _get_ref_rect_qt(ref_win_for_qt, screen)
    widget   = RegionSelectorWidget(ref_rect, screenshot)

    # Usar exec() del widget como diálogo para bloquear correctamente
    # Alternativa robusta: QEventLoop explícito
    try:
        import importlib
        # Intentar obtener QEventLoop del backend disponible
        for pkg in ['PySide6.QtCore', 'PyQt6.QtCore', 'PySide2.QtCore', 'PyQt5.QtCore']:
            try:
                _core = importlib.import_module(pkg)
                QEventLoop = _core.QEventLoop
                loop = QEventLoop()

                # Conectar cierre del widget al fin del loop
                try:
                    widget.destroyed.connect(loop.quit)
                except Exception:
                    pass

                widget.show()
                widget.raise_()
                widget.activateWindow()
                widget.setFocus()

                # También escuchar closeEvent via override
                _original_close = widget.closeEvent
                def _on_close(ev):
                    _original_close(ev)
                    try:
                        loop.quit()
                    except Exception:
                        pass
                widget.closeEvent = _on_close

                exec_fn = getattr(loop, 'exec', None) or loop.exec_
                exec_fn()
                break
            except (ImportError, AttributeError):
                continue
        else:
            # Fallback: ejecutar app completa
            widget.show()
            exec_app = getattr(app, 'exec', None) or app.exec_
            exec_app()
    except Exception:
        widget.show()

    return widget.get_relative_region()
