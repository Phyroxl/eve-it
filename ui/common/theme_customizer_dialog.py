"""
ui/common/theme_customizer_dialog.py — Full UI color control for Market Command.
Allows real-time preview and persistence of custom themes.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QColorDialog, QTabWidget, QWidget,
    QGridLayout, QMessageBox, QSpacerItem, QSizePolicy
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt, Signal
from .theme_manager import ThemeManager, DEFAULT_TOKENS

class ColorSwatch(QPushButton):
    colorChanged = Signal(str)
    
    def __init__(self, token_key, current_color, parent=None):
        super().__init__(parent)
        self.token_key = token_key
        self.hex_color = current_color
        self.setFixedSize(70, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.update_style()
        self.clicked.connect(self.on_clicked)
        
    def update_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.hex_color};
                border: 2px solid #333;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: #00c8ff;
            }}
        """ )
        self.setToolTip(f"{self.token_key}: {self.hex_color}")
        
    def on_clicked(self):
        # Ensure we have a valid QColor for the dialog
        initial_color = QColor(self.hex_color) if self.hex_color.startswith("#") else Qt.white
        col = QColorDialog.getColor(initial_color, self, f"Color: {self.token_key}")
        if col.isValid():
            self.hex_color = col.name()
            self.update_style()
            self.colorChanged.emit(self.hex_color)

