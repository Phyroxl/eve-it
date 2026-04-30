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


class TestVisualOCRHardeningFields(unittest.TestCase):
    """Phase 3C hardening: new diagnostic fields in _format_automation_section."""

    def _auto_with_ocr_fields(self, **extra):
        auto = _base_automation()
        auto.update({
            "visual_ocr_blue_bands_found": 2,
            "visual_ocr_section_used":     "sell",
            "visual_ocr_section_y_min":    44,
            "visual_ocr_section_y_max":    116,
            "visual_ocr_own_marker_matched": True,
            "visual_ocr_price_text":       "1595.90",
            "visual_ocr_quantity_text":    "10",
        })
        auto.update(extra)
        return auto

    def test_blue_bands_found_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Blue Bands", section)
        self.assertIn("2", section)

    def test_section_used_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Section", section)
        self.assertIn("sell", section)

    def test_section_y_min_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Sec Y Min", section)
        self.assertIn("44", section)

    def test_section_y_max_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Sec Y Max", section)
        self.assertIn("116", section)

    def test_own_marker_matched_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Own Marker", section)
        self.assertIn("True", section)

    def test_price_text_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Price Txt", section)
        self.assertIn("1595.90", section)

    def test_quantity_text_shown(self):
        section = format_automation_section(self._auto_with_ocr_fields())
        self.assertIn("Visual OCR Qty Txt", section)
        self.assertIn("10", section)

    def test_overlay_path_shown_when_set(self):
        auto = self._auto_with_ocr_fields(
            visual_ocr_debug_overlay_path="/tmp/visual_ocr_overlay_123.png"
        )
        section = format_automation_section(auto)
        self.assertIn("Visual OCR Overlay", section)
        self.assertIn("/tmp/visual_ocr_overlay_123.png", section)

    def test_overlay_path_absent_when_none(self):
        auto = self._auto_with_ocr_fields()
        auto.pop("visual_ocr_debug_overlay_path", None)
        section = format_automation_section(auto)
        self.assertNotIn("Visual OCR Overlay", section)


class TestVisualOCRSectionRendering(unittest.TestCase):

    def test_visual_ocr_enabled_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Enabled", section)

    def test_visual_ocr_status_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Status", section)

    def test_visual_ocr_candidates_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Candidates", section)

    def test_visual_ocr_price_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Price", section)

    def test_visual_ocr_quantity_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Quantity", section)

    def test_visual_ocr_row_x_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Row X", section)

    def test_visual_ocr_row_y_shown(self):
        section = format_automation_section(_base_automation())
        self.assertIn("Visual OCR Row Y", section)

    def test_visual_ocr_debug_img_shown_when_set(self):
        auto = _base_automation()
        auto["visual_ocr_debug_screenshot_path"] = "/tmp/test_screenshot.png"
        section = format_automation_section(auto)
        self.assertIn("Visual OCR Debug Img", section)
        self.assertIn("/tmp/test_screenshot.png", section)

    def test_visual_ocr_debug_img_absent_when_none(self):
        auto = _base_automation()
        auto.pop("visual_ocr_debug_screenshot_path", None)
        section = format_automation_section(auto)
        self.assertNotIn("Visual OCR Debug Img", section)

    def test_visual_ocr_enabled_false_value(self):
        auto = _base_automation()
        auto["visual_ocr_enabled"] = False
        section = format_automation_section(auto)
        lines = section.split("\n")
        enabled_lines = [l for l in lines if "Visual OCR Enabled" in l]
        self.assertTrue(enabled_lines)
        self.assertIn("False", enabled_lines[0])

    def test_visual_ocr_status_value_shown(self):
        auto = _base_automation()
        auto["visual_ocr_status"] = "unique_match"
        section = format_automation_section(auto)
        self.assertIn("unique_match", section)


    def test_manual_region_enabled_shown(self):
        auto = _base_automation()
        auto["config"] = {"visual_ocr_manual_region_enabled": True}
        section = format_automation_section(auto)
        self.assertIn("Manual Region Enabled: True", section)

    def test_manual_region_used_shown(self):
        auto = _base_automation()
        auto["visual_ocr_debug"] = {"manual_region_used": True}
        section = format_automation_section(auto)
        self.assertIn("Manual Region Used   : True", section)

    def test_manual_region_ratios_shown(self):
        auto = _base_automation()
        auto["visual_ocr_debug"] = {
            "manual_region_used": True,
            "manual_region_ratios": [0.1, 0.2, 0.3, 0.4]
        }
        section = format_automation_section(auto)
        self.assertIn("Manual Region Ratios : [0.1, 0.2, 0.3, 0.4]", section)

class TestSafetyGuardDiagnostics(unittest.TestCase):
    """Phase 3F: Safety Guards in diagnostic report."""

    def test_safety_guards_header_present(self):
        section = format_automation_section(_base_automation())
        self.assertIn("SAFETY GUARDS", section)

    def test_automation_run_id_shown(self):
        auto = _base_automation(automation_run_id="f7a2b9c1")
        section = format_automation_section(auto)
        self.assertIn("Automation Run ID", section)
        self.assertIn("f7a2b9c1", section)

    def test_safe_to_paste_shown(self):
        auto = _base_automation(safe_to_paste=True)
        section = format_automation_section(auto)
        self.assertIn("Safe To Paste", section)
        self.assertIn("True", section)

    def test_paste_block_reason_shown(self):
        auto = _base_automation(paste_block_reason="foreground_window_mismatch")
        section = format_automation_section(auto)
        self.assertIn("Paste Block Reason", section)
        self.assertIn("foreground_window_mismatch", section)

    def test_foreground_win_details_shown(self):
        auto = _base_automation(
            foreground_win_handle=12345,
            foreground_win_title="EVE - Test"
        )
        section = format_automation_section(auto)
        self.assertIn("Foreground Win Handle: 12345", section)
        self.assertIn("Foreground Win Title : EVE - Test", section)

    def test_menu_sent_flags_shown(self):
        auto = _base_automation(
            context_menu_click_sent=True,
            modify_menu_click_sent=False
        )
        section = format_automation_section(auto)
        self.assertIn("Context Menu Sent    : True", section)
        self.assertIn("Modify Menu Sent     : False", section)

if __name__ == "__main__":
    unittest.main()
