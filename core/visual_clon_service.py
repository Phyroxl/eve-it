"""Core service for Visual Clon — EVE client layout cloning tool.

Detects EVE settings folders, discovers char profiles, and performs
safe copy operations with automatic backup.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from core.visual_clon_models import (
    EveCharProfile, EveSettingsFolder, CopyPlan, CloneResult, BackupRecord,
)
from core.visual_clon_backup import create_backup

logger = logging.getLogger('eve.visual_clon')


# ── Path discovery ─────────────────────────────────────────────────────────────

def _candidate_paths() -> List[Path]:
    candidates: List[Path] = []

    local_app = Path(os.environ.get('LOCALAPPDATA', ''))
    ccp_local = local_app / 'CCP' / 'EVE'
    if ccp_local.is_dir():
        try:
            for child in ccp_local.iterdir():
                if not child.is_dir():
                    continue
                settings = child / 'settings_Default'
                if settings.is_dir():
                    candidates.append(settings)
                elif any(
                    re.match(r'^core_char_\d+\.dat$', f.name)
                    for f in child.iterdir() if f.is_file()
                ):
                    candidates.append(child)
        except Exception:
            pass

    appdata = Path(os.environ.get('APPDATA', ''))
    ccp_appdata = appdata / 'CCP' / 'EVE'
    if ccp_appdata.is_dir():
        try:
            for child in ccp_appdata.iterdir():
                if not child.is_dir():
                    continue
                settings = child / 'settings_Default'
                if settings.is_dir():
                    candidates.append(settings)
        except Exception:
            pass

    try:
        import ctypes, ctypes.wintypes as wt
        buf = ctypes.create_unicode_buffer(wt.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buf)
        docs_eve = Path(buf.value) / 'EVE'
        if docs_eve.is_dir():
            for child in docs_eve.iterdir():
                if child.is_dir():
                    settings = child / 'settings_Default'
                    if settings.is_dir():
                        candidates.append(settings)
    except Exception:
        pass

    return candidates


def detect_eve_settings_folders() -> List[EveSettingsFolder]:
    """Auto-detect all valid EVE settings folders on this system."""
    found: List[EveSettingsFolder] = []
    seen: set = set()

    for path in _candidate_paths():
        try:
            real = path.resolve()
        except Exception:
            real = path
        if real in seen:
            continue
        seen.add(real)

        folder = scan_settings_folder(path)
        if folder.is_valid():
            found.append(folder)
            logger.info(f"[DETECT] {path} — {len(folder.char_profiles)} profile(s)")
        else:
            logger.debug(f"[DETECT] No profiles at {path}")

    return found


def scan_settings_folder(path: Path) -> EveSettingsFolder:
    """Scan a folder and return all discovered EVE char/user profiles."""
    folder = EveSettingsFolder(path=path)
    try:
        for f in path.iterdir():
            if not f.is_file():
                continue
            m = re.match(r'^core_char_(\d+)\.dat$', f.name)
            if m:
                stat = f.stat()
                from datetime import datetime as _dt
                profile = EveCharProfile(
                    char_id=m.group(1),
                    file_path=f,
                    file_size=stat.st_size,
                    modified=_dt.fromtimestamp(stat.st_mtime),
                )
                folder.char_profiles.append(profile)
                continue
            m2 = re.match(r'^core_user_(\d+)\.dat$', f.name)
            if m2:
                folder.user_profile_ids.append(m2.group(1))
    except PermissionError as e:
        logger.warning(f"[SCAN] Permission denied: {path}: {e}")
    except Exception as e:
        logger.error(f"[SCAN] Error scanning {path}: {e}")

    folder.char_profiles.sort(key=lambda p: p.char_id)
    return folder


def validate_settings_folder(path: Path) -> Tuple[bool, str]:
    """Return (is_valid, message). Does not modify any files."""
    if not path.is_dir():
        return False, "La carpeta no existe."
    try:
        files = list(path.iterdir())
    except PermissionError:
        return False, "Sin permisos para leer la carpeta."

    char_files = [f for f in files if re.match(r'^core_char_\d+\.dat$', f.name)]
    if not char_files:
        return False, (
            "No se encontraron archivos de perfil EVE (core_char_*.dat). "
            "Verifica que esta es la carpeta correcta de configuración de EVE."
        )
    return True, f"Carpeta válida — {len(char_files)} perfil(es) de personaje."


def _md5(path: Path) -> str:
    """Compute MD5 hex digest of a file. Returns '' on error."""
    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ''


def is_eve_running() -> bool:
    """Return True if any EVE Online process is running (best-effort, Windows only)."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        # Check for 'exefile.exe' (EVE launcher/client process name)
        eve_titles: list = []

        def _enum_cb(hwnd, _):
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            class_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 256)
            if class_buf.value == 'trinityWindow':
                eve_titles.append(hwnd)
            return True

        ctypes.windll.user32.EnumWindows(
            ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(_enum_cb), 0
        )
        return bool(eve_titles)
    except Exception:
        return False


