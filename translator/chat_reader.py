"""chat_reader.py - Chat Input Layer"""
from __future__ import annotations
import re, time, threading, logging, os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional

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
    # Fallback: buscar via find_all_log_dirs
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
                    # Ajustado a 40KB para capturar ~30 min de historial ligero
                    f.seek(0, 2)
                    size = f.tell()
                    self._pos = max(0, size - 40960)
                else:
                    f.seek(0, 2)
                    self._pos = f.tell()
            self._initialized = True
        except Exception as e:
            logger.debug(f"ChatFileReader init error {self.filepath}: {e}")

    def read_new(self) -> list:
        if not self._initialized:
            self.initialize()
            return []
        msgs = []
        try:
            enc = getattr(self, '_encoding', 'utf-16')
            with open(self.filepath, 'r', encoding=enc, errors='ignore') as f:
                f.seek(self._pos)
                new_text = f.read()
                self._pos = f.tell()
            for line in new_text.splitlines():
                line = line.strip()
                if not line: continue
                m = CHAT_LINE_RE.match(line)
                if m:
                    ts, sender, text = m.group(1), m.group(2).strip(), m.group(3).strip()
                    if text and sender not in ('EVE System', 'Mensaje', 'Message', 'System', 'Sistema', 'Сообщение', 'Message', 'Nachricht'):
                        msgs.append(ChatMessage(ts, self._channel, sender, text, self._listener))
        except Exception as e:
            logger.debug(f"ChatFileReader read error: {e}")
        return msgs

class ChatWatcher:
    def __init__(self, callback: Callable, poll_interval: float = 1.5,
                 active_channels: Optional[set] = None, active_window_minutes: int = 120):
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
        """Mapea nombres crudos de EVE a IDs internas de traducción."""
        import re as _re
        # Extraer nombre si es un chat privado: "Private Chat (Player Name)" -> "Player Name"
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
        """Cambia el canal activo y rebobina los lectores para cargar historial."""
        with self._lock:
            self._active_channels = {ch_id}
            logger.info(f"Watcher: Canal activo cambiado a -> {ch_id}")
            # Forzar rebobinado de los archivos que coincidan con el nuevo canal
            for fpath, reader in self._readers.items():
                if self._channel_matches(fpath.name):
                    try:
                        reader.initialize(read_existing=True)
                        logger.debug(f"Rebobinado lector: {fpath.name}")
                    except Exception: pass

    def _get_channel_aliases(self, ch_id: str) -> list:
        """Dada una ID (ej ch_fleet), devuelve todos los prefijos de archivo posibles."""
        if ch_id == 'ch_local': return ['local']
        if ch_id == 'ch_fleet': return ['fleet', 'flota', 'escuadrón', 'esquadrão']
        if ch_id == 'ch_corp':  return ['corp.', 'corporación', 'corporação', 'корпорация']
        if ch_id == 'ch_alliance': return ['alliance', 'alianza', 'aliança']
        # Para privados, el alias es el nombre del personaje limpio
        return [ch_id.lower().strip()]

    def _channel_matches(self, fname: str) -> bool:
        """Filtra por canal activo basándose en sinónimos de IDs canónicas."""
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
                        
                        self._seen_ids.add(msg.msg_id)
                        if len(self._seen_ids) > 5000:
                            self._seen_ids = set(list(self._seen_ids)[-2000:])
                        
                        try: self._callback(msg)
                        except Exception: pass
            except Exception as e:
                logger.debug(f"ChatWatcher loop error: {e}")
            
            # Limpieza periódica de lectores antiguos (> 2 horas de inactividad)
            try:
                if time.time() % 300 < 2: # cada 5 minutos aprox
                    cutoff = time.time() - 7200 # 2 horas
                    to_del = [fp for fp, r in self._readers.items() if fp.stat().st_mtime < cutoff]
                    for fp in to_del:
                        del self._readers[fp]
                        logger.debug(f"Nettoyage: Lector eliminado por antigüedad -> {fp.name}")
            except Exception: pass

            time.sleep(self._poll_interval)

    def get_known_channels(self) -> list:
        """Devuelve lista de canales únicos detectados por los readers activos."""
        seen = []
        for reader in self._readers.values():
            ch = getattr(reader, '_channel', '')
            if ch and ch not in seen:
                seen.append(ch)
        return sorted(seen)

    def get_all_channels(self) -> list:
        """
        Escanea logs recientes y devuelve IDs canónicas o nombres crudos (privados).
        """
        import re as _re
        from pathlib import Path
        # Canales base que SIEMPRE deben estar visibles
        seen = {'ch_local', 'ch_fleet', 'ch_corp', 'ch_alliance'}
        
        try:
            # Escaneamos los archivos del último periodo (60 min) para el menú
            for fpath in self._get_files(window_minutes=60):
                try:
                    # Detectar canal desde la cabecera del archivo
                    enc = 'utf-16' # EVE logs son casi siempre utf-16
                    try:
                        with open(fpath, 'r', encoding=enc, errors='ignore') as f:
                            header = f.read(2048)
                    except Exception:
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            header = f.read(2048)
                    
                    found_ch = None
                    m = _re.search(r'Channel Name[:\s]+(.+)', header)
                    if m:
                        found_ch = m.group(1).strip()
                    else:
                        # Fallback a nombre de archivo
                        stem = Path(fpath).stem
                        found_ch = stem.split('_')[0] if '_' in stem else stem
                    
                    if found_ch:
                        seen.add(self._get_canonical_id(found_ch))
                except Exception: pass
        except Exception: pass
            
        # Ordenar: primero local, luego alfabético
        res = sorted(list(seen), key=lambda x: (x != 'ch_local', x))
        return res
