from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
    QPushButton, QScrollArea, QGridLayout, QDoubleSpinBox, 
    QSpinBox, QCheckBox, QComboBox, QProgressBar, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPixmap

from core.market_models import FilterConfig
from .refresh_worker import MarketRefreshWorker
from .widgets import AdvancedMarketTableWidget

class MarketAdvancedView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.icon_cache = {}
        self.setup_ui()
        
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)
        
        # 1. Header Area
        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title_lbl = QLabel("MARKET COMMAND — MODO AVANZADO")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        subtitle = QLabel("INVESTIGACIÓN PROFUNDA Y ANÁLISIS DE OPORTUNIDADES")
        subtitle.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        title_v.addWidget(title_lbl)
        title_v.addWidget(subtitle)
        
        self.btn_refresh = QPushButton("EJECUTAR ESCANEO AVANZADO")
        self.btn_refresh.setObjectName("SaveButton")
        self.btn_refresh.setFixedWidth(200)
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        
        header.addLayout(title_v)
        header.addStretch()
        header.addWidget(self.btn_refresh)
        self.main_layout.addLayout(header)
        
        # 2. Main Content Split
        content_split = QHBoxLayout()
        
        # LEFT: Advanced Filter Panel
        filter_panel = QFrame()
        filter_panel.setObjectName("SettingsGroup")
        filter_panel.setFixedWidth(250)
        filter_l = QVBoxLayout(filter_panel)
        filter_l.setContentsMargins(15, 15, 15, 15)
        filter_l.setSpacing(10)
        
        filter_l.addWidget(QLabel("FILTROS AVANZADOS", objectName="ModuleHeader"))
        
        # Group: Capital & Volume
        filter_l.addWidget(QLabel("CAPITAL Y VOLUMEN", styleSheet="color: #94a3b8; font-size: 8px; font-weight: 800; margin-top: 5px;"))
        self.spin_capital = self.create_advanced_spin("Cap. Máximo (ISK)", 1_000_000_000, 10_000_000, 100_000_000_000)
        self.spin_vol = self.create_advanced_spin("Vol. Mínimo (5D)", 20, 0, 100_000)
        filter_l.addWidget(self.spin_capital)
        filter_l.addWidget(self.spin_vol)
        
        # Group: Performance
        filter_l.addWidget(QLabel("RENDIMIENTO", styleSheet="color: #94a3b8; font-size: 8px; font-weight: 800; margin-top: 5px;"))
        self.spin_margin = self.create_advanced_spin("Margen Mínimo %", 5.0, 0, 1000)
        self.spin_spread = self.create_advanced_spin("Spread Máximo %", 40.0, 0, 1000)
        self.spin_profit_day = self.create_advanced_spin("Profit/Día Mínimo", 0, 0, 10_000_000_000)
        filter_l.addWidget(self.spin_margin)
        filter_l.addWidget(self.spin_spread)
        filter_l.addWidget(self.spin_profit_day)
        
        # Group: Scoring & Risk
        filter_l.addWidget(QLabel("SCORE Y RIESGO", styleSheet="color: #94a3b8; font-size: 8px; font-weight: 800; margin-top: 5px;"))
        self.spin_score = self.create_advanced_spin("Score Mínimo", 0.0, 0, 100)
        self.combo_risk = QComboBox()
        self.combo_risk.addItems(["Cualquier Riesgo", "Máximo Medium", "Solo Low"])
        self.combo_risk.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; padding: 5px;")
        filter_l.addWidget(self.spin_score)
        filter_l.addWidget(self.combo_risk)
        
        # Group: Liquidity Depth
        filter_l.addWidget(QLabel("PROFUNDIDAD", styleSheet="color: #94a3b8; font-size: 8px; font-weight: 800; margin-top: 5px;"))
        self.spin_buy_orders = self.create_advanced_spin("Buy Orders Mín.", 0, 0, 1000)
        self.spin_sell_orders = self.create_advanced_spin("Sell Orders Mín.", 0, 0, 1000)
        self.spin_hist_days = self.create_advanced_spin("Días Historial Mín.", 0, 0, 365)
        filter_l.addWidget(self.spin_buy_orders)
        filter_l.addWidget(self.spin_sell_orders)
        filter_l.addWidget(self.spin_hist_days)
        
        self.check_plex = QCheckBox("EXCLUIR PLEX / SKINS")
        self.check_plex.setChecked(True)
        self.check_plex.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 600;")
        filter_l.addWidget(self.check_plex)
        
        filter_l.addStretch()
        content_split.addWidget(filter_panel)
        
        # RIGHT: Table and Detail
        right_panel = QVBoxLayout()
        
        # Table
        self.table = AdvancedMarketTableWidget()
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.item_action_triggered.connect(self.on_item_action)
        right_panel.addWidget(self.table)
        
        # Detail Panel (Advanced)
        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("AnalyticBox")
        self.detail_panel.setFixedHeight(220)
        self.setup_detail_ui()
        right_panel.addWidget(self.detail_panel)
        
        content_split.addLayout(right_panel, 1)
        self.main_layout.addLayout(content_split)
        
        # Status Bar
        status_bar = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar { background-color: #1e293b; border: none; } QProgressBar::chunk { background-color: #3b82f6; }")
        
        self.lbl_status = QLabel("● SISTEMA LISTO")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        
        status_bar.addWidget(self.lbl_status)
        status_bar.addWidget(self.progress)
        self.main_layout.addLayout(status_bar)

    def setup_detail_ui(self):
        l = QHBoxLayout(self.detail_panel)
        l.setContentsMargins(20, 20, 20, 20)
        l.setSpacing(25)
        
        # 1. Info básica e Icono
        id_v = QVBoxLayout()
        self.det_icon = QLabel()
        self.det_icon.setFixedSize(64, 64)
        self.det_icon.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;")
        
        self.det_name = QLabel("SELECCIONA UN ITEM")
        self.det_name.setStyleSheet("color: #f1f5f9; font-size: 14px; font-weight: 900;")
        self.det_type_id = QLabel("TYPE ID: ---")
        self.det_type_id.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")
        
        id_v.addWidget(self.det_icon, 0, Qt.AlignCenter)
        id_v.addWidget(self.det_name, 0, Qt.AlignCenter)
        id_v.addWidget(self.det_type_id, 0, Qt.AlignCenter)
        id_v.addStretch()
        l.addLayout(id_v)
        
        # 2. Advanced Metrics Grid
        metrics_g = QGridLayout()
        metrics_g.setSpacing(10)
        
        self.det_buy = self.create_detail_item("BEST BUY", "---", "#60a5fa")
        self.det_sell = self.create_detail_item("BEST SELL", "---", "#f87171")
        self.det_margin = self.create_detail_item("MARGEN NETO", "---", "#10b981")
        self.det_profit_u = self.create_detail_item("PROFIT/U", "---", "#34d399")
        self.det_profit_d = self.create_detail_item("PROFIT/DÍA EST.", "---", "#fbbf24")
        self.det_vol = self.create_detail_item("VOLUMEN 5D", "---", "#cbd5e1")
        self.det_depth = self.create_detail_item("PROFUNDIDAD (B/S)", "---", "#94a3b8")
        self.det_hist = self.create_detail_item("HISTORIAL", "---", "#94a3b8")
        
        metrics_g.addWidget(self.det_buy, 0, 0)
        metrics_g.addWidget(self.det_sell, 0, 1)
        metrics_g.addWidget(self.det_margin, 1, 0)
        metrics_g.addWidget(self.det_profit_u, 1, 1)
        metrics_g.addWidget(self.det_profit_d, 2, 0)
        metrics_g.addWidget(self.det_vol, 2, 1)
        metrics_g.addWidget(self.det_depth, 3, 0)
        metrics_g.addWidget(self.det_hist, 3, 1)
        l.addLayout(metrics_g, 1)
        
        # 3. Score Breakdown Panel
        score_v = QVBoxLayout()
        score_v.setSpacing(5)
        score_v.addWidget(QLabel("SCORE BREAKDOWN", styleSheet="color: #64748b; font-size: 9px; font-weight: 800;"))
        
        self.det_score = QLabel("0.0")
        self.det_score.setStyleSheet("color: #3b82f6; font-size: 32px; font-weight: 900;")
        score_v.addWidget(self.det_score)
        
        self.score_bars_v = QVBoxLayout()
        self.bar_liq = self.create_score_bar("LIQUIDEZ")
        self.bar_roi = self.create_score_bar("ROI")
        self.bar_profit = self.create_score_bar("PROFIT")
        self.score_bars_v.addLayout(self.bar_liq)
        self.score_bars_v.addLayout(self.bar_roi)
        self.score_bars_v.addLayout(self.bar_profit)
        score_v.addLayout(self.score_bars_v)
        
        self.det_penalties = QLabel("Penalizaciones: Ninguna")
        self.det_penalties.setStyleSheet("color: #f87171; font-size: 9px; font-weight: 600;")
        self.det_penalties.setWordWrap(True)
        score_v.addWidget(self.det_penalties)
        
        score_v.addStretch()
        l.addLayout(score_v)
        
        # 4. Operation Recommendation
        op_v = QVBoxLayout()
        op_v.setFixedWidth(180)
        op_v.setSpacing(8)
        op_v.addWidget(QLabel("RECOMENDACIÓN COMPRA", styleSheet="color: #64748b; font-size: 9px; font-weight: 800;"))
        
        self.det_rec_qty = QLabel("0 units")
        self.det_rec_qty.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 800;")
        self.det_rec_cost = QLabel("Coste: 0 ISK")
        self.det_rec_cost.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        
        self.det_risk_badge = QLabel("RIESGO: ---")
        self.det_risk_badge.setStyleSheet("padding: 5px; border-radius: 3px; background: #1e293b; color: #f1f5f9; font-size: 10px; font-weight: 800; text-align: center;")
        self.det_risk_badge.setAlignment(Qt.AlignCenter)
        
        op_v.addWidget(self.det_rec_qty)
        op_v.addWidget(self.det_rec_cost)
        op_v.addStretch()
        op_v.addWidget(self.det_risk_badge)
        l.addLayout(op_v)

    def create_advanced_spin(self, label, val, min_v, max_v):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        lbl = QLabel(label.upper())
        lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700;")
        if isinstance(val, float):
            s = QDoubleSpinBox()
            s.setDecimals(1)
        else:
            s = QSpinBox()
        s.setRange(min_v, max_v)
        s.setValue(val)
        s.setStyleSheet("background: #0f172a; color: #f1f5f9; border: 1px solid #1e293b; padding: 4px;")
        l.addWidget(lbl)
        l.addWidget(s)
        return w

    def create_detail_item(self, label, val, color):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: 800;")
        v = QLabel(val)
        v.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 600;")
        l.addWidget(lbl)
        l.addWidget(v)
        return w

    def create_score_bar(self, label):
        l = QVBoxLayout()
        l.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #94a3b8; font-size: 8px; font-weight: 700;")
        prog = QProgressBar()
        prog.setFixedHeight(4)
        prog.setTextVisible(False)
        prog.setStyleSheet("QProgressBar { background-color: #1e293b; border: none; } QProgressBar::chunk { background-color: #60a5fa; }")
        l.addWidget(lbl)
        l.addWidget(prog)
        return l

    def on_refresh_clicked(self):
        if self.worker and self.worker.isRunning():
            return
            
        config = FilterConfig(
            capital_max=self.spin_capital.findChild((QSpinBox, QDoubleSpinBox)).value(),
            vol_min_day=self.spin_vol.findChild((QSpinBox, QDoubleSpinBox)).value(),
            margin_min_pct=self.spin_margin.findChild((QSpinBox, QDoubleSpinBox)).value(),
            spread_max_pct=self.spin_spread.findChild((QSpinBox, QDoubleSpinBox)).value(),
            score_min=self.spin_score.findChild((QSpinBox, QDoubleSpinBox)).value(),
            profit_day_min=self.spin_profit_day.findChild((QSpinBox, QDoubleSpinBox)).value(),
            buy_orders_min=self.spin_buy_orders.findChild((QSpinBox, QDoubleSpinBox)).value(),
            sell_orders_min=self.spin_sell_orders.findChild((QSpinBox, QDoubleSpinBox)).value(),
            history_days_min=self.spin_hist_days.findChild((QSpinBox, QDoubleSpinBox)).value(),
            exclude_plex=self.check_plex.isChecked()
        )
        
        risk_idx = self.combo_risk.currentIndex()
        if risk_idx == 1: config.risk_max = 2 # Medium
        elif risk_idx == 2: config.risk_max = 1 # Low
        else: config.risk_max = 3 # Any
        
        self.worker = MarketRefreshWorker("10000002", config) # Default Forge
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.lbl_status.setText)
        self.worker.finished.connect(self.on_scan_finished)
        
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("ESCANEO EN CURSO...")
        self.worker.start()

    def on_scan_finished(self, opportunities):
        self.table.populate(opportunities)
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("EJECUTAR ESCANEO AVANZADO")
        self.lbl_status.setText(f"● ESCANEO COMPLETADO: {len(opportunities)} ITEMS")

    def on_selection_changed(self):
        selected = self.table.selectedItems()
        if not selected: return
        
        row = selected[0].row()
        item_name = self.table.item(row, 1).text()
        
        opp = None
        if hasattr(self.worker, 'last_results'):
            for o in self.worker.last_results:
                if o.item_name == item_name:
                    opp = o
                    break
        
        if opp:
            self.update_detail(opp)

    def update_detail(self, opp):
        self.det_name.setText(opp.item_name.upper())
        self.det_type_id.setText(f"TYPE ID: {opp.type_id}")
        
        # Metrics
        self.det_buy.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.best_buy_price:,.2f}")
        self.det_sell.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.best_sell_price:,.2f}")
        self.det_margin.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.margin_net_pct:.2f}%")
        self.det_profit_u.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.profit_per_unit:,.2f}")
        self.det_profit_d.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.profit_day_est:,.0f}")
        self.det_vol.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(str(opp.liquidity.volume_5d))
        self.det_depth.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.liquidity.buy_orders_count} / {opp.liquidity.sell_orders_count}")
        self.det_hist.findChild(QLabel, "", Qt.FindDirectChildrenOnly)[1].setText(f"{opp.liquidity.history_days} días")
        
        # Score Breakdown
        sb = opp.score_breakdown
        if sb:
            self.det_score.setText(f"{sb.final_score:.1f}")
            self.bar_liq.findChild(QProgressBar).setValue(int(sb.liquidity_norm * 100))
            self.bar_roi.findChild(QProgressBar).setValue(int(sb.roi_norm * 100))
            self.bar_profit.findChild(QProgressBar).setValue(int(sb.profit_day_norm * 100))
            
            p_text = "Penalizaciones: " + (", ".join([f"{p:.1f}" for p in sb.penalties]) if sb.penalties else "Ninguna")
            self.det_penalties.setText(p_text)
        
        # Risk Badge
        self.det_risk_badge.setText(f"RIESGO: {opp.risk_level.upper()}")
        risk_colors = {"Low": "#10b981", "Medium": "#fbbf24", "High": "#ef4444"}
        self.det_risk_badge.setStyleSheet(f"padding: 5px; border-radius: 3px; background: {risk_colors.get(opp.risk_level, '#1e293b')}; color: white; font-size: 10px; font-weight: 800;")
        
        # Icon
        if opp.type_id in self.table.icon_cache:
            self.det_icon.setPixmap(self.table.icon_cache[opp.type_id].scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.det_icon.setPixmap(QPixmap()) # Clear while loading if we had logic for it
            
        # Recommendation
        # Lógica: 1.5 días de volumen, castigo si riesgo alto
        safe_qty = int((opp.liquidity.volume_5d / 5.0) * 1.5)
        if opp.risk_level == "High": safe_qty = int(safe_qty * 0.5)
        
        # Limitar por capital
        config = self.worker.config if self.worker else FilterConfig()
        max_afford = int(config.capital_max / opp.best_buy_price) if opp.best_buy_price > 0 else 0
        final_qty = max(1, min(safe_qty, max_afford))
        
        self.det_rec_qty.setText(f"{final_qty:,} units")
        self.det_rec_cost.setText(f"Coste Est: {final_qty * opp.best_buy_price:,.0f} ISK")

    def on_item_action(self, action, item_name):
        if action == "copied":
            self.lbl_status.setText(f"● PORTAPAPELES: {item_name.upper()}")
        elif action == "double_clicked":
            self.lbl_status.setText(f"● JUEGO (COPIADO): BUSCA {item_name.upper()}")
