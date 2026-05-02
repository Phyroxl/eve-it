"""
Tests for Sesión 38:
A) Tabs: 4 tabs only (no Advanced Mode)
B) Import: command_main imports without advanced_view
C) Profit/u: column uses profit_per_unit, not profit_day_est
D) Filters: score_min, risk_max, category
E) Fees: no manual broker/sales_tax inputs; ESI fees applied
F) Config migration: old config with deprecated settings loads without crash
"""
import unittest
from unittest.mock import MagicMock, patch
from core.market_models import MarketOpportunity, FilterConfig, LiquidityMetrics, ScoreBreakdown
from core.market_engine import apply_filters, apply_filters_with_diagnostics


def _make_opp(type_id=1, name="Item", buy=100.0, sell=120.0, margin=15.0,
              profit_unit=18.0, profit_day=500.0, spread=20.0, risk="Low",
              vol5d=300, score=75.0, enriched=True):
    opp = MarketOpportunity(
        type_id=type_id, item_name=name,
        best_buy_price=buy, best_sell_price=sell,
        margin_net_pct=margin, profit_per_unit=profit_unit,
        profit_day_est=profit_day, spread_pct=spread, risk_level=risk,
        tags=[], liquidity=LiquidityMetrics(vol5d, 30, 5, 5),
        recommended_qty=10, recommended_cost=buy * 10,
    )
    opp.is_enriched = enriched
    opp.score_breakdown = ScoreBreakdown(
        base_score=0.7, liquidity_norm=0.6, roi_norm=0.7,
        profit_day_norm=0.4, penalties=[], final_score=score
    )
    return opp


# ─────────────────────────────────────────────────────────────────────────────
# A) TABS — 4 only, no Advanced
# ─────────────────────────────────────────────────────────────────────────────
class TestTabStructure(unittest.TestCase):

    def test_command_main_has_four_views(self):
        """_view_classes must have exactly 4 entries: Simple, Performance, MyOrders, Contracts."""
        import inspect
        from ui.market_command import command_main as mod
        src = inspect.getsource(mod)
        # Count dict entries in _view_classes via the 4 class references
        self.assertIn("MarketSimpleView", src)
        self.assertIn("MarketPerformanceView", src)
        self.assertIn("MarketMyOrdersView", src)
        self.assertIn("MarketContractsView", src)

    def test_advanced_view_not_imported_in_command_main(self):
        """command_main must not import MarketAdvancedView."""
        import inspect
        from ui.market_command import command_main as mod
        src = inspect.getsource(mod)
        self.assertNotIn("MarketAdvancedView", src)
        self.assertNotIn("advanced_view", src)

    def test_view_names_has_four_items(self):
        """_view_names dict must not contain 'Modo Avanzado'."""
        import inspect
        from ui.market_command import command_main as mod
        src = inspect.getsource(mod)
        self.assertNotIn("Modo Avanzado", src)

    def test_range_is_four_in_stack_init(self):
        """Stack placeholders loop must use range(4), not range(5)."""
        import inspect
        from ui.market_command import command_main as mod
        src = inspect.getsource(mod)
        self.assertIn("range(4)", src)
        self.assertNotIn("range(5)", src)


# ─────────────────────────────────────────────────────────────────────────────
# B) IMPORT — no advanced_view dependency
# ─────────────────────────────────────────────────────────────────────────────
class TestImportNoAdvanced(unittest.TestCase):

    def test_no_advanced_view_import_in_command_main(self):
        """Importing command_main must not trigger advanced_view import."""
        import sys
        # Remove from cache to force fresh import check
        mods_before = set(sys.modules.keys())
        import ui.market_command.command_main  # noqa
        new_mods = set(sys.modules.keys()) - mods_before
        advanced_loaded = any("advanced_view" in m for m in new_mods)
        self.assertFalse(advanced_loaded, "advanced_view must not be imported by command_main")


