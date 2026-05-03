"""
overlay/replicator_settings_dialog.py
Per-replica settings: General | Layout | Etiqueta | Borde | Avanzado (Hotkeys).
"""
from __future__ import annotations
import logging

logger = logging.getLogger('eve.replicator_settings')

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
        QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
        QPushButton, QColorDialog, QLineEdit, QSizePolicy,
        QMessageBox, QTextEdit, QScrollArea,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
        QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
        QPushButton, QColorDialog, QLineEdit, QSizePolicy,
        QMessageBox, QTextEdit, QScrollArea,
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor

# ... (skipping style and other tabs for brevity, focus on _tab_hotkeys overhaul)
# Note: I will replace the entire _tab_hotkeys method content correctly this time.

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
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
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
QPushButton#green { background: rgba(0,255,100,0.1); border-color: rgba(0,255,100,0.3);
                    color: #00ff64; }
QPushButton#green:hover { background: rgba(0,255,100,0.25); border-color: #00ff64; }
"""


def _row(parent_layout, label_text: str, widget) -> None:
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
    btn.setFixedSize(32, 22)
    btn.setStyleSheet(f"background:{color_hex}; border:1px solid #334155; border-radius:3px;")
    def _pick():
        opt = QColorDialog.ColorDialogOption.ShowAlphaChannel \
              if hasattr(QColorDialog, 'ColorDialogOption') else QColorDialog.ShowAlphaChannel
        c = QColorDialog.getColor(QColor(color_hex), options=opt)
        if c.isValid():
            h = c.name()
            btn.setStyleSheet(f"background:{h}; border:1px solid #334155; border-radius:3px;")
            callback(h)
    btn.clicked.connect(_pick)
    return btn


class ReplicatorSettingsDialog(QDialog):
    """Per-replica settings dialog: General | Layout | Etiqueta | Borde | Avanzado."""

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._ov = overlay
        self.setWindowTitle(f"Ajustes — {overlay._title}")
        self.setMinimumWidth(440)
        self.setStyleSheet(_STYLE)
        flags = (Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint) if hasattr(Qt, 'WindowType') else (Qt.Tool | Qt.WindowStaysOnTopHint)
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
        tabs.addTab(self._tab_hotkeys(), "Hotkeys")
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

        chk_hide = QCheckBox("Ocultar si EVE no esta activo")
        chk_hide.setChecked(bool(self._cfg('hide_when_inactive')))
        chk_hide.toggled.connect(lambda v: self._set('hide_when_inactive', v))
        lay.addWidget(chk_hide)

        chk_lock = QCheckBox("Bloquear posicion")
        chk_lock.setChecked(bool(self._cfg('locked')))
        chk_lock.toggled.connect(lambda v: self._set('locked', v))
        lay.addWidget(chk_lock)

        chk_sync = QCheckBox("Sincronizar desde aqui")
        chk_sync.setChecked(bool(getattr(self._ov, '_sync_active', False)))
        chk_sync.toggled.connect(lambda v: setattr(self._ov, '_sync_active', v))
        lay.addWidget(chk_sync)

        # --- Apply non-layout settings to all ---
        _section(lay, "APLICAR CONFIGURACION A TODAS")

        lbl_info = QLabel("Copia General, Etiqueta y Borde a todas las replicas. NO copia posicion, tamano, perfiles, snap, FPS ni region.")
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color:#475569; font-size:10px;")
        lay.addWidget(lbl_info)

        lbl_gen_status = QLabel("")
        lbl_gen_status.setStyleSheet("color:#00ff64; font-size:10px;")
 
        chk_inc_color = QCheckBox("Incluir color por cliente")
        chk_inc_color.setStyleSheet("color:#cbd5e1; font-size:10px;")
        lay.addWidget(chk_inc_color)

        def _apply_non_layout():
            from overlay.replicator_config import apply_common_settings_to_all, NON_LAYOUT_COPY_KEYS
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            apply_common_settings_to_all(
                self._ov._cfg, self._ov._title, 
                keys=NON_LAYOUT_COPY_KEYS, 
                include_client_color=chk_inc_color.isChecked()
            )
            src = {k: self._ov._ov_cfg[k] for k in NON_LAYOUT_COPY_KEYS if k in self._ov._ov_cfg}
            if chk_inc_color.isChecked() and 'client_color' in self._ov._ov_cfg:
                src['client_color'] = self._ov._ov_cfg['client_color']

            peers = [p for p in list(_OVERLAY_REGISTRY) if p is not self._ov]
            for peer in peers:
                try:
                    peer.apply_settings_dict(src, persist=False)
                except Exception:
                    pass
            lbl_gen_status.setText(f"Copiado a {len(peers)} replica(s).")

        btn_gen = QPushButton("Copiar ajustes no-layout a todas")
        btn_gen.setObjectName("green")
        btn_gen.clicked.connect(_apply_non_layout)
        lay.addWidget(btn_gen)
        lay.addWidget(lbl_gen_status)

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

        # --- Layout profiles ---
        _section(lay, "PERFIL DE LAYOUT")

        from overlay.replicator_config import (
            get_layout_profiles, save_layout_profile, delete_layout_profile,
            get_active_layout_profile, apply_layout_profile_to_ov_cfg, LAYOUT_PROFILE_KEYS,
        )

        prof_row = QHBoxLayout()
        lp_combo = QComboBox()
        lp_combo.setMinimumWidth(100)
        prof_row.addWidget(QLabel("Perfil:"))
        prof_row.addWidget(lp_combo, 1)

        btn_lp_save = QPushButton("💾")
        btn_lp_save.setToolTip("Guardar")
        btn_lp_apply = QPushButton("Aplicar")
        btn_lp_del = QPushButton("🗑️")
        for b in [btn_lp_save, btn_lp_apply, btn_lp_del]:
            b.setFixedWidth(50 if b.text() else 30)
            b.setFixedHeight(22)
            prof_row.addWidget(b)
        lay.addLayout(prof_row)

        btn_lp_new = QPushButton("+ Nuevo perfil")
        btn_lp_new.setFixedHeight(22)
        lay.addWidget(btn_lp_new)

        def _reload_lp_combo():
            profiles = get_layout_profiles(self._ov._cfg)
            active, _ = get_active_layout_profile(self._ov._cfg)
            lp_combo.blockSignals(True)
            lp_combo.clear()
            for n in profiles:
                lp_combo.addItem(n)
            idx = lp_combo.findText(active)
            if idx >= 0:
                lp_combo.setCurrentIndex(idx)
            lp_combo.blockSignals(False)

        _reload_lp_combo()

        def _lp_new():
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "Nuevo perfil", "Nombre:")
            if ok and name.strip():
                profile = {k: self._ov._ov_cfg[k] for k in LAYOUT_PROFILE_KEYS if k in self._ov._ov_cfg}
                save_layout_profile(self._ov._cfg, name.strip(), profile)
                _reload_lp_combo()
                lp_combo.setCurrentText(name.strip())

        def _lp_save():
            name = lp_combo.currentText()
            if name:
                profile = {k: self._ov._ov_cfg[k] for k in LAYOUT_PROFILE_KEYS if k in self._ov._ov_cfg}
                save_layout_profile(self._ov._cfg, name, profile)

        def _lp_apply():
            name = lp_combo.currentText()
            if name:
                profiles = get_layout_profiles(self._ov._cfg)
                prof = profiles.get(name, {})
                apply_layout_profile_to_ov_cfg(self._ov._ov_cfg, prof)
                self._ov._cfg['active_layout_profile'] = name
                w_val = int(self._ov._ov_cfg.get('w', 280))
                h_val = int(self._ov._ov_cfg.get('h', 200))
                self._ov.resize(w_val, h_val)
                if hasattr(self._ov, '_thread'):
                    self._ov._thread.set_fps(int(self._ov._ov_cfg.get('fps', 30)))
                self._ov._schedule_autosave()
                self._ov.update()

        def _lp_del():
            name = lp_combo.currentText()
            if name and name != 'Default':
                delete_layout_profile(self._ov._cfg, name)
                _reload_lp_combo()

        btn_lp_new.clicked.connect(_lp_new)
        btn_lp_save.clicked.connect(_lp_save)
        btn_lp_apply.clicked.connect(_lp_apply)
        btn_lp_del.clicked.connect(_lp_del)

        # --- Position / size ---
        _section(lay, "POSICION Y TAMANO")

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

        chk_ma = QCheckBox("Mantener proporcion de captura")
        chk_ma.setChecked(bool(self._cfg('maintain_aspect')))
        chk_ma.toggled.connect(lambda v: (self._set('maintain_aspect', v), self._ov.update()))
        lay.addWidget(chk_ma)

        btn_save = QPushButton("Guardar layout")
        btn_save.clicked.connect(self._ov._do_save)
        btn_reset = QPushButton("Resetear posicion")
        btn_reset.clicked.connect(lambda: (self._ov.move(400, 300),
                                            self._ov.resize(280, 200),
                                            self._ov._schedule_autosave()))
        row_btns = QHBoxLayout()
        row_btns.addWidget(btn_save)
        row_btns.addWidget(btn_reset)
        row_btns.addStretch()
        lay.addLayout(row_btns)

        # --- Snap ---
        _section(lay, "SNAP A CUADRICULA")

        chk_snap = QCheckBox("Alinear a cuadricula al mover (ALT para omitir)")
        chk_snap.setChecked(bool(self._cfg('snap_enabled')))
        chk_snap.toggled.connect(lambda v: self._set('snap_enabled', v))
        lay.addWidget(chk_snap)

        sp_gx = QSpinBox(); sp_gx.setRange(1, 200); sp_gx.setValue(int(self._cfg('snap_x') or 20))
        sp_gy = QSpinBox(); sp_gy.setRange(1, 200); sp_gy.setValue(int(self._cfg('snap_y') or 20))
        sp_gx.valueChanged.connect(lambda v: self._set('snap_x', v))
        sp_gy.valueChanged.connect(lambda v: self._set('snap_y', v))
        _row(lay, "Grid X (px):", sp_gx)
        _row(lay, "Grid Y (px):", sp_gy)

        # --- FPS ---
        _section(lay, "CAPTURA")

        cmb_fps = QComboBox()
        cmb_fps.addItems(['5', '10', '15', '30', '60', '120'])
        fps_now = str(getattr(self._ov._thread, '_fps', 30) if hasattr(self._ov, '_thread') else 30)
        if cmb_fps.findText(fps_now) >= 0:
            cmb_fps.setCurrentText(fps_now)
        cmb_fps.currentTextChanged.connect(lambda v: self._ov._set_fps(int(v)))
        _row(lay, "Fotogramas (FPS):", cmb_fps)

        # --- Copy layout to all ---
        _section(lay, "COPIAR LAYOUT A TODAS")

        chk_copy_size = QCheckBox("Incluir tamano (ancho/alto)")
        chk_copy_size.setChecked(False)
        lay.addWidget(chk_copy_size)

        lbl_layout_status = QLabel("")
        lbl_layout_status.setStyleSheet("color:#00ff64; font-size:10px;")

        def _copy_layout_all():
            from overlay.replicator_config import apply_common_settings_to_all, LAYOUT_PROFILE_KEYS
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            keys_to_copy = [k for k in LAYOUT_PROFILE_KEYS if k not in ('w', 'h')]
            if chk_copy_size.isChecked():
                keys_to_copy = LAYOUT_PROFILE_KEYS[:]
            apply_common_settings_to_all(self._ov._cfg, self._ov._title, keys=keys_to_copy)
            src = {k: self._ov._ov_cfg[k] for k in keys_to_copy if k in self._ov._ov_cfg}
            peers = [p for p in list(_OVERLAY_REGISTRY) if p is not self._ov]
            for peer in peers:
                try:
                    peer.apply_settings_dict(src, persist=False)
                except Exception:
                    pass
            lbl_layout_status.setText(f"Layout copiado a {len(peers)} replica(s).")

        btn_copy_layout = QPushButton("Replicar layout")
        btn_copy_layout.setObjectName("green")
        btn_copy_layout.clicked.connect(_copy_layout_all)
        lay.addWidget(btn_copy_layout)
        lay.addWidget(lbl_layout_status)

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
        _row(lay, "Posicion:", cmb_pos)

        sp_fs = QSpinBox(); sp_fs.setRange(6, 24); sp_fs.setValue(int(self._cfg('label_font_size') or 10))
        sp_fs.valueChanged.connect(lambda v: (self._set('label_font_size', v), self._ov.update()))
        _row(lay, "Tamano fuente:", sp_fs)

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

        lay.addSpacing(10)
        lbl_status = QLabel("")
        lbl_status.setStyleSheet("color:#00ff64; font-size:10px;")

        def _apply_label_all():
            from overlay.replicator_config import LABEL_COPY_KEYS, apply_settings_keys_to_all
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            apply_settings_keys_to_all(self._ov._cfg, self._ov._title, LABEL_COPY_KEYS)
            src = {k: self._ov._ov_cfg[k] for k in LABEL_COPY_KEYS if k in self._ov._ov_cfg}
            peers = [p for p in list(_OVERLAY_REGISTRY) if p is not self._ov]
            for peer in peers:
                try:
                    peer.apply_settings_dict(src, persist=False)
                except Exception:
                    pass
            lbl_status.setText(f"Etiqueta aplicada a {len(peers)} replicas.")

        btn_apply = QPushButton("Aplicar etiqueta a todas")
        btn_apply.setObjectName("green")
        btn_apply.clicked.connect(_apply_label_all)
        lay.addWidget(btn_apply)
        lay.addWidget(lbl_status)

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

        chk_ha = QCheckBox("Destacar cuando este cliente esta activo")
        chk_ha.setChecked(bool(self._cfg('highlight_active')))
        chk_ha.toggled.connect(lambda v: self._set('highlight_active', v))
        lay.addWidget(chk_ha)

        sp_bw = QSpinBox(); sp_bw.setRange(1, 10); sp_bw.setValue(int(self._cfg('border_width') or 2))
        sp_bw.valueChanged.connect(lambda v: (self._set('border_width', v), self._ov.update()))
        _row(lay, "Grosor borde:", sp_bw)

        _shapes = ['square', 'rounded', 'pill', 'glow', 'brackets']
        cmb_shape = QComboBox()
        cmb_shape.addItems(_shapes)
        cur_shape = self._cfg('border_shape') or 'square'
        if cur_shape in _shapes:
            cmb_shape.setCurrentText(cur_shape)
        cmb_shape.currentTextChanged.connect(lambda v: (self._set('border_shape', v), self._ov.update()))
        _row(lay, "Forma:", cmb_shape)

        _section(lay, "COLORES")

        btn_ac = _color_btn(self._cfg('active_border_color') or '#00ff64',
                            lambda v: (self._set('active_border_color', v), self._ov.update()))
        _row(lay, "Color activo:", btn_ac)

        btn_cc = _color_btn(self._cfg('client_color') or '#00c8ff',
                            lambda v: (self._set('client_color', v), self._ov.update()))
        _row(lay, "Color cliente:", btn_cc)

        lay.addSpacing(10)
        chk_inc_col = QCheckBox("Incluir color por cliente")
        chk_inc_col.setChecked(False)
        lay.addWidget(chk_inc_col)
        
        lbl_b_status = QLabel("")
        lbl_b_status.setStyleSheet("color:#00ff64; font-size:10px;")

        def _apply_border_all():
            from overlay.replicator_config import BORDER_COPY_KEYS, apply_settings_keys_to_all
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            apply_settings_keys_to_all(self._ov._cfg, self._ov._title, BORDER_COPY_KEYS, 
                                        include_client_color=chk_inc_col.isChecked())
            keys = BORDER_COPY_KEYS[:]
            if chk_inc_col.isChecked(): keys.append('client_color')
            src = {k: self._ov._ov_cfg[k] for k in keys if k in self._ov._ov_cfg}
            peers = [p for p in list(_OVERLAY_REGISTRY) if p is not self._ov]
            for peer in peers:
                try:
                    peer.apply_settings_dict(src, persist=False)
                except Exception:
                    pass
            lbl_b_status.setText(f"Borde aplicado a {len(peers)} replicas.")

        btn_apply_b = QPushButton("Aplicar borde a todas")
        btn_apply_b.setObjectName("green")
        btn_apply_b.clicked.connect(_apply_border_all)
        lay.addWidget(btn_apply_b)
        lay.addWidget(lbl_b_status)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ #
    # Tab: Hotkeys (Phase 2)
    # ------------------------------------------------------------------ #
    def _tab_hotkeys(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(6)

        from overlay.replicator_config import get_hotkeys_cfg, save_hotkeys_cfg
        hk = get_hotkeys_cfg(self._ov._cfg)

        _section(lay, "GRUPO DE CICLO")
        
        group_row = QHBoxLayout()
        cmb_group = QComboBox()
        cmb_group.addItems(["Grupo 1", "Grupo 2", "Grupo 3", "Grupo 4", "Grupo 5"])
        group_row.addWidget(cmb_group)
        chk_grp_en = QCheckBox("Habilitado")
        group_row.addWidget(chk_grp_en)
        lay.addLayout(group_row)

        le_grp_name = QLineEdit()
        le_grp_name.setPlaceholderText("Nombre del grupo (ej: Dps)")
        _row(lay, "Nombre:", le_grp_name)

        le_grp_next = QLineEdit()
        le_grp_next.setPlaceholderText("Siguiente en grupo")
        _row(lay, "Hotkey Sig:", le_grp_next)

        le_grp_prev = QLineEdit()
        le_grp_prev.setPlaceholderText("Anterior en grupo")
        _row(lay, "Hotkey Ant:", le_grp_prev)

        lay.addWidget(QLabel("Seleccionar cuentas para el grupo:"))
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(120)
        scroll.setStyleSheet("background: #0d1117; border: 1px solid #1e293b; border-radius: 4px;")
        
        scroll_content = QWidget()
        self._accounts_lay = QVBoxLayout(scroll_content)
        self._accounts_lay.setContentsMargins(5, 5, 5, 5)
        self._accounts_lay.setSpacing(2)
        scroll.setWidget(scroll_content)
        lay.addWidget(scroll)

        self._account_chks = {}

        def refresh_accounts():
            while self._accounts_lay.count():
                child = self._accounts_lay.takeAt(0)
                if child.widget(): child.widget().deleteLater()
            self._account_chks = {}
            from overlay.win32_capture import find_eve_windows
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            ov_titles = {ov._title for ov in list(_OVERLAY_REGISTRY)}
            win_titles = {w['title'] for w in find_eve_windows()}
            all_titles = sorted(list(ov_titles | win_titles))
            for t in all_titles:
                chk = QCheckBox(t)
                chk.setStyleSheet("color: #cbd5e1; font-size: 10px;")
                self._accounts_lay.addWidget(chk)
                self._account_chks[t] = chk
            self._accounts_lay.addStretch()

        btn_refresh = QPushButton("🔄 Refrescar clientes")
        btn_refresh.setFixedWidth(120)
        btn_refresh.clicked.connect(refresh_accounts)
        lay.addWidget(btn_refresh)

        def _load_group(idx):
            gid = str(idx + 1)
            gdata = hk.get('groups', {}).get(gid, {})
            chk_grp_en.setChecked(bool(gdata.get('enabled', False)))
            le_grp_name.setText(gdata.get('name', f"Grupo {gid}"))
            le_grp_next.setText(gdata.get('next', ''))
            le_grp_prev.setText(gdata.get('prev', ''))
            saved_clients = gdata.get('clients_order', [])
            for t, chk in self._account_chks.items():
                chk.setChecked(t in saved_clients)

        def _save_current_group():
            gid = str(cmb_group.currentIndex() + 1)
            checked = [t for t, chk in self._account_chks.items() if chk.isChecked()]
            hk.setdefault('groups', {})[gid] = {
                'enabled': chk_grp_en.isChecked(),
                'name': le_grp_name.text().strip(),
                'next': le_grp_next.text().strip().upper(),
                'prev': le_grp_prev.text().strip().upper(),
                'clients_order': checked
            }
            save_hotkeys_cfg(self._ov._cfg, hk)
            lbl_hk_status.setText(f"Grupo {gid} guardado.")

        btn_save_group = QPushButton("💾 Guardar Grupo")
        btn_save_group.setObjectName("blue")
        btn_save_group.clicked.connect(_save_current_group)
        lay.addWidget(btn_save_group)

        cmb_group.currentIndexChanged.connect(_load_group)
        refresh_accounts()
        _load_group(0)

        lbl_hk_status = QLabel("")
        lbl_hk_status.setStyleSheet("color:#00ff64; font-size:10px;")

        def _save_all_hk():
            from overlay.replicator_hotkeys import register_hotkeys, update_hotkey_cache, unregister_hotkeys
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            # Save groups logic is handled per-group in _save_current_group, 
            # but we still save the master hk config here if needed.
            save_hotkeys_cfg(self._ov._cfg, hk)
            def _get_titles():
                return [ov._title for ov in list(_OVERLAY_REGISTRY)]
            try:
                titles = _get_titles()
                update_hotkey_cache(titles)
                register_hotkeys(self._ov._cfg, cycle_titles_getter=_get_titles)
                lbl_hk_status.setText("Hotkeys aplicadas correctamente.")
            except Exception as e:
                lbl_hk_status.setText(f"Error: {e}")

        btn_hk_save = QPushButton("Aplicar Hotkeys")
        btn_hk_save.setObjectName("green")
        btn_hk_save.clicked.connect(_save_all_hk)
        lay.addWidget(btn_hk_save)
        lay.addWidget(lbl_hk_status)

        lay.addStretch()
        return w