class ThemeCustomizerDialog(QDialog):
    themeUpdated = Signal()

    def __init__(self, view_scope=None, parent=None):
        super().__init__(parent)
        self.view_scope = view_scope
        self.tm = ThemeManager.instance()
        
        # Working copy for live preview
        self.original_global = self.tm.theme_data["global"].copy()
        self.original_view = self.tm.theme_data["views"].get(view_scope, {}).copy() if view_scope else {}
        
        self.setWindowTitle(f"PERSONALIZACIÓN VISUAL - {view_scope.upper() if view_scope else 'GLOBAL'}")
        self.setMinimumWidth(550)
        self.setMinimumHeight(700)
        
        # Apply base styling for the dialog itself
        self.setStyleSheet(f"""
            QDialog {{ background-color: #05070a; color: #e2e8f0; }}
            QLabel {{ color: #e2e8f0; font-size: 11px; }}
            QPushButton {{ background-color: #10161d; color: #94a3b8; border: 1px solid #1e293b; border-radius: 3px; padding: 6px; }}
            QPushButton:hover {{ border-color: #00c8ff; color: #00c8ff; }}
        """ )
        
        self.setup_ui()

    def setup_ui(self):
        main_l = QVBoxLayout(self)
        main_l.setContentsMargins(15, 15, 15, 15)
        
        header = QLabel("THEME COMMAND CENTER")
        header.setStyleSheet("color: #00c8ff; font-size: 16px; font-weight: 900; letter-spacing: 2px;")
        main_l.addWidget(header)
        
        sub = QLabel(f"Personalizando: {self.view_scope.upper() if self.view_scope else 'TEMA GLOBAL'}")
        sub.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800;")
        main_l.addWidget(sub)
        
        main_l.addSpacing(10)
        
        # Tabs for categorization
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1e293b; background: #0b1016; }
            QTabBar::tab { background: #070a0e; color: #64748b; padding: 8px 15px; border-right: 1px solid #1e293b; }
            QTabBar::tab:selected { background: #0b1016; color: #00c8ff; border-bottom: 2px solid #00c8ff; }
        """ )
        
        # Create categories
        self.add_category_tab(tabs, "GENERAL", ["BG_WINDOW", "BG_PANEL", "BG_PANEL_ALT", "BG_NAV", "ACCENT", "BORDER"])
        self.add_category_tab(tabs, "TEXTOS", ["TEXT_MAIN", "TEXT_DIM", "SUCCESS", "DANGER", "WARNING", "INFO"])
        self.add_category_tab(tabs, "TABLAS", ["TABLE_BG", "TABLE_HEADER_BG", "TABLE_TEXT", "TABLE_GRID", "TABLE_SELECT_BG"])
        self.add_category_tab(tabs, "BOTONES", ["BTN_PRIMARY_BG", "BTN_PRIMARY_TEXT", "BTN_SECONDARY_BG", "BTN_SECONDARY_TEXT", "BTN_DANGER_BG", "BTN_DANGER_TEXT"])
        self.add_category_tab(tabs, "TRADING", ["COLOR_BUY", "COLOR_SELL", "COLOR_PROFIT_POS", "COLOR_PROFIT_NEG", "COLOR_ROI", "COLOR_SCORE_HIGH", "COLOR_SCORE_MID", "COLOR_SCORE_LOW"])
        self.add_category_tab(tabs, "METRICAS", ["CHART_LINE", "CHART_FILL", "METRIC_VALUE", "METRIC_LABEL"])
        
        main_l.addWidget(tabs)
        
        # Bottom Actions
        actions = QHBoxLayout()
        btn_reset_view = QPushButton("RESET ESTA VISTA")
        btn_reset_view.clicked.connect(self.on_reset_view)
        
        btn_reset_all = QPushButton("RESET GLOBAL")
        btn_reset_all.clicked.connect(self.on_reset_all)
        
        actions.addWidget(btn_reset_view)
        actions.addWidget(btn_reset_all)
        actions.addStretch()
        
        btn_cancel = QPushButton("CANCELAR")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("GUARDAR TEMA")
        btn_save.setFixedWidth(120)
        btn_save.setStyleSheet("background-color: #00c8ff; color: black; font-weight: bold;")
        btn_save.clicked.connect(self.on_save)
        
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_save)
        
        main_l.addLayout(actions)

    def add_category_tab(self, tabs, title, tokens):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        content = QWidget()
        layout = QGridLayout(content)
        layout.setSpacing(10)
        
        for i, key in enumerate(tokens):
            lbl = QLabel(key.replace("_", " "))
            lbl.setStyleSheet("font-weight: bold; color: #cbd5e1;")
            
            # Use current theme value
            current_val = self.tm.get_token(key, self.view_scope)
            swatch = ColorSwatch(key, current_val)
            swatch.colorChanged.connect(lambda val, k=key: self.on_token_changed(k, val))
            
            layout.addWidget(lbl, i, 0)
            layout.addWidget(swatch, i, 1, Qt.AlignRight)
            
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), len(tokens), 0)
        
        scroll.setWidget(content)
        v = QVBoxLayout(page)
        v.addWidget(scroll)
        tabs.addTab(page, title)

    def on_token_changed(self, key, value):
        # Live preview update (only in memory for now)
        self.tm.set_token(key, value, self.view_scope)
        self.apply_live_preview()

    def apply_live_preview(self):
        # Signal to parents that theme changed
        from .theme import Theme
        # In a real app, we'd find the main window and update its stylesheet
        # For now, we emit a signal and hope the caller handles it
        self.themeUpdated.emit()
        
        # We also try to apply to the parent if it's a QWidget
        if self.parent() and isinstance(self.parent(), QWidget):
            self.parent().setStyleSheet(Theme.get_qss(self.view_scope))

    def on_save(self):
        self.tm.save_theme()
        QMessageBox.information(self, "TEMA GUARDADO", "La configuración visual ha sido persistida con éxito.")
        self.accept()

    def on_reset_view(self):
        if QMessageBox.question(self, "RESET VISTA", "¿Deseas revertir los cambios de ESTA pestaña al tema global?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.tm.reset_view(self.view_scope)
            self.apply_live_preview()
            self.close() # Simple way to refresh
            
    def on_reset_all(self):
        if QMessageBox.question(self, "RESET GLOBAL", "¿Deseas revertir TODO el tema de Market Command a los valores de fábrica?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.tm.reset_all()
            self.apply_live_preview()
            self.close()

    def reject(self):
        # Revert changes by reloading or restoring
        self.tm.theme_data["global"] = self.original_global
        if self.view_scope:
            self.tm.theme_data["views"][self.view_scope] = self.original_view
        self.apply_live_preview()
        super().reject()
