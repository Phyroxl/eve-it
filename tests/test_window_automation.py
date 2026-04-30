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
    "recommended_price_text", "delays", "config",
    "window_source", "selected_window_handle", "selected_window_title",
    "candidate_windows_count", "candidate_windows",
    "experimental_paste_enabled", "paste_into_focused_window",
    "clear_price_field_before_paste", "paste_method",
    "price_pasted", "never_confirm_final_order",
    # Phase 3: Modify Order
    "modify_order_step_enabled", "modify_order_strategy",
    "modify_order_prepare_attempted", "modify_order_dialog_verified",
    "require_modify_dialog_ready", "paste_without_modify_dialog_verification",
    "modify_order_warning",
    # Phase 3B: hotkey_experimental
    "modify_order_hotkey_configured", "allow_unverified_modify_order_paste",
    # Phase 3C: visual_ocr
    "visual_ocr_enabled", "visual_ocr_status", "visual_ocr_candidates_count",
    "visual_ocr_matched_price", "visual_ocr_matched_quantity",
    "visual_ocr_row_x", "visual_ocr_row_y",
    # Phase 3C hardening: new diagnostic fields
    "visual_ocr_blue_bands_found", "visual_ocr_section_used",
    "visual_ocr_section_y_min", "visual_ocr_section_y_max",
    "visual_ocr_own_marker_matched", "visual_ocr_price_text",
    "visual_ocr_quantity_text", "visual_ocr_debug_overlay_path",
    # Phase 3E: robust context menu
    "visual_ocr_rc_attempts", "visual_ocr_rc_attempt_details",
    "visual_ocr_context_menu_open",
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
        self.assertGreaterEqual(score, 90)

    def test_eve_online_window_good_score(self):
        score, is_self = _score_window("EVE Online")
        self.assertFalse(is_self)
        self.assertGreaterEqual(score, 40)

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
            "enabled": True,
            "dry_run": False,
            "experimental_paste_enabled": True,
            "paste_into_focused_window": True,
            "clear_price_field_before_paste": True,
            "pre_paste_delay_ms": 0,
            "paste_price_delay_ms": 0,
            "client_window_title_contains": "EVE",
            "require_window_selection": True,
            "allow_title_fallback_without_selection": False,
        }
        self._order = {"order_id": 1}
        self._selected = {"handle": 12345, "title": "EVE - Test"}

    @patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle")
    @patch("core.window_automation.EVEWindowAutomation._connect_by_handle")
    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("pywinauto.keyboard.send_keys")
    def test_paste_ctrl_v_executed(self, mock_keys, mock_focus, mock_conn, mock_fg):
        mock_conn.return_value = MagicMock()
        mock_fg.return_value = 12345
        auto = EVEWindowAutomation(self._cfg_base)
        result = auto.execute_quick_order_update(self._order, "100.50", selected_window=self._selected)
        
        self.assertTrue(result["price_pasted"], f"Price should be pasted, reason: {result.get('paste_block_reason')}")
        self.assertIn("sent_ctrl_a", result["steps_executed"])
        self.assertIn("sent_ctrl_v", result["steps_executed"])
        self.assertEqual(mock_keys.call_count, 2)
        mock_keys.assert_any_call("^a")
        mock_keys.assert_any_call("^v")

    @patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle")
    @patch("core.window_automation.EVEWindowAutomation._connect_by_handle")
    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    @patch("pywinauto.keyboard.send_keys")
    def test_paste_typewrite_executed(self, mock_keys, mock_focus, mock_conn, mock_fg):
        cfg = {**self._cfg_base, "paste_method": "typewrite"}
        mock_conn.return_value = MagicMock()
        mock_fg.return_value = 12345
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(self._order, "100.50", selected_window=self._selected)
        
        self.assertTrue(result["price_pasted"], f"Price should be pasted, reason: {result.get('paste_block_reason')}")
        self.assertIn("typewrite_price", result["steps_executed"])
        mock_keys.assert_any_call("100.50")

    @patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle")
    @patch("core.window_automation.EVEWindowAutomation._connect_by_handle")
    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    def test_paste_skipped_if_disabled(self, mock_focus, mock_conn, mock_fg):
        cfg = {**self._cfg_base, "experimental_paste_enabled": False}
        mock_conn.return_value = MagicMock()
        mock_fg.return_value = 12345
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(self._order, "100.50", selected_window=self._selected)
        
        self.assertFalse(result["price_pasted"])
        self.assertIn("experimental_paste_disabled", result["steps_skipped"])

    @patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle")
    @patch("core.window_automation.EVEWindowAutomation._connect_by_handle")
    @patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True)
    def test_paste_skipped_if_paste_into_focused_false(self, mock_focus, mock_conn, mock_fg):
        cfg = {**self._cfg_base, "paste_into_focused_window": False}
        mock_conn.return_value = MagicMock()
        mock_fg.return_value = 12345
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(self._order, "100.50", selected_window=self._selected)
        
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


