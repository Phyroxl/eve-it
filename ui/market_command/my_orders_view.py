import logging # VERSION: 1.1.21-STABLE (Full Restore & Feature Complete)
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
    """Item de tabla que ordena numéricamente pero muestra texto formateado."""
    def __init__(self, text, value):
        super().__init__(str(text))
        self.sort_value = float(value) if value is not None else -1e18

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)

class SemanticTableWidgetItem(QTableWidgetItem):
    """Item de tabla que ordena por prioridad semántica o ROI."""
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

class SyncWorker(QThread):
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
            self.status_update.emit("CONECTANDO CON ESI...", 10)
            
            # Sincronizar dependencias
            self.status_update.emit("SINCRONIZANDO TAXES...", 20)
            TaxService.instance().refresh_from_esi(self.char_id, self.token)
            
            self.status_update.emit("DESCARGANDO ÓRDENES...", 40)
            orders = client.character_orders(self.char_id, self.token)
            if not orders:
                self.finished_data.emit([])
                return
            
            self.status_update.emit("CARGANDO PRECIOS DE MERCADO...", 60)
            type_ids = list(set(o['type_id'] for o in orders))
            client.cache.cache.pop("market_orders_10000002", None)
            all_market_orders = client.market_orders(10000002)
            
            self.status_update.emit("CALCULANDO WAC...", 80)
            CostBasisService.instance().refresh_from_esi(self.char_id, self.token)
            
            self.status_update.emit("ANALIZANDO ESTADOS...", 95)
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            analyzed = analyze_character_orders(
                orders, all_market_orders, item_names, load_market_filters(), 
                char_id=self.char_id, token=self.token
            )
            self.status_update.emit("SINCRONIZACIÓN EXITOSA", 100)
            self.finished_data.emit(analyzed)
        except Exception as e:
            self.error.emit(str(e))

class InventoryWorker(QThread):
    finished_data = Signal(list)
    location_info = Signal(str)
    status_update = Signal(str, int)
    error = Signal(str)

    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token

    def run(self):
        try:
            client = ESIClient()
            self.status_update.emit("LOCALIZANDO...", 10)
            loc_res = client.character_location(self.char_id, self.token)
            curr_loc_id = None
            loc_name = "TODO EL INVENTARIO"
            
            if loc_res and loc_res != "missing_scope":
                curr_loc_id = loc_res.get('station_id') or loc_res.get('structure_id')
                if curr_loc_id:
                    names = client.universe_names([curr_loc_id])
                    if names:
                        loc_name = names[0]['name']
            
            self.location_info.emit(loc_name)
            self.status_update.emit("DESCARGANDO ACTIVOS...", 40)
            assets = client.character_assets(self.char_id, self.token)
            if assets == "missing_scope":
                self.error.emit("missing_scope")
                return
            if not assets:
                self.finished_data.emit([])
                return
            
            # Filtrar activos no tangibles (slots, etc)
            filtered = [a for a in assets if 'slot' not in a.get('location_flag', '').lower()]
            if curr_loc_id:
                filtered = [a for a in assets if a.get('location_id') == curr_loc_id]
            
            if not filtered:
                self.finished_data.emit([])
                return

            self.status_update.emit("BUSCANDO PRECIOS...", 70)
            type_ids = list(set(a['type_id'] for a in filtered))
            all_mo = client.market_orders(10000002)
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            self.status_update.emit("CALCULANDO WAC...", 90)
            CostBasisService.instance().refresh_from_esi(self.char_id, self.token)
                
            analyzed = analyze_inventory(
                filtered, all_mo, item_names, load_market_filters(), 
                char_id=self.char_id, token=self.token
            )
            self.status_update.emit("LISTO", 100)
            self.finished_data.emit(analyzed)
        except Exception as e:
            self.error.emit(str(e))

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
            
            self.status_update.emit("CALCULANDO RENTABILIDAD HISTÓRICA...", 50)
            sorted_tx = sorted(txs, key=lambda x: x['date'])
            trades = []
            stock_map = {} # type_id -> {qty, cost}
            
            type_ids = list(set(t['type_id'] for t in sorted_tx))
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            tx_service = TaxService.instance()
            tx_service.refresh_from_esi(self.char_id, self.token)
            taxes = tx_service.get_taxes(self.char_id)
            sales_tax_pct = taxes.sales_tax_pct
            
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
                    # Compra: Aplicar fee y añadir al stock
                    total_buy = qty * price * (1.0 + fee_pct/100.0)
                    curr['qty'] += qty
                    curr['cost'] += total_buy
                else:
                    # Venta: Calcular beneficio contra WAC
                    if curr['qty'] > 0:
                        wac_unit = curr['cost'] / curr['qty']
                        cost_matched = qty * wac_unit
                        
                        gross_sell = qty * price
                        fees_amt = gross_sell * (fee_pct/100.0 + sales_tax_pct/100.0)
                        net_sell = gross_sell - fees_amt
                        
                        profit = net_sell - cost_matched
                        margin = (profit / cost_matched * 100) if cost_matched > 0 else 0
                        
                        trades.append({
                            'date': t['date'],
                            'type_id': tid,
                            'name': item_names.get(tid, f"Item {tid}"),
                            'qty': qty,
                            'buy_unit': wac_unit,
                            'sell_unit': price,
                            'buy_total': cost_matched,
                            'sell_total': gross_sell,
                            'fees': fees_amt,
                            'margin': margin,
                            'profit': profit
                        })
                        
                        curr['qty'] -= qty
                        curr['cost'] -= cost_matched
                        if curr['qty'] < 0:
                            curr['qty'] = 0
                            curr['cost'] = 0.0
            
            self.status_update.emit("FINALIZADO", 100)
            self.finished_data.emit(list(reversed(trades)))
        except Exception as e:
            self.error.emit(str(e))

