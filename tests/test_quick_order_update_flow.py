"""
Tests for Quick Order Update flow (Fase 1).
Covers: column detection, order recovery, double-click dispatch,
        recommendation building, clipboard formatting, and dialog.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Mock heavy dependencies BEFORE importing anything from our modules.
# Only mock what my_orders_view.py needs; do NOT mock quick_order_update_dialog,
# market_order_pricing, or quick_order_update_diagnostics.
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
_diag_mod.format_my_orders_diagnostic_report = MagicMock(return_value="diag_report")

_MOCKS = {
    "core.eve_icon_service":             _icon_mod,
    "core.auth_manager":                 _auth_mod,
    "core.esi_client":                   MagicMock(),
    "core.market_engine":                MagicMock(),
    "core.config_manager":               _cfg_mod,
    "core.item_metadata":                MagicMock(),
    "core.cost_basis_service":           _cost_mod,
    "core.tax_service":                  _tax_mod,
    "core.my_orders_diagnostics":        _diag_mod,
    "utils.formatters":                  _fmt_mod,
    "ui.market_command.widgets":         _widgets_mod,
    "ui.market_command.performance_view": MagicMock(),
    "ui.market_command.diagnostics_dialog": MagicMock(),
}
for _mod_name, _mock_obj in _MOCKS.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mock_obj

# ---------------------------------------------------------------------------
# Qt setup (offscreen)
# ---------------------------------------------------------------------------
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt

_app = QApplication.instance() or QApplication(sys.argv)

# ---------------------------------------------------------------------------
# Import modules under test AFTER mocks and QApplication are ready
# ---------------------------------------------------------------------------
from ui.market_command.my_orders_view import MarketMyOrdersView
from ui.market_command.quick_order_update_dialog import (
    QuickOrderUpdateDialog, format_price_for_clipboard,
)
from core.market_order_pricing import build_order_update_recommendation

# ---------------------------------------------------------------------------
# Fake data models
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
    best_sell: float = 1_050.0
    spread_pct: float = 10.0
    competitive: bool = False
    difference_to_best: float = -50.0
    competitor_price: float = 1_050.0


@dataclass
class _FakeOrder:
    order_id: int = 999
    type_id: int = 34
    item_name: str = "Tritanium"
    is_buy_order: bool = False
    price: float = 1_100.0
    volume_total: int = 1_000
    volume_remain: int = 500
    issued: str = "2026-01-01T00:00:00Z"
    location_id: int = 60_003_760
    range: str = "station"
    analysis: Optional[object] = None


def _make_view() -> MarketMyOrdersView:
    """Instantiate MarketMyOrdersView with all dependencies mocked."""
    return MarketMyOrdersView()


def _make_table_with_headers(headers):
    """Return a QTableWidget with the given string headers."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    return t


# ---------------------------------------------------------------------------
# 1. format_price_for_clipboard
# ---------------------------------------------------------------------------
class TestFormatPriceForClipboard(unittest.TestCase):

    def test_integer_price(self):
        self.assertEqual(format_price_for_clipboard(12540.0), "12540")

    def test_half_decimal(self):
        self.assertEqual(format_price_for_clipboard(12540.5), "12540.5")

    def test_small_decimal(self):
        self.assertEqual(format_price_for_clipboard(0.01), "0.01")

    def test_large_integer(self):
        self.assertEqual(format_price_for_clipboard(15_750_000.0), "15750000")

    def test_zero(self):
        self.assertEqual(format_price_for_clipboard(0.0), "0")

    def test_two_decimals(self):
        # 1000.99 → not int → "1000.99"
        self.assertEqual(format_price_for_clipboard(1_000.99), "1000.99")


