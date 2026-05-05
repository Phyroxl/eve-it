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


# ── Public diagnostics API ────────────────────────────────────────────────────

def set_hotkey_diagnostics_enabled(enabled: bool, callback=None):
    """Enable/disable live diagnostics. callback(event_dict) is called from hotkey thread."""
    global _hotkey_diagnostics_enabled, _hotkey_diagnostics_callback
    _hotkey_diagnostics_enabled = enabled
    _hotkey_diagnostics_callback = callback if enabled else None


def clear_hotkey_diagnostics():
    """Clear the in-memory event ring buffer."""
    _hotkey_diagnostics_events.clear()


def get_hotkey_diagnostics_events():
    """Return a snapshot of current diagnostic events."""
    return list(_hotkey_diagnostics_events)


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


# ── Main registration ─────────────────────────────────────────────────────────

def register_hotkeys(cfg: dict, cycle_titles_getter: Callable[[], List[str]] = None):
    """Register all enabled hotkeys from cfg.
    EULA-safe: only calls focus_eve_window(), no game input injection.
    """
    global _thread, _running

    unregister_hotkeys()

    hk_cfg = cfg.get('hotkeys', {})
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

        _cycle_in_progress = True
        _last_cycle_time   = now

        try:
            from overlay.win32_capture import (
                get_foreground_hwnd, get_window_title,
                focus_eve_window_perf, resolve_eve_window_handle, is_hwnd_valid,
            )
            from overlay.replication_overlay import ReplicationOverlay, _OVERLAY_REGISTRY

            titles = _cached_titles or (cycle_titles_getter() if cycle_titles_getter else [])
            if not titles:
                return

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

            # ── Focus target (non-blocking async Z-order + SetForegroundWindow) ──
            ok, focus_detail = focus_eve_window_perf(target_hwnd)
            _perf_log(f'[FOCUS PERF] target={target!r} {focus_detail}')
            _diag_event('focus_result', scope='global', target_title=target, target_hwnd=target_hwnd,
                focus_ok=ok, source_idx=current_idx, target_idx=next_idx,
                total_ms=round((_time.perf_counter() - t0) * 1000, 1))

            # ── Verify foreground ──
            from overlay.win32_capture import verify_foreground_window
            verified, actual_hwnd, verify_ms = verify_foreground_window(
                target_hwnd, timeout_ms=40, poll_ms=2
            )
            _diag_event('focus_verify_result', scope='global',
                target_title=target, target_hwnd=target_hwnd,
                requested_ok=ok, verified=verified, actual_hwnd=actual_hwnd,
                verify_ms=round(verify_ms, 1), source_idx=current_idx, target_idx=next_idx)

            if ok and verified:
                _last_group_index['__global__'] = next_idx
                _last_cycle_client_id           = target
                _last_cycle_client_id_time      = now
                ReplicationOverlay.notify_active_client_changed(target_hwnd)
            elif ok:
                ReplicationOverlay.notify_active_client_changed(target_hwnd)

            total_ms = (_time.perf_counter() - t0) * 1000
            _perf_log(
                f'[HOTKEY PERF] accepted hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'entry=_cycle source_idx={current_idx} target_idx={next_idx} target={target!r} '
                f'resolve_ms={resolve_ms:.1f} total_ms={total_ms:.1f} '
                f'focus_ok={ok} focus_verified={verified} verify_ms={verify_ms:.1f} used_last_cycle={used_last}'
            )
            _diag_event('cycle_done', scope='global',
                direction='next' if direction > 0 else 'prev',
                source_idx=current_idx, target_idx=next_idx, target_title=target,
                focus_ok=ok, focus_verified=verified, verify_ms=round(verify_ms, 1),
                total_ms=round(total_ms, 1),
                used_last_cycle=used_last, resolver_used=_diag_resolver)
        finally:
            _cycle_in_progress = False

    def _cycle_group(group_id: str, direction: int):
        """Group cycle — uses group['clients_order']. Macro-safe fast path."""
        global _cycle_in_progress, _last_cycle_time
        global _last_cycle_client_id, _last_cycle_client_id_time
        global _capture_suspended_until
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

        _cycle_in_progress = True
        _last_cycle_time   = now

        try:
            from overlay.win32_capture import (
                get_foreground_hwnd, get_window_title,
                focus_eve_window_perf, resolve_eve_window_handle, is_hwnd_valid,
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
                    break

            if not target_hwnd:
                _perf_log(
                    f'[HOTKEY PERF] failed hotkey={hk_label} entry=_cycle_group '
                    f'group_id={group_id} reason=no_valid_window'
                )
                return

            # ── Suspend capture for CAPTURE_SUSPEND_MS — reduces BitBlt competition ──
            _capture_suspended_until = now + CAPTURE_SUSPEND_MS / 1000.0

            # ── Focus target (non-blocking async Z-order + SetForegroundWindow) ──
            ok, focus_detail = focus_eve_window_perf(target_hwnd)
            _perf_log(f'[FOCUS PERF] target={target!r} {focus_detail}')
            _diag_event('focus_result', group_id=group_id, target_title=target, target_hwnd=target_hwnd,
                focus_ok=ok, source_idx=current_idx, target_idx=next_idx,
                total_ms=round((_time.perf_counter() - t0) * 1000, 1))

            # ── Verify foreground: poll until Windows confirms the focus change ──
            from overlay.win32_capture import verify_foreground_window
            verified, actual_hwnd, verify_ms = verify_foreground_window(
                target_hwnd, timeout_ms=40, poll_ms=2
            )
            _diag_event('focus_verify_result', group_id=group_id,
                target_title=target, target_hwnd=target_hwnd,
                requested_ok=ok, verified=verified, actual_hwnd=actual_hwnd,
                verify_ms=round(verify_ms, 1), source_idx=current_idx, target_idx=next_idx)
            if ok and not verified:
                _perf_log(
                    f'[HOTKEY PERF] focus_not_verified group_id={group_id} target={target!r} '
                    f'target_hwnd={target_hwnd} actual_hwnd={actual_hwnd} verify_ms={verify_ms:.1f}'
                )

            # Advance index only when foreground is confirmed — avoids desync on rapid macros.
            if ok and verified:
                _last_group_index[group_id]    = next_idx
                _last_cycle_client_id          = target
                _last_cycle_client_id_time     = now
                ReplicationOverlay.notify_active_client_changed(target_hwnd)
            elif ok:
                ReplicationOverlay.notify_active_client_changed(target_hwnd)

            total_ms = (_time.perf_counter() - t0) * 1000
            _perf_log(
                f'[HOTKEY PERF] accepted hotkey={hk_label} direction={"next" if direction>0 else "prev"} '
                f'entry=_cycle_group group_id={group_id} group_name={group.get("name","")} '
                f'source_idx={current_idx} target_idx={next_idx} target={target!r} '
                f'resolve_ms={resolve_ms:.1f} total_ms={total_ms:.1f} '
                f'focus_ok={ok} focus_verified={verified} verify_ms={verify_ms:.1f} used_last_cycle={used_last}'
            )
            _diag_event('cycle_group_done', group_id=group_id,
                direction='next' if direction > 0 else 'prev',
                source_idx=current_idx, target_idx=next_idx, target_title=target,
                focus_ok=ok, focus_verified=verified, verify_ms=round(verify_ms, 1),
                total_ms=round(total_ms, 1),
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
