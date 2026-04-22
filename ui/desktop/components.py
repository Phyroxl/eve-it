from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

class AnimatedCard(QFrame):
    """
    Una tarjeta simple y limpia con un sutil efecto de hover.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CharacterCard")
        
    def enterEvent(self, event):
        # Efecto visual manejado principalmente por CSS para simplicidad
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

class IndustrialBadge(QLabel):
    """
    Un badge de estado simple y profesional.
    """
    def __init__(self, text, color="#3182ce", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f\"\"\"
            QLabel {{
                background-color: rgba({self._hex_to_rgb(color)}, 0.1);
                color: {color};
                border: 1px solid rgba({self._hex_to_rgb(color)}, 0.3);
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
                border-radius: 10px;
            }}
        \"\"\")

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        return f\"{int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}\"