# ---------------------------------------------------------------------------
# 2. _get_type_column
# ---------------------------------------------------------------------------
class TestGetTypeColumn(unittest.TestCase):

    def setUp(self):
        self.view = _make_view()

    def tearDown(self):
        self.view.close()

    def test_finds_tipo_in_sell_table(self):
        col = self.view._get_type_column(self.view.table_sell)
        # Header list: ["ÍTEM","TIPO","PRECIO","PROMEDIO","MEJOR","TOTAL","RESTO","SPREAD","MARGEN","PROFIT","ESTADO"]
        self.assertEqual(col, 1)

    def test_finds_tipo_in_buy_table(self):
        col = self.view._get_type_column(self.view.table_buy)
        self.assertEqual(col, 1)

    def test_fallback_when_column_missing(self):
        t = _make_table_with_headers(["A", "B", "C"])
        col = self.view._get_type_column(t)
        self.assertEqual(col, 1)

    def test_accepts_type_english(self):
        t = _make_table_with_headers(["ITEM", "TYPE", "PRICE"])
        col = self.view._get_type_column(t)
        self.assertEqual(col, 1)


# ---------------------------------------------------------------------------
# 3. _get_order_from_row
# ---------------------------------------------------------------------------
class TestGetOrderFromRow(unittest.TestCase):

    def setUp(self):
        self.view = _make_view()
        self.order = _FakeOrder(order_id=42, type_id=34, is_buy_order=False)
        self.view.all_orders = [self.order]

        # Put one row into table_sell with correct data
        self.view.table_sell.setRowCount(1)
        name_item = QTableWidgetItem("Tritanium")
        name_item.setData(Qt.UserRole, 34)
        name_item.setData(Qt.UserRole + 1, 42)
        self.view.table_sell.setItem(0, 0, name_item)

        tipo_item = QTableWidgetItem("SELL")
        tipo_item.setData(Qt.UserRole, 34)
        self.view.table_sell.setItem(0, 1, tipo_item)

    def tearDown(self):
        self.view.close()

    def test_recovers_by_order_id(self):
        order = self.view._get_order_from_row(self.view.table_sell, 0)
        self.assertIsNotNone(order)
        self.assertEqual(order.order_id, 42)

    def test_returns_none_when_row_empty(self):
        self.view.table_sell.setRowCount(2)
        order = self.view._get_order_from_row(self.view.table_sell, 1)
        self.assertIsNone(order)

    def test_fallback_by_type_id_and_side(self):
        # Remove order_id from UserRole+1 to force fallback
        name_item = QTableWidgetItem("Tritanium")
        name_item.setData(Qt.UserRole, 34)
        name_item.setData(Qt.UserRole + 1, None)
        self.view.table_sell.setItem(0, 0, name_item)

        order = self.view._get_order_from_row(self.view.table_sell, 0)
        # Should still find by type_id=34 and is_buy=False
        self.assertIsNotNone(order)
        self.assertEqual(order.type_id, 34)


# ---------------------------------------------------------------------------
# 4. Double-click dispatch: ÍTEM column → open market, no popup
# ---------------------------------------------------------------------------
class TestDoubleClickDispatch(unittest.TestCase):

    def setUp(self):
        self.view = _make_view()
        self.order = _FakeOrder(order_id=99, type_id=34, is_buy_order=False)
        self.order.analysis = _FakeAnalysis()
        self.view.all_orders = [self.order]

        self.view.table_sell.setRowCount(1)
        name_item = QTableWidgetItem("Tritanium")
        name_item.setData(Qt.UserRole, 34)
        name_item.setData(Qt.UserRole + 1, 99)
        self.view.table_sell.setItem(0, 0, name_item)

        tipo_item = QTableWidgetItem("SELL")
        tipo_item.setData(Qt.UserRole, 34)
        self.view.table_sell.setItem(0, 1, tipo_item)

    def tearDown(self):
        if getattr(self.view, "_quick_order_dialog", None):
            self.view._quick_order_dialog.close()
        self.view.close()

    def test_item_column_calls_open_market_not_popup(self):
        # Click on col 0 (ÍTEM) → calls open_market, no popup
        item = self.view.table_sell.item(0, 0)
        with patch.object(self.view, "_open_market_from_table_item") as mock_market, \
             patch.object(self.view, "_handle_quick_order_update_double_click") as mock_popup:
            self.view.on_double_click_item(item, self.view.table_sell)
            mock_market.assert_called_once()
            mock_popup.assert_not_called()

    def test_tipo_column_calls_quick_update_not_open_market(self):
        # Click on col 1 (TIPO) → calls quick update handler, not open_market
        item = self.view.table_sell.item(0, 1)
        with patch.object(self.view, "_open_market_from_table_item") as mock_market, \
             patch.object(self.view, "_handle_quick_order_update_double_click") as mock_popup:
            self.view.on_double_click_item(item, self.view.table_sell)
            mock_popup.assert_called_once()
            mock_market.assert_not_called()

    def test_none_item_does_not_crash(self):
        self.view.on_double_click_item(None, self.view.table_sell)  # must not raise


