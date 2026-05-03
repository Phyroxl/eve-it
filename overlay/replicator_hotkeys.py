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

# Minimum ms between accepted cycles — prevents accumulation when macro sends
# multiple F14 presses faster than we can process them.
MIN_CYCLE_INTERVAL_MS: int = 60

_cycle_in_progress: bool = False          # Safety guard (same-thread re-entry)
_last_cycle_time: float = 0.0             # monotonic() of last *accepted* cycle
_last_cycle_client_id: Optional[str] = None       # Title of last focused client
_last_cycle_client_id_time: float = 0.0           # monotonic() of above

# Written by _cycle/_cycle_group; read by CaptureThread.run() in replication_overlay.
# CaptureThread skips one frame while < now, reducing competition with Win32 focus.
_capture_suspended_until: float = 0.0


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
            global _last_cycle_client_id, _last_cycle_client_id_time
            from overlay.win32_capture import focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid
            import time as _time
            t0 = _time.perf_counter()
            hwnd = _hwnd_cache.get(t)
            if not hwnd or not is_hwnd_valid(hwnd):
                hwnd = resolve_eve_window_handle(t)
                if hwnd:
                    _hwnd_cache[t] = hwnd
            if hwnd:
                ok = focus_eve_window_fast(hwnd)
                if ok:
                    from overlay.replication_overlay import ReplicationOverlay
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                    _last_cycle_client_id = t
                    _last_cycle_client_id_time = _time.monotonic()
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

        # ── Anti-accumulation guards ──
        if _cycle_in_progress:
            _perf_log(
                f'[HOTKEY PERF] skipped hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'reason=in_progress since_ms={(now - _last_cycle_time)*1000:.1f}'
            )
            return
        delta_ms = (now - _last_cycle_time) * 1000
        if _last_cycle_time > 0 and delta_ms < MIN_CYCLE_INTERVAL_MS:
            _perf_log(
                f'[HOTKEY PERF] skipped hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'reason=cooldown delta_ms={delta_ms:.1f}'
            )
            return

        _cycle_in_progress = True
        _last_cycle_time   = now

        try:
            from overlay.win32_capture import (
                get_foreground_hwnd, get_window_title,
                focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid,
            )
            from overlay.replication_overlay import ReplicationOverlay, _OVERLAY_REGISTRY

            titles = _cached_titles or (cycle_titles_getter() if cycle_titles_getter else [])
            if not titles:
                return

            # ── Resolve current index ─────────────────────────────────────
            # Priority: last_cycle_client_id (deterministic, avoids stale fg)
            #           → foreground hwnd / title
            #           → saved index
            t_res = _time.perf_counter()
            current_idx = -1
            used_last   = False

            if (_last_cycle_client_id and _last_cycle_client_id in titles
                    and (now - _last_cycle_client_id_time) < 5.0):
                current_idx = titles.index(_last_cycle_client_id)
                used_last   = True

            if current_idx == -1:
                fg_hwnd = get_foreground_hwnd()
                if fg_hwnd:
                    fg_title = get_window_title(fg_hwnd)
                    if fg_title:
                        try:
                            current_idx = next(
                                i for i, t in enumerate(titles)
                                if t == fg_title or (t and t in fg_title)
                            )
                        except StopIteration:
                            pass
                    if current_idx == -1:
                        for ov in list(_OVERLAY_REGISTRY):
                            if ov._hwnd and ov._hwnd == fg_hwnd and ov._title in titles:
                                current_idx = titles.index(ov._title)
                                break

            if current_idx == -1:
                current_idx = _last_group_index.get('__global__', -1)

            resolve_ms = (_time.perf_counter() - t_res) * 1000

            # ── Find target ───────────────────────────────────────────────
            start      = current_idx if current_idx != -1 else (-1 if direction > 0 else 0)
            target     = target_hwnd = None
            next_idx   = -1

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
                    break

            if not target_hwnd:
                _perf_log(f'[HOTKEY PERF] failed hotkey=cycle direction={"next" if direction>0 else "prev"} entry=_cycle reason=no_valid_window')
                return

            # ── Suspend capture for ~80 ms (skip one frame, reduce competition) ──
            _capture_suspended_until = now + 0.08

            # ── Focus target ──────────────────────────────────────────────
            t_foc    = _time.perf_counter()
            ok       = focus_eve_window_fast(target_hwnd)
            focus_ms = (_time.perf_counter() - t_foc) * 1000

            if ok:
                _last_group_index['__global__'] = next_idx
                _last_cycle_client_id           = target
                _last_cycle_client_id_time      = now
                ReplicationOverlay.notify_active_client_changed(target_hwnd)

            total_ms = (_time.perf_counter() - t0) * 1000
            _perf_log(
                f'[HOTKEY PERF] accepted hotkey=cycle direction={"next" if direction>0 else "prev"} '
                f'entry=_cycle source_idx={current_idx} target_idx={next_idx} target={target!r} '
                f'resolve_ms={resolve_ms:.1f} focus_ms={focus_ms:.1f} total_ms={total_ms:.1f} '
                f'focus_ok={ok} used_last_cycle={used_last}'
            )
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

        # ── Anti-accumulation guards ──
        if _cycle_in_progress:
            _perf_log(
                f'[HOTKEY PERF] skipped group_id={group_id} direction={"next" if direction>0 else "prev"} '
                f'reason=in_progress since_ms={(now - _last_cycle_time)*1000:.1f}'
            )
            return
        delta_ms = (now - _last_cycle_time) * 1000
        if _last_cycle_time > 0 and delta_ms < MIN_CYCLE_INTERVAL_MS:
            _perf_log(
                f'[HOTKEY PERF] skipped group_id={group_id} direction={"next" if direction>0 else "prev"} '
                f'reason=cooldown delta_ms={delta_ms:.1f}'
            )
            return

        _cycle_in_progress = True
        _last_cycle_time   = now

        try:
            from overlay.win32_capture import (
                get_foreground_hwnd, get_window_title,
                focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid,
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

            if (_last_cycle_client_id and _last_cycle_client_id in titles
                    and (now - _last_cycle_client_id_time) < 5.0):
                current_idx = titles.index(_last_cycle_client_id)
                used_last   = True

            if current_idx == -1:
                fg_hwnd = get_foreground_hwnd()
                if fg_hwnd:
                    fg_title = get_window_title(fg_hwnd)
                    if fg_title:
                        try:
                            current_idx = next(
                                i for i, t in enumerate(titles)
                                if t == fg_title or (t and t in fg_title)
                            )
                        except StopIteration:
                            pass
                    if current_idx == -1:
                        for ov in list(_OVERLAY_REGISTRY):
                            if ov._hwnd and ov._hwnd == fg_hwnd and ov._title in titles:
                                current_idx = titles.index(ov._title)
                                break

            if current_idx == -1:
                current_idx = _last_group_index.get(group_id, -1)

            resolve_ms = (_time.perf_counter() - t_res) * 1000

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
                    break

            if not target_hwnd:
                _perf_log(
                    f'[HOTKEY PERF] failed hotkey={hk_label} entry=_cycle_group '
                    f'group_id={group_id} reason=no_valid_window'
                )
                return

            # ── Suspend capture for ~80 ms ────────────────────────────────
            _capture_suspended_until = now + 0.08

            # ── Focus target ──────────────────────────────────────────────
            t_foc    = _time.perf_counter()
            ok       = focus_eve_window_fast(target_hwnd)
            focus_ms = (_time.perf_counter() - t_foc) * 1000

            if ok:
                _last_group_index[group_id]    = next_idx
                _last_cycle_client_id          = target
                _last_cycle_client_id_time     = now
                ReplicationOverlay.notify_active_client_changed(target_hwnd)

            total_ms = (_time.perf_counter() - t0) * 1000
            _perf_log(
                f'[HOTKEY PERF] accepted hotkey={hk_label} direction={"next" if direction>0 else "prev"} '
                f'entry=_cycle_group group_id={group_id} group_name={group.get("name","")} '
                f'source_idx={current_idx} target_idx={next_idx} target={target!r} '
                f'resolve_ms={resolve_ms:.1f} focus_ms={focus_ms:.1f} total_ms={total_ms:.1f} '
                f'focus_ok={ok} used_last_cycle={used_last}'
            )
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

    # Global cycle — skip if the combo is reserved by a group
    for key, direction in [('cycle_next', +1), ('cycle_prev', -1)]:
        entry = hk_cfg.get(key, {})
        combo = entry.get('combo', '') if isinstance(entry, dict) else ''
        mods, vk = parse_hotkey(combo)
        if vk:
            if (mods, vk) in group_combos:
                res_gid = group_combos[(mods, vk)]
                logger.info(f'[HOTKEY] Global {key} ({combo}) reserved by group {res_gid} → skipping')
                _perf_log(f'[HOTKEY REGISTER SKIP] hotkey={combo} reason=reserved_by_group group={res_gid} global={key}')
            else:
                logger.info(f'[HOTKEY] Registering global {key} → {combo}')
                _perf_log(f'[HOTKEY REGISTER] scope=global hotkey={combo} callback=_cycle direction={"next" if direction>0 else "prev"}')
                registrations.append((mods, vk, lambda d=direction: _cycle(d)))

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
            registrations.append((n_mods, n_vk, lambda gid=g_id: _cycle_group(gid, +1)))
        p_mods, p_vk = parse_hotkey(g_data.get('prev', ''))
        if p_vk:
            logger.info(f'[HOTKEY] Registering group {g_id} prev → {g_data.get("prev")}')
            _perf_log(
                f'[HOTKEY REGISTER] scope=group group_id={g_id} group_name={g_data.get("name","")} '
                f'hotkey={g_data.get("prev")} direction=prev callback=_cycle_group'
            )
            registrations.append((p_mods, p_vk, lambda gid=g_id: _cycle_group(gid, -1)))

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
