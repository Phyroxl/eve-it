import unittest
from unittest.mock import MagicMock, patch
from core.market_order_pricing import recalculate_competitor_price, recommend_sell_price, recommend_buy_price
from core.market_models import OpenOrder, OpenOrderAnalysis

class TestMarketCompetitorRevalidation(unittest.TestCase):

    def test_recalculate_competitor_sell_simple(self):
        """Basic case: SELL order, find best competitor and exclude own."""
        # Own orders: 2 orders at 1692000
        own = [
            {"type_id": 28209, "is_buy_order": False, "price": 1692000},
            {"type_id": 28209, "is_buy_order": False, "price": 1692000},
        ]
        
        # Market: 1 at 1612000 (competitor), 2 at 1692000 (ours)
        market = [
            {"is_buy_order": False, "price": 1612000}, # Competitor
            {"is_buy_order": False, "price": 1692000}, # Own 1
            {"is_buy_order": False, "price": 1692000}, # Own 2
            {"is_buy_order": True,  "price": 1500000}, # Buy order (ignore)
        ]
        
        res = recalculate_competitor_price(market, own, 28209, False)
        
        self.assertEqual(res["competitor_price"], 1612000)
        self.assertEqual(res["own_excluded_count"], 2)
        self.assertEqual(res["orders_count"], 3) # only sells

    def test_recalculate_competitor_sell_warden_case(self):
        """
        Warden II case: 
        Analysis thought competitor was 1.612M.
        Fresh market says competitor is 1.687M.
        """
        own = [{"type_id": 28209, "is_buy_order": False, "price": 1692000}]
        
        market = [
            {"is_buy_order": False, "price": 1687000}, # Real competitor
            {"is_buy_order": False, "price": 1692000}, # Own
        ]
        
        res = recalculate_competitor_price(market, own, 28209, False)
        
        self.assertEqual(res["competitor_price"], 1687000)
        self.assertEqual(res["own_excluded_count"], 1)
        
        # Fresh recommendation should be 1.687M - 1k tick = 1.686M
        rec = recommend_sell_price(res["competitor_price"])
        self.assertEqual(rec, 1686000)

class TestIntegrationMyOrdersView(unittest.TestCase):
    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_success(self, mock_esi_class):
        mock_esi = mock_esi_class.return_value
        # Warden II scenario
        mock_esi.get_market_orders_for_type.return_value = [
            {"is_buy_order": False, "price": 1687000}, # Competitor
            {"is_buy_order": False, "price": 1692000}, # Own
        ]
        
        # Mock view and labels to avoid PySide6 instantiation issues
        from ui.market_command.my_orders_view import MarketMyOrdersView
        view = MagicMock()
        view.all_orders = []
        
        order = OpenOrder(
            order_id=42, type_id=28209, item_name="Warden II",
            is_buy_order=False, price=1692000, 
            volume_total=10, volume_remain=10, issued="", location_id=60003760, range="",
            analysis=OpenOrderAnalysis(
                is_buy=False, state="Superada", competitor_price=1612000,
                best_buy=1500000, best_sell=1612000, spread_pct=5.0, 
                competitive=False, difference_to_best=80000,
                gross_profit_per_unit=0, net_profit_per_unit=0, net_profit_total=0, margin_pct=0
            )
        )
        view.all_orders = [order]
        
        # Call the method directly from the class, passing our mock view as 'self'
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        
        self.assertTrue(res["checked"])
        self.assertTrue(res["is_fresh"])
        self.assertEqual(res["fresh_competitor_price"], 1687000)
        self.assertEqual(res["fresh_recommended_price"], 1686000)
        self.assertTrue(res["price_changed"])
        self.assertEqual(res["price_source"], "fresh_market_book")

    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_error(self, mock_esi_class):
        mock_esi = mock_esi_class.return_value
        mock_esi.get_market_orders_for_type.side_effect = Exception("ESI Down")
        
        from ui.market_command.my_orders_view import MarketMyOrdersView
        view = MagicMock()
        view.all_orders = []
        
        order = MagicMock()
        order.type_id = 1234
        order.analysis.competitor_price = 100.0
        
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        
        self.assertFalse(res["is_fresh"])
        self.assertIn("Error revalidando mercado: ESI Down", res["warnings"])

if __name__ == "__main__":
    unittest.main()
