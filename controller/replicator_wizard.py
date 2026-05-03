import logging
import sys
import ctypes
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, QStackedWidget,
    QComboBox, QSpinBox, QGridLayout, QLineEdit, QApplication
)

# Configurar logger
logger = logging.getLogger('eve.replicator_wizard')
from utils.i18n import t
from overlay.replicator_hotkeys import update_hotkey_cache, register_hotkeys, unregister_hotkeys

class ReplicatorWizard:
    """
    Controlador del Asistente del Replicador 2.0.
    Unificado en una sola pantalla para selección de ventanas, región y FPS.
    """
    def __init__(self, W, C, G, cfg, cfg_mod, lang='es', suite_win=None, callback=None):
        self._W = W
        self._C = C
        self._G = G
        self._cfg = cfg
        self._cfg_mod = cfg_mod
        self._lang = lang
        self._suite_win = suite_win
        self._callback = callback
        
        self._windows_cache = []
        self._custom_cards = []
        self._drag_pos = None
        
        # UI Components
        self.dlg = None
        self._setup_ui()

    def _reassert_topmost(self):
        try:
            hwnd = int(self.dlg.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception: pass
        
    def _setup_ui(self):
        W, C = self._W, self._C
        self.dlg = QDialog()
        self.dlg.setWindowTitle("EVE iT")
        self.dlg.setMinimumSize(420, 480)
        
        flags = (Qt.WindowType.FramelessWindowHint | 
                 Qt.WindowType.WindowStaysOnTopHint | 
                 Qt.WindowType.Tool)
        self.dlg.setWindowFlags(flags)

        # [NUEVO] Refuerzo topmost unificado
        from overlay.dialog_utils import make_replicator_dialog_topmost, REPLICATOR_STYLE
        make_replicator_dialog_topmost(self.dlg)

        self._top_timer = QTimer(self.dlg)
        self._top_timer.timeout.connect(self._reassert_topmost)
        self._top_timer.start(2000)
        
        self.dlg.setStyleSheet(REPLICATOR_STYLE)

        main_lay = QVBoxLayout(self.dlg)
        main_lay.setContentsMargins(0,0,0,0); main_lay.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(30); hdr.setStyleSheet("background: #000; border-bottom: 1px solid #1a2533;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10,0,10,0)
        hl.addWidget(QLabel("🪟"))
        title_lbl = QLabel("REPLICADOR"); title_lbl.setStyleSheet("color: #00c8ff; font-weight: bold; font-size: 11px;")
        hl.addWidget(title_lbl); hl.addStretch()
        
        self.step_lbl = QLabel("ASISTENTE"); self.step_lbl.setStyleSheet("color: #405060; font-weight: bold;")
        hl.addWidget(self.step_lbl)
        
        btn_close = QPushButton("\u00d7"); btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("QPushButton{background:rgba(255,50,50,0.1);border-color:rgba(255,50,50,0.3);color:#ff6666;}QPushButton:hover{background:rgba(255,50,50,0.3);}")
        btn_close.clicked.connect(self.dlg.reject); hl.addWidget(btn_close)
        main_lay.addWidget(hdr)
        
        # Drag logic
        def mousePressEvent(event):
            if event.button() == Qt.LeftButton: self._drag_pos = event.globalPosition().toPoint()
        def mouseMoveEvent(event):
            if event.buttons() & Qt.LeftButton and self._drag_pos:
                gpos = event.globalPosition().toPoint()
                self.dlg.move(self.dlg.pos() + gpos - self._drag_pos)
                self._drag_pos = gpos
        hdr.mousePressEvent = mousePressEvent; hdr.mouseMoveEvent = mouseMoveEvent; hdr.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)

        # Content
        p1 = QWidget(); l1 = QVBoxLayout(p1); l1.setContentsMargins(20,15,20,15); l1.setSpacing(10)
        self.lbl_step1_title = QLabel(t('repl_p1_title', self._lang))
        self.lbl_step1_title.setStyleSheet("color: #00c8ff; font-size: 13px; font-weight: bold;")
        l1.addWidget(self.lbl_step1_title)
        
        self.win_list = QListWidget()
        self.win_list.setDragEnabled(True); self.win_list.setAcceptDrops(True); self.win_list.setDropIndicatorShown(True)
        self.win_list.setDragDropMode(QListWidget.InternalMove)
        l1.addWidget(self.win_list)
        
        btn_row = QHBoxLayout()
        self.btn_all = QPushButton("Todos"); btn_row.addWidget(self.btn_all)
        self.btn_none = QPushButton("Ninguno"); btn_row.addWidget(self.btn_none)
        self.btn_refresh = QPushButton("Refrescar"); btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch(); l1.addLayout(btn_row)

        # Region & FPS Config (Merged)
        conf_box = QWidget()
        conf_box.setStyleSheet("background: rgba(0,200,255,0.03); border: 1px solid rgba(0,200,255,0.1); border-radius: 6px;")
        conf_lay = QVBoxLayout(conf_box); conf_lay.setContentsMargins(15, 12, 15, 12); conf_lay.setSpacing(8)

        # Profile Row
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Perfil:"))
        self.prof_combo = QComboBox(); self.prof_combo.setMinimumWidth(120); prof_row.addWidget(self.prof_combo)
        btn_p_add = QPushButton("+"); btn_p_add.setFixedSize(24,24); prof_row.addWidget(btn_p_add)
        btn_p_del = QPushButton("-"); btn_p_del.setFixedSize(24,24); prof_row.addWidget(btn_p_del)
        
        prof_row.addSpacing(15); prof_row.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox(); self.fps_combo.addItems(["5", "10", "15", "20", "30", "60", "120"])
        self.fps_combo.setCurrentText(str(self._cfg.get('global_fps', 30)))
        self.fps_combo.setFixedWidth(50); prof_row.addWidget(self.fps_combo)
        prof_row.addStretch(); conf_lay.addLayout(prof_row)

        # Region Numeric Grid
        reg_grid = QGridLayout(); reg_grid.setSpacing(6)
        for i, k in enumerate(['x', 'y', 'w', 'h']):
            lbl = QLabel(f"{k.upper()}:")
            sp = QSpinBox(); sp.setRange(0, 4096); sp.setFixedWidth(65)
            setattr(self, f"sp_{k}", sp)
            reg_grid.addWidget(lbl, 0, i*2)
            reg_grid.addWidget(sp, 0, i*2 + 1)
            sp.valueChanged.connect(self._sync_to_cfg)
        conf_lay.addLayout(reg_grid)

        # Region Select Button
        self.btn_visual = QPushButton("SELECCIONAR REGIÓN")
        self.btn_visual.setMinimumHeight(35); self.btn_visual.setObjectName("primary")
        conf_lay.addWidget(self.btn_visual)
        l1.addWidget(conf_box)

        # Footer
        footer = QWidget(); footer.setFixedHeight(50); footer.setStyleSheet("background: #040810; border-top: 1px solid #1a2533;")
        fl = QHBoxLayout(footer); fl.setContentsMargins(20,0,20,0)
        self.btn_back = QPushButton("CERRAR"); fl.addWidget(self.btn_back)
        fl.addStretch()
        self.btn_next = QPushButton("LANZAR RÉPLICAS"); self.btn_next.setObjectName("primary"); self.btn_next.setMinimumHeight(32); fl.addWidget(self.btn_next)
        
        main_lay.addWidget(p1)
        main_lay.addWidget(footer)

        # Connections
        self.btn_refresh.clicked.connect(self._refresh_windows)
        self.btn_visual.clicked.connect(self._on_visual_select)
        self.prof_combo.currentIndexChanged.connect(self._on_profile_change)
        self.fps_combo.currentIndexChanged.connect(self._sync_to_cfg)
        btn_p_add.clicked.connect(self._on_profile_add); btn_p_del.clicked.connect(self._on_profile_del)
        self.btn_all.clicked.connect(lambda: [self._set_checked_helper(c, True) for c in self._custom_cards])
        self.btn_none.clicked.connect(lambda: [self._set_checked_helper(c, False) for c in self._custom_cards])
        self.btn_next.clicked.connect(self._go_next)
        self.btn_back.clicked.connect(self.dlg.reject)
        
        self._refresh_windows()
        self._load_profiles()
        self._update_visual_button_state()
        self._load_position()

    def _update_visual_button_state(self):
        is_valid = self.sp_w.value() > 1 and self.sp_h.value() > 1
        if is_valid:
            self.btn_visual.setStyleSheet("QPushButton#primary { background: rgba(0,255,100,0.15); border: 1px solid rgba(0,255,100,0.4); color: #00ff64; } QPushButton#primary:hover { background: rgba(0,255,100,0.3); }")
            self.btn_visual.setText("REGIÓN SELECCIONADA ✓")
        else:
            self.btn_visual.setStyleSheet("QPushButton#primary { background: rgba(255,50,50,0.15); border: 1px solid rgba(255,50,50,0.4); color: #ff6666; } QPushButton#primary:hover { background: rgba(255,50,50,0.3); }")
            self.btn_visual.setText("SELECCIONAR REGIÓN")

    def _sync_to_cfg(self):
        self._cfg['region'] = self._get_current_relative_reg()
        self._cfg['global_fps'] = int(self.fps_combo.currentText())
        self._update_visual_button_state()

    def _get_current_relative_reg(self):
        return {
            'x': self.sp_x.value() / 1920.0, 'y': self.sp_y.value() / 1080.0,
            'w': self.sp_w.value() / 1920.0, 'h': self.sp_h.value() / 1080.0
        }

    def _on_visual_select(self):
        try:
            if self.win_list.count() > 0:
                first_it = self.win_list.item(0)
                widget = self.win_list.itemWidget(first_it)
                if widget:
                    chk = widget.findChild(QLabel)
                    anchor_title = chk.property("win_title")
                    from overlay.win32_capture import resolve_eve_window_handle
                    hwnd = resolve_eve_window_handle(anchor_title)
                    if hwnd and ctypes.windll.user32.IsWindow(hwnd):
                        ctypes.windll.user32.ShowWindow(hwnd, 9)
                        ctypes.windll.user32.BringWindowToTop(hwnd)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        self._anchor_hwnd_ref = hwnd
        except Exception: pass

        self.dlg.hide()
        if self._suite_win: self._suite_win.hide()
        from overlay.region_selector import select_region
        ref_hwnd = getattr(self, '_anchor_hwnd_ref', None)
        if not ref_hwnd and self._windows_cache: ref_hwnd = self._windows_cache[0]['hwnd']
        reg = select_region({'hwnd': ref_hwnd} if ref_hwnd else {'rect': (0,0,1920,1080)})
        if self._suite_win: self._suite_win.show()
        if reg:
            self.sp_x.setValue(int(reg['x'] * 1920)); self.sp_y.setValue(int(reg['y'] * 1080))
            self.sp_w.setValue(int(reg['w'] * 1920)); self.sp_h.setValue(int(reg['h'] * 1080))
            self._sync_to_cfg()
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()

    def _refresh_windows(self):
        self.win_list.clear(); self._custom_cards = []
        from overlay.win32_capture import find_eve_windows
        self._windows_cache = find_eve_windows()
        self.win_list.setStyleSheet("QListWidget { background: transparent; border: none; outline: none; } QListWidget::item { background: transparent; padding: 0; margin: 2px 0; }")

        def set_custom_chk(lbl, state):
            lbl.setProperty("is_checked", state)
            if state:
                lbl.setText("✔"); lbl.setStyleSheet("border: 1px solid #00ff9d; border-radius: 3px; background: rgba(0,255,157,0.15); color: #00ff9d; font-weight: bold; font-size: 11px;")
            else:
                lbl.setText(""); lbl.setStyleSheet("border: 1px solid rgba(0,180,255,0.3); border-radius: 3px; background: transparent;")
        self._set_checked_helper = set_custom_chk
        if hasattr(self, 'lbl_step1_title'): self.lbl_step1_title.setText(f"{t('repl_p1_title', self._lang)} ({len(self._windows_cache)})")

        for w in self._windows_cache:
            it = QListWidgetItem()
            it.setData(256, w['title'])
            self.win_list.addItem(it)
            card = QWidget(); card.setObjectName("Card")
            lay = QHBoxLayout(card); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(10)
            grip = QLabel("\u283f"); grip.setStyleSheet("color: rgba(0,200,255,0.2); font-size: 14px;"); grip.setFixedWidth(12)
            grip.setAttribute(Qt.WA_TransparentForMouseEvents, True); lay.addWidget(grip)
            chk = QLabel(); chk.setFixedSize(14, 14); chk.setProperty("win_title", w['title'])
            set_custom_chk(chk, False); self._custom_cards.append(chk)
            lbl_title = QLabel(w['title']); lbl_title.setStyleSheet("color: #e1e9f5; font-size: 11px; font-weight: bold;")
            lbl_res = QLabel(f"{w['size'][0]}x{w['size'][1]}"); lbl_res.setStyleSheet("color: rgba(0,200,255,0.4); font-size: 9px;")
            card.mouseReleaseEvent = lambda e, _chk=chk: set_custom_chk(_chk, not _chk.property("is_checked"))
            lay.addWidget(chk); lay.addWidget(lbl_title); lay.addStretch(); lay.addWidget(lbl_res)
            it.setSizeHint(card.sizeHint()); self.win_list.setItemWidget(it, card)

    def _sync_cache_from_ui(self):
        new_cache = []
        for i in range(self.win_list.count()):
            it = self.win_list.item(i); title = it.data(256)
            orig_w = next((w for w in self._windows_cache if w['title'] == title), None)
            if orig_w: new_cache.append(orig_w)
        if new_cache: self._windows_cache = new_cache; self._refresh_list_ui_only()

    def _refresh_list_ui_only(self):
        selected_titles = [c.property("win_title") for c in self._custom_cards if c.property("is_checked")]
        self.win_list.clear(); self._custom_cards = []
        for w in self._windows_cache:
            it = QListWidgetItem(); it.setData(256, w['title']); self.win_list.addItem(it)
            card = QWidget(); card.setObjectName("Card")
            lay = QHBoxLayout(card); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(10)
            grip = QLabel("\u283f"); grip.setStyleSheet("color: rgba(0,200,255,0.2); font-size: 14px;"); lay.addWidget(grip)
            chk = QLabel(); chk.setFixedSize(14, 14); chk.setProperty("win_title", w['title'])
            self._set_checked_helper(chk, w['title'] in selected_titles); self._custom_cards.append(chk)
            lbl_title = QLabel(w['title']); lbl_title.setStyleSheet("color: #e1e9f5; font-size: 11px; font-weight: bold;")
            card.mouseReleaseEvent = lambda e, _chk=chk: self._set_checked_helper(_chk, not _chk.property("is_checked"))
            lay.addWidget(chk); lay.addWidget(lbl_title); lay.addStretch()
            it.setSizeHint(card.sizeHint()); self.win_list.setItemWidget(it, card)

    def _load_profiles(self):
        self.prof_combo.clear()
        for name in self._cfg.get('regions', {}).keys(): self.prof_combo.addItem(name)
        curr = self._cfg.get('global', {}).get('current_profile', 'Default')
        idx = self.prof_combo.findText(curr)
        if idx >= 0: self.prof_combo.setCurrentIndex(idx)

    def _on_profile_change(self):
        name = self.prof_combo.currentText()
        if not name: return
        reg = self._cfg.get('regions', {}).get(name)
        if reg:
            self.sp_x.setValue(int(reg.get('x',0) * 1920)); self.sp_y.setValue(int(reg.get('y',0) * 1080))
            self.sp_w.setValue(int(reg.get('w',0.1) * 1920)); self.sp_h.setValue(int(reg.get('h',0.1) * 1080))

    def _on_profile_add(self):
        text, ok = self._show_custom_dialog("Nuevo Perfil", "Nombre:", is_input=True)
        if ok and text:
            self._cfg.setdefault('regions', {})[text] = self._get_current_relative_reg()
            self._save_and_refresh_profiles(text)

    def _on_profile_del(self):
        name = self.prof_combo.currentText()
        if name and name != 'Default':
            del self._cfg['regions'][name]; self._save_and_refresh_profiles('Default')

    def _save_and_refresh_profiles(self, select_name):
        self._cfg_mod.save_config(self._cfg); self._load_profiles()
        idx = self.prof_combo.findText(select_name)
        if idx >= 0: self.prof_combo.setCurrentIndex(idx)

    def _save_position(self):
        self._cfg.setdefault('sizes', {})['wizard_pos'] = {'x': self.dlg.x(), 'y': self.dlg.y()}
        self._cfg_mod.save_config(self._cfg)
        
    def _load_position(self):
        pos = self._cfg.get('sizes', {}).get('wizard_pos')
        if pos: self.dlg.move(pos['x'], pos['y'])

    def _go_next(self):
        sel = [c.property("win_title") for c in self._custom_cards if c.property("is_checked")]
        if not sel: self._show_custom_dialog("Aviso", "Selecciona al menos una ventana."); return
        if self.sp_w.value() <= 1 or self.sp_h.value() <= 1: self._show_custom_dialog("Aviso", "Selecciona una región válida."); return
        self._cfg['selected_windows'] = sel; self._cfg_mod.save_config(self._cfg); self.dlg.accept()
        if not self._callback: self._launch_direct()
        else: self._callback(self._cfg, self._cfg_mod)

    def _launch_direct(self):
        try:
            from overlay.win32_capture import find_eve_windows
            from overlay.replication_overlay import ReplicationOverlay
            from overlay import replicator_config as cfg_lib
            
            titles = self._cfg.get('selected_windows', [])
            region = self._cfg.get('region', {'x':0, 'y':0, 'w':0.1, 'h':0.1})
            current = find_eve_windows()
            handles = {w['title']: w['hwnd'] for w in current}
            self._overlays_refs = []
            
            for i, title in enumerate(titles):
                h = handles.get(title)
                if not h: continue
                ov_region = region.copy()
                fps = self._cfg.get('global_fps', 30)
                self._cfg.setdefault('overlays', {}).setdefault(title, {})['fps'] = fps
                ov = ReplicationOverlay(title=title, hwnd=h, region_rel=ov_region, cfg=self._cfg, 
                                        save_callback=lambda *a: cfg_lib.save_overlay_state(self._cfg, *a))
                
                try:
                    from overlay.replicator_config import get_active_layout_profile
                    from overlay.win32_capture import get_window_size
                    _, lp = get_active_layout_profile(self._cfg)
                    init_w = int(lp.get('w', 280))
                    ev_w, ev_h = get_window_size(h)
                    rw = ov_region.get('w', 0.3) * ev_w
                    rh = ov_region.get('h', 0.2) * ev_h
                    init_h = max(64, int(init_w / (rw / rh))) if rh > 0 else int(lp.get('h', 200))
                    screen = QApplication.primaryScreen().geometry()
                    ov.resize(init_w, init_h)
                    ov.move(screen.x() + (screen.width()-init_w)//2 + i*20, screen.y() + (screen.height()-init_h)//2 + i*20)
                except Exception:
                    ov.resize(280, 200); ov.move(400+i*20, 300+i*20)
                
                ov.show(); self._overlays_refs.append(ov)
            update_hotkey_cache(titles)
            register_hotkeys(self._cfg, cycle_titles_getter=lambda: self._cfg.get('selected_windows', []))
        except Exception as e: logger.error(f"Error en lanzamiento directo: {e}")

    def _show_custom_dialog(self, title, msg, is_input=False):
        d = QDialog(self.dlg); d.setWindowTitle(title); d.setFixedSize(320, 150)
        d.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        d.setStyleSheet("QDialog { background: #000; border: 1px solid #00c8ff; color: #fff; }")
        lay = QVBoxLayout(d); lay.setContentsMargins(15, 15, 15, 15)
        lay.addWidget(QLabel(msg))
        input_f = None
        if is_input:
            input_f = QLineEdit(); input_f.setStyleSheet("background:#0d1626; border:1px solid #1a2533; color:#00c8ff;"); lay.addWidget(input_f)
        btns = QHBoxLayout(); btns.addStretch()
        if is_input:
            bc = QPushButton("Cancelar"); bc.clicked.connect(d.reject); btns.addWidget(bc)
        bok = QPushButton("OK"); bok.setObjectName("primary"); bok.clicked.connect(d.accept); btns.addWidget(bok)
        btns.addStretch(); lay.addLayout(btns)
        res = d.exec()
        if is_input: return input_f.text(), res == QDialog.Accepted
        return res

    def show(self):
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()

    def show_for_region_change(self, overlay):
        """Muestra el wizard enfocándolo para cambio de región desde una réplica."""
        self.show()
        # Opcional: cargar datos del overlay si fuera necesario
        logger.info(f"Wizard enfocado para cambio de región: {overlay._title}")

    def _animate_minimize(self, widget): widget.hide() # Simplified
    def _animate_restore(self, widget): widget.show() # Simplified
    def retranslate_ui(self, lang): pass # Stub for now to keep it clean
