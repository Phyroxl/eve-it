"""
Visual detector for EVE Online market window — own-order row detection.

Strategy:
  1. Restrict search to the relevant section (Sell or Buy) via configurable ratios.
  2. Find blue-highlighted rows (EVE marks own orders with a dark-blue band).
  3. For each candidate row, check for the own-order marker in the left zone.
  4. OCR the price and quantity columns using configurable column ratios.
  5. Compare against order_data["price"] and order_data["volume_remain"].
  6. Return unique_match / ambiguous / not_found / error.

Blue-band detection works without pytesseract.  OCR matching requires
pytesseract.  If OCR is unavailable and matching is requested, status="error"
but blue_bands_found is still reported in debug so calibration is possible.

NOTE: EVE Online renders its UI inside the game window.  The "Modify Order"
dialog is NOT a native OS window.  This detector works at the pixel level
only; OS-level dialog verification is not possible.
"""
import logging
import re

_log = logging.getLogger('eve.market.visual_detector')

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PILImage = None
    _PIL_AVAILABLE = False

try:
    import pytesseract as _pytesseract
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    _pytesseract = None
    _PYTESSERACT_AVAILABLE = False

try:
    import numpy as _np
    _NUMPY_AVAILABLE = True
except ImportError:
    _np = None
    _NUMPY_AVAILABLE = False

import os
import subprocess

def _autodetect_tesseract_cmd() -> str:
    """Search for tesseract.exe in common Windows installation paths."""
    paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return ""


# ---------------------------------------------------------------------------
# Pure utility functions (no image dependencies)
# ---------------------------------------------------------------------------

