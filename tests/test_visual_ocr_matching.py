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

if __name__ == "__main__":
    unittest.main()