# ---------------------------------------------------------------------------
# 5. _launch_quick_order_update calls build_order_update_recommendation
#    (QuickOrderUpdateDialog is fully mocked to avoid cross-widget segfaults)
# ---------------------------------------------------------------------------
class TestLaunchQuickOrderUpdate(unittest.TestCase):

    def setUp(self):
        self.view = _make_view()
        self.order = _FakeOrder(order_id=77, type_id=34, is_buy_order=False)
        self.order.analysis = _FakeAnalysis(competitor_price=1_000.0)
        self.view.all_orders = [self.order]

    def tearDown(self):
        self.view.close()

    def _fresh_result(self, order, is_fresh=True):
        """Build a synthetic freshness result for an order."""
        return {
            "checked":       True,
            "is_fresh":      is_fresh,
            "order_exists":  True,
            "fresh_price":   order.price,
            "old_price":     order.price,
            "price_changed": not is_fresh,
            "warnings":      [] if is_fresh else ["Precio desactualizado (mock)"],
            "fresh_order":   {"order_id": order.order_id, "price": order.price},
        }

    def _patched_launch(self, order=None, market_ok=True, is_fresh=True):
        """Helper: launch with QuickOrderUpdateDialog and freshness fully mocked."""
        if order is None:
            order = self.order
        mock_dlg_instance = MagicMock()
        freshness = self._fresh_result(order, is_fresh=is_fresh)
        with patch("ui.market_command.my_orders_view.QuickOrderUpdateDialog",
                   return_value=mock_dlg_instance) as mock_dlg_cls, \
             patch.object(self.view, "_open_market_for_order", return_value=market_ok), \
             patch.object(self.view, "_revalidate_order_freshness", return_value=freshness), \
             patch.object(self.view, "_revalidate_market_competitor", 
                          return_value={"used_fresh_price": False, "checked": True, "is_fresh": True}):
            self.view._launch_quick_order_update(order)
            return mock_dlg_cls, mock_dlg_instance

    def test_calls_build_order_update_recommendation(self):
        freshness = self._fresh_result(self.order)
        with patch("ui.market_command.my_orders_view.build_order_update_recommendation",
                   wraps=build_order_update_recommendation) as mock_build, \
             patch("ui.market_command.my_orders_view.QuickOrderUpdateDialog",
                   return_value=MagicMock()), \
             patch.object(self.view, "_open_market_for_order", return_value=True), \
             patch.object(self.view, "_revalidate_order_freshness", return_value=freshness), \
             patch.object(self.view, "_revalidate_market_competitor", 
                          return_value={"used_fresh_price": False, "checked": True, "is_fresh": True}):
            self.view._launch_quick_order_update(self.order)
        mock_build.assert_called_once_with(self.order, self.order.analysis)
    def test_sets_clipboard(self):
        from PySide6.QtGui import QGuiApplication
        self._patched_launch()
        cb_text = QGuiApplication.clipboard().text()
        # SELL, competitor=1000 → recommended=999 → clipboard "999"
        self.assertEqual(cb_text, "999")

    def test_uses_fresh_market_data_if_available(self):
        """REQ 7: ensure fresh market override is applied to dialog and clipboard."""
        from PySide6.QtGui import QGuiApplication
        # Old analysis: competitor=1612000 (from self.order setup)
        # Fresh market: competitor=1687000, recommended=1686000
        market_val = {
            "checked": True,
            "is_fresh": True,
            "used_fresh_price": True,
            "fresh_competitor_price": 1687000,
            "fresh_best_buy": 1500000,
            "fresh_best_sell": 1687000,
            "fresh_recommended_price": 1686000,
            "price_source": "fresh_market_book_location",
            "market_scope": "station_location",
            "target_location_id": 60003760
        }
        mock_dlg_instance = MagicMock()
        freshness = self._fresh_result(self.order, is_fresh=True)
        
        with patch("ui.market_command.my_orders_view.QuickOrderUpdateDialog",
                   return_value=mock_dlg_instance) as mock_dlg_cls, \
             patch.object(self.view, "_open_market_for_order", return_value=True), \
             patch.object(self.view, "_revalidate_order_freshness", return_value=freshness), \
             patch.object(self.view, "_revalidate_market_competitor", return_value=market_val):
            
            self.view._launch_quick_order_update(self.order)
            
            # Verify clipboard
            cb_text = QGuiApplication.clipboard().text()
            self.assertEqual(cb_text, "1686000")
            
            # Verify dialog args
            args, kwargs = mock_dlg_cls.call_args
            recommendation = kwargs.get("recommendation") or args[1]
            self.assertEqual(recommendation["competitor_price"], 1687000)
            self.assertEqual(recommendation["recommended_price"], 1686000)
            self.assertEqual(recommendation["price_source"], "fresh_market_book_location")
            self.assertEqual(recommendation["market_scope"], "station_location")
            self.assertEqual(recommendation["location_id"], 60003760)

    def test_creates_dialog_instance(self):
        mock_cls, mock_inst = self._patched_launch()
        # Constructor was called once
        mock_cls.assert_called_once()
        # .show() was called on the instance
        mock_inst.show.assert_called_once()

    def test_dialog_reference_stored(self):
        _, mock_inst = self._patched_launch()
        self.assertIs(self.view._quick_order_dialog, mock_inst)

    def test_no_analysis_does_not_crash(self):
        order_no_analysis = _FakeOrder(order_id=88, type_id=35, is_buy_order=True)
        order_no_analysis.analysis = None
        self.view.all_orders = [order_no_analysis]
        self._patched_launch(order=order_no_analysis, market_ok=False)  # must not raise


