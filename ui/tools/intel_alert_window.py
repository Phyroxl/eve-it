"""Intel Alert — ventana de configuración y alertas de hostiles en EVE."""
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QCheckBox,
    QFrame, QScrollArea, QComboBox, QSpinBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor

from ui.common.custom_titlebar import CustomTitleBar, apply_salva_close_btn_style, apply_salva_min_btn_style
from core.intel_alert_service import IntelAlertService, IntelAlertConfig, IntelEvent

logger = logging.getLogger('eve.intel')

# ── Shared styles (minimal — lean on CustomTitleBar for titlebar) ─────────────
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

    _event_signal = Signal(object)   # IntelEvent, cross-thread

    def __init__(self, parent=None, controller=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self._ctrl = controller
        self._config = IntelAlertConfig.load()
        self._service: Optional[IntelAlertService] = None
        self._active = False
        self._event_history = []

        self._setup_ui()
        self._load_config_to_ui()

        self._event_signal.connect(self._on_event_ui)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setMinimumSize(700, 600)
        self.setStyleSheet("QWidget{background:#060d18;color:#94a3b8;font-size:11px;}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Titlebar (shared component) ───────────────────────────────────
        self._tb = CustomTitleBar("⚠  INTEL ALERT", self)
        # Override close: hide instead of destroy
        self._tb.btn_close.clicked.disconnect()
        self._tb.btn_close.clicked.connect(self._on_close)
        self._tb.btn_min.clicked.disconnect()
        self._tb.btn_min.clicked.connect(self.hide)
        root.addWidget(self._tb)

        # ── Body ──────────────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(10, 8, 10, 8)
        body.setSpacing(10)

        body.addWidget(self._build_left_panel(), 0)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#1e293b;")
        body.addWidget(sep)

        body.addWidget(self._build_right_panel(), 1)

        root.addLayout(body, 1)

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
        ich_v.addWidget(QLabel("Canales Intel:", styleSheet=_SECTION))
        self._list_intel_ch = QListWidget()
        self._list_intel_ch.setFixedHeight(64)
        self._list_intel_ch.setStyleSheet(_LIST_STYLE)
        ich_v.addWidget(self._list_intel_ch)

        ich_row = QHBoxLayout()
        self._edit_intel_ch = QLineEdit()
        self._edit_intel_ch.setPlaceholderText("Delve.Intel, Standing Fleet…")
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

        self._lbl_intel_hint = QLabel("Sin canales configurados: detecta ficheros con 'intel'.")
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
        jumps_row.addWidget(QLabel("Rango de alerta (saltos):"))
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

        lbl_map = QLabel("⚠ Sin dataset SDE/mapa cargado. distance_jumps → None.\n"
                         "Las alertas de distancia dependen del checkbox anterior.")
        lbl_map.setStyleSheet("color:#475569;font-size:9px;")
        lbl_map.setWordWrap(True)
        iv.addWidget(lbl_map)

        iv.addWidget(self._hline())

        # ── Safe names ────────────────────────────────────────────────────
        iv.addWidget(QLabel("Lista segura (nunca alertan):", styleSheet=_SECTION))
        self._list_safe = QListWidget()
        self._list_safe.setFixedHeight(64)
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
        self._list_watch.setFixedHeight(64)
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
        self._chk_alert_unknown = QCheckBox("Alertar pilotos desconocidos")
        self._chk_alert_unknown.setStyleSheet(_CHK)
        iv.addWidget(self._chk_alert_unknown)

        self._chk_alert_watch = QCheckBox("Alertar lista vigilancia")
        self._chk_alert_watch.setStyleSheet(_CHK)
        iv.addWidget(self._chk_alert_watch)

        self._chk_sound = QCheckBox("Alerta sonora")
        self._chk_sound.setStyleSheet(_CHK)
        iv.addWidget(self._chk_sound)

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
        btn_test = QPushButton("🔔 Sonido")
        btn_test.setStyleSheet(_BTN)
        btn_test.clicked.connect(self._test_sound)
        btn_reset = QPushButton("🔄 Reset")
        btn_reset.setStyleSheet(_BTN)
        btn_reset.clicked.connect(self._reset_session)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_test)
        btn_row.addWidget(btn_reset)
        iv.addLayout(btn_row)

        iv.addStretch()
        scroll.setWidget(inner)
        wl.addWidget(scroll, 1)
        return wrapper

    def _build_right_panel(self) -> QWidget:
        """History panel (stretch)."""
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

        return right

    @staticmethod
    def _hline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color:#1e293b;margin:2px 0;")
        return f

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
        self._chk_sound.setChecked(self._config.alert_sound)
        self._edit_cooldown.setText(str(self._config.pilot_cooldown_secs))

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
        self._config.alert_sound = self._chk_sound.isChecked()
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
            self._btn_toggle.setText("⏹  DETENER")
            self._btn_toggle.setStyleSheet(_BTN_RED)
        else:
            if self._service:
                self._service.stop()
                self._service = None
            self._active = False
            self._btn_toggle.setText("▶  ACTIVAR")
            self._btn_toggle.setStyleSheet(_BTN_GREEN)
        self._refresh_status()

    def _reset_session(self):
        if self._service:
            self._service.reset_session()
        self._lbl_status.setText("● Sesión reiniciada")
        QTimer.singleShot(2000, self._refresh_status)

    def _refresh_status(self):
        if self._active:
            mode = self._config.source_mode.capitalize()
            self._lbl_status.setText(f"● Activo ({mode})")
            self._lbl_status.setStyleSheet("color:#4ade80;font-size:10px;")
        else:
            self._lbl_status.setText("● Inactivo")
            self._lbl_status.setStyleSheet("color:#475569;font-size:10px;")

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

    # ── Sound test ────────────────────────────────────────────────────────────

    def _test_sound(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.beep()
            except Exception:
                pass

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def _on_close(self):
        if self._service:
            self._service.stop()
            self._service = None
        self.hide()

    def closeEvent(self, e):
        e.ignore()
        self._on_close()
