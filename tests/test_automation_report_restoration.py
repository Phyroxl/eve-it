"""
Tests for automation report restoration logic.
Verifies that [AUTOMATION] is added even on exceptions and correctly replaced.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.quick_order_update_diagnostics import (
    format_automation_section, replace_or_append_automation_section
)

class TestAutomationReportRestoration(unittest.TestCase):

    def test_append_to_empty_report(self):
        report = "Header\n\n[ERRORS]\n - none"
        auto_data = {"status": "success", "enabled": True}
        auto_section = format_automation_section(auto_data)
        
        updated = replace_or_append_automation_section(report, auto_section)
        self.assertIn("[AUTOMATION]", updated)
        self.assertIn("Status               : success", updated)

    def test_replace_existing_section(self):
        report = "Header\n\n[AUTOMATION]\n  Status               : old_status\n\n[NOTES]\n - none"
        auto_data = {"status": "new_status", "enabled": True}
        auto_section = format_automation_section(auto_data)
        
        updated = replace_or_append_automation_section(report, auto_section)
        self.assertEqual(updated.count("[AUTOMATION]"), 1)
        self.assertIn("Status               : new_status", updated)
        self.assertNotIn("old_status", updated)
        self.assertIn("[NOTES]", updated)

    def test_format_automation_section_no_crash_on_missing_keys(self):
        # Should not crash even if dict is empty
        try:
            section = format_automation_section({})
            self.assertIn("[AUTOMATION]", section)
            self.assertIn("Status               : N/A", section)
        except Exception as e:
            self.fail(f"format_automation_section crashed on empty dict: {e}")

    def test_format_automation_section_handles_visual_ocr_debug(self):
        auto_data = {
            "visual_ocr_debug": {
                "raw_candidate_bands": [(1,2), (3,4)],
                "rejected_bands_by_height": [(5,6)],
                "filtered_candidate_bands": [(7,8)]
            }
        }
        section = format_automation_section(auto_data)
        self.assertIn("Visual OCR Raw Bands : 2", section)
        self.assertIn("Visual OCR Rej Height: 1", section)
        self.assertIn("Visual OCR Filtered  : 1", section)

if __name__ == "__main__":
    unittest.main()
