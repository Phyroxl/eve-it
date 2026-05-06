"""Intel Alert — ventana de configuración y alertas de hostiles."""
import logging
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QCheckBox,
    QFrame, QSplitter, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor

from core.intel_alert_service import IntelAlertService, IntelAlertConfig, IntelEvent

logger = logging.getLogger('eve.intel')

# ── Estilos ──────────────────────────────────────────────────────────────────
_BTN = """
QPushButton {
    background:#0f172a; border:1px solid #1e293b;
    color:#94a3b8; font-size:11px; padding:4px 10px;
}
QPushButton:hover { background:#1e293b; color:#e2e8f0; }
QPushButton:disabled { color:#334155; }
"""
_BTN_GREEN = """
QPushButton {
    background:#052e16; border:1px solid #16a34a;
    color:#4ade80; font-size:11px; font-weight:bold; padding:4px 10px;
}
QPushButton:hover { background:#14532d; }
"""
_BTN_RED = """
QPushButton {
    background:#1a0000; border:1px solid #7f1d1d;
    color:#f87171; font-size:11px; font-weight:bold; padding:4px 10px;
}
QPushButton:hover { background:#450a0a; }
"""
_INPUT = "background:#0d1626;border:1px solid #1e293b;color:#e2e8f0;padding:4px;font-size:11px;"
_SECTION = "color:#64748b;font-size:10px;font-weight:bold;margin-top:6px;"
_LIST = """
QListWidget {
    background:#060d18; border:1px solid #1e293b;
    color:#94a3b8; font-size:11px;
}
QListWidget::item:selected { background:#1e293b; color:#e2e8f0; }
"""
_HISTORY_LOCAL = "#22c55e"
_HISTORY_WATCH = "#f59e0b"
_HISTORY_INTEL = "#38bdf8"


