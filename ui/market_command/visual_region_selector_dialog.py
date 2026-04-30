"""
Dialog to manually select screen regions and columns for Visual OCR.
Supports multi-step calibration (Region -> Quantity Column -> Price Column).
"""
import logging
from typing import Optional, Tuple, Dict, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage

_log = logging.getLogger('eve.market.ui')

class VisualRegionSelectorDialog(QDialog):
    """
    Shows a screenshot and lets the user draw rectangles for multiple steps.
    Returns a dict mapping step_id to (x0, y0, x1, y1) in pixel coordinates.
    """
    
    def __init__(self, screenshot: QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CALIBRACIÓN VISUAL MANUAL")
        self.setMinimumSize(1100, 800)
        self.setStyleSheet("background-color:#0f172a; color:#f1f5f9;")
        
        self.original_image = screenshot
        self.pixmap = QPixmap.fromImage(screenshot)
        
        # Steps definition
        self.steps = [
            {"id": "region", "label": "PASO 1/3: SELECCIONA LA REGIÓN DE LAS FILAS (ÁREA TOTAL DE ÓRDENES)"},
            {"id": "quantity", "label": "PASO 2/3: SELECCIONA EL ANCHO DE LA COLUMNA 'CANTIDAD'"},
            {"id": "price", "label": "PASO 3/3: SELECCIONA EL ANCHO DE LA COLUMNA 'PRECIO'"}
        ]
        self.current_step_idx = 0
        self.results: Dict[str, Tuple[int, int, int, int]] = {}
        
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_drawing = False
        self.selected_rect = QRect()
        
        self._setup_ui()
        self._update_step_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        
        self.hdr = QLabel("")
        self.hdr.setStyleSheet("color:#3b82f6; font-size:12px; font-weight:900;")
        self.hdr.setAlignment(Qt.AlignCenter)
        root.addWidget(self.hdr)
        
        self.sub_hdr = QLabel("Haz clic y arrastra para dibujar un rectángulo sobre la zona indicada.")
        self.sub_hdr.setStyleSheet("color:#64748b; font-size:10px;")
        self.sub_hdr.setAlignment(Qt.AlignCenter)
        root.addWidget(self.sub_hdr)
        
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
        
        self.lbl_coords = QLabel("Sin selección")
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
        
        self.btn_next = QPushButton("SIGUIENTE")
        self.btn_next.setEnabled(False)
        self.btn_next.setStyleSheet(
            "QPushButton { background:#065f46; color:white; font-weight:700; padding:8px 20px; border-radius:4px; }"
            "QPushButton:hover { background:#059669; }"
            "QPushButton:disabled { background:#1e293b; color:#475569; }"
        )
        self.btn_next.clicked.connect(self._on_next)
        btn_row.addWidget(self.btn_next)
        
        root.addLayout(btn_row)

    def _update_step_ui(self):
        step = self.steps[self.current_step_idx]
        self.hdr.setText(step["label"])
        self.btn_next.setText("CONFIRMAR Y FINALIZAR" if self.current_step_idx == len(self.steps) - 1 else "CONFIRMAR Y CONTINUAR")
        self.btn_next.setEnabled(not self.selected_rect.isNull())
        self.lbl_coords.setText("Dibujando..." if self.is_drawing else ("Seleccionado" if not self.selected_rect.isNull() else "Esperando selección..."))

    def _on_next(self):
        step_id = self.steps[self.current_step_idx]["id"]
        r = self.selected_rect
        self.results[step_id] = (r.left(), r.top(), r.right(), r.bottom())
        
        if self.current_step_idx < len(self.steps) - 1:
            self.current_step_idx += 1
            self.selected_rect = QRect() # Reset for next step
            self._update_step_ui()
            self.image_label.update()
        else:
            self.accept()

    def _on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_drawing = True
            self.image_label.update()

    def _on_mouse_move(self, event):
        if self.is_drawing:
            self.end_point = event.pos()
            self.image_label.update()

    def _on_mouse_release(self, event):
        if event.button() == Qt.LeftButton:
            self.end_point = event.pos()
            self.is_drawing = False
            self.selected_rect = QRect(self.start_point, self.end_point).normalized()
            
            # Simple validation: must be more than a click
            if self.selected_rect.width() > 5 and self.selected_rect.height() > 5:
                self.btn_next.setEnabled(True)
                r = self.selected_rect
                self.lbl_coords.setText(f"Seleccionado: {r.width()}x{r.height()} px")
            else:
                self.selected_rect = QRect()
                self.btn_next.setEnabled(False)
                self.lbl_coords.setText("Selección demasiado pequeña")
            
            self.image_label.update()

    def _on_paint(self, event):
        painter = QPainter(self.image_label)
        painter.drawPixmap(0, 0, self.pixmap)
        
        # 1. Draw previous results in grey
        for sid, coords in self.results.items():
            x0, y0, x1, y1 = coords
            rect = QRect(QPoint(x0, y0), QPoint(x1, y1))
            painter.setPen(QPen(QColor(100, 100, 100, 150), 1, Qt.DashLine))
            painter.setBrush(QColor(100, 100, 100, 30))
            painter.drawRect(rect)
            # Label the previous step
            painter.drawText(rect.topLeft() + QPoint(5, 15), sid)
        
        # 2. Draw current selection
        if self.is_drawing or not self.selected_rect.isNull():
            rect = QRect(self.start_point, self.end_point).normalized() if self.is_drawing else self.selected_rect
            
            color = QColor("#3b82f6")
            pen = QPen(color, 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(QColor(59, 130, 246, 50)) 
            painter.drawRect(rect)
            
            # Add label for current step
            step_name = self.steps[self.current_step_idx]["id"].upper()
            painter.setPen(QPen(Qt.white))
            painter.drawText(rect.topLeft() + QPoint(5, -5), f"ACTUAL: {step_name}")

    def get_results(self) -> Dict[str, Tuple[int, int, int, int]]:
        """Return dict of step_id -> (x0, y0, x1, y1)."""
        return self.results

    def get_region(self) -> Optional[Tuple[int, int, int, int]]:
        """Legacy compatibility for the first step."""
        return self.results.get("region")
