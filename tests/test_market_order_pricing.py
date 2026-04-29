"""Tests for core/market_order_pricing.py"""
import sys
import os
import unittest
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.market_order_pricing import (
    price_tick,
    recommend_sell_price,
    recommend_buy_price,
    build_order_update_recommendation,
)


# ---------------------------------------------------------------------------
# Minimal stubs that mirror OpenOrder / OpenOrderAnalysis fields used by pricing
# ---------------------------------------------------------------------------

@dataclass
class FakeAnalysis:
    competitor_price: float = 0.0
    best_buy: float = 0.0
    best_sell: float = 0.0
    competitive: bool = False
    state: str = "Superada"


@dataclass
class FakeOrder:
    order_id: int = 1
    type_id: int = 34
    item_name: str = "Tritanium"
    is_buy_order: bool = False
    price: float = 5.00
    volume_total: int = 1000
    volume_remain: int = 500
    location_id: int = 60003760
    analysis: Optional[FakeAnalysis] = None


# ---------------------------------------------------------------------------
# price_tick tests
# ---------------------------------------------------------------------------

class TestPriceTick(unittest.TestCase):

    def test_below_100(self):
        self.assertAlmostEqual(price_tick(50.0), 0.01)

    def test_at_100(self):
        # price == 100 → bracket is "< 1000" → tick 0.1
        self.assertAlmostEqual(price_tick(100.0), 0.1)

    def test_below_1k(self):
        self.assertAlmostEqual(price_tick(999.99), 0.1)

    def test_at_1k(self):
        self.assertAlmostEqual(price_tick(1_000.0), 1.0)

    def test_below_10k(self):
        self.assertAlmostEqual(price_tick(9_999.0), 1.0)

    def test_at_10k(self):
        self.assertAlmostEqual(price_tick(10_000.0), 10.0)

    def test_below_100k(self):
        self.assertAlmostEqual(price_tick(50_000.0), 10.0)

    def test_at_100k(self):
        self.assertAlmostEqual(price_tick(100_000.0), 100.0)

    def test_below_1m(self):
        self.assertAlmostEqual(price_tick(500_000.0), 100.0)

    def test_at_1m(self):
        self.assertAlmostEqual(price_tick(1_000_000.0), 1_000.0)

    def test_below_10m(self):
        self.assertAlmostEqual(price_tick(5_000_000.0), 1_000.0)

    def test_at_10m(self):
        self.assertAlmostEqual(price_tick(10_000_000.0), 10_000.0)

    def test_below_100m(self):
        self.assertAlmostEqual(price_tick(50_000_000.0), 10_000.0)

    def test_at_100m(self):
        self.assertAlmostEqual(price_tick(100_000_000.0), 100_000.0)

    def test_very_large(self):
        self.assertAlmostEqual(price_tick(1_000_000_000.0), 100_000.0)


# ---------------------------------------------------------------------------
# recommend_sell_price tests
# ---------------------------------------------------------------------------

class TestRecommendSellPrice(unittest.TestCase):

    def test_undercut_one_tick(self):
        # competitor at 1000 ISK → tick 1.0 → recommend 999.0
        self.assertAlmostEqual(recommend_sell_price(1_000.0), 999.0)

    def test_undercut_cheap_item(self):
        # competitor at 50 ISK → tick 0.01 → recommend 49.99
        self.assertAlmostEqual(recommend_sell_price(50.0), 49.99)

    def test_floor_at_0_01(self):
        # competitor at 0.01 → tick 0.01 → would be 0.00 → floor at 0.01
        self.assertAlmostEqual(recommend_sell_price(0.01), 0.01)

    def test_expensive_item(self):
        # competitor at 500M → tick 100_000 → recommend 499_900_000
        self.assertAlmostEqual(recommend_sell_price(500_000_000.0), 499_900_000.0)


# ---------------------------------------------------------------------------
# recommend_buy_price tests
# ---------------------------------------------------------------------------

class TestRecommendBuyPrice(unittest.TestCase):

    def test_outbid_one_tick(self):
        # competitor at 1000 → tick 1 → recommend 1001
        self.assertAlmostEqual(recommend_buy_price(1_000.0), 1_001.0)

    def test_outbid_cheap_item(self):
        # competitor at 50 → tick 0.01 → recommend 50.01
        self.assertAlmostEqual(recommend_buy_price(50.0), 50.01)

    def test_outbid_expensive(self):
        # competitor at 10M → tick 10_000 → recommend 10_010_000
        self.assertAlmostEqual(recommend_buy_price(10_000_000.0), 10_010_000.0)


# ---------------------------------------------------------------------------
# build_order_update_recommendation tests
# ---------------------------------------------------------------------------

