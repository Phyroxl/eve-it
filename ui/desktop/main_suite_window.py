from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QFrame, QLabel, QPushButton, QStackedWidget,
    QScrollArea, QGridLayout, QLineEdit, QCheckBox, 
    QDoubleSpinBox, QComboBox, QFileDialog, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QSize, QTimer, QSettings
from PySide6.QtGui import QColor, QIcon, QFont, QLinearGradient, QPixmap
import sys

from ui.desktop.styles import MAIN_STYLE
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        print("DEBUG: Inicializando MainSuiteWindow Premium...")
        self.controller = controller
        self.tray_manager = None
        self.setWindowTitle("EVE iT — Desktop Suite Premium")
        self.resize(1100, 750)
        
        self.account_cards = {}
        self.current_character = None 
        
        try:
            self.setup_ui()
            self.apply_styles()
            print("DEBUG: UI Premium cargada correctamente.")
        except Exception as e:
            import traceback
            print(f"ERROR CRÍTICO EN UI: {e}")
            traceback.print_exc()

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
        self.section_title = QLabel("PERSONAJES ACTIVOS"); self.section_title.setObjectName("SectionTitle")
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
        self.btn_tools.clicked.connect(lambda: self.switch_page(1, "HERRAMIENTAS"))
        self.btn_settings.clicked.connect(lambda: self.switch_page(2, "CONFIGURACIÓN"))

    def switch_page(self, index, title):
        self.stack.setCurrentIndex(index); self.section_title.setText(title)
        btns = [self.btn_dashboard, self.btn_tools, self.btn_settings]
        for i, b in enumerate(btns):
            b.setProperty("active", "true" if i == index else "false"); b.setStyle(b.style())

    def create_nav_button(self, text, active=False):
        b = QPushButton(text); b.setProperty("class", "NavButton"); b.setProperty("active", str(active).lower()); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(55); return b

    def create_dashboard_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); self.accounts_layout = QGridLayout(cont); self.accounts_layout.setContentsMargins(0, 0, 10, 10); self.accounts_layout.setSpacing(20)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_account_card(self, acc):
        name = acc.get('display_name', acc.get('character'))
        card = QFrame(); card.setObjectName("CharacterCard"); card.setFixedSize(300, 140); card.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(card); l.setContentsMargins(15, 15, 15, 15); l.setSpacing(15)
        avatar = QLabel(); avatar.setObjectName("CharAvatar"); avatar.setFixedSize(64, 64); avatar.setAlignment(Qt.AlignCenter); avatar.setText(name[0].upper())
        info = QVBoxLayout(); name_lbl = QLabel(name); name_lbl.setObjectName("CharName")
        status = QLabel("● ONLINE" if acc.get('status') == 'active' else "○ IDLE")
        status.setStyleSheet(f"color: {'#00ff9d' if acc.get('status') == 'active' else '#ffd700'}; font-family: 'Share Tech Mono'; font-size: 10px;")
        isk_h = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h"); isk_h.setStyleSheet("color: rgba(255,255,255,0.4); font-family: 'Share Tech Mono'; font-size: 12px;")
        info.addWidget(name_lbl); info.addWidget(status); info.addStretch(); info.addWidget(isk_h)
        l.addWidget(avatar); l.addLayout(info); card.mousePressEvent = lambda e: self.open_character_detail(acc); return card

    def open_character_detail(self, acc):
        self.current_character = acc; self.update_detail_view(); self.stack.setCurrentIndex(3); self.section_title.setText("PERFIL DE PERSONAJE")

    def create_detail_page(self):
        p = QFrame(); p.setObjectName("DetailView"); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(25)
        back = QPushButton("← VOLVER"); back.setObjectName("BackButton"); back.clicked.connect(lambda: self.switch_page(0, "PERSONAJES ACTIVOS"))
        l.addWidget(back, 0, Qt.AlignLeft); h = QHBoxLayout()
        self.detail_avatar = QLabel(); self.detail_avatar.setObjectName("CharAvatar"); self.detail_avatar.setFixedSize(100, 100); self.detail_avatar.setAlignment(Qt.AlignCenter)
        v = QVBoxLayout(); self.detail_name = QLabel("NAME"); self.detail_name.setObjectName("DetailTitle")
        self.detail_status = QLabel("STATUS"); self.detail_status.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 14px; color: #00ff9d;")
        v.addWidget(self.detail_name); v.addWidget(self.detail_status); h.addWidget(self.detail_avatar); h.addLayout(v); h.addStretch(); l.addLayout(h)
        grid = QGridLayout(); self.box_1h = self.create_analytic_box("Rendimiento 1h", "0.00 ISK")
        grid.addWidget(self.box_1h, 0, 0); grid.addWidget(self.create_analytic_box("Rendimiento 24h", "PROXIMAMENTE"), 0, 1); l.addLayout(grid); l.addStretch(); return p

    def create_analytic_box(self, label, value):
        b = QFrame(); b.setObjectName("AnalyticBox"); l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: rgba(0, 180, 255, 0.5); font-family: 'Share Tech Mono'; font-size: 11px;"))
        v = QLabel(value); v.setObjectName("AnalyticVal"); l.addWidget(v); return b

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character; name = acc.get('display_name', acc.get('character'))
        self.detail_name.setText(name.upper()); self.detail_avatar.setText(name[0].upper())
        self.detail_status.setText("● SISTEMA ACTIVO" if acc.get('status') == 'active' else "○ EN ESPERA")
        self.box_1h.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('isk_per_hour', 0), short=True))

    def create_tools_page(self):
        p = QWidget(); l = QVBoxLayout(p); g = QGridLayout()
        g.addWidget(self.create_tool_card("HUD OVERLAY", "Control en vivo.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("TRADUCTOR", "Traducción chat.", "🌐", self._on_translator_clicked), 0, 1)
        l.addLayout(g); l.addStretch(); return p

    def create_tool_card(self, title, desc, icon, callback):
        c = QFrame(); c.setObjectName("CharacterCard"); c.setFixedSize(320, 120); c.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(c); ico = QLabel(icon); ico.setStyleSheet("font-size: 32px;"); l.addWidget(ico)
        v = QVBoxLayout(); t = QLabel(title); t.setObjectName("CharName"); d = QLabel(desc); d.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px;")
        v.addWidget(t); v.addWidget(d); l.addLayout(v); c.mousePressEvent = lambda e: callback(); return c

    def create_settings_page(self):
        p = QWidget(); l = QVBoxLayout(p); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setSpacing(15)
        g1, l1 = self.create_settings_group("TRACKER & LOGS", "Gestión de datos.")
        self.edit_log_dir = QLineEdit(); l1.addWidget(self.edit_log_dir); self.check_skip_logs = QCheckBox("Omitir históricos"); l1.addWidget(self.check_skip_logs)
        c_l.addWidget(g1); c_l.addStretch()
        save = QPushButton("GUARDAR CONFIGURACIÓN"); save.setObjectName("SaveButton"); save.clicked.connect(self.save_settings); c_l.addWidget(save)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_settings_group(self, title, subtitle):
        g = QFrame(); g.setObjectName("SettingsGroup"); l = QVBoxLayout(g)
        t = QLabel(title); t.setStyleSheet("font-family: 'Orbitron'; font-size: 13px; color: #00c8ff; font-weight: bold;")
        s = QLabel(subtitle); s.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px; margin-bottom: 10px;")
        l.addWidget(t); l.addWidget(s); return g, l

    def refresh_data(self):
        if not self.controller or not self.controller._tracker: return
        try:
            from datetime import datetime
            summary = self.controller._tracker.get_summary(datetime.now())
            accounts = summary.get('per_character', [])
            self.update_accounts_view(accounts)
            if self.stack.currentIndex() == 3: self.update_detail_view()
        except: pass

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
        s = QSettings("EVE_iT", "Suite"); self.edit_log_dir.setText(s.value("log_dir", ""))
        self.check_skip_logs.setChecked(s.value("skip_logs", "true") == "true")
    def save_settings(self):
        s = QSettings("EVE_iT", "Suite"); s.setValue("log_dir", self.edit_log_dir.text())
        s.setValue("skip_logs", "true" if self.check_skip_logs.isChecked() else "false")
        self.section_title.setText("CONFIGURACIÓN GUARDADA"); QTimer.singleShot(2000, lambda: self.section_title.setText("CONFIGURACIÓN"))
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
