import unittest
import time
from core.market_orders_cache import MarketOrdersCache

class TestMarketOrdersCacheInvalidation(unittest.TestCase):
    def setUp(self):
        self.cache = MarketOrdersCache.instance()
        self.cache.clear()

    def test_invalidate_region_removes_entry(self):
        region_id = 10000002
        orders = [{'id': 1, 'price': 100.0}]
        
        self.cache.set(region_id, orders)
        self.assertIsNotNone(self.cache.get(region_id))
        
        self.cache.invalidate(region_id)
        self.assertIsNone(self.cache.get(region_id), "La entrada de la región debería haber sido eliminada.")

    def test_invalidate_missing_region_no_crash(self):
        # No debería lanzar excepción si la región no existe
        self.cache.invalidate(99999999)

    def test_force_refresh_logic_integration_esi_mock(self):
        # Simular comportamiento de ESIClient con force_refresh
        region_id = 10000002
        orders_v1 = [{'id': 1, 'price': 100.0}]
        
        self.cache.set(region_id, orders_v1)
        
        # Simulamos lo que hace market_orders(force_refresh=True)
        force_refresh = True
        if force_refresh:
            self.cache.invalidate(region_id)
            
        self.assertIsNone(self.cache.get(region_id), "La caché debería estar vacía tras invalidación forzada.")

if __name__ == '__main__':
    unittest.main()