def normalize_price_text(text: str) -> float:
    """
    Parse EVE market price text to float.

    Handles:
      European  : 249.900.000,00 ISK  → 249900000.0
      English   : 249,900,000.00 ISK  → 249900000.0
      Plain     : 249900000           → 249900000.0
      No suffix : 249900000.0         → 249900000.0
    """
    text = str(text).strip().upper()
    for suffix in (" ISK", "ISK"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    text = text.strip()
    if not text:
        return 0.0

    if "," in text and "." in text:
        last_dot   = text.rfind(".")
        last_comma = text.rfind(",")
        if last_comma > last_dot:
            # European: dots=thousands, comma=decimal
            text = text.replace(".", "").replace(",", ".")
        else:
            # English: commas=thousands, dot=decimal
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2 and parts[1].isdigit():
            text = text.replace(",", ".")   # decimal comma
        else:
            text = text.replace(",", "")    # thousands commas
    elif "." in text and text.count(".") > 1:
        text = text.replace(".", "")        # European thousands-only dots

    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_quantity_text(text: str) -> int:
    """Parse EVE market quantity text to int. Tolerates whitespace and suffixes."""
    text = str(text).strip()
    m = re.match(r"^([\d\s.,]+)", text)
    if m:
        num = re.sub(r"[\s.,]", "", m.group(1))
        try:
            return int(num)
        except ValueError:
            return 0
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _base_detection_result() -> dict:
    return {
        "status":               "error",
        "error":                None,
        "candidates_count":     0,
        "row_center_x":         None,
        "row_center_y":         None,
        "matched_price":        False,
        "matched_quantity":     False,
        "matched_own_marker":   False,
        "matched_side_section": False,
        "price_text":           None,
        "quantity_text":        None,
        "debug": {
            "blue_bands_found":  0,
            "section_used":      None,
            "section_y_min":     None,
            "section_y_max":     None,
            "price_col_x_min":   None,
            "price_col_x_max":   None,
            "qty_col_x_min":     None,
            "qty_col_x_max":     None,
            "candidate_bands":   [],
            "marker_rejected_bands": [],
            "ocr_attempts":      [],
            "matched_band":      None,
        },
    }


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------

class EveMarketVisualDetector:
    """
    Detect the own-order row in an EVE Online market window screenshot.

    Own orders are highlighted with a dark-blue horizontal band.  The
    detector restricts its search to the relevant section (Sell or Buy),
    finds these bands, checks for the own-order marker, runs OCR on
    price/quantity regions inside each band, and compares against the
    known order values.

    All methods are separated for testability.
    """

    # Approximate RGB range for EVE's own-order row highlight (dark blue)
    # Default fallback values (will be overridden by config)
    _BLUE_MIN = (5,   10,  35)
    _BLUE_MAX = (80,  90,  130)
    _BLUE_THRESHOLD = 0.02

    # Own-order marker: bright-blue pixels distinct from the dim row background
    _MARKER_MIN_B     = 140
    _MARKER_B_OVER_R  = 30
    _MARKER_B_OVER_G  = 20
    _MARKER_MIN_COUNT = 4

    def __init__(self, config: dict):
        self.require_unique_match  = bool(config.get("visual_ocr_require_unique_match",     True))
        self.match_price           = bool(config.get("visual_ocr_match_price",              True))
        self.match_quantity        = bool(config.get("visual_ocr_match_quantity",           True))
        self.require_own_marker    = bool(config.get("visual_ocr_require_own_order_marker", True))
        self.side_section_required = bool(config.get("visual_ocr_side_section_required",    True))
        
        # Section y-axis ratios
        self.sell_y_min_ratio   = float(config.get("visual_ocr_sell_section_y_min_ratio", 0.22))
        self.sell_y_max_ratio   = float(config.get("visual_ocr_sell_section_y_max_ratio", 0.58))
        self.buy_y_min_ratio    = float(config.get("visual_ocr_buy_section_y_min_ratio",  0.55))
        self.buy_y_max_ratio    = float(config.get("visual_ocr_buy_section_y_max_ratio",  0.88))
        
        # Market Panel (The subset of the window containing the actual order book)
        self.panel_x_min_ratio  = float(config.get("visual_ocr_market_panel_x_min_ratio", 0.36))
        self.panel_x_max_ratio  = float(config.get("visual_ocr_market_panel_x_max_ratio", 0.70))

        # Column x-axis ratios (RELATIVE to Market Panel)
        self.price_x_min_ratio  = float(config.get("visual_ocr_price_col_x_min_ratio",   0.43))
        self.price_x_max_ratio  = float(config.get("visual_ocr_price_col_x_max_ratio",   0.68))
        self.qty_x_min_ratio    = float(config.get("visual_ocr_qty_col_x_min_ratio",     0.25))
        self.qty_x_max_ratio    = float(config.get("visual_ocr_qty_col_x_max_ratio",     0.45))
        
        # Marker detection ratios (RELATIVE to Market Panel)
        self.marker_x_min_ratio = float(config.get("visual_ocr_marker_x_min_ratio",      0.00))
        self.marker_x_max_ratio = float(config.get("visual_ocr_marker_x_max_ratio",      0.18))
        self.marker_required    = bool(config.get("visual_ocr_marker_required",           True))

        # Dark Blue Detection Calibration
        self.blue_r_min = int(config.get("visual_ocr_blue_r_min", 5))
        self.blue_r_max = int(config.get("visual_ocr_blue_r_max", 80))
        self.blue_g_min = int(config.get("visual_ocr_blue_g_min", 10))
        self.blue_g_max = int(config.get("visual_ocr_blue_g_max", 90))
        self.blue_b_min = int(config.get("visual_ocr_blue_b_min", 35))
        self.blue_b_max = int(config.get("visual_ocr_blue_b_max", 130))
        self.blue_b_over_r = int(config.get("visual_ocr_blue_b_over_r", 8))
        self.blue_b_over_g = int(config.get("visual_ocr_blue_b_over_g", 5))
        self.blue_row_threshold = float(config.get("visual_ocr_blue_row_threshold", 0.02))
        self.blue_detection_mode = config.get("visual_ocr_blue_detection_mode", "rgb_or_relative")

        # Tesseract Configuration
        self.tesseract_cmd  = config.get("visual_ocr_tesseract_cmd", "")
        self.tesseract_lang = config.get("visual_ocr_tesseract_lang", "eng")
        self.tesseract_psm  = int(config.get("visual_ocr_tesseract_psm", 7))
        
        if _PYTESSERACT_AVAILABLE:
            if not self.tesseract_cmd:
                self.tesseract_cmd = _autodetect_tesseract_cmd()
            
            if self.tesseract_cmd:
                _pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def _is_tesseract_available(self) -> bool:
        """Check if Tesseract executable is actually callable."""
        if not _PYTESSERACT_AVAILABLE:
            return False
        
        cmd = self.tesseract_cmd or "tesseract"
        try:
            # Run tesseract --version to see if it responds
            # Using startupinfo to avoid console window flickering on Windows
            si = None
            if os.name == 'nt':
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run([cmd, "--version"], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL,
                           startupinfo=si,
                           check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, Exception):
            return False

    def detect_own_order_row(self, screenshot, order_data: dict,
                             window_rect: dict) -> dict:
        """
        Main entry point.

        Args:
            screenshot  : PIL Image or numpy array of the EVE window region.
            order_data  : {"price": float, "volume_remain": int, "is_buy_order": bool}
            window_rect : {"left": int, "top": int, "width": int, "height": int}

        Returns detection result dict (see _base_detection_result).
        """
        result = _base_detection_result()

        if not _PIL_AVAILABLE or not _NUMPY_AVAILABLE:
            result["error"] = "ocr_backend_unavailable"
            return result

        try:
            return self._run_detection(screenshot, order_data, window_rect, result)
        except Exception as exc:
            _log.error(f"[VISUAL_OCR] detection error: {exc}")
            result["status"] = "error"
            result["error"]  = f"detection_error: {exc}"
            return result

    # ── internal methods (patchable) ─────────────────────────────────────────

    def _run_detection(self, screenshot, order_data: dict,
                       window_rect: dict, result: dict) -> dict:
        img       = _ensure_pil_image(screenshot)
        img_array = _np.array(img)

        target_price    = float(order_data.get("price", 0))
        target_quantity = int(order_data.get("volume_remain", 0))
        is_buy_order    = bool(order_data.get("is_buy_order", False))

        h, w = img_array.shape[:2]

        # 1. Determine section bounds based on order side
        if is_buy_order:
            y_min_ratio  = self.buy_y_min_ratio
            y_max_ratio  = self.buy_y_max_ratio
            section_name = "buy"
        else:
            y_min_ratio  = self.sell_y_min_ratio
            y_max_ratio  = self.sell_y_max_ratio
            section_name = "sell"

        section_y_min = max(0, min(int(h * y_min_ratio), h - 1))
        section_y_max = max(section_y_min + 1, min(int(h * y_max_ratio), h))

        result["debug"]["section_used"]  = section_name
        result["debug"]["section_y_min"] = section_y_min
        result["debug"]["section_y_max"] = section_y_max
        result["matched_side_section"]   = True

        # 2. Determine Market Panel bounds (Search only within the list)
        panel_x0 = int(w * self.panel_x_min_ratio)
        panel_x1 = int(w * self.panel_x_max_ratio)
        panel_w  = panel_x1 - panel_x0
        result["debug"]["market_panel_x_min"] = panel_x0
        result["debug"]["market_panel_x_max"] = panel_x1

        # 3. Pre-compute column pixel coordinates (RELATIVE TO PANEL)
        price_x0 = panel_x0 + int(panel_w * self.price_x_min_ratio)
        price_x1 = panel_x0 + int(panel_w * self.price_x_max_ratio)
        qty_x0   = panel_x0 + int(panel_w * self.qty_x_min_ratio)
        qty_x1   = panel_x0 + int(panel_w * self.qty_x_max_ratio)
        result["debug"]["price_col_x_min"] = price_x0
        result["debug"]["price_col_x_max"] = price_x1
        result["debug"]["qty_col_x_min"]   = qty_x0
        result["debug"]["qty_col_x_max"]   = qty_x1

        # 4. Find blue bands in section (searching only inside panel width)
        candidate_bands = self._find_blue_row_bands(
            img_array, section_y_min, section_y_max, panel_x0, panel_x1, result["debug"]
        )
        result["debug"]["blue_bands_found"] = len(candidate_bands)
        result["debug"]["candidate_bands"]  = list(candidate_bands)

        if not candidate_bands:
            result["status"]          = "not_found"
            result["candidates_count"] = 0
            return result

        # 4. OCR availability check AFTER band detection (keeps blue_bands_found accurate)
        need_ocr = (
            (self.match_price    and target_price    > 0) or
            (self.match_quantity and target_quantity > 0)
        )
        
        # Enhanced backend diagnostics
        result["debug"]["pytesseract_module_available"] = _PYTESSERACT_AVAILABLE
        result["debug"]["tesseract_executable_ready"]    = self._is_tesseract_available()
        result["debug"]["tesseract_cmd_used"]           = self.tesseract_cmd or "N/A"
        result["debug"]["tesseract_suggested_path"]     = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        if need_ocr:
            if not _PYTESSERACT_AVAILABLE:
                result["status"]           = "error"
                result["error"]            = "ocr_backend_unavailable_module_missing"
                result["candidates_count"] = len(candidate_bands)
                return result
            
            if not result["debug"]["tesseract_executable_ready"]:
                result["status"]           = "error"
                result["error"]            = "ocr_backend_unavailable_tesseract_executable_missing"
                result["candidates_count"] = len(candidate_bands)
                return result

        # 5. For each band: marker check + OCR validation
        verified = []
        for (y_min, y_max) in candidate_bands:
            own_marker, m_pix, m_rgb = self._detect_own_order_marker(img_array, y_min, y_max, w)
            
            if self.marker_required and not own_marker:
                result["debug"]["marker_rejected_bands"].append({
                    "band": [y_min, y_max],
                    "marker_pixels": m_pix,
                    "marker_avg_rgb": m_rgb
                })
                continue

            price_ok   = True
            qty_ok     = True
            price_text = ""
            qty_text   = ""

            if self.match_price and target_price > 0:
                price_text = self._ocr_region(img_array[y_min:y_max, price_x0:price_x1])
                ocr_price  = normalize_price_text(price_text)
                price_ok   = abs(ocr_price - target_price) < (target_price * 0.001 + 1.0)

            if self.match_quantity and target_quantity > 0:
                qty_text = self._ocr_region(img_array[y_min:y_max, qty_x0:qty_x1])
                ocr_qty  = normalize_quantity_text(qty_text)
                qty_ok   = (ocr_qty == target_quantity)

            # Record attempt regardless of match
            result["debug"]["ocr_attempts"].append({
                "band": [y_min, y_max],
                "marker_matched": own_marker,
                "price_text": price_text,
                "quantity_text": qty_text,
                "price_match": price_ok,
                "quantity_match": qty_ok
            })

            if price_ok and qty_ok:
                y_c = (y_min + y_max) // 2
                x_c = w // 2
                verified.append({
                    "row_center_x":       x_c + window_rect.get("left", 0),
                    "row_center_y":       y_c + window_rect.get("top",  0),
                    "matched_price":      price_ok,
                    "matched_quantity":   qty_ok,
                    "matched_own_marker": own_marker,
                    "price_text":         price_text,
                    "quantity_text":      qty_text,
                    "band":               (y_min, y_max),
                })

        result["candidates_count"] = len(verified)

        if len(verified) == 0:
            result["status"] = "not_found"
        elif len(verified) > 1:
            result["status"] = "ambiguous"
        else:
            row = verified[0]
            result["status"]             = "unique_match"
            result["row_center_x"]       = row["row_center_x"]
            result["row_center_y"]       = row["row_center_y"]
            result["matched_price"]      = row["matched_price"]
            result["matched_quantity"]   = row["matched_quantity"]
            result["matched_own_marker"] = row["matched_own_marker"]
            result["price_text"]         = row["price_text"]
            result["quantity_text"]      = row["quantity_text"]
            result["debug"]["matched_band"] = row["band"]

        return result

    def _find_blue_row_bands(self, img_array, y_start: int, y_end: int,
                              x_start: int, x_end: int, debug: dict) -> list:
        """
        Find horizontal pixel bands matching EVE's own-order blue color.
        Returns list of (y_min, y_max) tuples in original image coordinates.
        """
        region = img_array[y_start:y_end, x_start:x_end]
        if region.size == 0:
            return []

        r = region[:, :, 0].astype(int)
        g = region[:, :, 1].astype(int)
        b = region[:, :, 2].astype(int)

        # RGB thresholds
        rgb_match = (
            (r >= self.blue_r_min) & (r <= self.blue_r_max) &
            (g >= self.blue_g_min) & (g <= self.blue_g_max) &
            (b >= self.blue_b_min) & (b <= self.blue_b_max)
        )
        
        # Relative blue dominance
        rel_match = (
            (b >= self.blue_b_min) &
            (b > r + self.blue_b_over_r) &
            (b > g + self.blue_b_over_g)
        )

        if self.blue_detection_mode == "rgb":
            blue_mask = rgb_match
        elif self.blue_detection_mode == "relative":
            blue_mask = rel_match
        else: # rgb_or_relative
            blue_mask = rgb_match | rel_match

        # Analyze blue density per row
        row_blue_counts = blue_mask.sum(axis=1)
        width = x_end - x_start
        threshold = max(1, int(width * self.blue_row_threshold))
        blue_rows = _np.where(row_blue_counts >= threshold)[0]

        # Debug info
        debug["sample_dark_blue_pixels_count"] = int(blue_mask.sum())
        if blue_mask.any():
            avg_b = int(_np.mean(b[blue_mask]))
            avg_g = int(_np.mean(g[blue_mask]))
            avg_r = int(_np.mean(r[blue_mask]))
            debug["average_blue_candidate_rgb"] = [avg_r, avg_g, avg_b]
            debug["max_blue_candidate_rgb"] = [int(r[blue_mask].max()), int(g[blue_mask].max()), int(b[blue_mask].max())]
            debug["min_blue_candidate_rgb"] = [int(r[blue_mask].min()), int(g[blue_mask].min()), int(b[blue_mask].min())]

        # Save top rows for calibration if nothing found
        if len(blue_rows) == 0:
            top_idx = _np.argsort(row_blue_counts)[-5:][::-1]
            debug["top_blue_candidate_rows"] = [
                {"y": int(y_start + i), "blue_pixels": int(row_blue_counts[i])} 
                for i in top_idx if row_blue_counts[i] > 0
            ]
            return []

        # Group rows into bands
        bands      = []
        band_start = int(blue_rows[0])
        prev       = int(blue_rows[0])
        for idx in blue_rows[1:]:
            idx = int(idx)
            if idx - prev > 5: # Gap of more than 5 pixels starts new band
                bands.append((y_start + band_start, y_start + prev + 1))
                band_start = idx
            prev = idx
        bands.append((y_start + band_start, y_start + prev + 1))
        return bands

    def _detect_own_order_marker(self, img_array, y_min: int, y_max: int,
                                  w: int) -> tuple:
        """
        Detect own-order marker in the left zone of a row.
        Coordinates are relative to the Market Panel.
        Returns (is_matched: bool, pixel_count: int, avg_rgb: list)
        """
        panel_x0 = int(w * self.panel_x_min_ratio)
        panel_x1 = int(w * self.panel_x_max_ratio)
        panel_w  = panel_x1 - panel_x0

        mx0 = panel_x0 + int(panel_w * self.marker_x_min_ratio)
        mx1 = panel_x0 + int(panel_w * self.marker_x_max_ratio)
        
        if mx0 >= mx1:
            return False, 0, [0, 0, 0]
        region = img_array[y_min:y_max, mx0:mx1]
        if region.size == 0 or region.shape[0] == 0 or region.shape[1] == 0:
            return False, 0, [0, 0, 0]

        r = region[:, :, 0].astype(int)
        g = region[:, :, 1].astype(int)
        b = region[:, :, 2].astype(int)

        marker_mask = (
            (b >= self._MARKER_MIN_B) &
            (b > r + self._MARKER_B_OVER_R) &
            (b > g + self._MARKER_B_OVER_G)
        )
        pixels = int(marker_mask.sum())
        matched = pixels >= self._MARKER_MIN_COUNT
        
        avg_rgb = [0, 0, 0]
        if matched and pixels > 0:
            avg_rgb = [int(_np.mean(r[marker_mask])), int(_np.mean(g[marker_mask])), int(_np.mean(b[marker_mask]))]
        elif pixels > 0:
            avg_rgb = [int(_np.mean(r[marker_mask])), int(_np.mean(g[marker_mask])), int(_np.mean(b[marker_mask]))]
            
        return matched, pixels, avg_rgb

    def _ocr_region(self, img_array) -> str:
        """Run pytesseract OCR on a numpy array region. Returns '' if unavailable."""
        if not _PYTESSERACT_AVAILABLE or not _PIL_AVAILABLE:
            return ""
        try:
            img  = _PILImage.fromarray(img_array.astype("uint8"))
            config = f"--psm {self.tesseract_psm}"
            text = _pytesseract.image_to_string(img, lang=self.tesseract_lang, config=config)
            return text.strip()
        except Exception as exc:
            _log.warning(f"[VISUAL_OCR] OCR region error: {exc}")
            return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_pil_image(screenshot):
    """Convert screenshot to PIL Image if not already one."""
    if _PIL_AVAILABLE and isinstance(screenshot, _PILImage.Image):
        return screenshot
    if _PIL_AVAILABLE and _NUMPY_AVAILABLE and isinstance(screenshot, _np.ndarray):
        return _PILImage.fromarray(screenshot.astype("uint8"))
    if _PIL_AVAILABLE:
        import io
        if isinstance(screenshot, (bytes, bytearray)):
            return _PILImage.open(io.BytesIO(bytes(screenshot)))
    # Last resort: return as-is and hope numpy conversion works
    return screenshot
