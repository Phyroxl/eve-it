import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QFrame, QLabel, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QSizeGrip
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QIcon, QFont, QLinearGradient

from ui.desktop.styles import MAIN_STYLE

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("EVE iT — Suite Control Panel")
        self.resize(1100, 700)
        
        # Frameless window configuration (Optional, for now keeping it standard but stylized)
        # self.setWindowFlags(Qt.FramelessWindowHint)
        # self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setup_ui()
        self.apply_styles()
        
    def setup_ui(self):
        # Central Widget
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)
        
        # Main Horizontal Layout
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Navigation Bar (Left Sidebar)
        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("NavBar")
        self.nav_layout = QVBoxLayout(self.nav_bar)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(0)
        
        # Logo Area
        self.logo_label = QLabel("EVE iT")
        self.logo_label.setObjectName("LogoLabel")
        self.nav_layout.addWidget(self.logo_label)
        
        # Navigation Buttons
        self.btn_dashboard = self.create_nav_button("📊 ESTADO GENERAL", True)
        self.btn_hud = self.create_nav_button("🕹️ HUD OVERLAY")
        self.btn_translator = self.create_nav_button("🌐 TRADUCTOR")
        self.btn_replicator = self.create_nav_button("🪟 REPLICADOR")
        
        self.nav_layout.addWidget(self.btn_dashboard)
        self.nav_layout.addWidget(self.btn_hud)
        self.nav_layout.addWidget(self.btn_translator)
        self.nav_layout.addWidget(self.btn_replicator)
        
        self.nav_layout.addStretch()
        
        # Settings button at bottom
        self.btn_settings = self.create_nav_button("⚙️ AJUSTES")
        self.nav_layout.addWidget(self.btn_settings)
        
        # 2. Content Area (Right Side)
        self.content_frame = QFrame()
        self.content_frame.setObjectName("ContentFrame")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(30, 30, 30, 30)
        
        # Stacked Widget for pages
        self.stack = QStackedWidget()
        self.content_layout.addWidget(self.stack)
        
        # Pages
        self.page_dashboard = self.create_dashboard_page()
        self.stack.addWidget(self.page_dashboard)
        
        # Add NavBar and Content to Main Layout
        self.main_layout.addWidget(self.nav_bar)
        self.main_layout.addWidget(self.content_frame, 1) # Content area stretches

        # Connect Signals
        self.btn_dashboard.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_hud.clicked.connect(self._on_hud_clicked)
        self.btn_translator.clicked.connect(self._on_translator_clicked)
        self.btn_replicator.clicked.connect(self._on_replicator_clicked)

    def _on_hud_clicked(self):
        if self.controller:
            # Si el controlador tiene el tray, usamos su lógica de toggle
            # O llamamos directamente al controlador
            self.controller.toggle_overlay()
            
    def _on_translator_clicked(self):
        # El traductor aún no tiene una UI de escritorio unificada, 
        # pero podemos mostrar un mensaje o abrir el dashboard
        if self.controller:
            self.controller.open_dashboard_browser()

    def _on_replicator_clicked(self):
        if self.controller:
            # Intentar lanzar el replicador usando el tray_manager si está disponible
            # El tray manager ya tiene toda la lógica de carga de PySide6 y prevención de GC
            try:
                # Intentamos acceder al tray manager desde el controlador o vía global
                from main import _tray_manager_ref
                if _tray_manager_ref:
                    _tray_manager_ref._on_replicator()
                else:
                    # Fallback directo si no hay tray manager
                    from controller.replicator_wizard import ReplicatorWizard
                    from PySide6 import QtWidgets, QtCore, QtGui
                    from overlay import replicator_config as cfg_mod
                    cfg = cfg_mod.load_config()
                    self.wizard = ReplicatorWizard(QtWidgets, QtCore, QtGui, cfg, cfg_mod)
                    self.wizard.show()
            except Exception as e:
                print(f"Error lanzando replicador desde Suite: {e}")

    def create_nav_button(self, text, active=False):
        btn = QPushButton(text)
        btn.setProperty("class", "NavButton")
        btn.setProperty("active", str(active).lower())
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(50)
        return btn
        
    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("PANEL DE CONTROL")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        
        # Metrics Row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(15)
        
        metrics_layout.addWidget(self.create_metric_card("ISK TOTAL", "0.00 ISK", "#00c8ff"))
        metrics_layout.addWidget(self.create_metric_card("ISK / HORA", "0.00 ISK/h", "#00ff9d"))
        metrics_layout.addWidget(self.create_metric_card("CUENTAS", "0 ACTIVAS", "#ffffff"))
        
        layout.addLayout(metrics_layout)
        
        layout.addSpacing(20)
        
        # Tools Grid Title
        tools_label = QLabel("HERRAMIENTAS DE LA SUITE")
        tools_label.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(255,255,255,0.4); font-size: 12px; letter-spacing: 2px;")
        layout.addWidget(tools_label)
        
        # Tools Layout
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(20)
        
        tools_layout.addWidget(self.create_tool_card("HUD OVERLAY", "Monitoriza ISK y ticks en tiempo real sobre el juego.", "🕹️"))
        tools_layout.addWidget(self.create_tool_card("TRADUCTOR", "Traduce chats de EVE automáticamente.", "🌐"))
        tools_layout.addWidget(self.create_tool_card("REPLICADOR", "Clona y escala zonas de pantalla para multiboxing.", "🪟"))
        
        layout.addLayout(tools_layout)
        
        layout.addStretch()
        
        # Status Footer
        footer = QLabel("SISTEMA OPERATIVO | LATENCIA: 14ms | LOGS: OK")
        footer.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(0, 200, 255, 0.3); font-size: 10px;")
        layout.addWidget(footer)
        
        return page
        
    def create_metric_card(self, label, value, color):
        card = QFrame()
        card.setProperty("class", "MetricCard")
        l = QVBoxLayout(card)
        
        lbl = QLabel(label)
        lbl.setProperty("class", "MetricLabel")
        
        val = QLabel(value)
        val.setProperty("class", "MetricValue")
        val.setStyleSheet(f"color: {color};")
        
        l.addWidget(lbl)
        l.addWidget(val)
        return card
        
    def create_tool_card(self, title, desc, icon):
        card = QFrame()
        card.setProperty("class", "ToolCard")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedHeight(140)
        
        l = QVBoxLayout(card)
        l.setContentsMargins(20, 20, 20, 20)
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 24px; margin-bottom: 5px;")
        
        title_lbl = QLabel(title)
        title_lbl.setObjectName("ToolTitle")
        
        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("ToolDesc")
        desc_lbl.setWordWrap(True)
        
        l.addWidget(icon_lbl)
        l.addWidget(title_lbl)
        l.addWidget(desc_lbl)
        l.addStretch()
        
        return card

    def apply_styles(self):
        self.setStyleSheet(MAIN_STYLE)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainSuiteWindow()
    window.show()
    sys.exit(app.exec())
