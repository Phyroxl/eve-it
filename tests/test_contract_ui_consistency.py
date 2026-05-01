import pytest
from core.contracts_models import ContractArbitrageResult, ContractItem, ContractsFilterConfig, ScanDiagnostics
from core.contracts_engine import apply_contracts_filters

def test_full_cycle_consistency():
    # 1. Mock a profitable result
    item1 = ContractItem(
        type_id=34, item_name="Tritanium", quantity=1000, is_included=True,
        jita_sell_price=10.0, jita_buy_price=8.0, line_sell_value=10000.0,
        line_buy_value=8000.0, pct_of_total=100.0
    )
    result = ContractArbitrageResult(
        contract_id=123, region_id=10000002, issuer_id=456, contract_cost=5000.0,
        date_expired="2026-05-01T00:00:00Z", location_id=60003760,
        item_type_count=1, total_units=1000, items=[item1],
        jita_sell_value=10000.0, jita_buy_value=8000.0,
        gross_profit=5000.0, net_profit=4500.0, roi_pct=90.0,
        value_concentration=1.0, has_unresolved_items=False,
        unresolved_count=0, score=80.0
    )
    
    config = ContractsFilterConfig(
        profit_min_isk=0, 
        roi_min_pct=0, 
        category_filter="all",
        exclude_blueprints=True,
        exclude_bpcs=True
    )
    
    # Simulate Worker Pass
    worker_diag = ScanDiagnostics()
    worker_filtered = apply_contracts_filters([result], config, worker_diag)
    assert len(worker_filtered) == 1
    assert worker_diag.profitable == 1
    
    # Simulate on_scan_finished receiving all analyzed results
    all_results = [result]
    
    # Simulate apply_filters_locally
    ui_diag = ScanDiagnostics()
    ui_filtered = apply_contracts_filters(all_results, config, ui_diag)
    
    assert len(ui_filtered) == 1, "Should still be 1 in UI pass"
    assert ui_diag.profitable == 1

def test_config_mutation_check():
    # Verify that changing config values (like from UI spinboxes) behaves as expected
    config = ContractsFilterConfig(profit_min_isk=0)
    
    item = ContractItem(
        type_id=1, item_name="X", quantity=1, line_sell_value=100,
        is_included=True, jita_sell_price=100, jita_buy_price=90, 
        line_buy_value=90, pct_of_total=100
    )
    res = ContractArbitrageResult(contract_id=1, net_profit=10.0, items=[item]) # Profit 10
    
    assert len(apply_contracts_filters([res], config)) == 1
    
    # Change config to be more strict
    config.profit_min_isk = 1000000 # 1M
    assert len(apply_contracts_filters([res], config)) == 0

if __name__ == "__main__":
    pytest.main([__file__])
