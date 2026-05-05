"""Data models for Visual Clon — EVE client layout cloning tool."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class EveCharProfile:
    """A discovered EVE character settings file (core_char_NNNN.dat)."""
    char_id: str
    file_path: Path
    file_size: int
    modified: Optional[datetime] = None
    char_name: str = ''

    @property
    def display_name(self) -> str:
        if self.char_name:
            return f"{self.char_name} ({self.char_id})"
        return f"Personaje {self.char_id}"


@dataclass
class EveSettingsFolder:
    """A detected EVE Online settings folder containing profile .dat files."""
    path: Path
    char_profiles: List[EveCharProfile] = field(default_factory=list)
    user_profile_ids: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return self.path.is_dir() and bool(self.char_profiles)


# Sections that Visual Clon copies — v1 copies the full char file
# (binary format), so all sections are included together.
COPY_SECTIONS = [
    ('window_layout', 'Layout de ventanas',
     'Posición y tamaño de todas las ventanas internas del cliente EVE.'),
    ('overview',      'Overview / columnas / pestañas',
     'Configuración del overview, pestañas activas y columnas visibles.'),
    ('chat',          'Paneles de chat',
     'Posición, tamaño y configuración de canales de chat.'),
    ('inventory',     'Inventario y paneles',
     'Inventario, market, wallet, industry, fitting, probe scanner y d-scan.'),
    ('ui_prefs',      'Preferencias visuales UI',
     'Escalado, colores de UI y otras preferencias visuales del cliente.'),
]


@dataclass
class CopyPlan:
    """Describes what would be copied in a Visual Clon operation."""
    source: EveCharProfile
    targets: List[EveCharProfile]
    dry_run: bool = True
    files_to_copy: List[Path] = field(default_factory=list)
    estimated_size_bytes: int = 0


@dataclass
class BackupRecord:
    """A timestamped backup created before applying Visual Clon."""
    backup_dir: Path
    timestamp: datetime
    source_char_id: str
    target_char_id: str
    original_files: List[Path] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'backup_dir': str(self.backup_dir),
            'timestamp': self.timestamp.isoformat(),
            'source_char_id': self.source_char_id,
            'target_char_id': self.target_char_id,
            'original_files': [str(f) for f in self.original_files],
        }


@dataclass
class CloneResult:
    """Result of a Visual Clon operation."""
    dry_run: bool
    success: bool
    files_copied: List[Path] = field(default_factory=list)
    files_skipped: List[Path] = field(default_factory=list)
    backups: List[BackupRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    log_lines: List[str] = field(default_factory=list)
