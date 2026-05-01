import unittest
import time
from core.contracts_models import ContractArbitrageResult, ContractItem, ContractsFilterConfig
from core.contracts_cache import ContractsCache
from dataclasses import asdict

class TestContractPerformance(unittest.TestCase):
    def setUp(self):
        self.cache = ContractsCache.instance()
        self.cache.cache = {} # Clear for test
        self.config = ContractsFilterConfig()

    def test_cache_hit_reuses_analysis(self):
        # 1. Simulate a first analysis
        cid = 12345
        items_raw = [{'type_id': 100, 'quantity': 1, 'is_included': True}]
        price = 1000.0
        
        analysis = {
            "contract_id": cid,
            "region_id": 10000002,
            "issuer_id": 99,
            "contract_cost": price,
            "date_expired": "2026-05-01",
            "location_id": 60003760,
            "item_type_count": 1,
            "total_units": 1,
            "items": [], # Minimal for test
            "jita_sell_value": 2000.0,
            "jita_buy_value": 1800.0,
            "gross_profit": 1000.0,
            "net_profit": 900.0,
            "roi_pct": 90.0,
            "value_concentration": 1.0,
            "has_unresolved_items": False,
            "unresolved_count": 0,
            "has_blueprints": False,
            "score": 50.0
        }
        
        self.cache.set_entry(cid, items_raw, price, analysis)
        
        # 2. Check hit
        hit = self.cache.get_entry(cid, items_raw, price)
        self.assertIsNotNone(hit)
        self.assertEqual(hit['net_profit'], 900.0)
        
        # 3. Check miss on different price
        miss = self.cache.get_entry(cid, items_raw, price + 1)
        self.assertIsNone(miss)

    def test_deduplication_logic_simulation(self):
        # Simulation of the logic in worker
        contracts = [
            {'contract_id': 1, 'price': 100},
            {'contract_id': 2, 'price': 200}
        ]
        items_by_contract = {
            1: [{'type_id': 100}, {'type_id': 101}],
            2: [{'type_id': 100}, {'type_id': 102}]
        }
        
        # Collect unique type_ids
        unique_tids = set()
        for items in items_by_contract.values():
            for it in items:
                unique_tids.add(it['type_id'])
                
        self.assertEqual(len(unique_tids), 3) # 100, 101, 102
        self.assertIn(100, unique_tids)
        self.assertIn(101, unique_tids)
        self.assertIn(102, unique_tids)

    def test_early_filtering_logic(self):
        # Case: cache says it's a blueprint
        cid = 999
        self.cache.set_entry(cid, [], 0, {"has_blueprints": True})
        
        light = self.cache.get_light_entry(cid)
        self.assertTrue(light['has_blueprints'])

if __name__ == '__main__':
    unittest.main()
