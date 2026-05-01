"""Runtime hotfixes loaded automatically by Python's site module.

This file keeps the Quick Order Update Visual OCR pipeline safe while the
SELL detector is being stabilized.  It is intentionally small and surgical:
only the SELL/manual-region path gets a reserved strict-pass budget so the
manual grid fallback can actually run before the global OCR timeout fires.
"""

from __future__ import annotations


def _install_visual_ocr_sell_budget_hotfix() -> None:
    try:
        from core import eve_market_visual_detector as visual_detector
    except Exception:
        return

    cls = getattr(visual_detector, "EveMarketVisualDetector", None)
    if cls is None or getattr(cls, "_sell_budget_hotfix_installed", False):
        return

    original_init = cls.__init__
    original_check_limits = getattr(cls, "_check_limits", None)
    original_run_detection_pass = getattr(cls, "_run_detection_pass", None)
    original_run_sell_grid = getattr(cls, "_run_sell_manual_grid_fallback", None)

    if not all([original_check_limits, original_run_detection_pass, original_run_sell_grid]):
        return

    class SellStrictBudgetExhausted(Exception):
        """Internal control-flow exception: strict SELL budget used up."""

    def patched_init(self, config: dict):
        original_init(self, config)
        self.sell_strict_max_ocr_calls = int(config.get("visual_ocr_sell_strict_max_ocr_calls", 20))
        self.sell_strict_timeout_ms = int(config.get("visual_ocr_sell_strict_timeout_ms", 2500))
        self.sell_grid_reserved_timeout_ms = int(config.get("visual_ocr_sell_grid_reserved_timeout_ms", 4000))
        if not getattr(self, "max_total_ocr_calls", 0):
            self.max_total_ocr_calls = int(config.get("visual_ocr_max_total_ocr_calls_per_detection", 120))

    def _write_limit_debug(self, result, elapsed_ms: int) -> None:
        if not result or "debug" not in result:
            return
        debug = result["debug"]
        debug["ocr_calls_count"] = getattr(self, "_ocr_calls_count", 0)
        debug["elapsed_ms"] = int(elapsed_ms)
        debug["max_ocr_calls"] = getattr(self, "max_total_ocr_calls", 120)
        debug["visual_ocr_max_ocr_calls"] = getattr(self, "max_total_ocr_calls", 120)
        phase = getattr(self, "_ocr_budget_phase", None)
        if phase:
            debug["visual_ocr_budget_phase"] = phase
        if phase == "sell_strict":
            start_t = getattr(self, "_ocr_budget_phase_start_time", None)
            start_c = getattr(self, "_ocr_budget_phase_start_calls", 0)
            if start_t is not None:
                import time
                debug["visual_ocr_strict_elapsed_ms"] = int((time.time() - start_t) * 1000)
            debug["visual_ocr_strict_ocr_calls"] = max(0, getattr(self, "_ocr_calls_count", 0) - start_c)

    def patched_check_limits(self, result=None):
        import time

        elapsed_ms = int((time.time() - getattr(self, "_start_time", time.time())) * 1000)
        _write_limit_debug(self, result, elapsed_ms)

        phase = getattr(self, "_ocr_budget_phase", None)
        if phase == "sell_strict":
            strict_start = getattr(self, "_ocr_budget_phase_start_time", time.time())
            strict_start_calls = getattr(self, "_ocr_budget_phase_start_calls", 0)
            strict_elapsed = int((time.time() - strict_start) * 1000)
            strict_calls = max(0, getattr(self, "_ocr_calls_count", 0) - strict_start_calls)
            if strict_calls >= getattr(self, "sell_strict_max_ocr_calls", 20):
                raise SellStrictBudgetExhausted("sell_strict_ocr_call_budget_exhausted")
            if strict_elapsed >= getattr(self, "sell_strict_timeout_ms", 2500):
                raise SellStrictBudgetExhausted("sell_strict_timeout_before_grid")

        timeout_ms = getattr(self, "detection_timeout_ms", 8000)
        if elapsed_ms > timeout_ms:
            raise visual_detector.OCRDetectionAborted("ocr_detection_timeout")

        max_calls = getattr(self, "max_total_ocr_calls", 120)
        if max_calls and getattr(self, "_ocr_calls_count", 0) > max_calls:
            raise visual_detector.OCRDetectionAborted("ocr_call_limit_exceeded")

    def patched_run_detection_pass(self, *args, **kwargs):
        # Signature after self:
        # img_array, candidate_bands, target_price, target_quantity,
        # panel_tuple, columns_tuple, section_y_min, section_y_max,
        # result, window_rect, manual_region=False, is_fallback=False, order_tick=0.0
        result = args[8] if len(args) > 8 else kwargs.get("result")
        manual_region = bool(kwargs.get("manual_region", False))
        is_fallback = bool(kwargs.get("is_fallback", False))
        is_sell = bool(result and result.get("_order_side") == "sell")

        if is_sell and manual_region and is_fallback:
            debug = result.setdefault("debug", {})
            debug["visual_ocr_sell_full_region_skipped"] = True
            debug["visual_ocr_sell_grid_skip_reason"] = "full_region_pass_skipped_to_reserve_grid_budget"
            return []

        if is_sell and manual_region and not is_fallback:
            import time
            self._ocr_budget_phase = "sell_strict"
            self._ocr_budget_phase_start_time = time.time()
            self._ocr_budget_phase_start_calls = getattr(self, "_ocr_calls_count", 0)
            try:
                return original_run_detection_pass(self, *args, **kwargs)
            except SellStrictBudgetExhausted as exc:
                debug = result.setdefault("debug", {})
                debug["visual_ocr_strict_timeout"] = True
                debug["visual_ocr_strict_abort_reason"] = str(exc)
                debug["visual_ocr_strict_elapsed_ms"] = int((time.time() - self._ocr_budget_phase_start_time) * 1000)
                debug["visual_ocr_strict_ocr_calls"] = max(0, getattr(self, "_ocr_calls_count", 0) - self._ocr_budget_phase_start_calls)
                debug["visual_ocr_sell_grid_enabled"] = True
                debug["visual_ocr_sell_grid_skip_reason"] = "strict_budget_exhausted_falling_through_to_grid"
                return []
            finally:
                self._ocr_budget_phase = None

        return original_run_detection_pass(self, *args, **kwargs)

    def patched_run_sell_grid(self, *args, **kwargs):
        result = args[12] if len(args) > 12 else kwargs.get("result")
        if result is not None:
            debug = result.setdefault("debug", {})
            debug["visual_ocr_sell_grid_enabled"] = True
            debug["visual_ocr_sell_grid_executed"] = True
            debug["visual_ocr_sell_grid_fallback"] = True
            elapsed = debug.get("elapsed_ms", 0)
            timeout = getattr(self, "detection_timeout_ms", 8000)
            debug["visual_ocr_remaining_budget_before_grid_ms"] = max(0, timeout - int(elapsed or 0))
            debug["visual_ocr_sell_grid_budget_ms"] = getattr(self, "sell_grid_reserved_timeout_ms", 4000)
        self._ocr_budget_phase = "sell_grid"
        try:
            return original_run_sell_grid(self, *args, **kwargs)
        finally:
            self._ocr_budget_phase = None
            if result is not None:
                debug = result.setdefault("debug", {})
                debug.setdefault("visual_ocr_sell_grid_executed", True)
                debug.setdefault("visual_ocr_sell_grid_fallback", True)

    cls.__init__ = patched_init
    cls._check_limits = patched_check_limits
    cls._run_detection_pass = patched_run_detection_pass
    cls._run_sell_manual_grid_fallback = patched_run_sell_grid
    cls._sell_budget_hotfix_installed = True
    cls._SellStrictBudgetExhausted = SellStrictBudgetExhausted


_install_visual_ocr_sell_budget_hotfix()
