"""
Tests for _revalidate_order_freshness in MarketMyOrdersView.

Covers:
  1. order_id exists, price matches       -> is_fresh=True
  2. order_id exists, price changed       -> is_fresh=False  (Mystic S case)
  3. order_id not in ESI response         -> order_exists=False
  4. ESI raises exception                 -> checked=False
  5. No token available                   -> checked=False
  6. Mystic S: local=1598, fresh=1594     -> blocked
  7. _launch_quick_order_update no-copies if freshness stale
  8. _launch_quick_order_update copies    if freshness fresh
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Mock heavy dependencies before importing our modules
# ---------------------------------------------------------------------------

_auth_instance = MagicMock()
_auth_instance.authenticated = MagicMock()
_auth_instance.authenticated.connect = MagicMock()
_auth_instance.current_token = "test_token"
_auth_instance.char_id = 12345
_auth_instance.char_name = "TestChar"
_auth_instance.get_token = MagicMock(return_value="test_token")
_auth_instance.get_valid_access_token = MagicMock(return_value="test_token")

_auth_mod = MagicMock()
_auth_mod.AuthManager = MagicMock()
_auth_mod.AuthManager.instance = MagicMock(return_value=_auth_instance)

_fake_pixmap = MagicMock()
_fake_pixmap.isNull = MagicMock(return_value=True)
_fake_pixmap.scaled = MagicMock(return_value=_fake_pixmap)

_icon_instance = MagicMock()
_icon_instance.get_icon = MagicMock(return_value=_fake_pixmap)
_icon_instance.get_diagnostics = MagicMock(return_value={
    "cache_size": 0, "cache_hits": 0, "requests": 0, "loaded": 0,
    "failed_total": 0, "placeholders": 0, "endpoint_icon": 0,
    "endpoint_render": 0, "endpoint_bp": 0, "endpoint_bpc": 0,
    "failed_count": 0, "last_errors": [], "failed_ids_sample": [],
})
_icon_mod = MagicMock()
_icon_mod.EveIconService = MagicMock()
_icon_mod.EveIconService.instance = MagicMock(return_value=_icon_instance)

_cost_result = MagicMock()
_cost_result.average_buy_price = 0.0
_cost_instance = MagicMock()
_cost_instance.get_cost_basis = MagicMock(return_value=_cost_result)
_cost_mod = MagicMock()
_cost_mod.CostBasisService = MagicMock()
_cost_mod.CostBasisService.instance = MagicMock(return_value=_cost_instance)

_cfg_mod = MagicMock()
_cfg_mod.load_ui_config = MagicMock(return_value={})
_cfg_mod.save_ui_config = MagicMock()
_cfg_mod.load_market_filters = MagicMock(return_value=MagicMock())

_fmt_mod = MagicMock()
_fmt_mod.format_isk = MagicMock(side_effect=lambda v: f"{v:.2f}")

_item_helper = MagicMock()
_item_helper.open_market_with_fallback = MagicMock(return_value=True)
_widgets_mod = MagicMock()
_widgets_mod.ItemInteractionHelper = _item_helper

_tax_instance = MagicMock()
_tax_instance.get_effective_taxes = MagicMock(return_value=(3.0, 3.0, "mock", ""))
_tax_mod = MagicMock()
_tax_mod.TaxService = MagicMock()
_tax_mod.TaxService.instance = MagicMock(return_value=_tax_instance)

_diag_mod = MagicMock()
_diag_mod.format_my_orders_diagnostic_report = MagicMock(return_value="")

_MOCKS = {
    "core.eve_icon_service":              _icon_mod,
    "core.auth_manager":                  _auth_mod,
    "core.esi_client":                    MagicMock(),
    "core.market_engine":                 MagicMock(),
    "core.config_manager":                _cfg_mod,
    "core.item_metadata":                 MagicMock(),
    "core.cost_basis_service":            _cost_mod,
    "core.tax_service":                   _tax_mod,
    "core.my_orders_diagnostics":         _diag_mod,
    "utils.formatters":                   _fmt_mod,
    "ui.market_command.widgets":          _widgets_mod,
    "ui.market_command.performance_view": MagicMock(),
    "ui.market_command.diagnostics_dialog": MagicMock(),
}
for _mod_name, _mock_obj in _MOCKS.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mock_obj

# ---------------------------------------------------------------------------
# Qt setup
# ---------------------------------------------------------------------------
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication
_app = QApplication.instance() or QApplication(sys.argv)

# ---------------------------------------------------------------------------
# Import modules under test
# ---------------------------------------------------------------------------
from ui.market_command.my_orders_view import MarketMyOrdersView
from ui.market_command.quick_order_update_dialog import QuickOrderUpdateDialog
from core.market_order_pricing import build_order_update_recommendation

# ---------------------------------------------------------------------------
# Minimal data stubs
# ---------------------------------------------------------------------------
@dataclass
class _FakeAnalysis:
    is_buy: bool = False
    state: str = "Superada"
    gross_profit_per_unit: float = 100.0
    net_profit_per_unit: float = 80.0
    net_profit_total: float = 80_000.0
    margin_pct: float = 10.0
    best_buy: float = 900.0
    best_sell: float = 1_600.0
    spread_pct: float = 10.0
    competitive: bool = False
    difference_to_best: float = -50.0
    competitor_price: float = 1_596.0


@dataclass
class _FakeOrder:
    order_id: int = 42
    type_id: int = 5679      # Mystic S type_id (illustrative)
    item_name: str = "Mystic S"
    is_buy_order: bool = False
    price: float = 1_598.0   # Local cached price
    volume_total: int = 10
    volume_remain: int = 5
    issued: str = "2026-04-29T00:00:00Z"
    location_id: int = 60_003_760
    range: str = "station"
    analysis: Optional[object] = None


def _make_view() -> MarketMyOrdersView:
    return MarketMyOrdersView()


def _fresh_result(is_fresh=True, checked=True, order_exists=True,
                  old_price=1_598.0, fresh_price=1_598.0,
                  price_changed=False, warnings=None):
    """Build a synthetic freshness result dict."""
    return {
        "checked":       checked,
        "is_fresh":      is_fresh,
        "order_exists":  order_exists,
        "fresh_price":   fresh_price,
        "old_price":     old_price,
        "price_changed": price_changed,
        "warnings":      warnings or [],
        "fresh_order":   {"order_id": 42, "price": fresh_price} if order_exists else None,
    }


# ---------------------------------------------------------------------------
# 1-6: Unit tests for _revalidate_order_freshness
# ---------------------------------------------------------------------------
class TestRevalidateOrderFreshness(unittest.TestCase):

    def setUp(self):
        self.view  = _make_view()
        self.order = _FakeOrder()    # local price=1598

    def tearDown(self):
        self.view.close()

    def _call_freshness(self, esi_orders=None, raises=None, token="tok"):
        """Patch AuthManager+ESIClient and call _revalidate_order_freshness."""
        with patch("ui.market_command.my_orders_view.AuthManager") as mock_auth, \
             patch("ui.market_command.my_orders_view.ESIClient") as mock_esi:
            mock_auth.instance.return_value.get_valid_access_token.return_value = token
            if raises:
                mock_esi.return_value.character_orders.side_effect = raises
            else:
                mock_esi.return_value.character_orders.return_value = esi_orders or []
            return self.view._revalidate_order_freshness(self.order)

    # --- Test 1: fresh, same price ---
    def test_fresh_order_same_price(self):
        esi_orders = [{"order_id": 42, "price": 1_598.0, "type_id": 5679}]
        result = self._call_freshness(esi_orders)
        self.assertTrue(result["checked"],       "checked should be True")
        self.assertTrue(result["is_fresh"],      "is_fresh should be True")
        self.assertTrue(result["order_exists"],  "order_exists should be True")
        self.assertFalse(result["price_changed"],"price_changed should be False")
        self.assertEqual(result["warnings"],     [], "no warnings expected")

    # --- Test 2: price changed (Mystic S base case) ---
    def test_price_changed_blocks_auto_copy(self):
        esi_orders = [{"order_id": 42, "price": 1_594.0, "type_id": 5679}]
        result = self._call_freshness(esi_orders)
        self.assertTrue(result["checked"],        "checked should be True")
        self.assertFalse(result["is_fresh"],      "is_fresh should be False")
        self.assertTrue(result["order_exists"],   "order_exists should be True")
        self.assertTrue(result["price_changed"],  "price_changed should be True")
        self.assertAlmostEqual(result["fresh_price"], 1_594.0)
        self.assertAlmostEqual(result["old_price"],   1_598.0)
        self.assertGreater(len(result["warnings"]), 0, "must have at least one warning")

    # --- Test 3: order not found in ESI ---
    def test_order_not_found(self):
        esi_orders = [{"order_id": 999, "price": 500.0, "type_id": 34}]
        result = self._call_freshness(esi_orders)
        self.assertTrue(result["checked"],         "checked should be True")
        self.assertFalse(result["is_fresh"],       "is_fresh should be False")
        self.assertFalse(result["order_exists"],   "order_exists should be False")
        self.assertGreater(len(result["warnings"]), 0)

    # --- Test 4: ESI raises exception ---
    def test_esi_exception_blocks(self):
        result = self._call_freshness(raises=Exception("Network error"))
        self.assertFalse(result["checked"],  "checked should be False on exception")
        self.assertFalse(result["is_fresh"], "is_fresh should be False on exception")
        self.assertGreater(len(result["warnings"]), 0)

    # --- Test 5: no token ---
    def test_no_token_blocks(self):
        with patch("ui.market_command.my_orders_view.AuthManager") as mock_auth:
            mock_auth.instance.return_value.get_valid_access_token.return_value = None
            result = self.view._revalidate_order_freshness(self.order)
        self.assertFalse(result["checked"],  "checked should be False without token")
        self.assertFalse(result["is_fresh"], "is_fresh should be False without token")
        self.assertGreater(len(result["warnings"]), 0)

    # --- Test 6: Mystic S full case ---
    def test_mystic_s_case(self):
        """
        Real scenario: local order.price=1598, ESI returns 1594.
        competitor_price=1594 was wrongly used as competitor but is own order.
        Freshness must detect the stale local price and block auto-copy.
        """
        order = _FakeOrder(order_id=42, type_id=5679, price=1_598.0)
        esi_orders = [{"order_id": 42, "price": 1_594.0, "type_id": 5679}]

        with patch("ui.market_command.my_orders_view.AuthManager") as mock_auth, \
             patch("ui.market_command.my_orders_view.ESIClient") as mock_esi:
            mock_auth.instance.return_value.get_valid_access_token.return_value = "tok"
            mock_esi.return_value.character_orders.return_value = esi_orders
            result = self.view._revalidate_order_freshness(order)

        # Core assertion: freshness must be False
        self.assertFalse(result["is_fresh"])
        self.assertTrue(result["price_changed"])
        self.assertAlmostEqual(result["old_price"],   1_598.0)
        self.assertAlmostEqual(result["fresh_price"], 1_594.0)

        # Warnings must mention both prices
        combined = " ".join(result["warnings"])
        self.assertIn("1594", combined)
        self.assertIn("1598", combined)

    # --- Test 7: ESI returns empty list ---
    def test_empty_esi_response_blocks(self):
        result = self._call_freshness(esi_orders=[])
        self.assertTrue(result["checked"])
        self.assertFalse(result["is_fresh"])
        self.assertFalse(result["order_exists"])

    # --- Test 8: within tolerance (small float diff) ---
    def test_within_tolerance_is_fresh(self):
        # Prices that differ only by 0.001 ISK should still be considered fresh
        esi_orders = [{"order_id": 42, "price": 1_598.001, "type_id": 5679}]
        result = self._call_freshness(esi_orders)
        self.assertTrue(result["is_fresh"])
        self.assertFalse(result["price_changed"])


# ---------------------------------------------------------------------------
# 7-8: Integration with _launch_quick_order_update
# ---------------------------------------------------------------------------
class TestLaunchWithFreshness(unittest.TestCase):

    def setUp(self):
        self.view  = _make_view()
        self.order = _FakeOrder()
        self.order.analysis = _FakeAnalysis()
        self.view.all_orders = [self.order]

    def tearDown(self):
        self.view.close()

    def _launch(self, freshness_result):
        """Launch with mocked freshness, dialog, and market."""
        mock_dlg = MagicMock()
        _fresh_market = {
            "checked": True, "is_fresh": True, "used_fresh_price": False,
            "old_competitor_price": 1596.0, "fresh_competitor_price": 1596.0,
            "fresh_recommended_price": 1595.9, "fresh_best_buy": 1000.0,
            "fresh_best_sell": 1596.0, "price_source": "local_market",
            "warnings": [],
        }
        with patch("ui.market_command.my_orders_view.QuickOrderUpdateDialog",
                   return_value=mock_dlg), \
             patch.object(self.view, "_open_market_for_order", return_value=True), \
             patch.object(self.view, "_revalidate_order_freshness",
                          return_value=freshness_result), \
             patch.object(self.view, "_revalidate_market_competitor",
                          return_value=_fresh_market):
            self.view._launch_quick_order_update(self.order)
        return mock_dlg

    # --- Test 7: stale freshness → no clipboard copy ---
    def test_stale_freshness_no_auto_copy(self):
        QGuiApplication.clipboard().setText("")  # Reset

        stale = _fresh_result(
            is_fresh=False, checked=True, order_exists=True,
            old_price=1_598.0, fresh_price=1_594.0, price_changed=True,
            warnings=["Precio local desactualizado: local=1598 ISK, ESI=1594 ISK."],
        )
        self._launch(stale)

        cb = QGuiApplication.clipboard().text()
        self.assertEqual(cb, "", "clipboard must NOT be set when freshness is stale")

    # --- Test 8: fresh order → clipboard set ---
    def test_fresh_order_auto_copy(self):
        fresh = _fresh_result(
            is_fresh=True, checked=True, order_exists=True,
            old_price=1_598.0, fresh_price=1_598.0, price_changed=False,
        )
        self._launch(fresh)

        cb = QGuiApplication.clipboard().text()
        # For SELL order with competitor=1596 → tick=0.1 (price in 1000-10000 range)
        # recommended = 1596 - 0.1 = 1595.9
        # format_price_for_clipboard(1595.9) = "1595.9"
        self.assertNotEqual(cb, "", "clipboard MUST be set when order is fresh")
        # Confirm it's a numeric price, not an error string
        try:
            float(cb)
            is_numeric = True
        except ValueError:
            is_numeric = False
        self.assertTrue(is_numeric, f"clipboard must contain a number, got: {cb!r}")

    # --- Test 9: unchecked freshness (ESI error) → no clipboard ---
    def test_esi_error_no_auto_copy(self):
        QGuiApplication.clipboard().setText("")

        unchecked = _fresh_result(
            is_fresh=False, checked=False, order_exists=False,
            warnings=["Error al revalidar con ESI: Network error"],
        )
        self._launch(unchecked)

        cb = QGuiApplication.clipboard().text()
        self.assertEqual(cb, "", "clipboard must NOT be set when ESI check failed")


if __name__ == "__main__":
    unittest.main()
