import unittest
from unittest.mock import MagicMock, patch, call
from core.window_automation import EVEWindowAutomation

class TestVisualOCRStability(unittest.TestCase):
    def setUp(self):
        self.config = {
            "enabled": True,
            "dry_run": False,
            "visual_ocr_enabled": True,
            "modify_order_strategy": "visual_ocr",
            "visual_ocr_verify_context_menu_open": True,
            "visual_ocr_modify_menu_hover_ms": 100,
            "visual_ocr_modify_click_retry_if_menu_closed": True,
            "visual_ocr_modify_click_max_retries": 1,
            "visual_ocr_right_click_max_attempts": 1,
            "visual_ocr_context_menu_delay_ms": 10,
            "visual_ocr_modify_dialog_delay_ms": 10,
        }
        self.automation = EVEWindowAutomation(self.config)
        self.automation._safe_sleep = MagicMock()
        self.automation._is_aborted = MagicMock(return_value=False)
        self.automation._active_run_matches = MagicMock(return_value=True)

    @patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", True)
    @patch("core.window_automation._ImageGrab")
    @patch.object(EVEWindowAutomation, "_capture_window_screenshot")
    @patch.object(EVEWindowAutomation, "_run_visual_ocr_detect")
    @patch.object(EVEWindowAutomation, "_mouse_move")
    @patch.object(EVEWindowAutomation, "_mouse_click")
    def test_modify_click_sequence_success(self, mock_click, mock_move, mock_detect, mock_screenshot, mock_grab):
        """Verify the full move/wait/verify/click sequence on success."""
        mock_screenshot.return_value = MagicMock()
        mock_detect.return_value = {
            "status": "unique_match",
            "row_center_x": 100,
            "row_center_y": 200,
            "candidates_count": 1,
            "matched_price": True,
            "matched_quantity": True,
            "matched_own_marker": True
        }
        
        # Mock context menu verification: always returns True (open)
        with patch.object(EVEWindowAutomation, "_is_context_menu_open", return_value=True) as mock_verify:
            result = self.automation._base_result("")
            result["selected_window_handle"] = 123
            errors = []
            self.automation._run_visual_ocr(result, {}, 123, errors)
            
            # Verify right click happened
            self.assertTrue(result.get("context_menu_click_sent"))
            
            # Verify modify move and hover happened
            # rc_x = 100 + 20 = 120
            # menu_x = 120 + 65 = 185
            mock_move.assert_any_call(185, 237)
            self.assertIn("waited_visual_ocr_modify_menu_hover", result["steps_executed"])
            
            # Verify re-check happened
            self.assertTrue(result.get("visual_ocr_menu_open_before_modify_click"))
            
            # Verify final left click happened
            self.assertTrue(result.get("modify_menu_click_sent"))
            mock_click.assert_called_with(185, 237, button="left")

    @patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", True)
    @patch("core.window_automation._ImageGrab")
    @patch.object(EVEWindowAutomation, "_capture_window_screenshot")
    @patch.object(EVEWindowAutomation, "_run_visual_ocr_detect")
    @patch.object(EVEWindowAutomation, "_mouse_move")
    @patch.object(EVEWindowAutomation, "_mouse_click")
    def test_modify_click_blocks_if_menu_closes(self, mock_click, mock_move, mock_detect, mock_screenshot, mock_grab):
        """Verify paste is blocked if menu closes before modify click and retry fails."""
        self.config["visual_ocr_modify_click_retry_if_menu_closed"] = False # Disable retry for this test
        self.automation = EVEWindowAutomation(self.config)
        self.automation._safe_sleep = MagicMock()
        
        mock_screenshot.return_value = MagicMock()
        mock_detect.return_value = {
            "status": "unique_match",
            "row_center_x": 100,
            "row_center_y": 200
        }
        
        # Mock verification: first True (right click ok), then False (closed before modify)
        with patch.object(EVEWindowAutomation, "_is_context_menu_open", side_effect=[True, False]):
            result = self.automation._base_result("")
            result["selected_window_handle"] = 123
            errors = []
            self.automation._run_visual_ocr(result, {}, 123, errors)
            
            self.assertFalse(result.get("modify_menu_click_sent"))
            self.assertEqual(result.get("paste_block_reason"), "context_menu_closed_before_modify_click")
            # Left click should NOT have been called for modify
            # But we expect 2 clicks total: 1 pre-click (left) + 1 right click
            self.assertEqual(mock_click.call_count, 2)
            # One pre-click, zero modify clicks
            left_clicks = [c for c in mock_click.call_args_list if c.kwargs.get('button', 'left') == 'left']
            self.assertEqual(len(left_clicks), 1)

    @patch("core.window_automation._PIL_IMAGEGRAB_AVAILABLE", True)
    @patch("core.window_automation._ImageGrab")
    @patch.object(EVEWindowAutomation, "_capture_window_screenshot")
    @patch.object(EVEWindowAutomation, "_run_visual_ocr_detect")
    @patch.object(EVEWindowAutomation, "_mouse_move")
    @patch.object(EVEWindowAutomation, "_mouse_click")
    def test_modify_click_retries_if_menu_closes(self, mock_click, mock_move, mock_detect, mock_screenshot, mock_grab):
        """Verify retry logic if menu closes."""
        mock_screenshot.return_value = MagicMock()
        mock_detect.return_value = {
            "status": "unique_match",
            "row_center_x": 100,
            "row_center_y": 200
        }
        
        # side_effect: 
        # 1. Right click verification -> True
        # 2. Pre-modify verification -> False (closed)
        # 3. (Retry) Pre-modify verification -> True (open)
        with patch.object(EVEWindowAutomation, "_is_context_menu_open", side_effect=[True, False, True]):
            result = self.automation._base_result("")
            result["selected_window_handle"] = 123
            errors = []
            self.automation._run_visual_ocr(result, {}, 123, errors)
            
            self.assertTrue(result.get("modify_menu_click_sent"))
            self.assertEqual(result.get("visual_ocr_modify_retry_count"), 1)
            # Should have sent 2 right clicks (one initial, one retry)
            rc_clicks = [c for c in mock_click.call_args_list if c[1].get('button') == 'right']
            self.assertEqual(len(rc_clicks), 2)

if __name__ == "__main__":
    unittest.main()
