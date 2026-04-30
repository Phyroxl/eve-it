import unittest
from core.market_engine import analyze_character_orders
from core.market_models import FilterConfig

class TestMyOrdersStateTransition(unittest.TestCase):
    def setUp(self):
        self.char_id = 12345
        self.token = "fake_token"
        self.item_names = {123: "Test Item"}
        self.config = FilterConfig()

    def test_sell_order_outbid_then_leading(self):
        # Escenario: Mi orden está a 100, el competidor a 99. Estado: Superada.
        # Luego actualizo mi orden a 98. El mercado fresco tiene mi orden a 98 y el competidor a 99. Estado: Liderando.
        
        location_id = 60003760
        type_id = 123
        
        my_order = {
            'order_id': 1,
            'type_id': type_id,
            'location_id': location_id,
            'price': 100.0,
            'is_buy_order': False,
            'volume_remain': 10
        }
        
        # Mercado con competidor a 99 y mi orden a 100
        market_orders = [
            {'type_id': type_id, 'location_id': location_id, 'price': 99.0, 'is_buy_order': False},
            {'type_id': type_id, 'location_id': location_id, 'price': 100.0, 'is_buy_order': False}
        ]
        
        analyzed = analyze_character_orders([my_order], market_orders, self.item_names, self.config, self.char_id, self.token)
        self.assertEqual(analyzed[0].analysis.state, "Superada con beneficio")
        self.assertFalse(analyzed[0].analysis.competitive)

        # AHORA: Actualizamos mi orden a 98 e inyectamos mercado fresco
        my_order_updated = my_order.copy()
        my_order_updated['price'] = 98.0
        
        market_orders_fresh = [
            {'type_id': type_id, 'location_id': location_id, 'price': 98.0, 'is_buy_order': False}, # Mi nueva orden
            {'type_id': type_id, 'location_id': location_id, 'price': 99.0, 'is_buy_order': False}  # El competidor
        ]
        
        analyzed_fresh = analyze_character_orders([my_order_updated], market_orders_fresh, self.item_names, self.config, self.char_id, self.token)
        self.assertEqual(analyzed_fresh[0].analysis.state, "Liderando")
        self.assertTrue(analyzed_fresh[0].analysis.competitive)

    def test_buy_order_leading_with_no_competitor(self):
        location_id = 60003760
        type_id = 456
        
        my_order = {
            'order_id': 2,
            'type_id': type_id,
            'location_id': location_id,
            'price': 50.0,
            'is_buy_order': True,
            'volume_remain': 10
        }
        
        # Solo mi orden en el mercado
        market_orders = [
            {'type_id': type_id, 'location_id': location_id, 'price': 50.0, 'is_buy_order': True}
        ]
        
        analyzed = analyze_character_orders([my_order], market_orders, self.item_names, self.config, self.char_id, self.token)
        self.assertEqual(analyzed[0].analysis.state, "Liderando (Empate)") # Empate conmigo mismo es esperado por lógica actual
        self.assertTrue(analyzed[0].analysis.competitive)

if __name__ == '__main__':
    unittest.main()
