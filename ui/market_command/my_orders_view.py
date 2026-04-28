import logging # VERSION: 1.1.20-REFORMATED (Clean Structure, No Compact Errors)
import time
import threading
import json
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, 
    QGridLayout, QDialog, QMessageBox, QProgressBar, QLineEdit, QComboBox, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap, QAction, QGuiApplication

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

# --- Helper Widgets ---

class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, text, value):
        super().__init__(str(text))
        self.sort_value = float(value) if value is not None else -1e18
    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)

class SemanticTableWidgetItem(QTableWidgetItem):
    PRIORITY = {
        "liderando": 1000, "competitiva": 950, "sana": 900, "rentable": 850,
        "superada con beneficio": 600, "ajustado": 500, "superada": 400,
        "fuera de mercado": 250, "pérdida": 200, "no rentable": 150, "error": 0,
        "vender": 500, "mantener": 200, "revisar": 100
    }
    def __init__(self, text, roi=None):
        super().__init__(text)
        self.roi = roi if roi is not None else -1e18
    def __lt__(self, other):
        if isinstance(other, SemanticTableWidgetItem):
            if self.roi != -1e18 or other.roi != -1e18:
                return self.roi < other.roi
            p1, p2 = 0, 0
            t1, t2 = self.text().lower(), other.text().lower()
            for k, v in self.PRIORITY.items():
                if k in t1: p1 = v; break
            for k, v in self.PRIORITY.items():
                if k in t2: p2 = v; break
            return p1 < p2
        return super().__lt__(other)

# --- Workers ---

class TradeProfitsWorker(QThread):
    finished_data = Signal(list)
    status_update = Signal(str, int)
    error = Signal(str)

    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token

    def run(self):
        try:
            client = ESIClient()
            self.status_update.emit("DESCARGANDO TRANSACCIONES...", 20)
            txs = client.wallet_transactions(self.char_id, self.token)
            if txs == "missing_scope":
                self.error.emit("Falta permiso: esi-wallet.read_character_wallet.v1")
                return
            if not txs:
                self.finished_data.emit([])
                return
            
            sorted_tx = sorted(txs, key=lambda x: x['date'])
            trades = []
            stock_map = {}
            
            type_ids = list(set(t['type_id'] for t in sorted_tx))
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            tx_service = TaxService.instance()
            tx_service.refresh_from_esi(self.char_id, self.token)
            taxes = tx_service.get_taxes(self.char_id)
            sales_tax = taxes.sales_tax_pct / 100.0
            
            for t in sorted_tx:
                tid = t['type_id']
                qty = t['quantity']
                price = t['unit_price']
                is_buy = t.get('is_buy', False)
                loc_id = t.get('location_id', 0)
                
                if tid not in stock_map:
                    stock_map[tid] = {'qty': 0, 'cost': 0.0}
                curr = stock_map[tid]
                fee_pct, _ = tx_service.get_effective_broker_fee(self.char_id, loc_id, self.token)
                
                if is_buy:
                    curr['qty'] += qty
                    curr['cost'] += qty * price * (1.0 + fee_pct/100.0)
                else:
                    if curr['qty'] > 0:
                        wac_unit = curr['cost'] / curr['qty']
                        total_cost = qty * wac_unit
                        gross_sell = qty * price
                        fees = (gross_sell * fee_pct / 100.0) + (gross_sell * sales_tax)
                        profit = gross_sell - fees - total_cost
                        margin = (profit / total_cost * 100) if total_cost > 0 else 0
                        
                        trades.append({
                            'date': t['date'],
                            'type_id': tid,
                            'name': item_names.get(tid, f"Item {tid}"),
                            'qty': qty,
                            'buy_unit': wac_unit,
                            'sell_unit': price,
                            'buy_total': total_cost,
                            'sell_total': gross_sell,
                            'fees': fees,
                            'margin': margin,
                            'profit': profit
                        })
                        curr['qty'] -= qty
                        curr['cost'] -= total_cost
                        if curr['qty'] < 0:
                            curr['qty'] = 0
                            curr['cost'] = 0.0
            
            self.finished_data.emit(list(reversed(trades)))
        except Exception as e:
            self.error.emit(str(e))

# --- Diálogos ---

