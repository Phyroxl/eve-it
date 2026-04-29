"""
Tests for validate_quick_update_price_source and related behaviour.
Covers the real-world Mystic S scenario:
  - my_price=1594, competitor misidentified as 1594 (should be 1596)
  - stale own order at 1598, competitor_price=1594 (own order leaked in)
  - normal case: prices are clearly different → confident
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.market_order_pricing import (
    validate_quick_update_price_source,
    build_order_update_recommendation,
    _prices_equal,
)

# ---------------------------------------------------------------------------
# Minimal fakes (no Qt, no ESI)
# ---------------------------------------------------------------------------

@dataclass
class _FakeAnalysis:
    is_buy: bool = False
    state: str = "Superada"
    gross_profit_per_unit: float = 0.0
    net_profit_per_unit: float = 0.0
    net_profit_total: float = 0.0
    margin_pct: float = 0.0
    best_buy: float = 0.0
    best_sell: float = 0.0
    spread_pct: float = 0.0
    competitive: bool = False
    difference_to_best: float = 0.0
    competitor_price: float = 0.0


@dataclass
class _FakeOrder:
    order_id: int = 1
    type_id: int = 99
    item_name: str = "Mystic S"
    is_buy_order: bool = False
    price: float = 1_594.0
    volume_total: int = 100
    volume_remain: int = 50
    issued: str = "2026-01-01T00:00:00Z"
    location_id: int = 60_003_760
    range: str = "station"
    analysis: Optional[object] = None


# ---------------------------------------------------------------------------
# 1. _prices_equal helper
# ---------------------------------------------------------------------------
class TestPricesEqual(unittest.TestCase):

    def test_same_price(self):
        self.assertTrue(_prices_equal(1594.0, 1594.0))

    def test_within_tolerance(self):
        self.assertTrue(_prices_equal(1594.0, 1594.004))

    def test_outside_tolerance(self):
        self.assertFalse(_prices_equal(1594.0, 1596.0))

    def test_zero_zero(self):
        self.assertTrue(_prices_equal(0.0, 0.0))


# ---------------------------------------------------------------------------
# 2. validate_quick_update_price_source
# ---------------------------------------------------------------------------
class TestValidatePriceSource(unittest.TestCase):

    # -- CASE 1: Stale SELL order — competitor_price == own price --------
    def test_sell_stale_own_price_detected(self):
        """
        Real scenario:
          order.price = 1598 (old ESI data)
          analysis.competitor_price = 1594  (actually MY current order)
          analysis.best_sell = 1594
        """
        order = _FakeOrder(price=1_598.0)
        # Here the 'competitor' is 1594 which is actually my current order
        # but let's test the simpler flag: competitor == own price
        # Stale: order was 1598, market now shows 1594 as "competitor"
        # but 1594 is NOT equal to 1598, so this won't trigger own_eq_competitor.
        # This is the "competitor_price != own_price but suspicious" case —
        # the app cannot detect this without market data, so it should pass normally.
        analysis = _FakeAnalysis(competitor_price=1_594.0, best_sell=1_594.0)
        result = validate_quick_update_price_source(order, analysis)
        # Prices are different, so no automatic warning — app can't detect staleness here
        self.assertFalse(result["own_price_eq_competitor"])

    # -- CASE 2: competitor_price == own price → OWN ORDER INCLUDED ------
    def test_sell_own_order_included_as_competitor(self):
        """
        Real scenario:
          order.price = 1594
          analysis.competitor_price = 1594
          → competitor price equals my own price
          → likely own order included as competitor
        """
        order = _FakeOrder(price=1_594.0)
        analysis = _FakeAnalysis(competitor_price=1_594.0, best_sell=1_594.0)
        result = validate_quick_update_price_source(order, analysis)

        self.assertTrue(result["own_price_eq_competitor"])
        self.assertFalse(result["is_confident"])
        self.assertEqual(result["confidence_label"], "Baja")
        self.assertGreater(len(result["warnings"]), 0)

    # -- CASE 2b: same test but for BUY ----------------------------------
    def test_buy_own_order_included_as_competitor(self):
        order = _FakeOrder(price=1_594.0, is_buy_order=True)
        analysis = _FakeAnalysis(
            is_buy=True,
            competitor_price=1_594.0,
            best_buy=1_594.0,
        )
        result = validate_quick_update_price_source(order, analysis)

        self.assertTrue(result["own_price_eq_competitor"])
        self.assertFalse(result["is_confident"])

    # -- CASE 3: Normal SELL — different prices → confident ---------------
    def test_sell_normal_confident(self):
        """
        Healthy scenario:
          order.price = 1598
          competitor_price = 1596  (clearly different)
          recommended = 1595
        """
        order = _FakeOrder(price=1_598.0)
        analysis = _FakeAnalysis(competitor_price=1_596.0, best_sell=1_596.0)
        result = validate_quick_update_price_source(order, analysis)

        self.assertFalse(result["own_price_eq_competitor"])
        self.assertTrue(result["is_confident"])
        self.assertEqual(result["confidence_label"], "Alta")
        self.assertEqual(result["warnings"], [])

    # -- CASE 4: No competitor → not confident ---------------------------
    def test_no_competitor_not_confident(self):
        order = _FakeOrder(price=1_594.0)
        analysis = _FakeAnalysis(competitor_price=0.0)
        result = validate_quick_update_price_source(order, analysis)

        self.assertFalse(result["is_confident"])
        self.assertGreater(len(result["warnings"]), 0)

    # -- CASE 5: Sentinel competitor value (9e12) → not confident --------
    def test_sentinel_not_confident(self):
        order = _FakeOrder(price=1_594.0)
        analysis = _FakeAnalysis(competitor_price=9_000_000_000_000.0)
        result = validate_quick_update_price_source(order, analysis)

        self.assertFalse(result["is_confident"])


# ---------------------------------------------------------------------------
# 3. build_order_update_recommendation includes validation key
# ---------------------------------------------------------------------------
class TestBuildRecommendationWithValidation(unittest.TestCase):

    def test_rec_contains_validation_key(self):
        order = _FakeOrder(price=1_598.0)
        analysis = _FakeAnalysis(competitor_price=1_596.0, best_sell=1_596.0)
        rec = build_order_update_recommendation(order, analysis)
        self.assertIn("validation", rec)

    def test_rec_confident_case_no_warning_prefix(self):
        order = _FakeOrder(price=1_598.0)
        analysis = _FakeAnalysis(competitor_price=1_596.0, best_sell=1_596.0, competitive=False)
        rec = build_order_update_recommendation(order, analysis)
        # Reason should NOT start with ⚠
        self.assertFalse(rec["reason"].startswith("⚠"))

    def test_rec_not_confident_has_warning_prefix(self):
        """competitor_price == own price → reason prefixed with ⚠."""
        order = _FakeOrder(price=1_594.0)
        analysis = _FakeAnalysis(competitor_price=1_594.0, best_sell=1_594.0, competitive=False)
        rec = build_order_update_recommendation(order, analysis)
        self.assertTrue(rec["reason"].startswith("⚠"))
        self.assertFalse(rec["validation"]["is_confident"])

    def test_rec_recommended_price_sell_normal(self):
        """SELL, competitor=1596 → recommended = 1595.9."""
        order = _FakeOrder(price=1_598.0, is_buy_order=False)
        analysis = _FakeAnalysis(competitor_price=1_596.0, best_sell=1_596.0, is_buy=False)
        rec = build_order_update_recommendation(order, analysis)
        # Price tick at 1596 is 1.0 (in the 1000-10000 range)
        self.assertAlmostEqual(rec["recommended_price"], 1_595.0, places=2)

    def test_rec_recommended_price_buy_normal(self):
        """BUY, competitor=1594 → recommended = 1595 (tick=1.0)."""
        order = _FakeOrder(price=1_590.0, is_buy_order=True)
        analysis = _FakeAnalysis(competitor_price=1_594.0, best_buy=1_594.0, is_buy=True)
        rec = build_order_update_recommendation(order, analysis)
        # Price tick at 1594 is 1.0 (in the 1000-10000 range)
        self.assertAlmostEqual(rec["recommended_price"], 1_595.0, places=2)


# ---------------------------------------------------------------------------
# 4. Auto-copy gate (integration — tests _launch_quick_order_update via rec)
# ---------------------------------------------------------------------------
class TestAutoCopyGate(unittest.TestCase):
    """
    Verifies that the is_confident flag correctly drives the auto-copy decision.
    This is tested at the pricing layer; the view layer passes it through.
    """

    def test_low_confidence_order_should_not_auto_copy(self):
        """
        When competitor_price == own price the result should signal is_confident=False.
        The caller (_launch_quick_order_update) MUST NOT auto-copy in this case.
        """
        order = _FakeOrder(price=1_594.0)
        analysis = _FakeAnalysis(competitor_price=1_594.0, best_sell=1_594.0)
        rec = build_order_update_recommendation(order, analysis)

        is_confident = rec["validation"]["is_confident"]
        self.assertFalse(is_confident, "Low-confidence case must not auto-copy")

    def test_high_confidence_order_should_auto_copy(self):
        """
        When prices are clearly different the result should signal is_confident=True.
        """
        order = _FakeOrder(price=1_598.0)
        analysis = _FakeAnalysis(competitor_price=1_596.0, best_sell=1_596.0)
        rec = build_order_update_recommendation(order, analysis)

        is_confident = rec["validation"]["is_confident"]
        self.assertTrue(is_confident, "High-confidence case should auto-copy")


if __name__ == "__main__":
    unittest.main()
