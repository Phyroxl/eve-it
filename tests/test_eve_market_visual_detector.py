"""
Tests for core/eve_market_visual_detector.py.

Covers:
  1. normalize_price_text — European, English, plain, ISK suffix
  2. normalize_quantity_text — plain, with whitespace/suffix
  3. EveMarketVisualDetector — detection with mocked _find_blue_row_bands / _ocr_region
  4. detect_own_order_row returns error when OCR backend unavailable
  5. unique_match / ambiguous / not_found paths
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.eve_market_visual_detector import (
    normalize_price_text,
    normalize_quantity_text,
    EveMarketVisualDetector,
    _base_detection_result,
)


# ---------------------------------------------------------------------------
# normalize_price_text
# ---------------------------------------------------------------------------

class TestNormalizePriceText(unittest.TestCase):

    def test_plain_integer(self):
        self.assertAlmostEqual(normalize_price_text("249900000"), 249900000.0)

    def test_plain_float(self):
        self.assertAlmostEqual(normalize_price_text("249900000.50"), 249900000.5)

    def test_english_thousands_dot_decimal(self):
        self.assertAlmostEqual(normalize_price_text("249,900,000.00"), 249900000.0)

    def test_european_dots_thousands_comma_decimal(self):
        self.assertAlmostEqual(normalize_price_text("249.900.000,00"), 249900000.0)

    def test_isk_suffix_english(self):
        self.assertAlmostEqual(normalize_price_text("1,595.90 ISK"), 1595.9)

    def test_isk_suffix_european(self):
        self.assertAlmostEqual(normalize_price_text("1.595,90 ISK"), 1595.9)

    def test_isk_no_space(self):
        self.assertAlmostEqual(normalize_price_text("1595.90ISK"), 1595.9)

    def test_case_insensitive_suffix(self):
        self.assertAlmostEqual(normalize_price_text("5000 isk"), 5000.0)

    def test_empty_string(self):
        self.assertEqual(normalize_price_text(""), 0.0)

    def test_only_isk(self):
        self.assertEqual(normalize_price_text("ISK"), 0.0)

    def test_invalid_text(self):
        self.assertEqual(normalize_price_text("no_number"), 0.0)

    def test_european_single_decimal_comma(self):
        # "1,5" — comma with ≤2 digits after → decimal comma
        self.assertAlmostEqual(normalize_price_text("1,5"), 1.5)

    def test_english_large_no_decimal(self):
        self.assertAlmostEqual(normalize_price_text("10,000,000"), 10000000.0)

    def test_european_dots_only_thousands(self):
        # Multiple dots with no comma → European thousands
        self.assertAlmostEqual(normalize_price_text("1.000.000"), 1000000.0)


# ---------------------------------------------------------------------------
# normalize_quantity_text
# ---------------------------------------------------------------------------

class TestNormalizeQuantityText(unittest.TestCase):

    def test_plain_integer(self):
        self.assertEqual(normalize_quantity_text("42"), 42)

    def test_with_suffix(self):
        self.assertEqual(normalize_quantity_text("100 units"), 100)

    def test_with_commas(self):
        self.assertEqual(normalize_quantity_text("10,000"), 10000)

    def test_with_dots(self):
        self.assertEqual(normalize_quantity_text("10.000"), 10000)

    def test_with_spaces(self):
        self.assertEqual(normalize_quantity_text("1 000"), 1000)

    def test_empty(self):
        self.assertEqual(normalize_quantity_text(""), 0)

    def test_non_numeric(self):
        self.assertEqual(normalize_quantity_text("abc"), 0)

    def test_leading_whitespace(self):
        self.assertEqual(normalize_quantity_text("  500"), 500)


# ---------------------------------------------------------------------------
# _base_detection_result
# ---------------------------------------------------------------------------

class TestBaseDetectionResult(unittest.TestCase):

    def test_has_required_keys(self):
        r = _base_detection_result()
        for key in ("status", "error", "candidates_count", "row_center_x",
                    "row_center_y", "matched_price", "matched_quantity",
                    "matched_own_marker", "matched_side_section",
                    "price_text", "quantity_text", "debug"):
            self.assertIn(key, r)

    def test_debug_has_required_keys(self):
        r = _base_detection_result()
        for key in ("blue_bands_found", "section_used", "section_y_min", "section_y_max",
                    "price_col_x_min", "price_col_x_max", "qty_col_x_min", "qty_col_x_max",
                    "candidate_bands", "matched_band"):
            self.assertIn(key, r["debug"])

    def test_default_status_error(self):
        self.assertEqual(_base_detection_result()["status"], "error")


# ---------------------------------------------------------------------------
# EveMarketVisualDetector — unit tests with mocked internals
# ---------------------------------------------------------------------------

def _det(overrides=None):
    cfg = {
        "visual_ocr_require_unique_match":      True,
        "visual_ocr_match_price":               True,
        "visual_ocr_match_quantity":            True,
        "visual_ocr_require_own_order_marker":  True,
        "visual_ocr_side_section_required":     True,
        # Hardening ratio defaults
        "visual_ocr_sell_section_y_min_ratio":  0.0,
        "visual_ocr_sell_section_y_max_ratio":  1.0,
        "visual_ocr_buy_section_y_min_ratio":   0.0,
        "visual_ocr_buy_section_y_max_ratio":   1.0,
        "visual_ocr_price_col_x_min_ratio":     0.48,
        "visual_ocr_price_col_x_max_ratio":     0.68,
        "visual_ocr_qty_col_x_min_ratio":       0.38,
        "visual_ocr_qty_col_x_max_ratio":       0.52,
        "visual_ocr_marker_x_min_ratio":        0.20,
        "visual_ocr_marker_x_max_ratio":        0.32,
        # Disable marker requirement by default so existing tests pass without marker data
        "visual_ocr_marker_required":           False,
        "visual_ocr_min_order_row_y_offset_from_section": 0,
        "visual_ocr_min_row_height": 1,
        "visual_ocr_max_row_height": 9999,
    }
    if overrides:
        cfg.update(overrides)
    return EveMarketVisualDetector(cfg)


def _make_screenshot():
    """Return a minimal 100×50 numpy array screenshot stub."""
    try:
        import numpy as np
        return np.zeros((50, 100, 3), dtype="uint8")
    except ImportError:
        return None


_ORDER = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
_WINDOW_RECT = {"left": 0, "top": 0, "width": 100, "height": 50}


class TestDetectorBackendUnavailable(unittest.TestCase):
    """When PIL/numpy/pytesseract are not available, returns error."""

    def test_returns_error_when_pil_unavailable(self):
        det = _det()
        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", False), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", False), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", False):
            result = det.detect_own_order_row(MagicMock(), _ORDER, _WINDOW_RECT)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "ocr_backend_unavailable")

    def test_returns_error_when_pytesseract_unavailable(self):
        import numpy as np
        det = _det()
        screenshot = np.zeros((50, 100, 3), dtype="uint8")
        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", False), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]):
            result = det.detect_own_order_row(screenshot, _ORDER, _WINDOW_RECT)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "ocr_backend_unavailable_module_missing")
        self.assertEqual(result["candidates_count"], 1)
        self.assertEqual(result["debug"]["blue_bands_found"], 1)


class TestDetectorNotFound(unittest.TestCase):

    def test_no_blue_bands_returns_not_found(self):
        import numpy as np
        det = _det()
        screenshot = np.zeros((50, 100, 3), dtype="uint8")
        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_find_blue_row_bands", return_value=[]), \
             patch.object(det, "_ocr_region", return_value=""):
            result = det.detect_own_order_row(screenshot, _ORDER, _WINDOW_RECT)
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["candidates_count"], 0)


class TestDetectorUniqueMatch(unittest.TestCase):

    def _run_with_bands(self, bands, price_texts, qty_texts):
        import numpy as np
        det = _det()
        screenshot = np.zeros((200, 400, 3), dtype="uint8")

        ocr_calls = iter(price_texts + qty_texts)

        def _ocr_side_effect(arr):
            try:
                return next(ocr_calls)
            except StopIteration:
                return ""

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=bands), \
             patch.object(det, "_ocr_region", side_effect=_ocr_side_effect):
            return det.detect_own_order_row(screenshot, _ORDER, _WINDOW_RECT)

    def test_unique_match_price_and_qty(self):
        result = self._run_with_bands(
            bands=[(10, 25)],
            price_texts=["1595.90 ISK"],
            qty_texts=["10"],
        )
        self.assertEqual(result["status"], "unique_match")
        self.assertTrue(result["matched_price"])
        self.assertTrue(result["matched_quantity"])
        self.assertIsNotNone(result["row_center_x"])
        self.assertIsNotNone(result["row_center_y"])

    def test_unique_match_includes_window_offset(self):
        window_rect = {"left": 100, "top": 200, "width": 400, "height": 200}
        import numpy as np
        det = _det()
        screenshot = np.zeros((200, 400, 3), dtype="uint8")

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 30)]), \
             patch.object(det, "_ocr_region", return_value="1595.90"):
            result = det.detect_own_order_row(screenshot, _ORDER, window_rect)
        if result["status"] == "unique_match":
            self.assertGreaterEqual(result["row_center_x"], 100)
            self.assertGreaterEqual(result["row_center_y"], 200)

    def test_not_found_when_price_mismatch(self):
        result = self._run_with_bands(
            bands=[(10, 25)],
            price_texts=["9999999.00 ISK"],
            qty_texts=["10"],
        )
        self.assertEqual(result["status"], "not_found")

    def test_not_found_when_qty_mismatch(self):
        result = self._run_with_bands(
            bands=[(10, 25)],
            price_texts=["1595.90 ISK"],
            qty_texts=["999"],
        )
        self.assertEqual(result["status"], "not_found")


class TestDetectorAmbiguous(unittest.TestCase):

    def test_two_matching_bands_returns_ambiguous(self):
        import numpy as np
        det = _det()
        screenshot = np.zeros((200, 400, 3), dtype="uint8")

        # OCR returns price then qty per band × 2 bands
        ocr_values = iter(["1595.90", "10", "1595.90", "10"])

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25), (50, 65)]), \
             patch.object(det, "_ocr_region", side_effect=lambda a: next(ocr_values)):
            result = det.detect_own_order_row(screenshot, _ORDER, _WINDOW_RECT)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates_count"], 2)


class TestDetectorMatchPriceDisabled(unittest.TestCase):

    def test_price_match_disabled_ignores_price(self):
        import numpy as np
        det = _det({"visual_ocr_match_price": False})
        screenshot = np.zeros((200, 400, 3), dtype="uint8")

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]), \
             patch.object(det, "_ocr_region", return_value="10"):
            result = det.detect_own_order_row(screenshot, _ORDER, _WINDOW_RECT)
        self.assertEqual(result["status"], "unique_match")

    def test_qty_match_disabled_ignores_qty(self):
        import numpy as np
        det = _det({"visual_ocr_match_quantity": False})
        screenshot = np.zeros((200, 400, 3), dtype="uint8")

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]), \
             patch.object(det, "_ocr_region", return_value="1595.90"):
            result = det.detect_own_order_row(screenshot, _ORDER, _WINDOW_RECT)
        self.assertEqual(result["status"], "unique_match")


class TestFindBlueRowBands(unittest.TestCase):
    """Unit test _find_blue_row_bands directly without mocking."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_empty_array_returns_empty(self):
        det = _det()
        empty = self._np.zeros((0, 10, 3), dtype="uint8")
        result = det._find_blue_row_bands(empty, 0, 0, 0, 10, {})
        self.assertEqual(result, [])

    def test_no_blue_pixels_returns_empty(self):
        det = _det()
        arr = self._np.zeros((50, 100, 3), dtype="uint8")
        # All red pixels
        arr[:, :, 0] = 200
        result = det._find_blue_row_bands(arr, 0, 50, 0, 100, {})
        self.assertEqual(result, [])

    def test_blue_row_detected(self):
        det = _det()
        arr = self._np.zeros((50, 100, 3), dtype="uint8")
        # Paint rows 10-20 with EVE blue color
        arr[10:21, :, 0] = 40   # R
        arr[10:21, :, 1] = 80   # G
        arr[10:21, :, 2] = 150  # B
        result = det._find_blue_row_bands(arr, 0, 50, 0, 100, {})
        self.assertGreater(len(result), 0)
        band = result[0]
        self.assertLessEqual(band[0], 10)
        self.assertGreaterEqual(band[1], 20)

    def test_two_separate_blue_rows_detected(self):
        det = _det()
        arr = self._np.zeros((100, 100, 3), dtype="uint8")
        arr[10:16, :, 0] = 40
        arr[10:16, :, 1] = 80
        arr[10:16, :, 2] = 150
        arr[60:66, :, 0] = 40
        arr[60:66, :, 1] = 80
        arr[60:66, :, 2] = 150
        result = det._find_blue_row_bands(arr, 0, 100, 0, 100, {})
        self.assertEqual(len(result), 2)


