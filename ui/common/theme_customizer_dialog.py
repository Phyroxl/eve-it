"""
ui/common/theme_customizer_dialog.py — Full UI color control for Market Command.
Allows real-time preview and persistence of custom themes with granular section control.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QColorDialog, QTabWidget, QWidget,
    QGridLayout, QMessageBox, QSpacerItem, QSizePolicy, QLineEdit,
    QComboBox
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt, Signal
from ui.theme.theme_manager import ThemeManager
from ui.theme.theme_tokens import DEFAULT_TOKENS, TOKEN_METADATA

class ColorSwatch(QPushButton):
    colorChanged = Signal(str)
    
    def __init__(self, token_key, current_color, parent=None):
        super().__init__(parent)
        self.token_key = token_key
        self.hex_color = current_color
        self.setFixedSize(80, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.update_style()
        self.clicked.connect(self.on_clicked)
        
    def update_style(self):
        # Determine text color (white or black) based on background luminance
        try:
            c = QColor(self.hex_color)
            lum = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
            text_col = "white" if lum < 0.5 else "black"
        except:
            text_col = "white"

        self.setText(self.hex_color.upper())
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.hex_color};
                color: {text_col};
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
                font-size: 9px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: #00c8ff;
            }}
        """ )
        self.setToolTip(f"{self.token_key}: {self.hex_color}")
        
    def on_clicked(self):
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
        
        self.setWindowTitle(f"EXPANDED THEME CUSTOMIZER - {view_scope.upper() if view_scope else 'GLOBAL'}")
        self.resize(750, 850)
        
        # Apply base styling for the dialog itself
        self.setStyleSheet("""
            QDialog { background-color: #05070a; color: #e2e8f0; }
            QLabel { color: #e2e8f0; font-size: 11px; }
            QPushButton { background-color: #10161d; color: #94a3b8; border: 1px solid #1e293b; border-radius: 3px; padding: 6px; }
            QPushButton:hover { border-color: #00c8ff; color: #00c8ff; }
        """ )
        
        self.setup_ui()

    def setup_ui(self):
        main_l = QVBoxLayout(self)
        main_l.setContentsMargins(20, 20, 20, 20)
        main_l.setSpacing(15)
        
        # Header
        header_l = QHBoxLayout()
        title_v = QVBoxLayout()
        header_lbl = QLabel("VISUAL COMMAND CENTER")
        header_lbl.setStyleSheet("color: #00c8ff; font-size: 18px; font-weight: 900; letter-spacing: 3px;")
        sub_lbl = QLabel(f"MODO: {self.view_scope.upper() if self.view_scope else 'GLOBAL'} | SISTEMA DE TOKENS V2")
        sub_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800;")
        title_v.addWidget(header_lbl)
        title_v.addWidget(sub_lbl)
        header_l.addLayout(title_v)
        header_l.addStretch()
        
        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar token...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet("background: #0b1016; border: 1px solid #1e293b; padding: 5px;")
        self.search_input.textChanged.connect(self.on_search_changed)
        header_l.addWidget(self.search_input)
        
        main_l.addLayout(header_l)
        
        # --- NEW: PRESET SELECTION SECTION ---
        preset_frame = QFrame()
        preset_frame.setObjectName("FilterCard")
        preset_frame.setFixedHeight(100)
        preset_l = QHBoxLayout(preset_frame)
        preset_l.setContentsMargins(15, 10, 15, 10)
        
        preset_info_v = QVBoxLayout()
        preset_lbl = QLabel("TEMAS PREDEFINIDOS")
        preset_lbl.setStyleSheet("color: #00c8ff; font-weight: 900; font-size: 10px; letter-spacing: 1px;")
        
        self.preset_combo = QComboBox()
        self.preset_combo.setFixedWidth(250)
        self.preset_combo.setFixedHeight(30)
        
        # Populate with presets
        presets = self.tm.get_available_presets()
        for pid, pdata in presets.items():
            self.preset_combo.addItem(pdata["name"], pid)
            
        # Set current active preset
        active_pid = self.tm.theme_data.get("active_preset", "replicator_core")
        idx = self.preset_combo.findData(active_pid)
        if idx >= 0: self.preset_combo.setCurrentIndex(idx)
        
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        
        preset_info_v.addWidget(preset_lbl)
        preset_info_v.addWidget(self.preset_combo)
        preset_l.addLayout(preset_info_v)
        
        # Swatches Preview
        self.preset_swatches_l = QHBoxLayout()
        self.preset_swatches_l.setSpacing(5)
        self.refresh_preset_preview()
        
        preset_l.addSpacing(20)
        preset_l.addLayout(self.preset_swatches_l)
        
        # Description
        self.preset_desc = QLabel()
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setStyleSheet("color: #94a3b8; font-size: 10px; font-style: italic;")
        self.update_preset_description()
        
        preset_l.addSpacing(20)
        preset_l.addWidget(self.preset_desc, 1)
        
        btn_apply_preset = QPushButton("APLICAR TEMA")
        btn_apply_preset.setFixedWidth(120)
        btn_apply_preset.setFixedHeight(35)
        btn_apply_preset.setStyleSheet("background-color: #00c8ff; color: black; font-weight: 900;")
        btn_apply_preset.clicked.connect(self.on_apply_preset_clicked)
        preset_l.addWidget(btn_apply_preset)
        
        main_l.addWidget(preset_frame)
        # --- END PRESET SECTION ---
        
        # Categories mapping
        self.categories = [
            "VENTANA GENERAL",
            "BARRA SUPERIOR Y PESTAÑAS",
            "CONFIGURACIÓN TÁCTICA",
            "CARDS / RESUMEN SUPERIOR",
            "TABLA PRINCIPAL",
            "DETALLE INFERIOR DEL ITEM",
            "BOTONES",
            "INPUTS / COMBOBOX / SPINBOX / CHECKBOX",
            "ESTADOS / TAGS / TEXTO SEMÁNTICO",
            "SCROLLBARS Y SELECCIÓN",
            "AVANZADO"
        ]
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1e293b; background: #0b1016; margin-top: -1px; }
            QTabBar::tab { background: #070a0e; color: #64748b; padding: 10px 15px; border-right: 1px solid #1e293b; font-size: 9px; font-weight: 800; }
            QTabBar::tab:selected { background: #0b1016; color: #00c8ff; border-bottom: 2px solid #00c8ff; }
            QTabBar::tab:hover { background: #10161d; }
        """ )
        
        self.category_widgets = {} # category -> list of (row_widget, token_key)
        
        for cat_name in self.categories:
            self.add_category_tab(cat_name)
            
        main_l.addWidget(self.tabs)
        
        # Bottom Actions
        actions = QHBoxLayout()
        
        btn_reset_view = QPushButton("RESET ESTA VISTA")
        btn_reset_view.clicked.connect(self.on_reset_view)
        btn_reset_view.setFixedWidth(140)

        btn_reset_replicator = QPushButton("REPLICATOR THEME")
        btn_reset_replicator.clicked.connect(self.on_reset_replicator)
        btn_reset_replicator.setFixedWidth(140)
        btn_reset_replicator.setStyleSheet("background-color: #070B10; border: 1px solid #00D9FF; color: #00D9FF;")
        
        actions.addWidget(btn_reset_view)
        actions.addWidget(btn_reset_replicator)
        actions.addStretch()
        
        btn_cancel = QPushButton("DESCARTAR")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("GUARDAR Y APLICAR")
        btn_save.setFixedWidth(150)
        btn_save.setStyleSheet("background-color: #00c8ff; color: black; font-weight: 900;")
        btn_save.clicked.connect(self.on_save)
        
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_save)
        
        main_l.addLayout(actions)

    def add_category_tab(self, cat_name):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(1) # Tight list
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Filter tokens for this category
        cat_tokens = []
        for k, meta in TOKEN_METADATA.items():
            if meta[1] == cat_name:
                cat_tokens.append((k, meta[0]))
        
        # If no metadata, fall back to matching categories from DEFAULT_TOKENS (optional logic)
        # For now we rely on TOKEN_METADATA
        
        rows = []
        for key, label_text in cat_tokens:
            row = QFrame()
            row.setFixedHeight(45)
            row.setStyleSheet("QFrame { border-bottom: 1px solid #151d27; } QFrame:hover { background: #0d131a; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 0, 10, 0)
            
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold; color: #cbd5e1; font-size: 11px;")
            
            key_lbl = QLabel(f"[{key}]")
            key_lbl.setStyleSheet("color: #475569; font-size: 8px; font-family: monospace;")
            
            rl.addWidget(lbl)
            rl.addSpacing(10)
            rl.addWidget(key_lbl)
            rl.addStretch()
            
            current_val = self.tm.get_token(key, self.view_scope)
            swatch = ColorSwatch(key, current_val)
            swatch.colorChanged.connect(lambda val, k=key: self.on_token_changed(k, val))
            rl.addWidget(swatch)
            
            layout.addWidget(row)
            rows.append((row, key, label_text))
            
        layout.addStretch()
        self.category_widgets[cat_name] = rows
        
        scroll.setWidget(content)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        self.tabs.addTab(page, cat_name)

    def on_search_changed(self, text):
        text = text.lower()
        for cat_name, rows in self.category_widgets.items():
            for row_widget, key, label in rows:
                match = text in key.lower() or text in label.lower()
                row_widget.setVisible(match)

    def on_token_changed(self, key, value):
        self.tm.set_token(key, value, self.view_scope)
        self.apply_live_preview()

    def apply_live_preview(self):
        self.themeUpdated.emit()
        
        # Try to find MarketCommandRoot and apply globally
        root = self.parent()
        found_root = False
        while root:
            if hasattr(root, "apply_market_theme"):
                root.apply_market_theme()
                found_root = True
                break
            root = root.parent()
            
        if not found_root and self.parent():
            # Fallback to local refresh if root not found
            from .theme import Theme
            self.parent().setStyleSheet(Theme.get_qss(self.view_scope))

    def on_save(self):
        self.tm.save_theme()
        QMessageBox.information(self, "TEMA GUARDADO", "La configuración visual ha sido persistida y aplicada con éxito.")
        self.accept()

    def on_reset_view(self):
        if QMessageBox.question(self, "RESET VISTA", f"¿Deseas revertir todos los cambios específicos de {self.view_scope.upper()} al tema global?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.tm.reset_view(self.view_scope)
            self.apply_live_preview()
            self.close()
            
    def on_reset_replicator(self):
        if QMessageBox.question(self, "REPLICATOR THEME", "¿Deseas restaurar la estética original del Replicator en toda la suite Market Command?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.tm.reset_to_replicator()
            self.apply_live_preview()
            self.accept()

    def on_preset_changed(self, index):
        self.refresh_preset_preview()
        self.update_preset_description()
        
    def refresh_preset_preview(self):
        # Clear existing
        while self.preset_swatches_l.count():
            item = self.preset_swatches_l.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        pid = self.preset_combo.currentData()
        presets = self.tm.get_available_presets()
        if pid in presets:
            for color in presets[pid].get("swatches", []):
                sw = QFrame()
                sw.setFixedSize(20, 20)
                sw.setStyleSheet(f"background-color: {color}; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1);")
                self.preset_swatches_l.addWidget(sw)

    def update_preset_description(self):
        pid = self.preset_combo.currentData()
        presets = self.tm.get_available_presets()
        if pid in presets:
            self.preset_desc.setText(presets[pid].get("description", ""))

    def on_apply_preset_clicked(self):
        pid = self.preset_combo.currentData()
        if pid:
            self.tm.apply_preset(pid)
            self.apply_live_preview()
            # We don't close the dialog, just refresh everything
            QMessageBox.information(self, "TEMA APLICADO", f"Se ha aplicado el tema '{pid}' correctamente.")
            # Note: We might want to refresh all ColorSwatches in the tabs too
            # For simplicity, let's just close and reopen or suggest saving
            self.accept()

    def reject(self):
        self.tm.theme_data["global"] = self.original_global
        if self.view_scope:
            self.tm.theme_data["views"][self.view_scope] = self.original_view
        self.apply_live_preview()
        super().reject()
