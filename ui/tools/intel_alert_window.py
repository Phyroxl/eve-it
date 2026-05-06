"""Intel Alert — ventana de configuración y alertas de hostiles en EVE."""
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QCheckBox,
    QFrame, QScrollArea, QComboBox, QSpinBox, QSizePolicy,
    QFileDialog, QStackedWidget, QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor

from ui.common.custom_titlebar import CustomTitleBar, apply_salva_close_btn_style, apply_salva_min_btn_style
from core.intel_alert_service import (
    IntelAlertService, IntelAlertConfig, IntelEvent, discover_chat_channels,
)

logger = logging.getLogger('eve.intel')

# ── Shared styles ─────────────────────────────────────────────────────────────
_BTN = ("QPushButton{background:#0f172a;border:1px solid #1e293b;"
        "color:#94a3b8;font-size:11px;padding:3px 8px;}"
        "QPushButton:hover{background:#1e293b;color:#e2e8f0;}"
        "QPushButton:disabled{color:#334155;}")
_BTN_GREEN = ("QPushButton{background:#052e16;border:1px solid #16a34a;"
              "color:#4ade80;font-size:11px;font-weight:bold;padding:3px 8px;}"
              "QPushButton:hover{background:#14532d;}")
_BTN_RED = ("QPushButton{background:#1a0000;border:1px solid #7f1d1d;"
            "color:#f87171;font-size:11px;font-weight:bold;padding:3px 8px;}"
            "QPushButton:hover{background:#450a0a;}")
_BTN_CYAN = ("QPushButton{background:#0c1a2e;border:1px solid #0891b2;"
             "color:#38bdf8;font-size:11px;padding:3px 8px;}"
             "QPushButton:hover{background:#0e2440;}")
_INPUT = ("background:#060d18;border:1px solid #1e293b;"
          "color:#e2e8f0;padding:3px;font-size:11px;")
_SECTION = "color:#64748b;font-size:10px;font-weight:bold;margin-top:4px;"
_LIST_STYLE = ("QListWidget{background:#060d18;border:1px solid #1e293b;"
               "color:#94a3b8;font-size:11px;}"
               "QListWidget::item:selected{background:#1e293b;color:#e2e8f0;}")
_CHK = "QCheckBox{color:#94a3b8;font-size:11px;}"
_COMBO = ("QComboBox{background:#060d18;border:1px solid #1e293b;color:#e2e8f0;"
          "font-size:11px;padding:2px 6px;}"
          "QComboBox::drop-down{border:none;}"
          "QComboBox QAbstractItemView{background:#0d1626;border:1px solid #1e293b;"
          "color:#e2e8f0;selection-background-color:#1e293b;}")
_SPIN = ("QSpinBox{background:#060d18;border:1px solid #1e293b;color:#e2e8f0;"
         "font-size:11px;padding:2px;}"
         "QSpinBox::up-button,QSpinBox::down-button{background:#0f172a;border:1px solid #1e293b;}")

_COL_LOCAL = "#22c55e"
_COL_WATCH = "#f59e0b"
_COL_INTEL = "#38bdf8"
_COL_UNKNOWN = "#94a3b8"


