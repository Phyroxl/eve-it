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

# ... (General, Layout, Etiqueta, Borde, Hotkeys)

from overlay.dialog_utils import REPLICATOR_STYLE as _STYLE_BASE

# Extra CSS: reorder buttons get named selectors so the dialog stylesheet wins over any inline style
_REORDER_STYLE = """
QPushButton#reorderUp, QPushButton#reorderDown {
    background: #1e293b; border: 1px solid #334155; color: #94a3b8;
    font-size: 16px; font-weight: bold; border-radius: 5px; padding: 0;
    min-width: 30px; min-height: 42px;
}
QPushButton#reorderUp:hover, QPushButton#reorderDown:hover {
    background: #1e3a4a; border-color: #00c8ff; color: #00c8ff;
}
QPushButton#reorderUp:pressed, QPushButton#reorderDown:pressed {
    background: #0f172a; border-color: #00c8ff;
}
"""
_STYLE = _STYLE_BASE + _REORDER_STYLE


def _row(parent_layout, label_text: str, widget) -> None:
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setFixedWidth(145) # Stretched ~10% (130 -> 145)
    row.addWidget(lbl)
    row.addWidget(widget)
    row.addStretch()
    parent_layout.addLayout(row)


def _section(parent_layout, text: str) -> None:
    lbl = QLabel(text)
    lbl.setObjectName("section")
    parent_layout.addWidget(lbl)


def _color_btn(parent_dlg, color_hex: str, callback) -> QPushButton:
    from overlay.dialog_utils import pick_color_topmost
    btn = QPushButton()
    btn.setFixedSize(32, 22)
    btn.setStyleSheet(f"background:{color_hex}; border:1px solid #334155; border-radius:3px;")
    def _pick():
        new_col = pick_color_topmost(parent_dlg, color_hex)
        if new_col:
            btn.setStyleSheet(f"background:{new_col}; border:1px solid #334155; border-radius:3px;")
            callback(new_col)
    btn.clicked.connect(_pick)
    return btn


