import json
import logging
from pathlib import Path

logger = logging.getLogger('eve.replicator_config')

CFG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'replicator.json'

# Default per-overlay settings (all new EVE-O style fields)
OVERLAY_DEFAULTS = {
    'fps': 30,
    'x': 400, 'y': 300,
    'w': 280, 'h': 200,
    'opacity': 1.0,
    'locked': False,
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
            'Default': {'x': 0.2, 'y': 0.2, 'w': 0.3, 'h': 0.3}
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
            return data
        except Exception as e:
            logger.error(f"Error cargando config: {e}")

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
    """Copia las claves globalizables del overlay fuente a todos los demás.

    No toca x, y, w, h, ni client_color (salvo include_client_color=True).
    Guarda la config completa al terminar.
    """
    if keys is None:
        keys = COMMON_SETTING_KEYS
    source = cfg.get('overlays', {}).get(source_title, {})
    for title, ov_data in cfg.get('overlays', {}).items():
        if title == source_title:
            continue
        for k in keys:
            if k in source:
                ov_data[k] = source[k]
        if include_client_color and 'client_color' in source:
            ov_data['client_color'] = source['client_color']
    save_config(cfg)
