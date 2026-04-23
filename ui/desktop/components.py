from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, 
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QPolygonF

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
        rgb = self._hex_to_rgb(color)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: rgba({rgb}, 0.1);
                color: {color};
                border: 1px solid rgba({rgb}, 0.3);
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
                border-radius: 10px;
            }}
        """)

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        return f"{int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}"

class TelemetryChart(QFrame):
    """
    Mini gráfico de telemetría de alto rendimiento (ISK acumulado).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setFixedHeight(65)
        self.setObjectName("AnalyticBox")

    def set_data(self, values):
        if self.data == values: return
        self.data = values
        self.update()

    def paintEvent(self, event):
        if len(self.data) < 2: return
        with QPainter(self) as p:
            p.setRenderHint(QPainter.Antialiasing)
            
            w = self.width(); h = self.height()
            max_val = max(self.data) if self.data else 1
            if max_val == 0: max_val = 1
            
            points = []
            step = w / (len(self.data) - 1)
            for i, val in enumerate(self.data):
                x = i * step
                # Escala invertida para Qt (y=0 arriba) con 10% margen
                y = h - (val / max_val * (h * 0.75)) - (h * 0.12)
                points.append(QPointF(x, y))
                
            # 1. Dibujar Área de Relleno (Gradient)
            poly = QPolygonF(points)
            poly.append(QPointF(w, h))
            poly.append(QPointF(0, h))
            
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor(37, 99, 235, 60)) # Blue-600
            grad.setColorAt(1, QColor(37, 99, 235, 0))
            p.setBrush(grad); p.setPen(Qt.NoPen)
            p.drawPolygon(poly)
            
            # 2. Dibujar Línea Principal
            pen = QPen(QColor("#60a5fa"), 1.5) # Blue-400
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            for i in range(len(points) - 1):
                p.drawLine(points[i], points[i+1])
                
            # 3. Punto Final (Efecto "Active")
            last = points[-1]
            p.setBrush(QColor("#60a5fa")); p.setPen(Qt.NoPen)
            p.drawEllipse(last, 2.5, 2.5)
