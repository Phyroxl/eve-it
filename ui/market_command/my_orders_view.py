import logging # VERSION: 1.1.5-FIX (Syntax & Stability)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout, QDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap

from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.market_engine import analyze_character_orders, analyze_inventory
from core.config_manager import load_market_filters, save_ui_config, load_ui_config
from ui.market_command.widgets import ItemInteractionHelper
from core.item_metadata import ItemMetadataHelper
from ui.market_command.performance_view import AsyncImageLoader
from core.cost_basis_service import CostBasisService
from core.tax_service import TaxService
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
            
            TaxService.instance().refresh_from_esi(self.char_id, self.token)
            
            type_ids = list(set(o['type_id'] for o in orders))
            all_market_orders = client.market_orders(10000002)
            relevant_market_orders = [mo for mo in all_market_orders if mo['type_id'] in type_ids]
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            config = load_market_filters()
            
            cost_service = CostBasisService.instance()
            if cost_service.has_wallet_scope():
                cost_service.refresh_from_esi(self.char_id, self.token)
            
            analyzed = analyze_character_orders(orders, relevant_market_orders, item_names, config, char_id=self.char_id)
            self.finished_data.emit(analyzed)
        except Exception as e:
            self.error.emit(str(e))

class InventoryWorker(QThread):
    finished_data = Signal(list)
    error = Signal(str)

    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token

    def run(self):
        try:
            client = ESIClient()
            assets = client.character_assets(self.char_id, self.token)
            if assets == "missing_scope":
                self.error.emit("missing_scope")
                return
            if not assets:
                self.finished_data.emit([])
                return
            
            filtered_assets = [a for a in assets if 'slot' not in a.get('location_flag', '').lower()]
            if not filtered_assets:
                self.finished_data.emit([])
                return

            type_ids = list(set(a['type_id'] for a in filtered_assets))
            all_market_orders = client.market_orders(10000002)
            if not all_market_orders:
                self.error.emit("pricing_error")
                return

            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            config = load_market_filters()
            analyzed = analyze_inventory(filtered_assets, all_market_orders, item_names, config, char_id=self.char_id)
            self.finished_data.emit(analyzed)
        except Exception as e:
            self.error.emit(str(e))

