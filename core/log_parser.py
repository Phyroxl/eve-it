"""
log_parser.py
-------------
Módulo responsable de leer y parsear los logs de EVE Online en tiempo real.

FORMATO DE LOGS EVE ONLINE:
  EVE genera dos tipos de logs:

  1. GAMELOGS (en logs/Gamelogs/):
     Nombre: YYYYMMDD_HHMMSS_SESSIONID.txt  (ej: 20260403_134357_96827802.txt)
     Cabecera:
       ------------------------------------------------------------
         Gamelog
         Listener: Phyrox Perez
         Session Started: 2026.04.03 13:43:57
       ------------------------------------------------------------
     Contiene: combat, bounty, notify lines. Las líneas de bounty son del tipo:
       [ 2026.04.03 13:47:52 ] (bounty) Se ha añadido <font...>247.500 ISK</b>...

  2. CHATLOGS (en logs/Chatlogs/):
     Nombre: ChannelName_YYYYMMDD_HHMMSS_SESSIONID.txt
     Cabecera:
       ------------------------------------------------------------
         Channel ID:    ...
         Channel Name:  Local
         Listener:      Phyrox Perez
         Session Started: ...
       ------------------------------------------------------------
     Contiene: mensajes de chat. NO contiene bounties.

  Los bounties están SOLO en Gamelogs. La cabecera de Gamelogs SÍ tiene "Listener:".
  El fallback numérico ocurre solo si el archivo no tiene cabecera aún (archivo recién creado).
"""

import re
import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional


HTML_TAG_RE = re.compile(r'<[^>]+>')

# Tipos de evento de ISK
EVT_INDIVIDUAL = 'individual'   # bounty individual de Gamelog (acumula en ciclo)
EVT_PAYOUT     = 'payout'       # pago ESS de Chatlog (marca fin de ciclo)
EVT_UNKNOWN    = 'unknown'

