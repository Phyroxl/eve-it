import pytest
import sqlite3
import os
from datetime import datetime, timedelta
from core.performance_fee_diagnostics import diagnose_fee_allocation, format_fee_diagnostics_report

@pytest.fixture
def temp_db():
    db_path = "tests/test_diag.db"
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
        order_id INTEGER,
        location_id INTEGER
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

def test_diagnose_exact_transaction_context(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (100, char_id, date_now, 34, "Tritanium", 1000, 5.0, 0, 1000, 60000001))
    
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (500, char_id, date_now, "transaction_tax", -150.0, 1000.0, "Tax", None, 100, "transaction_id"))
    
    temp_db.commit()
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    e = diag["entries"][0]
    assert e["classification"] == "exact_transaction_context"
    assert e["confidence"] == "high"
    assert e["best_guess_item_id"] == 34

def test_diagnose_exact_order_context(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (101, char_id, date_now, 1230, "Vexor", 1, 20000000.0, 0, 5000, 60000001))
    
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (501, char_id, date_now, "brokers_fee", -250000.0, 1000.0, "Broker", None, 5000, "order_id"))
    
    temp_db.commit()
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    e = diag["entries"][0]
    assert e["classification"] == "exact_order_context"
    assert e["confidence"] == "high"
    assert e["best_guess_order_id"] == 5000

def test_diagnose_description_match(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (102, char_id, date_now, 638, "Raven", 1, 500000000.0, 1, 6000000000, 60000001))
    
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (502, char_id, date_now, "brokers_fee", -5000000.0, 1000.0, "Market order commission for 6000000000", None, None, None))
    
    temp_db.commit()
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    e = diag["entries"][0]
    assert e["best_guess_order_id"] == 6000000000
    assert e["classification"] == "description_match"
    assert e["confidence"] == "medium"

def test_diagnose_timing_exact_cluster(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (103, char_id, date_now, 34, "Tritanium", 1000, 5.0, 0, 7000, 60000001))
    
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (503, char_id, date_now, "transaction_tax", -150.0, 1000.0, "Sales tax", None, None, None))
    
    temp_db.commit()
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    e = diag["entries"][0]
    assert e["classification"] == "timing_exact_sale_cluster"
    assert e["confidence"] == "high"

def test_diagnose_nearby_sorting(temp_db):
    c = temp_db.cursor()
    char_id = 1
    j_date = "2026-05-01T12:00:00Z"
    
    # SELL item A at 11:59:20 (delta -40s)
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (101, char_id, "2026-05-01T11:59:20Z", 10, "Item A", 1, 100, 0, 101, 1))
    # SELL item B at 12:00:00 (delta 0s)
    c.execute("INSERT INTO wallet_transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (102, char_id, j_date, 20, "Item B", 1, 200, 0, 102, 1))
              
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (502, char_id, j_date, "transaction_tax", -10.0, 1000.0, "Tax", None, None, None))
              
    temp_db.commit()
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    e = diag["entries"][0]
    assert e["nearby_transactions"][0]["item_id"] == 20

def test_diagnose_orphan(temp_db):
    c = temp_db.cursor()
    char_id = 1
    
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (504, char_id, "2026-05-01T12:00:00Z", "brokers_fee", -100.0, 1000.0, "Mystery fee", None, None, None))
    
    temp_db.commit()
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    e = diag["entries"][0]
    assert e["classification"] == "orphan"
    assert e["confidence"] == "none"

def test_report_formatter_with_warning(temp_db):
    c = temp_db.cursor()
    char_id = 1
    date_now = "2026-05-01T12:00:00Z"
    
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (505, char_id, date_now, "brokers_fee", -100.0, 1000.0, "Test", None, None, None))
    temp_db.commit()
    
    diag = diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    report = format_fee_diagnostics_report(diag)
    
    assert "[WALLET FEE DIAGNOSTICS]" in report
    assert "[!] WARNING: CONTEXT_ID UNAVAILABLE" in report
    assert "ID: 505" in report

def test_diagnostic_is_readonly(temp_db):
    c = temp_db.cursor()
    char_id = 1
    c.execute("INSERT INTO wallet_journal VALUES (?,?,?,?,?,?,?,?,?,?)",
              (506, char_id, "2026-05-01T12:00:00Z", "brokers_fee", -100.0, 1000.0, "Test", None, None, None))
    temp_db.commit()
    
    c.execute("SELECT COUNT(*) FROM wallet_journal")
    before = c.fetchone()[0]
    
    diagnose_fee_allocation(temp_db, char_id, "2026-05-01", "2026-05-01")
    
    c.execute("SELECT COUNT(*) FROM wallet_journal")
    after = c.fetchone()[0]
    
    assert before == after
