from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QComboBox, QScrollArea, QGridLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
import sqlite3

from core.performance_engine import PerformanceEngine
from datetime import datetime, timedelta

class KPIWidget(QFrame):
    def __init__(self, title, value, color="#3b82f6", parent=None):
        super().__init__(parent)
        self.setObjectName("AnalyticBox")
        self.setStyleSheet(f"background-color: #0f172a; border: 1px solid #1e293b; border-radius: 4px; min-width: 160px;")
        
        l = QVBoxLayout(self)
        l.setContentsMargins(15, 12, 15, 12)
        l.setSpacing(2)
        
        t = QLabel(title.upper())
        t.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: 800; letter-spacing: 1px;")
        
        self.v = QLabel(value)
        self.v.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 900;")
        
        self.d = QLabel("+0.0% vs prev.")
        self.d.setStyleSheet("color: #64748b; font-size: 8px; font-weight: 600;")
        
        l.addWidget(t)
        l.addWidget(self.v)
        l.addWidget(self.d)

    def update_value(self, val, delta_text=""):
        self.v.setText(val)
        self.d.setText(delta_text)

class SimpleBarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = [] # List of (date, value)
        self.setMinimumHeight(150)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        if not self.data: return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        padding = 30
        chart_w = w - (padding * 2)
        chart_h = h - (padding * 2)
        
        # Scale
        max_val = max([abs(d[1]) for d in self.data]) if self.data else 1
        if max_val == 0: max_val = 1
        
        bar_w = (chart_w / len(self.data)) * 0.8
        spacing = (chart_w / len(self.data)) * 0.2
        
        zero_line = chart_h / 2 + padding
        
        for i, (date, val) in enumerate(self.data):
            x = padding + i * (bar_w + spacing)
            # Normalize height
            norm_h = (val / max_val) * (chart_h / 2)
            
            color = QColor("#10b981") if val >= 0 else QColor("#ef4444")
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            
            p.drawRect(x, zero_line, bar_w, -norm_h)
            
        p.setPen(QPen(QColor("#475569"), 1))
        p.drawLine(padding, zero_line, w - padding, zero_line)

