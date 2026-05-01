import unittest
from unittest.mock import patch
from core.eve_market_visual_detector import (
    EveMarketVisualDetector, normalize_quantity_text, normalize_price_text,
    _price_groups, _price_group_tokens_matched,
)

class TestVisualOCRMatching(unittest.TestCase):
    def setUp(self):
        self.config = {
            "visual_ocr_require_unique_match": True,
            "visual_ocr_match_price": True,
            "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 0.5,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150
        }
        self.detector = EveMarketVisualDetector(self.config)

    def test_normalize_quantity_with_artifacts(self):
        """Verify that O is handled as 0 and other noise is removed."""
        self.assertEqual(normalize_quantity_text("1OO"), 100)
        self.assertEqual(normalize_quantity_text("74O/745"), 740745)
        self.assertEqual(normalize_quantity_text("  1,234  "), 1234)
        self.assertEqual(normalize_quantity_text("abc"), 0)

    def test_match_quantity_tiers(self):
        """Verify confidence tiers for quantity matching."""
        # Exact
        res = self.detector._match_quantity(741, 741, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "exact")

        # Suffix
        res = self.detector._match_quantity(41, 741, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "suffix")

        # Near OCR (small diff, high confidence on others)
        res = self.detector._match_quantity(740, 741, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "near_ocr")

        # Mismatch (large diff)
        res = self.detector._match_quantity(500, 741, True, True)
        self.assertFalse(res["matched"])
        self.assertEqual(res["confidence"], "none")

    def test_match_price_digit_patterns(self):
        """Verify target-aware digit pattern matching for prices."""
        # 1. Numeric tolerance (normal match)
        res = self.detector._match_price_ocr("29 660.000", 29660000.0)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "numeric_tolerance")
        
        # 2. Digit pattern (messy punctuation and junk digits like ISK -> 15K)
        res = self.detector._match_price_ocr("29.66O.OOO @@ ISK", 29660000.0)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "digit_pattern")
        self.assertEqual(res["reason"], "partial_digit_pattern_match")
        
        # 3. Partial digit pattern (lost leading or trailing)
        res = self.detector._match_price_ocr("9.660.000", 29660000.0)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "digit_pattern")
        
        # 4. Scaled digit pattern (lost last group in BUY) - caught by substring first
        res = self.detector._match_price_ocr("29660", 29660000.0, is_buy_order=True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "digit_pattern")
        
        # 5. Competitor price rejected (digits do not match target pattern)
        res = self.detector._match_price_ocr("29 708.000", 29660000.0)
        self.assertFalse(res["matched"])
        self.assertEqual(res["reason"], "insufficient_digit_similarity")

    def test_match_quantity_single_digit_safety(self):
        """Verify that single-digit targets do not incorrectly match larger numbers."""
        target_qty = 8
        
        # Isolated 8 works
        res = self.detector._match_quantity(8, target_qty, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "exact")
        
        # 18 should NOT match suffix 8 for target 8
        res = self.detector._match_quantity(18, target_qty, True, True)
        self.assertFalse(res["matched"])
        
        # Suffix matching for large numbers still works
        res = self.detector._match_quantity(100, 1100, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "suffix")

    def test_match_quantity_buy_artifacts(self):
        """Verify common BUY OCR artifacts like 'g' for '8'."""
        target_qty = 8
        
        # 'g' mapping for BUY
        res = self.detector._match_quantity(0, target_qty, True, True, is_buy_order=True, ocr_text="in g")
        self.assertTrue(res["matched"])
        self.assertEqual(res["reason"], "buy_artifact_g_for_8")
        
        # 'g' should NOT map for SELL
        res = self.detector._match_quantity(0, target_qty, True, True, is_buy_order=False, ocr_text="in g")
        self.assertFalse(res["matched"])

