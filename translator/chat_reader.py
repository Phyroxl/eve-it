"""chat_reader.py - Chat Input Layer"""
from __future__ import annotations
import re, time, threading, logging, os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional
from datetime import datetime, timezone

logger = logging.getLogger('eve.translator')
CHAT_LINE_RE = re.compile(r'.*?\[\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})\s*\]\s+([^>]+?)\s*>\s*(.*)', re.UNICODE)

def _get_chatlog_dir() -> Optional[Path]:
    """Encuentra la carpeta Chatlogs de EVE."""
    candidates = [
        Path(os.path.expanduser('~')) / 'Documents' / 'EVE' / 'logs' / 'Chatlogs',
        Path(os.path.expandvars('%USERPROFILE%')) / 'Documents' / 'EVE' / 'logs' / 'Chatlogs',
        Path('C:/Users') / os.environ.get('USERNAME','') / 'Documents' / 'EVE' / 'logs' / 'Chatlogs',
    ]
    for p in candidates:
        if p.exists():
            return p
    try:
        from core.log_parser import find_all_log_dirs
        for dirs in find_all_log_dirs().values():
            for d in dirs:
                chat = d.parent / 'Chatlogs'
                if chat.exists(): return chat
                if d.exists(): return d
    except Exception: pass
    return None

@dataclass
class ChatMessage:
    timestamp: str
    channel: str
    sender: str
    text: str
    listener: str = ''
    msg_id: str = field(default='', init=False)
    def __post_init__(self):
        self.msg_id = f"{self.timestamp}|{self.channel}|{self.sender}|{self.text[:40]}"

