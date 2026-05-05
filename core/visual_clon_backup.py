"""Backup management for Visual Clon."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from core.visual_clon_models import BackupRecord

logger = logging.getLogger('eve.visual_clon.backup')

_PROJECT_ROOT = Path(__file__).parent.parent
_BACKUP_ROOT = _PROJECT_ROOT / 'config' / 'visual_clon_backups'


def get_backup_root() -> Path:
    try:
        _BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        return _BACKUP_ROOT
    except Exception:
        import tempfile
        fallback = Path(tempfile.gettempdir()) / 'eve_visual_clon_backups'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def create_backup(source_char_id: str, target_char_id: str,
                  files_to_backup: List[Path]) -> BackupRecord:
    now = datetime.now()
    ts = now.strftime('%Y%m%d_%H%M%S')
    backup_dir = get_backup_root() / f"{ts}_src{source_char_id}_dst{target_char_id}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    record = BackupRecord(
        backup_dir=backup_dir,
        timestamp=now,
        source_char_id=source_char_id,
        target_char_id=target_char_id,
    )

    for src_file in files_to_backup:
        if not src_file.exists():
            continue
        dst = backup_dir / src_file.name
        try:
            shutil.copy2(src_file, dst)
            record.original_files.append(src_file)
            logger.info(f"[BACKUP] {src_file.name} → {dst.name}")
        except Exception as e:
            logger.error(f"[BACKUP] Failed {src_file}: {e}")

    try:
        (backup_dir / 'backup_manifest.json').write_text(
            json.dumps(record.to_dict(), indent=2), encoding='utf-8'
        )
    except Exception as e:
        logger.warning(f"[BACKUP] Manifest write failed: {e}")

    return record


def restore_backup(record: BackupRecord) -> List[str]:
    errors: List[str] = []
    for original_path in record.original_files:
        backup_file = record.backup_dir / original_path.name
        if not backup_file.exists():
            errors.append(f"Archivo de backup no encontrado: {backup_file.name}")
            continue
        try:
            shutil.copy2(backup_file, original_path)
            logger.info(f"[RESTORE] {backup_file.name} → {original_path}")
        except Exception as e:
            errors.append(f"Error restaurando {original_path.name}: {e}")
            logger.error(f"[RESTORE] {e}")
    return errors


def list_backups() -> List[BackupRecord]:
    records: List[BackupRecord] = []
    root = get_backup_root()
    for backup_dir in sorted(root.iterdir(), reverse=True):
        if not backup_dir.is_dir():
            continue
        manifest = backup_dir / 'backup_manifest.json'
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            records.append(BackupRecord(
                backup_dir=Path(data['backup_dir']),
                timestamp=datetime.fromisoformat(data['timestamp']),
                source_char_id=data['source_char_id'],
                target_char_id=data['target_char_id'],
                original_files=[Path(f) for f in data.get('original_files', [])],
            ))
        except Exception as e:
            logger.warning(f"[BACKUP] Bad manifest {manifest}: {e}")
    return records