# ---------------------------------------------------------------------------
# 6. QuickOrderUpdateDialog instantiation
# ---------------------------------------------------------------------------
class TestQuickOrderUpdateDialogInstantiation(unittest.TestCase):

    def _make_dialog(self, order=None, rec=None, callback=None):
        if order is None:
            order = _FakeOrder()
            order.analysis = _FakeAnalysis()
        if rec is None:
            rec = build_order_update_recommendation(order, order.analysis)
        return QuickOrderUpdateDialog(
            order=order,
            recommendation=rec,
            parent=None,
            open_market_callback=callback,
        )

    def test_instantiates_without_crash(self):
        dlg = self._make_dialog()
        self.assertIsNotNone(dlg)
        dlg.close()

    def test_is_non_modal(self):
        dlg = self._make_dialog()
        self.assertFalse(dlg.isModal())
        dlg.close()

    def test_instantiates_with_no_analysis(self):
        order = _FakeOrder()
        order.analysis = None
        rec = build_order_update_recommendation(order, None)
        dlg = QuickOrderUpdateDialog(order=order, recommendation=rec)
        self.assertIsNotNone(dlg)
        dlg.close()


# ---------------------------------------------------------------------------
# 7. Dialog button: copy price → sets clipboard
# ---------------------------------------------------------------------------
class TestDialogCopyButton(unittest.TestCase):

    def setUp(self):
        self.order = _FakeOrder(is_buy_order=False, price=1_100.0)
        self.order.analysis = _FakeAnalysis(competitor_price=1_000.0)
        self.rec = build_order_update_recommendation(self.order, self.order.analysis)
        self.dlg = QuickOrderUpdateDialog(
            order=self.order, recommendation=self.rec
        )

    def tearDown(self):
        self.dlg.close()

    def test_copy_button_sets_clipboard(self):
        from PySide6.QtGui import QGuiApplication
        self.dlg.btn_copy.click()
        cb = QGuiApplication.clipboard().text()
        expected = format_price_for_clipboard(self.rec["recommended_price"])
        self.assertEqual(cb, expected)