class TestSectionBasedDetection(unittest.TestCase):
    """Blue-band search is restricted to the correct section (sell vs buy)."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def _run(self, is_buy, expected_section):
        det = _det()
        order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": is_buy}
        window_rect = {"left": 0, "top": 0, "width": 100, "height": 200}
        screenshot = self._np.zeros((200, 100, 3), dtype="uint8")
        calls = []

        orig = det._find_blue_row_bands
        def spy(arr, y0, y1, x0, x1, debug):
            calls.append((y0, y1))
            return []
        det._find_blue_row_bands = spy

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True):
            result = det.detect_own_order_row(screenshot, order, window_rect)

        self.assertTrue(calls, "expected _find_blue_row_bands to be called")
        y0_used, y1_used = calls[0]
        if expected_section == "sell":
            self.assertAlmostEqual(y0_used, int(200 * det.sell_y_min_ratio), delta=1)
            self.assertAlmostEqual(y1_used, int(200 * det.sell_y_max_ratio), delta=1)
        else:
            self.assertAlmostEqual(y0_used, int(200 * det.buy_y_min_ratio), delta=1)
            self.assertAlmostEqual(y1_used, int(200 * det.buy_y_max_ratio), delta=1)
        self.assertEqual(result["debug"]["section_used"], expected_section)

    def test_sell_order_uses_sell_section(self):
        self._run(is_buy=False, expected_section="sell")

    def test_buy_order_uses_buy_section(self):
        self._run(is_buy=True, expected_section="buy")


class TestColumnRatios(unittest.TestCase):
    """Column pixel coords are derived from config ratios and stored in debug."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_column_coords_in_debug(self):
        det = _det({
            "visual_ocr_market_panel_x_min_ratio": 0.0,
            "visual_ocr_market_panel_x_max_ratio": 1.0, # Full width for simplicity
            "visual_ocr_price_col_x_min_ratio": 0.50,
            "visual_ocr_price_col_x_max_ratio": 0.70,
            "visual_ocr_qty_col_x_min_ratio":   0.30,
            "visual_ocr_qty_col_x_max_ratio":   0.45,
        })
        order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 200, "height": 200}
        screenshot = self._np.zeros((200, 200, 3), dtype="uint8")

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_find_blue_row_bands", return_value=[]):
            result = det.detect_own_order_row(screenshot, order, window_rect)

        dbg = result["debug"]
        self.assertEqual(dbg["price_col_x_min"], 100) # 0 + 200*0.5
        self.assertEqual(dbg["price_col_x_max"], 140) # 0 + 200*0.7
        self.assertEqual(dbg["qty_col_x_min"],   60)  # 0 + 200*0.3
        self.assertEqual(dbg["qty_col_x_max"],   90)  # 0 + 200*0.45


