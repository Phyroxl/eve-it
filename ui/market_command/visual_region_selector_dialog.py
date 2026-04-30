"""
Dialog to manually select screen regions and columns for Visual OCR.
Supports multi-step calibration (Single Side or Full SELL+BUY).
"""
import logging
from typing import Optional, Tuple, Dict, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QWidget, QMessageBox
)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage

_log = logging.getLogger('eve.market.ui')

# Validation constants
MIN_REGION_WIDTH_PX = 350
MIN_REGION_HEIGHT_PX = 180
MIN_COLUMN_WIDTH_PX = 40
MAX_COLUMN_WIDTH_PX = 300

class VisualRegionSelectorDialog(QDialog):
    """
    Shows a screenshot and lets the user draw rectangles for multiple steps.
    Returns a dict mapping step_id to (x0, y0, x1, y1) in pixel coordinates.
    """
    
    def __init__(self, screenshot: QImage, mode: str = "single_side", side: str = "sell", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.side = side
        self.setWindowTitle("CALIBRACIÓN VISUAL MANUAL")
        self.setMinimumSize(1100, 800)
        self.setStyleSheet("background-color:#0f172a; color:#f1f5f9;")
        
        self.original_image = screenshot
        self.pixmap = QPixmap.fromImage(screenshot)
        
        # Steps definition with clearer instructions
        instr_reg = (
            "Selecciona TODO el bloque visible de filas de {}"
            ", desde la primera hasta la última fila visible. "
            "Asegúrate de incluir la fila azul de tu orden."
        )
        instr_qty = (
            "Selecciona la columna CANTIDAD completa, incluyendo TODOS los dígitos. "
            "Ej: si ves 741/745, selecciona desde el 7 hasta el último dígito visible."
        )
        instr_col = "Selecciona solo el ancho horizontal de la columna. La altura no importa."
        
        if self.mode == "sell_buy_full":
            self.steps = [
                {"id": "sell_region", "label": "PASO 1/6: SELECCIONA REGIÓN SELL (Vendedores)", "instr": instr_reg.format("VENDEDORES"), "color": QColor("#3b82f6")},
                {"id": "sell_quantity", "label": "PASO 2/6: COLUMNA CANTIDAD (SELL)", "instr": instr_qty, "color": QColor("#10b981")},
                {"id": "sell_price", "label": "PASO 3/6: COLUMNA PRECIO (SELL)", "instr": instr_col, "color": QColor("#f59e0b")},
                {"id": "buy_region", "label": "PASO 4/6: SELECCIONA REGIÓN BUY (Compradores)", "instr": instr_reg.format("COMPRADORES"), "color": QColor("#3b82f6")},
                {"id": "buy_quantity", "label": "PASO 5/6: COLUMNA CANTIDAD (BUY)", "instr": instr_qty, "color": QColor("#10b981")},
                {"id": "buy_price", "label": "PASO 6/6: COLUMNA PRECIO (BUY)", "instr": instr_col, "color": QColor("#f59e0b")},
            ]
        else:
            s = side.upper()
            s_es = "VENDEDORES" if side == "sell" else "COMPRADORES"
            self.steps = [
                {"id": "region", "label": f"PASO 1/3: SELECCIONA REGIÓN {s}", "instr": instr_reg.format(s_es), "color": QColor("#3b82f6")},
                {"id": "quantity", "label": f"PASO 2/3: COLUMNA CANTIDAD ({s})", "instr": instr_qty, "color": QColor("#10b981")},
                {"id": "price", "label": f"PASO 3/3: COLUMNA PRECIO ({s})", "instr": instr_col, "color": QColor("#f59e0b")}
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
        self.hdr.setStyleSheet("color:#f1f5f9; font-size:13px; font-weight:900;")
        self.hdr.setAlignment(Qt.AlignCenter)
        root.addWidget(self.hdr)
        
        self.sub_hdr = QLabel("")
        self.sub_hdr.setStyleSheet("color:#94a3b8; font-size:10px;")
        self.sub_hdr.setAlignment(Qt.AlignCenter)
        self.sub_hdr.setWordWrap(True)
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
        color_hex = step["color"].name()
        self.hdr.setText(step["label"])
        self.hdr.setStyleSheet(f"color:{color_hex}; font-size:13px; font-weight:900;")
        self.sub_hdr.setText(step["instr"])
        
        self.btn_next.setText("CONFIRMAR Y FINALIZAR" if self.current_step_idx == len(self.steps) - 1 else "CONFIRMAR Y CONTINUAR")
        self.btn_next.setEnabled(not self.selected_rect.isNull())
        self.lbl_coords.setText("Dibujando..." if self.is_drawing else ("Seleccionado" if not self.selected_rect.isNull() else "Esperando selección..."))

    def _on_next(self):
        r = self.selected_rect
        w = r.width()
        h = r.height()
        
        # Validation
        step_id = self.steps[self.current_step_idx]["id"]
        if "region" in step_id:
            if w < MIN_REGION_WIDTH_PX or h < MIN_REGION_HEIGHT_PX:
                QMessageBox.warning(
                    self, "REGIÓN DEMASIADO PEQUEÑA",
                    f"La región seleccionada ({w}x{h} px) es demasiado pequeña.\n\n"
                    f"Mínimo requerido: {MIN_REGION_WIDTH_PX}x{MIN_REGION_HEIGHT_PX} px.\n\n"
                    "Selecciona TODO el bloque visible de filas, desde la primera hasta la última, "
                    "incluyendo tu orden azul."
                )
                return
        elif "quantity" in step_id or "price" in step_id:
            if w < MIN_COLUMN_WIDTH_PX:
                QMessageBox.warning(
                    self, "COLUMNA DEMASIADO ESTRECHA",
                    f"La columna ({w} px) es demasiado estrecha.\n\n"
                    f"Mínimo requerido: {MIN_COLUMN_WIDTH_PX} px.\n\n"
                    "Selecciona solo el ancho horizontal de la columna."
                )
                return
            if w > MAX_COLUMN_WIDTH_PX:
                QMessageBox.warning(
                    self, "COLUMNA DEMASIADO ANCHA",
                    f"La columna ({w} px) es demasiado ancha.\n\n"
                    f"Máximo permitido: {MAX_COLUMN_WIDTH_PX} px.\n\n"
                    "Selecciona solo el ancho horizontal de la columna, no toda la tabla."
                )
                return

        # Save result
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
            
            # Basic non-zero validation
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
        
        # 1. Draw previous results
        for idx, (sid, coords) in enumerate(self.results.items()):
            # Find color for this step
            step_color = QColor(100, 100, 100) # Default
            for s in self.steps:
                if s["id"] == sid:
                    step_color = s["color"]
                    break
            
            x0, y0, x1, y1 = coords
            rect = QRect(QPoint(x0, y0), QPoint(x1, y1))
            
            # Semi-transparent border and fill
            p_color = QColor(step_color)
            p_color.setAlpha(150)
            painter.setPen(QPen(p_color, 1, Qt.DashLine))
            
            f_color = QColor(step_color)
            f_color.setAlpha(30)
            painter.setBrush(f_color)
            painter.drawRect(rect)
            
            # Label the previous step
            painter.setPen(QPen(step_color))
            painter.drawText(rect.topLeft() + QPoint(5, 15), sid)
        
        # 2. Draw current selection
        if self.is_drawing or not self.selected_rect.isNull():
            rect = QRect(self.start_point, self.end_point).normalized() if self.is_drawing else self.selected_rect
            
            curr_color = self.steps[self.current_step_idx]["color"]
            pen = QPen(curr_color, 2, Qt.SolidLine)
            painter.setPen(pen)
            
            fill_color = QColor(curr_color)
            fill_color.setAlpha(60)
            painter.setBrush(fill_color) 
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