class MarketPerformanceView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = PerformanceEngine()
        # Inicializar poller para datos demo si no hay nada
        from core.wallet_poller import WalletPoller
        WalletPoller().ensure_demo_data(0)
        
        self.setup_ui()
        self.discover_characters()
        self.refresh_view() # Cargar datos iniciales

    def discover_characters(self):
        """Busca personajes en los logs y llena el combo."""
        chars = self.engine.find_active_characters()
        self.combo_char.clear()
        if not chars:
            self.combo_char.addItem("Sin personajes detectados", 0)
        else:
            for c in chars:
                self.combo_char.addItem(c['name'], c['id'])
        
        self.combo_char.currentIndexChanged.connect(self.refresh_view)
        
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)
        
        # 1. Header & Selectors
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MARKET PERFORMANCE")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        subtitle = QLabel("RENDIMIENTO REAL DE TRADING")
        subtitle.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        title_v.addWidget(title_lbl)
        title_v.addWidget(subtitle)
        
        self.combo_char = QComboBox()
        self.combo_char.addItem("Sincroniza para ver personajes")
        self.combo_char.setFixedWidth(200)
        self.combo_char.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; padding: 5px;")
        
        self.combo_range = QComboBox()
        self.combo_range.addItems(["Hoy", "7 días", "30 días", "90 días"])
        self.combo_range.setFixedWidth(100)
        self.combo_range.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; padding: 5px;")
        self.combo_range.currentIndexChanged.connect(self.refresh_view)
        
        self.btn_refresh = QPushButton("SINCRONIZAR ESI")
        self.btn_refresh.setFixedWidth(120)
        self.btn_refresh.setFixedHeight(30)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.on_sync_clicked)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.combo_char)
        header.addWidget(self.combo_range)
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)
        
        # 2. KPIs Row
        kpis_layout = QHBoxLayout()
        self.kpi_profit = KPIWidget("Profit Neto", "0 ISK", "#10b981")
        self.kpi_income = KPIWidget("Ingresos", "0 ISK", "#60a5fa")
        self.kpi_cost = KPIWidget("Gastos", "0 ISK", "#f87171")
        self.kpi_fees = KPIWidget("Fees & Tax", "0 ISK", "#f59e0b")
        self.kpi_wallet = KPIWidget("Wallet Balance", "0 ISK", "#cbd5e1")
        
        kpis_layout.addWidget(self.kpi_profit)
        kpis_layout.addWidget(self.kpi_income)
        kpis_layout.addWidget(self.kpi_cost)
        kpis_layout.addWidget(self.kpi_fees)
        kpis_layout.addWidget(self.kpi_wallet)
        self.main_layout.addLayout(kpis_layout)
        
        # 3. Middle Row: Chart & Top Items
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(20)
        
        # Chart
        self.chart_frame = QFrame()
        self.chart_frame.setObjectName("AnalyticBox")
        self.chart_frame.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;")
        self.chart_frame.setMinimumHeight(250)
        chart_l = QVBoxLayout(self.chart_frame)
        
        chart_title = QLabel("PROFIT DIARIO (ISK)")
        chart_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        chart_l.addWidget(chart_title)
        
        self.chart = SimpleBarChart()
        chart_l.addWidget(self.chart)
        middle_layout.addWidget(self.chart_frame, 3)
        
        # Top Items Table
        self.top_items_table = QTableWidget(0, 4)
        self.top_items_table.setHorizontalHeaderLabels(["Item", "Ventas", "Profit", "Margen"])
        self.top_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.top_items_table.setStyleSheet("background: #0f172a; color: #f1f5f9; border: none;")
        self.top_items_table.setShowGrid(False)
        self.top_items_table.verticalHeader().setVisible(False)
        self.top_items_table.setFixedHeight(250)
        middle_layout.addWidget(self.top_items_table, 2)
        
        self.main_layout.addLayout(middle_layout)
        
        # 4. Bottom Row: Recent Transactions
        self.trans_table = QTableWidget(0, 6)
        self.trans_table.setHorizontalHeaderLabels(["Fecha", "Item", "Tipo", "Cantidad", "Total", "Fee Est."])
        self.trans_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trans_table.setStyleSheet("background: #0f172a; color: #f1f5f9; border: none;")
        self.trans_table.setShowGrid(False)
        self.trans_table.verticalHeader().setVisible(False)
        self.trans_table.setMinimumHeight(300)
        self.main_layout.addWidget(self.trans_table)
        
        self.main_layout.addStretch()

    def on_sync_clicked(self):
        from core.auth_manager import AuthManager
        from core.wallet_poller import WalletPoller
        from PySide6.QtCore import QThread
        
        auth = AuthManager.instance()
        token = auth.current_token
        
        # Para el MVP, si no hay token (porque no se ha configurado el Client ID)
        # avisamos de que se necesita configuración real.
        if not token or token == "MOCK_TOKEN":
            self.btn_refresh.setText("REQ. CLIENT ID")
            self.btn_refresh.setStyleSheet("background: #ef4444; color: white; font-weight: 800; border-radius: 4px;")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: (
                self.btn_refresh.setText("SINCRONIZAR ESI"), 
                self.btn_refresh.setEnabled(True),
                self.btn_refresh.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; border-radius: 4px;")
            ))
            return

        self.btn_refresh.setText("SINCRONIZANDO...")
        self.btn_refresh.setEnabled(False)
        
        # Worker Thread
        self.poller_thread = QThread()
        self.poller = WalletPoller()
        self.poller.moveToThread(self.poller_thread)
        
        self.poller_thread.started.connect(lambda: self.poller.poll(0, token)) # Usando ID 0 para MVP
        self.poller.finished.connect(self.on_sync_finished)
        self.poller.error.connect(self.on_sync_error)
        
        self.poller_thread.start()

    def on_sync_finished(self):
        self.btn_refresh.setText("COMPLETO")
        self.btn_refresh.setEnabled(True)
        self.refresh_view()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.btn_refresh.setText("SINCRONIZAR ESI"))
        self.poller_thread.quit()

    def on_sync_error(self, msg):
        self.btn_refresh.setText("ERROR")
        self.btn_refresh.setEnabled(True)
        print(f"Sync Error: {msg}")
        self.poller_thread.quit()

    def refresh_view(self):
        # Calculate range
        days_map = {0: 1, 1: 7, 2: 30, 3: 90}
        days = days_map.get(self.combo_range.currentIndex(), 7)
        date_to = datetime.utcnow().strftime("%Y-%m-%d")
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Obtener personaje seleccionado
        char_id = self.combo_char.currentData() or 0
        
        summary = self.engine.build_character_summary(char_id, date_from, date_to)
        daily_pnl = self.engine.build_daily_pnl(char_id, date_from, date_to)
        items = self.engine.build_item_summary(char_id, date_from, date_to)
        
        from utils.formatters import format_isk
        self.kpi_profit.update_value(format_isk(summary.total_profit_net, short=True) + " ISK")
        self.kpi_income.update_value(format_isk(summary.total_income, short=True) + " ISK")
        self.kpi_cost.update_value(format_isk(summary.total_cost, short=True) + " ISK")
        self.kpi_fees.update_value(format_isk(summary.total_fees, short=True) + " ISK")
        self.kpi_wallet.update_value(format_isk(summary.wallet_current, short=True) + " ISK", f"Sync: {summary.last_synced_at.strftime('%H:%M')}")
        
        # Update Chart
        chart_data = [(d.date, d.profit_net) for d in daily_pnl]
        self.chart.set_data(chart_data)
        
        # Update Top Items
        self.top_items_table.setRowCount(len(items[:10]))
        for i, item in enumerate(items[:10]):
            self.top_items_table.setItem(i, 0, QTableWidgetItem(item.item_name))
            self.top_items_table.setItem(i, 1, QTableWidgetItem(str(item.total_sold_units)))
            self.top_items_table.setItem(i, 2, QTableWidgetItem(format_isk(item.profit_net, short=True)))
            self.top_items_table.setItem(i, 3, QTableWidgetItem(f"{item.margin_real_pct:.1f}%"))

        # Update Recent Transactions
        conn = sqlite3.connect(self.engine.db_path)
        c = conn.cursor()
        c.execute("""SELECT date, item_name, is_buy, quantity, unit_price 
                     FROM wallet_transactions 
                     WHERE character_id = ? 
                     ORDER BY date DESC LIMIT 50""", (char_id,))
        rows = c.fetchall()
        conn.close()
        
        self.trans_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            date_short = r[0].split("T")[0]
            tipo = "COMPRA" if r[2] == 1 else "VENTA"
            color = "#f87171" if r[2] == 1 else "#34d399"
            
            self.trans_table.setItem(i, 0, QTableWidgetItem(date_short))
            self.trans_table.setItem(i, 1, QTableWidgetItem(r[1] or "Unknown"))
            
            type_item = QTableWidgetItem(tipo)
            type_item.setForeground(QColor(color))
            self.trans_table.setItem(i, 2, type_item)
            
            self.trans_table.setItem(i, 3, QTableWidgetItem(str(r[3])))
            self.trans_table.setItem(i, 4, QTableWidgetItem(format_isk(r[3] * r[4], short=True)))
            self.trans_table.setItem(i, 5, QTableWidgetItem("~3.0%")) # Estimado MVP
