import logging
import sys
from pathlib import Path

# Configurar logger
logger = logging.getLogger('eve.replicator_wizard')
from utils.i18n import t

class ReplicatorWizard:
    """
    Controlador del Asistente del Replicador 2.0.
    Ahora implementado como una clase limpia que gestiona un QDialog.
    """
    def __init__(self, W, C, G, cfg, cfg_mod, lang='es', callback=None):
        self._W = W
        self._C = C
        self._G = G
        self._cfg = cfg
        self._cfg_mod = cfg_mod
        self._lang = lang
        self._callback = callback
        
        self._windows_cache = []
        self._current_rect = {'x': 0, 'y': 0, 'w': 100, 'h': 100} # Píxeles reales de referencia
        self._drag_pos = None
        
        # UI Components
        self.dlg = None
        self.hub = None # Referencia al HUB táctico
        self._setup_ui()

    def _reassert_topmost(self):
        try:
            import ctypes
            hwnd = int(self.dlg.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except: pass
        
    def _setup_ui_content(self): # Helper or just continue in _setup_ui
        pass

    def _setup_ui(self):
        W, C, G = self._W, self._C, self._G
        self.dlg = W.QDialog()
        self.dlg.setWindowTitle("EVE iT")
        self.dlg.setMinimumSize(400, 360)
        
        # Tool & Frameless & TopMost Window Hints
        flags = (self._C.Qt.WindowType.FramelessWindowHint | 
                 self._C.Qt.WindowType.WindowStaysOnTopHint | 
                 self._C.Qt.WindowType.Tool) \
                if hasattr(self._C.Qt, 'WindowType') else \
                (self._C.Qt.FramelessWindowHint | 
                 self._C.Qt.WindowStaysOnTopHint | 
                 self._C.Qt.Tool)
        
        self.dlg.setWindowFlags(flags)

        # Forzar TopMost via Win32 API inmediatamente
        try:
            import ctypes
            hwnd = int(self.dlg.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        except: pass

        # Re-afirmar cada 2 segundos mientras esté abierto
        self._top_timer = self._C.QTimer(self.dlg)
        self._top_timer.timeout.connect(self._reassert_topmost)
        self._top_timer.start(2000)
        
        # Estilo Global (Neon Dark - Fondo negro puro)
        self.dlg.setStyleSheet("""
            QDialog { background: #000000; border: 1px solid rgba(0,180,255,0.3); color: #e1e9f5; font-family: 'Segoe UI', sans-serif; }
            QLabel { color: #a0b0c0; font-size: 11px; }
            QLabel#title { color: #00c8ff; font-size: 16px; font-weight: bold; padding-bottom: 5px; }
            QPushButton { 
                background: rgba(0,180,255,0.1); border: 1px solid rgba(0,180,255,0.3);
                border-radius: 4px; color: #00c8ff; padding: 6px 15px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(0,180,255,0.2); border-color: #00c8ff; }
            QPushButton:pressed { background: rgba(0,180,255,0.3); }
            QPushButton#primary { background: rgba(0,200,255,0.2); border-color: #00e0ff; color: #00ffff; }
            QPushButton#primary:hover { background: rgba(0,200,255,0.4); }
            QListWidget { background: #040810; border: 1px solid #1a2533; border-radius: 5px; color: #e1e9f5; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #0d1626; }
            QListWidget::item:selected { background: rgba(0,180,255,0.15); color: #00c8ff; }
            QSpinBox, QComboBox { 
                background: #0d1626; border: 1px solid #1a2533; border-radius: 3px; 
                color: #00c8ff; padding: 4px; 
            }
        """)

        main_lay = W.QVBoxLayout(self.dlg)
        main_lay.setContentsMargins(0,0,0,0); main_lay.setSpacing(0)

        # Header Custom
        hdr = W.QWidget(); hdr.setFixedHeight(28); hdr.setStyleSheet("background: #000000; border-bottom: 1px solid #1a2533;")
        hl = W.QHBoxLayout(hdr); hl.setContentsMargins(10,0,10,0)
        
        icon_lbl = W.QLabel("🪟")
        hl.addWidget(icon_lbl)
        
        title_lbl = W.QLabel(""); title_lbl.setStyleSheet("color: rgba(0,200,255,0.8); font-size: 10px; font-weight: normal;")
        hl.addWidget(title_lbl)
        
        hl.addStretch()
        self.step_lbl = W.QLabel("Paso 1 / 3"); self.step_lbl.setStyleSheet("color: #405060; font-weight: bold;")
        hl.addWidget(self.step_lbl)
        
        # Botones Min / Close (Estandarizados con Translator)
        btn_min = W.QPushButton("\u2212")
        btn_min.setFixedSize(18, 18)
        btn_min.setStyleSheet("QPushButton{background:rgba(0,180,255,0.15);border:1px solid rgba(0,180,255,0.4);border-radius:3px;color:#00c8ff;font-size:10px;padding:0;margin:0;font-weight:normal;}QPushButton:hover{background:rgba(0,180,255,0.35);}")
        btn_min.clicked.connect(lambda: self._animate_minimize(self.dlg))
        hl.addWidget(btn_min)
        
        btn_close = W.QPushButton("\u00d7")
        btn_close.setFixedSize(18, 18)
        btn_close.setStyleSheet("QPushButton{background:rgba(255,50,50,0.15);border:1px solid rgba(255,50,50,0.4);border-radius:3px;color:#ff6666;font-size:10px;padding:0;margin:0;font-weight:normal;}QPushButton:hover{background:rgba(255,50,50,0.35);}")
        btn_close.clicked.connect(self.dlg.reject)
        hl.addWidget(btn_close)
        
        main_lay.addWidget(hdr)
        
        # Lógica de arrastre
        def mousePressEvent(event):
            left = C.Qt.MouseButton.LeftButton if hasattr(C.Qt, 'MouseButton') else C.Qt.LeftButton
            if event.button() == left:
                self._drag_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
        
        def mouseMoveEvent(event):
            left = C.Qt.MouseButton.LeftButton if hasattr(C.Qt, 'MouseButton') else C.Qt.LeftButton
            if event.buttons() & left and self._drag_pos:
                gpos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self.dlg.move(self.dlg.pos() + gpos - self._drag_pos)
                self._drag_pos = gpos
                
        def mouseReleaseEvent(event):
            self._drag_pos = None
            self._save_position()

        hdr.mousePressEvent = mousePressEvent
        hdr.mouseMoveEvent = mouseMoveEvent
        hdr.mouseReleaseEvent = mouseReleaseEvent
        
        # Main Title (Step 1 visual title)
        title_bar = W.QWidget(); title_bar.setFixedHeight(35); title_bar.setStyleSheet("background: transparent;")
        tbl = W.QHBoxLayout(title_bar); tbl.setContentsMargins(20,5,20,0)
        title_main = W.QLabel(""); title_main.setStyleSheet("color: rgba(0,200,255,0.7); font-size: 14px; font-weight: bold;"); tbl.addWidget(title_main)
        tbl.addStretch()
        main_lay.addWidget(title_bar)


        # Stack logic
        self.stack = W.QStackedWidget(); main_lay.addWidget(self.stack)

        # STEP 1: Selección de Ventanas
        self._setup_step1()
        # STEP 2: Gestión de Regiones
        self._setup_step2()
        # STEP 3 ELIMINADO

        # Bottom Bar
        footer = W.QWidget(); footer.setFixedHeight(45); footer.setStyleSheet("background: #040810; border-top: 1px solid #1a2533;")
        fl = W.QHBoxLayout(footer); fl.setContentsMargins(20,0,20,0)
        self.btn_back = W.QPushButton("CERRAR"); fl.addWidget(self.btn_back)
        fl.addStretch()
        self.btn_next = W.QPushButton("SIGUIENTE"); fl.addWidget(self.btn_next)
        main_lay.addWidget(footer)

        # Connections
        self.btn_next.clicked.connect(self._go_next)
        self.btn_back.clicked.connect(self._go_back)
        
        # Re-translate initial
        self.retranslate_ui(self._lang)
        
        # Load Position
        self._load_position()

    def retranslate_ui(self, lang: str):
        self._lang = lang
        from utils.i18n import t
        idx = self.stack.currentIndex()
        if idx == 0:
            self.btn_back.setText(t('gui_btn_close', lang))
        else:
            self.btn_back.setText(t('repl_btn_back', lang))
        if idx == 1:
            self.btn_next.setText(t('repl_btn_launch', lang))
        else:
            self.btn_next.setText(t('repl_btn_next', lang))
            
        if hasattr(self, 'step_lbl'): self.step_lbl.setText(t('repl_step', lang) + f" {idx+1} / 2")
        if hasattr(self, 'lbl_step1_title'): self.lbl_step1_title.setText(t('repl_p1_title', lang))
        if hasattr(self, 'btn_all'): self.btn_all.setText(t('repl_btn_all', lang))
        if hasattr(self, 'btn_none'): self.btn_none.setText(t('repl_btn_none', lang))
        if hasattr(self, 'btn_refresh'): self.btn_refresh.setText(t('repl_btn_refresh', lang))
        
        if hasattr(self, 'lbl_step2_title'): self.lbl_step2_title.setText(t('repl_p2_title', lang))
        if hasattr(self, 'lbl_profile'): self.lbl_profile.setText(t('repl_profile', lang))
        if hasattr(self, 'lbl_w'): self.lbl_w.setText(t('repl_width', lang))
        if hasattr(self, 'lbl_h'): self.lbl_h.setText(t('repl_height', lang))
        if hasattr(self, 'btn_visual'): self.btn_visual.setText(t('repl_btn_select', lang))
        
        if hasattr(self, 'lbl_step3_title'): self.lbl_step3_title.setText(t('repl_p3_title', lang))
        if idx == 2 and hasattr(self, 'summary_txt'):
            wins = ", ".join(self._cfg.get('selected_windows', []))
            s_out = t('repl_summary_wins', lang, wins=wins) + "\n" + t('repl_summary_reg', lang, profile=self.prof_combo.currentText())
            self.summary_txt.setText(s_out)
            
        if hasattr(self, 'hub_window') and self.hub_window:
            try: self.hub_window.retranslate_ui(lang)
            except: pass

    def _save_position(self):
        self._cfg.setdefault('sizes', {})['wizard_pos'] = {'x': self.dlg.x(), 'y': self.dlg.y()}
        self._cfg_mod.save_config(self._cfg)
        
    def _load_position(self):
        pos = self._cfg.get('sizes', {}).get('wizard_pos')
        if pos:
            self.dlg.move(pos['x'], pos['y'])

    def _setup_step1(self):
        W = self._W
        p1 = W.QWidget(); l1 = W.QVBoxLayout(p1); l1.setContentsMargins(15,10,15,10); l1.setSpacing(8)
        self.lbl_step1_title = W.QLabel(t('repl_p1_title', self._lang))
        self.lbl_step1_title.setStyleSheet("color: #00c8ff; font-weight: bold; font-size: 11px;")
        l1.addWidget(self.lbl_step1_title)
        self.win_list = W.QListWidget(); l1.addWidget(self.win_list)
        
        btn_row = W.QHBoxLayout()
        self.btn_all = W.QPushButton("Seleccionar Todos")
        self.btn_all.setStyleSheet("font-size: 9px; padding: 4px 10px;")
        btn_row.addWidget(self.btn_all)
        
        self.btn_none = W.QPushButton("Deseleccionar Todos")
        self.btn_none.setStyleSheet("QPushButton { background: rgba(255,50,50,0.08); border: 1px solid rgba(255,60,60,0.25); color: rgba(255,120,120,0.7); font-size: 9px; padding: 4px 10px; } "
                               "QPushButton:hover { background: rgba(255,50,50,0.22); border-color: #ff4444; color: #ff6666; }")
        btn_row.addWidget(self.btn_none)
        
        self.btn_refresh = W.QPushButton("Refrescar Lista")
        self.btn_refresh.setStyleSheet("font-size: 9px; padding: 4px 10px;")
        btn_row.addWidget(self.btn_refresh)
        
        btn_row.addStretch()
        l1.addLayout(btn_row)
        
        self.btn_refresh.clicked.connect(self._refresh_windows)
        def _sel_all():
            if hasattr(self, '_set_checked_helper'):
                for c in getattr(self, '_custom_cards', []): self._set_checked_helper(c, True)
        def _sel_none():
            if hasattr(self, '_set_checked_helper'):
                for c in getattr(self, '_custom_cards', []): self._set_checked_helper(c, False)
        
        self.btn_all.clicked.connect(_sel_all)
        self.btn_none.clicked.connect(_sel_none)
        
        self.stack.addWidget(p1)
        self._refresh_windows()

    def _setup_step2(self):
        W = self._W
        p2 = W.QWidget(); l2 = W.QVBoxLayout(p2); l2.setContentsMargins(15,10,15,10); l2.setSpacing(10)
        
        self.lbl_step2_title = W.QLabel("CONFIGURAR REGIÓN DE CAPTURA")
        l2.addWidget(self.lbl_step2_title)
        
        # Profile Row
        prof_row = W.QHBoxLayout()
        self.lbl_profile = W.QLabel("Perfil:")
        prof_row.addWidget(self.lbl_profile)
        self.prof_combo = W.QComboBox(); self.prof_combo.setMinimumWidth(200); prof_row.addWidget(self.prof_combo)
        btn_add = W.QPushButton("+"); btn_add.setFixedSize(30,30); prof_row.addWidget(btn_add)
        btn_del = W.QPushButton("-"); btn_del.setFixedSize(30,30); prof_row.addWidget(btn_del)
        prof_row.addStretch()
        l2.addLayout(prof_row)

        # Numeric Control Grid (Match user image)
        grid = W.QGridLayout(); grid.setSpacing(15)
        
        # X / Y
        self.lbl_x = W.QLabel("X:"); grid.addWidget(self.lbl_x, 0, 0)
        self.sp_x = W.QSpinBox(); self.sp_x.setRange(0, 10000); grid.addWidget(self.sp_x, 0, 1)
        
        self.lbl_w = W.QLabel("Anchura:"); grid.addWidget(self.lbl_w, 0, 2)
        self.sp_w = W.QSpinBox(); self.sp_w.setRange(1, 10000); grid.addWidget(self.sp_w, 0, 3)
        
        self.lbl_y = W.QLabel("Y:"); grid.addWidget(self.lbl_y, 1, 0)
        self.sp_y = W.QSpinBox(); self.sp_y.setRange(0, 10000); grid.addWidget(self.sp_y, 1, 1)
        
        self.lbl_h = W.QLabel("Altura:"); grid.addWidget(self.lbl_h, 1, 2)
        self.sp_h = W.QSpinBox(); self.sp_h.setRange(1, 10000); grid.addWidget(self.sp_h, 1, 3)
        
        l2.addLayout(grid)
        
        # Visual Selector Button
        self.btn_visual = W.QPushButton("SELECCIONAR REGIÓN EN PANTALLA")
        self.btn_visual.setMinimumHeight(45)
        self.btn_visual.setObjectName("primary")
        self.btn_visual.setStyleSheet("QPushButton#primary { background: rgba(0,200,100,0.1); border-color: rgba(0,200,100,0.3); color: #00ff9d; } QPushButton#primary:hover { background: rgba(0,200,100,0.2); }")
        l2.addWidget(self.btn_visual)
        
        l2.addStretch()
        self.stack.addWidget(p2)

        # Connections for Step 2
        self.btn_visual.clicked.connect(self._on_visual_select)
        self.prof_combo.currentIndexChanged.connect(self._on_profile_change)
        btn_add.clicked.connect(self._on_profile_add)
        btn_del.clicked.connect(self._on_profile_del)
        
        # Sync Spinboxes to internal state
        for sp in [self.sp_x, self.sp_y, self.sp_w, self.sp_h]:
            sp.valueChanged.connect(self._sync_to_cfg)

        self._load_profiles()

    def start_visual_selection(self):
        """Inicia el modo de selección visual directamente."""
        self._on_visual_select()

    def _setup_step3(self):
        W = self._W
        p3 = W.QWidget(); l3 = W.QVBoxLayout(p3); l3.setContentsMargins(25,20,25,20); l3.setSpacing(10)
        self.lbl_step3_title = W.QLabel("RESUMEN DE CONFIGURACIÓN")
        l3.addWidget(self.lbl_step3_title)
        self.summary_txt = W.QLabel("Listo para lanzar..."); self.summary_txt.setStyleSheet("color: #00ff9d; font-size: 13px;")
        l3.addWidget(self.summary_txt)
        l3.addStretch()
        self.stack.addWidget(p3)

    # --- Methods ---
    def _refresh_windows(self):
        self.win_list.clear()
        self._custom_cards = []
        from overlay.win32_capture import find_eve_windows
        self._windows_cache = find_eve_windows()
        
        self.win_list.setStyleSheet(
            "QListWidget { background: transparent; border: 1px solid rgba(0,180,255,0.1); border-radius: 6px; outline: none; padding: 4px; }"
            "QListWidget::item { background: transparent; padding: 0px; margin: 2px 0; }"
            "QListWidget::item:selected { background: transparent; }"
            "QListWidget::item:hover { background: transparent; }"
        )

        # Helper for our custom pseudo-checkboxes
        def set_custom_chk(lbl, state):
            lbl.setProperty("is_checked", state)
            if state:
                lbl.setText("✔")
                lbl.setStyleSheet("border: 1px solid #00ff9d; border-radius: 3px; background: rgba(0,255,157,0.1); color: #00ff9d; font-weight: bold; font-size: 13px; padding-bottom: 2px;")
            else:
                lbl.setText("")
                lbl.setStyleSheet("border: 1px solid rgba(0,180,255,0.5); border-radius: 3px; background: transparent; color: transparent;")
        
        self._set_checked_helper = set_custom_chk

        # Actualizar título con el conteo (Task: Ventanas EvE Detectadas (X))
        count = len(self._windows_cache)
        self.lbl_step1_title.setText(f"{t('repl_p1_title', self._lang)} ({count})")

        for w in self._windows_cache:
            it = self._W.QListWidgetItem()
            self.win_list.addItem(it)
            
            card = self._W.QWidget()
            card.setStyleSheet(
                "QWidget#Card { background: rgba(0,180,255,0.03); border: 1px solid rgba(0,180,255,0.1); border-radius: 4px; }"
                "QWidget#Card:hover { background: rgba(0,180,255,0.08); border-color: rgba(0,180,255,0.3); }"
            )
            card.setObjectName("Card")
            lay = self._W.QHBoxLayout(card)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(12)
            
            chk = self._W.QLabel()
            chk.setFixedSize(16, 16)
            AlignC = getattr(self._C.Qt, 'AlignCenter', getattr(self._C.Qt.AlignmentFlag, 'AlignCenter', 0x0084)) if hasattr(self._C, 'Qt') else 4
            chk.setAlignment(AlignC)
            chk.setProperty("win_title", w['title'])
            set_custom_chk(chk, False)
            self._custom_cards.append(chk)
            
            lbl_title = self._W.QLabel(w['title'])
            lbl_title.setStyleSheet("color: #e1e9f5; font-weight: bold; font-size: 11px;")
            
            lbl_res = self._W.QLabel(f"{w['size'][0]}x{w['size'][1]}")
            lbl_res.setStyleSheet("color: rgba(0,200,255,0.6); font-size: 10px; background: rgba(0,0,0,0.3); border-radius: 3px; padding: 2px 6px;")
            
            def _toggle(ev, _chk=chk): self._set_checked_helper(_chk, not _chk.property("is_checked"))
            card.mousePressEvent = _toggle
            
            lay.addWidget(chk); lay.addWidget(lbl_title); lay.addStretch(); lay.addWidget(lbl_res)
            
            it.setSizeHint(card.sizeHint())
            self.win_list.setItemWidget(it, card)

    def _load_profiles(self):
        self.prof_combo.clear()
        regions = self._cfg.get('regions', {})
        for name in regions.keys():
            self.prof_combo.addItem(name)
        curr = self._cfg.get('global', {}).get('current_profile', 'Default')
        idx = self.prof_combo.findText(curr)
        if idx >= 0: self.prof_combo.setCurrentIndex(idx)

    def _on_profile_change(self):
        name = self.prof_combo.currentText()
        if not name: return
        reg = self._cfg.get('regions', {}).get(name)
        if reg:
            # Note: stored as relative 0.0-1.0, convert to pixels for spinboxes
            # We'll assume a base of 1920x1080 for manual input if no ref window
            self.sp_x.setValue(int(reg.get('x',0) * 1920))
            self.sp_y.setValue(int(reg.get('y',0) * 1080))
            self.sp_w.setValue(int(reg.get('w',0.1) * 1920))
            self.sp_h.setValue(int(reg.get('h',0.1) * 1080))

    def _on_profile_add(self):
        text, ok = self._show_custom_dialog("Nuevo Perfil", "Nombre del perfil:", is_input=True)
        if ok and text:
            self._cfg.setdefault('regions', {})[text] = self._get_current_relative_reg()
            self._save_and_refresh_profiles(text)

    def _on_profile_del(self):
        name = self.prof_combo.currentText()
        if name and name != 'Default':
            del self._cfg['regions'][name]
            self._save_and_refresh_profiles('Default')

    def _save_and_refresh_profiles(self, select_name):
        self._cfg_mod.save_config(self._cfg)
        self._load_profiles()
        idx = self.prof_combo.findText(select_name)
        if idx >= 0: self.prof_combo.setCurrentIndex(idx)

    def _get_current_relative_reg(self):
        return {
            'x': self.sp_x.value() / 1920.0,
            'y': self.sp_y.value() / 1080.0,
            'w': self.sp_w.value() / 1920.0,
            'h': self.sp_h.value() / 1080.0
        }

    def _sync_to_cfg(self):
        # Update current region in cfg
        self._cfg['region'] = self._get_current_relative_reg()

    def _on_visual_select(self):
        self.dlg.hide()
        from overlay.region_selector import select_region
        # Use first selected window as reference if available
        ref = self._windows_cache[0] if self._windows_cache else {'rect': (0,0,1920,1080)}
        reg = select_region(ref)
        if reg:
            self.sp_x.setValue(int(reg['x'] * 1920))
            self.sp_y.setValue(int(reg['y'] * 1080))
            self.sp_w.setValue(int(reg['w'] * 1920))
            self.sp_h.setValue(int(reg['h'] * 1080))
            self._sync_to_cfg()
        self.dlg.show()
        self.dlg.raise_()

    def _show_custom_dialog(self, title, msg, is_input=False):
        W, C = self._W, self._C
        d = W.QDialog(self.dlg)
        d.setWindowTitle(title)
        d.setFixedSize(300, 140)
        flags = C.Qt.WindowType.FramelessWindowHint if hasattr(C.Qt, 'WindowType') else C.Qt.FramelessWindowHint
        tool_flag = C.Qt.WindowType.Tool if hasattr(C.Qt, 'WindowType') else C.Qt.Tool
        d.setWindowFlags(tool_flag | flags)
        d.setStyleSheet(self.dlg.styleSheet() + " QDialog { border: 1px solid rgba(0,200,255,0.5); }")
        
        lay = W.QVBoxLayout(d)
        lay.setContentsMargins(0, 0, 0, 0)
        
        # Header
        hdr = W.QWidget(); hdr.setFixedHeight(30)
        hdr.setStyleSheet("background: #000000; border-bottom: 1px solid #1a2533;")
        hl = W.QHBoxLayout(hdr); hl.setContentsMargins(10, 0, 10, 0)
        
        lbl_title = W.QLabel(title)
        lbl_title.setStyleSheet("color: rgba(200,230,255,0.8); font-size: 11px; font-weight: bold;")
        hl.addWidget(lbl_title); hl.addStretch()
        
        btn_close = W.QPushButton("\u00d7"); btn_close.setFixedSize(16, 16)
        btn_close.setStyleSheet("QPushButton{background:rgba(255,50,50,0.15);border:1px solid rgba(255,50,50,0.4);border-radius:3px;color:#ff6666;font-size:10px;padding:0;margin:0;}QPushButton:hover{background:rgba(255,50,50,0.35);}")
        btn_close.clicked.connect(d.reject)
        hl.addWidget(btn_close)
        lay.addWidget(hdr)
        
        # Dragging logic
        self._d_drag_pos = None
        def mp(e):
            left = C.Qt.MouseButton.LeftButton if hasattr(C.Qt, 'MouseButton') else C.Qt.LeftButton
            if e.button() == left: self._d_drag_pos = e.globalPosition().toPoint() if hasattr(e, 'globalPosition') else e.globalPos()
        def mm(e):
            left = C.Qt.MouseButton.LeftButton if hasattr(C.Qt, 'MouseButton') else C.Qt.LeftButton
            if e.buttons() & left and self._d_drag_pos:
                gpos = e.globalPosition().toPoint() if hasattr(e, 'globalPosition') else e.globalPos()
                d.move(d.pos() + gpos - self._d_drag_pos)
                self._d_drag_pos = gpos
        def mr(e): self._d_drag_pos = None
        hdr.mousePressEvent = mp; hdr.mouseMoveEvent = mm; hdr.mouseReleaseEvent = mr

        # Body
        body_lay = W.QVBoxLayout()
        body_lay.setContentsMargins(20, 15, 20, 15)
        
        body_lbl = W.QLabel(msg)
        body_lbl.setAlignment(C.Qt.AlignmentFlag.AlignCenter if hasattr(C.Qt, 'AlignmentFlag') else C.Qt.AlignCenter)
        body_lbl.setStyleSheet("color: #e1e9f5; font-size: 11px;")
        body_lbl.setWordWrap(True)
        body_lay.addWidget(body_lbl)
        
        input_field = None
        if is_input:
            input_field = W.QLineEdit()
            input_field.setStyleSheet("background: #0d1626; border: 1px solid #1a2533; border-radius: 3px; color: #00c8ff; padding: 4px;")
            body_lay.addWidget(input_field)
            
        lay.addLayout(body_lay)
        
        # Footer
        footer = W.QHBoxLayout(); footer.setContentsMargins(20, 0, 20, 15)
        footer.addStretch()
        if is_input:
            btn_cancel = W.QPushButton("Cancelar")
            btn_cancel.clicked.connect(d.reject)
            footer.addWidget(btn_cancel)
        
        btn_ok = W.QPushButton("OK")
        btn_ok.clicked.connect(d.accept)
        footer.addWidget(btn_ok)
        footer.addStretch()
        lay.addLayout(footer)
        
        res = d.exec()
        if is_input:
            return input_field.text(), res == W.QDialog.DialogCode.Accepted if hasattr(W.QDialog, 'DialogCode') else res == 1
        return res

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            sel = [c.property("win_title") for c in getattr(self, '_custom_cards', []) if c.property("is_checked")]
            if not sel:
                self._show_custom_dialog("Aviso", "Selecciona al menos una ventana.")
                return
            self._cfg['selected_windows'] = sel
            self.stack.setCurrentIndex(1)
            self.retranslate_ui(self._lang)
        elif idx == 1:
            self._cfg_mod.save_config(self._cfg)
            self.dlg.accept()
            self._launch_hub()
        elif idx == 2:
            self._cfg_mod.save_config(self._cfg)
            self.dlg.accept()
            self._launch_hub()

    def _launch_hub(self):
        """Lanza el nuevo panel de control HUB y las réplicas asegurando instancia única."""
        global _GLOBAL_HUB
        try:
            # Si ya existe un HUB activo, lo restauramos y salimos
            if _GLOBAL_HUB and hasattr(_GLOBAL_HUB, 'window') and not _GLOBAL_HUB._is_closed:
                try:
                    if _GLOBAL_HUB.window.isMinimized():
                        _GLOBAL_HUB.window.showNormal()
                    _GLOBAL_HUB.window.show()
                    _GLOBAL_HUB.window.raise_()
                    _GLOBAL_HUB.window.activateWindow()
                    return
                except:
                    _GLOBAL_HUB = None # Si falló la comprobación, lo limpiamos

            titles = self._cfg.get('selected_windows', [])
            region = self._cfg.get('region', {'x':0, 'y':0, 'w':0.1, 'h':0.1})
            
            # Crear HUB único
            self.hub_window = ReplicatorHub(self._W, self._C, self._G, self._cfg, titles, region)
            self.hub_window.show()
            _GLOBAL_HUB = self.hub_window
        except Exception as e:
            logger.error(f"Error lanzando HUB: {e}")

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self.dlg.reject()
        elif idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self.retranslate_ui(self._lang)

    def show(self):
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def _animate_minimize(self, widget):
        """Anima una ventana deslizándose hacia el dock antes de ocultarla."""
        try:
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
            from PySide6.QtWidgets import QApplication

            self._saved_geo = widget.geometry()
            self._saved_opacity = widget.windowOpacity()
            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    end_x = tg.x() + tg.width() // 2 - 60
                    end_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                end_x = sg.x() + sg.width() // 2 - 60
                end_y = sg.y() + sg.height() - 50
            end_geo = QRect(end_x, end_y, 120, 30)

            group = QParallelAnimationGroup(widget)

            anim_geo = QPropertyAnimation(widget, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(self._saved_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.InCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.InCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(widget, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(self._saved_opacity)
            anim_op.setEndValue(0.0)
            group.addAnimation(anim_op)

            def _on_finished():
                widget.setWindowOpacity(self._saved_opacity)
                widget.setGeometry(self._saved_geo)
                widget.hide()

            group.finished.connect(_on_finished)
            group.start()
            self._anim_group = group
        except Exception:
            widget.hide()

    def _animate_restore(self, widget):
        try:
            if not hasattr(self, '_saved_geo'): return
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
            from PySide6.QtWidgets import QApplication

            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    start_x = tg.x() + tg.width() // 2 - 60
                    start_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                start_x = sg.x() + sg.width() // 2 - 60
                start_y = sg.y() + sg.height() - 50
            
            start_geo = QRect(start_x, start_y, 120, 30)
            end_geo = self._saved_geo

            widget.setGeometry(start_geo)
            widget.setWindowOpacity(0.0)

            group = QParallelAnimationGroup(widget)

            anim_geo = QPropertyAnimation(widget, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(start_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.OutCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.OutCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(widget, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(0.0)
            anim_op.setEndValue(self._saved_opacity if hasattr(self, '_saved_opacity') else 1.0)
            group.addAnimation(anim_op)

            group.start()
            self._anim_group = group
        except Exception:
            pass

    @property
    def result(self):
        return self.dlg.result()

_GLOBAL_HUB = None

class ReplicatorHub:
    def __init__(self, W, C, G, cfg, initial_titles, region):
        self._W = W; self._C = C; self._G = G
        self._cfg = cfg; self._region = region
        self._overlays = {}; self._handles = {}
        self._drag_pos = None
        self._is_closed = False # Marca de estado activo
        
        self.window = W.QWidget()
        self.window.setObjectName("ReplicatorHub")
        self.window.setWindowTitle("Panel de Control")
        self.window.closeEvent = self._on_close

        Qt = C.Qt
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.window.setWindowFlags(flags)
        self.window.setMinimumSize(260, 320)
        self.window.resize(260, 380)
        
        # Estilo HUB Premium (Como el de ISK y Wizard)
        self.window.setStyleSheet("""
            QWidget#ReplicatorHub { 
                background: #000; border: 1px solid rgba(0,200,255,0.3); border-radius: 6px; 
            }
            QLabel { color: rgba(200,230,255,0.9); font-family: 'Segoe UI', sans-serif; font-size: 11px; }
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item:selected { background: rgba(0,180,255,0.1); }
            
            QPushButton { 
                background: rgba(0,180,255,0.08); border: 1px solid rgba(0,180,255,0.25);
                border-radius: 4px; color: #00c8ff; padding: 5px; font-weight: bold; font-size: 10px;
            }
            QPushButton:hover { background: rgba(0,180,255,0.2); border-color: #00c8ff; }
            
            QCheckBox::indicator {
                width: 18px; height: 18px;
                background: rgba(0,255,157,0.05);
                border: 2px solid rgba(0,255,157,0.3);
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background: #00ff9d;
                border-color: #00ff9d;
                image: url(none);
            }
            QCheckBox::indicator:hover {
                border-color: #00ff9d;
            }
        """)
        
        lay = W.QVBoxLayout(self.window); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        
        # Cabecera Arrastrable
        BTN_MIN_STYLE = (
            "QPushButton{background:rgba(0,180,255,0.15);border:1px solid rgba(0,180,255,0.4);"
            "border-radius:3px;color:#00c8ff;font-size:10px;}QPushButton:hover{background:rgba(0,180,255,0.35);}"
        )
        BTN_CLS_STYLE = (
            "QPushButton{background:rgba(255,50,50,0.15);border:1px solid rgba(255,50,50,0.4);"
            "border-radius:3px;color:#ff6666;font-size:10px;}QPushButton:hover{background:rgba(255,50,50,0.35);}"
        )

        self.hdr = W.QWidget(); self.hdr.setFixedHeight(30)
        self.hdr.setStyleSheet("background: #000; border-bottom: 1px solid rgba(0,180,255,0.15);")
        hl = W.QHBoxLayout(self.hdr); hl.setContentsMargins(12,0,8,0); hl.setSpacing(6)
        from utils.i18n import t
        self._lbl_title = W.QLabel("Panel de control")
        self._lbl_title.setStyleSheet("font-weight: bold; color: rgba(0,180,255,0.8); letter-spacing: 1px; font-size: 11px;")
        hl.addWidget(self._lbl_title); hl.addStretch()
        
        bm = W.QPushButton("\u2212"); bm.setFixedSize(18,18); bm.setStyleSheet(BTN_MIN_STYLE)
        bm.clicked.connect(lambda: self._animate_minimize_hub()); hl.addWidget(bm)
        
        bc = W.QPushButton("\u00d7"); bc.setFixedSize(18,18); bc.setStyleSheet(BTN_CLS_STYLE)
        bc.clicked.connect(self.window.close); hl.addWidget(bc)
        lay.addWidget(self.hdr)
        
        # Cuerpo (Lista estilo Wizard)
        body = W.QWidget(); bl = W.QVBoxLayout(body); bl.setContentsMargins(5,5,5,5)
        self._list = W.QListWidget(); bl.addWidget(self._list)
        lay.addWidget(body)
        
        # Footer
        footer = W.QWidget(); footer.setFixedHeight(45); fl = W.QHBoxLayout(footer); fl.setContentsMargins(12,0,12,0)
        br = W.QPushButton("🔄"); br.setFixedSize(28, 28); br.setToolTip("Refrescar"); br.clicked.connect(lambda: self.refresh_windows()); fl.addWidget(br)
        fl.addStretch()
        bo = W.QPushButton("\u2715 CERRAR TODO"); bo.setFixedHeight(28); 
        bo.setStyleSheet("QPushButton { background: rgba(255,50,50,0.08); border: 1px solid rgba(255,60,60,0.25); color: rgba(255,120,120,0.7); font-size: 9px; padding: 4px 12px; font-weight:bold; } "
                         "QPushButton:hover { background: rgba(255,50,50,0.22); border-color: #ff4444; color: #ff6666; }")
        bo.clicked.connect(self.close_all); fl.addWidget(bo)
        lay.addWidget(footer)

        # Lógica de Arrastre (Conectada directamente a la ventana)
        def _press(e): 
            if e.button() == Qt.MouseButton.LeftButton: 
                self._drag_pos = e.globalPosition().toPoint() if hasattr(e, 'globalPosition') else e.globalPos()
        def _move(e):
            if e.buttons() & Qt.MouseButton.LeftButton and self._drag_pos:
                gpos = e.globalPosition().toPoint() if hasattr(e, 'globalPosition') else e.globalPos()
                self.window.move(self.window.pos() + gpos - self._drag_pos)
                self._drag_pos = gpos
        self.hdr.mousePressEvent = _press
        self.hdr.mouseMoveEvent = _move
        
        # Lógica de Minimizado/Restaurado
        def _change_event(e):
            if e.type() == C.QEvent.WindowStateChange:
                if self.window.isMinimized():
                    logger.info("HUB Minimizado")
                    # Aquí podríamos avisar al controlador
                else:
                    logger.info("HUB Restaurado")
            self.window.old_change_event(e)
            
        self.window.old_change_event = self.window.changeEvent
        self.window.changeEvent = _change_event
        
        self._timer = C.QTimer(); self._timer.timeout.connect(lambda: self.refresh_windows()); self._timer.start(5000)
        C.QTimer.singleShot(200, lambda: self.refresh_windows(initial_titles))

    def retranslate_ui(self, lang):
        from utils.i18n import t
        if hasattr(self, '_lbl_title'):
            self._lbl_title.setText("Panel de control")
        # Refrescar botones de la lista si es necesario
        self.refresh_windows()

    def show(self): self.window.show(); self.window.raise_(); self.window.activateWindow()

    def _animate_minimize_hub(self):
        """Anima la ventana del HUB deslizándose hacia el dock."""
        try:
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
            from PySide6.QtWidgets import QApplication

            self._saved_geo = self.window.geometry()
            self._saved_opacity = self.window.windowOpacity()
            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    end_x = tg.x() + tg.width() // 2 - 60
                    end_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                end_x = sg.x() + sg.width() // 2 - 60
                end_y = sg.y() + sg.height() - 50
            end_geo = QRect(end_x, end_y, 120, 30)

            group = QParallelAnimationGroup(self.window)

            anim_geo = QPropertyAnimation(self.window, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(self._saved_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.InCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.InCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(self.window, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(self._saved_opacity)
            anim_op.setEndValue(0.0)
            group.addAnimation(anim_op)

            def _on_finished():
                self.window.setWindowOpacity(self._saved_opacity)
                self.window.setGeometry(self._saved_geo)
                self.window.hide()

            group.finished.connect(_on_finished)
            group.start()
            self._hub_anim_group = group
        except Exception:
            self.window.hide()

    def _animate_restore_hub(self):
        try:
            if not hasattr(self, '_saved_geo'): return
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
            from PySide6.QtWidgets import QApplication

            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    start_x = tg.x() + tg.width() // 2 - 60
                    start_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                start_x = sg.x() + sg.width() // 2 - 60
                start_y = sg.y() + sg.height() - 50
            
            start_geo = QRect(start_x, start_y, 120, 30)
            end_geo = self._saved_geo

            self.window.setGeometry(start_geo)
            self.window.setWindowOpacity(0.0)

            group = QParallelAnimationGroup(self.window)

            anim_geo = QPropertyAnimation(self.window, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(start_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.OutCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.OutCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(self.window, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(0.0)
            anim_op.setEndValue(self._saved_opacity if hasattr(self, '_saved_opacity') else 1.0)
            group.addAnimation(anim_op)

            group.start()
            self._hub_anim_group = group
        except Exception:
            pass

    def refresh_windows(self, force_titles=None):
        if not isinstance(force_titles, (list, tuple)): force_titles = None
        try:
            from overlay.win32_capture import find_eve_windows
            current = find_eve_windows()
            self._handles = {w['title']: w['hwnd'] for w in current}
            active = force_titles if force_titles is not None else [t for t, ov in self._overlays.items()]
            
            self._list.clear()
            self._custom_cards = []
            
            for w in current:
                title = w['title']
                item = self._W.QListWidgetItem(self._list)
                
                card = self._W.QWidget()
                card.setStyleSheet(
                    "QWidget#Card { background: rgba(0,180,255,0.03); border: 1px solid rgba(0,180,255,0.08); border-radius: 4px; }"
                    "QWidget#Card:hover { background: rgba(0,180,255,0.06); border-color: rgba(0,180,255,0.2); }"
                )
                card.setObjectName("Card")
                rl = self._W.QHBoxLayout(card); rl.setContentsMargins(10, 6, 10, 6); rl.setSpacing(10)
                
                # Checkbox Estilo Wizard
                chk = self._W.QLabel()
                chk.setFixedSize(16, 16)
                AlignC = getattr(self._C.Qt, 'AlignCenter', getattr(self._C.Qt.AlignmentFlag, 'AlignCenter', 0x0084))
                chk.setAlignment(AlignC)
                
                is_on = (title in active or title in self._overlays)
                
                def set_custom_chk(lbl, state):
                    lbl.setProperty("is_checked", state)
                    if state:
                        lbl.setText("✔"); lbl.setStyleSheet("border: 1px solid #00ff9d; border-radius: 3px; background: rgba(0,255,157,0.1); color: #00ff9d; font-weight: bold; font-size: 12px;")
                    else:
                        lbl.setText(""); lbl.setStyleSheet("border: 1px solid rgba(0,180,255,0.4); border-radius: 3px; background: transparent;")
                
                set_custom_chk(chk, is_on)
                rl.addWidget(chk)
                
                # Nombre
                name = self._W.QLabel(title)
                name.setStyleSheet("font-weight: bold; color: #e1e9f5; font-size: 10px;")
                rl.addWidget(name); rl.addStretch()
                
                # Botones de Opacidad
                BTN_OP_STYLE = "QPushButton { background: rgba(0,180,255,0.05); border: 1px solid rgba(0,180,255,0.2); border-radius:3px; color: #00c8ff; font-weight:bold; } QPushButton:hover { background: rgba(0,180,255,0.15); }"
                b1 = self._W.QPushButton("-"); b1.setFixedSize(20, 20); b1.setStyleSheet(BTN_OP_STYLE); b1.clicked.connect(lambda _, t=title: self._adj_op(t, -0.1))
                b2 = self._W.QPushButton("+"); b2.setFixedSize(20, 20); b2.setStyleSheet(BTN_OP_STYLE); b2.clicked.connect(lambda _, t=title: self._adj_op(t, 0.1))
                rl.addWidget(b1); rl.addWidget(b2)
                
                def _toggle_hub(ev, _t=title, _chk=chk):
                    new_state = not _chk.property("is_checked")
                    set_custom_chk(_chk, new_state)
                    self._toggle(_t, new_state)
                card.mousePressEvent = _toggle_hub
                
                item.setSizeHint(card.sizeHint())
                self._list.setItemWidget(item, card)
                if is_on and title not in self._overlays: self._launch_one(title)

            # Ajuste de altura dinámico
            item_count = len(current)
            new_h = 30 + 45 + (item_count * 42) + 15 # header + footer + items + padding
            new_h = max(150, min(600, new_h))
            self.window.setFixedHeight(new_h)
            
        except Exception as e: 
            logger.error(f"Error refresh HUB: {e}")

    def _toggle(self, title, active):
        if active: self._launch_one(title)
        else: self._stop_one(title)

    def _launch_one(self, title):
        if title in self._overlays: return
        h = self._handles.get(title)
        if not h: return
        from overlay.replication_overlay import ReplicationOverlay
        from overlay import replicator_config as cfg_lib
        ov = ReplicationOverlay(title=title, hwnd_getter=lambda t=title: self._handles.get(t),
                                region_rel=self._region, cfg=self._cfg, 
                                save_callback=lambda *a: cfg_lib.save_overlay_state(self._cfg, *a))
        # CONEXIÓN CRÍTICA: Re-selección de zona desde el HUB
        try:
            from controller.tray_manager import _GLOBAL_TRAY
            if _GLOBAL_TRAY:
                ov.selection_requested.connect(_GLOBAL_TRAY._on_reselect_region)
        except: pass
        
        ov.show(); self._overlays[title] = ov

    def _stop_one(self, title):
        try:
            if title in self._overlays:
                ov = self._overlays.pop(title)
                # Desconectar señales antes de cerrar para evitar llamadas a objetos borrados
                try: ov.selection_requested.disconnect()
                except: pass
                ov.close()
        except Exception as e:
            logger.error(f"Error al detener réplica {title}: {e}")

    def _adj_op(self, title, d):
        if title in self._overlays:
            o = self._overlays[title]
            o.setWindowOpacity(max(0.1, min(1.0, o.windowOpacity() + d)))

    def close_all(self):
        for t in list(self._overlays.keys()): self._stop_one(t)
        self.refresh_windows([])

    def _on_close(self, event):
        """Limpia todo al cerrar la ventana principal del HUB."""
        self.close_all()
        self._is_closed = True
        event.accept()