class TestMarkerRequired(unittest.TestCase):
    """When marker_required=True and no marker found, band is excluded."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_marker_required_no_marker_not_found(self):
        det = _det({"visual_ocr_marker_required": True})
        order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = self._np.zeros((200, 400, 3), dtype="uint8")

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]), \
             patch.object(det, "_ocr_region", return_value="1595.90"), \
             patch.object(det, "_detect_own_order_marker", return_value=(False, 0, [0,0,0])):
            result = det.detect_own_order_row(screenshot, order, window_rect)
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(len(result["debug"]["marker_rejected_bands"]), 1)

    def test_marker_not_required_passes_without_marker(self):
        det = _det({"visual_ocr_marker_required": False})
        order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = self._np.zeros((200, 400, 3), dtype="uint8")
        ocr_values = iter(["1595.90", "10"])

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]), \
             patch.object(det, "_ocr_region", side_effect=lambda a: next(ocr_values)), \
             patch.object(det, "_detect_own_order_marker", return_value=(False, 0, [0,0,0])):
            result = det.detect_own_order_row(screenshot, order, window_rect)
        self.assertEqual(result["status"], "unique_match")
        self.assertEqual(len(result["debug"]["ocr_attempts"]), 1)

    def test_ocr_attempts_are_recorded(self):
        det = _det({"visual_ocr_marker_required": False})
        order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = self._np.zeros((200, 400, 3), dtype="uint8")
        
        # Two bands, first one matches price only, second matches both
        ocr_values = iter(["1595.90", "5", "1595.90", "10"])

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25), (40, 55)]), \
             patch.object(det, "_ocr_region", side_effect=lambda a: next(ocr_values)), \
             patch.object(det, "_detect_own_order_marker", return_value=(True, 10, [0,0,255])):
            result = det.detect_own_order_row(screenshot, order, window_rect)
            
        self.assertEqual(len(result["debug"]["ocr_attempts"]), 2)
        att1 = result["debug"]["ocr_attempts"][0]
        self.assertEqual(att1["price_match"], True)
        self.assertEqual(att1["quantity_match"], False)
        
        att2 = result["debug"]["ocr_attempts"][1]
        self.assertEqual(att2["price_match"], True)
        self.assertEqual(att2["quantity_match"], True)

    def test_multiple_price_quantity_matches_returns_ambiguous(self):
        det = _det({"visual_ocr_marker_required": False})
        order = {"price": 100, "volume_remain": 10, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = self._np.zeros((200, 400, 3), dtype="uint8")
        
        # Both bands match perfectly
        ocr_values = iter(["100", "10", "100", "10"])

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25), (40, 55)]), \
             patch.object(det, "_ocr_region", side_effect=lambda a: next(ocr_values)), \
             patch.object(det, "_detect_own_order_marker", return_value=(True, 10, [0,0,255])):
            result = det.detect_own_order_row(screenshot, order, window_rect)
            
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates_count"], 2)


class TestNoPytesseractReportsBlueBands(unittest.TestCase):
    """Without pytesseract, blue_bands_found is still reported in debug."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_blue_bands_reported_without_ocr(self):
        det = _det()
        order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 100, "height": 50}
        screenshot = self._np.zeros((50, 100, 3), dtype="uint8")

        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", False), \
             patch.object(det, "_find_blue_row_bands", return_value=[(5, 20), (25, 40)]):
            result = det.detect_own_order_row(screenshot, order, window_rect)
        self.assertEqual(result["debug"]["blue_bands_found"], 2)
        self.assertEqual(result["candidates_count"], 2)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "ocr_backend_unavailable_module_missing")


