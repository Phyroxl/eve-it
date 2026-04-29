import unittest
from core.my_orders_diagnostics import format_my_orders_diagnostic_report

class TestMyOrdersDiagnostics(unittest.TestCase):
    def test_report_structure(self):
        diag = {
            "char_id": 123456789,
            "char_name": "Test Pilot",
            "duration": 5.4321,
            "status": "SUCCESS",
            "sell_count": 10,
            "buy_count": 5,
            "total_count": 15,
            "rows_sell_table": 10,
            "rows_buy_table": 5,
            "sales_tax": 4.5,
            "broker_fee": 1.2,
            "tax_source": "Skills",
            "location_id": 60003760,
            "sell_icon_requests": 10,
            "buy_icon_requests": 5,
            "detail_icon_requests": 1,
            "icon_direct_applied_sell": 8,
            "icon_fallback_applied_sell": 1,
            "icon_missed_sell": 1,
            "icon_direct_applied_buy": 5,
            "icon_fallback_applied_buy": 0,
            "icon_missed_buy": 0,
            "generation_skipped": 0,
            "missing_type_id_items": [{"side": "SELL", "row": 5, "item_name": "No ID Item"}],
            "failed_items": [{"side": "SELL", "type_id": 12005, "item_name": "Ishtar"}],
            "callback_missed_items": [{"side": "SELL", "row": 9, "type_id": 34, "item_name": "Tritanium"}],
            "skipped_items": [],
            "sell_rows_with_tid": 9,
            "buy_rows_with_tid": 5,
            "notes": ["Test note 1", "Test note 2"]
        }
        
        icon_diag = {
            "requests": 16,
            "cache_hits": 2,
            "loaded": 12,
            "failed_count": 1,
            "placeholders": 1,
            "endpoint_icon": 10,
            "endpoint_render": 2,
            "endpoint_bp": 0,
            "endpoint_bpc": 0,
            "endpoint_portrait": 0,
            "last_errors": ["ID 12005: icon failed: 404"]
        }
        
        report = format_my_orders_diagnostic_report(diag, icon_diag)
        
        # Verify sections
        self.assertIn("EVE iT — MY ORDERS DIAGNOSTIC REPORT", report)
        self.assertIn("[ORDERS SUMMARY]", report)
        self.assertIn("[TAXES]", report)
        self.assertIn("[ICON SUMMARY]", report)
        self.assertIn("[ICON ENDPOINT SUCCESS]", report)
        self.assertIn("[TABLE CALLBACK DIAGNOSTICS]", report)
        self.assertIn("[MISSING / PLACEHOLDER ICON ITEMS]", report)
        self.assertIn("[LAST ICON ERRORS]", report)
        self.assertIn("[TYPE ID VALIDATION]", report)
        self.assertIn("[NOTES]", report)
        
        # Verify specific data
        self.assertIn("TEST PILOT", report)
        self.assertIn("Ishtar", report)
        self.assertIn("Tritanium", report)
        self.assertIn("No ID Item", report)
        self.assertIn("Test note 1", report)
        
        print("test_report_structure: PASSED")

if __name__ == "__main__":
    unittest.main()
