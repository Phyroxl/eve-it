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
from ui.desktop.components import AnimatedCard, IndustrialBadge
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        import logging
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
            self.diag_log.error(f"ERROR en setup_ui/apply_styles: {e}")
            traceback.print_exc()

        self.load_settings()
        self.restore_geometry()
        
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(2000)

    def apply_styles(self):
        """Aplica la hoja de estilos global a la ventana."""
        self.setStyleSheet(MAIN_STYLE)
        
    def setup_ui(self):
        self.central_widget = QWidget(); self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
        
        # 1. Sidebar (Ancho forzado y verificable)
        self.nav_bar = QFrame(); self.nav_bar.setObjectName("NavBar")
        self.nav_bar.setFixedWidth(240)
        self.nav_layout = QVBoxLayout(self.nav_bar); self.nav_layout.setContentsMargins(0, 0, 0, 0); self.nav_layout.setSpacing(0)
        
        logo = QLabel("EVE iT"); logo.setObjectName("LogoLabel"); self.nav_layout.addWidget(logo)
        self.btn_dashboard = self.create_nav_button("Dashboard", True)
        self.btn_tools = self.create_nav_button("Herramientas")
        self.btn_settings = self.create_nav_button("Configuración")
        
        self.nav_layout.addWidget(self.btn_dashboard); self.nav_layout.addWidget(self.btn_tools)
        self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.btn_settings)
        
        # 2. Content Area (Command Deck Interface)
        self.content_frame = QFrame(); self.content_frame.setObjectName("ContentFrame")
        self.content_layout = QVBoxLayout(self.content_frame); self.content_layout.setContentsMargins(30, 25, 30, 25); self.content_layout.setSpacing(15)
        
        header = QHBoxLayout()
        self.section_title = QLabel("Dashboard"); self.section_title.setObjectName("SectionTitle")
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

        self.btn_dashboard.clicked.connect(lambda: self.switch_page(0, "Dashboard"))
        self.btn_tools.clicked.connect(lambda: self.switch_page(1, "Herramientas"))
        self.btn_settings.clicked.connect(lambda: self.switch_page(2, "Configuración"))

    def switch_page(self, index, title):
        self.stack.setCurrentIndex(index); self.section_title.setText(title)
        btns = [self.btn_dashboard, self.btn_tools, self.btn_settings]
        for i, b in enumerate(btns):
            b.setProperty("active", "true" if i == index else "false"); b.setStyle(b.style())

    def create_nav_button(self, text, active=False):
        b = QPushButton(text); b.setProperty("class", "NavButton"); b.setProperty("active", str(active).lower()); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(44); return b

    def create_dashboard_page(self):
        p = QWidget()
        outer = QVBoxLayout(p)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        # --- Panel de estado del sistema (siempre visible) ---
        self.status_bar = QFrame()
        self.status_bar.setObjectName("AnalyticBox")
        self.status_bar.setFixedHeight(60)
        sb_l = QHBoxLayout(self.status_bar)
        sb_l.setContentsMargins(16, 8, 16, 8)

        self.lbl_tracker_status = QLabel("● Tracker: Inactivo")
        self.lbl_tracker_status.setStyleSheet("color: #718096; font-size: 12px; font-weight: 600;")

        self.lbl_chars_count = QLabel("Personajes: 0")
        self.lbl_chars_count.setStyleSheet("color: #a0aec0; font-size: 12px;")

        self.lbl_last_update = QLabel("Sin datos")
        self.lbl_last_update.setStyleSheet("color: #4a5568; font-size: 11px;")

        sb_l.addWidget(self.lbl_tracker_status)
        sb_l.addSpacing(30)
        sb_l.addWidget(self.lbl_chars_count)
        sb_l.addStretch()
        sb_l.addWidget(self.lbl_last_update)
        outer.addWidget(self.status_bar)

        # --- Área scrollable de tarjetas ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        cont = QWidget()
        cont_l = QVBoxLayout(cont)
        cont_l.setContentsMargins(0, 0, 10, 10)
        cont_l.setSpacing(12)

        # Grid de tarjetas de personajes
        self.cards_container = QWidget()
        self.accounts_layout = QGridLayout(self.cards_container)
        self.accounts_layout.setContentsMargins(0, 0, 0, 0)
        self.accounts_layout.setSpacing(12)
        self.accounts_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        cont_l.addWidget(self.cards_container)

        # Estado vacío (visible cuando no hay personajes)
        self.empty_state = QWidget()
        es_l = QVBoxLayout(self.empty_state)
        es_l.setAlignment(Qt.AlignCenter)
        es_icon = QLabel("📋")
        es_icon.setStyleSheet("font-size: 40px;")
        es_icon.setAlignment(Qt.AlignCenter)
        es_title = QLabel("No hay personajes detectados")
        es_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #a0aec0;")
        es_title.setAlignment(Qt.AlignCenter)
        es_desc = QLabel("Configura el directorio de logs de EVE en la pestaña Configuración\npara comenzar a monitorizar tus personajes.")
        es_desc.setStyleSheet("font-size: 12px; color: #4a5568; line-height: 1.6;")
        es_desc.setAlignment(Qt.AlignCenter)
        es_desc.setWordWrap(True)
        es_l.addWidget(es_icon)
        es_l.addSpacing(8)
        es_l.addWidget(es_title)
        es_l.addSpacing(4)
        es_l.addWidget(es_desc)
        cont_l.addWidget(self.empty_state)
        cont_l.addStretch()

        scroll.setWidget(cont)
        outer.addWidget(scroll)
        return p

    def create_account_card(self, acc):
        name = acc.get('display_name', acc.get('character'))
        card = AnimatedCard()
        card.setFixedSize(240, 120)
        card.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 12, 15, 12)
        
        # Header: Avatar + Identificación
        top = QHBoxLayout()
        avatar = QLabel(name[0].upper())
        avatar.setObjectName("CharAvatar")
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignCenter)
        
        info = QVBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setObjectName("CharName")
        
        is_active = acc.get('status') == 'active'
        status_badge = IndustrialBadge(
            "Activo" if is_active else "Inactivo",
            "#48bb78" if is_active else "#a0aec0"
        )
        
        info.addWidget(name_lbl)
        info.addWidget(status_badge)
        top.addWidget(avatar)
        top.addLayout(info)
        top.addStretch()
        
        # Body: Telemetría de Ingresos
        bot = QHBoxLayout()
        isk_lbl = QLabel("Ingresos Estimados:")
        isk_lbl.setObjectName("MetricLabel")
        
        isk_val = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        isk_val.setObjectName("IskValue")
        
        bot.addWidget(isk_lbl)
        bot.addStretch()
        bot.addWidget(isk_val)
        
        layout.addLayout(top)
        layout.addStretch()
        layout.addLayout(bot)
        
        card.mousePressEvent = lambda e: self.open_character_detail(acc)
        return card

    def open_character_detail(self, acc):
        self.current_character = acc; self.update_detail_view(); self.stack.setCurrentIndex(3); self.section_title.setText("Perfil de Personaje")

    def create_detail_page(self):
        p = QFrame(); p.setObjectName("DetailView"); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(20)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setContentsMargins(0, 0, 0, 0); c_l.setSpacing(25)
        
        back = QPushButton("← Volver"); back.setObjectName("BackButton"); back.clicked.connect(lambda: self.switch_page(0, "Dashboard"))
        c_l.addWidget(back, 0, Qt.AlignLeft)
        
        # Profile Header (Console Diagnostic Panel)
        h = QHBoxLayout(); h.setSpacing(20)
        self.detail_avatar = QLabel(); self.detail_avatar.setObjectName("CharAvatar"); self.detail_avatar.setFixedSize(90, 90); self.detail_avatar.setAlignment(Qt.AlignCenter)
        v = QVBoxLayout(); self.detail_name = QLabel("Nombre"); self.detail_name.setObjectName("DetailTitle")
        self.detail_name.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        self.detail_status = QLabel("Estado: Estable"); self.detail_status.setStyleSheet("font-size: 13px; color: #48bb78;")
        self.detail_meta = QLabel("Monitorización de datos activa"); self.detail_meta.setStyleSheet("color: #718096; font-size: 11px;")
        v.addWidget(self.detail_name); v.addWidget(self.detail_status); v.addWidget(self.detail_meta); h.addWidget(self.detail_avatar); h.addLayout(v); h.addStretch(); c_l.addLayout(h)
        
        # Impact Metrics
        impact = QHBoxLayout(); impact.setSpacing(20)
        self.box_wallet = self.create_impact_box("Wallet Acumulada", "0.00 ISK", "#ecc94b")
        self.box_1h = self.create_impact_box("Rendimiento Actual", "0.00 ISK/h", "#48bb78")
        impact.addWidget(self.box_wallet); impact.addWidget(self.box_1h); c_l.addLayout(impact)
        
        # Matrix Grid
        matrix = QGridLayout(); matrix.setSpacing(15)
        self.box_session_avg = self.create_analytic_box("Promedio Sesión", "0.00 ISK/h")
        self.box_session_peak = self.create_analytic_box("Pico Máximo", "0.00 ISK")
        self.box_24h_proj = self.create_analytic_box("Proyección 24H", "0.00 ISK")
        self.box_events_count = self.create_analytic_box("Señales Detectadas", "0")
        matrix.addWidget(self.box_session_avg, 0, 0); matrix.addWidget(self.box_session_peak, 0, 1)
        matrix.addWidget(self.box_24h_proj, 1, 0); matrix.addWidget(self.box_events_count, 1, 1)
        c_l.addLayout(matrix)
        
        # Modules Split
        bottom = QHBoxLayout(); bottom.setSpacing(20)
        
        # PI Shield
        pi_frame = QFrame(); pi_frame.setObjectName("AnalyticBox"); pi_frame.setMinimumHeight(200)
        pi_l = QVBoxLayout(pi_frame); pi_l.setContentsMargins(20,20,20,20)
        pi_t = QLabel("Planetología (PI)"); pi_t.setStyleSheet("font-size: 14px; color: #63b3ed; font-weight: bold;")
        pi_s = QLabel("Estado: Pendiente"); pi_s.setStyleSheet("color: #718096; font-size: 11px;")
        pi_desc = QLabel("Módulo en espera de sincronización con la API de EVE."); pi_desc.setStyleSheet("color: #4a5568; font-size: 12px; margin-top: 8px;")
        pi_l.addWidget(pi_t); pi_l.addWidget(pi_s); pi_l.addWidget(pi_desc); pi_l.addStretch(); bottom.addWidget(pi_frame, 1)
        
        # Activity Feed
        act_frame = QFrame(); act_frame.setObjectName("AnalyticBox")
        act_l = QVBoxLayout(act_frame); act_l.addWidget(QLabel("REGISTRO DE ACTIVIDAD", styleSheet="font-size: 11px; color: #718096; font-weight: bold; margin-bottom: 5px;"))
        self.activity_feed = QListWidget(); self.activity_feed.setStyleSheet("background: transparent; border: none; color: #e2e8f0; font-size: 12px;")
        self.activity_empty = QLabel("Sin actividad detectada"); self.activity_empty.setObjectName("EmptyStateText"); self.activity_empty.setAlignment(Qt.AlignCenter)
        act_l.addWidget(self.activity_feed); act_l.addWidget(self.activity_empty); bottom.addWidget(act_frame, 1)
        
        c_l.addLayout(bottom); scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_impact_box(self, label, value, color_hex):
        b = QFrame(); b.setObjectName("AnalyticBox")
        b.setMinimumHeight(100)
        l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: #718096; font-size: 12px;"))
        v = QLabel(value); v.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color_hex};")
        l.addWidget(v); return b

    def create_analytic_box(self, label, value):
        b = QFrame(); b.setObjectName("AnalyticBox"); l = QVBoxLayout(b)
        l.addWidget(QLabel(label, styleSheet="color: #718096; font-size: 11px; font-weight: 500;"))
        v = QLabel(value); v.setObjectName("AnalyticVal"); l.addWidget(v); return b

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character; name = acc.get('display_name', acc.get('character'))
        self.detail_name.setText(name.upper()); self.detail_avatar.setText(name[0].upper())
        self.detail_status.setText("● Sensores Activos" if acc.get('status') == 'active' else "○ En Espera")
        
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
        
        # Wrapper centrado con ancho máximo real para cohesión
        wrapper = QWidget(); wrapper_l = QHBoxLayout(wrapper); wrapper_l.setContentsMargins(0, 20, 0, 0)
        
        center_cont = QWidget(); center_cont.setMaximumWidth(750); center_l = QVBoxLayout(center_cont); center_l.setContentsMargins(0, 0, 0, 0)
        g = QGridLayout(); g.setSpacing(20); g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        g.addWidget(self.create_tool_card("HUD Overlay", "Control visual en juego.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("Traductor", "Traducción automática de chats.", "🌐", self._on_translator_clicked), 0, 1)
        g.addWidget(self.create_tool_card("Replicador", "Sincronización de ventanas.", "🪟", self._on_replicator_clicked), 1, 0)
        
        center_l.addLayout(g); center_l.addStretch()
        wrapper_l.addWidget(center_cont); wrapper_l.addStretch() # Ancla el bloque a la izquierda-centro
        
        l.addWidget(wrapper); return p

    def create_tool_card(self, title, desc, icon, callback):
        c = QFrame(); c.setObjectName("CharacterCard"); c.setFixedSize(320, 120); c.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(c); l.setContentsMargins(20,20,20,20)
        ico = QLabel(icon); ico.setStyleSheet("font-size: 32px;"); l.addWidget(ico)
        v = QVBoxLayout(); t = QLabel(title); t.setObjectName("CharName"); d = QLabel(desc); d.setStyleSheet("color: #718096; font-size: 12px;")
        v.addWidget(t); v.addWidget(d); l.addLayout(v); c.mousePressEvent = lambda e: callback(); return c

    def create_settings_page(self):
        p = QWidget(); l = QVBoxLayout(p); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setSpacing(20)
        
        g1, l1 = self.create_settings_group("Motor EVE iT (Core)", "Gestión de datos y registros.")
        l1.addWidget(QLabel("Directorio de Logs:", styleSheet="color: #cbd5e0; font-size: 12px; margin-bottom: 5px;"))
        path_l = QHBoxLayout(); self.edit_log_dir = QLineEdit(); btn_b = QPushButton("..."); btn_b.setFixedWidth(35); btn_b.clicked.connect(self._on_browse_logs)
        path_l.addWidget(self.edit_log_dir); path_l.addWidget(btn_b); l1.addLayout(path_l)
        self.check_skip_logs = QCheckBox("Ignorar registros antiguos"); l1.addWidget(self.check_skip_logs)
        c_l.addWidget(g1)
        
        g2, l2 = self.create_settings_group("Interfaz y HUD", "Ajustes de visibilidad y efectos.")
        self.check_blur = QCheckBox("Habilitar efectos de desenfoque"); l2.addWidget(self.check_blur)
        self.check_hide_hud = QCheckBox("Ocultar HUD automáticamente"); l2.addWidget(self.check_hide_hud)
        c_l.addWidget(g2)
        
        g3, l3 = self.create_settings_group("Automatización y Traductor", "Configuración de idiomas.")
        l3.addWidget(QLabel("Idioma Destino:", styleSheet="color: #cbd5e0; font-size: 12px; margin-bottom: 5px;"))
        self.combo_translator_lang = QComboBox()
        self.combo_translator_lang.addItems(["Español", "English", "Deutsch", "Français", "Russian"])
        l3.addWidget(self.combo_translator_lang)
        c_l.addWidget(g3)
        
        c_l.addStretch()
        save = QPushButton("Guardar Configuración"); save.setObjectName("SaveButton"); save.clicked.connect(self.save_settings); c_l.addWidget(save)
        scroll.setWidget(cont); l.addWidget(scroll); return p

    def create_settings_group(self, title, subtitle):
        g = QFrame(); g.setObjectName("SettingsGroup"); l = QVBoxLayout(g); l.setContentsMargins(20,20,20,20)
        t = QLabel(title); t.setStyleSheet("font-size: 16px; color: #ffffff; font-weight: bold;")
        s = QLabel(subtitle); s.setStyleSheet("color: #718096; font-size: 12px; margin-bottom: 12px;")
        l.addWidget(t); l.addWidget(s); return g, l

    def refresh_data(self):
        # Actualizar estado del sistema en el status bar
        try:
            tracker_running = self.controller and self.controller._tracker is not None
            if tracker_running:
                self.lbl_tracker_status.setText("● Tracker: Activo")
                self.lbl_tracker_status.setStyleSheet("color: #48bb78; font-size: 12px; font-weight: 600;")
            else:
                self.lbl_tracker_status.setText("● Tracker: Inactivo")
                self.lbl_tracker_status.setStyleSheet("color: #718096; font-size: 12px; font-weight: 600;")
        except Exception:
            pass

        if not self.controller or not self.controller._tracker:
            self._show_empty_state(True)
            return
        try:
            summary = self.controller._tracker.get_summary(datetime.now())
            accounts = summary.get('per_character', [])
            self.lbl_chars_count.setText(f"Personajes: {len(accounts)}")
            self.lbl_last_update.setText(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")
            self.update_accounts_view(accounts)
            if self.stack.currentIndex() == 3: self.update_detail_view()
        except Exception as e:
            self.diag_log.error(f"DIAG: Error en refresh_data: {e}")

    def _show_empty_state(self, show: bool):
        """Muestra u oculta el estado vacío y el contenedor de tarjetas."""
        try:
            self.empty_state.setVisible(show)
            self.cards_container.setVisible(not show)
        except Exception:
            pass

    def update_accounts_view(self, accounts):
        if not self.accounts_layout: return

        if not accounts:
            self._show_empty_state(True)
            return

        self._show_empty_state(False)
        names = [acc.get('display_name', acc.get('character')) for acc in accounts]

        # Eliminar tarjetas de personajes que ya no existen
        for name in list(self.account_cards.keys()):
            if name not in names:
                card = self.account_cards.pop(name)
                self.accounts_layout.removeWidget(card)
                card.deleteLater()

        # Añadir o actualizar tarjetas
        for i, acc in enumerate(accounts):
            name = acc.get('display_name', acc.get('character'))
            if name not in self.account_cards:
                card = self.create_account_card(acc)
                self.account_cards[name] = card
                self.accounts_layout.addWidget(card, i // 3, i % 3)
            else:
                card = self.account_cards[name]
                isk_val = card.findChild(QLabel, "IskValue")
                if isk_val:
                    isk_val.setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")

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
        saved_dir = s.value("log_dir", "")

        # Si no hay directorio guardado, intentar auto-detección
        if not saved_dir:
            try:
                from core.log_parser import find_all_log_dirs
                dirs = find_all_log_dirs()
                gamelogs = dirs.get('Gamelogs', [])
                if gamelogs:
                    saved_dir = str(gamelogs[0])
            except Exception:
                pass

        if self.edit_log_dir: self.edit_log_dir.setText(saved_dir)
        if self.check_skip_logs: self.check_skip_logs.setChecked(s.value("skip_logs", "true") == "true")
        if self.check_blur: self.check_blur.setChecked(s.value("enable_blur", "false") == "true")
        if self.check_hide_hud: self.check_hide_hud.setChecked(s.value("auto_hide_hud", "false") == "true")
        if self.combo_translator_lang:
            idx = self.combo_translator_lang.findText(s.value("translator_lang", "Español"))
            if idx >= 0: self.combo_translator_lang.setCurrentIndex(idx)

    def save_settings(self):
        s = QSettings("EVE_iT", "Suite")
        new_log_dir = self.edit_log_dir.text() if self.edit_log_dir else ""
        if self.edit_log_dir: s.setValue("log_dir", new_log_dir)
        if self.check_skip_logs: s.setValue("skip_logs", "true" if self.check_skip_logs.isChecked() else "false")
        if self.check_blur: s.setValue("enable_blur", "true" if self.check_blur.isChecked() else "false")
        if self.check_hide_hud: s.setValue("auto_hide_hud", "true" if self.check_hide_hud.isChecked() else "false")
        if self.combo_translator_lang: s.setValue("translator_lang", self.combo_translator_lang.currentText())

        # Relanzar tracker si el directorio cambió
        if self.controller and new_log_dir:
            try:
                self.controller.set_log_directory(new_log_dir)
                skip = s.value("skip_logs", "true") == "true"
                self.controller.start_tracker(skip_existing=skip)
            except Exception as e:
                self.diag_log.error(f"Error relanzando tracker: {e}")

        self.section_title.setText("Configuración Guardada")
        QTimer.singleShot(2000, lambda: self.section_title.setText("Configuración"))
    def closeEvent(self, event):
        try: QSettings("EVE_iT", "Suite").setValue("geometry", self.saveGeometry())
        except: pass
        event.ignore(); self.hide()
    def restore_geometry(self):
        try:
            self.diag_log.info("DIAG: Restaurando geometría...")
            s = QSettings("EVE_iT", "Suite")
            geo = s.value("geometry")
            if geo:
                self.restoreGeometry(geo)
                self.diag_log.info(f"DIAG: Geometría cargada. Posición actual: {self.pos()}")
                
            # Validación de visibilidad: ¿Está la ventana en algún monitor?
            screen = self.screen()
            if screen:
                geom = self.geometry()
                available = screen.availableGeometry()
                self.diag_log.info(f"DIAG: Geometría ventana: {geom} | Disponible: {available}")
                
                # Si la ventana está totalmente fuera o es invisible por geometría corrupta
                if not available.intersects(geom):
                    self.diag_log.warning("DIAG: Ventana fuera de límites. Reseteando al centro.")
                    self.setGeometry(available.center().x() - self.width()//2,
                                    available.center().y() - self.height()//2,
                                    self.width(), self.height())
            
            self.showNormal()
            self.diag_log.info(f"DIAG: showNormal() ejecutado. Visible={self.isVisible()}, Min={self.isMinimized()}")
        except Exception as e:
            self.diag_log.error(f"DIAG: Error en restore_geometry: {e}")

    def show(self):
        self.diag_log.info(f"DIAG: Llamada a show(). Estado previo: Visible={self.isVisible()}, Min={self.isMinimized()}")
        super().show()
        self.diag_log.info(f"DIAG: show() completado. Estado actual: Visible={self.isVisible()}, Geom={self.geometry()}")

    def showNormal(self):
        self.diag_log.info("DIAG: Llamada a showNormal()")
        super().showNormal()

    def showEvent(self, event):
        self.diag_log.info("DIAG: showEvent disparado por el sistema.")
        super().showEvent(event)

    def hideEvent(self, event):
        self.diag_log.info("DIAG: hideEvent disparado por el sistema.")
        super().hideEvent(event)

    def closeEvent(self, event):
        self.diag_log.info("DIAG: closeEvent detectado.")
        try: QSettings("EVE_iT", "Suite").setValue("geometry", self.saveGeometry())
        except: pass
        
        # Si el tray está activo, ocultar en lugar de cerrar
        if self.tray_manager:
            self.diag_log.info("DIAG: Redirigiendo close a hide (Tray activo).")
            event.ignore()
            self.hide()
        else:
            self.diag_log.info("DIAG: Cerrando aplicación (Sin Tray).")
            event.accept()
