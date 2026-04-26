from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QPushButton, QFrame, QLabel
from PySide6.QtCore import Qt
from .simple_view import MarketSimpleView
from .advanced_view import MarketAdvancedView

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
        
        self.btn_simple.clicked.connect(lambda: self.switch_view(0))
        self.btn_advanced.clicked.connect(lambda: self.switch_view(1))
        
        nav_layout.addWidget(self.btn_simple)
        nav_layout.addWidget(self.btn_advanced)
        nav_layout.addStretch()
        
        # Status Label inside Nav
        self.lbl_mode = QLabel("ANÁLISIS OPERATIVO")
        self.lbl_mode.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; letter-spacing: 1px;")
        nav_layout.addWidget(self.lbl_mode)
        
        self.layout.addWidget(self.nav_frame)
        
        # 2. Stacked Widget
        self.stack = QStackedWidget()
        self.view_simple = MarketSimpleView()
        self.view_advanced = MarketAdvancedView()
        
        self.stack.addWidget(self.view_simple)
        self.stack.addWidget(self.view_advanced)
        
        self.layout.addWidget(self.stack)

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
        self.update_btn_style(self.btn_simple, index == 0)
        self.update_btn_style(self.btn_advanced, index == 1)
        
        if index == 0:
            self.lbl_mode.setText("ANÁLISIS OPERATIVO")
        else:
            self.lbl_mode.setText("INVESTIGACIÓN ESTRATÉGICA")
