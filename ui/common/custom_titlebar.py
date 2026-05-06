"""Reusable frameless custom titlebar for Salva Suite windows.

Style is identical to the main suite window (_TitleBar in main_suite_window.py).
Use this component in every frameless secondary window to keep button appearance
uniform across the entire suite.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

# ── Canonical button stylesheet (identical to main_suite_window._TitleBar) ────
_BTN_STYLE = """
    QPushButton#TitleBarMinBtn, QPushButton#TitleBarCloseBtn {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 3px;
        color: #94a3b8;
        font-size: 11px;
        font-weight: 700;
    }
    QPushButton#TitleBarMinBtn:hover {
        background-color: #1e293b;
        color: #e2e8f0;
    }
    QPushButton#TitleBarCloseBtn:hover {
        background-color: rgba(239, 68, 68, 0.2);
        border-color: #ef4444;
        color: #ef4444;
    }
"""

_TITLEBAR_STYLE = """
    QWidget#CustomTitleBar {
        background-color: #0b1016;
        border-bottom: 1px solid #1e293b;
    }
    QLabel#TitleBarLabel {
        color: #00c8ff;
        font-size: 10px;
        font-weight: 900;
        letter-spacing: 2px;
    }
""" + _BTN_STYLE


def apply_salva_close_btn_style(btn: QPushButton) -> None:
    """Apply canonical close-button style to an existing QPushButton."""
    btn.setObjectName("TitleBarCloseBtn")
    btn.setFixedSize(20, 18)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(_BTN_STYLE)


def apply_salva_min_btn_style(btn: QPushButton) -> None:
    """Apply canonical minimize-button style to an existing QPushButton."""
    btn.setObjectName("TitleBarMinBtn")
    btn.setFixedSize(20, 18)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(_BTN_STYLE)


class CustomTitleBar(QWidget):
    """Drop-in dark titlebar: drag, minimize, close. No native Windows frame.

    Button size and colors are identical to the main suite window titlebar.
    """

    def __init__(self, title="", parent=None, show_minimize=True):
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(28)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(4)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setObjectName("TitleBarLabel")
        layout.addWidget(self.title_lbl)
        layout.addStretch()

        if show_minimize:
            self.btn_min = QPushButton("−")
            self.btn_min.setObjectName("TitleBarMinBtn")
            self.btn_min.setFixedSize(20, 18)
            self.btn_min.setCursor(Qt.PointingHandCursor)
            self.btn_min.clicked.connect(self._minimize)
            layout.addWidget(self.btn_min)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("TitleBarCloseBtn")
        self.btn_close.setFixedSize(20, 18)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self._close)
        layout.addWidget(self.btn_close)

        self.setStyleSheet(_TITLEBAR_STYLE)

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
