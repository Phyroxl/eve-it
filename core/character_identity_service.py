"""Character identity (name resolution) for Visual Clon.

Resolves EVE character IDs to display names via the public ESI
/universe/names/ endpoint (no authentication required).
Results are cached in memory and persisted to disk across sessions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger('eve.visual_clon.identity')

# ── In-memory cache (str char_id → str name) ─────────────────────────────────
_NAME_CACHE: Dict[str, str] = {}

_CACHE_FILE = Path(__file__).parent.parent / 'config' / 'visual_clon_name_cache.json'
_ESI_NAMES_URL = (
    'https://esi.evetech.net/latest/universe/names/?datasource=tranquility'
)
_REQUEST_TIMEOUT = 8  # seconds


def _load_disk_cache() -> None:
    if not _CACHE_FILE.exists():
        return
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding='utf-8'))
        _NAME_CACHE.update({str(k): str(v) for k, v in data.items()})
        logger.debug(f"[IDENTITY] Disk cache loaded: {len(data)} names")
    except Exception as e:
        logger.warning(f"[IDENTITY] Failed to load disk cache: {e}")


def _save_disk_cache() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps(_NAME_CACHE, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
    except Exception as e:
        logger.warning(f"[IDENTITY] Failed to save disk cache: {e}")


def get_name(char_id: str) -> str:
    """Return cached name or 'Personaje {id}' fallback. Never blocks."""
    return _NAME_CACHE.get(str(char_id), f"Personaje {char_id}")


def resolve_names_batch(char_ids: List[str]) -> Dict[str, str]:
    """
    Resolve character IDs to names via ESI /universe/names/ (public endpoint).
    Filters already-cached IDs, fetches only the missing ones.
    Updates in-memory and disk cache.
    Returns {char_id: name} for all requested IDs.
    """
    ids = [str(c) for c in char_ids]
    uncached = [cid for cid in ids if cid not in _NAME_CACHE]

    if uncached:
        _fetch_from_esi(uncached)

    return {cid: _NAME_CACHE.get(cid, f"Personaje {cid}") for cid in ids}


def _fetch_from_esi(char_ids: List[str]) -> None:
    try:
        import requests as _req
        ids_int = [int(cid) for cid in char_ids]
        resp = _req.post(
            _ESI_NAMES_URL,
            json=ids_int,
            timeout=_REQUEST_TIMEOUT,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
        )
        if resp.status_code == 200:
            for item in resp.json():
                if isinstance(item, dict) and item.get('category') == 'character':
                    _NAME_CACHE[str(item['id'])] = item['name']
            _save_disk_cache()
            logger.info(f"[IDENTITY] ESI resolved {len(char_ids)} IDs")
        else:
            logger.warning(f"[IDENTITY] ESI returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"[IDENTITY] ESI name resolution failed: {e}")


# Load disk cache when module is first imported
_load_disk_cache()