class TradeProfitsDialog(QDialog):
    def __init__(self, char_id, token, image_loader, parent=None):
        super().__init__(parent)
        self.char_id = char_id
        self.token = token
        self.image_loader = image_loader
        self.all_trades = []
        self.filtered_trades = []
        self.page_size = 50
        self.current_page = 0
        self.setWindowTitle("TRADE PROFITS")
        self.setMinimumSize(1200, 750)
        self.setStyleSheet("background-color: #000000;")
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        f_frame = QFrame()
        f_frame.setStyleSheet("background: #0f172a; border-radius: 8px; border: 1px solid #1e293b;")
        fl = QHBoxLayout(f_frame)
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filtrar item...")
        self.txt_filter.setFixedWidth(250)
        self.txt_filter.textChanged.connect(self.apply_filters)
        
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Todos", "Ganancias", "Pérdidas"])
        self.cmb_mode.currentIndexChanged.connect(self.apply_filters)
        
        fl.addWidget(QLabel("ÍTEM:"))
        fl.addWidget(self.txt_filter)
        fl.addWidget(QLabel("MODO:"))
        fl.addWidget(self.cmb_mode)
        fl.addStretch()
        layout.addWidget(f_frame)
        
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["FECHA", "", "ÍTEM", "CANT", "P. COMPRA", "P. VENTA", "T. COMPRA", "T. VENTA", "FEES", "MARGEN %", "PROFIT"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table)
        
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("ANTERIOR")
        self.btn_next = QPushButton("SIGUIENTE")
        self.lbl_page = QLabel("Página 1")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.lbl_page)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

    def load_data(self):
        self.worker = TradeProfitsWorker(self.char_id, self.token)
        self.worker.finished_data.connect(self.on_data)
        self.worker.start()

    def on_data(self, data):
        self.all_trades = data
        self.apply_filters()

    def apply_filters(self):
        txt = self.txt_filter.text().lower()
        mode = self.cmb_mode.currentIndex()
        self.filtered_trades = [t for t in self.all_trades if txt in t['name'].lower()]
        if mode == 1:
            self.filtered_trades = [t for t in self.filtered_trades if t['profit'] > 0]
        elif mode == 2:
            self.filtered_trades = [t for t in self.filtered_trades if t['profit'] < 0]
        self.current_page = 0
        self.update_table()

    def update_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        start = self.current_page * self.page_size
        end = (self.current_page + 1) * self.page_size
        page_items = self.filtered_trades[start:end]
        self.table.setRowCount(len(page_items))
        
        for r, t in enumerate(page_items):
            self.table.setItem(r, 0, QTableWidgetItem(t['date'].replace('T', ' ')))
            i_ico = QTableWidgetItem()
            i_ico.setData(Qt.UserRole, t['type_id'])
            self.image_loader.load(ItemMetadataHelper.get_icon_url(t['type_id']), lambda px, it=i_ico: it.setIcon(QIcon(px)))
            self.table.setItem(r, 1, i_ico)
            self.table.setItem(r, 2, QTableWidgetItem(t['name']))
            self.table.setItem(r, 3, NumericTableWidgetItem(f"{t['qty']:,}", t['qty']))
            self.table.setItem(r, 4, NumericTableWidgetItem(format_isk(t['buy_unit']), t['buy_unit']))
            self.table.setItem(r, 5, NumericTableWidgetItem(format_isk(t['sell_unit']), t['sell_unit']))
            self.table.setItem(r, 6, NumericTableWidgetItem(format_isk(t['buy_total']), t['buy_total']))
            self.table.setItem(r, 7, NumericTableWidgetItem(format_isk(t['sell_total']), t['sell_total']))
            self.table.setItem(r, 8, NumericTableWidgetItem(format_isk(t['fees']), t['fees']))
            
            m_col = QColor("#10b981" if t['margin'] > 15 else ("#f59e0b" if t['margin'] >= 0 else "#ef4444"))
            i_mar = NumericTableWidgetItem(f"{t['margin']:.1f}%", t['margin'])
            i_mar.setForeground(m_col)
            self.table.setItem(r, 9, i_mar)
            
            p_col = QColor("#10b981" if t['profit'] > 0 else "#ef4444")
            i_prof = NumericTableWidgetItem(format_isk(t['profit']), t['profit'])
            i_prof.setForeground(p_col)
            self.table.setItem(r, 10, i_prof)
            
        self.table.setSortingEnabled(True)
        tot = (len(self.filtered_trades) + self.page_size - 1) // self.page_size
        self.lbl_page.setText(f"Página {self.current_page + 1} de {max(1, tot)}")
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(end < len(self.filtered_trades))

    def prev_page(self):
        self.current_page -= 1
        self.update_table()

    def next_page(self):
        self.current_page += 1
        self.update_table()

    def show_context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        item = self.table.item(idx.row(), 2)
        menu = QMenu(self)
        copy_act = QAction("Copiar nombre", self)
        copy_act.triggered.connect(lambda: QGuiApplication.clipboard().setText(item.text()))
        menu.addAction(copy_act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def on_double_click(self, item):
        tid = self.table.item(item.row(), 1).data(Qt.UserRole)
        name = self.table.item(item.row(), 2).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: None)