class InventoryAnalysisDialog(QDialog):
    def __init__(self, items, image_loader, parent=None):
        super().__init__(parent)
        self.items = items
        self.image_loader = image_loader
        self.setWindowTitle("INVENTARIO - VALOR DE ACTIVOS")
        self.setMinimumSize(950, 650)
        self.setStyleSheet("background-color: #000000;")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        header = QFrame()
        header.setFixedHeight(70)
        header.setStyleSheet("background-color: #1e293b; border-radius: 4px; border: 1px solid #334155;")
        hl = QHBoxLayout(header)
        title_v = QVBoxLayout()
        title = QLabel("VALORACIÓN DE ACTIVOS")
        title.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 900; letter-spacing: 1px; border:none;")
        subtitle = QLabel("PRECIOS DE VENTA JITA 4-4 (NETOS)")
        subtitle.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700; border:none;")
        title_v.addWidget(title)
        title_v.addWidget(subtitle)
        hl.addLayout(title_v)
        hl.addStretch()
        
        total_val = sum(item.analysis.est_total_value for item in self.items)
        val_v = QVBoxLayout()
        val_lbl = QLabel(format_isk(total_val))
        val_lbl.setStyleSheet("color: #10b981; font-size: 20px; font-weight: 900; border:none;")
        val_sub = QLabel("VALOR TOTAL ESTIMADO")
        val_sub.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 800; border:none;")
        val_sub.setAlignment(Qt.AlignRight)
        val_v.addWidget(val_lbl)
        val_v.addWidget(val_sub)
        hl.addLayout(val_v)
        layout.addWidget(header)

        self.table = QTableWidget(len(self.items), 6)
        self.table.setHorizontalHeaderLabels(["", "ÍTEM", "CANTIDAD", "PRECIO UNIT. (NETO)", "VALOR TOTAL", "%"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setStyleSheet(
            "QTableWidget { background: #000000; color: #f1f5f9; gridline-color: #1e293b; border: 1px solid #1e293b; font-size: 11px; } "
            "QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; padding: 8px; } "
            "QTableWidget::item:selected { background: #1e293b; }"
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(32, 32))
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 300)

        sorted_items = sorted(self.items, key=lambda x: x.analysis.est_total_value, reverse=True)
        for row, item in enumerate(sorted_items):
            i_icon = QTableWidgetItem()
            url = ItemMetadataHelper.get_icon_url(item.type_id)
            self.image_loader.load(url, lambda px, it=i_icon: it.setIcon(QIcon(px)))
            i_name = QTableWidgetItem(item.item_name)
            i_qty = QTableWidgetItem(f"{item.quantity:,}")
            i_qty.setTextAlignment(Qt.AlignCenter)
            i_price = QTableWidgetItem(format_isk(item.analysis.est_net_sell_unit))
            i_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            i_total = QTableWidgetItem(format_isk(item.analysis.est_total_value))
            i_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            i_total.setForeground(QColor("#10b981"))
            pct = (item.analysis.est_total_value / total_val * 100) if total_val > 0 else 0
            i_pct = QTableWidgetItem(f"{pct:.1f}%")
            i_pct.setTextAlignment(Qt.AlignCenter)
            
            self.table.setItem(row, 0, i_icon)
            self.table.setItem(row, 1, i_name)
            self.table.setItem(row, 2, i_qty)
            self.table.setItem(row, 3, i_price)
            self.table.setItem(row, 4, i_total)
            self.table.setItem(row, 5, i_pct)
        layout.addWidget(self.table)

class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.inv_worker = None
        self.all_orders = []
        self.image_loader = AsyncImageLoader()
        self.inventory_cache = None
        self.inventory_status = "idle" 
        self.inventory_error_msg = ""
        self._syncing_headers = False
        
        self.setup_ui()
        self._load_ui_state()
        AuthManager.instance().authenticated.connect(self._on_authenticated)

    def _on_authenticated(self, char_name, tokens):
        self.do_sync(is_update=False)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MIS PEDIDOS")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        self.lbl_status = QLabel("● SINCRONIZACIÓN REQUERIDA")
        self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: 800;")
        title_v.addWidget(title_lbl)
        title_v.addWidget(self.lbl_status)

        self.btn_repopulate = QPushButton("ACTUALIZAR")
        self.btn_refresh = QPushButton("SINCRONIZAR ÓRDENES")
        self.btn_inventory = QPushButton("INVENTARIO")
        
        for b in [self.btn_repopulate, self.btn_refresh, self.btn_inventory]:
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(35)
            b.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #94a3b8; font-size: 10px; font-weight: 900; border: 1px solid #334155; border-radius: 4px; padding: 0 15px; }"
                "QPushButton:hover { background-color: #334155; color: #f1f5f9; }"
            )
        self.btn_refresh.setStyleSheet(self.btn_refresh.styleSheet().replace("#1e293b", "#3b82f6").replace("#94a3b8", "white"))
        self.btn_inventory.setStyleSheet(self.btn_inventory.styleSheet().replace("#1e293b", "#10b981").replace("#94a3b8", "white"))

        self.btn_repopulate.clicked.connect(lambda: self.do_sync(is_update=True))
        self.btn_refresh.clicked.connect(lambda: self.do_sync(is_update=False))
        self.btn_inventory.clicked.connect(self.do_inventory_analysis)

        header_layout.addLayout(title_v)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_inventory)
        header_layout.addSpacing(10)
        header_layout.addWidget(self.btn_repopulate)
        header_layout.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header_layout)

        def create_t():
            t = QTableWidget(0, 12)
            t.setHorizontalHeaderLabels(["", "ÍTEM", "TIPO", "MI PRECIO", "MI PROMEDIO", "MEJOR COMPRA", "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setStyleSheet("QTableWidget { background: #000000; color: #f1f5f9; border: 1px solid #1e293b; font-size: 10px; } "
                            "QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; padding: 4px; }")
            t.horizontalHeader().setStretchLastSection(True)
            t.setIconSize(QSize(24, 24))
            t.setColumnWidth(0, 32)
            t.setColumnWidth(1, 180)
            return t

        self.table_sell = create_t()
        self.table_buy = create_t()
        
        self.table_sell.horizontalHeader().sectionResized.connect(lambda i, o, n: self._on_header_resized(self.table_sell, i, n))
        self.table_buy.horizontalHeader().sectionResized.connect(lambda i, o, n: self._on_header_resized(self.table_buy, i, n))
        self.table_sell.horizontalHeader().sectionMoved.connect(lambda i, o, n: self._on_header_moved(self.table_sell, i, o, n))
        self.table_buy.horizontalHeader().sectionMoved.connect(lambda i, o, n: self._on_header_moved(self.table_buy, i, o, n))

        self.table_sell.itemSelectionChanged.connect(self.on_sell_selection_changed)
        self.table_buy.itemSelectionChanged.connect(self.on_buy_selection_changed)
        self.table_sell.itemDoubleClicked.connect(lambda i: self.on_double_click(i, self.table_sell))
        self.table_buy.itemDoubleClicked.connect(lambda i: self.on_double_click(i, self.table_buy))

        self.lbl_sell_count = QLabel("ÓRDENES DE VENTA (0)")
        self.lbl_sell_count.setStyleSheet("color:#ef4444; font-weight:900; font-size:10px;")
        self.lbl_buy_count = QLabel("ÓRDENES DE COMPRA (0)")
        self.lbl_buy_count.setStyleSheet("color:#3b82f6; font-weight:900; font-size:10px;")
        
        self.main_layout.addWidget(self.lbl_sell_count)
        self.main_layout.addWidget(self.table_sell, 1)
        self.main_layout.addWidget(self.lbl_buy_count)
        self.main_layout.addWidget(self.table_buy, 1)

        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(130)
        self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_layout()
        self.main_layout.addWidget(self.detail_panel)

    def setup_detail_layout(self):
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(15, 12, 15, 12)
        
        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setFixedSize(64, 64)
        self.lbl_det_icon.setStyleSheet("background:#1e293b; border-radius:4px;")
        dl.addWidget(self.lbl_det_icon)

        info_v = QVBoxLayout()
        self.lbl_det_item = QLabel("SELECCIONA UNA ORDEN")
        self.lbl_det_item.setStyleSheet("color:#f1f5f9; font-size:14px; font-weight:900;")
        self.lbl_det_type = QLabel("---")
        self.lbl_det_type.setStyleSheet("color:#64748b; font-size:10px; font-weight:800;")
        self.lbl_det_cost_msg = QLabel("---")
        self.lbl_det_cost_msg.setStyleSheet("color:#475569; font-size:9px; font-weight:700;")
        
        info_v.addWidget(self.lbl_det_item)
        info_v.addWidget(self.lbl_det_type)
        info_v.addWidget(self.lbl_det_cost_msg)
        info_v.addStretch()
        dl.addLayout(info_v, 2)

        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        def add_m(l, r, c):
            v = QVBoxLayout()
            lbl = QLabel(l, styleSheet="color:#475569; font-size:9px; font-weight:900;")
            val = QLabel("---", styleSheet="color:#f1f5f9; font-size:11px; font-weight:900;")
            v.addWidget(lbl)
            v.addWidget(val)
            self.grid.addLayout(v, r, c)
            return val

        self.det_price = add_m("MI PRECIO", 0, 0)
        self.det_avg = add_m("MI PROMEDIO", 0, 1)
        self.det_best_buy = add_m("MEJOR COMPRA", 0, 2)
        self.det_best_sell = add_m("MEJOR VENTA", 0, 3)
        self.det_margin = add_m("MARGEN NETO", 1, 0)
        self.det_profit_u = add_m("PROFIT / U", 1, 1)
        self.det_profit_t = add_m("PROFIT TOTAL", 1, 2)
        self.det_state = add_m("ESTADO", 1, 3)
        
        dl.addLayout(self.grid, 5)

    def _on_header_resized(self, source_table, index, size):
        if self._syncing_headers: return
        self._syncing_headers = True
        target = self.table_buy if source_table == self.table_sell else self.table_sell
        target.setColumnWidth(index, size)
        self._syncing_headers = False
        self._save_ui_state()

    def _on_header_moved(self, source_table, index, old_idx, new_idx):
        if self._syncing_headers: return
        self._syncing_headers = True
        target = self.table_buy if source_table == self.table_sell else self.table_sell
        target.horizontalHeader().moveSection(old_idx, new_idx)
        self._syncing_headers = False
        self._save_ui_state()

    def _save_ui_state(self):
        h = self.table_sell.horizontalHeader()
        state = {
            "widths": [self.table_sell.columnWidth(i) for i in range(self.table_sell.columnCount())],
            "order": [h.visualIndex(i) for i in range(self.table_sell.columnCount())]
        }
        save_ui_config("my_orders", state)

    def _load_ui_state(self):
        state = load_ui_config("my_orders")
        if not state: return
        self._syncing_headers = True
        try:
            widths = state.get("widths", [])
            for i, w in enumerate(widths):
                if i < self.table_sell.columnCount():
                    self.table_sell.setColumnWidth(i, w)
                    self.table_buy.setColumnWidth(i, w)
            order = state.get("order", [])
            for logical_idx, visual_idx in enumerate(order):
                if logical_idx < self.table_sell.columnCount():
                    self.table_sell.horizontalHeader().moveSection(self.table_sell.horizontalHeader().visualIndex(logical_idx), visual_idx)
                    self.table_buy.horizontalHeader().moveSection(self.table_buy.horizontalHeader().visualIndex(logical_idx), visual_idx)
        finally:
            self._syncing_headers = False

    def do_sync(self, is_update=False):
        auth = AuthManager.instance()
        if not auth.current_token:
            auth.login()
            return
        
        self.btn_refresh.setEnabled(False)
        self.btn_repopulate.setEnabled(False)
        self.lbl_status.setText("● SINCRONIZANDO CON ESI...")
        self.lbl_status.setStyleSheet("color:#3b82f6;")
        
        self.worker = SyncWorker(auth.char_id, auth.current_token)
        self.worker.finished_data.connect(self.on_data_ready)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_data_ready(self, orders):
        self.all_orders = orders
        self.populate_all(orders)
        self.btn_refresh.setEnabled(True)
        self.btn_repopulate.setEnabled(True)
        self.lbl_status.setText(f"● LISTO: {len(orders)} ÓRDENES")
        self.lbl_status.setStyleSheet("color:#10b981;")
        self._start_inventory_preload()

    def _start_inventory_preload(self):
        auth = AuthManager.instance()
        if not auth.current_token: return
        self.inventory_status = "loading"
        self.inv_worker = InventoryWorker(auth.char_id, auth.current_token)
        self.inv_worker.finished_data.connect(self._on_inv_preloaded)
        self.inv_worker.error.connect(self._on_inv_error)
        self.inv_worker.start()

    def _on_inv_preloaded(self, data):
        self.inventory_cache = data
        self.inventory_status = "ready"

    def _on_inv_error(self, err):
        self.inventory_status = "error"
        self.inventory_error_msg = err

    def populate_all(self, orders):
        sells = [o for o in orders if not o.is_buy_order]
        buys = [o for o in orders if o.is_buy_order]
        
        self.lbl_sell_count.setText(f"ÓRDENES DE VENTA ({len(sells)})")
        self.lbl_buy_count.setText(f"ÓRDENES DE COMPRA ({len(buys)})")

        def fill(t, data):
            t.setRowCount(0)
            t.setRowCount(len(data))
            for r, o in enumerate(data):
                a = o.analysis
                cost = CostBasisService.instance().get_cost_basis(o.type_id)
                
                i_ico = QTableWidgetItem()
                i_ico.setData(Qt.UserRole, o.type_id)
                i_ico.setData(Qt.UserRole + 1, o.order_id)
                self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px, it=i_ico: it.setIcon(QIcon(px)))

                i_avg = QTableWidgetItem(format_isk(cost.average_buy_price) if cost else "Sin registros")
                i_avg.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                i_avg.setForeground(QColor("#f1f5f9") if cost else QColor("#475569"))
                
                i_state = QTableWidgetItem(a.state)
                s_txt = a.state.lower()
                if any(x in s_txt for x in ["sana", "liderando", "competitiva"]): i_state.setForeground(QColor("#10b981")) 
                elif any(x in s_txt for x in ["superado", "ajustado", "rentable"]): i_state.setForeground(QColor("#f59e0b")) 
                elif any(x in s_txt for x in ["perdida", "error", "no rentable"]): i_state.setForeground(QColor("#ef4444")) 
                else: i_state.setForeground(QColor("#94a3b8")) 

                items = [
                    i_ico, QTableWidgetItem(o.item_name), 
                    QTableWidgetItem("BUY" if o.is_buy_order else "SELL"),
                    QTableWidgetItem(format_isk(o.price)),
                    i_avg,
                    QTableWidgetItem(format_isk(a.best_buy if o.is_buy_order else a.best_sell)),
                    QTableWidgetItem(str(o.volume_total)), QTableWidgetItem(str(o.volume_remain)),
                    QTableWidgetItem(f"{a.spread_pct:.1f}%"), 
                    QTableWidgetItem(f"{a.margin_pct:.1f}%" if not o.is_buy_order and cost else "---"),
                    QTableWidgetItem(format_isk(a.net_profit_total) if not o.is_buy_order and cost else "---"),
                    i_state
                ]
                for i in [3,4,5,10]: items[i].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                for i in [2,6,7,8,9,11]: items[i].setTextAlignment(Qt.AlignCenter)
                
                items[2].setForeground(QColor("#3b82f6") if o.is_buy_order else QColor("#ef4444"))
                if not o.is_buy_order and cost:
                    if a.margin_pct > 15: items[9].setForeground(QColor("#10b981"))
                    if a.net_profit_total > 0: items[10].setForeground(QColor("#10b981"))

                for c, item in enumerate(items): t.setItem(r, c, item)

        fill(self.table_sell, sells)
        fill(self.table_buy, buys)

    def on_sell_selection_changed(self):
        self.table_buy.clearSelection()
        self._handle_sel(self.table_sell)

    def on_buy_selection_changed(self):
        self.table_sell.clearSelection()
        self._handle_sel(self.table_buy)

    def _handle_sel(self, t):
        si = t.selectedItems()
        if not si: return
        oid = t.item(si[0].row(), 0).data(Qt.UserRole + 1)
        o = next((ord for ord in self.all_orders if ord.order_id == oid), None)
        if o: self.update_det(o)

    def update_det(self, o):
        self.lbl_det_item.setText(o.item_name.upper())
        self.lbl_det_type.setText("COMPRA" if o.is_buy_order else "VENTA")
        self.lbl_det_type.setStyleSheet("color:#3b82f6;" if o.is_buy_order else "color:#ef4444;")
        self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px: self.lbl_det_icon.setPixmap(px.scaled(64,64,Qt.KeepAspectRatio)))
        
        a = o.analysis
        cost = CostBasisService.instance().get_cost_basis(o.type_id)
        avg = cost.average_buy_price if cost else 0.0
        
        if o.is_buy_order:
            self.lbl_det_cost_msg.setText("Profit potencial basado en Jita Sell")
        elif avg > 0:
            self.lbl_det_cost_msg.setText("Profit real basado en Coste Medio Ponderado (WAC)")
        else:
            self.lbl_det_cost_msg.setText("Sin registros de coste real para calcular beneficio")
        
        self.det_price.setText(format_isk(o.price))
        self.det_price.setStyleSheet("color:#f1f5f9; font-weight:900;")
        self.det_avg.setText(format_isk(avg) if avg > 0 else "SIN REGISTROS")
        self.det_avg.setStyleSheet("color:#f1f5f9;" if avg > 0 else "color:#475569;")
        self.det_best_buy.setText(format_isk(a.best_buy))
        self.det_best_buy.setStyleSheet("color:#3b82f6; font-weight:900;")
        self.det_best_sell.setText(format_isk(a.best_sell))
        self.det_best_sell.setStyleSheet("color:#ef4444; font-weight:900;")
        
        s_txt = a.state.lower()
        self.det_state.setText(a.state.upper())
        if any(x in s_txt for x in ["sana", "liderando"]): self.det_state.setStyleSheet("color:#10b981; font-weight:900;")
        elif "superado" in s_txt: self.det_state.setStyleSheet("color:#f59e0b; font-weight:900;")
        else: self.det_state.setStyleSheet("color:#ef4444; font-weight:900;")
        
        if (not o.is_buy_order and avg > 0) or o.is_buy_order:
            self.det_margin.setText(f"{a.margin_pct:.1f}%")
            self.det_margin.setStyleSheet("color:#10b981;" if a.margin_pct > 0 else "color:#ef4444;")
            self.det_profit_u.setText(format_isk(a.net_profit_per_unit))
            self.det_profit_u.setStyleSheet("color:#10b981;" if a.net_profit_per_unit > 0 else "color:#ef4444;")
            self.det_profit_t.setText(format_isk(a.net_profit_total))
            self.det_profit_t.setStyleSheet("color:#10b981;" if a.net_profit_total > 0 else "color:#ef4444;")
        else:
            self.det_margin.setText("---")
            self.det_margin.setStyleSheet("color:#475569;")
            self.det_profit_u.setText("---")
            self.det_profit_u.setStyleSheet("color:#475569;")
            self.det_profit_t.setText("---")
            self.det_profit_t.setStyleSheet("color:#475569;")

    def on_double_click(self, item, t):
        tid = t.item(item.row(), 0).data(Qt.UserRole)
        name = t.item(item.row(), 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: self.lbl_status.setText(m))

    def do_inventory_analysis(self):
        if self.inventory_status == "ready" and self.inventory_cache is not None:
            if not self.inventory_cache:
                QMessageBox.information(self, "Inventario Vacío", "No se encontraron activos valorables.")
                return
            InventoryAnalysisDialog(self.inventory_cache, self.image_loader, self).exec()
            return
        if self.inventory_status == "loading":
            QMessageBox.information(self, "Cargando", "Analizando inventario...")
            return
        if self.inventory_status == "error":
            self.on_inventory_error(self.inventory_error_msg)
            self.inventory_status = "idle"
            return
        
        self.lbl_status.setText("● CARGANDO INVENTARIO...")
        self.lbl_status.setStyleSheet("color:#3b82f6;")
        auth = AuthManager.instance()
        if not auth.current_token:
            auth.login()
            return
        
        self.inventory_status = "loading"
        self.inv_worker = InventoryWorker(auth.char_id, auth.current_token)
        
        def on_done(data): 
            self.inventory_cache = data
            self.inventory_status = "ready"
            if not data:
                QMessageBox.information(self, "Inventario Vacío", "No se encontraron activos valorables.")
            else:
                InventoryAnalysisDialog(data, self.image_loader, self).exec()
        
        self.inv_worker.finished_data.connect(on_done)
        self.inv_worker.error.connect(self.on_inventory_error)
        self.inv_worker.start()

    def on_inventory_error(self, msg):
        if msg == "missing_scope": QMessageBox.warning(self, "Permiso Faltante", "Falta el permiso 'esi-assets.read_assets.v1'.")
        elif msg == "pricing_error": QMessageBox.critical(self, "Error de Precios", "No se pudieron obtener precios de Jita.")
        else: QMessageBox.critical(self, "Error", f"Fallo al cargar inventario: {msg}")

    def on_error(self, err):
        self.btn_refresh.setEnabled(True)
        self.btn_repopulate.setEnabled(True)
        self.lbl_status.setText(f"● ERROR: {err[:50]}")
        self.lbl_status.setStyleSheet("color:#ef4444;")