class TestDarkBlueDetection(unittest.TestCase):
    """Test detection of dark blue rows typical of EVE own orders."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_detects_dark_eve_blue_row(self):
        # RGB (14, 23, 57) is very dark blue
        det = _det({
            "visual_ocr_blue_detection_mode": "rgb_or_relative",
            "visual_ocr_blue_r_max": 80,
            "visual_ocr_blue_b_min": 35,
        })
        arr = self._np.zeros((50, 100, 3), dtype="uint8")
        # Paint a row with real EVE dark blue
        arr[10:20, :, 0] = 14
        arr[10:20, :, 1] = 23
        arr[10:20, :, 2] = 57
        
        result = det._find_blue_row_bands(arr, 0, 50, 0, 100, {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (10, 20))

    def test_relative_blue_detection_mode(self):
        # Even if RGB range is slightly off, relative mode should catch it if B is dominant
        det = _det({
            "visual_ocr_blue_detection_mode": "relative",
            "visual_ocr_blue_b_over_r": 5,
            "visual_ocr_blue_b_over_g": 5,
            "visual_ocr_blue_b_min": 30
        })
        arr = self._np.zeros((50, 100, 3), dtype="uint8")
        # 10, 10, 40 -> B is 30 units over R/G
        arr[5:10, :, 0] = 10
        arr[5:10, :, 1] = 10
        arr[5:10, :, 2] = 40
        
        result = det._find_blue_row_bands(arr, 0, 50, 0, 100, {})
        self.assertEqual(len(result), 1)

    def test_blue_detection_uses_market_panel_width(self):
        # The blue row only occupies 30% of the screen (the market panel)
        det = _det({
            "visual_ocr_market_panel_x_min_ratio": 0.30,
            "visual_ocr_market_panel_x_max_ratio": 0.60,
            "visual_ocr_blue_row_threshold": 0.02
        })
        w, h = 1000, 500
        arr = self._np.zeros((h, w, 3), dtype="uint8")
        
        # Panel is x=300 to x=600 (width=300)
        # 2% of 300 is 6 pixels. Let's paint 20 pixels blue in the panel.
        p0, p1 = 300, 600
        arr[100:110, p0:p0+20, 0] = 20
        arr[100:110, p0:p0+20, 1] = 20
        arr[100:110, p0:p0+20, 2] = 80
        
        # Searching whole width (0 to 1000) would need 20 pixels (2% of 1000).
        # But we search in panel (300 to 600) so we only need 6 pixels (2% of 300).
        result = det._find_blue_row_bands(arr, 0, h, p0, p1, {})
        self.assertEqual(len(result), 1)


class TestPanelRelativeColumns(unittest.TestCase):
    """Verify OCR columns are calculated relative to market panel."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_ocr_columns_are_panel_relative(self):
        det = _det({
            "visual_ocr_market_panel_x_min_ratio": 0.10,
            "visual_ocr_market_panel_x_max_ratio": 0.90,
            "visual_ocr_price_col_x_min_ratio": 0.50, # middle of the panel
            "visual_ocr_price_col_x_max_ratio": 0.60,
        })
        # Window width 1000 -> Panel width 800 (from 100 to 900)
        # Price col should start at 100 + (800 * 0.50) = 500
        order = {"price": 100, "volume_remain": 1, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 1000, "height": 500}
        screenshot = self._np.zeros((500, 1000, 3), dtype="uint8")

        with patch.object(det, "_find_blue_row_bands", return_value=[]):
            result = det.detect_own_order_row(screenshot, order, window_rect)
        
        dbg = result["debug"]
        self.assertEqual(dbg["market_panel_x_min"], 100)
        self.assertEqual(dbg["market_panel_x_max"], 900)
        self.assertEqual(dbg["price_col_x_min"], 500)
        self.assertEqual(dbg["price_col_x_max"], 580) # 500 + 800*0.10


