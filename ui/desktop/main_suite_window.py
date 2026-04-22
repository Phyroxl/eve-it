import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QFrame, QLabel, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QSizeGrip, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QIcon, QFont, QLinearGradient

from ui.desktop.styles import MAIN_STYLE
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("EVE iT — Suite Control Panel")
        self.resize(1100, 750)
        
        # UI References for updating
        self.val_total_isk = None
        self.val_isk_h = None
        self.val_accounts = None
        self.accounts_layout = None
        self.account_cards = {} # {char_name: card_widget}
        
        self.setup_ui()
        self.apply_styles()
        
        # Timer for real-time updates
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(1500)
        
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
        self.btn_dashboard = self.create_nav_button("📊 RESUMEN", True)
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
        self.content_layout.setContentsMargins(25, 25, 25, 25)
        self.content_layout.setSpacing(20)
        
        # Top Header
        header_layout = QHBoxLayout()
        self.section_title = QLabel("PANEL DE CONTROL")
        self.section_title.setObjectName("SectionTitle")
        header_layout.addWidget(self.section_title)
        header_layout.addStretch()
        
        # Session info
        self.session_info = QLabel("SESIÓN: --:--:--")
        self.session_info.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(200, 230, 255, 0.4); font-size: 12px;")
        header_layout.addWidget(self.session_info)
        
        self.content_layout.addLayout(header_layout)
        
        # Stacked Widget for pages
        self.stack = QStackedWidget()
        self.content_layout.addWidget(self.stack)
        
        # Page: Dashboard
        self.page_dashboard = self.create_dashboard_page()
        self.stack.addWidget(self.page_dashboard)
        
        # Add NavBar and Content to Main Layout
        self.main_layout.addWidget(self.nav_bar)
        self.main_layout.addWidget(self.content_frame, 1)

        # Connect Signals
        self.btn_dashboard.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_hud.clicked.connect(self._on_hud_clicked)
        self.btn_translator.clicked.connect(self._on_translator_clicked)
        self.btn_replicator.clicked.connect(self._on_replicator_clicked)

    def refresh_data(self):
        """Actualiza las métricas y la lista de cuentas con datos reales."""
        if not self.controller or not self.controller._tracker:
            return
            
        try:
            from datetime import datetime
            now = datetime.now()
            summary = self.controller._tracker.get_summary(now)
            
            # 1. Update Global Metrics
            if self.val_total_isk:
                self.val_total_isk.setText(format_isk(summary.get('total_isk', 0), short=True))
            if self.val_isk_h:
                self.val_isk_h.setText(format_isk(summary.get('isk_per_hour_rolling', 0), short=True) + "/h")
            if self.val_accounts:
                count = summary.get('character_count', 0)
                self.val_accounts.setText(f"{count} ACTIVAS")
            
            from utils.formatters import format_duration
            self.session_info.setText(f"SESIÓN: {format_duration(summary.get('session_duration'))}")
            
            # 2. Update Account List
            self.update_accounts_view(summary.get('per_character', []))
                
        except Exception as e:
            import traceback
            # print(f"Error actualizando métricas en Suite: {e}")
            # traceback.print_exc()

    def update_accounts_view(self, accounts):
        """Crea o actualiza las tarjetas de cuenta."""
        if not self.accounts_layout:
            return

        active_names = [a.get('display_name', a.get('character')) for a in accounts]
        
        # Remove cards for accounts that are no longer active
        for name in list(self.account_cards.keys()):
            if name not in active_names:
                card = self.account_cards.pop(name)
                self.accounts_layout.removeWidget(card)
                card.deleteLater()

        # Update or create cards
        for i, acc in enumerate(accounts):
            name = acc.get('display_name', acc.get('character'))
            if name not in self.account_cards:
                card = self.create_account_card(acc)
                self.account_cards[name] = card
                # Add to grid: 3 columns
                row = i // 3
                col = i % 3
                self.accounts_layout.addWidget(card, row, col)
            else:
                self.update_account_card(self.account_cards[name], acc)

    def create_account_card(self, acc):
        card = QFrame()
        card.setObjectName("AccountCard")
        card.setStyleSheet("""
            QFrame#AccountCard {
                background-color: rgba(6, 14, 26, 0.6);
                border: 1px solid rgba(0, 180, 255, 0.1);
                border-radius: 6px;
                padding: 10px;
            }
            QFrame#AccountCard:hover {
                border-color: rgba(0, 180, 255, 0.3);
            }
        """)
        card.setMinimumWidth(250)
        
        l = QVBoxLayout(card)
        l.setSpacing(4)
        
        # Header: Name + Status
        h = QHBoxLayout()
        name_lbl = QLabel(acc.get('display_name', acc.get('character')))
        name_lbl.setObjectName("AccName")
        name_lbl.setStyleSheet("font-family: 'Orbitron'; font-size: 13px; color: #ffffff; font-weight: bold;")
        
        status_dot = QLabel("●")
        status_dot.setObjectName("AccStatus")
        status_dot.setStyleSheet("font-size: 14px; color: #00ff9d;")
        
        h.addWidget(name_lbl)
        h.addStretch()
        h.addWidget(status_dot)
        l.addLayout(h)
        
        # ISK Stats
        stats = QHBoxLayout()
        
        total_l = QVBoxLayout()
        t_lbl = QLabel("TOTAL")
        t_lbl.setStyleSheet("font-size: 9px; color: rgba(200,230,255,0.4);")
        t_val = QLabel(format_isk(acc.get('total_isk', 0), short=True))
        t_val.setObjectName("AccTotal")
        t_val.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 12px; color: #ffd700; font-weight: bold;")
        total_l.addWidget(t_lbl)
        total_l.addWidget(t_val)
        
        roll_l = QVBoxLayout()
        r_lbl = QLabel("ROLLING")
        r_lbl.setStyleSheet("font-size: 9px; color: rgba(200,230,255,0.4);")
        r_val = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        r_val.setObjectName("AccRoll")
        r_val.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 12px; color: #00ff9d;")
        roll_l.addWidget(r_lbl)
        roll_l.addWidget(r_val)
        
        stats.addLayout(total_l)
        stats.addLayout(roll_l)
        l.addLayout(stats)
        
        # Last Activity
        last_act = QLabel("ÚLTIMO: ---")
        last_act.setObjectName("AccLast")
        last_act.setStyleSheet("font-size: 10px; color: rgba(0, 180, 255, 0.4); margin-top: 4px;")
        l.addWidget(last_act)
        
        return card

    def update_account_card(self, card, acc):
        # Update values
        total_val = card.findChild(QLabel, "AccTotal")
        if total_val: total_val.setText(format_isk(acc.get('total_isk', 0), short=True))
        
        roll_val = card.findChild(QLabel, "AccRoll")
        if roll_val: roll_val.setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        
        last_val = card.findChild(QLabel, "AccLast")
        if last_val:
            le = acc.get('last_event')
            time_str = le.strftime('%H:%M:%S') if le else "---"
            last_val.setText(f"ÚLTIMO: {time_str}")
            
        status_dot = card.findChild(QLabel, "AccStatus")
        if status_dot:
            status = acc.get('status', 'idle')
            color = "#00ff9d" if status == 'active' else "#ffd700" if status == 'idle' else "#ff4444"
            status_dot.setStyleSheet(f"font-size: 14px; color: {color};")

    def _on_hud_clicked(self):
        if self.controller:
            self.controller.toggle_overlay()
            
    def _on_translator_clicked(self):
        if self.controller:
            # Lanzar el traductor real
            self.controller.start_translator()

    def _on_replicator_clicked(self):
        if self.controller:
            try:
                # Intentamos acceder al tray manager desde el controlador o vía global
                from main import _tray_manager_ref
                if _tray_manager_ref:
                    _tray_manager_ref._on_replicator()
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
        
        # 1. Top Metrics Row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(15)
        
        card_isk = self.create_metric_card("ISK TOTAL", "0.00 ISK", "#00c8ff")
        self.val_total_isk = card_isk.findChild(QLabel, "MetricValue")
        
        card_h = self.create_metric_card("ISK / HORA", "0.00 ISK/h", "#00ff9d")
        self.val_isk_h = card_h.findChild(QLabel, "MetricValue")
        
        card_acc = self.create_metric_card("CUENTAS", "0 ACTIVAS", "#ffffff")
        self.val_accounts = card_acc.findChild(QLabel, "MetricValue")
        
        metrics_layout.addWidget(card_isk)
        metrics_layout.addWidget(card_h)
        metrics_layout.addWidget(card_acc)
        
        layout.addLayout(metrics_layout)
        
        # 2. Accounts Section (Scrollable)
        acc_title = QLabel("CUENTAS ACTIVAS")
        acc_title.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(255,255,255,0.4); font-size: 12px; letter-spacing: 2px;")
        layout.addWidget(acc_title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self.accounts_layout = QGridLayout(scroll_content)
        self.accounts_layout.setContentsMargins(0, 0, 0, 0)
        self.accounts_layout.setSpacing(10)
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1) # This takes most space
        
        # 3. Tools Footer Section (Compact)
        tools_label = QLabel("ACCESO RÁPIDO")
        tools_label.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(255,255,255,0.2); font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(tools_label)
        
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10)
        
        self.card_hud = self.create_tool_card_compact("HUD", "🕹️")
        self.card_hud.mousePressEvent = lambda e: self._on_hud_clicked()
        
        self.card_trans = self.create_tool_card_compact("TRADUCTOR", "🌐")
        self.card_trans.mousePressEvent = lambda e: self._on_translator_clicked()
        
        self.card_repl = self.create_tool_card_compact("REPLICADOR", "🪟")
        self.card_repl.mousePressEvent = lambda e: self._on_replicator_clicked()
        
        tools_layout.addWidget(self.card_hud)
        tools_layout.addWidget(self.card_trans)
        tools_layout.addWidget(self.card_repl)
        tools_layout.addStretch()
        
        layout.addLayout(tools_layout)
        
        # Status Footer
        footer = QLabel("EVE iT ENGINE OK | SYSTEM: WINDOWS | SYNC: LIVE")
        footer.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(0, 200, 255, 0.2); font-size: 9px; margin-top: 5px;")
        layout.addWidget(footer)
        
        return page

    def create_tool_card_compact(self, title, icon):
        card = QFrame()
        card.setObjectName("ToolCard")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(160, 50)
        card.setStyleSheet("""
            QFrame#ToolCard {
                background-color: rgba(0, 180, 255, 0.05);
                border: 1px solid rgba(0, 180, 255, 0.1);
                border-radius: 4px;
            }
            QFrame#ToolCard:hover {
                background-color: rgba(0, 180, 255, 0.15);
                border-color: rgba(0, 180, 255, 0.4);
            }
        """)
        
        l = QHBoxLayout(card)
        l.setContentsMargins(10, 0, 10, 0)
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 16px;")
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-family: 'Orbitron'; font-size: 11px; color: #ffffff;")
        
        l.addWidget(icon_lbl)
        l.addWidget(title_lbl)
        l.addStretch()
        
        return card
        
    def create_metric_card(self, label, value, color):
        card = QFrame()
        card.setProperty("class", "MetricCard")
        l = QVBoxLayout(card)
        
        lbl = QLabel(label)
        lbl.setProperty("class", "MetricLabel")
        
        val = QLabel(value)
        val.setObjectName("MetricValue") # Usar objectName para búsqueda
        val.setProperty("class", "MetricValue")
        val.setStyleSheet(f"color: {color};")
        
        l.addWidget(lbl)
        l.addWidget(val)
        return card
        
    def apply_styles(self):
        self.setStyleSheet(MAIN_STYLE)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainSuiteWindow()
    window.show()
    sys.exit(app.exec())
