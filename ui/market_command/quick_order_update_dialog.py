"""
Non-modal Quick Order Update dialog (Fase 1 + Fase 2 experimental).
Shows order data, pricing recommendation, and action buttons.
Automation button connects to EVEWindowAutomation when enabled in config.
Window selector lets the user pick the target EVE client window explicitly.
"""
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QTextEdit, QComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

_log = logging.getLogger('eve.market.quick_update')

_SENTINEL_MAX = 9_000_000_000_000.0


def format_price_for_clipboard(price: float) -> str:
    """Format price without thousands separators for clipboard paste into EVE."""
    if price == int(price):
        return str(int(price))
    return f"{price:.2f}".rstrip('0').rstrip('.')


def _fmt_isk(v) -> str:
    try:
        v = float(v)
        if v <= 0 or v >= _SENTINEL_MAX:
            return "---"
        return f"{v:,.2f} ISK"
    except Exception:
        return "N/A"


class QuickOrderUpdateDialog(QDialog):
    """
    Non-modal popup for Quick Order Update.
    Open with .show(), never .exec().
    """

    _BTN = (
        "QPushButton { background:#1e293b; color:white; font-size:9px; font-weight:900;"
        " border:1px solid #334155; border-radius:4px; padding:8px 16px; }"
        " QPushButton:hover { background:#334155; }"
        " QPushButton:disabled { color:#334155; border-color:#1e293b; }"
    )

    def __init__(self, order, recommendation: dict, parent=None,
                 open_market_callback=None, diag_report: str = ""):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint
        )
        self.setModal(False)
        self.order = order
        self.recommendation = recommendation
        self.open_market_callback = open_market_callback
        self._diag_report = diag_report
        self._report_visible = False
        self._window_candidates: list = []   # list of candidate dicts from list_candidate_windows

        # Load automation config once at init
        try:
            from core.quick_order_update_config import load_quick_order_update_config
            self._automation_cfg = load_quick_order_update_config()
        except Exception:
            self._automation_cfg = {
                "enabled": False, "dry_run": True,
                "require_window_selection": True,
                "allow_title_fallback_without_selection": False,
            }

        self.setWindowTitle(f"Quick Order Update — {order.item_name}")
        self.setMinimumSize(560, 620)
        self.setStyleSheet("background-color:#000000; color:#f1f5f9;")
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        # Fresh data indicator banner
        price_src = self.recommendation.get("price_source", "analysis.competitor_price")
        if price_src == "fresh_market_book":
            info = QFrame()
            info.setStyleSheet("background:#1e3a8a; border-radius:6px; border:1px solid #3b82f6;")
            il = QHBoxLayout(info)
            il.setContentsMargins(10, 6, 10, 6)
            msg = QLabel("ℹ  PRECIOS REVALIDADOS CON MARKET BOOK FRESCO (ESI)")
            msg.setStyleSheet("color:#93c5fd; font-size:8px; font-weight:900;")
            il.addWidget(msg)
            root.addWidget(info)

        root.addWidget(self._build_data_grid())

        # Confidence / warning banner
        validation = self.recommendation.get("validation", {})
        if not validation.get("is_confident", True):
            root.addWidget(self._build_warning_frame(validation))

        root.addWidget(self._build_reason_frame())
        root.addWidget(self._build_window_selector())

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#10b981; font-size:9px; font-weight:800;")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._status_lbl)

        root.addLayout(self._build_buttons())

        self._report_edit = QTextEdit()
        self._report_edit.setReadOnly(True)
        self._report_edit.setPlainText(self._diag_report or "(sin reporte)")
        self._report_edit.setStyleSheet(
            "background:#0a0f1a; color:#64748b; font-size:9px;"
            " border:1px solid #1e293b; border-radius:4px;"
        )
        self._report_edit.setFixedHeight(160)
        self._report_edit.hide()
        root.addWidget(self._report_edit)

    # ------------------------------------------------------------------
    def _build_window_selector(self) -> QFrame:
        """Section for detecting and selecting the target EVE client window."""
        frame = QFrame()
        frame.setStyleSheet(
            "background:#0f172a; border-radius:6px; border:1px solid #1e293b;"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(6)

        hdr = QLabel("VENTANA OBJETIVO (AUTOMATIZACIÓN)")
        hdr.setStyleSheet("color:#475569; font-size:8px; font-weight:900;")
        fl.addWidget(hdr)

        row = QHBoxLayout()

        self._window_combo = QComboBox()
        self._window_combo.setStyleSheet(
            "QComboBox { background:#0a0f1a; color:#f1f5f9; font-size:9px;"
            " border:1px solid #334155; border-radius:4px; padding:4px 8px; }"
            " QComboBox::drop-down { border:none; }"
            " QComboBox QAbstractItemView { background:#0a0f1a; color:#f1f5f9;"
            " selection-background-color:#1e293b; font-size:9px; }"
        )
        self._window_combo.addItem("— detecta ventanas primero —", None)
        row.addWidget(self._window_combo, stretch=1)

        self.btn_detect_windows = QPushButton("DETECTAR")
        self.btn_detect_windows.setStyleSheet(self._BTN)
        self.btn_detect_windows.clicked.connect(self._on_detect_windows)
        row.addWidget(self.btn_detect_windows)

        fl.addLayout(row)

        self._window_status_lbl = QLabel(
            "Pulsa DETECTAR para buscar ventanas del cliente EVE."
        )
        self._window_status_lbl.setStyleSheet("color:#475569; font-size:8px;")
        self._window_status_lbl.setWordWrap(True)
        fl.addWidget(self._window_status_lbl)

        return frame

    def _build_warning_frame(self, validation: dict) -> QFrame:
        """Orange warning block shown when confidence is low."""
        frame = QFrame()
        frame.setStyleSheet(
            "background:#431407; border-radius:6px; border:1px solid #f59e0b;"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(4)

        hdr = QLabel("⚠  CONFIANZA BAJA — PRECIO NO COPIADO AUTOMÁTICAMENTE")
        hdr.setStyleSheet("color:#f59e0b; font-size:9px; font-weight:900;")
        fl.addWidget(hdr)

        for w in validation.get("warnings", []):
            lbl = QLabel(f"• {w}")
            lbl.setStyleSheet("color:#fbbf24; font-size:8px;")
            lbl.setWordWrap(True)
            fl.addWidget(lbl)

        note = QLabel(
            "Refresca Mis Pedidos para actualizar datos o copia el precio manualmente si deseas continuar."
        )
        note.setStyleSheet("color:#94a3b8; font-size:8px;")
        note.setWordWrap(True)
        fl.addWidget(note)

        return frame

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setStyleSheet("background:#0f172a; border-radius:8px; border:1px solid #1e293b;")
        hdr.setFixedHeight(72)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 8, 16, 8)

        side_color = "#3b82f6" if self.order.is_buy_order else "#ef4444"
        side_text  = "BUY"    if self.order.is_buy_order else "SELL"

        side_lbl = QLabel(side_text)
        side_lbl.setStyleSheet(
            f"color:{side_color}; font-size:24px; font-weight:900; min-width:64px;"
        )
        side_lbl.setAlignment(Qt.AlignCenter)

        title_v = QVBoxLayout()
        name_lbl = QLabel(self.order.item_name.upper())
        name_lbl.setStyleSheet("color:#f1f5f9; font-size:13px; font-weight:900;")
        sub_lbl = QLabel(
            f"Order ID: {self.order.order_id}  |  Type ID: {self.order.type_id}"
        )
        sub_lbl.setStyleSheet("color:#475569; font-size:9px; font-weight:800;")
        title_v.addWidget(name_lbl)
        title_v.addWidget(sub_lbl)

        hl.addWidget(side_lbl)
        hl.addSpacing(12)
        hl.addLayout(title_v)
        hl.addStretch()
        return hdr

    def _build_data_grid(self) -> QFrame:
        rec      = self.recommendation
        analysis = self.order.analysis

        grid_frame = QFrame()
        grid_frame.setStyleSheet(
            "background:#0a0f1a; border-radius:8px; border:1px solid #1e293b;"
        )
        gl = QGridLayout(grid_frame)
        gl.setContentsMargins(16, 14, 16, 14)
        gl.setSpacing(8)

        action_needed = rec.get("action_needed", False)
        rec_color = "#10b981" if action_needed else "#94a3b8"

        validation = rec.get("validation", {})
        conf_label = validation.get("confidence_label", "Alta")
        conf_color = "#10b981" if conf_label == "Alta" else "#f59e0b"

        price_src = rec.get("price_source", "analysis.competitor_price")
        src_label = "FRESCO (ESI)" if price_src == "fresh_market_book" else "CACHÉ (ANÁLISIS)"
        src_color = "#3b82f6" if price_src == "fresh_market_book" else "#475569"

        rows_data = [
            ("MI PRECIO ACTUAL",   _fmt_isk(self.order.price),           "#f1f5f9"),
            ("PRECIO COMPETIDOR",  _fmt_isk(rec.get("competitor_price")), "#f59e0b"),
            ("MEJOR COMPRA",       _fmt_isk(rec.get("best_buy")),         "#94a3b8"),
            ("MEJOR VENTA",        _fmt_isk(rec.get("best_sell")),        "#94a3b8"),
            ("TICK",               _fmt_isk(rec.get("tick")),             "#64748b"),
            ("PRECIO RECOMENDADO", _fmt_isk(rec.get("recommended_price")), rec_color),
            ("CONFIANZA",          conf_label,                            conf_color),
            ("FUENTE PRECIO",      src_label,                             src_color),
            ("MARKET SCOPE",       rec.get("market_scope", "regional"),   "#94a3b8"),
            ("LOCATION ID",       str(rec.get("location_id") or "N/A"),  "#94a3b8"),
            ("VOLUMEN RESTANTE",
             f"{self.order.volume_remain:,} / {self.order.volume_total:,}", "#94a3b8"),
        ]

        if analysis:
            state_color  = "#10b981" if analysis.competitive else "#f59e0b"
            profit_color = "#10b981" if analysis.net_profit_total >= 0 else "#ef4444"
            margin_color = "#10b981" if analysis.margin_pct > 0 else "#ef4444"
            rows_data += [
                ("ESTADO",       analysis.state.upper(),              state_color),
                ("MARGEN NETO",  f"{analysis.margin_pct:.1f}%",       margin_color),
                ("PROFIT TOTAL", _fmt_isk(analysis.net_profit_total), profit_color),
            ]

        cols = 2
        for idx, (label, value, color) in enumerate(rows_data):
            grid_col = (idx % cols) * 2
            grid_row = (idx // cols) * 2

            lbl_w = QLabel(label)
            lbl_w.setStyleSheet("color:#475569; font-size:8px; font-weight:900;")
            val_w = QLabel(value)
            val_w.setStyleSheet(f"color:{color}; font-size:11px; font-weight:900;")

            gl.addWidget(lbl_w, grid_row,     grid_col)
            gl.addWidget(val_w, grid_row + 1, grid_col)

        return grid_frame

    def _build_reason_frame(self) -> QFrame:
        rec = self.recommendation
        action_needed = rec.get("action_needed", False)

        frame = QFrame()
        frame.setStyleSheet("background:#0f172a; border-radius:6px; border:1px solid #1e293b;")
        rl = QVBoxLayout(frame)
        rl.setContentsMargins(14, 10, 14, 10)

        hdr_color = "#f59e0b" if action_needed else "#10b981"
        hdr_text  = "ACCIÓN RECOMENDADA" if action_needed else "SIN ACCIÓN REQUERIDA"

        reason_hdr = QLabel(hdr_text)
        reason_hdr.setStyleSheet(f"color:{hdr_color}; font-size:9px; font-weight:900;")
        reason_val = QLabel(rec.get("reason", "---"))
        reason_val.setStyleSheet("color:#94a3b8; font-size:10px;")
        reason_val.setWordWrap(True)

        rl.addWidget(reason_hdr)
        rl.addWidget(reason_val)
        return frame

    def _build_buttons(self) -> QHBoxLayout:
        btn_row = QHBoxLayout()

        self.btn_copy   = QPushButton("COPIAR PRECIO")
        self.btn_market = QPushButton("ABRIR MERCADO")
        self.btn_both   = QPushButton("COPIAR + ABRIR")
        self.btn_report = QPushButton("VER REPORTE")
        self.btn_close  = QPushButton("CERRAR")

        # Phase 2: label reflects enabled/dry-run state
        automation_enabled = self._automation_cfg.get("enabled", False)
        dry_run            = self._automation_cfg.get("dry_run", True)
        if automation_enabled and dry_run:
            phase2_label = "AUTOMATIZAR (DRY-RUN)"
        elif automation_enabled:
            phase2_label = "AUTOMATIZAR (FASE 2)"
        else:
            phase2_label = "AUTOMATIZAR (DESACTIVADO)"
        self.btn_phase2 = QPushButton(phase2_label)
        self.btn_phase2.setEnabled(True)   # always clickable — handler explains if disabled

        for btn in [self.btn_copy, self.btn_market, self.btn_report,
                    self.btn_close, self.btn_phase2]:
            btn.setStyleSheet(self._BTN)

        self.btn_both.setStyleSheet(
            self._BTN.replace("background:#1e293b", "background:#1d4ed8")
        )

        if automation_enabled:
            self.btn_phase2.setStyleSheet(
                self._BTN.replace("background:#1e293b", "background:#065f46")
            )

        self.btn_copy.clicked.connect(self._on_copy_price)
        self.btn_market.clicked.connect(self._on_open_market)
        self.btn_both.clicked.connect(self._on_copy_and_open)
        self.btn_report.clicked.connect(self._toggle_report)
        self.btn_close.clicked.connect(self.close)
        self.btn_phase2.clicked.connect(self._on_automate)

        btn_row.addWidget(self.btn_copy)
        btn_row.addWidget(self.btn_market)
        btn_row.addWidget(self.btn_both)
        btn_row.addWidget(self.btn_report)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_phase2)
        btn_row.addWidget(self.btn_close)
        return btn_row

    # ------------------------------------------------------------------
    def _on_copy_price(self):
        price_text = format_price_for_clipboard(
            self.recommendation.get("recommended_price", 0)
        )
        QGuiApplication.clipboard().setText(price_text)
        _log.info(f"[QUICK UPDATE] clipboard_set text={price_text}")
        self._status_lbl.setText(f"Precio copiado: {price_text} ISK")

    def _on_open_market(self):
        if self.open_market_callback:
            self.open_market_callback(self.order)
            self._status_lbl.setText("Mercado in-game abierto")
        else:
            self._status_lbl.setText("Sin callback de mercado disponible")

    def _on_copy_and_open(self):
        self._on_copy_price()
        self._on_open_market()

    def _toggle_report(self):
        self._report_visible = not self._report_visible
        if self._report_visible:
            self._report_edit.show()
            self.btn_report.setText("OCULTAR REPORTE")
        else:
            self._report_edit.hide()
            self.btn_report.setText("VER REPORTE")
        self.adjustSize()

    # ------------------------------------------------------------------
    # Phase 2: window detection
    # ------------------------------------------------------------------
    def _on_detect_windows(self):
        """Enumerate visible windows and populate the selection combo."""
        self._window_status_lbl.setText("Detectando ventanas...")
        self._window_status_lbl.setStyleSheet("color:#3b82f6; font-size:8px;")

        try:
            from core.window_automation import list_candidate_windows
            candidates = list_candidate_windows(self._automation_cfg)
        except Exception as exc:
            self._window_status_lbl.setText(f"Error al detectar ventanas: {exc}")
            self._window_status_lbl.setStyleSheet("color:#ef4444; font-size:8px;")
            return

        self._window_candidates = candidates
        self._window_combo.clear()

        if not candidates:
            self._window_combo.addItem("(ninguna ventana detectada)", None)
            self._window_status_lbl.setText(
                "No se detectaron ventanas. ¿pywinauto instalado y hay ventanas abiertas?"
            )
            self._window_status_lbl.setStyleSheet("color:#f59e0b; font-size:8px;")
            return

        best_idx = 0
        best_score = -9999
        for i, c in enumerate(candidates):
            title  = c["title"]
            handle = c["handle"]
            score  = c["score"]
            if c["is_self_app"]:
                label = f"{title}  [IGNORAR — propia app]"
            else:
                label = f"{title}  [handle: {handle}  score: {score:+d}]"
            self._window_combo.addItem(label, c)
            # Track best non-self candidate
            if not c["is_self_app"] and score > best_score:
                best_score = score
                best_idx = i

        # Auto-select best non-self candidate (if any exists)
        best = candidates[best_idx]
        if not best["is_self_app"]:
            self._window_combo.setCurrentIndex(best_idx)
            self._window_status_lbl.setText(
                f"Detectadas {len(candidates)} ventana(s). "
                f"Seleccionada automáticamente: {best['title'][:50]}"
            )
            self._window_status_lbl.setStyleSheet("color:#10b981; font-size:8px;")
        else:
            self._window_status_lbl.setText(
                f"Detectadas {len(candidates)} ventana(s). "
                "Selecciona manualmente el cliente EVE Online."
            )
            self._window_status_lbl.setStyleSheet("color:#f59e0b; font-size:8px;")

        _log.info(
            f"[QUICK UPDATE] detect_windows found={len(candidates)} "
            f"best_score={best_score}"
        )

    def _selected_window(self) -> Optional[dict]:
        """Return the currently selected window candidate dict, or None."""
        return self._window_combo.currentData()

    # ------------------------------------------------------------------
    # Phase 2: automation
    # ------------------------------------------------------------------
    def _on_automate(self):
        cfg = self._automation_cfg
        if not cfg.get("enabled", False):
            msg = (
                "Automatización experimental desactivada. "
                "Activa enabled=true en config/quick_order_update.json para usar esta función."
            )
            self._status_lbl.setText(msg)
            self._status_lbl.setStyleSheet("color:#f59e0b; font-size:9px; font-weight:800;")
            _log.info("[QUICK UPDATE] automation button clicked but enabled=false")
            return

        selected = self._selected_window()
        require  = cfg.get("require_window_selection", True)
        allow_fb = cfg.get("allow_title_fallback_without_selection", False)

        # Guard: no selection + requires selection + no fallback allowed
        if selected is None and require and not allow_fb:
            msg = (
                "No hay ventana objetivo seleccionada. "
                "Pulsa DETECTAR y selecciona el cliente EVE Online antes de automatizar."
            )
            self._status_lbl.setText(msg)
            self._status_lbl.setStyleSheet("color:#f59e0b; font-size:9px; font-weight:800;")
            _log.warning("[QUICK UPDATE] automation blocked — no window selected")
            return

        price_text = format_price_for_clipboard(
            self.recommendation.get("recommended_price", 0)
        )
        order_data = {
            "order_id":      self.order.order_id,
            "type_id":       self.order.type_id,
            "item_name":     self.order.item_name,
            "price":         self.order.price,
            "volume_remain": getattr(self.order, "volume_remain", 0),
            "volume_total":  getattr(self.order, "volume_total", 0),
            "is_buy_order":  getattr(self.order, "is_buy_order", False),
            "location_id":   getattr(self.order, "location_id", None),
        }

        self._status_lbl.setText("Ejecutando automatización experimental...")
        self._status_lbl.setStyleSheet("color:#3b82f6; font-size:9px; font-weight:800;")

        result = None
        try:
            from core.window_automation import EVEWindowAutomation
            auto   = EVEWindowAutomation(cfg)
            result = auto.execute_quick_order_update(
                order_data, price_text, selected_window=selected
            )
        except Exception as exc:
            _log.error(f"[QUICK UPDATE] automation crash: {exc}")
            # Create a minimal error result to allow report generation
            result = {
                "status": "error",
                "errors": [f"Crash en automatización: {exc}"],
                "steps_executed": [],
                "steps_skipped": ["automation_crashed"],
            }
        
        # Inject candidate list metadata into result for diagnostics
        result["candidate_windows_count"] = len(self._window_candidates)
        result["candidate_windows"]       = self._window_candidates[:8]

        # Update the report panel — replace existing [AUTOMATION] if present
        try:
            from core.quick_order_update_diagnostics import (
                format_automation_section, replace_or_append_automation_section,
            )
            auto_section   = format_automation_section(result)
            updated_report = replace_or_append_automation_section(
                self._diag_report, auto_section
            )
            self._diag_report = updated_report
            self._report_edit.setPlainText(updated_report)
        except Exception as exc:
            _log.warning(f"[QUICK UPDATE] could not update diag report: {exc}")
            # Fallback: if even formatting fails, just append raw error to report if possible
            if "[AUTOMATION]" not in self._diag_report:
                self._diag_report += f"\n\n[AUTOMATION]\n  Status: error\n  Error: formatting_failed {exc}"
                self._report_edit.setPlainText(self._diag_report)

        status  = result.get("status", "unknown")
        errors  = result.get("errors", [])

        if status == "dry_run":
            sel_title = (selected.get("title", "?")[:40] if selected else "fallback por título")
            msg   = f"Dry-run completado. Ventana: {sel_title}. Ver reporte."
            color = "#10b981"
        elif status == "success":
            msg   = "Automatización completada. Precio copiado y ventana enfocada."
            color = "#10b981"
        elif status == "partial":
            err_summary = errors[0] if errors else "error desconocido"
            msg   = f"Automatización parcial: {err_summary}"
            color = "#f59e0b"
        elif status == "error":
            err_summary = errors[0] if errors else "error desconocido"
            msg   = f"Error en automatización: {err_summary}"
            color = "#ef4444"
        else:
            msg   = f"Estado: {status}"
            color = "#94a3b8"

        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"color:{color}; font-size:9px; font-weight:800;"
        )

        # Auto-show report
        if not self._report_visible:
            self._toggle_report()

        _log.info(
            f"[QUICK UPDATE] automation status={status} "
            f"window_source={result.get('window_source')} errors={len(errors)}"
        )