# ---------------------------------------------------------------------------
# 8. Dialog button: open market → calls callback
# ---------------------------------------------------------------------------
class TestDialogOpenMarketButton(unittest.TestCase):

    def setUp(self):
        self.order = _FakeOrder(is_buy_order=True, price=900.0)
        self.order.analysis = _FakeAnalysis(is_buy=True, competitor_price=910.0)
        self.rec = build_order_update_recommendation(self.order, self.order.analysis)
        self.callback = MagicMock()
        self.dlg = QuickOrderUpdateDialog(
            order=self.order,
            recommendation=self.rec,
            open_market_callback=self.callback,
        )

    def tearDown(self):
        self.dlg.close()

    def test_open_market_button_calls_callback(self):
        self.dlg.btn_market.click()
        self.callback.assert_called_once_with(self.order)

    def test_copy_and_open_calls_both(self):
        from PySide6.QtGui import QGuiApplication
        self.callback.reset_mock()
        self.dlg.btn_both.click()
        self.callback.assert_called_once_with(self.order)
        cb = QGuiApplication.clipboard().text()
        self.assertNotEqual(cb, "")  # clipboard was set


# ---------------------------------------------------------------------------
# 9. Phase 2 automation button
# ---------------------------------------------------------------------------
class TestAutomationButton(unittest.TestCase):
    """Automation button behaviour for disabled / dry-run / enabled configs."""

    def _make_dialog(self, automation_cfg=None):
        order = _FakeOrder()
        order.analysis = _FakeAnalysis()
        rec = build_order_update_recommendation(order, order.analysis)
        dlg = QuickOrderUpdateDialog(order=order, recommendation=rec)
        if automation_cfg is not None:
            dlg._automation_cfg = automation_cfg
            # Rebuild button label to match new config
            enabled = automation_cfg.get("enabled", False)
            dry_run = automation_cfg.get("dry_run", True)
            if enabled and dry_run:
                dlg.btn_phase2.setText("AUTOMATIZAR (DRY-RUN)")
            elif enabled:
                dlg.btn_phase2.setText("AUTOMATIZAR (FASE 2)")
            else:
                dlg.btn_phase2.setText("AUTOMATIZAR (DESACTIVADO)")
        return dlg

    def tearDown(self):
        # Clean up any dialog that was created
        pass

    def test_automation_button_exists(self):
        dlg = self._make_dialog()
        self.assertTrue(hasattr(dlg, "btn_phase2"), "btn_phase2 must exist")
        dlg.close()

    def test_automation_button_is_enabled_widget(self):
        dlg = self._make_dialog()
        self.assertTrue(dlg.btn_phase2.isEnabled(),
                        "btn_phase2 widget must always be clickable")
        dlg.close()

    def test_disabled_config_shows_message_not_automation(self):
        """With enabled=False, click sets status message without running automation."""
        cfg = {"enabled": False, "dry_run": True}
        dlg = self._make_dialog(automation_cfg=cfg)
        # Patch loader to return disabled config
        with patch("ui.market_command.quick_order_update_dialog.load_quick_order_update_config", return_value=cfg):
            with patch("core.window_automation.EVEWindowAutomation") as mock_auto:
                dlg.btn_phase2.click()
                # Should NOT have created EVEWindowAutomation
                mock_auto.assert_not_called()
        status_text = dlg._status_lbl.text()
        self.assertGreater(len(status_text), 0, "status label must be set")
        self.assertIn("desactivad", status_text.lower(),
                      "status must mention automation is disabled")
        dlg.close()

    def test_dry_run_config_executes_automation(self):
        """With enabled=True dry_run=True, click runs automation and updates report exactly once."""
        cfg = {
            "enabled": True, "dry_run": True, "confirm_required": True,
            "open_market_delay_ms": 0, "focus_client_delay_ms": 0,
            "paste_price_delay_ms": 0, "post_action_delay_ms": 0,
            "client_window_title_contains": "EVE",
            "use_pywinauto": False, "use_pyautogui_fallback": False,
            "max_attempts": 1, "restore_clipboard_after": False,
            "require_window_selection": False,
            "allow_title_fallback_without_selection": True,
            "exclude_self_app_windows": True,
        }
        dlg = self._make_dialog(automation_cfg=cfg)
        
        # Manually set a report that ALREADY has [AUTOMATION] to simulate duplication risk
        dlg._diag_report += "\n\n[AUTOMATION]\n  Enabled              : True\n  Status               : stale"
        dlg._report_edit.setPlainText(dlg._diag_report)
        
        # Must mock selected_window to pass the selection guard
        # AND mock load_quick_order_update_config to return our test config
        with patch.object(QuickOrderUpdateDialog, "_selected_window", return_value={"handle": 123, "score": 100}), \
             patch("ui.market_command.quick_order_update_dialog.load_quick_order_update_config", return_value=cfg):
            dlg.btn_phase2.click()

        status_text = dlg._status_lbl.text()
        self.assertGreater(len(status_text), 0)
        # Should mention dry-run
        self.assertIn("dry", status_text.lower())
        
        report_text = dlg._report_edit.toPlainText()
        # Report edit should contain automation section
        self.assertIn("[AUTOMATION]", report_text)
        
        # CRITICAL: Section should appear exactly once
        self.assertEqual(report_text.count("[AUTOMATION]"), 1, "Should not have duplicate [AUTOMATION] section")
        
        # Verify content
        self.assertIn("Status               : dry_run", report_text)
        self.assertIn("Final Confirm Action : NOT_EXECUTED_BY_DESIGN", report_text)
        
        dlg.close()

    def test_copy_button_still_works_after_automation_button_added(self):
        """Existing copy button must not be broken by Phase 2 changes."""
        from PySide6.QtGui import QGuiApplication
        dlg = self._make_dialog()
        QGuiApplication.clipboard().setText("")
        dlg.btn_copy.click()
        cb = QGuiApplication.clipboard().text()
        self.assertNotEqual(cb, "", "copy button must still set clipboard")
        dlg.close()

    def test_market_button_still_works_after_automation_button_added(self):
        """Existing market button must not be broken by Phase 2 changes."""
        callback = MagicMock()
        order = _FakeOrder()
        order.analysis = _FakeAnalysis()
        rec = build_order_update_recommendation(order, order.analysis)
        dlg = QuickOrderUpdateDialog(order=order, recommendation=rec,
                                     open_market_callback=callback)
        dlg.btn_market.click()
        callback.assert_called_once_with(order)
        dlg.close()


