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

# Persistencia del último índice activado por grupo para ciclos deterministas
_last_group_index: Dict[str, int] = {}

def _log_to_file(msg: str):
    try:
        from utils.paths import ROOT_DIR
        import datetime
        log_dir = ROOT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hotkey_order_debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


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
        from overlay.replication_overlay import ReplicationOverlay, _OVERLAY_REGISTRY
        import time
        t0 = time.perf_counter()
        
        _log_to_file(f"[HOTKEY ENTRY DEBUG] function=_cycle direction={'next' if direction>0 else 'prev'}")
        
        titles = _cached_titles
        if not titles:
            titles = cycle_titles_getter() if cycle_titles_getter else []
            if not titles: 
                _log_to_file("[CYCLE DEBUG] No titles available for global cycle.")
                return

        fg_hwnd = get_foreground_hwnd()
        fg_title = get_window_title(fg_hwnd)
        
        # 1. Detectar índice actual
        current_idx = -1
        try:
            current_idx = next(i for i, t in enumerate(titles) if t == fg_title or (t and t in fg_title))
        except StopIteration:
            for ov in list(_OVERLAY_REGISTRY):
                if ov._hwnd and ov._hwnd == fg_hwnd:
                    if ov._title in titles:
                        current_idx = titles.index(ov._title)
                        break
        
        if current_idx == -1:
            current_idx = _last_group_index.get('__global__', -1)

        # Logging detallado
        l1 = "--- START GLOBAL CYCLE ---"
        l2 = f"hotkey_pressed={'F14' if direction>0 else 'Ctrl+F14'}"
        l3 = f"titles_in_cycle={titles}"
        _log_to_file(f"[HOTKEY ORDER DEBUG] {l1}")
        _log_to_file(f"[HOTKEY ORDER DEBUG] {l2}")
        _log_to_file(f"[HOTKEY ORDER DEBUG] {l3}")
        _log_to_file(f"[HOTKEY ORDER DEBUG] foreground_hwnd={fg_hwnd} title='{fg_title}' current_idx={current_idx}")

        start_search_idx = current_idx if current_idx != -1 else (-1 if direction > 0 else 0)
        
        for attempt in range(1, len(titles) + 1):
            next_idx = (start_search_idx + direction * attempt) % len(titles)
            target = titles[next_idx]
            
            hwnd = _hwnd_cache.get(target)
            if not hwnd or not is_hwnd_valid(hwnd):
                hwnd = resolve_eve_window_handle(target)
                if hwnd: _hwnd_cache[target] = hwnd
            
            if hwnd and is_hwnd_valid(hwnd):
                _log_to_file(f"[HOTKEY ORDER DEBUG] target_index={next_idx} target_title='{target}'")
                ok = focus_eve_window_fast(hwnd)
                if ok:
                    _last_group_index['__global__'] = next_idx
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                    
                dt = (time.perf_counter() - t0) * 1000
                _log_to_file(f"[HOTKEY ORDER DEBUG] --- DONE ok={ok} ms={dt:.1f} ---")
                
                logger.info(f"[REPLICATOR GLOBAL HOTKEY] dir={direction} target={target!r} ok={ok}")
                return

        _log_to_file("[HOTKEY ORDER DEBUG] --- FAILED (No valid windows found) ---")

    # Group hotkeys
    def _cycle_group(group_id: str, direction: int):
        from overlay.win32_capture import (
            get_foreground_hwnd, get_window_title,
            focus_eve_window_fast, resolve_eve_window_handle, is_hwnd_valid
        )
        from overlay.replication_overlay import ReplicationOverlay, _OVERLAY_REGISTRY
        import time
        t0 = time.perf_counter()
        
        _log_to_file(f"[HOTKEY ENTRY DEBUG] function=_cycle_group group_id={group_id} direction={'next' if direction>0 else 'prev'}")
        
        hk_cfg = cfg.get('hotkeys', {})
        group = hk_cfg.get('groups', {}).get(group_id)
        if not group or not group.get('enabled'):
            return
            
        titles = group.get('clients_order', [])
        if not titles:
            logger.warning(f"[HOTKEY ORDER DEBUG] Grupo {group_id} sin miembros ordenados.")
            return

        fg_hwnd = get_foreground_hwnd()
        fg_title = get_window_title(fg_hwnd)
        
        # 1. Intentar detectar índice actual por ventana en primer plano
        current_idx = -1
        try:
            current_idx = next(i for i, t in enumerate(titles) if t == fg_title or (t and t in fg_title))
        except StopIteration:
            # 2. Si falla, buscar si alguna réplica del grupo tiene el foco de Windows
            for ov in list(_OVERLAY_REGISTRY):
                if ov._hwnd and ov._hwnd == fg_hwnd:
                    ov_title = ov._title
                    if ov_title in titles:
                        current_idx = titles.index(ov_title)
                        break
        
        # 3. Si sigue fallando, usar el último índice recordado para este grupo
        if current_idx == -1:
            current_idx = _last_group_index.get(group_id, -1)
            
        # Logging de diagnóstico ULTRA-DETALLADO
        l1 = "--- START CYCLE ---"
        l2 = f"hotkey_pressed={'Next' if direction>0 else 'Prev'}"
        l3 = f"active_group_name='{group.get('name')}'"
        l4 = f"group_raw_data={group}"
        l5 = f"members_order={titles}"
        
        logger.info(f"[HOTKEY ORDER DEBUG] {l1}")
        logger.info(f"[HOTKEY ORDER DEBUG] {l2}")
        logger.info(f"[HOTKEY ORDER DEBUG] {l3}")
        logger.info(f"[HOTKEY ORDER DEBUG] {l4}")
        logger.info(f"[HOTKEY ORDER DEBUG] {l5}")
        
        _log_to_file(f"[CYCLE] {l1}")
        _log_to_file(f"[CYCLE] {l2}")
        _log_to_file(f"[CYCLE] {l3}")
        _log_to_file(f"[CYCLE] {l4}")
        _log_to_file(f"[CYCLE] {l5}")
        
        # Overlays abiertos
        open_ovs = []
        for i, ov in enumerate(list(_OVERLAY_REGISTRY)):
            open_ovs.append({
                'idx': i,
                'overlay_title': ov._title,
                'hwnd': ov._hwnd,
                'visible': ov.isVisible()
            })
        logger.info(f"[HOTKEY ORDER DEBUG] open_overlays={open_ovs}")
        _log_to_file(f"[CYCLE] open_overlays={open_ovs}")
        
        logger.info(f"[HOTKEY ORDER DEBUG] foreground_hwnd={fg_hwnd}")
        logger.info(f"[HOTKEY ORDER DEBUG] active_detected_id_title='{fg_title}'")
        logger.info(f"[HOTKEY ORDER DEBUG] current_index={current_idx}")
        _log_to_file(f"[CYCLE] foreground_hwnd={fg_hwnd} title='{fg_title}' current_idx={current_idx}")

        # 4. Calcular siguiente salto
        start_search_idx = current_idx if current_idx != -1 else (-1 if direction > 0 else 0)
        
        for attempt in range(1, len(titles) + 1):
            next_idx = (start_search_idx + direction * attempt) % len(titles)
            target = titles[next_idx]
            
            hwnd = _hwnd_cache.get(target)
            cache_hit = True
            if not hwnd or not is_hwnd_valid(hwnd):
                cache_hit = False
                hwnd = resolve_eve_window_handle(target)
                if hwnd: _hwnd_cache[target] = hwnd
            
            if hwnd and is_hwnd_valid(hwnd):
                logger.info(f"[HOTKEY ORDER DEBUG] target_index_calculated={next_idx}")
                logger.info(f"[HOTKEY ORDER DEBUG] target_id_title_chosen='{target}'")
                logger.info(f"[HOTKEY ORDER DEBUG] method_exact_used='focus_eve_window_fast'")
                
                _log_to_file(f"[CYCLE] target_index={next_idx} target_title='{target}'")
                
                ok = focus_eve_window_fast(hwnd)
                if ok:
                    _last_group_index[group_id] = next_idx
                    ReplicationOverlay.notify_active_client_changed(hwnd)
                    
                dt = (time.perf_counter() - t0) * 1000
                logger.info(f"[HOTKEY ORDER DEBUG] --- CYCLE DONE ok={ok} ms={dt:.1f} ---")
                _log_to_file(f"[CYCLE] --- DONE ok={ok} ms={dt:.1f} ---")
                return
            else:
                logger.debug(f"[HOTKEY ORDER DEBUG] Saltando '{target}' (sin ventana válida)")
                _log_to_file(f"[CYCLE] Skipping '{target}' (invalid/missing)")

        logger.warning(f"[HOTKEY ORDER DEBUG] --- CYCLE FAILED (No valid windows found) ---")
        _log_to_file("[CYCLE] --- FAILED (No valid windows found) ---")

    # 1. Recolectar teclas usadas por grupos para evitar conflictos con el ciclo global
    group_vks = set()
    groups = hk_cfg.get('groups', {})
    for g_data in groups.values():
        if g_data.get('enabled'):
            _, n_vk = parse_hotkey(g_data.get('next', ''))
            _, p_vk = parse_hotkey(g_data.get('prev', ''))
            if n_vk: group_vks.add(n_vk)
            if p_vk: group_vks.add(p_vk)

    # 2. Registrar ciclo global (solo si no hay conflicto con grupos)
    for key, direction in [('cycle_next', +1), ('cycle_prev', -1)]:
        entry = hk_cfg.get(key, {})
        combo = entry.get('combo', '') if isinstance(entry, dict) else ''
        mods, vk = parse_hotkey(combo)
        if vk:
            if vk in group_vks:
                logger.info(f"[HOTKEY] Omitiendo ciclo global para {combo} (asignado a grupo)")
                continue
            registrations.append((mods, vk, lambda d=direction: _cycle(d)))

    # 3. Registrar hotkeys de grupos
    for g_id, g_data in groups.items():
        if not g_data.get('enabled'):
            continue
        # Siguiente
        n_mods, n_vk = parse_hotkey(g_data.get('next', ''))
        if n_vk:
            registrations.append((n_mods, n_vk, lambda gid=g_id: _cycle_group(gid, +1)))
        # Anterior
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