class IntelAlertWindow(QWidget):
    """Ventana de Intel Alert — detección de hostiles en chatlogs de EVE."""

    _event_signal = Signal(object)  # IntelEvent

    def __init__(self, parent=None, controller=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self._ctrl = controller
        self._config = IntelAlertConfig.load()
        self._service: Optional[IntelAlertService] = None
        self._drag_pos = None
        self._active = False
        self._event_history = []

        self._setup_ui()
        self._load_config_to_ui()

        self._event_signal.connect(self._on_event_ui)

    # ── UI setup ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setMinimumSize(620, 560)
        self.setStyleSheet("QWidget{background:#060d18;color:#94a3b8;font-size:11px;}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Titlebar ──────────────────────────────────────────────────────
        tb = QWidget(); tb.setFixedHeight(28)
        tb.setStyleSheet("background:#0f172a;border-bottom:1px solid #1e293b;")
        tbl = QHBoxLayout(tb); tbl.setContentsMargins(10, 0, 6, 0); tbl.setSpacing(6)

        ico = QLabel("⚠"); ico.setStyleSheet("color:#f59e0b;font-size:13px;background:transparent;")
        ttl = QLabel("Intel Alert"); ttl.setStyleSheet("color:#e2e8f0;font-size:11px;font-weight:bold;background:transparent;")
        tbl.addWidget(ico); tbl.addWidget(ttl); tbl.addStretch()

        BTN_BASE = "QPushButton{background:#0f172a;border:1px solid #1e293b;border-radius:3px;color:#94a3b8;font-size:11px;font-weight:700;padding:0;}QPushButton:hover{background:#1e293b;color:#e2e8f0;}"
        BTN_CLOSE = "QPushButton{background:#0f172a;border:1px solid #1e293b;border-radius:3px;color:#94a3b8;font-size:11px;font-weight:700;padding:0;}QPushButton:hover{background:rgba(239,68,68,0.2);border-color:#ef4444;color:#ef4444;}"

        btn_min = QPushButton("−"); btn_min.setFixedSize(20, 18); btn_min.setStyleSheet(BTN_BASE)
        btn_min.clicked.connect(self.hide)
        btn_cls = QPushButton("×"); btn_cls.setFixedSize(20, 18); btn_cls.setStyleSheet(BTN_CLOSE)
        btn_cls.clicked.connect(self._on_close)
        tbl.addWidget(btn_min); tbl.addWidget(btn_cls)

        tb.mousePressEvent = lambda e: setattr(self, '_drag_pos', e.globalPosition().toPoint() - self.frameGeometry().topLeft()) if e.button() == Qt.LeftButton else None
        tb.mouseMoveEvent = lambda e: self.move(e.globalPosition().toPoint() - self._drag_pos) if self._drag_pos and e.buttons() == Qt.LeftButton else None
        tb.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        root.addWidget(tb)

        # ── Body ─────────────────────────────────────────────────────────
        body = QHBoxLayout(); body.setContentsMargins(12, 10, 12, 10); body.setSpacing(12)

        # Left: config
        left = QWidget(); left.setFixedWidth(280)
        lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(6)

        # Status row
        status_row = QHBoxLayout()
        self._btn_toggle = QPushButton("▶ ACTIVAR"); self._btn_toggle.setStyleSheet(_BTN_GREEN)
        self._btn_toggle.clicked.connect(self._toggle_service)
        self._lbl_status = QLabel("● Inactivo"); self._lbl_status.setStyleSheet("color:#475569;font-size:10px;")
        status_row.addWidget(self._btn_toggle); status_row.addStretch(); status_row.addWidget(self._lbl_status)
        lv.addLayout(status_row)

        # Options
        self._chk_sound = QCheckBox("Alerta sonora"); self._chk_sound.setStyleSheet("QCheckBox{color:#94a3b8;}")
        self._chk_unknown = QCheckBox("Alertar pilotos desconocidos en Local"); self._chk_unknown.setStyleSheet("QCheckBox{color:#94a3b8;}")
        lv.addWidget(self._chk_sound)
        lv.addWidget(self._chk_unknown)

        # Cooldown
        cd_row = QHBoxLayout()
        cd_row.addWidget(QLabel("Cooldown (s):"))
        self._edit_cooldown = QLineEdit("120"); self._edit_cooldown.setFixedWidth(50); self._edit_cooldown.setStyleSheet(_INPUT)
        cd_row.addWidget(self._edit_cooldown); cd_row.addStretch()
        lv.addLayout(cd_row)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine); sep1.setStyleSheet("color:#1e293b;")
        lv.addWidget(sep1)

        # Safe names (whitelist)
        lv.addWidget(QLabel("Lista segura (no alertar):", styleSheet=_SECTION))
        self._list_safe = QListWidget(); self._list_safe.setFixedHeight(90); self._list_safe.setStyleSheet(_LIST)
        lv.addWidget(self._list_safe)
        safe_row = QHBoxLayout(); safe_row.setSpacing(4)
        self._edit_safe = QLineEdit(); self._edit_safe.setPlaceholderText("Nombre de piloto..."); self._edit_safe.setStyleSheet(_INPUT)
        btn_add_safe = QPushButton("+"); btn_add_safe.setFixedWidth(28); btn_add_safe.setStyleSheet(_BTN)
        btn_add_safe.clicked.connect(self._add_safe)
        btn_del_safe = QPushButton("−"); btn_del_safe.setFixedWidth(28); btn_del_safe.setStyleSheet(_BTN)
        btn_del_safe.clicked.connect(lambda: self._del_selected(self._list_safe))
        safe_row.addWidget(self._edit_safe); safe_row.addWidget(btn_add_safe); safe_row.addWidget(btn_del_safe)
        lv.addLayout(safe_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setStyleSheet("color:#1e293b;")
        lv.addWidget(sep2)

        # Watch names (alert always)
        lv.addWidget(QLabel("Lista vigilancia (siempre alertar):", styleSheet=_SECTION))
        self._list_watch = QListWidget(); self._list_watch.setFixedHeight(90); self._list_watch.setStyleSheet(_LIST)
        lv.addWidget(self._list_watch)
        watch_row = QHBoxLayout(); watch_row.setSpacing(4)
        self._edit_watch = QLineEdit(); self._edit_watch.setPlaceholderText("Nombre de piloto..."); self._edit_watch.setStyleSheet(_INPUT)
        btn_add_watch = QPushButton("+"); btn_add_watch.setFixedWidth(28); btn_add_watch.setStyleSheet(_BTN)
        btn_add_watch.clicked.connect(self._add_watch)
        btn_del_watch = QPushButton("−"); btn_del_watch.setFixedWidth(28); btn_del_watch.setStyleSheet(_BTN)
        btn_del_watch.clicked.connect(lambda: self._del_selected(self._list_watch))
        watch_row.addWidget(self._edit_watch); watch_row.addWidget(btn_add_watch); watch_row.addWidget(btn_del_watch)
        lv.addLayout(watch_row)

        lv.addStretch()

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        btn_save = QPushButton("💾 Guardar"); btn_save.setStyleSheet(_BTN); btn_save.clicked.connect(self._save)
        btn_reset = QPushButton("🔄 Reset sesión"); btn_reset.setStyleSheet(_BTN); btn_reset.clicked.connect(self._reset_session)
        btn_test = QPushButton("🔔 Test sonido"); btn_test.setStyleSheet(_BTN); btn_test.clicked.connect(self._test_sound)
        btn_row.addWidget(btn_save); btn_row.addWidget(btn_reset); btn_row.addWidget(btn_test)
        lv.addLayout(btn_row)

        # Right: event history
        right = QWidget()
        rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(4)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(QLabel("Historial de alertas:", styleSheet=_SECTION))
        hdr_row.addStretch()
        btn_clear = QPushButton("Limpiar"); btn_clear.setFixedWidth(60); btn_clear.setStyleSheet(_BTN)
        btn_clear.clicked.connect(self._clear_history)
        hdr_row.addWidget(btn_clear)
        rv.addLayout(hdr_row)

        self._list_history = QListWidget(); self._list_history.setStyleSheet(_LIST)
        self._list_history.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rv.addWidget(self._list_history, 1)

        # Legend
        leg_row = QHBoxLayout(); leg_row.setSpacing(10)
        for color, label in [(_HISTORY_LOCAL, "Local nuevo"), (_HISTORY_WATCH, "Vigilancia"), (_HISTORY_INTEL, "Intel")]:
            dot = QLabel(f"● {label}"); dot.setStyleSheet(f"color:{color};font-size:10px;")
            leg_row.addWidget(dot)
        leg_row.addStretch()
        rv.addLayout(leg_row)

        body.addWidget(left)
        sep_v = QFrame(); sep_v.setFrameShape(QFrame.VLine); sep_v.setStyleSheet("color:#1e293b;")
        body.addWidget(sep_v)
        body.addWidget(right, 1)

        root.addLayout(body, 1)

    # ── Config load / save ────────────────────────────────────────────────────

    def _load_config_to_ui(self):
        self._chk_sound.setChecked(self._config.alert_sound)
        self._chk_unknown.setChecked(self._config.alert_on_unknown)
        self._edit_cooldown.setText(str(self._config.pilot_cooldown_secs))
        self._list_safe.clear()
        for n in self._config.safe_names:
            self._list_safe.addItem(n)
        self._list_watch.clear()
        for n in self._config.watch_names:
            self._list_watch.addItem(n)

    def _collect_config_from_ui(self):
        self._config.alert_sound = self._chk_sound.isChecked()
        self._config.alert_on_unknown = self._chk_unknown.isChecked()
        try:
            self._config.pilot_cooldown_secs = max(5, int(self._edit_cooldown.text()))
        except ValueError:
            pass
        self._config.safe_names = [self._list_safe.item(i).text() for i in range(self._list_safe.count())]
        self._config.watch_names = [self._list_watch.item(i).text() for i in range(self._list_watch.count())]

    def _save(self):
        self._collect_config_from_ui()
        self._config.save()
        if self._service:
            self._service.update_config(self._config)
        self._lbl_status.setText("● Config guardada")
        QTimer.singleShot(2000, self._refresh_status_label)

    # ── List management ───────────────────────────────────────────────────────

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

    def _list_has(self, lst: QListWidget, name: str) -> bool:
        return any(lst.item(i).text().lower() == name.lower() for i in range(lst.count()))

    # ── Service control ───────────────────────────────────────────────────────

    def _toggle_service(self):
        if not self._active:
            self._collect_config_from_ui()
            self._config.enabled = True
            self._start_service()
            self._active = True
            self._btn_toggle.setText("⏹ DETENER")
            self._btn_toggle.setStyleSheet(_BTN_RED)
        else:
            if self._service:
                self._service.stop()
                self._service = None
            self._active = False
            self._btn_toggle.setText("▶ ACTIVAR")
            self._btn_toggle.setStyleSheet(_BTN_GREEN)
        self._refresh_status_label()

    def _start_service(self):
        if self._service:
            self._service.stop()
        self._service = IntelAlertService(self._config, self._on_event_thread)
        self._service.start()

    def _reset_session(self):
        if self._service:
            self._service.reset_session()
        self._lbl_status.setText("● Sesión reiniciada")
        QTimer.singleShot(2000, self._refresh_status_label)

    def _refresh_status_label(self):
        if self._active:
            self._lbl_status.setText("● Activo")
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
            'local_new': _HISTORY_LOCAL,
            'watchlist_hit': _HISTORY_WATCH,
            'intel_msg': _HISTORY_INTEL,
        }.get(event.event_type, '#94a3b8')

        tag = {'local_new': 'LOCAL', 'watchlist_hit': '⚡ WATCH', 'intel_msg': '📡 INTEL'}.get(event.event_type, '?')
        ts = event.timestamp[-8:] if len(event.timestamp) >= 8 else event.timestamp
        text = f"[{ts}] [{tag}] {event.pilot} — {event.message[:60]}"

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
        self._on_close()
        super().closeEvent(e)
