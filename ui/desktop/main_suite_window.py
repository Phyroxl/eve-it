from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QPushButton, QStackedWidget,
    QScrollArea, QGridLayout, QLineEdit, QCheckBox,
    QDoubleSpinBox, QComboBox, QFileDialog, QSpacerItem, QSizePolicy,
    QListWidget, QProgressBar
)
from PySide6.QtCore import Qt, QSize, QTimer, QSettings, QUrl, QPoint
from PySide6.QtGui import QColor, QIcon, QFont, QLinearGradient, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import sys
from datetime import datetime, timedelta

from ui.desktop.styles import MAIN_STYLE
from ui.desktop.components import AnimatedCard, IndustrialBadge, TelemetryChart
from utils.formatters import format_isk


class _TitleBar(QWidget):
    """Custom frameless titlebar for MainSuiteWindow."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setObjectName("CustomTitleBar")
        self.setStyleSheet("""
            QWidget#CustomTitleBar {
                background-color: #0b1016;
                border-bottom: 1px solid #1e293b;
            }
            QLabel#TitleLabel {
                color: #00c8ff;
                font-size: 10px;
                font-weight: 900;
                letter-spacing: 2px;
            }
            QPushButton#TitleMinBtn, QPushButton#TitleCloseBtn {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 3px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#TitleMinBtn:hover {
                background-color: #1e293b;
                color: #e2e8f0;
            }
            QPushButton#TitleCloseBtn:hover {
                background-color: rgba(239, 68, 68, 0.2);
                border-color: #ef4444;
                color: #ef4444;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(4)

        self.lbl_title = QLabel("SALVA SUITE")
        self.lbl_title.setObjectName("TitleLabel")
        lay.addWidget(self.lbl_title)
        lay.addStretch()

        self.btn_min = QPushButton("−")
        self.btn_min.setObjectName("TitleMinBtn")
        self.btn_min.setFixedSize(20, 18)
        self.btn_min.setCursor(Qt.PointingHandCursor)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("TitleCloseBtn")
        self.btn_close.setFixedSize(20, 18)
        self.btn_close.setCursor(Qt.PointingHandCursor)

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_close)

        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        import logging
        self.diag_log = logging.getLogger('eve.suite.diag')
        self.diag_log.info("DIAG: Instanciando MainSuiteWindow...")

        self.controller = controller
        self.tray_manager = None
        self.setWindowTitle("Salva Suite")
        # Tamaño fijo: el mínimo es igual al máximo
        self.setFixedSize(960, 680)

        # Frameless window — keep Qt.Window so taskbar icon is visible
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.Window)
        
        self.account_cards = {}
        self.current_character = None 
        self.network_manager = QNetworkAccessManager(self)
        
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
        outer_layout = QVBoxLayout(self.central_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Custom Titlebar
        self._titlebar = _TitleBar(self)
        self._titlebar.btn_min.clicked.connect(self.showMinimized)
        self._titlebar.btn_close.clicked.connect(self._action_logoff)
        outer_layout.addWidget(self._titlebar)

        # Content area below titlebar
        content_widget = QWidget()
        self.main_layout = QHBoxLayout(content_widget); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
        outer_layout.addWidget(content_widget, 1)

        # 1. Sidebar (Compact)
        self.nav_bar = QFrame(); self.nav_bar.setObjectName("NavBar")
        self.nav_bar.setFixedWidth(180)
        self.nav_l = QVBoxLayout(self.nav_bar); self.nav_l.setContentsMargins(0, 0, 0, 0); self.nav_l.setSpacing(0)

        self.logo = QLabel("SALVA SUITE"); self.logo.setObjectName("LogoLabel"); self.logo.setAlignment(Qt.AlignCenter)
        self.nav_l.addWidget(self.logo)
        
        self.btn_dashboard = self.create_nav_button("Dashboard", True)
        self.btn_tools = self.create_nav_button("Herramientas")
        self.btn_settings = self.create_nav_button("Configuración")
        
        self.nav_l.addWidget(self.btn_dashboard)
        self.nav_l.addWidget(self.btn_tools)
        self.nav_l.addStretch()
        
        # Botón de Configuración
        self.nav_l.addWidget(self.btn_settings)
        
        # Botón de Logoff (Cierre total)
        self.btn_exit = self.create_nav_button("Logoff")
        self.btn_exit.setStyleSheet("QPushButton { color: #ef4444; font-weight: 800; border-top: 1px solid rgba(255,0,0,0.1); } QPushButton:hover { background: rgba(239, 68, 68, 0.1); }")
        self.btn_exit.clicked.connect(self._action_logoff)
        self.nav_l.addWidget(self.btn_exit)
        
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
        
        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_tools)
        self.stack.addWidget(self.page_settings)
        self.stack.addWidget(self.page_detail)
        
        self.content_layout.addWidget(self.stack)
        self.main_layout.addWidget(self.nav_bar); self.main_layout.addWidget(self.content_frame, 1)

        self.btn_dashboard.clicked.connect(lambda: self.switch_page(0, "Dashboard"))
        self.btn_tools.clicked.connect(lambda: self.switch_page(1, "Herramientas"))
        self.btn_settings.clicked.connect(lambda: self.switch_page(2, "Configuración"))

    def switch_page(self, index, title):
        self.stack.setCurrentIndex(index); self.section_title.setText(title)
        
        idx_to_btn = {0: self.btn_dashboard, 1: self.btn_tools, 2: self.btn_settings}
        
        for idx, b in idx_to_btn.items():
            if b:
                b.setProperty("active", "true" if idx == index else "false")
                b.setStyle(b.style())

    def create_nav_button(self, text, active=False):
        b = QPushButton(text); b.setProperty("class", "NavButton"); b.setProperty("active", str(active).lower()); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(44); return b

    def create_dashboard_page(self):
        p = QWidget()
        outer = QVBoxLayout(p)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # --- Panel de resumen global (Command Center Style) ---
        summary_panel = QHBoxLayout()
        summary_panel.setSpacing(10)
        
        # Módulos de estado de la flota (Fila 1 - Táctica)
        self.fleet_status_box = self.create_mini_analytic("ESTADO DE FLOTA", "0/0 ONLINE", "#60a5fa")
        self.elite_pilot_box = self.create_mini_analytic("ELITE PILOT", "---", "#fbbf24")
        self.total_isk_box = self.create_mini_analytic("TOTAL SESIÓN", "0 ISK", "#cbd5e1")
        self.isk_h_box = self.create_mini_analytic("ISK / HORA", "0/h", "#10b981")
        self.next_tick_box = self.create_mini_analytic("NEXT TICK ETA", "--:--", "#63b3ed")
        self.signals_box = self.create_mini_analytic("SEÑALES", "0", "#48bb78")
        
        summary_panel.addWidget(self.fleet_status_box)
        summary_panel.addWidget(self.elite_pilot_box)
        summary_panel.addWidget(self.total_isk_box)
        summary_panel.addWidget(self.isk_h_box)
        summary_panel.addWidget(self.next_tick_box)
        summary_panel.addWidget(self.signals_box)
        outer.addLayout(summary_panel)

        # Gráfico de Telemetría de Sesión (NUEVO)
        chart_v = QVBoxLayout(); chart_v.setSpacing(5); chart_v.setContentsMargins(0, 5, 0, 0)
        chart_v.addWidget(QLabel("TELEMETRÍA DE SESIÓN (ISK ACUMULADO)", objectName="ModuleHeader"))
        self.perf_chart = TelemetryChart()
        chart_v.addWidget(self.perf_chart)
        outer.addLayout(chart_v)

        # --- Panel de estado (Command Center Style) ---
        self.status_bar = QFrame()
        self.status_bar.setObjectName("AnalyticBox")
        self.status_bar.setFixedHeight(30)
        sb_l = QHBoxLayout(self.status_bar)
        sb_l.setContentsMargins(12, 0, 12, 0)

        self.lbl_tracker_status = QLabel("● SISTEMA ACTIVO")
        self.lbl_tracker_status.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 800; letter-spacing: 1px;")

        self.lbl_last_update = QLabel("SINCRONIZACIÓN: --:--:--")
        self.lbl_last_update.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")

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

        # Secciones Inferiores: Timeline e Insights
        bottom_row = QHBoxLayout(); bottom_row.setSpacing(15)

        # 1. ACTIVITY TIMELINE
        tl_v = QVBoxLayout(); tl_v.setSpacing(5)
        tl_v.addWidget(QLabel("ACTIVITY TIMELINE", objectName="ModuleHeader"))
        self.tl_frame = QFrame(); self.tl_frame.setObjectName("AnalyticBox")
        tl_l = QVBoxLayout(self.tl_frame); tl_l.setContentsMargins(10, 10, 10, 10)
        self.global_feed = QListWidget() # Reutilizamos nombre para compatibilidad
        self.global_feed.setFrameShape(QFrame.NoFrame)
        self.global_feed.setStyleSheet("background: transparent; color: #cbd5e1; font-size: 9px;")
        self.global_feed.setFixedHeight(180)
        tl_l.addWidget(self.global_feed)
        tl_v.addWidget(self.tl_frame)
        bottom_row.addLayout(tl_v, 2)

        # 2. FLEET INSIGHTS
        fi_v = QVBoxLayout(); fi_v.setSpacing(5)
        fi_v.addWidget(QLabel("FLEET INSIGHTS", objectName="ModuleHeader"))
        self.fi_frame = QFrame(); self.fi_frame.setObjectName("AnalyticBox")
        fi_l = QVBoxLayout(self.fi_frame); fi_l.setContentsMargins(15, 15, 15, 15); fi_l.setSpacing(10)
        
        self.insight_top_pilot = self.create_insight_item("PILOTO ÉLITE", "---", "#fbbf24")
        self.insight_max_isk = self.create_insight_item("PICO RENDIMIENTO", "0 ISK/H", "#63b3ed")
        self.insight_idle = self.create_insight_item("PILOTOS EN ESPERA", "0", "#f87171")
        self.insight_active_time = self.create_insight_item("DURACIÓN SESIÓN", "00:00:00", "#10b981")
        
        fi_l.addWidget(self.insight_top_pilot)
        fi_l.addWidget(self.insight_max_isk)
        fi_l.addWidget(self.insight_idle)
        fi_l.addWidget(self.insight_active_time)
        fi_l.addStretch()
        
        fi_v.addWidget(self.fi_frame)
        bottom_row.addLayout(fi_v, 1)

        # 3. SUITE STATUS (NUEVO)
        ss_v = QVBoxLayout(); ss_v.setSpacing(5)
        ss_v.addWidget(QLabel("SUITE STATUS", objectName="ModuleHeader"))
        self.ss_frame = QFrame(); self.ss_frame.setObjectName("AnalyticBox")
        ss_l = QVBoxLayout(self.ss_frame); ss_l.setContentsMargins(15, 15, 15, 15); ss_l.setSpacing(12)
        
        self.st_tracker = self.create_status_item("TRACKER CORE")
        self.st_overlay = self.create_status_item("HUD OVERLAY")
        self.st_translator = self.create_status_item("CHAT TRANSLATOR")
        self.st_replicator = self.create_status_item("REPLICATOR")
        self.st_esi = self.create_status_item("ESI IDENTITY")
        
        ss_l.addWidget(self.st_tracker)
        ss_l.addWidget(self.st_overlay)
        ss_l.addWidget(self.st_translator)
        ss_l.addWidget(self.st_replicator)
        ss_l.addWidget(self.st_esi)
        ss_l.addStretch()
        
        ss_v.addWidget(self.ss_frame)
        bottom_row.addLayout(ss_v, 1)

        # 4. QUICK ACTIONS (NUEVO)
        qa_v = QVBoxLayout(); qa_v.setSpacing(5)
        qa_v.addWidget(QLabel("QUICK ACTIONS", objectName="ModuleHeader"))
        self.qa_frame = QFrame(); self.qa_frame.setObjectName("AnalyticBox")
        qa_l = QVBoxLayout(self.qa_frame); qa_l.setContentsMargins(15, 15, 15, 15); qa_l.setSpacing(10)
        
        self.btn_hud = self.create_action_button("Toggle HUD", "👁", self.controller.toggle_overlay)
        
        # Perfiles Rápidos (NUEVO)
        self.btn_prof_pve = self.create_action_button("Profile: PvE", "⚔", lambda: self._apply_profile("PvE"))
        self.btn_prof_pvp = self.create_action_button("Profile: PvP", "🛡", lambda: self._apply_profile("PvP"))
        self.btn_prof_farm = self.create_action_button("Profile: Farm", "💰", lambda: self._apply_profile("Farm Focus"))
        
        self.btn_reset = self.create_action_button("Reset Session", "↺", self._action_reset)
        self.btn_refresh = self.create_action_button("Force Sync", "⚡", self.refresh_data)
        
        qa_l.addWidget(self.btn_hud)
        qa_l.addWidget(self.btn_prof_pve)
        qa_l.addWidget(self.btn_prof_pvp)
        qa_l.addWidget(self.btn_prof_farm)
        qa_l.addWidget(self.btn_reset)
        qa_l.addWidget(self.btn_refresh)
        qa_l.addStretch()
        
        qa_v.addWidget(self.qa_frame)
        bottom_row.addLayout(qa_v, 1)

        cont_l.addLayout(bottom_row)

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

    def create_insight_item(self, label, value, color):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(1)
        lbl = QLabel(label); lbl.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: 800; letter-spacing: 0.5px;")
        val = QLabel(value); val.setObjectName("InsightVal"); val.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 600;")
        l.addWidget(lbl); l.addWidget(val); return w

    def create_status_item(self, label):
        from ui.common.theme import Theme
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        dot = QLabel("●"); dot.setObjectName("StatusDot")
        dot.setStyleSheet(f"color: {Theme.TEXT_DIM}; font-size: 12px;") # Default gray
        lbl = QLabel(label.upper()); lbl.setStyleSheet(f"color: {Theme.TEXT_DIM}; font-size: 8px; font-weight: 700; letter-spacing: 0.5px;")
        l.addWidget(dot); l.addWidget(lbl); l.addStretch()
        return w

    def create_action_button(self, text, icon_text, callback):
        from ui.common.theme import Theme
        btn = QPushButton(f" {icon_text}  {text.upper()}")
        btn.setObjectName("ActionButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton#ActionButton {{
                background-color: {Theme.BG_PANEL};
                border: 1px solid {Theme.BORDER};
                color: {Theme.TEXT_MAIN};
                font-size: 9px;
                font-weight: 800;
                padding: 8px 12px;
                text-align: left;
                border-radius: 2px;
                letter-spacing: 0.5px;
            }}
            QPushButton#ActionButton:hover {{
                background-color: {Theme.ACCENT_LOW};
                border-color: {Theme.ACCENT};
                color: {Theme.ACCENT};
            }}
            QPushButton#ActionButton:pressed {{
                background-color: {Theme.ACCENT};
                color: black;
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def create_mini_analytic(self, label, value, color):
        from ui.common.theme import Theme
        f = QFrame(); f.setObjectName("MetricCard"); f.setFixedHeight(45)
        l = QVBoxLayout(f); l.setContentsMargins(10, 5, 10, 5); l.setSpacing(0)
        lbl = QLabel(label); lbl.setObjectName("MetricTitle"); lbl.setStyleSheet(f"color: {color};")
        val = QLabel(value); val.setObjectName("MetricValue")
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
        card.setFixedSize(210, 105)
        card.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)
        
        # Header: Identidad
        top = QHBoxLayout(); top.setSpacing(12)
        
        # Avatar Técnico (Estructura preparada para imagen real)
        self.avatar_frame = QFrame()
        self.avatar_frame.setObjectName("CharAvatar")
        self.avatar_frame.setFixedSize(38, 38)
        af_l = QVBoxLayout(self.avatar_frame); af_l.setContentsMargins(0,0,0,0)
        
        self.avatar_img = QLabel()
        self.avatar_img.setObjectName("CharPortrait") # ID para futuras actualizaciones
        self.avatar_img.setAlignment(Qt.AlignCenter)
        
        id_status = acc.get('id_status', 'pending')
        portrait_url = acc.get('portrait_url')
        
        # Tooltip técnico discreto
        status_map = {
            'resolved': 'PORTRAIT READY',
            'resolving': 'RESOLVING IDENTITY',
            'pending': 'NO PORTRAIT',
            'failed': 'IDENTITY FAILED'
        }
        self.avatar_img.setToolTip(status_map.get(id_status, 'UNKNOWN'))

        if portrait_url:
            # Preparado para carga asíncrona
            self._load_portrait_async(self.avatar_img, portrait_url, name[0].upper())
        else:
            self._apply_fallback_avatar(self.avatar_img, name[0].upper())
        
        af_l.addWidget(self.avatar_img)
        
        info = QVBoxLayout(); info.setSpacing(1); info.setContentsMargins(0, 2, 0, 0)
        name_lbl = QLabel(name.upper()); name_lbl.setObjectName("CharName")
        
        metrics_row = QHBoxLayout(); metrics_row.setSpacing(8)
        isk_val = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        isk_val.setObjectName("IskValue"); isk_val.setStyleSheet("font-size: 11px; font-weight: 700; color: #10b981;")
        
        sess_val = QLabel(format_isk(acc.get('total_isk', 0), short=True))
        sess_val.setObjectName("SessionIsk"); sess_val.setStyleSheet("font-size: 10px; color: #718096;")
        
        metrics_row.addWidget(isk_val); metrics_row.addWidget(sess_val); metrics_row.addStretch()
        
        info.addWidget(name_lbl); info.addLayout(metrics_row); info.addStretch()
        top.addWidget(self.avatar_frame); top.addLayout(info); top.addStretch()
        layout.addLayout(top)
        
        # Middle: Telemetry row (NUEVO)
        mid = QHBoxLayout(); mid.setSpacing(12); mid.setContentsMargins(0, 4, 0, 4)
        
        last_tick_lbl = QLabel("LAST: ---")
        last_tick_lbl.setObjectName("LastTick"); last_tick_lbl.setStyleSheet("color: #94a3b8; font-size: 8px; font-weight: 700;")
        
        dur_lbl = QLabel("UPTIME: --:--:--")
        dur_lbl.setObjectName("CharDuration"); dur_lbl.setStyleSheet("color: #94a3b8; font-size: 8px; font-weight: 700;")
        
        mid.addWidget(last_tick_lbl); mid.addWidget(dur_lbl); mid.addStretch()
        layout.addLayout(mid)

        layout.addStretch()
        
        # Footer: Telemetría de Estado
        bot = QHBoxLayout(); bot.setContentsMargins(0, 5, 0, 0)
        self.status_badge = IndustrialBadge("IDENTIFICANDO...", "#64748b")
        self.status_badge.setObjectName("StatusBadge")
        bot.addWidget(self.status_badge); bot.addStretch()
        
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
        metrics_l.addWidget(self.det_isk_total); metrics_l.addWidget(self.det_isk_h); metrics_l.addWidget(self.det_events)
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
        f = QFrame(); f.setObjectName("AnalyticBox"); f.setFixedHeight(55)
        l = QVBoxLayout(f); l.setContentsMargins(10, 5, 10, 5); l.setSpacing(0)
        lbl = QLabel(label); lbl.setObjectName("MetricLabel"); lbl.setStyleSheet(f"color: {color}; font-size: 8px;")
        val = QLabel(value); val.setObjectName("AnalyticVal"); val.setStyleSheet("font-size: 13px;")
        l.addWidget(lbl); l.addWidget(val)
        return f

    def update_detail_view(self):
        if not self.current_character: return
        acc = self.current_character
        name = acc.get('display_name', acc.get('character'))
        
        self.detail_name.setText(name.upper())
        self.detail_avatar.setText(name[0].upper())
        
        status = acc.get('status', 'idle')
        if status == 'active':
            self.detail_status_lbl.setText("SISTEMA: OPERATIVO"); self.detail_status_lbl.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 800;")
        elif status == 'idle':
            self.detail_status_lbl.setText("SISTEMA: EN ESPERA"); self.detail_status_lbl.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 800;")
        else:
            self.detail_status_lbl.setText("SISTEMA: INACTIVO"); self.detail_status_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")

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
        
        g = QGridLayout(); g.setSpacing(15); g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # Fila 1
        g.addWidget(self.create_tool_card("HUD Overlay", "HUD visual táctico.", "🕹️", self._on_hud_clicked), 0, 0)
        g.addWidget(self.create_tool_card("Traductor", "Traducción de logs.", "🌐", self._on_translator_clicked), 0, 1)
        g.addWidget(self.create_tool_card("Replicador", "Sincronización.", "🪟", self._on_replicator_clicked), 0, 2)
        
        # Fila 2
        g.addWidget(self.create_tool_card("Market Command", "Station Trading AI.", "📈", self._on_market_clicked), 1, 0)
        g.addWidget(self.create_tool_card("Visual Clon", "Copia el layout visual de un personaje a otros.", "🖥️", self._on_visual_clon_clicked), 1, 1)
        g.addWidget(self.create_tool_card("Intel Alert", "Hostiles en Local / Intel.", "⚠️", self._on_intel_alert_clicked), 1, 2)

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
        cont = QWidget(); c_l = QVBoxLayout(cont); c_l.setSpacing(15); c_l.setContentsMargins(0, 5, 5, 5)
        
        # Grupo 1
        g1 = QFrame(); g1.setObjectName("SettingsGroup"); g1_l = QVBoxLayout(g1)
        g1_l.addWidget(QLabel("NÚCLEO OPERATIVO", objectName="ModuleHeader"))
        g1_l.addWidget(QLabel("Ruta de logs de EVE Online:", styleSheet="color: #64748b; font-size: 10px; margin-top: 5px;"))
        path_l = QHBoxLayout(); self.edit_log_dir = QLineEdit(); btn_b = QPushButton("..."); btn_b.setFixedWidth(30); btn_b.clicked.connect(self._on_browse_logs)
        path_l.addWidget(self.edit_log_dir); path_l.addWidget(btn_b); g1_l.addLayout(path_l)
        self.check_skip_logs = QCheckBox("Ignorar registros históricos"); g1_l.addWidget(self.check_skip_logs)
        c_l.addWidget(g1)
        
        # Grupo 2
        g2 = QFrame(); g2.setObjectName("SettingsGroup"); g2_l = QVBoxLayout(g2)
        g2_l.addWidget(QLabel("TELEMETRÍA Y HUD", objectName="ModuleHeader"))
        
        g2_l.addWidget(QLabel("Preset de HUD táctico:", styleSheet="color: #64748b; font-size: 10px; margin-top: 5px;"))
        self.combo_hud_preset = QComboBox()
        self.combo_hud_preset.addItems(["BALANCED", "COMPACT", "FOCUS"])
        g2_l.addWidget(self.combo_hud_preset)

        self.check_blur = QCheckBox("Efecto de transparencia avanzado"); g2_l.addWidget(self.check_blur)
        self.check_hide_hud = QCheckBox("Ocultación automática de HUD"); g2_l.addWidget(self.check_hide_hud)
        
        g2_l.addWidget(QLabel("VISIBILIDAD HUD:", styleSheet="color: #64748b; font-size: 8px; margin-top: 8px; font-weight: bold;"))
        self.check_hud_total = QCheckBox("Mostrar ISK Total"); g2_l.addWidget(self.check_hud_total)
        self.check_hud_tick = QCheckBox("Mostrar Siguiente Tick"); g2_l.addWidget(self.check_hud_tick)
        self.check_hud_dur = QCheckBox("Mostrar Duración"); g2_l.addWidget(self.check_hud_dur)

        c_l.addWidget(g2)
        
        # Grupo 3
        g3 = QFrame(); g3.setObjectName("SettingsGroup"); g3_l = QVBoxLayout(g3)
        g3_l.addWidget(QLabel("MOTOR DE TRADUCCIÓN", objectName="ModuleHeader"))
        self.combo_translator_lang = QComboBox()
        self.combo_translator_lang.addItems(["Español", "English", "Deutsch", "Français", "Russian"])
        g3_l.addWidget(self.combo_translator_lang)
        c_l.addWidget(g3)
        
        c_l.addStretch()
        save = QPushButton("Guardar Cambios"); save.setObjectName("SaveButton"); save.clicked.connect(self.save_settings); c_l.addWidget(save)
        scroll.setWidget(cont); l.addWidget(scroll); return p

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
            # Si el tracker está intentando arrancar, esperamos un poco antes de mostrar vacío
            self._show_empty_state(True)
            return
            
        try:
            summary = self.controller._tracker.get_summary(datetime.now())
            accounts = summary.get('per_character', [])
            
            # Si hay personajes pero el tracker acaba de empezar, dale un ciclo de gracia
            if not accounts and self.controller.state.tracker_running:
                # No mostramos "vacio" inmediatamente si el tracker está activo (puede estar escaneando)
                pass 
            elif not accounts:
                self._show_empty_state(True)
                return
            
            self._show_empty_state(False)
            
            # Actualizar Summary Global
            self.total_isk_box.findChild(QLabel, "AnalyticVal").setText(format_isk(summary.get('total_isk', 0), short=True))
            self.isk_h_box.findChild(QLabel, "AnalyticVal").setText(format_isk(summary.get('isk_per_hour_rolling', 0), short=True) + "/h")
            
            # Fleet Status mejorado (X/Y Pilots)
            online = summary.get('online_count', 0)
            total = summary.get('total_pilots', 0)
            self.fleet_status_box.findChild(QLabel, "AnalyticVal").setText(f"{online}/{total} PILOTOS")
            
            # Elite Pilot (Top ISK)
            elite_name = "---"
            if accounts:
                elite_p = max(accounts, key=lambda x: x.get('total_isk', 0))
                elite_name = elite_p.get('display_name', '---').upper()
            self.elite_pilot_box.findChild(QLabel, "AnalyticVal").setText(elite_name)
            
            # Next Tick ETA (Mínimo de todos los personajes activos)
            next_tick_str = "--:--"
            active_etas = [acc.get('last_tick', {}).get('secs_until_next', 0) for acc in accounts if acc.get('status') == 'active']
            if active_etas:
                min_eta = min(active_etas)
                next_tick_str = f"{min_eta//60:02d}:{min_eta%60:02d}"
            self.next_tick_box.findChild(QLabel, "AnalyticVal").setText(next_tick_str)

            # Contador de señales (ISK Events)
            total_signals = sum(acc.get('event_count', 0) for acc in accounts)
            self.signals_box.findChild(QLabel, "AnalyticVal").setText(str(total_signals))
            
            self.lbl_last_update.setText(f"TELEMETRÍA SYNC: {datetime.now().strftime('%H:%M:%S')}")
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
                item = f"[{ts_str}] {name.upper()}: +{format_isk(isk, short=True)}"
                self.global_feed.addItem(item)
            
            # Actualizar FLEET INSIGHTS
            if accounts:
                top_p = max(accounts, key=lambda x: x.get('total_isk', 0))
                self.insight_top_pilot.findChild(QLabel, "InsightVal").setText(top_p.get('display_name', '---').upper())
                
                max_isk = max(accounts, key=lambda x: x.get('isk_per_hour', 0))
                self.insight_max_isk.findChild(QLabel, "InsightVal").setText(format_isk(max_isk.get('isk_per_hour', 0), short=True) + "/H")
                
                idle_count = sum(1 for acc in accounts if acc.get('status') == 'idle')
                self.insight_idle.findChild(QLabel, "InsightVal").setText(str(idle_count))
                
                duration_secs = summary.get('session_duration_seconds', 0)
                from utils.formatters import format_duration
                from datetime import timedelta
                self.insight_active_time.findChild(QLabel, "InsightVal").setText(format_duration(timedelta(seconds=duration_secs)))

            # Actualizar SUITE STATUS
            st = self.controller.state
            self._update_status_indicator(self.st_tracker, st.tracker_running)
            self._update_status_indicator(self.st_overlay, st.overlay_active)
            self._update_status_indicator(self.st_translator, getattr(self.controller, '_translator_overlay', None) is not None)
            self._update_status_indicator(self.st_replicator, st.replicator_active)
            
            # Lógica ESI Identity
            if self.controller and self.controller._tracker:
                accs = self.controller._tracker.sessions.values()
                if not accs:
                    self._update_status_indicator(self.st_esi, False)
                else:
                    all_ok = all(a.id_status == 'resolved' for a in accs)
                    any_fail = any(a.id_status == 'failed' for a in accs)
                    if any_fail: self._update_status_indicator(self.st_esi, "degraded")
                    else: self._update_status_indicator(self.st_esi, all_ok)

            # Actualizar Mini Gráfico (NUEVO)
            if self.controller and self.controller._tracker:
                hist = self.controller._tracker.get_isk_history_for_chart()
                if hist:
                    vals = [h['total_isk'] for h in hist]
                    # Si solo hay un punto o valores planos, añadir un 0 al inicio para perspectiva
                    if len(vals) == 1: vals = [0] + vals
                    self.perf_chart.set_data(vals)

            if self.stack.currentIndex() == 3: self.update_detail_view()
        except Exception as e:
            self.diag_log.error(f"DIAG: Error en refresh_data: {e}")

    def _apply_fallback_avatar(self, label, initial):
        """Aplica el fallback técnico al avatar."""
        label.setPixmap(QPixmap()) # Limpiar pixmap
        label.setText(initial)
        label.setStyleSheet("font-size: 14px; font-weight: 900; color: #60a5fa; background: transparent;")

    def _load_portrait_async(self, label, url, fallback_initial):
        """Carga el retrato de forma asíncrona y segura."""
        request = QNetworkRequest(QUrl(url))
        reply = self.network_manager.get(request)
        
        def on_finished():
            if reply.error() == QNetworkReply.NoError:
                pixmap = QPixmap()
                if pixmap.loadFromData(reply.readAll()):
                    label.setText("")
                    label.setPixmap(pixmap.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self._apply_fallback_avatar(label, fallback_initial)
            else:
                self._apply_fallback_avatar(label, fallback_initial)
            reply.deleteLater()
            
        reply.finished.connect(on_finished)

    def _update_status_indicator(self, widget, state):
        from ui.common.theme import Theme
        dot = widget.findChild(QLabel, "StatusDot")
        if not dot: return
        if state == "degraded":
            dot.setStyleSheet(f"color: {Theme.WARNING}; font-size: 12px;") # Amber
        elif state:
            dot.setStyleSheet(f"color: {Theme.SUCCESS}; font-size: 12px;") # Green
        else:
            dot.setStyleSheet(f"color: {Theme.DANGER}; font-size: 12px;") # Red

    def _action_reset(self):
        if self.controller and self.controller._tracker:
            self.controller._tracker.reset_all()
            self.refresh_data()
            self.diag_log.info("DIAG: Session reset triggered from Dashboard.")

    def _apply_profile(self, name):
        """Aplica un perfil visual predefinido a la Suite."""
        s_hud = QSettings("EVEISKTracker", "Overlay")
        if name == "PvE":
            s_hud.setValue("preset", "balanced")
            s_hud.setValue("show_total", "true")
            s_hud.setValue("show_tick", "true")
            s_hud.setValue("show_dur", "true")
        elif name == "PvP":
            s_hud.setValue("preset", "compact")
            s_hud.setValue("show_total", "false")
            s_hud.setValue("show_tick", "false")
            s_hud.setValue("show_dur", "false")
        elif name == "Farm Focus":
            s_hud.setValue("preset", "focus")
            s_hud.setValue("show_total", "true")
            s_hud.setValue("show_tick", "true")
            s_hud.setValue("show_dur", "false")
        
        # Sincronizar UI de settings y controlador
        self.load_settings()
        
        # Notificar al overlay si está activo
        if self.controller and self.controller.overlay_window:
            try:
                preset = s_hud.value("preset", "balanced")
                if hasattr(self.controller.overlay_window, '_apply_preset'):
                    self.controller.overlay_window._apply_preset(preset)
            except Exception: pass
            
        self.diag_log.info(f"DIAG: Quick Profile '{name}' applied successfully.")

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

        # Actualizar Fleet Status
        online_count = sum(1 for acc in accounts if acc.get('status') in ['active', 'idle'])
        self.fleet_status_box.findChild(QLabel, "AnalyticVal").setText(f"{online_count}/{len(accounts)} ONLINE")
        
        # Sincronización de tarjetas
        for i, acc in enumerate(accounts):
            name = acc.get('display_name', acc.get('character'))
            status = acc.get('status', 'idle')

            if name not in self.account_cards:
                card = self.create_account_card(acc)
                self.account_cards[name] = card
                self.accounts_layout.addWidget(card, i // 3, i % 3)
            else:
                card = self.account_cards[name]
                
            # Actualizar estado técnico (Tooltip)
            id_status = acc.get('id_status', 'pending')
            status_map = {
                'resolved': 'PORTRAIT READY',
                'resolving': 'RESOLVING IDENTITY',
                'pending': 'NO PORTRAIT',
                'failed': 'IDENTITY FAILED'
            }
            portrait_label = card.findChild(QLabel, "CharPortrait")
            if portrait_label:
                portrait_label.setToolTip(status_map.get(id_status, 'UNKNOWN'))

            # Actualizar ISK/h y Session Total
            isk_val = card.findChild(QLabel, "IskValue")
            if isk_val:
                isk_val.setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
            
            sess_isk = card.findChild(QLabel, "SessionIsk")
            if sess_isk:
                sess_isk.setText(format_isk(acc.get('total_isk', 0), short=True))
                
            # Actualizar Badge de Estado Operativo
            badge = card.findChild(QLabel, "StatusBadge")
            if badge:
                if status == 'active':
                    badge.setText("● SISTEMA ACTIVE")
                    badge.setStyleSheet("background-color: rgba(16,185,129,0.1); color: #10b981; border: 1px solid rgba(16,185,129,0.2); padding: 2px 8px; font-size: 8px; font-weight: 900; border-radius: 2px;")
                elif status == 'idle':
                    badge.setText("○ STANDBY (IDLE)")
                    badge.setStyleSheet("background-color: rgba(245,158,11,0.1); color: #f59e0b; border: 1px solid rgba(245,158,11,0.2); padding: 2px 8px; font-size: 8px; font-weight: 900; border-radius: 2px;")
                else:
                    badge.setText("× SYNC LOST")
                    badge.setStyleSheet("background-color: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.2); padding: 2px 8px; font-size: 8px; font-weight: 900; border-radius: 2px;")

            # Actualizar Telemetría Media (NUEVO)
            last_tick = acc.get('last_tick', {})
            last_val = last_tick.get('current_cycle_isk', 0)
            last_lbl = card.findChild(QLabel, "LastTick")
            if last_lbl:
                last_lbl.setText(f"LAST: {format_isk(last_val, short=True)}")
            
            # Usar duración de sesión si no hay por personaje
            dur_lbl = card.findChild(QLabel, "CharDuration")
            if dur_lbl:
                from utils.formatters import format_duration
                from datetime import timedelta
                dur_secs = acc.get('inactivity_seconds', 0) # Esto es inactividad, no uptime. 
                # El summary de flota tiene 'session_duration_seconds'. 
                # Por ahora mostraremos el global si no tenemos el del personaje.
                # Pero en la proxima iteración del tracker podemos añadirlo.
                # Por ahora lo dejamos como placeholder dinámico o usamos un valor base.
                dur_lbl.setText(f"UPTIME: {format_duration(timedelta(seconds=acc.get('total_isk', 0)/max(1, acc.get('isk_per_hour', 1))*3600))[:8]}") # Estimación simple por ahora

    def set_tray_manager(self, tm): self.tray_manager = tm
    def _on_hud_clicked(self):
        if self.tray_manager: self.tray_manager._on_overlay()
    def _on_translator_clicked(self):
        if self.controller: self.controller.start_translator()
    def _on_replicator_clicked(self):
        if self.tray_manager: self.tray_manager._on_replicator()
    def _on_market_clicked(self):
        try:
            if not hasattr(self, '_market_window') or self._market_window is None:
                from ui.market_command.command_main import MarketCommandMain
                from ui.common.custom_titlebar import CustomTitleBar
                from PySide6.QtWidgets import QVBoxLayout as _QVBox

                # Wrapper frameless para Market Command
                self._market_window = QWidget()
                self._market_window.setWindowTitle("Salva Suite — Market Command")
                self._market_window.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
                self._market_window.resize(840, 820)

                outer = _QVBox(self._market_window)
                outer.setContentsMargins(0, 0, 0, 0)
                outer.setSpacing(0)

                tb = CustomTitleBar("Salva Suite — Market Command", self._market_window)
                outer.addWidget(tb)

                mc = MarketCommandMain()
                outer.addWidget(mc, 1)
                self._market_window._mc = mc  # keep ref

                from ui.desktop.styles import MAIN_STYLE
                mc.setStyleSheet(MAIN_STYLE)

            self._market_window.show()
            self._market_window.raise_()
            self._market_window.activateWindow()
        except Exception as e:
            print(f"Error opening Market Command: {e}")
            import traceback
            traceback.print_exc()
    def _on_visual_clon_clicked(self):
        try:
            if not hasattr(self, '_visual_clon_window') or self._visual_clon_window is None:
                from ui.tools.visual_clon_view import VisualClonView
                from ui.common.custom_titlebar import CustomTitleBar
                from PySide6.QtWidgets import QVBoxLayout as _QVBox

                self._visual_clon_window = QWidget()
                self._visual_clon_window.setWindowTitle("Salva Suite — Visual Clon")
                self._visual_clon_window.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
                self._visual_clon_window.setFixedSize(900, 675)

                outer = _QVBox(self._visual_clon_window)
                outer.setContentsMargins(0, 0, 0, 0)
                outer.setSpacing(0)

                tb = CustomTitleBar("Salva Suite — Visual Clon", self._visual_clon_window)
                outer.addWidget(tb)

                vc = VisualClonView()
                outer.addWidget(vc, 1)
                self._visual_clon_window._vc = vc

            self._visual_clon_window.show()
            self._visual_clon_window.raise_()
            self._visual_clon_window.activateWindow()
        except Exception as e:
            print(f"Error opening Visual Clon: {e}")
            import traceback
            traceback.print_exc()

    def _on_intel_alert_clicked(self):
        try:
            if not hasattr(self, '_intel_alert_win') or self._intel_alert_win is None:
                from ui.tools.intel_alert_window import IntelAlertWindow
                self._intel_alert_win = IntelAlertWindow(controller=self._ctrl if hasattr(self, '_ctrl') else None)
                self._intel_alert_win.setWindowTitle("Salva Suite — Intel Alert")
            self._intel_alert_win.show()
            self._intel_alert_win.raise_()
            self._intel_alert_win.activateWindow()
        except Exception as e:
            print(f"Error opening Intel Alert: {e}")
            import traceback
            traceback.print_exc()

    def _on_browse_logs(self):
        d = QFileDialog.getExistingDirectory(self, "Logs EVE"); self.edit_log_dir.setText(d if d else "")
    def load_settings(self):
        s = QSettings("SalvaSuite", "Suite")
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
        
        # ASEGURAR que el controlador tiene la ruta cargada para que el tracker empiece bien
        if self.controller and saved_dir:
            self.controller.set_log_directory(saved_dir)
            # Si el tracker no ha arrancado, lo forzamos con los ajustes cargados
            if not self.controller.state.tracker_running:
                skip = s.value("skip_logs", "true") == "true"
                self.controller.start_tracker(skip_existing=skip)

        if self.check_skip_logs: self.check_skip_logs.setChecked(s.value("skip_logs", "true") == "true")
        if self.check_blur: self.check_blur.setChecked(s.value("enable_blur", "false") == "true")
        if self.check_hide_hud: self.check_hide_hud.setChecked(s.value("auto_hide_hud", "false") == "true")
        
        if hasattr(self, 'combo_hud_preset'):
            s_hud = QSettings("EVEISKTracker", "Overlay")
            preset_val = str(s_hud.value("preset", "balanced")).upper()
            idx = self.combo_hud_preset.findText(preset_val)
            if idx >= 0: self.combo_hud_preset.setCurrentIndex(idx)
            
            self.check_hud_total.setChecked(str(s_hud.value("show_total", "true")) == "true")
            self.check_hud_tick.setChecked(str(s_hud.value("show_tick", "true")) == "true")
            self.check_hud_dur.setChecked(str(s_hud.value("show_dur", "true")) == "true")
        
        if self.combo_translator_lang:
            idx = self.combo_translator_lang.findText(s.value("translator_lang", "Español"))
            if idx >= 0: self.combo_translator_lang.setCurrentIndex(idx)

    def save_settings(self):
        s = QSettings("SalvaSuite", "Suite")
        new_log_dir = self.edit_log_dir.text() if self.edit_log_dir else ""
        if self.edit_log_dir: s.setValue("log_dir", new_log_dir)
        if self.check_skip_logs: s.setValue("skip_logs", "true" if self.check_skip_logs.isChecked() else "false")
        if self.check_blur: s.setValue("enable_blur", "true" if self.check_blur.isChecked() else "false")
        if self.check_hide_hud: s.setValue("auto_hide_hud", "true" if self.check_hide_hud.isChecked() else "false")
        if self.combo_translator_lang: s.setValue("translator_lang", self.combo_translator_lang.currentText())

        # Guardar Preset de HUD
        if hasattr(self, 'combo_hud_preset'):
            preset_val = self.combo_hud_preset.currentText().lower()
            s_hud = QSettings("EVEISKTracker", "Overlay")
            s_hud.setValue("preset", preset_val)
            s_hud.setValue("show_total", "true" if self.check_hud_total.isChecked() else "false")
            s_hud.setValue("show_tick", "true" if self.check_hud_tick.isChecked() else "false")
            s_hud.setValue("show_dur", "true" if self.check_hud_dur.isChecked() else "false")

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
        try:
            QSettings("SalvaSuite", "Suite").setValue("geometry", self.saveGeometry())
        except Exception:
            pass
        event.ignore()
        self.hide()
    def restore_geometry(self):
        try:
            self.diag_log.info("DIAG: Restaurando geometría...")
            s = QSettings("SalvaSuite", "Suite")
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

    def _action_logoff(self):
        """Cierre total de la aplicación con confirmación visual/auditiva."""
        self.diag_log.info("DIAG: Logoff manual solicitado.")
        # Limpiar tray_manager para que el closeEvent no intercepte el cierre
        self.tray_manager = None
        self.close()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def closeEvent(self, event):
        self.diag_log.info("DIAG: closeEvent detectado.")
        try:
            QSettings("SalvaSuite", "Suite").setValue("geometry", self.saveGeometry())
        except Exception:
            pass
        
        # Si el tray está activo, ocultar en lugar de cerrar
        if self.tray_manager:
            self.diag_log.info("DIAG: Redirigiendo close a hide (Tray activo).")
            event.ignore()
            self.hide()
        else:
            self.diag_log.info("DIAG: Cerrando aplicación (Sin Tray).")
            event.accept()