class ReplicatorSettingsDialog(QDialog):
    """Per-replica settings dialog: General | Layout | Etiqueta | Borde | Avanzado."""

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._ov = overlay
        self.setWindowTitle(f"Ajustes — {overlay._title}")
        self.setMinimumWidth(380)
        self.setStyleSheet(_STYLE)
        
        # Premium: Frameless + Custom Drag Header
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool) if hasattr(Qt, 'WindowType') else (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowFlags(flags)
        
        self._drag_pos = None
        self._build_ui()
        self._load_geometry()
        
        # Sync geometry in real-time from overlay
        self._ov.geometryChanged.connect(self._on_overlay_geometry_changed)

    def _on_overlay_geometry_changed(self, x, y, w, h):
        # Update spinboxes if they exist (they are defined in _tab_layout)
        if hasattr(self, '_sp_x'):
            self._sp_x.blockSignals(True)
            self._sp_y.blockSignals(True)
            self._sp_w.blockSignals(True)
            self._sp_h.blockSignals(True)
            
            self._sp_x.setValue(x)
            self._sp_y.setValue(y)
            self._sp_w.setValue(w)
            self._sp_h.setValue(h)
            
            self._sp_x.blockSignals(False)
            self._sp_y.blockSignals(False)
            self._sp_w.blockSignals(False)
            self._sp_h.blockSignals(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            gpos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            diff = gpos - self._drag_pos
            self.move(self.pos() + diff)
            self._drag_pos = gpos

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._save_geometry()

    def _save_geometry(self):
        try:
            self._ov._cfg.setdefault('global', {})['settings_dialog_size'] = {
                'w': self.width(),
                'h': self.height()
            }
            # Also save position if desired, but task only asks for size.
            # We'll stick to size to keep it simple as requested.
        except Exception:
            pass

    def _load_geometry(self):
        try:
            size = self._ov._cfg.get('global', {}).get('settings_dialog_size')
            if size:
                self.resize(size.get('w', 360), size.get('h', 420))
        except Exception:
            pass

    def _cfg(self, key, default=None):
        return self._ov._ov_cfg.get(key, default)

    def _set(self, key, value):
        self._ov._ov_cfg[key] = value
        self._ov._schedule_autosave()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Custom Header
        hdr = QWidget()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet("background: #000; border-bottom: 1px solid #1e293b;")
        h_lay = QHBoxLayout(hdr)
        h_lay.setContentsMargins(12, 0, 6, 0)
        
        icon_lbl = QLabel("⚙️")
        h_lay.addWidget(icon_lbl)
        
        title_lbl = QLabel(f"AJUSTES — {self._ov._title.upper()}")
        title_lbl.setStyleSheet("color: #00c8ff; font-weight: 800; font-size: 10px; letter-spacing: 1px;")
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()
        
        btn_x = QPushButton("×")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: #64748b; font-size: 18px; font-weight: normal; }
            QPushButton:hover { color: #ff6666; background: rgba(255,50,50,0.1); border-radius: 3px; }
        """)
        btn_x.clicked.connect(self.reject)
        h_lay.addWidget(btn_x)
        lay.addWidget(hdr)

        content_lay = QVBoxLayout()
        content_lay.setContentsMargins(12, 12, 12, 12)
        content_lay.setSpacing(8)
        
        tabs = QTabWidget()
        tabs.addTab(self._tab_general(),  "General")
        tabs.addTab(self._tab_layout(),   "Layout")
        tabs.addTab(self._tab_label(),    "Etiqueta")
        tabs.addTab(self._tab_border(),   "Borde")
        tabs.addTab(self._tab_hotkeys(), "Hotkeys")
        content_lay.addWidget(tabs)

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("close")
        btn_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_close)
        content_lay.addLayout(row)
        lay.addLayout(content_lay)

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

        # --- Apply settings to all ---
        _section(lay, "APLICAR CONFIGURACION A TODAS")

        lbl_gen_status = QLabel("")
        lbl_gen_status.setStyleSheet("color:#00ff64; font-size:10px;")
 
        chk_inc_color = QCheckBox("Incluir color por cliente")
        chk_inc_color.setStyleSheet("color:#cbd5e1; font-size:10px;")
        lay.addWidget(chk_inc_color)

        def _replicate_all():
            from overlay.replicator_config import apply_settings_keys_to_all, FULL_REPLICATE_KEYS
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            
            # 1. Sincronizar estado actual del widget a ov_cfg
            self._ov._do_save()
            
            src_title = self._ov._title
            keys = FULL_REPLICATE_KEYS
            
            # 2. Replicar en el archivo de configuración
            apply_settings_keys_to_all(
                self._ov._cfg, src_title, 
                keys=keys, 
                include_client_color=chk_inc_color.isChecked()
            )
            
            # 3. Replicar en caliente a los objetos activos
            src = {k: self._ov._ov_cfg[k] for k in keys if k in self._ov._ov_cfg}
            if chk_inc_color.isChecked() and 'client_color' in self._ov._ov_cfg:
                src['client_color'] = self._ov._ov_cfg['client_color']

            peers = [p for p in list(_OVERLAY_REGISTRY) if p is not self._ov]
            for peer in peers:
                try:
                    # Aplicar todos los ajustes visuales (incluyendo región)
                    peer.apply_settings_dict(src, persist=False)
                    
                    # Aplicar geometría de ventana (x, y, w, h)
                    x_v = int(src.get('x', peer.x()))
                    y_v = int(src.get('y', peer.y()))
                    w_v = int(src.get('w', peer.width()))
                    h_v = int(src.get('h', peer.height()))
                    peer.move(x_v, y_v)
                    peer.resize(w_v, h_v)
                    
                    peer.update()
                except Exception as e:
                    logger.error(f"Error replicando ajustes a peer: {e}")
                    
            lbl_gen_status.setText(f"Ajustes replicados a {len(peers)} replica(s).")

        btn_gen = QPushButton("Copiar y replicar ajustes")
        btn_gen.setObjectName("green")
        btn_gen.clicked.connect(_replicate_all)
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
            get_active_layout_profile, apply_layout_profile_to_ov_cfg,
            LAYOUT_PROFILE_KEYS, FULL_PROFILE_KEYS,
        )

        prof_row = QHBoxLayout()
        lp_combo = QComboBox()
        lp_combo.setMinimumWidth(100)
        prof_row.addWidget(QLabel("Perfil:"))
        prof_row.addWidget(lp_combo, 1)

        btn_lp_new = QPushButton("+")
        btn_lp_new.setToolTip("Nuevo perfil")
        btn_lp_save = QPushButton("Guardar")
        btn_lp_del = QPushButton("Eliminar")
        
        btn_lp_new.setFixedWidth(32)
        for b in [btn_lp_new, btn_lp_save, btn_lp_del]:
            b.setFixedHeight(24)
            if b != btn_lp_new:
                b.setMinimumWidth(65)
            prof_row.addWidget(b)
        lay.addLayout(prof_row)

        btn_lp_apply = QPushButton("Aplicar")
        btn_lp_apply.setObjectName("blue")
        btn_lp_apply.setFixedHeight(24)
        lay.addWidget(btn_lp_apply)

        chk_lp_all = QCheckBox("Aplicar a todas las réplicas")
        chk_lp_all.setStyleSheet("font-size: 10px; color: #94a3b8;")
        lay.addWidget(chk_lp_all)

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
                self._ov._do_save()
                # Save full profile (all settings, not just layout)
                profile = {k: self._ov._ov_cfg[k] for k in FULL_PROFILE_KEYS if k in self._ov._ov_cfg}
                save_layout_profile(self._ov._cfg, name.strip(), profile)
                _reload_lp_combo()
                lp_combo.setCurrentText(name.strip())

        def _lp_save():
            name = lp_combo.currentText()
            if name:
                self._ov._do_save()
                # Save full profile (all settings, not just layout)
                profile = {k: self._ov._ov_cfg[k] for k in FULL_PROFILE_KEYS if k in self._ov._ov_cfg}
                save_layout_profile(self._ov._cfg, name, profile)

        def _lp_apply():
            name = lp_combo.currentText()
            if not name: return
            
            profiles = get_layout_profiles(self._ov._cfg)
            prof = profiles.get(name, {})
            if not prof: return

            self._ov._cfg['active_layout_profile'] = name
            
            # ¿Aplicar a todas?
            if chk_lp_all.isChecked():
                from overlay.replication_overlay import _OVERLAY_REGISTRY
                peers = list(_OVERLAY_REGISTRY)
                logger.info(f"[REPLICATOR SETTINGS] Aplicando perfil '{name}' a {len(peers)} replicas")
                for peer in peers:
                    try:
                        apply_layout_profile_to_ov_cfg(peer._ov_cfg, prof)
                        # Usar el helper unificado para aplicar cambios visuales (incluyendo región)
                        peer.apply_settings_dict(prof, persist=True)
                        # Forzar redimensionado manual ya que apply_settings_dict no toca x/y/w/h de ventana directamente
                        w_v = int(peer._ov_cfg.get('w', 280))
                        h_v = int(peer._ov_cfg.get('h', 200))
                        peer.resize(w_v, h_v)
                    except Exception as e:
                        logger.error(f"Error aplicando perfil a peer: {e}")
            else:
                # Solo a la actual
                apply_layout_profile_to_ov_cfg(self._ov._ov_cfg, prof)
                self._ov.apply_settings_dict(prof, persist=True)
                w_val = int(self._ov._ov_cfg.get('w', 280))
                h_val = int(self._ov._ov_cfg.get('h', 200))
                self._ov.resize(w_val, h_val)

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

        # --- FPS ---
        _section(lay, "CAPTURA")

        cmb_fps = QComboBox()
        cmb_fps.addItems(['1', '5', '10', '15', '30', '60', '120'])
        fps_now = str(getattr(self._ov._thread, '_fps', 30) if hasattr(self._ov, '_thread') else 30)
        if cmb_fps.findText(fps_now) >= 0:
            cmb_fps.setCurrentText(fps_now)
        cmb_fps.currentTextChanged.connect(lambda v: self._ov._set_fps(int(v)))
        _row(lay, "Fotogramas (FPS):", cmb_fps)

        # --- Position / size ---
        _section(lay, "POSICIÓN y TAMAÑO")

        sp_x = QSpinBox(); sp_x.setRange(0, 9999); sp_x.setValue(self._ov.x())
        sp_y = QSpinBox(); sp_y.setRange(0, 9999); sp_y.setValue(self._ov.y())
        sp_w = QSpinBox(); sp_w.setRange(20, 4096); sp_w.setValue(self._ov.width())
        sp_h = QSpinBox(); sp_h.setRange(20, 4096); sp_h.setValue(self._ov.height())

        # Guardar referencias para el sync en tiempo real
        self._sp_x = sp_x; self._sp_y = sp_y; self._sp_w = sp_w; self._sp_h = sp_h

        sp_x.valueChanged.connect(lambda v: self._ov.move(v, self._ov.y()))
        sp_y.valueChanged.connect(lambda v: self._ov.move(self._ov.x(), v))
        sp_w.valueChanged.connect(lambda v: self._ov.resize(v, self._ov.height()))
        sp_h.valueChanged.connect(lambda v: self._ov.resize(self._ov.width(), v))
        
        # ENTER aplica cambios (editingFinished dispara la actualizacion final)
        sp_x.editingFinished.connect(lambda: self._ov.move(sp_x.value(), sp_y.value()))
        sp_y.editingFinished.connect(lambda: self._ov.move(sp_x.value(), sp_y.value()))
        sp_w.editingFinished.connect(lambda: self._ov.resize(sp_w.value(), sp_h.value()))
        sp_h.editingFinished.connect(lambda: self._ov.resize(sp_w.value(), sp_h.value()))

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
        sp_gx.editingFinished.connect(lambda: self._set('snap_x', sp_gx.value()))
        sp_gy.editingFinished.connect(lambda: self._set('snap_y', sp_gy.value()))

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
        _row(lay, "Posicion:", cmb_pos)

        sp_fs = QSpinBox(); sp_fs.setRange(6, 24); sp_fs.setValue(int(self._cfg('label_font_size') or 10))
        sp_fs.valueChanged.connect(lambda v: (self._set('label_font_size', v), self._ov.update()))
        sp_fs.editingFinished.connect(lambda: (self._set('label_font_size', sp_fs.value()), self._ov.update()))
        _row(lay, "Tamano fuente:", sp_fs)

        btn_col = _color_btn(self, self._cfg('label_color') or '#ffffff',
                             lambda v: (self._set('label_color', v), self._ov.update()))
        _row(lay, "Color texto:", btn_col)

        _section(lay, "FONDO")

        chk_bg = QCheckBox("Fondo de etiqueta")
        chk_bg.setChecked(bool(self._cfg('label_bg')))
        chk_bg.toggled.connect(lambda v: (self._set('label_bg', v), self._ov.update()))
        lay.addWidget(chk_bg)

        btn_bgcol = _color_btn(self, self._cfg('label_bg_color') or '#000000',
                               lambda v: (self._set('label_bg_color', v), self._ov.update()))
        _row(lay, "Color fondo:", btn_bgcol)

        sp_bop = QDoubleSpinBox()
        sp_bop.setRange(0.0, 1.0); sp_bop.setSingleStep(0.05)
        sp_bop.setValue(float(self._cfg('label_bg_opacity') or 0.65))
        sp_bop.valueChanged.connect(lambda v: (self._set('label_bg_opacity', v), self._ov.update()))
        sp_bop.editingFinished.connect(lambda: (self._set('label_bg_opacity', sp_bop.value()), self._ov.update()))
        _row(lay, "Opacidad fondo:", sp_bop)

        sp_pad = QSpinBox(); sp_pad.setRange(0, 20); sp_pad.setValue(int(self._cfg('label_padding') or 4))
        sp_pad.valueChanged.connect(lambda v: (self._set('label_padding', v), self._ov.update()))
        sp_pad.editingFinished.connect(lambda: (self._set('label_padding', sp_pad.value()), self._ov.update()))
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

        btn_apply = QPushButton("Replicar etiqueta")
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
        sp_bw.editingFinished.connect(lambda: (self._set('border_width', sp_bw.value()), self._ov.update()))
        _row(lay, "Grosor borde:", sp_bw)

        _shapes = ['square', 'rounded', 'pill']
        cmb_shape = QComboBox()
        cmb_shape.addItems(_shapes)
        cur_shape = self._cfg('border_shape') or 'square'
        if cur_shape in _shapes:
            cmb_shape.setCurrentText(cur_shape)
        else:
            # Fallback visual en el combo si la config tiene algo raro
            cmb_shape.setCurrentText('square')
            
        cmb_shape.currentTextChanged.connect(lambda v: (
            self._set('border_shape', v),
            self._ov._apply_window_shape_mask(),
            self._ov.update(),
            self._ov.repaint(),
        ))
        _row(lay, "Forma:", cmb_shape)

        _section(lay, "COLORES")

        btn_ac = _color_btn(self, self._cfg('active_border_color') or '#00ff64',
                            lambda v: (self._set('active_border_color', v), self._ov.update()))
        _row(lay, "Color activo:", btn_ac)

        btn_cc = _color_btn(self, self._cfg('client_color') or '#00c8ff',
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
            keys = BORDER_COPY_KEYS[:]
            if chk_inc_col.isChecked():
                keys.append('client_color')
            # Flush current _ov_cfg values to cfg['overlays'] before apply_settings_keys_to_all
            # reads them — avoids propagating a stale value when autosave hasn't fired yet.
            src_title = self._ov._title
            self._ov._cfg.setdefault('overlays', {}).setdefault(src_title, {})
            for k in keys:
                if k in self._ov._ov_cfg:
                    self._ov._cfg['overlays'][src_title][k] = self._ov._ov_cfg[k]
            apply_settings_keys_to_all(self._ov._cfg, src_title, BORDER_COPY_KEYS,
                                        include_client_color=chk_inc_col.isChecked())
            src = {k: self._ov._ov_cfg[k] for k in keys if k in self._ov._ov_cfg}
            peers = [p for p in list(_OVERLAY_REGISTRY) if p is not self._ov]
            for peer in peers:
                try:
                    peer.apply_settings_dict(src, persist=False)
                    peer.update()
                    peer.repaint()
                    if hasattr(peer, '_schedule_autosave'):
                        peer._schedule_autosave()
                except Exception:
                    pass
            lbl_b_status.setText(f"Borde aplicado a {len(peers)} replicas.")

        btn_apply_b = QPushButton("Replicar borde")
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
        
        def _format_group_label(gid, gdata):
            name = gdata.get('name', '').strip()
            if name: return f"Grupo {gid} — {name}"
            return f"Grupo {gid}"

        group_row = QHBoxLayout()
        cmb_group = QComboBox()
        def _reload_group_combo():
            cur_gid = cmb_group.currentData() or "1"
            cmb_group.blockSignals(True)
            cmb_group.clear()
            for i in range(1, 6):
                gid = str(i)
                gdata = hk.get('groups', {}).get(gid, {})
                cmb_group.addItem(_format_group_label(gid, gdata), gid)
            idx = cmb_group.findData(cur_gid)
            if idx >= 0: cmb_group.setCurrentIndex(idx)
            cmb_group.blockSignals(False)

        group_row.addWidget(cmb_group)
        chk_grp_en = QCheckBox("Habilitado")
        group_row.addWidget(chk_grp_en)
        lay.addLayout(group_row)

        le_grp_name = QLineEdit()
        le_grp_name.setPlaceholderText("Nombre del grupo (ej: Dps)")
        le_grp_next = QLineEdit()
        le_grp_next.setPlaceholderText("Siguiente en grupo")
        le_grp_prev = QLineEdit()
        le_grp_prev.setPlaceholderText("Anterior en grupo")

        lbl_hk_status = QLabel("")
        lbl_hk_status.setStyleSheet("color:#00ff64; font-size:10px;")

        def _save_current_group():
            gid = cmb_group.currentData() or str(cmb_group.currentIndex() + 1)
            
            # Leer el orden visual desde el QListWidget
            ordered_titles = []
            for i in range(self._accounts_list.count()):
                item = self._accounts_list.item(i)
                title = item.data(Qt.UserRole)
                
                # Fallback de seguridad: si UserRole es None, intentar extraer del texto visual
                if title is None:
                    raw_text = item.text()
                    if ". " in raw_text:
                        title = raw_text.split(". ", 1)[1]
                    else:
                        title = raw_text
                    logger.warning(f"[HOTKEY CONFIG WARN] Client ID era None en index {i}. Recuperado del texto: '{title}'")
                
                if item.checkState() == Qt.Checked and title:
                    ordered_titles.append(title)

            hk.setdefault('groups', {})[gid] = {
                'enabled': chk_grp_en.isChecked(),
                'name': le_grp_name.text().strip(),
                'next': le_grp_next.text().strip().upper(),
                'prev': le_grp_prev.text().strip().upper(),
                'clients_order': ordered_titles
            }
            save_hotkeys_cfg(self._ov._cfg, hk)
            _reload_group_combo()
            lbl_hk_status.setText(f"Grupo {gid} guardado.")
            
            # Log a archivo para diagnóstico
            try:
                from overlay.replicator_hotkeys import _log_to_file
                _log_to_file(f"[CONFIG SAVE] Group '{le_grp_name.text()}' ({gid}) saved. Order: {ordered_titles}")
            except Exception: pass
            
            logger.info(f"[HOTKEY ORDER DEBUG] Group {gid} saved. Order: {ordered_titles}")

        def _save_all_hk():
            from overlay.replicator_hotkeys import register_hotkeys, update_hotkey_cache, unregister_hotkeys
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            # Flush current group UI state first so its hotkey combo is in hk['groups']
            # before register_hotkeys reads group_combos — prevents F14 registering globally.
            _save_current_group()
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

        def _load_group(idx):
            gid = cmb_group.itemData(idx) or str(idx + 1)
            gdata = hk.get('groups', {}).get(gid, {})
            chk_grp_en.setChecked(bool(gdata.get('enabled', False)))
            le_grp_name.setText(gdata.get('name', f"Grupo {gid}"))
            le_grp_next.setText(gdata.get('next', ''))
            le_grp_prev.setText(gdata.get('prev', ''))
            
            saved_clients = gdata.get('clients_order', [])
            
            # Reordenar y marcar según guardado
            # 1. Obtener todos los items actuales
            items_data = []
            for i in range(self._accounts_list.count()):
                it = self._accounts_list.item(i)
                title = it.data(Qt.UserRole)
                items_data.append((title, it.checkState()))
            
            # 2. Reordenar: los que están en saved_clients primero, en su orden
            new_order = []
            found_titles = set()
            for s_t in saved_clients:
                # Buscar si existe en los detectados
                match = next((x for x in items_data if x[0] == s_t), None)
                if match:
                    new_order.append((s_t, Qt.Checked))
                    found_titles.add(s_t)
            
            # Añadir el resto (no estaban en el grupo)
            for title, _ in items_data:
                if title not in found_titles:
                    new_order.append((title, Qt.Unchecked))
            
            # 3. Re-poblar lista
            self._accounts_list.clear()
            for i, (title, state) in enumerate(new_order, 1):
                it = QListWidgetItem(f"{i}. {title}")
                it.setData(Qt.UserRole, title)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                it.setCheckState(state)
                self._accounts_list.addItem(it)

        # Conexiones ENTER para guardar
        le_grp_name.returnPressed.connect(_save_current_group)
        le_grp_next.returnPressed.connect(_save_current_group)
        le_grp_prev.returnPressed.connect(_save_current_group)

        _row(lay, "Nombre:", le_grp_name)
        _row(lay, "Hotkey Sig:", le_grp_next)
        _row(lay, "Hotkey Ant:", le_grp_prev)

        lay.addWidget(QLabel("Seleccionar cuentas y orden (1 = primero):"))
        
        list_box = QHBoxLayout()
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
        self._accounts_list = QListWidget()
        self._accounts_list.setMinimumHeight(180) # Mostrar al menos 5-6 cuentas
        self._accounts_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._accounts_list.setStyleSheet("""
            QListWidget { background: #0d1117; border: 1px solid #1e293b; border-radius: 4px; color: #cbd5e1; font-size: 10px; }
            QListWidget::item { padding: 2px; border-bottom: 1px solid #1a2533; }
            QListWidget::item:selected { background: #1e293b; color: #00c8ff; }
        """)
        
        # Actualizar números tras mover
        def _update_numbers():
            for i in range(self._accounts_list.count()):
                it = self._accounts_list.item(i)
                title = it.data(Qt.UserRole)
                it.setText(f"{i+1}. {title}")
        
        self._accounts_list.model().rowsMoved.connect(lambda: QTimer.singleShot(0, _update_numbers))
        
        list_box.addWidget(self._accounts_list)
        
        # Botones de orden — usan objectName para que el stylesheet del diálogo tenga máxima prioridad
        btn_lay = QVBoxLayout()
        btn_up = QPushButton("↑")
        btn_up.setObjectName("reorderUp")
        btn_up.setFixedSize(30, 44)
        btn_up.setToolTip("Subir cuenta")

        btn_down = QPushButton("↓")
        btn_down.setObjectName("reorderDown")
        btn_down.setFixedSize(30, 44)
        btn_down.setToolTip("Bajar cuenta")
        
        def _move_item(up=True):
            curr = self._accounts_list.currentRow()
            if curr < 0: return
            target = curr - 1 if up else curr + 1
            if 0 <= target < self._accounts_list.count():
                it = self._accounts_list.takeItem(curr)
                self._accounts_list.insertItem(target, it)
                self._accounts_list.setCurrentRow(target)
                _update_numbers()

        btn_up.clicked.connect(lambda: _move_item(True))
        btn_down.clicked.connect(lambda: _move_item(False))
        btn_lay.addWidget(btn_up); btn_lay.addWidget(btn_down); btn_lay.addStretch()
        list_box.addLayout(btn_lay)
        lay.addLayout(list_box)

        def refresh_accounts():
            # Preservar el orden visual actual si es posible
            current_order = []
            for i in range(self._accounts_list.count()):
                it = self._accounts_list.item(i)
                title = it.data(Qt.UserRole)
                current_order.append((title, it.checkState()))

            self._accounts_list.clear()
            from overlay.win32_capture import find_eve_windows
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            ov_titles = {ov._title for ov in list(_OVERLAY_REGISTRY)}
            win_titles = {w['title'] for w in find_eve_windows()}
            all_detected = list(ov_titles | win_titles)
            
            # Re-poblar siguiendo el orden previo si existe
            final_list = []
            found = set()
            for title, state in current_order:
                if title in all_detected:
                    final_list.append((title, state))
                    found.add(title)
            
            # Añadir nuevos
            for t in sorted(all_detected):
                if t not in found:
                    final_list.append((t, Qt.Unchecked))
            
            for i, (t, state) in enumerate(final_list, 1):
                it = QListWidgetItem(f"{i}. {t}")
                it.setData(Qt.UserRole, t)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                it.setCheckState(state)
                self._accounts_list.addItem(it)

        btn_row_ops = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Refrescar clientes")
        btn_refresh.setFixedWidth(140)
        btn_refresh.clicked.connect(refresh_accounts)
        
        btn_select_all = QPushButton("✅ Seleccionar todos")
        btn_select_all.setFixedWidth(140)
        def _select_all_clients():
            for i in range(self._accounts_list.count()):
                self._accounts_list.item(i).setCheckState(Qt.Checked)
        btn_select_all.clicked.connect(_select_all_clients)
        
        btn_row_ops.addWidget(btn_refresh)
        btn_row_ops.addWidget(btn_select_all)
        btn_row_ops.addStretch()
        lay.addLayout(btn_row_ops)
        

        btn_save_group = QPushButton("💾 Guardar Grupo")
        btn_save_group.setObjectName("blue")
        btn_save_group.clicked.connect(_save_current_group)
        lay.addWidget(btn_save_group)

        cmb_group.currentIndexChanged.connect(_load_group)
        _reload_group_combo()
        refresh_accounts()
        _load_group(0)

        btn_apply_hk = QPushButton("Aplicar Hotkeys")
        btn_apply_hk.setObjectName("green")
        btn_apply_hk.clicked.connect(_save_all_hk)
        lay.addWidget(btn_apply_hk)
        lay.addWidget(lbl_hk_status)

        lay.addStretch()
        return w
