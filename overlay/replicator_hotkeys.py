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

_user32  = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# Thread state
_thread: Optional[threading.Thread] = None
_running = False
_pending_registrations: list = []  # list of (mods, vk, callback)
_id_seq = 0
_lock = threading.Lock()

# Cache for instant switching
_hwnd_cache: Dict[str, int] = {}
_cached_titles: List[str] = []


def parse_hotkey(combo: str) -> tuple:
    """Parse 'CTRL+F13' -> (mods_int, vk_int).  Returns (0, 0) if invalid/empty."""
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
            logger.debug(f"Unknown hotkey token: {part!r}")
    return (mods, vk)


def _next_id() -> int:
    global _id_seq
    _id_seq += 1
    return _id_seq


def _listener_thread(registrations: list):
    """Background thread: register hotkeys, pump messages, unregister on exit."""
    registered: Dict[int, Callable] = {}

    for mods, vk, cb in registrations:
        if not vk:
            continue
        hk_id = _next_id()
        if _user32.RegisterHotKey(None, hk_id, mods, vk):
            registered[hk_id] = cb
            logger.info(f"RegisterHotKey id={hk_id} mods={mods:#x} vk={vk:#x}")
        else:
            err = _kernel32.GetLastError()
            logger.warning(f"RegisterHotKey failed mods={mods:#x} vk={vk:#x} err={err}")

    if not registered:
        logger.debug("No hotkeys registered -- listener exits")
        return

    msg = wt.MSG()
    import time
    while _running:
        # PeekMessage with a small sleep to remain responsive without high CPU
        if _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == WM_HOTKEY:
                hk_id = msg.wParam
                cb = registered.get(hk_id)
                if cb:
                    try:
                        t_start = time.perf_counter()
                        cb()
                        ms = (time.perf_counter() - t_start) * 1000
                        logger.debug(f"[REPLICATOR HOTKEY] Handled id={hk_id} in {ms:.1f}ms")
                    except Exception as e:
                        logger.error(f"Hotkey cb error: {e}")
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        else:
            time.sleep(0.005) # 5ms polling for near-instant feel

    for hk_id in registered:
        _user32.UnregisterHotKey(None, hk_id)
    logger.debug("Hotkey listener stopped, all hotkeys unregistered")


def update_hotkey_cache(titles: List[str]):
    """Update the internal cache of window handles for instant switching."""
    global _hwnd_cache, _cached_titles
    from overlay.win32_capture import resolve_eve_window_handle
    new_cache = {}
    for t in titles:
        # Try to keep existing hwnd if still valid
        existing = _hwnd_cache.get(t)
        from overlay.win32_capture import is_hwnd_valid
        if existing and is_hwnd_valid(existing):
            new_cache[t] = existing
        else:
            hwnd = resolve_eve_window_handle(t)
            if hwnd:
                new_cache[t] = hwnd
    
    with _lock:
        _hwnd_cache = new_cache
        _cached_titles = list(titles)
    logger.debug(f"[REPLICATOR HOTKEY] Cache updated: {len(_hwnd_cache)} clients")


