"""Visual Clon — main UI widget.

Clona la configuración visual y el layout de ventanas de un personaje
EVE Online a otros personajes de forma segura, con backup automático.

v3: portrait + nombre resuelto; sin panel de log visible.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QListWidget, QListWidgetItem, QCheckBox,
    QFileDialog, QLineEdit, QAbstractItemView, QProgressBar,
    QScrollArea, QMessageBox,
)

logger = logging.getLogger('eve.visual_clon')

# ── Stylesheet ─────────────────────────────────────────────────────────────────
_STYLE = """
QWidget { background: #05070a; color: #e2e8f0;
          font-family: 'Segoe UI', sans-serif; font-size: 10px; }
QFrame#VCPanel { background: #0b1016; border: 1px solid #1e293b; border-radius: 3px; }
QFrame#VCSourceCard { background: #0b1016; border: 1px solid #00c8ff;
                      border-radius: 3px; }
QLabel#VCTitle { color: #00c8ff; font-size: 14px; font-weight: 800;
                 letter-spacing: 2px; }
QLabel#VCSub { color: #64748b; font-size: 10px; }
QLabel#VCSectionLabel { color: #94a3b8; font-size: 10px; font-weight: 700;
                        letter-spacing: 1px; margin-top: 4px; }
QLabel#VCCharName { color: #e2e8f0; font-size: 12px; font-weight: 800; }
QLabel#VCCharId { color: #64748b; font-size: 9px; }
QLabel#VCCharInfo { color: #64748b; font-size: 9px; }
QLabel#VCStatusOk { color: #10b981; font-size: 10px; }
QLabel#VCStatusErr { color: #ef4444; font-size: 10px; }
QLabel#VCStatus { color: #94a3b8; font-size: 10px; }
QLabel#VCPortrait { border: 2px solid #1e2a3a; border-radius: 3px;
                    background: #0d1626; }
QLabel#VCPortraitSrc { border: 2px solid #00c8ff; border-radius: 3px;
                       background: #0d1626; }
QPushButton#VCPrimary { background: #00c8ff; color: #05070a; font-weight: 800;
    border: none; border-radius: 3px; padding: 7px 16px; }
QPushButton#VCPrimary:hover { background: #38d4ff; }
QPushButton#VCPrimary:disabled { background: #1e293b; color: #64748b; }
QPushButton#VCSecondary { background: #0d1626; color: #00c8ff;
    border: 1px solid #1e293b; border-radius: 3px; padding: 6px 14px; }
QPushButton#VCSecondary:hover { border-color: #00c8ff; }
QPushButton#VCSecondary:disabled { color: #64748b; border-color: #1e293b; }
QPushButton#VCDanger { background: #0d1626; color: #ef4444;
    border: 1px solid #1e293b; border-radius: 3px; padding: 6px 14px; }
