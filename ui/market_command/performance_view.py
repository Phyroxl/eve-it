from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QComboBox, QScrollArea, QGridLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QCheckBox,
    QAbstractItemView, QDialog
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPixmap, QIcon
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
import sqlite3
import logging
from datetime import datetime, timedelta

from core.performance_engine import PerformanceEngine
from core.eve_icon_service import EveIconService

_log = logging.getLogger('eve.performance')

class KPIWidget(QFrame):
    def __init__(self, title, value, color="#3b82f6", tooltip=None, parent=None):
        super().__init__(parent)
        self.setObjectName("AnalyticBox")
        self.setStyleSheet(f"background-color: #0f172a; border: 1px solid #1e293b; border-radius: 4px; min-width: 140px;")
        if tooltip:
            self.setToolTip(tooltip)
        
        l = QVBoxLayout(self)
        l.setContentsMargins(12, 10, 12, 10)
        l.setSpacing(2)
        
        t = QLabel(title.upper())
        t.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        
        self.v = QLabel(value)
        self.v.setStyleSheet("color: #f1f5f9; font-size: 14px; font-weight: 900;")
        
        self.d = QLabel("CONTABILIDAD CERRADA")
        self.d.setStyleSheet("color: #475569; font-size: 9px; font-weight: 700;")
        
        l.addWidget(t)
        l.addWidget(self.v)
        l.addWidget(self.d)

    def update_value(self, val, detail=None, color=None):
        self.v.setText(val)
        if detail: self.d.setText(detail.upper())
        if color: self.v.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 900;")

class SimpleBarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = [] # List of (date, value)
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.hover_index = -1

    def set_data(self, data):
        self.data = data
        self.hover_index = -1
        self.update()

    def mouseMoveEvent(self, event):
        if not self.data: return
        w = self.width()
        padding_l, padding_r = 40, 40
        chart_w = w - padding_l - padding_r
        
        rel_x = event.position().x() - padding_l
        if rel_x < 0 or rel_x > chart_w:
            self.hover_index = -1
        else:
            idx = int(rel_x / (chart_w / len(self.data))) if len(self.data) > 0 else -1
            if idx != self.hover_index:
                self.hover_index = idx
                self.update()

    def leaveEvent(self, event):
        self.hover_index = -1
        self.update()

    def paintEvent(self, event):
        if not self.data: return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        padding_l, padding_r = 40, 40
        padding_t, padding_b = 20, 20
        chart_w = w - padding_l - padding_r
        chart_h = h - padding_t - padding_b
        
        vals = [d[1] for d in self.data]
        cumulative = []
        curr = 0
        for v in vals:
            curr += v
            cumulative.append(curr)
            
        max_val = max([abs(v) for v in vals]) if vals else 1
        max_cum = max([abs(c) for c in cumulative]) if cumulative else 1
        
        bar_w_step = chart_w / len(self.data) if len(self.data) > 0 else 10
        bar_w = bar_w_step * 0.6
        spacing = bar_w_step * 0.4
        
        zero_line = padding_t + chart_h / 2
        
        # Grid lines
        p.setPen(QPen(QColor("#0f172a"), 1))
        p.drawLine(padding_l, padding_t, padding_l, h-padding_b)
        p.setPen(QPen(QColor("#1e293b"), 1, Qt.DashLine))
        p.drawLine(padding_l, zero_line, w - padding_r, zero_line)
        
        # Bars
        for i, val in enumerate(vals):
            x = padding_l + i * bar_w_step + spacing/2
            norm_h = (val / max_val) * (chart_h / 2)
            
            color = QColor("#10b981") if val >= 0 else QColor("#ef4444")
            if i == self.hover_index:
                color = color.lighter(130)
            else:
                color.setAlpha(160)
                
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawRect(x, zero_line, bar_w, -norm_h)
            
        # Cumulative Line
        if len(cumulative) > 1:
            p.setPen(QPen(QColor("#3b82f6"), 2))
            p.setBrush(Qt.NoBrush)
            points = []
            for i, cum_val in enumerate(cumulative):
                x = padding_l + i * bar_w_step + bar_w_step/2
                norm_cum_h = (cum_val / max_cum) * (chart_h * 0.4)
                points.append((x, zero_line - norm_cum_h))
            
            for i in range(len(points)-1):
                p.drawLine(points[i][0], points[i][1], points[i+1][0], points[i+1][1])

        # Tooltip
        if self.hover_index != -1 and self.hover_index < len(self.data):
            date, val = self.data[self.hover_index]
            cum = cumulative[self.hover_index]
            from utils.formatters import format_isk
            
            tip_w, tip_h = 130, 45
            tip_x = padding_l + self.hover_index * bar_w_step + bar_w_step/2 - tip_w/2
            tip_y = padding_t
            
            # Clamp tooltip in window
            tip_x = max(5, min(tip_x, w - tip_w - 5))
            
            p.setBrush(QBrush(QColor("#1e293b")))
            p.setPen(QPen(QColor("#3b82f6"), 1))
            p.drawRoundedRect(tip_x, tip_y, tip_w, tip_h, 3, 3)
            
            p.setPen(QColor("#f1f5f9"))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.drawText(tip_x + 8, tip_y + 15, date)
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(tip_x + 8, tip_y + 28, f"DIARIO: {format_isk(val, True)}")
            p.setPen(QColor("#3b82f6"))
            p.drawText(tip_x + 8, tip_y + 40, f"TOTAL: {format_isk(cum, True)}")

