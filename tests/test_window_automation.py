"""
Tests for core/window_automation.py — EVEWindowAutomation + list_candidate_windows.

Covers:
  1.  enabled=False → status=disabled, no pywinauto touched
  2.  dry_run=True → status=dry_run, steps simulated, no OS calls
  3.  enabled=True, dry_run=False, no pywinauto → partial/error with clear message
  4.  execute_quick_order_update returns dict with all required keys
  5.  no final_confirm step present in steps_executed
  6.  clipboard_set=False when disabled; not set in dry_run result
  7.  recommended_price_text preserved in result
  8.  steps_skipped contains NO_CONFIRM_BY_DESIGN in real mode
  9.  result enabled/dry_run fields mirror config
  10. list_candidate_windows returns [] when pywinauto not available
  11. _score_window marks EVE iT as is_self_app
  12. selected_window_handle bypasses title search
  13. require_window_selection without selection → error, no focus
  14. selected_window dry-run reports window_source=selected_handle
  15. base_result has new keys (window_source, selected_window_handle, etc.)
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.window_automation import (
    EVEWindowAutomation, list_candidate_windows, _score_window,
)

_REQUIRED_KEYS = {
    "status", "enabled", "dry_run", "steps_executed", "steps_skipped",
    "errors", "window_found", "window_title", "focused", "clipboard_set",
    "recommended_price_text", "delays",
    "window_source", "selected_window_handle", "selected_window_title",
    "candidate_windows_count", "candidate_windows",
    "experimental_paste_enabled", "paste_into_focused_window",
    "clear_price_field_before_paste", "paste_method",
    "price_pasted", "never_confirm_final_order",
}

_CFG_DISABLED = {
    "enabled": False, "dry_run": True, "confirm_required": True,
    "open_market_delay_ms": 0, "focus_client_delay_ms": 0,
    "paste_price_delay_ms": 0, "post_action_delay_ms": 0,
    "restore_clipboard_after": False, "client_window_title_contains": "EVE",
    "use_pywinauto": False, "use_pyautogui_fallback": False, "max_attempts": 1,
    "require_window_selection": True,
    "allow_title_fallback_without_selection": False,
    "exclude_self_app_windows": True,
}

_CFG_DRY_RUN = {**_CFG_DISABLED, "enabled": True, "dry_run": True}

_CFG_REAL = {**_CFG_DISABLED, "enabled": True, "dry_run": False,
             "use_pywinauto": False, "use_pyautogui_fallback": False}

_CFG_REAL_ALLOW_FB = {**_CFG_REAL,
                      "require_window_selection": False,
                      "allow_title_fallback_without_selection": True}


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
        # Use config that allows fallback to title search (so pywinauto path is reached)
        auto = EVEWindowAutomation(_CFG_REAL_ALLOW_FB)
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False), \
             patch("core.window_automation._PYAUTOGUI_AVAILABLE", False):
            result = auto.execute_quick_order_update({}, "999")
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


# ---------------------------------------------------------------------------
# list_candidate_windows tests
# ---------------------------------------------------------------------------
class TestListCandidateWindows(unittest.TestCase):

    def test_returns_empty_without_pywinauto(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = list_candidate_windows()
        self.assertEqual(result, [])

    def test_returns_list_type(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = list_candidate_windows()
        self.assertIsInstance(result, list)


class TestScoreWindow(unittest.TestCase):

    def test_eve_iT_is_self_app(self):
        score, is_self = _score_window("EVE iT Market Command")
        self.assertTrue(is_self, "EVE iT should be marked as self-app")
        self.assertLess(score, 0, "self-app should have negative score")

    def test_market_command_is_self_app(self):
        _, is_self = _score_window("Market Command — Mis Pedidos")
        self.assertTrue(is_self)

    def test_quick_order_update_is_self_app(self):
        _, is_self = _score_window("Quick Order Update — Tritanium")
        self.assertTrue(is_self)

    def test_eve_character_window_high_score(self):
        score, is_self = _score_window("EVE - Nina Herrera")
        self.assertFalse(is_self)
        self.assertGreaterEqual(score, 100)

    def test_eve_online_window_good_score(self):
        score, is_self = _score_window("EVE Online")
        self.assertFalse(is_self)
        self.assertGreaterEqual(score, 80)

    def test_unrelated_window_zero_score(self):
        score, is_self = _score_window("Microsoft Word")
        self.assertFalse(is_self)
        self.assertEqual(score, 0)


# ---------------------------------------------------------------------------
# selected_window / require_window_selection tests
# ---------------------------------------------------------------------------
class TestSelectedWindowHandle(unittest.TestCase):

    def setUp(self):
        self._selected = {
            "handle":     99999,
            "title":      "EVE - Test Char",
            "class_name": "EVEWindow",
            "visible":    True,
            "is_self_app": False,
            "score":      100,
        }

    def test_dry_run_with_selected_window_reports_handle(self):
        auto = EVEWindowAutomation(_CFG_DRY_RUN)
        result = auto.execute_quick_order_update({}, "999", selected_window=self._selected)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["selected_window_handle"], 99999)
        self.assertEqual(result["selected_window_title"], "EVE - Test Char")
        self.assertEqual(result["window_source"], "selected_handle")

    def test_dry_run_without_selected_window_uses_title_search(self):
        auto = EVEWindowAutomation(_CFG_DRY_RUN)
        result = auto.execute_quick_order_update({}, "999", selected_window=None)
        self.assertEqual(result["window_source"], "title_search")

    def test_require_selection_no_window_returns_error(self):
        """require_window_selection=True and no selected window → error step."""
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            auto   = EVEWindowAutomation(_CFG_REAL)
            result = auto.execute_quick_order_update({}, "999", selected_window=None)
        combined_errors = " ".join(result["errors"])
        self.assertIn("no selected target window", combined_errors)
        self.assertFalse(result["focused"], "must not focus when no window selected")

    def test_require_selection_no_window_skips_window_search(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            auto   = EVEWindowAutomation(_CFG_REAL)
            result = auto.execute_quick_order_update({}, "999", selected_window=None)
        combined_skipped = " ".join(result["steps_skipped"])
        self.assertIn("no_selection", combined_skipped)

    def test_allow_fallback_without_selection_uses_title_search(self):
        """When require=False and allow_fallback=True, no selection → title search attempted."""
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            auto   = EVEWindowAutomation(_CFG_REAL_ALLOW_FB)
            result = auto.execute_quick_order_update({}, "999", selected_window=None)
        self.assertEqual(result["window_source"], "title_search")

    def test_selected_window_real_reports_source(self):
        """In real mode with a selected window, window_source should be selected_handle."""
        mock_win = MagicMock()
        mock_win.window_text.return_value = "EVE - Test Char"
        mock_win.set_focus = MagicMock()

        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True):
            auto   = EVEWindowAutomation({**_CFG_REAL, "use_pywinauto": True})
            result = auto.execute_quick_order_update({}, "999", selected_window=self._selected)

        self.assertEqual(result["window_source"], "selected_handle")

    def test_base_result_has_new_keys(self):
        result = EVEWindowAutomation._base_result("123")
        for key in ("window_source", "selected_window_handle", "selected_window_title",
                    "candidate_windows_count", "candidate_windows"):
            self.assertIn(key, result, f"new key '{key}' missing from _base_result")

    def test_all_required_keys_present_with_selection(self):
        auto   = EVEWindowAutomation(_CFG_DRY_RUN)
        result = auto.execute_quick_order_update({}, "999", selected_window=self._selected)
        for key in _REQUIRED_KEYS:
            self.assertIn(key, result, f"key '{key}' missing")

    def test_no_confirm_with_selected_window_real(self):
        mock_win = MagicMock()
        mock_win.window_text.return_value = "EVE - Test Char"
        mock_win.set_focus = MagicMock()

        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True):
            auto   = EVEWindowAutomation({**_CFG_REAL, "use_pywinauto": True})
            result = auto.execute_quick_order_update({}, "999", selected_window=self._selected)

        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower(),
                             f"confirm must never be in steps_executed: {step}")
        combined_skipped = " ".join(result["steps_skipped"])
        self.assertIn("DESIGN", combined_skipped)


# ---------------------------------------------------------------------------
# Experimental Paste tests
# ---------------------------------------------------------------------------
class TestExperimentalPaste(unittest.TestCase):

    def setUp(self):
        self._cfg_base = {
            "enabled": True, "dry_run": False, "use_pywinauto": True,
            "experimental_paste_enabled": True,
            "paste_into_focused_window": True,
            "clear_price_field_before_paste": True,
            "paste_method": "ctrl+v",
            "pre_paste_delay_ms": 0,
            "client_window_title_contains": "EVE",
            "require_window_selection": False,
            "allow_title_fallback_without_selection": True,
        }
        self._order = {"order_id": 1}

    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("core.window_automation.EVEWindowAutomation._find_via_pywinauto")
    @patch("pywinauto.keyboard.send_keys")
    def test_paste_ctrl_v_executed(self, mock_keys, mock_find, mock_focus):
        mock_find.return_value = MagicMock()
        auto = EVEWindowAutomation(self._cfg_base)
        result = auto.execute_quick_order_update(self._order, "100.50")
        
        self.assertTrue(result["price_pasted"])
        self.assertIn("sent_ctrl_a", result["steps_executed"])
        self.assertIn("sent_ctrl_v", result["steps_executed"])
        # Check mock calls: ^a then ^v
        self.assertEqual(mock_keys.call_count, 2)
        mock_keys.assert_any_call("^a")
        mock_keys.assert_any_call("^v")

    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("core.window_automation.EVEWindowAutomation._find_via_pywinauto")
    @patch("pywinauto.keyboard.send_keys")
    def test_paste_typewrite_executed(self, mock_keys, mock_find, mock_focus):
        cfg = {**self._cfg_base, "paste_method": "typewrite"}
        mock_find.return_value = MagicMock()
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(self._order, "100.50")
        
        self.assertTrue(result["price_pasted"])
        self.assertIn("typewrite_price", result["steps_executed"])
        mock_keys.assert_any_call("100.50")

    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("core.window_automation.EVEWindowAutomation._find_via_pywinauto")
    def test_paste_skipped_if_disabled(self, mock_find, mock_focus):
        cfg = {**self._cfg_base, "experimental_paste_enabled": False}
        mock_find.return_value = MagicMock()
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(self._order, "100.50")
        
        self.assertFalse(result["price_pasted"])
        self.assertIn("experimental_paste_disabled", result["steps_skipped"])

    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("core.window_automation.EVEWindowAutomation._find_via_pywinauto")
    def test_paste_skipped_if_paste_into_focused_false(self, mock_find, mock_focus):
        cfg = {**self._cfg_base, "paste_into_focused_window": False}
        mock_find.return_value = MagicMock()
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(self._order, "100.50")
        
        self.assertFalse(result["price_pasted"])
        self.assertIn("paste_into_focused_window_disabled", result["steps_skipped"])

    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("core.window_automation.EVEWindowAutomation._find_via_pywinauto")
    def test_safety_never_confirms_with_paste_enabled(self, mock_find, mock_focus):
        mock_find.return_value = MagicMock()
        auto = EVEWindowAutomation(self._cfg_base)
        result = auto.execute_quick_order_update(self._order, "100.50")
        
        for step in result["steps_executed"]:
            sl = step.lower()
            self.assertNotIn("confirm", sl)
            self.assertNotIn("accept", sl)
            self.assertNotIn("submit", sl)
            self.assertNotIn("enter", sl)
            self.assertNotIn("click", sl)
        
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))


if __name__ == "__main__":
    unittest.main()