# --- Diálogos ---

class InventoryAnalysisDialog(QDialog):
    def __init__(self, items, loc_name, image_loader, parent=None):
        super().__init__(parent)
        self.items = items
        self.loc_name = loc_name
        self.image_loader = image_loader
        self.setWindowTitle("INVENTARIO - VALOR DE ACTIVOS")
        self.setMinimumSize(1150, 750)
        self.setStyleSheet("background-color: #000000;")
        self.setup_ui()
        self.load_layout()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header = QFrame()
        header.setFixedHeight(85)
        header.setStyleSheet("background-color: #0f172a; border-radius: 8px; border: 1px solid #1e293b;")
        hl = QHBoxLayout(header)
        title_v = QVBoxLayout()
        title = QLabel("INVENTARIO LOCAL")
        title.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900;")
        loc_lbl = QLabel(f"UBICACIÓN: {self.loc_name.upper()}")
        loc_lbl.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800;")
        title_v.addWidget(title)
        title_v.addWidget(loc_lbl)
        hl.addLayout(title_v)
        hl.addStretch()
        
        total_val = sum(item.analysis.est_total_value for item in self.items)
        val_lbl = QLabel(format_isk(total_val))
        val_lbl.setStyleSheet("color: #10b981; font-size: 22px; font-weight: 900;")
        hl.addWidget(val_lbl)
        layout.addWidget(header)

        # Tabla
        self.table = QTableWidget(len(self.items), 9)
        self.table.setHorizontalHeaderLabels(["", "ÍTEM", "CANTIDAD", "MI PROMEDIO", "P. UNIT NETO", "PROFIT DE VENTA", "VALOR %", "RECOMENDACIÓN", "MOTIVO"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("QTableWidget { background: #000000; color: #f1f5f9; border: none; font-size: 11px; } QHeaderView::section { background: #000000; color: #64748b; font-weight: 900; border: none; border-bottom: 1px solid #1e293b; padding: 10px; } QTableWidget::item { border-bottom: 1px solid #0f172a; padding: 8px; }")
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(32, 32))
        self.table.setSortingEnabled(False)
        
        for row, item in enumerate(self.items):
            a = item.analysis
            avg = getattr(item, "_avg_buy", 0.0)
            profit_t = getattr(item, "_net_profit_total", 0.0)
            roi = (profit_t / (avg * item.quantity)) if (avg > 0 and item.quantity > 0) else -1e18
            
            i_icon = QTableWidgetItem()
            i_icon.setData(Qt.UserRole, item.type_id)
            self.image_loader.load(ItemMetadataHelper.get_icon_url(item.type_id), lambda px, it=i_icon: it.setIcon(QIcon(px)))
            
            i_name = QTableWidgetItem(item.item_name)
            i_qty = NumericTableWidgetItem(f"{item.quantity:,}", item.quantity)
            i_avg = NumericTableWidgetItem(format_isk(avg) if avg > 0 else "Sin registros", avg)
            i_price = NumericTableWidgetItem(format_isk(a.est_net_sell_unit), a.est_net_sell_unit)
            
            i_profit = NumericTableWidgetItem(format_isk(profit_t) if avg > 0 else "Sin registros", profit_t if avg > 0 else -1e18)
            if avg > 0:
                i_profit.setForeground(QColor("#10b981" if profit_t >= 0 else "#ef4444"))
            
            pct = (a.est_total_value / total_val * 100) if total_val > 0 else 0
            i_pct = NumericTableWidgetItem(f"{pct:.1f}%", pct)
            
            i_rec = SemanticTableWidgetItem(a.recommendation.upper())
            i_reason = SemanticTableWidgetItem(a.reason, roi=roi)
            r_txt = a.reason.lower()
            if "spread" in r_txt:
                i_reason.setForeground(QColor("#87E101"))
            elif "profit" in r_txt or roi > 0:
                i_reason.setForeground(QColor("#10b981"))
            elif "pérdida" in r_txt:
                i_reason.setForeground(QColor("#ef4444"))
            else:
                i_reason.setForeground(QColor("#64748b"))
            
            self.table.setItem(row, 0, i_icon)
            self.table.setItem(row, 1, i_name)
            self.table.setItem(row, 2, i_qty)
            self.table.setItem(row, 3, i_avg)
            self.table.setItem(row, 4, i_price)
            self.table.setItem(row, 5, i_profit)
            self.table.setItem(row, 6, i_pct)
            self.table.setItem(row, 7, i_rec)
            self.table.setItem(row, 8, i_reason)
            
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.table)
        
        self.table.horizontalHeader().sectionResized.connect(self.save_layout)

    def on_double_click(self, item):
        tid = self.table.item(item.row(), 0).data(Qt.UserRole)
        name = self.table.item(item.row(), 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: None)

    def save_layout(self):
        cfg = {"widths": [self.table.columnWidth(i) for i in range(self.table.columnCount())]}
        save_ui_config("inventory", cfg)

    def load_layout(self):
        cfg = load_ui_config("inventory")
        widths = cfg.get("widths")
        if widths:
            for i, w in enumerate(widths):
                if i < self.table.columnCount():
                    self.table.setColumnWidth(i, w)

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
        self.setWindowTitle("HISTORIAL DE TRADE PROFITS")
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
        self.txt_filter.setPlaceholderText("Filtrar por item...")
        self.txt_filter.setFixedWidth(250)
        self.txt_filter.setStyleSheet("background:#1e293b; color:white; padding:8px; border:1px solid #334155;")
        self.txt_filter.textChanged.connect(self.apply_filters)
        
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Todos los resultados", "Solo Ganancias", "Solo Pérdidas"])
        self.cmb_mode.setStyleSheet("background:#1e293b; color:white; padding:8px;")
        self.cmb_mode.currentIndexChanged.connect(self.apply_filters)
        
        fl.addWidget(QLabel("FILTRAR:")); fl.addWidget(self.txt_filter)
        fl.addSpacing(20); fl.addWidget(QLabel("MODO:")); fl.addWidget(self.cmb_mode)
        fl.addStretch()
        layout.addWidget(f_frame)
        
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["FECHA", "", "ÍTEM", "UNIDADES", "P. COMPRA", "P. VENTA", "TOTAL COMPRA", "TOTAL VENTA", "FEES + TAX", "MARGEN %", "PROFIT NETO"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("QTableWidget { background: #000000; color: #f1f5f9; border: none; font-size: 11px; } QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; padding: 10px; }")
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(24, 24))
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.table)
        
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("ANTERIOR")
        self.btn_next = QPushButton("SIGUIENTE")
        self.lbl_page = QLabel("Página 1")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        nav.addWidget(self.btn_prev); nav.addStretch(); nav.addWidget(self.lbl_page); nav.addStretch(); nav.addWidget(self.btn_next)
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
            dt = t['date'].replace('T', ' ').replace('Z', '')
            self.table.setItem(r, 0, QTableWidgetItem(dt))
            
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
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(12)
        
        # Header
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MIS PEDIDOS")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        
        status_h = QHBoxLayout()
        self.lbl_spinner = QLabel("")
        self.lbl_spinner.setFixedWidth(15)
        self.lbl_spinner.setStyleSheet("color: #3b82f6; font-weight: 900;")
        self.lbl_status = QLabel("● ESPERANDO SINCRONIZACIÓN")
        self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: 800;")
        status_h.addWidget(self.lbl_spinner)
        status_h.addWidget(self.lbl_status)
        status_h.addStretch()
        
        title_v.addWidget(title_lbl)
        title_v.addLayout(status_h)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #1e293b; border: none; } QProgressBar::chunk { background: #3b82f6; }")
        self.progress_bar.hide()
        title_v.addWidget(self.progress_bar)
        
        self.btn_repopulate = QPushButton("ACTUALIZAR")
        self.btn_inventory = QPushButton("INVENTARIO")
        self.btn_trades = QPushButton("TRADE PROFITS")
        
        for b in [self.btn_repopulate, self.btn_inventory, self.btn_trades]:
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(35)
            b.setStyleSheet("QPushButton { background-color: #1e293b; color: white; font-size: 10px; font-weight: 900; border: 1px solid #334155; border-radius: 4px; padding: 0 15px; } QPushButton:hover { background-color: #334155; }")
        
        self.btn_inventory.setStyleSheet(self.btn_inventory.styleSheet().replace("#1e293b", "#10b981"))
        self.btn_repopulate.clicked.connect(self.do_sync)
        self.btn_inventory.clicked.connect(self.do_inventory)
        self.btn_trades.clicked.connect(self.open_trades)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_inventory)
        header.addWidget(self.btn_trades)
        header.addWidget(self.btn_repopulate)
        self.main_layout.addLayout(header)

        # Tablas
        self.lbl_sell = QLabel("ÓRDENES DE VENTA (0)")
        self.lbl_sell.setStyleSheet("color:#ef4444; font-weight:900; font-size:10px;")
        self.main_layout.addWidget(self.lbl_sell)
        
        self.table_sell = self.create_table(False)
        self.main_layout.addWidget(self.table_sell, 1)
        
        # Taxes bar
        self.setup_taxes_bar()
        
        self.lbl_buy = QLabel("ÓRDENES DE COMPRA (0)")
        self.lbl_buy.setStyleSheet("color:#3b82f6; font-weight:900; font-size:10px;")
        self.main_layout.addWidget(self.lbl_buy)
        
        self.table_buy = self.create_table(True)
        self.main_layout.addWidget(self.table_buy, 1)

        # Detail Panel
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(130)
        self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_layout()
        self.main_layout.addWidget(self.detail_panel)
        
        # Sincronización
        self.table_sell.horizontalHeader().sectionResized.connect(lambda i, o, n: self.sync_cols(self.table_sell, self.table_buy, i, n))
        self.table_buy.horizontalHeader().sectionResized.connect(lambda i, o, n: self.sync_cols(self.table_buy, self.table_sell, i, n))
        self.table_sell.horizontalHeader().sectionMoved.connect(lambda i, oi, ni: self.sync_order(self.table_sell, self.table_buy, i, ni))
        self.table_buy.horizontalHeader().sectionMoved.connect(lambda i, oi, ni: self.sync_order(self.table_buy, self.table_sell, i, ni))

    def setup_taxes_bar(self):
        self.taxes_bar = QFrame()
        self.taxes_bar.setFixedHeight(30)
        self.taxes_bar.setStyleSheet("background-color: #0f172a; border-radius: 15px; border: 1px solid #1e293b;")
        l = QHBoxLayout(self.taxes_bar)
        l.setContentsMargins(15, 0, 15, 0)
        self.lbl_sales_tax = QLabel("SALES TAX: ---")
        self.lbl_broker_fee = QLabel("BROKER FEE: ---")
        self.lbl_tax_source = QLabel("FUENTE: ---")
        for lbl in [self.lbl_sales_tax, self.lbl_broker_fee, self.lbl_tax_source]:
            lbl.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800;")
        l.addWidget(self.lbl_sales_tax)
        l.addSpacing(20)
        l.addWidget(self.lbl_broker_fee)
        l.addStretch()
        l.addWidget(self.lbl_tax_source)
        self.main_layout.addWidget(self.taxes_bar)

    def create_table(self, is_buy):
        t = QTableWidget(0, 12)
        t.setHorizontalHeaderLabels(["", "ÍTEM", "TIPO", "PRECIO", "PROMEDIO", "MEJOR", "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setStyleSheet("QTableWidget { background: #000000; color: white; border: 1px solid #1e293b; font-size: 10px; } QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; }")
        t.horizontalHeader().setSectionsMovable(True)
        t.setIconSize(QSize(24, 24))
        t.setSortingEnabled(True)
        t.itemSelectionChanged.connect(self.on_selection_changed)
        t.itemDoubleClicked.connect(lambda i: self.on_double_click_item(i, t))
        return t

    def setup_detail_layout(self):
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(15, 12, 15, 12)
        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setFixedSize(64, 64)
        dl.addWidget(self.lbl_det_icon)
        
        info_v = QVBoxLayout()
        self.lbl_det_item = QLabel("SELECCIONA UNA ORDEN")
        self.lbl_det_item.setStyleSheet("color:#f1f5f9; font-size:14px; font-weight:900;")
        self.lbl_det_type = QLabel("---")
        self.lbl_det_cost_msg = QLabel("---")
        info_v.addWidget(self.lbl_det_item)
        info_v.addWidget(self.lbl_det_type)
        info_v.addWidget(self.lbl_det_cost_msg)
        info_v.addStretch()
        dl.addLayout(info_v, 2)
        
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        def add_m(l, r, c):
            v = QVBoxLayout()
            v.addWidget(QLabel(l, styleSheet="color:#475569; font-size:9px; font-weight:900;"))
            val = QLabel("---", styleSheet="color:#f1f5f9; font-size:11px; font-weight:900;")
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

    def sync_cols(self, src, dst, idx, size):
        if src.signalsBlocked(): return
        dst.blockSignals(True)
        dst.setColumnWidth(idx, size)
        dst.blockSignals(False)
        self.save_layouts()

    def sync_order(self, src, dst, old_idx, new_idx):
        if src.signalsBlocked(): return
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
                if i < 12:
                    self.table_sell.setColumnWidth(i, val)
                    self.table_buy.setColumnWidth(i, val)
        if v:
            self.table_sell.blockSignals(True)
            self.table_buy.blockSignals(True)
            for visual_idx, logical_idx in enumerate(v):
                if visual_idx < 12 and logical_idx < 12:
                    self.table_sell.horizontalHeader().moveSection(self.table_sell.horizontalHeader().visualIndex(logical_idx), visual_idx)
                    self.table_buy.horizontalHeader().moveSection(self.table_buy.horizontalHeader().visualIndex(logical_idx), visual_idx)
            self.table_sell.blockSignals(False)
            self.table_buy.blockSignals(False)

    def do_sync(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if not t: return
        self._start_sync_ui()
        self.worker = SyncWorker(auth.char_id, t)
        self.worker.status_update.connect(lambda m, v: (self.lbl_status.setText(m), self.progress_bar.setValue(v)))
        self.worker.finished_data.connect(self.on_data)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_data(self, data):
        self.all_orders = data
        self.update_taxes_info()
        sells = [o for o in data if not o.is_buy_order]
        buys = [o for o in data if o.is_buy_order]
        self.lbl_sell.setText(f"ÓRDENES DE VENTA ({len(sells)})")
        self.lbl_buy.setText(f"ÓRDENES DE COMPRA ({len(buys)})")
        self.fill_table(self.table_sell, sells)
        self.fill_table(self.table_buy, buys)
        self._stop_sync_ui()

    def fill_table(self, t, data):
        t.setSortingEnabled(False)
        t.setRowCount(len(data))
        for r, o in enumerate(data):
            a = o.analysis
            cost = CostBasisService.instance().get_cost_basis(o.type_id)
            avg = cost.average_buy_price if cost else 0.0
            
            i_ico = QTableWidgetItem()
            i_ico.setData(Qt.UserRole, o.type_id)
            i_ico.setData(Qt.UserRole + 1, o.order_id)
            self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px, it=i_ico: it.setIcon(QIcon(px)))
            
            i_name = QTableWidgetItem(o.item_name)
            i_type = QTableWidgetItem("BUY" if o.is_buy_order else "SELL")
            i_type.setForeground(QColor("#3b82f6" if o.is_buy_order else "#ef4444"))
            
            i_price = NumericTableWidgetItem(format_isk(o.price), o.price)
            i_avg = NumericTableWidgetItem(format_isk(avg) if avg > 0 else "---", avg)
            
            ref_v = a.best_sell if o.is_buy_order else a.best_buy
            i_ref = NumericTableWidgetItem(format_isk(ref_v) if ref_v > 0 else "---", ref_v)
            
            i_tot = NumericTableWidgetItem(str(o.volume_total), o.volume_total)
            i_rem = NumericTableWidgetItem(str(o.volume_remain), o.volume_remain)
            i_spr = NumericTableWidgetItem(f"{a.spread_pct:.1f}%", a.spread_pct)
            
            i_mar = NumericTableWidgetItem(f"{a.margin_pct:.1f}%", a.margin_pct)
            if a.margin_pct > 15: i_mar.setForeground(QColor("#10b981"))
            elif a.margin_pct < 0: i_mar.setForeground(QColor("#ef4444"))
            
            i_prof = NumericTableWidgetItem(format_isk(a.net_profit_total), a.net_profit_total)
            if a.net_profit_total > 0: i_prof.setForeground(QColor("#10b981"))
            elif a.net_profit_total < 0: i_prof.setForeground(QColor("#ef4444"))
            
            i_state = SemanticTableWidgetItem(a.state.upper())
            s_low = a.state.lower()
            if any(x in s_low for x in ["liderando", "competitiva", "sana", "rentable"]):
                i_state.setForeground(QColor("#3b82f6" if o.is_buy_order else "#10b981"))
            elif "superada" in s_low or "ajustado" in s_low:
                i_state.setForeground(QColor("#f59e0b"))
            elif any(x in s_low for x in ["pérdida", "no rentable", "fuera"]):
                i_state.setForeground(QColor("#ef4444"))
            
            items = [i_ico, i_name, i_type, i_price, i_avg, i_ref, i_tot, i_rem, i_spr, i_mar, i_prof, i_state]
            for i, it in enumerate(items):
                if i in [3, 4, 5, 10]: it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif i in [2, 6, 7, 8, 9, 11]: it.setTextAlignment(Qt.AlignCenter)
                t.setItem(r, i, it)
                
        t.setSortingEnabled(True)

    def on_selection_changed(self):
        s = self.sender()
        tar = self.table_buy if s == self.table_sell else self.table_sell
        tar.blockSignals(True)
        tar.clearSelection()
        tar.blockSignals(False)
        si = s.selectedItems()
        if not si: return
        oid = s.item(si[0].row(), 0).data(Qt.UserRole + 1)
        o = next((ord for ord in self.all_orders if ord.order_id == oid), None)
        if o: self.update_det(o)

    def update_det(self, o):
        self.lbl_det_item.setText(o.item_name.upper())
        self.lbl_det_type.setText("COMPRA" if o.is_buy_order else "VENTA")
        self.lbl_det_type.setStyleSheet("color:#3b82f6;" if o.is_buy_order else "color:#ef4444;")
        self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px: self.lbl_det_icon.setPixmap(px.scaled(64, 64, Qt.KeepAspectRatio)))
        
        a = o.analysis
        cost = CostBasisService.instance().get_cost_basis(o.type_id)
        avg = cost.average_buy_price if cost else 0.0
        
        self.lbl_det_cost_msg.setText(f"Info: {a.state} | Order ID: {o.order_id}")
        self.det_price.setText(format_isk(o.price))
        self.det_avg.setText(format_isk(avg) if avg > 0 else "---")
        self.det_best_buy.setText(format_isk(a.best_buy))
        self.det_best_sell.setText(format_isk(a.best_sell))
        self.det_margin.setText(f"{a.margin_pct:.1f}%")
        self.det_profit_u.setText(format_isk(a.net_profit_per_unit))
        self.det_profit_t.setText(format_isk(a.net_profit_total))
        self.det_state.setText(a.state.upper())

    def on_double_click_item(self, item, t):
        tid = t.item(item.row(), 0).data(Qt.UserRole)
        name = t.item(item.row(), 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: self.lbl_status.setText(m))

    def update_taxes_info(self):
        auth = AuthManager.instance()
        tx = TaxService.instance().get_taxes(auth.char_id)
        self.lbl_sales_tax.setText(f"SALES TAX: {tx.sales_tax_pct:.2f}%")
        self.lbl_broker_fee.setText(f"BROKER FEE: {tx.broker_fee_pct:.2f}% (BASE)")
        self.lbl_tax_source.setText(f"FUENTE: {'REAL' if tx.status=='ready' else 'FALLBACK'}")

    def do_inventory(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if not t: return
        self._start_sync_ui()
        self.inv_worker = InventoryWorker(auth.char_id, t)
        self.inv_worker.status_update.connect(lambda m, v: (self.lbl_status.setText(m), self.progress_bar.setValue(v)))
        def on_done(data):
            self._stop_sync_ui()
            if data:
                InventoryAnalysisDialog(data, "Loc", self.image_loader, self).exec()
            else:
                QMessageBox.information(self, "Vacío", "No hay items en esta ubicación.")
        self.inv_worker.finished_data.connect(on_done)
        self.inv_worker.start()

    def open_trades(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if t:
            TradeProfitsDialog(auth.char_id, t, self.image_loader, self).exec()

    def _update_spinner(self):
        self.spinner_idx = (self.spinner_idx + 1) % 4
        self.lbl_spinner.setText(self.spinner_chars[self.spinner_idx])

    def _start_sync_ui(self):
        self.spinner_timer.start(100)
        self.lbl_status.setText("SINCRONIZANDO...")
        self.lbl_status.setStyleSheet("color: #3b82f6;")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.btn_repopulate.setEnabled(False)
        self.btn_inventory.setEnabled(False)
        self.btn_trades.setEnabled(False)

    def _stop_sync_ui(self):
        self.spinner_timer.stop()
        self.lbl_spinner.setText("")
        self.lbl_status.setText("LISTO")
        self.lbl_status.setStyleSheet("color: #10b981;")
        self.progress_bar.hide()
        self.btn_repopulate.setEnabled(True)
        self.btn_inventory.setEnabled(True)
        self.btn_trades.setEnabled(True)

    def on_error(self, err):
        self._stop_sync_ui()
        self.lbl_status.setText(f"ERROR: {err[:40]}")
        self.lbl_status.setStyleSheet("color: #ef4444;")
