import os
import time
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QPlainTextEdit, QLabel, QApplication
)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt

class MarketDiagnosticsDialog(QDialog):
    def __init__(self, report_text: str, parent=None):
        super().__init__(parent)
        self.report_text = report_text
        self.setWindowTitle("Market Command — Diagnóstico del Escaneo")
        self.setMinimumSize(700, 800)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel("REPORTE INTERNO DEL PIPELINE DE MERCADO")
        header.setStyleSheet("color: #3b82f6; font-weight: 900; font-size: 14px; letter-spacing: 1px;")
        layout.addWidget(header)

        desc = QLabel("Copia este reporte y pégalo en el chat para diagnosticar problemas de filtrado.")
        desc.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(desc)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(self.report_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #000000;
                color: #d1d5db;
                border: 1px solid #1e293b;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.text_edit, 1)

        btn_layout = QHBoxLayout()
        
        self.btn_copy = QPushButton("COPIAR REPORTE")
        self.btn_copy.setFixedHeight(35)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white; font-weight: 800; border-radius: 4px; padding: 0 20px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        
        self.btn_save = QPushButton("GUARDAR TXT")
        self.btn_save.setFixedHeight(35)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #f1f5f9; font-weight: 800; border-radius: 4px; padding: 0 20px;
            }
            QPushButton:hover { background-color: #334155; }
        """)
        self.btn_save.clicked.connect(self.save_to_file)

        self.btn_close = QPushButton("CERRAR")
        self.btn_close.setFixedHeight(35)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #64748b; font-weight: 800; border: 1px solid #1e293b; border-radius: 4px; padding: 0 20px;
            }
            QPushButton:hover { background-color: #1e293b; }
        """)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_copy)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.report_text)
        self.btn_copy.setText("¡COPIADO!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.btn_copy.setText("COPIAR REPORTE"))

    def save_to_file(self):
        try:
            diag_dir = os.path.join(os.getcwd(), "data", "diagnostics")
            os.makedirs(diag_dir, exist_ok=True)
            filename = f"market_scan_{int(time.time())}.txt"
            path = os.path.join(diag_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.report_text)
            self.btn_save.setText("¡GUARDADO!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.btn_save.setText("GUARDAR TXT"))
        except Exception as e:
            print(f"Error saving diagnostic: {e}")
            self.btn_save.setText("ERROR")
