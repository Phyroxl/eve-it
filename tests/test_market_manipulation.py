"""Tests for core/market_manipulation_detector.py"""
import unittest
from core.market_manipulation_detector import (
    detect_sell_manipulation,
    detect_buy_manipulation,
    get_safe_competitor_price,
)


def _sell_order(price, qty=100):
    return {"price": price, "volume_remain": qty, "is_buy_order": False}


def _buy_order(price, qty=100):
    return {"price": price, "volume_remain": qty, "is_buy_order": True}


class TestSELLManipulation(unittest.TestCase):

    def test_normal_sell_not_flagged(self):
        """Normal sell with 20% spread above best_buy is not flagged."""
        res = detect_sell_manipulation(best_sell=1_200_000.0, best_buy=1_000_000.0)
        self.assertFalse(res.manipulation_detected)
        self.assertFalse(res.blocked_auto_update)

    def test_sell_near_buy_flagged(self):
        """best_sell only 1% above best_buy — cue order, should be flagged."""
        res = detect_sell_manipulation(best_sell=1_010_000.0, best_buy=1_000_000.0)
        self.assertTrue(res.manipulation_detected)
        self.assertTrue(res.blocked_auto_update)
        self.assertEqual(res.manipulation_side, "SELL")
        self.assertIsNotNone(res.manipulation_reason)

    def test_sell_manipulation_safe_price_from_orderbook(self):
        """When manipulation is detected, safe_competitor_price uses next valid sell."""
        orders = [
            _sell_order(1_001_000.0),   # manipulated (too close to buy)
            _sell_order(1_120_000.0),   # valid (>5% above buy)
        ]
        res = detect_sell_manipulation(
            best_sell=1_001_000.0,
            best_buy=1_000_000.0,
            sell_orders=orders,
        )
        self.assertTrue(res.manipulation_detected)
        self.assertAlmostEqual(res.safe_competitor_price, 1_120_000.0)
        self.assertFalse(res.blocked_auto_update)

    def test_sell_manipulation_no_valid_fallback_blocks(self):
        """If no valid price exists in order book, update is blocked."""
        orders = [_sell_order(1_001_000.0)]
        res = detect_sell_manipulation(
            best_sell=1_001_000.0,
            best_buy=1_000_000.0,
            sell_orders=orders,
        )
        self.assertTrue(res.manipulation_detected)
        self.assertTrue(res.blocked_auto_update)

    def test_zero_prices_not_flagged(self):
        """Missing prices (0) should not trigger manipulation."""
        res = detect_sell_manipulation(best_sell=0.0, best_buy=0.0)
        self.assertFalse(res.manipulation_detected)


class TestBUYManipulation(unittest.TestCase):

    def test_normal_buy_not_flagged(self):
        """Best buy only 20% above next buy — not manipulation."""
        orders = [_buy_order(1_200_000.0), _buy_order(1_000_000.0)]
        res = detect_buy_manipulation(
            best_buy=1_200_000.0,
            buy_orders=orders,
        )
        self.assertFalse(res.manipulation_detected)

    def test_buy_jump_50pct_flagged(self):
        """best_buy >= next_buy * 1.5 — manipulation detected."""
        orders = [_buy_order(1_500_000.0), _buy_order(1_000_000.0)]
        res = detect_buy_manipulation(
            best_buy=1_500_000.0,
            buy_orders=orders,
        )
        self.assertTrue(res.manipulation_detected)
        self.assertTrue(res.blocked_auto_update)
        self.assertEqual(res.manipulation_side, "BUY")

    def test_buy_manipulation_allowed_if_profit_ok(self):
        """Manipulation detected but profit >= 20% — update allowed with warning."""
        orders = [_buy_order(1_500_000.0), _buy_order(1_000_000.0)]
        res = detect_buy_manipulation(
            best_buy=1_500_000.0,
            buy_orders=orders,
            estimated_profit_margin=25.0,
        )
        self.assertTrue(res.manipulation_detected)
        self.assertFalse(res.blocked_auto_update)
        self.assertEqual(res.warning_level, "medium")

    def test_buy_manipulation_blocked_low_margin(self):
        """Manipulation detected and margin < 20% — update blocked."""
        orders = [_buy_order(1_500_000.0), _buy_order(1_000_000.0)]
        res = detect_buy_manipulation(
            best_buy=1_500_000.0,
            buy_orders=orders,
            estimated_profit_margin=10.0,
        )
        self.assertTrue(res.manipulation_detected)
        self.assertTrue(res.blocked_auto_update)
        self.assertEqual(res.warning_level, "high")

    def test_single_buy_order_not_flagged(self):
        """With only one buy level, cannot determine jump — not flagged."""
        orders = [_buy_order(1_500_000.0)]
        res = detect_buy_manipulation(best_buy=1_500_000.0, buy_orders=orders)
        self.assertFalse(res.manipulation_detected)

    def test_no_orders_not_flagged(self):
        res = detect_buy_manipulation(best_buy=1_500_000.0, buy_orders=None)
        self.assertFalse(res.manipulation_detected)