class IntelAlertWindow(QWidget):
    """Frameless Intel Alert window — detection of hostiles in EVE chatlogs."""

    _event_signal = Signal(object)    # IntelEvent, cross-thread
    _discover_done = Signal(list)     # list[str] channel names — cross-thread safe

    def __init__(self, parent=None, controller=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self._ctrl = controller
        self._config = IntelAlertConfig.load()
        self._service: Optional[IntelAlertService] = None
        self._active = False
        self._event_history = []
        self._compact_mode = False

        self._setup_ui()
        self._load_config_to_ui()

        self._event_signal.connect(self._on_event_ui)
        self._discover_done.connect(self._on_discovered)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet("QWidget{background:#060d18;color:#94a3b8;font-size:11px;}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Titlebar ──────────────────────────────────────────────────────
        self._tb = CustomTitleBar("⚠  INTEL ALERT", self)
        self._tb.btn_close.clicked.disconnect()
        self._tb.btn_close.clicked.connect(self._on_close)
        self._tb.btn_min.clicked.disconnect()
        self._tb.btn_min.clicked.connect(self.hide)
        # Compact toggle button on titlebar
        self._btn_compact_toggle = QPushButton("▣")
        self._btn_compact_toggle.setFixedSize(24, 24)
        self._btn_compact_toggle.setToolTip("Modo compacto")
        self._btn_compact_toggle.setStyleSheet(_BTN)
        self._btn_compact_toggle.clicked.connect(self._toggle_compact)
        self._tb.layout().insertWidget(self._tb.layout().count() - 2, self._btn_compact_toggle)
        root.addWidget(self._tb)

        # ── Stacked: compact (0) / full (1) ───────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_compact_panel())
        self._stack.addWidget(self._build_full_panel())
        self._stack.setCurrentIndex(1)
        root.addWidget(self._stack, 1)

    def _build_compact_panel(self) -> QWidget:
        """200×80 panel: ON/OFF + status — máximo compacto."""
        panel = QWidget()
        panel.setFixedSize(200, 80)
        panel.setStyleSheet("QWidget{background:#060d18;}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        self._btn_toggle_compact = QPushButton("▶  ACTIVAR")
        self._btn_toggle_compact.setStyleSheet(_BTN_GREEN)
        self._btn_toggle_compact.setFixedHeight(32)
        self._btn_toggle_compact.clicked.connect(self._toggle_service)
        lay.addWidget(self._btn_toggle_compact)

        self._lbl_status_compact = QLabel("● Inactivo")
        self._lbl_status_compact.setStyleSheet("color:#475569;font-size:10px;")
        self._lbl_status_compact.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._lbl_status_compact)

        return panel

    def _build_full_panel(self) -> QWidget:
        """Full configuration + history panel."""
        panel = QWidget()
        panel.setMinimumSize(700, 580)

        body = QHBoxLayout(panel)
        body.setContentsMargins(10, 8, 10, 8)
        body.setSpacing(10)

        body.addWidget(self._build_left_panel(), 0)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#1e293b;")
        body.addWidget(sep)

        body.addWidget(self._build_right_panel(), 1)

        return panel

    def _build_left_panel(self) -> QWidget:
        """Scrollable config column (fixed 290px)."""
        wrapper = QWidget()
        wrapper.setFixedWidth(290)
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        # Activate row
        act_row = QHBoxLayout()
        self._btn_toggle = QPushButton("▶  ACTIVAR")
        self._btn_toggle.setStyleSheet(_BTN_GREEN)
        self._btn_toggle.clicked.connect(self._toggle_service)
        self._lbl_status = QLabel("● Inactivo")
        self._lbl_status.setStyleSheet("color:#475569;font-size:10px;")
        act_row.addWidget(self._btn_toggle)
        act_row.addStretch()
        act_row.addWidget(self._lbl_status)
        wl.addLayout(act_row)
        wl.addSpacing(6)

        # Scroll area for config
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollBar:vertical{width:4px;background:#060d18;}"
                             "QScrollBar::handle:vertical{background:#1e293b;}")

        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 4, 0)
        iv.setSpacing(4)

        # ── Source mode ───────────────────────────────────────────────────
        iv.addWidget(QLabel("Fuente de monitoreo:", styleSheet=_SECTION))
        self._combo_source = QComboBox()
        self._combo_source.setStyleSheet(_COMBO)
        self._combo_source.addItems(["Local", "Intel", "Ambos"])
        self._combo_source.currentIndexChanged.connect(self._on_source_changed)
        iv.addWidget(self._combo_source)

        # Intel channels section (shown/hidden by source mode)
        self._intel_ch_frame = QWidget()
        ich_v = QVBoxLayout(self._intel_ch_frame)
        ich_v.setContentsMargins(0, 0, 0, 0)
        ich_v.setSpacing(3)

        ich_header = QHBoxLayout()
        ich_header.addWidget(QLabel("Canales Intel:", styleSheet=_SECTION))
        ich_header.addStretch()
        self._btn_discover = QPushButton("⟳ Descubrir")
        self._btn_discover.setFixedHeight(18)
        self._btn_discover.setStyleSheet(_BTN_CYAN)
        self._btn_discover.clicked.connect(self._discover_channels)
        ich_header.addWidget(self._btn_discover)
        ich_v.addLayout(ich_header)

        self._list_intel_ch = QListWidget()
        self._list_intel_ch.setFixedHeight(64)
        self._list_intel_ch.setStyleSheet(_LIST_STYLE)
        ich_v.addWidget(self._list_intel_ch)

        # Discovered channels chooser
        self._combo_discovered = QComboBox()
        self._combo_discovered.setStyleSheet(_COMBO)
        self._combo_discovered.addItem("— canales detectados —")
        self._combo_discovered.currentIndexChanged.connect(self._on_discovered_selected)
        ich_v.addWidget(self._combo_discovered)

        ich_row = QHBoxLayout()
        self._edit_intel_ch = QLineEdit()
        self._edit_intel_ch.setPlaceholderText("Nombre manual…")
        self._edit_intel_ch.setStyleSheet(_INPUT)
        btn_add_ich = QPushButton("+")
        btn_add_ich.setFixedWidth(24)
        btn_add_ich.setStyleSheet(_BTN)
        btn_add_ich.clicked.connect(self._add_intel_channel)
        btn_del_ich = QPushButton("−")
        btn_del_ich.setFixedWidth(24)
        btn_del_ich.setStyleSheet(_BTN)
        btn_del_ich.clicked.connect(lambda: self._del_selected(self._list_intel_ch))
        ich_row.addWidget(self._edit_intel_ch)
        ich_row.addWidget(btn_add_ich)
        ich_row.addWidget(btn_del_ich)
        ich_v.addLayout(ich_row)

        self._lbl_intel_hint = QLabel("Sin canales: detecta ficheros con 'intel'.")
        self._lbl_intel_hint.setStyleSheet("color:#475569;font-size:9px;")
        self._lbl_intel_hint.setWordWrap(True)
        ich_v.addWidget(self._lbl_intel_hint)
        iv.addWidget(self._intel_ch_frame)
        self._intel_ch_frame.setVisible(False)

        iv.addWidget(self._hline())

        # ── Sistema / Distancia ───────────────────────────────────────────
        iv.addWidget(QLabel("Distancia:", styleSheet=_SECTION))
        sys_row = QHBoxLayout()
        sys_row.addWidget(QLabel("Sistema actual:"))
        self._edit_system = QLineEdit()
        self._edit_system.setPlaceholderText("Ej: 1DQ1-A")
        self._edit_system.setStyleSheet(_INPUT)
        sys_row.addWidget(self._edit_system, 1)
        iv.addLayout(sys_row)

        jumps_row = QHBoxLayout()
        jumps_row.addWidget(QLabel("Rango (saltos):"))
        self._spin_jumps = QSpinBox()
        self._spin_jumps.setRange(0, 10)
        self._spin_jumps.setValue(5)
        self._spin_jumps.setStyleSheet(_SPIN)
        self._spin_jumps.setFixedWidth(52)
        jumps_row.addWidget(self._spin_jumps)
        jumps_row.addStretch()
        iv.addLayout(jumps_row)

        self._chk_unknown_dist = QCheckBox("Alertar si distancia desconocida")
        self._chk_unknown_dist.setStyleSheet(_CHK)
        iv.addWidget(self._chk_unknown_dist)

        lbl_map = QLabel("⚠ Sin SDE/mapa. distance_jumps → None.\n"
                         "Las alertas de distancia dependen del checkbox.")
        lbl_map.setStyleSheet("color:#475569;font-size:9px;")
        lbl_map.setWordWrap(True)
        iv.addWidget(lbl_map)

        iv.addWidget(self._hline())

        # ── Safe names ────────────────────────────────────────────────────
        iv.addWidget(QLabel("Lista segura (nunca alertan):", styleSheet=_SECTION))
        self._list_safe = QListWidget()
        self._list_safe.setFixedHeight(52)
        self._list_safe.setStyleSheet(_LIST_STYLE)
        iv.addWidget(self._list_safe)
        safe_row = QHBoxLayout()
        self._edit_safe = QLineEdit()
        self._edit_safe.setPlaceholderText("Nombre de piloto…")
        self._edit_safe.setStyleSheet(_INPUT)
        btn_add_safe = QPushButton("+")
        btn_add_safe.setFixedWidth(24)
        btn_add_safe.setStyleSheet(_BTN)
        btn_add_safe.clicked.connect(self._add_safe)
        btn_del_safe = QPushButton("−")
        btn_del_safe.setFixedWidth(24)
        btn_del_safe.setStyleSheet(_BTN)
        btn_del_safe.clicked.connect(lambda: self._del_selected(self._list_safe))
        safe_row.addWidget(self._edit_safe)
        safe_row.addWidget(btn_add_safe)
        safe_row.addWidget(btn_del_safe)
        iv.addLayout(safe_row)

        iv.addWidget(self._hline())

        # ── Watch names ───────────────────────────────────────────────────
        iv.addWidget(QLabel("Lista vigilancia (alerta siempre):", styleSheet=_SECTION))
        self._list_watch = QListWidget()
        self._list_watch.setFixedHeight(52)
        self._list_watch.setStyleSheet(_LIST_STYLE)
        iv.addWidget(self._list_watch)
        watch_row = QHBoxLayout()
        self._edit_watch = QLineEdit()
        self._edit_watch.setPlaceholderText("Nombre de piloto…")
        self._edit_watch.setStyleSheet(_INPUT)
        btn_add_watch = QPushButton("+")
        btn_add_watch.setFixedWidth(24)
        btn_add_watch.setStyleSheet(_BTN)
        btn_add_watch.clicked.connect(self._add_watch)
        btn_del_watch = QPushButton("−")
        btn_del_watch.setFixedWidth(24)
        btn_del_watch.setStyleSheet(_BTN)
        btn_del_watch.clicked.connect(lambda: self._del_selected(self._list_watch))
        watch_row.addWidget(self._edit_watch)
        watch_row.addWidget(btn_add_watch)
        watch_row.addWidget(btn_del_watch)
        iv.addLayout(watch_row)

        iv.addWidget(self._hline())

        # ── Toggles ───────────────────────────────────────────────────────
        self._chk_alert_unknown = QCheckBox("Alertar neutrales / desconocidos")
        self._chk_alert_unknown.setStyleSheet(_CHK)
        iv.addWidget(self._chk_alert_unknown)

        self._chk_alert_watch = QCheckBox("Alertar lista vigilancia")
        self._chk_alert_watch.setStyleSheet(_CHK)
        iv.addWidget(self._chk_alert_watch)

        iv.addWidget(QLabel("Filtro standing (ESI):", styleSheet=_SECTION))
        self._chk_ignore_corp = QCheckBox("Ignorar miembros de mi corp")
        self._chk_ignore_corp.setStyleSheet(_CHK)
        iv.addWidget(self._chk_ignore_corp)

        self._chk_ignore_good_standing = QCheckBox("Ignorar buen standing")
        self._chk_ignore_good_standing.setStyleSheet(_CHK)
        iv.addWidget(self._chk_ignore_good_standing)

        self._chk_alert_bad_standing = QCheckBox("Alertar mal standing")
        self._chk_alert_bad_standing.setStyleSheet(_CHK)
        iv.addWidget(self._chk_alert_bad_standing)

        self._lbl_esi_status = QLabel("⚠ ESI standing no disponible — listas manuales activas")
        self._lbl_esi_status.setStyleSheet("color:#475569;font-size:9px;")
        self._lbl_esi_status.setWordWrap(True)
        iv.addWidget(self._lbl_esi_status)

        iv.addWidget(self._hline())

        # ── Sound selector ────────────────────────────────────────────────
        iv.addWidget(QLabel("Sonido de alerta:", styleSheet=_SECTION))
        snd_row = QHBoxLayout()
        self._combo_sound = QComboBox()
        self._combo_sound.setStyleSheet(_COMBO)
        self._combo_sound.addItems(["Pitido sistema", "Silencio", "Archivo WAV…"])
        self._combo_sound.currentIndexChanged.connect(self._on_sound_mode_changed)
        snd_row.addWidget(self._combo_sound, 1)
        self._btn_test_sound = QPushButton("▶")
        self._btn_test_sound.setFixedWidth(26)
        self._btn_test_sound.setStyleSheet(_BTN)
        self._btn_test_sound.setToolTip("Probar sonido")
        self._btn_test_sound.clicked.connect(self._test_sound)
        snd_row.addWidget(self._btn_test_sound)
        iv.addLayout(snd_row)

        wav_row = QHBoxLayout()
        self._edit_wav_path = QLineEdit()
        self._edit_wav_path.setPlaceholderText("Ruta .wav o .mp3…")
        self._edit_wav_path.setStyleSheet(_INPUT)
        self._edit_wav_path.setReadOnly(True)
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(26)
        btn_browse.setStyleSheet(_BTN)
        btn_browse.clicked.connect(self._browse_wav)
        wav_row.addWidget(self._edit_wav_path)
        wav_row.addWidget(btn_browse)
        self._wav_row_widget = QWidget()
        self._wav_row_widget.setLayout(wav_row)
        self._wav_row_widget.setVisible(False)
        iv.addWidget(self._wav_row_widget)

        iv.addWidget(self._hline())

        # ── Cooldown ──────────────────────────────────────────────────────
        cd_row = QHBoxLayout()
        cd_row.addWidget(QLabel("Cooldown (s):"))
        self._edit_cooldown = QLineEdit("120")
        self._edit_cooldown.setFixedWidth(50)
        self._edit_cooldown.setStyleSheet(_INPUT)
        cd_row.addWidget(self._edit_cooldown)
        cd_row.addStretch()
        iv.addLayout(cd_row)

        iv.addWidget(self._hline())

        # ── Bottom buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_save = QPushButton("💾 Guardar")
        btn_save.setStyleSheet(_BTN)
        btn_save.clicked.connect(self._save)
        btn_reset = QPushButton("🔄 Reset")
        btn_reset.setStyleSheet(_BTN)
        btn_reset.clicked.connect(self._reset_session)
        btn_diag = QPushButton("📋 Diagnóstico")
        btn_diag.setStyleSheet(_BTN)
        btn_diag.clicked.connect(self._show_diagnostics)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_diag)
        iv.addLayout(btn_row)

        iv.addStretch()
        scroll.setWidget(inner)
        wl.addWidget(scroll, 1)
        return wrapper

    def _build_right_panel(self) -> QWidget:
        """History + diagnostics panel (stretch)."""
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Historial de alertas:", styleSheet=_SECTION))
        hdr.addStretch()
        btn_clr = QPushButton("Limpiar")
        btn_clr.setFixedWidth(58)
        btn_clr.setStyleSheet(_BTN)
        btn_clr.clicked.connect(self._clear_history)
        hdr.addWidget(btn_clr)
        rv.addLayout(hdr)

        self._list_history = QListWidget()
        self._list_history.setStyleSheet(_LIST_STYLE)
        self._list_history.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rv.addWidget(self._list_history, 1)

        legend = QHBoxLayout()
        legend.setSpacing(10)
        for col, lbl in [(_COL_LOCAL, "Local"), (_COL_WATCH, "Vigilancia"), (_COL_INTEL, "Intel")]:
            dot = QLabel(f"● {lbl}")
            dot.setStyleSheet(f"color:{col};font-size:10px;")
            legend.addWidget(dot)
        legend.addStretch()
        rv.addLayout(legend)

        # ── Diagnostics mini-panel ────────────────────────────────────────
        rv.addWidget(self._hline())
        diag_hdr = QHBoxLayout()
        diag_hdr.addWidget(QLabel("Diagnóstico:", styleSheet=_SECTION))
        diag_hdr.addStretch()
        self._btn_copy_diag = QPushButton("Copiar")
        self._btn_copy_diag.setFixedWidth(50)
        self._btn_copy_diag.setStyleSheet(_BTN)
        self._btn_copy_diag.clicked.connect(self._copy_diagnostics)
        diag_hdr.addWidget(self._btn_copy_diag)
        rv.addLayout(diag_hdr)

        self._lbl_diag_files = QLabel("Archivos vigilados: —")
        self._lbl_diag_files.setStyleSheet("color:#475569;font-size:10px;")
        rv.addWidget(self._lbl_diag_files)

        self._lbl_diag_last_msg = QLabel("Último mensaje: —")
        self._lbl_diag_last_msg.setStyleSheet("color:#475569;font-size:10px;")
        self._lbl_diag_last_msg.setWordWrap(True)
        rv.addWidget(self._lbl_diag_last_msg)

        self._lbl_diag_last_alert = QLabel("Última alerta: —")
        self._lbl_diag_last_alert.setStyleSheet("color:#475569;font-size:10px;")
        rv.addWidget(self._lbl_diag_last_alert)

        self._diag_timer = QTimer(self)
        self._diag_timer.timeout.connect(self._refresh_diagnostics_ui)
        self._diag_timer.start(3000)

        return right

    @staticmethod
    def _hline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color:#1e293b;margin:2px 0;")
        return f

    # ── Compact mode ──────────────────────────────────────────────────────────

    def _toggle_compact(self):
        self._compact_mode = not self._compact_mode
        if self._compact_mode:
            self._stack.setCurrentIndex(0)
            self.setMinimumSize(200, 80)
            self.setMaximumSize(200, 80)
            self.resize(200, 80)
        else:
            self.setMinimumSize(700, 580)
            self.setMaximumSize(16777215, 16777215)
            self.resize(780, 620)
            self._stack.setCurrentIndex(1)
        self._btn_compact_toggle.setText("□" if self._compact_mode else "▣")

    # ── Config I/O ────────────────────────────────────────────────────────────

    def _load_config_to_ui(self):
        mode_map = {"local": 0, "intel": 1, "both": 2}
        self._combo_source.setCurrentIndex(mode_map.get(self._config.source_mode, 0))
        self._on_source_changed(self._combo_source.currentIndex())

        self._list_intel_ch.clear()
        for ch in self._config.intel_channels:
            self._list_intel_ch.addItem(ch)

        self._edit_system.setText(self._config.current_system)
        self._spin_jumps.setValue(self._config.max_jumps)
        self._chk_unknown_dist.setChecked(self._config.alert_unknown_distance)

        self._list_safe.clear()
        for n in self._config.safe_names:
            self._list_safe.addItem(n)
        self._list_watch.clear()
        for n in self._config.watch_names:
            self._list_watch.addItem(n)

        self._chk_alert_unknown.setChecked(self._config.alert_on_unknown)
        self._chk_alert_watch.setChecked(self._config.alert_on_watchlist)
        self._chk_ignore_corp.setChecked(getattr(self._config, 'ignore_corp_members', True))
        self._chk_ignore_good_standing.setChecked(getattr(self._config, 'ignore_good_standing', True))
        self._chk_alert_bad_standing.setChecked(getattr(self._config, 'alert_bad_standing', True))
        self._edit_cooldown.setText(str(self._config.pilot_cooldown_secs))

        # Sound mode
        sound_idx = {"beep": 0, "silent": 1, "wav": 2}.get(self._config.alert_sound_mode, 0)
        self._combo_sound.setCurrentIndex(sound_idx)
        self._edit_wav_path.setText(self._config.alert_sound_path or "")
        self._wav_row_widget.setVisible(sound_idx == 2)

    def _collect_config_from_ui(self):
        modes = ["local", "intel", "both"]
        self._config.source_mode = modes[self._combo_source.currentIndex()]
        self._config.intel_channels = [
            self._list_intel_ch.item(i).text()
            for i in range(self._list_intel_ch.count())
        ]
        self._config.current_system = self._edit_system.text().strip()
        self._config.max_jumps = self._spin_jumps.value()
        self._config.alert_unknown_distance = self._chk_unknown_dist.isChecked()
        self._config.safe_names = [
            self._list_safe.item(i).text() for i in range(self._list_safe.count())
        ]
        self._config.watch_names = [
            self._list_watch.item(i).text() for i in range(self._list_watch.count())
        ]
        self._config.alert_on_unknown = self._chk_alert_unknown.isChecked()
        self._config.alert_on_watchlist = self._chk_alert_watch.isChecked()
        self._config.ignore_corp_members = self._chk_ignore_corp.isChecked()
        self._config.ignore_good_standing = self._chk_ignore_good_standing.isChecked()
        self._config.alert_bad_standing = self._chk_alert_bad_standing.isChecked()
        sound_modes = ["beep", "silent", "wav"]
        self._config.alert_sound_mode = sound_modes[self._combo_sound.currentIndex()]
        self._config.alert_sound = self._config.alert_sound_mode != "silent"
        self._config.alert_sound_path = self._edit_wav_path.text().strip()
        try:
            self._config.pilot_cooldown_secs = max(5, int(self._edit_cooldown.text()))
        except ValueError:
            pass

    def _save(self):
        self._collect_config_from_ui()
        self._config.save()
        if self._service:
            self._service.update_config(self._config)
        self._lbl_status.setText("● Guardado")
        QTimer.singleShot(2000, self._refresh_status)

    # ── List management ───────────────────────────────────────────────────────

    def _on_source_changed(self, idx: int):
        show_intel = idx != 0  # 0 = Local
        self._intel_ch_frame.setVisible(show_intel)

    def _add_intel_channel(self):
        name = self._edit_intel_ch.text().strip()
        if name and not self._list_has(self._list_intel_ch, name):
            self._list_intel_ch.addItem(name)
        self._edit_intel_ch.clear()

    def _add_safe(self):
        name = self._edit_safe.text().strip()
        if name and not self._list_has(self._list_safe, name):
            self._list_safe.addItem(name)
        self._edit_safe.clear()

    def _add_watch(self):
        name = self._edit_watch.text().strip()
        if name and not self._list_has(self._list_watch, name):
            self._list_watch.addItem(name)
        self._edit_watch.clear()

    def _del_selected(self, lst: QListWidget):
        for item in lst.selectedItems():
            lst.takeItem(lst.row(item))

    @staticmethod
    def _list_has(lst: QListWidget, name: str) -> bool:
        return any(lst.item(i).text().lower() == name.lower() for i in range(lst.count()))

    # ── Channel discovery ─────────────────────────────────────────────────────

    def _discover_channels(self):
        """Escanea chatlogs en background y devuelve canales via Signal (thread-safe)."""
        self._btn_discover.setEnabled(False)
        self._btn_discover.setText("Buscando…")

        def _do():
            try:
                channels = discover_chat_channels(max_age_hours=72)
                logger.debug(f"discover_channels found: {channels}")
            except Exception as e:
                logger.debug(f"discover_channels error: {e}")
                channels = []
            # Signal.emit() es thread-safe — entrega en el hilo principal
            self._discover_done.emit(channels)

        import threading
        threading.Thread(target=_do, daemon=True, name='intel_discover').start()

    def _on_discovered(self, channels):
        self._btn_discover.setEnabled(True)
        self._btn_discover.setText("⟳ Descubrir")
        self._combo_discovered.clear()
        if channels:
            self._combo_discovered.addItem("— seleccionar canal —")
            for ch in channels:
                self._combo_discovered.addItem(ch)
        else:
            self._combo_discovered.addItem("— sin canales encontrados —")

    def _on_discovered_selected(self, idx: int):
        if idx <= 0:
            return
        name = self._combo_discovered.currentText()
        if name and not name.startswith("—") and not self._list_has(self._list_intel_ch, name):
            self._list_intel_ch.addItem(name)
        self._combo_discovered.setCurrentIndex(0)

    # ── Sound ─────────────────────────────────────────────────────────────────

    def _on_sound_mode_changed(self, idx: int):
        self._wav_row_widget.setVisible(idx == 2)

    def _browse_wav(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de audio", "",
            "Audio (*.wav *.mp3);;WAV (*.wav);;MP3 (*.mp3)"
        )
        if path:
            self._edit_wav_path.setText(path)

    def _test_sound(self):
        mode = ["beep", "silent", "wav"][self._combo_sound.currentIndex()]
        if mode == "silent":
            return
        if mode == "wav":
            path = self._edit_wav_path.text().strip()
            if path:
                self._play_audio_file(path)
                return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            try:
                QApplication.beep()
            except Exception:
                pass

    def _play_audio_file(self, path: str):
        """Reproduce WAV o MP3. Para WAV usa winsound; para MP3 usa QMediaPlayer."""
        import os
        if not os.path.isfile(path):
            logger.debug(f"SOUND file not found: {path}")
            return
        lower = path.lower()
        if lower.endswith('.wav'):
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
            except Exception as e:
                logger.debug(f"SOUND winsound error: {e}")
        # MP3 o fallback WAV via QMediaPlayer
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl
            if not hasattr(self, '_media_player'):
                self._media_player = QMediaPlayer(self)
                self._audio_output = QAudioOutput(self)
                self._media_player.setAudioOutput(self._audio_output)
            self._media_player.setSource(QUrl.fromLocalFile(path))
            self._media_player.play()
        except Exception as e:
            logger.debug(f"SOUND QMediaPlayer error: {e} — fallback beep")
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

    # ── Service control ───────────────────────────────────────────────────────

    def _toggle_service(self):
        if not self._active:
            self._collect_config_from_ui()
            self._config.enabled = True
            if self._service:
                self._service.stop()
            self._service = IntelAlertService(self._config, self._on_event_thread)
            self._service.start()
            self._active = True
            for btn in (self._btn_toggle, self._btn_toggle_compact):
                btn.setText("⏹  DETENER")
                btn.setStyleSheet(_BTN_RED)
        else:
            if self._service:
                self._service.stop()
                self._service = None
            self._active = False
            for btn in (self._btn_toggle, self._btn_toggle_compact):
                btn.setText("▶  ACTIVAR")
                btn.setStyleSheet(_BTN_GREEN)
        self._refresh_status()

    def _reset_session(self):
        if self._service:
            self._service.reset_session()
        self._lbl_status.setText("● Sesión reiniciada")
        QTimer.singleShot(2000, self._refresh_status)

    def _refresh_status(self):
        if self._active:
            mode = self._config.source_mode.capitalize()
            text = f"● Activo ({mode})"
            style = "color:#4ade80;font-size:10px;"
        else:
            text = "● Inactivo"
            style = "color:#475569;font-size:10px;"
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(style)
        self._lbl_status_compact.setText(text)
        self._lbl_status_compact.setStyleSheet(style.replace("10px", "11px"))

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def _refresh_diagnostics_ui(self):
        if not self._service:
            return
        d = self._service.get_diagnostics()
        self._lbl_diag_files.setText(f"Archivos vigilados: {d['files_watched']}")
        if d['last_message']:
            self._lbl_diag_last_msg.setText(f"Último msg ({d['last_message_ago']}): {d['last_message'][:60]}")
        if d['last_alert']:
            self._lbl_diag_last_alert.setText(f"Última alerta ({d['last_alert_ago']}): {d['last_alert']}")

    def _show_diagnostics(self):
        if not self._service:
            self._lbl_status.setText("● Servicio inactivo")
            return
        d = self._service.get_diagnostics()
        lines = [
            f"Archivos vigilados: {d['files_watched']}",
            f"Último archivo: {d['last_file']}",
            f"Último mensaje ({d['last_message_ago']}): {d['last_message']}",
            f"Última alerta ({d['last_alert_ago']}): {d['last_alert']}",
            f"Total alertas sesión: {d['total_alerts']}",
            f"Modo fuente: {d['source_mode']}",
            f"Canales Intel: {', '.join(d['intel_channels']) or 'ninguno'}",
            f"Keywords: {', '.join(d['keywords'][:8])}…",
        ]
        self._list_history.insertItem(0, QListWidgetItem("── Diagnóstico ──────────────────────────────────"))
        for line in reversed(lines):
            item = QListWidgetItem(line)
            item.setForeground(QColor("#475569"))
            self._list_history.insertItem(1, item)

    def _copy_diagnostics(self):
        if not self._service:
            return
        d = self._service.get_diagnostics()
        text = "\n".join(f"{k}: {v}" for k, v in d.items())
        QApplication.clipboard().setText(text)
        self._btn_copy_diag.setText("✓")
        QTimer.singleShot(1500, lambda: self._btn_copy_diag.setText("Copiar"))

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_event_thread(self, event: IntelEvent):
        self._event_signal.emit(event)

    def _on_event_ui(self, event: IntelEvent):
        self._event_history.append(event)
        if len(self._event_history) > 200:
            self._event_history.pop(0)

        color = {
            'watchlist': _COL_WATCH,
            'intel': _COL_INTEL,
            'unknown': _COL_LOCAL,
        }.get(event.classification, _COL_UNKNOWN)

        tag = {
            'watchlist': '⚡WATCH',
            'unknown':   'LOCAL',
            'intel':     '📡INTEL',
        }.get(event.classification, '?')

        src = event.source.upper()
        ts = event.timestamp[-8:] if len(event.timestamp) >= 8 else event.timestamp
        sys_part = f" [{event.system}]" if event.system else ""
        jmp_part = ""
        if event.jumps is not None:
            jmp_part = f" {event.jumps}j"
        elif event.system:
            jmp_part = " ?j"

        text = f"[{ts}] [{src}/{tag}]{sys_part}{jmp_part} {event.pilot} — {event.message[:50]}"

        item = QListWidgetItem(text)
        item.setForeground(QColor(color))
        self._list_history.insertItem(0, item)
        if self._list_history.count() > 200:
            self._list_history.takeItem(self._list_history.count() - 1)

    def _clear_history(self):
        self._list_history.clear()
        self._event_history.clear()

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        try:
            from ui.common.window_shape import force_square_corners
            force_square_corners(int(self.winId()))
        except Exception:
            pass

    def _on_close(self):
        if self._service:
            self._service.stop()
            self._service = None
        self.hide()

    def closeEvent(self, e):
        e.ignore()
        self._on_close()
