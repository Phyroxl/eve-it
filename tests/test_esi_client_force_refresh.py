import unittest
from unittest.mock import MagicMock, patch
import time
from core.esi_client import ESIClient
from core.market_orders_cache import MarketOrdersCache

class TestESIClientForceRefresh(unittest.TestCase):
    def setUp(self):
        self.client = ESIClient()
        self.cache = MarketOrdersCache.instance()
        self.cache.clear()

    @patch('core.esi_client.ESIClient._fetch_market_page')
    def test_market_orders_uses_cache_by_default(self, mock_fetch):
        region_id = 10000002
        orders = [{'id': 1, 'price': 100.0}]
        self.cache.set(region_id, orders)
        
        result = self.client.market_orders(region_id, force_refresh=False)
        
        self.assertEqual(result, orders)
        mock_fetch.assert_not_called()
        self.assertEqual(self.client.market_orders_timings[region_id]["source"], "memory_cache")
        self.assertFalse(self.client.market_orders_timings[region_id]["force_refresh"])

    @patch('core.esi_client.ESIClient._fetch_market_page')
    def test_market_orders_force_refresh_invalidates_and_fetches(self, mock_fetch):
        region_id = 10000002
        old_orders = [{'id': 1, 'price': 100.0}]
        new_orders = [{'id': 1, 'price': 99.0}]
        
        self.cache.set(region_id, old_orders)
        
        # Mock para devolver 1 página de resultados nuevos
        mock_fetch.return_value = (new_orders, 1)
        
        result = self.client.market_orders(region_id, force_refresh=True)
        
        self.assertEqual(result, new_orders)
        mock_fetch.assert_called_once_with(region_id, 1)
        
        timings = self.client.market_orders_timings[region_id]
        self.assertEqual(timings["source"], "esi_forced_refresh")
        self.assertTrue(timings["force_refresh"])
        self.assertFalse(timings["cache_hit"])

if __name__ == '__main__':
    unittest.main()
