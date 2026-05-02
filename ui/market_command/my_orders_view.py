import logging # VERSION: 1.1.21-STABLE (Full Restore & Feature Complete)
import time
import threading
import json
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, 
    QGridLayout, QDialog, QMessageBox, QProgressBar, QLineEdit, QComboBox, QMenu,
    QStackedWidget, QToolTip
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap, QAction, QGuiApplication, QPainter, QBrush, QFont, QCursor
from PySide6.QtCharts import QChart, QChartView, QBarSet, QBarSeries, QBarCategoryAxis, QValueAxis, QLegend
from core.eve_icon_service import EveIconService
from ui.common.theme import Theme

from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.market_engine import analyze_character_orders, analyze_inventory
from core.config_manager import load_market_filters, save_ui_config, load_ui_config
from ui.market_command.widgets import ItemInteractionHelper
from core.item_metadata import ItemMetadataHelper
from ui.market_command.performance_view import MarketPerformanceView
from core.cost_basis_service import CostBasisService
from core.tax_service import TaxService
from utils.formatters import format_isk
from ui.market_command.diagnostics_dialog import MarketDiagnosticsDialog
from core.my_orders_diagnostics import format_my_orders_diagnostic_report
from ui.market_command.quick_order_update_dialog import (
    QuickOrderUpdateDialog, format_price_for_clipboard,
)
from core.market_order_pricing import (
    build_order_update_recommendation, 
    recalculate_competitor_price,
    recommend_sell_price,
    recommend_buy_price,
    price_tick,
    _SENTINEL_MAX,
    _SENTINEL_MIN
)
from core.quick_order_update_diagnostics import format_quick_update_report
from core.item_resolver import ItemResolver

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

class ClickableIcon(QLabel):
    """Icono que detecta doble click para abrir mercado."""
    double_clicked = Signal(int, str) # type_id, name
    
    def __init__(self, type_id, name, parent=None):
        super().__init__(parent)
        self.type_id = type_id
        self.item_name = name
        self.setCursor(Qt.PointingHandCursor)
        
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.type_id, self.item_name)

# --- Workers ---

class SyncWorker(QThread):
    finished_data = Signal(list)
    initial_data_ready = Signal(list)  # Phase 1: Fast render with cached data
    status_update = Signal(str, int)
    location_ready = Signal(int)
    error = Signal(str)

    def __init__(self, char_id, token):
        super().__init__()
        self.char_id = char_id
        self.token = token
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            from core.progress_tracker import ProgressTracker
            tracker = ProgressTracker(
                callback=lambda p, m: self.status_update.emit(m, p),
                task_name="OrdersSync"
            )
            client = ESIClient()
            
            # ──────────────────────────────────────────────────────────────────
            # FASE 1 — CARGA RÁPIDA (Snapshot ESI + Caches locales)
            # ──────────────────────────────────────────────────────────────────
            tracker.set_phase("CONECTANDO CON ESI...", 0, 5)
            
            tracker.set_phase("DESCARGANDO ÓRDENES...", 5, 20)
            orders = client.character_orders(self.char_id, self.token)
            if not orders:
                tracker.finish("Sin órdenes activas")
                self.finished_data.emit([])
                return
            
            if not self.is_running: return

            # Cargar promedios cacheados (WAC) para render inmediato
            tracker.set_phase("CARGANDO CACHÉ...", 20, 25)
            CostBasisService.instance().load_from_file(self.char_id)
            CostBasisService.instance()._rebuild_cache_from_map()
            
            type_ids = list(set(o['type_id'] for o in orders))
            
            # Intentar usar nombres cacheados
            item_resolver = ItemResolver.instance()
            item_names = {}
            for tid in type_ids:
                info = item_resolver.cache.get(tid)
                if info and 'name' in info:
                    item_names[tid] = info['name']
            
            # Usar mercado cacheado
            from core.market_orders_cache import MarketOrdersCache
            cached_market = MarketOrdersCache.instance().get(10000002) or []
            
            tracker.set_phase("RENDERIZADO INICIAL...", 25, 30)
            initial_analyzed = analyze_character_orders(
                orders, cached_market, item_names, load_market_filters(), 
                char_id=self.char_id, token=self.token
            )
            self.initial_data_ready.emit(initial_analyzed)
            
            if not self.is_running: return

            # ──────────────────────────────────────────────────────────────────
            # FASE 2 — HIDRATACIÓN COMPLETA (ESI Deep Sync)
            # ──────────────────────────────────────────────────────────────────
            
            tracker.set_phase("SINCRONIZANDO TAXES...", 30, 40)
            TaxService.instance().refresh_from_esi(self.char_id, self.token)
            
            if not self.is_running: return

            tracker.set_phase("LOCALIZANDO PERSONAJE...", 40, 50)
            loc_res = client.character_location(self.char_id, self.token)
            if loc_res and loc_res != "missing_scope":
                loc_id = loc_res.get('station_id') or loc_res.get('structure_id') or 0
                if loc_id:
                    self.location_ready.emit(loc_id)

            if not self.is_running: return

            tracker.set_phase("ACTUALIZANDO PRECIOS DE MERCADO...", 50, 75)
            all_market_orders = client.market_orders_for_types(10000002, type_ids)
            
            if not all_market_orders and type_ids:
                tracker.update(50, message="Fallback: Mercado regional...")
                all_market_orders = client.market_orders(10000002, force_refresh=True)

            if not self.is_running: return

            tracker.set_phase("SINCRONIZANDO PROMEDIOS (WAC)...", 75, 90)
            CostBasisService.instance().refresh_from_esi(self.char_id, self.token)
            
            if not self.is_running: return

            tracker.set_phase("RESOLVIENDO NOMBRES...", 90, 95)
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            tracker.set_phase("FINALIZANDO ANÁLISIS...", 95, 100)
            final_analyzed = analyze_character_orders(
                orders, all_market_orders, item_names, load_market_filters(), 
                char_id=self.char_id, token=self.token
            )
            
            tracker.finish("ACTUALIZACIÓN COMPLETA")
            self.finished_data.emit(final_analyzed)
            
        except Exception as e:
            _log.error(f"[SYNC WORKER ERR] {e}", exc_info=True)
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
            from core.progress_tracker import ProgressTracker
            tracker = ProgressTracker(
                callback=lambda p, m: self.status_update.emit(m, p),
                task_name="InventorySync"
            )
            client = ESIClient()
            
            tracker.set_phase("LOCALIZANDO...", 0, 15)
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
            
            tracker.set_phase("DESCARGANDO ACTIVOS...", 15, 50)
            assets = client.character_assets(self.char_id, self.token)
            if assets == "missing_scope":
                self.error.emit("missing_scope")
                return
            if not assets:
                tracker.finish("Sin activos")
                self.finished_data.emit([])
                return
            
            # Filtrar activos no tangibles (slots, etc)
            filtered = [a for a in assets if 'slot' not in a.get('location_flag', '').lower()]
            if curr_loc_id:
                filtered = [a for a in assets if a.get('location_id') == curr_loc_id]
            
            if not filtered:
                tracker.finish("Sin activos en esta ubicación")
                self.finished_data.emit([])
                return

            tracker.set_phase("BUSCANDO PRECIOS...", 50, 75)
            type_ids = list(set(a['type_id'] for a in filtered))
            all_mo = client.market_orders(10000002)
            
            tracker.update(50, message="Resolviendo nombres...")
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            tracker.set_phase("CALCULANDO WAC...", 75, 95)
            CostBasisService.instance().refresh_from_esi(self.char_id, self.token, current_assets=assets)
            
            tracker.set_phase("FINALIZANDO...", 95, 100)
            analyzed = analyze_inventory(
                filtered, all_mo, item_names, load_market_filters(), 
                char_id=self.char_id, token=self.token
            )
            tracker.finish("Listo")
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
            from core.progress_tracker import ProgressTracker
            tracker = ProgressTracker(
                callback=lambda p, m: self.status_update.emit(m, p),
                task_name="TradeProfits"
            )
            client = ESIClient()
            
            tracker.set_phase("DESCARGANDO TRANSACCIONES...", 0, 60)
            txs = client.wallet_transactions(self.char_id, self.token)
            if txs == "missing_scope":
                self.error.emit("Falta permiso: esi-wallet.read_character_wallet.v1")
                return
            if not txs:
                tracker.finish("Sin transacciones")
                self.finished_data.emit([])
                return
            
            tracker.set_phase("CALCULANDO RENTABILIDAD HISTÓRICA...", 60, 100, total=len(txs))
            sorted_tx = sorted(txs, key=lambda x: x['date'])
            trades = []
            stock_map = {} # type_id -> {qty, cost}
            
            type_ids = list(set(t['type_id'] for t in sorted_tx))
            tracker.update(0, message="Resolviendo nombres de ítems...")
            names_data = client.universe_names(type_ids)
            item_names = {n['id']: n['name'] for n in names_data}
            
            tracker.update(5, message="Sincronizando impuestos...")
            tx_service = TaxService.instance()
            tx_service.refresh_from_esi(self.char_id, self.token)
            
            for i, t in enumerate(sorted_tx):
                tid = t['type_id']
                qty = t['quantity']
                price = t['unit_price']
                is_buy = t.get('is_buy', False)
                loc_id = t.get('location_id', 0)
                
                # Obtener TAXES EFECTIVAS para esta ubicación específica
                s_tax_pct, b_fee_pct, source, debug = tx_service.get_effective_taxes(self.char_id, loc_id, self.token)
                
                if tid not in stock_map:
                    stock_map[tid] = {'qty': 0, 'cost': 0.0}
                curr = stock_map[tid]
                
                if is_buy:
                    # Compra: Aplicar broker fee efectivo
                    total_buy = qty * price * (1.0 + b_fee_pct/100.0)
                    curr['qty'] += qty
                    curr['cost'] += total_buy
                else:
                    # Venta: Calcular beneficio contra WAC usando fees y taxes efectivos
                    if curr['qty'] > 0:
                        wac_unit = curr['cost'] / curr['qty']
                        cost_matched = qty * wac_unit
                        
                        gross_sell = qty * price
                        fees_amt = gross_sell * (b_fee_pct/100.0 + s_tax_pct/100.0)
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
                
                if i % 10 == 0:
                    tracker.update(i + 1, message=f"Analizando transacción {i+1}/{len(sorted_tx)}")
            
            tracker.finish("Análisis completado")
            self.finished_data.emit(list(reversed(trades)))
        except Exception as e:
            _log.error(f"[PROFITS ERR] {e}", exc_info=True)
            self.error.emit(str(e))

# --- Diálogos ---

