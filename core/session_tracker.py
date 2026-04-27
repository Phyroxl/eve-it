"""
session_tracker.py — Motor de cálculo ISK en tiempo real.
"""

from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict, Set
import json
import threading

from core.tick_calculator import TickCalculator
import logging

_EVT_PAYOUT = 'payout'

logger = logging.getLogger('eve.tracker')

# ── Estados de personaje (semáforo) ──────────────────────────────────────────
class CharStatus:
    ACTIVE   = 'active'    # 🟢 tiene eventos recientes
    IDLE     = 'idle'      # 🟡 detectado pero sin eventos aún / inactivo
    INACTIVE = 'inactive'  # 🔴 sin eventos en mucho tiempo (configurable)

class IdentityStatus:
    PENDING   = 'pending'
    RESOLVING = 'resolving'
    RESOLVED  = 'resolved'
    FAILED    = 'failed'


class CharacterSession:

    def __init__(self, character_name: str, wall_start: datetime):
        self.character = character_name
        self.character_id: Optional[int] = None
        self.portrait_url: Optional[str] = None
        self.id_status = IdentityStatus.PENDING
        self.total_isk = 0
        self.events: list[dict] = []
        self.wall_start: datetime = wall_start
        self.last_event_time: Optional[datetime] = None
        self.detected_at: datetime = datetime.now()
        
        # Iniciar resolución de identidad en background
        self._trigger_identity_resolution()
        
        # Wall clock del último evento procesado — para calcular inactividad real.
        # Independiente del timestamp del log (que puede estar en el pasado).
        self.last_processed_at: Optional[datetime] = None
        self._rolling_window_minutes = 15
        self._rolling_events: deque = deque()
        self._latest_event_ts: Optional[datetime] = None
        # Motor de cálculo de ticks ESS (módulo separado)
        self._tick_calc: TickCalculator = TickCalculator()
        
    def _trigger_identity_resolution(self):
        """Intenta resolver el Character ID y Portrait URL de forma asíncrona."""
        if self.id_status != IdentityStatus.PENDING:
            return

        def worker():
            from utils.eve_api import resolve_character_id, build_character_portrait_url
            self.id_status = IdentityStatus.RESOLVING
            try:
                char_id = resolve_character_id(self.character)
                if char_id:
                    self.character_id = char_id
                    self.portrait_url = build_character_portrait_url(char_id)
                    self.id_status = IdentityStatus.RESOLVED
                    logger.info(f"Identidad resuelta: {self.character} -> {char_id}")
                else:
                    self.id_status = IdentityStatus.FAILED
            except Exception as e:
                self.id_status = IdentityStatus.FAILED
                logger.debug(f"Error silencioso en resolución de {self.character}: {e}")
                
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def add_event(self, timestamp: datetime, isk: int, raw_line: str = '',
                 processed_at: Optional[datetime] = None,
                 evt_type: str = 'individual'):
        self.total_isk += isk
        self.last_event_time = timestamp
        self._latest_event_ts = timestamp
        wall = processed_at or datetime.now()
        self.last_processed_at = wall
        self.events.append({'timestamp': timestamp, 'isk': isk, 'line': raw_line})
        self._rolling_events.append((timestamp, isk))
        self._prune_rolling_window(timestamp)
        # Pasar is_payout al TickCalculator para detección precisa. Usar 'timestamp' (hora real del evento)
        self._tick_calc.record_event(timestamp, isk, is_payout=(evt_type == _EVT_PAYOUT))

    def _prune_rolling_window(self, reference: datetime):
        cutoff = reference - timedelta(minutes=self._rolling_window_minutes)
        while self._rolling_events and self._rolling_events[0][0] < cutoff:
            self._rolling_events.popleft()

    def get_tick_info(self, now: Optional[datetime] = None) -> dict:
        """Delega al TickCalculator. Garantiza compatibilidad de campos con la UI."""
        result = self._tick_calc.get_tick_info(now or datetime.now())
        # Añadir campo 'session_isk' para compatibilidad con UI existente
        result['session_isk'] = self.total_isk
        # Alias de campos para compatibilidad con código que usaba 'last_tick_ts'
        if 'last_payout_at' in result and 'last_tick_ts' not in result:
            result['last_tick_ts'] = result['last_payout_at']
        return result

    def get_session_duration(self, now: Optional[datetime] = None) -> timedelta:
        return (now or datetime.now()) - self.wall_start

    def get_isk_per_hour_session(self, now: Optional[datetime] = None) -> float:
        hours = self.get_session_duration(now).total_seconds() / 3600
        if hours < 0.001:
            return 0.0
        return self.total_isk / hours

    def get_rolling_isk_per_hour(self) -> float:
        if not self._rolling_events or self._latest_event_ts is None:
            return 0.0
        self._prune_rolling_window(self._latest_event_ts)
        if not self._rolling_events:
            return 0.0
        window_isk = sum(isk for _, isk in self._rolling_events)
        oldest = self._rolling_events[0][0]
        window_seconds = max((self._latest_event_ts - oldest).total_seconds(), 60.0)
        return (window_isk / window_seconds) * 3600

    def get_isk_per_minute_session(self, now: Optional[datetime] = None) -> float:
        if not self.events:
            return 0.0
        first_ts = self.events[0]['timestamp']
        last_ts = self.last_event_time or first_ts
        span_minutes = max((last_ts - first_ts).total_seconds() / 60, 1.0)
        return self.total_isk / span_minutes

    def get_inactivity_duration(self, now: Optional[datetime] = None) -> timedelta:
        """
        Usa wall clock real (last_processed_at) para medir inactividad.
        Evita el desfase entre timestamps del log y datetime.now():
        si un evento del log dice 22:18:49 pero el tracker se inició a las
        22:20:00, la inactividad real es de ~1min, no de horas.
        """
        now = now or datetime.now()
        if self.last_processed_at is not None:
            return now - self.last_processed_at
        if self.last_event_time is None:
            return now - self.detected_at
        # Fallback: si no hay processed_at, usar detected_at para personajes sin eventos
        return now - self.detected_at

    def get_status(self, inactive_threshold_minutes: float = 5.0,
                   now: Optional[datetime] = None) -> str:
        """
        Máquina de estados:
          IDLE     → detectado, sin eventos aún (siempre desde 0, nunca INACTIVE)
          ACTIVE   → tiene eventos y último procesado hace < inactive_threshold
          INACTIVE → tuvo eventos pero lleva > inactive_threshold sin actividad

        IMPORTANTE: un personaje SIN eventos nunca es INACTIVE, siempre IDLE.
        La inactividad se mide por wall clock (last_processed_at), no por
        el timestamp del log, para evitar falsos positivos.
        """
        now = now or datetime.now()

        if not self.events:
            # Sin eventos → siempre IDLE, nunca INACTIVE
            return CharStatus.IDLE

        # Con eventos: medir por wall clock real
        inactivity_secs = self.get_inactivity_duration(now).total_seconds()
        if inactivity_secs > inactive_threshold_minutes * 60:
            return CharStatus.INACTIVE
        return CharStatus.ACTIVE

    def is_inactive(self, threshold_minutes: float = 2.5, now: Optional[datetime] = None) -> bool:
        return self.get_inactivity_duration(now).total_seconds() > threshold_minutes * 60

    def reset(self, wall_start: datetime):
        self.total_isk = 0
        self.events.clear()
        self._rolling_events.clear()
        self._tick_calc.reset()
        self.wall_start = wall_start
        self.last_event_time = None
        self._latest_event_ts = None
        self.last_processed_at = None
        self.detected_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            'character': self.character,
            'total_isk': self.total_isk,
            'wall_start': self.wall_start.isoformat(),
            'last_event_time': self.last_event_time.isoformat() if self.last_event_time else None,
            'event_count': len(self.events),
            'events': [
                {'timestamp': e['timestamp'].isoformat(), 'isk': e['isk']}
                for e in self.events
            ]
        }


