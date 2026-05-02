import copy
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox, QFormLayout, QProgressBar, QFrame, QGridLayout, QScrollArea,
    QComboBox
)
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtCore import Qt, QTimer
from ui.market_command.widgets import MarketTableWidget
from ui.market_command.refresh_worker import MarketRefreshWorker
from ui.market_command.diagnostics_dialog import MarketDiagnosticsDialog
from core.market_engine import apply_filters, apply_filters_with_diagnostics
from core.market_models import FilterConfig
from core.market_scan_diagnostics import MarketScanDiagnostics
from core.config_manager import save_market_filters, load_market_filters
from core.eve_icon_service import EveIconService
from ui.common.theme import Theme

class MarketSimpleView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SimpleViewRoot")
        self.worker = None
        self.all_opportunities = []
        self.last_scan_diagnostics = None
        self._diag_dialog = None
        self.current_config = load_market_filters()
        self.setup_ui()
        
    def refresh_theme(self):
        """Re-applies the current theme QSS to this view and refreshes dynamic data."""
        self.setStyleSheet(Theme.get_qss("simple"))
        if hasattr(self, 'table'):
            self.table.setStyleSheet(Theme.get_qss("simple"))
        # Force refresh of table items to update QColor foregrounds
        self.apply_and_display()
        
    def activate_view(self):
        """Hook para activación de pestaña."""
        pass

    def _show_scan_overlay(self, text="ESCANEANDO MERCADO...", sub="Obteniendo datos ESI — por favor espera"):
        self._ov_text.setText(text)
        self._ov_sub.setText(sub)
        self._scan_overlay.setVisible(True)
        self._scan_overlay.raise_()
        self._ov_timer.start()
        self._reposition_overlay()

    def _hide_scan_overlay(self):
        self._ov_timer.stop()
        self._scan_overlay.setVisible(False)

    def _reposition_overlay(self):
        if hasattr(self, '_scan_overlay') and hasattr(self, 'table'):
            tbl = self.table
            pos = tbl.mapTo(self, tbl.rect().topLeft())
            self._scan_overlay.setGeometry(pos.x(), pos.y(), tbl.width(), tbl.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlay()
        
    def create_insight_box(self, title, object_name=None):
        f = QFrame(); f.setObjectName("SummaryMetricCard")
        f.setCursor(Qt.PointingHandCursor)
        f._insight_type_id = 0
        f._insight_item_name = ""
        l = QVBoxLayout(f); l.setContentsMargins(8, 6, 8, 6); l.setSpacing(2)
        t = QLabel(title); t.setObjectName("SummaryMetricTitle")
        row = QHBoxLayout(); row.setSpacing(4)
        icon_lbl = QLabel(); icon_lbl.setFixedSize(22, 22); icon_lbl.setObjectName("InsightIconLabel")
        v = QLabel("---"); v.setObjectName("SummaryMetricValue")
        if object_name: v.setObjectName(object_name)
        row.addWidget(icon_lbl); row.addWidget(v, 1)
        l.addWidget(t); l.addLayout(row)
        f._icon_lbl = icon_lbl

        def _on_double_click(event, frame=f):
            if event.button() == Qt.LeftButton and frame._insight_type_id:
                from ui.market_command.widgets import ItemInteractionHelper
                from core.esi_client import ESIClient
                from core.auth_manager import AuthManager
                def fb(msg, color): self.lbl_status.setText(f"● {msg.upper()}")
                ItemInteractionHelper.open_market_with_fallback(
                    ESIClient(), AuthManager.instance().char_id,
                    frame._insight_type_id, frame._insight_item_name, fb
                )
        f.mouseDoubleClickEvent = _on_double_click
        return f, v

    def setup_ui(self):
        self.setStyleSheet(Theme.get_qss("simple"))
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)
        
        # 1. Header Area
        header_frame = QFrame()
        header_frame.setObjectName("SimpleActionBar")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(0, 0, 0, 0)
        
        title_v = QVBoxLayout()
        title_lbl = QLabel("MARKET COMMAND")
        title_lbl.setObjectName("SectionTitle")
        self.lbl_status = QLabel("● SISTEMA OPERATIVO")
        self.lbl_status.setObjectName("ModeLabel")
        title_v.addWidget(title_lbl)
        title_v.addWidget(self.lbl_status)
        
        self.btn_refresh = QPushButton("REFRESCAR MERCADO (ESI)")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setMinimumWidth(220)
        self.btn_refresh.setFixedHeight(35)
        self.btn_refresh.setObjectName("RefreshButton")
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        
        self.btn_customize = QPushButton("PERSONALIZAR")
        self.btn_customize.setCursor(Qt.PointingHandCursor)
        self.btn_customize.setMinimumWidth(110)
        self.btn_customize.setFixedHeight(35)
        self.btn_customize.setObjectName("CustomizeButton")
        self.btn_customize.clicked.connect(self.on_customize_clicked)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_customize)
        header.addWidget(self.btn_refresh)
        self.main_layout.addWidget(header_frame)
        
        # 2. Main Content Split
        content_split = QHBoxLayout()
        content_split.setSpacing(15)
        
        # LEFT: Tactical Configuration
        filter_panel = QFrame()
        filter_panel.setObjectName("TacticalPanel")
        filter_panel.setFixedWidth(220)
        filter_l = QVBoxLayout(filter_panel)
        filter_l.setContentsMargins(0, 0, 0, 10)
        filter_l.setSpacing(10)
        
        header_lbl = QLabel("CONFIGURACIÓN TÁCTICA")
        header_lbl.setObjectName("ModuleHeader")
        filter_l.addWidget(header_lbl)
        
        scroll = QScrollArea()
        scroll.setObjectName("TacticalScrollArea")
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setObjectName("TacticalScrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)

        def add_compact_input(layout, label, widget):
            card = QFrame()
            card.setObjectName("TacticalFilterCard")
            v = QVBoxLayout(card)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(1)
            lbl = QLabel(label.upper())
            lbl.setObjectName("TacticalFilterLabel")
            v.addWidget(lbl)
            v.addWidget(widget)
            layout.addWidget(card)

        from core.item_categories import get_all_categories
        self.combo_category = QComboBox()
        self.combo_category.addItems(get_all_categories())
        self.combo_category.setCurrentText(self.current_config.selected_category)
        add_compact_input(scroll_layout, "Categoría", self.combo_category)

        self.spin_capital = QDoubleSpinBox()
        self.spin_capital.setRange(0, 1e12); self.spin_capital.setDecimals(0); self.spin_capital.setSuffix(" ISK")
        self.spin_capital.setValue(self.current_config.capital_max)
        self.spin_capital.setVisible(False)

        self.spin_vol = QSpinBox()
        self.spin_vol.setRange(0, 10000); self.spin_vol.setValue(self.current_config.vol_min_day)
        add_compact_input(scroll_layout, "Vol. Mínimo (5D)", self.spin_vol)

        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0, 100); self.spin_margin.setSuffix("%"); self.spin_margin.setValue(self.current_config.margin_min_pct)
        add_compact_input(scroll_layout, "Margen Mínimo %", self.spin_margin)

        self.spin_spread = QDoubleSpinBox()
        self.spin_spread.setRange(0, 999999); self.spin_spread.setSuffix("%"); self.spin_spread.setValue(9999999)
        self.spin_spread.setVisible(False)

        self.spin_max_items = QSpinBox()
        self.spin_max_items.setRange(0, 10000); self.spin_max_items.setValue(0)
        self.spin_max_items.setVisible(False)

        self.spin_score = QDoubleSpinBox()
        self.spin_score.setRange(0, 100); self.spin_score.setDecimals(1); self.spin_score.setValue(self.current_config.score_min)
        self.spin_score.setToolTip("Score mínimo (0-100). Solo muestra items con puntuación ≥ este valor.\n>70 Excelente | >40 Buena | <40 Arriesgada.")
        add_compact_input(scroll_layout, "Score Mínimo", self.spin_score)

        self.combo_risk = QComboBox()
        self.combo_risk.addItems(["Cualquier Riesgo", "Máximo Medium", "Solo Low"])
        self.combo_risk.setCurrentIndex(max(0, self.current_config.risk_max - 1))
        self.combo_risk.setToolTip("Riesgo máximo permitido.\nSolo Low = solo oportunidades de bajo riesgo.\nMáximo Medium = excluye riesgo High.\nCualquier Riesgo = sin filtro.")
        add_compact_input(scroll_layout, "Riesgo Máximo", self.combo_risk)

        self.spin_profit_unit = QDoubleSpinBox()
        self.spin_profit_unit.setRange(0, 1e12); self.spin_profit_unit.setDecimals(0); self.spin_profit_unit.setSuffix(" ISK")
        self.spin_profit_unit.setValue(self.current_config.profit_unit_min)
        self.spin_profit_unit.setToolTip("Profit neto mínimo por unidad vendida (después de fees).\n0 = sin filtro.")
        add_compact_input(scroll_layout, "Profit/u Mínimo", self.spin_profit_unit)

        self.spin_capital_min = QDoubleSpinBox()
        self.spin_capital_min.setRange(0, 1e12); self.spin_capital_min.setDecimals(0); self.spin_capital_min.setSuffix(" ISK")
        self.spin_capital_min.setValue(self.current_config.capital_min)
        self.spin_capital_min.setToolTip("Precio mínimo de compra por unidad. Filtra items demasiado baratos.\n0 = sin filtro.")
        add_compact_input(scroll_layout, "Capital Mínimo/u", self.spin_capital_min)

        self.spin_buy_orders = QSpinBox()
        self.spin_buy_orders.setRange(0, 10000); self.spin_buy_orders.setValue(0)
        self.spin_buy_orders.setVisible(False)

        self.spin_sell_orders = QSpinBox()
        self.spin_sell_orders.setRange(0, 10000); self.spin_sell_orders.setValue(0)
        self.spin_sell_orders.setVisible(False)

        self.spin_history_days = QSpinBox()
        self.spin_history_days.setRange(0, 365); self.spin_history_days.setValue(0)
        self.spin_history_days.setVisible(False)

        self.chk_require_buy_sell = QCheckBox("REQUERIR BUY Y SELL")
        self.chk_require_buy_sell.setObjectName("TacticalCheckbox")
        self.chk_require_buy_sell.setChecked(self.current_config.require_buy_sell)
        self.chk_require_buy_sell.setToolTip("Excluir items sin órdenes de compra Y venta activas simultáneamente.")
        scroll_layout.addWidget(self.chk_require_buy_sell)

        self.chk_plex = QCheckBox("EXCLUIR PLEX / VOLÁTILES")
        self.chk_plex.setObjectName("TacticalCheckbox")
        self.chk_plex.setChecked(self.current_config.exclude_plex)
        scroll_layout.addWidget(self.chk_plex)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        filter_l.addWidget(scroll)

        self.btn_apply = QPushButton("APLICAR FILTROS")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self.on_apply_filters)
        
        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setFixedHeight(24)
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.setObjectName("SecondaryButton")
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
        self.box_top, self.lbl_sum_top = self.create_insight_box("Mejor")
        self.box_liq, self.lbl_sum_liquid = self.create_insight_box("Líquida")
        self.box_mar, self.lbl_sum_margin = self.create_insight_box("Margen")
        self.box_cnt, self.lbl_sum_count = self.create_insight_box("Filtrados")
        self.box_ins, self.lbl_sum_insight = self.create_insight_box("Lectura")
        
        for b in [self.box_top, self.box_liq, self.box_mar, self.box_cnt, self.box_ins]:
            insights_l.addWidget(b)
        right_panel.addLayout(insights_l)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(2); self.progress_bar.setTextVisible(False); self.progress_bar.setVisible(False)
        right_panel.addWidget(self.progress_bar)

        self.table = MarketTableWidget()
        self.table.setObjectName("MarketResultsTable")
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        self.table.item_action_triggered.connect(self.on_item_action)

        # Scan loading overlay (stacked over the table)
        self._scan_overlay = QFrame(self)
        self._scan_overlay.setObjectName("ScanOverlay")
        self._scan_overlay.setStyleSheet(
            "QFrame#ScanOverlay { background-color: rgba(5,7,10,200); border-radius:8px; }"
        )
        ov_layout = QVBoxLayout(self._scan_overlay)
        ov_layout.setAlignment(Qt.AlignCenter)
        self._ov_icon = QLabel("◎")
        self._ov_icon.setStyleSheet("color:#00c8ff; font-size:32px;")
        self._ov_icon.setAlignment(Qt.AlignCenter)
        self._ov_text = QLabel("ESCANEANDO MERCADO...")
        self._ov_text.setStyleSheet("color:#00c8ff; font-size:13px; font-weight:900; letter-spacing:2px;")
        self._ov_text.setAlignment(Qt.AlignCenter)
        self._ov_sub = QLabel("Obteniendo datos ESI — por favor espera")
        self._ov_sub.setStyleSheet("color:#64748b; font-size:9px; font-weight:700; letter-spacing:1px;")
        self._ov_sub.setAlignment(Qt.AlignCenter)
        ov_layout.addWidget(self._ov_icon)
        ov_layout.addWidget(self._ov_text)
        ov_layout.addWidget(self._ov_sub)
        self._scan_overlay.setVisible(False)

        # Animate overlay icon
        self._ov_timer = QTimer(self)
        self._ov_timer.setInterval(600)
        _ov_frames = ["◎", "◉", "●", "◉"]
        _ov_idx = [0]
        def _tick_icon():
            _ov_idx[0] = (_ov_idx[0] + 1) % len(_ov_frames)
            self._ov_icon.setText(_ov_frames[_ov_idx[0]])
        self._ov_timer.timeout.connect(_tick_icon)

        right_panel.addWidget(self.table, 1)
        from ui.common.table_layout_manager import restore_table_layout, connect_table_layout_persistence
        restore_table_layout(self.table, "scan_main_table")
        connect_table_layout_persistence(self.table, "scan_main_table")
        
        self.detail_panel = QFrame()
        self.detail_panel.setFixedHeight(120)
        self.detail_panel.setObjectName("MarketDetailPanel")
        self.setup_detail_layout()
        right_panel.addWidget(self.detail_panel)
        
        content_split.addLayout(right_panel, 1)
        self.main_layout.addLayout(content_split)

    def setup_detail_layout(self):
        dl = QHBoxLayout(self.detail_panel)
        dl.setContentsMargins(12, 8, 12, 8)
        dl.setSpacing(10)

        # --- Icon block with border ---
        icon_frame = QFrame()
        icon_frame.setObjectName("DetailIconFrame")
        icon_frame.setFixedSize(64, 64)
        icon_frame.setStyleSheet(
            "QFrame#DetailIconFrame{background:#0b1016;border:1px solid #1e293b;border-radius:6px;}"
        )
        icon_fl = QVBoxLayout(icon_frame)
        icon_fl.setContentsMargins(4, 4, 4, 4)
        self.lbl_det_icon = QLabel()
        self.lbl_det_icon.setFixedSize(52, 52)
        self.lbl_det_icon.setObjectName("IconFrame")
        self.lbl_det_icon.setAlignment(Qt.AlignCenter)
        icon_fl.addWidget(self.lbl_det_icon)
        dl.addWidget(icon_frame)

        # --- Name + tags block ---
        name_v = QVBoxLayout()
        name_v.setSpacing(3)
        self.lbl_det_item = QLabel("SELECCIONA UN ITEM")
        self.lbl_det_item.setFixedWidth(240)
        self.lbl_det_item.setObjectName("DetailName")
        self.lbl_det_item.setStyleSheet("font-size:13px;font-weight:900;letter-spacing:1px;")
        self.lbl_det_tags = QLabel("---")
        self.lbl_det_tags.setFixedWidth(240)
        self.lbl_det_tags.setObjectName("DetailTagline")
        self.lbl_det_tags.setWordWrap(True)
        name_v.addWidget(self.lbl_det_item)
        name_v.addWidget(self.lbl_det_tags)
        name_v.addStretch()
        dl.addLayout(name_v)

        # --- Separator ---
        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#1e293b;"); sep.setFixedWidth(1)
        dl.addWidget(sep)

        # --- Metric cards helper ---
        def make_metric_card(label_text, val_obj_name="DetailMetricValue"):
            card = QFrame()
            card.setObjectName("DetailMetricCard")
            card.setStyleSheet(
                "QFrame#DetailMetricCard{background:#0b1016;border:1px solid #1e293b;"
                "border-radius:5px;min-width:90px;padding:4px 6px;}"
            )
            cv = QVBoxLayout(card)
            cv.setContentsMargins(6, 4, 6, 4)
            cv.setSpacing(2)
            lbl = QLabel(label_text.upper())
            lbl.setObjectName("DetailMetricTitle")
            lbl.setStyleSheet("font-size:7px;font-weight:800;letter-spacing:0.8px;")
            val = QLabel("---")
            val.setObjectName(val_obj_name)
            val.setStyleSheet("font-size:11px;font-weight:900;")
            cv.addWidget(lbl)
            cv.addWidget(val)
            return card, val

        self.lbl_det_buy = QLabel("---")
        self.lbl_det_sell = QLabel("---")
        self.lbl_det_profit = QLabel("---")
        self.lbl_det_margin = QLabel("---")
        self.lbl_det_score = QLabel("0.0")
        self.lbl_det_pens = QLabel("---")
        self.lbl_det_rec_qty = QLabel("0 uds")
        self.lbl_det_rec_cost = QLabel("Coste: 0 ISK")

        card_buy, _ = make_metric_card("BUY PRICE"); _ .setText("---"); self.lbl_det_buy = _
        card_sell, _ = make_metric_card("SELL PRICE"); _.setText("---"); self.lbl_det_sell = _
        card_profit, _ = make_metric_card("PROFIT / U"); _.setText("---"); self.lbl_det_profit = _
        card_margin, _ = make_metric_card("MARGEN %"); _.setText("---"); self.lbl_det_margin = _
        card_score, _ = make_metric_card("SCORE"); _.setText("0.0"); self.lbl_det_score = _
        self.lbl_det_pens = QLabel("---"); self.lbl_det_pens.setObjectName("DetailTagline")
        self.lbl_det_pens.setStyleSheet("font-size:8px;color:#64748b;")

        card_score_inner = card_score.layout()
        card_score_inner.addWidget(self.lbl_det_pens)

        card_qty, _ = make_metric_card("QTY RECOM."); _.setText("0 uds"); self.lbl_det_rec_qty = _
        self.lbl_det_rec_cost = QLabel("Coste: 0 ISK")
        self.lbl_det_rec_cost.setObjectName("DetailTagline")
        self.lbl_det_rec_cost.setStyleSheet("font-size:8px;color:#64748b;")
        card_qty.layout().addWidget(self.lbl_det_rec_cost)

        for card in [card_buy, card_sell, card_profit, card_margin, card_score, card_qty]:
            dl.addWidget(card)

    def on_item_action(self, action, item_name, type_id):
        if action == "copied":
            self.lbl_status.setText(f"● PORTAPAPELES: {item_name.upper()}")
        elif action == "opened_in_game":
            self.lbl_status.setText(f"● EVE ONLINE: MERCADO ABIERTO ({item_name.upper()})")
        elif action == "double_clicked":
            from ui.market_command.widgets import ItemInteractionHelper
            from core.esi_client import ESIClient
            from core.auth_manager import AuthManager
            auth = AuthManager.instance()
            def feedback(msg, color):
                self.lbl_status.setText(f"● {msg.upper()}")
                self.lbl_status.setObjectName("ModeLabel")
            ItemInteractionHelper.open_market_with_fallback(ESIClient(), auth.char_id, type_id, item_name, feedback)

    def on_refresh_clicked(self):
        if self.worker and self.worker.isRunning(): return
        self.update_config_from_ui()
        self._log_scan_config()
        self.btn_refresh.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("● OBTENIENDO MERCADO (ESI)...")
        self.lbl_status.setObjectName("ModeLabel")
        self._show_scan_overlay("ESCANEANDO MERCADO...", "Conectando con ESI — descargando órdenes...")
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

    def on_customize_clicked(self):
        from ui.common.theme_customizer_dialog import ThemeCustomizerDialog
        dialog = ThemeCustomizerDialog(view_scope="simple", parent=self)
        # Full refresh on theme update
        dialog.themeUpdated.connect(self.refresh_theme)
        dialog.exec()

    def on_initial_data_ready(self, opps):
        import logging
        logging.getLogger('eve.market.simple').info(f"[PIPELINE] initial_opportunities={len(opps)}")
        self.update_config_from_ui()
        self.all_opportunities = opps
        self.apply_and_display()
        cat = self.current_config.selected_category
        if opps:
            msg = f"● RESULTADOS INICIALES ({len(opps)}) — ENRIQUECIENDO HISTORIAL..."
            self._show_scan_overlay("ENRIQUECIENDO DATOS...", f"{len(opps)} items — calculando historial y scores...")
        else:
            msg = f"● BUSCANDO {cat.upper()}... DESCARGANDO METADATA" if cat != "Todos" else "● ENRIQUECIENDO..."
        self.lbl_status.setText(msg)
        self.lbl_status.setObjectName("ModeLabel")
        self.btn_refresh.setText("ENRIQUECIENDO...")

    def on_enriched_data_ready(self, opps):
        import logging
        try:
            logging.getLogger('eve.market.simple').info(f"[PIPELINE] enriched_opportunities={len(opps)}")
            self.update_config_from_ui()
            self.all_opportunities = opps
            self.apply_and_display()
            self.lbl_status.setText("● ESCANEO COMPLETADO — DATOS ENRIQUECIDOS")
            self.lbl_status.setObjectName("ModeLabel")
        except Exception as e:
            logging.getLogger('eve.market.simple').exception(f"Error in on_enriched_data_ready: {e}")
            self.on_error(str(e))
        finally:
            self._hide_scan_overlay()
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("REFRESCAR MERCADO (ESI)")
            self.progress_bar.setVisible(False)

    def on_error(self, err_msg):
        self._hide_scan_overlay()
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"● ERROR: {err_msg.upper()}")
        self.lbl_status.setObjectName("ModeLabel")

    def on_diagnostics_ready(self, diagnostics):
        from PySide6.QtCore import QTimer
        self.last_scan_diagnostics = diagnostics
        # Delay opening to ensure UI has applied final filters for the report and icons have time to load
        QTimer.singleShot(2000, lambda: self.complete_and_show_diagnostics(diagnostics))

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
        diagnostics.after_category = filter_diag.get("after_category", 0)
        diagnostics.after_filters = filter_diag.get("after_filters", 0)
        diagnostics.metadata_missing_count = filter_diag.get("metadata_missing_count", 0)
        diagnostics.metadata_missing_ids = filter_diag.get("metadata_missing_ids", [])
        diagnostics.selected_category_ui = self.current_config.selected_category
        diagnostics.mode = "Scan"
        
        if hasattr(self.table, 'get_icon_diagnostics'):
            icon_stats = self.table.get_icon_diagnostics()
            diagnostics.icon_requests = icon_stats.get("icon_requests", 0)
            diagnostics.icon_loaded = icon_stats.get("icon_loaded", 0)
            diagnostics.icon_failed = icon_stats.get("icon_failed", 0)
            diagnostics.icon_cache_hits = icon_stats.get("icon_cache_hits", 0)
            diagnostics.icon_cache_size = icon_stats.get("icon_cache_size", 0)
            diagnostics.icon_placeholders_used = icon_stats.get("icon_placeholders_used", 0)
            diagnostics.icon_endpoint_icon_success = icon_stats.get("icon_endpoint_icon_success", 0)
            diagnostics.icon_endpoint_render_success = icon_stats.get("icon_endpoint_render_success", 0)
            diagnostics.icon_endpoint_bp_success = icon_stats.get("icon_endpoint_bp_success", 0)
            diagnostics.icon_endpoint_bpc_success = icon_stats.get("icon_endpoint_bpc_success", 0)
            diagnostics.icon_all_endpoints_failed = icon_stats.get("icon_all_endpoints_failed", 0)
            diagnostics.icon_last_errors = icon_stats.get("icon_last_errors", [])

        # 4. Show dialog and keep reference to prevent GC
        self._diag_dialog = MarketDiagnosticsDialog(diagnostics.to_report(), self)
        self._diag_dialog.show()

    def update_config_from_ui(self):
        self.current_config.capital_max = self.spin_capital.value()
        self.current_config.vol_min_day = self.spin_vol.value()
        self.current_config.margin_min_pct = self.spin_margin.value()
        self.current_config.spread_max_pct = self.spin_spread.value()
        self.current_config.exclude_plex = self.chk_plex.isChecked()
        self.current_config.selected_category = self.combo_category.currentText()
        self.current_config.max_item_types = self.spin_max_items.value()
        self.current_config.score_min = self.spin_score.value()
        self.current_config.risk_max = self.combo_risk.currentIndex() + 1
        self.current_config.profit_unit_min = self.spin_profit_unit.value()
        self.current_config.capital_min = self.spin_capital_min.value()
        self.current_config.buy_orders_min = self.spin_buy_orders.value()
        self.current_config.sell_orders_min = self.spin_sell_orders.value()
        self.current_config.history_days_min = self.spin_history_days.value()
        self.current_config.require_buy_sell = self.chk_require_buy_sell.isChecked()
        self.current_config.profit_day_min = 0  # Not exposed; profit_unit_min covers per-unit filtering

        # Fees desde ESI (no editable en UI — siempre vienen del personaje autenticado)
        self._apply_esi_fees_to_config()

    def _apply_esi_fees_to_config(self):
        """Overwrites broker/tax in config with ESI effective values for the active character."""
        import logging
        log = logging.getLogger('eve.market.simple')
        try:
            from core.tax_service import TaxService
            from core.auth_manager import AuthManager
            auth = AuthManager.instance()
            
            # Default Jita 4-4 (Caldari Navy Assembly Plant)
            loc_id = 60003760
            self._last_fees_loc = loc_id
            
            if auth.char_id:
                token = auth.get_token()
                st, bf, source, debug = TaxService.instance().get_effective_taxes(auth.char_id, loc_id, token)
                
                self.current_config.broker_fee_pct = bf
                self.current_config.sales_tax_pct = st
                self._last_fees_source = source
                self._last_fees_debug = debug
                self._last_fees_fallback = False
                
                log.info(f"[FEES] Effective taxes applied: ST={st}%, BF={bf}% (Source: {source})")
            else:
                self._last_fees_source = "NO AUTH"
                self._last_fees_debug = "No character authenticated"
                self._last_fees_fallback = True
                log.warning("[FEES] No authenticated character — using FilterConfig defaults")
                
        except Exception as e:
            log.warning(f"[FEES] TaxService failed: {e} — using FilterConfig defaults")
            self._last_fees_source = "ERROR"
            self._last_fees_debug = str(e)
            self._last_fees_fallback = True

    def _log_scan_config(self):
        import logging
        log = logging.getLogger('eve.market.simple')
        cfg = self.current_config
        
        from core.auth_manager import AuthManager
        auth = AuthManager.instance()
        
        fees_source = getattr(self, '_last_fees_source', 'N/A')
        loc_id = getattr(self, '_last_fees_loc', 0)
        fallback = getattr(self, '_last_fees_fallback', True)
        debug = getattr(self, '_last_fees_debug', 'N/A')

        log.info(
            f"\n[SIMPLE FEES]\n"
            f"  character_id: {auth.char_id}\n"
            f"  location_id: {loc_id}\n"
            f"  sales_tax_pct: {cfg.sales_tax_pct}%\n"
            f"  broker_fee_pct: {cfg.broker_fee_pct}%\n"
            f"  source: {fees_source}\n"
            f"  fallback_used: {fallback}\n"
            f"  debug: {debug}"
        )

        log.info(
            f"\n[SIMPLE SCAN CONFIG]\n"
            f"  selected_category: {cfg.selected_category}\n"
            f"  filters:\n"
            f"    profit_unit_min: {cfg.profit_unit_min}\n"
            f"    capital_min: {cfg.capital_min}\n"
            f"    capital_max: {cfg.capital_max}\n"
            f"    volume_min_5d: {cfg.vol_min_day}\n"
            f"    margin_min_pct: {cfg.margin_min_pct}\n"
            f"    spread_max_pct: {cfg.spread_max_pct}\n"
            f"    score_min: {cfg.score_min}\n"
            f"    risk_max: {cfg.risk_max}\n"
            f"    buy_orders_min: {cfg.buy_orders_min}\n"
            f"    sell_orders_min: {cfg.sell_orders_min}\n"
            f"    history_days_min: {cfg.history_days_min}\n"
            f"    require_buy_sell: {cfg.require_buy_sell}\n"
            f"    max_item_types: {cfg.max_item_types}\n"
            f"    exclude_plex: {cfg.exclude_plex}\n"
            f"  effective_sales_tax: {cfg.sales_tax_pct}%\n"
            f"  effective_broker_fee: {cfg.broker_fee_pct}%\n"
            f"  fees_source: {fees_source}"
        )

    def on_apply_filters(self):
        import logging
        log = logging.getLogger('eve.market.simple')
        try:
            self.update_config_from_ui()
        except Exception as e:
            log.warning(f"[APPLY] update_config_from_ui failed (fees may be defaults): {e}")
        save_market_filters(self.current_config)
        self.apply_and_display()
        log.info(f"[APPLY] Filters applied: category={self.current_config.selected_category} max_items={self.current_config.max_item_types} margin={self.current_config.margin_min_pct}")

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
        self.combo_category.setCurrentText(self.current_config.selected_category)
        self.spin_max_items.setValue(self.current_config.max_item_types)
        self.spin_score.setValue(self.current_config.score_min)
        self.combo_risk.setCurrentIndex(max(0, self.current_config.risk_max - 1))
        self.spin_profit_unit.setValue(self.current_config.profit_unit_min)
        self.spin_capital_min.setValue(self.current_config.capital_min)
        self.spin_buy_orders.setValue(self.current_config.buy_orders_min)
        self.spin_sell_orders.setValue(self.current_config.sell_orders_min)
        self.spin_history_days.setValue(self.current_config.history_days_min)
        self.chk_require_buy_sell.setChecked(self.current_config.require_buy_sell)

    def apply_and_display(self):
        import logging
        log = logging.getLogger('eve.market.simple')
        total_raw = len(self.all_opportunities)
        log.info(f"[UI DIAG] before_apply_filters={total_raw} selected_category={self.current_config.selected_category}")
        
        filtered, diag = apply_filters_with_diagnostics(self.all_opportunities, self.current_config)
        filtered.sort(key=lambda x: x.score_breakdown.final_score if x.score_breakdown else 0, reverse=True)
        
        log.info(f"[UI DIAG] after_apply_filters={len(filtered)}")

        self.table.populate(filtered)
        self.lbl_sum_count.setText(f"{len(filtered)}")

        # Actualizar UI si no hay resultados
        if total_raw == 0:
            self.lbl_sum_top.setText("---"); self.lbl_sum_liquid.setText("---"); self.lbl_sum_margin.setText("---")
            self.lbl_sum_insight.setText("SIN DATOS DEL ESCANEO")
            self.lbl_sum_insight.setObjectName("MetricValueInfo")
            self.lbl_status.setText("● SIN DATOS — PRIMERO REALIZA UN ESCANEO (REFRESCAR MERCADO)")
            self.lbl_status.setObjectName("ModeLabel")
        elif len(filtered) == 0:
            self.lbl_sum_top.setText("---"); self.lbl_sum_liquid.setText("---"); self.lbl_sum_margin.setText("---")
            dom = diag.get("dominant_filter", "DESCONOCIDO")
            count = diag["removed"].get(dom, total_raw)
            self.lbl_sum_insight.setText(f"FILTRO DOMINANTE: {dom.upper()} ({count})")
            self.lbl_sum_insight.setObjectName("MetricValueDanger")
            self.lbl_status.setText(f"● {total_raw} ITEMS ENCONTRADOS PERO 0 PASAN FILTRO: {dom.upper()}")
            self.lbl_status.setObjectName("ModeLabel")
        else:
            top_opp = filtered[0]
            self.lbl_sum_top.setText(top_opp.item_name)
            self.box_top._insight_type_id = top_opp.type_id
            self.box_top._insight_item_name = top_opp.item_name
            _px = self.table.icon_service.get_icon(top_opp.type_id, 22)
            self.box_top._icon_lbl.setPixmap(_px.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            liquid_opp = max(filtered, key=lambda x: x.liquidity.volume_5d)
            self.lbl_sum_liquid.setText(f"{liquid_opp.item_name}")
            self.box_liq._insight_type_id = liquid_opp.type_id
            self.box_liq._insight_item_name = liquid_opp.item_name
            _px = self.table.icon_service.get_icon(liquid_opp.type_id, 22)
            self.box_liq._icon_lbl.setPixmap(_px.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            solid_opps = [o for o in filtered if "Sólida" in o.tags]
            if solid_opps:
                best_solid = max(solid_opps, key=lambda x: x.margin_net_pct)
                self.lbl_sum_margin.setText(f"{best_solid.item_name} ({best_solid.margin_net_pct:.1f}%)")
                self.box_mar._insight_type_id = best_solid.type_id
                self.box_mar._insight_item_name = best_solid.item_name
                _px = self.table.icon_service.get_icon(best_solid.type_id, 22)
                self.box_mar._icon_lbl.setPixmap(_px.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.lbl_sum_margin.setText("Ninguna")
                self.box_mar._icon_lbl.clear()
            if len(filtered) > 50:
                self.lbl_sum_insight.setText("MERCADO SALUDABLE")
                self.lbl_sum_insight.setObjectName("MetricValueSuccess")
            else:
                self.lbl_sum_insight.setText("ALTA SELECTIVIDAD")
                self.lbl_sum_insight.setObjectName("MetricValueWarning")

            # Apply semantic classes to top summary boxes if they show real items
            self.lbl_sum_top.setObjectName("MetricValueInfo")
            self.lbl_sum_liquid.setObjectName("MetricValueInfo")
            self.lbl_sum_margin.setObjectName("MetricValueSuccess")
            
            self.lbl_status.setText(f"● MOSTRANDO {len(filtered)} RESULTADOS")
            self.lbl_status.setObjectName("ModeLabel")
            
            # Refresh style to apply new ObjectNames
            for lbl in [self.lbl_sum_top, self.lbl_sum_liquid, self.lbl_sum_margin, self.lbl_sum_insight]:
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)

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
            # Get icon from centralized service (will be instant if cached)
            pixmap = self.table.icon_service.get_icon(opp.type_id, 48)
            self.lbl_det_icon.setPixmap(pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            from utils.formatters import format_isk
            from core.market_engine import compute_profit_breakdown
            self.lbl_det_buy.setText(f"{format_isk(opp.best_buy_price, short=True)} ISK")
            self.lbl_det_sell.setText(f"{format_isk(opp.best_sell_price, short=True)} ISK")
            self.lbl_det_profit.setText(f"{format_isk(opp.profit_per_unit, short=False)} ISK")

            # BUY = green, SELL = red
            self.lbl_det_buy.setObjectName("MetricValueSuccess")
            self.lbl_det_buy.style().unpolish(self.lbl_det_buy)
            self.lbl_det_buy.style().polish(self.lbl_det_buy)
            self.lbl_det_sell.setObjectName("MetricValueDanger")
            self.lbl_det_sell.style().unpolish(self.lbl_det_sell)
            self.lbl_det_sell.style().polish(self.lbl_det_sell)

            # PROFIT/U color follows margin
            if opp.profit_per_unit > 0 and opp.margin_net_pct > 10.0:
                self.lbl_det_profit.setObjectName("MetricValueSuccess")
            elif opp.profit_per_unit >= 0:
                self.lbl_det_profit.setObjectName("MetricValueWarning")
            else:
                self.lbl_det_profit.setObjectName("MetricValueDanger")
            self.lbl_det_profit.style().unpolish(self.lbl_det_profit)
            self.lbl_det_profit.style().polish(self.lbl_det_profit)

            # Margin coloring logic
            self.lbl_det_margin.setText(f"{opp.margin_net_pct:.1f}%")
            if opp.margin_net_pct > 10.0:
                self.lbl_det_margin.setObjectName("MetricValueSuccess")
            elif opp.margin_net_pct >= 0.0:
                self.lbl_det_margin.setObjectName("MetricValueWarning")
            else:
                self.lbl_det_margin.setObjectName("MetricValueDanger")
            self.lbl_det_margin.style().unpolish(self.lbl_det_margin)
            self.lbl_det_margin.style().polish(self.lbl_det_margin)
            # Profit breakdown tooltip
            bd = compute_profit_breakdown(
                opp.best_buy_price, opp.best_sell_price,
                self.current_config.broker_fee_pct, self.current_config.sales_tax_pct
            )
            self.lbl_det_profit.setToolTip(
                f"[PROFIT BREAKDOWN]\n"
                f"  buy_price:       {format_isk(opp.best_buy_price, short=False)} ISK\n"
                f"  sell_price:      {format_isk(opp.best_sell_price, short=False)} ISK\n"
                f"  Gross Spread:    {format_isk(bd['gross_spread'], short=False)} ISK\n"
                f"  Sales Tax pct:   {bd['sales_tax_pct']:.2f}%\n"
                f"  broker_fee_pct:  {bd['broker_fee_pct']:.2f}%\n"
                f"  Sales Tax ISK:   -{format_isk(bd['sales_tax_isk'], short=False)} ISK\n"
                f"  broker_sell_isk: -{format_isk(bd['broker_fee_sell_isk'], short=False)} ISK\n"
                f"  broker_buy_isk:  -{format_isk(bd['broker_fee_buy_isk'], short=False)} ISK\n"
                f"  {'-' * 40}\n"
                f"  net_profit_unit: {format_isk(bd['net_profit_per_unit'], short=False)} ISK\n"
                f"  formula:         {bd['formula']}"
            )
            
            sb = opp.score_breakdown
            if sb:
                self.lbl_det_score.setText(f"{sb.final_score:.1f}")
                if sb.final_score > 70: self.lbl_det_score.setObjectName("MetricValueSuccess")
                elif sb.final_score > 40: self.lbl_det_score.setObjectName("MetricValueWarning")
                else: self.lbl_det_score.setObjectName("MetricValueDanger")
                self.lbl_det_score.style().unpolish(self.lbl_det_score)
                self.lbl_det_score.style().polish(self.lbl_det_score)
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
