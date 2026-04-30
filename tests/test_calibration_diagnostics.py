"""
Tests for calibration diagnostics in core/quick_order_update_diagnostics.py.
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.quick_order_update_diagnostics import format_quick_update_report

class TestCalibrationDiagnostics(unittest.TestCase):

    def test_report_shows_manual_region_dimensions(self):
        automation_data = {
            "enabled": True,
            "visual_ocr_debug": {
                "manual_region_used": True,
                "manual_region_width_px": 400,
                "manual_region_height_px": 200,
                "manual_region_ratios": [0.1, 0.1, 0.5, 0.5]
            },
            "config": {
                "manual_region_source": "selected_now"
            }
        }
        report = format_quick_update_report({"automation": automation_data})
        
        self.assertIn("Manual Region Width Px: 400", report)
        self.assertIn("Manual Region Height Px: 200", report)
        self.assertNotIn("Manual Region Warning: region_too_short", report)

    def test_report_shows_warning_for_short_region(self):
        automation_data = {
            "enabled": True,
            "visual_ocr_debug": {
                "manual_region_used": True,
                "manual_region_width_px": 400,
                "manual_region_height_px": 150,
                "manual_region_ratios": [0.1, 0.1, 0.5, 0.5]
            },
            "config": {
                "manual_region_source": "selected_now_retry"
            }
        }
        report = format_quick_update_report({"automation": automation_data})
        
        self.assertIn("Manual Region Height Px: 150", report)
        self.assertIn("Manual Region Warning: region_too_short", report)

if __name__ == "__main__":
    unittest.main()
