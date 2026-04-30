import unittest
from core.my_orders_diagnostics import format_my_orders_diagnostic_report

class TestMyOrdersDiagnosticsExtended(unittest.TestCase):
    def test_report_includes_watchlist_and_sync_details(self):
        diag = {
            "market_timings": {
                "source": "esi_type_filtered_refresh",
                "type_ids_count": 5,
                "type_ids_fetched": 5,
                "total_elapsed": 1.23,
                "orders_count": 150
            },
            "all_orders": [
                MagicOrder("Wasp I", "Superada con beneficio", 1201, 100.0, 60003760)
            ]
        }
        icon_diag = {"requests": 0, "cache_hits": 0, "loaded": 0, "failed_count": 0, "placeholders": 0}
        
        report = format_my_orders_diagnostic_report(diag, icon_diag)
        
        self.assertIn("[MARKET SYNCHRONIZATION]", report)
        self.assertIn("ESI_TYPE_FILTERED_REFRESH", report)
        self.assertIn("Type IDs Count: 5", report)
        self.assertIn("[ORDER STATE DEBUG — WATCHLIST]", report)
        self.assertIn("Wasp I", report)
        self.assertIn("State:      SUPERADA CON BENEFICIO", report)

class MagicOrder:
    def __init__(self, name, state, tid, price, loc):
        self.item_name = name
        self.is_buy_order = False
        self.price = price
        self.location_id = loc
        self.type_id = tid
        self.analysis = MagicAnalysis(state)
        self._state_debug = {"market_orders_loc_sell_count": 10}

class MagicAnalysis:
    def __init__(self, state):
        self.state = state
        self.best_buy = 0
        self.best_sell = 99.0
        self.competitor_price = 99.0
        self.competitive = False
        self.difference_to_best = 1.0

if __name__ == '__main__':
    unittest.main()
