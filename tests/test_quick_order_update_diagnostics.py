"""
Tests for core/quick_order_update_diagnostics.py — automation section rendering.

Verifies that the [AUTOMATION] section correctly displays Phase 3 modify-order
fields and always shows Final Confirm Action : NOT_EXECUTED_BY_DESIGN.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.quick_order_update_diagnostics import (
    format_automation_section,
    replace_or_append_automation_section,
    _format_automation_section,
)


def _base_automation(**overrides) -> dict:
    base = {
        "status":                    "success",
        "enabled":                   True,
        "dry_run":                   False,
        "window_found":              True,
        "window_title":              "EVE - Test Char",
        "focused":                   True,
        "clipboard_set":             True,
        "recommended_price_text":    "1595.90",
        "experimental_paste_enabled": False,
        "paste_into_focused_window":  False,
        "clear_price_field_before_paste": True,
        "paste_method":              "ctrl+v",
        "price_pasted":              False,
        "never_confirm_final_order": True,
        "window_source":             "selected_handle",
        "selected_window_handle":    99999,
        "selected_window_title":     "EVE - Test Char",
        "candidate_windows_count":   1,
        "candidate_windows":         [],
        "steps_executed":            ["clipboard_set", "focused_eve_window"],
        "steps_skipped":             ["final_confirm_NOT_EXECUTED_BY_DESIGN"],
        "errors":                    [],
        "delays":                    {},
        # Phase 3 fields
        "modify_order_step_enabled":               False,
        "modify_order_strategy":                   "manual_focus_guard",
        "modify_order_prepare_attempted":          False,
        "modify_order_dialog_verified":            False,
        "require_modify_dialog_ready":             False,
        "paste_without_modify_dialog_verification": True,
        "modify_order_warning":                    None,
        # Phase 3B fields
        "modify_order_hotkey_configured":          False,
        "allow_unverified_modify_order_paste":     False,
    }
    base.update(overrides)
    return base


class TestAutomationSectionRendering(unittest.TestCase):

    def test_modify_order_step_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Modify Order Step", section)

    def test_modify_order_strategy_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Modify Order Strategy", section)

    def test_modify_dialog_verified_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Modify Dialog Verified", section)

    def test_paste_without_verify_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Paste Without Verify", section)

    def test_final_confirm_not_executed_by_design(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Final Confirm Action : NOT_EXECUTED_BY_DESIGN", section)

    def test_automation_section_marker(self):
        section = format_automation_section(_base_automation())
        self.assertIn("[AUTOMATION]", section)

    def test_modify_order_step_enabled_false_value(self):
        section = format_automation_section(_base_automation(modify_order_step_enabled=False))
        self.assertIn("False", section)

    def test_modify_order_strategy_value(self):
        section = format_automation_section(
            _base_automation(modify_order_strategy="manual_focus_guard")
        )
        self.assertIn("manual_focus_guard", section)

    def test_modify_dialog_verified_false_value(self):
        section = format_automation_section(_base_automation(modify_order_dialog_verified=False))
        lines = section.split("\n")
        verified_lines = [l for l in lines if "Modify Dialog Verified" in l]
        self.assertTrue(verified_lines)
        self.assertIn("False", verified_lines[0])

    def test_paste_without_verify_true_value(self):
        section = format_automation_section(
            _base_automation(paste_without_modify_dialog_verification=True)
        )
        lines = section.split("\n")
        paste_lines = [l for l in lines if "Paste Without Verify" in l]
        self.assertTrue(paste_lines)
        self.assertIn("True", paste_lines[0])

    def test_replace_or_append_does_not_duplicate(self):
        """replace_or_append_automation_section must not duplicate [AUTOMATION]."""
        report = "initial report\n\n[AUTOMATION]\n  old content"
        new_section = format_automation_section(_base_automation())
        updated = replace_or_append_automation_section(report, new_section)
        self.assertEqual(updated.count("[AUTOMATION]"), 1)

    def test_replace_or_append_appends_if_absent(self):
        report = "initial report without automation"
        new_section = format_automation_section(_base_automation())
        updated = replace_or_append_automation_section(report, new_section)
        self.assertIn("[AUTOMATION]", updated)
        self.assertIn("initial report", updated)

    def test_final_confirm_present_across_strategies(self):
        for strategy in ("manual_focus_guard", "hotkey_experimental"):
            section = format_automation_section(
                _base_automation(modify_order_strategy=strategy)
            )
            self.assertIn(
                "Final Confirm Action : NOT_EXECUTED_BY_DESIGN", section,
                f"missing safety line for strategy={strategy}",
            )

    def test_modify_hotkey_configured_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Modify Hotkey Config", section)

    def test_require_dialog_ready_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Require Dialog Ready", section)

    def test_allow_unverified_paste_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Allow Unverified Paste", section)

    def test_modify_hotkey_configured_set_label(self):
        section = format_automation_section(_base_automation(modify_order_hotkey_configured=True))
        lines = section.split("\n")
        hotkey_lines = [l for l in lines if "Modify Hotkey Config" in l]
        self.assertTrue(hotkey_lines)
        self.assertIn("set", hotkey_lines[0])

    def test_modify_hotkey_configured_empty_label(self):
        section = format_automation_section(_base_automation(modify_order_hotkey_configured=False))
        lines = section.split("\n")
        hotkey_lines = [l for l in lines if "Modify Hotkey Config" in l]
        self.assertTrue(hotkey_lines)
        self.assertIn("empty", hotkey_lines[0])

    def test_modify_order_warning_shown_when_set(self):
        section = format_automation_section(
            _base_automation(modify_order_warning="test warning message")
        )
        self.assertIn("test warning message", section)

    def test_modify_order_warning_absent_when_none(self):
        section = format_automation_section(_base_automation(modify_order_warning=None))
        self.assertNotIn("Modify Order Warning", section)


if __name__ == "__main__":
    unittest.main()
