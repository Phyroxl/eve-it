"""
ui/common/theme_manager.py — Dynamic Theme Management for EVE iT Market Command.
Handles loading, saving, and applying custom color tokens.
"""
import json
import os
import logging
from PySide6.QtGui import QColor

_log = logging.getLogger('eve.theme_manager')

DEFAULT_TOKENS = {
    # --- GENERAL ---
    "BG_MAIN": "#05070a",
    "BG_WINDOW": "#05070a",
    "BG_PANEL": "#0b1016",
    "BG_PANEL_ALT": "#10161d",
    "BG_NAV": "#070a0e",
    "ACCENT": "#00c8ff",
    "ACCENT_HOVER": "#33d6ff",
    "ACCENT_LOW": "rgba(0, 200, 255, 0.2)",
    "BORDER": "rgba(0, 180, 255, 0.3)",
    "BORDER_BRIGHT": "rgba(0, 180, 255, 0.6)",
    
    # --- TEXT & SEMANTIC ---
    "TEXT_MAIN": "#e2e8f0",
    "TEXT_DIM": "#64748b",
    "SUCCESS": "#00ffcc",
    "DANGER": "#ff3232",
    "WARNING": "#ffb800",
    "NEUTRAL": "#94a3b8",
    "INFO": "#3b82f6",
    
    # --- TABLES ---
    "TABLE_BG": "#0b1016",
    "TABLE_HEADER_BG": "#070a0e",
    "TABLE_TEXT": "#e2e8f0",
    "TABLE_GRID": "rgba(0, 180, 255, 0.2)",
    "TABLE_SELECT_BG": "rgba(0, 200, 255, 0.15)",
    
    # --- INPUTS ---
    "INPUT_BG": "#070a0e",
    "INPUT_BORDER": "rgba(0, 180, 255, 0.3)",
    "INPUT_TEXT": "#e2e8f0",
    
    # --- BUTTONS ---
    "BTN_PRIMARY_BG": "#10161d",
    "BTN_PRIMARY_TEXT": "#00c8ff",
    "BTN_PRIMARY_BORDER": "rgba(0, 200, 255, 0.4)",
    "BTN_SECONDARY_BG": "#0b1016",
    "BTN_SECONDARY_TEXT": "#94a3b8",
    "BTN_DANGER_BG": "rgba(255, 50, 50, 0.1)",
    "BTN_DANGER_TEXT": "#ff3232",
    
    # --- STATES & TRADING ---
    "COLOR_BUY": "#00ffcc",
    "COLOR_SELL": "#ff3232",
    "COLOR_PROFIT_POS": "#00ffcc",
    "COLOR_PROFIT_NEG": "#ff3232",
    "COLOR_ROI": "#00c8ff",
    "COLOR_SCORE_HIGH": "#00ffcc",
    "COLOR_SCORE_MID": "#ffb800",
    "COLOR_SCORE_LOW": "#ff3232",
    
    # --- CHARTS & METRICS ---
    "CHART_LINE": "#00c8ff",
    "CHART_FILL": "rgba(0, 200, 255, 0.1)",
    "METRIC_VALUE": "#e2e8f0",
    "METRIC_LABEL": "#64748b",
}