class MarketPerformanceView(QWidget):
    def __init__(self, parent=None, defer_initial_refresh=False):
        super().__init__(parent)
        from core.config_manager import load_performance_config
        self.config = load_performance_config()
        self._sync_in_progress = False
        self._is_auto_sync = False
        self._image_generation = 0
        self._initial_refresh_done = False
        self.engine = PerformanceEngine()
        self.icon_service = EveIconService.instance()
        self._purge_fake_char0()
        self.setup_ui()
        
        # Setup Auto-Refresh Timer
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._on_auto_timer_tick)
        self._next_sync_seconds = 0
        
        if not defer_initial_refresh:
            self.discover_characters()
            if self.config.auto_refresh_enabled:
                self.start_auto_refresh()
            self.refresh_view()
        else:
            self._diag_label.setText("▸ Performance listo — carga diferida")

    def activate_view(self):
        """Llamado por el contenedor principal cuando esta pestaña se hace visible."""
        if not self._initial_refresh_done:
            _log.info("[PERF] Activación inicial de la vista Performance")
            self.discover_characters()
            if self.config.auto_refresh_enabled:
                self.start_auto_refresh()
            self.refresh_view()
            self._initial_refresh_done = True
        else:
            _log.debug("[PERF] Vista ya estaba activa, saltando refresh automático")

    def _purge_fake_char0(self):
        """Elimina datos demo/fallback con character_id=0 que contaminan la vista."""
        try:
            conn = sqlite3.connect(self.engine.db_path)
            try:
                deleted = conn.execute("DELETE FROM wallet_transactions WHERE character_id = 0").rowcount
                conn.execute("DELETE FROM wallet_snapshots WHERE character_id = 0")
                conn.execute("DELETE FROM wallet_journal WHERE character_id = 0")
                conn.commit()
                if deleted:
                    _log.info(f"[PURGE] Eliminados {deleted} registros demo con char_id=0")
            finally:
                conn.close()
        except Exception as e:
            _log.warning(f"[PURGE] No se pudo limpiar char_id=0: {e}")

    def discover_characters(self):
        """Busca personajes en los logs y llena el combo, ignorando fallbacks con id=0."""
        chars = self.engine.find_active_characters()
        self.combo_char.clear()
        # Filtrar estrictamente: solo aceptar personajes con ID real (>0)
        valid = [c for c in chars if isinstance(c.get('id'), int) and c['id'] > 0]
        if not valid:
            self.combo_char.addItem("Haz login ESI para sincronizar", -1)
        else:
            for c in valid:
                self.combo_char.addItem(c['name'], c['id'])

        self.combo_char.currentIndexChanged.connect(self.refresh_view)
        
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)
        
        # 1. Header & Selectors
        header = QHBoxLayout()
        
        # Portrait del personaje
        self.lbl_portrait = QLabel()
        self.lbl_portrait.setFixedSize(48, 48)
        self.lbl_portrait.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 24px;")
        self.lbl_portrait.setScaledContents(True)
        header.addWidget(self.lbl_portrait)
        
        title_v = QVBoxLayout()
        title_lbl = QLabel("MARKET PERFORMANCE")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        subtitle = QLabel("RENDIMIENTO REAL DE TRADING")
        subtitle.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        title_v.addWidget(title_lbl)
        title_v.addWidget(subtitle)
        
        # Nueva etiqueta de contexto operativa
        self.context_lbl = QLabel("ANALIZANDO OPERATIVA...")
        self.context_lbl.setStyleSheet("color: #3b82f6; font-size: 9px; font-weight: 800; letter-spacing: 0.5px;")
        title_v.addWidget(self.context_lbl)
        
        # Auto-Refresh Group
        auto_group = QHBoxLayout()
        auto_group.setSpacing(5)
        
        self.check_auto = QCheckBox("Auto-Refresh")
        self.check_auto.setChecked(self.config.auto_refresh_enabled)
        self.check_auto.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        self.check_auto.toggled.connect(self.on_auto_refresh_toggled)
        
        self.combo_auto_time = QComboBox()
        for m in [1, 2, 5, 10, 15]:
            self.combo_auto_time.addItem(f"{m} min", m)
        
        # Seleccionar valor guardado
        idx = self.combo_auto_time.findData(self.config.refresh_interval_min)
        if idx >= 0: self.combo_auto_time.setCurrentIndex(idx)
        
        self.combo_auto_time.setFixedWidth(70)
        self.combo_auto_time.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; font-size: 9px;")
        self.combo_auto_time.currentIndexChanged.connect(self.on_auto_interval_changed)
        
        auto_group.addWidget(self.check_auto)
        auto_group.addWidget(self.combo_auto_time)
        
        # Selectores de Personaje y Rango (Inicialización faltante restaurada)
        self.combo_char = QComboBox()
        self.combo_char.addItem("Sincroniza para ver personajes")
        self.combo_char.setFixedWidth(200)
        self.combo_char.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; padding: 5px;")
        
        self.combo_range = QComboBox()
        self.combo_range.addItems(["Hoy", "7 días", "30 días", "90 días"])
        self.combo_range.setCurrentIndex(2)
        self.combo_range.setFixedWidth(100)
        self.combo_range.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; padding: 5px;")
        self.combo_range.currentIndexChanged.connect(self.refresh_view)
        
        self.btn_refresh = QPushButton("SINCRONIZAR ESI")
        self.btn_refresh.setFixedWidth(120)
        self.btn_refresh.setFixedHeight(30)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.on_sync_clicked)
        
        self.btn_diag_fees = QPushButton("DIAGNÓSTICO FEES")
        self.btn_diag_fees.setFixedWidth(120)
        self.btn_diag_fees.setFixedHeight(30)
        self.btn_diag_fees.setCursor(Qt.PointingHandCursor)
        self.btn_diag_fees.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: 800; border-radius: 4px; border: 1px solid #334155;")
        self.btn_diag_fees.clicked.connect(self.on_diag_fees_clicked)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.combo_char)
        header.addWidget(self.combo_range)
        header.addLayout(auto_group)
        header.addWidget(self.btn_diag_fees)
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)

        # Barra de estado de diagnóstico (siempre visible)
        self._diag_label = QLabel("▸ Sin datos — pulsa SINCRONIZAR ESI para empezar")
        self._diag_label.setStyleSheet(
            "color: #475569; font-size: 9px; font-weight: 700; "
            "padding: 4px 8px; background: #0f172a; "
            "border: 1px solid #1e293b; border-radius: 3px;"
        )
        self.main_layout.addWidget(self._diag_label)

        # 2. KPIs Section (Rediseñado para Net Profit)
        kpis_v = QVBoxLayout()
        kpis_v.setSpacing(6)
        
        # Fila 1: Métricas Críticas (Profit vs Cashflow vs Stock)
        kpis_row1 = QHBoxLayout(); kpis_row1.setSpacing(6)
        self.kpi_net_profit = KPIWidget(
            "Net Profit", "0 ISK", "#10b981", 
            "Beneficio Real Realizado: Ventas - COGS (Coste Adquisición Unidades Vendidas) - Fees/Tax. "
            "Es el rendimiento real de tu trading, independiente de si has comprado stock extra o no."
        )
        self.kpi_cashflow = KPIWidget(
            "Trade Cashflow", "0 ISK", "#3b82f6", 
            "Movimiento Neto de ISK: Income - Coste Compras - Fees/Tax. "
            "Representa la variación real de tu cartera. Si es negativo, estás invirtiendo en stock."
        )
        self.kpi_exposure = KPIWidget(
            "Inventory Exposure", "0 ISK", "#cbd5e1",
            "Valor de mercado estimado del stock acumulado durante este periodo."
        )
        kpis_row1.addWidget(self.kpi_net_profit)
        kpis_row1.addWidget(self.kpi_cashflow)
        kpis_row1.addWidget(self.kpi_exposure)
        
        # Fila 2: Desglose Operativo
        kpis_row2 = QHBoxLayout(); kpis_row2.setSpacing(6)
        self.kpi_income = KPIWidget("Sales Income", "0 ISK", "#60a5fa")
        self.kpi_cost = KPIWidget("Buy Investment", "0 ISK", "#f87171")
        self.kpi_broker = KPIWidget("Broker Fees", "0 ISK", "#f59e0b")
        self.kpi_tax = KPIWidget("Sales Tax", "0 ISK", "#f97316")
        
        kpis_row2.addWidget(self.kpi_income)
        kpis_row2.addWidget(self.kpi_cost)
        kpis_row2.addWidget(self.kpi_broker)
        kpis_row2.addWidget(self.kpi_tax)
        
        kpis_v.addLayout(kpis_row1)
        kpis_v.addLayout(kpis_row2)
        self.main_layout.addLayout(kpis_v)
        
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
        from PySide6.QtWidgets import QAbstractItemView
        self.top_items_table = QTableWidget(0, 6)
        self.top_items_table.setHorizontalHeaderLabels(["Item", "In (Qty)", "Out (Qty)", "Net Stock", "Realized Profit", "Estado"])
        self.top_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.top_items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.top_items_table.setColumnWidth(0, 180)
        self.top_items_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.top_items_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.top_items_table.customContextMenuRequested.connect(self.on_table_context_menu)
        self.top_items_table.setStyleSheet("background: #0f172a; color: #f1f5f9; border: none; font-size: 10px;")
        self.top_items_table.setShowGrid(False)
        self.top_items_table.verticalHeader().setVisible(False)
        self.top_items_table.setFixedHeight(250)
        self.top_items_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.top_items_table.setSelectionMode(QTableWidget.SingleSelection)
        self.top_items_table.itemSelectionChanged.connect(self.on_item_selection_changed)
        self.top_items_table.itemDoubleClicked.connect(self._on_table_double_click)
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
        self.det_profit, self.lbl_det_profit = create_det_box("Realized (COGS)", "#10b981")
        self.det_fees, self.lbl_det_fees = create_det_box("Fees (Broker/Tax)", "#f59e0b")
        self.det_alloc, self.lbl_det_alloc = create_det_box("Allocation Info", "#94a3b8")
        self.det_margin, self.lbl_det_margin = create_det_box("Margin")
        self.det_status, self.lbl_det_status = create_det_box("Operational Status", "#fbbf24")
        
        dl.addWidget(self.det_in)
        dl.addWidget(self.det_out)
        dl.addWidget(self.det_stock)
        dl.addWidget(self.det_profit)
        dl.addWidget(self.det_fees)
        dl.addWidget(self.det_alloc)
        dl.addWidget(self.det_margin)
        dl.addWidget(self.det_status)
        
        self.main_layout.addWidget(self.detail_frame)
        
        # 4. Bottom Row: Recent Transactions
        self.trans_table = QTableWidget(0, 6)
        self.trans_table.setHorizontalHeaderLabels(["Fecha", "Item", "Tipo", "Cantidad", "Total", "Fee Est."])
        self.trans_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.trans_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.trans_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.trans_table.itemDoubleClicked.connect(self._on_table_double_click)
        self.trans_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trans_table.customContextMenuRequested.connect(self.on_table_context_menu)
        self.trans_table.setStyleSheet("background: #000000; color: #f1f5f9; border: none; font-size: 10px;")
        self.trans_table.setShowGrid(False)
        self.trans_table.verticalHeader().setVisible(False)
        self.trans_table.setMinimumHeight(250)
        self.main_layout.addWidget(self.trans_table)
        
        self.main_layout.addStretch()

    def on_sync_clicked(self, is_auto=False):
        if self._sync_in_progress:
            _log.info("[SYNC] Ignorando petición, ya hay una sync en curso.")
            return

        from core.auth_manager import AuthManager
        from core.wallet_poller import WalletPoller
        from PySide6.QtCore import QThread
        
        auth = AuthManager.instance()
        self._is_auto_sync = is_auto
        
        # Si no hay token, iniciar login ESI (solo si es manual)
        if not auth.current_token:
            if is_auto:
                _log.info("[SYNC] Auto-refresh cancelado: no hay token.")
                return
            auth.login()
            self.btn_refresh.setText("ESPERANDO LOGIN...")
            self.btn_refresh.setEnabled(False)
            self._auth_poll_timer = QTimer(self)
            self._auth_poll_timer.setInterval(500)
            self._auth_poll_timer.timeout.connect(self._poll_auth_completion)
            self._auth_poll_timer.start()
            self._auth_poll_count = 0
            return
            
        char_id = self.combo_char.currentData()

        # El personaje autenticado tiene prioridad absoluta sobre el combo
        if auth.char_id:
            char_id = auth.char_id
            # Actualizar combo para que refleje el personaje real autenticado
            found = False
            for i in range(self.combo_char.count()):
                if self.combo_char.itemData(i) == char_id:
                    self.combo_char.blockSignals(True)
                    self.combo_char.setCurrentIndex(i)
                    self.combo_char.blockSignals(False)
                    found = True
                    break

            if not found:
                self.combo_char.blockSignals(True)
                self.combo_char.addItem(auth.char_name, auth.char_id)
                self.combo_char.setCurrentIndex(self.combo_char.count() - 1)
                self.combo_char.blockSignals(False)

        _log.info(f"[SYNC] Iniciando sync para char_id={char_id} (auth.char_id={auth.char_id}, combo_data={self.combo_char.currentData()})")

        if not char_id or char_id <= 0:
            self.btn_refresh.setText("SELECT CHAR")
            QTimer.singleShot(2000, lambda: self.btn_refresh.setText("SINCRONIZAR ESI"))
            return

        self.btn_refresh.setText("SINCRONIZANDO...")
        self.btn_refresh.setEnabled(False)
        self._sync_in_progress = True
        
        # Worker Thread
        self.poller_thread = QThread()
        self.poller = WalletPoller()
        self.poller.moveToThread(self.poller_thread)
        
        self._last_sync_report = None
        self.poller_thread.started.connect(lambda: self.poller.poll(char_id, auth.current_token))
        self.poller.sync_report.connect(self._on_sync_report)
        self.poller.finished.connect(self.on_sync_finished)
        self.poller.error.connect(self.on_sync_error)

        self.poller_thread.start()

    def on_sync_finished(self):
        self._sync_in_progress = False
        self.btn_refresh.setText("COMPLETO")
        self.btn_refresh.setEnabled(True)

        from core.auth_manager import AuthManager
        from PySide6.QtWidgets import QMessageBox
        auth = AuthManager.instance()
        char_id = self.combo_char.currentData() or auth.char_id
        
        # Garantizar rango ≥ 30 días antes de refrescar
        if self.combo_range.currentIndex() < 2:
            self.combo_range.blockSignals(True)
            self.combo_range.setCurrentIndex(2)
            self.combo_range.blockSignals(False)

        # Limpiar hilo worker primero
        if hasattr(self, 'poller_thread'):
            self.poller_thread.quit()
            self.poller_thread.wait(2000)

        # Solo mostrar popup si fue manual
        if not self._is_auto_sync:
            # Construir mensaje de diagnóstico
            r = self._last_sync_report or {}
            rep_char_id   = r.get('char_id', char_id)
            balance       = r.get('balance')
            esi_trans     = r.get('esi_trans_count', '?')
            esi_journal   = r.get('esi_journal_count', '?')
            saved_trans   = r.get('saved_trans', '?')
            saved_journal = r.get('saved_journal', '?')
            db_trans      = r.get('db_transactions', '?')
            db_journal    = r.get('db_journal', '?')
            db_snaps      = r.get('db_snapshots', '?')
            date_min      = r.get('db_trans_date_min') or '—'
            date_max      = r.get('db_trans_date_max') or '—'
            balance_str   = f"{balance:,.0f} ISK" if isinstance(balance, (int, float)) else "No recibido"

            msg = (
                f"═══ DIAGNÓSTICO DE SYNC ═══\n\n"
                f"char_id usado:      {rep_char_id}\n"
                f"auth.char_id:       {auth.char_id}\n"
                f"combo currentData:  {self.combo_char.currentData()}\n\n"
                f"── ESI recibido ──\n"
                f"  Balance:          {balance_str}\n"
                f"  Transacciones:    {esi_trans}\n"
                f"  Journal entries:  {esi_journal}\n\n"
                f"── Guardado en DB ──\n"
                f"  Trans guardadas:  {saved_trans}\n"
                f"  Journal guardado: {saved_journal}\n\n"
                f"── Estado DB total para char_id ──\n"
                f"  wallet_snapshots: {db_snaps}\n"
                f"  wallet_trans:     {db_trans}  ({date_min} → {date_max})\n"
                f"  wallet_journal:   {db_journal}\n"
            )
            if isinstance(db_trans, int) and db_trans > 0:
                box = QMessageBox(QMessageBox.Information, "Sincronización ESI", msg, parent=self)
            else:
                box = QMessageBox(QMessageBox.Warning, "Sincronización ESI — Sin datos", msg, parent=self)
            box.exec()

        self.refresh_view()
        QTimer.singleShot(3000, lambda: self.btn_refresh.setText("SINCRONIZAR ESI"))
        
        # Resetear timer si está activo
        if self.config.auto_refresh_enabled:
            self.start_auto_refresh()

    def _on_sync_report(self, report: dict):
        """Recibe el informe de diagnóstico emitido por WalletPoller desde el hilo worker."""
        self._last_sync_report = report
        _log.info(f"[SYNC_REPORT] {report}")

    def _poll_auth_completion(self):
        """Polling en hilo principal cada 500ms — detecta token disponible o error de auth."""
        from core.auth_manager import AuthManager
        from PySide6.QtWidgets import QMessageBox
        auth = AuthManager.instance()
        self._auth_poll_count += 1

        if auth.current_token:
            self._auth_poll_timer.stop()
            self.btn_refresh.setText("SINCRONIZAR ESI")
            self.btn_refresh.setEnabled(True)
            _log.info(f"[AUTH] Token detectado tras {self._auth_poll_count * 500}ms — iniciando sync")
            self.on_sync_clicked()
        elif auth.auth_error:
            # El servidor de callback ya terminó con error — no tiene sentido seguir esperando
            self._auth_poll_timer.stop()
            self.btn_refresh.setText("SINCRONIZAR ESI")
            self.btn_refresh.setEnabled(True)
            _log.error(f"[AUTH] Error reportado por AuthManager: {auth.auth_error}")
            QMessageBox.critical(self, "Error de Autenticación ESI", auth.auth_error)
        elif self._auth_poll_count >= 120:  # 60 segundos de timeout
            self._auth_poll_timer.stop()
            self.btn_refresh.setText("SINCRONIZAR ESI")
            self.btn_refresh.setEnabled(True)
            _log.warning("[AUTH] Timeout esperando token de autenticación (60s)")
            QMessageBox.warning(self, "Login ESI", "No se recibió respuesta de EVE SSO en 60 segundos.\nIntenta de nuevo.")

    def on_sync_error(self, msg):
        self._sync_in_progress = False
        _log.error(f"[SYNC ERROR] {msg}")
        self.btn_refresh.setText("ERROR")
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setStyleSheet("background: #ef4444; color: white; font-weight: 800; border-radius: 4px;")
        if hasattr(self, 'poller_thread'):
            self.poller_thread.quit()
            self.poller_thread.wait(2000)
        
        # Pausar auto-refresh si falla auth/token
        if "token" in msg.lower() or "auth" in msg.lower():
            self.check_auto.setChecked(False)
            _log.warning("[SYNC] Auto-refresh desactivado por error de token.")

    def refresh_view(self):
        """Entry point público — captura cualquier excepción y la hace visible."""
        self._initial_refresh_done = True
        try:
            self._do_refresh()
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            _log.error(f"[REFRESH] EXCEPCIÓN:\n{tb}")
            self._diag_label.setText(f"▸ ERROR CRÍTICO: {exc}")
            self._diag_label.setStyleSheet("color: #ef4444; font-size: 9px; font-weight: 700; padding: 4px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 3px;")

    def _do_refresh(self):
        self._image_generation += 1
        gen = self._image_generation
        self.detail_frame.setVisible(False)
        days_map = {0: 1, 1: 7, 2: 30, 3: 90}
        days = days_map.get(self.combo_range.currentIndex(), 30)
        date_to   = datetime.utcnow().strftime("%Y-%m-%d")
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        char_id = self.combo_char.currentData()
        _log.info(
            f"[REFRESH] ▶ char_id={char_id!r}  tipo={type(char_id).__name__}  "
            f"rango={days}d  ({date_from} → {date_to})"
        )

        if char_id is None or char_id == -1:
            _log.info(f"[REFRESH] char_id inválido ({char_id!r}) → salida temprana")
            self._diag_label.setText(
                "▸ Selecciona un personaje y pulsa SINCRONIZAR ESI para cargar datos."
            )
            self._diag_label.setStyleSheet(
                "color: #94a3b8; font-size: 9px; font-weight: 700; "
                "padding: 4px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 3px;"
            )
            # Resetear todos los KPIs
            self.kpi_cashflow.update_value("0 ISK")
            self.kpi_income.update_value("0 ISK")
            self.kpi_cost.update_value("0 ISK")
            self.kpi_broker.update_value("0 ISK")
            self.kpi_tax.update_value("0 ISK")
            self.kpi_net_profit.update_value("0 ISK")
            self.kpi_exposure.update_value("0 ISK", "No sync")
            
            self.context_lbl.setText("SIN DATOS")
            self.chart.set_data([])
            self.top_items_table.setRowCount(0)
            self.trans_table.setRowCount(0)
            return

        # ── Verificación SQL directa (pre-engine) ─────────────────────────
        conn = sqlite3.connect(self.engine.db_path)
        try:
            sql_tx = conn.execute(
                "SELECT COUNT(*) FROM wallet_transactions "
                "WHERE character_id=? AND substr(date,1,10) BETWEEN ? AND ?",
                (char_id, date_from, date_to)
            ).fetchone()[0]
            sql_jn = conn.execute(
                "SELECT COUNT(*) FROM wallet_journal "
                "WHERE character_id=? AND substr(date,1,10) BETWEEN ? AND ?",
                (char_id, date_from, date_to)
            ).fetchone()[0]
            sql_tx_total = conn.execute(
                "SELECT COUNT(*) FROM wallet_transactions WHERE character_id=?",
                (char_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        _log.info(
            f"[REFRESH] SQL directo → tx_total={sql_tx_total}  "
            f"tx_en_rango={sql_tx}  journal_en_rango={sql_jn}"
        )

        # ── Engine ────────────────────────────────────────────────────────
        summary  = self.engine.build_character_summary(char_id, date_from, date_to)
        daily_pnl = self.engine.build_daily_pnl(char_id, date_from, date_to)
        items    = self.engine.build_item_summary(char_id, date_from, date_to)

        _log.info(
            f"[REFRESH] Engine → daily={len(daily_pnl)} días  items={len(items)}  "
            f"income={summary.total_income:.0f}  cost={summary.total_cost:.0f}  "
            f"fees={summary.total_fees:.0f}  cashflow={summary.net_cashflow:.0f}  "
            f"wallet={summary.wallet_current:.0f}"
        )

        from utils.formatters import format_isk

        # ── Actualizar barra de diagnóstico ───────────────────────────────
        diag_color = "#10b981" if summary.total_income > 0 else "#f59e0b"
        
        auto_text = ""
        if self.config.auto_refresh_enabled:
            m, s = divmod(self._next_sync_seconds, 60)
            auto_text = f" | Next Sync: {m:02d}:{s:02d}"

        self._diag_label.setText(
            f"▸ char={char_id}  rango={days}d  "
            f"tx_rango={sql_tx}  journal={sql_jn}  items={len(items)}  "
            f"income={format_isk(summary.total_income, True)} ISK | "
            f"fees={format_isk(summary.broker_fees, True)} | tax={format_isk(summary.sales_tax, True)} | "
            f"cashflow={format_isk(summary.net_cashflow, True)} ISK | "
            f"net_profit={format_isk(summary.total_net_profit, True)} ISK"
            f"{auto_text}"
        )
        self._diag_label.setStyleSheet(
            f"color: {diag_color}; font-size: 9px; font-weight: 700; "
            f"padding: 4px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 3px;"
        )

        # ── KPIs ──────────────────────────────────────────────────────────
        self.kpi_net_profit.update_value(
            format_isk(summary.total_net_profit, short=True) + " ISK",
            f"COGS: {format_isk(summary.total_cogs, True)}",
            "#10b981" if summary.total_net_profit >= 0 else "#f87171"
        )
        self.kpi_cashflow.update_value(
            format_isk(summary.net_cashflow, short=True) + " ISK",
            "Variación ISK",
            "#3b82f6" if summary.net_cashflow >= 0 else "#f87171"
        )
        self.kpi_income.update_value(format_isk(summary.total_income, short=True) + " ISK", "Ingresos")
        self.kpi_cost.update_value(format_isk(summary.total_cost, short=True) + " ISK", "Inversión")
        self.kpi_broker.update_value(format_isk(summary.broker_fees, short=True) + " ISK", "Brokerage")
        self.kpi_tax.update_value(format_isk(summary.sales_tax, short=True) + " ISK", "Impuestos")
        self.kpi_exposure.update_value(
            format_isk(summary.inventory_exposure, short=True) + " ISK",
            f"Wallet: {format_isk(summary.wallet_current, True)}"
        )
        self.context_lbl.setText(summary.period_context.upper())

        # Portrait
        self.icon_service.get_portrait(char_id, 64, lambda pix: self.lbl_portrait.setPixmap(pix))

        # ── Gráfico ───────────────────────────────────────────────────────
        self.chart.set_data([(d.date, d.profit_net) for d in daily_pnl])

        # ── Top Items ─────────────────────────────────────────────────────
        self.current_items = items
        self.top_items_table.setRowCount(len(items[:15]))
        status_colors = {
            "Rotando Bien": "#10b981",
            "Acumulando Stock": "#fbbf24",
            "Liquidando": "#f87171",
            "Flujo Equilibrado": "#60a5fa",
            "Salida Lenta": "#94a3b8",
            "Exposición Alta": "#ef4444"
        }
        for i, item in enumerate(items[:15]):
            item_cell = QTableWidgetItem(item.item_name)
            item_cell.setData(Qt.UserRole, item.item_id)
            
            pix = self.icon_service.get_icon(
                item.item_id, 32, 
                lambda p, tid=item.item_id, row=i: self._load_icon_into_table_item(self.top_items_table, row, 0, tid, p, gen)
            )
            item_cell.setIcon(QIcon(pix))
            
            self.top_items_table.setItem(i, 0, item_cell)
            self.top_items_table.setItem(i, 1, QTableWidgetItem(f"{item.total_bought_units:,}"))
            self.top_items_table.setItem(i, 2, QTableWidgetItem(f"{item.total_sold_units:,}"))
            
            stock_item = QTableWidgetItem(f"{item.net_units:,}")
            if item.net_units > 0: stock_item.setForeground(QColor("#60a5fa"))
            self.top_items_table.setItem(i, 3, stock_item)
            
            profit_item = QTableWidgetItem(format_isk(item.net_profit, short=True))
            if item.net_profit > 0: profit_item.setForeground(QColor("#10b981"))
            elif item.net_profit < 0: profit_item.setForeground(QColor("#f87171"))
            self.top_items_table.setItem(i, 4, profit_item)

            s_low = item.status_text.lower()
            status_item = QTableWidgetItem(item.status_text)
            if any(x in s_low for x in ["liderando", "competitiva", "sana", "rentable"]):
                status_item.setForeground(QColor("#10b981"))
            else:
                status_item.setForeground(QColor(status_colors.get(item.status_text, "#94a3b8")))
            self.top_items_table.setItem(i, 5, status_item)
            
            for col in range(6):
                it = self.top_items_table.item(i, col)
                if it: it.setTextAlignment(Qt.AlignCenter)

        self.top_items_table.setStyleSheet("background: #000000; color: #f1f5f9; border: none; font-size: 10px;")

        # ── Recent Transactions (sin filtro de fecha) ─────────────────────
        conn2 = sqlite3.connect(self.engine.db_path)
        try:
            rows = conn2.execute(
                "SELECT date, item_name, is_buy, quantity, unit_price, item_id "
                "FROM wallet_transactions "
                "WHERE character_id=? ORDER BY date DESC LIMIT 50",
                (char_id,)
            ).fetchall()
        finally:
            conn2.close()
        _log.info(f"[REFRESH] Recent Transactions: {len(rows)} filas para char_id={char_id}")

        self.trans_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            date_short = r[0].split("T")[0]
            tipo  = "COMPRA" if r[2] == 1 else "VENTA"
            color = "#f87171" if r[2] == 1 else "#34d399"
            
            self.trans_table.setItem(i, 0, QTableWidgetItem(date_short))
            
            name_cell = QTableWidgetItem(r[1] or "Unknown")
            name_cell.setData(Qt.UserRole, r[5])
            
            pix = self.icon_service.get_icon(
                r[5], 32,
                lambda p, tid=r[5], row=i: self._load_icon_into_table_item(self.trans_table, row, 1, tid, p, gen)
            )
            name_cell.setIcon(QIcon(pix))
            self.trans_table.setItem(i, 1, name_cell)
            
            type_item = QTableWidgetItem(tipo)
            type_item.setForeground(QColor(color))
            self.trans_table.setItem(i, 2, type_item)
            
            self.trans_table.setItem(i, 3, QTableWidgetItem(f"{r[3]:,}"))
            self.trans_table.setItem(i, 4, QTableWidgetItem(format_isk(r[3] * r[4], short=True)))
            self.trans_table.setItem(i, 5, QTableWidgetItem("~3.0%"))
            
            for col in range(6):
                it = self.trans_table.item(i, col)
                if it: it.setTextAlignment(Qt.AlignCenter)

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
            self.lbl_det_profit.setText(format_isk(item.net_profit))
            self.lbl_det_margin.setText(f"{item.margin_real_pct:.1f}%")
            
            # Allocated Fees Info
            b_fees = format_isk(item.allocated_broker_fees, True)
            s_tax = format_isk(item.allocated_sales_tax, True)
            self.lbl_det_fees.setText(f"{b_fees} / {s_tax}")
            
            # Allocation Method & Confidence
            conf_color = "#10b981" if item.fee_allocation_confidence == "high" else "#fbbf24" if item.fee_allocation_confidence == "medium" else "#64748b"
            self.lbl_det_alloc.setText(f"{item.fee_allocation_method.upper()} ({item.fee_allocation_confidence.upper()})")
            self.lbl_det_alloc.setStyleSheet(f"color: {conf_color}; font-size: 11px; font-weight: 700;")
            
            # Contexto adicional en el detalle
            exposure_text = f"Exposure: {format_isk(item.inventory_value_est, True)}"
            self.lbl_det_status.setText(f"{item.status_text.upper()} | {exposure_text}")
            
            self.detail_frame.setVisible(True)

    def on_table_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QGuiApplication
        
        table = self.sender()
        item = table.itemAt(pos)
        if not item: return
        
        # Dinamismo táctico: identificar columna de item según la tabla
        col_name = 1 if table == self.top_items_table else 2
        name_item = table.item(item.row(), col_name)
        if not name_item: return
        
        name = name_item.text()
        
        menu = QMenu()
        copy_action = menu.addAction(f"Copiar '{name}'")
        action = menu.exec(table.mapToGlobal(pos))
        
        if action == copy_action:
            QGuiApplication.clipboard().setText(name)

    def _on_table_double_click(self, item):
        table = self.sender()
        row = item.row()
        
        # Dinamismo táctico: la columna del item varía según la tabla
        col_name = 0 if table == self.top_items_table else 1
        name_item = table.item(row, col_name)
        
        if not name_item: return
        
        item_name = name_item.text()
        type_id = name_item.data(Qt.UserRole)
        char_id = self.combo_char.currentData()
        
        from ui.market_command.widgets import ItemInteractionHelper
        from core.esi_client import ESIClient
        
        def feedback(msg, color):
            self._diag_label.setText(f"▸ {msg.upper()}")
            self._diag_label.setStyleSheet(
                f"color: {color}; font-size: 9px; font-weight: 700; "
                f"padding: 4px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 3px;"
            )

        ItemInteractionHelper.open_market_with_fallback(
            ESIClient(), char_id, type_id, item_name, feedback
        )

    # ── Auto-Refresh Logic ───────────────────────────────────────────
    
    def on_auto_refresh_toggled(self, checked):
        self.config.auto_refresh_enabled = checked
        from core.config_manager import save_performance_config
        save_performance_config(self.config)
        
        if checked:
            self.start_auto_refresh()
        else:
            self.auto_timer.stop()
            self.refresh_view() # Para limpiar el texto de "Next sync" en el diag label

    def on_auto_interval_changed(self):
        val = self.combo_auto_time.currentData()
        self.config.refresh_interval_min = val
        from core.config_manager import save_performance_config
        save_performance_config(self.config)
        if self.check_auto.isChecked():
            self.start_auto_refresh()

    def on_diag_fees_clicked(self):
        char_id = self.combo_char.currentData()
        if not char_id or char_id <= 0:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Diagnóstico de Fees", "Selecciona un personaje válido primero.")
            return
            
        days_map = {0: 1, 1: 7, 2: 30, 3: 90}
        days = days_map.get(self.combo_range.currentIndex(), 30)
        from datetime import datetime, timedelta
        date_to   = datetime.utcnow().strftime("%Y-%m-%d")
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        from core.performance_fee_diagnostics import diagnose_fee_allocation, format_fee_diagnostics_report
        import sqlite3
        
        try:
            conn = sqlite3.connect(self.engine.db_path)
            diag_data = diagnose_fee_allocation(conn, char_id, date_from, date_to)
            report = format_fee_diagnostics_report(diag_data)
            conn.close()
            
            dialog = FeeDiagnosticsDialog(report, self)
            dialog.exec()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error de Diagnóstico", f"No se pudo generar el reporte: {e}")



    def start_auto_refresh(self):
        self._next_sync_seconds = self.config.refresh_interval_min * 60
        self.auto_timer.start(1000) # Tick cada segundo

    def _on_auto_timer_tick(self):
        if not self.config.auto_refresh_enabled:
            self.auto_timer.stop()
            return
            
        if self._sync_in_progress:
            return # Esperamos a que termine la actual antes de descontar

        self._next_sync_seconds -= 1
        
        # Actualizar feedback visual (re-usamos refresh_view que actualiza diag label)
        self.refresh_view()
        
        if self._next_sync_seconds <= 0:
            self.auto_timer.stop() # Pausar mientras sincroniza
            self.on_sync_clicked(is_auto=True)

    def _load_icon_into_table_item(self, table, row, col, type_id, pixmap, generation):
        """Helper seguro para cargar iconos en tablas sin riesgo de RuntimeError."""
        try:
            if generation != self._image_generation:
                return
            if table is None or row < 0 or row >= table.rowCount():
                return
            if col < 0 or col >= table.columnCount():
                return
            item = table.item(row, col)
            if item is None or item.data(Qt.UserRole) != type_id:
                return
            item.setIcon(QIcon(pixmap))
        except RuntimeError:
            return

class FeeDiagnosticsDialog(QDialog):
    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnóstico de Wallet Fees")
        self.setMinimumSize(700, 600)
        self.setStyleSheet("background: #0f172a; color: #f1f5f9;")
        
        layout = QVBoxLayout(self)
        
        header = QLabel("DIAGNÓSTICO DE ASIGNACIÓN DE FEES")
        header.setStyleSheet("color: #3b82f6; font-size: 14px; font-weight: 900;")
        layout.addWidget(header)
        
        desc = QLabel("Este reporte analiza cómo se vinculan las comisiones (Broker) e impuestos (Tax) a tus transacciones.")
        desc.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(desc)
        
        from PySide6.QtWidgets import QTextEdit
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setPlainText(report)
        self.text_area.setStyleSheet("""
            QTextEdit {
                background: #000000;
                color: #10b981;
                border: 1px solid #1e293b;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.text_area)
        
        btns = QHBoxLayout()
        btn_copy = QPushButton("COPIAR REPORTE")
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; padding: 8px; border-radius: 4px;")
        btn_copy.clicked.connect(self.copy_to_clipboard)
        
        btn_close = QPushButton("CERRAR")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: 800; padding: 8px; border-radius: 4px;")
        btn_close.clicked.connect(self.accept)
        
        btns.addStretch()
        btns.addWidget(btn_copy)
        btns.addWidget(btn_close)
        layout.addLayout(btns)
        
    def copy_to_clipboard(self):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.text_area.toPlainText())
        # Visual feedback
        btn = self.sender()
        old_text = btn.text()
        btn.setText("¡COPIADO!")
        btn.setStyleSheet("background: #10b981; color: white; font-weight: 800; padding: 8px; border-radius: 4px;")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._reset_copy_btn(btn, old_text))
        
    def _reset_copy_btn(self, btn, old_text):
        btn.setText(old_text)
        btn.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; padding: 8px; border-radius: 4px;")
