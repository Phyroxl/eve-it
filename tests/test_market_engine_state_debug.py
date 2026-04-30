import unittest
from core.market_engine import analyze_character_orders
from core.market_models import FilterConfig

class TestMarketEngineStateDebug(unittest.TestCase):
    def setUp(self):
        self.item_names = {1201: "Wasp I"}
        self.config = FilterConfig()

    def test_wasp_i_state_debug_presence(self):
        char_orders = [{
            'order_id': 100,
            'type_id': 1201,
            'price': 100.0,
            'is_buy_order': False,
            'location_id': 60003760,
            'volume_remain': 5
        }]
        
        market_orders = [
            {'type_id': 1201, 'location_id': 60003760, 'price': 99.0, 'is_buy_order': False},
            {'type_id': 1201, 'location_id': 60003760, 'price': 100.0, 'is_buy_order': False}
        ]
        
        results = analyze_character_orders(char_orders, market_orders, self.item_names, self.config)
        
        o = results[0]
        self.assertTrue(hasattr(o, "_state_debug"))
        debug = o._state_debug
        
        self.assertEqual(debug["item_name"], "Wasp I")
        self.assertEqual(debug["competitor_price"], 99.0)
        self.assertEqual(debug["market_orders_loc_sell_count"], 2)
        self.assertEqual(debug["own_orders_excluded_count"], 1)

if __name__ == '__main__':
    unittest.main()