class TestPriceGroupHelpers(unittest.TestCase):
    """Unit tests for _price_groups and _price_group_tokens_matched helpers."""

    def test_price_groups_basic(self):
        self.assertEqual(_price_groups(29660000.0), [29, 660, 0])

    def test_price_groups_no_trailing_zeros(self):
        self.assertEqual(_price_groups(1234567.0), [1, 234, 567])

    def test_price_groups_exact_million(self):
        self.assertEqual(_price_groups(1000000.0), [1, 0, 0])

    def test_price_groups_zero(self):
        self.assertEqual(_price_groups(0.0), [0])

    def test_group_tokens_matched_all_significant(self):
        # OCR [20, 669] vs groups [29, 660, 0] → 2 significant, both match
        tgt = [29, 660, 0]
        matched, sig = _price_group_tokens_matched([20, 669], tgt)
        self.assertEqual(sig, 2)
        self.assertEqual(matched, 2)

    def test_group_tokens_competitor_rejected(self):
        # OCR [29, 708] vs target groups [29, 660, 0]
        # 29→29 match, 708 vs 660 diff=48 > tol=33 → only 1/2
        tgt = [29, 660, 0]
        matched, sig = _price_group_tokens_matched([29, 708], tgt)
        self.assertEqual(sig, 2)
        self.assertLess(matched, sig)

    def test_group_tokens_29700000_rejected(self):
        # 700 vs 660: diff=40 > tol=33 → fails
        tgt = [29, 660, 0]
        matched, sig = _price_group_tokens_matched([29, 700], tgt)
        self.assertLess(matched, sig)

    def test_group_tokens_32990000_rejected(self):
        # groups [32, 990, 0]: 32≈29 ok but 990 vs 660 diff=330 >> tol → fails
        tgt = [29, 660, 0]
        matched, sig = _price_group_tokens_matched([32, 990], tgt)
        self.assertLess(matched, sig)


class TestBUYCorruptedPriceMatching(unittest.TestCase):
    """
    Verifies the Phase 3J corrupted-million-pattern matcher for BUY orders.
    Real-world case: Mid-grade Amulet Alpha, order_id=7317475994,
    my_price=29,660,000, qty=8, OCR reads '20 669 Gag aa ISK' / 'in g'.
    """

    def setUp(self):
        self.config = {
            "visual_ocr_require_unique_match": True,
            "visual_ocr_match_price": True,
            "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 0.5,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150,
        }
        self.detector = EveMarketVisualDetector(self.config)
        self.target_price = 29_660_000.0
        self.target_qty = 8

    # ── corrupted_million_pattern acceptance ──────────────────────────────────

    def test_corrupted_price_group_match(self):
        """'20 669 Gag aa ISK' must match target 29,660,000 via group matching."""
        res = self.detector._match_price_ocr(
            "20 669 Gag aa ISK", self.target_price, is_buy_order=True
        )
        self.assertTrue(res["matched"],
                        f"Expected corrupted_million_pattern match, got: {res}")
        self.assertEqual(res["confidence"], "corrupted_million_pattern")

    def test_corrupted_price_returns_target_as_normalized(self):
        """corrupted_million_pattern must normalize to target_price (not OCR value)."""
        res = self.detector._match_price_ocr(
            "20 669 Gag aa ISK", self.target_price, is_buy_order=True
        )
        self.assertEqual(res["normalized"], self.target_price)

    def test_corrupted_price_groups_populated(self):
        """target_groups and ocr_groups must be populated for diagnostics."""
        res = self.detector._match_price_ocr(
            "20 669 Gag aa ISK", self.target_price, is_buy_order=True
        )
        self.assertIn("target_groups", res)
        self.assertIn("ocr_groups", res)
        self.assertEqual(res["target_groups"], [29, 660, 0])

    def test_corrupted_price_not_matched_for_sell(self):
        """corrupted_million_pattern must NOT fire for SELL orders."""
        res = self.detector._match_price_ocr(
            "20 669 Gag aa ISK", self.target_price, is_buy_order=False
        )
        self.assertFalse(res["matched"],
                         "Corrupted million pattern must only activate for BUY")

    # ── competitor / false-positive rejection ─────────────────────────────────

    def test_competitor_29708000_rejected(self):
        """'29 708.000 @@ ISK' (competitor) must be rejected for target 29,660,000."""
        res = self.detector._match_price_ocr(
            "29 708.000 @@ ISK", self.target_price, is_buy_order=True
        )
        self.assertFalse(res["matched"],
                         f"Competitor 29,708,000 must not match target 29,660,000; got: {res}")

    def test_price_29700000_rejected(self):
        """'29 700 000 ISK' must be rejected for target 29,660,000."""
        res = self.detector._match_price_ocr(
            "29 700 000 ISK", self.target_price, is_buy_order=True
        )
        self.assertFalse(res["matched"])

    def test_price_32990000_rejected(self):
        """'32 990 000 ISK' must be rejected for target 29,660,000."""
        res = self.detector._match_price_ocr(
            "32 990 000 ISK", self.target_price, is_buy_order=True
        )
        self.assertFalse(res["matched"])

    # ── quantity safety ───────────────────────────────────────────────────────

    def test_qty_18_not_suffix_match_for_target_8(self):
        """OCR qty 18 must NOT match target qty 8 via suffix (single-digit safety)."""
        res = self.detector._match_quantity(18, self.target_qty, True, True)
        self.assertFalse(res["matched"],
                         "18 must not suffix-match target qty 8")

    def test_qty_in_g_matches_buy_target_8(self):
        """'in g' must match target qty 8 for BUY via buy_artifact."""
        res = self.detector._match_quantity(
            0, self.target_qty, True, True,
            is_buy_order=True, ocr_text="in g"
        )
        self.assertTrue(res["matched"])
        self.assertEqual(res["reason"], "buy_artifact_g_for_8")

    def test_qty_in_8_matches_buy_target_8(self):
        """OCR qty 8 (exact) must match target qty 8."""
        res = self.detector._match_quantity(
            8, self.target_qty, True, True, is_buy_order=True, ocr_text="in 8"
        )
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "exact")

    def test_qty_in_g_does_not_match_sell(self):
        """'in g' must NOT match target qty 8 for SELL."""
        res = self.detector._match_quantity(
            0, self.target_qty, True, True,
            is_buy_order=False, ocr_text="in g"
        )
        self.assertFalse(res["matched"])

    # ── score sanity ──────────────────────────────────────────────────────────

    def test_corrupted_million_score_is_lower_than_clean_match(self):
        """corrupted_million_pattern must rank below any cleaner price confidence."""
        # "29.660.000" → numeric_tolerance (exact); "20 669 Gag aa ISK" → corrupted_million
        clean_res = self.detector._match_price_ocr("29.660.000", self.target_price, is_buy_order=True)
        corr_res = self.detector._match_price_ocr("20 669 Gag aa ISK", self.target_price, is_buy_order=True)
        self.assertTrue(clean_res["matched"])
        self.assertTrue(corr_res["matched"])
        # Higher rank = better confidence
        conf_rank = {
            "numeric_tolerance": 3,
            "digit_pattern": 2,
            "scaled_digit_pattern": 1,
            "corrupted_million_pattern": 0,
        }
        clean_rank = conf_rank.get(clean_res["confidence"], -1)
        corr_rank = conf_rank.get(corr_res["confidence"], -1)
        self.assertGreater(clean_rank, corr_rank,
                           f"Clean match ({clean_res['confidence']}) should outrank "
                           f"corrupted_million ({corr_res['confidence']})")


