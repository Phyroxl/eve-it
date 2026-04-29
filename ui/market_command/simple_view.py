import copy
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox, QFormLayout, QProgressBar, QFrame, QGridLayout, QScrollArea,
    QComboBox
)
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtCore import Qt
from ui.market_command.widgets import MarketTableWidget
from ui.market_command.refresh_worker import MarketRefreshWorker
from ui.market_command.diagnostics_dialog import MarketDiagnosticsDialog
from core.market_engine import apply_filters, apply_filters_with_diagnostics
from core.market_models import FilterConfig
from core.market_scan_diagnostics import MarketScanDiagnostics
from core.config_manager import save_market_filters, load_market_filters

class MarketSimpleView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.all_opportunities = []
        self.last_scan_diagnostics = None
        self._diag_dialog = None
        self.current_config = load_market_filters()
        self.setup_ui()
        
    def create_insight_box(self, title, color):
        f = QFrame()
        f.setStyleSheet("""
            QFrame {
                background-color: #1a1e23;
                border: 1px solid #2d3748;
                border-radius: 4px;
            }
        """)
        l = QVBoxLayout(f)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; border: none; background: transparent;")
        v = QLabel("---")
        v.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        l.addWidget(t)
        l.addWidget(v)
        return f, v

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)
        
        # 1. Header Area
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MARKET COMMAND — MODO SIMPLE")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 900; letter-spacing: 1px;")
        self.lbl_status = QLabel("● SISTEMA LISTO")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        title_v.addWidget(title_lbl)
        title_v.addWidget(self.lbl_status)
        
        self.btn_refresh = QPushButton("REFRESCAR MERCADO (ESI)")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setMinimumWidth(220)
        self.btn_refresh.setFixedHeight(35)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #3b82f6; border: 2px solid #3b82f6;
                font-size: 10px; font-weight: 900; border-radius: 4px; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: rgba(59, 130, 246, 0.1); }
            QPushButton:disabled { color: #334155; border-color: #334155; }
        """)
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)
        
        # 2. Main Content Split
        content_split = QHBoxLayout()
        content_split.setSpacing(15)
        
        # LEFT: Tactical Configuration
        filter_panel = QFrame()
        filter_panel.setObjectName("AnalyticBox")
        filter_panel.setFixedWidth(240)
        filter_panel.setStyleSheet("background-color: #0f172a; border-right: 1px solid #1e293b; border-radius: 4px;")
        filter_l = QVBoxLayout(filter_panel)
        filter_l.setContentsMargins(12, 12, 12, 12)
        filter_l.setSpacing(12)
        
        filter_l.addWidget(QLabel("CONFIGURACIÓN TÁCTICA", styleSheet="color: #64748b; font-size: 9px; font-weight: 900; letter-spacing: 1px;"))
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)

        def add_compact_input(layout, label, widget):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            lbl = QLabel(label.upper())
            lbl.setStyleSheet("color: #475569; font-size: 8px; font-weight: 800;")
            widget.setStyleSheet("background: #000000; color: #f1f5f9; border: 1px solid #1e293b; padding: 4px; border-radius: 2px;")
            widget.setFixedHeight(28)
            v.addWidget(lbl)
            v.addWidget(widget)
            layout.addWidget(w)

        from core.item_categories import get_all_categories
        self.combo_category = QComboBox()
        self.combo_category.addItems(get_all_categories())
        self.combo_category.setCurrentText(self.current_config.selected_category)
        add_compact_input(scroll_layout, "Categoría", self.combo_category)

        self.spin_capital = QDoubleSpinBox()
        self.spin_capital.setRange(0, 1e12); self.spin_capital.setDecimals(0); self.spin_capital.setSuffix(" ISK")
        self.spin_capital.setValue(self.current_config.capital_max)
        add_compact_input(scroll_layout, "Cap. Máximo", self.spin_capital)

        self.spin_vol = QSpinBox()
        self.spin_vol.setRange(0, 10000); self.spin_vol.setValue(self.current_config.vol_min_day)
        add_compact_input(scroll_layout, "Vol. Mínimo (5D)", self.spin_vol)

        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0, 100); self.spin_margin.setSuffix("%"); self.spin_margin.setValue(self.current_config.margin_min_pct)
        add_compact_input(scroll_layout, "Margen Mínimo %", self.spin_margin)

        self.spin_spread = QDoubleSpinBox()
        self.spin_spread.setRange(0, 999999); self.spin_spread.setSuffix("%"); self.spin_spread.setValue(self.current_config.spread_max_pct)
        add_compact_input(scroll_layout, "Spread Máximo %", self.spin_spread)

        self.spin_broker = QDoubleSpinBox()
        self.spin_broker.setRange(0, 10); self.spin_broker.setSuffix("%"); self.spin_broker.setValue(self.current_config.broker_fee_pct)
        add_compact_input(scroll_layout, "Broker Fee %", self.spin_broker)

        self.spin_tax = QDoubleSpinBox()
        self.spin_tax.setRange(0, 10); self.spin_tax.setSuffix("%"); self.spin_tax.setValue(self.current_config.sales_tax_pct)
        add_compact_input(scroll_layout, "Sales Tax %", self.spin_tax)

        self.chk_plex = QCheckBox("EXCLUIR PLEX / VOLÁTILES")
        self.chk_plex.setChecked(self.current_config.exclude_plex)
        self.chk_plex.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; margin-top: 5px;")
        scroll_layout.addWidget(self.chk_plex)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        filter_l.addWidget(scroll)

        self.btn_apply = QPushButton("APLICAR FILTROS")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setStyleSheet("background: #3b82f6; color: white; font-weight: 800; border-radius: 4px; font-size: 10px;")
        self.btn_apply.clicked.connect(self.on_apply_filters)
        
        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setFixedHeight(24)
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.setStyleSheet("background: #1e293b; color: #64748b; font-size: 9px; font-weight: 800; border-radius: 4px;")
        self.btn_reset.clicked.connect(self.on_reset_filters)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_reset)
        filter_l.addLayout(btn_row)

        content_split.addWidget(filter_panel)

        # RIGHT: Items and Insights
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)
        
        insights_l = QHBoxLayout()
        insights_l.setSpacing(8)
        self.box_top, self.lbl_sum_top = self.create_insight_box("Mejor", "#fbbf24")
        self.box_liq, self.lbl_sum_liquid = self.create_insight_box("Líquida", "#60a5fa")
        self.box_mar, self.lbl_sum_margin = self.create_insight_box("Margen", "#34d399")
        self.box_cnt, self.lbl_sum_count = self.create_insight_box("Filtrados", "#a78bfa")
        self.box_ins, self.lbl_sum_insight = self.create_insight_box("Lectura", "#94a3b8")
        
        for b in [self.box_top, self.box_liq, self.box_mar, self.box_cnt, self.box_ins]:
            insights_l.addWidget(b)
        right_panel.addLayout(insights_l)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(2); self.progress_bar.setTextVisible(False); self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #1e293b; border: none; } QProgressBar::chunk { background: #3b82f6; }")
        right_panel.addWidget(self.progress_bar)

        self.table = MarketTableWidget()
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        self.table.item_action_triggered.connect(self.on_item_action)
        right_panel.addWidget(self.table, 1)
        
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(90)
        self.detail_panel.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 4px;")
        self.setup_detail_layout()
        right_panel.addWidget(self.detail_panel)
        
        content_split.addLayout(right_panel, 1)
        self.main_layout.addLayout(content_split)

    def setup_detail_layout(self):
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(10, 10, 10, 10)
        dl.setSpacing(15)
        
        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setFixedSize(48, 48)
        self.lbl_det_icon.setStyleSheet("background: #0f172a; border-radius: 4px;")
        dl.addWidget(self.lbl_det_icon)
        
        name_v = QVBoxLayout()
        self.lbl_det_item = QLabel("SELECCIONA ITEM")
        self.lbl_det_item.setFixedHeight(20)
        self.lbl_det_item.setFixedWidth(280) # Ancho fijo para evitar que crezca la grid
        self.lbl_det_item.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 900; border: none;")
        self.lbl_det_tags = QLabel("---")
        self.lbl_det_tags.setFixedHeight(12)
        self.lbl_det_tags.setFixedWidth(280)
        self.lbl_det_tags.setStyleSheet("color: #3b82f6; font-size: 9px; font-weight: 700; border: none;")
        name_v.addWidget(self.lbl_det_item); name_v.addWidget(self.lbl_det_tags); name_v.addStretch()
        
        dl.addLayout(name_v)

        m_g = QGridLayout()
        m_g.setSpacing(5)
        def add_det_metric(layout, row, col, lbl_txt, val_obj, color="#e2e8f0"):
            lbl = QLabel(lbl_txt, styleSheet="color: #475569; font-size: 7px; font-weight: 800;")
            lbl.setFixedWidth(80)
            layout.addWidget(lbl, row*2, col)
            val_obj.setFixedWidth(80)
            val_obj.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 800;")
            layout.addWidget(val_obj, row*2+1, col)

        self.lbl_det_buy = QLabel("---"); self.lbl_det_sell = QLabel("---")
        self.lbl_det_profit = QLabel("---"); self.lbl_det_margin = QLabel("---")
        add_det_metric(m_g, 0, 0, "BUY PRICE", self.lbl_det_buy)
        add_det_metric(m_g, 0, 1, "SELL PRICE", self.lbl_det_sell)
        add_det_metric(m_g, 1, 0, "NET PROFIT", self.lbl_det_profit, "#10b981")
        add_det_metric(m_g, 1, 1, "MARGIN %", self.lbl_det_margin, "#3b82f6")
        dl.addLayout(m_g)

        s_v = QVBoxLayout()
        s_v.addWidget(QLabel("SCORE & RISK", styleSheet="color: #475569; font-size: 7px; font-weight: 800;"))
        self.lbl_det_score = QLabel("0.0"); self.lbl_det_score.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900;")
        self.lbl_det_pens = QLabel("---"); self.lbl_det_pens.setStyleSheet("color: #64748b; font-size: 8px; font-weight: 600;")
        s_v.addWidget(self.lbl_det_score); s_v.addWidget(self.lbl_det_pens); s_v.addStretch()
        dl.addLayout(s_v, 1)

        r_v = QVBoxLayout()
        r_v.addWidget(QLabel("RECOMMENDED QTY", styleSheet="color: #475569; font-size: 7px; font-weight: 800;"))
        self.lbl_det_rec_qty = QLabel("0 uds"); self.lbl_det_rec_qty.setStyleSheet("color: #fbbf24; font-size: 14px; font-weight: 900;")
        self.lbl_det_rec_cost = QLabel("Cost: 0 ISK"); self.lbl_det_rec_cost.setStyleSheet("color: #64748b; font-size: 8px; font-weight: 600;")
        r_v.addWidget(self.lbl_det_rec_qty); r_v.addWidget(self.lbl_det_rec_cost); r_v.addStretch()
        dl.addLayout(r_v, 1)

    def on_item_action(self, action, item_name, type_id):
        if action == "copied":
            self.lbl_status.setText(f"● PORTAPAPELES: {item_name.upper()}")
            self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        elif action == "opened_in_game":
            self.lbl_status.setText(f"● EVE ONLINE: MERCADO ABIERTO ({item_name.upper()})")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        elif action == "double_clicked":
            from ui.market_command.widgets import ItemInteractionHelper
            from core.esi_client import ESIClient
            from core.auth_manager import AuthManager
            auth = AuthManager.instance()
            def feedback(msg, color):
                self.lbl_status.setText(f"● {msg.upper()}")
                self.lbl_status.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
            ItemInteractionHelper.open_market_with_fallback(ESIClient(), auth.char_id, type_id, item_name, feedback)

    def on_refresh_clicked(self):
        if self.worker and self.worker.isRunning(): return
        self.update_config_from_ui()
        self.btn_refresh.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("● OBTENIENDO MERCADO (ESI)...")
        self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        self.worker = MarketRefreshWorker(region_id=10000002, config=copy.deepcopy(self.current_config))
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.initial_data_ready.connect(self.on_initial_data_ready)
        self.worker.enriched_data_ready.connect(self.on_enriched_data_ready)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.diagnostics_ready.connect(self.on_diagnostics_ready) # New
        self.worker.start()

    def on_progress(self, pct, text):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"● {text.upper()}")

    def on_initial_data_ready(self, opps):
        import logging
        logging.getLogger('eve.market.simple').info(f"[PIPELINE] initial_opportunities={len(opps)}")
        self.update_config_from_ui()
        self.all_opportunities = opps
        self.apply_and_display()
        cat = self.current_config.selected_category
        if opps:
            msg = f"● RESULTADOS INICIALES ({len(opps)}) — ENRIQUECIENDO HISTORIAL..."
        else:
            msg = f"● BUSCANDO {cat.upper()}... DESCARGANDO METADATA" if cat != "Todos" else "● ENRIQUECIENDO..."
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #fbbf24; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        self.btn_refresh.setText("ENRIQUECIENDO...")

    def on_enriched_data_ready(self, opps):
        import logging
        logging.getLogger('eve.market.simple').info(f"[PIPELINE] enriched_opportunities={len(opps)}")
        self.update_config_from_ui()
        self.all_opportunities = opps
        self.apply_and_display()
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("REFRESCAR MERCADO (ESI)")
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("● ESCANEO COMPLETADO — DATOS ENRIQUECIDOS")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

    def on_error(self, err_msg):
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"● ERROR: {err_msg.upper()}")
        self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

    def on_diagnostics_ready(self, diagnostics):
        from PySide6.QtCore import QTimer
        self.last_scan_diagnostics = diagnostics
        # Delay opening to ensure UI has applied final filters for the report
        QTimer.singleShot(500, lambda: self.complete_and_show_diagnostics(diagnostics))

    def complete_and_show_diagnostics(self, diagnostics):
        # 1. Update config from UI to have final filter values
        self.update_config_from_ui()
        
        # 2. Get fresh filter diagnostics for the report
        _, filter_diag = apply_filters_with_diagnostics(self.all_opportunities, self.current_config)
        
        # 3. Populate diagnostics object
        diagnostics.ui_all_opportunities_count = len(self.all_opportunities)
        diagnostics.ui_filtered_count = len([o for o in self.all_opportunities if o in self.all_opportunities]) # Just count pass
        # Re-apply filters to get exact filtered count if needed, or just use filter_diag result
        filtered_results, _ = apply_filters_with_diagnostics(self.all_opportunities, self.current_config)
        diagnostics.ui_filtered_count = len(filtered_results)
        
        diagnostics.ui_config_at_filter_time = self.current_config.__dict__.copy() if hasattr(self.current_config, '__dict__') else {}
        diagnostics.filter_diagnostics = filter_diag
        diagnostics.dominant_filter = filter_diag.get("dominant_filter")
        diagnostics.selected_category_ui = self.current_config.selected_category
        diagnostics.mode = "Simple"
        
        if hasattr(self.table, 'get_icon_diagnostics'):
            icon_stats = self.table.get_icon_diagnostics()
            diagnostics.icon_requests = icon_stats.get("icon_requests", 0)
            diagnostics.icon_loaded = icon_stats.get("icon_loaded", 0)
            diagnostics.icon_failed = icon_stats.get("icon_failed", 0)
            diagnostics.icon_cache_size = icon_stats.get("icon_cache_size", 0)

        # 4. Show dialog and keep reference to prevent GC
        self._diag_dialog = MarketDiagnosticsDialog(diagnostics.to_report(), self)
        self._diag_dialog.show()

    def update_config_from_ui(self):
        self.current_config.capital_max = self.spin_capital.value()
        self.current_config.vol_min_day = self.spin_vol.value()
        self.current_config.margin_min_pct = self.spin_margin.value()
        self.current_config.spread_max_pct = self.spin_spread.value()
        self.current_config.broker_fee_pct = self.spin_broker.value()
        self.current_config.sales_tax_pct = self.spin_tax.value()
        self.current_config.exclude_plex = self.chk_plex.isChecked()
        self.current_config.selected_category = self.combo_category.currentText()
        
        # Reset advanced filters to safe defaults in Simple Mode
        self.current_config.buy_orders_min = 0
        self.current_config.sell_orders_min = 0
        self.current_config.history_days_min = 0
        self.current_config.profit_day_min = 0
        self.current_config.risk_max = 3 # Any risk
        self.current_config.score_min = 0

    def on_apply_filters(self):
        self.update_config_from_ui()
        import logging
        logging.getLogger('eve.market.simple').info(f"[CATEGORY UI] mode=Simple selected_category={self.current_config.selected_category}")
        save_market_filters(self.current_config)
        self.apply_and_display()

    def on_reset_filters(self):
        self.current_config = FilterConfig()
        save_market_filters(self.current_config)
        self.update_ui_from_config()
        self.apply_and_display()

    def update_ui_from_config(self):
        self.spin_capital.setValue(self.current_config.capital_max)
        self.spin_vol.setValue(self.current_config.vol_min_day)
        self.spin_margin.setValue(self.current_config.margin_min_pct)
        self.spin_spread.setValue(self.current_config.spread_max_pct)
        self.chk_plex.setChecked(self.current_config.exclude_plex)
        self.spin_broker.setValue(self.current_config.broker_fee_pct)
        self.spin_tax.setValue(self.current_config.sales_tax_pct)
        self.combo_category.setCurrentText(self.current_config.selected_category)

    def apply_and_display(self):
        import logging
        log = logging.getLogger('eve.market.simple')
        total_raw = len(self.all_opportunities)
        log.info(f"[UI DIAG] before_apply_filters={total_raw} selected_category={self.current_config.selected_category}")
        
        filtered, diag = apply_filters_with_diagnostics(self.all_opportunities, self.current_config)
        filtered.sort(key=lambda x: x.score_breakdown.final_score if x.score_breakdown else 0, reverse=True)
        
        log.info(f"[UI DIAG] after_apply_filters={len(filtered)}")
        
        top_50 = filtered[:50]
        self.table.populate(top_50)
        
        self.lbl_sum_count.setText(f"{len(filtered)}")
        
        # Actualizar UI si no hay resultados
        if total_raw == 0:
            self.lbl_sum_top.setText("---"); self.lbl_sum_liquid.setText("---"); self.lbl_sum_margin.setText("---")
            self.lbl_sum_insight.setText("SIN DATOS DEL ESCANEO")
            self.lbl_sum_insight.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: 800; border: none; background: transparent;")
            self.lbl_status.setText("● SIN DATOS DISPONIBLES — REALIZA UN ESCANEO")
            self.lbl_status.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        elif len(filtered) == 0:
            self.lbl_sum_top.setText("---"); self.lbl_sum_liquid.setText("---"); self.lbl_sum_margin.setText("---")
            
            dom = diag.get("dominant_filter", "DESCONOCIDO")
            count = diag["removed"].get(dom, total_raw)
            self.lbl_sum_insight.setText(f"FILTRO DOMINANTE: {dom.upper()} ({count})")
            self.lbl_sum_insight.setStyleSheet("color: #f87171; font-size: 11px; font-weight: 800; border: none; background: transparent;")
            
            self.lbl_status.setText(f"● {total_raw} ITEMS ENCONTRADOS PERO 0 PASAN FILTRO: {dom.upper()}")
            self.lbl_status.setStyleSheet("color: #f87171; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        else:
            self.lbl_sum_top.setText(top_50[0].item_name)
            liquid_opp = max(filtered, key=lambda x: x.liquidity.volume_5d)
            self.lbl_sum_liquid.setText(f"{liquid_opp.item_name}")
            solid_opps = [o for o in filtered if "Sólida" in o.tags]
            if solid_opps:
                best_solid = max(solid_opps, key=lambda x: x.margin_net_pct)
                self.lbl_sum_margin.setText(f"{best_solid.item_name} ({best_solid.margin_net_pct:.1f}%)")
            else: self.lbl_sum_margin.setText("Ninguna")
            if len(filtered) > 50:
                self.lbl_sum_insight.setText("MERCADO SALUDABLE")
                self.lbl_sum_insight.setStyleSheet("color: #34d399; font-size: 13px; font-weight: 800; border: none; background: transparent;")
            else:
                self.lbl_sum_insight.setText("ALTA SELECTIVIDAD")
                self.lbl_sum_insight.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 800; border: none; background: transparent;")

    def on_table_selection(self):
        sel = self.table.selectedItems()
        if not sel:
            self.lbl_det_item.setText("SELECCIONA UN ITEM"); self.lbl_det_tags.setText("---"); self.lbl_det_icon.clear()
            return
        row = sel[0].row()
        item_name = self.table.item(row, 1).text()
        opp = next((o for o in self.all_opportunities if o.item_name == item_name), None)
        if opp:
            # Texto elidido para el nombre
            metrics = self.lbl_det_item.fontMetrics()
            elided = metrics.elidedText(opp.item_name.upper(), Qt.ElideRight, self.lbl_det_item.width())
            self.lbl_det_item.setText(elided)
            self.lbl_det_item.setToolTip(opp.item_name.upper())

            tags_str = " ".join([f"[{t.upper()}]" for t in opp.tags])
            self.lbl_det_tags.setText(tags_str if tags_str else "SIN ETIQUETAS")
            if opp.type_id in self.table.icon_cache:
                pixmap = self.table.icon_cache[opp.type_id]
                self.lbl_det_icon.setPixmap(pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else: 
                # Placeholder si no hay icono aún
                placeholder = QPixmap(48, 48)
                placeholder.fill(QColor("#0f172a"))
                self.lbl_det_icon.setPixmap(placeholder)
            
            from utils.formatters import format_isk
            self.lbl_det_buy.setText(f"{format_isk(opp.best_buy_price, short=True)} ISK")
            self.lbl_det_sell.setText(f"{format_isk(opp.best_sell_price, short=True)} ISK")
            self.lbl_det_profit.setText(f"{format_isk(opp.profit_per_unit, short=False)} ISK")
            self.lbl_det_margin.setText(f"{opp.margin_net_pct:.1f}%")
            
            sb = opp.score_breakdown
            if sb:
                self.lbl_det_score.setText(f"{sb.final_score:.1f}")
                if sb.final_score > 70: self.lbl_det_score.setStyleSheet("color: #34d399; font-size: 18px; font-weight: 900;")
                elif sb.final_score > 40: self.lbl_det_score.setStyleSheet("color: #fbbf24; font-size: 18px; font-weight: 900;")
                else: self.lbl_det_score.setStyleSheet("color: #f87171; font-size: 18px; font-weight: 900;")
                penalties = ", ".join([f"x{p:.2f}" for p in sb.penalties]) if sb.penalties else "Ninguna"
                self.lbl_det_pens.setText(f"Riesgo: {opp.risk_level.upper()} | {penalties}")
            
            # Cantidad Recomendada
            safe_qty = int(opp.liquidity.volume_5d / 3.3)
            if safe_qty < 1: safe_qty = 1
            if "Alto" in opp.risk_level: safe_qty = int(safe_qty * 0.5)
            max_afford = int(self.current_config.capital_max / opp.best_buy_price) if opp.best_buy_price > 0 else 0
            rec_qty = min(safe_qty, max_afford)
            if rec_qty <= 0: rec_qty = 1
            self.lbl_det_rec_qty.setText(f"{rec_qty:,} uds")
            self.lbl_det_rec_cost.setText(f"Coste: {format_isk(rec_qty * opp.best_buy_price, short=True)} ISK")
