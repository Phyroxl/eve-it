import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor

from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.market_engine import analyze_character_orders
from core.config_manager import load_market_filters
from ui.market_command.widgets import ItemInteractionHelper
from utils.formatters import format_isk

_log = logging.getLogger('eve.market.my_orders')

class SyncWorker(QThread):
    finished_data = Signal(list)
    error = Signal(str)

    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token

    def run(self):
        try:
            client = ESIClient()
            orders = client.character_orders(self.char_id, self.token)
            if not orders:
                self.finished_data.emit([])
                return
            
            type_ids = list(set(o['type_id'] for o in orders))
            all_market_orders = client.market_orders(10000002)
            relevant_market_orders = [mo for mo in all_market_orders if mo['type_id'] in type_ids]
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            config = load_market_filters()
            
            analyzed = analyze_character_orders(orders, relevant_market_orders, item_names, config)
            self.finished_data.emit(analyzed)
            
        except Exception as e:
            self.error.emit(str(e))

class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.worker = None
        self.all_orders = []
        
        AuthManager.instance().authenticated.connect(self._on_authenticated)

    def _on_authenticated(self, char_name, tokens):
        self.do_sync(is_update=False)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(12)

        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MIS PEDIDOS")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 900; letter-spacing: 1px;")
        subtitle = QLabel("ANÁLISIS OPERATIVO DE ÓRDENES ABIERTAS")
        subtitle.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;")
        
        self.lbl_status = QLabel("● ESPERANDO SINCRONIZACIÓN")
        self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

        title_v.addWidget(title_lbl)
        title_v.addWidget(subtitle)
        title_v.addWidget(self.lbl_status)

        self.btn_refresh = QPushButton("SINCRONIZAR ÓRDENES")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setMinimumWidth(200)
        self.btn_refresh.setFixedHeight(35)
        self.btn_refresh.setStyleSheet(
            "QPushButton { background-color: #3b82f6; color: white; font-size: 10px; font-weight: 900; "
            "border-radius: 4px; letter-spacing: 1px; padding: 0 15px; } "
            "QPushButton:hover { background-color: #2563eb; } "
            "QPushButton:disabled { background-color: #1e293b; color: #64748b; }"
        )
        self.btn_refresh.clicked.connect(lambda: self.do_sync(is_update=False))

        self.btn_repopulate = QPushButton("ACTUALIZAR")
        self.btn_repopulate.setCursor(Qt.PointingHandCursor)
        self.btn_repopulate.setMinimumWidth(120)
        self.btn_repopulate.setFixedHeight(35)
        self.btn_repopulate.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #f1f5f9; font-size: 10px; font-weight: 900; "
            "border-radius: 4px; letter-spacing: 1px; padding: 0 15px; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_repopulate.clicked.connect(lambda: self.do_sync(is_update=True))

        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_repopulate)
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)

        def create_table():
            t = QTableWidget(0, 10)
            t.setHorizontalHeaderLabels([
                "Item", "Type", "My Price", "Best Competitor", "Total", "Remain", "Spread", "Margin", "Total Profit", "Status"
            ])
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setSelectionBehavior(QTableWidget.SelectRows)
            t.setSelectionMode(QTableWidget.SingleSelection)
            t.setShowGrid(False)
            t.verticalHeader().setVisible(False)
            t.setStyleSheet(
                "QTableWidget { background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; font-size: 10px; } "
                "QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; font-size: 9px; border: none; padding: 4px; } "
                "QTableWidget::item:selected { background: #1e293b; }"
            )
            return t

        self.table_sell = create_table()
        self.table_buy = create_table()

        self.table_sell.itemSelectionChanged.connect(self.on_sell_selection_changed)
        self.table_buy.itemSelectionChanged.connect(self.on_buy_selection_changed)

        self.table_sell.itemDoubleClicked.connect(lambda item: self.on_double_click(item, self.table_sell))
        self.table_buy.itemDoubleClicked.connect(lambda item: self.on_double_click(item, self.table_buy))

        self.table_sell.customContextMenuRequested.connect(lambda pos: self.on_context_menu(pos, self.table_sell))
        self.table_buy.customContextMenuRequested.connect(lambda pos: self.on_context_menu(pos, self.table_buy))

        lbl_sell = QLabel("ÓRDENES DE VENTA")
        lbl_sell.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: 900; letter-spacing: 1px; margin-top: 5px;")
        
        lbl_buy = QLabel("ÓRDENES DE COMPRA")
        lbl_buy.setStyleSheet("color: #3b82f6; font-size: 11px; font-weight: 900; letter-spacing: 1px; margin-top: 5px;")

        self.main_layout.addWidget(lbl_sell)
        self.main_layout.addWidget(self.table_sell, 1)
        self.main_layout.addWidget(lbl_buy)
        self.main_layout.addWidget(self.table_buy, 1)

        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(120)
        self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_ui()
        self.main_layout.addWidget(self.detail_panel)

    def setup_detail_ui(self):
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(15, 15, 15, 15)
        dl.setSpacing(20)

        info_v = QVBoxLayout()
        self.lbl_det_item = QLabel("SELECCIONA UNA ORDEN")
        self.lbl_det_item.setStyleSheet("color: #f1f5f9; font-size: 15px; font-weight: 900;")
        self.lbl_det_type = QLabel("---")
        self.lbl_det_type.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        info_v.addWidget(self.lbl_det_item)
        info_v.addWidget(self.lbl_det_type)
        info_v.addStretch()
        dl.addLayout(info_v, 1)

        m_g = QGridLayout()
        m_g.setSpacing(10)
        
        def add_metric(layout, row, col, label, color="#e2e8f0"):
            layout.addWidget(QLabel(label, styleSheet="color: #475569; font-size: 8px; font-weight: 800;"), row*2, col)
            val = QLabel("---")
            val.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 800;")
            layout.addWidget(val, row*2+1, col)
            return val

        self.lbl_det_my_price = add_metric(m_g, 0, 0, "MI PRECIO", "#3b82f6")
        self.lbl_det_best_buy = add_metric(m_g, 0, 1, "BEST BUY")
        self.lbl_det_best_sell = add_metric(m_g, 0, 2, "BEST SELL")
        
        self.lbl_det_margin = add_metric(m_g, 1, 0, "MARGEN NETO", "#10b981")
        self.lbl_det_profit_unit = add_metric(m_g, 1, 1, "PROFIT NETO / U", "#10b981")
        self.lbl_det_profit_total = add_metric(m_g, 1, 2, "PROFIT TOTAL EST.", "#10b981")
        
        dl.addLayout(m_g, 2)

        st_v = QVBoxLayout()
        st_v.addWidget(QLabel("ESTADO OPERATIVO", styleSheet="color: #475569; font-size: 8px; font-weight: 800;"))
        self.lbl_det_status = QLabel("---")
        self.lbl_det_status.setStyleSheet("color: #f1f5f9; font-size: 12px; font-weight: 900;")
        self.lbl_det_diff = QLabel("---")
        self.lbl_det_diff.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
        st_v.addWidget(self.lbl_det_status)
        st_v.addWidget(self.lbl_det_diff)
        st_v.addStretch()
        dl.addLayout(st_v, 1)

    def do_sync(self, is_update=False):
        if self.worker and self.worker.isRunning():
            return

        auth = AuthManager.instance()
        if not auth.current_token or not auth.char_id:
            self.lbl_status.setText("● INICIANDO LOGIN ESI...")
            self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800;")
            auth.login()
            return

        self.btn_refresh.setEnabled(False)
        self.btn_repopulate.setEnabled(False)
        
        if is_update:
            self.btn_repopulate.setText("ACTUALIZANDO...")
            self.lbl_status.setText("● ACTUALIZANDO ANÁLISIS DE MERCADO...")
        else:
            self.btn_refresh.setText("SINCRONIZANDO...")
            self.lbl_status.setText("● DESCARGANDO ÓRDENES Y MERCADO...")
            
        self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800;")
        self.is_update_mode = is_update

        self.worker = SyncWorker(auth.char_id, auth.current_token)
        self.worker.finished_data.connect(self.on_data_ready)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_data_ready(self, orders):
        self.all_orders = orders
        self.populate_tables(orders)
        self.btn_refresh.setEnabled(True)
        self.btn_repopulate.setEnabled(True)
        self.btn_refresh.setText("SINCRONIZAR ÓRDENES")
        self.btn_repopulate.setText("ACTUALIZAR")
        
        if getattr(self, 'is_update_mode', False):
            self.lbl_status.setText(f"● ÓRDENES ACTUALIZADAS: {len(orders)} ACTIVAS")
        else:
            self.lbl_status.setText(f"● SISTEMA LISTO: {len(orders)} ÓRDENES ABIERTAS")
            
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800;")
        
        if not orders:
            self.lbl_det_item.setText("SELECCIONA UNA ORDEN")
            self.lbl_det_type.setText("---")
            self.lbl_det_my_price.setText("---")
            self.lbl_det_best_buy.setText("---")
            self.lbl_det_best_sell.setText("---")
            self.lbl_det_margin.setText("---")
            self.lbl_det_profit_unit.setText("---")
            self.lbl_det_profit_total.setText("---")
            self.lbl_det_status.setText("---")
            self.lbl_det_diff.setText("---")

    def on_error(self, msg):
        self.btn_refresh.setEnabled(True)
        self.btn_repopulate.setEnabled(True)
        self.btn_refresh.setText("SINCRONIZAR ÓRDENES")
        self.btn_repopulate.setText("ACTUALIZAR")
        self.lbl_status.setText(f"● ERROR: {msg.upper()}")
        self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800;")
        
        if "token" in msg.lower() or "401" in msg or "403" in msg:
            auth = AuthManager.instance()
            auth.current_token = None
            self.lbl_status.setText("● SESIÓN EXPIRADA. VUELVE A PULSAR SINCRONIZAR.")

    def populate_tables(self, orders):
        sell_orders = [o for o in orders if not o.is_buy_order]
        buy_orders = [o for o in orders if o.is_buy_order]

        def fill_table(table, data):
            table.setRowCount(0)
            table.setRowCount(len(data))
            for row, o in enumerate(data):
                a = o.analysis
                
                i_name = QTableWidgetItem(o.item_name)
                i_name.setData(Qt.UserRole, o.type_id)
                
                i_type = QTableWidgetItem("BUY" if o.is_buy_order else "SELL")
                i_type.setForeground(QColor("#3b82f6") if o.is_buy_order else QColor("#ef4444"))
                
                i_myprice = QTableWidgetItem(format_isk(o.price))
                
                best_comp = a.best_buy if o.is_buy_order else a.best_sell
                i_best = QTableWidgetItem(format_isk(best_comp))
                
                i_total = QTableWidgetItem(f"{o.volume_total:,}")
                i_remain = QTableWidgetItem(f"{o.volume_remain:,}")
                
                i_spread = QTableWidgetItem(f"{a.spread_pct:.1f}%")
                
                i_margin = QTableWidgetItem(f"{a.margin_pct:.1f}%")
                if a.margin_pct > 15: i_margin.setForeground(QColor("#10b981"))
                elif a.margin_pct < 0: i_margin.setForeground(QColor("#ef4444"))
                
                i_profit = QTableWidgetItem(format_isk(a.net_profit_total))
                if a.net_profit_total > 0: i_profit.setForeground(QColor("#10b981"))
                elif a.net_profit_total < 0: i_profit.setForeground(QColor("#ef4444"))
                
                i_state = QTableWidgetItem(a.state)
                if "Sana" in a.state or "Competitiva" in a.state or "Rotación Sana" in a.state:
                    i_state.setForeground(QColor("#10b981"))
                elif "Ajustado" in a.state or "Aún Rentable" in a.state:
                    i_state.setForeground(QColor("#f59e0b"))
                else:
                    i_state.setForeground(QColor("#ef4444"))
                    
                table.setItem(row, 0, i_name)
                table.setItem(row, 1, i_type)
                table.setItem(row, 2, i_myprice)
                table.setItem(row, 3, i_best)
                table.setItem(row, 4, i_total)
                table.setItem(row, 5, i_remain)
                table.setItem(row, 6, i_spread)
                table.setItem(row, 7, i_margin)
                table.setItem(row, 8, i_profit)
                table.setItem(row, 9, i_state)

        fill_table(self.table_sell, sell_orders)
        fill_table(self.table_buy, buy_orders)

    def on_sell_selection_changed(self):
        sel = self.table_sell.selectedItems()
        if not sel: return
        self.table_buy.blockSignals(True)
        self.table_buy.clearSelection()
        self.table_buy.blockSignals(False)
        self._handle_selection(self.table_sell, sel[0].row())

    def on_buy_selection_changed(self):
        sel = self.table_buy.selectedItems()
        if not sel: return
        self.table_sell.blockSignals(True)
        self.table_sell.clearSelection()
        self.table_sell.blockSignals(False)
        self._handle_selection(self.table_buy, sel[0].row())

    def _handle_selection(self, table, row):
        t_id = table.item(row, 0).data(Qt.UserRole)
        myprice = table.item(row, 2).text().replace(',', '').replace(' ISK', '')
        o = next((ord for ord in self.all_orders if ord.type_id == t_id and format_isk(ord.price) == table.item(row, 2).text()), None)
        if o:
            self.update_detail(o)

    def update_detail(self, o):
        self.lbl_det_item.setText(o.item_name.upper())
        self.lbl_det_type.setText(f"ORDEN DE {'COMPRA' if o.is_buy_order else 'VENTA'} | ID: {o.order_id}")
        
        a = o.analysis
        self.lbl_det_my_price.setText(format_isk(o.price, True))
        self.lbl_det_best_buy.setText(format_isk(a.best_buy, True))
        self.lbl_det_best_sell.setText(format_isk(a.best_sell, True))
        
        self.lbl_det_margin.setText(f"{a.margin_pct:.1f}%")
        self.lbl_det_profit_unit.setText(format_isk(a.net_profit_per_unit, True))
        self.lbl_det_profit_total.setText(format_isk(a.net_profit_total, True))
        
        self.lbl_det_status.setText(a.state.upper())
        if "Sana" in a.state or "Competitiva" in a.state or "Rotación Sana" in a.state:
            self.lbl_det_status.setStyleSheet("color: #10b981; font-size: 14px; font-weight: 900;")
        elif "Ajustado" in a.state or "Aún Rentable" in a.state:
            self.lbl_det_status.setStyleSheet("color: #f59e0b; font-size: 14px; font-weight: 900;")
        else:
            self.lbl_det_status.setStyleSheet("color: #ef4444; font-size: 14px; font-weight: 900;")
            
        diff_str = format_isk(abs(a.difference_to_best), True)
        if a.competitive:
            self.lbl_det_diff.setText(f"Liderando por {diff_str}")
        else:
            self.lbl_det_diff.setText(f"Superado por {diff_str}")

    def on_double_click(self, item, table):
        row = item.row()
        t_id = table.item(row, 0).data(Qt.UserRole)
        item_name = table.item(row, 0).text()
        
        auth = AuthManager.instance()
        def feedback(msg, color):
            self.lbl_status.setText(f"● {msg.upper()}")
            self.lbl_status.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
            
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), auth.char_id, t_id, item_name, feedback)

    def on_context_menu(self, pos, table):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QGuiApplication
        
        item = table.itemAt(pos)
        if not item: return
            
        row = item.row()
        item_name = table.item(row, 0).text()
        
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #1e293b; color: #f1f5f9; border: 1px solid #334155; font-size: 11px; } "
            "QMenu::item { padding: 4px 15px; } "
            "QMenu::item:selected { background-color: #3b82f6; }"
        )
        
        copy_action = menu.addAction(f"Copiar nombre: {item_name}")
        action = menu.exec(table.viewport().mapToGlobal(pos))
        
        if action == copy_action:
            QGuiApplication.clipboard().setText(item_name)
            self.lbl_status.setText(f"● {item_name.upper()} COPIADO AL PORTAPAPELES")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800;")
