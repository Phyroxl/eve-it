"""
ui/common/theme.py — Unified Design System for Salva Suite.
Centralizes colors, style tokens, and shared QSS fragments via ThemeManager.
"""
from ui.theme.theme_manager import ThemeManager

class ThemeMeta(type):
    def __getattr__(cls, key):
        # Delegate token retrieval to ThemeManager
        return ThemeManager.instance().get_token(key)

class Theme(metaclass=ThemeMeta):
    """
    Dynamic theme proxy. 
    Tokens available via Theme.TOKEN (e.g. Theme.ACCENT)
    
    Common Tokens:
    BG_MAIN, BG_PANEL, BG_PANEL_ALT, BG_NAV, 
    ACCENT, SUCCESS, DANGER, WARNING, NEUTRAL, TEXT_MAIN, TEXT_DIM
    """

    @staticmethod
    def get_qss(view_scope=None):
        """Returns the dynamic QSS for the suite/view."""
        return ThemeManager.instance().get_qss(view_scope)

    @staticmethod
    def apply_to(widget, view_scope=None):
        """Applies dynamic QSS to a widget with optional view scope."""
        widget.setStyleSheet(ThemeManager.instance().get_qss(view_scope))
