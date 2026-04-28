import logging # VERSION: 1.1.14-FIXTABLE (Explicit Sort/Display Roles)
import time
import threading
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

class NumericTableWidgetItem(QTableWidgetItem):
    """Item de tabla que ordena numéricamente pero muestra texto formateado."""
    def __init__(self, text, value):
        super().__init__(text)
        self.sort_value = float(value) if value is not None else -1e18

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)

class SemanticTableWidgetItem(QTableWidgetItem):
    """Item de tabla que ordena por prioridad semántica (colores/estados)."""
    PRIORITY = {
        # Estados Órdenes
        "liderando": 100, "competitiva": 95, "sana": 90, "rentable": 85,
        "superada con beneficio": 60, "ajustado": 50, "superada": 40,
        "fuera de mercado": 25, "pérdida": 20, "no rentable": 15, "error": 0,
        # Recomendaciones Inventario
        "vender": 100, "mantener": 50, "revisar": 10
    }
    def __lt__(self, other):
        p1 = 0
        t1 = self.text().lower()
        for k, v in self.PRIORITY.items():
            if k in t1: p1 = v; break
        p2 = 0
        t2 = other.text().lower()
        for k, v in self.PRIORITY.items():
            if k in t2: p2 = v; break
        return p1 < p2

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
            AuthManager.instance().get_token()
            
            self.status_update.emit("DESCARGANDO ÓRDENES...", 20)
            orders = client.character_orders(self.char_id, self.token)
            if not orders:
                self.finished_data.emit([])
                return
            
            self.status_update.emit("APLICANDO TAXES Y STANDINGS...", 40)
            TaxService.instance().refresh_from_esi(self.char_id, self.token)
            
            self.status_update.emit("CARGANDO DATOS DE MERCADO...", 60)
            type_ids = list(set(o['type_id'] for o in orders))
            client.cache.cache.pop(f"market_orders_10000002", None)
            all_market_orders = client.market_orders(10000002)
            relevant_market_orders = [mo for mo in all_market_orders if mo['type_id'] in type_ids]
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            self.status_update.emit("CALCULANDO WAC (MI PROMEDIO)...", 80)
            cost_service = CostBasisService.instance()
            if cost_service.has_wallet_scope():
                cost_service.refresh_from_esi(self.char_id, self.token)
            
            self.status_update.emit("FINALIZANDO ANÁLISIS...", 95)
            analyzed = analyze_character_orders(orders, relevant_market_orders, item_names, load_market_filters(), char_id=self.char_id, token=self.token)
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
                if loc_res.get('station_id'): curr_loc_id = loc_res.get('station_id')
                elif loc_res.get('structure_id'): curr_loc_id = loc_res.get('structure_id')
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
            
            filtered_assets = [a for a in assets if a.get('location_id') == curr_loc_id] if curr_loc_id else [a for a in assets if 'slot' not in a.get('location_flag', '').lower()]
            if not filtered_assets:
                self.finished_data.emit([])
                return

            self.status_update.emit("OBTENIENDO PRECIOS JITA...", 70)
            type_ids = list(set(a['type_id'] for a in filtered_assets))
            client.cache.cache.pop(f"market_orders_10000002", None)
            all_market_orders = client.market_orders(10000002)
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            self.status_update.emit("CALCULANDO BENEFICIOS...", 90)
            cost_service = CostBasisService.instance()
            if cost_service.has_wallet_scope():
                cost_service.refresh_from_esi(self.char_id, self.token)
                
            analyzed = analyze_inventory(filtered_assets, all_market_orders, item_names, load_market_filters(), char_id=self.char_id, token=self.token)
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
        title_v.addWidget(title); title_v.addWidget(loc_lbl)
        hl.addLayout(title_v); hl.addStretch()
        
        total_val = sum(item.analysis.est_total_value for item in self.items)
        val_v = QVBoxLayout()
        val_lbl = QLabel(format_isk(total_val))
        val_lbl.setStyleSheet("color: #10b981; font-size: 22px; font-weight: 900; border:none;")
        val_sub = QLabel("VALOR ESTIMADO NETO")
        val_sub.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; border:none;")
        val_sub.setAlignment(Qt.AlignRight)
        val_v.addWidget(val_lbl); val_v.addWidget(val_sub)
        hl.addLayout(val_v)
        layout.addWidget(header)

        self.table = QTableWidget(len(self.items), 9)
        self.table.setHorizontalHeaderLabels(["", "ÍTEM", "CANTIDAD", "MI PROMEDIO", "P. UNIT NETO", "PROFIT DE VENTA", "VALOR %", "RECOMENDACIÓN", "MOTIVO"])
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
        self.table.setColumnWidth(0, 45); self.table.setColumnWidth(1, 220); self.table.setColumnWidth(5, 140); self.table.setColumnWidth(7, 120)

        self.table.setSortingEnabled(False)
        sorted_items = sorted(self.items, key=lambda x: getattr(x, "_net_profit_total", 0.0), reverse=True)
        for row, item in enumerate(sorted_items):
            a = item.analysis
            avg_buy = getattr(item, "_avg_buy", 0.0)
            net_profit_total = getattr(item, "_net_profit_total", 0.0)
            
            i_icon = QTableWidgetItem()
            i_icon.setData(Qt.UserRole, item.type_id)
            self.image_loader.load(ItemMetadataHelper.get_icon_url(item.type_id), lambda px, it=i_icon: it.setIcon(QIcon(px)))
            
            i_name = QTableWidgetItem(item.item_name)
            
            i_qty = NumericTableWidgetItem(f"{item.quantity:,}", item.quantity)
            i_qty.setTextAlignment(Qt.AlignCenter)
            
            i_avg = NumericTableWidgetItem(format_isk(avg_buy) if avg_buy > 0 else "Sin registros", avg_buy)
            i_avg.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            i_avg.setForeground(QColor("#94a3b8") if avg_buy > 0 else QColor("#334155"))
            
            i_price = NumericTableWidgetItem(format_isk(a.est_net_sell_unit), a.est_net_sell_unit)
            i_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            i_profit = NumericTableWidgetItem(format_isk(net_profit_total) if avg_buy > 0 else "Sin registros", net_profit_total if avg_buy > 0 else -1e15)
            i_profit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if avg_buy > 0:
                if net_profit_total > 0: i_profit.setForeground(QColor("#10b981"))
                elif net_profit_total < 0: i_profit.setForeground(QColor("#ef4444"))
            else: i_profit.setForeground(QColor("#334155"))
            
            pct = (a.est_total_value / total_val * 100) if total_val > 0 else 0
            i_pct = NumericTableWidgetItem(f"{pct:.1f}%", pct)
            i_pct.setTextAlignment(Qt.AlignCenter)
            
            i_rec = SemanticTableWidgetItem(a.recommendation.upper())
            i_rec.setTextAlignment(Qt.AlignCenter)
            if a.recommendation == "VENDER": i_rec.setForeground(QColor("#10b981"))
            elif a.recommendation == "REVISAR": i_rec.setForeground(QColor("#f59e0b"))
            else: i_rec.setForeground(QColor("#3b82f6"))
            
            i_reason = SemanticTableWidgetItem(a.reason)
            r_txt = a.reason.lower()
            if any(x in r_txt for x in ["spread excesivo", "profit sólido", "margen positivo"]): i_reason.setForeground(QColor("#10b981"))
            elif "bajo" in r_txt: i_reason.setForeground(QColor("#f59e0b"))
            elif "pérdida" in r_txt or "bajo el coste" in r_txt: i_reason.setForeground(QColor("#ef4444"))
            else: i_reason.setForeground(QColor("#64748b"))
            
            self.table.setItem(row, 0, i_icon); self.table.setItem(row, 1, i_name); self.table.setItem(row, 2, i_qty)
            self.table.setItem(row, 3, i_avg); self.table.setItem(row, 4, i_price); self.table.setItem(row, 5, i_profit)
            self.table.setItem(row, 6, i_pct); self.table.setItem(row, 7, i_rec); self.table.setItem(row, 8, i_reason)
            
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.table)
        
        footer = QLabel("* Puedes hacer click en las cabeceras para ordenar por cualquier columna.")
        footer.setStyleSheet("color: #334155; font-size: 9px; font-weight: 700;")
        layout.addWidget(footer)

    def on_double_click(self, item):
        tid = self.table.item(item.row(), 0).data(Qt.UserRole)
        name = self.table.item(item.row(), 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: None)

class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None; self.inv_worker = None; self.all_orders = []
        self.image_loader = AsyncImageLoader(); self.inventory_cache = None
        self.inventory_loc_name = "DESCONOCIDA"; self.inventory_status = "idle" 
        self._syncing_headers = False
        self.spinner_chars = ["|", "/", "-", "\\"]; self.spinner_idx = 0
        self.spinner_timer = QTimer(self); self.spinner_timer.timeout.connect(self._update_spinner)
        self.setup_ui()
        self._load_ui_state()
        AuthManager.instance().authenticated.connect(self._on_authenticated)

    def _on_authenticated(self, char_name, tokens): self.do_sync(is_update=False)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(15, 15, 15, 15); self.main_layout.setSpacing(12)
        header_layout = QHBoxLayout(); title_v = QVBoxLayout()
        title_lbl = QLabel("MIS PEDIDOS"); title_lbl.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        status_h = QHBoxLayout(); self.lbl_spinner = QLabel(""); self.lbl_spinner.setFixedWidth(15); self.lbl_spinner.setStyleSheet("color: #3b82f6; font-weight: 900;")
        self.lbl_status = QLabel("● SINCRONIZACIÓN REQUERIDA"); self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: 800;")
        status_h.addWidget(self.lbl_spinner); status_h.addWidget(self.lbl_status); status_h.addStretch()
        title_v.addWidget(title_lbl); title_v.addLayout(status_h)
        self.progress_bar = QProgressBar(); self.progress_bar.setFixedHeight(4); self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #1e293b; border: none; } QProgressBar::chunk { background: #3b82f6; }"); self.progress_bar.hide()
        title_v.addWidget(self.progress_bar)
        
        self.btn_repopulate = QPushButton("ACTUALIZAR"); self.btn_refresh = QPushButton("SINCRONIZAR ÓRDENES"); self.btn_inventory = QPushButton("INVENTARIO")
        for b in [self.btn_repopulate, self.btn_refresh, self.btn_inventory]:
            b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(35)
            b.setStyleSheet("QPushButton { background-color: #1e293b; color: #94a3b8; font-size: 10px; font-weight: 900; border: 1px solid #334155; border-radius: 4px; padding: 0 15px; }"
                            "QPushButton:hover { background-color: #334155; color: #f1f5f9; } QPushButton:disabled { color: #475569; }")
        self.btn_refresh.setStyleSheet(self.btn_refresh.styleSheet().replace("#1e293b", "#3b82f6").replace("#94a3b8", "white"))
        self.btn_inventory.setStyleSheet(self.btn_inventory.styleSheet().replace("#1e293b", "#10b981").replace("#94a3b8", "white"))
        self.btn_repopulate.clicked.connect(lambda: self.do_sync(is_update=True))
        self.btn_refresh.clicked.connect(lambda: self.do_sync(is_update=False))
        self.btn_inventory.clicked.connect(self.do_inventory_analysis)

        header_layout.addLayout(title_v); header_layout.addStretch(); header_layout.addWidget(self.btn_inventory)
        header_layout.addSpacing(10); header_layout.addWidget(self.btn_repopulate); header_layout.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header_layout)

        self.lbl_sell_count = QLabel("ÓRDENES DE VENTA (0)"); self.lbl_sell_count.setStyleSheet("color:#ef4444; font-weight:900; font-size:10px;")
        self.main_layout.addWidget(self.lbl_sell_count)
        self.table_sell = self.create_table(is_buy=False); self.main_layout.addWidget(self.table_sell, 1)
        self.setup_taxes_bar()
        self.lbl_buy_count = QLabel("ÓRDENES DE COMPRA (0)"); self.lbl_buy_count.setStyleSheet("color:#3b82f6; font-weight:900; font-size:10px;")
        self.main_layout.addWidget(self.lbl_buy_count)
        self.table_buy = self.create_table(is_buy=True); self.main_layout.addWidget(self.table_buy, 1)

        self.detail_panel = QFrame(); self.detail_panel.setFixedHeight(130); self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_layout(); self.main_layout.addWidget(self.detail_panel)
        self.table_sell.horizontalHeader().sectionResized.connect(lambda i, o, n: self._on_header_resized(self.table_sell, i, n))
        self.table_buy.horizontalHeader().sectionResized.connect(lambda i, o, n: self._on_header_resized(self.table_buy, i, n))

    def setup_taxes_bar(self):
        self.taxes_bar = QFrame(); self.taxes_bar.setFixedHeight(30); self.taxes_bar.setStyleSheet("background-color: #0f172a; border-radius: 15px; border: 1px solid #1e293b;")
        layout = QHBoxLayout(self.taxes_bar); layout.setContentsMargins(15, 0, 15, 0)
        self.lbl_sales_tax = QLabel("SALES TAX: ---"); self.lbl_broker_fee = QLabel("BROKER FEE: ---"); self.lbl_tax_source = QLabel("FUENTE: ---")
        for lbl in [self.lbl_sales_tax, self.lbl_broker_fee, self.lbl_tax_source]: lbl.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800;")
        layout.addWidget(self.lbl_sales_tax); layout.addSpacing(20); layout.addWidget(self.lbl_broker_fee); layout.addStretch(); layout.addWidget(self.lbl_tax_source)
        self.main_layout.addWidget(self.taxes_bar)

    def create_table(self, is_buy=False):
        t = QTableWidget(0, 12)
        t.setHorizontalHeaderLabels(["", "ÍTEM", "TIPO", "MI PRECIO", "MI PROMEDIO", "MEJOR VENTA" if is_buy else "MEJOR COMPRA", "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
        t.verticalHeader().setVisible(False); t.setSelectionBehavior(QAbstractItemView.SelectRows); t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setStyleSheet("QTableWidget { background: #000000; color: #f1f5f9; border: 1px solid #1e293b; font-size: 10px; } QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; padding: 4px; }")
        t.horizontalHeader().setStretchLastSection(True); t.setIconSize(QSize(24, 24)); t.setColumnWidth(0, 32); t.setColumnWidth(1, 180)
        t.itemSelectionChanged.connect(self.on_selection_changed); t.itemDoubleClicked.connect(lambda i: self.on_double_click(i, t))
        t.setSortingEnabled(True)
        return t

    def setup_detail_layout(self):
        dl = QHBoxLayout(self.detail_panel); dl.setContentsMargins(15, 12, 15, 12)
        self.lbl_det_icon = QLabel(); self.lbl_det_icon.setFixedSize(64, 64); self.lbl_det_icon.setStyleSheet("background:#1e293b; border-radius:4px;"); dl.addWidget(self.lbl_det_icon)
        info_v = QVBoxLayout(); self.lbl_det_item = QLabel("SELECCIONA UNA ORDEN"); self.lbl_det_item.setStyleSheet("color:#f1f5f9; font-size:14px; font-weight:900;")
        self.lbl_det_type = QLabel("---"); self.lbl_det_cost_msg = QLabel("---"); info_v.addWidget(self.lbl_det_item); info_v.addWidget(self.lbl_det_type); info_v.addWidget(self.lbl_det_cost_msg); info_v.addStretch(); dl.addLayout(info_v, 2)
        self.grid = QGridLayout(); self.grid.setSpacing(10)
        def add_m(l, r, c):
            v = QVBoxLayout(); v.addWidget(QLabel(l, styleSheet="color:#475569; font-size:9px; font-weight:900;"))
            val = QLabel("---", styleSheet="color:#f1f5f9; font-size:11px; font-weight:900;"); v.addWidget(val); self.grid.addLayout(v, r, c); return val
        self.det_price = add_m("MI PRECIO", 0, 0); self.det_avg = add_m("MI PROMEDIO", 0, 1); self.det_best_buy = add_m("MEJOR COMPRA", 0, 2); self.det_best_sell = add_m("MEJOR VENTA", 0, 3)
        self.det_margin = add_m("MARGEN NETO", 1, 0); self.det_profit_u = add_m("PROFIT / U", 1, 1); self.det_profit_t = add_m("PROFIT TOTAL", 1, 2); self.det_state = add_m("ESTADO", 1, 3); dl.addLayout(self.grid, 5)

    def _update_spinner(self): self.lbl_spinner.setText(self.spinner_chars[self.spinner_idx]); self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
    def _start_sync_ui(self, msg="INICIANDO..."): self.btn_refresh.setEnabled(False); self.btn_repopulate.setEnabled(False); self.btn_inventory.setEnabled(False); self.lbl_status.setText(msg); self.lbl_status.setStyleSheet("color: #3b82f6;"); self.progress_bar.setValue(0); self.progress_bar.show(); self.spinner_timer.start(100)
    def _stop_sync_ui(self, msg="LISTO", color="#10b981"): self.btn_refresh.setEnabled(True); self.btn_repopulate.setEnabled(True); self.btn_inventory.setEnabled(True); self.lbl_status.setText(msg); self.lbl_status.setStyleSheet(f"color: {color};"); self.lbl_spinner.setText(""); self.spinner_timer.stop(); QTimer.singleShot(3000, lambda: self.progress_bar.hide())
    def _on_sync_update(self, msg, val): self.lbl_status.setText(msg); self.progress_bar.setValue(val)

    def do_sync(self, is_update=False):
        auth = AuthManager.instance(); t = auth.get_token()
        if not t: auth.login(); return
        self._start_sync_ui("SINCRONIZANDO ÓRDENES..."); self.worker = SyncWorker(auth.char_id, t); self.worker.status_update.connect(self._on_sync_update); self.worker.finished_data.connect(self.on_data_ready); self.worker.error.connect(self.on_error); self.worker.start()

    def on_data_ready(self, orders): self.all_orders = orders; self.update_taxes_info(); self.populate_all(orders); self._stop_sync_ui(f"SINCRONIZACIÓN EXITOSA ({len(orders)} ÓRDENES)"); self._start_inventory_preload()

    def populate_all(self, orders):
        sells = [o for o in orders if not o.is_buy_order]; buys = [o for o in orders if o.is_buy_order]
        self.lbl_sell_count.setText(f"ÓRDENES DE VENTA ({len(sells)})"); self.lbl_buy_count.setText(f"ÓRDENES DE COMPRA ({len(buys)})")
        self.fill_table(self.table_sell, sells); self.fill_table(self.table_buy, buys)

    def fill_table(self, t, data):
        t.setSortingEnabled(False); t.setRowCount(0); t.setRowCount(len(data))
        for r, o in enumerate(data):
            a = o.analysis; cost = CostBasisService.instance().get_cost_basis(o.type_id)
            i_ico = QTableWidgetItem(); i_ico.setData(Qt.UserRole, o.type_id); i_ico.setData(Qt.UserRole + 1, o.order_id)
            self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px, it=i_ico: it.setIcon(QIcon(px)))
            i_name = QTableWidgetItem(o.item_name)
            i_type = QTableWidgetItem("BUY" if o.is_buy_order else "SELL"); i_type.setForeground(QColor("#3b82f6") if o.is_buy_order else QColor("#ef4444"))
            
            i_price = NumericTableWidgetItem(format_isk(o.price), o.price)
            avg = cost.average_buy_price if cost else 0.0
            i_avg = NumericTableWidgetItem(format_isk(avg) if avg > 0 else "---", avg)
            ref_v = a.best_sell if o.is_buy_order else a.best_buy
            i_ref = NumericTableWidgetItem(format_isk(ref_v) if ref_v > 0 else "---", ref_v)
            i_tot = NumericTableWidgetItem(str(o.volume_total), o.volume_total)
            i_rem = NumericTableWidgetItem(str(o.volume_remain), o.volume_remain)
            i_spr = NumericTableWidgetItem(f"{a.spread_pct:.1f}%", a.spread_pct)
            i_mar = NumericTableWidgetItem(f"{a.margin_pct:.1f}%" if a.margin_pct != 0 else "---", a.margin_pct)
            if a.margin_pct > 15: i_mar.setForeground(QColor("#10b981"))
            elif a.margin_pct < 0: i_mar.setForeground(QColor("#ef4444"))
            
            i_prof = NumericTableWidgetItem(format_isk(a.net_profit_total) if a.net_profit_total != 0 else "---", a.net_profit_total)
            if a.net_profit_total > 0: i_prof.setForeground(QColor("#10b981"))
            elif a.net_profit_total < 0: i_prof.setForeground(QColor("#ef4444"))
            
            i_state = SemanticTableWidgetItem(a.state.upper())
            s_low = a.state.lower()
            if any(x in s_low for x in ["liderando", "competitiva", "sana", "rentable"]): i_state.setForeground(QColor("#3b82f6") if o.is_buy_order else QColor("#10b981"))
            elif "superada" in s_low or "ajustado" in s_low: i_state.setForeground(QColor("#f59e0b"))
            elif "pérdida" in s_low or "no rentable" in s_low or "fuera" in s_low: i_state.setForeground(QColor("#ef4444"))
            
            items = [i_ico, i_name, i_type, i_price, i_avg, i_ref, i_tot, i_rem, i_spr, i_mar, i_prof, i_state]
            for i, it in enumerate(items):
                if i in [3,4,5,10]: it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif i in [2,6,7,8,9,11]: it.setTextAlignment(Qt.AlignCenter)
                t.setItem(r, i, it)
        t.setSortingEnabled(True)

    def on_selection_changed(self):
        s = self.sender(); tar = self.table_buy if s == self.table_sell else self.table_sell
        tar.blockSignals(True); tar.clearSelection(); tar.blockSignals(False)
        si = s.selectedItems()
        if not si: return
        oid = s.item(si[0].row(), 0).data(Qt.UserRole + 1)
        o = next((ord for ord in self.all_orders if ord.order_id == oid), None)
        if o: self.update_det(o)

    def update_det(self, o):
        self.lbl_det_item.setText(o.item_name.upper()); self.lbl_det_type.setText("COMPRA" if o.is_buy_order else "VENTA")
        self.lbl_det_type.setStyleSheet("color:#3b82f6;" if o.is_buy_order else "color:#ef4444;")
        self.image_loader.load(ItemMetadataHelper.get_icon_url(o.type_id), lambda px: self.lbl_det_icon.setPixmap(px.scaled(64,64,Qt.KeepAspectRatio)))
        a = o.analysis; cost = CostBasisService.instance().get_cost_basis(o.type_id); avg = cost.average_buy_price if cost else 0.0
        self.lbl_det_cost_msg.setText(f"Info: {a.state} | Fee: {getattr(o, '_b_fee_pct', 3.0):.2f}% ({getattr(o, '_fee_source', 'Default')})")
        self.det_price.setText(format_isk(o.price)); self.det_avg.setText(format_isk(avg) if avg > 0 else "---")
        self.det_best_buy.setText(format_isk(a.best_buy)); self.det_best_sell.setText(format_isk(a.best_sell))
        self.det_margin.setText(f"{a.margin_pct:.1f}%"); self.det_profit_u.setText(format_isk(a.net_profit_per_unit)); self.det_profit_t.setText(format_isk(a.net_profit_total))
        self.det_state.setText(a.state.upper())

    def on_double_click(self, item, t):
        tid = t.item(item.row(), 0).data(Qt.UserRole); name = t.item(item.row(), 1).text()
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, lambda m, c: self.lbl_status.setText(m))

    def do_inventory_analysis(self):
        if self.inventory_status == "ready" and self.inventory_cache:
            InventoryAnalysisDialog(self.inventory_cache, self.inventory_loc_name, self.image_loader, self).exec(); return
        auth = AuthManager.instance(); t = auth.get_token()
        if not t: auth.login(); return
        self._start_sync_ui("CARGANDO INVENTARIO..."); self.inventory_status = "loading"
        self.inv_worker = InventoryWorker(auth.char_id, t); self.inv_worker.status_update.connect(self._on_sync_update)
        def on_done(data):
            self.inventory_cache = data; self.inventory_status = "ready"; self._stop_sync_ui("INVENTARIO CARGADO")
            if data: InventoryAnalysisDialog(data, self.inventory_loc_name, self.image_loader, self).exec()
            else: QMessageBox.information(self, "Vacio", "No hay items en esta ubicacion.")
        self.inv_worker.finished_data.connect(on_done); self.inv_worker.location_info.connect(lambda n: setattr(self, "inventory_loc_name", n)); self.inv_worker.start()

    def update_taxes_info(self):
        auth = AuthManager.instance(); tx = TaxService.instance().get_taxes(auth.char_id)
        self.lbl_sales_tax.setText(f"SALES TAX: {tx.sales_tax_pct:.2f}%"); self.lbl_broker_fee.setText(f"BROKER FEE: {tx.broker_fee_pct:.2f}% (BASE)")
        self.lbl_tax_source.setText(f"FUENTE: {'REAL' if tx.status=='ready' else 'FALLBACK'}")

    def on_error(self, err): self._stop_sync_ui(f"ERROR: {err[:40]}", "#ef4444")
    def on_inventory_error(self, msg): self._stop_sync_ui(f"ERR INV: {msg[:30]}", "#ef4444")
    def _load_ui_state(self): pass
    def _on_header_resized(self, table, idx, size): pass
    def _save_ui_state(self): pass
