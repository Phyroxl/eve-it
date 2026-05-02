"""
tests/test_market_command_view_imports.py
Verifica que todas las pestañas de Market Command puedan instanciarse sin errores.
"""
import pytest
import sys
import os
from PySide6.QtWidgets import QApplication

# Asegurar que el directorio raíz está en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app

def test_simple_view_constructs(qapp):
    from ui.market_command.simple_view import MarketSimpleView
    view = MarketSimpleView()
    assert view is not None

def test_performance_view_constructs(qapp):
    from ui.market_command.performance_view import MarketPerformanceView
    view = MarketPerformanceView(defer_initial_refresh=True)
    assert view is not None

def test_my_orders_view_constructs(qapp):
    from ui.market_command.my_orders_view import MarketMyOrdersView
    view = MarketMyOrdersView()
    assert view is not None

def test_contracts_view_constructs(qapp):
    from ui.market_command.contracts_view import MarketContractsView
    view = MarketContractsView()
    assert view is not None
    # Verificar atributos críticos que fallaron
    assert hasattr(view, "capital_min_spin")
    assert hasattr(view, "items_max_spin")