QPushButton#VCDanger:hover { border-color: #ef4444; }
QPushButton#VCDanger:disabled { color: #64748b; border-color: #1e293b; }
QComboBox { background: #0d1626; color: #e2e8f0; border: 1px solid #1e293b;
    border-radius: 3px; padding: 5px 8px; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #0b1016; color: #e2e8f0;
    border: 1px solid #1e293b; }
QListWidget { background: #0d1626; color: #e2e8f0; border: 1px solid #1e293b;
    border-radius: 3px; }
QListWidget::item { padding: 0; border-bottom: 1px solid #111827; }
QListWidget::item:hover { background: #111827; }
QLineEdit { background: #0d1626; color: #e2e8f0; border: 1px solid #1e293b;
    border-radius: 3px; padding: 5px 8px; }
QCheckBox { color: #e2e8f0; spacing: 6px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #1e293b;
    background: #0d1626; border-radius: 2px; }
QCheckBox::indicator:checked { background: #00c8ff; border-color: #00c8ff; }
QCheckBox::indicator:disabled { background: #0d1626; border-color: #111827; }
QProgressBar { background: #0d1626; border: 1px solid #1e293b; border-radius: 2px;
    height: 4px; }
QProgressBar::chunk { background: #00c8ff; border-radius: 2px; }
QScrollBar:vertical { background: #0b1016; width: 6px; }
QScrollBar::handle:vertical { background: #1e293b; border-radius: 3px; }
QScrollArea { border: none; background: transparent; }
"""


# ── Reusable helpers ───────────────────────────────────────────────────────────

def _panel() -> tuple:
    f = QFrame(); f.setObjectName("VCPanel")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(6)
    return f, lay


def _label(text: str, obj: str = '') -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    return lb


def _make_portrait_placeholder(size: int, label: str = 'PILOT') -> QPixmap:
    from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, QColor('#1e293b'))
    grad.setColorAt(1, QColor('#0f172a'))
    painter.setBrush(grad)
    painter.setPen(QColor('#334155'))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    painter.setPen(QColor('#475569'))
    font = QFont('Segoe UI', max(6, size // 8), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, label)
    painter.end()
    return pix


# ── Character source card ──────────────────────────────────────────────────────

class CharSourceCard(QFrame):
    """Preview card for the selected source character: portrait + name + ID + file info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VCSourceCard")
        self._setup()

    def _setup(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        self.portrait_lbl = QLabel()
        self.portrait_lbl.setObjectName("VCPortraitSrc")
        self.portrait_lbl.setFixedSize(64, 64)
        self.portrait_lbl.setAlignment(Qt.AlignCenter)
        self.portrait_lbl.setPixmap(_make_portrait_placeholder(60))
        lay.addWidget(self.portrait_lbl)

        text = QVBoxLayout()
        text.setSpacing(2)
        self.name_lbl = _label("—", 'VCCharName')
        self.id_lbl = _label("", 'VCCharId')
        self.info_lbl = _label("", 'VCCharInfo')
        text.addWidget(self.name_lbl)
        text.addWidget(self.id_lbl)
        text.addWidget(self.info_lbl)
        text.addStretch()
        lay.addLayout(text, 1)

    def update_profile(self, profile, name_override: str = ''):
        if not profile:
            self.name_lbl.setText("—")
            self.id_lbl.setText("")
            self.info_lbl.setText("")
            self.portrait_lbl.setPixmap(_make_portrait_placeholder(60))
            return

        display = name_override if name_override else profile.display_name
        self.name_lbl.setText(display)
        self.id_lbl.setText(f"ID: {profile.char_id}")
        modified = profile.modified.strftime('%d/%m/%Y %H:%M') if profile.modified else '?'
        self.info_lbl.setText(f"Tamaño: {profile.file_size // 1024} KB | Modificado: {modified}")
        self._load_portrait(profile)

    def set_portrait(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.portrait_lbl.setPixmap(scaled)

    def _load_portrait(self, profile):
        try:
            from core.eve_icon_service import EveIconService
            char_id_int = int(profile.char_id)
            svc = EveIconService.instance()
            pix = svc.get_portrait(
                char_id_int, size=64,
                callback=lambda p, w=self: w.set_portrait(p),
            )
            if pix and not pix.isNull():
                self.set_portrait(pix)
        except Exception as e:
            logger.debug(f"[VC] Portrait src {profile.char_id}: {e}")


# ── Custom target row widget ───────────────────────────────────────────────────

class CharRowWidget(QWidget):
    """One row in the targets list: [checkbox] [portrait] [name / ID]."""

    _PORTRAIT_SIZE = 48

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setFixedHeight(62)
        self._portrait_loaded = False
        self._setup()

    def _setup(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        self.chk = QCheckBox()
        lay.addWidget(self.chk)

        self.portrait_lbl = QLabel()
        self.portrait_lbl.setObjectName("VCPortrait")
        self.portrait_lbl.setFixedSize(self._PORTRAIT_SIZE, self._PORTRAIT_SIZE)
        self.portrait_lbl.setAlignment(Qt.AlignCenter)
        self.portrait_lbl.setPixmap(_make_portrait_placeholder(self._PORTRAIT_SIZE - 4))
        lay.addWidget(self.portrait_lbl)

        text = QVBoxLayout()
        text.setSpacing(1)
        self.name_lbl = QLabel(self.profile.display_name)
        self.name_lbl.setStyleSheet("font-weight: 700; color: #e2e8f0; font-size: 10px;")
        self.id_lbl = QLabel(f"ID: {self.profile.char_id}")
        self.id_lbl.setStyleSheet("color: #64748b; font-size: 9px;")
        text.addWidget(self.name_lbl)
        text.addWidget(self.id_lbl)
        lay.addLayout(text, 1)

    def is_checked(self) -> bool:
        return self.chk.isChecked()

    def set_checked(self, checked: bool):
        self.chk.setChecked(checked)

    def set_portrait(self, pixmap: QPixmap):
        try:
            if pixmap and not pixmap.isNull():
                s = self._PORTRAIT_SIZE - 4
                scaled = pixmap.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.portrait_lbl.setPixmap(scaled)
        except RuntimeError:
            pass

    def set_name(self, name: str):
        if name:
            try:
                self.name_lbl.setText(name)
            except RuntimeError:
                pass

    def load_portrait(self):
        if self._portrait_loaded:
            return
        self._portrait_loaded = True
        try:
            from core.eve_icon_service import EveIconService
            char_id_int = int(self.profile.char_id)
            svc = EveIconService.instance()
            pix = svc.get_portrait(
                char_id_int, size=64,
                callback=lambda p, w=self: w.set_portrait(p),
            )
            if pix and not pix.isNull():
                self.set_portrait(pix)
        except Exception as e:
            logger.debug(f"[VC] Portrait dst {self.profile.char_id}: {e}")


# ── Main view ─────────────────────────────────────────────────────────────────

class VisualClonView(QWidget):
    """Main Visual Clon widget, embedded inside a frameless window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLE)
        self.setObjectName("VisualClonView")

        self._folder: Optional[object] = None
        self._scan_worker = None
        self._clone_worker = None
        self._identity_worker = None
        self._resolved_names: Dict[str, str] = {}

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(_label("VISUAL CLON", 'VCTitle'))
        hdr.addStretch()
        sub = _label("Clona configuración visual y layout de ventanas entre personajes EVE.", 'VCSub')
        hdr.addWidget(sub)
        root.addLayout(hdr)

        # ── Two-column body ─────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_left_col(), 0)   # fixed width left
        body.addWidget(self._build_right_col(), 1)  # stretch right
        root.addLayout(body, 1)

        # ── Bottom bar ──────────────────────────────────────────────────────
        self.lbl_result = _label("", 'VCStatus')
        self.lbl_result.setWordWrap(True)
        root.addWidget(self.lbl_result)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.btn_analyze = QPushButton("Analizar")
        self.btn_analyze.setObjectName("VCSecondary")
        self.btn_simulate = QPushButton("Simular copia")
        self.btn_simulate.setObjectName("VCSecondary")
        self.btn_apply = QPushButton("Aplicar Visual Clon")
        self.btn_apply.setObjectName("VCPrimary")
        self.btn_restore = QPushButton("Restaurar backup")
        self.btn_restore.setObjectName("VCDanger")
        for btn in (self.btn_analyze, self.btn_simulate, self.btn_apply, self.btn_restore):
            btn.setCursor(Qt.PointingHandCursor)
            btns.addWidget(btn)
        btns.addStretch()
        root.addLayout(btns)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.btn_analyze.clicked.connect(self._on_analyze)
        self.btn_simulate.clicked.connect(self._on_simulate)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_restore.clicked.connect(self._on_restore)
        self._set_action_enabled(False)

    # ── Left column: folder + source ───────────────────────────────────────────

    def _build_left_col(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(370)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # EVE folder
        fp, fl = _panel()
        fl.addWidget(_label("CARPETA EVE", 'VCSectionLabel'))
        self.edit_path = QLineEdit()
        self.edit_path.setPlaceholderText("Ruta settings_Default de EVE…")
        self.edit_path.setReadOnly(True)
        fl.addWidget(self.edit_path)
        btn_row = QHBoxLayout()
        self.btn_detect = QPushButton("Detectar auto")
        self.btn_detect.setObjectName("VCSecondary")
        self.btn_detect.setCursor(Qt.PointingHandCursor)
        self.btn_browse = QPushButton("Seleccionar…")
        self.btn_browse.setObjectName("VCSecondary")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(self.btn_detect)
        btn_row.addWidget(self.btn_browse)
        btn_row.addStretch()
        fl.addLayout(btn_row)
        self.lbl_folder_status = _label("", 'VCStatusOk')
        fl.addWidget(self.lbl_folder_status)
        lay.addWidget(fp)
        self.btn_detect.clicked.connect(self._on_detect)
        self.btn_browse.clicked.connect(self._on_browse)

        # Source
        sp, sl = _panel()
        sl.addWidget(_label("PERSONAJE ORIGEN", 'VCSectionLabel'))
        self.combo_source = QComboBox()
        self.combo_source.setPlaceholderText("— seleccionar origen —")
        sl.addWidget(self.combo_source)
        self.source_card = CharSourceCard()
        sl.addWidget(self.source_card)
        lay.addWidget(sp)
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)

        # Safety options
        safe_p, safe_l = _panel()
        safe_l.addWidget(_label("SEGURIDAD", 'VCSectionLabel'))
        self.chk_backup = QCheckBox("Backup antes de aplicar (recomendado)")
        self.chk_backup.setChecked(True)
        self.chk_backup.setEnabled(False)
        safe_l.addWidget(self.chk_backup)
        self.chk_validate = QCheckBox("Validar archivos antes de copiar")
        self.chk_validate.setChecked(True)
        safe_l.addWidget(self.chk_validate)
        lay.addWidget(safe_p)

        lay.addStretch()
        return w

    # ── Right column: targets + sections ───────────────────────────────────────

    def _build_right_col(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Targets
        tp, tl = _panel()
        tl.addWidget(_label("PERSONAJES DESTINO", 'VCSectionLabel'))
        self.list_targets = QListWidget()
        self.list_targets.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_targets.setMinimumHeight(220)
        self.list_targets.setSpacing(0)
        tl.addWidget(self.list_targets, 1)
        trow = QHBoxLayout()
        btn_all = QPushButton("Seleccionar todos")
        btn_all.setObjectName("VCSecondary")
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_clr = QPushButton("Limpiar")
        btn_clr.setObjectName("VCSecondary")
        btn_clr.setCursor(Qt.PointingHandCursor)
        trow.addWidget(btn_all); trow.addWidget(btn_clr); trow.addStretch()
        tl.addLayout(trow)
        lay.addWidget(tp, 1)
        btn_all.clicked.connect(self._select_all_targets)
        btn_clr.clicked.connect(self._clear_targets)

        # Sections info (read-only note, no interactive checkboxes shown)
        sec_p, sec_l = _panel()
        sec_l.addWidget(_label("SECCIONES A COPIAR", 'VCSectionLabel'))
        note = _label(
            "El perfil EVE es binario — se copia el archivo completo "
            "(layout, overview, chat, inventario, preferencias visuales).", 'VCSub'
        )
        note.setWordWrap(True)
        sec_l.addWidget(note)
        self._section_checks: List[QCheckBox] = []
        lay.addWidget(sec_p)

        return w

    # ── Legacy alias kept for compatibility ────────────────────────────────────
    def _build_left(self) -> QWidget:
        return self._build_left_col()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, ok: bool = True, warn: bool = False):
        self.lbl_result.setText(msg)
        if warn:
            self.lbl_result.setStyleSheet('color: #f59e0b;')
        elif ok:
            self.lbl_result.setStyleSheet('color: #10b981;')
        else:
            self.lbl_result.setStyleSheet('color: #ef4444;')

    def _set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        for btn in (self.btn_detect, self.btn_browse, self.btn_analyze,
                    self.btn_simulate, self.btn_apply, self.btn_restore):
            btn.setEnabled(not busy)

    def _set_action_enabled(self, ok: bool):
        for btn in (self.btn_analyze, self.btn_simulate, self.btn_apply):
            btn.setEnabled(ok)

    def _show_folder_status(self, ok: bool, msg: str):
        self.lbl_folder_status.setText(msg)
        self.lbl_folder_status.setStyleSheet(
            'color: #10b981;' if ok else 'color: #ef4444;'
        )

    def _populate_profiles(self):
        if not self._folder:
            return
        profiles = self._folder.char_profiles
        prev_data = self.combo_source.currentData()
        self.combo_source.blockSignals(True)
        self.combo_source.clear()
        for p in profiles:
            name = self._resolved_names.get(p.char_id, '')
            label = name if name else p.display_name
            self.combo_source.addItem(label, userData=p)
        self.combo_source.blockSignals(False)
        if prev_data:
            for i in range(self.combo_source.count()):
                if self.combo_source.itemData(i).char_id == prev_data.char_id:
                    self.combo_source.setCurrentIndex(i)
                    break
        elif profiles:
            self.combo_source.setCurrentIndex(0)
        self._on_source_changed()

    def _rebuild_targets(self):
        self.list_targets.clear()
        if not self._folder:
            return
        src = self.combo_source.currentData()
        src_id = src.char_id if src else None
        for p in self._folder.char_profiles:
            if p.char_id == src_id:
                continue
            row_widget = CharRowWidget(p)
            name = self._resolved_names.get(p.char_id, '')
            if name:
                row_widget.set_name(name)
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, row_widget.height()))
            item.setData(Qt.UserRole, p)
            self.list_targets.addItem(item)
            self.list_targets.setItemWidget(item, row_widget)
            row_widget.load_portrait()

    def _row_widget(self, item: QListWidgetItem) -> Optional[CharRowWidget]:
        return self.list_targets.itemWidget(item)

    def _get_selected_targets(self):
        targets = []
        for i in range(self.list_targets.count()):
            item = self.list_targets.item(i)
            w = self._row_widget(item)
            if w and w.is_checked():
                targets.append(item.data(Qt.UserRole))
        return targets

    def _select_all_targets(self):
        for i in range(self.list_targets.count()):
            w = self._row_widget(self.list_targets.item(i))
            if w:
                w.set_checked(True)

    def _clear_targets(self):
        for i in range(self.list_targets.count()):
            w = self._row_widget(self.list_targets.item(i))
            if w:
                w.set_checked(False)

    # ── Identity resolution ────────────────────────────────────────────────────

    def _start_identity_resolution(self):
        if not self._folder:
            return
        char_ids = [p.char_id for p in self._folder.char_profiles]
        from ui.tools.visual_clon_worker import IdentityResolveWorker
        self._identity_worker = IdentityResolveWorker(char_ids=char_ids, parent=self)
        self._identity_worker.names_ready.connect(self._on_names_ready)
        self._identity_worker.start()

    def _on_names_ready(self, names: dict):
        self._resolved_names.update(names)
        if not self._folder:
            return
        self.combo_source.blockSignals(True)
        for i in range(self.combo_source.count()):
            p = self.combo_source.itemData(i)
            if p:
                name = names.get(p.char_id, '')
                if name:
                    self.combo_source.setItemText(i, name)
        self.combo_source.blockSignals(False)
        src = self.combo_source.currentData()
        if src:
            name = names.get(src.char_id, '')
            self.source_card.update_profile(src, name_override=name)
        for i in range(self.list_targets.count()):
            item = self.list_targets.item(i)
            p = item.data(Qt.UserRole)
            w = self._row_widget(item)
            if p and w:
                name = names.get(p.char_id, '')
                if name:
                    w.set_name(name)
        resolved_count = sum(1 for v in names.values() if not v.startswith('Personaje '))
        logger.debug(f"[VC] Nombres resueltos: {resolved_count}/{len(names)}")

    # ── Slots ───────────────────────────────────────────────────────────────────

    def _on_detect(self):
        self._set_status("Buscando instalaciones de EVE Online…", ok=True)
        self._set_busy(True)
        self._scan_worker = self._make_scan_worker(path=None)
        self._scan_worker.start()

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de configuración de EVE"
        )
        if not path:
            return
        self._set_status(f"Escaneando: {path}", ok=True)
        self._set_busy(True)
        self._scan_worker = self._make_scan_worker(path=Path(path))
        self._scan_worker.start()

    def _make_scan_worker(self, path):
        from ui.tools.visual_clon_worker import ScanWorker
        w = ScanWorker(path=path, parent=self)
        w.status.connect(lambda m: logger.info(f"[VC] {m}"))
        w.finished.connect(self._on_scan_done)
        w.error.connect(self._on_scan_error)
        return w

    def _on_scan_done(self, folder):
        self._set_busy(False)
        self._folder = folder
        self._resolved_names.clear()
        self.edit_path.setText(str(folder.path))
        n = len(folder.char_profiles)
        self._show_folder_status(True, f"Válido — {n} perfil(es) de personaje encontrados.")
        if n == 0:
            self._set_status("No se encontraron perfiles (core_char_*.dat).", ok=False, warn=True)
        else:
            self._set_status(f"{n} perfiles encontrados. Resolviendo nombres…", ok=True)
        self._populate_profiles()
        self._set_action_enabled(n > 0)
        if n > 0:
            self._start_identity_resolution()

    def _on_scan_error(self, msg: str):
        self._set_busy(False)
        self._show_folder_status(False, msg)
        self._set_status(f"Error: {msg}", ok=False)

    def _on_source_changed(self):
        src = self.combo_source.currentData()
        if src:
            name = self._resolved_names.get(src.char_id, '')
            self.source_card.update_profile(src, name_override=name)
        else:
            self.source_card.update_profile(None)
        self._rebuild_targets()

    def _on_analyze(self):
        if not self._validate_selection():
            return
        src = self.combo_source.currentData()
        targets = self._get_selected_targets()
        src_name = self._resolved_names.get(src.char_id, src.display_name)
        target_names = [
            self._resolved_names.get(t.char_id, t.display_name) for t in targets
        ]
        lines = [
            f"Origen: {src_name} (ID {src.char_id})",
            f"Destinos ({len(targets)}): {', '.join(target_names)}",
            f"Archivo: {src.file_path.name} ({src.file_size // 1024} KB)",
            "",
            "Archivos destino (con backup previo):",
        ]
        from core.visual_clon_models import COPY_SECTIONS
        for t in targets:
            dst = src.file_path.parent / f"core_char_{t.char_id}.dat"
            exists = "existe" if dst.exists() else "no existe aún"
            tname = self._resolved_names.get(t.char_id, t.display_name)
            lines.append(f"  → {dst.name} — {tname} ({exists})")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Análisis — Visual Clon")
        msg_box.setText('\n'.join(lines))
        msg_box.exec()
        self._set_status("Análisis completado.", ok=True)

    def _on_simulate(self):
        self._run_clone(dry_run=True)

    def _on_apply(self):
        targets = self._get_selected_targets()
        src = self.combo_source.currentData()
        if not src or not targets:
            self._set_status("Selecciona origen y al menos un destino.", ok=False, warn=True)
            return
        src_name = self._resolved_names.get(src.char_id, src.display_name)
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirmar Visual Clon")
        msg.setText(
            f"¿Aplicar Visual Clon?\n\n"
            f"Origen: {src_name}\n"
            f"Destinos: {len(targets)} personaje(s)\n\n"
            f"Se creará backup automático antes de copiar.\n"
            f"⚠ Cierra el cliente EVE antes de aplicar."
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        if msg.exec() == QMessageBox.Yes:
            self._run_clone(dry_run=False)

    def _run_clone(self, dry_run: bool):
        if not self._validate_selection():
            return
        from core.visual_clon_service import build_copy_plan
        from ui.tools.visual_clon_worker import CloneWorker

        src = self.combo_source.currentData()
        targets = self._get_selected_targets()
        plan = build_copy_plan(source=src, targets=targets, dry_run=dry_run)

        mode_lbl = "SIMULACIÓN" if dry_run else "APLICANDO"
        src_name = self._resolved_names.get(src.char_id, src.display_name)
        logger.info(f"[VC] [{mode_lbl}] {src_name} → {len(targets)} destino(s)")
        self._set_status(f"[{mode_lbl}] Iniciando…", ok=True)

        self._set_busy(True)
        self._clone_worker = CloneWorker(plan=plan, parent=self)
        self._clone_worker.status.connect(lambda m: logger.info(f"[VC] {m}"))
        self._clone_worker.finished.connect(self._on_clone_done)
        self._clone_worker.error.connect(self._on_clone_error)
        self._clone_worker.start()

    def _on_clone_done(self, result):
        self._set_busy(False)
        if result.dry_run:
            self._set_status("Simulación completada. No se han modificado archivos.", ok=True)
        elif result.success:
            self._set_status(
                f"¡Visual Clon aplicado! {len(result.files_copied)} archivo(s) copiados, "
                f"{len(result.backups)} backup(s) creados.",
                ok=True,
            )
        else:
            detail = '; '.join(result.errors[:2])
            self._set_status(f"Completado con errores: {detail}", ok=False)
            if result.errors:
                QMessageBox.warning(self, "Errores — Visual Clon", '\n'.join(result.errors))

    def _on_clone_error(self, msg: str):
        self._set_busy(False)
        self._set_status(f"Error: {msg}", ok=False)
        QMessageBox.critical(self, "Error — Visual Clon", msg)

    def _on_restore(self):
        from core.visual_clon_backup import list_backups, restore_backup
        from PySide6.QtWidgets import QInputDialog
        backups = list_backups()
        if not backups:
            self._set_status("No hay backups disponibles.", ok=False, warn=True)
            return
        items = [
            f"{b.timestamp.strftime('%d/%m/%Y %H:%M:%S')} — "
            f"src:{b.source_char_id} → dst:{b.target_char_id} "
            f"({len(b.original_files)} archivo(s))"
            for b in backups
        ]
        item, ok = QInputDialog.getItem(
            self, "Restaurar backup", "Selecciona el backup a restaurar:", items, 0, False
        )
        if not ok:
            return
        record = backups[items.index(item)]
        conf = QMessageBox.question(
            self, "Confirmar restauración",
            f"¿Restaurar backup del {record.timestamp.strftime('%d/%m/%Y %H:%M')}?\n"
            f"Esto sobreescribirá los archivos del personaje destino {record.target_char_id}."
        )
        if conf != QMessageBox.Yes:
            return
        self._set_status("Restaurando backup…", ok=True)
        errors = restore_backup(record)
        if errors:
            self._set_status("Restauración con errores.", ok=False, warn=True)
            QMessageBox.warning(self, "Errores — Restauración", '\n'.join(errors))
        else:
            self._set_status("Backup restaurado correctamente.", ok=True)

    def _validate_selection(self) -> bool:
        if not self.combo_source.currentData():
            self._set_status("Selecciona un personaje origen.", ok=False, warn=True)
            return False
        if not self._get_selected_targets():
            self._set_status("Selecciona al menos un personaje destino.", ok=False, warn=True)
            return False
        return True