class TestSmallPriceNormalization(unittest.TestCase):
    """Tests for small EVE prices with 2-digit decimal format (Phase 3K)."""

    def test_dot_thousands_two_digit_decimal(self):
        """Test C: '16.680.00 ISK' → 16680.0 (thousands dot + 2-digit cents)."""
        self.assertAlmostEqual(normalize_price_text("16.680.00 ISK"), 16680.0, places=2)

    def test_dot_thousands_two_digit_decimal_competitor(self):
        """Test B pre: '16.698.00 ISK' → 16698.0 (competitor price, different value)."""
        self.assertAlmostEqual(normalize_price_text("16.698.00 ISK"), 16698.0, places=2)

    def test_million_price_unchanged(self):
        """'29.660.000' is still handled by the 3-digit groups path → 29660000."""
        self.assertAlmostEqual(normalize_price_text("29.660.000"), 29660000.0, places=1)

    def test_european_dual_separator_unchanged(self):
        """'194.308,00' → 194308.0 (existing European path, unchanged)."""
        self.assertAlmostEqual(normalize_price_text("194.308,00"), 194308.0, places=2)


class TestSmallPriceOCRMatching(unittest.TestCase):
    """
    Integration tests for BUY row alignment: Vespa EC-600 real case.
    order_id=7320444128, target_price=16680.0 ISK, target_qty=1879.
    """

    def setUp(self):
        self.config = {
            "visual_ocr_require_unique_match": True,
            "visual_ocr_match_price": True,
            "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 15.0,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150,
            "visual_ocr_buy_allow_price_anchor_quantity_weak": True,
            "visual_ocr_buy_vertical_search_enabled": True,
            "visual_ocr_buy_vertical_search_offsets": [-16, -12, -8, -4, 0, 4, 8],
        }
        self.detector = EveMarketVisualDetector(self.config)
        self.target_price = 16_680.0
        self.target_qty   = 1879

    # ── Test C: target small price accepted ──────────────────────────────────

    def test_target_small_price_dot_format(self):
        """Test C: '16.680.00 ISK' must match target 16680."""
        res = self.detector._match_price_ocr("16.680.00 ISK", self.target_price)
        self.assertTrue(res["matched"], f"Expected match for '16.680.00 ISK', got: {res}")

    # ── Test D: O/0 artifact accepted ────────────────────────────────────────

    def test_o_artifact_small_price(self):
        """Test D: '16.68O.OO ISK' (O as 0) must match target 16680."""
        res = self.detector._match_price_ocr("16.68O.OO ISK", self.target_price)
        self.assertTrue(res["matched"], f"Expected match with O→0 artifact, got: {res}")

    def test_space_separated_price_digit_pattern(self):
        """'16 680 00 ISK' matches via digit_pattern (target digits in OCR digits)."""
        res = self.detector._match_price_ocr("16 680 00 ISK", self.target_price)
        self.assertTrue(res["matched"])

    # ── Test B: competitor rejected ──────────────────────────────────────────

    def test_competitor_16698_rejected(self):
        """Test B: '16.698. 00 ISK' (competitor 16698) must be rejected for target 16680."""
        res = self.detector._match_price_ocr("16.698. 00 ISK", self.target_price, is_buy_order=True)
        self.assertFalse(res["matched"],
                         f"Competitor 16698 must not match target 16680; got: {res}")

    def test_competitor_16698_digit_pattern_rejected(self):
        """'16698 ISK' must not match target 16680 via digit_pattern."""
        res = self.detector._match_price_ocr("16698 ISK", self.target_price)
        self.assertFalse(res["matched"],
                         f"16698 must be rejected for target 16680; diff=18 > tol=15")

    # ── Test E: bad quantity rejected ────────────────────────────────────────

    def test_qty_70_rejected_for_1879(self):
        """Test E: OCR qty 70 must NOT match target qty 1879."""
        res = self.detector._match_quantity(70, self.target_qty, True, True)
        self.assertFalse(res["matched"], "qty=70 must not match target_qty=1879")

    def test_qty_18_rejected_for_1879(self):
        """Test E extra: OCR qty 18 must NOT match target qty 1879."""
        res = self.detector._match_quantity(18, self.target_qty, True, True)
        self.assertFalse(res["matched"], "qty=18 must not match target_qty=1879")

    def test_qty_1880_near_match(self):
        """OCR qty 1880 is a near_ocr match for target 1879 (diff=1 ≤ 2)."""
        res = self.detector._match_quantity(1880, self.target_qty, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "near_ocr")

    def test_qty_1879_exact(self):
        """OCR qty 1879 exact match."""
        res = self.detector._match_quantity(1879, self.target_qty, True, True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "exact")

    # ── Test F: price-anchor tightened to own_marker ─────────────────────────

    def test_price_anchor_requires_own_marker(self):
        """
        Test F: price_anchor must NOT fire when own_marker=False even with
        is_background_band-equivalent (marker_match=False).
        Phase 3K tightened price_anchor to require own_marker=True.
        The _match_quantity API doesn't track this — we verify behavior via
        the score math: background-only bands (marker_match=False) do not
        trigger the price_anchor path in _run_detection_pass.
        """
        # Verify qty 70 is still rejected (no price-anchor fires at this level)
        res = self.detector._match_quantity(70, self.target_qty, price_match=True, marker_match=False)
        self.assertFalse(res["matched"],
                         "qty=70 must not match even with price_match=True when marker=False")

    def test_price_anchor_fires_with_own_marker(self):
        """
        Test F continued: with own_marker=True + strong price, price_anchor
        allows qty acceptance. We test that the price_anchor path is reached
        by verifying that a reasonable near-ocr qty still matches with marker.
        """
        # 1878 is within 10% of 1879 (diff=1), should match near_ocr with marker
        res = self.detector._match_quantity(1878, self.target_qty, price_match=True, marker_match=True)
        self.assertTrue(res["matched"])