# ---------------------------------------------------------------------------
# Phase 3: Modify Order preparation tests
# ---------------------------------------------------------------------------
class TestModifyOrderPhase(unittest.TestCase):
    """Tests for Phase 3 — prepare_modify_order_dialog."""

    _SELECTED = {
        "handle": 99999, "title": "EVE - Test",
        "class_name": "EVEWindow", "visible": True,
        "is_self_app": False, "score": 100,
    }

    def _cfg(self, **overrides):
        base = {
            "enabled": True, "dry_run": False, "use_pywinauto": True,
            "require_window_selection": False,
            "allow_title_fallback_without_selection": True,
            "experimental_paste_enabled": True,
            "paste_into_focused_window": True,
            "clear_price_field_before_paste": False,
            "paste_method": "ctrl+v",
            "pre_paste_delay_ms": 0,
            "open_market_delay_ms": 0,
            "focus_client_delay_ms": 0,
            "paste_price_delay_ms": 0,
            "post_action_delay_ms": 0,
            "modify_order_delay_ms": 0,
            "modify_order_step_enabled": False,
            "modify_order_strategy": "manual_focus_guard",
            "require_modify_dialog_ready": False,
            "paste_without_modify_dialog_verification": True,
            "never_confirm_final_order": True,
        }
        base.update(overrides)
        return base

    def _run(self, cfg):
        mock_win = MagicMock()
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True), \
             patch("pywinauto.keyboard.send_keys"):
            auto = EVEWindowAutomation(cfg)
            return auto.execute_quick_order_update({}, "100", selected_window=self._SELECTED)

    # -- step disabled (default safe behavior) --------------------------------

    def test_disabled_records_safe_skip(self):
        result = self._run(self._cfg(modify_order_step_enabled=False))
        self.assertIn("modify_order_prepare_skipped_safe_default",
                      result["steps_skipped"])

    def test_disabled_prepare_attempted_false(self):
        result = self._run(self._cfg(modify_order_step_enabled=False))
        self.assertFalse(result["modify_order_prepare_attempted"])

    def test_disabled_does_not_block_paste(self):
        result = self._run(self._cfg(modify_order_step_enabled=False))
        self.assertNotIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])

    # -- manual_focus_guard strategy ------------------------------------------

    def test_manual_focus_guard_records_attempted(self):
        result = self._run(self._cfg(modify_order_step_enabled=True))
        self.assertTrue(result["modify_order_prepare_attempted"])
        self.assertIn("modify_order_prepare_attempted_manual_focus_guard",
                      " ".join(result["steps_executed"]))

    def test_manual_focus_guard_dialog_not_verified(self):
        result = self._run(self._cfg(modify_order_step_enabled=True))
        self.assertFalse(result["modify_order_dialog_verified"])

    def test_paste_allowed_when_paste_without_verify_true(self):
        result = self._run(self._cfg(
            modify_order_step_enabled=True,
            paste_without_modify_dialog_verification=True,
        ))
        self.assertNotIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])

    def test_paste_blocked_when_paste_without_verify_false(self):
        result = self._run(self._cfg(
            modify_order_step_enabled=True,
            paste_without_modify_dialog_verification=False,
        ))
        self.assertIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])
        self.assertFalse(result["price_pasted"])

    # -- require_modify_dialog_ready ------------------------------------------

    def test_require_ready_blocks_paste(self):
        result = self._run(self._cfg(
            modify_order_step_enabled=True,
            require_modify_dialog_ready=True,
        ))
        self.assertIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])

    def test_require_ready_overrides_paste_without_verify_true(self):
        result = self._run(self._cfg(
            modify_order_step_enabled=True,
            require_modify_dialog_ready=True,
            paste_without_modify_dialog_verification=True,
        ))
        self.assertIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])

    # -- final confirm always absent ------------------------------------------

    def test_final_confirm_never_executed_step_disabled(self):
        result = self._run(self._cfg(modify_order_step_enabled=False))
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower())

    def test_final_confirm_never_executed_step_enabled(self):
        result = self._run(self._cfg(modify_order_step_enabled=True))
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower())

    def test_final_confirm_never_executed_require_ready(self):
        result = self._run(self._cfg(
            modify_order_step_enabled=True, require_modify_dialog_ready=True,
        ))
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))

    # -- all new keys present -------------------------------------------------

    def test_new_phase3_keys_in_result(self):
        auto = EVEWindowAutomation(self._cfg())
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = auto.execute_quick_order_update({}, "100")
        for key in ("modify_order_step_enabled", "modify_order_strategy",
                    "modify_order_prepare_attempted", "modify_order_dialog_verified",
                    "require_modify_dialog_ready", "paste_without_modify_dialog_verification",
                    "modify_order_warning", "modify_order_hotkey_configured",
                    "allow_unverified_modify_order_paste"):
            self.assertIn(key, result, f"Phase 3 key '{key}' missing from result")


