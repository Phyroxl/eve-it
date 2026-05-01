import logging
import traceback
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDoubleSpinBox, QSpinBox, QCheckBox, QProgressBar,
    QGridLayout, QComboBox, QSplitter, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPixmap, QPainter, QKeySequence

logger = logging.getLogger(__name__)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from core.eve_icon_service import EveIconService

from core.contracts_models import ContractsFilterConfig, ScanDiagnostics
from core.config_manager import load_contracts_filters, save_contracts_filters
from ui.market_command.contracts_worker import ContractsScanWorker
# from ui.market_command.performance_view import AsyncImageLoader (Removed)
from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.item_metadata import ItemMetadataHelper, MARKET_CATEGORIES
from ui.market_command.widgets import ItemInteractionHelper


def _format_isk(value: float) -> str:
    abs_v = abs(value)
    if abs_v >= 1_000_000_000: 
        res = f"{value/1_000_000_000:.2f}B".replace(".", ",")
    elif abs_v >= 1_000_000:
        res = f"{value/1_000_000:.1f}M".replace(".", ",")
    elif abs_v >= 1_000:
        res = f"{value/1_000:.1f}K".replace(".", ",")
    else:
        res = f"{value:.0f}"
    
    return f"{res} ISK"

def _format_isk_full(value: float) -> str:
    """Formato con puntos de miles: 1.234.567 ISK"""
    # En Python {:,} usa comas por defecto.
    s = f"{int(value):,}".replace(",", ".")
    return f"{s} ISK"

class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, text, value):
        super().__init__(str(text))
        self.sort_value = float(value) if value is not None else -1e18

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)

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