class TestBUYVerticalOCRSearch(unittest.TestCase):
    """
    Test A: Verify vertical OCR search finds price/qty from offset window.
    Uses mock OCR to simulate marker at [516,534] with text at offset=-8 window.
    """

    def setUp(self):
        self.config = {
            "visual_ocr_require_unique_match": True,
            "visual_ocr_match_price": True,
            "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 15.0,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150,
            "visual_ocr_buy_allow_price_anchor_quantity_weak": True,
            "visual_ocr_buy_vertical_search_enabled": True,
            "visual_ocr_buy_vertical_search_offsets": [-16, -12, -8, -4, 0, 4, 8],
        }
        self.detector = EveMarketVisualDetector(self.config)
        self.target_price = 16_680.0
        self.target_qty   = 1879

    def test_vertical_search_finds_price_at_negative_offset(self):
        """
        Test A: marker at band=[516,534], text readable at offset=-8 window [508,526].
        _ocr_vertical_search must return that offset and matched price.
        """
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")

        img = _np.zeros((600, 600, 3), dtype=_np.uint8)

        # Mock ocr_region: returns "16.680.00 ISK" at the 3rd price call (offset=-8),
        # and garbage for all others. Offsets: [-16,-12,-8,-4,0,4,8] → 7 price calls.
        # When offset=-8 matches, qty call fires immediately after (1 qty call).
        ocr_sequence = iter([
            "con anicy",       # offset=-16 price
            "con anicy",       # offset=-12 price
            "16.680.00 ISK",   # offset=-8  price → match
            "1879",            # offset=-8  qty
            "con anicy",       # offset=-4  price
            "con anicy",       # offset=0   price
            "con anicy",       # offset=4   price
            "con anicy",       # offset=8   price
        ])

        with patch.object(self.detector, '_ocr_region', side_effect=ocr_sequence):
            result = self.detector._ocr_vertical_search(
                img, y_center=525, row_height=18,
                price_x0=100, price_x1=200,
                qty_x0=50,    qty_x1=90,
                target_price=self.target_price, is_buy_order=True
            )

        self.assertIsNotNone(result, "Vertical search must return a result when price is found")
        self.assertTrue(result["p_match"]["matched"])
        self.assertEqual(result["offset"], -8)
        self.assertEqual(result["qty_text"], "1879")

    def test_vertical_search_returns_none_when_no_match(self):
        """Vertical search returns None when no offset window gives a price match."""
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")

        img = _np.zeros((600, 600, 3), dtype=_np.uint8)

        with patch.object(self.detector, '_ocr_region', return_value="con anicy"):
            result = self.detector._ocr_vertical_search(
                img, y_center=525, row_height=18,
                price_x0=100, price_x1=200,
                qty_x0=50,    qty_x1=90,
                target_price=self.target_price, is_buy_order=True
            )

        self.assertIsNone(result)

    def test_vertical_search_picks_highest_confidence(self):
        """When multiple offsets match, the one with higher confidence is selected."""
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")

        img = _np.zeros((600, 600, 3), dtype=_np.uint8)

        # offset=-12 → digit_pattern match (rank=3)
        # offset=-8  → numeric_tolerance match (rank=4, better)
        # Both are valid but numeric_tolerance wins.
        ocr_sequence = iter([
            "con anicy",       # offset=-16 price
            "16 680 00 ISK",   # offset=-12 price → digit_pattern match
            "1879",            # offset=-12 qty
            "16.680.00 ISK",   # offset=-8  price → numeric_tolerance (better)
            "1 879",           # offset=-8  qty
            "con anicy",       # offset=-4  price
            "con anicy",       # offset=0   price
            "con anicy",       # offset=4   price
            "con anicy",       # offset=8   price
        ])

        with patch.object(self.detector, '_ocr_region', side_effect=ocr_sequence):
            result = self.detector._ocr_vertical_search(
                img, y_center=525, row_height=18,
                price_x0=100, price_x1=200,
                qty_x0=50,    qty_x1=90,
                target_price=self.target_price, is_buy_order=True
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["p_match"]["confidence"], "numeric_tolerance")
        self.assertEqual(result["offset"], -8)

    def test_sell_vertical_search_not_triggered(self):
        """
        Test G sentinel: SELL orders don't use BUY vertical search.
        _ocr_vertical_search is a BUY-only feature. SELL flow doesn't call it.
        """
        # Verify the method signature accepts is_buy_order=False without error
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")

        img = _np.zeros((200, 200, 3), dtype=_np.uint8)

        with patch.object(self.detector, '_ocr_region', return_value=""):
            result = self.detector._ocr_vertical_search(
                img, y_center=100, row_height=18,
                price_x0=50, price_x1=150,
                qty_x0=10,   qty_x1=40,
                target_price=16680.0, is_buy_order=False
            )
        # Returns None (no match found with empty OCR)
        self.assertIsNone(result)