def register_hotkeys(cfg: dict, cycle_titles_getter: Callable[[], List[str]] = None):
    """Register all enabled hotkeys from cfg.

    cycle_titles_getter() should return the ordered list of active overlay titles
    for cycle_next / cycle_prev navigation.
    EULA-safe: only calls focus_eve_window(), no game input.
    """
    global _thread, _running

    unregister_hotkeys()

    hk_cfg = cfg.get('hotkeys', {})
    registrations = []

    # Per-client hotkeys
    for title, entry in hk_cfg.get('per_client', {}).items():
        combo = entry.get('combo', '') if isinstance(entry, dict) else str(entry)
        mods, vk = parse_hotkey(combo)
        if not vk:
            continue
        
        def _focus_cb(t=title):
            from overlay.win32_capture import focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid
            import time
            t0 = time.perf_counter()
            hwnd = _hwnd_cache.get(t)
            cache_hit = True
            if not hwnd or not is_hwnd_valid(hwnd):
                cache_hit = False
                hwnd = resolve_eve_window_handle(t)
                if hwnd:
                    _hwnd_cache[t] = hwnd
            
            if hwnd:
                ok = focus_eve_window_fast(hwnd)
                if ok:
                    from overlay.replication_overlay import ReplicationOverlay
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                dt = (time.perf_counter() - t0) * 1000
                logger.info(f"[REPLICATOR HOTKEY] mode=per_client target={t!r} hwnd={hwnd} cache_hit={cache_hit} ms={dt:.1f} success={ok}")
            else:
                logger.warning(f"[REPLICATOR HOTKEY] Could not resolve window for {t!r}")

        registrations.append((mods, vk, _focus_cb))

    # Cycle hotkeys
    def _cycle(direction: int):
        from overlay.win32_capture import (
            get_foreground_hwnd, get_window_title,
            focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid
        )
        import time
        t0 = time.perf_counter()
        
        titles = _cached_titles
        if not titles:
            titles = cycle_titles_getter() if cycle_titles_getter else []
            if not titles: return

        fg_hwnd = get_foreground_hwnd()
        fg_title = get_window_title(fg_hwnd)
        
        try:
            idx = next(i for i, t in enumerate(titles) if t in fg_title or fg_title in t)
        except StopIteration:
            idx = -1 if direction > 0 else 0 # Default starting point
            
        for attempt in range(1, len(titles) + 1):
            next_idx = (idx + direction * attempt) % len(titles)
            target = titles[next_idx]
            
            hwnd = _hwnd_cache.get(target)
            cache_hit = True
            if not hwnd or not is_hwnd_valid(hwnd):
                cache_hit = False
                hwnd = resolve_eve_window_handle(target)
                if hwnd: _hwnd_cache[target] = hwnd
                
            if hwnd and is_hwnd_valid(hwnd):
                ok = focus_eve_window_fast(hwnd)
                if ok:
                    from overlay.replication_overlay import ReplicationOverlay
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                dt = (time.perf_counter() - t0) * 1000
                logger.info(f"[REPLICATOR HOTKEY] mode=cycle direction={direction} target={target!r} cache_hit={cache_hit} ms={dt:.1f} ok={ok}")
                return

    # Group hotkeys
    def _cycle_group(group_id: str, direction: int):
        from overlay.win32_capture import (
            get_foreground_hwnd, get_window_title,
            focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid
        )
        import time
        t0 = time.perf_counter()
        
        hk_cfg = cfg.get('hotkeys', {})
        group = hk_cfg.get('groups', {}).get(group_id)
        if not group or not group.get('enabled'):
            return
            
        titles = group.get('clients_order', [])
        if not titles:
            return

        fg_hwnd = get_foreground_hwnd()
        fg_title = get_window_title(fg_hwnd)
        
        try:
            idx = next(i for i, t in enumerate(titles) if t in fg_title or fg_title in t)
        except StopIteration:
            idx = -1 if direction > 0 else 0
            
        for attempt in range(1, len(titles) + 1):
            next_idx = (idx + direction * attempt) % len(titles)
            target = titles[next_idx]
            
            hwnd = _hwnd_cache.get(target)
            cache_hit = True
            if not hwnd or not is_hwnd_valid(hwnd):
                cache_hit = False
                hwnd = resolve_eve_window_handle(target)
                if hwnd: _hwnd_cache[target] = hwnd
            
            if hwnd and is_hwnd_valid(hwnd):
                ok = focus_eve_window_fast(hwnd)
                if ok:
                    from overlay.replication_overlay import ReplicationOverlay
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                dt = (time.perf_counter() - t0) * 1000
                logger.info(f"[REPLICATOR GROUP HOTKEY] group={group.get('name')} id={group_id} dir={direction} target={target!r} cache_hit={cache_hit} ms={dt:.1f} ok={ok}")
                return
        
        logger.warning(f"[REPLICATOR GROUP HOTKEY] No valid windows found for group {group_id}")

    for key, direction in [('cycle_next', +1), ('cycle_prev', -1)]:
        entry = hk_cfg.get(key, {})
        combo = entry.get('combo', '') if isinstance(entry, dict) else ''
        mods, vk = parse_hotkey(combo)
        if vk:
            registrations.append((mods, vk, lambda d=direction: _cycle(d)))

    # Register groups
    groups = hk_cfg.get('groups', {})
    for g_id, g_data in groups.items():
        if not g_data.get('enabled'):
            continue
        # Next
        n_mods, n_vk = parse_hotkey(g_data.get('next', ''))
        if n_vk:
            registrations.append((n_mods, n_vk, lambda gid=g_id: _cycle_group(gid, +1)))
        # Prev
        p_mods, p_vk = parse_hotkey(g_data.get('prev', ''))
        if p_vk:
            registrations.append((p_mods, p_vk, lambda gid=g_id: _cycle_group(gid, -1)))

    if not registrations:
        logger.debug("No hotkey combos configured")
        return

    _running = True
    _thread = threading.Thread(
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
