import unittest
import sys
import os

# Añadir el path del proyecto al sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.market_models import MarketOpportunity, FilterConfig, LiquidityMetrics, ScoreBreakdown
from core.market_engine import apply_filters

class TestSimpleFiltersRelaxed(unittest.TestCase):
    def setUp(self):
        # Configuración relajada típica de Modo Simple
        self.config = FilterConfig(
            selected_category="Todos",
            capital_max=10_000_000_000,
            vol_min_day=0,
            margin_min_pct=0,
            spread_max_pct=500,
            broker_fee_pct=3,
            sales_tax_pct=1,
            exclude_plex=True,
            buy_orders_min=0,
            sell_orders_min=0,
            history_days_min=0,
            profit_day_min=0,
            risk_max=3,
            score_min=0
        )

    def test_initial_data_passes_relaxed(self):
        # Datos iniciales (sin historial, is_enriched=False)
        opp = MarketOpportunity(
            type_id=123,
            item_name="Tritanium",
            best_buy_price=5.0,
            best_sell_price=6.0,
            margin_net_pct=10.0,
            profit_per_unit=1.0,
            profit_day_est=0.0,
            spread_pct=20.0,
            risk_level="Medium",
            tags=[],
            liquidity=LiquidityMetrics(volume_5d=0, history_days=0, buy_orders_count=10, sell_orders_count=10),
            recommended_qty=100,
            recommended_cost=500
        )
        opp.is_enriched = False
        opp.score_breakdown = ScoreBreakdown(base_score=0.5, liquidity_norm=0, roi_norm=0.5, profit_day_norm=0, penalties=[], final_score=50.0)
        
        results = apply_filters([opp], self.config)
        self.assertEqual(len(results), 1, "Initial data should pass relaxed filters even if volume/history is 0")

    def test_enriched_data_passes_relaxed(self):
        # Datos enriquecidos (con historial, is_enriched=True)
        opp = MarketOpportunity(
            type_id=123,
            item_name="Tritanium",
            best_buy_price=5.0,
            best_sell_price=6.0,
            margin_net_pct=10.0,
            profit_per_unit=1.0,
            profit_day_est=100.0,
            spread_pct=20.0,
            risk_level="Low",
            tags=[],
            liquidity=LiquidityMetrics(volume_5d=1000, history_days=30, buy_orders_count=10, sell_orders_count=10),
            recommended_qty=100,
            recommended_cost=500
        )
        opp.is_enriched = True
        opp.score_breakdown = ScoreBreakdown(base_score=0.8, liquidity_norm=0.8, roi_norm=0.8, profit_day_norm=0.8, penalties=[], final_score=80.0)
        
        results = apply_filters([opp], self.config)
        self.assertEqual(len(results), 1, "Enriched data should pass relaxed filters")

    def test_exclude_plex_logic(self):
        opp_plex = MarketOpportunity(
            type_id=4499, item_name="3000 PLEX", best_buy_price=1e9, best_sell_price=1.1e9,
            margin_net_pct=5.0, profit_per_unit=1e6, profit_day_est=1e9, spread_pct=1.0,
            risk_level="Low", tags=[], liquidity=LiquidityMetrics(10, 30, 10, 10), recommended_qty=1, recommended_cost=1e9
        )
        opp_plex.is_enriched = True
        
        opp_normal = MarketOpportunity(
            type_id=123, item_name="Amulet", best_buy_price=1e6, best_sell_price=1.2e6,
            margin_net_pct=15.0, profit_per_unit=1e5, profit_day_est=1e7, spread_pct=5.0,
            risk_level="Low", tags=[], liquidity=LiquidityMetrics(10, 30, 10, 10), recommended_qty=1, recommended_cost=1e6
        )
        opp_normal.is_enriched = True

        results = apply_filters([opp_plex, opp_normal], self.config)
        names = [o.item_name for o in results]
        self.assertIn("Amulet", names)
        self.assertNotIn("3000 PLEX", names, "PLEX should be excluded when exclude_plex=True")

    def test_hidden_filters_can_kill_results(self):
        # Caso donde filtros avanzados (ocultos en Simple) matan el resultado
        opp = MarketOpportunity(
            type_id=123, item_name="Tritanium", best_buy_price=5.0, best_sell_price=6.0,
            margin_net_pct=10.0, profit_per_unit=1.0, profit_day_est=100.0, spread_pct=20.0,
            risk_level="Low", tags=[], liquidity=LiquidityMetrics(volume_5d=1000, history_days=30, buy_orders_count=2, sell_orders_count=2),
            recommended_qty=100, recommended_cost=500
        )
        opp.is_enriched = True
        
        # Filtro oculto restrictivo
        config_restrictive = FilterConfig(
            selected_category="Todos",
            capital_max=10e9, vol_min_day=0, margin_min_pct=0, spread_max_pct=500,
            buy_orders_min=5, # Este filtro mata el item (tiene 2)
            risk_max=3, score_min=0
        )
        
        results = apply_filters([opp], config_restrictive)
        self.assertEqual(len(results), 0, "Hidden filters (buy_orders_min) should be able to kill results if not reset")

if __name__ == "__main__":
    unittest.main()