def build_copy_plan(
    source: EveCharProfile,
    targets: List[EveCharProfile],
    dry_run: bool = True,
) -> CopyPlan:
    """Build a CopyPlan without executing any file operations.

    Only core_char_*.dat is copied (character-specific layout/settings).
    core_user_*.dat files are account-scoped and shared across multiple
    characters; copying them by char_id would produce invalid filenames
    and corrupt account-level settings.
    """
    files_to_copy = [source.file_path] if source.file_path.exists() else []
    size = sum(f.stat().st_size for f in files_to_copy if f.exists())
    return CopyPlan(
        source=source,
        targets=[t for t in targets if t.char_id != source.char_id],
        dry_run=dry_run,
        files_to_copy=files_to_copy,
        estimated_size_bytes=size,
    )


def execute_clone(plan: CopyPlan) -> CloneResult:
    """Execute (or simulate) a Visual Clon operation."""
    result = CloneResult(dry_run=plan.dry_run, success=True)

    def _log(msg: str):
        result.log_lines.append(msg)
        logger.info(f"[CLONE] {msg}")

    if not plan.targets:
        result.errors.append("No hay personajes destino seleccionados.")
        result.success = False
        return result

    if not plan.files_to_copy:
        result.errors.append("Archivo de origen no encontrado.")
        result.success = False
        return result

    for f in plan.files_to_copy:
        if not f.exists():
            result.errors.append(f"Archivo origen no encontrado: {f.name}")
            result.success = False
            return result

    # Warn if EVE is running — it may overwrite settings on close
    if not plan.dry_run and is_eve_running():
        msg = ("WARNING EVE RUNNING — El cliente EVE está abierto. "
               "Ciérralo antes de aplicar para evitar que sobrescriba los cambios al cerrar.")
        _log(msg)
        result.log_lines.append(msg)

    if plan.dry_run:
        _log(f"[SIMULACIÓN] Origen: {plan.source.display_name}")
        _log(f"[SIMULACIÓN] Archivos a copiar: {[f.name for f in plan.files_to_copy]}")
        for target in plan.targets:
            for src in plan.files_to_copy:
                dst = src.parent / f"core_char_{target.char_id}.dat"
                _log(f"[SIMULACIÓN] {src.name} → {dst.name}")
            result.files_skipped.extend(plan.files_to_copy)
        _log("[SIMULACIÓN] Ningún archivo modificado. EVE debe estar cerrado para aplicar.")
        return result

    _log(f"VISUAL CLON SOURCE profile={plan.source.file_path.name} char={plan.source.display_name}")
    _log(f"Destinos: {', '.join(t.display_name for t in plan.targets)}")

    for target in plan.targets:
        for src_file in plan.files_to_copy:
            target_file = src_file.parent / f"core_char_{target.char_id}.dat"

            _log(f"VISUAL CLON DEST profile={target_file.name} char={target.display_name}")

            # Backup existing destination file
            if target_file.exists():
                try:
                    backup = create_backup(
                        source_char_id=plan.source.char_id,
                        target_char_id=target.char_id,
                        files_to_backup=[target_file],
                    )
                    result.backups.append(backup)
                    _log(f"BACKUP CREATED path={backup.backup_dir}")
                except Exception as e:
                    err = f"Error creando backup para {target.display_name}: {e}"
                    result.errors.append(err)
                    _log(f"ERROR: {err}")
                    result.success = False
                    continue

            try:
                src_hash = _md5(src_file)
                _log(f"COPY FILE source={src_file.name} dest={target_file.name}")
                shutil.copy2(src_file, target_file)
                result.files_copied.append(target_file)
                # Verify hash after copy
                dst_hash = _md5(target_file)
                if src_hash and dst_hash:
                    if src_hash == dst_hash:
                        _log(f"VERIFY HASH OK {target_file.name} md5={dst_hash[:8]}…")
                    else:
                        _log(f"VERIFY HASH FAIL {target_file.name} src={src_hash[:8]} dst={dst_hash[:8]}")
                        result.errors.append(f"Hash mismatch after copy: {target_file.name}")
            except Exception as e:
                err = f"Error copiando a {target_file.name}: {e}"
                result.errors.append(err)
                _log(f"ERROR: {err}")
                result.success = False

    if result.success and result.files_copied:
        _log("¡Visual Clon aplicado con éxito!")
    elif not result.files_copied and not result.errors:
        _log("Sin cambios realizados.")
    else:
        _log(f"Completado con {len(result.errors)} error(es). Revisa los backups.")

    return result