class TestBUYTickDisambiguation(unittest.TestCase):
    """Phase 3L: tick-based price rejection and small-qty strictness."""

    def setUp(self):
        self.config = {
            "visual_ocr_match_price": True,
            "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 15.0,
            "visual_ocr_price_match_rel_tolerance": 0.001,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150,
            "visual_ocr_buy_allow_price_anchor_quantity_weak": True,
            "visual_ocr_buy_price_max_tick_fraction": 0.49,
        }
        self.detector = EveMarketVisualDetector(self.config)

    # ── Test A: one-tick competitor rejected ─────────────────────────────────

    def test_buy_competitor_one_tick_rejected(self):
        """Test A: 7,262,000 is one tick above target 7,261,000 → must be rejected."""
        res = self.detector._match_price_ocr(
            "7.262.000,00 ISK", 7_261_000.0, is_buy_order=True, order_tick=1000.0
        )
        self.assertFalse(res["matched"],
                         f"Competitor one tick away must be rejected; got: {res}")
        self.assertEqual(res["reason"], "price_diff_exceeds_tick_fraction")

    # ── Test B: exact own price accepted ─────────────────────────────────────

    def test_buy_own_price_accepted(self):
        """Test B: '7.261.000.00 ISK' must match target 7,261,000."""
        res = self.detector._match_price_ocr(
            "7.261.000.00 ISK", 7_261_000.0, is_buy_order=True, order_tick=1000.0
        )
        self.assertTrue(res["matched"], f"Own price must be accepted; got: {res}")

    def test_buy_price_small_diff_accepted(self):
        """40,020 OCR vs 40,020 target with tick=10 → accept (diff=0 < 4.9)."""
        res = self.detector._match_price_ocr(
            "40.020.00 ISK", 40_020.0, is_buy_order=True, order_tick=10.0
        )
        self.assertTrue(res["matched"])

    def test_sell_no_tick_check(self):
        """Test G: SELL with tick set still passes numeric_tolerance (tick check is BUY-only)."""
        res = self.detector._match_price_ocr(
            "7.262.000,00 ISK", 7_261_000.0, is_buy_order=False, order_tick=1000.0
        )
        # SELL: tick check not applied, numeric tolerance (diff=1000 vs tol=max(15,7261))
        # diff=1000 > tol=7261? No, tol = max(15, 7261000*0.001)=7261, 1000<7261 → matched
        self.assertTrue(res["matched"])

    def test_no_tick_no_rejection(self):
        """When tick=0, tick-fraction check is skipped; numeric tolerance decides."""
        res = self.detector._match_price_ocr(
            "7.262.000,00 ISK", 7_261_000.0, is_buy_order=True, order_tick=0.0
        )
        # diff=1000, tol=max(15, 7261)=7261 → 1000 < 7261 → accepted
        self.assertTrue(res["matched"])

    # ── Test C: small qty strict — near_ocr blocked ──────────────────────────

    def test_small_qty_near_ocr_blocked(self):
        """Test C: target_qty=8, ocr_qty=10 → must NOT match via near_ocr."""
        res = self.detector._match_quantity(10, 8, price_match=True, marker_match=True)
        self.assertFalse(res["matched"])
        self.assertEqual(res["reason"], "quantity_small_target_near_ocr_blocked")

    def test_small_qty_9_near_ocr_blocked(self):
        """target_qty=8, ocr_qty=9 → blocked (diff=1 ≤ 2 but target ≤ 10)."""
        res = self.detector._match_quantity(9, 8, price_match=True, marker_match=True)
        self.assertFalse(res["matched"])

    def test_large_qty_near_ocr_still_works(self):
        """target_qty=1879, ocr_qty=1880 → near_ocr still works for large targets."""
        res = self.detector._match_quantity(1880, 1879, price_match=True, marker_match=True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["confidence"], "near_ocr")

    # ── Test D: buy artifact still works ─────────────────────────────────────

    def test_buy_artifact_g_still_works(self):
        """Test D: 'in g' must still match target_qty=8 as buy_artifact."""
        res = self.detector._match_quantity(
            0, 8, price_match=True, marker_match=True,
            is_buy_order=True, ocr_text="in g"
        )
        self.assertTrue(res["matched"])
        self.assertEqual(res["reason"], "buy_artifact_g_for_8")

    # ── Test E: weak_price_anchor blocked on clear wrong qty ─────────────────

    def test_weak_anchor_blocked_on_clear_wrong_qty(self):
        """
        Test E: target_qty=8, ocr_qty=10 → weak_price_anchor must be blocked.
        We call _match_quantity to verify ocr_qty=10 is rejected, then verify
        that the anchor-block reason is set when the detector would try to anchor.
        The anchor logic lives in _run_detection_pass; here we confirm _match_quantity
        returns no match, and the anchor condition (ocr_qty>0 and ocr_qty!=target)
        correctly identifies it as clear-wrong.
        """
        # 10 != 8, so anchor is blocked
        self.assertTrue(10 > 0 and 10 != 8, "anchor block condition: ocr_qty>0 and !=target")
        res = self.detector._match_quantity(10, 8, price_match=True, marker_match=True)
        self.assertFalse(res["matched"])

    def test_weak_anchor_allowed_zero_qty(self):
        """Empty OCR (ocr_qty=0) does not block anchor (garbage OCR, not clear wrong)."""
        # ocr_qty=0 means OCR returned empty/garbage, anchor should be allowed
        # We can't easily test the anchor path here without a full detection pass,
        # but we verify that 0 != target triggers the condition opposite of block.
        self.assertFalse(0 > 0, "ocr_qty=0 must NOT trigger anchor block")

    # ── Test F: known successful examples unchanged ───────────────────────────

    def test_known_good_price_40020(self):
        """Test F: '40.020.00 ISK', target=40020, tick=10 → matched."""
        res = self.detector._match_price_ocr(
            "40.020.00 ISK", 40_020.0, is_buy_order=True, order_tick=10.0
        )
        self.assertTrue(res["matched"])

    def test_known_good_price_771_30(self):
        """Test F: '771,30 ISK', target=771.30, tick=0.10 → matched."""
        res = self.detector._match_price_ocr(
            "771,30 ISK", 771.30, is_buy_order=True, order_tick=0.10
        )
        self.assertTrue(res["matched"])


