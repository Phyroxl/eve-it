import unittest
from core.eve_market_visual_detector import (
    EveMarketVisualDetector, normalize_quantity_text,
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


if __name__ == "__main__":
    unittest.main()
