import time
import logging

logger = logging.getLogger('eve.market.cache')

class MarketOrdersCache:
    """
    Session-based memory cache for full market order snapshots.
    Prevents redundant heavy downloads (400k+ orders) within short intervals.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MarketOrdersCache, cls).__new__(cls)
            cls._instance._cache = {} # region_id -> {'orders': list, 'timestamp': float}
            cls._instance.ttl = 300 # Default TTL: 5 minutes
        return cls._instance

    @classmethod
    def instance(cls):
        return cls()

    def set(self, region_id: int, orders: list):
        if not orders:
            return
        self._cache[region_id] = {
            'orders': orders,
            'timestamp': time.time()
        }
        logger.info(f"[CACHE] Stored {len(orders)} orders for region {region_id}")

    def get(self, region_id: int):
        entry = self._cache.get(region_id)
        if not entry:
            return None
        
        age = time.time() - entry['timestamp']
        if age > self.ttl:
            logger.info(f"[CACHE] Entry for region {region_id} expired (age={age:.1f}s)")
            del self._cache[region_id]
            return None
            
        logger.info(f"[CACHE] Hit for region {region_id} (age={age:.1f}s, count={len(entry['orders'])})")
        return entry['orders']

    def get_age(self, region_id: int) -> float:
        entry = self._cache.get(region_id)
        if not entry:
            return 0.0
        return time.time() - entry['timestamp']

    def clear(self):
        self._cache.clear()
        logger.info("[CACHE] Cleared all market order snapshots")
