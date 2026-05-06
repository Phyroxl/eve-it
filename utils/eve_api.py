# eve_api.py - ESI API helpers
import requests
import logging
import json
import time
import unicodedata
import os
from typing import Optional, Dict, Set
from utils.paths import get_identity_cache_path

logger = logging.getLogger('eve.api')

# Ruta del archivo de caché persistente (ahora centralizada)
CACHE_FILE = get_identity_cache_path()

# Caché persistente en disco — SOLO éxitos confirmados (char_id > 0)
_ID_CACHE: Dict[str, int] = {}

# Fallos transitorios en memoria con TTL — no se persisten al disco
# {nombre: timestamp_de_fallo}  — se reintenta tras _FAILED_TTL segundos
_FAILED_NAMES: Dict[str, float] = {}
_FAILED_TTL = 1800  # 30 minutos

# Registro de resoluciones en curso para evitar duplicidad concurrente
_RESOLVING_NOW: Set[str] = set()

def _load_cache():
    """Carga la caché desde el disco al iniciar — filtra entradas None/inválidas."""
    global _ID_CACHE
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Solo cargar entradas con char_id positivo válido
                    _ID_CACHE = {k: v for k, v in data.items() if isinstance(v, int) and v > 0}
                    logger.info(f"Caché de identidad cargada: {len(_ID_CACHE)} registros.")
        except Exception as e:
            logger.debug(f"Error silencioso cargando caché: {e}")

def _save_cache():
    """Guarda solo éxitos confirmados en disco."""
    try:
        to_save = {k: v for k, v in _ID_CACHE.items() if isinstance(v, int) and v > 0}
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Error silencioso guardando caché: {e}")

# Cargar caché al importar el módulo
_load_cache()

def _normalize_sender(name: str) -> str:
    """Elimina caracteres de control/invisibles que los chatlogs de EVE pueden incluir."""
    # Eliminar BOM y caracteres de control Unicode
    clean = ''.join(ch for ch in name if unicodedata.category(ch) not in ('Cc', 'Cf', 'Zs') or ch == ' ')
    return clean.strip()

def build_character_portrait_url(character_id: Optional[int], size: int = 128) -> Optional[str]:
    """Construye la URL del retrato del personaje desde el Image Server de EVE."""
    if not character_id:
        return None
    return f"https://images.evetech.net/characters/{character_id}/portrait?size={size}"

def resolve_character_id(name: str) -> Optional[int]:
    """
    Resuelve un nombre de personaje a su Character ID usando ESI.
    - Éxitos: cachados en disco indefinidamente.
    - Fallos ESI definitivos (4xx / nombre no encontrado): TTL de 30 min en memoria.
    - Fallos de red (5xx / timeout): no se cachean — se reintenta la próxima vez.
    """
    if not name:
        return None

    name_clean = _normalize_sender(name)
    if not name_clean:
        return None

    # 1. Caché de éxitos (persistente)
    if name_clean in _ID_CACHE:
        logger.debug(f"PORTRAIT CACHE HIT {name_clean!r} → {_ID_CACHE[name_clean]}")
        return _ID_CACHE[name_clean]

    # 2. Fallos recientes en cooldown
    if name_clean in _FAILED_NAMES:
        age = time.time() - _FAILED_NAMES[name_clean]
        if age < _FAILED_TTL:
            logger.debug(f"PORTRAIT FAIL COOLDOWN {name_clean!r} age={age:.0f}s")
            return None
        del _FAILED_NAMES[name_clean]  # TTL expirado → reintentar

    # 3. Control de concurrencia
    if name_clean in _RESOLVING_NOW:
        return None

    _RESOLVING_NOW.add(name_clean)
    try:
        url = "https://esi.evetech.net/latest/universe/ids/"
        logger.debug(f"PORTRAIT RESOLVE ESI {name_clean!r}")
        r = requests.post(url, json=[name_clean], timeout=8)
        if r.ok:
            data = r.json()
            chars = data.get('characters', [])
            if chars:
                char_id = chars[0].get('id')
                if char_id and char_id > 0:
                    _ID_CACHE[name_clean] = char_id
                    _save_cache()
                    logger.debug(f"PORTRAIT RESOLVED {name_clean!r} → {char_id}")
                    return char_id

            # ESI OK pero sin resultados → nombre inválido o NPC → cooldown
            logger.debug(f"PORTRAIT NOT FOUND ESI {name_clean!r} → cooldown {_FAILED_TTL}s")
            _FAILED_NAMES[name_clean] = time.time()

        elif r.status_code < 500:
            # Error cliente (400/401/404) → probable nombre inválido → cooldown
            logger.debug(f"PORTRAIT ESI 4xx {r.status_code} {name_clean!r} → cooldown")
            _FAILED_NAMES[name_clean] = time.time()
        else:
            # Error servidor (500+) → transitorio → no cachear, reintentar próxima vez
            logger.warning(f"PORTRAIT ESI {r.status_code} transitorio para {name_clean!r}")

    except Exception as e:
        # Timeout / red → no cachear
        logger.warning(f"PORTRAIT ESI timeout/error para {name_clean!r}: {e}")
    finally:
        _RESOLVING_NOW.discard(name_clean)

    return None

def get_character_info(char_id):
    r=requests.get(f'https://esi.evetech.net/latest/characters/{char_id}/', timeout=5)
    return r.json() if r.ok else {}
