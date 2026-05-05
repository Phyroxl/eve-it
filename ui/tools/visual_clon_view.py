"""Visual Clon — main UI widget.

Clona la configuración visual y el layout de ventanas de un personaje
EVE Online a otros personajes de forma segura, con backup automático.

Mejoras v2: portrait + nombre resuelto para origen y destinos.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QListWidget, QListWidgetItem, QTextEdit, QCheckBox,
    QFileDialog, QLineEdit, QSplitter, QAbstractItemView, QProgressBar,
    QScrollArea,
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
QTextEdit { background: #030508; color: #94a3b8; border: 1px solid #1e293b;
    border-radius: 3px; font-family: 'Consolas', monospace; font-size: 9px; }
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


# ── Reusable helper functions ──────────────────────────────────────────────────

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
    """Generate a pilot placeholder pixmap matching the dark theme."""
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
        placeholder = _make_portrait_placeholder(60)
        self.portrait_lbl.setPixmap(placeholder)
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
            pix = EveIconService.instance().get_portrait(
                char_id_int, size=64,
                callback=lambda p: self.set_portrait(p),
            )
            if pix and not pix.isNull():
                self.set_portrait(pix)
        except Exception as e:
            logger.debug(f"[VC] Portrait load src {profile.char_id}: {e}")


# ── Custom target row widget ───────────────────────────────────────────────────

class CharRowWidget(QWidget):
    """One row in the targets list: [checkbox] [portrait] [name / ID]."""

    _PORTRAIT_SIZE = 48

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setFixedHeight(62)
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
        if pixmap and not pixmap.isNull():
            s = self._PORTRAIT_SIZE - 4
            scaled = pixmap.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.portrait_lbl.setPixmap(scaled)

    def set_name(self, name: str):
        if name:
            self.name_lbl.setText(name)

    def load_portrait(self):
        try:
            from core.eve_icon_service import EveIconService
            char_id_int = int(self.profile.char_id)
            pix = EveIconService.instance().get_portrait(
                char_id_int, size=64,
                callback=lambda p: self.set_portrait(p),
            )
            if pix and not pix.isNull():
                self.set_portrait(pix)
        except Exception as e:
            logger.debug(f"[VC] Portrait load dst {self.profile.char_id}: {e}")


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
        # {char_id: name} resolved from ESI
        self._resolved_names: Dict[str, str] = {}

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(_label("VISUAL CLON", 'VCTitle'))
        hdr.addStretch()
        root.addLayout(hdr)

        sub = _label(
            "Clona la configuración visual y el layout de ventanas de un "
            "personaje EVE a otros personajes.", 'VCSub'
        )
        sub.setWordWrap(True)
        root.addWidget(sub)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet("QSplitter::handle { background: #1e293b; }")
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([530, 330])
        root.addWidget(splitter, 1)

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

    # ── Left panel ─────────────────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        # ── EVE folder ───────────────────────────────────────────────────────
        fp, fl = _panel()
        fl.addWidget(_label("CARPETA DE CONFIGURACIÓN EVE", 'VCSectionLabel'))
        self.edit_path = QLineEdit()
        self.edit_path.setPlaceholderText("Ruta a la carpeta settings_Default de EVE…")
        self.edit_path.setReadOnly(True)
        fl.addWidget(self.edit_path)
        btn_row = QHBoxLayout()
        self.btn_detect = QPushButton("Detectar automáticamente")
        self.btn_detect.setObjectName("VCSecondary")
        self.btn_detect.setCursor(Qt.PointingHandCursor)
        self.btn_browse = QPushButton("Seleccionar carpeta…")
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

        # ── Source selector + card ───────────────────────────────────────────
        sp, sl = _panel()
        sl.addWidget(_label("PERSONAJE ORIGEN", 'VCSectionLabel'))
        self.combo_source = QComboBox()
        self.combo_source.setPlaceholderText("— seleccionar origen —")
        sl.addWidget(self.combo_source)
        self.source_card = CharSourceCard()
        sl.addWidget(self.source_card)
        lay.addWidget(sp)
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)

        # ── Targets list ─────────────────────────────────────────────────────
        tp, tl = _panel()
        tl.addWidget(_label("PERSONAJES DESTINO", 'VCSectionLabel'))
        self.list_targets = QListWidget()
        self.list_targets.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_targets.setMinimumHeight(130)
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

        # ── Sections ─────────────────────────────────────────────────────────
        sec_p, sec_l = _panel()
        sec_l.addWidget(_label("SECCIONES A COPIAR", 'VCSectionLabel'))
        note = _label(
            "En v1, el archivo de perfil EVE es binario — se copia completo "
            "incluyendo todas las secciones.", 'VCSub'
        )
        note.setWordWrap(True)
        sec_l.addWidget(note)
        from core.visual_clon_models import COPY_SECTIONS
        self._section_checks: List[QCheckBox] = []
        for _, sec_name, sec_desc in COPY_SECTIONS:
            cb = QCheckBox(sec_name)
            cb.setChecked(True)
            cb.setToolTip(sec_desc)
            sec_l.addWidget(cb)
            self._section_checks.append(cb)
        lay.addWidget(sec_p)

        # ── Safety ────────────────────────────────────────────────────────────
        safe_p, safe_l = _panel()
        safe_l.addWidget(_label("OPCIONES DE SEGURIDAD", 'VCSectionLabel'))
        self.chk_backup = QCheckBox("Crear backup antes de aplicar (recomendado)")
        self.chk_backup.setChecked(True)
        self.chk_backup.setEnabled(False)
        safe_l.addWidget(self.chk_backup)
        self.chk_validate = QCheckBox("Validar archivos antes de copiar")
        self.chk_validate.setChecked(True)
        safe_l.addWidget(self.chk_validate)
        lay.addWidget(safe_p)

        scroll.setWidget(w)
        return scroll

    # ── Right panel ────────────────────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_label("RESULTADOS / LOG", 'VCSectionLabel'))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(200)
        lay.addWidget(self.log_view, 1)
        self.lbl_result = _label("", 'VCStatusOk')
        self.lbl_result.setWordWrap(True)
        lay.addWidget(self.lbl_result)
        return w

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _log(self, msg: str, color: str = '#94a3b8'):
        self.log_view.append(f'<span style="color:{color};">{msg}</span>')
        logger.info(f"[VC UI] {msg}")

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
        # Update combo labels
        self.combo_source.blockSignals(True)
        for i in range(self.combo_source.count()):
            p = self.combo_source.itemData(i)
            if p:
                name = names.get(p.char_id, '')
                if name:
                    self.combo_source.setItemText(i, name)
        self.combo_source.blockSignals(False)
        # Update source card
        src = self.combo_source.currentData()
        if src:
            name = names.get(src.char_id, '')
            self.source_card.update_profile(src, name_override=name)
        # Update target row names
        for i in range(self.list_targets.count()):
            item = self.list_targets.item(i)
            p = item.data(Qt.UserRole)
            w = self._row_widget(item)
            if p and w:
                name = names.get(p.char_id, '')
                if name:
                    w.set_name(name)
        resolved_count = sum(1 for cid in names if not names[cid].startswith('Personaje '))
        self._log(f"Nombres resueltos: {resolved_count}/{len(names)}", '#00c8ff')

    # ── Slots ───────────────────────────────────────────────────────────────────

    def _on_detect(self):
        self.log_view.clear()
        self._log("Buscando instalaciones de EVE Online…", '#00c8ff')
        self._set_busy(True)
        self._scan_worker = self._make_scan_worker(path=None)
        self._scan_worker.start()

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de configuración de EVE"
        )
        if not path:
            return
        self.log_view.clear()
        self._log(f"Escaneando: {path}", '#00c8ff')
        self._set_busy(True)
        self._scan_worker = self._make_scan_worker(path=Path(path))
        self._scan_worker.start()

    def _make_scan_worker(self, path):
        from ui.tools.visual_clon_worker import ScanWorker
        w = ScanWorker(path=path, parent=self)
        w.status.connect(lambda m: self._log(m))
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
        self._log(f"Carpeta: {folder.path}", '#10b981')
        self._log(f"Perfiles encontrados: {n}", '#10b981')
        self._populate_profiles()
        self._set_action_enabled(n > 0)
        if n == 0:
            self._log("No se encontraron perfiles (core_char_*.dat).", '#f59e0b')
        else:
            self._log("Resolviendo nombres de personaje…", '#64748b')
            self._start_identity_resolution()

    def _on_scan_error(self, msg: str):
        self._set_busy(False)
        self._show_folder_status(False, msg)
        self._log(f"ERROR: {msg}", '#ef4444')

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
        self.log_view.clear()
        src = self.combo_source.currentData()
        targets = self._get_selected_targets()
        src_name = self._resolved_names.get(src.char_id, src.display_name)
        self._log("Analizando…", '#00c8ff')
        self._log(f"Origen: {src_name} (ID {src.char_id})")
        target_names = [
            self._resolved_names.get(t.char_id, t.display_name) for t in targets
        ]
        self._log(f"Destinos ({len(targets)}): {', '.join(target_names)}")
        self._log(f"Archivo origen: {src.file_path.name} ({src.file_size // 1024} KB)")
        self._log("Secciones incluidas en el archivo de perfil EVE:")
        from core.visual_clon_models import COPY_SECTIONS
        for cb, (_, sec_name, _) in zip(self._section_checks, COPY_SECTIONS):
            self._log(f"  {'✓' if cb.isChecked() else '○'} {sec_name}")
        self._log("Archivos destino (con backup previo):")
        for t in targets:
            dst = src.file_path.parent / f"core_char_{t.char_id}.dat"
            exists = "existe" if dst.exists() else "no existe aún"
            tname = self._resolved_names.get(t.char_id, t.display_name)
            self._log(f"  → {dst.name} — {tname} ({exists})")
        self._log("Análisis completado.", '#10b981')
        self.lbl_result.setText("Análisis completado.")
        self.lbl_result.setStyleSheet('color: #10b981;')

    def _on_simulate(self):
        self._run_clone(dry_run=True)

    def _on_apply(self):
        from PySide6.QtWidgets import QMessageBox
        targets = self._get_selected_targets()
        src = self.combo_source.currentData()
        if not src or not targets:
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

        self.log_view.clear()
        mode_lbl = "SIMULACIÓN" if dry_run else "APLICANDO"
        src_name = self._resolved_names.get(src.char_id, src.display_name)
        self._log(f"[{mode_lbl}] Origen: {src_name}", '#00c8ff')
        self._log(f"[{mode_lbl}] Destinos: {len(targets)}", '#00c8ff')

        self._set_busy(True)
        self._clone_worker = CloneWorker(plan=plan, parent=self)
        self._clone_worker.status.connect(self._log)
        self._clone_worker.finished.connect(self._on_clone_done)
        self._clone_worker.error.connect(self._on_clone_error)
        self._clone_worker.start()

    def _on_clone_done(self, result):
        self._set_busy(False)
        color = '#10b981' if result.success else '#f59e0b'
        if result.dry_run:
            msg = "Simulación completada. No se han modificado archivos."
        elif result.success:
            msg = (f"¡Visual Clon aplicado! {len(result.files_copied)} archivo(s) copiados, "
                   f"{len(result.backups)} backup(s) creados.")
        else:
            msg = f"Completado con errores: {'; '.join(result.errors[:2])}"
        self.lbl_result.setText(msg)
        self.lbl_result.setStyleSheet(f'color: {color};')
        for err in result.errors:
            self._log(f"ERROR: {err}", '#ef4444')

    def _on_clone_error(self, msg: str):
        self._set_busy(False)
        self._log(f"ERROR: {msg}", '#ef4444')
        self.lbl_result.setText(f"Error: {msg}")
        self.lbl_result.setStyleSheet('color: #ef4444;')

    def _on_restore(self):
        from core.visual_clon_backup import list_backups, restore_backup
        from PySide6.QtWidgets import QInputDialog
        backups = list_backups()
        if not backups:
            self._log("No hay backups disponibles.", '#f59e0b')
            self.lbl_result.setText("No hay backups disponibles.")
            self.lbl_result.setStyleSheet('color: #f59e0b;')
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
        from PySide6.QtWidgets import QMessageBox
        conf = QMessageBox.question(
            self, "Confirmar restauración",
            f"¿Restaurar backup del {record.timestamp.strftime('%d/%m/%Y %H:%M')}?\n"
            f"Esto sobreescribirá los archivos del personaje destino {record.target_char_id}."
        )
        if conf != QMessageBox.Yes:
            return
        self.log_view.clear()
        self._log(f"Restaurando backup: {record.backup_dir.name}…", '#00c8ff')
        errors = restore_backup(record)
        if errors:
            for e in errors:
                self._log(f"ERROR: {e}", '#ef4444')
            self.lbl_result.setText("Restauración con errores.")
            self.lbl_result.setStyleSheet('color: #f59e0b;')
        else:
            self._log("Backup restaurado correctamente.", '#10b981')
            self.lbl_result.setText("Backup restaurado.")
            self.lbl_result.setStyleSheet('color: #10b981;')

    def _validate_selection(self) -> bool:
        if not self.combo_source.currentData():
            self._log("Selecciona un personaje origen.", '#f59e0b')
            return False
        if not self._get_selected_targets():
            self._log("Selecciona al menos un personaje destino.", '#f59e0b')
            return False
        return True
