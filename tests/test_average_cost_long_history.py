"""Tests for CostBasisService long-history backfill and ESIClient transaction limits."""
import unittest
from unittest.mock import MagicMock, patch
from core.cost_basis_service import CostBasisService


CHAR_ID = 93000001


def _make_service():
    svc = CostBasisService.__new__(CostBasisService)
    svc.cache = {}
    svc.stock_map = {}
    svc.last_transaction_id = 0
    svc.client = MagicMock()
    svc.last_fetch_time = None
    svc.backfill_stats = {}
    return svc


def _tx(tid, type_id, qty, price, is_buy, date="2025-01-15T12:00:00Z"):
    return {
        "transaction_id": tid,
        "type_id": type_id,
        "quantity": qty,
        "unit_price": price,
        "is_buy": is_buy,
        "date": date,
    }


class TestHistoryLimitConstants(unittest.TestCase):

    def test_history_days_is_365(self):
        """AVERAGE_COST_MIN_HISTORY_DAYS must be 365 (1 year)."""
        self.assertEqual(CostBasisService.AVERAGE_COST_MIN_HISTORY_DAYS, 365)

    def test_esi_client_safety_limit_is_100k(self):
        """ESIClient wallet_transactions safety limit must be 100,000."""
        import inspect
        from core import esi_client
        src = inspect.getsource(esi_client.ESIClient.wallet_transactions)
        self.assertIn("100000", src, "Safety limit should be 100,000 transactions")
        self.assertNotIn("15000", src, "Old 15k limit should be removed")


class TestWACCalculation(unittest.TestCase):

    def test_buy_only_builds_wac(self):
        svc = _make_service()
        txs = [_tx(1, 34, 100, 5.0, True), _tx(2, 34, 200, 6.0, True)]
        svc.client.wallet_transactions.return_value = txs
        with patch.object(svc, "load_from_file"), patch.object(svc, "save_to_file"):
            svc.refresh_from_esi(CHAR_ID, "token")
        cb = svc.get_cost_basis(34)
        self.assertIsNotNone(cb)
        # WAC: (100*5 + 200*6) / 300 = 1700/300 = 5.667
        self.assertAlmostEqual(cb.average_buy_price, 1700 / 300, places=4)
        self.assertEqual(cb.total_quantity, 300)

    def test_sell_reduces_wac_proportionally(self):
        svc = _make_service()
        txs = [
            _tx(1, 34, 300, 5.667, True),
            _tx(2, 34, 100, 9.0, False),  # sell 100 units
        ]
        svc.client.wallet_transactions.return_value = txs
        with patch.object(svc, "load_from_file"), patch.object(svc, "save_to_file"):
            svc.refresh_from_esi(CHAR_ID, "token")
        cb = svc.get_cost_basis(34)
        self.assertIsNotNone(cb)
        self.assertEqual(cb.total_quantity, 200)
        # cost after sell = 200 * 5.667
        self.assertAlmostEqual(cb.total_spent, 200 * 5.667, places=2)

    def test_sell_all_zeroes_out(self):
        svc = _make_service()
        txs = [
            _tx(1, 34, 100, 5.0, True),
            _tx(2, 34, 100, 9.0, False),
        ]
        svc.client.wallet_transactions.return_value = txs
        with patch.object(svc, "load_from_file"), patch.object(svc, "save_to_file"):
            svc.refresh_from_esi(CHAR_ID, "token")
        cb = svc.get_cost_basis(34)
        self.assertIsNone(cb)  # qty=0 → not in cache

    def test_incremental_update_skips_old_txs(self):
        """Only transactions newer than last_transaction_id are processed."""
        svc = _make_service()
        svc.stock_map = {"34": {"qty": 100, "cost": 500.0}}
        svc.last_transaction_id = 10
        txs = [
            _tx(5, 34, 50, 4.0, True),   # old — should be skipped
            _tx(15, 34, 50, 6.0, True),  # new — should be applied
        ]
        svc.client.wallet_transactions.return_value = txs
        with patch.object(svc, "load_from_file"), patch.object(svc, "save_to_file"):
            svc.refresh_from_esi(CHAR_ID, "token")
        cb = svc.get_cost_basis(34)
        self.assertEqual(cb.total_quantity, 150)
        self.assertAlmostEqual(cb.total_spent, 500.0 + 50 * 6.0, places=4)

    def test_missing_scope_returns_false(self):
        svc = _make_service()
        svc.client.wallet_transactions.return_value = "missing_scope"
        with patch.object(svc, "load_from_file"):
            result = svc.refresh_from_esi(CHAR_ID, "token")
        self.assertFalse(result)

    def test_backfill_stats_populated(self):
        svc = _make_service()
        txs = [
            _tx(1, 34, 100, 5.0, True, "2024-06-01T00:00:00Z"),
            _tx(2, 35, 50, 10.0, True, "2025-01-01T00:00:00Z"),
        ]
        svc.client.wallet_transactions.return_value = txs
        with patch.object(svc, "load_from_file"), patch.object(svc, "save_to_file"):
            svc.refresh_from_esi(CHAR_ID, "token")
        stats = svc.backfill_stats
        self.assertEqual(stats["count"], 2)
        self.assertEqual(stats["requested_days"], 365)
        self.assertIn("oldest", stats)
        self.assertIn("newest", stats)

    def test_asset_reconciliation_resets_missing_items(self):
        """Items in WAC but not in assets are zeroed out."""
        svc = _make_service()
        svc.client.wallet_transactions.return_value = []
        svc.stock_map = {
            "34": {"qty": 100, "cost": 500.0},
            "35": {"qty": 50, "cost": 250.0},
        }
        assets = [{"type_id": 34, "quantity": 100}]  # 35 missing from assets
        with patch.object(svc, "load_from_file"), patch.object(svc, "save_to_file"):
            svc.refresh_from_esi(CHAR_ID, "token", current_assets=assets)
        self.assertEqual(svc.stock_map["35"]["qty"], 0)
        self.assertEqual(svc.stock_map["35"]["cost"], 0.0)
        cb35 = svc.get_cost_basis(35)
        self.assertIsNone(cb35)

    def test_tooltip_message_does_not_contain_2500(self):
        """The N/A tooltip no longer references the old 2500-transaction limit."""
        import inspect
        from ui.market_command import my_orders_view
        src = inspect.getsource(my_orders_view)
        idx = src.find("Coste medio no disponible")
        self.assertNotEqual(idx, -1, "Updated tooltip text not found")
        excerpt = src[idx:idx+200]
        self.assertNotIn("2500", excerpt, "Old 2500 limit reference must be removed from tooltip")


if __name__ == "__main__":
    unittest.main()
