import logging # VERSION: 1.1.12-SYNCPRO (Profit Inventory, ESI Sync Progress, Spinner)
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout, QDialog, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
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
    status_update = Signal(str, int) # (mensaje, progreso_0_100)
    error = Signal(str)

    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token

    def run(self):
        try:
            client = ESIClient()
            self.status_update.emit("CONECTANDO CON ESI...", 10)
            
            self.status_update.emit("DESCARGANDO ÓRDENES...", 20)
            orders = client.character_orders(self.char_id, self.token)
            if not orders:
                self.finished_data.emit([])
                return
            
            self.status_update.emit("APLICANDO TAXES Y STANDINGS...", 40)
            TaxService.instance().refresh_from_esi(self.char_id, self.token)
            
            self.status_update.emit("CARGANDO DATOS DE MERCADO...", 60)
            type_ids = list(set(o['type_id'] for o in orders))
            all_market_orders = client.market_orders(10000002)
            relevant_market_orders = [mo for mo in all_market_orders if mo['type_id'] in type_ids]
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            config = load_market_filters()
            
            self.status_update.emit("CALCULANDO WAC (MI PROMEDIO)...", 80)
            cost_service = CostBasisService.instance()
            if cost_service.has_wallet_scope():
                cost_service.refresh_from_esi(self.char_id, self.token)
            
            self.status_update.emit("FINALIZANDO ANÁLISIS...", 95)
            analyzed = analyze_character_orders(orders, relevant_market_orders, item_names, config, char_id=self.char_id, token=self.token)
            
            self.status_update.emit("SINCRONIZACIÓN COMPLETADA", 100)
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
            self.status_update.emit("LOCALIZANDO PERSONAJE...", 10)
            
            loc_res = client.character_location(self.char_id, self.token)
            curr_loc_id = None
            loc_name = "TODO EL INVENTARIO (FALLBACK)"
            
            if loc_res == "missing_scope":
                self.location_info.emit("missing_scope")
            elif loc_res:
                if loc_res.get('station_id'):
                    curr_loc_id = loc_res.get('station_id')
                elif loc_res.get('structure_id'):
                    curr_loc_id = loc_res.get('structure_id')
                
                if curr_loc_id:
                    names = client.universe_names([curr_loc_id])
                    if names: loc_name = names[0]['name']
                else:
                    ss_id = loc_res.get('solar_system_id')
                    names = client.universe_names([ss_id])
                    if names: loc_name = f"ESPACIO: {names[0]['name']}"
                    
                self.location_info.emit(loc_name)

            self.status_update.emit("DESCARGANDO ASSETS...", 40)
            assets = client.character_assets(self.char_id, self.token)
            if assets == "missing_scope":
                self.error.emit("missing_scope")
                return
            if not assets:
                self.finished_data.emit([])
                return
            
            if curr_loc_id:
                filtered_assets = [a for a in assets if a.get('location_id') == curr_loc_id]
            else:
                filtered_assets = [a for a in assets if 'slot' not in a.get('location_flag', '').lower()]

            if not filtered_assets:
                self.finished_data.emit([])
                return

            self.status_update.emit("OBTENIENDO PRECIOS JITA...", 70)
            type_ids = list(set(a['type_id'] for a in filtered_assets))
            all_market_orders = client.market_orders(10000002)
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            self.status_update.emit("CALCULANDO BENEFICIOS...", 90)
            config = load_market_filters()
            
            cost_service = CostBasisService.instance()
            if cost_service.has_wallet_scope():
                cost_service.refresh_from_esi(self.char_id, self.token)
                
            analyzed = analyze_inventory(filtered_assets, all_market_orders, item_names, config, char_id=self.char_id, token=self.token)
            self.status_update.emit("LISTO", 100)
            self.finished_data.emit(analyzed)
        except Exception as e:
            self.error.emit(str(e))

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

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        header = QFrame()
        header.setFixedHeight(85)
        header.setStyleSheet("background-color: #0f172a; border-radius: 8px; border: 1px solid #1e293b;")
        hl = QHBoxLayout(header)
        
        title_v = QVBoxLayout()
        title = QLabel("INVENTARIO LOCAL")
        title.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px; border:none;")
        
        loc_lbl = QLabel(f"UBICACIÓN: {self.loc_name.upper()}")
        loc_color = "#3b82f6" if "FALLBACK" not in self.loc_name else "#f59e0b"
        loc_lbl.setStyleSheet(f"color: {loc_color}; font-size: 10px; font-weight: 800; border:none;")
        
        title_v.addWidget(title)
        title_v.addWidget(loc_lbl)
        hl.addLayout(title_v)
        hl.addStretch()
        
        total_val = sum(item.analysis.est_total_value for item in self.items)
        val_v = QVBoxLayout()
        val_lbl = QLabel(format_isk(total_val))
        val_lbl.setStyleSheet("color: #10b981; font-size: 22px; font-weight: 900; border:none;")
        val_sub = QLabel("VALOR ESTIMADO NETO")
        val_sub.setToolTip("Suma del valor de mercado (Sell Jita) descontando impuestos.")
        val_sub.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; border:none;")
        val_sub.setAlignment(Qt.AlignRight)
        val_v.addWidget(val_lbl)
        val_v.addWidget(val_sub)
        hl.addLayout(val_v)
        layout.addWidget(header)

        self.table = QTableWidget(len(self.items), 9)
        self.table.setHorizontalHeaderLabels([
            "", "ÍTEM", "CANTIDAD", "MI PROMEDIO", "P. UNIT NETO", "PROFIT DE VENTA", "VALOR %", "RECOMENDACIÓN", "MOTIVO"
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(
            "QTableWidget { background: #000000; color: #f1f5f9; border: none; font-size: 11px; } "
            "QHeaderView::section { background: #000000; color: #64748b; font-weight: 900; border: none; border-bottom: 1px solid #1e293b; padding: 10px; } "
            "QTableWidget::item { border-bottom: 1px solid #0f172a; padding: 8px; } "
            "QTableWidget::item:selected { background: #0f172a; color: white; }"
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(32, 32))
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(7, 120)

        # Tooltip para Profit
        h = self.table.horizontalHeader()
        h.setSectionsClickable(True)
        self.table.horizontalHeaderItem(5).setToolTip("Beneficio real estimado: (Precio Neto Jita - Mi Promedio) * Cantidad")

        self.table.itemDoubleClicked.connect(self.on_double_click)

        sorted_items = sorted(self.items, key=lambda x: getattr(x, "_net_profit_total", 0.0), reverse=True)
        for row, item in enumerate(sorted_items):
            a = item.analysis
            avg_buy = getattr(item, "_avg_buy", 0.0)
            net_profit_total = getattr(item, "_net_profit_total", 0.0)
            
            i_icon = QTableWidgetItem()
            i_icon.setData(Qt.UserRole, item.type_id)
            url = ItemMetadataHelper.get_icon_url(item.type_id)
            self.image_loader.load(url, lambda px, it=i_icon: it.setIcon(QIcon(px)))
            
            i_name = QTableWidgetItem(item.item_name)
            i_qty = QTableWidgetItem(f"{item.quantity:,}")
            i_qty.setTextAlignment(Qt.AlignCenter)
            
            i_avg = QTableWidgetItem(format_isk(avg_buy) if avg_buy > 0 else "Sin registros")
            i_avg.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            i_avg.setForeground(QColor("#94a3b8") if avg_buy > 0 else QColor("#334155"))
            
            i_price = QTableWidgetItem(format_isk(a.est_net_sell_unit))
            i_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            if avg_buy > 0:
                i_profit = QTableWidgetItem(format_isk(net_profit_total))
                if net_profit_total > 0: i_profit.setForeground(QColor("#10b981"))
                elif net_profit_total < 0: i_profit.setForeground(QColor("#ef4444"))
                else: i_profit.setForeground(QColor("#94a3b8"))
            else:
                i_profit = QTableWidgetItem("Sin registros")
                i_profit.setForeground(QColor("#334155"))
            i_profit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            i_profit.setToolTip(f"Valor Total Estimado: {format_isk(a.est_total_value)}")
            
            pct = (a.est_total_value / total_val * 100) if total_val > 0 else 0
            i_pct = QTableWidgetItem(f"{pct:.1f}%")
            i_pct.setTextAlignment(Qt.AlignCenter)
            
            i_rec = QTableWidgetItem(a.recommendation.upper())
            i_rec.setTextAlignment(Qt.AlignCenter)
            if a.recommendation == "VENDER": i_rec.setForeground(QColor("#10b981"))
            elif a.recommendation == "REVISAR": i_rec.setForeground(QColor("#f59e0b"))
            else: i_rec.setForeground(QColor("#3b82f6"))
            
            i_reason = QTableWidgetItem(a.reason)
            r_txt = a.reason.lower()
            if any(x in r_txt for x in ["spread excesivo", "profit sólido", "margen positivo"]):
                i_reason.setForeground(QColor("#10b981"))
            elif "bajo" in r_txt:
                i_reason.setForeground(QColor("#f59e0b"))
            elif "pérdida" in r_txt or "bajo el coste" in r_txt:
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
            
        layout.addWidget(self.table)
        
        footer = QLabel("* PROFIT DE VENTA: Ganancia estimada restando el coste de compra e impuestos al valor de mercado actual.")
        footer.setStyleSheet("color: #334155; font-size: 9px; font-weight: 700;")
        layout.addWidget(footer)

    def on_double_click(self, item):
        row = item.row()
        tid = self.table.item(row, 0).data(Qt.UserRole)
        name = self.table.item(row, 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: None)

class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.inv_worker = None
        self.all_orders = []
        self.image_loader = AsyncImageLoader()
        self.inventory_cache = None
        self.inventory_loc_name = "DESCONOCIDA"
        self.inventory_status = "idle" 
        self.inventory_error_msg = ""
        self._syncing_headers = False
        
        # Spinner logic
        self.spinner_chars = ["|", "/", "-", "\\"]
        self.spinner_idx = 0
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._update_spinner)
        
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
        
        self.status_container = QHBoxLayout()
        self.lbl_spinner = QLabel("")
        self.lbl_spinner.setFixedWidth(15)
        self.lbl_spinner.setStyleSheet("color: #3b82f6; font-weight: 900;")
        
        self.lbl_status = QLabel("● SINCRONIZACIÓN REQUERIDA")
        self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: 800;")
        
        self.status_container.addWidget(self.lbl_spinner)
        self.status_container.addWidget(self.lbl_status)
        self.status_container.addStretch()
        
        title_v.addWidget(title_lbl)
        title_v.addLayout(self.status_container)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #1e293b; border: none; border-radius: 2px; } QProgressBar::chunk { background: #3b82f6; border-radius: 2px; }")
        self.progress_bar.hide()
        title_v.addWidget(self.progress_bar)

        self.btn_repopulate = QPushButton("ACTUALIZAR")
        self.btn_refresh = QPushButton("SINCRONIZAR ÓRDENES")
        self.btn_inventory = QPushButton("INVENTARIO")
        
        for b in [self.btn_repopulate, self.btn_refresh, self.btn_inventory]:
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(35)
            b.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #94a3b8; font-size: 10px; font-weight: 900; border: 1px solid #334155; border-radius: 4px; padding: 0 15px; }"
                "QPushButton:hover { background-color: #334155; color: #f1f5f9; }"
                "QPushButton:disabled { background-color: #0f172a; color: #475569; border: 1px solid #1e293b; }"
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

        # SECCIÓN ÓRDENES DE VENTA
        self.lbl_sell_count = QLabel("ÓRDENES DE VENTA (0)")
        self.lbl_sell_count.setStyleSheet("color:#ef4444; font-weight:900; font-size:10px;")
        self.main_layout.addWidget(self.lbl_sell_count)
        
        self.table_sell = self.create_table(is_buy=False)
        self.main_layout.addWidget(self.table_sell, 1)

        self.setup_taxes_bar()

        # SECCIÓN ÓRDENES DE COMPRA
        self.lbl_buy_count = QLabel("ÓRDENES DE COMPRA (0)")
        self.lbl_buy_count.setStyleSheet("color:#3b82f6; font-weight:900; font-size:10px;")
        self.main_layout.addWidget(self.lbl_buy_count)
        
        self.table_buy = self.create_table(is_buy=True)
        self.main_layout.addWidget(self.table_buy, 1)

        # PANEL DE DETALLE
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(130)
        self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_layout()
        self.main_layout.addWidget(self.detail_panel)

        self.table_sell.horizontalHeader().sectionResized.connect(lambda i, o, n: self._on_header_resized(self.table_sell, i, n))
        self.table_buy.horizontalHeader().sectionResized.connect(lambda i, o, n: self._on_header_resized(self.table_buy, i, n))
        self.table_sell.horizontalHeader().sectionMoved.connect(lambda i, o, n: self._on_header_moved(self.table_sell, i, o, n))
        self.table_buy.horizontalHeader().sectionMoved.connect(lambda i, o, n: self._on_header_moved(self.table_buy, i, o, n))

    def setup_taxes_bar(self):
        self.taxes_bar = QFrame()
        self.taxes_bar.setFixedHeight(30)
        self.taxes_bar.setStyleSheet("background-color: #0f172a; border-radius: 15px; border: 1px solid #1e293b;")
        layout = QHBoxLayout(self.taxes_bar)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.lbl_sales_tax = QLabel("SALES TAX: ---")
        self.lbl_broker_fee = QLabel("BROKER FEE: ---")
        self.lbl_tax_source = QLabel("FUENTE: ---")
        
        for lbl in [self.lbl_sales_tax, self.lbl_broker_fee, self.lbl_tax_source]:
            lbl.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800; letter-spacing: 0.5px;")
        
        self.lbl_tax_source.setStyleSheet(self.lbl_tax_source.styleSheet() + " color: #3b82f6;")
        
        layout.addWidget(self.lbl_sales_tax)
        layout.addSpacing(20)
        layout.addWidget(self.lbl_broker_fee)
        layout.addStretch()
        layout.addWidget(self.lbl_tax_source)
        
        self.main_layout.addWidget(self.taxes_bar)

    def create_table(self, is_buy=False):
        ref_col = "MEJOR VENTA" if is_buy else "MEJOR COMPRA"
        t = QTableWidget(0, 12)
        t.setHorizontalHeaderLabels(["", "ÍTEM", "TIPO", "MI PRECIO", "MI PROMEDIO", ref_col, "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setStyleSheet("QTableWidget { background: #000000; color: #f1f5f9; border: 1px solid #1e293b; font-size: 10px; } "
                        "QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; padding: 4px; }")
        t.horizontalHeader().setStretchLastSection(True)
        t.setIconSize(QSize(24, 24))
        t.setColumnWidth(0, 32)
        t.setColumnWidth(1, 180)
        
        t.itemSelectionChanged.connect(self.on_selection_changed)
        t.itemDoubleClicked.connect(lambda i: self.on_double_click(i, t))
        return t

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

    def _update_spinner(self):
        self.lbl_spinner.setText(self.spinner_chars[self.spinner_idx])
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)

    def _start_sync_ui(self, msg="INICIANDO..."):
        self.btn_refresh.setEnabled(False)
        self.btn_repopulate.setEnabled(False)
        self.btn_inventory.setEnabled(False)
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #3b82f6;")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.spinner_timer.start(100)

    def _stop_sync_ui(self, msg="LISTO", color="#10b981"):
        self.btn_refresh.setEnabled(True)
        self.btn_repopulate.setEnabled(True)
        self.btn_inventory.setEnabled(True)
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color: {color};")
        self.lbl_spinner.setText("")
        self.spinner_timer.stop()
        QTimer.singleShot(3000, lambda: self.progress_bar.hide())

    def _on_sync_update(self, msg, val):
        self.lbl_status.setText(msg)
        self.progress_bar.setValue(val)

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
        
        self._start_sync_ui("SINCRONIZANDO ÓRDENES...")
        self.worker = SyncWorker(auth.char_id, auth.current_token)
        self.worker.status_update.connect(self._on_sync_update)
        self.worker.finished_data.connect(self.on_data_ready)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_data_ready(self, orders):
        self.all_orders = orders
        self.update_taxes_info()
        self.populate_all(orders)
        self._stop_sync_ui(f"SINCRONIZACIÓN EXITOSA ({len(orders)} ÓRDENES)")
        self._start_inventory_preload()

    def update_taxes_info(self):
        auth = AuthManager.instance()
        taxes = TaxService.instance().get_taxes(auth.char_id)
        self.lbl_sales_tax.setText(f"SALES TAX: {taxes.sales_tax_pct:.2f}%")
        self.lbl_broker_fee.setText(f"BROKER FEE: {taxes.broker_fee_pct:.2f}% (BASE)")
        
        if taxes.status == "ready":
            src_text = "FUENTE: SKILLS REALES (Broker Fee Dinámico*)"
            self.lbl_tax_source.setText(src_text)
            self.lbl_tax_source.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 800;")
            tip = "Sales Tax basado en Accounting. Broker Fee ajustado por Standings en estaciones NPC."
            if taxes.standings_status != "ready":
                tip += "\nNOTA: Falta permiso de Standings. El fee NPC no incluye rebaja por reputación."
            self.lbl_tax_source.setToolTip(tip)
        elif taxes.status == "missing_scope":
            self.lbl_tax_source.setText("FALTA PERMISO DE SKILLS/STANDINGS — REAUTORIZAR")
            self.lbl_tax_source.setStyleSheet("color: #ef4444; font-size: 9px; font-weight: 800;")
            self.lbl_tax_source.setToolTip("Haz login de nuevo para conceder todos los permisos.")
        else:
            self.lbl_tax_source.setText("FUENTE: VALORES ESTIMADOS (FALLBACK)")
            self.lbl_tax_source.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 800;")
            self.lbl_tax_source.setToolTip("Usando configuración por defecto (8% Tax / 3% Fee).")

    def _start_inventory_preload(self):
        auth = AuthManager.instance()
        if not auth.current_token: return
        self.inventory_status = "loading"
        self.inv_worker = InventoryWorker(auth.char_id, auth.current_token)
        self.inv_worker.finished_data.connect(self._on_inv_preloaded)
        self.inv_worker.location_info.connect(self._on_inv_loc_ready)
        self.inv_worker.status_update.connect(lambda m, v: None) # Silencioso para preload
        self.inv_worker.error.connect(self._on_inv_error)
        self.inv_worker.start()

    def _on_inv_loc_ready(self, name):
        self.inventory_loc_name = name

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

        self.fill_table(self.table_sell, sells)
        self.fill_table(self.table_buy, buys)

    def fill_table(self, t, data):
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
            
            ref_val = a.best_sell if o.is_buy_order else a.best_buy
            ref_txt = format_isk(ref_val) if ref_val > 0 else "Sin datos"
            i_ref = QTableWidgetItem(ref_txt)
            i_ref.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            i_state = QTableWidgetItem(a.state.upper())
            s_txt = a.state.lower()
            
            if any(x in s_txt for x in ["sana", "liderando", "competitiva", "rentable"]):
                if o.is_buy_order: i_state.setForeground(QColor("#3b82f6"))
                else: i_state.setForeground(QColor("#10b981"))
            elif any(x in s_txt for x in ["superada", "ajustado", "revisar", "beneficio"]):
                i_state.setForeground(QColor("#f59e0b"))
            elif any(x in s_txt for x in ["pérdida", "no rentable", "error", "fuera"]):
                i_state.setForeground(QColor("#ef4444"))
            else:
                i_state.setForeground(QColor("#3b82f6"))

            items = [
                i_ico, QTableWidgetItem(o.item_name), 
                QTableWidgetItem("BUY" if o.is_buy_order else "SELL"),
                QTableWidgetItem(format_isk(o.price)),
                i_avg,
                i_ref,
                QTableWidgetItem(str(o.volume_total)), QTableWidgetItem(str(o.volume_remain)),
                QTableWidgetItem(f"{a.spread_pct:.1f}%"), 
                QTableWidgetItem(f"{a.margin_pct:.1f}%" if a.margin_pct != 0 else "---"),
                QTableWidgetItem(format_isk(a.net_profit_total) if a.net_profit_total != 0 else "---"),
                i_state
            ]
            for i in [3,4,5,10]: items[i].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for i in [2,6,7,8,9,11]: items[i].setTextAlignment(Qt.AlignCenter)
            
            items[2].setForeground(QColor("#3b82f6") if o.is_buy_order else QColor("#ef4444"))
            
            if a.margin_pct > 15: items[9].setForeground(QColor("#10b981"))
            elif a.margin_pct < 0: items[9].setForeground(QColor("#ef4444"))
            elif a.margin_pct > 0: items[9].setForeground(QColor("#f59e0b"))
            
            if a.net_profit_total > 0: items[10].setForeground(QColor("#10b981"))
            elif a.net_profit_total < 0: items[10].setForeground(QColor("#ef4444"))

            for c, item in enumerate(items): t.setItem(r, c, item)

    def on_selection_changed(self):
        sender = self.sender()
        target = self.table_buy if sender == self.table_sell else self.table_sell
        
        target.blockSignals(True)
        target.clearSelection()
        target.blockSignals(False)
        
        si = sender.selectedItems()
        if not si: return
        oid = sender.item(si[0].row(), 0).data(Qt.UserRole + 1)
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
        
        fee_source = getattr(o, "_fee_source", "Skills fallback")
        fee_val = getattr(o, "_b_fee_pct", 3.0)
        
        if o.is_buy_order:
            self.lbl_det_cost_msg.setText(f"Profit potencial (Jita Sell) | Fee: {fee_val:.2f}% via {fee_source}")
        elif avg > 0:
            self.lbl_det_cost_msg.setText(f"Profit real (WAC) | Fee: {fee_val:.2f}% via {fee_source}")
        else:
            self.lbl_det_cost_msg.setText(f"Sin registros de coste real | Fee: {fee_val:.2f}% via {fee_source}")
        
        self.det_price.setText(format_isk(o.price))
        self.det_avg.setText(format_isk(avg) if avg > 0 else "SIN REGISTROS")
        self.det_best_buy.setText(format_isk(a.best_buy))
        self.det_best_sell.setText(format_isk(a.best_sell))
        
        self.det_state.setText(a.state.upper())
        s_txt = a.state.lower()
        if any(x in s_txt for x in ["sana", "liderando", "competitiva", "rentable"]):
            color = "#3b82f6" if o.is_buy_order else "#10b981"
            self.det_state.setStyleSheet(f"color:{color}; font-weight:900;")
        elif any(x in s_txt for x in ["superada", "ajustado", "revisar", "beneficio"]):
            self.det_state.setStyleSheet("color:#f59e0b; font-weight:900;")
        else:
            self.det_state.setStyleSheet("color:#ef4444; font-weight:900;")
        
        if (not o.is_buy_order and avg > 0) or (o.is_buy_order and a.best_sell > 0):
            self.det_margin.setText(f"{a.margin_pct:.1f}%")
            self.det_margin.setStyleSheet("color:#10b981;" if a.margin_pct > 15 else ("color:#f59e0b;" if a.margin_pct > 0 else "color:#ef4444;"))
            self.det_profit_u.setText(format_isk(a.net_profit_per_unit))
            self.det_profit_u.setStyleSheet("color:#10b981;" if a.net_profit_per_unit > 0 else "color:#ef4444;")
            self.det_profit_t.setText(format_isk(a.net_profit_total))
            self.det_profit_t.setStyleSheet("color:#10b981;" if a.net_profit_total > 0 else "color:#ef4444;")
        else:
            for l in [self.det_margin, self.det_profit_u, self.det_profit_t]:
                l.setText("---")
                l.setStyleSheet("color:#475569;")

    def on_double_click(self, item, t):
        tid = t.item(item.row(), 0).data(Qt.UserRole)
        name = t.item(item.row(), 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: self.lbl_status.setText(m))

    def do_inventory_analysis(self):
        if self.inventory_status == "ready" and self.inventory_cache is not None:
            if not self.inventory_cache:
                QMessageBox.information(self, "Inventario Local Vacío", f"No se encontraron activos valorables en {self.inventory_loc_name}.")
                return
            InventoryAnalysisDialog(self.inventory_cache, self.inventory_loc_name, self.image_loader, self).exec()
            return
        if self.inventory_status == "loading":
            QMessageBox.information(self, "Cargando", "Analizando inventario local...")
            return
        
        self._start_sync_ui("CARGANDO INVENTARIO LOCAL...")
        auth = AuthManager.instance()
        if not auth.current_token:
            auth.login()
            return
        
        self.inventory_status = "loading"
        self.inv_worker = InventoryWorker(auth.char_id, auth.current_token)
        self.inv_worker.status_update.connect(self._on_sync_update)
        
        def on_done(data): 
            self.inventory_cache = data
            self.inventory_status = "ready"
            self._stop_sync_ui("INVENTARIO CARGADO")
            if not data:
                QMessageBox.information(self, "Inventario Local Vacío", f"No se encontraron activos valorables en {self.inventory_loc_name}.")
            else:
                InventoryAnalysisDialog(data, self.inventory_loc_name, self.image_loader, self).exec()
        
        self.inv_worker.finished_data.connect(on_done)
        self.inv_worker.location_info.connect(lambda n: setattr(self, "inventory_loc_name", n))
        self.inv_worker.error.connect(self.on_inventory_error)
        self.inv_worker.start()

    def on_inventory_error(self, msg):
        self._stop_sync_ui(f"ERROR: {msg[:30]}", "#ef4444")
        if msg == "missing_scope": QMessageBox.warning(self, "Permiso Faltante", "Falta el permiso 'esi-assets.read_assets.v1' o 'esi-location.read_location.v1'. Reautoriza el personaje.")
        elif msg == "pricing_error": QMessageBox.critical(self, "Error de Precios", "No se pudieron obtener precios de Jita.")
        else: QMessageBox.critical(self, "Error", f"Fallo al cargar inventario: {msg}")

    def on_error(self, err):
        self._stop_sync_ui(f"ERROR ESI: {err[:30]}", "#ef4444")
