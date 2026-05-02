"""Reusable frameless custom titlebar for Salva Suite windows."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt


class CustomTitleBar(QWidget):
    """Drop-in dark titlebar: drag, minimize, close. No native Windows frame."""

    def __init__(self, title="", parent=None, show_minimize=True):
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(30)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(4)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setObjectName("TitleBarLabel")
        layout.addWidget(self.title_lbl)
        layout.addStretch()

        if show_minimize:
            self.btn_min = QPushButton("─")
            self.btn_min.setObjectName("TitleBarMinBtn")
            self.btn_min.setFixedSize(26, 22)
            self.btn_min.setCursor(Qt.PointingHandCursor)
            self.btn_min.clicked.connect(self._minimize)
            layout.addWidget(self.btn_min)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("TitleBarCloseBtn")
        self.btn_close.setFixedSize(26, 22)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self._close)
        layout.addWidget(self.btn_close)

        self.setStyleSheet("""
            QWidget#CustomTitleBar {
                background-color: #0b1016;
                border-bottom: 1px solid #1e293b;
            }
            QLabel#TitleBarLabel {
                color: #64748b;
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 1.5px;
            }
            QPushButton#TitleBarMinBtn, QPushButton#TitleBarCloseBtn {
                background: transparent;
                color: #64748b;
                border: none;
                font-size: 15px;
                font-weight: 400;
                border-radius: 3px;
                padding: 0;
            }
            QPushButton#TitleBarMinBtn:hover {
                background: #1e293b;
                color: #e2e8f0;
            }
            QPushButton#TitleBarCloseBtn:hover {
                background: #ef4444;
                color: white;
            }
        """)

    def set_title(self, title: str):
        self.title_lbl.setText(title.upper())

    def _minimize(self):
        win = self.window()
        if win:
            win.showMinimized()

    def _close(self):
        win = self.window()
        if win:
            win.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