# ---------------------------------------------------------------------------
# Phase 3B: hotkey_experimental strategy tests
# ---------------------------------------------------------------------------
class TestHotkeyExperimentalStrategy(unittest.TestCase):
    """Tests for Phase 3B — hotkey_experimental modify-order strategy."""

    _SELECTED = {
        "handle": 99999, "title": "EVE - Test",
        "class_name": "EVEWindow", "visible": True,
        "is_self_app": False, "score": 100,
    }

    def _cfg(self, **overrides):
        base = {
            "enabled": True, "dry_run": False, "use_pywinauto": True,
            "require_window_selection": False,
            "allow_title_fallback_without_selection": True,
            "experimental_paste_enabled": True,
            "paste_into_focused_window": True,
            "clear_price_field_before_paste": False,
            "paste_method": "ctrl+v",
            "pre_paste_delay_ms": 0,
            "open_market_delay_ms": 0,
            "focus_client_delay_ms": 0,
            "paste_price_delay_ms": 0,
            "post_action_delay_ms": 0,
            "modify_order_delay_ms": 0,
            "modify_order_step_enabled": True,
            "modify_order_strategy": "hotkey_experimental",
            "modify_order_hotkey": "",
            "modify_order_verify_window_title_contains": "Modify Order",
            "modify_order_post_hotkey_delay_ms": 0,
            "require_modify_dialog_ready": False,
            "paste_without_modify_dialog_verification": True,
            "allow_unverified_modify_order_paste": False,
            "never_confirm_final_order": True,
        }
        base.update(overrides)
        return base

    def _run(self, cfg, verify_result=False):
        """Run automation with mocked focus+connect+verify."""
        mock_win = MagicMock()
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True), \
             patch("pywinauto.keyboard.send_keys"), \
             patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle",
                   return_value=99999), \
             patch("core.window_automation.EVEWindowAutomation._verify_modify_order_dialog",
                   return_value=verify_result):
            auto = EVEWindowAutomation(cfg)
            return auto.execute_quick_order_update({}, "100", selected_window=self._SELECTED)

    # -- empty hotkey (default unconfigured) ----------------------------------

    def test_empty_hotkey_records_missing(self):
        result = self._run(self._cfg(modify_order_hotkey=""))
        self.assertIn("modify_order_hotkey_missing", result["steps_skipped"])

    def test_empty_hotkey_dialog_not_verified(self):
        result = self._run(self._cfg(modify_order_hotkey=""))
        self.assertFalse(result["modify_order_dialog_verified"])

    def test_empty_hotkey_no_hotkey_step_in_executed(self):
        result = self._run(self._cfg(modify_order_hotkey=""))
        self.assertNotIn("sent_modify_order_hotkey", result["steps_executed"])

    def test_empty_hotkey_blocks_paste_by_default(self):
        result = self._run(self._cfg(
            modify_order_hotkey="", allow_unverified_modify_order_paste=False
        ))
        self.assertIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])
        self.assertFalse(result["price_pasted"])

    # -- hotkey configured, verification fails --------------------------------

    def test_hotkey_sent_when_configured(self):
        result = self._run(self._cfg(modify_order_hotkey="^e"), verify_result=False)
        self.assertIn("sent_modify_order_hotkey", result["steps_executed"])

    def test_hotkey_attempts_verification(self):
        result = self._run(self._cfg(modify_order_hotkey="^e"), verify_result=False)
        self.assertIn("modify_order_dialog_verification_attempted", result["steps_executed"])

    def test_hotkey_blocks_paste_if_verification_fails(self):
        result = self._run(self._cfg(
            modify_order_hotkey="^e", allow_unverified_modify_order_paste=False
        ), verify_result=False)
        self.assertIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])
        self.assertFalse(result["price_pasted"])

    # -- hotkey configured, verification succeeds (mocked) --------------------

    def test_hotkey_dialog_verified_when_mock_passes(self):
        result = self._run(self._cfg(modify_order_hotkey="^e"), verify_result=True)
        self.assertTrue(result["modify_order_dialog_verified"])
        self.assertIn("modify_order_dialog_verified", result["steps_executed"])

    def test_hotkey_paste_allowed_when_verified(self):
        result = self._run(self._cfg(
            modify_order_hotkey="^e", allow_unverified_modify_order_paste=False
        ), verify_result=True)
        self.assertNotIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])
        self.assertTrue(result["price_pasted"])

    def test_hotkey_verified_no_confirm(self):
        result = self._run(self._cfg(
            modify_order_hotkey="^e", allow_unverified_modify_order_paste=False
        ), verify_result=True)
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower(),
                             f"confirm must never be in steps_executed: {step}")
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))

    # -- manual_focus_guard is unaffected ------------------------------------

    def test_manual_focus_guard_no_hotkey_sent(self):
        cfg = self._cfg(
            modify_order_strategy="manual_focus_guard",
            modify_order_hotkey="^e",
            paste_without_modify_dialog_verification=True,
        )
        result = self._run(cfg)
        self.assertNotIn("sent_modify_order_hotkey", result["steps_executed"])
        self.assertIn("modify_order_prepare_attempted_manual_focus_guard",
                      " ".join(result["steps_executed"]))

    # -- final confirm always absent -----------------------------------------

    def test_final_confirm_never_executed_empty_hotkey(self):
        result = self._run(self._cfg(modify_order_hotkey=""))
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower())

    def test_final_confirm_never_executed_with_hotkey_verified(self):
        result = self._run(self._cfg(modify_order_hotkey="^e"), verify_result=True)
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower())

    def test_hotkey_configured_flag_true(self):
        result = self._run(self._cfg(modify_order_hotkey="^e"))
        self.assertTrue(result["modify_order_hotkey_configured"])

    def test_hotkey_configured_flag_false_when_empty(self):
        result = self._run(self._cfg(modify_order_hotkey=""))
        self.assertFalse(result["modify_order_hotkey_configured"])


