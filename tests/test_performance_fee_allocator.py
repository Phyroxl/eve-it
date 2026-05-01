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
