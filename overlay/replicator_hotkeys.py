"""
overlay/replicator_hotkeys.py
Hotkeys Phase 2: per-client focus + cycle navigation.

Uses Win32 RegisterHotKey on a dedicated background thread.
Hotkeys are only active when cfg['hotkeys']['global_enabled'] = True.
EULA-safe: only calls focus_eve_window(), never injects input to the game.
"""
import ctypes
import ctypes.wintypes as wt
import threading
import logging
import queue
from collections import deque
from typing import Dict, Callable, List, Optional

logger = logging.getLogger('eve.hotkeys')

_VK_MAP = {
    'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73,
    'F5': 0x74, 'F6': 0x75, 'F7': 0x76, 'F8': 0x77,
    'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
    'F13': 0x7C, 'F14': 0x7D, 'F15': 0x7E, 'F16': 0x7F,
    'F17': 0x80, 'F18': 0x81, 'F19': 0x82, 'F20': 0x83,
    'F21': 0x84, 'F22': 0x85, 'F23': 0x86, 'F24': 0x87,
}
for _i, _c in enumerate('0123456789'):
    _VK_MAP[_c] = 0x30 + _i
for _i, _c in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    _VK_MAP[_c] = 0x41 + _i

_MOD_ALT      = 0x0001
_MOD_CTRL     = 0x0002
_MOD_SHIFT    = 0x0004
_MOD_WIN      = 0x0008
_MOD_NOREPEAT = 0x4000

_MOD_NAME = {
    'ALT': _MOD_ALT, 'CTRL': _MOD_CTRL, 'CONTROL': _MOD_CTRL,
    'SHIFT': _MOD_SHIFT, 'WIN': _MOD_WIN,
}

WM_HOTKEY = 0x0312

_user32   = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# Thread state
_thread: Optional[threading.Thread] = None
_running = False
_id_seq = 0
_lock = threading.Lock()

# Cache for instant switching
_hwnd_cache: Dict[str, int] = {}
_cached_titles: List[str] = []

# Per-group last-activated index for deterministic cycles
_last_group_index: Dict[str, int] = {}

# Snapshot of the last registered hk_cfg — used by note_active_client_changed
# to update all group indices when a client is activated by a non-hotkey path.
_last_hk_cfg: dict = {}

# ── Fast-path performance state ──────────────────────────────────────────────

# Minimum ms between accepted cycles.
# Lowered to 10 ms for experimental high-speed macro testing.
MIN_CYCLE_INTERVAL_MS: int = 10

# Extra settle guard: capture threads stay suspended for this many ms after focus.
# Reduces BitBlt competition with the DWM compositing triggered by focus change.
CAPTURE_SUSPEND_MS: int = 150

# How long last_cycle_client_id is considered authoritative for index resolution.
FOCUS_SETTLE_MS: int = 80

_cycle_in_progress: bool = False          # Safety guard (same-thread re-entry)
_last_cycle_time: float = 0.0             # monotonic() of last *accepted* cycle
_last_cycle_client_id: Optional[str] = None       # Title of last focused client
_last_cycle_client_id_time: float = 0.0           # monotonic() of above

# Written by _cycle/_cycle_group; read by CaptureThread.run() in replication_overlay.
# CaptureThread skips one frame while < now, reducing competition with Win32 focus.
_capture_suspended_until: float = 0.0

# ── Last focus-done snapshot (passive macro timing diagnostics) ───────────────
_last_focus_done_time: float = 0.0
_last_focus_done_hwnd: int = 0
_last_focus_done_target: str = ''
_last_focus_done_ok: bool = False

# ── Passive macro key hook (WH_KEYBOARD_LL, F1–F8 observation only) ──────────
_WH_KEYBOARD_LL: int = 13
_WM_KEYDOWN: int = 0x0100
_WM_SYSKEYDOWN: int = 0x0104
_WM_QUIT_MSG: int = 0x0012
_MACRO_VK_TO_NAME: dict = {
    0x70: 'F1', 0x71: 'F2', 0x72: 'F3', 0x73: 'F4',
    0x74: 'F5', 0x75: 'F6', 0x76: 'F7', 0x77: 'F8',
}
_REPLICA_PREFIXES: tuple = ('Replica - ', 'Réplica - ', 'Replica — ', 'Réplica — ')
_EVE_CLIENT_PREFIX: str = 'EVE — '   # 'EVE — ' (em-dash) — strict client title prefix
MACRO_COMPLETION_GUARD_MS: int = 70        # min ms between verified focus and next accepted cycle
_MACRO_SEQ_WINDOW_MS: float = 300.0
_focus_epoch_id: int = 0
_macro_hook_handle = None
_macro_hook_thread: Optional[threading.Thread] = None
_macro_hook_running: bool = False
_macro_seq_epoch_id: int = -1
_macro_seq_target: str = ''
_macro_seq_focus_hwnd: int = 0
_macro_seq_focus_ok: bool = False
_macro_seq_keys: list = []
_macro_seq_key_times: list = []
_macro_seq_key_deltas: list = []
_macro_seq_key_fg_hwnds: list = []
_macro_seq_last_key_perf: float = 0.0
_macro_stats_total: int = 0
_macro_stats_complete_safe: int = 0
_macro_stats_complete_risky: int = 0
_macro_stats_incomplete: int = 0
_macro_stats_fg_mismatch: int = 0
_macro_stats_min_first_delta: float = float('inf')
_macro_stats_max_first_delta: float = 0.0
_macro_stats_recommended_min_delay: float = 0.0
_macro_observed_epochs: set = set()
_macro_missing_pending_epoch: int = -1
_macro_missing_pending_target: str = ''
_macro_missing_pending_time: float = 0.0
_macro_stats_missing_after_focus: int = 0
_macro_stats_missing_targets: list = []
_focus_failed_epochs: set = set()
_macro_stats_focus_failed: int = 0
_macro_stats_focus_failed_targets: list = []
_macro_stats_stale_count: int = 0
_macro_stats_stale_targets: list = []
_macro_stats_valid_for_delay: int = 0
_macro_target_stats: dict = {}
_last_verified_focus_perf: float = 0.0      # perf_counter() of last ok=True focus
_non_client_rejection_titles: dict = {}     # fg_title → rejection count

# ── Live diagnostics (zero-overhead when disabled) ────────────────────────────
_hotkey_diagnostics_enabled: bool = False
_hotkey_diagnostics_callback = None
_hotkey_diagnostics_events: deque = deque(maxlen=1000)


# ── Compact perf logger (FileHandler stays open — no open/close per call) ────

_perf_logger: Optional[logging.Logger] = None

def _get_perf_logger() -> Optional[logging.Logger]:
    global _perf_logger
    if _perf_logger is not None:
        return _perf_logger
    try:
        from utils.paths import ROOT_DIR
        log_dir = ROOT_DIR / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        lgr = logging.getLogger('eve.hotkey_perf')
        lgr.setLevel(logging.DEBUG)
        lgr.propagate = False
        if not lgr.handlers:
            fh = logging.FileHandler(
                str(log_dir / 'hotkey_perf.log'), encoding='utf-8', mode='a'
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter('%(message)s'))
            lgr.addHandler(fh)
        _perf_logger = lgr
    except Exception:
        pass
    return _perf_logger


def _perf_log(msg: str):
    """Write one compact line to hotkey_perf.log. FileHandler stays open → fast."""
    try:
        lgr = _get_perf_logger()
        if lgr:
            import datetime
            ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
            lgr.info(f'{ts} {msg}')
    except Exception:
        pass


def _log_to_file(msg: str):
    """Legacy debug logger — kept for backward compat, not called in hot path."""
    try:
        from utils.paths import ROOT_DIR
        import datetime
        log_dir = ROOT_DIR / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / 'hotkey_order_debug.log', 'a', encoding='utf-8') as f:
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f'[{ts}] {msg}\n')
    except Exception:
        pass


def _is_replica_window_title(title: str) -> bool:
    """Return True if title belongs to an EVE iT overlay window, not an actual EVE client."""
    return bool(title and any(title.startswith(p) for p in _REPLICA_PREFIXES))


def _is_eve_client_title(title: str) -> bool:
    """Return True only if title is a genuine EVE game client (starts with 'EVE — ')."""
    return bool(title and title.startswith(_EVE_CLIENT_PREFIX))


