"""
overlay/replicator_visual_diagnostics.py
Visual diagnostics for Replicator overlays.
Reads widget state, flags, config and generates a text report.
No persistent changes to overlay config or behaviour.
"""
import datetime
import logging
import os

logger = logging.getLogger('eve.replicator_diag')

# Qt shim
try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QLabel, QApplication,
    )
    from PySide6.QtCore import Qt
except ImportError:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QLabel, QApplication,
    )
    from PyQt6.QtCore import Qt


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_visual_diagnostic_report(overlay) -> str:
    lines: list[str] = []

    def S(title: str):
        lines.append(f"\n{'='*56}\n  {title}\n{'='*56}")

    def I(key: str, val):
        lines.append(f"  {key:<40} {val}")

    lines.append(
        f"[REPLICATOR VISUAL DIAG]  {datetime.datetime.now().isoformat()}"
    )

    # ------------------------------------------------------------------
    # 1) Identity
    # ------------------------------------------------------------------
    S("1) IDENTIDAD")
    I("title", repr(overlay._title))
    I("hwnd EVE asociado", overlay._hwnd)
    try:
        I("overlay winId", int(overlay.winId()))
    except Exception:
        I("overlay winId", "N/A")
    I("geometry (x, y)", f"{overlay.x()}, {overlay.y()}")
    I("geometry (w, h)", f"{overlay.width()}, {overlay.height()}")
    try:
        fg = overlay.frameGeometry()
        I("frameGeometry", f"x={fg.x()} y={fg.y()} w={fg.width()} h={fg.height()}")
    except Exception:
        I("frameGeometry", "N/A")
    try:
        dpr = overlay.devicePixelRatioF()
    except Exception:
        try:
            dpr = overlay.devicePixelRatio()
        except Exception:
            dpr = "N/A"
    I("devicePixelRatio", dpr)

    # ------------------------------------------------------------------
    # 2) Config visual
    # ------------------------------------------------------------------
    S("2) CONFIG VISUAL (_ov_cfg)")
    ov = getattr(overlay, '_ov_cfg', {})
    I("overlay_title", repr(getattr(overlay, '_title', '?')))
    I("id(_ov_cfg)", id(ov))
    for k in [
        'border_shape', 'show_gray_frame', 'border_visible', 'border_width',
        'highlight_active', 'active_border_color', 'client_color',
        'label_visible', 'maintain_aspect', 'opacity',
    ]:
        I(k, ov.get(k, '<ausente>'))

    # ------------------------------------------------------------------
    # 3) Qt / window flags and attributes
    # ------------------------------------------------------------------
    S("3) QT FLAGS Y ATRIBUTOS")
    try:
        flags = overlay.windowFlags()
        def _f(name_new, name_old):
            if hasattr(Qt, 'WindowType'):
                v = getattr(Qt.WindowType, name_new, None)
            else:
                v = getattr(Qt, name_old, None)
            return v
        fwh   = _f('FramelessWindowHint',      'FramelessWindowHint')
        wsot  = _f('WindowStaysOnTopHint',     'WindowStaysOnTopHint')
        tool  = _f('Tool',                     'Tool')
        ndsw  = _f('NoDropShadowWindowHint',   'NoDropShadowWindowHint')
        I("FramelessWindowHint",          bool(flags & fwh)  if fwh  else "N/A")
        I("WindowStaysOnTopHint",         bool(flags & wsot) if wsot else "N/A")
        I("Tool flag",                    bool(flags & tool) if tool else "N/A")
        I("NoDropShadowWindowHint",       bool(flags & ndsw) if ndsw else "N/A")
    except Exception as e:
        I("flags (error)", str(e))

    WA_TB  = Qt.WA_TranslucentBackground if hasattr(Qt, 'WA_TranslucentBackground') else 120
    WA_NSB = Qt.WA_NoSystemBackground    if hasattr(Qt, 'WA_NoSystemBackground')    else 9
    I("WA_TranslucentBackground",   overlay.testAttribute(WA_TB))
    I("WA_NoSystemBackground",      overlay.testAttribute(WA_NSB))
    I("autoFillBackground",         overlay.autoFillBackground())
    I("windowOpacity",              overlay.windowOpacity())
    I("isVisible",                  overlay.isVisible())
    I("_debug_visual_layers",       getattr(overlay, '_debug_visual_layers', False))

    # ------------------------------------------------------------------
    # 4) Stylesheets (overlay + children)
    # ------------------------------------------------------------------
    S("4) STYLESHEETS")
    ss = overlay.styleSheet() or "<vacío>"
    I("overlay.styleSheet()", (ss[:280] + "…") if len(ss) > 280 else ss)

    try:
        from PySide6.QtWidgets import QFrame as _QF
    except ImportError:
        try:
            from PyQt6.QtWidgets import QFrame as _QF
        except ImportError:
            _QF = None

    try:
        all_children = overlay.findChildren(object)
        widget_children = [
            c for c in all_children
            if hasattr(c, 'styleSheet') and hasattr(c, 'autoFillBackground')
        ]
        I("total children",   len(all_children))
        I("widget children",  len(widget_children))

        suspicious = []
        for i, c in enumerate(widget_children[:12]):
            cn  = type(c).__name__
            on  = c.objectName() if callable(getattr(c, 'objectName', None)) else ''
            css = c.styleSheet() or '' if hasattr(c, 'styleSheet') else ''
            afb = c.autoFillBackground() if hasattr(c, 'autoFillBackground') else '?'
            lines.append(f"  Child[{i}]  {cn}  objectName={on!r}")
            lines.append(f"    autoFillBackground : {afb}")
            if css:
                lines.append(f"    styleSheet         : {css[:120]}")
            if _QF and isinstance(c, _QF):
                fs   = c.frameShape()
                fval = fs.value if hasattr(fs, 'value') else int(fs)
                lines.append(
                    f"    frameShape={fval}  "
                    f"frameShadow={c.frameShadow()}  "
                    f"lineWidth={c.lineWidth()}"
                )
                if fval != 0:
                    suspicious.append(f"  Child {cn!r} frameShape={fval} (≠0)")
            if afb is True:
                suspicious.append(f"  Child {cn!r} autoFillBackground=True")
            if css and ('background' in css.lower() or 'border' in css.lower()):
                if 'transparent' not in css.lower():
                    suspicious.append(f"  Child {cn!r} stylesheet: {css[:80]}")
        if suspicious:
            lines.append("  ⚠ Suspicious children (may paint rectangle):")
            lines.extend(suspicious)
    except Exception as e:
        I("children (error)", str(e))

    # ------------------------------------------------------------------
    # 5) Mask / clipping + native Win32 region
    # ------------------------------------------------------------------
    S("5) MASK / CLIPPING + WIN32 REGION")
    import sys as _sys, platform as _platform
    I("platform",       _sys.platform)
    I("OS",             _platform.platform())

    try:
        mask  = overlay.mask()
        empty = mask.isEmpty()
        I("mask().isEmpty()", empty)
        if not empty:
            br = mask.boundingRect()
            I("mask.boundingRect()",
              f"x={br.x()} y={br.y()} w={br.width()} h={br.height()}")
    except Exception as e:
        I("mask (error)", str(e))

    try:
        shape = ov.get('border_shape', 'square')
        bw    = max(1, int(ov.get('border_width', 2))) if ov.get('border_visible', True) else 0
        adj   = bw / 2.0
        wr, hr = overlay.width(), overlay.height()
        I("border_shape",              shape)
        I("should_use_win32_region",   shape != 'square' and _sys.platform == 'win32')
        I("border_width",              bw)
        I("widget.rect()",             f"0, 0, {wr}, {hr}")
        I("border_rect",               f"{adj:.1f}, {adj:.1f}, {wr-2*adj:.1f}, {hr-2*adj:.1f}")
        I("content_rect",              f"{bw}, {bw}, {wr-2*bw}, {hr-2*bw}")
        if shape != 'square':
            radius = min(wr, hr) if shape == 'pill' else 20
            I("win32_rgn_expected",
              f"CreateRoundRectRgn(0,0,{wr+1},{hr+1},{radius},{radius})")
    except Exception as e:
        I("shape/rects (error)", str(e))

    # ------------------------------------------------------------------
    # 6) Screenshot
    # ------------------------------------------------------------------
    S("6) CAPTURA PNG")
    try:
        screen = QApplication.primaryScreen()
        if screen:
            pix = screen.grabWindow(int(overlay.winId()))
            if not pix.isNull():
                ts      = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                log_dir = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '..', 'logs')
                )
                os.makedirs(log_dir, exist_ok=True)
                path = os.path.join(
                    log_dir, f"replicator_visual_debug_{ts}.png"
                )
                pix.save(path)
                I("guardado en", path)
            else:
                I("screenshot", "pixmap nulo (overlay no visible o minimizado)")
        else:
            I("screenshot", "sin pantalla disponible")
    except Exception as e:
        I("screenshot (error)", str(e))

    # ------------------------------------------------------------------
    # 7) Hipótesis automáticas
    # ------------------------------------------------------------------
    S("7) POSIBLES CAUSAS DEL MARCO GRIS")
    hyp: list[str] = []

    # NoDropShadowWindowHint check
    try:
        flags = overlay.windowFlags()
        ndsw = (Qt.WindowType.NoDropShadowWindowHint
                if hasattr(Qt, 'WindowType')
                else getattr(Qt, 'NoDropShadowWindowHint', None))
        if ndsw is not None and not bool(flags & ndsw):
            hyp.append(
                "⚠  NoDropShadowWindowHint ausente → DWM/Windows puede dibujar sombra "
                "o borde alrededor de la ventana. Añadir este flag elimina la sombra nativa."
            )
        else:
            hyp.append("✓  NoDropShadowWindowHint activo → sombra DWM desactivada.")
    except Exception:
        pass

    if not overlay.testAttribute(WA_TB):
        hyp.append(
            "⚠  WA_TranslucentBackground=False → el OS pinta el fondo de la ventana "
            "(gris por defecto en Windows). Activar este atributo hace el fondo transparente."
        )

    WA_NSB2 = Qt.WA_NoSystemBackground if hasattr(Qt, 'WA_NoSystemBackground') else 9
    if not overlay.testAttribute(WA_NSB2):
        hyp.append(
            "⚠  WA_NoSystemBackground=False → Qt puede pedir al sistema que pinte el "
            "fondo antes del paintEvent."
        )

    if overlay.autoFillBackground():
        hyp.append(
            "⚠  autoFillBackground=True → Qt rellena el fondo con el color del palette "
            "ANTES del paintEvent. Suele generar fondo gris/blanco."
        )

    ss_lower = (overlay.styleSheet() or '').lower()
    if 'border' in ss_lower and 'none' not in ss_lower:
        hyp.append(
            "⚠  Stylesheet contiene 'border' sin 'none' explícito → posible borde CSS activo."
        )
    if 'background' in ss_lower and 'transparent' not in ss_lower:
        hyp.append(
            "⚠  Stylesheet tiene 'background' no-transparent → posible relleno de fondo visible."
        )

    if _QF:
        try:
            for c in overlay.findChildren(object):
                if isinstance(c, _QF):
                    fs   = c.frameShape()
                    fval = fs.value if hasattr(fs, 'value') else int(fs)
                    if fval != 0:
                        hyp.append(
                            f"⚠  QFrame hijo con frameShape={fval} (≠0/NoFrame) → "
                            "puede estar pintando un marco propio."
                        )
        except Exception:
            pass

    try:
        mask_empty = overlay.mask().isEmpty()
    except Exception:
        mask_empty = True

    shape_now = ov.get('border_shape', 'square')
    if mask_empty and shape_now in ('pill', 'rounded'):
        hyp.append(
            f"⚠  shape='{shape_now}' pero mask vacía → para el OS el widget sigue siendo un "
            f"RECTÁNGULO COMPLETO. El área exterior al {shape_now} es transparente via "
            f"WA_TranslucentBackground, pero DWM/Windows puede pintar sombra/borde alrededor "
            f"del rectángulo completo. Solución: usar setMask() con la ruta del {shape_now} "
            f"para que el OS recorte a esa forma."
        )

    show_gray = ov.get('show_gray_frame', True)
    if not show_gray:
        hyp.append(
            "✓  show_gray_frame=False → paintEvent no dibuja el drawRect gris (alpha=40). "
            "Si el marco sigue visible, su origen es el OS/DWM, no el código Python."
        )
    else:
        hyp.append(
            "ℹ  show_gray_frame=True → paintEvent dibuja QPen(QColor(100,100,100,40)) "
            "alrededor de todo el rect del widget. Desmarca 'Mostrar borde gris' en "
            "Ajustes > Borde para eliminarlo."
        )

    try:
        fg = overlay.frameGeometry()
        g  = overlay.geometry()
        dw = fg.width()  - g.width()
        dh = fg.height() - g.height()
        if dw > 0 or dh > 0:
            hyp.append(
                f"⚠  frameGeometry ({fg.width()}×{fg.height()}) > geometry "
                f"({g.width()}×{g.height()}) en +{dw}px×+{dh}px → "
                "margen de marco de ventana del sistema visible."
            )
    except Exception:
        pass

    if not hyp:
        hyp.append(
            "✓  No se detectaron problemas obvios. El marco puede ser un artefacto "
            "del compositor DWM de Windows alrededor del rectángulo de la ventana."
        )

    for h in hyp:
        lines.append(f"  {h}")

    report = "\n".join(lines)
    logger.info(
        "[REPLICATOR VISUAL DIAG] title=%r  hypotheses=%d",
        overlay._title, len(hyp),
    )
    return report


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ReplicatorDiagnosticsDialog(QDialog):
    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._overlay = overlay
        self.setWindowTitle(f"Diagnóstico Visual — {overlay._title}")

        flags = (
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint
        ) if hasattr(Qt, 'WindowType') else (
            Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        )
        self.setWindowFlags(flags)
        self.setMinimumSize(600, 520)
        self.resize(680, 600)
        self.setStyleSheet("""
            QDialog   { background:#05070a; color:#e2e8f0; }
            QTextEdit { background:#0b1016; color:#94a3b8;
                        border:1px solid #1e293b;
                        font-family:'Consolas','Courier New',monospace;
                        font-size:11px; }
            QPushButton {
                background:rgba(0,200,255,.10);
                border:1px solid rgba(0,200,255,.30);
                color:#00c8ff; padding:5px 12px;
                border-radius:4px; font-size:11px; font-weight:700;
            }
            QPushButton:hover  { background:rgba(0,200,255,.25); border-color:#00c8ff; }
            QPushButton#warn   { background:rgba(255,200,0,.10);
                                 border-color:rgba(255,200,0,.30); color:#ffc800; }
            QPushButton#warn:checked { background:rgba(255,200,0,.30); border-color:#ffc800; }
            QPushButton#close  { background:rgba(255,50,50,.10);
                                 border-color:rgba(255,50,50,.30); color:#ef4444; }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lbl = QLabel(f"Diagnóstico: {overlay._title}")
        lbl.setStyleSheet("color:#00c8ff; font-weight:bold; font-size:12px;")
        lay.addWidget(lbl)

        self._txt = QTextEdit()
        self._txt.setReadOnly(True)
        lay.addWidget(self._txt)

        # Button row
        btn_row = QHBoxLayout()

        btn_refresh = QPushButton("🔄 Regenerar")
        btn_refresh.clicked.connect(self._refresh)
        btn_row.addWidget(btn_refresh)

        btn_copy = QPushButton("📋 Copiar")
        btn_copy.clicked.connect(self._copy_text)
        btn_row.addWidget(btn_copy)

        self._btn_debug = QPushButton("🎨 Capas debug")
        self._btn_debug.setObjectName("warn")
        self._btn_debug.setCheckable(True)
        self._btn_debug.setChecked(bool(getattr(overlay, '_debug_visual_layers', False)))
        self._btn_debug.toggled.connect(self._toggle_debug)
        btn_row.addWidget(self._btn_debug)

        btn_row.addStretch()

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        lay.addLayout(btn_row)

        # Initial report
        self._refresh()

        # Win32 topmost
        try:
            from overlay.dialog_utils import make_replicator_dialog_topmost
            make_replicator_dialog_topmost(self)
        except Exception:
            pass

    def _refresh(self):
        txt = build_visual_diagnostic_report(self._overlay)
        self._txt.setPlainText(txt)

    def _copy_text(self):
        try:
            QApplication.clipboard().setText(self._txt.toPlainText())
        except Exception:
            pass

    def _toggle_debug(self, active: bool):
        self._overlay._debug_visual_layers = active
        self._overlay.update()
        self._overlay.repaint()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_visual_diagnostic(overlay, parent=None) -> ReplicatorDiagnosticsDialog:
    """Open (or focus) the visual diagnostics dialog for *overlay*."""
    dlg = ReplicatorDiagnosticsDialog(overlay, parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
