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
        if _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == WM_HOTKEY:
                cb = registered.get(msg.wParam)
                if cb:
                    try:
                        cb()
                    except Exception as e:
                        logger.error(f"Hotkey cb error: {e}")
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        else:
            time.sleep(0.02)

    for hk_id in registered:
        _user32.UnregisterHotKey(None, hk_id)
    logger.debug("Hotkey listener stopped, all hotkeys unregistered")


def register_hotkeys(cfg: dict, cycle_titles_getter: Callable[[], List[str]] = None):
    """Register all enabled hotkeys from cfg.

    cycle_titles_getter() should return the ordered list of active overlay titles
    for cycle_next / cycle_prev navigation.
    EULA-safe: only calls focus_eve_window(), no game input.
    """
    global _thread, _running

    unregister_hotkeys()

    hk_cfg = cfg.get('hotkeys', {})
    if not hk_cfg.get('global_enabled', False):
        return

    registrations = []

    # Per-client hotkeys
    for title, entry in hk_cfg.get('per_client', {}).items():
        combo = entry.get('combo', '') if isinstance(entry, dict) else str(entry)
        mods, vk = parse_hotkey(combo)
        if not vk:
            continue
        def _focus_cb(t=title):
            from overlay.win32_capture import focus_eve_window, resolve_eve_window_handle
            hwnd = resolve_eve_window_handle(t)
            if hwnd:
                ok = focus_eve_window(hwnd)
                logger.debug(f"[HOTKEY] focus {t!r} hwnd={hwnd} ok={ok}")
        registrations.append((mods, vk, _focus_cb))

    # Cycle hotkeys
    def _cycle(direction: int):
        titles = cycle_titles_getter() if cycle_titles_getter else []
        if not titles:
            return
        from overlay.win32_capture import (
            get_foreground_hwnd, get_window_title,
            focus_eve_window, resolve_eve_window_handle,
        )
        fg_hwnd = get_foreground_hwnd()
        fg_title = get_window_title(fg_hwnd)
        try:
            idx = next(i for i, t in enumerate(titles)
                       if t in fg_title or fg_title in t)
        except StopIteration:
            idx = -1
        next_idx = (idx + direction) % len(titles)
        target = titles[next_idx]
        hwnd = resolve_eve_window_handle(target)
        if hwnd:
            focus_eve_window(hwnd)
            logger.debug(f"[HOTKEY] cycle -> {target!r}")

    for key, direction in [('cycle_next', +1), ('cycle_prev', -1)]:
        entry = hk_cfg.get(key, {})
        combo = entry.get('combo', '') if isinstance(entry, dict) else ''
        mods, vk = parse_hotkey(combo)
        if vk:
            registrations.append((mods, vk, lambda d=direction: _cycle(d)))

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
        'global_enabled': False,
        'per_client': {},
        'cycle_next': {'combo': ''},
        'cycle_prev': {'combo': ''},
    }