# ---------------------------------------------------------------------------
# Phase 3C: visual_ocr strategy tests
# ---------------------------------------------------------------------------
class TestVisualOCRStrategy(unittest.TestCase):
    """Tests for Phase 3C — visual_ocr modify-order strategy."""

    _SELECTED = {
        "handle": 99999, "title": "EVE - Test",
        "class_name": "EVEWindow", "visible": True,
        "is_self_app": False, "score": 100,
    }

    def _cfg(self, **overrides):
        base = {
            "enabled": True, "dry_run": False, "use_pywinauto": True,
            "require_window_selection": False,
            "allow_title_fallback_without_selection": True,
            "experimental_paste_enabled": True,
            "paste_into_focused_window": True,
            "clear_price_field_before_paste": False,
            "paste_method": "ctrl+v",
            "pre_paste_delay_ms": 0,
            "open_market_delay_ms": 0,
            "focus_client_delay_ms": 0,
            "paste_price_delay_ms": 0,
            "post_action_delay_ms": 0,
            "modify_order_delay_ms": 0,
            "modify_order_step_enabled": True,
            "modify_order_strategy": "visual_ocr",
            "visual_ocr_enabled": True,
            "visual_ocr_require_unique_match": True,
            "visual_ocr_match_price": True,
            "visual_ocr_match_quantity": True,
            "visual_ocr_require_own_order_marker": True,
            "visual_ocr_side_section_required": True,
            "visual_ocr_allow_unverified_paste": False,
            "visual_ocr_context_menu_delay_ms": 0,
            "visual_ocr_modify_dialog_delay_ms": 0,
            "visual_ocr_right_click_max_attempts": 3,
            "visual_ocr_right_click_retry_delay_ms": 0,
            "visual_ocr_pre_right_click_hover_ms": 0,
            "visual_ocr_pre_right_click_left_click": False,
            "visual_ocr_right_click_candidate_offsets": [
                {"name": "qty_left", "x_offset": 20, "y_offset": 0}
            ],
            "visual_ocr_verify_context_menu_open": True,
            "visual_ocr_menu_click_mode": "relative_to_right_click",
            "visual_ocr_modify_menu_offset_x": 65,
            "visual_ocr_modify_menu_offset_y": 37,
            "visual_ocr_debug_save_screenshot": False,
            "visual_ocr_debug_dir": "data/debug/visual_ocr",
            "never_confirm_final_order": True,
        }
        base.update(overrides)
        return base

    def _detection_unique(self):
        return {
            "status": "unique_match", "error": None,
            "candidates_count": 1, "row_center_x": 200, "row_center_y": 150,
            "matched_price": True, "matched_quantity": True,
            "matched_own_marker": True, "matched_side_section": True,
            "price_text": "1595.90", "quantity_text": "10",
            "debug": {
                "blue_bands_found": 1, "section_used": "sell",
                "section_y_min": 44, "section_y_max": 116,
                "price_col_x_min": 192, "price_col_x_max": 272,
                "qty_col_x_min": 152, "qty_col_x_max": 208,
                "candidate_bands": [(145, 160)], "matched_band": (145, 160),
            },
        }

    def _detection_not_found(self):
        return {
            "status": "not_found", "error": None,
            "candidates_count": 0, "row_center_x": None, "row_center_y": None,
            "matched_price": False, "matched_quantity": False,
            "matched_own_marker": False, "matched_side_section": False,
            "price_text": None, "quantity_text": None,
            "debug": {
                "blue_bands_found": 0, "section_used": "sell",
                "section_y_min": 44, "section_y_max": 116,
                "price_col_x_min": 192, "price_col_x_max": 272,
                "qty_col_x_min": 152, "qty_col_x_max": 208,
                "candidate_bands": [], "matched_band": None,
            },
        }

    def _detection_ambiguous(self):
        return {
            "status": "ambiguous", "error": None,
            "candidates_count": 2, "row_center_x": None, "row_center_y": None,
            "matched_price": False, "matched_quantity": False,
            "matched_own_marker": False, "matched_side_section": False,
            "price_text": None, "quantity_text": None,
            "debug": {
                "blue_bands_found": 2, "section_used": "sell",
                "section_y_min": 44, "section_y_max": 116,
                "price_col_x_min": 192, "price_col_x_max": 272,
                "qty_col_x_min": 152, "qty_col_x_max": 208,
                "candidate_bands": [(10, 25), (50, 65)], "matched_band": None,
            },
        }

    def _detection_ocr_error(self):
        return {
            "status": "error", "error": "ocr_backend_unavailable",
            "candidates_count": 1, "row_center_x": None, "row_center_y": None,
            "matched_price": False, "matched_quantity": False,
            "matched_own_marker": False, "matched_side_section": False,
            "price_text": None, "quantity_text": None,
            "debug": {
                "blue_bands_found": 1, "section_used": "sell",
                "section_y_min": 44, "section_y_max": 116,
                "price_col_x_min": 192, "price_col_x_max": 272,
                "qty_col_x_min": 152, "qty_col_x_max": 208,
                "candidate_bands": [(10, 25)], "matched_band": None,
            },
        }

    def _run(self, cfg, detection=None, screenshot=None):
        """Run automation with all OS interactions mocked."""
        import numpy as np
        mock_win = MagicMock()
        if screenshot is None:
            screenshot = np.zeros((200, 400, 3), dtype="uint8")
        if detection is None:
            detection = self._detection_unique()

        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._get_window_rect",
                   return_value={"left": 0, "top": 0, "width": 400, "height": 200}), \
             patch("core.window_automation.EVEWindowAutomation._capture_window_screenshot",
                   return_value=screenshot), \
             patch("core.window_automation.EVEWindowAutomation._run_visual_ocr_detect",
                   return_value=detection), \
             patch("core.window_automation.EVEWindowAutomation._visual_ocr_right_click",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._visual_ocr_left_click",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._check_image_difference",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle",
                   return_value=99999), \
             patch("core.window_automation.EVEWindowAutomation._mouse_move"), \
             patch("core.window_automation.EVEWindowAutomation._mouse_click"), \
             patch("PIL.ImageGrab.grab", return_value=MagicMock()), \
             patch("pywinauto.keyboard.send_keys"):
            auto = EVEWindowAutomation(cfg)
            order = {"price": 1595.9, "volume_remain": 10, "is_buy_order": False}
            return auto.execute_quick_order_update(
                order, "1595.90", selected_window=self._SELECTED
            )

    # -- visual_ocr_enabled=False skips entirely and blocks paste -----------------

    def test_visual_ocr_disabled_in_cfg_skips(self):
        result = self._run(self._cfg(visual_ocr_enabled=False))
        self.assertIn("visual_ocr_disabled_in_config", result["steps_skipped"])

    def test_visual_ocr_disabled_blocks_paste(self):
        result = self._run(self._cfg(visual_ocr_enabled=False))
        self.assertIn("paste_skipped_modify_dialog_not_verified", result["steps_skipped"])
        self.assertFalse(result["price_pasted"])

    # -- ambiguous detection: no click, no paste ----------------------------------

    def test_ambiguous_no_click_no_paste(self):
        result = self._run(self._cfg(), detection=self._detection_ambiguous())
        skipped = " ".join(result["steps_skipped"])
        self.assertIn("visual_ocr_no_unique_match", skipped)
        self.assertIn("paste_skipped_visual_ocr_step_failed", skipped)
        self.assertFalse(result["price_pasted"])
        self.assertEqual(result["visual_ocr_status"], "ambiguous")
        self.assertEqual(result["visual_ocr_candidates_count"], 2)

    # -- ocr error detection: no click, no paste ----------------------------------

    def test_ocr_error_no_click_no_paste(self):
        result = self._run(self._cfg(), detection=self._detection_ocr_error())
        skipped = " ".join(result["steps_skipped"])
        self.assertIn("paste_skipped_visual_ocr_step_failed", skipped)
        self.assertFalse(result["price_pasted"])
        self.assertEqual(result["visual_ocr_status"], "error")

    # -- screenshot backend missing ----------------------------------------------

    def test_screenshot_failed_blocks_paste(self):
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", False), \
             patch("core.window_automation._PYAUTOGUI_AVAILABLE", False), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=MagicMock()), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._get_window_rect",
                   return_value={"left": 0, "top": 0, "width": 400, "height": 200}):
            auto = EVEWindowAutomation(self._cfg())
            order = {"price": 1595.9, "volume_remain": 10}
            result = auto.execute_quick_order_update(
                order, "1595.90", selected_window=self._SELECTED
            )
        self.assertEqual(result["visual_ocr_status"], "error_screenshot_failed")
        self.assertFalse(result["price_pasted"])

    # -- not_found detection blocks paste ----------------------------------------

    def test_not_found_blocks_paste(self):
        result = self._run(self._cfg(), detection=self._detection_not_found())
        skipped = " ".join(result["steps_skipped"])
        self.assertIn("visual_ocr_no_unique_match", skipped)
        self.assertIn("paste_skipped_visual_ocr_step_failed", skipped)
        self.assertFalse(result["price_pasted"])

    def test_not_found_status_in_result(self):
        result = self._run(self._cfg(), detection=self._detection_not_found())
        self.assertEqual(result["visual_ocr_status"], "not_found")

    # -- unique_match: clicks executed -------------------------------------------

    def test_unique_match_records_row_coords(self):
        result = self._run(self._cfg())
        self.assertEqual(result["visual_ocr_row_x"], 200)
        self.assertEqual(result["visual_ocr_row_y"], 150)

    def test_unique_match_records_match_status(self):
        result = self._run(self._cfg())
        self.assertEqual(result["visual_ocr_status"], "unique_match")

    def test_unique_match_right_click_called(self):
        import numpy as np
        mock_win = MagicMock()
        screenshot = np.zeros((200, 400, 3), dtype="uint8")
        mock_right_click = MagicMock(return_value=True)

        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._get_window_rect",
                   return_value={"left": 0, "top": 0, "width": 400, "height": 200}), \
             patch("core.window_automation.EVEWindowAutomation._capture_window_screenshot",
                   return_value=screenshot), \
             patch("core.window_automation.EVEWindowAutomation._run_visual_ocr_detect",
                   return_value=self._detection_unique()), \
             patch("core.window_automation.EVEWindowAutomation._visual_ocr_right_click",
                   mock_right_click), \
             patch("core.window_automation.EVEWindowAutomation._visual_ocr_left_click",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._check_image_difference",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle",
                   return_value=99999), \
             patch("core.window_automation.EVEWindowAutomation._mouse_move"), \
             patch("core.window_automation.EVEWindowAutomation._mouse_click"), \
             patch("PIL.ImageGrab.grab", return_value=MagicMock()), \
             patch("pywinauto.keyboard.send_keys"):
            auto = EVEWindowAutomation(self._cfg())
            order = {"price": 1595.9, "volume_remain": 10}
            auto.execute_quick_order_update(order, "1595.90", selected_window=self._SELECTED)
        mock_right_click.assert_called_once()

    def test_unique_match_menu_click_step_recorded(self):
        result = self._run(self._cfg())
        any_click_sent = any(s.startswith("visual_ocr_modify_order_menu_click_sent") for s in result["steps_executed"])
        self.assertTrue(any_click_sent, "visual_ocr_modify_order_menu_click_sent step not found")

    # -- paste blocking defaults (visual_ocr_allow_unverified_paste=False) -------

    def test_paste_blocked_by_default_after_click(self):
        result = self._run(self._cfg(visual_ocr_allow_unverified_paste=False))
        skipped = result["steps_skipped"]
        self.assertIn("paste_skipped_visual_ocr_dialog_not_verified", skipped)
        self.assertFalse(result["price_pasted"])

    def test_paste_allowed_when_unverified_paste_enabled(self):
        result = self._run(self._cfg(visual_ocr_allow_unverified_paste=True))
        self.assertNotIn("paste_skipped_visual_ocr_dialog_not_verified",
                         result["steps_skipped"])

    # -- final confirm NEVER executed --------------------------------------------

    def test_final_confirm_never_executed_unique_match(self):
        result = self._run(self._cfg())
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))
        for step in result["steps_executed"]:
            self.assertNotIn("confirm", step.lower(),
                             f"confirm must never be in steps_executed: {step}")

    def test_final_confirm_never_executed_not_found(self):
        result = self._run(self._cfg(), detection=self._detection_not_found())
        self.assertIn("DESIGN", " ".join(result["steps_skipped"]))

    # -- all required keys present -----------------------------------------------

    def test_all_required_keys_present_visual_ocr(self):
        result = self._run(self._cfg())
        for key in _REQUIRED_KEYS:
            self.assertIn(key, result, f"key '{key}' missing from result")

    # -- new diagnostic fields populated from detection --------------------------

    def test_blue_bands_found_populated(self):
        result = self._run(self._cfg())
        self.assertEqual(result["visual_ocr_blue_bands_found"], 1)

    def test_section_used_populated(self):
        result = self._run(self._cfg())
        self.assertEqual(result["visual_ocr_section_used"], "sell")

    def test_section_y_min_populated(self):
        result = self._run(self._cfg())
        self.assertIsNotNone(result["visual_ocr_section_y_min"])

    def test_own_marker_matched_populated(self):
        result = self._run(self._cfg())
        self.assertTrue(result["visual_ocr_own_marker_matched"])

    def test_price_text_populated(self):
        result = self._run(self._cfg())
        self.assertEqual(result["visual_ocr_price_text"], "1595.90")

    def test_quantity_text_populated(self):
        result = self._run(self._cfg())
        self.assertEqual(result["visual_ocr_quantity_text"], "10")

    # -- visual_ocr_enabled flag reflected in result -----------------------------

    def test_visual_ocr_enabled_true_in_result(self):
        result = self._run(self._cfg())
        self.assertTrue(result["visual_ocr_enabled"])

    def test_visual_ocr_enabled_false_in_result_when_disabled(self):
        auto = EVEWindowAutomation(self._cfg(visual_ocr_enabled=False))
        with patch("core.window_automation._PYWINAUTO_AVAILABLE", False):
            result = auto.execute_quick_order_update({}, "100")
        self.assertFalse(result["visual_ocr_enabled"])

    # -- right_click_fail blocks paste -------------------------------------------

    def test_right_click_fail_blocks_paste(self):
        import numpy as np
        mock_win = MagicMock()
        screenshot = np.zeros((200, 400, 3), dtype="uint8")

        with patch("core.window_automation._PYWINAUTO_AVAILABLE", True), \
             patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", True), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle",
                   return_value=mock_win), \
             patch("core.window_automation.EVEWindowAutomation._focus_window",
                   return_value=True), \
             patch("core.window_automation.EVEWindowAutomation._get_window_rect",
                   return_value={"left": 0, "top": 0, "width": 400, "height": 200}), \
             patch("core.window_automation.EVEWindowAutomation._capture_window_screenshot",
                   return_value=screenshot), \
             patch("core.window_automation.EVEWindowAutomation._run_visual_ocr_detect",
                   return_value=self._detection_unique()), \
             patch("core.window_automation.EVEWindowAutomation._visual_ocr_right_click",
                   return_value=False), \
             patch("pywinauto.keyboard.send_keys"):
            auto = EVEWindowAutomation(self._cfg())
            order = {"price": 1595.9, "volume_remain": 10}
            result = auto.execute_quick_order_update(
                order, "1595.90", selected_window=self._SELECTED
            )
        self.assertIn("paste_skipped_visual_ocr_step_failed", result["steps_skipped"])
        self.assertFalse(result["price_pasted"])


    def test_visual_ocr_debug_save_crops_exists(self):
        # Regression test for missing attribute bug
        auto = EVEWindowAutomation(self._cfg())
        self.assertTrue(hasattr(auto, "visual_ocr_debug_save_crops"))
        self.assertIsInstance(auto.visual_ocr_debug_save_crops, bool)

    def test_execute_accepts_manual_region(self):
        # Verify execute_quick_order_update accepts manual_region without error
        auto = EVEWindowAutomation(self._cfg())
        manual = {"x_min_ratio": 0.1, "y_min_ratio": 0.2, "x_max_ratio": 0.3, "y_max_ratio": 0.4}
        # Should not raise TypeError: execute_quick_order_update() got an unexpected keyword argument 'manual_region'
        result = auto.execute_quick_order_update({}, "100", manual_region=manual)
        self.assertIn("config", result)

    def test_manual_region_config_in_result(self):
        auto = EVEWindowAutomation(self._cfg())
        result = auto.execute_quick_order_update({}, "100")
        self.assertIn("visual_ocr_manual_region_enabled", result["config"])
        self.assertIn("visual_ocr_manual_region_prompt_each_time", result["config"])
        self.assertIn("visual_ocr_manual_region_save_profile", result["config"])