class InventoryAnalysisDialog(QDialog):
    def __init__(self, items, loc_name, parent=None):
        super().__init__(parent)
        self.items = items
        self.loc_name = loc_name
        self.icon_service = EveIconService.instance()
        self._image_generation = 0
        _log.info(f"[INVENTORY] Dialog initialized for loc_name={loc_name}")
        self.setWindowTitle("INVENTARIO - VALOR DE ACTIVOS")
        self.setMinimumSize(1150, 750)
        self.setStyleSheet(Theme.get_qss("my_orders"))
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
        self.val_lbl = QLabel(format_isk(total_val))
        self.val_lbl.setObjectName("MetricValueSuccess")
        hl.addWidget(self.val_lbl)

        # Refresh button
        self._refresh_btn = QPushButton("↻ Actualizar")
        self._refresh_btn.setStyleSheet(
            "QPushButton { background: #1e293b; color: #94a3b8; border: 1px solid #334155; "
            "border-radius: 4px; font-size: 9px; font-weight: 800; padding: 4px 10px; }"
            "QPushButton:hover { background: #334155; color: #f1f5f9; }"
            "QPushButton:disabled { color: #475569; }"
        )
        self._refresh_btn.clicked.connect(self._do_refresh)
        hl.addWidget(self._refresh_btn)
        layout.addWidget(header)

        # Tabla
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ÍTEM", "CANTIDAD", "MI PROMEDIO", "P. UNIT NETO", "PROFIT DE VENTA", "VALOR %", "RECOMENDACIÓN", "MOTIVO"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(32, 32))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self.on_double_click)
        self.table.horizontalHeader().sectionResized.connect(self.save_layout)
        layout.addWidget(self.table)

        self._populate_table(self.items)

    def _populate_table(self, items):
        total_val = sum(item.analysis.est_total_value for item in items)
        self.val_lbl.setText(format_isk(total_val))

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))

        self._image_generation += 1
        gen = self._image_generation

        for row, item in enumerate(items):
            a = item.analysis
            avg = getattr(item, "_avg_buy", 0.0)
            profit_t = getattr(item, "_net_profit_total", 0.0)

            cost_total = avg * item.quantity
            roi = (profit_t / cost_total * 100) if cost_total > 0 else -1e18

            i_name = QTableWidgetItem(item.item_name)
            i_name.setData(Qt.UserRole, item.type_id)

            pix = self.icon_service.get_icon(
                item.type_id, 32,
                callback=lambda p, tid=item.type_id, row=row, gen=gen: self._load_icon_into_table_item(self.table, row, 0, tid, p, gen)
            )
            i_name.setIcon(QIcon(pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            _log.debug(f"[INVENTORY ICON] Requesting {item.type_id} for row {row}")

            i_qty = NumericTableWidgetItem(f"{item.quantity:,}", item.quantity)
            i_avg = NumericTableWidgetItem(format_isk(avg) if avg > 0 else "Sin registros", avg)
            i_price = NumericTableWidgetItem(format_isk(a.est_net_sell_unit), a.est_net_sell_unit)

            i_profit = NumericTableWidgetItem(format_isk(profit_t) if avg > 0 else "Sin registros", profit_t if avg > 0 else -1e18)
            if avg > 0:
                i_profit.setForeground(QColor(Theme.TABLE_PROFIT_POSITIVE if profit_t >= 0 else Theme.TABLE_PROFIT_NEGATIVE))

            pct = (a.est_total_value / total_val * 100) if total_val > 0 else 0
            i_pct = NumericTableWidgetItem(f"{pct:.1f}%", pct)

            rec_text = a.recommendation.upper()
            i_rec = SemanticTableWidgetItem(rec_text)
            if "VEND" in rec_text:
                i_rec.setForeground(QColor("#10b981"))  # green — VENDER
            elif "MANT" in rec_text:
                i_rec.setForeground(QColor("#3b82f6"))  # blue — MANTENER
            else:
                i_rec.setForeground(QColor("#94a3b8"))

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

            for i, it in enumerate([i_name, i_qty, i_avg, i_price, i_profit, i_pct, i_rec, i_reason]):
                it.setTextAlignment(Qt.AlignCenter)
                it.setData(Qt.UserRole, item.type_id)
                self.table.setItem(row, i, it)

        self.table.setSortingEnabled(True)

    def on_double_click(self, item):
        row = item.row()
        col = item.column()
        tid = None
        name = ""

        for c in range(self.table.columnCount()):
            it = self.table.item(row, c)
            if it:
                if not tid: tid = it.data(Qt.UserRole)
                if c == 0: name = it.text()

        # RECOMENDACIÓN column (col 6): VENDER opens market; MANTENER is no-op
        if col == 6:
            rec_text = item.text().upper()
            if "VEND" in rec_text and tid:
                _log.info(f"[INVENTORY] VENDER action — opening market for type_id={tid}")
                ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, None)
            elif "MANT" in rec_text:
                _log.debug(f"[INVENTORY] MANTENER — no action required for type_id={tid}")
            return

        if tid:
            _log.info(f"[OPEN MARKET] inventory double_clicked row={row} type_id={tid}")
            ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, None)
        else:
            _log.warning(f"[OPEN MARKET] inventory double_clicked without type_id row={row}")

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; }"
            "QMenu::item:selected { background: #334155; }"
        )
        act_copy_cell = QAction("Copiar celda", self)
        act_copy_cell.triggered.connect(lambda: QGuiApplication.clipboard().setText(item.text()))
        menu.addAction(act_copy_cell)

        name_item = self.table.item(row, 0)
        if name_item and name_item.text():
            act_copy_name = QAction("Copiar nombre del ítem", self)
            act_copy_name.triggered.connect(lambda: QGuiApplication.clipboard().setText(name_item.text()))
            menu.addAction(act_copy_name)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _do_refresh(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if not t:
            return
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Cargando...")
        self._refresh_worker = InventoryWorker(auth.char_id, t)
        self._refresh_worker.finished_data.connect(self._on_refresh_done)
        self._refresh_worker.start()

    def _on_refresh_done(self, data):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↻ Actualizar")
        if data:
            self.items = data
            self._populate_table(data)
        else:
            _log.info("[INVENTORY] Refresh returned empty data")

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

    def _load_icon_into_table_item(self, table, row, col, type_id, pixmap, generation):
        """Callback robusto para cargar iconos en la tabla de inventario."""
        try:
            if generation != self._image_generation: return
            if table is None: return
            
            # 1. Intento directo por fila/columna
            item = table.item(row, col)
            if item and item.data(Qt.UserRole) == type_id:
                if item.text().strip() == "-": item.setText("") # Limpiar placeholder si existe
                item.setIcon(QIcon(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                return
                
            # 2. Fallback: la tabla se ha ordenado, buscar por type_id
            for r in range(table.rowCount()):
                it = table.item(r, col)
                if it and it.data(Qt.UserRole) == type_id:
                    if it.text().strip() == "-": it.setText("") # Limpiar placeholder si existe
                    it.setIcon(QIcon(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                    _log.debug(f"[INVENTORY ICON] Applied {type_id} to fallback row {r}")
                    break
        except Exception as e:
            _log.error(f"[INVENTORY ICON ERR] {e}")

class TradeProfitsDialog(QDialog):
    def __init__(self, char_id, token, parent=None):
        super().__init__(parent)
        self.char_id = char_id
        self.token = token
        self.icon_service = EveIconService.instance()
        self._image_generation = 0
        self.all_trades = []
        self.filtered_trades = []
        self.page_size = 50
        self.current_page = 0
        self.setWindowTitle("HISTORIAL DE TRADE PROFITS")
        self.setMinimumSize(1200, 750)
        self.setStyleSheet(Theme.get_qss("my_orders"))
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        self.setStyleSheet(Theme.get_qss("my_orders"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        f_frame = QFrame()
        f_frame.setObjectName("TacticalPanel")
        fl = QHBoxLayout(f_frame)
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filtrar por item...")
        self.txt_filter.setFixedWidth(200)
        self.txt_filter.textChanged.connect(self.apply_filters)
        
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Todos los resultados", "Solo Ganancias", "Solo Pérdidas"])
        self.cmb_mode.currentIndexChanged.connect(self.apply_filters)
        
        self.btn_global = QPushButton("VISTA GLOBAL")
        self.btn_global.setObjectName("SecondaryButton")
        self.btn_global.setFixedWidth(120)
        self.btn_global.clicked.connect(self.toggle_global_view)
        
        self.btn_customize = QPushButton("PERSONALIZAR")
        self.btn_customize.setObjectName("SecondaryButton")
        self.btn_customize.setFixedWidth(100)
        self.btn_customize.clicked.connect(self.on_customize_clicked)
        
        fl.addWidget(QLabel("FILTRAR:")); fl.addWidget(self.txt_filter)
        fl.addSpacing(20); fl.addWidget(QLabel("MODO:")); fl.addWidget(self.cmb_mode)
        fl.addStretch()
        fl.addWidget(self.btn_customize)
        fl.addWidget(self.btn_global)
        fl.addWidget(self.btn_global)
        
        layout.addWidget(f_frame)
        
        self.stack = QStackedWidget()
        
        # Página 1: Tabla de Transacciones (Original)
        self.table_page = QWidget()
        table_layout = QVBoxLayout(self.table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["FECHA", "ÍTEM", "UNIDADES", "P. COMPRA", "P. VENTA", "TOTAL COMPRA", "TOTAL VENTA", "FEES + TAX", "MARGEN %", "PROFIT NETO"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(f"QTableWidget {{ background: {Theme.BG_MAIN}; color: {Theme.TEXT_MAIN}; border: none; font-size: 11px; }} QHeaderView::section {{ background: {Theme.BG_NAV}; color: {Theme.TEXT_DIM}; font-weight: 800; border: none; padding: 10px; }}")
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(24, 24))
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDoubleClicked.connect(self.on_double_click)
        table_layout.addWidget(self.table)
        
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("ANTERIOR")
        self.btn_next = QPushButton("SIGUIENTE")
        self.lbl_page = QLabel("Página 1")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        nav.addWidget(self.btn_prev); nav.addStretch(); nav.addWidget(self.lbl_page); nav.addStretch(); nav.addWidget(self.btn_next)
        table_layout.addLayout(nav)
        
        self.stack.addWidget(self.table_page)
        
        # Página 2: Vista Global (Dashboard Premium)
        self.global_page = QWidget()
        self.global_layout = QVBoxLayout(self.global_page)
        self.global_layout.setContentsMargins(10, 10, 10, 10)
        self.global_layout.setSpacing(20)
        
        # Tarjetas de Resumen (Métricas Superiores)
        self.metrics_layout = QHBoxLayout()
        self.card_total = self._create_metric_card("NET PROFIT TOTAL", "0.00 ISK", "Beneficio consolidado")
        self.card_winner = self._create_metric_card("TOP WINNER", "---", "Mayor ganancia única")
        self.card_loser = self._create_metric_card("TOP LOSER", "---", "Mayor pérdida única")
        self.card_count = self._create_metric_card("TOTAL TRADES", "0", "Operaciones cerradas")
        
        self.metrics_layout.addWidget(self.card_total)
        self.metrics_layout.addWidget(self.card_winner)
        self.metrics_layout.addWidget(self.card_loser)
        self.metrics_layout.addWidget(self.card_count)
        self.global_layout.addLayout(self.metrics_layout)
        
        # Área de Contenido (Gráfico + Ranking Lateral)
        self.content_h = QHBoxLayout()
        self.content_h.setSpacing(15)
        
        # Contenedor del Gráfico + Iconos
        self.chart_container = QFrame()
        self.chart_container.setObjectName("AnalyticBox")
        chart_v = QVBoxLayout(self.chart_container)
        chart_v.setContentsMargins(10, 10, 10, 5)
        chart_v.setSpacing(0)
        
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setStyleSheet("background: transparent; border: none;")
        chart_v.addWidget(self.chart_view)
        
        # Fila de Iconos debajo del chart
        self.icon_row_frame = QFrame()
        self.icon_row_frame.setFixedHeight(35)
        self.icon_row_frame.setStyleSheet("background: transparent; border: none;")
        self.icon_row_layout = QHBoxLayout(self.icon_row_frame)
        self.icon_row_layout.setContentsMargins(55, 0, 15, 5) # Ajuste manual inicial para el eje Y
        self.icon_row_layout.setSpacing(2)
        chart_v.addWidget(self.icon_row_frame)
        
        self.content_h.addWidget(self.chart_container, 2)
        
        # Panel de Ranking Lateral
        self.ranking_panel = QFrame()
        self.ranking_panel.setFixedWidth(260)
        self.ranking_panel.setObjectName("AnalyticBox")
        ranking_v = QVBoxLayout(self.ranking_panel)
        ranking_v.setContentsMargins(15, 15, 15, 15)
        
        rank_title = QLabel("TOP 20 RENTABILIDAD")
        rank_title.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        ranking_v.addWidget(rank_title)
        
        self.ranking_table = QTableWidget(0, 2)
        self.ranking_table.setHorizontalHeaderLabels(["ÍTEM", "PROFIT NETO"])
        self.ranking_table.horizontalHeader().setVisible(False)
        self.ranking_table.verticalHeader().setVisible(False)
        self.ranking_table.setShowGrid(False)
        self.ranking_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ranking_table.setStyleSheet(f"background: transparent; color: {Theme.TEXT_MAIN}; border: none; font-size: 11px;")
        self.ranking_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ranking_table.setIconSize(QSize(24, 24))
        self.ranking_table.itemDoubleClicked.connect(self.on_ranking_double_click)
        
        ranking_v.addWidget(self.ranking_table)
        self.content_h.addWidget(self.ranking_panel, 1)
        
        self.global_layout.addLayout(self.content_h, 1)
        
        self.stack.addWidget(self.global_page)
        
        layout.addWidget(self.stack)

    def _create_metric_card(self, title, value, subtitle):
        card = QFrame()
        card.setFixedHeight(110)
        card.setStyleSheet(f"background: {Theme.BG_PANEL}; border-radius: 10px; border: 1px solid {Theme.BORDER}; padding: 12px;")
        l = QVBoxLayout(card)
        l.setSpacing(2)
        
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("color: #94a3b8; font-size: 8px; font-weight: 800; letter-spacing: 1.2px;")
        v_lbl = QLabel(value)
        v_lbl.setStyleSheet("color: #f1f5f9; font-size: 15px; font-weight: 900;")
        s_lbl = QLabel(subtitle)
        s_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 500;")
        s_lbl.setWordWrap(True)
        
        l.addWidget(t_lbl); l.addWidget(v_lbl); l.addWidget(s_lbl)
        card.setProperty("v_label", v_lbl) 
        card.setProperty("s_label", s_lbl)
        return card

    def _format_short_isk(self, val):
        abs_val = abs(val)
        prefix = "-" if val < 0 else ""
        if abs_val >= 1_000_000_000:
            return f"{prefix}{abs_val/1_000_000_000:.1f}B"
        if abs_val >= 1_000_000:
            return f"{prefix}{abs_val/1_000_000:.1f}M"
        if abs_val >= 1_000:
            return f"{prefix}{abs_val/1_000:.0f}K"
        return f"{prefix}{abs_val:,.0f}"

    def load_data(self):
        self.worker = TradeProfitsWorker(self.char_id, self.token)
        self.worker.finished_data.connect(self.on_data)
        self.worker.start()

    def on_data(self, data):
        self.all_trades = data
        self.apply_filters()
        if self.stack.currentIndex() == 1:
            self.update_chart()

    def on_customize_clicked(self):
        from ui.common.theme_customizer_dialog import ThemeCustomizerDialog
        dialog = ThemeCustomizerDialog(view_scope="my_orders", parent=self)
        dialog.themeUpdated.connect(self.refresh_theme)
        dialog.exec()

    def toggle_global_view(self):
        if self.stack.currentIndex() == 0:
            # Ir a Global
            self.stack.setCurrentIndex(1)
            self.btn_global.setText("TABLA TRADES")
            self.update_chart()
        else:
            # Ir a Tabla
            self.stack.setCurrentIndex(0)
            self.btn_global.setText("VISTA GLOBAL")

    def on_ranking_double_click(self, item):
        row = item.row()
        it_name = self.ranking_table.item(row, 0)
        if it_name:
            tid = it_name.data(Qt.UserRole)
            name = it_name.text()
            if tid:
                self.open_market_for_item(tid, name, "ranking_table")

    def on_bar_double_clicked(self, index, barset):
        if hasattr(self, '_current_chart_items') and index < len(self._current_chart_items):
            item = self._current_chart_items[index]
            self.open_market_for_item(item['type_id'], item['name'], "chart_bar")

    def on_icon_double_clicked(self, tid, name):
        self.open_market_for_item(tid, name, "chart_icon")

    def open_market_for_item(self, tid, name, source):
        _log.info(f"[TRADE PROFITS OPEN MARKET] source={source} type_id={tid} item={name}")
        try:
            from ui.market_command.widgets import ItemInteractionHelper
            ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, None)
        except Exception as e:
            _log.error(f"[TRADE PROFITS OPEN MARKET ERROR] {e}")

    def on_bar_hovered(self, status, index, barset):
        if status:
            if not hasattr(self, '_current_chart_items') or index >= len(self._current_chart_items):
                return
            
            item = self._current_chart_items[index]
            from core.cost_basis_service import CostBasisService
            wac = CostBasisService.instance()
            cb = wac.get_cost_basis(item['type_id'])
            stock = wac.stock_map.get(str(item['type_id']), {}).get('qty', 0)
            
            avg_profit = item['net_profit'] / item['count'] if item['count'] > 0 else 0
            
            tooltip = f"<b>{item['name']}</b><br/>"
            tooltip += f"<hr/>"
            tooltip += f"Profit Neto: <span style='color:{'#10b981' if item['net_profit'] >= 0 else '#ef4444'}'>{format_isk(item['net_profit'])}</span><br/>"
            tooltip += f"Operaciones: {item['count']}<br/>"
            tooltip += f"Avg Profit/Trade: {format_isk(avg_profit)}<br/>"
            tooltip += f"<hr/>"
            tooltip += f"Stock Actual: {'SÍ (' + str(stock) + ')' if stock > 0 else 'NO'}<br/>"
            if cb:
                tooltip += f"Coste Medio (WAC): {format_isk(cb.average_buy_price)}<br/>"
            else:
                tooltip += f"Coste Medio: N/A<br/>"
                
            QToolTip.showText(QCursor.pos(), tooltip, self.chart_view)
        else:
            QToolTip.hideText()

    def update_chart(self):
        if not self.all_trades:
            return

        # 1. Calcular Métricas Globales
        total_profit = sum(t['profit'] for t in self.all_trades)
        max_win = max([t['profit'] for t in self.all_trades]) if self.all_trades else 0
        max_loss = min([t['profit'] for t in self.all_trades]) if self.all_trades else 0
        trade_count = len(self.all_trades)
        
        # Encontrar items responsables de top/worst
        top_win_item = "---"
        top_loss_item = "---"
        for t in self.all_trades:
            if t['profit'] == max_win: top_win_item = t['name']
            if t['profit'] == max_loss: top_loss_item = t['name']

        # Actualizar Tarjetas
        self.card_total.property("v_label").setText(format_isk(total_profit))
        self.card_total.property("v_label").setStyleSheet(f"color: {'#10b981' if total_profit >= 0 else '#ef4444'}; font-size: 15px; font-weight: 900;")
        
        self.card_winner.property("v_label").setText(format_isk(max_win))
        self.card_winner.property("s_label").setText(f"Responsable: {top_win_item}")
        
        self.card_loser.property("v_label").setText(format_isk(max_loss))
        self.card_loser.property("s_label").setText(f"Responsable: {top_loss_item}")
        
        self.card_count.property("v_label").setText(str(trade_count))
        
        # 2. Agrupar por item para el gráfico
        stats = {}
        for t in self.all_trades:
            tid = t['type_id']
            if tid not in stats:
                stats[tid] = {'type_id': tid, 'name': t['name'], 'net_profit': 0.0, 'count': 0}
            stats[tid]['net_profit'] += t['profit']
            stats[tid]['count'] += 1

        sorted_stats = sorted(stats.values(), key=lambda x: x['net_profit'], reverse=True)
        
        # Tomar los 10 mejores y los 10 peores
        if len(sorted_stats) > 20:
            top_items = sorted_stats[:10] + sorted_stats[-10:]
        else:
            top_items = sorted_stats

        self._current_chart_items = top_items
        if not top_items:
            return

        chart = QChart()
        chart.setTitle("RANKING DE RENTABILIDAD POR ÍTEM")
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setBackgroundVisible(False)
        chart.setTitleBrush(QBrush(QColor("#f1f5f9")))
        chart.setTitleFont(QFont("Inter", 12, QFont.Bold))

        series = QBarSeries()
        
        # Usamos dos sets para diferenciar colores
        set_gain = QBarSet("Ganancias")
        set_loss = QBarSet("Pérdidas")
        set_gain.setColor(QColor("#10b981"))
        set_loss.setColor(QColor("#ef4444"))
        
        categories = []
        for item in top_items:
            val = item['net_profit']
            if val >= 0:
                set_gain.append(val)
                set_loss.append(0)
            else:
                set_gain.append(0)
                set_loss.append(val)
                
            name = item['name']
            if len(name) > 15: name = name[:13] + ".."
            categories.append(name)

        series.append(set_gain)
        series.append(set_loss)
        series.hovered.connect(self.on_bar_hovered)
        series.doubleClicked.connect(self.on_bar_double_clicked)
        chart.addSeries(series)

        axisX = QBarCategoryAxis()
        axisX.append(categories)
        axisX.setLabelsColor(QColor("#94a3b8"))
        axisX.setLabelsAngle(-45)
        axisX.setGridLineVisible(False)
        chart.addAxis(axisX, Qt.AlignBottom)
        series.attachAxis(axisX)

        axisY = QValueAxis()
        axisY.setLabelsColor(QColor("#94a3b8"))
        axisY.setGridLineColor(QColor("#1e293b"))
        axisY.setLabelFormat("%.0f") 
        chart.addAxis(axisY, Qt.AlignLeft)
        series.attachAxis(axisY)

        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.legend().setLabelColor(QColor("#94a3b8"))
        chart.legend().setMarkerShape(QLegend.MarkerShapeCircle)

        self.chart_view.setChart(chart)
        
        # Ajustar márgenes para alinear iconos con el PlotArea (aprox)
        # El eje Y suele ocupar unos 60-70px con números largos.
        self.icon_row_layout.setContentsMargins(60, 0, 20, 5)
        
        # 3. Limpiar y Repoblar Iconos debajo de las barras
        while self.icon_row_layout.count():
            child = self.icon_row_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        for item in top_items:
            tid = item['type_id']
            i_lbl = ClickableIcon(tid, item['name'])
            i_lbl.setFixedSize(24, 24)
            i_lbl.setToolTip(f"<b>{item['name']}</b><br/>Doble click para abrir mercado")
            i_lbl.setStyleSheet("background: transparent; border: none;")
            i_lbl.double_clicked.connect(self.on_icon_double_clicked)
            
            pix = self.icon_service.get_icon(tid, 24)
            if pix and not pix.isNull():
                i_lbl.setPixmap(pix.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                i_lbl.setStyleSheet("background: #1e293b; border-radius: 4px;")
            
            self.icon_row_layout.addWidget(i_lbl, 0, Qt.AlignCenter)
        
        # 4. Actualizar Tabla de Ranking
        self.ranking_table.setRowCount(0)
        self.ranking_table.setRowCount(len(top_items))
        self._image_generation += 1
        gen = self._image_generation
        
        for r, item in enumerate(top_items):
            tid = item.get('type_id')
            
            i_item = QTableWidgetItem(item['name'])
            i_item.setData(Qt.UserRole, tid)
            
            if tid:
                pix = self.icon_service.get_icon(
                    tid, 24,
                    callback=lambda p, t_id=tid, row=r, g=gen: 
                        self._load_icon_into_table_item(self.ranking_table, row, 0, t_id, p, g)
                )
                if pix and not pix.isNull():
                    i_item.setIcon(QIcon(pix.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

            i_profit = QTableWidgetItem(self._format_short_isk(item['net_profit']))
            i_profit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            i_profit.setForeground(QColor("#10b981" if item['net_profit'] >= 0 else "#ef4444"))
            
            # Tooltip rico para el ranking
            avg_p = item['net_profit'] / item['count'] if item['count'] > 0 else 0
            tt = f"Ítem: {item['name']}\nProfit Neto: {format_isk(item['net_profit'])}\nTrades: {item['count']}\nAvg/Trade: {format_isk(avg_p)}"
            i_item.setToolTip(tt)
            i_profit.setToolTip(tt)
            
            self.ranking_table.setItem(r, 0, i_item)
            self.ranking_table.setItem(r, 1, i_profit)

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
        self._image_generation += 1
        gen = self._image_generation
        start = self.current_page * self.page_size
        end = (self.current_page + 1) * self.page_size
        page_items = self.filtered_trades[start:end]
        self.table.setRowCount(len(page_items))
        
        for r, t in enumerate(page_items):
            dt = t['date'].replace('T', ' ').replace('Z', '')
            i_date = QTableWidgetItem(dt)
            
            # Columna ÍTEM (Icono + Nombre)
            i_item = QTableWidgetItem(t['name'])
            i_item.setData(Qt.UserRole, t['type_id'])
            
            pix = self.icon_service.get_icon(
                t['type_id'], 24,
                callback=lambda p, tid=t['type_id'], row=r, gen=gen: self._load_icon_into_table_item(self.table, row, 1, tid, p, gen)
            )
            i_item.setIcon(QIcon(pix.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            _log.debug(f"[TRADES ICON] Requesting {t['type_id']} for row {r}")
            
            i_qty = NumericTableWidgetItem(f"{t['qty']:,}", t['qty'])
            i_buy_u = NumericTableWidgetItem(format_isk(t['buy_unit']), t['buy_unit'])
            i_sell_u = NumericTableWidgetItem(format_isk(t['sell_unit']), t['sell_unit'])
            i_buy_t = NumericTableWidgetItem(format_isk(t['buy_total']), t['buy_total'])
            i_sell_t = NumericTableWidgetItem(format_isk(t['sell_total']), t['sell_total'])
            i_fees = NumericTableWidgetItem(format_isk(t['fees']), t['fees'])
            
            # Margen
            m_col = QColor("#10b981" if t['margin'] > 15 else ("#f59e0b" if t['margin'] >= 0 else "#ef4444"))
            i_mar = NumericTableWidgetItem(f"{t['margin']:.1f}%", t['margin'])
            i_mar.setForeground(m_col)
            
            # Profit Neto
            prof_val = t['profit']
            i_prof = NumericTableWidgetItem(format_isk(prof_val), prof_val)
            if prof_val > 0: i_prof.setForeground(QColor("#10b981"))
            elif prof_val < 0: i_prof.setForeground(QColor("#ef4444"))
            else: i_prof.setForeground(QColor("#94a3b8"))
            
            # Montar fila (10 columnas exactas)
            cells = [i_date, i_item, i_qty, i_buy_u, i_sell_u, i_buy_t, i_sell_t, i_fees, i_mar, i_prof]
            for col, it in enumerate(cells):
                it.setTextAlignment(Qt.AlignCenter)
                it.setData(Qt.UserRole, t['type_id']) # Redundancia
                self.table.setItem(r, col, it)
            
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

    def _load_icon_into_table_item(self, table, row, col, type_id, pixmap, generation):
        """Callback robusto para cargar iconos en la tabla de trades."""
        try:
            if generation != self._image_generation: return
            if table is None: return
            
            # 1. Intento directo
            item = table.item(row, col)
            if item and item.data(Qt.UserRole) == type_id:
                if item.text().strip() == "-": item.setText("") # Limpiar placeholder si existe
                item.setIcon(QIcon(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                return
                
            # 2. Fallback
            for r in range(table.rowCount()):
                it = table.item(r, col)
                if it and it.data(Qt.UserRole) == type_id:
                    if it.text().strip() == "-": it.setText("") # Limpiar placeholder si existe
                    it.setIcon(QIcon(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                    _log.debug(f"[TRADES ICON] Applied {type_id} to fallback row {r}")
                    break
        except Exception as e:
            _log.error(f"[TRADES ICON ERR] {e}")

    def show_context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        item = self.table.item(idx.row(), 1) # Columna ÍTEM
        if not item: return
        menu = QMenu(self)
        copy_act = QAction("Copiar nombre", self)
        copy_act.triggered.connect(lambda: QGuiApplication.clipboard().setText(item.text()))
        menu.addAction(copy_act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def on_double_click(self, item):
        row = item.row()
        tid = None
        name = ""
        
        for col in range(self.table.columnCount()):
            it = self.table.item(row, col)
            if it:
                if not tid: tid = it.data(Qt.UserRole)
                if col == 1: name = it.text()

        import logging
        log = logging.getLogger('eve.interaction')
        if tid:
            log.info(f"[OPEN MARKET] trades double_clicked row={row} type_id={tid}")
            ItemInteractionHelper.open_market_with_fallback(ESIClient(), AuthManager.instance().char_id, tid, name, None)
        else:
            log.warning(f"[OPEN MARKET] trades double_clicked without type_id row={row}")

# --- Main View ---

class MarketMyOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MyOrdersViewRoot")
        self.worker = None
        self.all_orders = []
        self.current_location_id = 0
        self.icon_service = EveIconService.instance()
        self._image_generation = 0
        self.spinner_chars = ["|", "/", "-", "\\"]
        self.spinner_idx = 0
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._update_spinner)
        
        AuthManager.instance().authenticated.connect(self.on_authenticated)
        self.setup_ui()
        self.load_layouts()
        self._init_diagnostics()
        self._initial_activation_done = False
        self._manual_login_requested = False
        
    def refresh_theme(self):
        """Re-applies the current theme QSS to this view."""
        self.setStyleSheet(Theme.get_qss("my_orders"))
        self.table_sell.setStyleSheet(Theme.get_qss("my_orders"))
        self.table_buy.setStyleSheet(Theme.get_qss("my_orders"))

    def _init_diagnostics(self):
        self._orders_diag = {
            "started_at": 0,
            "char_id": 0,
            "char_name": "",
            "sell_count": 0,
            "buy_count": 0,
            "total_count": 0,
            "sell_icon_requests": 0,
            "buy_icon_requests": 0,
            "detail_icon_requests": 0,
            "icon_direct_applied_sell": 0,
            "icon_fallback_applied_sell": 0,
            "icon_immediate_applied_sell": 0,
            "icon_missed_sell": 0,
            "icon_direct_applied_buy": 0,
            "icon_fallback_applied_buy": 0,
            "icon_immediate_applied_buy": 0,
            "icon_missed_buy": 0,
            "generation_skipped": 0,
            "missing_type_id_items": [],
            "failed_items": [],
            "callback_missed_items": [],
            "skipped_items": [],
            "sell_rows_with_tid": 0,
            "buy_rows_with_tid": 0,
            "sell_dash_cells": [],
            "buy_dash_cells": [],
            "notes": []
        }

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(12)
        
        # Header
        header_frame = QFrame()
        header_frame.setObjectName("MyOrdersActionBar")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(0, 0, 0, 0)
        title_v = QVBoxLayout()
        title_lbl = QLabel("MIS PEDIDOS")
        title_lbl.setObjectName("SectionTitle")
        
        status_h = QHBoxLayout()
        self.lbl_spinner = QLabel("")
        self.lbl_spinner.setFixedWidth(15)
        self.lbl_spinner.setObjectName("ModeLabel")
        self.lbl_status = QLabel("● ESPERANDO SINCRONIZACIÓN")
        self.lbl_status.setObjectName("ModeLabel")
        status_h.addWidget(self.lbl_spinner)
        status_h.addWidget(self.lbl_status)
        status_h.addStretch()
        
        title_v.addWidget(title_lbl)
        title_v.addLayout(status_h)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setObjectName("SyncProgressBar")
        self.progress_bar.hide()
        title_v.addWidget(self.progress_bar)
        
        self.btn_repopulate = QPushButton("SINCRONIZAR ESI")
        self.btn_repopulate.setObjectName("PrimaryButton")
        self.btn_inventory = QPushButton("INVENTARIO")
        self.btn_inventory.setObjectName("SecondaryButton")
        self.btn_trades = QPushButton("TRANSACCIONES")
        self.btn_trades.setObjectName("SecondaryButton")
        self.btn_esi = QPushButton("ESI: ONLINE")
        self.btn_esi.setObjectName("SecondaryButton")
        self.btn_customize = QPushButton("PERSONALIZAR")
        self.btn_customize.setObjectName("CustomizeButton")
        
        for b in [self.btn_repopulate, self.btn_inventory, self.btn_trades, self.btn_esi, self.btn_customize]:
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(35)
            if b == self.btn_customize: b.setMinimumWidth(110)
        
        self.btn_repopulate.clicked.connect(self.do_sync)
        self.btn_inventory.clicked.connect(self.do_inventory)
        self.btn_trades.clicked.connect(self.open_trades)
        self.btn_esi.clicked.connect(self.toggle_esi)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_esi)
        header.addWidget(self.btn_inventory)
        header.addWidget(self.btn_trades)
        header.addWidget(self.btn_customize)
        header.addWidget(self.btn_repopulate)
        self.main_layout.addWidget(header_frame)

        # Tablas
        self.lbl_sell = QLabel("ÓRDENES DE VENTA (0)")
        self.lbl_sell.setObjectName("ModeLabel")
        self.main_layout.addWidget(self.lbl_sell)
        
        self.table_sell = self.create_table(False)
        self.table_sell.setObjectName("MyOrdersSellTable")
        self.main_layout.addWidget(self.table_sell, 1)
        from ui.common.table_layout_manager import restore_table_layout, connect_table_layout_persistence
        restore_table_layout(self.table_sell, "my_orders_sell_table")
        connect_table_layout_persistence(self.table_sell, "my_orders_sell_table")

        # Taxes bar
        self.setup_taxes_bar()

        self.lbl_buy = QLabel("ÓRDENES DE COMPRA (0)")
        self.lbl_buy.setObjectName("ModeLabel")
        self.main_layout.addWidget(self.lbl_buy)

        self.table_buy = self.create_table(True)
        self.table_buy.setObjectName("MyOrdersBuyTable")
        self.main_layout.addWidget(self.table_buy, 1)
        restore_table_layout(self.table_buy, "my_orders_buy_table")
        connect_table_layout_persistence(self.table_buy, "my_orders_buy_table")

        # Overlays de carga para las tablas
        self._ov_sell = self._create_table_overlay(self.table_sell)
        self._ov_buy = self._create_table_overlay(self.table_buy)
        self._ov_timer = QTimer(self)
        self._ov_timer.setInterval(600)
        _ov_frames = ["◎", "◉", "●", "◉"]
        _ov_idx = [0]
        def _tick():
            _ov_idx[0] = (_ov_idx[0] + 1) % len(_ov_frames)
            self._ov_sell.findChild(QLabel, "_ov_icon").setText(_ov_frames[_ov_idx[0]])
            self._ov_buy.findChild(QLabel, "_ov_icon").setText(_ov_frames[_ov_idx[0]])
        self._ov_timer.timeout.connect(_tick)

        # Detail Panel
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(130)
        self.detail_panel.setObjectName("MetricCard")
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
        self.taxes_bar.setObjectName("MyOrdersTaxBar")
        l = QHBoxLayout(self.taxes_bar)
        l.setContentsMargins(15, 0, 15, 0)
        self.lbl_sales_tax = QLabel("SALES TAX: ---")
        self.lbl_broker_fee = QLabel("BROKER FEE: ---")
        self.lbl_tax_source = QLabel("FUENTE: ---")
        for lbl in [self.lbl_sales_tax, self.lbl_broker_fee, self.lbl_tax_source]:
            lbl.setObjectName("ModeLabel")
        l.addWidget(self.lbl_sales_tax)
        l.addSpacing(20)
        l.addWidget(self.lbl_broker_fee)
        l.addStretch()
        l.addWidget(self.lbl_tax_source)
        self.main_layout.addWidget(self.taxes_bar)

    def create_table(self, is_buy):
        t = QTableWidget(0, 11)
        t.setObjectName("MarketResultsTable")
        t.setHorizontalHeaderLabels(["ÍTEM", "TIPO", "PRECIO", "PROMEDIO", "MEJOR", "TOTAL", "RESTO", "SPREAD", "MARGEN", "PROFIT", "ESTADO"])
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setSectionsMovable(True)
        t.setIconSize(QSize(24, 24))
        t.setSortingEnabled(True)
        t.itemSelectionChanged.connect(self.on_selection_changed)
        t.itemDoubleClicked.connect(lambda i: self.on_double_click_item(i, t))
        return t
    def setup_detail_layout(self):
        self.detail_panel.setObjectName("MarketDetailPanel")
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(15, 12, 15, 12)
        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setObjectName("IconFrame")
        self.lbl_det_icon.setFixedSize(64, 64)
        dl.addWidget(self.lbl_det_icon)
        
        info_v = QVBoxLayout()
        self.lbl_det_item = QLabel("SELECCIONA UNA ORDEN")
        self.lbl_det_item.setFixedWidth(300)
        self.lbl_det_item.setObjectName("MarketDetailTitle")
        self.lbl_det_type = QLabel("---")
        self.lbl_det_type.setObjectName("DetailTagline")
        self.lbl_det_cost_msg = QLabel("---")
        self.lbl_det_cost_msg.setObjectName("DetailTagline")
        info_v.addWidget(self.lbl_det_item)
        info_v.addWidget(self.lbl_det_type)
        info_v.addWidget(self.lbl_det_cost_msg)
        info_v.addStretch()
        dl.addLayout(info_v, 2)
        
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        def add_m(l, r, c):
            v = QVBoxLayout()
            lbl = QLabel(l)
            lbl.setObjectName("DetailMetricTitle")
            v.addWidget(lbl)
            val = QLabel("---")
            val.setObjectName("DetailMetricValue")
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
        n_cols = self.table_sell.columnCount()
        cfg = {
            "w": [self.table_sell.columnWidth(i) for i in range(n_cols)],
            "v": [self.table_sell.horizontalHeader().visualIndex(i) for i in range(n_cols)]
        }
        save_ui_config("my_orders", cfg)

    def load_layouts(self):
        cfg = load_ui_config("my_orders")
        n_cols = self.table_sell.columnCount()
        w = cfg.get("w")
        v = cfg.get("v")
        if w:
            for i, val in enumerate(w):
                if i < n_cols:
                    self.table_sell.setColumnWidth(i, val)
                    self.table_buy.setColumnWidth(i, val)
        if v:
            self.table_sell.blockSignals(True)
            self.table_buy.blockSignals(True)
            for visual_idx, logical_idx in enumerate(v):
                if visual_idx < n_cols and logical_idx < n_cols:
                    self.table_sell.horizontalHeader().moveSection(self.table_sell.horizontalHeader().visualIndex(logical_idx), visual_idx)
                    self.table_buy.horizontalHeader().moveSection(self.table_buy.horizontalHeader().visualIndex(logical_idx), visual_idx)
            self.table_sell.blockSignals(False)
            self.table_buy.blockSignals(False)

    def _get_char_id(self):
        """Helper seguro para obtener el character id activo."""
        cid = self._orders_diag.get("char_id")
        if cid and cid != 0:
            return cid
        return AuthManager.instance().char_id

    def do_sync(self):
        auth = AuthManager.instance()
        t = auth.get_valid_access_token()
        if not t:
            if auth.requires_reauth:
                self.lbl_status.setText("SESIÓN EXPIRADA — REAUTORIZA EL PERSONAJE")
                self.lbl_status.setStyleSheet("color: #ef4444;")
            else:
                self.lbl_status.setText("ESI NO DISPONIBLE — REINTENTANDO EN SEGUNDO PLANO")
                self.lbl_status.setStyleSheet("color: #f59e0b;")
            return
        self.table_sell.setRowCount(0)
        self.table_buy.setRowCount(0)
        
        # Reset Diagnostics
        self._init_diagnostics()
        self._orders_diag["started_at"] = time.time()
        self._orders_diag["char_id"] = auth.char_id
        self._orders_diag["char_name"] = auth.char_name
        
        self._start_sync_ui()
        self.worker = SyncWorker(auth.char_id, t)
        self.worker.status_update.connect(lambda m, v: (self.lbl_status.setText(m), self.progress_bar.setValue(v)))
        self.worker.location_ready.connect(self._on_location_found)
        self.worker.initial_data_ready.connect(self.on_initial_data)
        self.worker.finished_data.connect(self.on_data)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def _on_location_found(self, loc_id):
        self.current_location_id = loc_id
        _log.info(f"[LOCATION] Personaje localizado en {loc_id}")
        self.update_taxes_info()

    def on_initial_data(self, data):
        """Phase 1: Renderizado rápido de órdenes (puede estar incompleto)."""
        self._orders_diag["phase1_at"] = time.time()
        self._orders_diag["phase1_duration"] = self._orders_diag["phase1_at"] - self._orders_diag["started_at"]
        
        _log.info(f"[MY ORDERS] Phase 1 Data Ready: {len(data)} orders (Time: {self._orders_diag['phase1_duration']:.2f}s)")
        self.all_orders = data
        sells = [o for o in data if not o.is_buy_order]
        buys = [o for o in data if o.is_buy_order]
        
        # Indicar estado de hidratación
        self.lbl_sell.setText(f"ÓRDENES DE VENTA ({len(sells)}) — HIDRATANDO...")
        self.lbl_buy.setText(f"ÓRDENES DE COMPRA ({len(buys)}) — HIDRATANDO...")
        
        self._image_generation += 1
        gen = self._image_generation
        self.fill_table(self.table_sell, sells, gen)
        self.fill_table(self.table_buy, buys, gen)

    def on_authenticated(self, name, tokens):
        self.btn_esi.setText(f"SALIR ({name.upper()})")
        self.btn_esi.setStyleSheet(self.btn_esi.styleSheet().replace("#3b82f6", "#1e293b"))
        
        # FIX: Solo sincronizar automáticamente si el usuario pulsó VINCULAR ESI manualmente
        if getattr(self, '_manual_login_requested', False):
            _log.info("[MY ORDERS] Login manual detectado, iniciando sync")
            self._manual_login_requested = False
            self.do_sync()
        else:
            _log.info("[MY ORDERS] Restauración de sesión detectada, omitiendo sync automático")

    def try_auto_login(self):
        auth = AuthManager.instance()
        # Si ya está autenticado (restaurado por MarketCommandMain), sólo actualizar UI
        if auth.current_token:
            self.btn_esi.setText(f"SALIR ({auth.char_name.upper() if auth.char_name else '???'})")
            self.btn_esi.setStyleSheet(self.btn_esi.styleSheet().replace("#3b82f6", "#1e293b"))
            self.lbl_status.setText(f"SESIÓN ACTIVA: {auth.char_name.upper() if auth.char_name else '???'}")
            self.lbl_status.setStyleSheet("color: #10b981;")
            return
        
        res = auth.try_restore_session()
        if res == "ok":
            self.btn_esi.setText(f"SALIR ({auth.char_name.upper()})")
            self.btn_esi.setStyleSheet(self.btn_esi.styleSheet().replace("#3b82f6", "#1e293b"))
            self.lbl_status.setText(f"SESIÓN RESTAURADA: {auth.char_name.upper()}")
            self.lbl_status.setStyleSheet("color: #10b981;")
        elif res == "temporary_failure":
            self.lbl_status.setText("ESI TEMPORALMENTE INACCESIBLE. REINTENTANDO EN SEGUNDO PLANO...")
            self.lbl_status.setStyleSheet("color: #f59e0b;")
        elif res == "new_scopes_required":
            self.lbl_status.setText("FALTAN PERMISOS NUEVOS DE ESI. REAUTORIZA EL PERSONAJE.")
            self.lbl_status.setStyleSheet("color: #f59e0b;")
            QMessageBox.warning(
                self, "ESI - Nuevos Permisos",
                "Se requieren permisos adicionales de ESI para las nuevas funciones.\n\n"
                "Por favor, vuelve a vincular tu personaje."
            )
        elif res == "expired":
            self.lbl_status.setText("SESIÓN EXPIRADA O REVOCADA. REAUTORIZACIÓN REQUERIDA.")
            self.lbl_status.setStyleSheet("color: #ef4444;")
        else:
            self.lbl_status.setText("SIN SESIÓN ESI ACTIVA")

    def toggle_esi(self):
        auth = AuthManager.instance()
        if auth.current_token:
            # Logout
            auth.logout()
            self.btn_esi.setText("VINCULAR ESI")
            self.lbl_status.setText("SESIÓN CERRADA")
            self.lbl_status.setObjectName("MetricValueInfo")
            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)
            self.all_orders = []
            self.table_sell.setRowCount(0)
            self.table_buy.setRowCount(0)
        else:
            # Login
            self._manual_login_requested = True
            self.lbl_status.setText("INICIANDO SSO EN NAVEGADOR...")
            auth.login()

    def on_customize_clicked(self):
        from ui.common.theme_customizer_dialog import ThemeCustomizerDialog
        dialog = ThemeCustomizerDialog(view_scope="my_orders", parent=self)
        dialog.themeUpdated.connect(self.refresh_theme)
        dialog.exec()

    def _load_icon_into_table_item(self, table, row, col, type_id, pixmap, generation, side=None, name=None):
        """Callback robusto para cargar iconos en las tablas de órdenes."""
        try:
            if generation != self._image_generation:
                self._orders_diag["generation_skipped"] += 1
                self._orders_diag["skipped_items"].append({"side": side, "row": row, "type_id": type_id, "item_name": name})
                return
            if table is None: return
            
            # 1. Intento directo por fila/columna
            if self._apply_icon_to_row(table, row, col, pixmap):
                if side == "SELL": self._orders_diag["icon_direct_applied_sell"] += 1
                elif side == "BUY": self._orders_diag["icon_direct_applied_buy"] += 1
                return
                
            # 2. Fallback: buscar por type_id en la columna especificada
            for r in range(table.rowCount()):
                it = table.item(r, col)
                if it and it.data(Qt.UserRole) == type_id:
                    if self._apply_icon_to_row(table, r, col, pixmap):
                        if side == "SELL": self._orders_diag["icon_fallback_applied_sell"] += 1
                        elif side == "BUY": self._orders_diag["icon_fallback_applied_buy"] += 1
                        _log.debug(f"[ORDERS ICON] Applied {type_id} to fallback row {r}")
                        return
            
            # 3. Comprobación final: si ya tiene icono (por aplicación inmediata), no contar como missed
            if self._row_has_icon_for_type_id(table, type_id):
                # Ya tiene icono, probablemente aplicado inmediatamente desde cache
                return

            # Si llegamos aquí, realmente se perdió
            if side == "SELL": self._orders_diag["icon_missed_sell"] += 1
            elif side == "BUY": self._orders_diag["icon_missed_buy"] += 1
            self._orders_diag["callback_missed_items"].append({"side": side, "row": row, "type_id": type_id, "item_name": name})
            
        except Exception as e:
            _log.error(f"[ORDERS ICON ERR] {e}")

    def _row_has_icon_for_type_id(self, table, type_id):
        """Verifica si alguna celda de la fila para ese type_id ya tiene icono."""
        for r in range(table.rowCount()):
            it_name = table.item(r, 0) # Asumimos col 0 es Ítem por ahora, o buscamos por type_id
            if it_name and it_name.data(Qt.UserRole) == type_id:
                if not it_name.icon().isNull():
                    return True
        return False

    def _apply_icon_to_row(self, table, row, item_col, pixmap):
        """Aplica el icono a la celda de la fila/columna especificada, limpiando guiones."""
        item = table.item(row, item_col)
        if item:
            if item.text().strip() == "-":
                item.setText("")
            item.setIcon(QIcon(pixmap.scaled(table.iconSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            return True
        return False

    def _get_item_column(self, table) -> int:
        """Encuentra el índice de la columna que contiene el texto ÍTEM."""
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header and "ÍTEM" in header.text().upper():
                return i
        return 0

    def on_data(self, data):
        self.all_orders = data
        self.update_taxes_info()
        sells = [o for o in data if not o.is_buy_order]
        buys = [o for o in data if o.is_buy_order]
        self.lbl_sell.setText(f"ÓRDENES DE VENTA ({len(sells)})")
        self.lbl_buy.setText(f"ÓRDENES DE COMPRA ({len(buys)})")
        
        # Diag counts
        self._orders_diag["sell_count"] = len(sells)
        self._orders_diag["buy_count"] = len(buys)
        self._orders_diag["total_count"] = len(data)
        self._orders_diag["rows_sell_table"] = len(sells)
        self._orders_diag["rows_buy_table"] = len(buys)
        
        # WAC Diagnostics
        try:
            wac = CostBasisService.instance()
            char_id = self._get_char_id()
            self._orders_diag["wac_item_count"] = len(wac.stock_map)
            self._orders_diag["wac_last_tx_id"] = wac.last_transaction_id
            self._orders_diag["wac_backfill_stats"] = wac.backfill_stats
            
            if char_id:
                self._orders_diag["wac_cache_file"] = os.path.basename(wac._get_cache_path(char_id))
            else:
                self._orders_diag["wac_cache_file"] = "N/A (No Char ID)"
                self._orders_diag["notes"].append("Warning: char_id not found for WAC diagnostics.")

            missing_wac = sum(1 for o in sells if wac.get_cost_basis(o.type_id) is None)
            self._orders_diag["wac_missing_count"] = missing_wac
            if len(sells) > 0:
                self._orders_diag["wac_hit_rate"] = ((len(sells) - missing_wac) / len(sells)) * 100
            else:
                self._orders_diag["wac_hit_rate"] = 100.0
        except Exception as e:
            _log.warning(f"[WAC DIAG ERR] Failed to collect WAC stats: {e}")
            self._orders_diag["wac_cache_file"] = "ERROR"
            self._orders_diag["notes"].append(f"WAC Diagnostic Error: {e}")
        
        self._image_generation += 1
        gen = self._image_generation
        _log.info(f"[MY ORDERS] Starting fill_table with gen={gen}")
        
        self.fill_table(self.table_sell, sells, gen)
        self.fill_table(self.table_buy, buys, gen)
        self._stop_sync_ui()
        
        # Finalize diag and show report
        self._orders_diag["finished_at"] = time.time()
        self._orders_diag["duration"] = self._orders_diag["finished_at"] - self._orders_diag["started_at"]
        self._orders_diag["phase2_duration"] = self._orders_diag["finished_at"] - self._orders_diag.get("phase1_at", self._orders_diag["started_at"])
        self._orders_diag["hydration_success"] = True
        
        # Count rows with type_id
        for r in range(self.table_sell.rowCount()):
            it = self.table_sell.item(r, 0)
            if it and it.data(Qt.UserRole): self._orders_diag["sell_rows_with_tid"] += 1
        for r in range(self.table_buy.rowCount()):
            it = self.table_buy.item(r, 0)
            if it and it.data(Qt.UserRole): self._orders_diag["buy_rows_with_tid"] += 1
            
        # Dash Cell Scan
        self._scan_for_dash_cells(self.table_sell, "SELL")
        self._scan_for_dash_cells(self.table_buy, "BUY")
        
        # Column Diag
        s_col = self._get_item_column(self.table_sell)
        b_col = self._get_item_column(self.table_buy)
        self._orders_diag["sell_item_col"] = s_col
        self._orders_diag["buy_item_col"] = b_col
        sh = self.table_sell.horizontalHeaderItem(s_col)
        bh = self.table_buy.horizontalHeaderItem(b_col)
        self._orders_diag["sell_header"] = sh.text() if sh else "None"
        self._orders_diag["buy_header"] = bh.text() if bh else "None"
            
        QTimer.singleShot(1500, self.show_my_orders_diagnostics)

    def _scan_for_dash_cells(self, table, side):
        diag_key = "sell_dash_cells" if side == "SELL" else "buy_dash_cells"
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                it = table.item(r, c)
                if it and it.text().strip() == "-":
                    h = table.horizontalHeaderItem(c)
                    h_txt = h.text() if h else str(c)
                    tid = it.data(Qt.UserRole)
                    has_icon = not it.icon().isNull()
                    self._orders_diag[diag_key].append({
                        "side": side, "row": r, "col": c, "header": h_txt,
                        "type_id": tid, "has_icon": has_icon
                    })

    def fill_table(self, t, data, gen):
        t.setSortingEnabled(False)
        t.setRowCount(len(data))
        for r, o in enumerate(data):
            a = o.analysis
            cost = CostBasisService.instance().get_cost_basis(o.type_id)
            avg = cost.average_buy_price if cost else 0.0
            
            i_name = QTableWidgetItem(o.item_name)
            i_name.setData(Qt.UserRole, o.type_id)
            i_name.setData(Qt.UserRole + 1, o.order_id)
            
            side = "SELL" if not o.is_buy_order else "BUY"
            if side == "SELL": self._orders_diag["sell_icon_requests"] += 1
            else: self._orders_diag["buy_icon_requests"] += 1
            
            if not o.type_id:
                self._orders_diag["missing_type_id_items"].append({"side": side, "row": r, "item_name": o.item_name})

            icon_col = self._get_item_column(t)
            
            pix = self.icon_service.get_icon(
                o.type_id, 24,
                callback=lambda p, tid=o.type_id, row=r, gen=gen, s=side, n=o.item_name, col=icon_col: 
                    self._load_icon_into_table_item(t, row, col, tid, p, gen, side=s, name=n)
            )
            
            # Aplicación inmediata si ya tenemos el pixmap (cache hit)
            if pix and not pix.isNull():
                i_name.setIcon(QIcon(pix.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                if side == "SELL": self._orders_diag["icon_immediate_applied_sell"] += 1
                else: self._orders_diag["icon_immediate_applied_buy"] += 1
                _log.debug(f"[ORDERS ICON] Immediate apply for {o.type_id} at row {r}")
            else:
                _log.debug(f"[ORDERS ICON] Requesting {o.type_id} for row {r}")
            
            i_type = QTableWidgetItem("BUY" if o.is_buy_order else "SELL")
            i_type.setForeground(QColor(Theme.ACCENT if o.is_buy_order else Theme.DANGER))
            
            i_price = NumericTableWidgetItem(format_isk(o.price), o.price)
            if not o.is_buy_order and avg <= 0:
                i_avg = NumericTableWidgetItem("N/A", 0)
                i_avg.setToolTip("Coste medio no disponible. El historial WAC (365 días / 100k tx) aún no cubre este ítem. Pulsa Sincronizar para actualizar.")
                i_avg.setForeground(QColor("#64748b"))
            else:
                i_avg = NumericTableWidgetItem(format_isk(avg) if avg > 0 else "---", avg)
            
            # MEJOR: Mostrar el mejor precio absoluto del mercado
            ref_v = a.best_buy if o.is_buy_order else a.best_sell
            i_ref = NumericTableWidgetItem(format_isk(ref_v) if ref_v > 0 and ref_v < 999999999999 else "---", ref_v)
            if not a.competitive and ref_v > 0:
                # Si estamos superados, resaltar el precio mejor
                i_ref.setForeground(QColor(Theme.WARNING))
            elif a.competitive:
                i_ref.setForeground(QColor(Theme.SUCCESS))
            
            # TOTAL y RESTO
            i_tot = NumericTableWidgetItem(f"{o.volume_total:,}", o.volume_total)
            i_rem = NumericTableWidgetItem(f"{o.volume_remain:,}", o.volume_remain)
            i_spr = NumericTableWidgetItem(f"{a.spread_pct:.1f}%", a.spread_pct)
            
            i_mar = NumericTableWidgetItem(f"{a.margin_pct:.1f}%", a.margin_pct)
            if a.margin_pct > 10.0: i_mar.setForeground(QColor(Theme.TABLE_MARGIN_POSITIVE))
            elif a.margin_pct >= 0.0: i_mar.setForeground(QColor(Theme.TABLE_MARGIN_WARNING))
            else: i_mar.setForeground(QColor(Theme.TABLE_MARGIN_NEGATIVE))
            
            i_prof = NumericTableWidgetItem(format_isk(a.net_profit_total), a.net_profit_total)
            if a.net_profit_total > 0: i_prof.setForeground(QColor(Theme.TABLE_PROFIT_POSITIVE))
            elif a.net_profit_total < 0: i_prof.setForeground(QColor(Theme.TABLE_PROFIT_NEGATIVE))
            
            i_state = SemanticTableWidgetItem(a.state.upper())
            s_low = a.state.lower()
            if any(x in s_low for x in ["liderando", "competitiva", "sana", "rentable"]):
                i_state.setForeground(QColor(Theme.SUCCESS))
            elif "superada" in s_low or "ajustado" in s_low:
                i_state.setForeground(QColor(Theme.WARNING))
            elif any(x in s_low for x in ["pérdida", "no rentable", "fuera"]):
                i_state.setForeground(QColor(Theme.DANGER))
            
            items = [i_name, i_type, i_price, i_avg, i_ref, i_tot, i_rem, i_spr, i_mar, i_prof, i_state]
            for i, it in enumerate(items):
                it.setTextAlignment(Qt.AlignCenter)
                it.setData(Qt.UserRole, o.type_id) # Redundancia
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
        self._selected_detail_type_id = o.type_id
        item_name = o.item_name.upper()
        self.lbl_det_item.setText(item_name)
        self.lbl_det_item.setToolTip(item_name)
        
        # Elide text manually if needed or let label handle it if set up
        metrics = self.lbl_det_item.fontMetrics()
        elided = metrics.elidedText(item_name, Qt.ElideRight, self.lbl_det_item.width())
        self.lbl_det_item.setText(elided)

        self.lbl_det_type.setText("COMPRA" if o.is_buy_order else "VENTA")
        self.lbl_det_type.setStyleSheet(f"color:{Theme.ACCENT};" if o.is_buy_order else f"color:{Theme.DANGER};")
        
        def on_det_icon_ready(pixmap, tid=o.type_id):
            if getattr(self, "_selected_detail_type_id", None) == tid:
                _log.debug(f"[DETAIL ICON] Applying high-res icon for {tid}")
                self.lbl_det_icon.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        _log.debug(f"[DETAIL ICON] Requesting {o.type_id}")
        self._orders_diag["detail_icon_requests"] += 1
        pix = self.icon_service.get_icon(o.type_id, 64, callback=on_det_icon_ready)
        self.lbl_det_icon.setPixmap(pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        a = o.analysis
        cost = CostBasisService.instance().get_cost_basis(o.type_id)
        avg = cost.average_buy_price if cost else 0.0

        # Item name — golden premium
        self.lbl_det_item.setStyleSheet("color:#f8c51c; font-size:14px; font-weight:900;")

        # Manipulation detection warning
        manip_warn = ""
        try:
            from core.market_manipulation_detector import detect_sell_manipulation, detect_buy_manipulation
            if not o.is_buy_order and a.best_buy > 0 and a.best_sell > 0:
                mres = detect_sell_manipulation(a.best_sell, a.best_buy)
                if mres.manipulation_detected:
                    manip_warn = f" ⚠ POSIBLE MANIP. SELL"
            elif o.is_buy_order and a.best_buy > 0:
                mres = detect_buy_manipulation(a.best_buy, buy_orders=None)
                if mres.manipulation_detected:
                    manip_warn = f" ⚠ POSIBLE MANIP. BUY"
        except Exception:
            pass

        self.lbl_det_cost_msg.setText(f"{a.state} | ID: {o.order_id}{manip_warn}")
        manip_color = Theme.WARNING if manip_warn else Theme.TEXT_DIM
        self.lbl_det_cost_msg.setStyleSheet(f"color:{manip_color}; font-size:9px;")

        _FMT = "font-size:11px; font-weight:900;"
        self.det_price.setText(format_isk(o.price))
        self.det_price.setStyleSheet(f"color:{Theme.TEXT_MAIN}; {_FMT}")

        self.det_avg.setText(format_isk(avg) if avg > 0 else "---")
        self.det_avg.setStyleSheet(f"color:{Theme.TEXT_DIM}; {_FMT}")

        self.det_best_buy.setText(format_isk(a.best_buy))
        self.det_best_buy.setStyleSheet(f"color:{Theme.ACCENT}; {_FMT}")  # blue — buy

        self.det_best_sell.setText(format_isk(a.best_sell))
        self.det_best_sell.setStyleSheet(f"color:{Theme.TABLE_MARGIN_POSITIVE}; {_FMT}")  # light-green — sell

        margin = a.margin_pct
        self.det_margin.setText(f"{margin:.1f}%")
        if margin >= 10.0:
            margin_color = Theme.TABLE_MARGIN_POSITIVE
        elif margin >= 0.0:
            margin_color = Theme.TABLE_MARGIN_WARNING
        else:
            margin_color = Theme.TABLE_MARGIN_NEGATIVE
        self.det_margin.setStyleSheet(f"color:{margin_color}; {_FMT}")

        profit_u = a.net_profit_per_unit
        self.det_profit_u.setText(format_isk(profit_u))
        self.det_profit_u.setStyleSheet(f"color:{'#10b981' if profit_u >= 0 else '#ef4444'}; {_FMT}")

        profit_t = a.net_profit_total
        self.det_profit_t.setText(format_isk(profit_t))
        self.det_profit_t.setStyleSheet(f"color:{Theme.TABLE_PROFIT_POSITIVE if profit_t >= 0 else Theme.TABLE_PROFIT_NEGATIVE}; {_FMT}")

        state_upper = a.state.upper()
        self.det_state.setText(state_upper)
        if "LIDER" in state_upper:
            state_color = Theme.SUCCESS   # green
        elif "SUPERA" in state_upper:
            state_color = Theme.DANGER    # red
        elif "ACTIV" in state_upper:
            state_color = Theme.WARNING   # amber
        else:
            state_color = Theme.TEXT_DIM   # neutral
        self.det_state.setStyleSheet(f"color:{state_color}; {_FMT}")

    # ------------------------------------------------------------------
    # Quick Order Update helpers
    # ------------------------------------------------------------------

    def _get_type_column(self, table) -> int:
        """Return the logical column index whose header is TIPO or TYPE."""
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header and header.text().strip().upper() in ("TIPO", "TYPE"):
                return i
        return 1  # fallback

    def _get_order_from_row(self, table, row):
        """Recover the OpenOrder for a given table row. Prefers order_id lookup."""
        item_col = self._get_item_column(table)
        name_item = table.item(row, item_col)
        if not name_item:
            return None

        order_id = name_item.data(Qt.UserRole + 1)
        type_id  = name_item.data(Qt.UserRole)

        if order_id:
            for order in self.all_orders:
                if order.order_id == order_id:
                    return order

        # Fallback: match by type_id + side read from TIPO column
        if type_id:
            tipo_col  = self._get_type_column(table)
            tipo_item = table.item(row, tipo_col)
            if tipo_item:
                is_buy = tipo_item.text().upper() == "BUY"
                for order in self.all_orders:
                    if order.type_id == type_id and order.is_buy_order == is_buy:
                        return order

        return None

    def _open_market_from_table_item(self, item, t):
        """Open in-game market for the item in a table row (original double-click behavior)."""
        row      = item.row()
        item_col = self._get_item_column(t)
        tid      = None
        name     = ""

        for col in range(t.columnCount()):
            it = t.item(row, col)
            if it:
                if not tid:
                    tid = it.data(Qt.UserRole)
                if col == item_col:
                    name = it.text()

        if tid:
            _log.info(f"[OPEN MARKET] my_orders double_clicked row={row} type_id={tid}")
            ItemInteractionHelper.open_market_with_fallback(
                ESIClient(), AuthManager.instance().char_id, tid, name,
                lambda m, c: self.lbl_status.setText(m),
            )
        else:
            _log.warning(
                f"[OPEN MARKET] my_orders double_clicked without type_id row={row}"
            )

    def _open_market_for_order(self, order) -> bool:
        """Open the in-game market window for an order's item."""
        try:
            auth = AuthManager.instance()
            return ItemInteractionHelper.open_market_with_fallback(
                ESIClient(),
                auth.char_id,
                order.type_id,
                order.item_name,
                feedback_callback=lambda m, c: self.lbl_status.setText(m),
            )
        except Exception as e:
            _log.warning(f"[QUICK UPDATE] market open error: {e}")
            return False

    def _revalidate_order_freshness(self, order) -> dict:
        """
        Call ESI to verify the local order snapshot is still current.
        Returns a freshness dict; non-fresh result blocks auto-copy.
        """
        _PRICE_TOL = 0.005  # Half-cent — same as EVE's minimum tick

        result = {
            "checked":       False,
            "is_fresh":      False,
            "order_exists":  False,
            "fresh_price":   None,
            "old_price":     order.price,
            "price_changed": False,
            "warnings":      [],
            "fresh_order":   None,
        }

        try:
            auth  = AuthManager.instance()
            token = auth.get_valid_access_token()
            if not token:
                result["warnings"].append(
                    "Sin token ESI activo — no se pudo revalidar la orden."
                )
                _log.warning("[QUICK UPDATE] freshness: no token available")
                return result

            client     = ESIClient()
            raw_orders = client.character_orders(auth.char_id, token)
            result["checked"] = True

            if not isinstance(raw_orders, list):
                result["warnings"].append(
                    "ESI devolvio respuesta inesperada al revalidar "
                    f"({type(raw_orders).__name__})."
                )
                return result

            # Locate by order_id
            fresh_raw = next(
                (o for o in raw_orders if o.get("order_id") == order.order_id),
                None,
            )

            if fresh_raw is None:
                result["order_exists"] = False
                result["warnings"].append(
                    f"La orden {order.order_id} no existe en ESI "
                    f"(cancelada, expirada, o aun no sincronizada). "
                    f"Refresca Mis Pedidos."
                )
                _log.warning(
                    f"[QUICK UPDATE] freshness: order_id={order.order_id} "
                    f"not found in ESI response ({len(raw_orders)} orders)"
                )
                return result

            result["order_exists"] = True
            result["fresh_order"]  = fresh_raw
            fresh_price            = float(fresh_raw.get("price", order.price))
            result["fresh_price"]  = fresh_price

            if abs(fresh_price - order.price) > _PRICE_TOL:
                result["price_changed"] = True
                result["is_fresh"]      = False
                result["warnings"].append(
                    f"Precio local desactualizado: "
                    f"local={order.price:.2f} ISK, ESI fresco={fresh_price:.2f} ISK. "
                    f"Refresca Mis Pedidos y vuelve a intentarlo."
                )
                _log.warning(
                    f"[QUICK UPDATE] freshness: price_changed "
                    f"local={order.price} fresh={fresh_price} "
                    f"order_id={order.order_id}"
                )
            else:
                result["is_fresh"] = True
                _log.info(
                    f"[QUICK UPDATE] freshness: OK "
                    f"price={fresh_price} order_id={order.order_id}"
                )

        except Exception as exc:
            result["warnings"].append(
                f"Error al revalidar con ESI: {str(exc)[:100]}"
            )
            _log.warning(f"[QUICK UPDATE] freshness check error: {exc}")

        return result

    def _handle_quick_order_update_double_click(self, item, table):
        """Entry point when user double-clicks the TIPO column."""
        row   = item.row()
        order = self._get_order_from_row(table, row)
        if not order:
            _log.warning(
                f"[QUICK UPDATE] failed reason=order_not_found row={row}"
            )
            self.lbl_status.setText("Quick Update: orden no encontrada en esta fila")
            return
        self._launch_quick_order_update(order)

    def _revalidate_market_competitor(self, order) -> dict:
        """
        Fetch fresh market orders for the item and find the best competitor,
        scoped by the order's location_id (station-local scope).
        Returns a dict with revalidation results.
        """
        res = {
            "checked": False,
            "is_fresh": False,
            "type_id": order.type_id,
            "region_id": 10000002,  # Default The Forge/Jita
            "location_id": order.location_id,
            "target_location_id": order.location_id,
            "side": "BUY" if order.is_buy_order else "SELL",
            "old_competitor_price": order.analysis.competitor_price if order.analysis else 0.0,
            "fresh_best_sell": 0.0,
            "fresh_best_buy": 0.0,
            "fresh_competitor_price": 0.0,
            "fresh_recommended_price": 0.0,
            "used_fresh_price": False,
            "price_changed": False,
            "warnings": [],
            "market_orders_count": 0,
            "regional_orders_count": 0,
            "location_orders_count": 0,
            "own_orders_excluded_count": 0,
            "price_source": "analysis.competitor_price",
            "market_scope": "station_location",
            "filtered_by_location": True
        }

        # Guard: order location is required for station-local scope
        if not order.location_id:
            res["checked"] = True
            res["warnings"].append("No order location_id available; cannot use local market scope.")
            _log.warning(f"[QUICK UPDATE] location_id missing for order {order.order_id}")
            return res
        
        client = ESIClient()
        try:
            # 1. Fetch fresh orders (regional)
            market_orders = client.get_market_orders_for_type(res["region_id"], order.type_id)
            res["checked"] = True
            res["regional_orders_count"] = len(market_orders)
            
            # 2. Recalculate using local scope (pure logic)
            fresh = recalculate_competitor_price(
                market_orders, self.all_orders, order.type_id, order.is_buy_order, 
                location_id=order.location_id
            )
            
            res["fresh_best_buy"] = fresh["best_buy"]
            res["fresh_best_sell"] = fresh["best_sell"]
            res["fresh_competitor_price"] = fresh["competitor_price"]
            res["own_orders_excluded_count"] = fresh["own_excluded_count"]
            res["location_orders_count"] = fresh["location_orders_count"]
            res["market_orders_count"] = fresh["location_orders_count"]
            
            # REQUISITO 8: Bloquear si no hay competidor local fiable
            if not fresh.get("comp_prices_found"):
                res["warnings"].append("No reliable local competitor found in fresh market book.")
                return res

            if res["fresh_competitor_price"] <= _SENTINEL_MIN or res["fresh_competitor_price"] >= _SENTINEL_MAX:
                res["warnings"].append("Invalid local competitor price (sentinel detected).")
                return res

            # 3. Calculate fresh recommendation
            if order.is_buy_order:
                res["fresh_recommended_price"] = recommend_buy_price(res["fresh_competitor_price"])
            else:
                res["fresh_recommended_price"] = recommend_sell_price(res["fresh_competitor_price"])
                
            # Validar recomendación
            if res["fresh_recommended_price"] <= 0:
                res["warnings"].append("Invalid local recommended price calculated (<= 0).")
                return res

            # 4. Compare
            diff = abs(res["fresh_competitor_price"] - res["old_competitor_price"])
            if diff > 0.01:
                res["price_changed"] = True
                res["warnings"].append(
                    f"Local market change: old={res['old_competitor_price']:,.2f}, fresh={res['fresh_competitor_price']:,.2f}"
                )
            
            # 5. Mark as successful
            res["is_fresh"] = True
            res["used_fresh_price"] = True
            res["price_source"] = "fresh_market_book_location"
            
        except Exception as e:
            res["warnings"].append(f"Error revalidando mercado local: {e}")
            _log.warning(f"[QUICK UPDATE] local market revalidation error: {e}")
            
        return res

    def _launch_quick_order_update(self, order):
        """Calculate recommendation, copy price, open market, show popup."""
        side = "BUY" if order.is_buy_order else "SELL"
        _log.info(
            f"[QUICK UPDATE] double_click side={side} "
            f"row=? order_id={order.order_id} type_id={order.type_id}"
        )

        # Step 1: ESI freshness checks — both own order and market book
        self.lbl_status.setText("Revalidando mercado con ESI...")
        self.lbl_status.setStyleSheet("color: #3b82f6;")
        
        freshness  = self._revalidate_order_freshness(order)
        market_val = self._revalidate_market_competitor(order)

        _log.info(
            f"[QUICK UPDATE MARKET REVALIDATION] checked={market_val.get('checked')} "
            f"is_fresh={market_val.get('is_fresh')} used_fresh={market_val.get('used_fresh_price')} "
            f"old_comp={market_val.get('old_competitor_price')} fresh_comp={market_val.get('fresh_competitor_price')} "
            f"fresh_rec={market_val.get('fresh_recommended_price')} warnings={len(market_val.get('warnings', []))}"
        )

        # Step 2: Build pricing recommendation
        rec        = build_order_update_recommendation(order, order.analysis)
        
        # Override with fresh market data if available
        if market_val.get("used_fresh_price"):
            _log.info(f"[QUICK UPDATE] Overriding cached analysis with fresh local market data for {order.item_name} at location {order.location_id}")
            rec["competitor_price"]  = market_val["fresh_competitor_price"]
            rec["best_buy"]          = market_val["fresh_best_buy"]
            rec["best_sell"]         = market_val["fresh_best_sell"]
            rec["recommended_price"] = market_val["fresh_recommended_price"]
            rec["price_source"]      = market_val["price_source"]
            rec["market_scope"]      = market_val.get("market_scope", "station_location")
            rec["location_id"]       = market_val.get("target_location_id")
            rec["tick"]              = price_tick(rec["competitor_price"])
            
            # Update reason and action_needed based on fresh results
            is_best = False
            if order.is_buy_order:
                is_best = order.price >= (rec["competitor_price"] - 0.005)
                rec["reason"] = "Ya liderando — sin cambio necesario" if is_best else f"Subir a {rec['recommended_price']:,.2f} ISK para superar competidor"
            else:
                is_best = order.price <= (rec["competitor_price"] + 0.005)
                rec["reason"] = "Ya liderando — sin cambio necesario" if is_best else f"Bajar a {rec['recommended_price']:,.2f} ISK para superar competidor"
            
            rec["action_needed"] = not is_best

        validation = rec.get("validation", {})

        # Step 3: Merge freshness into validation — block auto-copy if anything is unreliable
        if not freshness.get("checked") or not freshness.get("is_fresh"):
            validation["is_confident"]    = False
            validation["confidence_label"] = "Baja"
            validation.setdefault("warnings", []).extend(freshness.get("warnings", []))
            
        if not market_val.get("checked") or not market_val.get("is_fresh"):
            validation["is_confident"]    = False
            validation["confidence_label"] = "Baja"
            validation.setdefault("warnings", []).extend(market_val.get("warnings", []))

        is_confident = validation.get("is_confident", True)

        _log.info(
            f"[QUICK UPDATE] FINAL recommendation price={rec['recommended_price']} "
            f"competitor={rec['competitor_price']} tick={rec['tick']} "
            f"confidence={validation.get('confidence_label', '?')} "
            f"fresh={freshness.get('is_fresh')} market_fresh={market_val.get('is_fresh')}"
        )
        if not is_confident:
            for w in validation.get("warnings", []):
                _log.warning(f"[QUICK UPDATE] WARNING: {w}")

        # Clipboard — ONLY auto-copy if validation is confident
        if is_confident:
            price_text = format_price_for_clipboard(rec["recommended_price"])
            QGuiApplication.clipboard().setText(price_text)
            _log.info(f"[QUICK UPDATE] clipboard_set text={price_text}")
            clipboard_value = price_text
        else:
            price_text = format_price_for_clipboard(rec["recommended_price"])
            clipboard_value = f"(no copiado: confianza baja) {price_text}"
            _log.warning(
                f"[QUICK UPDATE] auto-copy SKIPPED — low confidence. "
                f"Suggested price: {price_text}"
            )

        # Market (auto on launch regardless of confidence)
        market_ok = self._open_market_for_order(order)
        _log.info(
            f"[QUICK UPDATE] market_open_sent type_id={order.type_id} ok={market_ok}"
        )

        # Diagnostics report (logged, also shown in dialog)
        diag_data = {
            "order_id":          order.order_id,
            "type_id":           order.type_id,
            "item_name":         order.item_name,
            "side":              side,
            "my_price":          order.price,
            "competitor_price":  rec.get("competitor_price"),
            "best_buy":          rec.get("best_buy"),
            "best_sell":         rec.get("best_sell"),
            "recommended_price": rec.get("recommended_price"),
            "tick":              rec.get("tick"),
            "market_window_opened": market_ok,
            "clipboard_value":   clipboard_value,
            "validation":        validation,
            "freshness":         freshness,
            "market_validation": market_val,
            "market_scope":      rec.get("market_scope", "regional"),
            "location_id":       rec.get("location_id"),
        }
        diag_report = format_quick_update_report(diag_data)
        _log.debug(f"[QUICK UPDATE] report:\n{diag_report}")

        # One dialog at a time
        if getattr(self, "_quick_order_dialog", None):
            self._quick_order_dialog.close()

        self._quick_order_dialog = QuickOrderUpdateDialog(
            order=order,
            recommendation=rec,
            parent=self,
            open_market_callback=self._open_market_for_order,
            diag_report=diag_report,
        )
        self._quick_order_dialog.show()

        # Status bar feedback
        if is_confident:
            self.lbl_status.setText(
                f"Precio copiado y mercado abierto — {order.item_name}"
            )
            self.lbl_status.setStyleSheet("color: #10b981;")
        else:
            warnings_text = " | ".join(validation.get("warnings", ["confianza baja"]))
            self.lbl_status.setText(
                f"⚠ Recomendación no fiable — revisa manualmente: {warnings_text}"
            )
            self.lbl_status.setStyleSheet("color: #f59e0b;")

    # ------------------------------------------------------------------
    # Double-click dispatch (column-aware)
    # ------------------------------------------------------------------

    def on_double_click_item(self, item, t):
        if not item:
            return
        col      = item.column()
        type_col = self._get_type_column(t)

        if col == type_col:
            self._handle_quick_order_update_double_click(item, t)
            return

        # ÍTEM column and any other column → open market (original behavior)
        self._open_market_from_table_item(item, t)

    def activate_view(self):
        """Llamado cuando esta pestaña se hace visible."""
        if not self._initial_activation_done:
            _log.info("[MY ORDERS] Activación inicial de la vista (lightweight)")
            self._initial_activation_done = True
            self.lbl_status.setText("● LISTO — PULSA ACTUALIZAR PARA CARGAR PEDIDOS")
            self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
            QTimer.singleShot(100, self._safe_lightweight_auth_restore)
        else:
            _log.debug("[MY ORDERS] Vista ya estaba activa")

    def _safe_lightweight_auth_restore(self):
        """Intenta restaurar la sesión de forma diferida pero sin sincronización pesada."""
        t_start = time.perf_counter()
        self.try_auto_login()
        t_end = time.perf_counter()
        _log.info(f"[MY ORDERS] _safe_lightweight_auth_restore completed in {(t_end - t_start)*1000:.2f} ms")


    def update_taxes_info(self):
        auth = AuthManager.instance()
        token = auth.get_token()
        if not token: return
        
        # Prioridad de ubicación:
        # 1. Ubicación detectada en el Sync más reciente (current_location_id)
        # 2. Ubicación de la primera orden si no hay detectada
        # 3. Fallback a 0 (Overrides globales seguirán funcionando)
        loc_id = self.current_location_id
        if not loc_id and self.all_orders:
            loc_id = self.all_orders[0].location_id
        
        s_tax, b_fee, source, debug = TaxService.instance().get_effective_taxes(auth.char_id, loc_id, token)
        
        self.lbl_sales_tax.setText(f"SALES TAX: {s_tax:.2f}%")
        self.lbl_broker_fee.setText(f"BROKER FEE: {b_fee:.2f}%")
        self.lbl_tax_source.setText(f"FUENTE: {source}")
        
        # Diag taxes
        self._orders_diag["sales_tax"] = s_tax
        self._orders_diag["broker_fee"] = b_fee
        self._orders_diag["tax_source"] = source
        self._orders_diag["location_id"] = loc_id
        
        _log.info(f"[TAX_UI_DIAG] char={auth.char_id} loc={loc_id} -> {debug}")

    def show_my_orders_diagnostics(self):
        if getattr(self, "_orders_diag_dialog", None):
            self._orders_diag_dialog.close()
            
        report = self.build_my_orders_report()
        self._orders_diag_dialog = MarketDiagnosticsDialog(report, self)
        self._orders_diag_dialog.setWindowTitle("Market Command — Diagnóstico de Mis Pedidos")
        self._orders_diag_dialog.show()

    def build_my_orders_report(self) -> str:
        icon_diag = self.icon_service.get_diagnostics()
        
        # Check failed items in this sync
        failed_sample = icon_diag.get("failed_ids_sample", [])
        for tid in failed_sample:
            # See if it was requested in this sync
            # This is hard to map perfectly without a request log, but we can try to find the item in all_orders
            ord_obj = next((o for o in self.all_orders if o.type_id == tid), None)
            if ord_obj:
                side = "BUY" if ord_obj.is_buy_order else "SELL"
                self._orders_diag["failed_items"].append({
                    "side": side,
                    "type_id": tid,
                    "item_name": ord_obj.item_name
                })
        
        self._orders_diag["market_timings"] = ESIClient().market_orders_timings.get(10000002, {})
        self._orders_diag["all_orders"] = self.all_orders
        
        return format_my_orders_diagnostic_report(self._orders_diag, icon_diag)


    def do_inventory(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if not t: return
        self._start_sync_ui()
        self._pending_loc_name = "TODO EL INVENTARIO"
        self.inv_worker = InventoryWorker(auth.char_id, t)
        self.inv_worker.status_update.connect(lambda m, v: (self.lbl_status.setText(m), self.progress_bar.setValue(v)))
        self.inv_worker.location_info.connect(lambda name: setattr(self, '_pending_loc_name', name))
        def on_done(data):
            self._stop_sync_ui()
            loc_name = getattr(self, '_pending_loc_name', 'INVENTARIO')
            if data:
                InventoryAnalysisDialog(data, loc_name, self).exec()
            else:
                QMessageBox.information(self, "Vacío", "No hay items en esta ubicación.")
        self.inv_worker.finished_data.connect(on_done)
        self.inv_worker.start()

    def open_trades(self):
        auth = AuthManager.instance()
        t = auth.get_token()
        if t:
            TradeProfitsDialog(auth.char_id, t, self).exec()

    def _update_spinner(self):
        self.spinner_idx = (self.spinner_idx + 1) % 4
        self.lbl_spinner.setText(self.spinner_chars[self.spinner_idx])

    def _create_table_overlay(self, table):
        ov = QFrame(self)
        ov.setObjectName("ScanOverlay")
        ov.setStyleSheet("QFrame#ScanOverlay{background-color:rgba(5,7,10,200);border-radius:6px;}")
        vl = QVBoxLayout(ov)
        vl.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel("◎")
        icon_lbl.setObjectName("_ov_icon")
        icon_lbl.setStyleSheet("color:#00c8ff;font-size:24px;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        text_lbl = QLabel("SINCRONIZANDO...")
        text_lbl.setStyleSheet("color:#00c8ff;font-size:10px;font-weight:900;letter-spacing:2px;")
        text_lbl.setAlignment(Qt.AlignCenter)
        vl.addWidget(icon_lbl)
        vl.addWidget(text_lbl)
        ov.setVisible(False)
        return ov

    def _reposition_overlays(self):
        for ov, tbl in [(self._ov_sell, self.table_sell), (self._ov_buy, self.table_buy)]:
            if ov.isVisible():
                pos = tbl.mapTo(self, tbl.rect().topLeft())
                ov.setGeometry(pos.x(), pos.y(), tbl.width(), tbl.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_ov_sell'):
            self._reposition_overlays()

    def _show_orders_overlays(self):
        for ov, tbl in [(self._ov_sell, self.table_sell), (self._ov_buy, self.table_buy)]:
            pos = tbl.mapTo(self, tbl.rect().topLeft())
            ov.setGeometry(pos.x(), pos.y(), tbl.width(), tbl.height())
            ov.setVisible(True)
            ov.raise_()
        self._ov_timer.start()

    def _hide_orders_overlays(self):
        self._ov_timer.stop()
        self._ov_sell.setVisible(False)
        self._ov_buy.setVisible(False)

    def _start_sync_ui(self):
        self.spinner_timer.start(100)
        self.lbl_status.setText("SINCRONIZANDO...")
        self.lbl_status.setStyleSheet("color: #3b82f6;")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.btn_repopulate.setEnabled(False)
        self.btn_inventory.setEnabled(False)
        self.btn_trades.setEnabled(False)
        if hasattr(self, '_ov_sell'):
            self._show_orders_overlays()

    def _stop_sync_ui(self):
        self.spinner_timer.stop()
        self.lbl_spinner.setText("")
        self.lbl_status.setText("LISTO")
        self.lbl_status.setStyleSheet("color: #10b981;")
        self.progress_bar.hide()
        self.btn_repopulate.setEnabled(True)
        self.btn_inventory.setEnabled(True)
        self.btn_trades.setEnabled(True)
        if hasattr(self, '_ov_sell'):
            self._hide_orders_overlays()

    def on_error(self, err):
        self._stop_sync_ui()
        self.lbl_status.setText(f"ERROR: {err[:40]}")
        self.lbl_status.setStyleSheet("color: #ef4444;")
