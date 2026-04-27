import os
from pathlib import Path
import logging

logger = logging.getLogger('eve.paths')

# Raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent

# Carpeta de datos runtime
DATA_DIR = ROOT_DIR / "data"

def ensure_dirs():
    """Asegura que las carpetas de datos existan."""
    try:
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.debug(f"Error creando directorios de datos: {e}")

def get_identity_cache_path() -> Path:
    """Centraliza la ruta de la caché de identidad y maneja la migración."""
    ensure_dirs()
    new_path = DATA_DIR / "identity_cache.json"
    old_path = ROOT_DIR / "identity_cache.json"
    
    # Migración automática desde la raíz si existe
    if old_path.exists() and not new_path.exists():
        try:
            old_path.rename(new_path)
            logger.info(f"Caché de identidad migrada a: {new_path}")
        except Exception as e:
            logger.warning(f"No se pudo migrar la caché antigua: {e}")
            return old_path # Fallback a la antigua si falla el movimiento
            
    return new_path
