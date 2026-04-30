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
    _BLUE_MIN = (15,  35,  70)
    _BLUE_MAX = (90, 130, 210)
    _BLUE_THRESHOLD = 0.12

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
        # Column x-axis ratios
        self.price_x_min_ratio  = float(config.get("visual_ocr_price_col_x_min_ratio",   0.48))
        self.price_x_max_ratio  = float(config.get("visual_ocr_price_col_x_max_ratio",   0.68))
        self.qty_x_min_ratio    = float(config.get("visual_ocr_qty_col_x_min_ratio",     0.38))
        self.qty_x_max_ratio    = float(config.get("visual_ocr_qty_col_x_max_ratio",     0.52))
        # Marker detection ratios
        self.marker_x_min_ratio = float(config.get("visual_ocr_marker_x_min_ratio",      0.20))
        self.marker_x_max_ratio = float(config.get("visual_ocr_marker_x_max_ratio",      0.32))
        self.marker_required    = bool(config.get("visual_ocr_marker_required",           True))

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

        # 2. Pre-compute column pixel coordinates (always set for debug/calibration)
        price_x0 = int(w * self.price_x_min_ratio)
        price_x1 = int(w * self.price_x_max_ratio)
        qty_x0   = int(w * self.qty_x_min_ratio)
        qty_x1   = int(w * self.qty_x_max_ratio)
        result["debug"]["price_col_x_min"] = price_x0
        result["debug"]["price_col_x_max"] = price_x1
        result["debug"]["qty_col_x_min"]   = qty_x0
        result["debug"]["qty_col_x_max"]   = qty_x1

        # 3. Find blue bands in section
        candidate_bands = self._find_blue_row_bands(
            img_array, section_y_min, section_y_max, 0, w
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
        if need_ocr and not _PYTESSERACT_AVAILABLE:
            result["status"]           = "error"
            result["error"]            = "ocr_backend_unavailable"
            result["candidates_count"] = len(candidate_bands)
            return result

        # 5. For each band: marker check + OCR validation
        verified = []
        for (y_min, y_max) in candidate_bands:
            own_marker = self._detect_own_order_marker(img_array, y_min, y_max, w)
            if self.marker_required and not own_marker:
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
                              x_start: int, x_end: int) -> list:
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

        rmin, rmax = self._BLUE_MIN[0], self._BLUE_MAX[0]
        gmin, gmax = self._BLUE_MIN[1], self._BLUE_MAX[1]
        bmin, bmax = self._BLUE_MIN[2], self._BLUE_MAX[2]

        blue_mask = (
            (r >= rmin) & (r <= rmax) &
            (g >= gmin) & (g <= gmax) &
            (b >= bmin) & (b <= bmax) &
            (b > r + 10) & (b > g + 5)
        )
        width     = x_end - x_start
        threshold = max(1, int(width * self._BLUE_THRESHOLD))
        blue_rows = _np.where(blue_mask.sum(axis=1) >= threshold)[0]

        if len(blue_rows) == 0:
            return []

        bands      = []
        band_start = int(blue_rows[0])
        prev       = int(blue_rows[0])
        for idx in blue_rows[1:]:
            idx = int(idx)
            if idx - prev > 5:
                bands.append((y_start + band_start, y_start + prev + 1))
                band_start = idx
            prev = idx
        bands.append((y_start + band_start, y_start + prev + 1))
        return bands

    def _detect_own_order_marker(self, img_array, y_min: int, y_max: int,
                                  w: int) -> bool:
        """
        Detect own-order marker in the left zone of a row.

        Checks for bright-blue pixels (the icon/check distinct from the
        dim dark-blue row background).  Returns True if enough qualifying
        pixels are found in the marker zone.
        """
        mx0 = int(w * self.marker_x_min_ratio)
        mx1 = int(w * self.marker_x_max_ratio)
        if mx0 >= mx1:
            return False
        region = img_array[y_min:y_max, mx0:mx1]
        if region.size == 0 or region.shape[0] == 0 or region.shape[1] == 0:
            return False

        r = region[:, :, 0].astype(int)
        g = region[:, :, 1].astype(int)
        b = region[:, :, 2].astype(int)

        marker_mask = (
            (b >= self._MARKER_MIN_B) &
            (b > r + self._MARKER_B_OVER_R) &
            (b > g + self._MARKER_B_OVER_G)
        )
        return int(marker_mask.sum()) >= self._MARKER_MIN_COUNT

    def _ocr_region(self, img_array) -> str:
        """Run pytesseract OCR on a numpy array region. Returns '' if unavailable."""
        if not _PYTESSERACT_AVAILABLE or not _PIL_AVAILABLE:
            return ""
        try:
            img  = _PILImage.fromarray(img_array.astype("uint8"))
            text = _pytesseract.image_to_string(img, config="--psm 7")
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
