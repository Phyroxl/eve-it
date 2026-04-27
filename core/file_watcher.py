"""
file_watcher.py — Watcher de logs EVE Online en tiempo real.

Clases:
  FileWatcher     — watcher de un único archivo (bajo nivel)
  EVELogWatcher   — watcher completo multi-archivo multi-directorio
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger('eve.file_watcher')

_NUMERIC_RE = re.compile(r'^\d+$')


class FileWatcher:
    """Vigila un único archivo y llama a callback cuando cambia su tamaño."""

    def __init__(self, path, callback, interval=1.0):
        self._path = Path(path)
        self._cb = callback
        self._interval = interval
        self._running = False
        self._thread = None
        self._last_size = 0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        while self._running:
            try:
                if self._path.exists():
                    sz = self._path.stat().st_size
                    if sz != self._last_size:
                        self._last_size = sz
                        self._cb(self._path)
            except Exception:
                pass
            time.sleep(self._interval)


class EVELogWatcher:
    """
    Vigila los directorios de logs de EVE Online en tiempo real.

    - Detecta archivos nuevos en Gamelogs y Chatlogs.
    - Lee líneas nuevas de cada archivo y las envía al MultiAccountTracker.
    - Resuelve alias ID numérico -> nombre real de personaje.
    """

    def __init__(
        self,
        tracker,
        log_dir=None,
        poll_interval=1.0,
        ess_retention=1.0,
        skip_existing=True,
        active_window_minutes=480,
    ):
        self._tracker = tracker
        self._log_dir = log_dir
        self._poll_interval = poll_interval
        self._ess_retention = ess_retention
        self._skip_existing = skip_existing
        self._active_window_minutes = active_window_minutes
        self._running = False
        self._thread = None
        self._readers = {}
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name='EVELogWatcher'
        )
        self._thread.start()
        logger.info("EVELogWatcher iniciado")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("EVELogWatcher detenido")

    def _run(self):
        while self._running:
            try:
                self._scan_and_process()
            except Exception as e:
                logger.error(f"EVELogWatcher error: {e}", exc_info=True)
            time.sleep(self._poll_interval)

    def _scan_and_process(self):
        from core.log_parser import find_all_log_dirs, LogReader
        import time as _time

        if self._log_dir:
            base = Path(self._log_dir)
            candidates = list(base.glob('*.txt')) if base.exists() else []
        else:
            all_dirs = find_all_log_dirs()
            candidates = []
            for log_type in ('Gamelogs', 'Chatlogs'):
                for d in all_dirs.get(log_type, []):
                    try:
                        candidates.extend(d.glob('*.txt'))
                    except (PermissionError, OSError):
                        pass

        cutoff = _time.time() - self._active_window_minutes * 60
        active = [f for f in candidates if _mtime_ok(f, cutoff)]

        with self._lock:
            # 1. Registrar archivos nuevos
            for f in active:
                key = str(f)
                if key not in self._readers:
                    reader = LogReader(f, ess_retention=self._ess_retention)
                    reader.initialize(skip_existing=self._skip_existing)
                    # Siempre intentar resolver nombre real de la cabecera
                    char = reader.try_resolve_name() or reader.character
                    reader._character = char
                    self._readers[key] = reader
                    if char and not _NUMERIC_RE.match(char.replace('_', '')):
                        self._tracker.register_character(char)
                    logger.debug(f"Nuevo log detectado: {f.name} -> {char}")

            # 2. Procesar líneas y Limpiar archivos inactivos
            active_keys = set(str(f) for f in active)
            for key, reader in list(self._readers.items()):
                # Si el archivo ya no cumple el criterio de 'active' (mtime antiguo o borrado)
                if key not in active_keys:
                    char = reader.character
                    if char:
                        self._tracker.remove_character(char)
                    del self._readers[key]
                    logger.info(f"Log inactivado y removido: {Path(key).name} ({char})")
                    continue

                try:
                    lines = reader.read_new_lines()
                except Exception as e:
                    logger.warning(f"Error leyendo {key}: {e}")
                    continue

                for event in lines:
                    char = event.get('character', '')
                    if _NUMERIC_RE.match(char.replace('_', '')):
                        resolved = reader.try_resolve_name()
                        if resolved and not _NUMERIC_RE.match(resolved.replace('_', '')):
                            self._tracker.register_alias(char, resolved)
                            char = resolved
                    if char:
                        self._tracker.register_character(char)
                    self._tracker.add_event(
                        character=char,
                        timestamp=event['timestamp'],
                        isk=event['isk'],
                        raw_line=event.get('line', ''),
                        processed_at=event.get('processed_at'),
                        evt_type=event.get('evt_type', 'individual'),
                    )


def _mtime_ok(f, cutoff):
    try:
        return f.stat().st_mtime >= cutoff
    except OSError:
        return False
