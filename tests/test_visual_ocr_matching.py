import unittest
from core.eve_market_visual_detector import EveMarketVisualDetector, normalize_quantity_text

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

if __name__ == "__main__":
    unittest.main()