class ContractReportDialog(QWidget):
    def __init__(self, report_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnóstico de Escaneo de Contratos")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.resize(700, 500)
        self.setStyleSheet("background: #0f172a; color: #f1f5f9;")
        
        layout = QVBoxLayout(self)
        self.txt = QTableWidget() # Usaremos un widget de texto para el reporte
        self.edit = QTextEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlainText(report_text)
        self.edit.setStyleSheet("""
            QTextEdit { 
                background: #000000; 
                color: #10b981; 
                font-family: 'Consolas', monospace; 
                font-size: 11px; 
                border: 1px solid #1e293b; 
                padding: 10px;
            }
        """)
        layout.addWidget(self.edit)
        
        btns = QHBoxLayout()
        btn_copy = QPushButton("COPIAR REPORTE")
        btn_copy.setStyleSheet("background: #10b981; color: #064e3b; font-weight: 800; padding: 10px; border-radius: 4px;")
        btn_copy.clicked.connect(self.copy_report)
        
        btn_close = QPushButton("CERRAR")
        btn_close.setStyleSheet("background: #1e293b; color: #f1f5f9; padding: 10px; border-radius: 4px;")
        btn_close.clicked.connect(self.close)
        
        btns.addWidget(btn_copy)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def copy_report(self):
        QGuiApplication.clipboard().setText(self.edit.toPlainText())


class MarketContractsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._all_results = []
        self.last_diag = None
        self._scan_start_time = None
        self._scan_events = []
        self.config = load_contracts_filters()
        self.icon_service = EveIconService.instance()
        self._image_generation = 0
        self._last_open_attempt = 0
        self._last_open_source = "none"
        self._last_open_success = False
        self._last_open_error = ""
        self.setup_ui()
        self._load_config()

    def activate_view(self):
        """Hook para activación de pestaña."""
        pass

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
        self.scan_max_spin = create_spin("MAX CONTRATOS A ESCANEAR", 0, 10000, 10)
        self.scan_max_spin.setSpecialValueText("0 (Sin límite)")

        self.exclude_no_price_check = QCheckBox("Excluir items sin precio")
        self.exclude_no_price_check.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        fl.addWidget(self.exclude_no_price_check)

        self.exclude_blueprints_check = QCheckBox("Excluir Blueprints (BPOs)")
        self.exclude_blueprints_check.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        fl.addWidget(self.exclude_blueprints_check)

        self.check_bpcs = QCheckBox("Excluir Copias (BPCs)")
        self.check_bpcs.setChecked(self.config.exclude_bpcs)
        self.check_bpcs.setStyleSheet("color: #94a3b8; font-size: 10px;")
        fl.addWidget(self.check_bpcs)

        self.check_abyssal = QCheckBox("Excluir Abyssal")
        self.check_abyssal.setChecked(self.config.exclude_abyssal)
        self.check_abyssal.setStyleSheet("color: #94a3b8; font-size: 10px;")
        fl.addWidget(self.check_abyssal)

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
        self.btn_clear.clicked.connect(self.on_clear_clicked)
        header_l.addWidget(self.btn_clear)

        self.btn_report = QPushButton("REPORTE")
        self.btn_report.setFixedHeight(35)
        self.btn_report.setCursor(Qt.PointingHandCursor)
        self.btn_report.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #94a3b8; font-size: 10px; font-weight: 800; border: 1px solid #334155; border-radius: 4px; padding: 0 15px; } "
            "QPushButton:hover { background-color: #334155; color: #f1f5f9; }"
        )
        self.btn_report.clicked.connect(self.on_report_clicked)
        header_l.addWidget(self.btn_report)

        self.btn_cancel = QPushButton("CANCELAR ESCANEO")
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
        self.btn_scan.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_scan.customContextMenuRequested.connect(self.on_scan_context_menu)
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
        self.results_table.setSortingEnabled(True)
        
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

        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(["Item", "Cant", "Precio Jita", "Valor", "% Total"])
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.items_table.setColumnWidth(1, 60)
        self.items_table.setColumnWidth(2, 100)
        self.items_table.setColumnWidth(3, 100)
        self.items_table.setColumnWidth(4, 60)
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

        self.main_layout.addWidget(content_panel)

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
        self.check_bpcs.setChecked(self.config.exclude_bpcs)
        self.check_abyssal.setChecked(self.config.exclude_abyssal)
        
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
        self.config.exclude_bpcs = self.check_bpcs.isChecked()
        self.config.exclude_abyssal = self.check_abyssal.isChecked()
        self.config.category_filter = self.combo_category.currentData() or "all"
        save_contracts_filters(self.config)

    def _clear_table(self):
        self.results_table.setRowCount(0)
        self._all_results = []
        self._scan_events = []
        self.detail_frame.setVisible(False)
        self.lbl_ins_scanned.setText("-")
        self.lbl_ins_profit.setText("-")
        self.lbl_ins_roi.setText("-")
        self.lbl_ins_top.setText("-")

    def reset_filters(self):
        from core.contracts_models import ContractsFilterConfig
        self.config = ContractsFilterConfig()
        self._load_config()

    def on_scan_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        force_act = menu.addAction("Forzar Recalcular Todo (Ignorar Cache)")
        force_act.triggered.connect(lambda: self.on_scan_clicked(force_refresh=True))
        menu.exec_(self.btn_scan.mapToGlobal(pos))

    def on_scan_clicked(self, force_refresh=False):
        if self.worker and self.worker.isRunning():
            return
        
        auth = AuthManager.instance()
        if not auth.current_token:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Login", "Por favor inicia sesión con EVE SSO (ve a la pestaña Performance o Mis Pedidos).")
            return

        import time
        self._scan_start_time = time.time()
        self._save_config()
        self._clear_table()
        
        self.btn_scan.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.progress_widget.setVisible(True)
        self.insights_widget.setVisible(False)
        self.progress_bar.setValue(0)

        self._scan_events.append(f"scan_started at {time.strftime('%H:%M:%S')}")
        
        self.worker = ContractsScanWorker(self.config, force_refresh=force_refresh)
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

    def on_clear_clicked(self):
        self._clear_table()
        self.status_label.setText("Tabla limpia.")
        self.status_label.setStyleSheet("color: #64748b; font-size: 9px;")

    def on_report_clicked(self):
        report = self.generate_diagnostic_report()
        self.diag_win = ContractReportDialog(report, self)
        self.diag_win.show()

    def generate_diagnostic_report(self) -> str:
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = []
        report.append("[CONTRACT SCAN REPORT]")
        report.append(f"Generated At: {now}")
        report.append(f"Region: {self.combo_region.currentText()} ({self.config.region_id})")
        report.append(f"Category: {self.combo_category.currentText()} ({self.config.category_filter})")
        report.append("\n[ESI FETCH]")
        report.append(f"  Region ID: {self.config.region_id}")
        report.append(f"  ESI X-Pages: {d.esi_total_pages}")
        report.append(f"  Pages Fetched: {d.esi_pages_fetched}")
        report.append(f"  Contracts Fetched Raw: {d.esi_raw_contracts:,}")
        report.append(f"  Contracts Fetched Unique: {d.esi_unique_contracts:,}")
        report.append(f"  Duplicate Contract IDs: {d.esi_raw_contracts - d.esi_unique_contracts:,}")
        report.append(f"  Fetch Stopped Reason: {d.esi_fetch_stopped_reason}")
        report.append(f"  Effective Max Contracts: {self.config.max_contracts_to_scan if self.config.max_contracts_to_scan > 0 else 'Unlimited'}")
        report.append(f"  Max Contracts Limit Hit: {d.esi_limit_hit}")

        report.append("\n[PIPELINE COUNTS]")
        report.append(f"  ESI Unique Contracts: {d.esi_unique_contracts:,}")
        report.append(f"  After Pre-Filters (Candidates): {d.total_scanned:,}")
        report.append(f"  Analyzed (Success): {d.val_total_items_seen if d.val_total_items_seen > 0 else d.total_scanned:,}")
        report.append(f"  Profitable Found: {d.profitable}")
        report.append(f"  Visible in UI: {self.results_table.rowCount()}")

        report.append("\n[HIDDEN FILTERS CHECK]")
        report.append("  Any Hidden Filters Active: True")
        report.append("  Hidden Type Filter: item_exchange (HARDCODED)")
        report.append("  Hidden Status Filter: outstanding (HARDCODED)")
        report.append("  Hidden Expire Filter: > 1 hour remaining (HARDCODED)")
        report.append(f"  Hidden Max Contracts: {self.config.max_contracts_to_scan if self.config.max_contracts_to_scan > 0 else 'None'}")

        report.append("\n[FILTERS (UI)]")
        report.append(f"  capital_min: {self.config.capital_min_isk:,.0f} ISK")
        report.append(f"  capital_max: {self.config.capital_max_isk:,.0f} ISK")
        report.append(f"  min_profit: {self.config.profit_min_isk:,.0f} ISK")
        report.append(f"  min_roi_pct: {self.config.roi_min_pct}%")
        report.append(f"  max_item_types: {self.config.item_types_max}")
        report.append(f"  category_filter: {self.config.category_filter}")
        report.append(f"  exclude_no_price: {self.config.exclude_no_price}")
        report.append(f"  exclude_blueprints: {self.config.exclude_blueprints}")
        report.append(f"  exclude_bpcs: {self.config.exclude_bpcs}")
        report.append(f"  exclude_abyssal: {self.config.exclude_abyssal}")

        report.append("\n[OPEN IN-GAME]")
        report.append(f"  Last Open Attempt: {self._last_open_attempt if self._last_open_attempt > 0 else 'None'}")
        report.append(f"  Last Open Source: {self._last_open_source}")
        report.append(f"  Selected Contract ID: {getattr(self, '_current_contract_id', 'None')}")
        report.append(f"  Open Method: ESI UI (POST /ui/openwindow/contract/)")
        report.append(f"  Open Success: {self._last_open_success}")
        if self._last_open_error:
            report.append(f"  Open Error: {self._last_open_error}")

        if not self.last_diag:
            report.append("\nNo hay diagnóstico disponible todavía. Ejecuta un escaneo.")
            return "\n".join(report)

        d = self.last_diag
        report.append("\n[PIPELINE]")
        report.append(f"  Total Scanned (Candidates): {len(self._all_results)}")
        report.append(f"  Profitable (Strict): {d.profitable}")
        report.append(f"  Visible in UI: {self.results_table.rowCount()}")

        report.append("\n[DISPLAY POLICY]")
        report.append(f"  Mode: EXPLORATORY (Show All Scanned)")
        report.append(f"  Hide Low Profit: {'True' if self.config.profit_min_isk > 0 else 'False'}")
        report.append(f"  Hide Low ROI: {'True' if self.config.roi_min_pct > 0 else 'False'}")
        report.append(f"  Hide Zero Value: {'True' if self.config.exclude_no_price else 'False'}")

        report.append(f"  Total Visible: {self.results_table.rowCount()}")

        report.append("\n[FILTER EXCLUSIONS (HIDDEN)]")
        report.append(f"  Excluded by Capital: {d.excluded_by_low_profit if self.config.capital_min_isk > 0 or self.config.capital_max_isk < 1e12 else 0}")
        report.append(f"  Excluded by No Items: {d.excluded_by_no_items}")
        report.append(f"  Excluded by Blueprint: {d.excluded_by_blueprint}")
        report.append(f"  Excluded by BPC: {d.excluded_by_bpc}")
        report.append(f"  Excluded by Abyssal: {d.excluded_by_abyssal}")
        report.append(f"  Excluded by Complexity: {d.excluded_by_complexity}")
        report.append(f"  Excluded by Category: {d.excluded_by_category}")
        if self.config.exclude_no_price:
            report.append(f"  Excluded by Zero Value Filter: {d.excluded_by_no_price}")

        report.append("\n[ICON DIAGNOSTICS]")
        id_diag = self.icon_service.get_diagnostics()
        report.append(f"  Loaded: {id_diag['loaded']} | Failed: {id_diag['failed_total']}")
        report.append(f"  Placeholders Used: {id_diag['placeholders']}")
        
        report.append("\n[ZERO VALUE ANALYSIS (NON-EXCLUDED)]")
        report.append(f"  Total Zero Value Seen: {d.excluded_by_zero_value}")
        report.append(f"  All Items Missing Price: {d.zv_all_items_missing_price}")
        report.append(f"  Item Details Missing: {d.zv_item_details_missing}")
        report.append(f"  Price Lookup Failed: {d.zv_price_lookup_failed}")
        report.append(f"  Jita Sell Missing: {d.zv_jita_sell_missing}")
        report.append(f"  Blueprint/BPC Disabled: {d.zv_blueprint_bpc_disabled}")
        report.append(f"  Unknown/Other: {d.zv_unknown}")

        report.append("\n[VALUATION COUNTS]")
        report.append(f"  Contracts With Any Priced Items: {d.val_any_priced}")
        report.append(f"  Contracts With All Items Priced: {d.val_all_priced}")
        report.append(f"  Contracts With Partial Pricing: {d.val_partial_pricing}")
        report.append(f"  Contracts With No Priced Items: {d.val_no_priced}")
        report.append(f"  Items Priced: {d.val_items_priced} / {d.val_total_items_seen}")
        report.append(f"  Items Missing Price: {d.val_items_missing_price}")

        report.append("\n[CACHE DETAILS]")
        from core.contracts_cache import ContractsCache
        cc = ContractsCache.instance()
        report.append(f"  Cache File: {cc._cache_file}")
        report.append(f"  Cache Version: {cc.VERSION}")
        report.append(f"  Cache Entries: {len(cc.cache)}")
        report.append(f"  Scan Hits: {d.contract_cache_hits}")
        report.append(f"  Scan Misses: {d.contract_cache_misses}")
        
        # Panel de detalles (info de selección actual)
        report.append("\n[DETAILS PANEL]")
        if hasattr(self, '_current_contract_id') and self._current_contract_id:
            report.append(f"  Selected Contract ID: {self._current_contract_id}")
            report.append(f"  Items in Table: {self.items_table.rowCount()}")
            # Buscar el objeto real
            target = next((res for res in self._all_results if res.contract_id == self._current_contract_id), None)
            if target:
                report.append(f"  Memory Item Count: {len(target.items)}")
                report.append(f"  Has Detailed Items: {len(target.items) > 0}")
            else:
                report.append("  Error: Selected contract not found in _all_results")
        else:
            report.append("  No contract selected in UI")

        if self._scan_start_time:
            import time
            elapsed = time.time() - self._scan_start_time
            report.append(f"\n[PERFORMANCE]")
            report.append(f"  Total Elapsed Time: {elapsed:.2f}s")

        report.append("\n[RESULT LIST SIZES]")
        report.append(f"  Raw Results (All): {len(self._all_results)}")
        report.append(f"  Analyzed Results: {d.total_scanned}")
        report.append(f"  Profitable Found: {d.profitable}")
        report.append(f"  Table Row Count: {self.results_table.rowCount()}")

        # Panel de detalles (info de selección actual)
        report.append("\n[DETAILS PANEL]")
        if hasattr(self, '_current_contract_id') and self._current_contract_id:
            report.append(f"  Selected Contract ID: {self._current_contract_id}")
            report.append(f"  Items in UI Table: {self.items_table.rowCount()}")
            
            # Buscar el objeto real
            target = next((res for res in self._all_results if res.contract_id == self._current_contract_id), None)
            if target:
                report.append(f"  Expected Item Count: {target.item_type_count}")
                report.append(f"  Memory Item Count: {len(target.items)}")
                report.append(f"  Has Detailed Items: {len(target.items) > 0}")
                report.append(f"  Details Load Source: {getattr(self, '_last_details_source', 'unknown')}")
                if hasattr(self, '_last_details_error') and self._last_details_error:
                    report.append(f"  Details Error: {self._last_details_error}")
            else:
                report.append("  Error: Selected contract not found in memory (_all_results)")
        else:
            report.append("  No contract selected in UI")

        if d.profitable > 0 and self.results_table.rowCount() == 0:
            report.append("\n!!! WARNING: profitable_results_exist_but_ui_empty !!!")
            report.append("  (Found profitable contracts but none are visible in the table)")

        report.append("\n[POST SCAN EVENTS]")
        for ev in self._scan_events[-10:]:
            report.append(f"  - {ev}")

        report.append("\n[SAMPLES DISPLAYED (VISIBLE)]")
        for i in range(min(5, self.results_table.rowCount())):
            item = self.results_table.item(i, 0)
            if item:
                c = item.data(Qt.UserRole)
                if c:
                    report.append(f"  ID:{c.contract_id} | Items:{c.item_type_count} (Mem:{len(c.items)}) | Profit:{c.net_profit:,.0f} | ROI:{c.roi_pct:.1f}% | FilterReason:{c.filter_reason}")

        # Muestras de contratos excluidos por Zero Value
        zero_value_samples = [c for c in self._all_results if c.jita_sell_value <= 0 and c.item_type_count > 0][:10]
        if zero_value_samples:
            report.append("\n[SAMPLE ZERO VALUE CONTRACTS]")
            for c in zero_value_samples:
                items_preview = ", ".join([i.item_name for i in c.items[:3]])
                report.append(f"  ID:{c.contract_id} | Items:{c.item_type_count} (Mem:{len(c.items)}) | Cost:{c.contract_cost:,.0f} | Reason:{c.filter_reason}")
                if items_preview:
                    report.append(f"    Sample Items: {items_preview}")

        # Buscar muestras rentables incluso si no están visibles
        if d.profitable > 0 and self.results_table.rowCount() == 0:
            report.append("\n[SAMPLES PROFITABLE (NOT VISIBLE)]")
            from core.contracts_engine import apply_contracts_filters
            profs = apply_contracts_filters(self._all_results, self.config)
            for c in profs[:5]:
                report.append(f"  ID:{c.contract_id} | Profit:{c.net_profit:,.0f} | ROI:{c.roi_pct:.1f}% | FilterReason:{c.filter_reason}")

        return "\n".join(report)

    def keyPressEvent(self, event):
        try:
            # Manejo de Copia (Ctrl+C)
            if event.matches(QKeySequence.StandardKey.Copy):
                if self.items_table.hasFocus():
                    self.copy_table_selection(self.items_table)
                    return
                if self.results_table.hasFocus():
                    self.copy_table_selection(self.results_table)
                    return
            
            # Manejo de Seleccionar Todo (Ctrl+A)
            elif event.matches(QKeySequence.StandardKey.SelectAll):
                if self.items_table.hasFocus():
                    self.items_table.selectAll()
                    return
                if self.results_table.hasFocus():
                    self.results_table.selectAll()
                    return
                    
        except Exception as e:
            logger.warning(f"[CONTRACTS] Error in keyPressEvent: {e}")
            
        super().keyPressEvent(event)

    def copy_table_selection(self, table):
        try:
            selection = table.selectedRanges()
            if not selection:
                # Si no hay rangos (pero quizás hay selección por celdas individuales en otros modos)
                # En QTableWidget con SelectRows/SingleSelection suele haber rangos.
                return
            
            rows_data_list = []
            
            # Recolectar todas las filas únicas involucradas en la selección
            # (El usuario puede seleccionar bloques no contiguos)
            all_selected_rows = set()
            for r in selection:
                for row in range(r.topRow(), r.bottomRow() + 1):
                    all_selected_rows.add(row)
            
            # Ordenar las filas para que el pegado sea coherente
            sorted_rows = sorted(list(all_selected_rows))
            
            for row in sorted_rows:
                row_cells = []
                # Copiamos todas las columnas visibles del widget
                for col in range(table.columnCount()):
                    it = table.item(row, col)
                    row_cells.append(it.text() if it else "")
                rows_data_list.append("\t".join(row_cells))
            
            if rows_data_list:
                text = "\n".join(rows_data_list)
                QGuiApplication.clipboard().setText(text)
                self.status_label.setText(f"Copiado: {len(rows_data_list)} filas al portapapeles")
                self.status_label.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 800;")
        except Exception as e:
            logger.error(f"[CONTRACTS] Error copying table selection: {e}")
            self.status_label.setText("Error al copiar")
            self.status_label.setStyleSheet("color: #ef4444; font-size: 9px;")

    def add_contract_row(self, c):
        row = self.results_table.rowCount()
        self.results_table.setSortingEnabled(False)
        self.results_table.insertRow(row)
        
        # Guardamos el objeto en la primera celda para recuperación rápida
        num_item = NumericTableWidgetItem(str(row + 1), row + 1)
        num_item.setData(Qt.UserRole, c)
        num_item.setForeground(QColor("#64748b"))
        
        items_item = NumericTableWidgetItem(str(c.item_type_count), c.item_type_count)
        
        cost_item = NumericTableWidgetItem(_format_isk(c.contract_cost), c.contract_cost)
        cost_item.setToolTip(_format_isk_full(c.contract_cost))
        
        sell_item = NumericTableWidgetItem(_format_isk(c.jita_sell_value), c.jita_sell_value)
        sell_item.setToolTip(_format_isk_full(c.jita_sell_value))
        
        buy_item = NumericTableWidgetItem(_format_isk(c.jita_buy_value), c.jita_buy_value)
        buy_item.setToolTip(_format_isk_full(c.jita_buy_value))
        
        profit_item = NumericTableWidgetItem(_format_isk(c.net_profit), c.net_profit)
        profit_item.setToolTip(_format_isk_full(c.net_profit))
        if c.net_profit > 0:
            profit_item.setForeground(QColor("#10b981")) # Verde
        elif c.net_profit < 0:
            profit_item.setForeground(QColor("#ef4444")) # Rojo
        else:
            profit_item.setForeground(QColor("#94a3b8")) # Gris
            
        roi_item = NumericTableWidgetItem(f"{c.roi_pct:.1f}%", c.roi_pct)
        if c.roi_pct >= 20: roi_item.setForeground(QColor("#10b981"))
        elif c.roi_pct < 0: roi_item.setForeground(QColor("#ef4444"))
        
        exp_item = QTableWidgetItem(_format_expiry(c.date_expired))
        
        score_item = NumericTableWidgetItem(f"{c.score:.1f}", c.score)
        if c.score >= 50: score_item.setForeground(QColor("#10b981"))
        
        self.results_table.setItem(row, 0, num_item)
        self.results_table.setItem(row, 1, items_item)
        self.results_table.setItem(row, 2, cost_item)
        self.results_table.setItem(row, 3, sell_item)
        self.results_table.setItem(row, 4, buy_item)
        self.results_table.setItem(row, 5, profit_item)
        self.results_table.setItem(row, 6, roi_item)
        self.results_table.setItem(row, 7, exp_item)
        self.results_table.setItem(row, 8, score_item)
        
        for col in range(9):
            it = self.results_table.item(row, col)
            if it: it.setTextAlignment(Qt.AlignCenter)
        
        self.results_table.setSortingEnabled(True)
        
        # Color coding de fila opcional
        if c.score > 70:
            for col in range(9):
                it = self.results_table.item(row, col)
                if it: it.setBackground(QColor("#0d2418"))
        elif c.score < 40:
            for col in range(9):
                it = self.results_table.item(row, col)
                if it: it.setBackground(QColor("#1a1505"))

    def apply_filters_locally(self):
        # Si no hay resultados, no borramos lo que había
        if not self._all_results:
            logger.info("[CONTRACTS] No results to filter locally.")
            return
            
        self._save_config()
        self.results_table.setRowCount(0)
        self._image_generation += 1
        
        from core.contracts_engine import apply_contracts_filters
        
        # Intentar diagnóstico, pero no bloquear si falla
        diag = None
        try:
            diag = ScanDiagnostics()
            # Copiar contadores de cache del último diagnóstico si existe (del worker)
            if self.last_diag:
                diag.contract_cache_hits = self.last_diag.contract_cache_hits
                diag.contract_cache_misses = self.last_diag.contract_cache_misses
            
            filtered = apply_contracts_filters(self._all_results, self.config, diag)
            self.last_diag = diag # Actualizar con el último filtrado local
            self._scan_events.append(f"filters_applied input={len(self._all_results)} output={len(filtered)}")
        except Exception as e:
            logger.error(f"[CONTRACTS] Error in local diagnostic/filter pass: {e}")
            self._scan_events.append(f"error_in_filtering: {e}")
            # Fallback: intentar filtrar sin diagnóstico si diag falló
            filtered = apply_contracts_filters(self._all_results, self.config)

        self._scan_events.append(f"table_rendered rows={len(filtered)}")
        
        if diag:
            logger.info(f"[CONTRACTS] Local filtering: in={len(self._all_results)}, out={len(filtered)}. Reasons: {diag.to_summary()}")
        
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

        # Mostrar diagnóstico en la barra de estado
        self.status_label.setText(f"Diagnóstico: {diag.to_summary()}")
        self.status_label.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 800;")
        self.status_label.setToolTip(
            f"Excluidos por:\n"
            f"- Profit bajo: {diag.excluded_by_low_profit}\n"
            f"- ROI bajo: {diag.excluded_by_low_roi}\n"
            f"- Sin precio: {diag.excluded_by_no_price}\n"
            f"- BP/BPC: {diag.excluded_by_blueprint}/{diag.excluded_by_bpc}\n"
            f"- Categoría: {diag.excluded_by_category}\n"
            f"- Complejidad: {diag.excluded_by_complexity}"
        )

    def on_scan_finished(self, results):
        logger.info(f"[CONTRACTS] Scan finished with {len(results)} results.")
        self._all_results = results
        self.last_diag = getattr(self.worker, 'diag', None)
        
        # Si el worker tiene diagnóstico, lo preservamos
        if self.last_diag:
            logger.info(f"[CONTRACTS] Preserving worker diag: {self.last_diag.to_summary()}")
        
        self.btn_scan.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.progress_widget.setVisible(False)
        self.insights_widget.setVisible(True)
        
        self._scan_events.append(f"scan_finished received results count={len(results)}")
        self.apply_filters_locally() # Re-render final ordenado

    def on_scan_error(self, msg):
        logger.error(f"[CONTRACTS] Scan error: {msg}")
        self.btn_scan.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.progress_widget.setVisible(False)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error de Escaneo", msg)

    def on_row_selected(self, row, col):
        item = self.results_table.item(row, 0)
        if not item: return
        c = item.data(Qt.UserRole)
        if c:
            if len(c.items) == 0 and c.item_type_count > 0:
                self.lazy_load_contract_details(c)
            else:
                self._last_details_source = "memory"
                self.populate_detail_panel(c)

    def lazy_load_contract_details(self, c):
        self.lbl_det_title.setText(f"BUSCANDO DETALLES DEL CONTRATO {c.contract_id}...")
        self.items_table.setRowCount(0)
        self._last_details_error = None
        
        try:
            from core.contracts_cache import ContractsCache
            cache = ContractsCache.instance()
            cached = cache.get_light_entry(c.contract_id)
            
            if cached and cached.get('items'):
                from core.contracts_models import ContractArbitrageResult
                rehydrated = ContractArbitrageResult.from_dict(cached)
                if rehydrated.items:
                    c.items = rehydrated.items
                    self._last_details_source = "cache"
                    self.populate_detail_panel(c)
                    return
            
            self._last_details_source = "missing"
            self._last_details_error = "Detalles no encontrados en cach. Por favor, re-escanea."
            self.lbl_det_title.setText(f"DETALLES NO DISPONIBLES PARA {c.contract_id}")
            self.lbl_det_risk.setText("<b>ERROR:</b> <span style='color:#ef4444;'>Los detalles de este contrato no estn en memoria ni en cach. Re-escanea para recuperarlos.</span>")
        except Exception as e:
            self._last_details_source = "error"
            self._last_details_error = str(e)
            logger.error(f"Error lazy loading details: {e}")

    def on_row_double_clicked(self, row, col):
        # Forzar obtención del objeto desde la columna 0 de la fila visual clicada
        item = self.results_table.item(row, 0)
        if not item: return
        c = item.data(Qt.UserRole)
        if c:
            self._current_contract_id = c.contract_id
            self._last_open_source = "double_click"
            logger.info(f"[CONTRACT OPEN] Double-click at row {row} -> ID {c.contract_id}")
            self.on_open_in_game_clicked()

    def populate_detail_panel(self, c):
        self._current_contract_id = c.contract_id
        
        # Guardar top item para poder abrir su mercado
        items = sorted(c.items, key=lambda x: getattr(x, 'line_sell_value', 0), reverse=True)
        self._current_main_item_id = items[0].type_id if items else 0
        
        self.lbl_det_title.setText(f"CONTRATO {c.contract_id} — SCORE: {c.score:.1f}")
        
        # Llenar métricas
        self.lbl_det_cost.setText(f"<b>COSTE:</b> <span style='color:#f1f5f9;'>{_format_isk_full(c.contract_cost)}</span>")
        self.lbl_det_sell.setText(f"<b>JITA SELL:</b> <span style='color:#f1f5f9;'>{_format_isk_full(c.jita_sell_value)}</span>")
        
        color_p = "#10b981" if c.net_profit > 0 else "#ef4444"
        self.lbl_det_profit.setText(f"<b>NET PROFIT:</b> <span style='color:{color_p};'>{_format_isk_full(c.net_profit)}</span>")
        
        color_r = "#10b981" if c.roi_pct >= 20 else ("#f59e0b" if c.roi_pct >= 10 else ("#ef4444" if c.roi_pct < 0 else "#f1f5f9"))
        self.lbl_det_roi.setText(f"<b>ROI:</b> <span style='color:{color_r};'>{c.roi_pct:.1f}%</span>")
        
        risk_msgs = []
        if c.filter_reason:
            risk_msgs.append(f"Criterio: {c.filter_reason}")
        if c.has_unresolved_items:
            risk_msgs.append(f"{c.unresolved_count} item(s) sin precio")
        if c.value_concentration > 0.80:
            risk_msgs.append(f"Alta concentración ({c.value_concentration*100:.0f}%)")
        if c.valuation_warning:
            risk_msgs.append(c.valuation_warning)
            
        if risk_msgs:
            self.lbl_det_risk.setText(f"<b>INFO:</b> <span style='color:#f59e0b;'>{' | '.join(risk_msgs)}</span>")
        else:
            self.lbl_det_risk.setText(f"<b>INFO:</b> <span style='color:#10b981;'>Ninguno</span>")
            
        self.detail_frame.setVisible(True)
        
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(items))
        self._image_generation += 1 
        gen = self._image_generation
        for r, item in enumerate(items):
            i_name = QTableWidgetItem(item.item_name)
            i_qty = QTableWidgetItem(f"{item.quantity:,}")
            i_qty.setTextAlignment(Qt.AlignCenter)
            
            if item.is_copy:
                i_name.setText(i_name.text() + " (COPIA BPC)")
                i_name.setForeground(QColor("#f59e0b"))
            elif not item.is_included:
                i_name.setText(i_name.text() + " (REQUERIDO)")
                i_name.setForeground(QColor("#ef4444"))
                
            price_txt = _format_isk(item.jita_sell_price) if item.jita_sell_price > 0 else "N/A"
            i_price = QTableWidgetItem(price_txt)
            i_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            val_txt = _format_isk(item.line_sell_value) if item.jita_sell_price > 0 else "N/A"
            i_val = QTableWidgetItem(val_txt)
            i_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            if item.valuation_status != "ok":
                i_price.setText("-")
                i_val.setText("-")
                i_val.setForeground(QColor("#64748b"))

            i_pct = QTableWidgetItem(f"{item.pct_of_total:.1f}%")
            i_pct.setTextAlignment(Qt.AlignCenter)
            
            if not item.is_included:
                for it in [i_price, i_val, i_pct]:
                    it.setText("-")
            
            pix = self.icon_service.get_icon(
                item.type_id, 24,
                lambda p, tid=item.type_id, row=r: self._load_icon_into_table_item(self.items_table, row, 0, tid, p, gen)
            )
            i_name.setIcon(QIcon(pix))

            self.items_table.setItem(r, 0, i_name)
            i_name.setData(Qt.UserRole, item.type_id)
            self.items_table.setItem(r, 1, i_qty)
            self.items_table.setItem(r, 2, i_price)
            self.items_table.setItem(r, 3, i_val)
            self.items_table.setItem(r, 4, i_pct)
            
            for col in range(5):
                it = self.items_table.item(r, col)
                if it: it.setTextAlignment(Qt.AlignCenter)

    def on_item_double_clicked(self, row, col):
        item_obj = self.items_table.item(row, 0)
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
        
        # Fallback: Si no hay un current_id (clic sin selección previa?), buscar en la tabla
        if not contract_id:
            sel_items = self.results_table.selectedItems()
            if sel_items:
                row = sel_items[0].row()
                it = self.results_table.item(row, 0)
                if it:
                    c = it.data(Qt.UserRole)
                    if c:
                        contract_id = c.contract_id
                        self._current_contract_id = contract_id

        if not contract_id or contract_id == 0:
            self.status_label.setText("● SELECCIONA UN CONTRATO PRIMERO")
            self.status_label.setStyleSheet("color: #f87171; font-size: 10px; font-weight: 800;")
            return
        
        # Tracking para diagnóstico
        self._last_open_attempt = contract_id
        if self._last_open_source != "double_click":
            self._last_open_source = "button"
            
        logger.info(f"[CONTRACT OPEN] Attempting source={self._last_open_source} contract_id={contract_id}")
        
        def feedback(msg, color):
            # Reconocemos éxito por el color verde del helper
            success = (color == "#34d399")
            self._last_open_success = success
            self._last_open_error = msg if not success else ""
            
            self.status_label.setText(f"● {msg.upper()}")
            self.status_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 800;")
            
            if success:
                logger.info(f"[CONTRACT OPEN SUCCESS] contract_id={contract_id}")
            else:
                logger.warning(f"[CONTRACT OPEN ERROR] contract_id={contract_id} msg={msg}")

        ItemInteractionHelper.open_contract_in_game(ESIClient(), contract_id, feedback)
        # Reset source para el siguiente
        self._last_open_source = "none"

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

    def _load_icon_into_table_item(self, table, row, col, type_id, pixmap, generation):
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
