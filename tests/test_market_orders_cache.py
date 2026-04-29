import unittest
import time
from core.market_orders_cache import MarketOrdersCache

class TestMarketOrdersCache(unittest.TestCase):
    def setUp(self):
        self.cache = MarketOrdersCache.instance()
        self.cache.clear()

    def test_set_get(self):
        region_id = 10000002
        orders = [{'id': 1}, {'id': 2}]
        self.cache.set(region_id, orders)
        
        cached = self.cache.get(region_id)
        self.assertEqual(cached, orders)
        self.assertEqual(len(cached), 2)

    def test_ttl_expiry(self):
        region_id = 10000002
        orders = [{'id': 1}]
        self.cache.set(region_id, orders)
        
        # Manually expire by setting old timestamp
        self.cache._cache[region_id]['timestamp'] = time.time() - 400
        
        cached = self.cache.get(region_id)
        self.assertIsNone(cached)

    def test_different_regions(self):
        self.cache.set(1, [{'id': 1}])
        self.cache.set(2, [{'id': 2}])
        
        self.assertEqual(len(self.cache.get(1)), 1)
        self.assertEqual(len(self.cache.get(2)), 1)
        self.assertEqual(self.cache.get(1)[0]['id'], 1)
        self.assertEqual(self.cache.get(2)[0]['id'], 2)

    def test_age_reporting(self):
        region_id = 10000002
        self.cache.set(region_id, []) # Should not store empty
        self.assertIsNone(self.cache.get(region_id))
        
        self.cache.set(region_id, [{'id': 1}])
        age = self.cache.get_age(region_id)
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 1)

if __name__ == '__main__':
    unittest.main()
