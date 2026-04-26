from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox, QFormLayout, QProgressBar
)
from PySide6.QtCore import Qt
from .widgets import MarketTableWidget
from .refresh_worker import MarketRefreshWorker
from core.market_engine import apply_filters
from core.market_models import FilterConfig

class MarketSimpleView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.all_opportunities = []
        self.current_config = FilterConfig()
        self.setup_ui()
        
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
        
        filter_layout.addRow("Capital Max:", self.spin_capital)
        filter_layout.addRow("Min Vol/Día:", self.spin_vol)
        filter_layout.addRow("Min Margen:", self.spin_margin)
        filter_layout.addRow("Max Spread:", self.spin_spread)
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
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        self.lbl_status = QLabel("Listo - Presiona Refrescar para cargar datos de Jita")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        
        self.table = MarketTableWidget()
        
        right_layout.addWidget(self.progress_bar)
        right_layout.addWidget(self.lbl_status)
        right_layout.addWidget(self.table)
        
        main_layout.addWidget(filter_panel)
        main_layout.addWidget(right_panel)
        
    def on_refresh_clicked(self):
        if self.worker and self.worker.isRunning():
            return
            
        self.update_config_from_ui()
        
        self.btn_refresh.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Iniciando conexión ESI...")
        
        self.worker = MarketRefreshWorker(region_id=10000002) # Default The Forge
        self.worker.config = self.current_config
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.data_ready.connect(self.on_data_ready)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()
        
    def on_progress(self, pct, text):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(text)
        
    def on_data_ready(self, opps):
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Cargadas {len(opps)} oportunidades desde ESI.")
        self.all_opportunities = opps
        self.apply_and_display()
        
    def on_error(self, err_msg):
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Error: {err_msg}")
        
    def update_config_from_ui(self):
        self.current_config.capital_max = self.spin_capital.value()
        self.current_config.vol_min_day = self.spin_vol.value()
        self.current_config.margin_min_pct = self.spin_margin.value()
        self.current_config.spread_max_pct = self.spin_spread.value()
        self.current_config.exclude_plex = self.chk_plex.isChecked()
        
    def on_apply_filters(self):
        self.update_config_from_ui()
        self.apply_and_display()
        
    def apply_and_display(self):
        filtered = apply_filters(self.all_opportunities, self.current_config)
        # Sort by score descending and take top 50
        filtered.sort(key=lambda x: x.score_breakdown.final_score if x.score_breakdown else 0, reverse=True)
        top_50 = filtered[:50]
        self.table.populate(top_50)
