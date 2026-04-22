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
import logging
from datetime import datetime, timedelta

from ui.desktop.styles import MAIN_STYLE
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self.diag_log = logging.getLogger('eve.suite.diag')
        self.diag_log.info("DIAG: Instanciando MainSuiteWindow...")
        
        self.controller = controller
        self.tray_manager = None
        self.setWindowTitle("EVE iT — Desktop Suite Premium")
        self.resize(1100, 800)
        
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
        except Exception as e:
            import traceback
            self.diag_log.error(f"DIAG: Error en setup_ui: {e}\n{traceback.format_exc()}")

        self.load_settings()
        self.restore_geometry()
        
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(2000)
        
    def setup_ui(self):
        self.central_widget = QWidget(); self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
        
        # 1. Sidebar (Ancho forzado y verificable)
        self.nav_bar = QFrame(); self.nav_bar.setObjectName("NavBar")
        self.nav_bar.setFixedWidth(240)
        self.nav_layout = QVBoxLayout(self.nav_bar); self.nav_layout.setContentsMargins(0, 0, 0, 0); self.nav_layout.setSpacing(0)
        
        logo = QLabel("EVE iT"); logo.setObjectName("LogoLabel"); self.nav_layout.addWidget(logo)
        self.btn_dashboard = self.create_nav_button("👤 MANDO", True)
        self.btn_tools = self.create_nav_button("🛠️ SUITE")
        self.btn_settings = self.create_nav_button("⚙️ SISTEMA")
        
        self.nav_layout.addWidget(self.btn_dashboard); self.nav_layout.addWidget(self.btn_tools)
        self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.btn_settings)
        
        # 2. Content Area (Arquitectura de Consola)
        self.content_frame = QFrame(); self.content_frame.setObjectName("ContentFrame")
        self.content_layout = QVBoxLayout(self.content_frame); self.content_layout.setContentsMargins(20, 20, 20, 20); self.content_layout.setSpacing(15)
        
        header = QHBoxLayout()
        self.section_title = QLabel("SISTEMA DE CONTROL TÁCTICO"); self.section_title.setObjectName("SectionTitle")
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

        self.btn_dashboard.clicked.connect(lambda: self.switch_page(0, "CENTRO DE MANDO"))
        self.btn_tools.clicked.connect(lambda: self.switch_page(1, "SUITE OPERATIVA"))
        self.btn_settings.clicked.connect(lambda: self.switch_page(2, "CONFIGURACIÓN DEL SISTEMA"))

    def switch_page(self, index, title):
        self.stack.setCurrentIndex(index); self.section_title.setText(title)
        btns = [self.btn_dashboard, self.btn_tools, self.btn_settings]
        for i, b in enumerate(btns):
            b.setProperty("active", "true" if i == index else "false"); b.setStyle(b.style())

    def create_nav_button(self, text, active=False):
        b = QPushButton(text); b.setProperty("class", "NavButton"); b.setProperty("active", str(active).lower()); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(50); return b

    def create_dashboard_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); self.accounts_layout = QGridLayout(cont); self.accounts_layout.setContentsMargins(0, 0, 10, 10); self.accounts_layout.setSpacing(12)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_account_card(self, acc):
        name = acc.get('display_name', acc.get('character'))
        card = QFrame(); card.setObjectName("CharacterCard"); card.setFixedSize(250, 120); card.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(card); l.setContentsMargins(12, 12, 12, 12); l.setSpacing(12)
        avatar = QLabel(); avatar.setObjectName("CharAvatar"); avatar.setFixedSize(50, 50); avatar.setAlignment(Qt.AlignCenter); avatar.setText(name[0].upper())
        info = QVBoxLayout(); name_lbl = QLabel(name.upper()); name_lbl.setObjectName("CharName")
        status = QLabel("● LINK ACTIVE" if acc.get('status') == 'active' else "○ LINK IDLE")
        status.setStyleSheet(f"color: {'#00ff9d' if acc.get('status') == 'active' else '#ffd700'}; font-family: 'Share Tech Mono'; font-size: 9px;")
        isk_h = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h"); isk_h.setStyleSheet("color: #ffd700; font-family: 'Share Tech Mono'; font-size: 11px; font-weight: bold;")
        info.addWidget(name_lbl); info.addWidget(status); info.addStretch(); info.addWidget(isk_h)
        l.addWidget(avatar); l.addLayout(info); card.mousePressEvent = lambda e: self.open_character_detail(acc); return card

    def open_character_detail(self, acc):
        self.current_character = acc; self.update_detail_view(); self.stack.setCurrentIndex(3); self.section_title.setText("PERFIL ESTRATÉGICO")

    def create_detail_page(self):
        p = QFrame(); p.setObjectName("DetailView"); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(20)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setContentsMargins(0, 0, 0, 0); c_l.setSpacing(25)
        
        back = QPushButton("← VOLVER AL MANDO"); back.setObjectName("BackButton"); back.clicked.connect(lambda: self.switch_page(0, "CENTRO DE MANDO"))
        c_l.addWidget(back, 0, Qt.AlignLeft)
        
        # Profile Header (Consola)
        h = QHBoxLayout(); h.setSpacing(20)
        self.detail_avatar = QLabel(); self.detail_avatar.setObjectName("CharAvatar"); self.detail_avatar.setFixedSize(100, 100); self.detail_avatar.setAlignment(Qt.AlignCenter)
        v = QVBoxLayout(); self.detail_name = QLabel("NAME"); self.detail_name.setObjectName("DetailTitle")
        self.detail_status = QLabel("SYSTEM LINK STATUS: ACTIVE"); self.detail_status.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 12px; color: #00ff9d;")
        self.detail_meta = QLabel("DIRECT ACCESS INTERFACE — CORE_VERSION_4.0"); self.detail_meta.setStyleSheet("color: rgba(0, 200, 255, 0.3); font-family: 'Share Tech Mono'; font-size: 9px;")
        v.addWidget(self.detail_name); v.addWidget(self.detail_status); v.addWidget(self.detail_meta); h.addWidget(self.detail_avatar); h.addLayout(v); h.addStretch(); c_l.addLayout(h)
        
        # Impact Metrics
        impact = QHBoxLayout(); impact.setSpacing(20)
        self.box_wallet = self.create_impact_box("WALLET ACUMULADA", "0.00 ISK", "#ffd700")
        self.box_1h = self.create_impact_box("RENDIMIENTO ACTUAL", "0.00 ISK/h", "#00ff9d")
        impact.addWidget(self.box_wallet); impact.addWidget(self.box_1h); c_l.addLayout(impact)
        
        # Matrix Grid
        matrix = QGridLayout(); matrix.setSpacing(15)
        self.box_session_avg = self.create_analytic_box("PROMEDIO SESIÓN", "0.00 ISK/h")
        self.box_session_peak = self.create_analytic_box("PICO MÁXIMO", "0.00 ISK")
        self.box_24h_proj = self.create_analytic_box("PROYECCIÓN 24H", "0.00 ISK")
        self.box_events_count = self.create_analytic_box("SEÑALES DETECTADAS", "0")
        matrix.addWidget(self.box_session_avg, 0, 0); matrix.addWidget(self.box_session_peak, 0, 1)
        matrix.addWidget(self.box_24h_proj, 1, 0); matrix.addWidget(self.box_events_count, 1, 1)
        c_l.addLayout(matrix)
        
        # Modules Split
        bottom = QHBoxLayout(); bottom.setSpacing(20)
        
        # PI Shield
        pi_frame = QFrame(); pi_frame.setObjectName("ModularPI"); pi_frame.setMinimumHeight(200)
        pi_l = QVBoxLayout(pi_frame); pi_l.setContentsMargins(25,25,25,25)
        pi_t = QLabel("PLANETOLOGÍA (PI)"); pi_t.setStyleSheet("font-family: 'Orbitron'; color: #00c8ff; font-weight: bold; font-size: 11px;")
        pi_s = QLabel("MODO: STANDBY — ESPERANDO ESI"); pi_s.setObjectName("PISubtitle")
        pi_desc = QLabel("Módulo táctico en espera. Requiere sincronización con la API de EVE para monitorizar extractores y silos."); pi_desc.setStyleSheet("color: rgba(0, 200, 255, 0.3); font-size: 10px; word-wrap: true; margin-top: 8px;")
        pi_l.addWidget(pi_t); pi_l.addWidget(pi_s); pi_l.addWidget(pi_desc); pi_l.addStretch(); bottom.addWidget(pi_frame, 1)
        
        # Activity Feed
        act_frame = QFrame(); act_frame.setStyleSheet("background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(0, 180, 255, 0.1); border-radius: 4px; padding: 20px;")
        act_l = QVBoxLayout(act_frame); act_l.addWidget(QLabel("REGISTRO DE SEÑALES", styleSheet="font-family: 'Orbitron'; color: #ffffff; font-size: 11px; margin-bottom: 5px;"))
        self.activity_feed = QListWidget(); self.activity_feed.setStyleSheet("background: transparent; border: none; color: rgba(0, 255, 157, 0.6); font-family: 'Share Tech Mono'; font-size: 11px;")
        self.activity_empty = QLabel("SIN ACTIVIDAD DETECTADA EN LOS SENSORES."); self.activity_empty.setObjectName("EmptyStateText"); self.activity_empty.setAlignment(Qt.AlignCenter); self.activity_empty.setWordWrap(True)
        act_l.addWidget(self.activity_feed); act_l.addWidget(self.activity_empty); bottom.addWidget(act_frame, 1)
        
        c_l.addLayout(bottom); scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_impact_box(self, label, value, color_hex):
        b = QFrame(); b.setStyleSheet(f"background: #080808; border: 1px solid rgba(0, 180, 255, 0.15); border-radius: 4px; padding: 15px;")
        b.setMinimumHeight(110)
        l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: rgba(0, 180, 255, 0.4); font-family: 'Share Tech Mono'; font-size: 9px;"))
        v = QLabel(value); v.setObjectName("GlowValue" if color_hex == "#ffd700" else "GlowValueGreen")
        l.addWidget(v); return b

    def create_analytic_box(self, label, value):
        b = QFrame(); b.setObjectName("AnalyticBox"); l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: rgba(0, 180, 255, 0.4); font-family: 'Share Tech Mono'; font-size: 9px; text-transform: uppercase;"))
        v = QLabel(value); v.setObjectName("AnalyticVal"); v.setStyleSheet("font-size: 16px; color: #ffffff; font-family: 'Share Tech Mono';")
        l.addWidget(v); return b

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character; name = acc.get('display_name', acc.get('character'))
        self.detail_name.setText(name.upper()); self.detail_avatar.setText(name[0].upper())
        self.detail_status.setText("SYSTEM LINK STATUS: ACTIVE" if acc.get('status') == 'active' else "SYSTEM LINK STATUS: IDLE")
        
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
                self.activity_feed.addItem(f"[{ts_str}] SEÑAL DETECTADA: +{format_isk(ev['isk'], short=True)}")

    def create_tools_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(0)
        wrapper = QWidget(); wrapper_l = QHBoxLayout(wrapper); wrapper_l.setContentsMargins(0, 20, 0, 0)
        center_cont = QWidget(); center_cont.setMaximumWidth(750); center_l = QVBoxLayout(center_cont); center_l.setContentsMargins(0, 0, 0, 0)
        g = QGridLayout(); g.setSpacing(20); g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        g.addWidget(self.create_tool_card("HUD OVERLAY", "Control visual táctico en juego.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("TRADUCTOR", "Inteligencia lingüística para chats locales.", "🌐", self._on_translator_clicked), 0, 1)
        g.addWidget(self.create_tool_card("REPLICADOR", "Sincronización masiva de ventanas.", "🪟", self._on_replicator_clicked), 1, 0)
        center_l.addLayout(g); center_l.addStretch()
        wrapper_l.addWidget(center_cont); wrapper_l.addStretch()
        l.addWidget(wrapper); return p

    def create_tool_card(self, title, desc, icon, callback):
        c = QFrame(); c.setObjectName("CharacterCard"); c.setFixedSize(340, 130); c.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(c); l.setContentsMargins(20,20,20,20)
        ico = QLabel(icon); ico.setStyleSheet("font-size: 40px;"); l.addWidget(ico)
        v = QVBoxLayout(); t = QLabel(title); t.setObjectName("CharName"); d = QLabel(desc); d.setStyleSheet("color: rgba(0, 200, 255, 0.4); font-family: 'Share Tech Mono'; font-size: 10px; word-wrap: true;")
        v.addWidget(t); v.addWidget(d); l.addLayout(v); c.mousePressEvent = lambda e: callback(); return c

    def create_settings_page(self):
        p = QWidget(); l = QVBoxLayout(p); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setSpacing(20)
        
        g1, l1 = self.create_settings_group("MOTOR EVE iT (CORE)", "Gestión de datos y logs.")
        l1.addWidget(QLabel("DIRECTORIO LOGS:", styleSheet="font-family: 'Share Tech Mono'; color: #00c8ff; font-size: 9px;"))
        path_l = QHBoxLayout(); self.edit_log_dir = QLineEdit(); btn_b = QPushButton("..."); btn_b.setFixedWidth(35); btn_b.clicked.connect(self._on_browse_logs)
        path_l.addWidget(self.edit_log_dir); path_l.addWidget(btn_b); l1.addLayout(path_l)
        self.check_skip_logs = QCheckBox("IGNORAR REGISTROS ANTIGUOS"); l1.addWidget(self.check_skip_logs)
        c_l.addWidget(g1)
        
        g2, l2 = self.create_settings_group("INTERFAZ & HUD", "Ajustes de transparencia y efectos visuales.")
        self.check_blur = QCheckBox("HABILITAR DESENFOQUE (BLUR) PROFUNDO"); l2.addWidget(self.check_blur)
        self.check_hide_hud = QCheckBox("AUTO-OCULTAR HUD SIN ACTIVIDAD"); l2.addWidget(self.check_hide_hud)
        c_l.addWidget(g2)
        
        g3, l3 = self.create_settings_group("AUTOMATIZACIÓN & TRADUCTOR", "Configuración de inteligencia lingüística.")
        l3.addWidget(QLabel("IDIOMA DESTINO:", styleSheet="font-family: 'Share Tech Mono'; color: #00c8ff; font-size: 9px;"))
        self.combo_translator_lang = QComboBox()
        self.combo_translator_lang.addItems(["ESPAÑOL", "ENGLISH", "DEUTSCH", "FRANÇAIS", "RUSSIAN"])
        l3.addWidget(self.combo_translator_lang)
        c_l.addWidget(g3)
        
        c_l.addStretch()
        save = QPushButton("GUARDAR Y SINCRONIZAR SISTEMA"); save.setObjectName("SaveButton"); save.clicked.connect(self.save_settings); c_l.addWidget(save)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_settings_group(self, title, subtitle):
        g = QFrame(); g.setObjectName("SettingsGroup"); l = QVBoxLayout(g); l.setContentsMargins(20,20,20,20)
        t = QLabel(title); t.setStyleSheet("font-family: 'Orbitron'; font-size: 13px; color: #00c8ff; font-weight: bold;")
        s = QLabel(subtitle); s.setStyleSheet("color: rgba(0, 180, 255, 0.4); font-family: 'Share Tech Mono'; font-size: 10px; margin-bottom: 12px;")
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
                card = self.account_cards[name] = self.create_account_card(acc)
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
        self.section_title.setText("SISTEMA SINCRONIZADO"); QTimer.singleShot(2000, lambda: self.section_title.setText("CONFIGURACIÓN DEL SISTEMA"))

    def closeEvent(self, event):
        self.diag_log.info("DIAG: closeEvent detectado.")
        try: QSettings("EVE_iT", "Suite").setValue("geometry", self.saveGeometry())
        except: pass
        if self.tray_manager:
            self.diag_log.info("DIAG: Redirigiendo close a hide (Tray activo).")
            event.ignore(); self.hide()
        else:
            self.diag_log.info("DIAG: Cerrando aplicación (Sin Tray).")
            event.accept()

    def restore_geometry(self):
        try:
            self.diag_log.info("DIAG: Restaurando geometría...")
            s = QSettings("EVE_iT", "Suite")
            geo = s.value("geometry")
            if geo:
                self.restoreGeometry(geo)
                self.diag_log.info(f"DIAG: Geometría cargada. Posición: {self.pos()}")
            
            screen = self.screen()
            if screen:
                geom = self.geometry(); avail = screen.availableGeometry()
                self.diag_log.info(f"DIAG: Ventana: {geom} | Monitor: {avail}")
                if not avail.intersects(geom):
                    self.diag_log.warning("DIAG: Fuera de límites. Reseteando.")
                    self.setGeometry(avail.center().x() - self.width()//2,
                                    avail.center().y() - self.height()//2,
                                    self.width(), self.height())
            self.showNormal()
            self.diag_log.info(f"DIAG: showNormal ejecutado. Visible={self.isVisible()}, Min={self.isMinimized()}")
        except Exception as e:
            self.diag_log.error(f"DIAG: Error en restore_geometry: {e}")

    def show(self):
        self.diag_log.info(f"DIAG: show() llamado. Estado previo: Visible={self.isVisible()}, Min={self.isMinimized()}")
        super().show()
        self.diag_log.info(f"DIAG: show() fin. Visible={self.isVisible()}, Geom={self.geometry()}")

    def showNormal(self):
        self.diag_log.info("DIAG: showNormal() llamado.")
        super().showNormal()

    def showEvent(self, event):
        self.diag_log.info("DIAG: showEvent disparado.")
        super().showEvent(event)

    def hideEvent(self, event):
        self.diag_log.info("DIAG: hideEvent disparado.")
        super().hideEvent(event)

    def apply_styles(self): self.setStyleSheet(MAIN_STYLE)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv); window = MainSuiteWindow(); window.show(); sys.exit(app.exec())
