"""EVE Map Service — extensible distance API.

Current state: no SDE / route dataset available.
- is_available() returns False.
- distance_jumps() returns None (distance unknown).
- extract_system_from_text() uses heuristics on EVE system name patterns.

TODO: load universe/systems + stargates from SDE to enable BFS routing.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger('eve.map')

# Pattern for null/low-sec system names like 1DQ1-A, MJ-5F9, J-GAMP, X-7OMU
_NULL_SYSTEM_RE = re.compile(r'\b([A-Z0-9]{1,6}-[A-Z0-9]{1,6})\b', re.IGNORECASE)
# Common words to exclude from proper-name heuristic
_COMMON_WORDS = frozenset({
    'Your', 'Gate', 'This', 'That', 'With', 'From', 'Into', 'Warp',
    'Jump', 'Camp', 'Navy', 'Corp', 'Kill', 'Star', 'Belt', 'Moon',
    'Null', 'Blue', 'Neut', 'Safe', 'Dock', 'Hold', 'Drop',
})


class EveMapService:
    """Singleton distance service. Returns None for all distances until SDE data is loaded."""

    _instance: Optional['EveMapService'] = None

    @classmethod
    def instance(cls) -> 'EveMapService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Returns True when route data is loaded and distance_jumps can resolve routes."""
        return False

    def normalize_system_name(self, name: str) -> str:
        return name.strip()

    def extract_system_from_text(self, text: str) -> Optional[str]:
        """Try to extract an EVE system name from a line of intel text.

        Priority:
        1. Null/low-sec pattern  (e.g. "1DQ1-A", "MJ-5F9")
        2. Proper-noun heuristic (e.g. "Jita", "Amarr VI")

        Returns None when no credible system name is found.
        Does NOT invent names — returns None rather than guessing.
        """
        m = _NULL_SYSTEM_RE.search(text)
        if m:
            return m.group(1).upper()

        # Proper-noun heuristic: Title-case word(s), 4+ chars, not a common word
        for tok in re.findall(r'\b([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]+)?)\b', text):
            if tok not in _COMMON_WORDS:
                return tok

        return None

    def distance_jumps(self, from_system: str, to_system: str) -> Optional[int]:
        """Return jump count between two systems, or None if route unavailable.

        NOTE: Always returns None — no SDE loaded. Respects alert_unknown_distance
        in IntelAlertService to decide whether to alert when distance is unknown.
        """
        # Exact match (same system) can be answered without data
        a = self.normalize_system_name(from_system).upper()
        b = self.normalize_system_name(to_system).upper()
        if a and b and a == b:
            return 0
        return None  # TODO: BFS over stargate graph once SDE is loaded
