import json
import logging
from pathlib import Path

logger = logging.getLogger('eve.replicator_config')

from utils.paths import ROOT_DIR
CFG_PATH = ROOT_DIR / 'config' / 'replicator.json'


def _profile_log(event: str, **kw):
    """Log compacto de eventos save/load de perfiles a consola + archivo."""
    msg = f"[PROFILE {event}] path={str(CFG_PATH)!r} " + " ".join(f"{k}={v!r}" for k, v in kw.items())
    logger.info(msg)
    try:
        _lp = CFG_PATH.parent.parent / 'logs' / 'replicator_profiles_debug.log'
        _lp.parent.mkdir(parents=True, exist_ok=True)
        import datetime
        ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        with open(_lp, 'a', encoding='utf-8') as _f:
            _f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

# Región de captura estándar de referencia (proporcional 0.0-1.0)
# Orientada por defecto a la zona inferior central (Módulos/Capacitor)
DEFAULT_REPLICATOR_CAPTURE_REGION = {
    'x': 0.46875,    # 900 / 1920
    'y': 0.3425926,  # 370 / 1080
    'w': 0.078125,   # 150 / 1920
    'h': 0.1388889   # 150 / 1080
}

# Default per-overlay settings (all new EVE-O style fields)
OVERLAY_DEFAULTS = {
    'fps': 30,
    'x': 400, 'y': 300,
    'w': 280, 'h': 200,
    'opacity': 1.0,
    'locked': False,
    'maintain_aspect': True,
    # Task 4 — visibility behaviour
    'always_on_top': True,
    'hide_when_inactive': False,
    # Task 5 — snap to grid
    'snap_enabled': False,
    'snap_x': 20,
    'snap_y': 20,
    # Task 6 — client label
    'label_visible': True,
    'label_pos': 'top_left',      # top_left|top_center|top_right|bottom_left|bottom_center|bottom_right
    'label_font_size': 10,
    'label_color': '#ffffff',
    'label_bg': True,
    'label_bg_color': '#000000',
    'label_bg_opacity': 0.65,
    'label_padding': 4,
    # Task 7 — border
    'border_visible': True,
    'border_width': 2,
    'border_shape': 'square', # square|rounded|pill
    'show_gray_frame': False,
    'client_color': '#00c8ff',
    'active_border_color': '#00ff64',
    'highlight_active': True,
}


def load_config():
    """Carga la configuración del replicador desde el archivo JSON."""
    default_cfg = {
        'global': {
            'capture_fps': 30,
            'current_profile': 'Default',
        },
        'regions': {
            'Default': DEFAULT_REPLICATOR_CAPTURE_REGION.copy()
        },
        'selected_windows': [],
        'overlays': {},
    }

    if CFG_PATH.exists():
        try:
            data = json.loads(CFG_PATH.read_text(encoding='utf-8'))
            if 'regions' not in data:
                data['regions'] = default_cfg['regions']
            if 'global' not in data:
                data['global'] = default_cfg['global']
            if 'overlays' not in data:
                data['overlays'] = {}
            _profiles = data.get('layout_profiles', {})
            _profile_log('LOAD', count=len(_profiles), names=list(_profiles.keys()))
            return data
        except Exception as e:
            logger.error(f"Error cargando config: {e}")
            _profile_log('LOAD_ERROR', error=str(e))

    _profile_log('LOAD_DEFAULT', reason='file_not_found')
    return default_cfg


def save_config(cfg):
    """Guarda la configuración completa."""
    try:
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CFG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        return True
    except Exception as e:
        logger.error(f"Error guardando config: {e}")
        return False