# ── Public diagnostics API ────────────────────────────────────────────────────

def set_hotkey_diagnostics_enabled(enabled: bool, callback=None):
    """Enable/disable live diagnostics. callback(event_dict) is called from hotkey thread."""
    global _hotkey_diagnostics_enabled, _hotkey_diagnostics_callback
    if enabled:
        _hotkey_diagnostics_enabled = True
        _hotkey_diagnostics_callback = callback
        _install_macro_key_hook()
    else:
        # Uninstall FIRST while still enabled so _check_and_emit_missing_macro can fire.
        _uninstall_macro_key_hook()
        _hotkey_diagnostics_enabled = False
        _hotkey_diagnostics_callback = None


def clear_hotkey_diagnostics():
    """Clear the in-memory event ring buffer and reset cumulative stats."""
    global _macro_stats_total, _macro_stats_complete_safe, _macro_stats_complete_risky
    global _macro_stats_incomplete, _macro_stats_fg_mismatch
    global _macro_stats_min_first_delta, _macro_stats_max_first_delta, _macro_stats_recommended_min_delay
    global _macro_stats_missing_after_focus, _macro_stats_missing_targets
    global _macro_missing_pending_epoch, _macro_missing_pending_target, _macro_missing_pending_time
    global _macro_stats_focus_failed, _macro_stats_focus_failed_targets
    global _macro_stats_stale_count, _macro_stats_stale_targets, _macro_stats_valid_for_delay
    global _last_verified_focus_perf
    _hotkey_diagnostics_events.clear()
    _macro_stats_total = 0
    _macro_stats_complete_safe = 0
    _macro_stats_complete_risky = 0
    _macro_stats_incomplete = 0
    _macro_stats_fg_mismatch = 0
    _macro_stats_min_first_delta = float('inf')
    _macro_stats_max_first_delta = 0.0
    _macro_stats_recommended_min_delay = 0.0
    _macro_stats_missing_after_focus = 0
    _macro_stats_missing_targets = []
    _macro_stats_focus_failed = 0
    _macro_stats_focus_failed_targets = []
    _macro_stats_stale_count = 0
    _macro_stats_stale_targets = []
    _macro_stats_valid_for_delay = 0
    _macro_observed_epochs.clear()
    _focus_failed_epochs.clear()
    _macro_target_stats.clear()
    _macro_missing_pending_epoch = -1
    _macro_missing_pending_target = ''
    _macro_missing_pending_time = 0.0
    _last_verified_focus_perf = 0.0
    _non_client_rejection_titles.clear()


def get_hotkey_diagnostics_events():
    """Return a snapshot of current diagnostic events."""
    return list(_hotkey_diagnostics_events)


def get_macro_summary() -> dict:
    """Return cumulative macro sequence diagnostics summary."""
    per_tgt = {}
    for tgt, ts in _macro_target_stats.items():
        per_tgt[tgt] = dict(ts)
        min_d = ts['min_first_delta_valid_ms']
        per_tgt[tgt]['min_first_delta_valid_ms'] = round(min_d, 1) if min_d < float('inf') else 0.0
    return {
        'total_macro_sequences': _macro_stats_total,
        'complete_safe_count': _macro_stats_complete_safe,
        'complete_risky_count': _macro_stats_complete_risky,
        'incomplete_count': _macro_stats_incomplete,
        'foreground_mismatch_count': _macro_stats_fg_mismatch,
        'min_first_delta_seen_ms': round(_macro_stats_min_first_delta, 1) if _macro_stats_min_first_delta < float('inf') else 0.0,
        'max_first_delta_seen_ms': round(_macro_stats_max_first_delta, 1),
        'recommended_min_delay_ms': round(_macro_stats_recommended_min_delay, 1),
        'missing_after_focus_count': _macro_stats_missing_after_focus,
        'missing_after_focus_targets': list(_macro_stats_missing_targets),
        'focus_failed_count': _macro_stats_focus_failed,
        'focus_failed_targets': list(_macro_stats_focus_failed_targets),
        'stale_or_unrelated_count': _macro_stats_stale_count,
        'stale_or_unrelated_targets': list(_macro_stats_stale_targets),
        'valid_sequences_for_delay': _macro_stats_valid_for_delay,
        'non_client_foreground_rejection_count': sum(_non_client_rejection_titles.values()),
        'non_client_foreground_rejections': dict(_non_client_rejection_titles),
        'per_target_summary': per_tgt,
    }


def _diag_event(event_type: str, **data):
    """Record one diagnostic event. No-op (returns immediately) when disabled."""
    if not _hotkey_diagnostics_enabled:
        return
    import datetime
    event = {
        'type': event_type,
        'ts': datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
        **data,
    }
    _hotkey_diagnostics_events.append(event)
    cb = _hotkey_diagnostics_callback
    if cb:
        try:
            cb(event)
        except Exception:
            pass


def _check_and_emit_missing_macro(reason: str) -> None:
    """If a previous ok-focus has no observed macro keys yet, emit macro_missing_after_focus."""
    global _macro_missing_pending_epoch, _macro_missing_pending_target, _macro_missing_pending_time
    global _macro_stats_missing_after_focus
    if _macro_missing_pending_epoch < 0:
        return
    if not _hotkey_diagnostics_enabled:
        _macro_missing_pending_epoch = -1
        _macro_missing_pending_target = ''
        _macro_missing_pending_time = 0.0
        return
    if _macro_missing_pending_epoch in _macro_observed_epochs:
        _macro_missing_pending_epoch = -1
        _macro_missing_pending_target = ''
        _macro_missing_pending_time = 0.0
        return
    import time as _t
    epoch = _macro_missing_pending_epoch
    target = _macro_missing_pending_target
    elapsed_ms = (_t.perf_counter() - _macro_missing_pending_time) * 1000.0 if _macro_missing_pending_time > 0 else 0.0
    _macro_stats_missing_after_focus += 1
    if target and target not in _macro_stats_missing_targets:
        _macro_stats_missing_targets.append(target)
    _diag_event('macro_missing_after_focus',
        epoch=epoch,
        target=target,
        reason=reason,
        elapsed_since_focus_ms=round(elapsed_ms, 1),
    )
    _perf_log(
        f'[MACRO MISSING] epoch={epoch} target={target!r} reason={reason} '
        f'elapsed_ms={elapsed_ms:.1f}'
    )
    _macro_missing_pending_epoch = -1
    _macro_missing_pending_target = ''
    _macro_missing_pending_time = 0.0
    if target:
        _ts_for(target)['missing_after_focus_count'] += 1
        _ts_for(target)['last_status'] = 'missing_after_focus'


def _ts_for(target: str) -> dict:
    """Get or create the per-target stats dict for a given target title."""
    if target not in _macro_target_stats:
        _macro_target_stats[target] = {
            'focus_ok_count': 0,
            'focus_failed_count': 0,
            'macro_sequences_count': 0,
            'missing_after_focus_count': 0,
            'stale_or_unrelated_count': 0,
            'invalid_focus_count': 0,
            'min_first_delta_valid_ms': float('inf'),
            'max_first_delta_valid_ms': 0.0,
            'last_status': '',
        }
    return _macro_target_stats[target]


# ── Passive macro timing helpers ──────────────────────────────────────────────

def _get_last_focus_done_snapshot() -> dict:
    return {
        'time': _last_focus_done_time,
        'hwnd': _last_focus_done_hwnd,
        'target': _last_focus_done_target,
        'ok': _last_focus_done_ok,
    }