class TestBuildOrderUpdateRecommendation(unittest.TestCase):

    def _sell_order(self, my_price=1_000.0, competitor_price=950.0, competitive=False):
        order = FakeOrder(is_buy_order=False, price=my_price)
        analysis = FakeAnalysis(
            competitor_price=competitor_price,
            best_sell=competitor_price,
            competitive=competitive,
        )
        return order, analysis

    def _buy_order(self, my_price=900.0, competitor_price=910.0, competitive=False):
        order = FakeOrder(is_buy_order=True, price=my_price)
        analysis = FakeAnalysis(
            competitor_price=competitor_price,
            best_buy=competitor_price,
            competitive=competitive,
        )
        return order, analysis

    # -- side field ----------------------------------------------------------

    def test_side_sell(self):
        order, analysis = self._sell_order()
        rec = build_order_update_recommendation(order, analysis)
        self.assertEqual(rec["side"], "SELL")

    def test_side_buy(self):
        order, analysis = self._buy_order()
        rec = build_order_update_recommendation(order, analysis)
        self.assertEqual(rec["side"], "BUY")

    # -- action_needed -------------------------------------------------------

    def test_sell_action_needed_when_not_competitive(self):
        order, analysis = self._sell_order(competitive=False)
        rec = build_order_update_recommendation(order, analysis)
        self.assertTrue(rec["action_needed"])

    def test_sell_no_action_when_already_competitive(self):
        order, analysis = self._sell_order(competitive=True)
        rec = build_order_update_recommendation(order, analysis)
        self.assertFalse(rec["action_needed"])

    def test_buy_action_needed_when_not_competitive(self):
        order, analysis = self._buy_order(competitive=False)
        rec = build_order_update_recommendation(order, analysis)
        self.assertTrue(rec["action_needed"])

    def test_buy_no_action_when_already_competitive(self):
        order, analysis = self._buy_order(competitive=True)
        rec = build_order_update_recommendation(order, analysis)
        self.assertFalse(rec["action_needed"])

    # -- recommended_price correctness ---------------------------------------

    def test_sell_recommended_price_is_undercut(self):
        # competitor at 1000 → recommend 999
        order, analysis = self._sell_order(competitor_price=1_000.0)
        rec = build_order_update_recommendation(order, analysis)
        self.assertAlmostEqual(rec["recommended_price"], 999.0)

    def test_buy_recommended_price_is_outbid(self):
        # competitor at 1000 → recommend 1001
        order, analysis = self._buy_order(competitor_price=1_000.0)
        rec = build_order_update_recommendation(order, analysis)
        self.assertAlmostEqual(rec["recommended_price"], 1_001.0)

    # -- no competitor -------------------------------------------------------

    def test_no_competitor_zero(self):
        order = FakeOrder(is_buy_order=False, price=500.0)
        analysis = FakeAnalysis(competitor_price=0.0)
        rec = build_order_update_recommendation(order, analysis)
        self.assertFalse(rec["action_needed"])
        self.assertAlmostEqual(rec["recommended_price"], 500.0)

    def test_no_competitor_sentinel(self):
        # ESI sentinel value meaning "no orders"
        sentinel = 9_000_000_000_000.0
        order = FakeOrder(is_buy_order=True, price=200.0)
        analysis = FakeAnalysis(competitor_price=sentinel)
        rec = build_order_update_recommendation(order, analysis)
        self.assertFalse(rec["action_needed"])

    # -- dict keys present ---------------------------------------------------

    def test_all_keys_present(self):
        order, analysis = self._sell_order()
        rec = build_order_update_recommendation(order, analysis)
        expected_keys = {
            "side", "my_price", "competitor_price", "best_buy", "best_sell",
            "tick", "recommended_price", "reason", "action_needed",
        }
        self.assertEqual(set(rec.keys()), expected_keys)


# ---------------------------------------------------------------------------
# format_quick_update_report smoke test
# ---------------------------------------------------------------------------

class TestFormatQuickUpdateReport(unittest.TestCase):

    def test_sections_present(self):
        from core.quick_order_update_diagnostics import format_quick_update_report
        data = {
            "order_id": 123,
            "type_id": 34,
            "item_name": "Tritanium",
            "side": "SELL",
            "my_price": 5.0,
            "competitor_price": 4.99,
            "recommended_price": 4.98,
            "reason": "Bajar un tick",
            "action_needed": True,
        }
        report = format_quick_update_report(data)
        for section in ("[ORDER]", "[MARKET]", "[RECOMMENDATION]", "[ACTIONS]",
                        "[CONFIG]", "[ERRORS]", "[NOTES]"):
            self.assertIn(section, report)

    def test_empty_dict_no_crash(self):
        from core.quick_order_update_diagnostics import format_quick_update_report
        report = format_quick_update_report({})
        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 0)


if __name__ == "__main__":
    unittest.main()
