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
        self.setWindowTitle("EVE iT Elite Suite")
        self.resize(960, 680)
        self.setMinimumSize(850, 600)
        
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
        
        # 1. Sidebar (Compact)
        self.nav_bar = QFrame(); self.nav_bar.setObjectName("NavBar")
        self.nav_bar.setFixedWidth(180)
        self.nav_l = QVBoxLayout(self.nav_bar); self.nav_l.setContentsMargins(0, 0, 0, 0); self.nav_l.setSpacing(0)
        
        self.logo = QLabel("EVE iT ELITE"); self.logo.setObjectName("LogoLabel"); self.logo.setAlignment(Qt.AlignCenter)
        self.nav_l.addWidget(self.logo)
        
        self.btn_dashboard = self.create_nav_button("Dashboard", True)
        self.btn_tools = self.create_nav_button("Herramientas")
        self.btn_settings = self.create_nav_button("Configuración")
        
        self.nav_l.addWidget(self.btn_dashboard); self.nav_l.addWidget(self.btn_tools)
        self.nav_l.addStretch()
        self.nav_l.addWidget(self.btn_settings)
        
        # 2. Content Area
        self.content_frame = QFrame(); self.content_frame.setObjectName("ContentFrame")
        self.content_layout = QVBoxLayout(self.content_frame); self.content_layout.setContentsMargins(20, 15, 20, 15)
        
        self.header = QHBoxLayout(); self.section_title = QLabel("Dashboard"); self.section_title.setObjectName("SectionTitle")
        self.header.addWidget(self.section_title); self.header.addStretch()
        self.content_layout.addLayout(self.header)
        
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
        outer.setSpacing(12)

        # --- Panel de resumen global ---
        summary_panel = QHBoxLayout()
        summary_panel.setSpacing(8)
        
        self.total_isk_box = self.create_mini_analytic("TOTAL SESIÓN", "0 ISK", "#ecc94b")
        self.isk_h_box = self.create_mini_analytic("ISK / HORA", "0/h", "#63b3ed")
        self.active_chars_box = self.create_mini_analytic("PERSONAJES", "0", "#48bb78")
        
        summary_panel.addWidget(self.total_isk_box)
        summary_panel.addWidget(self.isk_h_box)
        summary_panel.addWidget(self.active_chars_box)
        outer.addLayout(summary_panel)

        # --- Panel de estado ---
        self.status_bar = QFrame()
        self.status_bar.setObjectName("AnalyticBox")
        self.status_bar.setFixedHeight(35)
        sb_l = QHBoxLayout(self.status_bar)
        sb_l.setContentsMargins(10, 0, 10, 0)

        self.lbl_tracker_status = QLabel("● Tracker: Inactivo")
        self.lbl_tracker_status.setStyleSheet("color: #718096; font-size: 10px; font-weight: 600;")

        self.lbl_last_update = QLabel("Sin datos")
        self.lbl_last_update.setStyleSheet("color: #4a5568; font-size: 9px;")

        sb_l.addWidget(self.lbl_tracker_status)
        sb_l.addStretch()
        sb_l.addWidget(self.lbl_last_update)
        outer.addWidget(self.status_bar)

        # --- Área scrollable ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        cont = QWidget()
        cont_l = QVBoxLayout(cont)
        cont_l.setContentsMargins(0, 0, 5, 0)
        cont_l.setSpacing(15)

        # 1. Grid de personajes
        char_section = QVBoxLayout()
        char_section.addWidget(QLabel("CENTRO DE TELEMETRÍA", objectName="ModuleHeader"))
        self.cards_container = QWidget()
        self.accounts_layout = QGridLayout(self.cards_container)
        self.accounts_layout.setContentsMargins(0, 5, 0, 5)
        self.accounts_layout.setSpacing(8)
        self.accounts_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        char_section.addWidget(self.cards_container)
        cont_l.addLayout(char_section)

        # 2. Global System Log (Para llenar espacio inferior y dar vida)
        log_section = QVBoxLayout()
        log_section.addWidget(QLabel("FEED GLOBAL DE SEÑALES", objectName="ModuleHeader"))
        self.global_log_frame = QFrame(); self.global_log_frame.setObjectName("AnalyticBox")
        gl_l = QVBoxLayout(self.global_log_frame); gl_l.setContentsMargins(10, 10, 10, 10)
        
        self.global_feed = QListWidget()
        self.global_feed.setFrameShape(QFrame.NoFrame); self.global_feed.setStyleSheet("background: transparent; color: #718096; font-size: 9px;")
        self.global_feed.setFixedHeight(180) # Altura fija para el log inferior
        gl_l.addWidget(self.global_feed)
        log_section.addWidget(self.global_log_frame)
        cont_l.addLayout(log_section)

        self.empty_state = QWidget()
        es_l = QVBoxLayout(self.empty_state)
        es_l.setAlignment(Qt.AlignCenter)
        es_icon = QLabel("📋")
        es_icon.setStyleSheet("font-size: 30px;")
        es_title = QLabel("No hay personajes detectados")
        es_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #a0aec0;")
        es_desc = QLabel("Configura el directorio de logs en Configuración.")
        es_desc.setStyleSheet("font-size: 10px; color: #4a5568;")
        es_l.addWidget(es_icon); es_l.addWidget(es_title); es_l.addWidget(es_desc)
        cont_l.addWidget(self.empty_state)
        
        cont_l.addStretch()
        scroll.setWidget(cont)
        outer.addWidget(scroll)
        return p

    def create_mini_analytic(self, label, value, color):
        f = QFrame(); f.setObjectName("AnalyticBox"); f.setFixedHeight(45)
        l = QVBoxLayout(f); l.setContentsMargins(10, 5, 10, 5); l.setSpacing(0)
        lbl = QLabel(label); lbl.setObjectName("MetricLabel"); lbl.setStyleSheet(f"color: {color}; font-size: 8px;")
        val = QLabel(value); val.setObjectName("AnalyticVal"); val.setStyleSheet("font-size: 13px;")
        l.addWidget(lbl); l.addWidget(val)
        return f

    def create_detail_box(self, label, value, color="#718096"):
        f = QFrame(); f.setObjectName("AnalyticBox"); f.setFixedHeight(50)
        l = QVBoxLayout(f); l.setContentsMargins(10, 5, 10, 5); l.setSpacing(0)
        lbl = QLabel(label); lbl.setObjectName("MetricLabel"); lbl.setStyleSheet(f"color: {color}; font-size: 8px;")
        val = QLabel(value); val.setObjectName("AnalyticVal"); val.setStyleSheet("font-size: 12px;")
        l.addWidget(lbl); l.addWidget(val)
        return f

    def create_account_card(self, acc):
        name = acc.get('display_name', acc.get('character'))
        card = AnimatedCard()
        card.setFixedSize(200, 105) # Ligeramente más grande para mejor jerarquía
        card.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)
        
        # Header (Densa)
        top = QHBoxLayout()
        avatar = QLabel(name[0].upper())
        avatar.setObjectName("CharAvatar"); avatar.setFixedSize(32, 32); avatar.setAlignment(Qt.AlignCenter)
        
        info = QVBoxLayout(); info.setSpacing(1); info.setContentsMargins(5, 0, 0, 0)
        name_lbl = QLabel(name.upper()); name_lbl.setObjectName("CharName")
        
        status = acc.get('status', 'idle')
        status_badge = IndustrialBadge("...", "#718096")
        status_badge.setObjectName("StatusBadge")
        
        info.addWidget(name_lbl); info.addWidget(status_badge)
        top.addWidget(avatar); top.addLayout(info); top.addStretch()
        layout.addLayout(top)
        
        layout.addStretch() # Separador visual natural
        
        # Data
        bot = QHBoxLayout()
        v_l = QVBoxLayout(); v_l.setSpacing(0)
        lbl = QLabel("RENDIMIENTO ACTUAL"); lbl.setObjectName("MetricLabel")
        val = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        val.setObjectName("IskValue")
        v_l.addWidget(lbl); v_l.addWidget(val)
        
        bot.addLayout(v_l); bot.addStretch()
        layout.addLayout(bot)
        
        card.mousePressEvent = lambda e: self.open_character_detail(acc)
        return card

    def open_character_detail(self, acc):
        self.current_character = acc; self.update_detail_view(); self.stack.setCurrentIndex(3); self.section_title.setText("Perfil de Personaje")

    def create_detail_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(10)
        
        # Header (Compacto)
        self.detail_header = QFrame(); self.detail_header.setObjectName("AnalyticBox"); self.detail_header.setFixedHeight(50)
        dh_l = QHBoxLayout(self.detail_header); dh_l.setContentsMargins(15, 0, 15, 0)
        
        self.detail_avatar = QLabel(); self.detail_avatar.setObjectName("CharAvatar"); self.detail_avatar.setFixedSize(30, 30); self.detail_avatar.setAlignment(Qt.AlignCenter)
        self.detail_name = QLabel("PERSONAJE"); self.detail_name.setObjectName("CharName"); self.detail_name.setStyleSheet("font-size: 14px;")
        self.detail_status_lbl = QLabel("ESTADO: ---"); self.detail_status_lbl.setStyleSheet("color: #718096; font-size: 9px; font-weight: bold;")
        
        name_v = QVBoxLayout(); name_v.setSpacing(0); name_v.addWidget(self.detail_name); name_v.addWidget(self.detail_status_lbl)
        
        self.btn_back = QPushButton("VOLVER"); self.btn_back.setFixedWidth(70); self.btn_back.setStyleSheet("font-size: 10px; font-weight: bold;"); self.btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        
        dh_l.addWidget(self.detail_avatar); dh_l.addLayout(name_v); dh_l.addStretch(); dh_l.addWidget(self.btn_back)
        l.addWidget(self.detail_header)
        
        # Grid de métricas (Densa)
        metrics_l = QHBoxLayout(); metrics_l.setSpacing(8)
        self.det_isk_total = self.create_detail_box("ISK TOTAL", "0 ISK", "#ecc94b")
        self.det_isk_h = self.create_detail_box("ISK / HORA", "0/h", "#63b3ed")
        self.det_events = self.create_detail_box("SEÑALES", "0", "#48bb78")
        metrics_l.addLayout(self.det_isk_total); metrics_l.addLayout(self.det_isk_h); metrics_l.addLayout(self.det_events)
        l.addLayout(metrics_l)
        
        # Modules Split
        bottom = QHBoxLayout(); bottom.setSpacing(10)
        
        # PI Module (Compacto)
        pi_frame = QFrame(); pi_frame.setObjectName("AnalyticBox")
        pi_l = QVBoxLayout(pi_frame); pi_l.setContentsMargins(12, 12, 12, 12)
        pi_t = QLabel("PLANETOLOGÍA"); pi_t.setObjectName("MetricLabel")
        pi_s = QLabel("Sincronización pendiente..."); pi_s.setStyleSheet("color: #4a5568; font-size: 10px; margin-top: 5px;")
        pi_l.addWidget(pi_t); pi_l.addWidget(pi_s); pi_l.addStretch()
        bottom.addWidget(pi_frame, 1)
        
        # Activity Feed (Compacto)
        act_frame = QFrame(); act_frame.setObjectName("AnalyticBox")
        act_l = QVBoxLayout(act_frame); act_l.setContentsMargins(12, 12, 12, 12)
        act_l.addWidget(QLabel("REGISTRO DE SEÑALES", styleSheet="color: #4a5568; font-size: 9px; font-weight: 800; margin-bottom: 5px;"))
        
        self.activity_feed = QListWidget()
        self.activity_feed.setFrameShape(QFrame.NoFrame); self.activity_feed.setStyleSheet("background: transparent; color: #cbd5e0; font-size: 10px;")
        self.activity_empty = QLabel("Sin actividad."); self.activity_empty.setAlignment(Qt.AlignCenter); self.activity_empty.setStyleSheet("color: #4a5568; font-size: 10px;")
        act_l.addWidget(self.activity_feed); act_l.addWidget(self.activity_empty)
        bottom.addWidget(act_frame, 1)
        
        l.addLayout(bottom, 1)
        return p

    def create_detail_box(self, label, value, color="#718096"):
        box = QVBoxLayout(); box.setSpacing(2)
        lbl = QLabel(label); lbl.setObjectName("MetricLabel"); lbl.setStyleSheet(f"color: {color};")
        val = QLabel(value); val.setObjectName("AnalyticVal"); val.setStyleSheet("font-size: 13px;")
        box.addWidget(lbl); box.addWidget(val)
        
        f = QFrame(); f.setObjectName("AnalyticBox"); f.setLayout(box); f.setFixedHeight(55)
        container = QVBoxLayout(); container.addWidget(f); container.setContentsMargins(0,0,0,0)
        return container

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character
        name = acc.get('display_name', acc.get('character'))
        
        self.detail_name.setText(name.upper())
        self.detail_avatar.setText(name[0].upper())
        
        status = acc.get('status', 'idle')
        if status == 'active':
            self.detail_status_lbl.setText("ESTADO: OPERATIVO"); self.detail_status_lbl.setStyleSheet("color: #48bb78; font-size: 9px; font-weight: bold;")
        elif status == 'idle':
            self.detail_status_lbl.setText("ESTADO: EN ESPERA"); self.detail_status_lbl.setStyleSheet("color: #ecc94b; font-size: 9px; font-weight: bold;")
        else:
            self.detail_status_lbl.setText("ESTADO: INACTIVO"); self.detail_status_lbl.setStyleSheet("color: #718096; font-size: 9px; font-weight: bold;")

        # Actualizar cajas de métricas
        self.det_isk_total.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('total_isk', 0), short=True))
        self.det_isk_h.findChild(QLabel, "AnalyticVal").setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        self.det_events.findChild(QLabel, "AnalyticVal").setText(str(acc.get('event_count', 0)))

        events = acc.get('events', [])
        self.activity_feed.clear()
        if not events:
            self.activity_feed.hide(); self.activity_empty.show()
        else:
            self.activity_empty.hide(); self.activity_feed.show()
            for ev in reversed(events[-15:]):
                ts = ev['timestamp']; ts_str = ts.strftime('%H:%M:%S') if isinstance(ts, datetime) else str(ts)[11:19]
                self.activity_feed.addItem(f"[{ts_str}] +{format_isk(ev['isk'], short=True)}")

    def create_tools_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(0)
        
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        cont = QWidget(); cont_l = QVBoxLayout(cont); cont_l.setContentsMargins(0, 0, 0, 0)
        
        g = QGridLayout(); g.setSpacing(12); g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        g.addWidget(self.create_tool_card("HUD Overlay", "HUD visual táctico.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("Traductor", "Traducción de logs.", "🌐", self._on_translator_clicked), 0, 1)
        g.addWidget(self.create_tool_card("Replicador", "Sincronización.", "🪟", self._on_replicator_clicked), 1, 0)
        
        cont_l.addLayout(g); cont_l.addStretch()
        scroll.setWidget(cont)
        l.addWidget(scroll); return p

    def create_tool_card(self, title, desc, icon, callback):
        c = QFrame(); c.setObjectName("CharacterCard"); c.setFixedSize(220, 80); c.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(c); l.setContentsMargins(12, 12, 12, 12); l.setSpacing(10)
        ico = QLabel(icon); ico.setStyleSheet("font-size: 24px;"); l.addWidget(ico)
        v = QVBoxLayout(); v.setSpacing(2)
        t = QLabel(title); t.setObjectName("CharName")
        d = QLabel(desc); d.setStyleSheet("color: #4a5568; font-size: 10px;")
        v.addWidget(t); v.addWidget(d); l.addLayout(v); l.addStretch()
        c.mousePressEvent = lambda e: callback(); return c

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
        try:
            tracker_running = self.controller and self.controller._tracker is not None
            if tracker_running:
                self.lbl_tracker_status.setText("● Tracker: Activo")
                self.lbl_tracker_status.setStyleSheet("color: #48bb78; font-size: 10px; font-weight: 600;")
            else:
                self.lbl_tracker_status.setText("● Tracker: Inactivo")
                self.lbl_tracker_status.setStyleSheet("color: #718096; font-size: 10px; font-weight: 600;")
        except Exception: pass

        if not self.controller or not self.controller._tracker:
            self._show_empty_state(True)
            return
            
        try:
            summary = self.controller._tracker.get_summary(datetime.now())
            accounts = summary.get('per_character', [])
            
            # Actualizar Summary Global
            self.total_isk_box.findChild(QLabel, "AnalyticVal").setText(format_isk(summary.get('total_isk', 0), short=True))
            self.isk_h_box.findChild(QLabel, "AnalyticVal").setText(format_isk(summary.get('isk_per_hour_rolling', 0), short=True) + "/h")
            self.active_chars_box.findChild(QLabel, "AnalyticVal").setText(str(len(accounts)))
            
            self.lbl_last_update.setText(f"SYNC: {datetime.now().strftime('%H:%M:%S')}")
            self.update_accounts_view(accounts)
            
            # Actualizar feed global
            self.global_feed.clear()
            all_events = []
            for acc in accounts:
                for ev in acc.get('events', []):
                    all_events.append((ev['timestamp'], acc.get('display_name'), ev['isk']))
            
            all_events.sort(key=lambda x: x[0], reverse=True)
            for ts, name, isk in all_events[:20]:
                ts_str = ts.strftime('%H:%M:%S') if isinstance(ts, datetime) else str(ts)[11:19]
                self.global_feed.addItem(f"[{ts_str}] {name.upper()}: +{format_isk(isk, short=True)}")
            
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
            status = acc.get('status', 'idle')

            if name not in self.account_cards:
                card = self.create_account_card(acc)
                self.account_cards[name] = card
                self.accounts_layout.addWidget(card, i // 3, i % 3)
            else:
                card = self.account_cards[name]
                # Actualizar ISK
                isk_val = card.findChild(QLabel, "IskValue")
                if isk_val:
                    isk_val.setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
                # Actualizar badge de estado
                badge = card.findChild(QLabel, "StatusBadge")
                if badge:
                    if status == 'active':
                        badge.setText("Activo")
                        badge.setStyleSheet("background-color: rgba(72,187,120,0.1); color: #48bb78; border: 1px solid rgba(72,187,120,0.3); padding: 2px 8px; font-size: 10px; font-weight: 600; border-radius: 10px;")
                    elif status == 'idle':
                        badge.setText("En espera")
                        badge.setStyleSheet("background-color: rgba(236,201,75,0.1); color: #ecc94b; border: 1px solid rgba(236,201,75,0.3); padding: 2px 8px; font-size: 10px; font-weight: 600; border-radius: 10px;")
                    else:
                        badge.setText("Inactivo")
                        badge.setStyleSheet("background-color: rgba(113,128,150,0.1); color: #718096; border: 1px solid rgba(113,128,150,0.3); padding: 2px 8px; font-size: 10px; font-weight: 600; border-radius: 10px;")

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
