import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication, QTableWidgetItem
from PySide6.QtCore import Qt
from ui.market_command.widgets import MarketTableWidget

class MockOpp:
    def __init__(self, name, type_id):
        self.item_name = name
        self.type_id = type_id
        self.score_breakdown = None
        self.liquidity = MockLiquidity()
        self.margin_net_pct = 10.0
        self.profit_per_unit = 500000.0
        self.profit_day_est = 1000000
        self.best_buy_price = 1000000.0
        self.best_sell_price = 1200000.0
        self.spread_pct = 5.0
        self.risk_level = "Bajo"
        self.tags = ["sólida"]

class MockLiquidity:
    def __init__(self):
        self.volume_5d = 100

def test_market_table_type_id():
    app = QApplication.instance() or QApplication([])
    table = MarketTableWidget()
    
    opps = [MockOpp("Tritanium", 34), MockOpp("Pyerite", 35)]
    table.populate(opps)
    
    # Test column 1 (Item)
    item = table.item(0, 1)
    assert item.text() == "Tritanium"
    assert item.data(Qt.UserRole) == 34
    
    # Test column 0 (Rank) - Redundancy check
    rank = table.item(0, 0)
    assert rank.data(Qt.UserRole) == 34
    
    # Test column 2 (Score) - Redundancy check
    score = table.item(0, 2)
    assert score.data(Qt.UserRole) == 34
    
    # Test helper _get_type_id_from_item
    assert table._get_type_id_from_item(item) == 34
    assert table._get_type_id_from_item(rank) == 34
    assert table._get_type_id_from_item(score) == 34
    
    # Test second row
    item2 = table.item(1, 1)
    assert item2.text() == "Pyerite"
    assert item2.data(Qt.UserRole) == 35
    assert table._get_type_id_from_item(item2) == 35
    
    print("test_market_table_type_id: PASSED")

if __name__ == "__main__":
    test_market_table_type_id()