def get_overlay_cfg(cfg, title: str) -> dict:
    """Devuelve la config del overlay con defaults rellenos para claves que falten."""
    stored = cfg.get('overlays', {}).get(title, {})
    merged = OVERLAY_DEFAULTS.copy()
    merged.update(stored)
    
    # [NUEVO] Migración / Fallback de formas eliminadas
    shape = merged.get('border_shape', 'square')
    if shape == 'glow':
        merged['border_shape'] = 'rounded'
    elif shape == 'brackets':
        merged['border_shape'] = 'square'
    elif shape not in ('square', 'rounded', 'pill'):
        merged['border_shape'] = 'square'
        
    return merged


def save_overlay_state(cfg, title, x, y, w, h, opacity, click_through=False, extra: dict = None):
    """Guarda el estado de una ventana overlay preservando claves no tocadas."""
    if 'overlays' not in cfg:
        cfg['overlays'] = {}
    if title not in cfg['overlays']:
        cfg['overlays'][title] = {}

    cfg['overlays'][title].update({
        'x': x, 'y': y, 'w': w, 'h': h,
        'opacity': opacity,
    })
    if extra:
        cfg['overlays'][title].update(extra)
    save_config(cfg)


def save_overlay_cfg(cfg, title: str, ov_cfg: dict):
    """Guarda el dict completo ov_cfg para un overlay concreto."""
    if 'overlays' not in cfg:
        cfg['overlays'] = {}
    if title not in cfg['overlays']:
        cfg['overlays'][title] = {}
    cfg['overlays'][title].update(ov_cfg)
    save_config(cfg)


# Keys safe to copy from one overlay to all others (excludes position/size/identity)
COMMON_SETTING_KEYS = [
    'always_on_top', 'hide_when_inactive', 'locked',
    'snap_enabled', 'snap_x', 'snap_y',
    'label_visible', 'label_pos', 'label_font_size',
    'label_color', 'label_bg', 'label_bg_color',
    'label_bg_opacity', 'label_padding',
    'border_visible', 'highlight_active', 'border_width',
    'active_border_color',
    'fps', 'opacity',
]


def apply_common_settings_to_all(cfg, source_title: str,
                                  keys=None, include_client_color: bool = False):
    """Legacy helper."""
    if keys is None:
        keys = COMMON_SETTING_KEYS
    apply_settings_keys_to_all(cfg, source_title, keys, include_client_color)

def apply_settings_keys_to_all(cfg, source_title: str,
                               keys: list, include_client_color: bool = False):
    """Copia un set específico de keys a todos los overlays.
    Si include_client_color es True, también copia client_color aunque no esté en keys.
    """
    source = cfg.get('overlays', {}).get(source_title, {})
    if not source: return
    for title, ov_data in cfg.get('overlays', {}).items():
        if title == source_title:
            continue
        for k in keys:
            if k in source:
                ov_data[k] = source[k]
        if include_client_color and 'client_color' in source:
            ov_data['client_color'] = source['client_color']
    save_config(cfg)


# Keys copied when user clicks "apply label settings to all"
LABEL_COPY_KEYS = [
    'label_visible', 'label_pos', 'label_font_size',
    'label_color', 'label_bg', 'label_bg_color',
    'label_bg_opacity', 'label_padding',
]

# Keys copied when user clicks "apply border settings to all"
BORDER_COPY_KEYS = [
    'border_visible', 'border_width', 'border_shape',
    'highlight_active', 'active_border_color', 'show_gray_frame',
]

# Keys stored in a layout profile (legacy subset — kept for backward compat with older profiles/tests)
LAYOUT_PROFILE_KEYS = [
    'w', 'h', 'maintain_aspect',
    'snap_enabled', 'snap_x', 'snap_y',
    'fps', 'opacity', 'label_visible', 'border_visible',
    'region_x', 'region_y', 'region_w', 'region_h',
]

