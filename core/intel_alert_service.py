"""Intel Alert Service — scans EVE chatlogs for hostile/unknown pilots.

Architecture:
- IntelAlertConfig: persisted to config/intel_alert.json
- IntelEvent: emitted per alert, carries pilot / system / classification / source
- Helper functions: parse_intel_message, classify_pilot, should_alert (all pure, testable)
- IntelAlertService: background thread, calls callback(IntelEvent) on match

source_mode controls which chatlog files are monitored:
  "local"  — only Local channel
  "intel"  — only configured intel_channels (fallback: files containing 'intel')
  "both"   — Local + intel_channels

Distance filtering:
  Requires EveMapService.distance_jumps() to return a value (currently always None
  because no SDE is loaded). When distance is unknown, alert_unknown_distance governs.
"""
import re
import threading
import time
import logging
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger('eve.intel')

CONFIG_FILE = Path(__file__).resolve().parent.parent / 'config' / 'intel_alert.json'


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class IntelAlertConfig:
    enabled: bool = True
    alert_sound: bool = True
    alert_on_unknown: bool = True
    alert_on_watchlist: bool = True
    source_mode: str = "local"              # "local" | "intel" | "both"
    intel_channels: List[str] = field(default_factory=list)
    current_system: str = ""
    max_jumps: int = 5
    alert_unknown_distance: bool = True
    safe_names: List[str] = field(default_factory=list)
    watch_names: List[str] = field(default_factory=list)
    pilot_cooldown_secs: int = 120

    def save(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as e:
            logger.debug(f"IntelAlertConfig save error: {e}")

    @classmethod
    def load(cls) -> 'IntelAlertConfig':
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                obj = cls()
                for k, v in data.items():
                    if hasattr(obj, k):
                        setattr(obj, k, v)
                return obj
        except Exception as e:
            logger.debug(f"IntelAlertConfig load error: {e}")
        return cls()


# ── Event ─────────────────────────────────────────────────────────────────────

@dataclass
class IntelEvent:
    timestamp: str
    pilot: str
    channel: str
    message: str
    classification: str = "unknown"     # "safe" | "watchlist" | "unknown" | "intel"
    source: str = "local"               # "local" | "intel"
    system: Optional[str] = None
    jumps: Optional[int] = None
    # Keep legacy field for backwards compat
    event_type: str = ""

    def __post_init__(self):
        if not self.event_type:
            self.event_type = self.classification


# ── Pure helper functions (testable without Qt) ───────────────────────────────

def parse_intel_message(text: str) -> dict:
    """Extract system name and any watchlist name hints from an intel text line.

    Returns: {'system': str | None, 'raw': str}
    Does NOT invent system names — returns None when uncertain.
    """
    from core.eve_map_service import EveMapService
    system = EveMapService.instance().extract_system_from_text(text)
    return {'system': system, 'raw': text}


def classify_pilot(name: str, config: IntelAlertConfig) -> str:
    """Return 'safe' | 'watchlist' | 'unknown'."""
    pl = name.lower().strip()
    if pl in {n.lower().strip() for n in config.safe_names if n.strip()}:
        return 'safe'
    if pl in {n.lower().strip() for n in config.watch_names if n.strip()}:
        return 'watchlist'
    return 'unknown'


def should_alert(event: IntelEvent, config: IntelAlertConfig) -> bool:
    """Return True if this event should trigger an alert given the current config."""
    if event.classification == 'safe':
        return False
    if event.classification == 'watchlist' and not config.alert_on_watchlist:
        return False
    if event.classification == 'unknown' and not config.alert_on_unknown:
        return False

    # Distance filtering only applies when max_jumps > 0 and a reference system is set
    if config.max_jumps > 0 and config.current_system.strip() and event.system:
        from core.eve_map_service import EveMapService
        jumps = EveMapService.instance().distance_jumps(
            config.current_system.strip(), event.system
        )
        if jumps is not None:
            return jumps <= config.max_jumps
        return config.alert_unknown_distance

    return True


# ── Service ───────────────────────────────────────────────────────────────────

class IntelAlertService:
    def __init__(self, config: IntelAlertConfig, callback: Callable[[IntelEvent], None]):
        self._config = config
        self._callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Pilots seen in Local this session (keyed by name)
        self._seen_pilots: Set[str] = set()
        # Cooldown: key = "source:pilot_lower:system_or_empty" → timestamp
        self._alert_cooldowns: Dict[str, float] = {}
        self._readers: dict = {}
        self._readers_lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='IntelAlert')
        self._thread.start()
        logger.info("IntelAlertService started (source_mode=%s)", self._config.source_mode)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("IntelAlertService stopped")

    def update_config(self, config: IntelAlertConfig):
        """Thread-safe config update. Resets readers when source/channels change."""
        old_mode = self._config.source_mode
        old_channels = self._config.intel_channels[:]
        self._config = config
        if old_mode != config.source_mode or old_channels != config.intel_channels:
            with self._readers_lock:
                self._readers.clear()
                logger.debug("IntelAlert: readers reset due to source/channel change")

    def reset_session(self):
        """Clear seen-pilot set and cooldowns for a fresh session."""
        self._seen_pilots.clear()
        self._alert_cooldowns.clear()
        logger.debug("IntelAlert: session reset")

    # ------------------------------------------------------------------
    # Channel matching
    # ------------------------------------------------------------------

    def _channel_file_matches(self, fname: str) -> bool:
        stem = fname.split('_')[0].lower() if '_' in fname else fname.lower()
        mode = self._config.source_mode

        is_local = 'local' in stem

        if mode == "local":
            return is_local

        if mode == "intel":
            return self._matches_intel_channels(stem)

        if mode == "both":
            return is_local or self._matches_intel_channels(stem)

        return False

    def _matches_intel_channels(self, stem: str) -> bool:
        channels = self._config.intel_channels
        if channels:
            for ch in channels:
                normalized_ch = ch.lower().replace(' ', '').replace('.', '')
                normalized_stem = stem.replace(' ', '').replace('.', '')
                if normalized_ch in normalized_stem:
                    return True
            return False
        # Fallback when no channels configured: match files containing 'intel'
        return 'intel' in stem

    # ------------------------------------------------------------------
    # Cooldown key
    # ------------------------------------------------------------------

    def _cooldown_key(self, event: IntelEvent) -> str:
        return f"{event.source}:{event.pilot.lower()}:{event.system or ''}"

    # ------------------------------------------------------------------
    # Alert dispatch
    # ------------------------------------------------------------------

    def _fire_alert(self, event: IntelEvent):
        if not should_alert(event, self._config):
            return

        key = self._cooldown_key(event)
        now = time.time()
        if now - self._alert_cooldowns.get(key, 0) < self._config.pilot_cooldown_secs:
            logger.debug("IntelAlert: cooldown skip %s", key)
            return
        self._alert_cooldowns[key] = now

        if self._config.alert_sound:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                try:
                    from PySide6.QtWidgets import QApplication
                    QApplication.beep()
                except Exception:
                    pass

        try:
            self._callback(event)
        except Exception as e:
            logger.debug(f"IntelAlert callback error: {e}")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self):
        from translator.chat_reader import ChatFileReader, _get_chatlog_dir
        chatlog_dir = _get_chatlog_dir()
        if not chatlog_dir:
            logger.warning("IntelAlert: no chatlog dir found")
            return

        while self._running:
            try:
                if not self._config.enabled:
                    time.sleep(2)
                    continue

                cutoff = time.time() - 20 * 60
                for fpath in chatlog_dir.glob('*.txt'):
                    try:
                        if fpath.stat().st_mtime < cutoff:
                            continue
                    except Exception:
                        continue

                    if not self._channel_file_matches(fpath.name):
                        continue

                    with self._readers_lock:
                        if fpath not in self._readers:
                            r = ChatFileReader(fpath)
                            r.initialize(read_existing=False)
                            self._readers[fpath] = r
                        reader = self._readers[fpath]

                    first_part = fpath.name.split('_')[0]
                    is_local = 'local' in first_part.lower()
                    src = "local" if is_local else "intel"

                    for msg in reader.read_new():
                        pilot = msg.sender.strip()
                        if not pilot or pilot in (
                            'EVE System', 'System', 'Sistema', 'Message', 'Mensaje',
                        ):
                            continue

                        if is_local:
                            self._handle_local_pilot(pilot, msg.timestamp, first_part, src)
                        else:
                            self._handle_intel_message(
                                pilot, msg.text, msg.timestamp, first_part, src
                            )

            except Exception as e:
                logger.debug(f"IntelAlert loop error: {e}")

            # Prune stale readers
            try:
                cutoff2 = time.time() - 7200
                with self._readers_lock:
                    stale = [fp for fp in list(self._readers)
                             if fp.stat().st_mtime < cutoff2]
                    for fp in stale:
                        del self._readers[fp]
            except Exception:
                pass

            time.sleep(1.5)

    def _handle_local_pilot(self, pilot: str, ts: str, channel: str, src: str):
        if pilot in self._seen_pilots:
            return
        self._seen_pilots.add(pilot)

        classification = classify_pilot(pilot, self._config)
        if classification == 'safe':
            return

        event = IntelEvent(
            timestamp=ts,
            pilot=pilot,
            channel=channel,
            message=f"{pilot} apareció en Local",
            classification=classification,
            source=src,
            system=self._config.current_system.strip() or None,
            jumps=0 if self._config.current_system.strip() else None,
        )
        self._fire_alert(event)

    def _handle_intel_message(self, sender: str, text: str, ts: str, channel: str, src: str):
        parsed = parse_intel_message(text)
        system = parsed.get('system')

        # Check if any watch_name appears in the text
        text_low = text.lower()
        watch_hit: Optional[str] = None
        for name in self._config.watch_names:
            n = name.lower().strip()
            if n and n in text_low:
                watch_hit = name
                break

        if not watch_hit:
            return  # Intel channel: only alert when watchlist name found in text

        classification = 'watchlist'
        event = IntelEvent(
            timestamp=ts,
            pilot=watch_hit,
            channel=channel,
            message=text[:120],
            classification=classification,
            source=src,
            system=system,
            jumps=None,
        )
        self._fire_alert(event)
