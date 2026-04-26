from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt

class CustomTableWidgetItem(QTableWidgetItem):
    def __init__(self, display_text, sort_value):
        super().__init__(display_text)
        self.sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, CustomTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)

class MarketTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "Rank", "Item", "Score", "Vol/Día", "Margen %", "Profit/Día", "Spread %", "Riesgo"
        ])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.setColumnWidth(1, 250)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setSortingEnabled(True)

    def populate(self, opportunities):
        self.setSortingEnabled(False)
        self.setRowCount(len(opportunities))
        
        for row, opp in enumerate(opportunities):
            rank = CustomTableWidgetItem(str(row + 1), row + 1)
            
            item = QTableWidgetItem(opp.item_name)
            
            score_val = opp.score_breakdown.final_score if opp.score_breakdown else 0.0
            score = CustomTableWidgetItem(f"{score_val:.1f}", score_val)
            
            vol_val = opp.liquidity.volume_5d
            vol = CustomTableWidgetItem(str(vol_val), vol_val)
            
            margin_val = opp.margin_net_pct
            margin = CustomTableWidgetItem(f"{margin_val:.1f}%", margin_val)
            
            profit_val = opp.profit_day_est
            profit = CustomTableWidgetItem(f"{profit_val:,.0f} ISK", profit_val)
            
            spread_val = opp.spread_pct
            spread = CustomTableWidgetItem(f"{spread_val:.1f}%", spread_val)
            
            risk = QTableWidgetItem(opp.risk_level)
            
            self.setItem(row, 0, rank)
            self.setItem(row, 1, item)
            self.setItem(row, 2, score)
            self.setItem(row, 3, vol)
            self.setItem(row, 4, margin)
            self.setItem(row, 5, profit)
            self.setItem(row, 6, spread)
            self.setItem(row, 7, risk)
            
        self.setSortingEnabled(True)
        # Default sort by score descending
        self.sortItems(2, Qt.DescendingOrder)
