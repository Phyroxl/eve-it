# VERSION_STAMP: 2026-04-27_20-00_ADVANCED_RESTORED
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QComboBox, QScrollArea, QGridLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QCheckBox,
    QProgressBar, QDoubleSpinBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from ui.market_command.widgets import AdvancedMarketTableWidget
from core.market_models import FilterConfig
from core.config_manager import save_market_filters, load_market_filters
from ui.market_command.refresh_worker import MarketRefreshWorker

_log = logging.getLogger('eve.market.advanced')

class MarketAdvancedView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.all_opportunities = []
        self.current_config = load_market_filters()
        self.lbl_status = None
        self.setup_ui()
        
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(12)
        
        # 1. Header Area
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MARKET COMMAND — MODO AVANZADO")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 900; letter-spacing: 1px;")
        subtitle = QLabel("CONFIGURACIÓN TÁCTICA Y ANÁLISIS ESTRATÉGICO")
        subtitle.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;")
        self.lbl_status = QLabel("● SISTEMA LISTO")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        
        title_v.addWidget(title_lbl)
        title_v.addWidget(subtitle)
        title_v.addWidget(self.lbl_status)
        
        self.btn_refresh = QPushButton("EJECUTAR ESCANEO AVANZADO")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setMinimumWidth(220)
        self.btn_refresh.setFixedHeight(35)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white; font-size: 10px; font-weight: 900;
                border-radius: 4px; letter-spacing: 1px; padding: 0 15px;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #1e293b; color: #64748b; }
        """)
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)
        
        # 2. Main Content Split
        content_split = QHBoxLayout()
        content_split.setSpacing(12)
        
        # LEFT: Advanced Filter Panel (Restored)
        filter_panel = QFrame()
        filter_panel.setObjectName("AnalyticBox")
        filter_panel.setFixedWidth(240) # Un poco más ancho para albergar los nuevos controles
        filter_panel.setStyleSheet("background-color: #0f172a; border-right: 1px solid #1e293b; border-radius: 4px;")
        filter_l = QVBoxLayout(filter_panel)
        filter_l.setContentsMargins(12, 12, 12, 12)
        filter_l.setSpacing(8)
        
        filter_l.addWidget(QLabel("FILTROS ESTRATÉGICOS", styleSheet="color: #64748b; font-size: 9px; font-weight: 900;"))
        
        # Filters List with Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)

        def add_adv_input(layout, label, widget):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
            lbl = QLabel(label.upper()); lbl.setStyleSheet("color: #475569; font-size: 7px; font-weight: 800;")
            widget.setStyleSheet("background: #000000; color: #f1f5f9; border: 1px solid #1e293b; padding: 3px; border-radius: 2px;")
            widget.setFixedHeight(26); v.addWidget(lbl); v.addWidget(widget); layout.addWidget(w)

        from core.item_categories import get_all_categories
        self.combo_category = QComboBox()
        self.combo_category.addItems(get_all_categories())
        self.combo_category.setCurrentText(self.current_config.selected_category)
        add_adv_input(scroll_layout, "Categoría", self.combo_category)

        self.spin_capital = QDoubleSpinBox()
        self.spin_capital.setRange(0, 1e12); self.spin_capital.setDecimals(0); self.spin_capital.setSuffix(" ISK")
        add_adv_input(scroll_layout, "Cap. Máximo", self.spin_capital)

        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0, 1000); self.spin_margin.setSuffix("%"); self.spin_margin.setDecimals(1)
        add_adv_input(scroll_layout, "Margen Mínimo %", self.spin_margin)

        self.spin_spread = QDoubleSpinBox()
        self.spin_spread.setRange(0, 999999); self.spin_spread.setSuffix("%"); self.spin_spread.setDecimals(1)
        add_adv_input(scroll_layout, "Spread Máximo %", self.spin_spread)

        # ─── BLOQUE 2: LIQUIDEZ Y VOLUMEN ───
        self.spin_vol = QSpinBox()
        self.spin_vol.setRange(0, 1000000)
        add_adv_input(scroll_layout, "Vol. Mínimo (Diario)", self.spin_vol)

        self.spin_buy_min = QSpinBox()
        self.spin_buy_min.setRange(0, 1000)
        add_adv_input(scroll_layout, "Mín. Órdenes Compra", self.spin_buy_min)

        self.spin_sell_min = QSpinBox()
        self.spin_sell_min.setRange(0, 1000)
        add_adv_input(scroll_layout, "Mín. Órdenes Venta", self.spin_sell_min)

        # ─── BLOQUE 3: COMISIONES Y TAX ───
        self.spin_broker = QDoubleSpinBox()
        self.spin_broker.setRange(0, 100); self.spin_broker.setSuffix("%"); self.spin_broker.setDecimals(2)
        add_adv_input(scroll_layout, "Broker Fee %", self.spin_broker)

        self.spin_tax = QDoubleSpinBox()
        self.spin_tax.setRange(0, 100); self.spin_tax.setSuffix("%"); self.spin_tax.setDecimals(2)
        add_adv_input(scroll_layout, "Sales Tax %", self.spin_tax)

        # ─── BLOQUE 4: PUNTUACIÓN Y RIESGO ───
        self.spin_profit_min = QDoubleSpinBox()
        self.spin_profit_min.setRange(0, 1e12); self.spin_profit_min.setDecimals(0); self.spin_profit_min.setSuffix(" ISK")
        add_adv_input(scroll_layout, "Profit Diario Mínimo", self.spin_profit_min)

        self.spin_score = QDoubleSpinBox()
        self.spin_score.setRange(0, 100); self.spin_score.setDecimals(1)
        add_adv_input(scroll_layout, "Score Mínimo (AI)", self.spin_score)

        self.combo_risk = QComboBox()
        self.combo_risk.addItems(["Cualquier Riesgo", "Máximo Medium", "Solo Low"])
        add_adv_input(scroll_layout, "Nivel de Riesgo Máx", self.combo_risk)

        self.check_plex = QCheckBox("EXCLUIR PLEX / SKINS")
        self.check_plex.setStyleSheet("color: #475569; font-size: 8px; font-weight: 700; margin-top: 5px;")
        scroll_layout.addWidget(self.check_plex)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        filter_l.addWidget(scroll)
        
        # Botones de Acción
        self.btn_apply = QPushButton("APLICAR FILTROS")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; border-radius: 4px; font-size: 10px;")
        self.btn_apply.clicked.connect(self.on_apply_filters)
        
        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setFixedHeight(22)
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.setStyleSheet("background: #1e293b; color: #64748b; font-size: 9px; font-weight: 800; border-radius: 4px;")
        self.btn_reset.clicked.connect(self.on_reset_filters)

        btn_row = QHBoxLayout(); btn_row.addWidget(self.btn_apply); btn_row.addWidget(self.btn_reset)
        filter_l.addLayout(btn_row)
        content_split.addWidget(filter_panel)
        
        # RIGHT: Table and Detail
        right_panel = QVBoxLayout(); right_panel.setSpacing(12)
        self.table = AdvancedMarketTableWidget()
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.item_action_triggered.connect(self.on_item_action)
        right_panel.addWidget(self.table, 1)
        
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(180)
        self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_ui()
        right_panel.addWidget(self.detail_panel)
        
        content_split.addLayout(right_panel, 1)
        self.main_layout.addLayout(content_split)
        
        # Progress Bar at bottom
        self.progress = QProgressBar(); self.progress.setFixedHeight(2); self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar { background: #1e293b; border: none; } QProgressBar::chunk { background: #3b82f6; }")
        self.main_layout.addWidget(self.progress)
        
        # Inicializar valores desde config
        self.update_ui_from_config()

    def setup_detail_ui(self):
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(15, 15, 15, 15)
        dl.setSpacing(20)
        
        # Section 1: Pilot & Name
        self.lbl_det_icon = QLabel(); self.lbl_det_icon.setFixedSize(64, 64)
        self.lbl_det_icon.setStyleSheet("background: #0f172a; border-radius: 4px;")
        name_v = QVBoxLayout()
        self.lbl_det_item = QLabel("ANÁLISIS ESTRATÉGICO")
        self.lbl_det_item.setStyleSheet("color: #f1f5f9; font-size: 15px; font-weight: 900;")
        self.lbl_det_tags = QLabel("---")
        self.lbl_det_tags.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 700;")
        name_v.addWidget(self.lbl_det_item); name_v.addWidget(self.lbl_det_tags); name_v.addStretch()
        dl.addWidget(self.lbl_det_icon); dl.addLayout(name_v, 1)

        # Metrics Grid
        m_g = QGridLayout()
        m_g.setSpacing(10)
        def add_metric(layout, row, col, label, color="#e2e8f0"):
            layout.addWidget(QLabel(label, styleSheet="color: #475569; font-size: 8px; font-weight: 800;"), row*2, col)
            val = QLabel("---"); val.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 800;")
            layout.addWidget(val, row*2+1, col)
            return val

        self.lbl_det_buy = add_metric(m_g, 0, 0, "BEST BUY")
        self.lbl_det_sell = add_metric(m_g, 0, 1, "BEST SELL")
        self.lbl_det_margin = add_metric(m_g, 1, 0, "MARGEN NETO", "#3b82f6")
        self.lbl_det_profit = add_metric(m_g, 1, 1, "PROFIT/U", "#10b981")
        dl.addLayout(m_g, 2)

        # Ops Section
        ops_v = QVBoxLayout()
        ops_v.addWidget(QLabel("MÉTRICAS DE FLUJO", styleSheet="color: #475569; font-size: 8px; font-weight: 800;"))
        self.lbl_det_vol = QLabel("Vol: ---"); self.lbl_det_vol.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 700;")
        self.lbl_det_depth = QLabel("Deep: ---"); self.lbl_det_depth.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
        ops_v.addWidget(self.lbl_det_vol); ops_v.addWidget(self.lbl_det_depth); ops_v.addStretch()
        dl.addLayout(ops_v, 1)

    def on_item_action(self, action, item_name, type_id):
        from ui.market_command.widgets import ItemInteractionHelper
        from core.esi_client import ESIClient
        from core.auth_manager import AuthManager
        auth = AuthManager.instance()
        def feedback(msg, color):
            if self.lbl_status:
                self.lbl_status.setText(f"● {msg.upper()}")
                self.lbl_status.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), auth.char_id, type_id, item_name, feedback)

    def on_refresh_clicked(self):
        if self.worker and self.worker.isRunning(): return
        self.update_config_from_ui()
        save_market_filters(self.current_config)
        self.worker = MarketRefreshWorker(region_id=10000002)
        self.worker.config = self.current_config
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.on_status_received)
        self.worker.data_ready.connect(self.on_scan_finished)
        self.worker.error_occurred.connect(self.on_scan_error)
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("ESCANEO EN CURSO...")
        self.progress.setValue(0)
        self.worker.start()

    def on_status_received(self, text):
        if self.lbl_status:
            self.lbl_status.setText(f"● {text.upper()}")
            self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

    def on_scan_finished(self, opportunities):
        self.all_opportunities = opportunities
        from core.market_engine import apply_filters
        filtered = apply_filters(opportunities, self.current_config)
        self.table.populate(filtered)
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("EJECUTAR ESCANEO AVANZADO")
        if self.lbl_status:
            self.lbl_status.setText(f"● ESCANEO COMPLETADO: {len(filtered)}/{len(opportunities)} ITEMS")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

    def on_scan_error(self, err_msg):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("EJECUTAR ESCANEO AVANZADO")
        if self.lbl_status:
            self.lbl_status.setText(f"● ERROR: {err_msg.upper()}")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

    def on_apply_filters(self):
        self.update_config_from_ui()
        import logging
        logging.getLogger('eve.market.advanced').info(f"[CATEGORY UI] mode=Advanced selected_category={self.current_config.selected_category}")
        save_market_filters(self.current_config)
        
        from core.market_engine import apply_filters
        filtered = apply_filters(self.all_opportunities, self.current_config)
        self.table.populate(filtered)

    def on_reset_filters(self):
        self.current_config = FilterConfig()
        save_market_filters(self.current_config)
        self.update_ui_from_config()
        self.table.populate(self.all_opportunities)

    def update_config_from_ui(self):
        self.current_config.capital_max = self.spin_capital.value()
        self.current_config.vol_min_day = self.spin_vol.value()
        self.current_config.margin_min_pct = self.spin_margin.value()
        self.current_config.spread_max_pct = self.spin_spread.value()
        self.current_config.exclude_plex = self.check_plex.isChecked()
        self.current_config.selected_category = self.combo_category.currentText()
        self.current_config.broker_fee_pct = self.spin_broker.value()
        self.current_config.sales_tax_pct = self.spin_tax.value()
        self.current_config.score_min = self.spin_score.value()
        self.current_config.buy_orders_min = self.spin_buy_min.value()
        self.current_config.sell_orders_min = self.spin_sell_min.value()
        self.current_config.profit_day_min = self.spin_profit_min.value()
        self.current_config.risk_max = self.combo_risk.currentIndex() + 1

    def update_ui_from_config(self):
        self.spin_capital.setValue(self.current_config.capital_max)
        self.spin_vol.setValue(self.current_config.vol_min_day)
        self.spin_margin.setValue(self.current_config.margin_min_pct)
        self.spin_spread.setValue(self.current_config.spread_max_pct)
        self.check_plex.setChecked(self.current_config.exclude_plex)
        self.combo_category.setCurrentText(self.current_config.selected_category)
        self.spin_broker.setValue(self.current_config.broker_fee_pct)
        self.spin_tax.setValue(self.current_config.sales_tax_pct)
        self.spin_score.setValue(self.current_config.score_min)
        self.spin_buy_min.setValue(self.current_config.buy_orders_min)
        self.spin_sell_min.setValue(self.current_config.sell_orders_min)
        self.spin_profit_min.setValue(self.current_config.profit_day_min)
        self.combo_risk.setCurrentIndex(max(0, self.current_config.risk_max - 1))

    def on_selection_changed(self):
        sel = self.table.selectedItems()
        if not sel: return
        row = sel[0].row()
        item_name = self.table.item(row, 1).text()
        opp = next((o for o in self.all_opportunities if o.item_name == item_name), None)
        if opp:
            self.update_detail(opp)

    def update_detail(self, opp):
        self.lbl_det_item.setText(opp.item_name.upper())
        tags_str = " ".join([f"[{t.upper()}]" for t in opp.tags])
        self.lbl_det_tags.setText(tags_str if tags_str else "ESTRATEGIA ESTÁNDAR")
        
        if opp.type_id in self.table.icon_cache:
            pixmap = self.table.icon_cache[opp.type_id]
            self.lbl_det_icon.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else: self.lbl_det_icon.clear()
        
        from utils.formatters import format_isk
        self.lbl_det_buy.setText(format_isk(opp.best_buy_price, True))
        self.lbl_det_sell.setText(format_isk(opp.best_sell_price, True))
        self.lbl_det_margin.setText(f"{opp.margin_net_pct:.1f}%")
        self.lbl_det_profit.setText(format_isk(opp.profit_per_unit, True))
        self.lbl_det_vol.setText(f"Vol (5D): {opp.liquidity.volume_5d}")
        self.lbl_det_depth.setText(f"Deep: {opp.liquidity.sell_depth} sell / {opp.liquidity.buy_depth} buy")