def _on_macro_key(vk: int) -> None:
    """Called from hook thread on each F1–F8 keydown. Purely observational — no blocking."""
    global _macro_seq_keys, _macro_seq_key_times, _macro_seq_last_key_perf
    global _macro_seq_epoch_id, _macro_seq_target, _macro_seq_focus_hwnd, _macro_seq_focus_ok
    global _macro_seq_key_deltas, _macro_seq_key_fg_hwnds
    if not _hotkey_diagnostics_enabled:
        return
    import time as _t
    now_perf = _t.perf_counter()

    delta_ms = (now_perf - _last_focus_done_time) * 1000.0 if _last_focus_done_time > 0 else -1.0
    key_name = _MACRO_VK_TO_NAME.get(vk, f'VK_{vk:#x}')
    try:
        from overlay.win32_capture import get_foreground_hwnd
        fg_hwnd = get_foreground_hwnd()
    except Exception:
        fg_hwnd = 0

    if 0.0 <= delta_ms < 5000.0:
        if delta_ms < 30.0:
            timing_class = 'too_early'
        elif delta_ms < 50.0:
            timing_class = 'risky'
        else:
            timing_class = 'safer'
        fg_matches = bool(fg_hwnd and _last_focus_done_hwnd and fg_hwnd == _last_focus_done_hwnd)
        _diag_event('macro_key_observed',
            epoch=_focus_epoch_id,
            key=key_name, vk=vk,
            delta_after_focus_done_ms=round(delta_ms, 1),
            timing_class=timing_class,
            fg_hwnd=fg_hwnd,
            fg_matches_focus_hwnd=fg_matches,
            focus_target=_last_focus_done_target,
            focus_hwnd=_last_focus_done_hwnd,
            focus_ok=_last_focus_done_ok,
        )
        _macro_observed_epochs.add(_focus_epoch_id)
        _perf_log(
            f'[MACRO INPUT] epoch={_focus_epoch_id} key={key_name} delta={delta_ms:.1f}ms '
            f'class={timing_class} fg_hwnd={fg_hwnd} fg_match={fg_matches} '
            f'focus_target={_last_focus_done_target!r}'
        )

    # MACRO_SEQ grouping — split on epoch change or inter-key timeout
    current_epoch = _focus_epoch_id
    elapsed_since_last = (
        (now_perf - _macro_seq_last_key_perf) * 1000.0
        if _macro_seq_last_key_perf > 0 else _MACRO_SEQ_WINDOW_MS + 1
    )
    epoch_changed = bool(_macro_seq_keys) and (_macro_seq_epoch_id != current_epoch)
    timed_out = bool(_macro_seq_keys) and elapsed_since_last > _MACRO_SEQ_WINDOW_MS
    if epoch_changed or timed_out:
        _flush_macro_seq()

    if not _macro_seq_keys:
        _macro_seq_epoch_id = current_epoch
        _macro_seq_target = _last_focus_done_target
        _macro_seq_focus_hwnd = _last_focus_done_hwnd
        _macro_seq_focus_ok = _last_focus_done_ok

    _macro_seq_keys.append(vk)
    _macro_seq_key_times.append(now_perf)
    _macro_seq_key_deltas.append(max(delta_ms, 0.0))
    _macro_seq_key_fg_hwnds.append(fg_hwnd)
    _macro_seq_last_key_perf = now_perf


def _flush_macro_seq() -> None:
    """Finalize and emit the current MACRO_SEQ with per-epoch analysis. Clears seq state."""
    global _macro_seq_keys, _macro_seq_key_times, _macro_seq_last_key_perf
    global _macro_seq_epoch_id, _macro_seq_target, _macro_seq_focus_hwnd, _macro_seq_focus_ok
    global _macro_seq_key_deltas, _macro_seq_key_fg_hwnds
    global _macro_stats_total, _macro_stats_complete_safe, _macro_stats_complete_risky
    global _macro_stats_incomplete, _macro_stats_fg_mismatch
    global _macro_stats_min_first_delta, _macro_stats_max_first_delta, _macro_stats_recommended_min_delay
    global _macro_stats_stale_count, _macro_stats_stale_targets, _macro_stats_valid_for_delay
    if not _macro_seq_keys:
        return

    seen_names = [_MACRO_VK_TO_NAME.get(vk, f'VK_{vk:#x}') for vk in _macro_seq_keys]
    seen_vk_set = set(_macro_seq_keys)
    missing_names = [name for vk, name in _MACRO_VK_TO_NAME.items() if vk not in seen_vk_set]
    seq_duration_ms = (
        (_macro_seq_key_times[-1] - _macro_seq_key_times[0]) * 1000.0
        if len(_macro_seq_key_times) > 1 else 0.0
    )

    deltas = _macro_seq_key_deltas
    first_delta = deltas[0] if deltas else 0.0
    last_delta = deltas[-1] if deltas else 0.0
    min_delta = min(deltas) if deltas else 0.0
    max_delta = max(deltas) if deltas else 0.0

    focus_hwnd = _macro_seq_focus_hwnd
    too_early_keys = [_MACRO_VK_TO_NAME.get(_macro_seq_keys[i], '') for i, d in enumerate(deltas) if d < 30.0]
    risky_keys = [_MACRO_VK_TO_NAME.get(_macro_seq_keys[i], '') for i, d in enumerate(deltas) if 30.0 <= d < 50.0]
    fg_mismatch_keys = [
        _MACRO_VK_TO_NAME.get(_macro_seq_keys[i], '')
        for i, fgh in enumerate(_macro_seq_key_fg_hwnds)
        if focus_hwnd and fgh and fgh != focus_hwnd
    ]

    has_fg_mismatch = bool(fg_mismatch_keys)
    has_missing = bool(missing_names)
    epoch_id = _macro_seq_epoch_id
    target = _macro_seq_target
    focus_failed_epoch = (epoch_id >= 0 and epoch_id in _focus_failed_epochs)

    if focus_failed_epoch:
        status = 'invalid_focus'
    elif first_delta > 1000.0:
        status = 'stale_or_unrelated'
    elif has_fg_mismatch:
        status = 'foreground_mismatch'
    elif has_missing:
        status = 'incomplete'
    elif first_delta < 50.0:
        status = 'complete_risky'
    else:
        status = 'complete_safe'

    import math
    if status in ('stale_or_unrelated', 'invalid_focus'):
        rec_delay = 0.0
    elif status in ('foreground_mismatch', 'incomplete'):
        rec_delay = max(80.0, first_delta + 20.0)
    elif first_delta < 50.0:
        rec_delay = 50.0
    elif first_delta < 70.0:
        rec_delay = 70.0
    else:
        rec_delay = math.ceil(first_delta / 10.0) * 10.0

    _diag_event('macro_seq_complete',
        epoch=epoch_id,
        target=target,
        focus_hwnd=focus_hwnd,
        focus_ok=_macro_seq_focus_ok,
        focus_failed_epoch=focus_failed_epoch,
        keys_seen=seen_names,
        keys_missing=missing_names,
        key_count=len(_macro_seq_keys),
        seq_duration_ms=round(seq_duration_ms, 1),
        first_key_delta_ms=round(first_delta, 1),
        last_key_delta_ms=round(last_delta, 1),
        min_delta_ms=round(min_delta, 1),
        max_delta_ms=round(max_delta, 1),
        too_early_keys=too_early_keys,
        risky_keys=risky_keys,
        fg_mismatch_keys=fg_mismatch_keys,
        sequence_status=status,
        recommended_min_delay_ms=round(rec_delay, 1),
    )
    _perf_log(
        f'[MACRO SEQ] epoch={epoch_id} target={target!r} status={status} '
        f'keys={seen_names} missing={missing_names} count={len(_macro_seq_keys)} '
        f'duration_ms={seq_duration_ms:.1f} first={first_delta:.1f}ms last={last_delta:.1f}ms '
        f'too_early={too_early_keys} risky={risky_keys} fg_mismatch={fg_mismatch_keys} '
        f'rec_delay={rec_delay:.0f}ms'
    )

    _macro_stats_total += 1
    if status == 'complete_safe':
        _macro_stats_complete_safe += 1
    elif status == 'complete_risky':
        _macro_stats_complete_risky += 1
    elif status == 'incomplete':
        _macro_stats_incomplete += 1
    elif status == 'foreground_mismatch':
        _macro_stats_fg_mismatch += 1
    elif status == 'stale_or_unrelated':
        _macro_stats_stale_count += 1
        if target and target not in _macro_stats_stale_targets:
            _macro_stats_stale_targets.append(target)
    valid_for_delay = rec_delay > 0
    if valid_for_delay:
        _macro_stats_valid_for_delay += 1
    if status not in ('stale_or_unrelated', 'invalid_focus') and first_delta > 0:
        _macro_stats_min_first_delta = min(_macro_stats_min_first_delta, first_delta)
        _macro_stats_max_first_delta = max(_macro_stats_max_first_delta, first_delta)
    if rec_delay > 0:
        _macro_stats_recommended_min_delay = max(_macro_stats_recommended_min_delay, rec_delay)

    # ── Per-target stats ──────────────────────────────────────────────────────
    if target:
        _ts = _ts_for(target)
        _ts['macro_sequences_count'] += 1
        _ts['last_status'] = status
        if status == 'stale_or_unrelated':
            _ts['stale_or_unrelated_count'] += 1
        elif status == 'invalid_focus':
            _ts['invalid_focus_count'] += 1
        elif valid_for_delay and first_delta > 0:
            _ts['min_first_delta_valid_ms'] = min(_ts['min_first_delta_valid_ms'], first_delta)
            _ts['max_first_delta_valid_ms'] = max(_ts['max_first_delta_valid_ms'], first_delta)

    _macro_seq_keys = []
    _macro_seq_key_times = []
    _macro_seq_key_deltas = []
    _macro_seq_key_fg_hwnds = []
    _macro_seq_last_key_perf = 0.0
    _macro_seq_epoch_id = -1
    _macro_seq_target = ''
    _macro_seq_focus_hwnd = 0
    _macro_seq_focus_ok = False


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode',      ctypes.c_ulong),
        ('scanCode',    ctypes.c_ulong),
        ('flags',       ctypes.c_ulong),
        ('time',        ctypes.c_ulong),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


