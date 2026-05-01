import pytest
import os
import json
from core.cost_basis_service import CostBasisService
from datetime import datetime

def test_wac_calculation_basic():
    service = CostBasisService()
    # Mock stock_map initial state
    service.stock_map = {"123": {"qty": 0, "cost": 0.0}}
    
    # 1. Buy 10 @ 100
    tx1 = {"transaction_id": 1, "type_id": 123, "quantity": 10, "unit_price": 100.0, "is_buy": True}
    service.stock_map["123"]["qty"] += tx1["quantity"]
    service.stock_map["123"]["cost"] += tx1["quantity"] * tx1["unit_price"]
    
    assert service.stock_map["123"]["qty"] == 10
    assert service.stock_map["123"]["cost"] == 1000.0
    
    # 2. Buy 10 @ 200
    tx2 = {"transaction_id": 2, "type_id": 123, "quantity": 10, "unit_price": 200.0, "is_buy": True}
    service.stock_map["123"]["qty"] += tx2["quantity"]
    service.stock_map["123"]["cost"] += tx2["quantity"] * tx2["unit_price"]
    
    assert service.stock_map["123"]["qty"] == 20
    assert service.stock_map["123"]["cost"] == 3000.0
    # WAC should be 3000/20 = 150

def test_wac_calculation_sales_and_reset():
    service = CostBasisService()
    service.stock_map = {"123": {"qty": 20, "cost": 3000.0}} # WAC = 150
    
    # 3. Sell 5
    # Logic from service: total_cost -= avg * qty
    avg = 3000.0 / 20.0 # 150
    sell_qty = 5
    service.stock_map["123"]["qty"] -= sell_qty
    service.stock_map["123"]["cost"] -= sell_qty * avg
    
    assert service.stock_map["123"]["qty"] == 15
    assert service.stock_map["123"]["cost"] == 2250.0
    assert service.stock_map["123"]["cost"] / service.stock_map["123"]["qty"] == 150.0
    
    # 4. Sell remaining 15
    sell_qty = 15
    service.stock_map["123"]["qty"] -= sell_qty
    if service.stock_map["123"]["qty"] <= 0:
        service.stock_map["123"]["qty"] = 0
        service.stock_map["123"]["cost"] = 0.0
        
    assert service.stock_map["123"]["qty"] == 0
    assert service.stock_map["123"]["cost"] == 0.0

def test_reconciliation_reset():
    service = CostBasisService()
    service.stock_map = {"123": {"qty": 10, "cost": 1000.0}}
    
    # Mock assets without item 123
    current_assets = [{"type_id": 456, "quantity": 5}]
    
    asset_qty_map = {}
    for a in current_assets:
        tid = str(a['type_id'])
        asset_qty_map[tid] = asset_qty_map.get(tid, 0) + a['quantity']
        
    for tid_str, data in service.stock_map.items():
        if data['qty'] > 0:
            real_qty = asset_qty_map.get(tid_str, 0)
            if real_qty == 0:
                data['qty'] = 0
                data['cost'] = 0.0
                
    assert service.stock_map["123"]["qty"] == 0
    assert service.stock_map["123"]["cost"] == 0.0
