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
from datetime import datetime, timedelta

from ui.desktop.styles import MAIN_STYLE
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        print("DEBUG: Restaurando Integridad Funcional Elite...")
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
            print("DEBUG: UI Elite Restaurada.")
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
        
        # Sidebar
        self.nav_bar = QFrame(); self.nav_bar.setObjectName("NavBar")
        self.nav_layout = QVBoxLayout(self.nav_bar); self.nav_layout.setContentsMargins(0, 0, 0, 0); self.nav_layout.setSpacing(0)
        
        logo = QLabel("EVE iT"); logo.setObjectName("LogoLabel"); self.nav_layout.addWidget(logo)
        self.btn_dashboard = self.create_nav_button("👤 PERSONAJES", True)
        self.btn_tools = self.create_nav_button("🛠️ HERRAMIENTAS")
        self.btn_settings = self.create_nav_button("⚙️ CONFIGURACIÓN")
        
        self.nav_layout.addWidget(self.btn_dashboard); self.nav_layout.addWidget(self.btn_tools)
        self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.btn_settings)
        
        # Content
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
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setContentsMargins(0, 0, 0, 0); c_l.setSpacing(35)
        
        back = QPushButton("← VOLVER AL DASHBOARD"); back.setObjectName("BackButton"); back.clicked.connect(lambda: self.switch_page(0, "PERSONAJES ACTIVOS"))
        c_l.addWidget(back, 0, Qt.AlignLeft)
        
        # Profile Header
        h = QHBoxLayout(); h.setSpacing(30)
        self.detail_avatar = QLabel(); self.detail_avatar.setObjectName("CharAvatar"); self.detail_avatar.setFixedSize(130, 130); self.detail_avatar.setAlignment(Qt.AlignCenter)
        v = QVBoxLayout(); self.detail_name = QLabel("NAME"); self.detail_name.setObjectName("DetailTitle")
        self.detail_status = QLabel("STATUS"); self.detail_status.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 14px; color: #00ff9d;")
        self.detail_meta = QLabel("SISTEMA DE ANÁLISIS VIVIDO — EVE iT ALPHA"); self.detail_meta.setStyleSheet("color: rgba(255,255,255,0.2); font-family: 'Share Tech Mono'; font-size: 11px;")
        v.addWidget(self.detail_name); v.addWidget(self.detail_status); v.addWidget(self.detail_meta); h.addWidget(self.detail_avatar); h.addLayout(v); h.addStretch(); c_l.addLayout(h)
        
        # Impact Metrics
        impact = QHBoxLayout(); impact.setSpacing(25)
        self.box_wallet = self.create_impact_box("WALLET ACUMULADA", "0.00 ISK", "#ffd700")
        self.box_1h = self.create_impact_box("RENDIMIENTO ACTUAL", "0.00 ISK/h", "#00ff9d")
        impact.addWidget(self.box_wallet); impact.addWidget(self.box_1h); c_l.addLayout(impact)
        
        # Matrix Analysis
        matrix_title = QLabel("MATRIZ DE RENDIMIENTO ESTRATÉGICO"); matrix_title.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(255,255,255,0.3); font-size: 11px; letter-spacing: 1px;")
        c_l.addWidget(matrix_title)
        
        matrix = QGridLayout(); matrix.setSpacing(20)
        self.box_session_avg = self.create_analytic_box("PROMEDIO SESIÓN", "0.00 ISK/h")
        self.box_session_peak = self.create_analytic_box("PICO MÁXIMO (TICK)", "0.00 ISK")
        self.box_24h_proj = self.create_analytic_box("ESTIMACIÓN 24H (PROY.)", "0.00 ISK")
        self.box_events_count = self.create_analytic_box("EVENTOS DETECTADOS", "0")
        matrix.addWidget(self.box_session_avg, 0, 0); matrix.addWidget(self.box_session_peak, 0, 1)
        matrix.addWidget(self.box_24h_proj, 1, 0); matrix.addWidget(self.box_events_count, 1, 1)
        c_l.addLayout(matrix)
        
        # Bottom Split
        bottom = QHBoxLayout(); bottom.setSpacing(25)
        
        # Planetology
        pi_frame = QFrame(); pi_frame.setObjectName("ModularPI"); pi_frame.setMinimumHeight(250)
        pi_l = QVBoxLayout(pi_frame); pi_l.setContentsMargins(30,30,30,30)
        pi_t = QLabel("MÓDULO DE PLANETOLOGÍA (PI)"); pi_t.setStyleSheet("font-family: 'Orbitron'; color: #00c8ff; font-weight: bold;")
        pi_s = QLabel("SINC: WAITING ESI HANDSHAKE"); pi_s.setObjectName("PISubtitle")
        pi_desc = QLabel("Los sensores están en modo espera. Conecta tu API para visualizar ciclos de extracción, timers de planetas y alertas de silos llenos."); pi_desc.setStyleSheet("color: rgba(255,255,255,0.2); font-size: 11px; word-wrap: true; margin-top: 10px;")
        pi_l.addWidget(pi_t); pi_l.addWidget(pi_s); pi_l.addWidget(pi_desc); pi_l.addStretch(); bottom.addWidget(pi_frame, 1)
        
        # Activity Feed
        act_frame = QFrame(); act_frame.setStyleSheet("background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 25px;")
        act_l = QVBoxLayout(act_frame); act_l.addWidget(QLabel("FEED DE ACTIVIDAD", styleSheet="font-family: 'Orbitron'; color: #ffffff; font-size: 12px;"))
        self.activity_feed = QListWidget(); self.activity_feed.setStyleSheet("background: transparent; border: none; color: rgba(0, 255, 157, 0.7); font-family: 'Share Tech Mono'; font-size: 11px;")
        self.activity_empty = QLabel("NO SE HAN DETECTADO EVENTOS DE ISK EN ESTA SESIÓN TODAVÍA."); self.activity_empty.setObjectName("EmptyStateText"); self.activity_empty.setAlignment(Qt.AlignCenter); self.activity_empty.setWordWrap(True)
        act_l.addWidget(self.activity_feed); act_l.addWidget(self.activity_empty); bottom.addWidget(act_frame, 1)
        
        c_l.addLayout(bottom); scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_impact_box(self, label, value, color_hex):
        b = QFrame(); b.setStyleSheet(f"background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px;")
        b.setMinimumHeight(130)
        l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: rgba(255,255,255,0.3); font-family: 'Share Tech Mono'; font-size: 11px;"))
        v = QLabel(value); v.setObjectName("GlowValue" if color_hex == "#ffd700" else "GlowValueGreen")
        l.addWidget(v); return b

    def create_analytic_box(self, label, value):
        b = QFrame(); b.setObjectName("AnalyticBox"); l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: rgba(0, 180, 255, 0.5); font-family: 'Share Tech Mono'; font-size: 10px;"))
        v = QLabel(value); v.setObjectName("AnalyticVal"); v.setStyleSheet("font-size: 18px; color: #ffffff; font-family: 'Share Tech Mono';")
        l.addWidget(v); return b

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character; name = acc.get('display_name', acc.get('character'))
        self.detail_name.setText(name.upper()); self.detail_avatar.setText(name[0].upper())
        self.detail_status.setText("● SISTEMA ACTIVO" if acc.get('status') == 'active' else "○ EN ESPERA")
        
        self.box_wallet.findChild(QLabel).setText(format_isk(acc.get('total_isk', 0), short=True))
        self.box_1h.findChild(QLabel).setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        self.box_session_avg.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('isk_per_hour_session', 0), short=True) + "/h")
        
        events = acc.get('events', [])
        peak = max([e['isk'] for e in events]) if events else 0
        self.box_session_peak.findChild(QLabel, "AnalyticVal").setText(format_isk(peak, short=True))
        self.box_events_count.findChild(QLabel, "AnalyticVal").setText(str(len(events)))
        
        proj_24h = acc.get('isk_per_hour', 0) * 24
        self.box_24h_proj.findChild(QLabel, "AnalyticVal").setText(format_isk(proj_24h, short=True))
        
        self.activity_feed.clear()
        if not events:
            self.activity_feed.hide(); self.activity_empty.show()
        else:
            self.activity_empty.hide(); self.activity_feed.show()
            for ev in reversed(events[-15:]):
                ts = ev['timestamp']; ts_str = ts.strftime('%H:%M:%S') if isinstance(ts, datetime) else ts[11:19]
                self.activity_feed.addItem(f"[{ts_str}] RECOMPENSA: +{format_isk(ev['isk'], short=True)}")

    def create_tools_page(self):
        p = QWidget(); l = QVBoxLayout(p); g = QGridLayout(); g.setSpacing(25)
        g.addWidget(self.create_tool_card("HUD OVERLAY", "Control visual táctico en tiempo real.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("TRADUCTOR", "Inteligencia lingüística para chats locales.", "🌐", self._on_translator_clicked), 0, 1)
        g.addWidget(self.create_tool_card("REPLICADOR", "Sincronización masiva de acciones y ventanas.", "🪟", self._on_replicator_clicked), 1, 0)
        l.addLayout(g); l.addStretch(); return p

    def create_tool_card(self, title, desc, icon, callback):
        c = QFrame(); c.setObjectName("CharacterCard"); c.setFixedSize(380, 160); c.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(c); l.setContentsMargins(25,25,25,25)
        ico = QLabel(icon); ico.setStyleSheet("font-size: 45px;"); l.addWidget(ico)
        v = QVBoxLayout(); t = QLabel(title); t.setObjectName("CharName"); d = QLabel(desc); d.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px; word-wrap: true;")
        v.addWidget(t); v.addWidget(d); l.addLayout(v); c.mousePressEvent = lambda e: callback(); return c

    def create_settings_page(self):
        p = QWidget(); l = QVBoxLayout(p); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setSpacing(25)
        
        # Core Engine
        g1, l1 = self.create_settings_group("MOTOR EVE iT (CORE)", "Gestión de datos y logs.")
        l1.addWidget(QLabel("DIRECTORIO LOGS:", styleSheet="font-family: 'Share Tech Mono'; color: #00c8ff; font-size: 10px;"))
        path_l = QHBoxLayout(); self.edit_log_dir = QLineEdit(); btn_b = QPushButton("..."); btn_b.setFixedWidth(40); btn_b.clicked.connect(self._on_browse_logs)
        path_l.addWidget(self.edit_log_dir); path_l.addWidget(btn_b); l1.addLayout(path_l)
        self.check_skip_logs = QCheckBox("IGNORAR HISTORIAL AL ARRANCAR"); l1.addWidget(self.check_skip_logs)
        c_l.addWidget(g1)
        
        # HUD Appearance
        g2, l2 = self.create_settings_group("HUD & APARIENCIA", "Personalización de la interfaz en juego.")
        self.check_blur = QCheckBox("HABILITAR DESENFOQUE (BLUR) PROFUNDO"); l2.addWidget(self.check_blur)
        self.check_hide_hud = QCheckBox("AUTO-OCULTAR HUD SIN ACTIVIDAD"); l2.addWidget(self.check_hide_hud)
        c_l.addWidget(g2)
        
        # Tools & Automation
        g3, l3 = self.create_settings_group("HERRAMIENTAS & AUTOMATIZACIÓN", "Ajustes de traducción y replicación.")
        l3.addWidget(QLabel("IDIOMA DESTINO (TRADUCTOR):"))
        self.combo_translator_lang = QComboBox()
        self.combo_translator_lang.addItems(["ESPAÑOL", "ENGLISH", "DEUTSCH", "FRANÇAIS", "RUSSIAN"])
        l3.addWidget(self.combo_translator_lang)
        c_l.addWidget(g3)
        
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
            else:
                card = self.account_cards[name]; labels = card.findChildren(QLabel)
                labels[2].setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")

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
        if self.edit_log_dir: self.edit_log_dir.setText(s.value("log_dir", ""))
        if self.check_skip_logs: self.check_skip_logs.setChecked(s.value("skip_logs", "true") == "true")
        if self.check_blur: self.check_blur.setChecked(s.value("enable_blur", "false") == "true")
        if self.check_hide_hud: self.check_hide_hud.setChecked(s.value("auto_hide_hud", "false") == "true")
        if self.combo_translator_lang:
            idx = self.combo_translator_lang.findText(s.value("translator_lang", "ESPAÑOL"))
            if idx >= 0: self.combo_translator_lang.setCurrentIndex(idx)

    def save_settings(self):
        s = QSettings("EVE_iT", "Suite")
        if self.edit_log_dir: s.setValue("log_dir", self.edit_log_dir.text())
        if self.check_skip_logs: s.setValue("skip_logs", "true" if self.check_skip_logs.isChecked() else "false")
        if self.check_blur: s.setValue("enable_blur", "true" if self.check_blur.isChecked() else "false")
        if self.check_hide_hud: s.setValue("auto_hide_hud", "true" if self.check_hide_hud.isChecked() else "false")
        if self.combo_translator_lang: s.setValue("translator_lang", self.combo_translator_lang.currentText())
        self.section_title.setText("SISTEMA ACTUALIZADO"); QTimer.singleShot(2000, lambda: self.section_title.setText("CONFIGURACIÓN"))

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
