"""QThread workers for Visual Clon — scan and clone operations."""
import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger('eve.visual_clon')


class ScanWorker(QThread):
    """Scans EVE settings folders in a background thread."""
    status = Signal(str)
    finished = Signal(object)   # EveSettingsFolder or None
    error = Signal(str)

    def __init__(self, path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._path = path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from core.visual_clon_service import (
                detect_eve_settings_folders, scan_settings_folder,
                validate_settings_folder,
            )

            if self._path:
                self.status.emit(f"Escaneando: {self._path}")
                ok, msg = validate_settings_folder(self._path)
                if not ok:
                    self.error.emit(msg)
                    return
                folder = scan_settings_folder(self._path)
                self.finished.emit(folder)
            else:
                self.status.emit("Buscando instalaciones de EVE Online…")
                folders = detect_eve_settings_folders()
                if self._cancelled:
                    return
                if not folders:
                    self.error.emit(
                        "No se encontraron carpetas de configuración de EVE. "
                        "Selecciona la carpeta manualmente."
                    )
                    return
                self.status.emit(
                    f"Encontradas {len(folders)} instalación(es). "
                    f"Usando: {folders[0].path}"
                )
                self.finished.emit(folders[0])

        except Exception as e:
            logger.error(f"[SCAN WORKER] {e}", exc_info=True)
            self.error.emit(str(e))


class CloneWorker(QThread):
    """Executes a Visual Clon operation in a background thread."""
    status = Signal(str)
    finished = Signal(object)   # CloneResult
    error = Signal(str)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self._plan = plan
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from core.visual_clon_service import execute_clone
            mode = "SIMULACIÓN" if self._plan.dry_run else "APLICANDO"
            self.status.emit(f"[{mode}] Iniciando…")
            result = execute_clone(self._plan)
            for line in result.log_lines:
                self.status.emit(line)
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"[CLONE WORKER] {e}", exc_info=True)
            self.error.emit(str(e))
