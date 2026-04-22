from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QFrame, QLabel, QPushButton, QStackedWidget,
    QScrollArea, QGridLayout, QLineEdit, QCheckBox, 
    QDoubleSpinBox, QComboBox, QFileDialog, QSpacerItem, QSizePolicy,
    QListWidget, QProgressBar
)
from PySide6.QtCore import Qt, QSize, QTimer, QSettings
from PySide6.QtGui import QColor, QIcon, QFont, QLinearGradient, QPixmap
import sys
from datetime import datetime

from ui.desktop.styles import MAIN_STYLE
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        print("DEBUG: Inicializando Suite Ultra Premium Integrada...")
        self.controller = controller
        self.tray_manager = None
        self.setWindowTitle("EVE iT — Desktop Suite Premium")
        self.resize(1150, 850)
        
        self.account_cards = {}
        self.current_character = None 
        
        # Refs para persistencia
        self.edit_log_dir = None
        self.check_skip_logs = None
        self.check_blur = None
        self.check_hide_hud = None
        self.combo_translator_lang = None
        
        try:
            self.setup_ui()
            self.apply_styles()
            print("DEBUG: UI Ultra Premium Integrada cargada.")
        except Exception as e:
            import traceback
            print(f"ERROR: {e}"); traceback.print_exc()

        self.load_settings()
        self.restore_geometry()
        
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(2000)
        
    def setup_ui(self):
        self.central_widget = QWidget(); self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
        
        # 1. Sidebar
        self.nav_bar = QFrame(); self.nav_bar.setObjectName("NavBar")
        self.nav_layout = QVBoxLayout(self.nav_bar); self.nav_layout.setContentsMargins(0, 0, 0, 0); self.nav_layout.setSpacing(0)
        
        logo = QLabel("EVE iT"); logo.setObjectName("LogoLabel"); self.nav_layout.addWidget(logo)
        self.btn_dashboard = self.create_nav_button("👤 PERSONAJES", True)
        self.btn_tools = self.create_nav_button("🛠️ HERRAMIENTAS")
        self.btn_settings = self.create_nav_button("⚙️ CONFIGURACIÓN")
        
        self.nav_layout.addWidget(self.btn_dashboard); self.nav_layout.addWidget(self.btn_tools)
        self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.btn_settings)
        
        # 2. Content
        self.content_frame = QFrame(); self.content_frame.setObjectName("ContentFrame")
        self.content_layout = QVBoxLayout(self.content_frame); self.content_layout.setContentsMargins(30, 30, 30, 30); self.content_layout.setSpacing(20)
        
        header = QHBoxLayout()
        self.section_title = QLabel("DASHBOARD"); self.section_title.setObjectName("SectionTitle")
        header.addWidget(self.section_title); header.addStretch()
        self.content_layout.addLayout(header)
        
        self.stack = QStackedWidget()
        self.page_dashboard = self.create_dashboard_page()
        self.page_tools = self.create_tools_page()
        self.page_settings = self.create_settings_page()
        self.page_detail = self.create_detail_page()
        
        self.stack.addWidget(self.page_dashboard); self.stack.addWidget(self.page_tools)
        self.stack.addWidget(self.page_settings); self.stack.addWidget(self.page_detail)
        
        self.content_layout.addWidget(self.stack)
        self.main_layout.addWidget(self.nav_bar); self.main_layout.addWidget(self.content_frame, 1)

        self.btn_dashboard.clicked.connect(lambda: self.switch_page(0, "PERSONAJES ACTIVOS"))
        self.btn_tools.clicked.connect(lambda: self.switch_page(1, "SUITE DE HERRAMIENTAS"))
        self.btn_settings.clicked.connect(lambda: self.switch_page(2, "CENTRO DE CONFIGURACIÓN"))

    def switch_page(self, index, title):
        self.stack.setCurrentIndex(index); self.section_title.setText(title)
        btns = [self.btn_dashboard, self.btn_tools, self.btn_settings]
        for i, b in enumerate(btns):
            b.setProperty("active", "true" if i == index else "false"); b.setStyle(b.style())

    def create_nav_button(self, text, active=False):
        b = QPushButton(text); b.setProperty("class", "NavButton"); b.setProperty("active", str(active).lower()); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(55); return b

    def create_dashboard_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoShape); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); self.accounts_layout = QGridLayout(cont); self.accounts_layout.setContentsMargins(0, 0, 10, 10); self.accounts_layout.setSpacing(20)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_account_card(self, acc):
        name = acc.get('display_name', acc.get('character'))
        card = QFrame(); card.setObjectName("CharacterCard"); card.setFixedSize(320, 160); card.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(card); l.setContentsMargins(20, 20, 20, 20); l.setSpacing(15)
        avatar = QLabel(); avatar.setObjectName("CharAvatar"); avatar.setFixedSize(70, 70); avatar.setAlignment(Qt.AlignCenter); avatar.setText(name[0].upper())
        info = QVBoxLayout(); name_lbl = QLabel(name); name_lbl.setObjectName("CharName")
        status = QLabel("● ONLINE" if acc.get('status') == 'active' else "○ IDLE")
        status.setStyleSheet(f"color: {'#00ff9d' if acc.get('status') == 'active' else '#ffd700'}; font-family: 'Share Tech Mono'; font-size: 10px;")
        isk_h = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h"); isk_h.setStyleSheet("color: #ffd700; font-family: 'Share Tech Mono'; font-size: 13px; font-weight: bold;")
        info.addWidget(name_lbl); info.addWidget(status); info.addStretch(); info.addWidget(isk_h)
        l.addWidget(avatar); l.addLayout(info); card.mousePressEvent = lambda e: self.open_character_detail(acc); return card

    def open_character_detail(self, acc):
        self.current_character = acc; self.update_detail_view(); self.stack.setCurrentIndex(3); self.section_title.setText("PERFIL ESTRATÉGICO")

    def create_detail_page(self):
        p = QFrame(); p.setObjectName("DetailView"); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(25)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoShape); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setContentsMargins(0, 0, 0, 0); c_l.setSpacing(30)
        
        back = QPushButton("← VOLVER AL DASHBOARD"); back.setObjectName("BackButton"); back.clicked.connect(lambda: self.switch_page(0, "PERSONAJES ACTIVOS"))
        c_l.addWidget(back, 0, Qt.AlignLeft)
        
        # Profile Header
        h = QHBoxLayout(); h.setSpacing(25)
        self.detail_avatar = QLabel(); self.detail_avatar.setObjectName("CharAvatar"); self.detail_avatar.setFixedSize(120, 120); self.detail_avatar.setAlignment(Qt.AlignCenter)
        v = QVBoxLayout(); self.detail_name = QLabel("NAME"); self.detail_name.setObjectName("DetailTitle")
        self.detail_status = QLabel("STATUS"); self.detail_status.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 14px; color: #00ff9d;")
        self.detail_corp = QLabel("SYNC: ACTIVE ENGINE v2.0"); self.detail_corp.setStyleSheet("color: rgba(0,200,255,0.4); font-size: 11px; font-family: 'Share Tech Mono';")
        v.addWidget(self.detail_name); v.addWidget(self.detail_status); v.addWidget(self.detail_corp); h.addWidget(self.detail_avatar); h.addLayout(v); h.addStretch(); c_l.addLayout(h)
        
        # Primary Metrics (Large)
        metrics = QHBoxLayout(); metrics.setSpacing(20)
        self.box_wallet = self.create_analytic_box("WALLET SESIÓN", "0.00 ISK", True)
        self.box_1h = self.create_analytic_box("ISK/H (ROLLING)", "0.00 ISK", True)
        metrics.addWidget(self.box_wallet); metrics.addWidget(self.box_1h); c_l.addLayout(metrics)
        
        # Secondary Metrics Grid
        grid = QGridLayout(); grid.setSpacing(15)
        self.box_24h = self.create_analytic_box("RENDIMIENTO 24H", "SINC...")
        self.box_7d = self.create_analytic_box("RENDIMIENTO 7D", "SINC...")
        self.box_30d = self.create_analytic_box("RENDIMIENTO 30D", "SINC...")
        self.box_lifetime = self.create_analytic_box("ISK TOTAL SESIÓN", "0.00 ISK")
        grid.addWidget(self.box_24h, 0, 0); grid.addWidget(self.box_7d, 0, 1); grid.addWidget(self.box_30d, 1, 0); grid.addWidget(self.box_lifetime, 1, 1)
        c_l.addLayout(grid)
        
        # Activity & PI Split
        split = QHBoxLayout(); split.setSpacing(20)
        
        # PI Section
        pi_box = QFrame(); pi_box.setStyleSheet("background: rgba(0, 20, 45, 0.4); border: 1px solid rgba(0,180,255,0.15); border-radius: 8px; padding: 25px;")
        pi_l = QVBoxLayout(pi_box); pi_l.addWidget(QLabel("PLANETOLOGÍA (PI)", styleSheet="font-family: 'Orbitron'; color: #00c8ff; font-weight: bold;"))
        pi_desc = QLabel("Módulo en desarrollo. Sincronización con ESI requerida para visualizar extractores activos."); pi_desc.setStyleSheet("color: rgba(255,255,255,0.2); font-size: 10px; margin-top: 10px; word-wrap: true;")
        pi_l.addWidget(pi_desc); pi_l.addStretch(); split.addWidget(pi_box, 1)
        
        # Activity Feed
        act_box = QFrame(); act_box.setStyleSheet("background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 20px;")
        act_l = QVBoxLayout(act_box); act_l.addWidget(QLabel("FEED DE ACTIVIDAD REAL", styleSheet="font-family: 'Orbitron'; color: #ffffff; font-weight: bold; font-size: 11px;"))
        self.activity_feed = QListWidget(); self.activity_feed.setStyleSheet("background: transparent; border: none; color: rgba(255,255,255,0.7); font-family: 'Share Tech Mono'; font-size: 11px;")
        act_l.addWidget(self.activity_feed); split.addWidget(act_box, 1)
        
        c_l.addLayout(split); scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_analytic_box(self, label, value, large=False):
        b = QFrame(); b.setObjectName("AnalyticBox")
        if large: b.setMinimumHeight(110); b.setStyleSheet("background: rgba(0, 180, 255, 0.05); border-color: rgba(0, 180, 255, 0.3);")
        l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: rgba(0, 180, 255, 0.6); font-family: 'Share Tech Mono'; font-size: 10px;"))
        v = QLabel(value); v.setObjectName("AnalyticVal")
        if large: v.setStyleSheet("font-size: 24px; color: #ffd700; font-weight: bold;")
        l.addWidget(v); return b

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character; name = acc.get('display_name', acc.get('character'))
        self.detail_name.setText(name.upper()); self.detail_avatar.setText(name[0].upper())
        self.detail_status.setText("● MONITORIZANDO" if acc.get('status') == 'active' else "○ EN REPOSO")
        
        # Data real
        self.box_1h.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('isk_per_hour', 0), short=True))
        self.box_wallet.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('total_isk', 0), short=True))
        self.box_lifetime.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('total_isk', 0), short=True))
        
        # Feed real
        self.activity_feed.clear()
        events = acc.get('events', [])
        if not events:
            self.activity_feed.addItem("ESPERANDO DATOS DE LOGS...")
        else:
            for ev in reversed(events):
                ts = ev.get('timestamp')
                if isinstance(ts, str): ts = datetime.fromisoformat(ts)
                ts_str = ts.strftime('%H:%M:%S')
                self.activity_feed.addItem(f"[{ts_str}] +{format_isk(ev['isk'], short=True)}")

    def create_tools_page(self):
        p = QWidget(); l = QVBoxLayout(p); g = QGridLayout(); g.setSpacing(25)
        g.addWidget(self.create_tool_card("HUD OVERLAY", "Control visual y métricas en juego.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("TRADUCTOR", "Traducción inteligente de chats locales.", "🌐", self._on_translator_clicked), 0, 1)
        g.addWidget(self.create_tool_card("REPLICADOR", "Sincronización de clics y ventanas masivas.", "🪟", self._on_replicator_clicked), 1, 0)
        l.addLayout(g); l.addStretch(); return p

    def create_tool_card(self, title, desc, icon, callback):
        c = QFrame(); c.setObjectName("CharacterCard"); c.setFixedSize(380, 150); c.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(c); l.setContentsMargins(25,25,25,25)
        ico = QLabel(icon); ico.setStyleSheet("font-size: 45px;"); l.addWidget(ico)
        v = QVBoxLayout(); t = QLabel(title); t.setObjectName("CharName"); d = QLabel(desc); d.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px; word-wrap: true;")
        v.addWidget(t); v.addWidget(d); l.addLayout(v); c.mousePressEvent = lambda e: callback(); return c

    def create_settings_page(self):
        p = QWidget(); l = QVBoxLayout(p); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoShape)
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setSpacing(20)
        
        # Bloque Motor
        g_eng, l_eng = self.create_settings_group("MOTOR EVE iT (CORE)", "Configuración del tracker y logs.")
        l_eng.addWidget(QLabel("DIRECTORIO LOGS:", styleSheet="font-family: 'Share Tech Mono'; color: #00c8ff; font-size: 10px;"))
        path_l = QHBoxLayout(); self.edit_log_dir = QLineEdit(); btn_b = QPushButton("..."); btn_b.setFixedWidth(40); btn_b.clicked.connect(self._on_browse_logs)
        path_l.addWidget(self.edit_log_dir); path_l.addWidget(btn_b); l_eng.addLayout(path_l)
        self.check_skip_logs = QCheckBox("OMITIR REGISTROS ANTIGUOS"); l_eng.addWidget(self.check_skip_logs)
        c_l.addWidget(g_eng)
        
        # Bloque Visual & HUD
        g_vis, l_vis = self.create_settings_group("INTERFAZ & HUD", "Ajustes de transparencia y efectos visuales.")
        self.check_blur = QCheckBox("HABILITAR DESENFOQUE (BLUR) EN OVERLAYS"); l_vis.addWidget(self.check_blur)
        self.check_hide_hud = QCheckBox("OCULTAR AUTOMÁTICAMENTE SI NO HAY ACTIVIDAD"); l_vis.addWidget(self.check_hide_hud)
        c_l.addWidget(g_vis)
        
        # Bloque Traductor
        g_tr, l_tr = self.create_settings_group("TRADUCCIÓN E INTELIGENCIA", "Configuración del motor de traducción.")
        l_tr.addWidget(QLabel("IDIOMA DESTINO:")); self.combo_translator_lang = QComboBox()
        self.combo_translator_lang.addItems(["ESPAÑOL", "ENGLISH", "DEUTSCH", "FRANÇAIS", "RUSSIAN"])
        l_tr.addWidget(self.combo_translator_lang)
        c_l.addWidget(g_tr)
        
        c_l.addStretch()
        save = QPushButton("GUARDAR Y SINCRONIZAR SUITE"); save.setObjectName("SaveButton"); save.clicked.connect(self.save_settings); c_l.addWidget(save)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_settings_group(self, title, subtitle):
        g = QFrame(); g.setObjectName("SettingsGroup"); l = QVBoxLayout(g); l.setContentsMargins(25,25,25,25)
        t = QLabel(title); t.setStyleSheet("font-family: 'Orbitron'; font-size: 14px; color: #00c8ff; font-weight: bold;")
        s = QLabel(subtitle); s.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px; margin-bottom: 15px;")
        l.addWidget(t); l.addWidget(s); return g, l

    def refresh_data(self):
        if not self.controller or not self.controller._tracker: return
        try:
            summary = self.controller._tracker.get_summary(datetime.now())
            accounts = summary.get('per_character', [])
            self.update_accounts_view(accounts)
            if self.stack.currentIndex() == 3: self.update_detail_view()
        except Exception as e: print(f"DEBUG: Error refresh: {e}")

    def update_accounts_view(self, accounts):
        if not self.accounts_layout: return
        names = [acc.get('display_name', acc.get('character')) for acc in accounts]
        for name in list(self.account_cards.keys()):
            if name not in names:
                card = self.account_cards.pop(name); self.accounts_layout.removeWidget(card); card.deleteLater()
        for i, acc in enumerate(accounts):
            name = acc.get('display_name', acc.get('character'))
            if name not in self.account_cards:
                card = self.create_account_card(acc); self.account_cards[name] = card
                self.accounts_layout.addWidget(card, i // 3, i % 3)
            else:
                card = self.account_cards[name]
                card.findChildren(QLabel)[2].setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")

    def set_tray_manager(self, tm): self.tray_manager = tm
    def _on_hud_clicked(self):
        if self.tray_manager: self.tray_manager._on_overlay()
    def _on_translator_clicked(self):
        if self.controller: self.controller.start_translator()
    def _on_replicator_clicked(self):
        if self.tray_manager: self.tray_manager._on_replicator()
    def _on_browse_logs(self):
        d = QFileDialog.getExistingDirectory(self, "Logs EVE"); self.edit_log_dir.setText(d if d else "")

    def load_settings(self):
        s = QSettings("EVE_iT", "Suite")
        self.edit_log_dir.setText(s.value("log_dir", ""))
        self.check_skip_logs.setChecked(s.value("skip_logs", "true") == "true")
        self.check_blur.setChecked(s.value("enable_blur", "false") == "true")
        self.check_hide_hud.setChecked(s.value("auto_hide_hud", "false") == "true")
        idx = self.combo_translator_lang.findText(s.value("translator_lang", "ESPAÑOL"))
        if idx >= 0: self.combo_translator_lang.setCurrentIndex(idx)

    def save_settings(self):
        s = QSettings("EVE_iT", "Suite")
        s.setValue("log_dir", self.edit_log_dir.text())
        s.setValue("skip_logs", "true" if self.check_skip_logs.isChecked() else "false")
        s.setValue("enable_blur", "true" if self.check_blur.isChecked() else "false")
        s.setValue("auto_hide_hud", "true" if self.check_hide_hud.isChecked() else "false")
        s.setValue("translator_lang", self.combo_translator_lang.currentText())
        self.section_title.setText("SISTEMA ACTUALIZADO"); QTimer.singleShot(2000, lambda: self.section_title.setText("CENTRO DE CONFIGURACIÓN"))

    def closeEvent(self, event):
        try: QSettings("EVE_iT", "Suite").setValue("geometry", self.saveGeometry())
        except: pass
        event.ignore(); self.hide()
    def restore_geometry(self):
        try:
            geo = QSettings("EVE_iT", "Suite").value("geometry")
            if geo: self.restoreGeometry(geo)
        except: pass
    def apply_styles(self): self.setStyleSheet(MAIN_STYLE)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv); window = MainSuiteWindow(); window.show(); sys.exit(app.exec())
