import pytest
import sqlite3
import os
from datetime import datetime, timedelta
from core.performance_fee_allocator import allocate_item_fees

@pytest.fixture
def temp_db():
    db_path = "tests/test_performance.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Tables
    c.execute('''CREATE TABLE wallet_transactions (
        transaction_id INTEGER PRIMARY KEY,
        character_id INTEGER,
        date TEXT,
        item_id INTEGER,
        item_name TEXT,
        quantity INTEGER,
        unit_price REAL,
        is_buy INTEGER,
        order_id INTEGER
    )''')
    
    c.execute('''CREATE TABLE wallet_journal (
        id INTEGER PRIMARY KEY,
        character_id INTEGER,
        date TEXT,
        ref_type TEXT,
        amount REAL,
        balance REAL,
        description TEXT,
        reason TEXT,
        context_id INTEGER,
        context_id_type TEXT
    )''')
    
    conn.commit()
    yield conn
    conn.close()
    if os.path.exists(db_path):
        os.remove(db_path)

def test_exact_match_allocation(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    # 1. Add transaction
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (100, char_id, date_now, 34, "Tritanium", 1000, 5.0, 0, 1000))
    
    # 2. Add journal entry with exact context_id match
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (500, char_id, date_now, "transaction_tax", -150.0, 1000.0, "Tax", None, 100, "transaction_id"))
    
    temp_db.commit()
    
    alloc = allocate_item_fees(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    assert 34 in alloc
    assert alloc[34]["allocated_sales_tax"] == 150.0
    assert alloc[34]["fee_allocation_confidence"] == "high"
    assert alloc[34]["allocation_method"] == "exact_match"

def test_timing_match_allocation(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    # 1. Add sell transaction
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (101, char_id, date_now, 1230, "Vexor", 1, 20000000.0, 0, 2000))
    
    # 2. Add tax entry at SAME second but NO context_id
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (501, char_id, date_now, "transaction_tax", -1000000.0, 1000.0, "Tax", None, None, None))
    
    temp_db.commit()
    
    alloc = allocate_item_fees(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    assert 1230 in alloc
    assert alloc[1230]["allocated_sales_tax"] == 1000000.0
    assert alloc[1230]["fee_allocation_confidence"] == "high" # Timing match is high-confidence for Tax

def test_proportional_fallback(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    # Two items with different volumes
    # Item A: 1000 ISK income
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (102, char_id, date_now, 1, "Item A", 1, 1000.0, 0, 3000))
    # Item B: 3000 ISK income
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (103, char_id, date_now, 2, "Item B", 1, 3000.0, 0, 4000))
    
    # Unallocated tax of 400 ISK
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (502, char_id, "2026-05-01T12:05:00Z", "transaction_tax", -400.0, 1000.0, "Tax", None, None, None))
    
    temp_db.commit()
    
    alloc = allocate_item_fees(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    assert alloc[1]["allocated_sales_tax"] == 100.0  # 1/4 of 400
    assert alloc[2]["allocated_sales_tax"] == 300.0  # 3/4 of 400
    assert alloc[1]["fee_allocation_confidence"] == "low"
    assert alloc[1]["allocation_method"] == "proportional_fallback"

def test_broker_fee_allocation(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    # Buy transaction with order_id 5000
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (104, char_id, date_now, 34, "Tritanium", 1000, 5.0, 1, 5000))
    
    # Broker fee for order_id 5000
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (503, char_id, date_now, "brokers_fee", -250.0, 1000.0, "Broker Fee", None, 5000, "order_id"))
    
    temp_db.commit()
    
    alloc = allocate_item_fees(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    assert alloc[34]["allocated_broker_fees"] == 250.0
    assert alloc[34]["fee_allocation_confidence"] == "high"

def test_timing_cluster_priority(temp_db):
    """transaction_tax chooses exact timestamp over earlier nearby transaction"""
    c = temp_db.cursor()
    char_id = 1
    # Entry at 14:03:08
    e_date = "2026-04-28T14:03:08Z"
    
    # SELL item A at 14:02:28 (delta -40s)
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (1, char_id, "2026-04-28T14:02:28Z", 10, "Item A", 1, 100, 0, 101))
    # SELL item B at 14:03:08 (delta 0s)
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (2, char_id, e_date, 20, "Item B", 1, 200, 0, 102))
              
    # Tax at 14:03:08
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (500, char_id, e_date, "transaction_tax", -10.0, 1000.0, "Tax", None, None, None))
              
    temp_db.commit()
    alloc = allocate_item_fees(temp_db, char_id, "2026-04-28", "2026-04-28")
    
    # Item B should get the tax because dt=0
    assert alloc[20]["allocated_sales_tax"] == 10.0
    assert alloc[10]["allocated_sales_tax"] == 0.0
    assert alloc[20]["fee_allocation_confidence"] == "high"

def test_timing_side_priority(temp_db):
    """transaction_tax chooses exact SELL over nearby BUY"""
    c = temp_db.cursor()
    char_id = 1
    e_date = "2026-04-28T14:09:35Z"
    
    # SELL Hound at 14:09:35 (delta 0s)
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (3, char_id, e_date, 30, "Hound", 1, 500, 0, 103))
    # BUY Bouncer II at 14:10:27 (delta 52s)
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (4, char_id, "2026-04-28T14:10:27Z", 40, "Bouncer II", 1, 1000, 1, 104))
              
    # Tax at 14:09:35
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (501, char_id, e_date, "transaction_tax", -25.0, 1000.0, "Tax", None, None, None))
              
    temp_db.commit()
    alloc = allocate_item_fees(temp_db, char_id, "2026-04-28", "2026-04-28")
    
    assert alloc[30]["allocated_sales_tax"] == 25.0
    assert alloc[40]["allocated_sales_tax"] == 0.0

def test_broker_fee_nearest(temp_db):
    """broker fee nearest transaction beats farther transaction"""
    c = temp_db.cursor()
    char_id = 1
    # broker fee at 13:48:33
    e_date = "2026-04-28T13:48:33Z"
    
    # SELL Manticore at 13:47:47, delta -46
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (5, char_id, "2026-04-28T13:47:47Z", 50, "Manticore", 1, 600, 0, 105))
    # SELL Small Ancillary at 13:48:24, delta -9
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?)",
              (6, char_id, "2026-04-28T13:48:24Z", 60, "Small Ancillary", 1, 100, 0, 106))
              
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (502, char_id, e_date, "brokers_fee", -5.0, 1000.0, "Broker", None, None, None))
              
    temp_db.commit()
    alloc = allocate_item_fees(temp_db, char_id, "2026-04-28", "2026-04-28")
    
    assert alloc[60]["allocated_broker_fees"] == 5.0
    assert alloc[60]["fee_allocation_confidence"] == "medium"
