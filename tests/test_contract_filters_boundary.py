import pytest
from core.contracts_models import ContractArbitrageResult, ContractItem, ContractsFilterConfig, ScanDiagnostics
from core.contracts_engine import apply_contracts_filters

def test_apply_filters_inclusive_boundary():
    item1 = ContractItem(
        type_id=34, item_name="Tritanium", quantity=1000, is_included=True,
        jita_sell_price=1.0, jita_buy_price=1.0, line_sell_value=1000.0,
        line_buy_value=1000.0, pct_of_total=100.0
    )
    # ROI 0% and Profit 0
    result = ContractArbitrageResult(
        contract_id=123, region_id=10000002, issuer_id=456, contract_cost=1000.0,
        date_expired="2026-05-01T00:00:00Z", location_id=60003760,
        item_type_count=1, total_units=1000, items=[item1],
        jita_sell_value=1000.0, jita_buy_value=1000.0,
        gross_profit=0.0, net_profit=0.0, roi_pct=0.0,
        value_concentration=1.0, has_unresolved_items=False,
        unresolved_count=0, score=50.0
    )
    
    # Boundary case: 0 vs 0
    config = ContractsFilterConfig(profit_min_isk=0, roi_min_pct=0, capital_min_isk=0, exclude_blueprints=False, exclude_bpcs=False)
    diag = ScanDiagnostics()
    filtered = apply_contracts_filters([result], config, diag)
    
    assert len(filtered) == 1, f"Should pass filters with 0/0. Diag: {diag.to_summary()}"
    assert diag.profitable == 1

def test_category_filter_normalization():
    item1 = ContractItem(
        type_id=34, item_name="Tritanium", quantity=1000, is_included=True,
        jita_sell_price=1.0, jita_buy_price=1.0, line_sell_value=1000.0,
        line_buy_value=1000.0, pct_of_total=100.0
    )
    result = ContractArbitrageResult(
        contract_id=123, region_id=10000002, issuer_id=456, contract_cost=1000.0,
        date_expired="2026-05-01T00:00:00Z", location_id=60003760,
        item_type_count=1, total_units=1000, items=[item1],
        jita_sell_value=1000.0, jita_buy_value=1000.0,
        gross_profit=0.0, net_profit=0.0, roi_pct=0.0,
        value_concentration=1.0, has_unresolved_items=False,
        unresolved_count=0, score=50.0
    )
    
    # Test "Todas las categorías" case
    config = ContractsFilterConfig(category_filter="Todas las categorías", profit_min_isk=0, roi_min_pct=0, capital_min_isk=0)
    filtered = apply_contracts_filters([result], config)
    assert len(filtered) == 1, "Category filter should be bypassed for 'Todas las categorías'"
    
    # Test "all" case
    config.category_filter = "all"
    filtered = apply_contracts_filters([result], config)
    assert len(filtered) == 1, "Category filter should be bypassed for 'all'"

if __name__ == "__main__":
    test_apply_filters_inclusive_boundary()
    test_category_filter_normalization()
    print("Tests passed!")