# Full profile keys — all per-overlay settings including x/y position (full snapshot)
FULL_PROFILE_KEYS = [
    # Position (saved in full profiles so layout restore is exact)
    'x', 'y',
    # Capture
    'fps', 'region_x', 'region_y', 'region_w', 'region_h',
    # Layout
    'w', 'h', 'maintain_aspect', 'opacity',
    'snap_enabled', 'snap_x', 'snap_y',
    # General
    'always_on_top', 'hide_when_inactive', 'locked',
    # Label
    'label_visible', 'label_pos', 'label_font_size',
    'label_color', 'label_bg', 'label_bg_color',
    'label_bg_opacity', 'label_padding',
    # Border
    'border_visible', 'border_width', 'border_shape',
    'show_gray_frame', 'client_color',
    'active_border_color', 'highlight_active',
]

# Keys copied when user clicks "copy all non-layout settings to all"
NON_LAYOUT_COPY_KEYS = [
    'always_on_top', 'hide_when_inactive', 'locked',
] + LABEL_COPY_KEYS + BORDER_COPY_KEYS

# Full replicate keys (everything except identity/hwnd)
FULL_REPLICATE_KEYS = list(set(
    ['x', 'y'] + LAYOUT_PROFILE_KEYS + NON_LAYOUT_COPY_KEYS
))

_DEFAULT_LAYOUT_PROFILE = {
    'w': 280, 'h': 200, 'maintain_aspect': True,
    'snap_enabled': False, 'snap_x': 20, 'snap_y': 20,
    'fps': 30, 'opacity': 1.0, 'label_visible': True, 'border_visible': True,
    'region_x': DEFAULT_REPLICATOR_CAPTURE_REGION['x'],
    'region_y': DEFAULT_REPLICATOR_CAPTURE_REGION['y'],
    'region_w': DEFAULT_REPLICATOR_CAPTURE_REGION['w'],
    'region_h': DEFAULT_REPLICATOR_CAPTURE_REGION['h'],
}

_HOTKEY_DEFAULTS = {
    'per_client': {},
    'cycle_next': {'combo': 'F14'},
    'cycle_prev': {'combo': 'CTRL+F14'},
    'groups': {}, # group_id: {enabled, name, clients_order, next, prev}
}


def get_layout_profiles(cfg: dict) -> dict:
    profiles = cfg.get('layout_profiles', {})
    if not profiles:
        profiles = {'Default': _DEFAULT_LAYOUT_PROFILE.copy()}
    return profiles


def save_layout_profile(cfg: dict, name: str, data: dict):
    cfg.setdefault('layout_profiles', {})
    # Save full profile (all FULL_PROFILE_KEYS present in data) for complete config restore
    cfg['layout_profiles'][name] = {k: data[k] for k in FULL_PROFILE_KEYS if k in data}
    ok = save_config(cfg)
    _profile_log('SAVE', name=name, keys=list(cfg['layout_profiles'][name].keys()),
                 total_profiles=list(cfg['layout_profiles'].keys()), ok=ok)


def delete_layout_profile(cfg: dict, name: str):
    cfg.get('layout_profiles', {}).pop(name, None)
    if cfg.get('active_layout_profile') == name:
        cfg['active_layout_profile'] = 'Default'
    save_config(cfg)


def get_active_layout_profile(cfg: dict) -> tuple:
    """Returns (name, profile_dict)."""
    profiles = get_layout_profiles(cfg)
    name = cfg.get('active_layout_profile', 'Default')
    if name not in profiles:
        name = next(iter(profiles), 'Default')
    return name, profiles.get(name, _DEFAULT_LAYOUT_PROFILE.copy())


def apply_layout_profile_to_ov_cfg(ov_cfg: dict, profile: dict):
    """Copy all profile keys into an overlay config dict. x/y are included when present in profile."""
    for k, v in profile.items():
        ov_cfg[k] = v


def get_hotkeys_cfg(cfg: dict) -> dict:
    result = _HOTKEY_DEFAULTS.copy()
    result.update(cfg.get('hotkeys', {}))
    return result


def save_hotkeys_cfg(cfg: dict, hk: dict):
    cfg['hotkeys'] = hk
    save_config(cfg)
