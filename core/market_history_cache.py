import json
import os
import time
import logging

logger = logging.getLogger('eve.history_cache')

HISTORY_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 horas

class MarketHistoryCache:
    _instance = None
    _cache_file = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', 'data', 'market_history_cache.json')
    )

    def __init__(self):
        self._data = {}
        self._load()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _key(self, region_id: int, type_id: int) -> str:
        return f"{region_id}:{type_id}"

    def get(self, region_id: int, type_id: int):
        entry = self._data.get(self._key(region_id, type_id))
        if entry and time.time() - entry['timestamp'] < HISTORY_CACHE_TTL_SECONDS:
            return entry['history']
        if entry:
            del self._data[self._key(region_id, type_id)]
        return None

    def set(self, region_id: int, type_id: int, history: list):
        self._data[self._key(region_id, type_id)] = {
            'timestamp': time.time(),
            'history': history
        }

    def get_many(self, region_id: int, type_ids) -> dict:
        result = {}
        for t in type_ids:
            h = self.get(region_id, t)
            if h is not None:
                result[t] = h
        return result

    def save(self):
        os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f)
            logger.debug(f"[HISTORY CACHE] saved {len(self._data)} entries")
        except Exception as e:
            logger.error(f"[HISTORY CACHE] save error: {e}")

    def _load(self):
        if not os.path.exists(self._cache_file):
            return
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            now = time.time()
            self._data = {
                k: v for k, v in raw.items()
                if now - v.get('timestamp', 0) < HISTORY_CACHE_TTL_SECONDS
            }
            logger.debug(f"[HISTORY CACHE] loaded {len(self._data)} valid entries")
        except Exception as e:
            logger.error(f"[HISTORY CACHE] load error: {e}")
            self._rename_corrupt()

    def _rename_corrupt(self):
        corrupt_path = self._cache_file + f".corrupt.{int(time.time())}"
        try:
            os.rename(self._cache_file, corrupt_path)
            logger.warning(f"[HISTORY CACHE] corrupt file renamed to: {corrupt_path}")
        except Exception as err:
            logger.error(f"[HISTORY CACHE] could not rename corrupt file: {err}")
