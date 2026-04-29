import unittest
from unittest.mock import MagicMock, patch
from core.market_order_pricing import recalculate_competitor_price, recommend_sell_price, recommend_buy_price, _SENTINEL_MAX, _SENTINEL_MIN
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
        self.assertTrue(res["comp_prices_found"])
        self.assertEqual(res["own_excluded_count"], 2)
        self.assertEqual(res["orders_count"], 3) # only sells

    def test_recalculate_competitor_sell_warden_case(self):
        """
        Warden II case: 
        Analysis thought competitor was 1.612M (regional).
        Fresh market says competitor is 1.687M in local station (60003760).
        There is another order at 1.612M in a different station.
        """
        own = [{"type_id": 28209, "is_buy_order": False, "price": 1692000, "location_id": 60003760}]
        
        market = [
            {"is_buy_order": False, "price": 1687000, "location_id": 60003760}, # Local competitor
            {"is_buy_order": False, "price": 1692000, "location_id": 60003760}, # Own
            {"is_buy_order": False, "price": 1612000, "location_id": 12345678}, # Other station competitor
        ]
        
        res = recalculate_competitor_price(market, own, 28209, False, location_id=60003760)
        
        self.assertEqual(res["competitor_price"], 1687000)
        self.assertTrue(res["comp_prices_found"])
        self.assertEqual(res["own_excluded_count"], 1)
        self.assertEqual(res["regional_orders_count"], 3)
        self.assertEqual(res["location_orders_count"], 2)
        
        # Fresh recommendation should be 1.687M - 1k tick = 1.686M
        rec = recommend_sell_price(res["competitor_price"])
        self.assertEqual(rec, 1686000)

    def test_recalculate_competitor_no_location_filter_still_works(self):
        """Ensure backward compatibility if location_id is None."""
        market = [{"is_buy_order": False, "price": 1000, "location_id": 1}]
        res = recalculate_competitor_price(market, [], 1, False, location_id=None)
        self.assertEqual(res["competitor_price"], 1000)
        self.assertFalse(res["filtered_by_location"])

class TestIntegrationMyOrdersView(unittest.TestCase):
    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_success_with_location(self, mock_esi_class):
        mock_esi = mock_esi_class.return_value
        # Warden II scenario: regional has 1.612M, but local (60003760) has 1.687M
        mock_esi.get_market_orders_for_type.return_value = [
            {"is_buy_order": False, "price": 1612000, "location_id": 123},     # Regional
            {"is_buy_order": False, "price": 1687000, "location_id": 60003760}, # Local Comp
            {"is_buy_order": False, "price": 1692000, "location_id": 60003760}, # Own
        ]
        
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
        
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        
        self.assertTrue(res["checked"])
        self.assertTrue(res["is_fresh"])
        self.assertEqual(res["fresh_competitor_price"], 1687000)
        self.assertEqual(res["fresh_recommended_price"], 1686000)
        self.assertEqual(res["price_source"], "fresh_market_book_location")
        self.assertEqual(res["market_scope"], "station_location")
        self.assertEqual(res["regional_orders_count"], 3)
        self.assertEqual(res["location_orders_count"], 2)

    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_no_location_id_blocks(self, mock_esi_class):
        """REQ 10.4: Missing location_id blocks revalidation."""
        from ui.market_command.my_orders_view import MarketMyOrdersView
        view = MagicMock(); view.all_orders = []
        order = OpenOrder(
            order_id=1, type_id=123, item_name="No Loc", is_buy_order=False, price=1000.0,
            volume_total=1, volume_remain=1, issued="", location_id=None, range="",
            analysis=None
        )
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        self.assertTrue(res["checked"])
        self.assertFalse(res["is_fresh"])
        self.assertIn("No order location_id available", "".join(res["warnings"]))

    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_no_competitor_local(self, mock_esi_class):
        """REQ 10.3: Competitor in other station but none in local station."""
        mock_esi = mock_esi_class.return_value
        mock_esi.get_market_orders_for_type.return_value = [
            {"is_buy_order": False, "price": 500.0, "location_id": 999}, # Other location
            {"is_buy_order": False, "price": 1000.0, "location_id": 1}, # My local order
        ]
        from ui.market_command.my_orders_view import MarketMyOrdersView
        view = MagicMock(); view.all_orders = []
        order = OpenOrder(
            order_id=1, type_id=123, item_name="Test Item", is_buy_order=False, price=1000.0,
            volume_total=1, volume_remain=1, issued="", location_id=1, range="",
            analysis=None
        )
        view.all_orders = [order]
        
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        
        self.assertTrue(res["checked"])
        self.assertFalse(res["is_fresh"])
        self.assertIn("No reliable local competitor found", "".join(res["warnings"]))

    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_sentinel_sell(self, mock_esi_class):
        """REQ 4.3: Recalculate returns sentinel MAX (SELL)."""
        mock_esi = mock_esi_class.return_value
        # Empty market or logic error results in sentinel
        mock_esi.get_market_orders_for_type.return_value = []
        from ui.market_command.my_orders_view import MarketMyOrdersView
        view = MagicMock(); view.all_orders = []
        order = MagicMock(); order.type_id=123; order.is_buy_order=False; order.analysis.competitor_price=100.0
        
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        
        self.assertFalse(res["is_fresh"])
        self.assertIn("No reliable local competitor found", "".join(res["warnings"]))

    @patch('ui.market_command.my_orders_view.ESIClient')
    def test_revalidate_market_competitor_sentinel_buy(self, mock_esi_class):
        """REQ 4.4: Recalculate returns sentinel MIN (BUY)."""
        mock_esi = mock_esi_class.return_value
        mock_esi.get_market_orders_for_type.return_value = []
        from ui.market_command.my_orders_view import MarketMyOrdersView
        view = MagicMock(); view.all_orders = []
        order = MagicMock(); order.type_id=123; order.is_buy_order=True; order.analysis.competitor_price=100.0
        
        res = MarketMyOrdersView._revalidate_market_competitor(view, order)
        
        self.assertFalse(res["is_fresh"])
        self.assertIn("No reliable local competitor found", "".join(res["warnings"]))

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
        self.assertIn("Error revalidando mercado local: ESI Down", res["warnings"])

if __name__ == "__main__":
    unittest.main()