class ChatFileReader:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._pos = 0
        self._channel = filepath.name.split('_')[0] if '_' in filepath.name else 'Unknown'
        self._listener = ''
        self._initialized = False

    def _try_read(self, encoding):
        with open(self.filepath, 'r', encoding=encoding, errors='ignore') as f:
            return f.read(4096)

    def _parse_header(self, text: str):
        m = re.search(r'Channel Name[:\s]+(.+)', text)
        if m: self._channel = m.group(1).strip()
        m = re.search(r'(?:Listener|Oyente)[:\s]+(.+)', text)
        if m: self._listener = m.group(1).strip()

    def _detect_encoding(self):
        """EVE escribe chatlogs en UTF-16 LE con BOM."""
        try:
            with open(self.filepath, 'rb') as f:
                bom = f.read(2)
            if bom in (b'\xff\xfe', b'\xfe\xff'):
                return 'utf-16'
        except Exception: pass
        return 'utf-8'

    def initialize(self, read_existing: bool = True):
        try:
            self._encoding = self._detect_encoding()
            with open(self.filepath, 'r', encoding=self._encoding, errors='ignore') as f:
                self._parse_header(f.read(4096))
                if read_existing:
                    # Buscar últimos 20 minutos (margen de 64KB)
                    f.seek(0, 2)
                    size = f.tell()
                    self._pos = max(0, size - 65536)
                else:
                    f.seek(0, 2)
                    self._pos = f.tell()
            self._initialized = True
        except Exception as e:
            logger.debug(f"ChatFileReader init error {self.filepath}: {e}")

    def read_new(self) -> list:
        if not self._initialized:
            self.initialize()
            # Solo queremos los últimos 20 minutos reales.
            return self._read_and_filter(max_age_minutes=20)
        return self._read_and_filter()

    def _read_and_filter(self, max_age_minutes: Optional[int] = None) -> list:
        msgs = []
        try:
            now_ts = time.time()
            enc = getattr(self, '_encoding', 'utf-16')
            with open(self.filepath, 'r', encoding=enc, errors='ignore') as f:
                # Detectar rotación de archivo (EVE creó uno nuevo / el archivo se achicó)
                f.seek(0, 2)
                current_size = f.tell()
                if current_size < self._pos:
                    logger.info(f"Rotación detectada en {self.filepath.name}, reiniciando posición")
                    self._pos = 0
                f.seek(self._pos)
                new_text = f.read()
                self._pos = f.tell()
            
            lines = new_text.splitlines()
            for line in lines:
                line = line.strip()
                if not line: continue
                m = CHAT_LINE_RE.match(line)
                if m:
                    ts_str, sender, text = m.group(1), m.group(2).strip(), m.group(3).strip()
                    if not text or sender in ('EVE System', 'Mensaje', 'Message', 'System', 'Sistema', 'Сообщение', 'Nachricht'):
                        continue
                    
                    # Validar antigüedad si se requiere
                    if max_age_minutes is not None:
                        try:
                            # Formato EVE: 2026.04.18 06:21:33 (UTC)
                            dt = datetime.strptime(ts_str, "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
                            age_secs = time.time() - dt.timestamp()
                            if age_secs > max_age_minutes * 60:
                                continue # Demasiado antiguo
                        except Exception: pass

                    msgs.append(ChatMessage(ts_str, self._channel, sender, text, self._listener))
        except Exception as e:
            logger.debug(f"ChatFileReader read error: {e}")
        return msgs

class ChatWatcher:
    def __init__(self, callback: Callable, poll_interval: float = 1.5,
                 active_channels: Optional[set] = None, active_window_minutes: int = 20):
        self._callback = callback
        self._poll_interval = poll_interval
        self._active_channels = active_channels or {'ch_local'}
        self._active_window_minutes = active_window_minutes
        self._readers: dict = {}
        self._seen_ids: set = set()
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._chatlog_dir = _get_chatlog_dir()
        logger.info(f"ChatWatcher: chatlog dir = {self._chatlog_dir}")

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='ChatWatcher')
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=3)

    def _get_files(self, window_minutes: Optional[int] = None) -> list:
        files = []
        win = window_minutes if window_minutes is not None else self._active_window_minutes
        cutoff = time.time() - win * 60
        dirs_to_scan = []
        if self._chatlog_dir and self._chatlog_dir.exists():
            dirs_to_scan.append(self._chatlog_dir)
        else:
            try:
                from core.log_parser import find_all_log_dirs
                # find_all_log_dirs ahora usa caché interna, es seguro llamarlo
                for dirs in find_all_log_dirs().values():
                    dirs_to_scan.extend(dirs)
            except Exception: pass
        for d in dirs_to_scan:
            if not d.is_dir(): continue
            for f in d.glob('*.txt'):
                try:
                    if f.stat().st_mtime >= cutoff:
                        files.append(f)
                except Exception: pass
        return files

    def _get_canonical_id(self, name: str) -> str:
        import re as _re
        m = _re.match(r'Private Chat \((.+)\)', name, _re.I)
        if m: name = m.group(1).strip()
        low = name.lower().strip()
        synonyms = {
            'local': 'ch_local',
            'fleet': 'ch_fleet', 'flota': 'ch_fleet', 'escuadrón': 'ch_fleet', 'esquadrão': 'ch_fleet',
            'corp.': 'ch_corp', 'corporación': 'ch_corp', 'corporação': 'ch_corp', 'корпорация': 'ch_corp',
            'alliance': 'ch_alliance', 'alianza': 'ch_alliance', 'aliança': 'ch_alliance'
        }
        return synonyms.get(low, name)

    def set_active_channel(self, ch_id: str):
        with self._lock:
            self._active_channels = {ch_id}
            logger.info(f"Watcher: Canal activo cambiado a -> {ch_id}")
            for fpath, reader in self._readers.items():
                if self._channel_matches(fpath.name):
                    try:
                        reader.initialize(read_existing=True)
                        logger.debug(f"Rebobinado lector: {fpath.name}")
                    except Exception: pass

    def _get_channel_aliases(self, ch_id: str) -> list:
        if ch_id == 'ch_local': return ['local']
        if ch_id == 'ch_fleet': return ['fleet', 'flota', 'escuadrón', 'esquadrão']
        if ch_id == 'ch_corp':  return ['corp.', 'corporación', 'corporação', 'корпорация']
        if ch_id == 'ch_alliance': return ['alliance', 'alianza', 'aliança']
        return [ch_id.lower().strip()]

    def _channel_matches(self, fname: str) -> bool:
        if not self._active_channels: return True
        stem = fname.split('_')[0].lower() if '_' in fname else fname.lower()
        for active_ch in self._active_channels:
            aliases = self._get_channel_aliases(active_ch)
            if any(a in stem for a in aliases):
                return True
        return False

    def _loop(self):
        while self._running:
            try:
                all_new_msgs = []
                for fpath in self._get_files():
                    # Escanear todos los archivos dentro del rango temporal (Persistencia)
                    if fpath not in self._readers:
                        r = ChatFileReader(fpath)
                        r.initialize(read_existing=True)
                        self._readers[fpath] = r
                    
                    for msg in self._readers[fpath].read_new():
                        if msg.msg_id in self._seen_ids: continue
                        
                        # Canonicalizar el canal
                        msg.channel = self._get_canonical_id(msg.channel)
                        
                        # FILTRO: Solo emitir si coincide con el canal activo en el HUD
                        if not self._channel_matches(fpath.name): continue
                        
                        # FILTRO TEMPORAL: Máximo 20 minutos
                        try:
                            from datetime import datetime, timezone
                            dt = datetime.strptime(msg.timestamp, "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
                            if time.time() - dt.timestamp() > 20 * 60:
                                continue
                        except: pass

                        all_new_msgs.append(msg)
                        self._seen_ids.add(msg.msg_id)
                
                # ORDENAR POR TIMESTAMP ANTES DE EMITIR
                if all_new_msgs:
                    all_new_msgs.sort(key=lambda x: x.timestamp)
                    for msg in all_new_msgs:
                        if len(self._seen_ids) > 5000:
                            self._seen_ids = set(list(self._seen_ids)[-2000:])
                        try:
                            self._callback(msg)
                        except Exception as e:
                            logger.warning(f"ChatWatcher callback error: {e}")
            except Exception as e:
                logger.debug(f"ChatWatcher loop error: {e}")
            try:
                if time.time() % 300 < 2:
                    cutoff = time.time() - 7200
                    to_del = [fp for fp, r in self._readers.items() if fp.stat().st_mtime < cutoff]
                    for fp in to_del:
                        del self._readers[fp]
                        logger.debug(f"Nettoyage: Lector eliminado por antigüedad -> {fp.name}")
            except Exception: pass
            time.sleep(self._poll_interval)

    def get_known_channels(self) -> list:
        seen = []
        for reader in self._readers.values():
            ch = getattr(reader, '_channel', '')
            if ch and ch not in seen:
                seen.append(ch)
        return sorted(seen)

    def get_all_channels(self) -> list:
        """Versión optimizada que usa los canales ya detectados por los readers."""
        seen = {'ch_local', 'ch_fleet', 'ch_corp', 'ch_alliance'}
        with self._lock:
            for r in self._readers.values():
                ch = getattr(r, '_channel', None)
                if ch: seen.add(self._get_canonical_id(ch))
        return sorted(list(seen), key=lambda x: (x != 'ch_local', x))
