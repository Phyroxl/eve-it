from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
    QGraphicsDropShadowEffect, QPushButton
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, Property
from PySide6.QtGui import QColor, QFont, QCursor

class AnimatedCard(QFrame):
    """
    Una tarjeta con efectos de iluminación y micro-animaciones al pasar el mouse.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CharacterCard")
        self._setup_animation()
        
    def _setup_animation(self):
        # Animación de escala/posicionamiento suave
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # Efecto de sombra (glow) dinámico
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.BlurRadius = 15
        self.shadow.setColor(QColor(0, 200, 255, 0))
        self.shadow.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow)
        
        self._shadow_anim = QPropertyAnimation(self.shadow, b"color")
        self._shadow_anim.setDuration(300)
        
    def enterEvent(self, event):
        self._shadow_anim.setEndValue(QColor(0, 200, 255, 100))
        self._shadow_anim.start()
        # Mover ligeramente hacia arriba (efecto lift)
        geom = self.geometry()
        self._original_geom = QRect(geom)
        self._anim.setEndValue(QRect(geom.x(), geom.y() - 3, geom.width(), geom.height()))
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow_anim.setEndValue(QColor(0, 200, 255, 0))
        self._shadow_anim.start()
        if hasattr(self, '_original_geom'):
            self._anim.setEndValue(self._original_geom)
            self._anim.start()
        super().leaveEvent(event)

class IndustrialBadge(QLabel):
    """
    Un badge con estilo militar/industrial para estados y etiquetas.
    """
    def __init__(self, text, color="#00c8ff", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f\"\"\"
            QLabel {{
                background: rgba({self._hex_to_rgb(color)}, 0.1);
                color: {color};
                border: 1px solid {color};
                padding: 2px 6px;
                font-family: 'Share Tech Mono';
                font-size: 9px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
                border-radius: 2px;
            }}
        \"\"\")

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return f\"{int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}\"
