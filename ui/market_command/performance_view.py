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
        
        # Generar datos demo si está vacío para facilitar la primera vista
        from core.wallet_poller import WalletPoller
        WalletPoller().ensure_demo_data(0)
        
        self.setup_ui()
        self.discover_characters()
        self.refresh_view() # Intentar cargar si hay algo ya en DB

    def discover_characters(self):
        """Busca personajes en los logs y llena el combo."""
        chars = self.engine.find_active_characters()
        self.combo_char.clear()
        if not chars:
            self.combo_char.addItem("Sin personajes detectados", -1)
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
        self.top_items_table = QTableWidget(0, 6)
        self.top_items_table.setHorizontalHeaderLabels(["Item", "In", "Out", "Stock", "Profit", "Estado"])
        self.top_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.top_items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.top_items_table.setStyleSheet("background: #0f172a; color: #f1f5f9; border: none; font-size: 10px;")
        self.top_items_table.setShowGrid(False)
        self.top_items_table.verticalHeader().setVisible(False)
        self.top_items_table.setFixedHeight(250)
        self.top_items_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.top_items_table.setSelectionMode(QTableWidget.SingleSelection)
        self.top_items_table.itemSelectionChanged.connect(self.on_item_selection_changed)
        middle_layout.addWidget(self.top_items_table, 4)
        
        self.main_layout.addLayout(middle_layout)
        
        # 3.5 Item Detail Panel (New)
        self.detail_frame = QFrame()
        self.detail_frame.setFixedHeight(80)
        self.detail_frame.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 4px;")
        self.detail_frame.setVisible(False)
        dl = QHBoxLayout(self.detail_frame)
        
        self.lbl_det_name = QLabel("ITEM DETAIL")
        self.lbl_det_name.setStyleSheet("color: #f1f5f9; font-size: 14px; font-weight: 800;")
        
        def create_det_box(label, color="#94a3b8"):
            w = QWidget()
            v_l = QVBoxLayout(w)
            v_l.setContentsMargins(0,0,0,0)
            v_l.setSpacing(1)
            l = QLabel(label.upper())
            l.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: 800;")
            val = QLabel("---")
            val.setStyleSheet("color: #f1f5f9; font-size: 12px; font-weight: 700;")
            v_l.addWidget(l)
            v_l.addWidget(val)
            return w, val

        dl.addWidget(self.lbl_det_name, 2)
        self.det_in, self.lbl_det_in = create_det_box("Total Bought")
        self.det_out, self.lbl_det_out = create_det_box("Total Sold")
        self.det_stock, self.lbl_det_stock = create_det_box("Net Stock", "#3b82f6")
        self.det_profit, self.lbl_det_profit = create_det_box("Profit", "#10b981")
        self.det_margin, self.lbl_det_margin = create_det_box("Margin")
        self.det_status, self.lbl_det_status = create_det_box("Operational Status", "#fbbf24")
        
        dl.addWidget(self.det_in)
        dl.addWidget(self.det_out)
        dl.addWidget(self.det_stock)
        dl.addWidget(self.det_profit)
        dl.addWidget(self.det_margin)
        dl.addWidget(self.det_status)
        
        self.main_layout.addWidget(self.detail_frame)
        
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
        
        # Si no hay token, loguear primero
        if not auth.current_token:
            try:
                auth.authenticated.disconnect(self.on_auth_success)
            except: pass
            auth.authenticated.connect(self.on_auth_success)
            auth.login()
            return
            
        char_id = self.combo_char.currentData()
        
        # Si el char_id no es válido pero acabamos de loguear, usar el de auth
        if auth.char_id:
            char_id = auth.char_id
            # Asegurarnos de que el combo tenga este personaje con el ID correcto
            found = False
            for i in range(self.combo_char.count()):
                if self.combo_char.itemData(i) == char_id:
                    self.combo_char.setCurrentIndex(i)
                    found = True
                    break
            
            if not found:
                self.combo_char.addItem(auth.char_name, auth.char_id)
                self.combo_char.setCurrentIndex(self.combo_char.count() - 1)
            
        if not char_id or char_id <= 0:
            self.btn_refresh.setText("SELECT CHAR")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.btn_refresh.setText("SINCRONIZAR ESI"))
            return

        self.btn_refresh.setText("SINCRONIZANDO...")
        self.btn_refresh.setEnabled(False)
        
        # Worker Thread
        self.poller_thread = QThread()
        self.poller = WalletPoller()
        self.poller.moveToThread(self.poller_thread)
        
        self.poller_thread.started.connect(lambda: self.poller.poll(char_id, auth.current_token))
        self.poller.finished.connect(self.on_sync_finished)
        self.poller.error.connect(self.on_sync_error)
        
        self.poller_thread.start()

    def on_sync_finished(self):
        self.btn_refresh.setText("COMPLETO")
        self.btn_refresh.setEnabled(True)
        
        # Obtener el char_id actual (el real que acabamos de usar)
        from core.auth_manager import AuthManager
        char_id = self.combo_char.currentData() or AuthManager.instance().char_id
        
        self.refresh_view()
        
        # Obtener conteo de la DB para ese personaje específico
        import sqlite3
        conn = sqlite3.connect(self.engine.db_path)
        count = conn.execute("SELECT COUNT(*) FROM wallet_transactions WHERE character_id = ?", (char_id,)).fetchone()[0]
        conn.close()
        
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Sincronización ESI", f"¡Éxito!\n\nSe han importado {count} transacciones para tu personaje.\n\nSi no ves nada en la tabla, cambia el filtro de tiempo a 'Últimos 30 días'.")
        
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self.btn_refresh.setText("SINCRONIZAR ESI"))
        if hasattr(self, 'poller_thread'):
            self.poller_thread.quit()

    def on_auth_success(self, name, tokens):
        """Slot para manejar el éxito de la autenticación desde el hilo de AuthManager."""
        from PySide6.QtCore import QTimer
        # Usar un timer de 0ms para forzar la ejecución en el hilo de la UI
        QTimer.singleShot(0, self.on_sync_clicked)

    def on_sync_error(self, msg):
        self.btn_refresh.setText("ERROR")
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setStyleSheet("background: #ef4444; color: white; font-weight: 800; border-radius: 4px;")
        print(f"Sync Error: {msg}")
        if hasattr(self, 'poller_thread'):
            self.poller_thread.quit()

    def refresh_view(self):
        self.detail_frame.setVisible(False)
        # Calculate range
        days_map = {0: 1, 1: 7, 2: 30, 3: 90}
        days = days_map.get(self.combo_range.currentIndex(), 7)
        date_to = datetime.utcnow().strftime("%Y-%m-%d")
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Obtener personaje seleccionado
        char_id = self.combo_char.currentData()
        if char_id is None or char_id == -1:
            # Limpiar vista si no hay personaje
            self.kpi_profit.update_value("0 ISK")
            self.kpi_income.update_value("0 ISK")
            self.kpi_cost.update_value("0 ISK")
            self.kpi_fees.update_value("0 ISK")
            self.kpi_wallet.update_value("0 ISK", "No sync")
            self.chart.set_data([])
            self.top_items_table.setRowCount(0)
            self.trans_table.setRowCount(0)
            return
        
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
        self.current_items = items # Guardar para detalle
        self.top_items_table.setRowCount(len(items[:15]))
        for i, item in enumerate(items[:15]):
            self.top_items_table.setItem(i, 0, QTableWidgetItem(item.item_name))
            self.top_items_table.setItem(i, 1, QTableWidgetItem(str(item.total_bought_units)))
            self.top_items_table.setItem(i, 2, QTableWidgetItem(str(item.total_sold_units)))
            
            stock_item = QTableWidgetItem(str(item.net_units))
            if item.net_units > 0: stock_item.setForeground(QColor("#60a5fa"))
            self.top_items_table.setItem(i, 3, stock_item)
            
            self.top_items_table.setItem(i, 4, QTableWidgetItem(format_isk(item.profit_net, short=True)))
            
            status_item = QTableWidgetItem(item.status_text)
            status_colors = {
                "Rotando Bien": "#10b981", 
                "Acumulando Stock": "#fbbf24", 
                "Liquidando": "#f87171", 
                "Flujo Equilibrado": "#60a5fa",
                "Salida Lenta": "#94a3b8"
            }
            status_item.setForeground(QColor(status_colors.get(item.status_text, "#94a3b8")))
            self.top_items_table.setItem(i, 5, status_item)

    def on_item_selection_changed(self):
        sel = self.top_items_table.selectedItems()
        if not sel:
            self.detail_frame.setVisible(False)
            return
            
        row = sel[0].row()
        if hasattr(self, 'current_items') and row < len(self.current_items):
            item = self.current_items[row]
            self.lbl_det_name.setText(item.item_name.upper())
            self.lbl_det_in.setText(str(item.total_bought_units))
            self.lbl_det_out.setText(str(item.total_sold_units))
            self.lbl_det_stock.setText(str(item.net_units))
            
            from utils.formatters import format_isk
            self.lbl_det_profit.setText(format_isk(item.profit_net))
            self.lbl_det_margin.setText(f"{item.margin_real_pct:.1f}%")
            self.lbl_det_status.setText(item.status_text.upper())
            
            self.detail_frame.setVisible(True)

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