class ThemeManager:
    _instance = None
    
    def __init__(self):
        self.config_path = os.path.join("config", "ui_theme_market_command.json")
        self.theme_data = {
            "version": 1,
            "global": DEFAULT_TOKENS.copy(),
            "views": {
                "simple": {},
                "performance": {},
                "my_orders": {},
                "contracts": {}
            }
        }
        self.load_theme()
        
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance
    
    def load_theme(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "global" in data:
                        self.theme_data["global"].update(data["global"])
                    if "views" in data:
                        for view, tokens in data["views"].items():
                            if view in self.theme_data["views"]:
                                self.theme_data["views"][view].update(tokens)
                _log.info("Theme loaded successfully.")
            except Exception as e:
                _log.error(f"Error loading theme: {e}")
                
    def save_theme(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.theme_data, f, indent=2)
            _log.info("Theme saved successfully.")
        except Exception as e:
            _log.error(f"Error saving theme: {e}")
            
    def get_token(self, key, view_scope=None):
        if view_scope and view_scope in self.theme_data["views"]:
            val = self.theme_data["views"][view_scope].get(key)
            if val: return val
        return self.theme_data["global"].get(key, DEFAULT_TOKENS.get(key, "#ff00ff"))

    def set_token(self, key, value, view_scope=None):
        if view_scope:
            if view_scope not in self.theme_data["views"]:
                self.theme_data["views"][view_scope] = {}
            self.theme_data["views"][view_scope][key] = value
        else:
            self.theme_data["global"][key] = value
            
    def reset_view(self, view_scope):
        if view_scope in self.theme_data["views"]:
            self.theme_data["views"][view_scope] = {}
            
    def reset_all(self):
        self.theme_data["global"] = DEFAULT_TOKENS.copy()
        for v in self.theme_data["views"]:
            self.theme_data["views"][v] = {}

    def get_qss(self, view_scope=None):
        """Generates dynamic QSS based on current tokens."""
        t = lambda k: self.get_token(k, view_scope)
        
        return f"""
            /* Dynamic Market Command Theme */
            
            QWidget {{
                color: {t('TEXT_MAIN')};
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }}
            
            QMainWindow, QWidget#MarketCommandRoot {{
                background-color: {t('BG_WINDOW')};
            }}
            
            QFrame#AnalyticBox, QFrame#MetricCard, QFrame#DetailPanel {{
                background-color: {t('BG_PANEL')};
                border: 1px solid {t('BORDER')};
                border-radius: 4px;
            }}
            
            QFrame#TacticalPanel {{
                background-color: {t('BG_PANEL_ALT')};
                border: 1px solid {t('BORDER')};
            }}
            
            QLabel#MetricTitle {{
                color: {t('ACCENT')};
                font-size: 8px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            QLabel#MetricValue {{
                color: {t('METRIC_VALUE')};
                font-size: 13px;
                font-weight: 800;
            }}
            
            /* TABLES */
            QTableWidget {{
                background-color: {t('TABLE_BG')};
                gridline-color: {t('TABLE_GRID')};
                color: {t('TABLE_TEXT')};
                selection-background-color: {t('TABLE_SELECT_BG')};
                border: 1px solid {t('BORDER')};
                font-size: 11px;
            }}
            
            QHeaderView::section {{
                background-color: {t('TABLE_HEADER_BG')};
                color: {t('TEXT_DIM')};
                padding: 6px;
                border: none;
                border-bottom: 1px solid {t('BORDER')};
                font-weight: bold;
            }}
            
            /* INPUTS */
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background-color: {t('INPUT_BG')};
                border: 1px solid {t('INPUT_BORDER')};
                color: {t('INPUT_TEXT')};
                padding: 4px;
                border-radius: 2px;
            }}
            
            QLineEdit:focus, QComboBox:focus {{
                border-color: {t('ACCENT')};
            }}
            
            /* BUTTONS */
            QPushButton {{
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 800;
                font-size: 10px;
                text-transform: uppercase;
            }}
            
            QPushButton#PrimaryButton {{
                background-color: {t('BTN_PRIMARY_BG')};
                color: {t('BTN_PRIMARY_TEXT')};
                border: 1px solid {t('BTN_PRIMARY_BORDER')};
            }}
            
            QPushButton#PrimaryButton:hover {{
                border-color: {t('ACCENT')};
                background-color: {t('BG_PANEL')};
            }}
            
            QPushButton#SecondaryButton {{
                background-color: {t('BTN_SECONDARY_BG')};
                color: {t('BTN_SECONDARY_TEXT')};
                border: 1px solid {t('BORDER')};
            }}
            
            QPushButton#DangerButton {{
                background-color: {t('BTN_DANGER_BG')};
                color: {t('BTN_DANGER_TEXT')};
                border: 1px solid {t('DANGER')};
            }}
            
            /* SCROLLBARS */
            QScrollBar:vertical {{
                background: {t('BG_MAIN')};
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {t('BG_PANEL_ALT')};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """
