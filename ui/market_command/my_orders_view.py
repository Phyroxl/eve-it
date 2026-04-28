import logging # Session 24 Improved
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QColor

from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.market_engine import analyze_character_orders
from core.config_manager import load_market_filters
from ui.market_command.widgets import ItemInteractionHelper
from core.item_metadata import ItemMetadataHelper
from ui.market_command.performance_view import AsyncImageLoader
from core.cost_basis_service import CostBasisService
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
            
            # Refrescar CostBasis (si hay scope)
            cost_service = CostBasisService.instance()
            if cost_service.has_wallet_scope():
                cost_service.refresh_from_esi(self.char_id, self.token)
            
            analyzed = analyze_character_orders(orders, relevant_market_orders, item_names, config)
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
            
            # Solo items en hangares o naves (excluir contenedores anidados para simplicidad en MVP)
            # location_flag: 'Hangar', 'Cargo', etc.
            filtered_assets = [a for a in assets if 'slot' not in a.get('location_flag', '').lower()]
            
            if not filtered_assets:
                self.finished_data.emit([])
                return

            type_ids = list(set(a['type_id'] for a in filtered_assets))
            
            # Para inventario, necesitamos precios de Jita
            all_market_orders = client.market_orders(10000002)
            if not all_market_orders:
                self.error.emit("pricing_error")
                return
            
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            from core.market_engine import analyze_inventory
            config = load_market_filters()
            
            analyzed = analyze_inventory(filtered_assets, all_market_orders, item_names, config)
            # Ordenar por valor total descendente
            analyzed.sort(key=lambda x: x.analysis.est_total_value, reverse=True)
            self.finished_data.emit(analyzed)
            
        except Exception as e:
            if "403" in str(e) or "missing_scope" in str(e):
                self.error.emit("missing_scope")
            else:
                import traceback
                traceback.print_exc()
                self.error.emit(str(e))

from PySide6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QHeaderView, QAbstractItemView
from PySide6.QtGui import QColor, QIcon

class InventoryAnalysisDialog(QDialog):
    def __init__(self, items, image_loader, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ANÁLISIS DE INVENTARIO - EVE iT")
        self.resize(1000, 700)
        self.setStyleSheet("background-color: #0f172a; color: #f1f5f9;")
        self.items = items
        self.image_loader = image_loader
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("INVENTARIO ANALIZADO")
        title.setStyleSheet("font-size: 18px; font-weight: 900; color: #3b82f6;")
        layout.addWidget(title)

        summary_h = QHBoxLayout()
        total_val = sum(i.analysis.est_total_value for i in self.items)
        lbl_total = QLabel(f"VALOR ESTIMADO TOTAL (NETO): {format_isk(total_val)}")
        lbl_total.setStyleSheet("font-size: 12px; font-weight: 800; color: #10b981;")
        summary_h.addWidget(lbl_total)
        summary_h.addStretch()
        layout.addLayout(summary_h)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "", "Item", "Cantidad", "Jita Sell", "Jita Buy", "Spread", "Valor Total Est.", "Recomendación", "Motivo"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 32)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet(
            "QTableWidget { background: #000000; border: 1px solid #1e293b; font-size: 11px; } "
            "QHeaderView::section { background: #1e293b; color: #94a3b8; font-weight: 800; border: none; padding: 5px; } "
        )
        layout.addWidget(self.table)

        self.populate_table()

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        close_btn = QPushButton("CERRAR")
        close_btn.setFixedSize(100, 30)
        close_btn.setStyleSheet("background: #334155; color: white; font-weight: 800; border-radius: 4px;")
        close_btn.clicked.connect(self.accept)
        btn_h.addWidget(close_btn)
        layout.addLayout(btn_h)

    def populate_table(self):
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.items))
        for r, item in enumerate(self.items):
            a = item.analysis
            
            i_icon = QTableWidgetItem()
            self.table.setItem(r, 0, i_icon)
            url = ItemMetadataHelper.get_icon_url(item.type_id)
            self.image_loader.load(url, lambda px, item_item=i_icon: item_item.setIcon(QIcon(px)))

            i_name = QTableWidgetItem(item.item_name)
            i_qty = QTableWidgetItem(f"{item.quantity:,}")
            i_qty.setTextAlignment(Qt.AlignCenter)
            
            i_sell = QTableWidgetItem(format_isk(a.best_sell))
            i_buy = QTableWidgetItem(format_isk(a.best_buy))
            i_spread = QTableWidgetItem(f"{a.spread_pct:.1f}%")
            i_total = QTableWidgetItem(format_isk(a.est_total_value))
            i_total.setForeground(QColor("#10b981"))
            
            i_rec = QTableWidgetItem(a.recommendation.upper())
            if a.recommendation == "Vender": i_rec.setForeground(QColor("#10b981"))
            elif a.recommendation == "Mantener": i_rec.setForeground(QColor("#f59e0b"))
            else: i_rec.setForeground(QColor("#ef4444"))
            
            i_reason = QTableWidgetItem(a.reason)
            i_reason.setForeground(QColor("#64748b"))

            self.table.setItem(r, 1, i_name)
            self.table.setItem(r, 2, i_qty)
            self.table.setItem(r, 3, i_sell)
            self.table.setItem(r, 4, i_buy)
            self.table.setItem(r, 5, i_spread)
            self.table.setItem(r, 6, i_total)
            self.table.setItem(r, 7, i_rec)
            self.table.setItem(r, 8, i_reason)


class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.inv_worker = None
        self.all_orders = []
        self.image_loader = AsyncImageLoader()
        
        # Cache de Inventario
        self.inventory_cache = None
        self.inventory_status = "idle" # idle, loading, ready, error
        self.inventory_error_msg = ""
        
        self.setup_ui()
        
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

        self.btn_inventory = QPushButton("ANALIZAR INVENTARIO")
        self.btn_inventory.setCursor(Qt.PointingHandCursor)
        self.btn_inventory.setMinimumWidth(150)
        self.btn_inventory.setFixedHeight(35)
        self.btn_inventory.setStyleSheet(
            "QPushButton { background-color: #059669; color: white; font-size: 10px; font-weight: 900; "
            "border-radius: 4px; letter-spacing: 1px; padding: 0 15px; } "
            "QPushButton:hover { background-color: #047857; }"
        )
        self.btn_inventory.clicked.connect(self.do_inventory_analysis)

        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_inventory)
        header.addWidget(self.btn_repopulate)
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)

        def create_table():
            t = QTableWidget(0, 12)
            t.setHorizontalHeaderLabels([
                "", "Ítem", "Tipo", "Mi Precio", "Mi Promedio", "Mejor Competidor", "Total", "Restante", "Spread", "Margen", "Beneficio Total", "Estado"
            ])
            t.setColumnWidth(0, 32)
            t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            t.setIconSize(QSize(24, 24))
            t.setColumnWidth(4, 100) # Mi Promedio
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
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
            t.setIconSize(QSize(24, 24))
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
        dl.setContentsMargins(15, 12, 15, 12)
        dl.setSpacing(25)

        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setFixedSize(64, 64)
        self.lbl_det_icon.setAlignment(Qt.AlignCenter)
        self.lbl_det_icon.setStyleSheet("background: #1e293b; border-radius: 6px; border: 1px solid #334155;")
        dl.addWidget(self.lbl_det_icon)

        info_v = QVBoxLayout()
        info_v.setSpacing(2)
        self.lbl_det_item = QLabel("SELECCIONA UNA ORDEN")
        self.lbl_det_item.setStyleSheet("color: #f8fafc; font-size: 14px; font-weight: 900; letter-spacing: 0.5px;")
        self.lbl_det_type = QLabel("---")
        self.lbl_det_type.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700; text-transform: uppercase;")
        info_v.addStretch()
        info_v.addWidget(self.lbl_det_item)
        info_v.addWidget(self.lbl_det_type)
        info_v.addStretch()
        dl.addLayout(info_v, 2)

        m_g = QGridLayout()
        m_g.setSpacing(8)
        m_g.setVerticalSpacing(4)
        
        def _create_det_row(layout, label):
            count = layout.count()
            row = count // 4
            col = count % 4
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0,0,0,0)
            v.setSpacing(1)
            lbl = QLabel(label, styleSheet="color: #475569; font-size: 9px; font-weight: 800; text-transform: uppercase;")
            val = QLabel("---")
            val.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 900;")
            v.addWidget(lbl)
            v.addWidget(val)
            layout.addWidget(w, row, col)
            return val

        self._create_det_row = _create_det_row
        self.lbl_det_my_price = self._create_det_row(m_g, "MI PRECIO")
        self.lbl_det_my_avg = self._create_det_row(m_g, "MI PROMEDIO")
        self.lbl_det_best_buy = self._create_det_row(m_g, "MEJOR COMPRA")
        self.lbl_det_best_sell = self._create_det_row(m_g, "MEJOR VENTA")
        self.lbl_det_margin = self._create_det_row(m_g, "MARGEN NETO")
        self.lbl_det_profit_u = self._create_det_row(m_g, "BENEFICIO / U")
        self.lbl_det_profit_total = self._create_det_row(m_g, "BENEFICIO TOTAL")
        self.lbl_det_state = self._create_det_row(m_g, "ESTADO")
        
        self.lbl_det_reason = QLabel()
        self.lbl_det_reason.setWordWrap(True)
        self.lbl_det_reason.setStyleSheet("color: #94a3b8; font-size: 10px; font-style: italic; border-top: 1px solid #1e293b; padding-top: 4px;")
        m_g.addWidget(self.lbl_det_reason, 2, 0, 1, 4)
        
        dl.addLayout(m_g, 5)

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
            
        # Iniciar precarga de inventario automáticamente
        self._preload_inventory()

    def _preload_inventory(self):
        auth = AuthManager.instance()
        if not auth.current_token: return
        
        if self.inv_worker and self.inv_worker.isRunning():
            return
            
        self.inventory_status = "loading"
        self.inv_worker = InventoryWorker(auth.char_id, auth.current_token)
        # Conectamos a señales de precarga
        self.inv_worker.finished_data.connect(self._on_inventory_preloaded)
        self.inv_worker.error.connect(self._on_inventory_preload_error)
        self.inv_worker.start()

    def _on_inventory_preloaded(self, items):
        self.inventory_cache = items
        self.inventory_status = "ready"
        _log.info(f"Inventario precargado: {len(items)} items.")

    def _on_inventory_preload_error(self, msg):
        # No mostramos error UI aquí porque es una precarga silenciosa
        self.inventory_status = "error"
        self.inventory_error_msg = msg
        _log.warning(f"Error en precarga de inventario: {msg}")

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
            table.clearContents()
            table.setRowCount(0)
            table.setRowCount(len(data))
            for row, o in enumerate(data):
                a = o.analysis
                
                i_icon = QTableWidgetItem()
                i_icon.setData(Qt.UserRole, o.type_id)
                i_icon.setData(Qt.UserRole + 1, o.order_id)
                url = ItemMetadataHelper.get_icon_url(o.type_id)
                self.image_loader.load(url, lambda px, item_item=i_icon: item_item.setIcon(QIcon(px)))

                i_name = QTableWidgetItem(o.item_name)
                
                i_type = QTableWidgetItem("BUY" if o.is_buy_order else "SELL")
                i_type.setForeground(QColor("#3b82f6") if o.is_buy_order else QColor("#ef4444"))
                
                i_myprice = QTableWidgetItem(format_isk(o.price))
                i_myprice.setData(Qt.UserRole, float(o.price))
                i_myprice.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                
                best_comp = a.best_buy if o.is_buy_order else a.best_sell
                i_best = QTableWidgetItem(format_isk(best_comp))
                i_best.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                
                i_total = QTableWidgetItem(f"{o.volume_total:,}")
                i_total.setTextAlignment(Qt.AlignCenter)
                i_remain = QTableWidgetItem(f"{o.volume_remain:,}")
                i_remain.setTextAlignment(Qt.AlignCenter)
                
                i_spread = QTableWidgetItem(f"{a.spread_pct:.1f}%")
                i_spread.setTextAlignment(Qt.AlignCenter)
                
                cost_basis = CostBasisService.instance().get_cost_basis(o.type_id)
                has_avg = cost_basis is not None
                
                # Para ventas, solo mostramos profit/margen si hay Mi Promedio real
                show_profit = o.is_buy_order or has_avg
                
                if show_profit:
                    i_margin = QTableWidgetItem(f"{a.margin_pct:.1f}%")
                    i_margin.setTextAlignment(Qt.AlignCenter)
                    if a.margin_pct > 15: i_margin.setForeground(QColor("#10b981"))
                    elif a.margin_pct < 0: i_margin.setForeground(QColor("#ef4444"))
                    
                    i_profit = QTableWidgetItem(format_isk(a.net_profit_total))
                    i_profit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if a.net_profit_total > 0: i_profit.setForeground(QColor("#10b981"))
                    elif a.net_profit_total < 0: i_profit.setForeground(QColor("#ef4444"))
                else:
                    i_margin = QTableWidgetItem("---")
                    i_margin.setTextAlignment(Qt.AlignCenter)
                    i_margin.setForeground(QColor("#475569"))
                    i_profit = QTableWidgetItem("---")
                    i_profit.setTextAlignment(Qt.AlignCenter)
                    i_profit.setForeground(QColor("#475569"))
                
                i_state = QTableWidgetItem(a.state)
                if "Sana" in a.state or "Competitiva" in a.state or "Rotación Sana" in a.state:
                    i_state.setForeground(QColor("#10b981"))
                elif "Ajustado" in a.state or "Aún Rentable" in a.state:
                    i_state.setForeground(QColor("#f59e0b"))
                else:
                    i_state.setForeground(QColor("#ef4444"))
                    
                # Obtener CostBasis
                cost_basis = CostBasisService.instance().get_cost_basis(o.type_id)
                if cost_basis:
                    i_avg = QTableWidgetItem(format_isk(cost_basis.average_buy_price))
                    i_avg.setForeground(QColor("#f1f5f9"))
                else:
                    i_avg = QTableWidgetItem("Sin registros")
                    i_avg.setForeground(QColor("#475569"))
                i_avg.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                table.setItem(row, 0, i_icon)
                table.setItem(row, 1, i_name)
                table.setItem(row, 2, i_type)
                table.setItem(row, 3, i_myprice)
                table.setItem(row, 4, i_avg)
                table.setItem(row, 5, i_best)
                table.setItem(row, 6, i_total)
                table.setItem(row, 7, i_remain)
                table.setItem(row, 8, i_spread)
                table.setItem(row, 9, i_margin)
                table.setItem(row, 10, i_profit)
                table.setItem(row, 11, i_state)

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
        item_0 = table.item(row, 0)
        if not item_0: return
        o_id = item_0.data(Qt.UserRole + 1)
        
        # Buscar la orden correspondiente por su order_id único
        o = next((ord for ord in self.all_orders if ord.order_id == o_id), None)
        if o:
            self.update_detail(o)

    def update_detail(self, o):
        self.lbl_det_item.setText(o.item_name.upper())
        self.lbl_det_type.setText(f"ORDEN DE {'COMPRA' if o.is_buy_order else 'VENTA'} | ID: {o.order_id}")
        
        # Icono detalle
        from PySide6.QtGui import QPixmap, QIcon
        url = ItemMetadataHelper.get_icon_url(o.type_id)
        # Cargamos el icono y lo escalamos preservando el aspecto para evitar deformación
        self.image_loader.load(url, lambda px: self.lbl_det_icon.setPixmap(
            px.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ))

        a = o.analysis
        cost_basis = CostBasisService.instance().get_cost_basis(o.type_id)
        avg_val = cost_basis.average_buy_price if cost_basis else 0.0

        self.lbl_det_my_price.setText(format_isk(o.price, True))
        self.lbl_det_my_avg.setText(format_isk(avg_val, True) if avg_val > 0 else "Sin registros")
        self.lbl_det_best_buy.setText(format_isk(a.best_buy, True))
        self.lbl_det_best_sell.setText(format_isk(a.best_sell, True))
        self.lbl_det_state.setText(a.state.upper())
        
        if a.margin_pct > 0:
            self.lbl_det_margin.setText(f"{a.margin_pct:.1f}%")
            self.lbl_det_margin.setStyleSheet("color: #10b981; font-weight: 800; font-size: 12px;")
        else:
            self.lbl_det_margin.setText(f"{a.margin_pct:.1f}%")
            self.lbl_det_margin.setStyleSheet("color: #ef4444; font-weight: 800; font-size: 12px;")

        self.lbl_det_profit_u.setText(format_isk(a.net_profit_per_unit, True))
        self.lbl_det_profit_total.setText(format_isk(a.net_profit_total, True))

        if o.is_buy_order:
            if not cost_basis:
                reason = "ANÁLISIS POTENCIAL: Esta es una orden de compra activa. La rentabilidad se estima comparando tu precio de compra contra el precio actual de venta en Jita (Spread)."
            else:
                reason = f"ESTRATEGIA DE RECOMPRA: Ya tienes stock a {format_isk(avg_val)}. Esta nueva compra reducirá tu coste promedio si se completa por debajo de ese precio."
        else:
            if cost_basis:
                reason = f"RENTABILIDAD REAL: Ítem adquirido a un promedio de {format_isk(avg_val)}. Beneficio neto basado en tu historial de transacciones."
            else:
                # Sin Mi Promedio para venta
                self.lbl_det_margin.setText("N/A")
                self.lbl_det_profit_u.setText("---")
                self.lbl_det_profit_total.setText("---")
                reason = "CONTROL DE RIESGO: No se ha detectado un precio de compra (Mi Promedio) para este ítem en tu historial reciente. No se muestra rentabilidad para evitar datos falsos."
        
        self.lbl_det_reason.setText(reason)

    def on_double_click(self, item, table):
        row = item.row()
        item_0 = table.item(row, 0)
        if not item_0: return
        t_id = item_0.data(Qt.UserRole)
        item_name = table.item(row, 1).text()
        
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
        item_name = table.item(row, 1).text()
        
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

    def do_inventory_analysis(self):
        # Si ya tenemos caché y está lista, abrir al instante
        if self.inventory_status == "ready" and self.inventory_cache is not None:
            self.on_inventory_ready(self.inventory_cache)
            return
            
        if self.inventory_status == "loading":
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Cargando", "El inventario se está analizando en segundo plano. Por favor, espera un momento...")
            return
            
        if self.inventory_status == "error":
            self.on_inventory_error(self.inventory_error_msg)
            # Resetear para reintentar si el usuario pulsa de nuevo
            self.inventory_status = "idle"
            return

        auth = AuthManager.instance()
        if not auth.current_token:
            self.lbl_status.setText("● ERROR: DEBES ESTAR AUTENTICADO")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800;")
            return

        if self.inv_worker and self.inv_worker.isRunning():
            return

        self.btn_inventory.setEnabled(False)
        self.btn_inventory.setText("ANALIZANDO...")
        self.lbl_status.setText("● CARGANDO ACTIVOS Y PRECIOS...")
        self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800;")

        self.inv_worker = InventoryWorker(auth.char_id, auth.current_token)
        self.inv_worker.finished_data.connect(self.on_inventory_ready)
        self.inv_worker.error.connect(self.on_inventory_error)
        self.inv_worker.start()


    def on_inventory_ready(self, items):
        self.btn_inventory.setEnabled(True)
        self.btn_inventory.setText("ANALIZAR INVENTARIO")
        self.lbl_status.setText(f"● ANÁLISIS DE INVENTARIO COMPLETADO: {len(items)} TIPOS")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800;")
        
        if not items:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Inventario Vacío", "No se encontraron activos valorables en tu inventario actual.")
            return

        dialog = InventoryAnalysisDialog(items, self.image_loader, self)
        dialog.exec()

    def on_inventory_error(self, msg):
        self.btn_inventory.setEnabled(True)
        self.btn_inventory.setText("ANALIZAR INVENTARIO")
        
        from PySide6.QtWidgets import QMessageBox
        
        if msg == "missing_scope":
            self.lbl_status.setText("● ERROR: FALTA PERMISO DE ACTIVOS")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800;")
            QMessageBox.warning(self, "Permiso Faltante", "No tienes el permiso 'esi-assets.read_assets.v1' activo.\nPor favor, vuelve a iniciar sesión con tu personaje para otorgar este permiso.")
        elif msg == "pricing_error":
            self.lbl_status.setText("● ERROR: FALLO DE PRECIOS")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800;")
            QMessageBox.critical(self, "Error de Precios", "No se han podido obtener los precios de mercado necesarios para valorar tu inventario.")
        elif "401" in msg or "expired" in msg.lower():
            self.lbl_status.setText("● ERROR: SESIÓN CADUCADA")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800;")
            QMessageBox.warning(self, "Sesión Caducada", "Tu sesión ha caducado. Por favor, pulsa 'Sincronizar Órdenes' para renovar el acceso.")
        else:
            self.lbl_status.setText(f"● ERROR: {msg.upper()}")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800;")
            QMessageBox.critical(self, "Error de Análisis", f"Ocurrió un error inesperado al analizar el inventario:\n{msg}")
