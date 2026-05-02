"""
tests/test_app_startup_imports.py
Verifica que los componentes principales de la UI puedan importarse sin errores (evita crasheos por SyntaxError o circular imports).
"""
import pytest
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_theme_imports():
    from ui.common.theme import Theme
    assert hasattr(Theme, "get_qss")

def test_main_window_imports():
    from ui.desktop.main_suite_window import MainSuiteWindow
    # No instanciamos para evitar requerir un QApplication activo en el test simple

def test_market_command_imports():
    from ui.market_command.command_main import MarketCommandMain

def test_market_views_import():
    from ui.market_command.simple_view import MarketSimpleView
    from ui.market_command.my_orders_view import MarketMyOrdersView
    from ui.market_command.contracts_view import MarketContractsView
    from ui.market_command.performance_view import MarketPerformanceView

def test_widgets_import():
    from ui.market_command.widgets import MarketTableWidget
