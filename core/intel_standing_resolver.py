"""Intel Standing Resolver — classifies pilots as friendly/neutral/hostile.

Priority order:
1. Manual safe_names → friendly (never alert)
2. Manual watch_names → watchlist (always alert)
3. ESI corp/alliance match → corp/alliance (no alert if ignore_corp_members)
4. ESI good standing (> 0) → good_standing (no alert if ignore_good_standing)
5. ESI bad standing (< 0) → bad_standing (alert if alert_bad_standing)
6. Unknown → neutral (alert if alert_neutrals / alert_on_unknown)

ESI notes:
- Requires scopes: esi-characters.read_contacts.v1 (personal contacts/standings)
- No auth token is integrated yet → ESI standing data not available by default
- When ESI unavailable: falls back to manual lists + neutral classification
- All ESI results are cached (TTL configurable, default 30 min)
"""
import logging
import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger('eve.intel.standing')

_CLASSIFICATION_FRIENDLY = 'friendly'
_CLASSIFICATION_CORP = 'corp'
_CLASSIFICATION_ALLIANCE = 'alliance'
_CLASSIFICATION_GOOD_STANDING = 'good_standing'
_CLASSIFICATION_NEUTRAL = 'neutral'
_CLASSIFICATION_BAD_STANDING = 'bad_standing'
_CLASSIFICATION_WATCHLIST = 'watchlist'
_CLASSIFICATION_UNKNOWN = 'unknown'


@dataclass
class StandingResult:
    classification: str           # one of _CLASSIFICATION_* constants
    should_alert: bool
    reason: str
    character_id: Optional[int] = None
    cached: bool = False


class IntelStandingResolver:
    """Resolves pilot standing/classification for Intel Alert filtering.

    Config keys consumed from IntelAlertConfig:
      safe_names, watch_names,
      ignore_corp_members (bool, default True),
      ignore_good_standing (bool, default True),
      alert_neutrals (bool, default True),
      alert_bad_standing (bool, default True)

    ESI standing data is not available without an authenticated token.
    When ESI is unavailable, unknown pilots are classified as neutral.
    """

    def __init__(self, ttl_seconds: int = 1800):
        self._cache: Dict[str, tuple] = {}  # name_lower -> (result, timestamp)
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def resolve(self, pilot_name: str, config) -> StandingResult:
        """Return StandingResult for pilot_name given the current config."""
        name_lower = pilot_name.lower().strip()

        # 1. Manual safe list
        safe = {n.lower().strip() for n in getattr(config, 'safe_names', []) if n.strip()}
        if name_lower in safe:
            return StandingResult(_CLASSIFICATION_FRIENDLY, False, "manual_safe")

        # 2. Manual watch list
        watch = {n.lower().strip() for n in getattr(config, 'watch_names', []) if n.strip()}
        if name_lower in watch:
            return StandingResult(_CLASSIFICATION_WATCHLIST, True, "manual_watch")

        # 3. Check cache
        with self._lock:
            cached = self._cache.get(name_lower)
            if cached:
                result, ts = cached
                if time.time() - ts < self._ttl:
                    # Recompute should_alert based on current config flags
                    result = self._apply_config_flags(result, config)
                    result.cached = True
                    return result
                del self._cache[name_lower]

        # 4. ESI lookup (not available without auth token)
        result = self._try_esi_lookup(pilot_name, config)
        if result is None:
            # Fallback: unknown/neutral
            alert_neutral = getattr(config, 'alert_neutrals', True) or getattr(config, 'alert_on_unknown', True)
            result = StandingResult(
                _CLASSIFICATION_NEUTRAL,
                alert_neutral,
                "esi_unavailable_classified_neutral",
            )

        with self._lock:
            self._cache[name_lower] = (result, time.time())

        return result

    def _try_esi_lookup(self, pilot_name: str, config) -> Optional[StandingResult]:
        """Attempt ESI lookup. Returns None when ESI is not available."""
        # ESI personal contacts/standings require an authenticated token with
        # esi-characters.read_contacts.v1 scope. This is not integrated yet.
        # When auth is available, implement:
        #   1. Resolve pilot_name → character_id (via /universe/ids/)
        #   2. Fetch /characters/{main_char_id}/contacts/
        #   3. Match character_id in contacts list
        #   4. Check standing value: > 0 → good, < 0 → bad, = 0 → neutral
        #   5. Check corp/alliance match against main char's corp/alliance
        logger.debug(f"ESI standing not available for {pilot_name!r} (no auth token)")
        return None

    def _apply_config_flags(self, result: StandingResult, config) -> StandingResult:
        """Recalculate should_alert from config flags without changing classification."""
        c = result.classification
        if c == _CLASSIFICATION_FRIENDLY or c == 'safe':
            should = False
        elif c == _CLASSIFICATION_WATCHLIST:
            should = getattr(config, 'alert_on_watchlist', True)
        elif c in (_CLASSIFICATION_CORP, _CLASSIFICATION_ALLIANCE):
            should = not getattr(config, 'ignore_corp_members', True)
        elif c == _CLASSIFICATION_GOOD_STANDING:
            should = not getattr(config, 'ignore_good_standing', True)
        elif c == _CLASSIFICATION_BAD_STANDING:
            should = getattr(config, 'alert_bad_standing', True)
        else:
            # neutral / unknown
            should = getattr(config, 'alert_neutrals', True) or getattr(config, 'alert_on_unknown', True)
        return StandingResult(c, should, result.reason, result.character_id)

    def clear_cache(self):
        with self._lock:
            self._cache.clear()

    def esi_status(self) -> str:
        """Human-readable ESI availability status."""
        return "Standing ESI no disponible — usando listas manuales + neutrales desconocidos"


# Module-level singleton
_resolver: Optional[IntelStandingResolver] = None


def get_resolver() -> IntelStandingResolver:
    global _resolver
    if _resolver is None:
        _resolver = IntelStandingResolver()
    return _resolver
