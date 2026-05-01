import pytest
from core.contracts_models import ContractArbitrageResult, ContractItem, ContractsFilterConfig, ScanDiagnostics
from core.contracts_engine import apply_contracts_filters

def test_zero_value_breakdown():
    config = ContractsFilterConfig(profit_min_isk=0, roi_min_pct=0)
    diag = ScanDiagnostics()
    
    # Contract with items but all missing price
    item = ContractItem(
        type_id=999999, item_name="Unpriced SKIN", quantity=1, is_included=True,
        jita_sell_price=0, jita_buy_price=0, line_sell_value=0,
        line_buy_value=0, pct_of_total=0
    )
    c = ContractArbitrageResult(
        contract_id=1, region_id=10000002, issuer_id=1, contract_cost=1000000,
        date_expired="", location_id=1, item_type_count=1, total_units=1,
        items=[item], jita_sell_value=0, jita_buy_value=0, gross_profit=0,
        net_profit=-1000000, roi_pct=0, value_concentration=0, 
        has_unresolved_items=True, unresolved_count=1
    )
    
    filtered = apply_contracts_filters([c], config, diag)
    assert len(filtered) == 0
    assert diag.excluded_by_zero_value == 1
    assert diag.zv_all_items_missing_price == 1
    assert diag.val_no_priced == 1

def test_low_profit_not_zero_value():
    config = ContractsFilterConfig(profit_min_isk=100, roi_min_pct=0)
    diag = ScanDiagnostics()
    
    # Contract with value but profit < min_profit
    item = ContractItem(
        type_id=1, item_name="Priced Item", quantity=1, is_included=True,
        jita_sell_price=50, jita_buy_price=40, line_sell_value=50,
        line_buy_value=40, pct_of_total=100
    )
    c = ContractArbitrageResult(
        contract_id=2, region_id=10000002, issuer_id=1, contract_cost=10,
        date_expired="", location_id=1, item_type_count=1, total_units=1,
        items=[item], jita_sell_value=50, jita_buy_value=40, gross_profit=40,
        net_profit=40, roi_pct=400, value_concentration=1, 
        has_unresolved_items=False, unresolved_count=0
    )
    # profit is 40, min_profit is 100.
    
    filtered = apply_contracts_filters([c], config, diag)
    assert len(filtered) == 0
    assert diag.excluded_by_low_profit == 1
    assert diag.excluded_by_zero_value == 0

if __name__ == "__main__":
    pytest.main([__file__])
