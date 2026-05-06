"""Intel Alert Service — scans EVE chatlogs for hostile/unknown pilots."""
import threading
import time
import logging
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger('eve.intel')

CONFIG_FILE = Path(__file__).resolve().parent.parent / 'config' / 'intel_alert.json'


@dataclass
class IntelAlertConfig:
    enabled: bool = True
    alert_sound: bool = True
    alert_on_unknown: bool = True
    monitored_channels: List[str] = field(default_factory=lambda: ['ch_local'])
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


@dataclass
class IntelEvent:
    timestamp: str
    pilot: str
    channel: str
    message: str
    event_type: str  # 'local_new' | 'watchlist_hit' | 'intel_msg'


class IntelAlertService:
    def __init__(self, config: IntelAlertConfig, callback: Callable[[IntelEvent], None]):
        self._config = config
        self._callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._seen_pilots: Set[str] = set()
        self._alert_cooldowns: Dict[str, float] = {}
        self._readers: dict = {}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='IntelAlert')
        self._thread.start()
        logger.info("IntelAlertService started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("IntelAlertService stopped")

    def update_config(self, config: IntelAlertConfig):
        self._config = config

    def reset_session(self):
        self._seen_pilots.clear()
        self._alert_cooldowns.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _channel_file_matches(self, fname: str) -> bool:
        stem = fname.split('_')[0].lower() if '_' in fname else fname.lower()
        for ch in self._config.monitored_channels:
            ch_low = ch.lower()
            if ch_low in ('ch_local', 'local') and 'local' in stem:
                return True
            if ch_low in ('ch_fleet', 'fleet') and ('fleet' in stem or 'flota' in stem):
                return True
            if ch_low in ('ch_corp', 'corp') and 'corp' in stem:
                return True
            if ch_low in ('ch_alliance', 'alliance') and ('alliance' in stem or 'alianza' in stem):
                return True
            # Custom channel name match (e.g. "Delve.Intel")
            if ch_low.replace(' ', '') in stem.replace(' ', ''):
                return True
        return False

    def _fire_alert(self, event: IntelEvent):
        key = event.pilot.lower()
        now = time.time()
        if now - self._alert_cooldowns.get(key, 0) < self._config.pilot_cooldown_secs:
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

    def _classify_local_pilot(self, pilot: str) -> Optional[str]:
        pl = pilot.lower().strip()
        safe = {n.lower().strip() for n in self._config.safe_names}
        watch = {n.lower().strip() for n in self._config.watch_names}
        if pl in safe:
            return None
        if pl in watch:
            return 'watchlist_hit'
        if self._config.alert_on_unknown:
            return 'local_new'
        return None

    def _check_intel_text(self, text: str) -> Optional[str]:
        text_low = text.lower()
        for name in self._config.watch_names:
            n = name.lower().strip()
            if n and n in text_low:
                return 'intel_msg'
        return None

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

                    if fpath not in self._readers:
                        r = ChatFileReader(fpath)
                        r.initialize(read_existing=False)
                        self._readers[fpath] = r

                    is_local = 'local' in fpath.name.split('_')[0].lower()
                    ch_name = fpath.name.split('_')[0]

                    for msg in self._readers[fpath].read_new():
                        pilot = msg.sender.strip()
                        if not pilot or pilot in ('EVE System', 'System', 'Sistema', 'Message', 'Mensaje'):
                            continue

                        if is_local:
                            if pilot not in self._seen_pilots:
                                self._seen_pilots.add(pilot)
                                ev_type = self._classify_local_pilot(pilot)
                                if ev_type:
                                    self._fire_alert(IntelEvent(
                                        timestamp=msg.timestamp,
                                        pilot=pilot,
                                        channel=ch_name,
                                        message=f"{pilot} apareció en Local",
                                        event_type=ev_type,
                                    ))
                        else:
                            ev_type = self._check_intel_text(msg.text)
                            if ev_type:
                                self._fire_alert(IntelEvent(
                                    timestamp=msg.timestamp,
                                    pilot=pilot,
                                    channel=ch_name,
                                    message=msg.text[:120],
                                    event_type=ev_type,
                                ))

            except Exception as e:
                logger.debug(f"IntelAlert loop error: {e}")

            # Prune stale readers every cycle
            try:
                stale = [fp for fp in list(self._readers) if fp.stat().st_mtime < time.time() - 7200]
                for fp in stale:
                    del self._readers[fp]
            except Exception:
                pass

            time.sleep(1.5)
