import pytest
from core.contracts_models import ContractArbitrageResult, ContractItem, ContractsFilterConfig, ScanDiagnostics
from core.contracts_engine import apply_contracts_filters

def test_abyssal_exclusion():
    config = ContractsFilterConfig(exclude_abyssal=True, capital_min_isk=0, roi_min_pct=0)
    diag = ScanDiagnostics()
    
    # Contract with Abyssal item
    item = ContractItem(
        type_id=1, item_name="Abyssal Warp Disruptor", quantity=1, is_included=True,
        jita_sell_price=0, jita_buy_price=0, line_sell_value=0,
        line_buy_value=0, pct_of_total=100
    )
    c = ContractArbitrageResult(
        contract_id=1, region_id=10000002, issuer_id=1, contract_cost=100,
        date_expired="", location_id=1, item_type_count=1, total_units=1,
        items=[item], jita_sell_value=0, jita_buy_value=0, gross_profit=0,
        net_profit=-100, roi_pct=0, value_concentration=1, 
        has_unresolved_items=True, unresolved_count=1
    )
    
    filtered = apply_contracts_filters([c], config, diag)
    assert len(filtered) == 0
    assert diag.excluded_by_abyssal == 1

def test_category_metadata_fallback():
    # Test that abyssal modules are excluded from ships even if they don't trigger the name check but are tagged as abyssal
    config = ContractsFilterConfig(category_filter="ships", capital_min_isk=0, roi_min_pct=0, exclude_no_price=False)
    diag = ScanDiagnostics()
    
    # Item that is an Abyssal module but we want to make sure it doesn't appear in ships
    item = ContractItem(
        type_id=1, item_name="Mutated Heavy Drone", quantity=1, is_included=True,
        jita_sell_price=0, jita_buy_price=0, line_sell_value=0,
        line_buy_value=0, pct_of_total=100
    )
    c = ContractArbitrageResult(
        contract_id=2, region_id=10000002, issuer_id=1, contract_cost=100,
        date_expired="", location_id=1, item_type_count=1, total_units=1,
        items=[item], jita_sell_value=0, jita_buy_value=0, gross_profit=0,
        net_profit=-100, roi_pct=0, value_concentration=1, 
        has_unresolved_items=True, unresolved_count=1
    )
    
    filtered = apply_contracts_filters([c], config, diag)
    assert len(filtered) == 0
    assert diag.excluded_by_category == 1