class MultiAccountTracker:

    def __init__(self, inactivity_threshold_minutes: float = 2.5):
        self.sessions: dict[str, CharacterSession] = {}
        self._sessions_lock = threading.RLock()
        self.inactivity_threshold = inactivity_threshold_minutes
        self.wall_start: datetime = datetime.now()
        self.isk_history: deque = deque(maxlen=3600)
        self._alias: dict[str, str] = {}
        self.is_paused = False
        self.pause_start = None
        self.total_paused_seconds = 0

    # ── Gestión de nombres ────────────────────────────────────────────────────

    def _normalize_character(self, raw_name: str) -> str:
        return self._alias.get(raw_name, raw_name)

    def register_character(self, name: str):
        """
        Registra un personaje INMEDIATAMENTE al detectar su log,
        aunque no haya generado eventos todavía.
        Crea una sesión vacía sincronizada con wall_start global.
        Idempotente: no hace nada si ya existe.
        """
        canonical = self._normalize_character(name)
        with self._sessions_lock:
            if canonical not in self.sessions:
                self.sessions[canonical] = CharacterSession(canonical, self.wall_start)

    def register_alias(self, alias: str, canonical_name: str):
        if not alias or not canonical_name or alias == canonical_name:
            return
        with self._sessions_lock:
            self._alias[alias] = canonical_name

        if alias in self.sessions and canonical_name not in self.sessions:
            self.sessions[canonical_name] = self.sessions.pop(alias)
            self.sessions[canonical_name].character = canonical_name
        elif alias in self.sessions and canonical_name in self.sessions:
            src = self.sessions.pop(alias)
            dst = self.sessions[canonical_name]
            dst.total_isk += src.total_isk
            dst.events.extend(src.events)
            for ev in src._rolling_events:
                dst._rolling_events.append(ev)
            if src.last_event_time:
                if dst.last_event_time is None or src.last_event_time > dst.last_event_time:
                    dst.last_event_time = src.last_event_time
            if src._latest_event_ts:
                if dst._latest_event_ts is None or src._latest_event_ts > dst._latest_event_ts:
                    dst._latest_event_ts = src._latest_event_ts

    def resolve_name(self, char_id: str) -> str:
        return self._normalize_character(char_id)

    def register_character_name(self, char_id: str, name: str):
        self.register_alias(char_id, name)

    def remove_character(self, name: str):
        """Elimina un personaje de la sesión activa."""
        canonical = self._normalize_character(name)
        if canonical in self.sessions:
            del self.sessions[canonical]
            logger.info(f"Personaje eliminado del tracker: {canonical}")

    # ── Eventos ───────────────────────────────────────────────────────────────

    def add_event(self, character: str, timestamp: datetime, isk: int,
                  raw_line: str = '', processed_at: Optional[datetime] = None,
                  evt_type: str = 'individual'):
        canonical = self._normalize_character(character)
        with self._sessions_lock:
            if canonical not in self.sessions:
                self.sessions[canonical] = CharacterSession(canonical, self.wall_start)
            self.sessions[canonical].add_event(timestamp, isk, raw_line, processed_at, evt_type)
        # El historial usa processed_at (wall clock real) para que el gráfico
        # muestre siempre timestamps correctos, independientemente de si los
        # eventos vienen de logs históricos con fechas antiguas.
        chart_ts = processed_at or datetime.now()
        self.isk_history.append({
            'timestamp': chart_ts,
            'total_isk': self.get_total_isk(),
            'character': canonical,
            'event_isk': isk
        })

    # ── Métricas ──────────────────────────────────────────────────────────────

    def get_total_isk(self) -> int:
        return sum(s.total_isk for s in self.sessions.values())

    def get_total_isk_per_hour_session(self, now: Optional[datetime] = None) -> float:
        hours = ((now or datetime.now()) - self.wall_start).total_seconds() / 3600
        if hours < 0.001:
            return 0.0
        return self.get_total_isk() / hours

    def get_rolling_isk_per_hour(self) -> float:
        return sum(s.get_rolling_isk_per_hour() for s in self.sessions.values())

    def get_total_isk_per_minute_session(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now()
        all_last = [s.last_event_time for s in self.sessions.values() if s.last_event_time]
        all_first = [s.events[0]['timestamp'] for s in self.sessions.values() if s.events]
        if not all_first:
            minutes = (now - self.wall_start).total_seconds() / 60
            if minutes < 0.1:
                return 0.0
            return self.get_total_isk() / minutes
        span_minutes = max((max(all_last) - min(all_first)).total_seconds() / 60, 1.0)
        return self.get_total_isk() / span_minutes

    def get_total_session_duration(self, now: Optional[datetime] = None) -> timedelta:
        now = now or datetime.now()
        duration = now - self.wall_start
        pause_sec = self.total_paused_seconds
        if self.is_paused and self.pause_start:
            pause_sec += (now - self.pause_start).total_seconds()
        return timedelta(seconds=max(0, duration.total_seconds() - pause_sec))

    def get_main_character(self) -> str:
        from pathlib import Path
        import json
        _cfg_file = Path(__file__).resolve().parent.parent / "_main_char.json"
        try:
            return json.loads(_cfg_file.read_text(encoding="utf-8")).get("main", "")
        except Exception:
            return ""

    def get_inactive_characters(self, now: Optional[datetime] = None) -> list[str]:
        return [n for n, s in self.sessions.items() if s.is_inactive(self.inactivity_threshold, now)]

    def get_summary(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now()
        duration = self.get_total_session_duration(now)
        rolling_isk_h = self.get_rolling_isk_per_hour()
        isk_per_hour_session = self.get_total_isk_per_hour_session(now)
        isk_per_min = self.get_total_isk_per_minute_session(now)

        per_character = []
        online_count = 0
        for char_id, s in self.sessions.items():
            status = s.get_status(self.inactivity_threshold, now)
            if status in [CharStatus.ACTIVE, CharStatus.IDLE]:
                online_count += 1
            inactivity = s.get_inactivity_duration(now)
            
            # Preparación para retratos reales
            char_uid = getattr(s, 'character_id', None)
            portrait_url = getattr(s, 'portrait_url', None)
            
            per_character.append({
                'character': char_id,
                'display_name': char_id,
                'character_id': char_uid,
                'portrait_url': portrait_url,
                'id_status': getattr(s, 'id_status', 'pending'),
                'total_isk': s.total_isk,
                'isk_per_hour': s.get_rolling_isk_per_hour(),
                'isk_per_hour_session': s.get_isk_per_hour_session(now),
                'isk_per_minute': s.get_isk_per_minute_session(now),
                'event_count': len(s.events),
                'is_inactive': s.is_inactive(self.inactivity_threshold, now),
                'inactivity_seconds': inactivity.total_seconds(),
                'last_event': s.last_event_time,
                'last_processed_at': s.last_processed_at,
                'status': s.get_status(inactive_threshold_minutes=5.0, now=now),
                'has_events': len(s.events) > 0,
                'tick_info': s.get_tick_info(now),
                'session_isk': s.total_isk,  # wallet de sesión
                'events': s.events[-20:], # Últimos 20 eventos para el feed
            })

        # Ordenar: primero activos con más ISK, luego idle, luego inactivos
        def sort_key(c):
            order = {CharStatus.ACTIVE: 0, CharStatus.IDLE: 1, CharStatus.INACTIVE: 2}
            return (order.get(c['status'], 1), -c['total_isk'])
        per_character.sort(key=sort_key)

        return {
            'total_isk': self.get_total_isk(),
            'session_duration': duration,
            'session_hours': duration.total_seconds() / 3600,
            'session_minutes': duration.total_seconds() / 60,
            'isk_per_hour_total': self.get_total_isk_per_hour_session(now),
            'isk_per_hour_rolling': rolling_isk_h,
            'isk_per_minute': isk_per_min,
            'per_character': per_character,
            'inactive_characters': self.get_inactive_characters(now),
            'character_count': len(self.sessions),
            'main_character': self.get_main_character(),
            'now': now,
            'is_paused': self.is_paused,
        }

    def reset_all(self):
        self.wall_start = datetime.now()
        self.isk_history.clear()
        self.is_paused = False
        self.pause_start = None
        self.total_paused_seconds = 0
        # No borrar las sesiones ni los alias, solo resetear el ISK y tiempo de cada uno
        for s in self.sessions.values():
            s.reset(self.wall_start)
        logger.info("Tracker reset (contadores a cero, personajes mantenidos)")

    def pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.pause_start = datetime.now()

    def resume(self):
        if self.is_paused:
            self.is_paused = False
            if self.pause_start:
                self.total_paused_seconds += (datetime.now() - self.pause_start).total_seconds()
                self.pause_start = None

    def toggle_pause(self):
        if self.is_paused:
            self.resume()
        else:
            self.pause()

    def reset_character(self, character: str):
        canonical = self._normalize_character(character)
        if canonical in self.sessions:
            self.sessions[canonical].reset(datetime.now())

    def save_history(self, filepath: str = "isk_history.json"):
        data = {
            'saved_at': datetime.now().isoformat(),
            'wall_start': self.wall_start.isoformat(),
            'total_isk': self.get_total_isk(),
            'session_duration_seconds': self.get_total_session_duration().total_seconds(),
            'sessions': {name: s.to_dict() for name, s in self.sessions.items()}
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath

    def get_isk_history_for_chart(self) -> list[dict]:
        return list(self.isk_history)
