"""Visual Clon — main UI widget.

Clona la configuración visual y el layout de ventanas de un personaje
EVE Online a otros personajes de forma segura, con backup automático.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QListWidget, QListWidgetItem, QTextEdit, QCheckBox,
    QFileDialog, QLineEdit, QScrollArea, QSizePolicy, QSplitter,
    QAbstractItemView, QProgressBar,
)

logger = logging.getLogger('eve.visual_clon')

_STYLE = """
QWidget { background: #05070a; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; font-size: 10px; }
QFrame#VCPanel { background: #0b1016; border: 1px solid #1e293b; border-radius: 3px; }
QLabel#VCTitle { color: #00c8ff; font-size: 14px; font-weight: 800; letter-spacing: 2px; }
QLabel#VCSub { color: #64748b; font-size: 10px; }
QLabel#VCSectionLabel { color: #94a3b8; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 4px; }
QLabel#VCStatusOk { color: #10b981; font-size: 10px; }
QLabel#VCStatusErr { color: #ef4444; font-size: 10px; }
QPushButton#VCPrimary {
    background: #00c8ff; color: #05070a; font-weight: 800;
    border: none; border-radius: 3px; padding: 7px 16px;
}
QPushButton#VCPrimary:hover { background: #38d4ff; }
QPushButton#VCPrimary:disabled { background: #1e293b; color: #64748b; }
QPushButton#VCSecondary {
    background: #0d1626; color: #00c8ff; border: 1px solid #1e293b;
    border-radius: 3px; padding: 6px 14px;
}
QPushButton#VCSecondary:hover { border-color: #00c8ff; }
QPushButton#VCSecondary:disabled { color: #64748b; border-color: #1e293b; }
QPushButton#VCDanger {
    background: #0d1626; color: #ef4444; border: 1px solid #1e293b;
    border-radius: 3px; padding: 6px 14px;
}
QPushButton#VCDanger:hover { border-color: #ef4444; }
QPushButton#VCDanger:disabled { color: #64748b; border-color: #1e293b; }
QComboBox {
    background: #0d1626; color: #e2e8f0; border: 1px solid #1e293b;
    border-radius: 3px; padding: 5px 8px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #0b1016; color: #e2e8f0; border: 1px solid #1e293b; }
QListWidget {
    background: #0d1626; color: #e2e8f0; border: 1px solid #1e293b;
    border-radius: 3px;
}
QListWidget::item { padding: 4px 6px; }
QListWidget::item:selected { background: #1e293b; color: #00c8ff; }
QListWidget::item:hover { background: #111827; }
QLineEdit {
    background: #0d1626; color: #e2e8f0; border: 1px solid #1e293b;
    border-radius: 3px; padding: 5px 8px;
}
QTextEdit {
    background: #030508; color: #94a3b8; border: 1px solid #1e293b;
    border-radius: 3px; font-family: 'Consolas', monospace; font-size: 9px;
}
QCheckBox { color: #e2e8f0; spacing: 6px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #1e293b; background: #0d1626; border-radius: 2px; }
QCheckBox::indicator:checked { background: #00c8ff; border-color: #00c8ff; }
QCheckBox::indicator:disabled { background: #0d1626; border-color: #111827; }
QProgressBar { background: #0d1626; border: 1px solid #1e293b; border-radius: 2px; height: 4px; text-align: center; }
QProgressBar::chunk { background: #00c8ff; border-radius: 2px; }
QScrollBar:vertical { background: #0b1016; width: 6px; }
QScrollBar::handle:vertical { background: #1e293b; border-radius: 3px; }
"""


def _panel(layout_type='v') -> tuple:
    f = QFrame()
    f.setObjectName("VCPanel")
    lay = QVBoxLayout(f) if layout_type == 'v' else QHBoxLayout(f)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(6)
    return f, lay


def _label(text: str, obj: str = '') -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    return lb


class VisualClonView(QWidget):
    """Main Visual Clon widget, embedded inside a frameless window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLE)
        self.setObjectName("VisualClonView")

        self._folder: Optional[object] = None   # EveSettingsFolder
        self._scan_worker = None
        self._clone_worker = None

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # ── Header ─────────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = _label("VISUAL CLON", 'VCTitle')
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        sub = _label(
            "Clona la configuración visual y el layout de ventanas de un "
            "personaje EVE a otros personajes.", 'VCSub'
        )
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Main splitter (left config / right log) ────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet("QSplitter::handle { background: #1e293b; }")

        left = self._build_left()
        right = self._build_right()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 340])

        root.addWidget(splitter, 1)

        # ── Bottom buttons ──────────────────────────────────────────────────────
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

        # ── Progress bar ────────────────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        # ── Connections ─────────────────────────────────────────────────────────
        self.btn_analyze.clicked.connect(self._on_analyze)
        self.btn_simulate.clicked.connect(self._on_simulate)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_restore.clicked.connect(self._on_restore)

        self._set_action_enabled(False)

    def _build_left(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        # ── EVE config folder ───────────────────────────────────────────────────
        fp, fl = _panel()
        fl.addWidget(_label("CARPETA DE CONFIGURACIÓN EVE", 'VCSectionLabel'))

        path_row = QHBoxLayout()
        self.edit_path = QLineEdit()
        self.edit_path.setPlaceholderText("Ruta a la carpeta settings_Default de EVE…")
        self.edit_path.setReadOnly(True)
        path_row.addWidget(self.edit_path, 1)
        fl.addLayout(path_row)

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

        # ── Source ──────────────────────────────────────────────────────────────
        sp, sl = _panel()
        sl.addWidget(_label("PERSONAJE ORIGEN", 'VCSectionLabel'))
        self.combo_source = QComboBox()
        self.combo_source.setPlaceholderText("— seleccionar origen —")
        sl.addWidget(self.combo_source)
        self.lbl_source_info = _label("", 'VCSub')
        sl.addWidget(self.lbl_source_info)
        lay.addWidget(sp)

        self.combo_source.currentIndexChanged.connect(self._on_source_changed)

        # ── Targets ─────────────────────────────────────────────────────────────
        tp, tl = _panel()
        tl.addWidget(_label("PERSONAJES DESTINO", 'VCSectionLabel'))
        self.list_targets = QListWidget()
        self.list_targets.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_targets.setMinimumHeight(100)
        tl.addWidget(self.list_targets, 1)

        trow = QHBoxLayout()
        btn_all = QPushButton("Seleccionar todos")
        btn_all.setObjectName("VCSecondary")
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_clear = QPushButton("Limpiar")
        btn_clear.setObjectName("VCSecondary")
        btn_clear.setCursor(Qt.PointingHandCursor)
        trow.addWidget(btn_all)
        trow.addWidget(btn_clear)
        trow.addStretch()
        tl.addLayout(trow)
        lay.addWidget(tp, 1)

        btn_all.clicked.connect(self._select_all_targets)
        btn_clear.clicked.connect(self._clear_targets)

        # ── Sections ─────────────────────────────────────────────────────────────
        sec_p, sec_l = _panel()
        sec_l.addWidget(_label("SECCIONES A COPIAR", 'VCSectionLabel'))

        note = _label(
            "En v1, el archivo de perfil de EVE es binario — se copia completo "
            "incluyendo todas las secciones seleccionadas.", 'VCSub'
        )
        note.setWordWrap(True)
        sec_l.addWidget(note)

        from core.visual_clon_models import COPY_SECTIONS
        self._section_checks: List[QCheckBox] = []
        for sec_id, sec_name, sec_desc in COPY_SECTIONS:
            cb = QCheckBox(sec_name)
            cb.setChecked(True)
            cb.setToolTip(sec_desc)
            sec_l.addWidget(cb)
            self._section_checks.append(cb)

        lay.addWidget(sec_p)

        # ── Safety options ────────────────────────────────────────────────────────
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
        return w

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

    def _populate_profiles(self):
        if not self._folder:
            return
        profiles = self._folder.char_profiles

        src_idx = self.combo_source.currentIndex()
        src_data = self.combo_source.currentData()
        self.combo_source.blockSignals(True)
        self.combo_source.clear()
        for p in profiles:
            self.combo_source.addItem(p.display_name, userData=p)
        self.combo_source.blockSignals(False)
        if src_data and any(p.char_id == src_data.char_id for p in profiles):
            for i in range(self.combo_source.count()):
                if self.combo_source.itemData(i).char_id == src_data.char_id:
                    self.combo_source.setCurrentIndex(i)
                    break
        elif profiles:
            self.combo_source.setCurrentIndex(0)

        self._rebuild_targets()

    def _rebuild_targets(self):
        self.list_targets.clear()
        if not self._folder:
            return
        src = self.combo_source.currentData()
        src_id = src.char_id if src else None
        for p in self._folder.char_profiles:
            if p.char_id == src_id:
                continue
            item = QListWidgetItem(p.display_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, p)
            self.list_targets.addItem(item)

    def _get_selected_targets(self):
        targets = []
        for i in range(self.list_targets.count()):
            item = self.list_targets.item(i)
            if item.checkState() == Qt.Checked:
                targets.append(item.data(Qt.UserRole))
        return targets

    def _select_all_targets(self):
        for i in range(self.list_targets.count()):
            self.list_targets.item(i).setCheckState(Qt.Checked)

    def _clear_targets(self):
        for i in range(self.list_targets.count()):
            self.list_targets.item(i).setCheckState(Qt.Unchecked)

    def _show_folder_status(self, ok: bool, msg: str):
        self.lbl_folder_status.setObjectName('VCStatusOk' if ok else 'VCStatusErr')
        self.lbl_folder_status.setText(msg)
        self.lbl_folder_status.setStyleSheet(
            'color: #10b981;' if ok else 'color: #ef4444;'
        )

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
        self.edit_path.setText(str(folder.path))
        n = len(folder.char_profiles)
        self._show_folder_status(True, f"Válido — {n} perfil(es) de personaje encontrados.")
        self._log(f"Carpeta: {folder.path}", '#10b981')
        self._log(f"Perfiles encontrados: {n}", '#10b981')
        self._populate_profiles()
        self._set_action_enabled(n > 0)
        if n == 0:
            self._log("No se encontraron perfiles de personaje (core_char_*.dat).", '#f59e0b')

    def _on_scan_error(self, msg: str):
        self._set_busy(False)
        self._show_folder_status(False, msg)
        self._log(f"ERROR: {msg}", '#ef4444')

    def _on_source_changed(self):
        src = self.combo_source.currentData()
        if src:
            modified = src.modified.strftime('%d/%m/%Y %H:%M') if src.modified else '?'
            size_kb = src.file_size // 1024
            self.lbl_source_info.setText(
                f"ID: {src.char_id} | Tamaño: {size_kb} KB | Modificado: {modified}"
            )
        else:
            self.lbl_source_info.setText('')
        self._rebuild_targets()

    def _on_analyze(self):
        if not self._validate_selection():
            return
        self.log_view.clear()
        src = self.combo_source.currentData()
        targets = self._get_selected_targets()
        self._log(f"Analizando…", '#00c8ff')
        self._log(f"Origen: {src.display_name}")
        self._log(f"Destinos ({len(targets)}): {', '.join(t.display_name for t in targets)}")
        self._log(f"Archivo origen: {src.file_path.name} ({src.file_size // 1024} KB)")
        self._log("Secciones incluidas en el archivo de perfil EVE:")
        from core.visual_clon_models import COPY_SECTIONS
        for cb, (sec_id, sec_name, _) in zip(self._section_checks, COPY_SECTIONS):
            status = '✓' if cb.isChecked() else '○'
            self._log(f"  {status} {sec_name}")
        self._log("Archivos destino que serían sobreescritos (con backup previo):")
        for t in targets:
            dst = src.file_path.parent / f"core_char_{t.char_id}.dat"
            exists = "existe" if dst.exists() else "no existe aún"
            self._log(f"  → {dst.name} ({exists})")
        self._log("Análisis completado. Usa 'Simular copia' o 'Aplicar Visual Clon'.", '#10b981')
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
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirmar Visual Clon")
        msg.setText(
            f"¿Aplicar Visual Clon?\n\n"
            f"Origen: {src.display_name}\n"
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
        self._log(f"[{mode_lbl}] Origen: {src.display_name}", '#00c8ff')
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
        idx = items.index(item)
        record = backups[idx]

        from PySide6.QtWidgets import QMessageBox
        conf = QMessageBox.question(
            self, "Confirmar restauración",
            f"¿Restaurar backup del {record.timestamp.strftime('%d/%m/%Y %H:%M')}?\n"
            f"Esto sobreescribirá los archivos actuales del personaje destino {record.target_char_id}."
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
        src = self.combo_source.currentData()
        if not src:
            self._log("Selecciona un personaje origen.", '#f59e0b')
            return False
        targets = self._get_selected_targets()
        if not targets:
            self._log("Selecciona al menos un personaje destino.", '#f59e0b')
            return False
        return True
