from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QPushButton, QFrame, QLabel
from PySide6.QtCore import Qt
from ui.market_command.simple_view import MarketSimpleView
from ui.market_command.advanced_view import MarketAdvancedView
from ui.market_command.performance_view import MarketPerformanceView

class MarketCommandMain(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 1. Navigation Header
        self.nav_frame = QFrame()
        self.nav_frame.setObjectName("NavBar")
        self.nav_frame.setFixedHeight(40)
        self.nav_frame.setStyleSheet("""
            QFrame#NavBar {
                background-color: #0f172a;
                border-bottom: 1px solid #1e293b;
            }
        """)
        nav_layout = QHBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(20, 0, 20, 0)
        nav_layout.setSpacing(10)
        
        self.btn_simple = self.create_tab_button("MODO SIMPLE", True)
        self.btn_advanced = self.create_tab_button("MODO AVANZADO")
        self.btn_performance = self.create_tab_button("PERFORMANCE")
        
        self.btn_simple.clicked.connect(lambda: self.switch_view(0))
        self.btn_advanced.clicked.connect(lambda: self.switch_view(1))
        self.btn_performance.clicked.connect(lambda: self.switch_view(2))
        
        nav_layout.addWidget(self.btn_simple)
        nav_layout.addWidget(self.btn_advanced)
        nav_layout.addWidget(self.btn_performance)
        nav_layout.addStretch()
        
        # SSO Section
        self.btn_sso = QPushButton("VINCULAR PERSONAJE")
        self.btn_sso.setCursor(Qt.PointingHandCursor)
        self.btn_sso.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 8px;
                font-weight: 800;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background: #334155;
                color: #f1f5f9;
            }
        """)
        from core.auth_manager import AuthManager
        self.btn_sso.clicked.connect(AuthManager.instance().login)
        AuthManager.instance().authenticated.connect(self.on_auth_success)
        
        nav_layout.addWidget(self.btn_sso)
        
        # Status Label inside Nav
        self.lbl_mode = QLabel("ANÁLISIS OPERATIVO")
        self.lbl_mode.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; letter-spacing: 1px;")
        nav_layout.addWidget(self.lbl_mode)
        
        self.layout.addWidget(self.nav_frame)
        
        # 2. Stacked Widget
        self.stack = QStackedWidget()
        self.view_simple = MarketSimpleView()
        self.view_advanced = MarketAdvancedView()
        self.view_performance = MarketPerformanceView()
        
        self.stack.addWidget(self.view_simple)
        self.stack.addWidget(self.view_advanced)
        self.stack.addWidget(self.view_performance)
        
        self.layout.addWidget(self.stack)

    def on_auth_success(self, char_name, tokens):
        self.btn_sso.setText(f"● {char_name.upper()}")
        self.btn_sso.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.1);
                color: #10b981;
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 4px;
                font-size: 8px;
                font-weight: 800;
                padding: 4px 10px;
            }
        """)

    def create_tab_button(self, text, active=False):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(40)
        self.update_btn_style(btn, active)
        return btn

    def update_btn_style(self, btn, active):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #3b82f6;
                    border: none;
                    border-bottom: 2px solid #3b82f6;
                    font-weight: 900;
                    font-size: 10px;
                    padding: 0 15px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #64748b;
                    border: none;
                    font-weight: 700;
                    font-size: 10px;
                    padding: 0 15px;
                }
                QPushButton:hover {
                    color: #f1f5f9;
                }
            """)

    def switch_view(self, index):
        self.stack.setCurrentIndex(index)
        self.btn_simple.setChecked(index == 0)
        self.btn_advanced.setChecked(index == 1)
        self.btn_performance.setChecked(index == 2)
        self.update_btn_style(self.btn_simple, index == 0)
        self.update_btn_style(self.btn_advanced, index == 1)
        self.update_btn_style(self.btn_performance, index == 2)
        
        if index == 0:
            self.lbl_mode.setText("ANÁLISIS OPERATIVO")
        elif index == 1:
            self.lbl_mode.setText("INVESTIGACIÓN ESTRATÉGICA")
        else:
            self.lbl_mode.setText("RENDIMIENTO REAL")
