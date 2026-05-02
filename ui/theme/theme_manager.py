"""
ui/theme/theme_manager.py — Centralized Theme Engine for Market Command.
Supports dynamic tokens, custom overrides, and 20+ preset themes.
"""
import os
import json
import logging
from .theme_tokens import DEFAULT_TOKENS
from .theme_presets import THEME_PRESETS

_log = logging.getLogger('eve.theme_manager')

class ThemeManager:
    _instance = None
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def __init__(self):
        self.config_path = os.path.join("config", "ui_theme_market_command.json")
        self.theme_data = {
            "active_preset": "replicator_core",
            "global": DEFAULT_TOKENS.copy(),
            "views": {}
        }
        self.load_theme()
        
    def load_theme(self):
        """Loads theme with robust recovery and preset support."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if not isinstance(data, dict):
                    raise ValueError("Configuración de tema inválida.")

                # Load active preset first
                self.theme_data["active_preset"] = data.get("active_preset", "replicator_core")
                
                # Apply global tokens (user overrides over preset/default)
                if "global" in data:
                    for k, v in data["global"].items():
                        if k in self.theme_data["global"]:
                            self.theme_data["global"][k] = v
                
                # Apply view-specific overrides
                if "views" in data:
                    for view, tokens in data["views"].items():
                        if view in self.theme_data["views"] and isinstance(tokens, dict):
                            self.theme_data["views"][view].update(tokens)
                            
                _log.info(f"[THEME] Loaded theme. Active Preset: {self.theme_data['active_preset']}")
            except Exception as e:
                _log.error(f"[THEME] Fallback to Replicator core due to error: {e}")
                self.handle_corrupt_config()

    def handle_corrupt_config(self):
        try:
            if os.path.exists(self.config_path):
                broken_path = self.config_path + ".broken"
                if os.path.exists(broken_path): os.remove(broken_path)
                os.rename(self.config_path, broken_path)
        except: pass
        self.reset_all()

    def save_theme(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.theme_data, f, indent=2)
            _log.info("Theme saved successfully.")
        except Exception as e:
            _log.error(f"Error saving theme: {e}")

    def apply_preset(self, preset_id, scope="global"):
        """Applies a preset theme. If scope is 'global', it clears most manual overrides."""
        if preset_id not in THEME_PRESETS:
            _log.warning(f"Preset {preset_id} not found.")
            return False
            
        preset = THEME_PRESETS[preset_id]
        _log.info(f"[THEME] Applying preset: {preset['name']}")
        
        if scope == "global":
            self.theme_data["active_preset"] = preset_id
            new_global = DEFAULT_TOKENS.copy()
            new_global.update(preset.get("tokens", {}))
            
            # Smart derivation for missing tactical/detail tokens
            bg = new_global.get("BG_WINDOW", "#05070a")
            nav = new_global.get("NAV_BG", "#0b1016")
            accent = new_global.get("ACCENT", "#00c8ff")
            
            def derive_tokens(tokens):
                # If a preset is minimal, we fill the gaps intelligently
                if "SIDEBAR_BG" not in tokens: tokens["SIDEBAR_BG"] = bg
                if "DETAIL_PANEL_BG" not in tokens: tokens["DETAIL_PANEL_BG"] = bg
                if "CARD_BG" not in tokens: tokens["CARD_BG"] = nav
                if "FILTER_CARD_BG" not in tokens: tokens["FILTER_CARD_BG"] = nav
                if "INPUT_BG" not in tokens: tokens["INPUT_BG"] = nav
                if "BTN_PRIMARY_BG" not in tokens: tokens["BTN_PRIMARY_BG"] = nav
                if "BTN_SECONDARY_BG" not in tokens: tokens["BTN_SECONDARY_BG"] = nav
                
                # Secondary text colors if missing
                if "CARD_TITLE" not in tokens: tokens["CARD_TITLE"] = tokens.get("TEXT_DIM", "#64748b")
                if "CARD_VALUE" not in tokens: tokens["CARD_VALUE"] = tokens.get("TEXT_MAIN", "#e2e8f0")
                if "DETAIL_ITEM_NAME_TEXT" not in tokens: tokens["DETAIL_ITEM_NAME_TEXT"] = accent
                
                # Table selection
                if "TABLE_SELECTION_BG" not in tokens: tokens["TABLE_SELECTION_BG"] = tokens.get("TAB_ACTIVE_BG", "#0f172a")
                
                # Semantic labels
                if "FILTER_LABEL" not in tokens: tokens["FILTER_LABEL"] = tokens.get("TEXT_DIM", "#64748b")

            derive_tokens(new_global)
            self.theme_data["global"] = new_global
            self.theme_data["views"] = {} 
        else:
            if scope not in self.theme_data["views"]:
                self.theme_data["views"][scope] = {}
            self.theme_data["views"][scope].update(preset.get("tokens", {}))
            
        return True

    def reset_to_replicator(self):
        self.apply_preset("replicator_core")
        self.save_theme()

    def get_token(self, key, view_scope=None):
        if view_scope and view_scope in self.theme_data["views"]:
            val = self.theme_data["views"][view_scope].get(key)
            if val: return val
        return self.theme_data["global"].get(key, DEFAULT_TOKENS.get(key, "#1e293b"))

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
        self.theme_data["active_preset"] = "replicator_core"
        self.theme_data["global"] = DEFAULT_TOKENS.copy()
        self.theme_data["views"] = {}

    def get_available_presets(self):
        return THEME_PRESETS

    def get_qss(self, view_scope=None):
        """Generates comprehensive dynamic QSS based on current tokens."""
        try:
            t = lambda k: self.get_token(k, view_scope)
            
            return f"""
            /* Dynamic Market Command Theme - Generated from tokens */
            
            QWidget {{
                color: {t('TEXT_MAIN')};
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }}
            
            QMainWindow, QWidget#MarketCommandRoot, QWidget#SimpleViewRoot, 
            QWidget#PerformanceViewRoot, QWidget#MyOrdersViewRoot, QWidget#ContractsViewRoot,
            QWidget#SimpleViewContent, QWidget#PerformanceContent, QWidget#MyOrdersContent, QWidget#ContractsContent {{
                background-color: {t('BG_WINDOW')};
            }}
            
            /* 1. NAVIGATION BAR & TOPBAR */
            QFrame#NavBar, QFrame#MarketTopBar, QFrame#SimpleActionBar, 
            QFrame#PerformanceActionBar, QFrame#MyOrdersActionBar, QFrame#ContractsActionBar,
            QFrame#MyOrdersTaxBar {{
                background-color: {t('NAV_BG')};
                border-bottom: 1px solid {t('NAV_BORDER')};
            }}
            
            QPushButton#TabButton {{
                background: transparent;
                color: {t('TAB_INACTIVE_TEXT')};
                border: none;
                font-weight: 800;
                font-size: 10px;
                padding: 10px 20px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
            }}
            
            QPushButton#TabButton:hover {{
                background-color: {t('TAB_HOVER_BG')};
                color: {t('TAB_ACTIVE_TEXT')};
            }}
            
            QPushButton#TabButton[active="true"] {{
                color: {t('TAB_ACTIVE_TEXT')};
                background-color: {t('TAB_ACTIVE_BG')};
                border-bottom: 2px solid {t('TAB_INDICATOR')};
            }}
 
            QLabel#CharacterBadge, QPushButton#CharacterBadge, QLabel#ContractReportRoot {{
                background-color: {t('CHARACTER_BADGE_BG')};
                color: {t('CHARACTER_BADGE_TEXT')};
                border: 1px solid {t('CHARACTER_BADGE_BORDER')};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9px;
                font-weight: 800;
                text-transform: uppercase;
            }}
 
            QLabel#ModeLabel, QLabel#SectionTitle {{
                color: {t('MODE_LABEL_TEXT')};
                font-size: 8px;
                font-weight: 900;
                letter-spacing: 1px;
            }}
            
            QLabel#SectionTitle {{
                font-size: 14px;
                letter-spacing: 2px;
            }}
 
            /* 2. TACTICAL SIDEBAR */
            QFrame#TacticalPanel, QFrame#PerformanceTacticalPanel, QFrame#ContractsFilterPanel,
            QWidget#TacticalScrollContent, QWidget#PerformanceTacticalContent, QWidget#ContractsFilterContent {{
                background-color: {t('SIDEBAR_BG')};
                border-right: 1px solid {t('SIDEBAR_BORDER')};
            }}
            
            QFrame#TacticalPanel QFrame#FilterCard, QFrame#TacticalPanel QFrame#TacticalFilterCard {{
                border-right: none;
            }}

            QLabel#ModuleHeader {{
                color: {t('SIDEBAR_HEADER_TEXT')};
                background-color: {t('SIDEBAR_HEADER_BG')};
                font-size: 10px;
                font-weight: 900;
                padding: 10px;
                border-bottom: 1px solid {t('SIDEBAR_BORDER')};
                letter-spacing: 2px;
                text-transform: uppercase;
            }}
            
            QScrollArea#TacticalScrollArea, QScrollArea#PerfScrollArea, QScrollArea#ContractsScrollArea {{
                background-color: {t('SIDEBAR_BG')};
                border: none;
            }}
            
            QScrollArea#TacticalScrollArea QWidget#TacticalScrollContent {{
                background-color: {t('SIDEBAR_BG')};
            }}
 
            /* 3. FILTERS & INPUTS */
            QFrame#FilterCard, QFrame#TacticalFilterCard, QFrame#ContractsFilterCard {{
                background-color: {t('FILTER_CARD_BG')};
                border: 1px solid {t('FILTER_CARD_BORDER')};
                border-radius: 4px;
            }}
            
            QFrame#FilterCard:hover, QFrame#TacticalFilterCard:hover, QFrame#ContractsFilterCard:hover {{
                border-color: {t('FILTER_CARD_HOVER')};
            }}
            
            QLabel#FilterLabel, QLabel#TacticalFilterLabel, QLabel#ContractsFilterLabel {{
                color: {t('FILTER_LABEL')};
                font-size: 8px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
 
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background-color: {t('INPUT_BG')};
                border: 1px solid {t('INPUT_BORDER')};
                color: {t('INPUT_TEXT')};
                padding: 5px;
                border-radius: 3px;
                font-size: 11px;
                selection-background-color: {t('ACCENT')};
                selection-color: {t('BG_WINDOW')};
            }}
            
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {t('INPUT_FOCUS')};
            }}
            
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
 
            QComboBox QAbstractItemView {{
                background-color: {t('INPUT_BG')};
                color: {t('INPUT_TEXT')};
                selection-background-color: {t('ACCENT')};
                selection-color: {t('BG_WINDOW')};
                border: 1px solid {t('INPUT_BORDER')};
            }}
            
            QCheckBox {{
                color: {t('CHECKBOX_TEXT')};
                font-size: 10px;
                font-weight: 700;
            }}
            
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                background-color: {t('CHECKBOX_BG')};
                border: 1px solid {t('CHECKBOX_BORDER')};
                border-radius: 2px;
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {t('CHECKBOX_CHECKED_BG')};
                border-color: {t('CHECKBOX_CHECKED_BG')};
            }}
 
            /* 4. SUMMARY & KPI CARDS */
            QFrame#SummaryMetricCard, QFrame#PerfMetricCard, QFrame#ContractMetricCard {{
                background-color: {t('CARD_BG')};
                border: 1px solid {t('CARD_BORDER')};
                border-radius: 6px;
            }}
            QFrame#SummaryMetricCard:hover, QFrame#PerfMetricCard:hover, QFrame#ContractMetricCard:hover {{
                border-color: {t('CARD_BORDER_HOVER')};
            }}
            
            QLabel#SummaryMetricTitle, QLabel#PerfMetricTitle, QLabel#DetailMetricTitle, QLabel#ContractMetricTitle {{
                color: {t('CARD_TITLE')};
                font-size: 9px;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            QLabel#SummaryMetricValue, QLabel#PerfMetricValue, QLabel#DetailMetricValue, QLabel#ContractMetricValue {{
                color: {t('CARD_VALUE')};
                font-size: 18px;
                font-weight: 900;
            }}
            
            QLabel#DetailTagline {{
                color: {t('TEXT_DIM')};
                font-size: 9px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}

            QLabel#MetricValueSuccess {{ color: {t('SUCCESS')}; font-weight: 900; }}
            QLabel#MetricValueWarning {{ color: {t('WARNING')}; font-weight: 900; }}
            QLabel#MetricValueDanger {{ color: {t('DANGER')}; font-weight: 900; }}
            QLabel#MetricValueInfo {{ color: {t('ACCENT')}; font-weight: 900; }}

            QFrame#MyOrdersTaxBar {{
                background-color: {t('NAV_BG')};
                border-top: 1px solid {t('NAV_BORDER')};
                border-bottom: 1px solid {t('NAV_BORDER')};
            }}
 
            /* 5. DETAIL PANELS */
            QFrame#MarketDetailPanel, QFrame#PerformanceDetailPanel, QFrame#ContractsDetailPanel {{
                background-color: {t('DETAIL_PANEL_BG')};
                border-top: 1px solid {t('DETAIL_PANEL_BORDER')};
                border-bottom: none;
                border-left: none;
                border-right: none;
            }}
            
            QLabel#MarketDetailTitle, QLabel#PerformanceDetailTitle, QLabel#ContractsDetailTitle, QLabel#DetailName {{
                color: {t('DETAIL_ITEM_NAME_TEXT')};
                font-size: 16px;
                font-weight: 900;
                text-transform: uppercase;
            }}
            
            QLabel#IconFrame, QLabel#MarketDetailIconFrame {{
                background-color: {t('DETAIL_ICON_FRAME_BG')};
                border: 1px solid {t('DETAIL_ICON_FRAME_BORDER')};
                border-radius: 8px;
                padding: 4px;
            }}
 
            /* 6. TABLES */
            QTableWidget#MarketResultsTable, QTableWidget#PerformanceTable, QTableWidget#MyOrdersSellTable, 
            QTableWidget#MyOrdersBuyTable, QTableWidget#ContractsTable, QTableWidget#PerformanceTransactionsTable {{
                background-color: {t('TABLE_BG')};
                alternate-background-color: {t('TABLE_ROW_ALT_BG')};
                gridline-color: {t('TABLE_GRID_LINE')};
                border: none;
                selection-background-color: {t('TABLE_SELECTION_BG')};
                selection-color: {t('TABLE_SELECTION_TEXT')};
            }}
            
            QHeaderView::section {{
                background-color: {t('TABLE_HEADER_BG')};
                color: {t('TABLE_HEADER_TEXT')};
                font-weight: 800;
                font-size: 9px;
                text-transform: uppercase;
                border: none;
                border-right: 1px solid {t('TABLE_HEADER_BORDER')};
                border-bottom: 1px solid {t('TABLE_HEADER_BORDER')};
                padding: 4px;
            }}
            
            QTableWidget::item {{
                padding: 5px;
            }}
 
            QTableWidget::item:selected {{
                background-color: {t('TABLE_SELECTION_BG')};
                color: {t('TABLE_SELECTION_TEXT')};
            }}
 
            /* 7. SCROLLBARS */
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: {t('SCROLL_TRACK')};
                width: 10px;
                height: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {t('SCROLL_HANDLE')};
                min-height: 20px;
                min-width: 20px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background: {t('SCROLL_HANDLE_HOVER')};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                background: none;
                height: 0px;
                width: 0px;
            }}
 
            /* 8. BUTTONS */
            QPushButton#RefreshButton, QPushButton#PrimaryButton {{
                background-color: {t('BTN_PRIMARY_BG')};
                color: {t('BTN_PRIMARY_TEXT')};
                border: 1px solid {t('BTN_PRIMARY_BORDER')};
                border-radius: 4px;
                font-weight: 900;
                padding: 5px 15px;
                text-transform: uppercase;
            }}
            QPushButton#RefreshButton:hover, QPushButton#PrimaryButton:hover {{
                background-color: {t('BTN_PRIMARY_HOVER_BG')};
                border-color: {t('ACCENT')};
            }}
            
            QPushButton#CustomizeButton, QPushButton#SecondaryButton {{
                background-color: {t('BTN_SECONDARY_BG')};
                color: {t('BTN_SECONDARY_TEXT')};
                border: 1px solid {t('BTN_SECONDARY_BORDER')};
                border-radius: 4px;
                font-weight: 800;
                padding: 5px 10px;
            }}
            QPushButton#CustomizeButton:hover, QPushButton#SecondaryButton:hover {{
                background-color: {t('BTN_SECONDARY_HOVER_BG')};
                border-color: {t('ACCENT_SECONDARY')};
            }}
            
            QPushButton#DangerButton {{
                background-color: {t('BTN_DANGER_BG')};
                color: {t('BTN_DANGER_TEXT')};
                border: 1px solid {t('DANGER')};
                border-radius: 4px;
                font-weight: 900;
            }}
 
            QProgressBar {{
                background-color: {t('SCROLL_TRACK')};
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {t('ACCENT')};
                border-radius: 1px;
            }}
            
            QTextEdit#DiagnosticReportText {{
                background-color: {t('BG_WINDOW')};
                color: {t('SUCCESS')};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid {t('NAV_BORDER')};
                padding: 10px;
            }}
            """
        except Exception as e:
            _log.exception(f"[THEME] Failed to generate QSS for {view_scope}: {e}")
            return "QWidget { background-color: #070B10; color: #EAF7FF; }"
