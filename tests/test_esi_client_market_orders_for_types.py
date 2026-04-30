import unittest
from unittest.mock import MagicMock, patch
from core.esi_client import ESIClient

class TestESIClientMarketOrdersForTypes(unittest.TestCase):
    def setUp(self):
        self.client = ESIClient()

    @patch('core.esi_client.ESIClient.get_market_orders_for_type')
    def test_market_orders_for_types_fetches_correctly(self, mock_get):
        region_id = 10000002
        type_ids = [1201, 1201, 34] # Duplicado intencional
        
        mock_get.side_effect = [
            [{'type_id': 1201, 'price': 10.0}],
            [{'type_id': 34, 'price': 5.0}]
        ]
        
        results = self.client.market_orders_for_types(region_id, type_ids)
        
        self.assertEqual(len(results), 2)
        # Debe haber llamado a get_market_orders_for_type para cada ID único (34 y 1201)
        self.assertEqual(mock_get.call_count, 2)
        
        timings = self.client.market_orders_timings[region_id]
        self.assertEqual(timings["source"], "esi_type_filtered_refresh")
        self.assertEqual(timings["type_ids_count"], 2)
        self.assertEqual(timings["type_ids_fetched"], 2)

if __name__ == '__main__':
    unittest.main()
