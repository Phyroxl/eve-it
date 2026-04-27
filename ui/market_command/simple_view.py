from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox, QFormLayout, QProgressBar, QFrame, QGridLayout
)
from PySide6.QtCore import Qt
from ui.market_command.widgets import MarketTableWidget
from ui.market_command.refresh_worker import MarketRefreshWorker
from core.market_engine import apply_filters
from core.market_models import FilterConfig

class MarketSimpleView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.all_opportunities = []
        self.current_config = FilterConfig()
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
        l.setContentsMargins(12, 10, 12, 10)
        l.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; border: none; background: transparent;")
        v = QLabel("---")
        v.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 800; border: none; background: transparent;")
        l.addWidget(t)
        l.addWidget(v)
        return f, v

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        # Left Panel: Filters
        filter_panel = QGroupBox("Filtros Modo Simple")
        filter_panel.setFixedWidth(300)
        filter_layout = QFormLayout(filter_panel)
        
        self.spin_capital = QDoubleSpinBox()
        self.spin_capital.setRange(0, 1000000000000)
        self.spin_capital.setValue(self.current_config.capital_max)
        self.spin_capital.setSuffix(" ISK")
        self.spin_capital.setDecimals(0)
        
        self.spin_vol = QSpinBox()
        self.spin_vol.setRange(0, 10000)
        self.spin_vol.setValue(self.current_config.vol_min_day)
        
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0, 100)
        self.spin_margin.setValue(self.current_config.margin_min_pct)
        self.spin_margin.setSuffix("%")
        
        self.spin_spread = QDoubleSpinBox()
        self.spin_spread.setRange(0, 100)
        self.spin_spread.setValue(self.current_config.spread_max_pct)
        self.spin_spread.setSuffix("%")
        
        self.chk_plex = QCheckBox("Excluir PLEX")
        self.chk_plex.setChecked(self.current_config.exclude_plex)
        
        self.spin_broker = QDoubleSpinBox()
        self.spin_broker.setRange(0, 100)
        self.spin_broker.setValue(self.current_config.broker_fee_pct)
        self.spin_broker.setSuffix("%")
        
        self.spin_tax = QDoubleSpinBox()
        self.spin_tax.setRange(0, 100)
        self.spin_tax.setValue(self.current_config.sales_tax_pct)
        self.spin_tax.setSuffix("%")
        
        filter_layout.addRow("Capital Max:", self.spin_capital)
        filter_layout.addRow("Min Vol/Día:", self.spin_vol)
        filter_layout.addRow("Min Margen:", self.spin_margin)
        filter_layout.addRow("Max Spread:", self.spin_spread)
        filter_layout.addRow("Broker Fee:", self.spin_broker)
        filter_layout.addRow("Sales Tax:", self.spin_tax)
        filter_layout.addRow("", self.chk_plex)
        
        self.btn_apply = QPushButton("Aplicar Filtros")
        self.btn_apply.clicked.connect(self.on_apply_filters)
        filter_layout.addRow("", self.btn_apply)
        
        self.btn_refresh = QPushButton("Refrescar Mercado (ESI)")
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        filter_layout.addRow("", self.btn_refresh)
        
        # Right Panel: Table and Progress
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(10)
        
        # HEADER
        header_l = QHBoxLayout()
        title_lbl = QLabel("MARKET COMMAND")
        title_lbl.setStyleSheet("color: #e2e8f0; font-size: 16px; font-weight: 800; letter-spacing: 1px;")
        
        self.lbl_status = QLabel("● ESPERANDO DATOS DE JITA")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        
        header_l.addWidget(title_lbl)
        header_l.addStretch()
        header_l.addWidget(self.lbl_status)
        right_layout.addLayout(header_l)
        
        # INSIGHTS
        insights_l = QHBoxLayout()
        insights_l.setSpacing(10)
        self.box_top, self.lbl_sum_top = self.create_insight_box("Mejor Oportunidad", "#fbbf24")
        self.box_liq, self.lbl_sum_liquid = self.create_insight_box("Más Líquida", "#60a5fa")
        self.box_mar, self.lbl_sum_margin = self.create_insight_box("Mayor Margen Sólido", "#34d399")
        self.box_cnt, self.lbl_sum_count = self.create_insight_box("Total Filtros", "#a78bfa")
        self.box_ins, self.lbl_sum_insight = self.create_insight_box("Lectura Mercado", "#94a3b8")
        
        insights_l.addWidget(self.box_top)
        insights_l.addWidget(self.box_liq)
        insights_l.addWidget(self.box_mar)
        insights_l.addWidget(self.box_cnt)
        insights_l.addWidget(self.box_ins)
        right_layout.addLayout(insights_l)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #1e293b; border: none; }
            QProgressBar::chunk { background-color: #3b82f6; }
        """)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.table = MarketTableWidget()
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        self.table.item_action_triggered.connect(self.on_item_action)
        right_layout.addWidget(self.table, 1)
        
        # DETAIL PANEL
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(110)
        self.detail_panel.setStyleSheet("""
            QFrame { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 4px; }
            QLabel { border: none; background: transparent; }
        """)
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(15, 15, 15, 15)
        dl.setSpacing(20)
        
        # Section 1: Identity
        id_l = QVBoxLayout()
        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setFixedSize(64, 64)
        self.lbl_det_item = QLabel("SELECCIONA UN ITEM")
        self.lbl_det_item.setStyleSheet("color: #f8fafc; font-size: 15px; font-weight: 900; letter-spacing: 0.5px;")
        self.lbl_det_tags = QLabel("---")
        self.lbl_det_tags.setStyleSheet("color: #60a5fa; font-size: 11px; font-weight: 800;")
        id_l.addWidget(self.lbl_det_item)
        id_l.addWidget(self.lbl_det_tags)
        id_l.addStretch()
        
        dl.addWidget(self.lbl_det_icon)
        dl.addLayout(id_l, 2)
        
        # Section 2: Metrics
        m_l = QGridLayout()
        m_l.setSpacing(8)
        lbl_buy = QLabel("BUY PRICE")
        lbl_buy.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        m_l.addWidget(lbl_buy, 0, 0)
        self.lbl_det_buy = QLabel("---")
        self.lbl_det_buy.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: 800;")
        m_l.addWidget(self.lbl_det_buy, 1, 0)
        
        lbl_sell = QLabel("SELL PRICE")
        lbl_sell.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        m_l.addWidget(lbl_sell, 0, 1)
        self.lbl_det_sell = QLabel("---")
        self.lbl_det_sell.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: 800;")
        m_l.addWidget(self.lbl_det_sell, 1, 1)
        
        lbl_prof = QLabel("NET PROFIT")
        lbl_prof.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        m_l.addWidget(lbl_prof, 2, 0)
        self.lbl_det_profit = QLabel("---")
        self.lbl_det_profit.setStyleSheet("color: #34d399; font-size: 14px; font-weight: 900;")
        m_l.addWidget(self.lbl_det_profit, 3, 0)
        
        lbl_marg = QLabel("NET MARGIN")
        lbl_marg.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        m_l.addWidget(lbl_marg, 2, 1)
        self.lbl_det_margin = QLabel("---")
        self.lbl_det_margin.setStyleSheet("color: #3b82f6; font-size: 14px; font-weight: 900;")
        m_l.addWidget(self.lbl_det_margin, 3, 1)
        
        dl.addLayout(m_l, 2)
        
        # Section 3: Score Breakdown
        s_l = QVBoxLayout()
        s_l.setSpacing(2)
        lbl_score_risk = QLabel("SCORE & RIESGO")
        lbl_score_risk.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        s_l.addWidget(lbl_score_risk)
        self.lbl_det_score = QLabel("0.0")
        self.lbl_det_score.setStyleSheet("color: #f1f5f9; font-size: 24px; font-weight: 900;")
        self.lbl_det_pens = QLabel("Ninguna")
        self.lbl_det_pens.setStyleSheet("color: #f87171; font-size: 10px; font-weight: 600;")
        s_l.addWidget(self.lbl_det_score)
        s_l.addWidget(self.lbl_det_pens)
        s_l.addStretch()
        dl.addLayout(s_l, 2)
        
        # Section 4: Operations
        o_l = QVBoxLayout()
        o_l.setSpacing(2)
        lbl_rec_buy = QLabel("RECOMENDACIÓN COMPRA")
        lbl_rec_buy.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        o_l.addWidget(lbl_rec_buy)
        self.lbl_det_rec_qty = QLabel("0 uds")
        self.lbl_det_rec_qty.setStyleSheet("color: #fbbf24; font-size: 18px; font-weight: 900;")
        self.lbl_det_rec_cost = QLabel("Coste Estimado: 0 ISK")
        self.lbl_det_rec_cost.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        o_l.addWidget(self.lbl_det_rec_qty)
        o_l.addWidget(self.lbl_det_rec_cost)
        o_l.addStretch()
        dl.addLayout(o_l, 2)

        right_layout.addWidget(self.detail_panel)
        
        main_layout.addWidget(filter_panel)
        main_layout.addWidget(right_panel)
        
    def on_item_action(self, action, item_name):
        if action == "copied":
            self.lbl_status.setText(f"● PORTAPAPELES: {item_name.upper()}")
            self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        elif action == "opened_in_game":
            self.lbl_status.setText(f"● EVE ONLINE: MERCADO ABIERTO ({item_name.upper()})")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")

    def on_item_double_clicked(self, item):
        row = item.row()
        item_name = self.table.item(row, 1).text()
        
        # Buscar el ID del ítem
        type_id = None
        for opp in getattr(self, 'all_opportunities', []):
            if opp.item_name == item_name:
                type_id = opp.type_id
                break
        
        # Intentar abrir en juego si hay token
        from core.auth_manager import AuthManager
        auth = AuthManager.instance()
        
        if type_id and auth.current_token and auth.current_token != "MOCK_TOKEN":
            from core.esi_client import ESIClient
            client = ESIClient()
            success = client.open_market_window(type_id, auth.current_token)
            if success:
                self.on_item_action("opened_in_game", item_name)
                return

        # Fallback: Copiar al portapapeles
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(item_name)
        self.on_item_action("copied", item_name)

    def on_refresh_clicked(self):
        if self.worker and self.worker.isRunning():
            return
            
        self.update_config_from_ui()
        
        self.btn_refresh.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("● OBTENIENDO MERCADO (ESI)...")
        self.lbl_status.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        
        self.worker = MarketRefreshWorker(region_id=10000002) # Default The Forge
        self.worker.config = self.current_config
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.data_ready.connect(self.on_data_ready)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()
        
    def on_progress(self, pct, text):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"● {text.upper()}")
        
    def on_data_ready(self, opps):
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("● SISTEMA LISTO")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        self.all_opportunities = opps
        self.apply_and_display()
        
    def on_error(self, err_msg):
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"● ERROR: {err_msg.upper()}")
        self.lbl_status.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        
    def update_config_from_ui(self):
        self.current_config.capital_max = self.spin_capital.value()
        self.current_config.vol_min_day = self.spin_vol.value()
        self.current_config.margin_min_pct = self.spin_margin.value()
        self.current_config.spread_max_pct = self.spin_spread.value()
        self.current_config.exclude_plex = self.chk_plex.isChecked()
        self.current_config.broker_fee_pct = self.spin_broker.value()
        self.current_config.sales_tax_pct = self.spin_tax.value()
        
    def on_apply_filters(self):
        self.update_config_from_ui()
        self.apply_and_display()
        
    def apply_and_display(self):
        filtered = apply_filters(self.all_opportunities, self.current_config)
        # Sort by score descending and take top 50
        filtered.sort(key=lambda x: x.score_breakdown.final_score if x.score_breakdown else 0, reverse=True)
        top_50 = filtered[:50]
        self.table.populate(top_50)
        
        self.lbl_sum_count.setText(f"{len(filtered)}")
        if top_50:
            self.lbl_sum_top.setText(top_50[0].item_name)
            liquid_opp = max(filtered, key=lambda x: x.liquidity.volume_5d)
            self.lbl_sum_liquid.setText(f"{liquid_opp.item_name}")
            
            solid_opps = [o for o in filtered if "Sólida" in o.tags]
            if solid_opps:
                best_solid = max(solid_opps, key=lambda x: x.margin_net_pct)
                self.lbl_sum_margin.setText(f"{best_solid.item_name} ({best_solid.margin_net_pct:.1f}%)")
            else:
                self.lbl_sum_margin.setText("Ninguna")
            
            if len(filtered) > 50:
                self.lbl_sum_insight.setText("MERCADO SALUDABLE")
                self.lbl_sum_insight.setStyleSheet("color: #34d399; font-size: 13px; font-weight: 800; border: none; background: transparent;")
            else:
                self.lbl_sum_insight.setText("ALTA SELECTIVIDAD")
                self.lbl_sum_insight.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 800; border: none; background: transparent;")
        else:
            self.lbl_sum_top.setText("---")
            self.lbl_sum_liquid.setText("---")
            self.lbl_sum_margin.setText("---")
            self.lbl_sum_insight.setText("SIN RESULTADOS")
            self.lbl_sum_insight.setStyleSheet("color: #f87171; font-size: 13px; font-weight: 800; border: none; background: transparent;")

    def on_table_selection(self):
        sel = self.table.selectedItems()
        if not sel:
            self.lbl_det_item.setText("SELECCIONA UN ITEM")
            self.lbl_det_tags.setText("---")
            self.lbl_det_icon.clear()
            return
            
        row = sel[0].row()
        item_name = self.table.item(row, 1).text()
        
        opp = next((o for o in self.all_opportunities if o.item_name == item_name), None)
        if opp:
            self.lbl_det_item.setText(opp.item_name.upper())
            tags_str = " ".join([f"[{t.upper()}]" for t in opp.tags])
            self.lbl_det_tags.setText(tags_str if tags_str else "SIN ETIQUETAS")
            
            # Icon from cache
            if opp.type_id in self.table.icon_cache:
                from PySide6.QtGui import QIcon, QPixmap
                pixmap = self.table.icon_cache[opp.type_id]
                self.lbl_det_icon.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.lbl_det_icon.clear()
            
            try:
                from utils.formatters import format_isk
                b_str = format_isk(opp.best_buy_price, short=True)
                s_str = format_isk(opp.best_sell_price, short=True)
                p_str = format_isk(opp.profit_per_unit, short=False)
            except ImportError:
                b_str = f"{opp.best_buy_price:,.0f}"
                s_str = f"{opp.best_sell_price:,.0f}"
                p_str = f"{opp.profit_per_unit:,.0f}"
                
            self.lbl_det_buy.setText(f"{b_str} ISK")
            self.lbl_det_sell.setText(f"{s_str} ISK")
            self.lbl_det_profit.setText(f"{p_str} ISK")
            self.lbl_det_margin.setText(f"{opp.margin_net_pct:.1f}%")
                
            sb = opp.score_breakdown
            if sb:
                self.lbl_det_score.setText(f"{sb.final_score:.1f}")
                if sb.final_score > 70: self.lbl_det_score.setStyleSheet("color: #34d399; font-size: 24px; font-weight: 900;")
                elif sb.final_score > 40: self.lbl_det_score.setStyleSheet("color: #fbbf24; font-size: 24px; font-weight: 900;")
                else: self.lbl_det_score.setStyleSheet("color: #f87171; font-size: 24px; font-weight: 900;")
                
                penalties = ", ".join([f"x{p:.2f}" for p in sb.penalties]) if sb.penalties else "Ninguna"
                self.lbl_det_pens.setText(f"Riesgo: {opp.risk_level.upper()} | {penalties}")
            else:
                self.lbl_det_score.setText("---")
                self.lbl_det_pens.setText("---")
                
            # Cálculo de Cantidad Recomendada
            capital = self.current_config.capital_max
            b_price = opp.best_buy_price
            
            # Criterio: aprox 1.5 días de volumen (volume_5d / 3.3)
            safe_qty = int(opp.liquidity.volume_5d / 3.3)
            if safe_qty < 1: safe_qty = 1
            
            if "Alto" in opp.risk_level: safe_qty = int(safe_qty * 0.5)
            
            max_afford = int(capital / b_price) if b_price > 0 else 0
            rec_qty = min(safe_qty, max_afford)
            if rec_qty <= 0: rec_qty = 1
            
            cost_est = rec_qty * b_price
            self.lbl_det_rec_qty.setText(f"{rec_qty:,} uds")
            
            try:
                from utils.formatters import format_isk
                cost_str = format_isk(cost_est, short=True)
            except:
                cost_str = f"{cost_est:,.0f}"
            self.lbl_det_rec_cost.setText(f"Coste: {cost_str} ISK")
