import pytest
from core.contracts_models import ContractArbitrageResult, ContractItem, ScoreBreakdown
from dataclasses import asdict

def test_contract_result_serialization():
    # Setup
    item1 = ContractItem(
        type_id=34, item_name="Tritanium", quantity=1000, is_included=True,
        jita_sell_price=4.0, jita_buy_price=3.5, line_sell_value=4000.0,
        line_buy_value=3500.0, pct_of_total=100.0
    )
    result = ContractArbitrageResult(
        contract_id=123, region_id=10000002, issuer_id=456, contract_cost=1000.0,
        date_expired="2026-05-01T00:00:00Z", location_id=60003760,
        item_type_count=1, total_units=1000, items=[item1],
        jita_sell_value=4000.0, jita_buy_value=3500.0,
        gross_profit=3000.0, net_profit=2500.0, roi_pct=250.0,
        value_concentration=1.0, has_unresolved_items=False,
        unresolved_count=0, score=85.0
    )
    
    # Serialize
    d = asdict(result)
    assert "items" in d
    assert len(d["items"]) == 1
    assert d["items"][0]["item_name"] == "Tritanium"
    
    # Deserialize
    restored = ContractArbitrageResult.from_dict(d)
    assert restored.contract_id == 123
    assert len(restored.items) == 1
    assert isinstance(restored.items[0], ContractItem)
    assert restored.items[0].item_name == "Tritanium"
    assert restored.items[0].quantity == 1000

if __name__ == "__main__":
    test_contract_result_serialization()
    print("Test passed!")