# --- Main View ---

class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.all_orders = []
        self.image_loader = AsyncImageLoader()
        self.spinner_chars = ["|", "/", "-", "\\"]
        self.spinner_idx = 0
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._update_spinner)
        self.setup_ui()
        self.load_layouts()
        AuthManager.instance().authenticated.connect(self.do_sync)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MIS PEDIDOS")
        title_lbl.setStyleSheet("color:#f1f5f9; font-size:18px; font-weight:900;")
        
        status_h = QHBoxLayout()
        self.lbl_spinner = QLabel("")
        self.lbl_spinner.setFixedWidth(15)
        self.lbl_status = QLabel("● ESPERANDO SINCRONIZACIÓN")
        status_h.addWidget(self.lbl_spinner)
        status_h.addWidget(self.lbl_status)
        status_h.addStretch()
        
        title_v.addWidget(title_lbl)
        title_v.addLayout(status_h)
        
        self.btn_repopulate = QPushButton("ACTUALIZAR")
        self.btn_inventory = QPushButton("INVENTARIO")
        self.btn_trades = QPushButton("TRADE PROFITS")
        self.btn_repopulate.clicked.connect(self.do_sync)
        self.btn_inventory.clicked.connect(self.do_inventory)
        self.btn_trades.clicked.connect(self.open_trades)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_inventory)
        header.addWidget(self.btn_trades)
        header.addWidget(self.btn_repopulate)
        self.main_layout.addLayout(header)
        
        self.table_sell = self.create_table(False)
        self.table_buy = self.create_table(True)
        self.main_layout.addWidget(QLabel("ÓRDENES DE VENTA"))
        self.main_layout.addWidget(self.table_sell, 1)
        self.main_layout.addWidget(QLabel("ÓRDENES DE COMPRA"))
        self.main_layout.addWidget(self.table_buy, 1)
        
        self.table_sell.horizontalHeader().sectionResized.connect(lambda i, o, n: self.sync_cols(self.table_sell, self.table_buy, i, n))
        self.table_buy.horizontalHeader().sectionResized.connect(lambda i, o, n: self.sync_cols(self.table_buy, self.table_sell, i, n))
        self.table_sell.horizontalHeader().sectionMoved.connect(lambda i, oi, ni: self.sync_order(self.table_sell, self.table_buy, i, ni))
        self.table_buy.horizontalHeader().sectionMoved.connect(lambda i, oi, ni: self.sync_order(self.table_buy, self.table_sell, i, ni))

    def create_table(self, is_buy):
        t = QTableWidget(0, 12)
        t.setHorizontalHeaderLabels(["", "ÍTEM", "TIPO", "PRECIO", "PROMEDIO", "MEJOR", "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.horizontalHeader().setSectionsMovable(True)
        t.setSortingEnabled(True)
        return t

    def sync_cols(self, src, dst, idx, size):
        if src.signalsBlocked():
            return
        dst.blockSignals(True)
        dst.setColumnWidth(idx, size)
        dst.blockSignals(False)
        self.save_layouts()

    def sync_order(self, src, dst, old_idx, new_idx):
        if src.signalsBlocked():
            return
        dst.blockSignals(True)
        dst.horizontalHeader().moveSection(old_idx, new_idx)
        dst.blockSignals(False)
        self.save_layouts()

    def save_layouts(self):
        cfg = {
            "w": [self.table_sell.columnWidth(i) for i in range(12)],
            "v": [self.table_sell.horizontalHeader().visualIndex(i) for i in range(12)]
        }
        save_ui_config("my_orders", cfg)

    def load_layouts(self):
        cfg = load_ui_config("my_orders")
        w = cfg.get("w")
        v = cfg.get("v")
        if w: 
            for i, val in enumerate(w):
                self.table_sell.setColumnWidth(i, val)
                self.table_buy.setColumnWidth(i, val)
        if v:
            self.table_sell.blockSignals(True)
            self.table_buy.blockSignals(True)
            for visual_idx, logical_idx in enumerate(v):
                self.table_sell.horizontalHeader().moveSection(self.table_sell.horizontalHeader().visualIndex(logical_idx), visual_idx)
                self.table_buy.horizontalHeader().moveSection(self.table_buy.horizontalHeader().visualIndex(logical_idx), visual_idx)
            self.table_sell.blockSignals(False)
            self.table_buy.blockSignals(False)

    def do_sync(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if not t:
            return
        self.worker = SyncWorker(auth.char_id, t)
        self.worker.finished_data.connect(self.on_data)
        self.worker.start()
        self.spinner_timer.start(100)
        self.lbl_status.setText("SINCRONIZANDO...")
        self.btn_repopulate.setEnabled(False)

    def on_data(self, data):
        self.all_orders = data
        self.fill_table(self.table_sell, [o for o in data if not o.is_buy_order])
        self.fill_table(self.table_buy, [o for o in data if o.is_buy_order])
        self.spinner_timer.stop()
        self.lbl_spinner.setText("")
        self.lbl_status.setText("LISTO")
        self.btn_repopulate.setEnabled(True)

    def fill_table(self, t, data):
        t.setSortingEnabled(False)
        t.setRowCount(len(data))
        for r, o in enumerate(data):
            a = o.analysis
            i_ico = QTableWidgetItem()
            self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px, it=i_ico: it.setIcon(QIcon(px)))
            t.setItem(r, 0, i_ico)
            t.setItem(r, 1, QTableWidgetItem(o.item_name))
            t.setItem(r, 2, QTableWidgetItem("BUY" if o.is_buy_order else "SELL"))
            t.setItem(r, 3, NumericTableWidgetItem(format_isk(o.price), o.price))
            t.setItem(r, 11, SemanticTableWidgetItem(a.state.upper()))
        t.setSortingEnabled(True)

    def do_inventory(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if not t:
            return
        self.inv_worker = InventoryWorker(auth.char_id, t)
        self.inv_worker.finished_data.connect(lambda d: InventoryAnalysisDialog(d, "Loc", self.image_loader, self).exec())
        self.inv_worker.start()

    def open_trades(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if t:
            TradeProfitsDialog(auth.char_id, t, self.image_loader, self).exec()

    def _update_spinner(self):
        self.spinner_idx = (self.spinner_idx + 1) % 4
        self.lbl_spinner.setText(self.spinner_chars[self.spinner_idx])

class SyncWorker(QThread):
    finished_data = Signal(list)
    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token
    def run(self):
        client = ESIClient()
        orders = client.character_orders(self.char_id, self.token)
        CostBasisService.instance().refresh_from_esi(self.char_id, self.token)
        all_mo = client.market_orders(10000002)
        analyzed = analyze_character_orders(orders, all_mo, {}, load_market_filters(), char_id=self.char_id, token=self.token)
        self.finished_data.emit(analyzed)

class InventoryWorker(QThread):
    finished_data = Signal(list)
    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token
    def run(self):
        client = ESIClient()
        assets = client.character_assets(self.char_id, self.token)
        all_mo = client.market_orders(10000002)
        analyzed = analyze_inventory(assets, all_mo, {}, load_market_filters(), char_id=self.char_id, token=self.token)
        self.finished_data.emit(analyzed)

class InventoryAnalysisDialog(QDialog):
    def __init__(self, items, loc_name, image_loader, parent=None):
        super().__init__(parent)
        self.items = items
        self.loc_name = loc_name
        self.image_loader = image_loader
        self.setWindowTitle("INVENTARIO")
        self.setMinimumSize(1150, 750)
        self.setup_ui()
        self.load_layout()
    def setup_ui(self):
        l = QVBoxLayout(self)
        self.table = QTableWidget(len(self.items), 9)
        self.table.setHorizontalHeaderLabels(["", "ÍTEM", "CANT", "PROM", "NETO", "PROFIT", "%", "REC", "MOTIVO"])
        self.table.setSortingEnabled(False)
        for r, it in enumerate(self.items):
            avg = getattr(it, "_avg_buy", 0.0)
            profit = getattr(it, "_net_profit_total", 0.0)
            roi = (profit / (avg * it.quantity)) if avg > 0 else -1e18
            self.table.setItem(r, 8, SemanticTableWidgetItem(it.analysis.reason, roi=roi))
        self.table.setSortingEnabled(True)
        l.addWidget(self.table)
    def save_layout(self):
        save_ui_config("inventory", {"w": [self.table.columnWidth(i) for i in range(9)]})
    def load_layout(self): 
        cfg = load_ui_config("inventory")
        w = cfg.get("w")
        if w: 
            for i, val in enumerate(w):
                self.table.setColumnWidth(i, val)
