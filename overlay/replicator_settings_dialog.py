"""
overlay/replicator_settings_dialog.py
Dialog de configuración por-réplica: General, Layout, Etiqueta, Borde, Avanzado.
Aplica cambios en vivo a la réplica y guarda en config.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

logger = logging.getLogger('eve.replicator_settings')

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
        QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
        QPushButton, QColorDialog, QFrame, QSizePolicy,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
        QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
        QPushButton, QColorDialog, QFrame, QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor

_STYLE = """
QDialog { background: #05070a; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
QTabWidget::pane { background: #0b1016; border: 1px solid #1e293b; }
QTabBar::tab { background: #0b1016; color: #64748b; padding: 6px 14px;
               border: 1px solid #1e293b; border-bottom: none; }
QTabBar::tab:selected { background: #05070a; color: #00c8ff; border-bottom: 1px solid #05070a; }
QLabel { color: #94a3b8; font-size: 11px; }
QLabel#section { color: #00c8ff; font-size: 10px; font-weight: 800;
                 letter-spacing: 1px; margin-top: 6px; }
QCheckBox { color: #e2e8f0; font-size: 11px; }
QCheckBox::indicator { width: 14px; height: 14px; background: #1e293b;
                       border: 1px solid #334155; border-radius: 2px; }
QCheckBox::indicator:checked { background: #00c8ff; border-color: #00c8ff; }
QSpinBox, QDoubleSpinBox, QComboBox {
    background: #1e293b; border: 1px solid #334155;
    color: #e2e8f0; padding: 3px 6px; border-radius: 3px; font-size: 11px;
}
QPushButton {
    background: rgba(0,200,255,0.1); border: 1px solid rgba(0,200,255,0.3);
    color: #00c8ff; padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: 700;
}
QPushButton:hover { background: rgba(0,200,255,0.25); border-color: #00c8ff; }
QPushButton#close { background: rgba(255,50,50,0.1); border-color: rgba(255,50,50,0.3);
                    color: #ef4444; }
QPushButton#close:hover { background: rgba(255,50,50,0.25); }
QPushButton.color_btn { min-width: 32px; max-width: 32px; min-height: 22px;
                        max-height: 22px; border-radius: 3px; }
"""


def _row(parent_layout, label_text: str, widget) -> None:
    """Añade una fila label + widget al layout."""
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setFixedWidth(160)
    row.addWidget(lbl)
    row.addWidget(widget)
    row.addStretch()
    parent_layout.addLayout(row)


def _section(parent_layout, text: str) -> None:
    lbl = QLabel(text)
    lbl.setObjectName("section")
    parent_layout.addWidget(lbl)


def _color_btn(color_hex: str, callback) -> QPushButton:
    btn = QPushButton()
    btn.setProperty('class', 'color_btn')
    btn.setStyleSheet(f"background:{color_hex}; border:1px solid #334155; border-radius:3px;")
    btn.setFixedSize(32, 22)
    def _pick():
        c = QColorDialog.getColor(QColor(color_hex), options=QColorDialog.ColorDialogOption.ShowAlphaChannel
                                  if hasattr(QColorDialog, 'ColorDialogOption') else QColorDialog.ShowAlphaChannel)
        if c.isValid():
            hex_val = c.name()
            btn.setStyleSheet(f"background:{hex_val}; border:1px solid #334155; border-radius:3px;")
            callback(hex_val)
    btn.clicked.connect(_pick)
    return btn


class ReplicatorSettingsDialog(QDialog):
    """Diálogo de ajustes per-réplica. Aplica cambios en vivo y guarda en config."""

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._ov = overlay
        self.setWindowTitle(f"Ajustes — {overlay._title}")
        self.setMinimumWidth(420)
        self.setStyleSheet(_STYLE)
        flags = Qt.WindowType.Tool if hasattr(Qt, 'WindowType') else Qt.Tool
        self.setWindowFlags(flags | (Qt.WindowType.WindowCloseButtonHint
                                     if hasattr(Qt, 'WindowType') else Qt.WindowCloseButtonHint))
        self._build_ui()

    def _cfg(self, key):
        return self._ov._ov_cfg.get(key)

    def _set(self, key, value):
        self._ov._ov_cfg[key] = value
        self._ov._schedule_autosave()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(),  "General")
        tabs.addTab(self._tab_layout(),   "Layout")
        tabs.addTab(self._tab_label(),    "Etiqueta")
        tabs.addTab(self._tab_border(),   "Borde")
        tabs.addTab(self._tab_advanced(), "Avanzado")
        lay.addWidget(tabs)

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("close")
        btn_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_close)
        lay.addLayout(row)

    # ------------------------------------------------------------------ #
    # Tab: General
    # ------------------------------------------------------------------ #
    def _tab_general(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(6)

        _section(lay, "COMPORTAMIENTO")

        chk_top = QCheckBox("Siempre encima")
        chk_top.setChecked(bool(self._cfg('always_on_top')))
        chk_top.toggled.connect(lambda v: (self._set('always_on_top', v),
                                            self._ov.apply_always_on_top(v)))
        lay.addWidget(chk_top)

        chk_hide = QCheckBox("Ocultar si EVE no está activo")
        chk_hide.setChecked(bool(self._cfg('hide_when_inactive')))
        chk_hide.toggled.connect(lambda v: self._set('hide_when_inactive', v))
        lay.addWidget(chk_hide)

        chk_lock = QCheckBox("Bloquear posición")
        chk_lock.setChecked(bool(self._cfg('locked')))
        chk_lock.toggled.connect(lambda v: self._set('locked', v))
        lay.addWidget(chk_lock)

        chk_sync = QCheckBox("Sincronizar desde aquí")
        chk_sync.setChecked(bool(getattr(self._ov, '_sync_active', False)))
        chk_sync.toggled.connect(lambda v: setattr(self._ov, '_sync_active', v))
        lay.addWidget(chk_sync)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ #
    # Tab: Layout
    # ------------------------------------------------------------------ #
    def _tab_layout(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(6)

        _section(lay, "POSICIÓN Y TAMAÑO")

        sp_x = QSpinBox(); sp_x.setRange(0, 9999); sp_x.setValue(self._ov.x())
        sp_y = QSpinBox(); sp_y.setRange(0, 9999); sp_y.setValue(self._ov.y())
        sp_w = QSpinBox(); sp_w.setRange(64, 4096); sp_w.setValue(self._ov.width())
        sp_h = QSpinBox(); sp_h.setRange(64, 4096); sp_h.setValue(self._ov.height())

        sp_x.valueChanged.connect(lambda v: self._ov.move(v, self._ov.y()))
        sp_y.valueChanged.connect(lambda v: self._ov.move(self._ov.x(), v))
        sp_w.valueChanged.connect(lambda v: self._ov.resize(v, self._ov.height()))
        sp_h.valueChanged.connect(lambda v: self._ov.resize(self._ov.width(), v))

        _row(lay, "X:", sp_x)
        _row(lay, "Y:", sp_y)
        _row(lay, "Ancho:", sp_w)
        _row(lay, "Alto:", sp_h)

        btn_save = QPushButton("Guardar layout")
        btn_save.clicked.connect(self._ov._do_save)
        btn_reset = QPushButton("Resetear posición")
        btn_reset.clicked.connect(lambda: (self._ov.move(400, 300),
                                            self._ov.resize(280, 200),
                                            self._ov._schedule_autosave()))
        row_btns = QHBoxLayout()
        row_btns.addWidget(btn_save)
        row_btns.addWidget(btn_reset)
        row_btns.addStretch()
        lay.addLayout(row_btns)

        _section(lay, "SNAP A CUADRÍCULA")

        chk_snap = QCheckBox("Alinear a cuadrícula al mover")
        chk_snap.setChecked(bool(self._cfg('snap_enabled')))
        chk_snap.toggled.connect(lambda v: self._set('snap_enabled', v))
        lay.addWidget(chk_snap)

        sp_gx = QSpinBox(); sp_gx.setRange(1, 200); sp_gx.setValue(int(self._cfg('snap_x') or 20))
        sp_gy = QSpinBox(); sp_gy.setRange(1, 200); sp_gy.setValue(int(self._cfg('snap_y') or 20))
        sp_gx.valueChanged.connect(lambda v: self._set('snap_x', v))
        sp_gy.valueChanged.connect(lambda v: self._set('snap_y', v))
        _row(lay, "Grid X (px):", sp_gx)
        _row(lay, "Grid Y (px):", sp_gy)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ #
    # Tab: Etiqueta
    # ------------------------------------------------------------------ #
    def _tab_label(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(6)

        _section(lay, "TEXTO")

        chk_vis = QCheckBox("Mostrar nombre del cliente")
        chk_vis.setChecked(bool(self._cfg('label_visible')))
        chk_vis.toggled.connect(lambda v: (self._set('label_visible', v), self._ov.update()))
        lay.addWidget(chk_vis)

        cmb_pos = QComboBox()
        _positions = ['top_left', 'top_center', 'top_right',
                      'bottom_left', 'bottom_center', 'bottom_right']
        cmb_pos.addItems(_positions)
        cur = self._cfg('label_pos') or 'top_left'
        if cur in _positions:
            cmb_pos.setCurrentIndex(_positions.index(cur))
        cmb_pos.currentTextChanged.connect(lambda v: (self._set('label_pos', v), self._ov.update()))
        _row(lay, "Posición:", cmb_pos)

        sp_fs = QSpinBox(); sp_fs.setRange(6, 24); sp_fs.setValue(int(self._cfg('label_font_size') or 10))
        sp_fs.valueChanged.connect(lambda v: (self._set('label_font_size', v), self._ov.update()))
        _row(lay, "Tamaño fuente:", sp_fs)

        btn_col = _color_btn(self._cfg('label_color') or '#ffffff',
                             lambda v: (self._set('label_color', v), self._ov.update()))
        _row(lay, "Color texto:", btn_col)

        _section(lay, "FONDO")

        chk_bg = QCheckBox("Fondo de etiqueta")
        chk_bg.setChecked(bool(self._cfg('label_bg')))
        chk_bg.toggled.connect(lambda v: (self._set('label_bg', v), self._ov.update()))
        lay.addWidget(chk_bg)

        btn_bgcol = _color_btn(self._cfg('label_bg_color') or '#000000',
                               lambda v: (self._set('label_bg_color', v), self._ov.update()))
        _row(lay, "Color fondo:", btn_bgcol)

        sp_bop = QDoubleSpinBox()
        sp_bop.setRange(0.0, 1.0); sp_bop.setSingleStep(0.05)
        sp_bop.setValue(float(self._cfg('label_bg_opacity') or 0.65))
        sp_bop.valueChanged.connect(lambda v: (self._set('label_bg_opacity', v), self._ov.update()))
        _row(lay, "Opacidad fondo:", sp_bop)

        sp_pad = QSpinBox(); sp_pad.setRange(0, 20); sp_pad.setValue(int(self._cfg('label_padding') or 4))
        sp_pad.valueChanged.connect(lambda v: (self._set('label_padding', v), self._ov.update()))
        _row(lay, "Padding:", sp_pad)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ #
    # Tab: Borde
    # ------------------------------------------------------------------ #
    def _tab_border(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(6)

        _section(lay, "BORDE")

        chk_bv = QCheckBox("Mostrar borde")
        chk_bv.setChecked(bool(self._cfg('border_visible')))
        chk_bv.toggled.connect(lambda v: (self._set('border_visible', v), self._ov.update()))
        lay.addWidget(chk_bv)

        chk_ha = QCheckBox("Destacar cuando este cliente está activo")
        chk_ha.setChecked(bool(self._cfg('highlight_active')))
        chk_ha.toggled.connect(lambda v: self._set('highlight_active', v))
        lay.addWidget(chk_ha)

        sp_bw = QSpinBox(); sp_bw.setRange(1, 10); sp_bw.setValue(int(self._cfg('border_width') or 2))
        sp_bw.valueChanged.connect(lambda v: (self._set('border_width', v), self._ov.update()))
        _row(lay, "Grosor borde:", sp_bw)

        _section(lay, "COLORES")

        btn_ac = _color_btn(self._cfg('active_border_color') or '#00ff64',
                            lambda v: (self._set('active_border_color', v), self._ov.update()))
        _row(lay, "Color activo (global):", btn_ac)

        btn_cc = _color_btn(self._cfg('client_color') or '#00c8ff',
                            lambda v: (self._set('client_color', v), self._ov.update()))
        _row(lay, "Color cliente:", btn_cc)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ #
    # Tab: Avanzado
    # ------------------------------------------------------------------ #
    def _tab_advanced(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(6)

        _section(lay, "CAPTURA")

        cmb_fps = QComboBox()
        cmb_fps.addItems(['5', '10', '15', '30', '60', '120'])
        fps_now = str(getattr(self._ov._thread, '_fps', 30) if hasattr(self._ov, '_thread') else 30)
        if cmb_fps.findText(fps_now) >= 0:
            cmb_fps.setCurrentText(fps_now)
        cmb_fps.currentTextChanged.connect(lambda v: self._ov._set_fps(int(v)))
        _row(lay, "Fotogramas (FPS):", cmb_fps)

        _section(lay, "HOTKEYS — FASE 2 (PRÓXIMAMENTE)")

        info = QLabel("Las hotkeys globales se habilitarán en la Fase 2.\n"
                      "Funcionalidades planificadas:\n"
                      "  · Hotkey por cliente para enfocar\n"
                      "  · Ciclo adelante/atrás entre grupos\n"
                      "  · Grupos de clientes configurables")
        info.setStyleSheet("color: #475569; font-size: 10px; padding: 6px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        lay.addStretch()
        return w
