"""
Dialog to manually select a screen region for Visual OCR.
Displays a screenshot and allows drawing a rectangle with the mouse.
"""
from typing import Optional, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage

class VisualRegionSelectorDialog(QDialog):
    """
    Shows a screenshot and lets the user draw a rectangle.
    Returns (x0, y0, x1, y1) in pixel coordinates.
    """
    
    def __init__(self, screenshot: QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CALIBRACIÓN MANUAL - SELECCIONA REGIÓN DE ÓRDENES")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("background-color:#0f172a; color:#f1f5f9;")
        
        self.original_image = screenshot
        self.pixmap = QPixmap.fromImage(screenshot)
        
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_drawing = False
        self.selected_rect = QRect()
        
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        
        hdr = QLabel("DIBUJA UN RECTÁNGULO SOBRE LA ZONA DE LAS ÓRDENES (PRECIO/CANTIDAD)")
        hdr.setStyleSheet("color:#3b82f6; font-size:11px; font-weight:900;")
        hdr.setAlignment(Qt.AlignCenter)
        root.addWidget(hdr)
        
        # Scroll area for the image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: 1px solid #1e293b; background:#000000;")
        
        self.image_label = QLabel()
        self.image_label.setPixmap(self.pixmap)
        self.image_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        
        # Overlay drawing logic
        self.image_label.mousePressEvent = self._on_mouse_press
        self.image_label.mouseMoveEvent = self._on_mouse_move
        self.image_label.mouseReleaseEvent = self._on_mouse_release
        self.image_label.paintEvent = self._on_paint
        
        self.scroll_area.setWidget(self.image_label)
        root.addWidget(self.scroll_area)
        
        # Buttons
        btn_row = QHBoxLayout()
        
        self.lbl_coords = QLabel("Sin región seleccionada")
        self.lbl_coords.setStyleSheet("color:#64748b; font-size:10px;")
        btn_row.addWidget(self.lbl_coords)
        
        btn_row.addStretch()
        
        self.btn_cancel = QPushButton("CANCELAR")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background:#1e293b; color:white; font-weight:700; padding:8px 20px; border-radius:4px; }"
            "QPushButton:hover { background:#334155; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        
        self.btn_confirm = QPushButton("CONFIRMAR REGIÓN")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setStyleSheet(
            "QPushButton { background:#065f46; color:white; font-weight:700; padding:8px 20px; border-radius:4px; }"
            "QPushButton:hover { background:#059669; }"
            "QPushButton:disabled { background:#1e293b; color:#475569; }"
        )
        self.btn_confirm.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_confirm)
        
        root.addLayout(btn_row)

    def _on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_drawing = True
            self.update()

    def _on_mouse_move(self, event):
        if self.is_drawing:
            self.end_point = event.pos()
            self.image_label.update()

    def _on_mouse_release(self, event):
        if event.button() == Qt.LeftButton:
            self.end_point = event.pos()
            self.is_drawing = False
            self.selected_rect = QRect(self.start_point, self.end_point).normalized()
            
            if self.selected_rect.width() > 10 and self.selected_rect.height() > 10:
                self.btn_confirm.setEnabled(True)
                r = self.selected_rect
                self.lbl_coords.setText(f"Región: {r.width()}x{r.height()} px  (x:{r.x()}, y:{r.y()})")
            else:
                self.btn_confirm.setEnabled(False)
            
            self.image_label.update()

    def _on_paint(self, event):
        # First draw the original pixmap
        painter = QPainter(self.image_label)
        painter.drawPixmap(0, 0, self.pixmap)
        
        # Then draw the selection rectangle
        if self.is_drawing or not self.selected_rect.isNull():
            rect = QRect(self.start_point, self.end_point).normalized() if self.is_drawing else self.selected_rect
            
            # Semi-transparent overlay outside the rect? (optional)
            # For now just a thick border
            pen = QPen(QColor("#3b82f6"), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(QColor(59, 130, 246, 50)) # Light blue transparent fill
            painter.drawRect(rect)
            
            # Crosshair or corner handles could be added here

    def get_region(self) -> Optional[Tuple[int, int, int, int]]:
        """Return (x0, y0, x1, y1) or None."""
        if self.selected_rect.isNull():
            return None
        r = self.selected_rect
        return (r.left(), r.top(), r.right(), r.bottom())
