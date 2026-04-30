import unittest
from unittest.mock import MagicMock, patch
from ui.market_command.my_orders_view import SyncWorker
from core.esi_client import ESIClient

class TestMyOrdersRefreshFreshMarket(unittest.TestCase):
    def setUp(self):
        self.char_id = 12345
        self.token = "fake_token"
        self.worker = SyncWorker(self.char_id, self.token)

    @patch('core.esi_client.ESIClient.character_orders')
    @patch('core.esi_client.ESIClient.market_orders_for_types')
    @patch('core.esi_client.ESIClient.universe_names')
    @patch('core.market_engine.analyze_character_orders')
    def test_sync_worker_uses_filtered_refresh(self, mock_analyze, mock_names, mock_market, mock_orders):
        # 1. Mock Character Orders
        mock_orders.return_value = [{'type_id': 1201, 'order_id': 1}]
        
        # 2. Mock Market Orders Filtered
        mock_market.return_value = [{'type_id': 1201, 'price': 99.0}]
        
        # 3. Mock Names
        mock_names.return_value = [{'id': 1201, 'name': 'Wasp I'}]
        
        # 4. Mock Analysis
        mock_analyze.return_value = []
        
        # Run worker logic (manually to avoid threading in test if possible, or just mock the call)
        # For simplicity, we check if the worker's run logic would call market_orders_for_types
        # We'll mock the client instance inside the worker if it uses one
        
        with patch('ui.market_command.my_orders_view.ESIClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.character_orders.return_value = [{'type_id': 1201, 'order_id': 1}]
            mock_client.market_orders_for_types.return_value = [{'type_id': 1201, 'price': 99.0}]
            mock_client.universe_names.return_value = [{'id': 1201, 'name': 'Wasp I'}]
            mock_client.market_orders_timings = {10000002: {"source": "test"}}
            
            # Executing a minimal version of the worker run logic
            self.worker.run()
            
            # Verify market_orders_for_types was called with the correct type_id
            mock_client.market_orders_for_types.assert_called_once_with(10000002, [1201])

if __name__ == '__main__':
    unittest.main()
