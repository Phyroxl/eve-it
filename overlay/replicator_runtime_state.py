"""
overlay/replicator_runtime_state.py
Lightweight shared runtime state for the Replicator.
No Qt imports. No circular dependencies.
Imported by both replicator_hotkeys.py and replication_overlay.py.
"""
import time

# Visual suspension window triggered by each accepted hotkey cycle.
HOTKEY_BURST_VISUAL_SUSPEND_MS: int = 120

# Minimum ms between burst log/diag entries to avoid spam.
HOTKEY_BURST_LOG_THROTTLE_MS: int = 500

_burst_until: float = 0.0
_burst_count: int = 0
_burst_last_log: float = 0.0


def note_hotkey_burst_event(reason: str = "cycle") -> None:
    """Extend the visual suspension window. Called on each accepted hotkey cycle."""
    global _burst_until, _burst_count
    now = time.perf_counter()
    _burst_until = max(_burst_until, now + HOTKEY_BURST_VISUAL_SUSPEND_MS / 1000.0)
    _burst_count += 1


def is_hotkey_burst_active() -> bool:
    """True while the visual suspension window is active. Cheap — no I/O."""
    return time.perf_counter() < _burst_until


def get_hotkey_burst_remaining_ms() -> float:
    """Milliseconds remaining in the current burst window (0.0 if inactive)."""
    return max(0.0, (_burst_until - time.perf_counter()) * 1000.0)


def get_hotkey_burst_count() -> int:
    """Total accepted hotkey cycles since module load."""
    return _burst_count


def should_log_burst() -> bool:
    """True if enough time has passed since last burst log entry (throttle).
    Updates internal timestamp when True — call only once per logging site.
    """
    global _burst_last_log
    now = time.perf_counter()
    if (now - _burst_last_log) * 1000.0 >= HOTKEY_BURST_LOG_THROTTLE_MS:
        _burst_last_log = now
        return True
    return False