# Patrones de bounties individuales (Gamelogs)
BOUNTY_PATTERNS = [
    re.compile(r'Se ha a[ñn]adido\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Recompensa de caza\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Bounty prize\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Added\b.*?([\d.,]+)\s*ISK.*?bounty', re.IGNORECASE),
    re.compile(r'Bounty payout\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'awarded a bounty of\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Mission reward\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Mission bonus\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Recompensa de misi[oó]n\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
]

# Patrones de PAYOUT ESS (Chatlogs de Registro/Journal)
# Formato: "Pagos de recompensa   9.037.207 ISK"
# o con tabuladores: "Pagos de recompensa<t>ISK<t>saldo<t>descripcion"
PAYOUT_PATTERNS = [
    re.compile(r'Pagos de recompensa.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Bounty payments.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'Bounty prize payments.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'\bPago de recompensa\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
    re.compile(r'\bRecompensa\b.*?([\d.,]+)\s*ISK', re.IGNORECASE),
]

# Patrón de IMPUESTO de corporación sobre recompensa — ignorar (ISK negativo)
TAX_PATTERN = re.compile(
    r'Impuesto.*recompensa|Tax.*bounty|Corporation.*tax.*bounty',
    re.IGNORECASE
)

TIMESTAMP_RE = re.compile(r'\[\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})\s*\]')

# Detecta la línea "Listener: Nombre" en cabeceras de Gamelogs y Chatlogs
LISTENER_RE = re.compile(r'^\s*(?:Listener|Oyente|Écouteur|Empfänger|Ascoltatore|Słuchacz|Ouvinte|Dinleyici|Слушатель|聆听者|リスナー):\s*(.+)', re.IGNORECASE)

# Detecta si un string es puramente numérico (ID de sesión, no nombre)
_NUMERIC_RE = re.compile(r'^\d+$')


def parse_timestamp(line: str) -> Optional[datetime]:
    m = TIMESTAMP_RE.search(line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y.%m.%d %H:%M:%S")
        except ValueError:
            return None
    return None


def parse_isk_number(raw: str) -> Optional[int]:
    raw = raw.strip()
    if ',' in raw and '.' in raw:
        raw = raw.replace(',', '')
        return int(float(raw))
    elif '.' in raw:
        raw = raw.replace('.', '')
    elif ',' in raw:
        raw = raw.replace(',', '')
    try:
        return int(raw)
    except ValueError:
        return None


def extract_isk(line: str) -> Optional[int]:
    """Extrae ISK de una línea. Retorna None si no hay ISK o es impuesto."""
    result = extract_isk_with_type(line)
    if result is None:
        return None
    return result[0]


def extract_isk_with_type(line: str) -> Optional[tuple]:
    """
    Extrae (isk, tipo) de una línea de log.
    tipo: EVT_INDIVIDUAL para bounties de Gamelog,
          EVT_PAYOUT para pagos ESS de Chatlog.
    Retorna None si no hay ISK relevante o es un impuesto (línea negativa).
    """
    clean_line = HTML_TAG_RE.sub(' ', line)

    # Ignorar líneas de impuesto (contienen ISK negativo o texto de impuesto)
    if TAX_PATTERN.search(line):
        return None

    # Intentar como PAYOUT primero (líneas de Chatlog "Pagos de recompensa")
    for candidate in [line, clean_line]:
        for pattern in PAYOUT_PATTERNS:
            m = pattern.search(candidate)
            if m:
                value = parse_isk_number(m.group(1))
                if value is not None and value > 0:
                    return (value, EVT_PAYOUT)

    # Intentar como bounty individual (Gamelog)
    for candidate in [line, clean_line]:
        for pattern in BOUNTY_PATTERNS:
            m = pattern.search(candidate)
            if m:
                value = parse_isk_number(m.group(1))
                if value is not None and value > 0:
                    return (value, EVT_INDIVIDUAL)

    return None


def extract_character_name(filepath: Path) -> str:
    """Extrae el nombre del personaje detectando automáticamente la codificación."""
    try:
        # 1. Intentar detectar codificación leyendo los primeros bytes
        with open(filepath, 'rb') as bf:
            head = bf.read(100)
            # Detección simple de UTF-16 (presencia de nulos en texto ASCII)
            # o BOM (Byte Order Mark)
            is_utf16 = b'\x00' in head or head.startswith(b'\xff\xfe') or head.startswith(b'\xfe\xff')
            enc = 'utf-16' if is_utf16 else 'utf-8'

        # 2. Leer con la codificación detectada
        with open(filepath, 'r', encoding=enc, errors='ignore') as f:
            for _ in range(60): # Aumentado a 60 por si hay mucho padding
                line = f.readline()
                if not line: break
                m = LISTENER_RE.match(line)
                if m:
                    name = m.group(1).strip()
                    if name and not _NUMERIC_RE.match(name):
                        return name
    except Exception as e:
        logger.error(f"Error extrayendo nombre de {filepath.name}: {e}")

    # Fallback: extraer la parte de ID del nombre del archivo
    stem = filepath.stem
    parts = stem.split('_')
    if len(parts) >= 3:
        # Para "20260403_134357_96827802" → devolver "96827802"
        # El watcher registrará el alias cuando relea la cabecera
        return '_'.join(parts[2:])
    return stem


def _build_eve_base_dirs() -> list[Path]:
    import string
    home = Path.home()
    bases = []
    doc_folders = [
        "Documents", "Documentos", "Mes documents", "Dokumente",
        "Documenti", "My Documents",
    ]
    for doc in doc_folders:
        bases.append(home / doc / "EVE")
    onedrive_roots = [home / "OneDrive", home / "OneDrive - Personal"]
    if (home / "OneDrive").exists():
        try:
            for sub in (home / "OneDrive").iterdir():
                if sub.is_dir():
                    onedrive_roots.append(sub)
        except PermissionError:
            pass
    for od in onedrive_roots:
        for doc in doc_folders:
            bases.append(od / doc / "EVE")
        bases.append(od / "EVE")
    bases.append(Path("C:/Users/Public/Documents/EVE"))
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:/")
        try:
            if drive.exists():
                bases.append(drive / "EVE")
                for gf in ["Games", "Juegos", "Program Files", "Program Files (x86)"]:
                    bases.append(drive / gf / "EVE")
        except (PermissionError, OSError):
            pass
    for sr in [
        Path("C:/Program Files (x86)/Steam/steamapps/common/Eve Online"),
        Path("C:/Program Files/Steam/steamapps/common/Eve Online"),
    ]:
        bases.append(sr / "EVE")
        bases.append(sr)
    for cr in [
        Path("C:/Program Files (x86)/CCP/EVE"),
        Path("C:/Program Files/CCP/EVE"),
        Path("C:/EVE"),
    ]:
        bases.append(cr)
    return bases


def find_all_log_dirs() -> dict[str, list[Path]]:
    found = {"Chatlogs": [], "Gamelogs": []}
    for base in _build_eve_base_dirs():
        for log_type in ["Chatlogs", "Gamelogs"]:
            candidate = base / "logs" / log_type
            try:
                if candidate.exists() and candidate.is_dir():
                    if candidate not in found[log_type]:
                        found[log_type].append(candidate)
            except (PermissionError, OSError):
                pass
    return found


def find_all_candidate_dirs() -> list[Path]:
    all_dirs = find_all_log_dirs()
    return all_dirs["Chatlogs"] + all_dirs["Gamelogs"]


def find_log_dir(base_path: Optional[str] = None) -> Optional[Path]:
    if base_path:
        p = Path(base_path)
        return p if p.exists() else None
    all_dirs = find_all_log_dirs()
    for d in all_dirs["Chatlogs"] + all_dirs["Gamelogs"]:
        return d
    return None


def find_log_files(base_path: Optional[str] = None) -> list[Path]:
    if base_path:
        p = Path(base_path)
        if p.exists():
            files = list(p.glob("*.txt"))
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return files
        return []
    all_dirs = find_all_log_dirs()
    all_files = []
    for log_type in ["Chatlogs", "Gamelogs"]:
        for log_dir in all_dirs[log_type]:
            try:
                all_files.extend(log_dir.glob("*.txt"))
            except (PermissionError, OSError):
                pass
    seen = set()
    unique_files = []
    for f in all_files:
        if str(f) not in seen:
            seen.add(str(f))
            unique_files.append(f)
    unique_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return unique_files


class LogReader:
    """Lector incremental de un archivo de log EVE."""

    def __init__(self, filepath: Path, ess_retention: float = 1.0):
        self.filepath = filepath
        self.ess_retention = ess_retention
        self._file_pos = 0
        self._initialized = False
        self._character: Optional[str] = None
        self._encoding = 'utf-8'
        self._detect_encoding()

    @property
    def character(self) -> str:
        if self._character is None:
            self._character = extract_character_name(self.filepath)
        return self._character

    @character.setter
    def character(self, value: str):
        self._character = value

    def _detect_encoding(self):
        """Detecta si el archivo es UTF-16 o UTF-8."""
        try:
            if not self.filepath.exists(): return
            with open(self.filepath, 'rb') as f:
                head = f.read(200)
                if b'\x00' in head or head.startswith(b'\xff\xfe') or head.startswith(b'\xfe\xff'):
                    self._encoding = 'utf-16'
                    logger.debug(f"Codificación detectada UTF-16 para {self.filepath.name}")
                else:
                    self._encoding = 'utf-8'
        except Exception:
            self._encoding = 'utf-8'

    def try_resolve_name(self) -> str:
        """
        Intenta (re)leer el nombre real del archivo.
        Útil cuando el archivo aún no tenía cabecera completa al registrarse.
        Actualiza self._character si encuentra un nombre válido.
        """
        name = extract_character_name(self.filepath)
        if name and not _NUMERIC_RE.match(name.replace('_', '')):
            self._character = name
        return self._character or name

    def initialize(self, skip_existing: bool = True):
        try:
            size = self.filepath.stat().st_size
            self._file_pos = size if skip_existing else 0
            self._initialized = True
        except OSError:
            self._initialized = False

    def read_new_lines(self) -> list[dict]:
        if not self._initialized:
            self.initialize()
        results = []
        try:
            current_size = self.filepath.stat().st_size
            if current_size <= self._file_pos:
                return results
            with open(self.filepath, 'r', encoding=self._encoding, errors='ignore') as f:
                f.seek(self._file_pos)
                new_content = f.read()
                self._file_pos = f.tell()
            for line in new_content.splitlines():
                line = line.strip()
                if not line:
                    continue
                result = extract_isk_with_type(line)
                if result is not None:
                    isk, evt_type = result
                    ts = parse_timestamp(line) or datetime.now()
                    # Aplicar ESS retention solo a bounties individuales
                    # Los payouts ya tienen el impuesto descontado en el log
                    if evt_type == EVT_INDIVIDUAL:
                        adjusted_isk = int(isk * self.ess_retention)
                    else:
                        adjusted_isk = isk
                    results.append({
                        'timestamp': ts,
                        'isk': adjusted_isk,
                        'raw_isk': isk,
                        'line': line,
                        'character': self.character,
                        'filepath': str(self.filepath),
                        'evt_type': evt_type,
                    })
        except (OSError, IOError):
            pass
        return results