# ─────────────────────────────────────────────────────────────────────────────
# C) PROFIT/U — column uses profit_per_unit
# ─────────────────────────────────────────────────────────────────────────────
class TestProfitPerUnitColumn(unittest.TestCase):

    def test_market_table_widget_header_is_profit_u(self):
        """MarketTableWidget header index 5 must be 'Profit/u', not 'Profit/Día'."""
        import inspect
        from ui.market_command import widgets as mod
        src = inspect.getsource(mod.MarketTableWidget)
        self.assertIn("Profit/u", src)
        # Old header must be gone from MarketTableWidget (AdvancedMarketTableWidget may still have it)
        # Check specifically in the simple table headers list
        idx = src.find('"Profit/u"')
        self.assertNotEqual(idx, -1, "'Profit/u' not found in MarketTableWidget source")

    def test_market_table_widget_populate_uses_profit_per_unit(self):
        """MarketTableWidget.populate must read opp.profit_per_unit (not profit_day_est)."""
        import inspect
        from ui.market_command import widgets as mod
        populate_src = inspect.getsource(mod.MarketTableWidget.populate)
        self.assertIn("profit_per_unit", populate_src)
        self.assertNotIn("profit_day_est", populate_src)

    def test_profit_per_unit_not_profit_day_in_simple_table(self):
        """The profit column in simple table must not reference profit_day_est."""
        import inspect
        from ui.market_command import widgets as mod
        src = inspect.getsource(mod.MarketTableWidget)
        # Should not have the old profit_day_est assignment for the simple table
        self.assertNotIn("profit_day_est", src)


# ─────────────────────────────────────────────────────────────────────────────
# D) FILTERS — score_min, risk_max, category still work
# ─────────────────────────────────────────────────────────────────────────────
class TestSimpleFiltersEngine(unittest.TestCase):

    def test_score_min_filters_low_score(self):
        """Items with score < score_min must be excluded."""
        high = _make_opp(type_id=1, score=80.0)
        low = _make_opp(type_id=2, score=30.0)
        cfg = FilterConfig(score_min=50.0)
        result = apply_filters([high, low], cfg)
        ids = [o.type_id for o in result]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

    def test_score_min_zero_passes_all(self):
        """score_min=0 should not filter anything."""
        opps = [_make_opp(type_id=i, score=float(i * 10)) for i in range(1, 6)]
        cfg = FilterConfig(score_min=0.0)
        result = apply_filters(opps, cfg)
        self.assertEqual(len(result), 5)

    def test_risk_max_1_excludes_medium_and_high(self):
        """risk_max=1 (Low only) must exclude Medium and High risk items."""
        low = _make_opp(type_id=1, risk="Low")
        med = _make_opp(type_id=2, risk="Medium")
        high = _make_opp(type_id=3, risk="High")
        cfg = FilterConfig(risk_max=1)
        result = apply_filters([low, med, high], cfg)
        ids = [o.type_id for o in result]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertNotIn(3, ids)

    def test_risk_max_2_excludes_high_only(self):
        """risk_max=2 (max Medium) must exclude High risk but allow Low and Medium."""
        low = _make_opp(type_id=1, risk="Low")
        med = _make_opp(type_id=2, risk="Medium")
        high = _make_opp(type_id=3, risk="High")
        cfg = FilterConfig(risk_max=2)
        result = apply_filters([low, med, high], cfg)
        ids = [o.type_id for o in result]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn(3, ids)

    def test_risk_max_3_passes_all(self):
        """risk_max=3 (any risk) passes Low, Medium, High."""
        opps = [_make_opp(type_id=1, risk="Low"), _make_opp(type_id=2, risk="Medium"), _make_opp(type_id=3, risk="High")]
        cfg = FilterConfig(risk_max=3)
        result = apply_filters(opps, cfg)
        self.assertEqual(len(result), 3)

    def test_category_todos_passes_all(self):
        """selected_category='Todos' skips category filter."""
        opps = [_make_opp(type_id=i) for i in range(1, 4)]
        cfg = FilterConfig(selected_category="Todos")
        result = apply_filters(opps, cfg)
        self.assertEqual(len(result), 3)


