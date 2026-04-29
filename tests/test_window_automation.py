"""
Tests for core/window_automation.py — EVEWindowAutomation.

Covers:
  1. enabled=False → status=disabled, no pywinauto touched
  2. dry_run=True → status=dry_run, steps simulated, no OS calls
  3. enabled=True, dry_run=False, no pywinauto → partial/error with clear message
  4. execute_quick_order_update returns dict with all required keys
  5. no final_confirm step present in steps_executed
  6. clipboard_set=False when disabled; not set in dry_run result
  7. recommended_price_text preserved in result
  8. steps_skipped contains NO_CONFIRM_BY_DESIGN in real mode
  9. result enabled/dry_run fields mirror config
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.window_automation import EVEWindowAutomation

_REQUIRED_KEYS = {
    "status", "enabled", "dry_run", "steps_executed", "steps_skipped",
    "errors", "window_found", "window_title", "focused", "clipboard_set",
    "recommended_price_text", "delays",
}

_CFG_DISABLED = {
    "enabled": False, "dry_run": True, "confirm_required": True,
    "open_market_delay_ms": 0, "focus_client_delay_ms": 0,
    "paste_price_delay_ms": 0, "post_action_delay_ms": 0,
    "restore_clipboard_after": False, "client_window_title_contains": "EVE",
    "use_pywinauto": False, "use_pyautogui_fallback": False, "max_attempts": 1,
}

_CFG_DRY_RUN = {**_CFG_DISABLED, "enabled": True, "dry_run": True}

_CFG_REAL = {**_CFG_DISABLED, "enabled": True, "dry_run": False,
             "use_pywinauto": False, "use_pyautogui_fallback": False}


class TestEVEWindowAutomationDisabled(unittest.TestCase):

    def setUp(self):
        self.auto = EVEWindowAutomation(_CFG_DISABLED)

    def test_status_is_disabled(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        self.assertEqual(result["status"], "disabled")

    def test_clipboard_not_set_when_disabled(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        self.assertFalse(result["clipboard_set"])

    def test_window_not_searched_when_disabled(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        self.assertFalse(result["window_found"])

    def test_enabled_flag_in_result_is_false(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        self.assertFalse(result["enabled"])

    def test_all_required_keys_present(self):
        result = self.auto.execute_quick_order_update({}, "999")
        for key in _REQUIRED_KEYS:
            self.assertIn(key, result, f"key '{key}' missing from result")

    def test_recommended_price_text_preserved(self):
        price = "12540.50"
        result = self.auto.execute_quick_order_update({}, price)
        self.assertEqual(result["recommended_price_text"], price)


class TestEVEWindowAutomationDryRun(unittest.TestCase):

    def setUp(self):
        self.auto = EVEWindowAutomation(_CFG_DRY_RUN)

    def test_status_is_dry_run(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        self.assertEqual(result["status"], "dry_run")

    def test_steps_executed_contains_would_steps(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        combined = " ".join(result["steps_executed"])
        self.assertIn("would_", combined)

    def test_no_confirm_in_steps_executed_dry_run(self):
        result = self.auto.execute_quick_order_update({}, "1595.90")
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower(),
                             f"confirm action must never be in steps_executed: {step}")

    def test_clipboard_set_false_in_dry_run(self):
        # dry_run must not actually set clipboard
        result = self.auto.execute_quick_order_update({}, "1595.90")
        self.assertFalse(result["clipboard_set"])

    def test_no_pywinauto_called_in_dry_run(self):
        # Even if pywinauto is available, dry_run must not call it
        with patch.dict("sys.modules", {"pywinauto": None}):
            result = self.auto.execute_quick_order_update({}, "1595.90")
        # Should still complete as dry_run with no errors from missing pywinauto
        self.assertEqual(result["status"], "dry_run")

    def test_all_required_keys_present(self):
        result = self.auto.execute_quick_order_update({}, "999")
        for key in _REQUIRED_KEYS:
            self.assertIn(key, result, f"key '{key}' missing from result")

    def test_recommended_price_text_preserved(self):
        price = "5000"
        result = self.auto.execute_quick_order_update({}, price)
        self.assertEqual(result["recommended_price_text"], price)

    def test_enabled_dry_run_flags_in_result(self):
        result = self.auto.execute_quick_order_update({}, "100")
        self.assertTrue(result["enabled"])
        self.assertTrue(result["dry_run"])


class TestEVEWindowAutomationRealNoPywinauto(unittest.TestCase):
    """Real mode with no pywinauto/pyautogui backend — must report error clearly."""

    def setUp(self):
        self.auto = EVEWindowAutomation(_CFG_REAL)

    def test_status_is_error_or_partial_without_backend(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False), \
             patch("core.window_automation._PYAUTOGUI_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, "999")
        self.assertIn(result["status"], ("error", "partial"))

    def test_errors_contain_pywinauto_message(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False), \
             patch("core.window_automation._PYAUTOGUI_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, "999")
        combined_errors = " ".join(result["errors"])
        self.assertIn("pywinauto", combined_errors.lower())

    def test_no_final_confirm_in_steps_executed_real_mode(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False), \
             patch("core.window_automation._PYAUTOGUI_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, "999")
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower(),
                             f"confirm action must never be in steps_executed: {step}")

    def test_no_confirm_skipped_contains_by_design(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, "999")
        combined_skipped = " ".join(result["steps_skipped"])
        self.assertIn("DESIGN", combined_skipped,
                      "steps_skipped must note confirm is skipped by design")

    def test_clipboard_set_attempted_in_real_mode(self):
        # Qt is available in test environment so clipboard should succeed
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, "1234")
        # clipboard_set should be True if Qt clipboard works
        # (may be False if Qt not headless-safe, but should not raise)
        self.assertIsInstance(result["clipboard_set"], bool)

    def test_all_required_keys_present_real(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, "999")
        for key in _REQUIRED_KEYS:
            self.assertIn(key, result, f"key '{key}' missing from result")

    def test_recommended_price_text_preserved_real(self):
        price = "4999.90"
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = self.auto.execute_quick_order_update({}, price)
        self.assertEqual(result["recommended_price_text"], price)


class TestFinalConfirmNeverExecuted(unittest.TestCase):
    """Verify confirm action is never in steps_executed across all modes."""

    def _check_no_confirm(self, cfg, label):
        auto = EVEWindowAutomation(cfg)
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = auto.execute_quick_order_update({}, "500")
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower(),
                             f"[{label}] confirm must never be in steps_executed: {step}")

    def test_no_confirm_when_disabled(self):
        self._check_no_confirm(_CFG_DISABLED, "disabled")

    def test_no_confirm_when_dry_run(self):
        self._check_no_confirm(_CFG_DRY_RUN, "dry_run")

    def test_no_confirm_when_real(self):
        self._check_no_confirm(_CFG_REAL, "real")


if __name__ == "__main__":
    unittest.main()
