
import pytest
import sys
import os

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_critical_imports():
    """Verifica que los módulos principales se puedan importar sin errores."""
    from ui.desktop.main_suite_window import MainSuiteWindow
    from ui.market_command.command_main import MarketCommandMain
    from ui.market_command.simple_view import MarketSimpleView
    from ui.market_command.performance_view import MarketPerformanceView
    from ui.market_command.my_orders_view import MarketMyOrdersView
    from ui.market_command.contracts_view import MarketContractsView
    from ui.market_command.widgets import MarketTableWidget
    from ui.theme.theme_manager import ThemeManager
    from ui.common.theme_customizer_dialog import ThemeCustomizerDialog
    
    assert True

def test_theme_manager_safety():
    """Verifica que el ThemeManager sea resiliente a fallos."""
    from ui.theme.theme_manager import ThemeManager
    tm = ThemeManager.instance()
    
    # Test get_qss doesn't crash
    qss = tm.get_qss("non_existent_view")
    assert isinstance(qss, str)
    assert len(qss) > 0
    
    # Test invalid token fallback
    val = tm.get_token("INVALID_TOKEN_ABC_123")
    assert val == "#ff00ff" or val.startswith("#")

def test_qapplication_init():
    """Verifica que los widgets se puedan instanciar si hay una QApplication."""
    from PySide6.QtWidgets import QApplication
    from ui.market_command.command_main import MarketCommandMain
    
    app = QApplication.instance() or QApplication([])
    try:
        m = MarketCommandMain()
        assert m is not None
    except Exception as e:
        pytest.fail(f"Fallo al instanciar MarketCommandMain: {e}")
