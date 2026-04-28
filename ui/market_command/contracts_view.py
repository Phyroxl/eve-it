from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDoubleSpinBox, QSpinBox, QCheckBox, QProgressBar,
    QGridLayout, QComboBox, QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from core.contracts_models import ContractsFilterConfig
from core.config_manager import load_contracts_filters, save_contracts_filters
from ui.market_command.contracts_worker import ContractsScanWorker
from ui.market_command.performance_view import AsyncImageLoader
from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.item_metadata import ItemMetadataHelper, MARKET_CATEGORIES
from ui.market_command.widgets import ItemInteractionHelper


def _format_isk(value: float) -> str:
    if value >= 1_000_000_000: return f"{value/1_000_000_000:.2f}B ISK"
    if value >= 1_000_000:     return f"{value/1_000_000:.1f}M ISK"
    if value >= 1_000:         return f"{value/1_000:.1f}K ISK"
    return f"{value:.0f} ISK"

def _format_expiry(date_expired: str) -> str:
    from datetime import datetime, timezone
    try:
        exp = datetime.fromisoformat(date_expired.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff = exp - now
        if diff.total_seconds() <= 0:
            return "Expirado"
        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return date_expired


class MarketContractsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._all_results = []
        self.config = load_contracts_filters()
        self.image_loader = AsyncImageLoader()
        self.setup_ui()
        self._load_config()

    def setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Panel izquierdo: Filtros (230px fijo)
        filter_panel = QFrame()
        filter_panel.setFixedWidth(230)
        filter_panel.setStyleSheet("background: #0f172a; border-right: 1px solid #1e293b;")
        fl = QVBoxLayout(filter_panel)
        fl.setContentsMargins(15, 15, 15, 15)
        fl.setSpacing(12)

        lbl_filters = QLabel("FILTROS")
        lbl_filters.setStyleSheet("color: #f1f5f9; font-size: 14px; font-weight: 900; letter-spacing: 1px; border: none;")
        fl.addWidget(lbl_filters)

        def create_dspin(label, min_v, max_v, step, suffix):
            v_l = QVBoxLayout()
            v_l.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 800; border: none;")
            spin = QDoubleSpinBox()
            spin.setRange(min_v, max_v)
            spin.setSingleStep(step)
            spin.setSuffix(suffix)
            spin.setDecimals(1)
            spin.setStyleSheet(
                "QDoubleSpinBox { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; padding: 4px; border-radius: 2px; }"
            )
            v_l.addWidget(lbl)
            v_l.addWidget(spin)
            fl.addLayout(v_l)
            return spin

        def create_spin(label, min_v, max_v, step):
            v_l = QVBoxLayout()
            v_l.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800; border: none;")
            spin = QSpinBox()
            spin.setRange(min_v, max_v)
            spin.setSingleStep(step)
            spin.setStyleSheet(
                "QSpinBox { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; padding: 4px; border-radius: 2px; }"
            )
            v_l.addWidget(lbl)
            v_l.addWidget(spin)
            fl.addLayout(v_l)
            return spin

        v_reg = QVBoxLayout()
        v_reg.setSpacing(2)
        lbl_reg = QLabel("REGIÓN")
        lbl_reg.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800; border: none;")
        self.combo_region = QComboBox()
        self.combo_region.setStyleSheet("QComboBox { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; padding: 4px; border-radius: 2px; }")
        self.combo_region.addItem("The Forge (Jita)", 10000002)
        self.combo_region.addItem("Domain (Amarr)", 10000043)
        self.combo_region.addItem("Sinq Laison (Dodixie)", 10000032)
        self.combo_region.addItem("Heimatar (Rens)", 10000030)
        self.combo_region.addItem("Metropolis (Hek)", 10000042)
        v_reg.addWidget(lbl_reg)
        v_reg.addWidget(self.combo_region)
        fl.addLayout(v_reg)

        v_cat = QVBoxLayout()
        v_cat.setSpacing(2)
        lbl_cat = QLabel("CATEGORÍA")
        lbl_cat.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800; border: none;")
        self.combo_category = QComboBox()
        self.combo_category.setStyleSheet("QComboBox { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; padding: 4px; border-radius: 2px; }")
        self.combo_category.addItem("Todas las categorías", "all")
        for cat in MARKET_CATEGORIES:
            self.combo_category.addItem(cat.name, cat.id)
        v_cat.addWidget(lbl_cat)
        v_cat.addWidget(self.combo_category)
        fl.addLayout(v_cat)

        self.capital_max_spin = create_dspin("CAPITAL MAX", 1, 100000, 100, " M ISK")
        self.capital_min_spin = create_dspin("CAPITAL MIN", 0, 100000, 1, " M ISK")
        self.profit_min_spin = create_dspin("PROFIT MINIMO", 0, 10000, 10, " M ISK")
        self.roi_min_spin = create_dspin("ROI MINIMO", 0, 500, 1, " %")
        self.items_max_spin = create_spin("MAX TIPOS ITEM", 1, 500, 1)
        self.scan_max_spin = create_spin("MAX CONTRATOS A ESCANEAR", 10, 5000, 10)

        self.exclude_no_price_check = QCheckBox("Excluir items sin precio")
        self.exclude_no_price_check.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        fl.addWidget(self.exclude_no_price_check)

        self.exclude_blueprints_check = QCheckBox("Excluir Blueprints / BPCs")
        self.exclude_blueprints_check.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        fl.addWidget(self.exclude_blueprints_check)

        fl.addStretch()

        self.btn_apply = QPushButton("APLICAR FILTROS")
        self.btn_apply.setFixedHeight(30)
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setStyleSheet(
            "QPushButton { background-color: #334155; color: white; font-size: 10px; font-weight: 800; border-radius: 4px; border: none; } "
            "QPushButton:hover { background-color: #475569; }"
        )
        self.btn_apply.clicked.connect(self.apply_filters_locally)
        fl.addWidget(self.btn_apply)

        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setFixedHeight(25)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setStyleSheet(
            "QPushButton { background-color: transparent; color: #64748b; font-size: 10px; font-weight: 800; border: 1px solid #334155; border-radius: 4px; } "
            "QPushButton:hover { background-color: #1e293b; color: #f1f5f9; }"
        )
        self.btn_reset.clicked.connect(self.reset_filters)
        fl.addWidget(self.btn_reset)

        self.main_layout.addWidget(filter_panel)

        # Panel derecho: Contenido
        content_panel = QFrame()
        content_panel.setStyleSheet("background: #000000; border: none;")
        cl = QVBoxLayout(content_panel)
        cl.setContentsMargins(15, 15, 15, 15)
        cl.setSpacing(10)

        # Barra superior
        header_l = QHBoxLayout()
        header_title = QLabel("CONTRATOS")
        header_title.setStyleSheet("color: #f1f5f9; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        header_l.addWidget(header_title)
        header_l.addStretch()

        self.btn_clear = QPushButton("LIMPIAR")
        self.btn_clear.setFixedHeight(35)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setStyleSheet(
            "QPushButton { background-color: transparent; color: #64748b; font-size: 10px; font-weight: 800; border: 1px solid #334155; border-radius: 4px; padding: 0 15px; } "
            "QPushButton:hover { background-color: #1e293b; color: #f1f5f9; }"
        )
        self.btn_clear.clicked.connect(self._clear_table)
        header_l.addWidget(self.btn_clear)

        self.btn_cancel = QPushButton("CANCELAR")
        self.btn_cancel.setFixedHeight(35)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #ef4444; color: white; font-size: 10px; font-weight: 800; border-radius: 4px; padding: 0 15px; } "
            "QPushButton:hover { background-color: #dc2626; }"
        )
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        header_l.addWidget(self.btn_cancel)

        self.btn_scan = QPushButton("ESCANEAR")
        self.btn_scan.setFixedHeight(35)
        self.btn_scan.setCursor(Qt.PointingHandCursor)
        self.btn_scan.setStyleSheet(
            "QPushButton { background-color: #3b82f6; color: white; font-size: 10px; font-weight: 900; border-radius: 4px; padding: 0 20px; } "
            "QPushButton:hover { background-color: #2563eb; }"
        )
        self.btn_scan.clicked.connect(self.on_scan_clicked)
        header_l.addWidget(self.btn_scan)

        cl.addLayout(header_l)

        # Insights Widget
        self.insights_widget = QFrame()
        self.insights_widget.setFixedHeight(60)
        self.insights_widget.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;")
        iw_l = QHBoxLayout(self.insights_widget)
        iw_l.setContentsMargins(10, 5, 10, 5)

        def create_kpi(title, color="#f1f5f9"):
            v_l = QVBoxLayout()
            v_l.setSpacing(0)
            t = QLabel(title)
            t.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; border: none;")
            v = QLabel("-")
            v.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 900; border: none;")
            v_l.addWidget(t)
            v_l.addWidget(v)
            iw_l.addLayout(v_l)
            return v

        self.lbl_ins_scanned = create_kpi("ESCANEADOS")
        self.lbl_ins_profit = create_kpi("CON PROFIT", "#10b981")
        self.lbl_ins_roi = create_kpi("MEJOR ROI", "#3b82f6")
        self.lbl_ins_top = create_kpi("TOP PROFIT", "#f59e0b")
        cl.addWidget(self.insights_widget)

        # Progress Widget
        self.progress_widget = QFrame()
        self.progress_widget.setVisible(False)
        pw_l = QHBoxLayout(self.progress_widget)
        pw_l.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("Preparando...")
        self.status_label.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 800;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #1e293b; border-radius: 2px; background: #0f172a; } "
            "QProgressBar::chunk { background-color: #3b82f6; border-radius: 1px; }"
        )
        pw_l.addWidget(self.status_label)
        pw_l.addWidget(self.progress_bar, 1)
        cl.addWidget(self.progress_widget)

        # Results Table
        self.results_table = QTableWidget(0, 9)
        self.results_table.setHorizontalHeaderLabels([
            "#", "Items", "Coste", "Val. Jita Sell", "Val. Jita Buy", "Profit Neto", "ROI %", "Expira", "Score"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.results_table.setColumnWidth(0, 40)
        self.results_table.setColumnWidth(1, 90)
        self.results_table.setColumnWidth(2, 130)
        self.results_table.setColumnWidth(5, 130)
        self.results_table.setColumnWidth(6, 80)
        self.results_table.setColumnWidth(7, 90)
        self.results_table.setColumnWidth(8, 70)

        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        self.results_table.setShowGrid(False)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setStyleSheet(
            "QTableWidget { background: #000000; color: #f1f5f9; border: 1px solid #1e293b; font-size: 10px; } "
            "QHeaderView::section { background: #0f172a; color: #94a3b8; font-weight: 800; font-size: 9px; border: none; padding: 4px; } "
            "QTableWidget::item:selected { background: #1e293b; }"
        )
        self.results_table.cellClicked.connect(self.on_row_selected)
        self.results_table.cellDoubleClicked.connect(self.on_row_double_clicked)
        
        # Splitter para resizabilidad
        self.splitter = QSplitter(Qt.Vertical)
        
        # Contenedor superior para la tabla
        self.table_container = QWidget()
        tc_l = QVBoxLayout(self.table_container)
        tc_l.setContentsMargins(0,0,0,0)
        tc_l.addWidget(self.results_table)
        
        self.splitter.addWidget(self.table_container)
        
        # Detail Frame
        self.detail_frame = QFrame()
        self.detail_frame.setVisible(False)
        self.detail_frame.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;")
        dl = QVBoxLayout(self.detail_frame)
        dl.setContentsMargins(10, 10, 10, 10)
        dl.setSpacing(10)
        
        self.splitter.addWidget(self.detail_frame)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        
        cl.addWidget(self.splitter, 1)

        dl_h1 = QHBoxLayout()
        self.lbl_det_title = QLabel("CONTRATO")
        self.lbl_det_title.setStyleSheet("color: #f1f5f9; font-size: 14px; font-weight: 900; border: none;")
        dl_h1.addWidget(self.lbl_det_title)
        dl_h1.addStretch()

        self.btn_copy_id = QPushButton("COPIAR CONTRACT ID")
        self.btn_copy_id.setCursor(Qt.PointingHandCursor)
        self.btn_copy_id.setStyleSheet(
            "QPushButton { background: transparent; color: #64748b; font-weight: 800; font-size: 9px; border: 1px solid #334155; border-radius: 2px; padding: 2px 8px; } "
            "QPushButton:hover { background: #1e293b; color: #f1f5f9; }"
        )
        self.btn_copy_id.clicked.connect(lambda: self.copy_contract_id(getattr(self, '_current_contract_id', 0)))
        dl_h1.addWidget(self.btn_copy_id)

        self.btn_open_game = QPushButton("ABRIR IN-GAME")
        self.btn_open_game.setCursor(Qt.PointingHandCursor)
        self.btn_open_game.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; font-weight: 800; font-size: 9px; border-radius: 2px; padding: 2px 8px; } "
            "QPushButton:hover { background: #2563eb; }"
        )
        self.btn_open_game.clicked.connect(self.on_open_in_game_clicked)
        dl_h1.addWidget(self.btn_open_game)

        dl.addLayout(dl_h1)

        # Panel de resumen (Métricas extendidas)
        self.det_metrics_layout = QHBoxLayout()
        dl.addLayout(self.det_metrics_layout)
        
        self.lbl_det_cost = QLabel()
        self.lbl_det_sell = QLabel()
        self.lbl_det_profit = QLabel()
        self.lbl_det_roi = QLabel()
        self.lbl_det_risk = QLabel()
        
        for l in [self.lbl_det_cost, self.lbl_det_sell, self.lbl_det_profit, self.lbl_det_roi, self.lbl_det_risk]:
            l.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 700; border: none;")
            self.det_metrics_layout.addWidget(l)
        self.det_metrics_layout.addStretch()

        self.items_table = QTableWidget(0, 6)
        self.items_table.setHorizontalHeaderLabels(["", "Item", "Cant", "Precio Jita", "Valor", "% Total"])
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.items_table.setColumnWidth(0, 32)
        self.items_table.setColumnWidth(2, 60)
        self.items_table.setColumnWidth(3, 100)
        self.items_table.setColumnWidth(4, 100)
        self.items_table.setColumnWidth(5, 60)
        self.items_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.items_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.items_table.setShowGrid(False)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.cellDoubleClicked.connect(self.on_item_double_clicked)
        self.items_table.setStyleSheet(
            "QTableWidget { background: #000000; color: #f1f5f9; border: none; font-size: 10px; } "
            "QHeaderView::section { background: #1e293b; color: #64748b; font-weight: 800; font-size: 8px; border: none; padding: 2px; } "
            "QTableWidget::item { border: none; }"
        )
        dl.addWidget(self.items_table, 1)

        self.main_layout.addWidget(content_panel, 1)

    def _load_config(self):
        index = self.combo_region.findData(self.config.region_id)
        if index >= 0:
            self.combo_region.setCurrentIndex(index)
        self.capital_max_spin.setValue(self.config.capital_max_isk / 1_000_000)
        self.capital_min_spin.setValue(self.config.capital_min_isk / 1_000_000)
        self.profit_min_spin.setValue(self.config.profit_min_isk / 1_000_000)
        self.roi_min_spin.setValue(self.config.roi_min_pct)
        self.items_max_spin.setValue(self.config.item_types_max)
        self.scan_max_spin.setValue(self.config.max_contracts_to_scan)
        self.exclude_no_price_check.setChecked(self.config.exclude_no_price)
        self.exclude_blueprints_check.setChecked(self.config.exclude_blueprints)
        
        idx = self.combo_category.findData(self.config.category_filter)
        if idx >= 0: self.combo_category.setCurrentIndex(idx)

    def _save_config(self):
        self.config.region_id = self.combo_region.currentData()
        self.config.capital_max_isk = self.capital_max_spin.value() * 1_000_000
        self.config.capital_min_isk = self.capital_min_spin.value() * 1_000_000
        self.config.profit_min_isk = self.profit_min_spin.value() * 1_000_000
        self.config.roi_min_pct = self.roi_min_spin.value()
        self.config.item_types_max = self.items_max_spin.value()
        self.config.max_contracts_to_scan = self.scan_max_spin.value()
        self.config.exclude_no_price = self.exclude_no_price_check.isChecked()
        self.config.exclude_blueprints = self.exclude_blueprints_check.isChecked()
        self.config.category_filter = self.combo_category.currentData() or "all"
        save_contracts_filters(self.config)

    def _clear_table(self):
        self.results_table.setRowCount(0)
        self._all_results = []
        self.detail_frame.setVisible(False)
        self.lbl_ins_scanned.setText("-")
        self.lbl_ins_profit.setText("-")
        self.lbl_ins_roi.setText("-")
        self.lbl_ins_top.setText("-")

    def reset_filters(self):
        self.config = ContractsFilterConfig()
        self._load_config()

    def on_scan_clicked(self):
        if self.worker and self.worker.isRunning():
            return
        
        auth = AuthManager.instance()
        if not auth.current_token:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Login", "Por favor inicia sesión con EVE SSO (ve a la pestaña Performance o Mis Pedidos).")
            return

        self._save_config()
        self._clear_table()
        
        self.btn_scan.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.progress_widget.setVisible(True)
        self.insights_widget.setVisible(False)
        self.progress_bar.setValue(0)

        self.worker = ContractsScanWorker(self.config)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.batch_ready.connect(self.add_contract_row)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.start()

    def on_cancel_clicked(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("Cancelando...")

    def add_contract_row(self, c):
        # Insertar fila si cumple filtro (aunque en worker ya deberia cumplir algo, 
        # pero es útil re-chequear si se cambian filtros locales? Worker ya lo manda si profit > 0)
        if c.net_profit < self.config.profit_min_isk or c.roi_pct < self.config.roi_min_pct or c.item_type_count > self.config.item_types_max:
            return
        if self.config.exclude_no_price and c.has_unresolved_items:
            return

        row = self.results_table.rowCount()
        self.results_table.insertRow(row)

        i_num = QTableWidgetItem(str(row + 1))
        i_num.setTextAlignment(Qt.AlignCenter)
        
        items_txt = str(c.item_type_count)
        if c.has_unresolved_items:
            items_txt += " ⚠"
        i_items = QTableWidgetItem(items_txt)
        i_items.setTextAlignment(Qt.AlignCenter)
        
        i_cost = QTableWidgetItem(_format_isk(c.contract_cost))
        i_cost.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        i_js = QTableWidgetItem(_format_isk(c.jita_sell_value))
        i_js.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        i_jb = QTableWidgetItem(_format_isk(c.jita_buy_value))
        i_jb.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        i_profit = QTableWidgetItem(_format_isk(c.net_profit))
        i_profit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        i_profit.setForeground(QColor("#10b981"))
        
        i_roi = QTableWidgetItem(f"{c.roi_pct:.1f}%")
        i_roi.setTextAlignment(Qt.AlignCenter)
        if c.roi_pct > 20: i_roi.setForeground(QColor("#10b981"))
        elif c.roi_pct > 10: i_roi.setForeground(QColor("#f59e0b"))
        else: i_roi.setForeground(QColor("#f1f5f9"))
        
        exp_txt = _format_expiry(c.date_expired)
        i_exp = QTableWidgetItem(exp_txt)
        i_exp.setTextAlignment(Qt.AlignCenter)
        if "m" in exp_txt and "d" not in exp_txt and "h" not in exp_txt:
            i_exp.setForeground(QColor("#ef4444"))
        elif "h" in exp_txt and "d" not in exp_txt:
            i_exp.setForeground(QColor("#ef4444"))
            
        i_score = QTableWidgetItem(f"{c.score:.1f}")
        i_score.setTextAlignment(Qt.AlignCenter)
        
        # Color coding de fila
        if c.score > 70:
            for i in [i_num, i_items, i_cost, i_js, i_jb, i_profit, i_roi, i_exp, i_score]:
                i.setBackground(QColor("#0d2418"))
        elif c.score < 40:
            for i in [i_num, i_items, i_cost, i_js, i_jb, i_profit, i_roi, i_exp, i_score]:
                i.setBackground(QColor("#1a1505"))

        self.results_table.setItem(row, 0, i_num)
        self.results_table.setItem(row, 1, i_items)
        self.results_table.setItem(row, 2, i_cost)
        self.results_table.setItem(row, 3, i_js)
        self.results_table.setItem(row, 4, i_jb)
        self.results_table.setItem(row, 5, i_profit)
        self.results_table.setItem(row, 6, i_roi)
        self.results_table.setItem(row, 7, i_exp)
        self.results_table.setItem(row, 8, i_score)
        
        for col in range(9):
            it = self.results_table.item(row, col)
            if it: it.setTextAlignment(Qt.AlignCenter)
        
        # Guardar ref oculta en la fila
        i_num.setData(Qt.UserRole, c)

    def on_scan_finished(self, results):
        self._all_results = results
        self.btn_scan.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.progress_widget.setVisible(False)
        self.insights_widget.setVisible(True)
        
        self.apply_filters_locally() # Re-render final ordenado

    def on_scan_error(self, msg):
        self.btn_scan.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.progress_widget.setVisible(False)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error de Escaneo", msg)

    def apply_filters_locally(self):
        if not self._all_results:
            return
        self._save_config()
        self.results_table.setRowCount(0)
        
        from core.contracts_engine import apply_contracts_filters
        filtered = apply_contracts_filters(self._all_results, self.config)
        
        for c in filtered:
            self.add_contract_row(c)
            
        # Actualizar Insights
        scanned = getattr(self.worker, '_scanned_count', len(self._all_results)) if self.worker else len(self._all_results)
        self.lbl_ins_scanned.setText(str(scanned))
        self.lbl_ins_profit.setText(str(len(filtered)))
        
        if filtered:
            best_roi = max(filtered, key=lambda x: x.roi_pct).roi_pct
            best_profit = max(filtered, key=lambda x: x.net_profit).net_profit
            self.lbl_ins_roi.setText(f"{best_roi:.1f}%")
            self.lbl_ins_top.setText(_format_isk(best_profit))
        else:
            self.lbl_ins_roi.setText("-")
            self.lbl_ins_top.setText("-")

    def on_row_selected(self, row, col):
        item = self.results_table.item(row, 0)
        if not item: return
        c = item.data(Qt.UserRole)
        if c:
            self.populate_detail_panel(c)

    def on_row_double_clicked(self, row, col):
        item = self.results_table.item(row, 0)
        if not item: return
        c = item.data(Qt.UserRole)
        if c:
            self._current_contract_id = c.contract_id
            self.on_open_in_game_clicked()

    def populate_detail_panel(self, c):
        self._current_contract_id = c.contract_id
        
        # Guardar top item para poder abrir su mercado
        items = sorted(c.items, key=lambda x: x.line_sell_value, reverse=True)
        self._current_main_item_id = items[0].type_id if items else 0
        
        self.lbl_det_title.setText(f"CONTRATO {c.contract_id} — SCORE: {c.score:.1f}")
        
        # Llenar métricas
        self.lbl_det_cost.setText(f"<b>COSTE:</b> <span style='color:#f1f5f9;'>{_format_isk(c.contract_cost)}</span>")
        self.lbl_det_sell.setText(f"<b>JITA SELL:</b> <span style='color:#f1f5f9;'>{_format_isk(c.jita_sell_value)}</span>")
        
        color_p = "#10b981" if c.net_profit > 0 else "#ef4444"
        self.lbl_det_profit.setText(f"<b>NET PROFIT:</b> <span style='color:{color_p};'>{_format_isk(c.net_profit)}</span>")
        
        color_r = "#10b981" if c.roi_pct >= 20 else ("#f59e0b" if c.roi_pct >= 10 else "#f1f5f9")
        self.lbl_det_roi.setText(f"<b>ROI:</b> <span style='color:{color_r};'>{c.roi_pct:.1f}%</span>")
        
        risk_msgs = []
        if c.has_unresolved_items:
            risk_msgs.append(f"{c.unresolved_count} item(s) sin precio")
        if c.value_concentration > 0.80:
            risk_msgs.append(f"Alta concentración ({c.value_concentration*100:.0f}%)")
            
        if risk_msgs:
            self.lbl_det_risk.setText(f"<b>RIESGO:</b> <span style='color:#f59e0b;'>{' | '.join(risk_msgs)}</span>")
        else:
            self.lbl_det_risk.setText(f"<b>RIESGO:</b> <span style='color:#10b981;'>Bajo</span>")
            
        self.detail_frame.setVisible(True)
        
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(items))
        for r, item in enumerate(items):
            i_name = QTableWidgetItem(item.item_name)
            i_qty = QTableWidgetItem(f"{item.quantity:,}")
            i_qty.setTextAlignment(Qt.AlignCenter)
            
            if not item.is_included:
                i_name.setText(i_name.text() + " (REQUERIDO)")
                i_name.setForeground(QColor("#ef4444"))
                
            price_txt = _format_isk(item.jita_sell_price) if item.jita_sell_price > 0 else "N/A"
            i_price = QTableWidgetItem(price_txt)
            i_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            val_txt = _format_isk(item.line_sell_value) if item.jita_sell_price > 0 else "N/A"
            i_val = QTableWidgetItem(val_txt)
            i_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            i_pct = QTableWidgetItem(f"{item.pct_of_total:.1f}%")
            i_pct.setTextAlignment(Qt.AlignCenter)
            
            if not item.is_included:
                for it in [i_price, i_val, i_pct]:
                    it.setText("-")
            
            if item.jita_sell_price == 0.0 and item.is_included:
                for it in [i_name, i_qty, i_price, i_val, i_pct]:
                    it.setForeground(QColor("#f59e0b"))

            # Icono asíncrono inteligente
            i_icon = QTableWidgetItem()
            self.items_table.setItem(r, 0, i_icon)
            
            icon_url = ItemMetadataHelper.get_icon_url(
                item.type_id, 
                is_blueprint=item.is_blueprint, 
                is_copy=item.is_copy
            )
            self.image_loader.load(icon_url, lambda px, item_item=i_icon: item_item.setIcon(QIcon(px)))

            self.items_table.setItem(r, 1, i_name)
            i_name.setData(Qt.UserRole, item.type_id)
            self.items_table.setItem(r, 2, i_qty)
            self.items_table.setItem(r, 3, i_price)
            self.items_table.setItem(r, 4, i_val)
            self.items_table.setItem(r, 5, i_pct)
            
            for col in range(6):
                it = self.items_table.item(r, col)
                if it: it.setTextAlignment(Qt.AlignCenter)

    def on_item_double_clicked(self, row, col):
        item_obj = self.items_table.item(row, 1)
        if not item_obj: return
        type_id = item_obj.data(Qt.UserRole)
        item_name = item_obj.text()
        
        auth = AuthManager.instance()
        def feedback(msg, color):
            self.status_label.setText(f"● {msg.upper()}")
            self.status_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800;")
            
        ItemInteractionHelper.open_market_with_fallback(ESIClient(), auth.char_id, type_id, item_name, feedback)

    def on_open_in_game_clicked(self):
        contract_id = getattr(self, '_current_contract_id', 0)
        if not contract_id: return
        
        def feedback(msg, color):
            self.status_label.setText(f"● {msg.upper()}")
            self.status_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800;")

        ItemInteractionHelper.open_contract_in_game(ESIClient(), contract_id, feedback)

    def open_main_item_market(self):
        auth = AuthManager.instance()
        if not auth.current_token:
            return
        main_item_id = getattr(self, '_current_main_item_id', 0)
        if main_item_id > 0:
            from ui.market_command.widgets import ItemInteractionHelper
            # Necesitamos pasar un callback de feedback, podemos usar lambda vacío ya que la barra está en parent
            ItemInteractionHelper.open_market_window(main_item_id, auth, lambda x, y: None)

    def copy_contract_id(self, contract_id):
        QGuiApplication.clipboard().setText(str(contract_id))