_HOOKPROC_TYPE = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wt.WPARAM, wt.LPARAM
)
_macro_hook_proc_ref = None


def _macro_hook_loop() -> None:
    """Dedicated thread: installs WH_KEYBOARD_LL, pumps messages, uninstalls on exit."""
    global _macro_hook_handle, _macro_hook_proc_ref

    def _proc(nCode, wParam, lParam):
        try:
            if nCode >= 0 and wParam in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if kb.vkCode in _MACRO_VK_TO_NAME:
                    _on_macro_key(kb.vkCode)
        except Exception:
            pass
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    _macro_hook_proc_ref = _HOOKPROC_TYPE(_proc)
    _macro_hook_handle = _user32.SetWindowsHookExW(
        _WH_KEYBOARD_LL, _macro_hook_proc_ref, None, 0
    )
    if not _macro_hook_handle:
        logger.warning(f'[MACRO HOOK] SetWindowsHookExW failed err={_kernel32.GetLastError()}')
        _macro_hook_proc_ref = None
        return

    logger.debug('[MACRO HOOK] WH_KEYBOARD_LL installed')
    msg = wt.MSG()
    while _macro_hook_running:
        ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret <= 0:
            break
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))

    _user32.UnhookWindowsHookEx(_macro_hook_handle)
    _macro_hook_handle = None
    _macro_hook_proc_ref = None
    logger.debug('[MACRO HOOK] WH_KEYBOARD_LL uninstalled')


def _install_macro_key_hook() -> None:
    global _macro_hook_thread, _macro_hook_running
    if _macro_hook_thread and _macro_hook_thread.is_alive():
        return
    _macro_hook_running = True
    _macro_hook_thread = threading.Thread(
        target=_macro_hook_loop, daemon=True, name='macro-key-hook'
    )
    _macro_hook_thread.start()


def _uninstall_macro_key_hook() -> None:
    global _macro_hook_running, _macro_hook_thread
    _macro_hook_running = False
    t = _macro_hook_thread
    if t and t.is_alive():
        tid = t.ident
        if tid:
            _user32.PostThreadMessageW(tid, _WM_QUIT_MSG, 0, 0)
        t.join(timeout=1.0)
    _macro_hook_thread = None
    _check_and_emit_missing_macro('diagnostic_stopped_without_macro')
    _flush_macro_seq()


# ── Hotkey parsing ────────────────────────────────────────────────────────────

def parse_hotkey(combo: str) -> tuple:
    """Parse 'CTRL+F13' → (mods_int, vk_int). Returns (0, 0) if invalid/empty."""
    if not combo or not combo.strip():
        return (0, 0)
    mods = _MOD_NOREPEAT
    vk = 0
    for part in combo.upper().split('+'):
        part = part.strip()
        if part in _MOD_NAME:
            mods |= _MOD_NAME[part]
        elif part in _VK_MAP:
            vk = _VK_MAP[part]
        else:
            logger.debug(f'Unknown hotkey token: {part!r}')
    return (mods, vk)


def _normalize_hotkey(combo: str) -> str:
    """Normalize a hotkey combo to canonical uppercase form (e.g. 'ctrl+f14' → 'CTRL+F14')."""
    if not combo or not combo.strip():
        return ''
    return '+'.join(p.strip().upper() for p in combo.split('+'))


def _next_id() -> int:
    global _id_seq
    _id_seq += 1
    return _id_seq


# ── Listener thread ───────────────────────────────────────────────────────────

def _listener_thread(registrations: list):
    """Background thread: register hotkeys, pump messages, unregister on exit."""
    registered: Dict[int, Callable] = {}

    for mods, vk, cb in registrations:
        if not vk:
            continue
        hk_id = _next_id()
        if _user32.RegisterHotKey(None, hk_id, mods, vk):
            registered[hk_id] = cb
            logger.info(f'RegisterHotKey id={hk_id} mods={mods:#x} vk={vk:#x}')
        else:
            err = _kernel32.GetLastError()
            logger.warning(f'RegisterHotKey failed mods={mods:#x} vk={vk:#x} err={err}')

    if not registered:
        logger.debug('No hotkeys registered -- listener exits')
        return

    msg = wt.MSG()
    import time
    while _running:
        if _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == WM_HOTKEY:
                hk_id = msg.wParam
                cb = registered.get(hk_id)
                if cb:
                    try:
                        cb()
                    except Exception as e:
                        logger.error(f'Hotkey cb error: {e}')
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        else:
            time.sleep(0.005)  # 5 ms polling — near-instant response, low CPU

    for hk_id in registered:
        _user32.UnregisterHotKey(None, hk_id)
    logger.debug('Hotkey listener stopped, all hotkeys unregistered')


# ── Window-handle cache ───────────────────────────────────────────────────────

def update_hotkey_cache(titles: List[str]):
    """Pre-populate hwnd cache for all active overlay titles."""
    global _hwnd_cache, _cached_titles
    from overlay.win32_capture import resolve_eve_window_handle, is_hwnd_valid
    new_cache: Dict[str, int] = {}
    for t in titles:
        existing = _hwnd_cache.get(t)
        if existing and is_hwnd_valid(existing):
            new_cache[t] = existing
        else:
            hwnd = resolve_eve_window_handle(t)
            if hwnd:
                new_cache[t] = hwnd
    with _lock:
        _hwnd_cache = new_cache
        _cached_titles = list(titles)
    logger.debug(f'[REPLICATOR HOTKEY] Cache updated: {len(_hwnd_cache)} clients')


def note_active_client_changed(title: str, source: str = 'external') -> None:
    """Sync hotkey cycle state when a client becomes active via a non-hotkey path.

    Must be called whenever focus changes outside the hotkey cycle — e.g. a
    direct replica click — so the next hotkey press resumes from the correct
    position instead of from a stale last_group_index or last_cycle_client_id.

    Thread-safe: only writes module-level globals and reads _last_hk_cfg
    (immutable after register_hotkeys) and _cached_titles (list, safe to read).
    """
    import time as _time
    global _last_cycle_client_id, _last_cycle_client_id_time

    if not title:
        return

    now = _time.monotonic()
    old_client = _last_cycle_client_id

    _last_cycle_client_id = title
    _last_cycle_client_id_time = now

    groups = _last_hk_cfg.get('groups', {})
    updated_groups: dict = {}
    not_in_groups: list = []

    for group_id, group in groups.items():
        if not group.get('enabled'):
            continue
        titles = group.get('clients_order', [])
        if title in titles:
            old_idx = _last_group_index.get(group_id, -1)
            new_idx = titles.index(title)
            _last_group_index[group_id] = new_idx
            updated_groups[group_id] = {
                'name': group.get('name', group_id),
                'old_idx': old_idx,
                'new_idx': new_idx,
            }
        else:
            not_in_groups.append(group_id)

    # Update global cycle index as well
    old_global = _last_group_index.get('__global__', -1)
    if title in _cached_titles:
        new_global = _cached_titles.index(title)
        _last_group_index['__global__'] = new_global
    else:
        new_global = old_global

    logger.debug(
        f"[CYCLE SYNC] active_changed source={source} client={title!r} "
        f"old_client={old_client!r} "
        f"global_idx: {old_global} -> {new_global} "
        f"groups_updated={updated_groups} "
        f"not_in_groups={not_in_groups}"
    )