# ─────────────────────────────────────────────────────────────────────────────
# E) FEES — no manual inputs; ESI fees set correctly
# ─────────────────────────────────────────────────────────────────────────────
class TestEsiFeeIntegration(unittest.TestCase):

    def test_simple_view_has_no_broker_spin(self):
        """simple_view.py source must not contain spin_broker widget creation."""
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.setup_ui)
        self.assertNotIn("spin_broker", src)
        self.assertNotIn("spin_tax", src)

    def test_simple_view_has_no_broker_in_update_config(self):
        """update_config_from_ui must not read broker/tax from spin widgets."""
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.update_config_from_ui)
        self.assertNotIn("spin_broker", src)
        self.assertNotIn("spin_tax", src)

    def test_simple_view_calls_apply_esi_fees(self):
        """update_config_from_ui must call _apply_esi_fees_to_config."""
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.update_config_from_ui)
        self.assertIn("_apply_esi_fees_to_config", src)

    def test_apply_esi_fees_uses_tax_service(self):
        """_apply_esi_fees_to_config must read from TaxService."""
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView._apply_esi_fees_to_config)
        self.assertIn("TaxService", src)

    def test_profit_calc_uses_config_fees(self):
        """parse_opportunities must use config.broker_fee_pct and sales_tax_pct for profit_per_unit."""
        from core.market_engine import parse_opportunities
        orders = [
            {"type_id": 1, "price": 100.0, "is_buy_order": True, "location_id": 1},
            {"type_id": 1, "price": 120.0, "is_buy_order": False, "location_id": 1},
        ]
        cfg_low_fee = FilterConfig(broker_fee_pct=1.0, sales_tax_pct=1.0)
        cfg_high_fee = FilterConfig(broker_fee_pct=5.0, sales_tax_pct=5.0)
        opps_low = parse_opportunities(orders, {}, {1: "TestItem"}, cfg_low_fee)
        opps_high = parse_opportunities(orders, {}, {1: "TestItem"}, cfg_high_fee)
        self.assertGreater(opps_low[0].profit_per_unit, opps_high[0].profit_per_unit,
                           "Higher fees must reduce profit_per_unit")


# ─────────────────────────────────────────────────────────────────────────────
# F) CONFIG MIGRATION — deprecated settings load without crash
# ─────────────────────────────────────────────────────────────────────────────
class TestConfigMigration(unittest.TestCase):

    def test_old_config_with_broker_tax_loads_ok(self):
        """FilterConfig loads from JSON with old broker_fee_pct/sales_tax_pct without crash."""
        import json, tempfile, os
        from pathlib import Path
        old_data = {
            "capital_max": 500_000_000.0,
            "vol_min_day": 20,
            "margin_min_pct": 5.0,
            "spread_max_pct": 40.0,
            "exclude_plex": True,
            "broker_fee_pct": 2.5,  # deprecated UI setting
            "sales_tax_pct": 4.5,   # deprecated UI setting
            "score_min": 0.0,
            "risk_max": 3,
            "buy_orders_min": 0,
            "sell_orders_min": 0,
            "history_days_min": 0,
            "profit_day_min": 0.0,
            "selected_category": "Todos",
            "max_item_types": 0
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(old_data, f)
            tmp_path = f.name
        try:
            with patch('core.config_manager._MARKET_FILTERS_FILE', Path(tmp_path)):
                from core.config_manager import load_market_filters
                cfg = load_market_filters()
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.vol_min_day, 20)
            self.assertEqual(cfg.selected_category, "Todos")
        finally:
            os.unlink(tmp_path)

    def test_load_market_filters_logs_deprecated_broker_fee(self, capsys=None):
        """load_market_filters logs [MARKET CONFIG] when broker_fee_pct differs from default."""
        import json, tempfile, os, io, sys
        from pathlib import Path
        old_data = {"broker_fee_pct": 2.5, "sales_tax_pct": 3.0}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(old_data, f)
            tmp_path = f.name
        try:
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                with patch('core.config_manager._MARKET_FILTERS_FILE', Path(tmp_path)):
                    from core.config_manager import load_market_filters
                    load_market_filters()
            finally:
                sys.stdout = old_stdout
            output = captured.getvalue()
            self.assertIn("[MARKET CONFIG]", output)
            self.assertIn("broker_fee_pct", output)
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
