from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu, QApplication
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QIcon, QPixmap, QColor, QFont, QClipboard
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
    item_action_triggered = Signal(str, str, int) # action_type, item_name, type_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(9)
        headers = ["Rank", "Item", "Score", "Vol/Día", "Margen %", "Profit/Día", "Spread %", "Riesgo", "Etiquetas (?)"]
        self.setHorizontalHeaderLabels(headers)
        
        tooltips = [
            "Ranking de oportunidad (1 es la mejor).",
            "Nombre del Item en el mercado.",
            "Puntuación heurística de rentabilidad y seguridad. >70 Excelente.",
            "Unidades movidas de media al día (basado en 5 días).",
            "Margen de beneficio neto esperado (ya deducidas las tasas).",
            "Beneficio en ISK estimado si capturas parte del volumen diario.",
            "Diferencia porcentual bruta entre órdenes Buy y Sell.",
            "Estimación de riesgo según capital requerido y volatilidad.",
            "ETIQUETAS INTELIGENTES:\n"
            "• RÁPIDA: Alto volumen (>500/5d).\n"
            "• LENTA: Bajo volumen (<50/5d).\n"
            "• BUEN MARGEN: Margen >20%.\n"
            "• SÓLIDA: Bajo riesgo y margen >15%.\n"
            "• CAPITAL ALTO: Ítem caro (>100M ISK).\n"
            "• CUIDADO: Spread extremo o margen <2%."
        ]
        for i, tip in enumerate(tooltips):
            self.horizontalHeaderItem(i).setToolTip(tip)
            
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.setColumnWidth(0, 50)
        self.setColumnWidth(1, 250)
        self.setColumnWidth(2, 60)
        self.setColumnWidth(3, 70)
        self.setColumnWidth(8, 150)
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
        
        self.itemDoubleClicked.connect(self.on_item_double_clicked)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is not None:
            row = item.row()
            item_name = self.item(row, 1).text()
            type_id = self.item(row, 1).data(Qt.UserRole)
            
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #1e293b; color: #f8fafc; border: 1px solid #3b82f6; } QMenu::item:selected { background-color: #3b82f6; }")
            copy_action = menu.addAction(f"Copiar Nombre: {item_name}")
            
            action = menu.exec(self.viewport().mapToGlobal(event.pos()))
            
            if action == copy_action:
                QApplication.clipboard().setText(item_name)
                self.item_action_triggered.emit("copied", item_name, type_id)

    def on_item_double_clicked(self, item):
        row = item.row()
        item_name = self.item(row, 1).text()
        type_id = self.item(row, 1).data(Qt.UserRole)
        self.item_action_triggered.emit("double_clicked", item_name, type_id)

    def populate(self, opportunities):
        self.setSortingEnabled(False)
        self.setRowCount(len(opportunities))
        
        for row, opp in enumerate(opportunities):
            rank = CustomTableWidgetItem(str(row + 1), row + 1)
            
            item = QTableWidgetItem(opp.item_name)
            item.setData(Qt.UserRole, opp.type_id)
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
class AdvancedMarketTableWidget(MarketTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Columns: Rank, Item, Score, Vol/Día, Margen %, Profit/U, Profit/Día, Spread %, Riesgo, Buy Ord, Sell Ord, Hist Days, Etiquetas
        self.setColumnCount(13)
        headers = [
            "Rank", "Item", "Score", "Vol/Día", "Margen %", 
            "Profit/U", "Profit/Día", "Spread %", "Riesgo", 
            "Buy Ord", "Sell Ord", "Hist Days", "Etiquetas (?)"
        ]
        self.setHorizontalHeaderLabels(headers)
        
        tooltips = [
            "Ranking.", "Nombre del Item.", "Score Final.", "Volumen 5d.", "Margen Neto %.",
            "Beneficio por unidad vendida.", "Beneficio diario estimado.", "Spread %.", 
            "Nivel de riesgo.", "Cantidad de órdenes de compra.", "Cantidad de órdenes de venta.",
            "Días de historial disponibles.", "ETIQUETAS INTELIGENTES (Ver modo simple para leyenda)."
        ]
        for i, tip in enumerate(tooltips):
            if i < self.columnCount():
                self.horizontalHeaderItem(i).setToolTip(tip)
                
        self.setColumnWidth(1, 200)
        self.setColumnWidth(12, 120)

    def populate(self, opportunities):
        self.setSortingEnabled(False)
        self.setRowCount(len(opportunities))
        
        for row, opp in enumerate(opportunities):
            # Reuse logic from MarketTableWidget for common columns if possible, 
            # but since it's hardcoded for column indices, we rewrite populate for precision.
            
            # 0. Rank
            rank = CustomTableWidgetItem(str(row + 1), row + 1)
            rank.setTextAlignment(Qt.AlignCenter)
            rank.setForeground(QColor("#64748b"))
            
            # 1. Item
            item = QTableWidgetItem(opp.item_name)
            item.setData(Qt.UserRole, opp.type_id)
            if opp.type_id in self.icon_cache:
                item.setIcon(QIcon(self.icon_cache[opp.type_id]))
            else:
                self.load_icon_async(opp.type_id, item)
            
            # 2. Score
            score_val = opp.score_breakdown.final_score if opp.score_breakdown else 0.0
            score = CustomTableWidgetItem(f"{score_val:.1f}", score_val)
            score.setTextAlignment(Qt.AlignCenter)
            score.setForeground(QColor("#34d399") if score_val > 70 else (QColor("#fbbf24") if score_val > 40 else QColor("#f87171")))
            score.setFont(QFont("Arial", 10, QFont.Bold))
            
            # 3. Vol
            vol_val = opp.liquidity.volume_5d
            vol = CustomTableWidgetItem(str(vol_val), vol_val)
            vol.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # 4. Margen
            margin_val = opp.margin_net_pct
            margin = CustomTableWidgetItem(f"{margin_val:.1f}%", margin_val)
            margin.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if margin_val > 15: margin.setForeground(QColor("#10b981"))
            
            # 5. Profit/U
            pu_val = opp.profit_per_unit
            pu = CustomTableWidgetItem(f"{pu_val:,.2f}", pu_val)
            pu.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # 6. Profit/Día
            pd_val = opp.profit_day_est
            pd = CustomTableWidgetItem(f"{pd_val:,.0f}", pd_val)
            pd.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # 7. Spread
            spread_val = opp.spread_pct
            spread = CustomTableWidgetItem(f"{spread_val:.1f}%", spread_val)
            spread.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # 8. Riesgo
            risk = QTableWidgetItem(opp.risk_level)
            risk.setTextAlignment(Qt.AlignCenter)
            
            # 9. Buy Ord
            bo_val = opp.liquidity.buy_orders_count
            bo = CustomTableWidgetItem(str(bo_val), bo_val)
            bo.setTextAlignment(Qt.AlignCenter)
            
            # 10. Sell Ord
            so_val = opp.liquidity.sell_orders_count
            so = CustomTableWidgetItem(str(so_val), so_val)
            so.setTextAlignment(Qt.AlignCenter)
            
            # 11. Hist Days
            hd_val = opp.liquidity.history_days
            hd = CustomTableWidgetItem(str(hd_val), hd_val)
            hd.setTextAlignment(Qt.AlignCenter)
            
            # 12. Tags
            tags_str = " ".join([f"[{t.upper()}]" for t in opp.tags])
            tags_item = QTableWidgetItem(tags_str)
            tags_item.setForeground(QColor("#60a5fa"))
            tags_item.setFont(QFont("Arial", 8, QFont.Bold))

            self.setItem(row, 0, rank)
            self.setItem(row, 1, item)
            self.setItem(row, 2, score)
            self.setItem(row, 3, vol)
            self.setItem(row, 4, margin)
            self.setItem(row, 5, pu)
            self.setItem(row, 6, pd)
            self.setItem(row, 7, spread)
            self.setItem(row, 8, risk)
            self.setItem(row, 9, bo)
            self.setItem(row, 10, so)
            self.setItem(row, 11, hd)
            self.setItem(row, 12, tags_item)
            
        self.setSortingEnabled(True)
        self.sortItems(2, Qt.DescendingOrder)
