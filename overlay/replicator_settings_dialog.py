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
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
        QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
        QPushButton, QColorDialog, QLineEdit, QSizePolicy,
        QMessageBox, QTextEdit, QScrollArea,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal as Signal
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

    # Cross-thread signal: hotkey thread → main thread UI update
    _hotkey_diag_signal = Signal(dict)

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
        self._resize_from_spinbox = False
        self._layout_change_broadcaster = None
        self._diag_active = False
        self._build_ui()
        self._load_geometry()

        # Sync geometry in real-time from overlay
        self._ov.geometryChanged.connect(self._on_overlay_geometry_changed)

    def closeEvent(self, event):
        if self._diag_active:
            try:
                from overlay.replicator_hotkeys import set_hotkey_diagnostics_enabled
                set_hotkey_diagnostics_enabled(False, None)
            except Exception:
                pass
            self._diag_active = False
        super().closeEvent(event)

    def _on_overlay_geometry_changed(self, x, y, w, h):
        # Update spinboxes if they exist (they are defined in _tab_layout)
        if hasattr(self, '_sp_x'):
            prev_w = self._sp_w.value()
            prev_h = self._sp_h.value()

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

            # Propagate manual border-drag resize to all peers (skip if spinbox triggered this)
            if not self._resize_from_spinbox and self._layout_change_broadcaster:
                if w != prev_w:
                    self._layout_change_broadcaster('w', w)
                if h != prev_h:
                    self._layout_change_broadcaster('h', h)

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

        def _hide_toggled(v):
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            ovs = list(_OVERLAY_REGISTRY)
            for ov in ovs:
                try:
                    ov._ov_cfg['hide_when_inactive'] = v
                    ov._schedule_autosave()
                except Exception:
                    pass
            if not v:
                for ov in ovs:
                    if not ov.isVisible():
                        saved = getattr(ov, '_last_visible_geom', None)
                        if saved:
                            sx, sy, sw, sh = saved
                            ov.show()
                            ov.setGeometry(sx, sy, sw, sh)
                        else:
                            ov.show()
            logger.info(f"[HIDE GLOBAL TOGGLE] enabled={v} overlays={len(ovs)}")

        chk_hide.toggled.connect(_hide_toggled)
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
                include_client_color=True
            )

            # 3. Replicar en caliente a los objetos activos
            src = {k: self._ov._ov_cfg[k] for k in keys if k in self._ov._ov_cfg}
            if 'client_color' in self._ov._ov_cfg:
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

        chk_lp_all = QCheckBox("Aplicar a todas las réplicas")
        chk_lp_all.setStyleSheet("font-size: 10px; color: #94a3b8;")
        lay.addWidget(chk_lp_all)

        def _reload_lp_combo():
            # Re-read from disk so profiles saved by other replicas' dialogs appear
            try:
                from overlay.replicator_config import load_config as _load_cfg
                disk = _load_cfg()
                self._ov._cfg['layout_profiles'] = disk.get('layout_profiles', {})
            except Exception:
                pass
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
            logger.debug(f"[LAYOUT PROFILE LOAD] count={len(profiles)} names={list(profiles.keys())}")

        _reload_lp_combo()

        # Guard: skip auto-apply triggered programmatically (e.g. during profile creation/reload)
        _profile_auto_applying = [False]

        def _lp_apply_profile(name: str):
            """Auto-apply: full profile restore (geometry + all settings) when user selects combo."""
            if not name or _profile_auto_applying[0]: return
            profiles = get_layout_profiles(self._ov._cfg)
            prof = profiles.get(name, {})
            if not prof: return
            self._ov._cfg['active_layout_profile'] = name
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            peers = list(_OVERLAY_REGISTRY)
            replicas = prof.get('replicas', {})
            for peer in peers:
                try:
                    cfg_to_use = replicas.get(peer._title) or prof
                    apply_layout_profile_to_ov_cfg(peer._ov_cfg, cfg_to_use)
                    peer.apply_settings_dict(cfg_to_use, persist=False)
                    x_v = int(cfg_to_use.get('x', peer.x()))
                    y_v = int(cfg_to_use.get('y', peer.y()))
                    w_v = int(cfg_to_use.get('w', peer.width()))
                    h_v = int(cfg_to_use.get('h', peer.height()))
                    peer.setGeometry(x_v, y_v, w_v, h_v)
                    peer._schedule_autosave()
                except Exception as e:
                    logger.error(f"[PROFILE AUTO-APPLY] error for {peer._title!r}: {e}")
            logger.info(f"[LAYOUT_PROFILE_LOAD] name='{name}' peers={len(peers)}")
            self._ov.update()

            # Auto-apply hotkeys: restore profile's hotkeys (if saved) then register.
            # This removes the need to manually click "Aplicar Hotkeys" after a profile load.
            try:
                from overlay.replicator_hotkeys import register_hotkeys, update_hotkey_cache
                prof_hotkeys = prof.get('hotkeys')
                if prof_hotkeys:
                    self._ov._cfg['hotkeys'] = prof_hotkeys
                    logger.info(
                        f"[HOTKEYS_PROFILE_RESTORED] profile='{name}' "
                        f"enabled={bool(prof_hotkeys.get('groups') or prof_hotkeys.get('per_client'))} "
                        f"count={len(prof_hotkeys)}"
                    )
                def _get_titles_lp():
                    return [o._title for o in list(_OVERLAY_REGISTRY)]
                titles_lp = _get_titles_lp()
                update_hotkey_cache(titles_lp)
                register_hotkeys(self._ov._cfg, cycle_titles_getter=_get_titles_lp)
                logger.info(
                    f"[HOTKEYS_AUTO_APPLY_AFTER_PROFILE_LOAD] profile='{name}' "
                    f"ok=True registered={len(titles_lp)}"
                )
            except Exception as _he:
                logger.warning(
                    f"[HOTKEYS_AUTO_APPLY_AFTER_PROFILE_LOAD] profile='{name}' err={_he}"
                )

        lp_combo.currentTextChanged.connect(_lp_apply_profile)

        def _collect_global_replicas() -> dict:
            """Snapshot geometry+config of ALL active overlays for multi-replica profile save."""
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            replicas = {}
            for ov in list(_OVERLAY_REGISTRY):
                try:
                    ov._do_save()
                    snap = {k: ov._ov_cfg[k] for k in FULL_PROFILE_KEYS if k in ov._ov_cfg}
                    snap['x'] = ov.x(); snap['y'] = ov.y()
                    snap['w'] = ov.width(); snap['h'] = ov.height()
                    replicas[ov._title] = snap
                except Exception as e:
                    logger.error(f"Error collecting replica snapshot for {ov._title!r}: {e}")
            return replicas

        def _lp_new():
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "Nuevo perfil", "Nombre:")
            if ok and name.strip():
                self._ov._do_save()
                profile = {k: self._ov._ov_cfg[k] for k in FULL_PROFILE_KEYS if k in self._ov._ov_cfg}
                hk_cfg = self._ov._cfg.get('hotkeys')
                if hk_cfg:
                    profile['hotkeys'] = dict(hk_cfg)
                replicas = _collect_global_replicas()
                save_layout_profile(self._ov._cfg, name.strip(), profile, replicas=replicas)
                logger.info(f"[PROFILE SAVE GLOBAL] name='{name.strip()}' replicas={len(replicas)} hotkeys_saved={bool(hk_cfg)}")
                # Propagate updated profiles dict to all active overlays so any
                # open settings dialog sees the new profile immediately
                _profs = self._ov._cfg.get('layout_profiles', {})
                for _ov in list(_OVERLAY_REGISTRY):
                    _ov._cfg['layout_profiles'] = _profs
                _profile_auto_applying[0] = True
                _reload_lp_combo()
                lp_combo.setCurrentText(name.strip())
                _profile_auto_applying[0] = False

        def _lp_save():
            name = lp_combo.currentText()
            if name:
                self._ov._do_save()
                profile = {k: self._ov._ov_cfg[k] for k in FULL_PROFILE_KEYS if k in self._ov._ov_cfg}
                hk_cfg = self._ov._cfg.get('hotkeys')
                if hk_cfg:
                    profile['hotkeys'] = dict(hk_cfg)
                replicas = _collect_global_replicas()
                save_layout_profile(self._ov._cfg, name, profile, replicas=replicas)
                logger.info(f"[PROFILE SAVE GLOBAL] name='{name}' replicas={len(replicas)} hotkeys_saved={bool(hk_cfg)}")
                # Propagate updated profiles dict to all active overlays
                _profs = self._ov._cfg.get('layout_profiles', {})
                for _ov in list(_OVERLAY_REGISTRY):
                    _ov._cfg['layout_profiles'] = _profs

        def _lp_del():
            name = lp_combo.currentText()
            if name and name != 'Default':
                delete_layout_profile(self._ov._cfg, name)
                _reload_lp_combo()

        btn_lp_new.clicked.connect(_lp_new)
        btn_lp_save.clicked.connect(_lp_save)
        btn_lp_del.clicked.connect(_lp_del)

        # --- Copy region to all other replicas ---
        btn_copy_region = QPushButton("Copiar región a todas")
        btn_copy_region.setToolTip(
            "Copia la región capturada de ESTA réplica a todas las demás.\n"
            "No cambia posición ni tamaño de ventana."
        )
        btn_copy_region.setFixedHeight(24)
        lay.addWidget(btn_copy_region)

        def _copy_region_to_all():
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            src_region = dict(self._ov._region)
            peers = [ov for ov in list(_OVERLAY_REGISTRY) if ov is not self._ov]
            for target in peers:
                try:
                    target._region.update(src_region)
                    # Keep per-overlay config keys in sync for persistence
                    target._ov_cfg['region_x'] = src_region.get('x', 0)
                    target._ov_cfg['region_y'] = src_region.get('y', 0)
                    target._ov_cfg['region_w'] = src_region.get('w', 1)
                    target._ov_cfg['region_h'] = src_region.get('h', 1)
                    target.update()
                    target._schedule_autosave()
                except Exception as e:
                    logger.error(f"[COPY REGION] error target={target._title!r}: {e}")
            logger.info(
                f"COPY REGION source={self._ov._title!r} targets={len(peers)} region={src_region}"
            )
            btn_copy_region.setText(f"✓ Copiado a {len(peers)} réplicas")
            QTimer.singleShot(3000, lambda: btn_copy_region.setText("Copiar región a todas"))

        btn_copy_region.clicked.connect(_copy_region_to_all)

        # --- Live-apply dispatcher: broadcasts non-X/Y changes to all overlays when checkbox is on ---
        _syncing = [False]

        def _on_layout_change(key, value):
            """Broadcast a layout setting to all overlays when 'apply to all' is active. Never copies X/Y."""
            if _syncing[0] or not chk_lp_all.isChecked():
                return
            if key in ('x', 'y'):
                return
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            peers = [ov for ov in list(_OVERLAY_REGISTRY) if ov is not self._ov]
            if not peers:
                return
            _syncing[0] = True
            try:
                for peer in peers:
                    try:
                        if key == 'w':
                            peer.setGeometry(peer.x(), peer.y(), value, peer.height())
                            peer._ov_cfg['w'] = value
                            peer._schedule_autosave()
                        elif key == 'h':
                            peer.setGeometry(peer.x(), peer.y(), peer.width(), value)
                            peer._ov_cfg['h'] = value
                            peer._schedule_autosave()
                        elif key == 'fps':
                            peer._set_fps(value)
                        elif key == 'maintain_aspect':
                            peer._ov_cfg['maintain_aspect'] = value
                            peer._schedule_autosave()
                        elif key == 'snap_x':
                            peer._ov_cfg['snap_x'] = value
                            peer._schedule_autosave()
                        elif key == 'snap_y':
                            peer._ov_cfg['snap_y'] = value
                            peer._schedule_autosave()
                    except Exception as e:
                        logger.error(f"[LIVE LAYOUT APPLY] error for {peer._title!r}: {e}")
            finally:
                _syncing[0] = False
            logger.info(f"[LIVE LAYOUT APPLY] key={key} value={value} "
                        f"apply_to_all=True overlays={len(peers)+1} exclude_xy=True")

        # Store broadcaster so _on_overlay_geometry_changed can call it for manual resizes
        self._layout_change_broadcaster = _on_layout_change

        # --- FPS ---
        _section(lay, "CAPTURA")

        cmb_fps = QComboBox()
        cmb_fps.addItems(['1', '5', '10', '15', '30', '60', '120'])
        fps_now = str(getattr(self._ov._thread, '_fps', 30) if hasattr(self._ov, '_thread') else 30)
        if cmb_fps.findText(fps_now) >= 0:
            cmb_fps.setCurrentText(fps_now)
        def _on_fps_changed(v_str):
            fps_v = int(v_str)
            self._ov._set_fps(fps_v)
            _on_layout_change('fps', fps_v)
        cmb_fps.currentTextChanged.connect(_on_fps_changed)
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
        def _on_w_changed(v):
            self._resize_from_spinbox = True
            self._ov.resize(v, self._ov.height())
            self._resize_from_spinbox = False
            _on_layout_change('w', v)
        def _on_h_changed(v):
            self._resize_from_spinbox = True
            self._ov.resize(self._ov.width(), v)
            self._resize_from_spinbox = False
            _on_layout_change('h', v)
        sp_w.valueChanged.connect(_on_w_changed)
        sp_h.valueChanged.connect(_on_h_changed)
        
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
        def _on_ma_toggled(v):
            self._set('maintain_aspect', v)
            self._ov.update()
            _on_layout_change('maintain_aspect', v)
        chk_ma.toggled.connect(_on_ma_toggled)
        lay.addWidget(chk_ma)

        _RESET_W = 150
        _RESET_H = 150

        def _reset_one_position(ov):
            try:
                from PySide6.QtWidgets import QApplication
            except ImportError:
                from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.availableGeometry()
                new_x = sg.x() + (sg.width() - _RESET_W) // 2
                new_y = sg.y() + (sg.height() - _RESET_H) // 2
            else:
                new_x, new_y = 400, 300
            ov.setGeometry(new_x, new_y, _RESET_W, _RESET_H)
            ov._schedule_autosave()
            logger.debug(f"[REPLICATOR RESET] Resetting one replica to default position and 150x150: title={ov._title!r}")

        def _reset_position():
            self._resize_from_spinbox = True
            try:
                if chk_lp_all.isChecked():
                    from overlay.replication_overlay import _OVERLAY_REGISTRY
                    targets = list(_OVERLAY_REGISTRY)
                    for ov in targets:
                        _reset_one_position(ov)
                    logger.info(f"[REPLICATOR RESET] apply_to_all enabled, resetting {len(targets)} replicas to default position and 150x150")
                else:
                    _reset_one_position(self._ov)
                    logger.info(f"[REPLICATOR RESET] Resetting one replica to default position and 150x150")
            finally:
                self._resize_from_spinbox = False

        btn_reset = QPushButton("Resetear posicion")
        btn_reset.clicked.connect(_reset_position)
        row_btns = QHBoxLayout()
        row_btns.addWidget(btn_reset)
        row_btns.addStretch()
        lay.addLayout(row_btns)

        # --- Snap ---
        _section(lay, "SNAP A CUADRICULA")

        chk_snap = QCheckBox("Alinear a cuadricula al mover (ALT para omitir)")
        chk_snap.setChecked(bool(self._cfg('snap_enabled')))

        def _snap_toggled(v):
            from overlay.replication_overlay import _OVERLAY_REGISTRY
            ovs = list(_OVERLAY_REGISTRY)
            for ov in ovs:
                try:
                    ov._ov_cfg['snap_enabled'] = v
                    ov._schedule_autosave()
                except Exception:
                    pass
            logger.info(f"[LAYOUT SNAP] enabled={v} overlays={len(ovs)}")

        chk_snap.toggled.connect(_snap_toggled)
        lay.addWidget(chk_snap)

        sp_gx = QSpinBox(); sp_gx.setRange(1, 200); sp_gx.setValue(int(self._cfg('snap_x') or 20))
        sp_gy = QSpinBox(); sp_gy.setRange(1, 200); sp_gy.setValue(int(self._cfg('snap_y') or 20))
        def _on_gx_changed(v):
            self._set('snap_x', v)
            _on_layout_change('snap_x', v)
        def _on_gy_changed(v):
            self._set('snap_y', v)
            _on_layout_change('snap_y', v)
        sp_gx.valueChanged.connect(_on_gx_changed)
        sp_gy.valueChanged.connect(_on_gy_changed)
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

        sp_tx = QSpinBox(); sp_tx.setRange(-2000, 2000); sp_tx.setValue(int(self._cfg('label_text_x') or 0))
        sp_tx.valueChanged.connect(lambda v: (self._set('label_text_x', v), self._ov.update()))
        sp_tx.editingFinished.connect(lambda: (self._set('label_text_x', sp_tx.value()), self._ov.update()))
        _row(lay, "Texto X:", sp_tx)

        sp_ty = QSpinBox(); sp_ty.setRange(-2000, 2000); sp_ty.setValue(int(self._cfg('label_text_y') or 0))
        sp_ty.valueChanged.connect(lambda v: (self._set('label_text_y', v), self._ov.update()))
        sp_ty.editingFinished.connect(lambda: (self._set('label_text_y', sp_ty.value()), self._ov.update()))
        _row(lay, "Texto Y:", sp_ty)

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

        _shapes = ['square', 'rounded', 'pill', 'diamond']
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
        
        # Botones de orden — objectName + setStyleSheet directo para máxima garantía
        _rb_style = (
            "QPushButton { background:#1e293b; border:1px solid #334155; color:#94a3b8;"
            " font-size:18px; font-weight:bold; border-radius:5px; }"
            " QPushButton:hover { background:#1e3a4a; border-color:#00c8ff; color:#00c8ff; }"
            " QPushButton:pressed { background:#0f172a; border-color:#00c8ff; }"
        )
        btn_lay = QVBoxLayout()
        btn_up = QPushButton("↑")
        btn_up.setObjectName("reorderUp")
        btn_up.setFixedSize(30, 44)
        btn_up.setToolTip("Subir cuenta")
        btn_up.setStyleSheet(_rb_style)

        btn_down = QPushButton("↓")
        btn_down.setObjectName("reorderDown")
        btn_down.setFixedSize(30, 44)
        btn_down.setToolTip("Bajar cuenta")
        btn_down.setStyleSheet(_rb_style)
        
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
