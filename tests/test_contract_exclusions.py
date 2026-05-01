import pytest
from core.contracts_models import ContractArbitrageResult, ContractItem, ContractsFilterConfig, ScanDiagnostics
from core.contracts_engine import apply_contracts_filters

def test_zero_item_exclusion():
    config = ContractsFilterConfig(profit_min_isk=0, roi_min_pct=0)
    diag = ScanDiagnostics()
    
    # Contract with 0 items
    c_empty = ContractArbitrageResult(
        contract_id=1, region_id=10000002, issuer_id=1, contract_cost=0,
        date_expired="", location_id=1, item_type_count=0, total_units=0,
        items=[], jita_sell_value=0, jita_buy_value=0, gross_profit=0,
        net_profit=0, roi_pct=0, value_concentration=0, 
        has_unresolved_items=False, unresolved_count=0
    )
    
    filtered = apply_contracts_filters([c_empty], config, diag)
    assert len(filtered) == 0
    assert diag.excluded_by_no_items == 1
    assert diag.profitable == 0

def test_zero_profit_exclusion_when_min_is_zero():
    config = ContractsFilterConfig(profit_min_isk=0, roi_min_pct=0)
    diag = ScanDiagnostics()
    
    # Contract with 0 profit (should be excluded if we want strictly positive profit)
    item = ContractItem(
        type_id=1, item_name="X", quantity=1, is_included=True,
        jita_sell_price=100, jita_buy_price=90, line_sell_value=100,
        line_buy_value=90, pct_of_total=100
    )
    c_zero = ContractArbitrageResult(
        contract_id=2, region_id=10000002, issuer_id=1, contract_cost=100,
        date_expired="", location_id=1, item_type_count=1, total_units=1,
        items=[item], jita_sell_value=100, jita_buy_value=90, gross_profit=0,
        net_profit=0, roi_pct=0, value_concentration=1, 
        has_unresolved_items=False, unresolved_count=0
    )
    
    filtered = apply_contracts_filters([c_zero], config, diag)
    assert len(filtered) == 0
    assert diag.excluded_by_low_profit == 1

if __name__ == "__main__":
    pytest.main([__file__])