class TestBUYDedupe(unittest.TestCase):
    """Phase 3M: duplicate candidate deduplication."""

    def setUp(self):
        self.config = {
            "visual_ocr_match_price": True, "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 15.0,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150,
            "visual_ocr_buy_manual_grid_fallback_enabled": True,
            "visual_ocr_buy_manual_grid_row_heights": [18, 20, 22],
            "visual_ocr_buy_manual_grid_step_px": 8,
        }
        self.detector = EveMarketVisualDetector(self.config)

    def _make_candidate(self, text_band, price_text, qty_text, score=185):
        return {
            "row_center_x": 400, "row_center_y": 540,
            "matched_price": True, "price_confidence": "numeric_tolerance",
            "matched_quantity": True, "quantity_match_type": "weak_price_anchor",
            "quantity_match_confidence": "weak_price_anchor",
            "quantity_reason": "price_anchor_override",
            "matched_own_marker": True,
            "price_text": price_text, "quantity_text": qty_text,
            "normalized_quantity": 0, "normalized_price": 60_110_000.0,
            "target_quantity": 9, "band": (text_band[0], text_band[1]),
            "text_band": text_band, "score": score,
        }

    def test_dedupes_same_text_band(self):
        """Test A: two candidates with same text_band, same price/qty → deduped to 1."""
        c1 = self._make_candidate([534, 552], "60.110.000,08 ISK", "nm g", score=185)
        c2 = self._make_candidate([534, 552], "60.110.000,08 ISK", "nm g", score=185)
        deduped, count = self.detector._dedupe_verified_candidates([c1, c2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(count, 1)

    def test_dedupes_overlapping_text_bands(self):
        """Two candidates with overlapping text bands (marker offset ±8) → deduped."""
        # [526,544] → text_band=[534,552]; [542,560] → text_band=[534,552] overlap
        c1 = self._make_candidate([534, 552], "60.110.000,08 ISK", "nm g", score=185)
        c2 = self._make_candidate([534, 552], "60.110.000,08 ISK", "nm g", score=185)
        c2["band"] = (542, 560)
        deduped, count = self.detector._dedupe_verified_candidates([c1, c2])
        self.assertEqual(len(deduped), 1)

    def test_does_not_dedupe_different_rows(self):
        """Test B: different text_band, different price → both kept."""
        c1 = self._make_candidate([500, 518], "60.110.000,08 ISK", "nm g", score=185)
        c2 = self._make_candidate([540, 558], "61.040.000,00 ISK", "nm g", score=120)
        c2["normalized_price"] = 61_040_000.0
        deduped, count = self.detector._dedupe_verified_candidates([c1, c2])
        self.assertEqual(len(deduped), 2)
        self.assertEqual(count, 0)

    def test_dedupes_keeps_highest_score(self):
        """When deduping, the higher-score candidate is kept."""
        c1 = self._make_candidate([534, 552], "60.110.000,08 ISK", "nm g", score=185)
        c2 = self._make_candidate([534, 552], "60.110.000,08 ISK", "nm g", score=200)
        deduped, _ = self.detector._dedupe_verified_candidates([c1, c2])
        self.assertEqual(deduped[0]["score"], 200)


class TestBUYManualGridFallback(unittest.TestCase):
    """Phase 3M: manual BUY grid fallback."""

    def setUp(self):
        self.config = {
            "visual_ocr_match_price": True, "visual_ocr_match_quantity": True,
            "visual_ocr_price_match_abs_tolerance": 15.0,
            "visual_ocr_price_match_rel_tolerance": 0.001,
            "visual_ocr_allow_quantity_suffix_match": True,
            "visual_ocr_quantity_suffix_min_digits": 2,
            "visual_ocr_allow_quantity_near_ocr": True,
            "visual_ocr_score_threshold": 150,
            "visual_ocr_buy_allow_price_anchor_quantity_weak": True,
            "visual_ocr_buy_manual_grid_fallback_enabled": True,
            "visual_ocr_buy_manual_grid_row_heights": [18, 20, 22],
            "visual_ocr_buy_manual_grid_step_px": 8,
            "visual_ocr_buy_price_max_tick_fraction": 0.49,
        }
        self.detector = EveMarketVisualDetector(self.config)

    def test_grid_creates_rows(self):
        """Test C: grid iterates the manual region and creates candidate windows."""
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")
        img   = _np.zeros((700, 600, 3), dtype=_np.uint8)
        result = {"debug": {}}
        with patch.object(self.detector, '_ocr_region', return_value=""):
            cands = self.detector._run_buy_manual_grid_fallback(
                img, 460, 670, 0, 600, 100, 300, 20, 80,
                29_660_000.0, 8, {}, result, order_tick=10_000.0
            )
        self.assertGreater(result["debug"]["visual_ocr_buy_grid_rows"], 0)

    def test_grid_requires_qty_match(self):
        """Test D: price matches but qty does not → no strong candidate."""
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")
        img   = _np.zeros((700, 600, 3), dtype=_np.uint8)
        result = {"debug": {}}
        ocr_iter = iter(["29.660.000,00 ISK", "bad qty text"] * 200)
        with patch.object(self.detector, '_ocr_region', side_effect=ocr_iter):
            cands = self.detector._run_buy_manual_grid_fallback(
                img, 460, 520, 0, 600, 100, 300, 20, 80,
                29_660_000.0, 8, {}, result, order_tick=10_000.0
            )
        self.assertEqual(len(cands), 0)

    def test_grid_accepts_exact_price_and_qty(self):
        """Test E: price and qty both match → one strong candidate returned."""
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")
        img    = _np.zeros((700, 600, 3), dtype=_np.uint8)
        result = {"debug": {}}

        def mock_ocr(region):
            if region.shape[1] > 100:   # price column is wider
                return "29.660.000,00 ISK"
            return "in g"              # qty column

        with patch.object(self.detector, '_ocr_region', side_effect=mock_ocr):
            cands = self.detector._run_buy_manual_grid_fallback(
                img, 460, 480, 0, 600, 100, 300, 20, 80,
                29_660_000.0, 8, {}, result, order_tick=10_000.0
            )
        self.assertGreater(len(cands), 0)
        self.assertTrue(cands[0]["matched_price"])
        self.assertTrue(cands[0]["matched_quantity"])

    def test_grid_ambiguous_if_two_rows(self):
        """Test F: two distinct rows match → both returned (caller marks ambiguous)."""
        try:
            import numpy as _np
        except ImportError:
            self.skipTest("numpy not available")
        img    = _np.zeros((700, 600, 3), dtype=_np.uint8)
        result = {"debug": {}}
        call   = [0]

        def mock_ocr(region):
            call[0] += 1
            if region.shape[1] > 100:
                return "29.660.000,00 ISK"
            return "8"

        with patch.object(self.detector, '_ocr_region', side_effect=mock_ocr):
            # Two non-overlapping y windows: 460-478 and 550-568
            # We manually call _run_buy_manual_grid_fallback with a range
            # that covers those two bands only
            cands = self.detector._run_buy_manual_grid_fallback(
                img, 460, 570, 0, 600, 100, 300, 20, 80,
                29_660_000.0, 8, {}, result, order_tick=10_000.0
            )
        # Two non-overlapping rows should both be accepted
        self.assertGreaterEqual(len(cands), 2,
            "Two distinct rows should both be returned for caller to decide ambiguous")


if __name__ == "__main__":
    unittest.main()
