import json
import logging
from pathlib import Path

logger = logging.getLogger('eve.replicator_config')

CFG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'replicator.json'

def load_config():
    """Carga la configuración del replicador desde el archivo JSON."""
    default_cfg = {
        'global': {
            'capture_fps': 5,
            'current_profile': 'Default'
        },
        'regions': {
            'Default': {'x': 0.2, 'y': 0.2, 'w': 0.3, 'h': 0.3}
        },
        'selected_windows': [],
        'overlays': {}
    }
    
    if CFG_PATH.exists():
        try:
            data = json.loads(CFG_PATH.read_text(encoding='utf-8'))
            # Asegurar estructura básica
            if 'regions' not in data: data['regions'] = default_cfg['regions']
            if 'global' not in data: data['global'] = default_cfg['global']
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

def save_overlay_state(cfg, title, x, y, w, h, opacity, click_through):
    """Guarda el estado de una ventana overlay específica preservando otros datos."""
    if 'overlays' not in cfg: cfg['overlays'] = {}
    if title not in cfg['overlays']: cfg['overlays'][title] = {}
    
    # Actualizar solo los campos de posición y estado
    cfg['overlays'][title].update({
        'x': x, 'y': y, 'w': w, 'h': h, 
        'opacity': opacity, 'click_through': click_through
    })
    save_config(cfg)