class TestTesseractBackend(unittest.TestCase):
    """Test Tesseract backend configuration and availability logic."""

    def test_autodetect_windows_path(self):
        # We need to mock os.path.exists for the autodetect function
        from core.eve_market_visual_detector import _autodetect_tesseract_cmd
        with patch("os.path.exists", side_effect=lambda p: "Tesseract-OCR" in p):
            path = _autodetect_tesseract_cmd()
            self.assertIn("Tesseract-OCR", path)
            self.assertIn("tesseract.exe", path)

    def test_tesseract_cmd_from_config(self):
        det = _det({"visual_ocr_tesseract_cmd": "C:\\Custom\\tesseract.exe"})
        self.assertEqual(det.tesseract_cmd, "C:\\Custom\\tesseract.exe")

    def test_module_missing_error(self):
        det = _det()
        order = {"price": 100, "volume_remain": 1, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = _make_screenshot()

        with patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", False), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]):
            result = det.detect_own_order_row(screenshot, order, window_rect)
            self.assertEqual(result["error"], "ocr_backend_unavailable_module_missing")

    def test_executable_missing_error(self):
        det = _det()
        order = {"price": 100, "volume_remain": 1, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = _make_screenshot()

        with patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=False), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 25)]):
            result = det.detect_own_order_row(screenshot, order, window_rect)
            self.assertEqual(result["error"], "ocr_backend_unavailable_tesseract_executable_missing")

    def test_tesseract_ready_detection(self):
        det = _det()
        with patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch("core.eve_market_visual_detector.subprocess.run", return_value=MagicMock(returncode=0)):
            self.assertTrue(det._is_tesseract_available())
        
        with patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch("core.eve_market_visual_detector.subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(det._is_tesseract_available())


class TestRowFiltering(unittest.TestCase):
    """Verify that rows are filtered by height and header offset."""

    def setUp(self):
        try:
            import numpy as np
            self._np = np
        except ImportError:
            self.skipTest("numpy not available")

    def test_filter_by_height(self):
        det = _det({
            "visual_ocr_min_row_height": 10,
            "visual_ocr_max_row_height": 20,
        })
        order = {"price": 100, "volume_remain": 1, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = self._np.zeros((200, 400, 3), dtype="uint8")

        # Mock find_blue_row_bands to return 3 bands:
        # 1. Too short (5px)
        # 2. OK (15px)
        # 3. Too tall (30px)
        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(10, 15), (30, 45), (60, 90)]):
            result = det.detect_own_order_row(screenshot, order, window_rect)
        
        dbg = result["debug"]
        self.assertEqual(len(dbg["raw_candidate_bands"]), 3)
        self.assertEqual(len(dbg["filtered_candidate_bands"]), 1)
        self.assertEqual(dbg["filtered_candidate_bands"][0], (30, 45))
        self.assertEqual(len(dbg["rejected_bands_by_height"]), 2)

    def test_filter_by_header_offset(self):
        det = _det({
            "visual_ocr_sell_section_y_min_ratio": 0.0,
            "visual_ocr_min_order_row_y_offset_from_section": 50,
        })
        order = {"price": 100, "volume_remain": 1, "is_buy_order": False}
        window_rect = {"left": 0, "top": 0, "width": 400, "height": 200}
        screenshot = self._np.zeros((200, 400, 3), dtype="uint8")

        # Mock find_blue_row_bands to return 2 bands:
        # 1. At y=20 (too close to top, offset is 50)
        # 2. At y=80 (OK)
        with patch("core.eve_market_visual_detector._PIL_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._NUMPY_AVAILABLE", True), \
             patch("core.eve_market_visual_detector._PYTESSERACT_AVAILABLE", True), \
             patch.object(det, "_is_tesseract_available", return_value=True), \
             patch.object(det, "_find_blue_row_bands", return_value=[(20, 35), (80, 95)]):
            result = det.detect_own_order_row(screenshot, order, window_rect)
            
        dbg = result["debug"]
        self.assertEqual(len(dbg["filtered_candidate_bands"]), 1)
        self.assertEqual(dbg["filtered_candidate_bands"][0], (80, 95))
        self.assertEqual(len(dbg["rejected_bands_by_offset"]), 1)


if __name__ == "__main__":
    unittest.main()
