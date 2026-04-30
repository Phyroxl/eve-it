import unittest
from unittest.mock import MagicMock, patch
import os
from core.window_automation import EVEWindowAutomation

class TestAutomationSafetyGuards(unittest.TestCase):
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
        }
        self.selected = {"handle": 12345, "title": "EVE - Test"}
        self.order = {"price": 100.0}

    def test_paste_blocked_if_foreground_mismatch(self):
        auto = EVEWindowAutomation(self.cfg)
        # Mock foreground to be different
        with patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle", return_value=99999), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle", return_value=MagicMock()), \
             patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True):
            
            result = auto.execute_quick_order_update(self.order, "100.00", selected_window=self.selected)
            
            self.assertFalse(result.get("price_pasted"))
            self.assertEqual(result.get("paste_block_reason"), "foreground_window_mismatch")
            self.assertIn("paste_skipped_foreground_mismatch", result["steps_skipped"])

    def test_paste_allowed_if_foreground_matches(self):
        auto = EVEWindowAutomation(self.cfg)
        # Mock foreground to match
        with patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle", return_value=12345), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle", return_value=MagicMock()), \
             patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True), \
             patch("pywinauto.keyboard.send_keys"):
            
            result = auto.execute_quick_order_update(self.order, "100.00", selected_window=self.selected)
            
            self.assertTrue(result.get("price_pasted"))
            self.assertTrue(result.get("foreground_matches_selected"))

    def test_paste_guard_prevents_multiple_pastes(self):
        auto = EVEWindowAutomation(self.cfg)
        
        # We need to manually call _handle_experimental_paste twice to verify guard
        result = auto._base_result("100.00")
        result["selected_window_handle"] = 12345
        
        with patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle", return_value=12345), \
             patch("pywinauto.keyboard.send_keys"):
            
            # First attempt
            auto._handle_experimental_paste(result, "100.00", [])
            self.assertTrue(result["price_pasted"])
            self.assertTrue(auto._paste_guard_consumed)
            
            # Reset result flags but NOT the auto state
            result["price_pasted"] = False
            result["steps_skipped"] = []
            
            # Second attempt
            auto._handle_experimental_paste(result, "100.00", [])
            self.assertFalse(result["price_pasted"])
            self.assertEqual(result["paste_block_reason"], "guard_consumed")

    def test_abort_flag_stops_execution_before_paste(self):
        auto = EVEWindowAutomation(self.cfg)
        
        # Set abort flag to True immediately
        auto.set_abort_flag(lambda: True)
        
        with patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle", return_value=12345), \
             patch("core.window_automation.EVEWindowAutomation._connect_by_handle", return_value=MagicMock()), \
             patch("core.window_automation.EVEWindowAutomation._focus_window", return_value=True), \
             patch("pywinauto.keyboard.send_keys") as mock_keys:
            
            result = auto.execute_quick_order_update(self.order, "100.00", selected_window=self.selected)
            
            self.assertFalse(result.get("price_pasted"))
            self.assertTrue(result.get("automation_cancelled"))
            self.assertEqual(mock_keys.call_count, 0)

    def test_release_modifiers_called_on_finally(self):
        auto = EVEWindowAutomation(self.cfg)
        
        with patch("pywinauto.keyboard.send_keys", side_with=Exception("Crash!")), \
             patch("core.window_automation.EVEWindowAutomation._release_modifiers") as mock_release, \
             patch("core.window_automation.EVEWindowAutomation._get_foreground_window_handle", return_value=12345):
            
            result = auto._base_result("100.00")
            result["selected_window_handle"] = 12345
            
            try:
                auto._handle_experimental_paste(result, "100.00", [])
            except:
                pass
            
            # Modifier release should be called in finally block
            mock_release.assert_called()

if __name__ == "__main__":
    unittest.main()
