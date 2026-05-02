"""
Tests for profit breakdown, detail panel size, and tactical filters.

A) Profit breakdown Manticore: verify formula with ESI fees vs defaults.
B) Profit/u formula: independent of qty, no day estimate, fee-sensitive.
C) Panel detail: height >= 99px, tooltip/breakdown exists.
D) New filters: profit_unit_min, capital_min, buy/sell_orders_min,
   history_days_min, require_buy_sell, old config loads without crash.
E) Fees: no manual inputs, fees_source in log.
"""
import unittest
from unittest.mock import patch

from core.market_models import FilterConfig, LiquidityMetrics, ScoreBreakdown, MarketOpportunity
from core.market_engine import apply_filters, apply_filters_with_diagnostics, compute_profit_breakdown


def _make_opp(type_id=1, name="Item", buy=100.0, sell=120.0, margin=15.0,
              profit_unit=18.0, profit_day=500.0, spread=20.0, risk="Low",
              vol5d=300, score=75.0, enriched=True,
              buy_orders=5, sell_orders=5, history_days=30):
    opp = MarketOpportunity(
        type_id=type_id, item_name=name,
        best_buy_price=buy, best_sell_price=sell,
        margin_net_pct=margin, profit_per_unit=profit_unit,
        profit_day_est=profit_day, spread_pct=spread, risk_level=risk,
        tags=[], liquidity=LiquidityMetrics(vol5d, history_days, buy_orders, sell_orders),
        recommended_qty=10, recommended_cost=buy * 10,
    )
    opp.is_enriched = enriched
    opp.score_breakdown = ScoreBreakdown(
        base_score=0.7, liquidity_norm=0.6, roi_norm=0.7,
        profit_day_norm=0.4, penalties=[], final_score=score
    )
    return opp


# ─────────────────────────────────────────────────────────────────────────────
# A) PROFIT BREAKDOWN — Manticore case
# ─────────────────────────────────────────────────────────────────────────────
class TestProfitBreakdown(unittest.TestCase):
    BUY = 18_760_000.0
    SELL = 23_250_000.0
    TAX = 3.37
    FEE = 1.43

    def _bd(self):
        return compute_profit_breakdown(self.BUY, self.SELL, self.FEE, self.TAX)

    def test_gross_spread(self):
        bd = self._bd()
        self.assertAlmostEqual(bd["gross_spread"], self.SELL - self.BUY, places=0)

    def test_sales_tax_isk(self):
        bd = self._bd()
        self.assertAlmostEqual(bd["sales_tax_isk"], self.SELL * self.TAX / 100, places=0)

    def test_broker_fee_buy_isk(self):
        bd = self._bd()
        self.assertAlmostEqual(bd["broker_fee_buy_isk"], self.BUY * self.FEE / 100, places=0)

    def test_broker_fee_sell_isk(self):
        bd = self._bd()
        self.assertAlmostEqual(bd["broker_fee_sell_isk"], self.SELL * self.FEE / 100, places=0)

    def test_total_fees_is_sum(self):
        bd = self._bd()
        expected = bd["sales_tax_isk"] + bd["broker_fee_buy_isk"] + bd["broker_fee_sell_isk"]
        self.assertAlmostEqual(bd["total_fees_isk"], expected, places=0)

    def test_net_profit_with_esi_fees_above_3m(self):
        """With ESI fees (3.37% tax, 1.43% broker) Manticore net profit > 3M ISK."""
        bd = self._bd()
        expected = self.SELL * (1 - self.TAX / 100 - self.FEE / 100) - self.BUY * (1 + self.FEE / 100)
        self.assertAlmostEqual(bd["net_profit_per_unit"], expected, places=0)
        self.assertGreater(bd["net_profit_per_unit"], 3_000_000)

    def test_defaults_8pct_3pct_produce_1_369_700(self):
        """With default fees (8% tax, 3% broker) net profit matches the value shown in UI."""
        bd = compute_profit_breakdown(self.BUY, self.SELL, 3.0, 8.0)
        self.assertAlmostEqual(bd["net_profit_per_unit"], 1_369_700, delta=500)

    def test_esi_fees_give_more_profit_than_defaults(self):
        bd_default = compute_profit_breakdown(self.BUY, self.SELL, 3.0, 8.0)
        bd_esi = self._bd()
        self.assertGreater(bd_esi["net_profit_per_unit"], bd_default["net_profit_per_unit"])

    def test_formula_key_present(self):
        bd = self._bd()
        self.assertIn("formula", bd)
        self.assertIn("fees_source", bd)


