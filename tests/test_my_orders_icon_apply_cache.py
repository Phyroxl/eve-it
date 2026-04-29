import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtCore import Qt, QSize
import sys

# Asegurar que podemos importar desde el root
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.market_command.my_orders_view import MarketMyOrdersView

class TestMyOrdersIconApplyCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Necesitamos una QApplication para los widgets de UI
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        # Mock de dependencias para evitar inicializar todo el sistema
        with patch('ui.market_command.my_orders_view.EveIconService'), \
             patch('ui.market_command.my_orders_view.AuthManager'), \
             patch('ui.market_command.my_orders_view.ESIClient'), \
             patch('ui.market_command.my_orders_view.CostBasisService'):
            self.view = MarketMyOrdersView()

    def test_immediate_icon_apply_in_fill_table(self):
        """Si get_icon devuelve un pixmap inmediato, fill_table debe aplicarlo."""
        table = QTableWidget(1, 11)
        table.setIconSize(QSize(24, 24))
        table.setHorizontalHeaderLabels(["ÍTEM", "TIPO", "PRECIO", "PROMEDIO", "MEJOR", "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
        
        mock_order = MagicMock()
        mock_order.type_id = 1234
        mock_order.item_name = "Test Item"
        mock_order.is_buy_order = False
        mock_order.price = 100.0
        mock_order.volume_total = 10
        mock_order.volume_remain = 5
        
        mock_order.analysis.state = "Sana"
        mock_order.analysis.best_buy = 90.0
        mock_order.analysis.best_sell = 110.0
        mock_order.analysis.competitive = True
        mock_order.analysis.spread_pct = 5.0
        mock_order.analysis.margin_pct = 10.0
        mock_order.analysis.net_profit_total = 50.0
        
        mock_pixmap = QPixmap(24, 24)
        mock_pixmap.fill(QColor("green"))
        
        # Simular cache hit en get_icon
        self.view.icon_service.get_icon.return_value = mock_pixmap
        
        self.view.fill_table(table, [mock_order], 1)
        
        item = table.item(0, 0)
        self.assertIsNotNone(item)
        self.assertFalse(item.icon().isNull())
        self.assertEqual(self.view._orders_diag["icon_immediate_applied_sell"], 1)

    def test_apply_icon_to_row_clears_dash(self):
        """_apply_icon_to_row debe borrar '-' si existe."""
        table = QTableWidget(1, 1)
        table.setIconSize(QSize(24, 24))
        item = QTableWidgetItem("-")
        table.setItem(0, 0, item)
        
        mock_pixmap = QPixmap(24, 24)
        mock_pixmap.fill(QColor("red"))
        
        res = self.view._apply_icon_to_row(table, 0, 0, mock_pixmap)
        
        self.assertTrue(res)
        self.assertEqual(item.text(), "")
        self.assertFalse(item.icon().isNull())

    def test_apply_icon_to_row_preserves_name(self):
        """_apply_icon_to_row no debe borrar el nombre normal del item."""
        table = QTableWidget(1, 1)
        table.setIconSize(QSize(24, 24))
        item = QTableWidgetItem("Tritanium")
        table.setItem(0, 0, item)
        
        mock_pixmap = QPixmap(24, 24)
        mock_pixmap.fill(QColor("blue"))
        
        res = self.view._apply_icon_to_row(table, 0, 0, mock_pixmap)
        
        self.assertTrue(res)
        self.assertEqual(item.text(), "Tritanium")
        self.assertFalse(item.icon().isNull())

    def test_row_has_icon_for_type_id(self):
        """_row_has_icon_for_type_id debe detectar si ya hay icono."""
        table = QTableWidget(1, 11)
        item = QTableWidgetItem("Item")
        item.setData(Qt.UserRole, 1234)
        table.setItem(0, 0, item)
        
        # Sin icono inicialmente
        self.assertFalse(self.view._row_has_icon_for_type_id(table, 1234))
        
        # Aplicamos icono
        px = QPixmap(24, 24)
        px.fill(QColor("yellow"))
        item.setIcon(QIcon(px))
        self.assertTrue(self.view._row_has_icon_for_type_id(table, 1234))

    def test_callback_no_miss_if_icon_exists(self):
        """El callback no debe contar miss si el icono ya fue aplicado (ej. inmediatamente)."""
        table = QTableWidget(1, 11)
        item = QTableWidgetItem("Item")
        item.setData(Qt.UserRole, 1234)
        px = QPixmap(24, 24)
        px.fill(QColor("white"))
        item.setIcon(QIcon(px))
        table.setItem(0, 0, item)
        
        # Intentamos cargar icono vía callback en una fila/col que no existe (ej. row 5)
        # Pero como el type_id 1234 ya tiene icono en la tabla, no debería contar miss
        self.view._orders_diag["icon_missed_sell"] = 0
        
        self.view._load_icon_into_table_item(table, 5, 0, 1234, px, self.view._image_generation, side="SELL")
        
        self.assertEqual(self.view._orders_diag["icon_missed_sell"], 0)

if __name__ == "__main__":
    unittest.main()
