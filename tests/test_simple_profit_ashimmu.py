import pytest
from core.market_engine import compute_profit_breakdown
from utils.formatters import format_isk

def test_ashimmu_profit_calculation_defaults():
    # Caso Ashimmu con defaults 8/3
    # Buy=182.800.000, Sell=369.900.000
    buy = 182_800_000
    sell = 369_900_000
    tax = 8.0
    fee = 3.0
    
    bd = compute_profit_breakdown(buy, sell, fee, tax)
    
    # sell*(1-0.08-0.03) - buy*(1+0.03)
    # 369.9M * 0.89 - 182.8M * 1.03
    expected_profit = 140_927_000
    
    assert int(bd['net_profit_per_unit']) == expected_profit
    print(f"\nAshimmu Defaults (8/3): {format_isk(bd['net_profit_per_unit'])}")

def test_ashimmu_profit_calculation_nina():
    # Caso Ashimmu con Nina fees 3.37/1.43
    buy = 182_800_000
    sell = 369_900_000
    tax = 3.37
    fee = 1.43
    
    bd = compute_profit_breakdown(buy, sell, fee, tax)
    
    # Formula: sell*(1 - s_tax - b_fee) - buy*(1 + b_fee)
    s_tax = tax / 100.0
    b_fee = fee / 100.0
    expected_profit = sell * (1.0 - s_tax - b_fee) - buy * (1.0 + b_fee)
    
    # 369.9M * (1 - 0.0337 - 0.0143) - 182.8M * (1 + 0.0143)
    # 369.9M * 0.952 - 182.8M * 1.0143
    # 352,144,800 - 185,414,040 = 166,730,760
    
    assert int(bd['net_profit_per_unit']) == 166_730_760
    print(f"Ashimmu Nina (3.37/1.43): {format_isk(bd['net_profit_per_unit'])}")
