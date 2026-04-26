from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QPixmap, QColor, QFont
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

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
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels([
            "Rank", "Item", "Score", "Vol/Día", "Margen %", "Profit/Día", "Spread %", "Riesgo", "Etiquetas"
        ])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.setColumnWidth(1, 250)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSortingEnabled(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(45)
        
        from PySide6.QtCore import QSize
        self.setIconSize(QSize(32, 32))
        
        self.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
                border: none;
                color: #e2e8f0;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #1e293b;
            }
            QTableWidget::item:selected {
                background-color: rgba(59, 130, 246, 0.15);
                border-left: 3px solid #3b82f6;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #64748b;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #1e293b;
                font-weight: 800;
                font-size: 9px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)
        
        self.net_manager = QNetworkAccessManager(self)
        self.icon_cache = {}

    def populate(self, opportunities):
        self.setSortingEnabled(False)
        self.setRowCount(len(opportunities))
        
        for row, opp in enumerate(opportunities):
            rank = CustomTableWidgetItem(str(row + 1), row + 1)
            
            item = QTableWidgetItem(opp.item_name)
            # Support for async icon loading
            if opp.type_id in self.icon_cache:
                item.setIcon(QIcon(self.icon_cache[opp.type_id]))
            else:
                self.load_icon_async(opp.type_id, item)
            
            score_val = opp.score_breakdown.final_score if opp.score_breakdown else 0.0
            score = CustomTableWidgetItem(f"{score_val:.1f}", score_val)
            score.setTextAlignment(Qt.AlignCenter)
            score.setForeground(QColor("#34d399") if score_val > 70 else (QColor("#fbbf24") if score_val > 40 else QColor("#f87171")))
            score.setFont(QFont("Arial", 10, QFont.Bold))
            
            vol_val = opp.liquidity.volume_5d
            vol = CustomTableWidgetItem(str(vol_val), vol_val)
            vol.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            margin_val = opp.margin_net_pct
            margin = CustomTableWidgetItem(f"{margin_val:.1f}%", margin_val)
            margin.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if margin_val > 15: margin.setForeground(QColor("#10b981"))
            
            profit_val = opp.profit_day_est
            profit = CustomTableWidgetItem(f"{profit_val:,.0f}", profit_val)
            profit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            spread_val = opp.spread_pct
            spread = CustomTableWidgetItem(f"{spread_val:.1f}%", spread_val)
            spread.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            risk = QTableWidgetItem(opp.risk_level)
            risk.setTextAlignment(Qt.AlignCenter)
            
            # Formatear etiquetas como [RÁPIDA] [SÓLIDA]
            tags_str = " ".join([f"[{t.upper()}]" for t in opp.tags])
            tags_item = QTableWidgetItem(tags_str)
            tags_item.setForeground(QColor("#60a5fa"))
            tags_item.setFont(QFont("Arial", 8, QFont.Bold))
            
            # Alineaciones generales
            rank.setTextAlignment(Qt.AlignCenter)
            rank.setForeground(QColor("#64748b"))
            
            self.setItem(row, 0, rank)
            self.setItem(row, 1, item)
            self.setItem(row, 2, score)
            self.setItem(row, 3, vol)
            self.setItem(row, 4, margin)
            self.setItem(row, 5, profit)
            self.setItem(row, 6, spread)
            self.setItem(row, 7, risk)
            self.setItem(row, 8, tags_item)
            
        self.setSortingEnabled(True)
        # Default sort by score descending
        self.sortItems(2, Qt.DescendingOrder)

    def load_icon_async(self, type_id, table_item):
        url = f"https://images.evetech.net/types/{type_id}/icon?size=32"
        request = QNetworkRequest(QUrl(url))
        reply = self.net_manager.get(request)
        
        # We need to keep a reference to table_item or find it again.
        # Capturing variables in a closure for the callback:
        def on_finished():
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    self.icon_cache[type_id] = pixmap
                    table_item.setIcon(QIcon(pixmap))
            reply.deleteLater()
            
        reply.finished.connect(on_finished)