# ── Main registration ─────────────────────────────────────────────────────────

def register_hotkeys(cfg: dict, cycle_titles_getter: Callable[[], List[str]] = None):
    """Register all enabled hotkeys from cfg.
    EULA-safe: only calls focus_eve_window(), no game input injection.
    """
    global _thread, _running, _last_hk_cfg

    unregister_hotkeys()

    hk_cfg = cfg.get('hotkeys', {})
    _last_hk_cfg = hk_cfg  # snapshot for note_active_client_changed lookups
    registrations = []

    # ── Per-client hotkeys ────────────────────────────────────────────────────
    for title, entry in hk_cfg.get('per_client', {}).items():
        combo = entry.get('combo', '') if isinstance(entry, dict) else str(entry)
        mods, vk = parse_hotkey(combo)
        if not vk:
            continue

        def _focus_cb(t=title):
            global _last_cycle_client_id, _last_cycle_client_id_time, _capture_suspended_until
            from overlay.win32_capture import focus_eve_window_perf, resolve_eve_window_handle, is_hwnd_valid
            import time as _time
            t0  = _time.perf_counter()
            now = _time.monotonic()
            hwnd = _hwnd_cache.get(t)
            if not hwnd or not is_hwnd_valid(hwnd):
                hwnd = resolve_eve_window_handle(t)
                if hwnd:
                    _hwnd_cache[t] = hwnd
            if hwnd:
                _capture_suspended_until = now + CAPTURE_SUSPEND_MS / 1000.0
                ok, focus_detail = focus_eve_window_perf(hwnd)
                _perf_log(f'[FOCUS PERF] target={t!r} {focus_detail}')
                if ok:
                    from overlay.replication_overlay import ReplicationOverlay
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                    _last_cycle_client_id = t
                    _last_cycle_client_id_time = now
                total_ms = (_time.perf_counter() - t0) * 1000
                _perf_log(f'[HOTKEY PERF] per_client target={t!r} focus_ok={ok} total_ms={total_ms:.1f}')

        registrations.append((mods, vk, _focus_cb))

    # ── Fast-path cycle closures ──────────────────────────────────────────────
    # Both _cycle and _cycle_group share the same guard/cooldown state so a
    # per-client focus and a group cycle don't race each other.

    def _cycle(direction: int):
        """Global cycle over _cached_titles / cycle_titles_getter order."""
        global _cycle_in_progress, _last_cycle_time
        global _last_cycle_client_id, _last_cycle_client_id_time
        global _capture_suspended_until
        global _last_focus_done_time, _last_focus_done_hwnd, _last_focus_done_target, _last_focus_done_ok
        global _focus_epoch_id
        global _macro_missing_pending_epoch, _macro_missing_pending_target, _macro_missing_pending_time
        global _macro_stats_focus_failed, _macro_stats_focus_failed_targets
        global _last_verified_focus_perf
        import time as _time

        t0  = _time.perf_counter()
        now = _time.monotonic()

        _diag_event('cycle_enter', direction='next' if direction > 0 else 'prev',
            scope='global', last_client=_last_cycle_client_id,
            last_global_idx=_last_group_index.get('__global__', -1),
            cooldown_remaining_ms=max(0.0, MIN_CYCLE_INTERVAL_MS - (now - _last_cycle_time) * 1000) if _last_cycle_time > 0 else 0.0,
            in_progress=_cycle_in_progress)

        # ── Anti-accumulation guards ──
        if _cycle_in_progress:
            _perf_log(
                f'[HOTKEY PERF] skipped hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'reason=in_progress since_ms={(now - _last_cycle_time)*1000:.1f}'
            )
            _diag_event('cycle_skipped', scope='global', reason='in_progress',
                direction='next' if direction > 0 else 'prev',
                since_ms=round((now - _last_cycle_time) * 1000, 1))
            return
        delta_ms = (now - _last_cycle_time) * 1000
        if _last_cycle_time > 0 and delta_ms < MIN_CYCLE_INTERVAL_MS:
            _perf_log(
                f'[HOTKEY PERF] skipped hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'reason=cooldown delta_ms={delta_ms:.1f}'
            )
            _diag_event('cycle_skipped', scope='global', reason='cooldown',
                direction='next' if direction > 0 else 'prev',
                delta_ms=round(delta_ms, 1), min_ms=MIN_CYCLE_INTERVAL_MS)
            return

        if _last_verified_focus_perf > 0:
            _guard_elapsed_ms = (t0 - _last_verified_focus_perf) * 1000.0
            if _guard_elapsed_ms < MACRO_COMPLETION_GUARD_MS:
                _perf_log(
                    f'[MACRO DELAY GUARD] scope=global elapsed_ms={_guard_elapsed_ms:.1f} '
                    f'min={MACRO_COMPLETION_GUARD_MS}ms'
                )
                _diag_event('macro_delay_guard', scope='global',
                    elapsed_ms=round(_guard_elapsed_ms, 1), min_ms=MACRO_COMPLETION_GUARD_MS)
                return

        _cycle_in_progress = True
        _last_cycle_time   = now
        _check_and_emit_missing_macro('next_cycle_without_macro')
        if _macro_seq_keys:
            _flush_macro_seq()

        try:
            from overlay.win32_capture import (
                get_foreground_hwnd, get_window_title,
                focus_eve_window_reliable, resolve_eve_window_handle, is_hwnd_valid,
            )
            from overlay.replication_overlay import ReplicationOverlay, _OVERLAY_REGISTRY

            titles = _cached_titles or (cycle_titles_getter() if cycle_titles_getter else [])
            if not titles:
                return

            logger.debug(
                f"[CYCLE SYNC] hotkey_enter group=__global__ "
                f"dir={'next' if direction > 0 else 'prev'} "
                f"last_client={_last_cycle_client_id!r} "
                f"last_global_idx={_last_group_index.get('__global__', -1)} "
                f"last_client_age_ms={round((now - _last_cycle_client_id_time) * 1000, 1) if _last_cycle_client_id_time else None}"
            )

            # ── Resolve current index ─────────────────────────────────────
            # Priority: last_cycle_client_id (deterministic, avoids stale fg)
            #           → foreground hwnd / title  → saved index
            t_res = _time.perf_counter()
            current_idx = -1
            used_last   = False
            _diag_resolver = 'none'
            _diag_fg_hwnd = 0
            _diag_fg_title = ''
            _diag_fg_match_idx = -1

            if (_last_cycle_client_id and _last_cycle_client_id in titles
                    and (now - _last_cycle_client_id_time) < 5.0):
                current_idx = titles.index(_last_cycle_client_id)
                used_last   = True
                _diag_resolver = 'last_cycle_client_id'

            if current_idx == -1:
                fg_hwnd = get_foreground_hwnd()
                _diag_fg_hwnd = fg_hwnd
                if fg_hwnd:
                    fg_title = get_window_title(fg_hwnd)
                    _diag_fg_title = fg_title or ''
                    if fg_title:
                        if not _is_eve_client_title(fg_title):
                            _perf_log(f'[FOREGROUND_REJECTED_AS_NON_CLIENT] hwnd={fg_hwnd} title={fg_title!r}')
                            _diag_event('foreground_rejected_as_non_client', fg_hwnd=fg_hwnd, fg_title=fg_title)
                            _non_client_rejection_titles[fg_title] = _non_client_rejection_titles.get(fg_title, 0) + 1
                        else:
                            try:
                                current_idx = next(
                                    i for i, t in enumerate(titles)
                                    if t == fg_title or (t and t in fg_title)
                                )
                                _diag_fg_match_idx = current_idx
                                if current_idx != -1:
                                    _diag_resolver = 'foreground_title'
                            except StopIteration:
                                pass
                    if current_idx == -1:
                        for ov in list(_OVERLAY_REGISTRY):
                            if ov._hwnd and ov._hwnd == fg_hwnd and ov._title in titles:
                                current_idx = titles.index(ov._title)
                                _diag_fg_match_idx = current_idx
                                _diag_resolver = 'foreground_overlay_hwnd'
                                break

            if current_idx == -1:
                current_idx = _last_group_index.get('__global__', -1)
                if current_idx != -1 and _diag_resolver == 'none':
                    _diag_resolver = 'last_group_index'

            resolve_ms = (_time.perf_counter() - t_res) * 1000
            _diag_mismatch = (
                _diag_fg_match_idx != -1 and current_idx != -1
                and _diag_fg_match_idx != current_idx
                and _diag_resolver in ('last_cycle_client_id', 'last_group_index')
            )
            _diag_event('foreground_snapshot', scope='global',
                fg_hwnd=_diag_fg_hwnd, fg_title=_diag_fg_title, fg_match_idx=_diag_fg_match_idx)
            _diag_event('current_index_resolved', scope='global',
                current_idx=current_idx,
                current_title=titles[current_idx] if 0 <= current_idx < len(titles) else None,
                resolver_used=_diag_resolver,
                last_client=_last_cycle_client_id,
                last_client_age_ms=round((now - _last_cycle_client_id_time) * 1000, 1) if _last_cycle_client_id_time else None,
                fg_hwnd=_diag_fg_hwnd, fg_title=_diag_fg_title, fg_idx=_diag_fg_match_idx,
                mismatch=_diag_mismatch)

            # ── Find target ───────────────────────────────────────────────
            start    = current_idx if current_idx != -1 else (-1 if direction > 0 else 0)
            target   = target_hwnd = None
            next_idx = -1

            for attempt in range(1, len(titles) + 1):
                idx  = (start + direction * attempt) % len(titles)
                t    = titles[idx]
                hwnd = _hwnd_cache.get(t)
                if not hwnd or not is_hwnd_valid(hwnd):
                    hwnd = resolve_eve_window_handle(t)
                    if hwnd:
                        _hwnd_cache[t] = hwnd
                if hwnd and is_hwnd_valid(hwnd):
                    target, target_hwnd, next_idx = t, hwnd, idx
                    _diag_event('target_selected', scope='global',
                        source_idx=current_idx,
                        source_title=titles[current_idx] if 0 <= current_idx < len(titles) else None,
                        target_idx=next_idx, target_title=t, target_hwnd=hwnd,
                        cache_hit=(_hwnd_cache.get(t) == hwnd))
                    break

            if not target_hwnd:
                _perf_log(
                    f'[HOTKEY PERF] failed hotkey=cycle direction={"next" if direction>0 else "prev"} '
                    f'entry=_cycle reason=no_valid_window'
                )
                return

            # ── Suspend capture for CAPTURE_SUSPEND_MS — reduces BitBlt competition ──
            _capture_suspended_until = now + CAPTURE_SUSPEND_MS / 1000.0

            # ── Mark hotkey burst — suspends visual updates for 120 ms ──
            try:
                from overlay.replicator_runtime_state import (
                    note_hotkey_burst_event, should_log_burst, get_hotkey_burst_count,
                )
                note_hotkey_burst_event("cycle")
                if should_log_burst():
                    _cnt = get_hotkey_burst_count()
                    _perf_log(f'[HOTKEY BURST] active suspend_ms=120 count={_cnt}')
                    _diag_event('burst_visual_suspend', suspend_ms=120, count=_cnt, reason='cycle')
            except Exception:
                pass

            # ── Focus target — reliable multi-strategy (verified internally) ──
            ok, focus_detail = focus_eve_window_reliable(target_hwnd)
            _perf_log(f'[FOCUS PERF] target={target!r} {focus_detail}')
            _diag_event('focus_result', scope='global', target_title=target, target_hwnd=target_hwnd,
                focus_ok=ok, focus_detail=focus_detail, source_idx=current_idx, target_idx=next_idx,
                total_ms=round((_time.perf_counter() - t0) * 1000, 1))

            # ok=True means foreground already verified inside focus_eve_window_reliable
            verified = ok
            _dp = {}
            for _p in focus_detail.split():
                if '=' in _p:
                    _k, _, _v = _p.partition('=')
                    _dp[_k] = _v
            verify_ms = float(_dp.get('verify_ms', 0) or 0)
            actual_hwnd = int(_dp.get('actual', 0) or 0)
            _strategy = _dp.get('strategy', 'unknown')
            _diag_event('focus_verify_result', scope='global',
                target_title=target, target_hwnd=target_hwnd,
                requested_ok=ok, verified=verified, actual_hwnd=actual_hwnd,
                verify_ms=round(verify_ms, 1), source_idx=current_idx, target_idx=next_idx)

            if ok:
                _last_group_index['__global__'] = next_idx
                _last_cycle_client_id           = target
                _last_cycle_client_id_time      = now
                _last_verified_focus_perf       = _time.perf_counter()
                ReplicationOverlay.notify_active_client_changed(target_hwnd)

            total_ms = (_time.perf_counter() - t0) * 1000
            _perf_log(
                f'[HOTKEY PERF] accepted hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'entry=_cycle source_idx={current_idx} target_idx={next_idx} target={target!r} '
                f'resolve_ms={resolve_ms:.1f} total_ms={total_ms:.1f} '
                f'focus_ok={ok} focus_verified={verified} strategy={_strategy} '
                f'verify_ms={verify_ms:.1f} used_last_cycle={used_last}'
            )
            _focus_epoch_id += 1
            _last_focus_done_time   = _time.perf_counter()
            _last_focus_done_hwnd   = target_hwnd if ok else 0
            _last_focus_done_target = target or ''
            _last_focus_done_ok     = ok
            if ok:
                _macro_missing_pending_epoch = _focus_epoch_id
                _macro_missing_pending_target = target or ''
                _macro_missing_pending_time = _last_focus_done_time
                if target:
                    _ts_for(target)['focus_ok_count'] += 1
            else:
                _focus_failed_epochs.add(_focus_epoch_id)
                _macro_stats_focus_failed += 1
                if target and target not in _macro_stats_focus_failed_targets:
                    _macro_stats_focus_failed_targets.append(target)
                if target:
                    _ts = _ts_for(target)
                    _ts['focus_failed_count'] += 1
                    _ts['last_status'] = 'focus_failed'
                _diag_event('epoch_focus_failed',
                    epoch=_focus_epoch_id, target=target, hwnd=target_hwnd,
                    reason='verify_failed')
                _perf_log(
                    f'[EPOCH FOCUS FAILED] epoch={_focus_epoch_id} target={target!r} '
                    f'hwnd={target_hwnd} reason=verify_failed'
                )
            _diag_event('cycle_done', scope='global',
                direction='next' if direction > 0 else 'prev',
                source_idx=current_idx, target_idx=next_idx, target_title=target,
                focus_ok=ok, focus_verified=verified, strategy=_strategy,
                verify_ms=round(verify_ms, 1), total_ms=round(total_ms, 1),
                used_last_cycle=used_last, resolver_used=_diag_resolver)
        finally:
            _cycle_in_progress = False

    def _cycle_group(group_id: str, direction: int):
        """Group cycle — uses group['clients_order']. Macro-safe fast path."""
        global _cycle_in_progress, _last_cycle_time
        global _last_cycle_client_id, _last_cycle_client_id_time
        global _capture_suspended_until
        global _last_focus_done_time, _last_focus_done_hwnd, _last_focus_done_target, _last_focus_done_ok
        global _focus_epoch_id
        global _macro_missing_pending_epoch, _macro_missing_pending_target, _macro_missing_pending_time
        global _macro_stats_focus_failed, _macro_stats_focus_failed_targets
        global _last_verified_focus_perf
        import time as _time

        t0  = _time.perf_counter()
        now = _time.monotonic()

        _diag_event('cycle_group_enter', group_id=group_id,
            direction='next' if direction > 0 else 'prev',
            last_client=_last_cycle_client_id,
            last_group_idx=_last_group_index.get(group_id, -1),
            cooldown_remaining_ms=max(0.0, MIN_CYCLE_INTERVAL_MS - (now - _last_cycle_time) * 1000) if _last_cycle_time > 0 else 0.0,
            in_progress=_cycle_in_progress)

        # ── Anti-accumulation guards ──
        if _cycle_in_progress:
            _perf_log(
                f'[HOTKEY PERF] skipped group_id={group_id} direction={"next" if direction>0 else "prev"} '
                f'reason=in_progress since_ms={(now - _last_cycle_time)*1000:.1f}'
            )
            _diag_event('cycle_group_skipped', group_id=group_id, reason='in_progress',
                direction='next' if direction > 0 else 'prev',
                since_ms=round((now - _last_cycle_time) * 1000, 1))
            return
        delta_ms = (now - _last_cycle_time) * 1000
        if _last_cycle_time > 0 and delta_ms < MIN_CYCLE_INTERVAL_MS:
            _perf_log(
                f'[HOTKEY PERF] skipped group_id={group_id} direction={"next" if direction>0 else "prev"} '
                f'reason=cooldown delta_ms={delta_ms:.1f}'
            )
            _diag_event('cycle_group_skipped', group_id=group_id, reason='cooldown',
                direction='next' if direction > 0 else 'prev',
                delta_ms=round(delta_ms, 1), min_ms=MIN_CYCLE_INTERVAL_MS)
            return

        if _last_verified_focus_perf > 0:
            _guard_elapsed_ms = (t0 - _last_verified_focus_perf) * 1000.0
            if _guard_elapsed_ms < MACRO_COMPLETION_GUARD_MS:
                _perf_log(
                    f'[MACRO DELAY GUARD] scope=group group_id={group_id} '
                    f'elapsed_ms={_guard_elapsed_ms:.1f} min={MACRO_COMPLETION_GUARD_MS}ms'
                )
                _diag_event('macro_delay_guard', scope='group', group_id=group_id,
                    elapsed_ms=round(_guard_elapsed_ms, 1), min_ms=MACRO_COMPLETION_GUARD_MS)
                return

        _cycle_in_progress = True
        _last_cycle_time   = now
        _check_and_emit_missing_macro('next_cycle_without_macro')
        if _macro_seq_keys:
            _flush_macro_seq()

        try:
            from overlay.win32_capture import (
                get_foreground_hwnd, get_window_title,
                focus_eve_window_reliable, resolve_eve_window_handle, is_hwnd_valid,
            )
            from overlay.replication_overlay import ReplicationOverlay, _OVERLAY_REGISTRY

            hk_cfg = cfg.get('hotkeys', {})
            group  = hk_cfg.get('groups', {}).get(group_id)
            if not group or not group.get('enabled'):
                return

            titles = group.get('clients_order', [])
            if not titles:
                logger.warning(f'[HOTKEY] Group {group_id} has no clients_order')
                return

            hk_label = group.get('next' if direction > 0 else 'prev', f'dir{direction}')

            logger.debug(
                f"[CYCLE SYNC] hotkey_enter group={group_id} "
                f"dir={'next' if direction > 0 else 'prev'} "
                f"last_client={_last_cycle_client_id!r} "
                f"last_group_idx={_last_group_index.get(group_id, -1)} "
                f"last_client_age_ms={round((now - _last_cycle_client_id_time) * 1000, 1) if _last_cycle_client_id_time else None}"
            )

            # ── Resolve current index ─────────────────────────────────────
            # Priority: last_cycle_client_id → foreground → saved index
            t_res       = _time.perf_counter()
            current_idx = -1
            used_last   = False
            _diag_resolver = 'none'
            _diag_fg_hwnd = 0
            _diag_fg_title = ''
            _diag_fg_match_idx = -1

            if (_last_cycle_client_id and _last_cycle_client_id in titles
                    and (now - _last_cycle_client_id_time) < 5.0):
                current_idx = titles.index(_last_cycle_client_id)
                used_last   = True
                _diag_resolver = 'last_cycle_client_id'

            if current_idx == -1:
                fg_hwnd = get_foreground_hwnd()
                _diag_fg_hwnd = fg_hwnd
                if fg_hwnd:
                    fg_title = get_window_title(fg_hwnd)
                    _diag_fg_title = fg_title or ''
                    if fg_title:
                        if not _is_eve_client_title(fg_title):
                            _perf_log(f'[FOREGROUND_REJECTED_AS_NON_CLIENT] hwnd={fg_hwnd} title={fg_title!r}')
                            _diag_event('foreground_rejected_as_non_client', fg_hwnd=fg_hwnd, fg_title=fg_title)
                            _non_client_rejection_titles[fg_title] = _non_client_rejection_titles.get(fg_title, 0) + 1
                        else:
                            try:
                                current_idx = next(
                                    i for i, t in enumerate(titles)
                                    if t == fg_title or (t and t in fg_title)
                                )
                                _diag_fg_match_idx = current_idx
                                if current_idx != -1:
                                    _diag_resolver = 'foreground_title'
                            except StopIteration:
                                pass
                    if current_idx == -1:
                        for ov in list(_OVERLAY_REGISTRY):
                            if ov._hwnd and ov._hwnd == fg_hwnd and ov._title in titles:
                                current_idx = titles.index(ov._title)
                                _diag_fg_match_idx = current_idx
                                _diag_resolver = 'foreground_overlay_hwnd'
                                break

            if current_idx == -1:
                current_idx = _last_group_index.get(group_id, -1)
                if current_idx != -1 and _diag_resolver == 'none':
                    _diag_resolver = 'last_group_index'

            resolve_ms = (_time.perf_counter() - t_res) * 1000
            _diag_mismatch = (
                _diag_fg_match_idx != -1 and current_idx != -1
                and _diag_fg_match_idx != current_idx
                and _diag_resolver in ('last_cycle_client_id', 'last_group_index')
            )
            _diag_event('foreground_snapshot', group_id=group_id,
                fg_hwnd=_diag_fg_hwnd, fg_title=_diag_fg_title, fg_match_idx=_diag_fg_match_idx)
            _diag_event('current_index_resolved', group_id=group_id,
                current_idx=current_idx,
                current_title=titles[current_idx] if 0 <= current_idx < len(titles) else None,
                resolver_used=_diag_resolver,
                last_client=_last_cycle_client_id,
                last_client_age_ms=round((now - _last_cycle_client_id_time) * 1000, 1) if _last_cycle_client_id_time else None,
                fg_hwnd=_diag_fg_hwnd, fg_title=_diag_fg_title, fg_idx=_diag_fg_match_idx,
                mismatch=_diag_mismatch)

            # ── Find target using clients_order ───────────────────────────
            start    = current_idx if current_idx != -1 else (-1 if direction > 0 else 0)
            target   = target_hwnd = None
            next_idx = -1

            for attempt in range(1, len(titles) + 1):
                idx  = (start + direction * attempt) % len(titles)
                t    = titles[idx]
                hwnd = _hwnd_cache.get(t)
                if not hwnd or not is_hwnd_valid(hwnd):
                    hwnd = resolve_eve_window_handle(t)
                    if hwnd:
                        _hwnd_cache[t] = hwnd
                if hwnd and is_hwnd_valid(hwnd):
                    target, target_hwnd, next_idx = t, hwnd, idx
                    _diag_event('target_selected', group_id=group_id,
                        source_idx=current_idx,
                        source_title=titles[current_idx] if 0 <= current_idx < len(titles) else None,
                        target_idx=next_idx, target_title=t, target_hwnd=hwnd,
                        cache_hit=(_hwnd_cache.get(t) == hwnd))
                    logger.debug(
                        f"[CYCLE SYNC] hotkey_target group={group_id} "
                        f"resolver={_diag_resolver} "
                        f"resolved_idx={current_idx} "
                        f"resolved_title={titles[current_idx] if 0 <= current_idx < len(titles) else None!r} "
                        f"target_idx={next_idx} target={t!r}"
                    )
                    break

            if not target_hwnd:
                _perf_log(
                    f'[HOTKEY PERF] failed hotkey={hk_label} entry=_cycle_group '
                    f'group_id={group_id} reason=no_valid_window'
                )
                if _last_cycle_client_id and _last_cycle_client_id not in titles:
                    logger.debug(
                        f"[CYCLE SYNC] active_client_not_in_group group={group_id} "
                        f"client={_last_cycle_client_id!r}"
                    )
                return

            # ── Suspend capture for CAPTURE_SUSPEND_MS — reduces BitBlt competition ──
            _capture_suspended_until = now + CAPTURE_SUSPEND_MS / 1000.0

            # ── Mark hotkey burst — suspends visual updates for 120 ms ──
            try:
                from overlay.replicator_runtime_state import (
                    note_hotkey_burst_event, should_log_burst, get_hotkey_burst_count,
                )
                note_hotkey_burst_event("cycle_group")
                if should_log_burst():
                    _cnt = get_hotkey_burst_count()
                    _perf_log(f'[HOTKEY BURST] active suspend_ms=120 count={_cnt}')
                    _diag_event('burst_visual_suspend', suspend_ms=120, count=_cnt, reason='cycle_group')
            except Exception:
                pass

            # ── Focus target — reliable multi-strategy (verified internally) ──
            ok, focus_detail = focus_eve_window_reliable(target_hwnd)
            _perf_log(f'[FOCUS PERF] target={target!r} {focus_detail}')
            _diag_event('focus_result', group_id=group_id, target_title=target, target_hwnd=target_hwnd,
                focus_ok=ok, focus_detail=focus_detail, source_idx=current_idx, target_idx=next_idx,
                total_ms=round((_time.perf_counter() - t0) * 1000, 1))

            # ok=True means foreground already verified inside focus_eve_window_reliable
            verified = ok
            _dp = {}
            for _p in focus_detail.split():
                if '=' in _p:
                    _k, _, _v = _p.partition('=')
                    _dp[_k] = _v
            verify_ms = float(_dp.get('verify_ms', 0) or 0)
            actual_hwnd = int(_dp.get('actual', 0) or 0)
            _strategy = _dp.get('strategy', 'unknown')
            _diag_event('focus_verify_result', group_id=group_id,
                target_title=target, target_hwnd=target_hwnd,
                requested_ok=ok, verified=verified, actual_hwnd=actual_hwnd,
                verify_ms=round(verify_ms, 1), source_idx=current_idx, target_idx=next_idx)
            if not ok:
                _perf_log(
                    f'[HOTKEY PERF] focus_not_verified group_id={group_id} target={target!r} '
                    f'target_hwnd={target_hwnd} actual_hwnd={actual_hwnd} verify_ms={verify_ms:.1f}'
                )

            # Advance index only when foreground is confirmed — avoids desync on rapid macros.
            if ok:
                _last_group_index[group_id]    = next_idx
                _last_cycle_client_id          = target
                _last_cycle_client_id_time     = now
                _last_verified_focus_perf      = _time.perf_counter()
                ReplicationOverlay.notify_active_client_changed(target_hwnd)

            total_ms = (_time.perf_counter() - t0) * 1000
            _perf_log(
                f'[HOTKEY PERF] accepted hotkey={hk_label} direction={"next" if direction>0 else "prev"} '
                f'entry=_cycle_group group_id={group_id} group_name={group.get("name","")} '
                f'source_idx={current_idx} target_idx={next_idx} target={target!r} '
                f'resolve_ms={resolve_ms:.1f} total_ms={total_ms:.1f} '
                f'focus_ok={ok} focus_verified={verified} strategy={_strategy} '
                f'verify_ms={verify_ms:.1f} used_last_cycle={used_last}'
            )
            _focus_epoch_id += 1
            _last_focus_done_time   = _time.perf_counter()
            _last_focus_done_hwnd   = target_hwnd if ok else 0
            _last_focus_done_target = target or ''
            _last_focus_done_ok     = ok
            if ok:
                _macro_missing_pending_epoch = _focus_epoch_id
                _macro_missing_pending_target = target or ''
                _macro_missing_pending_time = _last_focus_done_time
                if target:
                    _ts_for(target)['focus_ok_count'] += 1
            else:
                _focus_failed_epochs.add(_focus_epoch_id)
                _macro_stats_focus_failed += 1
                if target and target not in _macro_stats_focus_failed_targets:
                    _macro_stats_focus_failed_targets.append(target)
                if target:
                    _ts = _ts_for(target)
                    _ts['focus_failed_count'] += 1
                    _ts['last_status'] = 'focus_failed'
                _diag_event('epoch_focus_failed',
                    epoch=_focus_epoch_id, target=target, hwnd=target_hwnd,
                    reason='verify_failed')
                _perf_log(
                    f'[EPOCH FOCUS FAILED] epoch={_focus_epoch_id} target={target!r} '
                    f'hwnd={target_hwnd} reason=verify_failed'
                )
            _diag_event('cycle_group_done', group_id=group_id,
                direction='next' if direction > 0 else 'prev',
                source_idx=current_idx, target_idx=next_idx, target_title=target,
                focus_ok=ok, focus_verified=verified, strategy=_strategy,
                verify_ms=round(verify_ms, 1), total_ms=round(total_ms, 1),
                used_last_cycle=used_last, resolver_used=_diag_resolver)
        finally:
            _cycle_in_progress = False

    # ── Registration logic ────────────────────────────────────────────────────

    # Collect group-reserved combos to prevent global conflicts
    group_combos: Dict[tuple, str] = {}
    groups = hk_cfg.get('groups', {})

    for g_id, g_data in groups.items():
        if g_data.get('enabled'):
            n_m, n_v = parse_hotkey(g_data.get('next', ''))
            p_m, p_v = parse_hotkey(g_data.get('prev', ''))
            if n_v:
                group_combos[(n_m, n_v)] = g_id
                logger.debug(f'[HOTKEY REG] group={g_id} next={g_data.get("next")}')
            if p_v:
                group_combos[(p_m, p_v)] = g_id
                logger.debug(f'[HOTKEY REG] group={g_id} prev={g_data.get("prev")}')

    from functools import partial

    # Global cycle — skip if the combo is reserved by a group
    n_global_skipped = 0
    for key, direction in [('cycle_next', +1), ('cycle_prev', -1)]:
        entry = hk_cfg.get(key, {})
        combo = entry.get('combo', '') if isinstance(entry, dict) else ''
        mods, vk = parse_hotkey(combo)
        if vk:
            if (mods, vk) in group_combos:
                res_gid = group_combos[(mods, vk)]
                logger.info(f'[HOTKEY] Global {key} ({combo}) reserved by group {res_gid} → skipping')
                _perf_log(f'[HOTKEY REGISTER SKIP] hotkey={combo} reason=reserved_by_group group={res_gid} global={key}')
                n_global_skipped += 1
            else:
                logger.info(f'[HOTKEY] Registering global {key} → {combo}')
                _perf_log(f'[HOTKEY REGISTER] scope=global hotkey={combo} callback=_cycle direction={"next" if direction>0 else "prev"}')
                registrations.append((mods, vk, partial(_cycle, direction)))

    # Group hotkeys (registered after globals; priority guaranteed by dedup above)
    for g_id, g_data in groups.items():
        if not g_data.get('enabled'):
            continue
        n_mods, n_vk = parse_hotkey(g_data.get('next', ''))
        if n_vk:
            logger.info(f'[HOTKEY] Registering group {g_id} next → {g_data.get("next")}')
            _perf_log(
                f'[HOTKEY REGISTER] scope=group group_id={g_id} group_name={g_data.get("name","")} '
                f'hotkey={g_data.get("next")} direction=next callback=_cycle_group'
            )
            registrations.append((n_mods, n_vk, partial(_cycle_group, g_id, +1)))
        p_mods, p_vk = parse_hotkey(g_data.get('prev', ''))
        if p_vk:
            logger.info(f'[HOTKEY] Registering group {g_id} prev → {g_data.get("prev")}')
            _perf_log(
                f'[HOTKEY REGISTER] scope=group group_id={g_id} group_name={g_data.get("name","")} '
                f'hotkey={g_data.get("prev")} direction=prev callback=_cycle_group'
            )
            registrations.append((p_mods, p_vk, partial(_cycle_group, g_id, -1)))

    _perf_log(
        f'[HOTKEY REGISTER SUMMARY] total={len(registrations)} '
        f'group_reserved={len(group_combos)} global_skipped={n_global_skipped} '
        f'groups_enabled={sum(1 for g in groups.values() if g.get("enabled"))}'
    )

    if not registrations:
        logger.debug('No hotkey combos configured')
        return

    _running = True
    _thread  = threading.Thread(
        target=_listener_thread, args=(registrations,), daemon=True, name='HotkeyListener'
    )
    _thread.start()


def unregister_hotkeys():
    global _running, _thread
    _running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=0.3)
    _thread = None


def get_hotkey_defaults() -> dict:
    return {
        'per_client': {},
        'cycle_next': {'combo': 'F14'},
        'cycle_prev': {'combo': 'CTRL+F14'},
        'groups': {},
    }