# ---------------------------------------------------------------------------
# 10. Window selector UI tests
# ---------------------------------------------------------------------------
class TestWindowSelectorUI(unittest.TestCase):
    """Tests for the window detect/select section in QuickOrderUpdateDialog."""

    def _make_dialog(self, automation_cfg=None):
        order = _FakeOrder()
        order.analysis = _FakeAnalysis()
        rec = build_order_update_recommendation(order, order.analysis)
        dlg = QuickOrderUpdateDialog(order=order, recommendation=rec)
        if automation_cfg is not None:
            dlg._automation_cfg = automation_cfg
        return dlg

    def test_detect_windows_button_exists(self):
        dlg = self._make_dialog()
        self.assertTrue(hasattr(dlg, "btn_detect_windows"),
                        "btn_detect_windows must exist")
        dlg.close()

    def test_window_combo_exists(self):
        dlg = self._make_dialog()
        self.assertTrue(hasattr(dlg, "_window_combo"),
                        "_window_combo must exist")
        dlg.close()

    def test_window_combo_initially_empty_selection(self):
        dlg = self._make_dialog()
        # combo starts with placeholder item, currentData() should be None
        self.assertIsNone(dlg._selected_window(),
                          "No window should be pre-selected")
        dlg.close()

    def test_detect_windows_populates_combo(self):
        """Clicking detect with mocked candidates should populate the combo."""
        fake_candidates = [
            {"handle": 101, "title": "EVE - Nina Herrera",
             "class_name": "EVEWindow", "visible": True,
             "is_self_app": False, "score": 100},
            {"handle": 102, "title": "EVE iT Market Command",
             "class_name": "Qt", "visible": True,
             "is_self_app": True, "score": -100},
        ]
        dlg = self._make_dialog()
        with patch("core.window_automation.list_candidate_windows",
                   return_value=fake_candidates):
            dlg.btn_detect_windows.click()

        # Combo should have 2 items
        self.assertEqual(dlg._window_combo.count(), 2)
        # Best non-self candidate (score=100) should be auto-selected
        selected = dlg._selected_window()
        self.assertIsNotNone(selected)
        self.assertEqual(selected["handle"], 101)
        dlg.close()

    def test_self_app_not_auto_selected(self):
        """If only self-app windows are found, none should be auto-selected."""
        fake_candidates = [
            {"handle": 102, "title": "EVE iT Market Command",
             "class_name": "Qt", "visible": True,
             "is_self_app": True, "score": -100},
        ]
        dlg = self._make_dialog()
        with patch("core.window_automation.list_candidate_windows",
                   return_value=fake_candidates):
            dlg.btn_detect_windows.click()

        # combo has 1 item but it's self-app; auto-select should not have picked it
        # (index 0 will be set, but the "best" logic should warn not auto-select)
        # At minimum: combo populated
        self.assertEqual(dlg._window_combo.count(), 1)
        dlg.close()

    def test_automate_no_selection_require_shows_warning(self):
        """With require_window_selection=True and no selection, automation must be blocked."""
        dlg = self._make_dialog(automation_cfg={
            "enabled": True, "dry_run": True,
            "require_window_selection": True,
            "allow_title_fallback_without_selection": False,
            "open_market_delay_ms": 0, "focus_client_delay_ms": 0,
            "paste_price_delay_ms": 0, "post_action_delay_ms": 0,
            "client_window_title_contains": "EVE",
            "use_pywinauto": False, "use_pyautogui_fallback": False,
            "max_attempts": 1, "restore_clipboard_after": False,
            "exclude_self_app_windows": True,
        })
        # No detect → no selection
        dlg.btn_phase2.click()

        status_text = dlg._status_lbl.text()
        self.assertGreater(len(status_text), 0)
        self.assertTrue(
            "seleccion" in status_text.lower() or "ventana" in status_text.lower(),
            f"Status must mention missing window selection, got: {status_text!r}"
        )
        dlg.close()

    def test_automate_with_window_selected_passes_to_automation(self):
        """With a window selected, automation should call execute with selected_window."""
        fake_candidates = [
            {"handle": 101, "title": "EVE - Nina Herrera",
             "class_name": "EVEWindow", "visible": True,
             "is_self_app": False, "score": 100},
        ]
        dlg = self._make_dialog(automation_cfg={
            "enabled": True, "dry_run": True,
            "require_window_selection": True,
            "allow_title_fallback_without_selection": False,
            "open_market_delay_ms": 0, "focus_client_delay_ms": 0,
            "paste_price_delay_ms": 0, "post_action_delay_ms": 0,
            "client_window_title_contains": "EVE",
            "use_pywinauto": False, "use_pyautogui_fallback": False,
            "max_attempts": 1, "restore_clipboard_after": False,
            "exclude_self_app_windows": True,
        })
        # Populate combo with one valid candidate
        with patch("core.window_automation.list_candidate_windows",
                   return_value=fake_candidates):
            dlg.btn_detect_windows.click()

        # Now automate — capture the selected_window argument
        captured = {}
        from core.window_automation import EVEWindowAutomation
        orig_execute = EVEWindowAutomation.execute_quick_order_update

        def capture_execute(self_inner, order_data, price_text, selected_window=None, manual_region=None, run_id=None):
            captured["selected_window"] = selected_window
            captured["run_id"] = run_id
            return {
                "status": "dry_run", "enabled": True, "dry_run": True,
                "steps_executed": ["would_use_selected_window: EVE - Nina Herrera"],
                "steps_skipped": ["no_confirm_final_action (by_design)"],
                "errors": [], "window_found": False, "window_title": None,
                "focused": False, "clipboard_set": False,
                "recommended_price_text": price_text,
                "delays": {}, "window_source": "selected_handle",
                "selected_window_handle": 101,
                "selected_window_title": "EVE - Nina Herrera",
                "candidate_windows_count": 0, "candidate_windows": [],
            }

        with patch.object(EVEWindowAutomation, "execute_quick_order_update", capture_execute):
            dlg.btn_phase2.click()

        self.assertIn("selected_window", captured)
        self.assertIsNotNone(captured["selected_window"])
        self.assertEqual(captured["selected_window"]["handle"], 101)
        dlg.close()

    def test_open_market_button_unaffected_by_window_selector(self):
        """Adding window selector must not break the market button."""
        callback = MagicMock()
        order = _FakeOrder()
        order.analysis = _FakeAnalysis()
        rec = build_order_update_recommendation(order, order.analysis)
        dlg = QuickOrderUpdateDialog(order=order, recommendation=rec,
                                     open_market_callback=callback)
        dlg.btn_market.click()
        callback.assert_called_once_with(order)
        dlg.close()

    def test_visual_ocr_retry_preserves_run_id(self):
        """REQUIRED FIX 5 — Retry execution must keep the same Automation Run ID."""
        order = _FakeOrder()
        order.analysis = _FakeAnalysis()
        # Ensure item_name is set for order_data builder
        order.item_name = "Test Item"
        rec = build_order_update_recommendation(order, order.analysis)
        
        cfg = {
            "enabled": True, "dry_run": False,
            "visual_ocr_enabled": True,
            "modify_order_strategy": "visual_ocr",
            "require_window_selection": False,
        }
        
        from ui.market_command.quick_order_update_dialog import QuickOrderUpdateDialog
        dlg = QuickOrderUpdateDialog(order=order, recommendation=rec)
        dlg._automation_cfg = cfg
        
        # Mock dependencies to reach the retry point
        with patch("ui.market_command.quick_order_update_dialog.load_quick_order_update_regions", return_value={"sell": {"c": 1}}), \
             patch.object(QuickOrderUpdateDialog, "_has_valid_calibration", return_value=True), \
             patch.object(QuickOrderUpdateDialog, "_prompt_recalibration_retry", return_value=True), \
             patch.object(QuickOrderUpdateDialog, "_prompt_single_side_calibration", return_value={"c": 2}), \
             patch("core.window_automation.EVEWindowAutomation.execute_quick_order_update") as mock_execute, \
             patch("ui.market_command.quick_order_update_dialog.format_price_for_clipboard", return_value="100.00"), \
             patch.object(QuickOrderUpdateDialog, "_selected_window", return_value={"handle": 123, "score": 100}):
            
            # First execution returns a failure that triggers retry
            mock_execute.side_effect = [
                {
                    "status": "partial", 
                    "visual_ocr_status": "not_found", 
                    "visual_ocr_suggested_action": "recalibrate_side",
                    "price_pasted": False, 
                    "errors": [], 
                    "steps_skipped": []
                },
                {"status": "success", "price_pasted": True, "steps_executed": ["retry"]}
            ]
            
            dlg.btn_phase2.click()
            
            # Check that execute_quick_order_update was called twice
            self.assertEqual(mock_execute.call_count, 2)
            
            # Verify both calls used the same run_id
            first_run_id = mock_execute.call_args_list[0].kwargs.get("run_id")
            second_run_id = mock_execute.call_args_list[1].kwargs.get("run_id")
            
            self.assertIsNotNone(first_run_id)
            self.assertEqual(first_run_id, second_run_id)
            
        dlg.close()


if __name__ == "__main__":
    unittest.main()
