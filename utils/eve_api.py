# eve_api.py - ESI API helpers
import requests
import logging
import json
import os
from typing import Optional, Dict, Set
from utils.paths import get_identity_cache_path

logger = logging.getLogger('eve.api')

# Ruta del archivo de caché persistente (ahora centralizada)
CACHE_FILE = get_identity_cache_path()

# Caché en memoria para evitar redundancia
# Éxito: {nombre: character_id}
# Fallo conocido: {nombre: None}
_ID_CACHE: Dict[str, Optional[int]] = {}

# Registro de resoluciones en curso para evitar duplicidad concurrente
_RESOLVING_NOW: Set[str] = set()

def _load_cache():
    """Carga la caché desde el disco al iniciar."""
    global _ID_CACHE
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _ID_CACHE = data
                    logger.info(f"Caché de identidad cargada: {len(_ID_CACHE)} registros.")
        except Exception as e:
            logger.debug(f"Error silencioso cargando caché: {e}")

def _save_cache():
    """Guarda la caché actual en el disco."""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_ID_CACHE, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Error silencioso guardando caché: {e}")

# Cargar caché al importar el módulo
_load_cache()

def build_character_portrait_url(character_id: Optional[int], size: int = 128) -> Optional[str]:
    """Construye la URL del retrato del personaje desde el Image Server de EVE."""
    if not character_id:
        return None
    return f"https://images.evetech.net/characters/{character_id}/portrait?size={size}"

def resolve_character_id(name: str) -> Optional[int]:
    """
    Resuelve un nombre de personaje a su Character ID usando ESI.
    Utiliza caché (éxitos y fallos) y control de concurrencia.
    """
    if not name:
        return None
        
    name_clean = name.strip()
    
    # 1. Verificar caché (incluyendo fallos conocidos)
    if name_clean in _ID_CACHE:
        return _ID_CACHE[name_clean]
        
    # 2. Control de concurrencia: evitar hilos paralelos para el mismo nombre
    if name_clean in _RESOLVING_NOW:
        return None 
        
    _RESOLVING_NOW.add(name_clean)
    try:
        url = "https://esi.evetech.net/latest/universe/ids/"
        r = requests.post(url, json=[name_clean], timeout=5)
        if r.ok:
            data = r.json()
            chars = data.get('characters', [])
            if chars:
                char_id = chars[0].get('id')
                if char_id:
                    _ID_CACHE[name_clean] = char_id
                    _save_cache() # Persistir éxito
                    return char_id
            
            # Si ESI responde OK pero no hay resultados -> Fallo conocido
            _ID_CACHE[name_clean] = None
            _save_cache() # Persistir fallo conocido
        else:
            if r.status_code < 500:
                _ID_CACHE[name_clean] = None
                _save_cache() # Persistir fallo cliente (ej: nombre inválido)
                
    except Exception as e:
        logger.warning(f"Error resolviendo ID para {name_clean}: {e}")
    finally:
        _RESOLVING_NOW.discard(name_clean)
        
    return None

def get_character_info(char_id):
    r=requests.get(f'https://esi.evetech.net/latest/characters/{char_id}/', timeout=5)
    return r.json() if r.ok else {}