# ─────────────────────────────────────────────────────────────────────────────
# B) PROFIT/U FORMULA — independent of qty and day estimate
# ─────────────────────────────────────────────────────────────────────────────
class TestProfitPerUnitFormula(unittest.TestCase):

    def test_profit_per_unit_not_multiplied_by_qty(self):
        """profit_per_unit must be the same regardless of capital_max (which affects rec_qty)."""
        from core.market_engine import parse_opportunities
        orders = [
            {"type_id": 1, "price": 100.0, "is_buy_order": True, "location_id": 1},
            {"type_id": 1, "price": 120.0, "is_buy_order": False, "location_id": 1},
        ]
        cfg_small = FilterConfig(capital_max=200.0, broker_fee_pct=1.0, sales_tax_pct=1.0)
        cfg_large = FilterConfig(capital_max=1e12, broker_fee_pct=1.0, sales_tax_pct=1.0)
        opps_small = parse_opportunities(orders, {}, {1: "Item"}, cfg_small)
        opps_large = parse_opportunities(orders, {}, {1: "Item"}, cfg_large)
        self.assertAlmostEqual(opps_small[0].profit_per_unit, opps_large[0].profit_per_unit, places=2)

    def test_fee_increase_reduces_profit(self):
        from core.market_engine import parse_opportunities
        orders = [
            {"type_id": 1, "price": 100.0, "is_buy_order": True, "location_id": 1},
            {"type_id": 1, "price": 120.0, "is_buy_order": False, "location_id": 1},
        ]
        low = parse_opportunities(orders, {}, {1: "Item"}, FilterConfig(broker_fee_pct=1.0, sales_tax_pct=1.0))
        high = parse_opportunities(orders, {}, {1: "Item"}, FilterConfig(broker_fee_pct=5.0, sales_tax_pct=5.0))
        self.assertGreater(low[0].profit_per_unit, high[0].profit_per_unit)

    def test_profit_per_unit_matches_breakdown_formula(self):
        """parse_opportunities profit_per_unit must match compute_profit_breakdown result."""
        from core.market_engine import parse_opportunities
        orders = [
            {"type_id": 1, "price": 18_760_000.0, "is_buy_order": True, "location_id": 1},
            {"type_id": 1, "price": 23_250_000.0, "is_buy_order": False, "location_id": 1},
        ]
        cfg = FilterConfig(broker_fee_pct=1.43, sales_tax_pct=3.37)
        opps = parse_opportunities(orders, {}, {1: "Manticore"}, cfg)
        bd = compute_profit_breakdown(18_760_000.0, 23_250_000.0, 1.43, 3.37)
        self.assertAlmostEqual(opps[0].profit_per_unit, bd["net_profit_per_unit"], places=0)


# ─────────────────────────────────────────────────────────────────────────────
# C) PANEL DETAIL SIZE AND BREAKDOWN TOOLTIP
# ─────────────────────────────────────────────────────────────────────────────
class TestDetailPanelSize(unittest.TestCase):

    def test_detail_panel_height_is_99(self):
        """Detail panel must be setFixedHeight(99), at least 10% above original 90."""
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.setup_ui)
        self.assertIn("setFixedHeight(99)", src)

    def test_detail_panel_not_90(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.setup_ui)
        self.assertNotIn("setFixedHeight(90)", src)

    def test_profit_tooltip_has_gross_in_selection_handler(self):
        """on_table_selection must build a tooltip containing 'Gross'."""
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.on_table_selection)
        self.assertIn("setToolTip", src)
        self.assertIn("Gross", src)

    def test_profit_tooltip_has_sales_tax(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.on_table_selection)
        self.assertIn("Sales Tax", src)

    def test_profit_label_named_net_profit_u(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.setup_detail_layout)
        self.assertIn("NET PROFIT/U", src)