class TestContractsBlueprintFilter(unittest.TestCase):
    """Verify blueprint detection helpers used in contracts_engine."""

    def test_blueprint_name_detected(self):
        from core.contracts_engine import _is_blueprint_name
        self.assertTrue(_is_blueprint_name("Myrmidon Blueprint"))
        self.assertTrue(_is_blueprint_name("Rifter Blueprint"))

    def test_bpc_name_detected(self):
        from core.contracts_engine import _is_blueprint_copy_name, _is_blueprint_name
        self.assertTrue(_is_blueprint_name("Myrmidon Blueprint Copy"))
        self.assertTrue(_is_blueprint_copy_name("Myrmidon Blueprint Copy"))

    def test_normal_item_not_blueprint(self):
        from core.contracts_engine import _is_blueprint_name, _is_blueprint_copy_name
        self.assertFalse(_is_blueprint_name("Tritanium"))
        self.assertFalse(_is_blueprint_copy_name("Tritanium"))
        self.assertFalse(_is_blueprint_name("Myrmidon"))

    def test_bpc_keyword_detected(self):
        from core.contracts_engine import _is_blueprint_copy_name
        self.assertTrue(_is_blueprint_copy_name("Drake BPC"))

    def test_filter_removes_blueprint_contract(self):
        from core.contracts_engine import apply_contracts_filters
        from core.contracts_models import ContractArbitrageResult, ContractsFilterConfig

        # profit_min_isk=0 and roi_min_pct=0 so the only active filter is exclude_blueprints
        cfg = ContractsFilterConfig(exclude_blueprints=True, profit_min_isk=0.0, roi_min_pct=0.0)

        def _make_contract(cid, has_bp):
            return ContractArbitrageResult(
                contract_id=cid, region_id=10000002, issuer_id=1,
                contract_cost=1_000_000.0, date_expired="2099-01-01T00:00:00Z",
                location_id=60003760, item_type_count=1, total_units=1,
                items=[], jita_sell_value=2_000_000.0, jita_buy_value=1_800_000.0,
                gross_profit=1_000_000.0, net_profit=15_000_000.0, roi_pct=90.0,
                value_concentration=0.5, has_unresolved_items=False, unresolved_count=0,
                has_blueprints=has_bp, score=100.0,
            )

        filtered = apply_contracts_filters([_make_contract(1, True), _make_contract(2, False)], cfg)
        ids = [c.contract_id for c in filtered]
        self.assertNotIn(1, ids, "Blueprint contract must be filtered out")
        self.assertIn(2, ids, "Normal contract must remain")


class TestGetSafeCompetitorPrice(unittest.TestCase):

    def test_sell_safe_price_skips_cue(self):
        orders = [_sell_order(1_001_000.0), _sell_order(1_120_000.0)]
        price = get_safe_competitor_price(orders, "SELL", best_buy=1_000_000.0)
        self.assertAlmostEqual(price, 1_120_000.0)

    def test_buy_returns_best(self):
        orders = [_buy_order(1_200_000.0), _buy_order(1_000_000.0)]
        price = get_safe_competitor_price(orders, "BUY")
        self.assertAlmostEqual(price, 1_200_000.0)


if __name__ == "__main__":
    unittest.main()