class TestEVEWindowAutomationSafetyMicrofixes(unittest.TestCase):
    """REQUIRED FIX 5 — Tests for safety microfixes."""

    def setUp(self):
        self.cfg = {
            "enabled": True,
            "dry_run": False,
            "experimental_paste_enabled": True,
            "paste_into_focused_window": True,
            "require_window_selection": True,
            "paste_method": "ctrl+v",
            "pre_paste_delay_ms": 0,
            "focus_client_delay_ms": 0,
            "modify_order_strategy": "visual_ocr"
        }
        self.selected = {"handle": 12345, "title": "EVE - Test"}
        self.order = {"price": 100.0}

    def test_run_id_mismatch_blocks_paste_before_hotkeys(self):
        auto = EVEWindowAutomation(self.cfg)
        # Setup active run check that returns False (mismatch)
        auto.set_active_run_check(lambda rid: False)
        
        result = auto._base_result("100.00")
        result["automation_run_id"] = "abc123"
        result["selected_window_handle"] = 12345
        result["window_found"] = True
        result["focused"] = True
        # Even if OCR is "perfect"
        result["visual_ocr_status"] = "unique_match"
        result["context_menu_click_sent"] = True
        result["modify_menu_click_sent"] = True
        
        with patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle", return_value=12345), \
             patch("pywinauto.keyboard.send_keys") as mock_keys:
            
            auto._handle_experimental_paste(result, "100.00", [])
            
            self.assertFalse(result.get("price_pasted"))
            self.assertEqual(result.get("paste_block_reason"), "run_id_mismatch")
            self.assertEqual(mock_keys.call_count, 0)

    def test_paste_guard_already_consumed_releases_modifiers(self):
        auto = EVEWindowAutomation(self.cfg)
        auto._paste_guard_consumed = True
        
        with patch("core.window_automation.EVEWindowAutomation._release_modifiers") as mock_release:
            result = auto._base_result("100.00")
            auto._handle_experimental_paste(result, "100.00", [])
            
            self.assertFalse(result.get("price_pasted"))
            self.assertEqual(result.get("paste_block_reason"), "paste_guard_already_consumed")
            mock_release.assert_called()

if __name__ == "__main__":
    unittest.main()