# ─────────────────────────────────────────────────────────────────────────────
# D) NEW FILTERS
# ─────────────────────────────────────────────────────────────────────────────
class TestNewFilters(unittest.TestCase):

    def test_profit_unit_min_excludes_low_profit(self):
        high = _make_opp(type_id=1, profit_unit=50_000_000)
        low = _make_opp(type_id=2, profit_unit=1_000_000)
        cfg = FilterConfig(profit_unit_min=10_000_000.0)
        result = apply_filters([high, low], cfg)
        ids = [o.type_id for o in result]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

    def test_profit_unit_min_zero_passes_all(self):
        opps = [_make_opp(type_id=i, profit_unit=float(i * 1000)) for i in range(1, 5)]
        result = apply_filters(opps, FilterConfig(profit_unit_min=0.0))
        self.assertEqual(len(result), 4)

    def test_capital_min_excludes_cheap(self):
        cheap = _make_opp(type_id=1, buy=500_000)
        expensive = _make_opp(type_id=2, buy=50_000_000)
        result = apply_filters([cheap, expensive], FilterConfig(capital_min=1_000_000.0))
        ids = [o.type_id for o in result]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    def test_capital_min_zero_passes_all(self):
        opps = [_make_opp(type_id=i, buy=float(i * 1000)) for i in range(1, 5)]
        result = apply_filters(opps, FilterConfig(capital_min=0.0))
        self.assertEqual(len(result), 4)

    def test_buy_orders_min_filters(self):
        few = _make_opp(type_id=1, buy_orders=1)
        many = _make_opp(type_id=2, buy_orders=10)
        result = apply_filters([few, many], FilterConfig(buy_orders_min=5))
        ids = [o.type_id for o in result]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    def test_sell_orders_min_filters(self):
        few = _make_opp(type_id=1, sell_orders=1)
        many = _make_opp(type_id=2, sell_orders=10)
        result = apply_filters([few, many], FilterConfig(sell_orders_min=5))
        ids = [o.type_id for o in result]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    def test_history_days_min_filters_enriched(self):
        short = _make_opp(type_id=1, history_days=5, enriched=True)
        long = _make_opp(type_id=2, history_days=60, enriched=True)
        result = apply_filters([short, long], FilterConfig(history_days_min=30))
        ids = [o.type_id for o in result]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    def test_require_buy_sell_excludes_no_sell(self):
        complete = _make_opp(type_id=1, buy=100.0, sell=120.0)
        no_sell = _make_opp(type_id=2, buy=100.0, sell=0.0, profit_unit=0.0, margin=0.0)
        result = apply_filters([complete, no_sell], FilterConfig(require_buy_sell=True))
        ids = [o.type_id for o in result]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

    def test_require_buy_sell_false_passes_no_sell(self):
        no_sell = _make_opp(type_id=1, buy=100.0, sell=0.0, profit_unit=0.0, margin=0.0)
        result = apply_filters([no_sell], FilterConfig(require_buy_sell=False))
        self.assertEqual(len(result), 1)

    def test_old_config_without_new_fields_loads_ok(self):
        """Config JSON missing profit_unit_min/capital_min/require_buy_sell loads with defaults."""
        import json, tempfile, os
        from pathlib import Path
        old_data = {
            "capital_max": 500_000_000.0, "vol_min_day": 20,
            "margin_min_pct": 5.0, "score_min": 0.0,
            "risk_max": 3, "selected_category": "Todos",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(old_data, f)
            tmp = f.name
        try:
            with patch('core.config_manager._MARKET_FILTERS_FILE', Path(tmp)):
                from core.config_manager import load_market_filters
                cfg = load_market_filters()
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.profit_unit_min, 0.0)
            self.assertEqual(cfg.capital_min, 0.0)
            self.assertFalse(cfg.require_buy_sell)
        finally:
            os.unlink(tmp)

    def test_filterconfig_new_fields_default_zero(self):
        cfg = FilterConfig()
        self.assertEqual(cfg.profit_unit_min, 0.0)
        self.assertEqual(cfg.capital_min, 0.0)
        self.assertFalse(cfg.require_buy_sell)


# ─────────────────────────────────────────────────────────────────────────────
# E) FEES — no manual inputs reappear, fees_source logged
# ─────────────────────────────────────────────────────────────────────────────
class TestFeesNotManual(unittest.TestCase):

    def test_no_spin_broker_in_setup_ui(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.setup_ui)
        self.assertNotIn("spin_broker", src)
        self.assertNotIn("spin_tax", src)

    def test_no_spin_broker_in_update_config(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView.update_config_from_ui)
        self.assertNotIn("spin_broker", src)
        self.assertNotIn("spin_tax", src)

    def test_log_scan_config_has_fees_source(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView._log_scan_config)
        self.assertIn("fees_source", src)

    def test_log_scan_config_has_profit_unit_min(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView._log_scan_config)
        self.assertIn("profit_unit_min", src)

    def test_log_scan_config_has_capital_min(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView._log_scan_config)
        self.assertIn("capital_min", src)

    def test_log_scan_config_has_require_buy_sell(self):
        import inspect
        from ui.market_command import simple_view as mod
        src = inspect.getsource(mod.MarketSimpleView._log_scan_config)
        self.assertIn("require_buy_sell", src)


if __name__ == "__main__":
    unittest.main()
