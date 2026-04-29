"""
Tests para verificar el comportamiento de apply_filters con is_enriched=True/False.
Ejecutar: python tests/test_market_initial_enriched_filters.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.market_models import MarketOpportunity, LiquidityMetrics, FilterConfig, ScoreBreakdown
from core.market_engine import apply_filters


def make_opp(type_id=1, item_name="TestItem", margin=10.0, buy=100.0, sell=120.0,
             vol_5d=0, history_days=0, profit_day=0.0, risk_level="High",
             buy_orders=5, sell_orders=5, is_enriched=False) -> MarketOpportunity:
    liq = LiquidityMetrics(volume_5d=vol_5d, history_days=history_days,
                            buy_orders_count=buy_orders, sell_orders_count=sell_orders)
    sb = ScoreBreakdown(base_score=0.5, liquidity_norm=0.1, roi_norm=0.3,
                         profit_day_norm=0.1, penalties=[], final_score=50.0)
    return MarketOpportunity(
        type_id=type_id, item_name=item_name,
        best_buy_price=buy, best_sell_price=sell,
        margin_net_pct=margin, profit_per_unit=sell - buy,
        profit_day_est=profit_day, spread_pct=((sell - buy) / buy) * 100,
        risk_level=risk_level, tags=[], liquidity=liq,
        score_breakdown=sb, is_enriched=is_enriched
    )


def test_initial_not_killed_by_volume_filter():
    config = FilterConfig(vol_min_day=50)  # vol > 0 required
    opp = make_opp(vol_5d=0, is_enriched=False)  # no history yet
    result = apply_filters([opp], config)
    assert len(result) == 1, f"Initial opp should NOT be killed by vol_min_day. Got {len(result)}"
    print("  [PASS] initial: vol_min_day skipped when is_enriched=False")


def test_enriched_killed_by_volume_filter():
    config = FilterConfig(vol_min_day=50)
    opp = make_opp(vol_5d=5, is_enriched=True)  # enriched but low volume
    result = apply_filters([opp], config)
    assert len(result) == 0, f"Enriched opp with low volume should be filtered. Got {len(result)}"
    print("  [PASS] enriched: vol_min_day applied when is_enriched=True")


def test_initial_not_killed_by_history_days_filter():
    config = FilterConfig(history_days_min=30)
    opp = make_opp(history_days=0, is_enriched=False)
    result = apply_filters([opp], config)
    assert len(result) == 1, f"Initial opp should NOT be killed by history_days_min. Got {len(result)}"
    print("  [PASS] initial: history_days_min skipped when is_enriched=False")


def test_initial_not_killed_by_profit_day_filter():
    config = FilterConfig(profit_day_min=1_000_000)
    opp = make_opp(profit_day=0.0, is_enriched=False)
    result = apply_filters([opp], config)
    assert len(result) == 1, f"Initial opp should NOT be killed by profit_day_min. Got {len(result)}"
    print("  [PASS] initial: profit_day_min skipped when is_enriched=False")


def test_initial_not_killed_by_risk_filter():
    config = FilterConfig(risk_max=1)  # Only Low risk
    opp = make_opp(risk_level="High", is_enriched=False)
    result = apply_filters([opp], config)
    assert len(result) == 1, f"Initial opp should NOT be killed by risk_max. Got {len(result)}"
    print("  [PASS] initial: risk_max skipped when is_enriched=False")


def test_enriched_killed_by_risk_filter():
    config = FilterConfig(risk_max=1)
    opp = make_opp(risk_level="High", is_enriched=True)
    result = apply_filters([opp], config)
    assert len(result) == 0, f"Enriched High-risk opp should be filtered with risk_max=1. Got {len(result)}"
    print("  [PASS] enriched: risk_max applied when is_enriched=True")


def test_capital_filter_applies_to_both():
    config = FilterConfig(capital_max=50.0)
    opp_initial = make_opp(buy=200.0, is_enriched=False)
    opp_enriched = make_opp(buy=200.0, is_enriched=True)
    r1 = apply_filters([opp_initial], config)
    r2 = apply_filters([opp_enriched], config)
    assert len(r1) == 0, "capital_max should apply to initial opps too"
    assert len(r2) == 0, "capital_max should apply to enriched opps too"
    print("  [PASS] capital_max applied to both initial and enriched")


def test_margin_filter_applies_to_both():
    config = FilterConfig(margin_min_pct=20.0)
    opp_initial = make_opp(margin=5.0, is_enriched=False)
    opp_enriched = make_opp(margin=5.0, is_enriched=True)
    r1 = apply_filters([opp_initial], config)
    r2 = apply_filters([opp_enriched], config)
    assert len(r1) == 0, "margin_min_pct should apply to initial opps"
    assert len(r2) == 0, "margin_min_pct should apply to enriched opps"
    print("  [PASS] margin_min_pct applied to both initial and enriched")


def test_score_min_filter():
    config = FilterConfig(score_min=80.0)  # score_min = 80, our opp has 50
    opp = make_opp(is_enriched=True)  # score_breakdown.final_score = 50
    result = apply_filters([opp], config)
    assert len(result) == 0, f"score_min=80 should filter opp with score=50. Got {len(result)}"
    print("  [PASS] score_min filter works")


def test_todos_category_passes_all():
    config = FilterConfig(selected_category="Todos", vol_min_day=0, margin_min_pct=0)
    opp1 = make_opp(type_id=1, is_enriched=False)
    opp2 = make_opp(type_id=2, is_enriched=True)
    result = apply_filters([opp1, opp2], config)
    assert len(result) == 2, f"Todos should pass both. Got {len(result)}"
    print("  [PASS] Todos: bypasses category filter for both initial and enriched")


def test_mixed_list_initial_and_enriched():
    """Si hay mix de initial y enriched, los filtros de historial solo aplican a enriched."""
    config = FilterConfig(vol_min_day=50, history_days_min=10)
    opp_initial_no_hist = make_opp(type_id=1, vol_5d=0, history_days=0, is_enriched=False)
    opp_enriched_low_vol = make_opp(type_id=2, vol_5d=5, history_days=5, is_enriched=True)
    opp_enriched_ok = make_opp(type_id=3, vol_5d=100, history_days=30, is_enriched=True)

    result = apply_filters([opp_initial_no_hist, opp_enriched_low_vol, opp_enriched_ok], config)
    ids = {o.type_id for o in result}
    assert 1 in ids, "Initial opp should pass (history filters skipped)"
    assert 2 not in ids, "Enriched with low volume should be filtered"
    assert 3 in ids, "Enriched OK should pass"
    print("  [PASS] mixed initial/enriched list handled correctly")


def run_tests():
    print("\n=== test_market_initial_enriched_filters ===\n")
    tests = [
        test_initial_not_killed_by_volume_filter,
        test_enriched_killed_by_volume_filter,
        test_initial_not_killed_by_history_days_filter,
        test_initial_not_killed_by_profit_day_filter,
        test_initial_not_killed_by_risk_filter,
        test_enriched_killed_by_risk_filter,
        test_capital_filter_applies_to_both,
        test_margin_filter_applies_to_both,
        test_score_min_filter,
        test_todos_category_passes_all,
        test_mixed_list_initial_and_enriched,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {e}")
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
