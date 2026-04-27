import sqlite3
import os
import logging
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer, QThread
from core.esi_client import ESIClient

class WalletPoller(QObject):
    finished = Signal()
    error = Signal(str)

    def __init__(self, db_path="data/market_performance.db"):
        super().__init__()
        # Usar ruta absoluta para evitar problemas de directorio de ejecución
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base_dir, "data", "market_performance.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.client = ESIClient()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Transactions table
        c.execute('''CREATE TABLE IF NOT EXISTS wallet_transactions (
            transaction_id INTEGER PRIMARY KEY,
            character_id INTEGER,
            date TEXT,
            item_id INTEGER,
            item_name TEXT,
            quantity INTEGER,
            unit_price REAL,
            is_buy INTEGER,
            order_id INTEGER,
            client_id INTEGER,
            location_id INTEGER
        )''')

        # Journal table (for fees and taxes)
        c.execute('''CREATE TABLE IF NOT EXISTS wallet_journal (
            id INTEGER PRIMARY KEY,
            character_id INTEGER,
            date TEXT,
            ref_type TEXT,
            amount REAL,
            balance REAL,
            description TEXT,
            reason TEXT
        )''')

        # Snapshots (balance history)
        c.execute('''CREATE TABLE IF NOT EXISTS wallet_snapshots (
            character_id INTEGER,
            date TEXT,
            balance REAL,
            PRIMARY KEY (character_id, date)
        )''')

        # Índices para consultas frecuentes
        c.execute('CREATE INDEX IF NOT EXISTS idx_wt_char_date ON wallet_transactions (character_id, date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_wj_char_date ON wallet_journal (character_id, date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_ws_char ON wallet_snapshots (character_id)')

        conn.commit()
        conn.close()

    def poll(self, character_id, token):
        """Ejecuta un ciclo de sincronización completo."""
        try:
            # 1. Wallet Balance
            balance = self.client.character_wallet(character_id, token)
            if balance is not None:
                self._save_snapshot(character_id, balance)

            # 2. Wallet Journal (Fees/Taxes)
            journal_entries = self.client.character_wallet_journal(character_id, token)
            if journal_entries:
                self._save_journal(character_id, journal_entries)

            # 3. Wallet Transactions (Sales/Purchases)
            transactions = self.client.character_wallet_transactions(character_id, token)
            if transactions:
                self._save_transactions(character_id, transactions)

            self.finished.emit()
        except Exception as e:
            logging.error(f"WalletPoller Error: {e}")
            self.error.emit(str(e))

    def _save_snapshot(self, char_id, balance):
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            now = datetime.utcnow().isoformat()
            c.execute("INSERT OR REPLACE INTO wallet_snapshots (character_id, date, balance) VALUES (?, ?, ?)",
                      (char_id, now, balance))
            conn.commit()
        finally:
            conn.close()

    def _save_journal(self, char_id, entries):
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            valid_types = ["market_transaction", "brokers_fee", "transaction_tax"]
            for e in entries:
                if e.get('ref_type') in valid_types:
                    c.execute("INSERT OR REPLACE INTO wallet_journal (id, character_id, date, ref_type, amount, balance, description) VALUES (?,?,?,?,?,?,?)",
                              (e['id'], char_id, e['date'], e['ref_type'], e['amount'], e.get('balance'), e.get('description')))
            conn.commit()
        finally:
            conn.close()

    def _save_transactions(self, char_id, transactions):
        if not transactions: return
        
        # 1. Resolver nombres de items que falten
        type_ids = list(set([t['type_id'] for t in transactions]))
        names_map = {}
        try:
            # Pedir nombres en bloques de 500 (límite ESI)
            for i in range(0, len(type_ids), 500):
                chunk = type_ids[i:i+500]
                res = self.client.universe_names(chunk)
                if res:
                    for item in res:
                        names_map[item['id']] = item['name']
        except Exception as e:
            logging.error(f"Error resolviendo nombres: {e}")

        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            for t in transactions:
                item_name = names_map.get(t['type_id'], "")
                c.execute("""INSERT OR REPLACE INTO wallet_transactions
                             (transaction_id, character_id, date, item_id, item_name, quantity, unit_price, is_buy, order_id, client_id, location_id)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (t['transaction_id'], char_id, t['date'], t['type_id'], item_name, t['quantity'], t['unit_price'],
                           1 if t['is_buy'] else 0, t.get('order_id'), t.get('client_id'), t.get('location_id')))
            conn.commit()
        finally:
            conn.close()

    def ensure_demo_data(self, char_id=0):
        """Genera datos de prueba si la BD está vacía."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM wallet_transactions WHERE character_id = ?", (char_id,))
        count = c.fetchone()[0]
        if count == 0:
            import random
            from datetime import timedelta
            
            # 1. Snapshot
            c.execute("INSERT OR REPLACE INTO wallet_snapshots VALUES (?, ?, ?)",
                      (char_id, datetime.utcnow().isoformat(), 1500000000.0))
            
            # 2. Transacciones de los últimos 30 días
            items = [(34, "Tritanium"), (1230, "Vexor"), (638, "Raven"), (29668, "Plex")]
            for i in range(100):
                days_ago = random.randint(0, 30)
                date = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
                item = random.choice(items)
                is_buy = random.choice([0, 1])
                qty = random.randint(1, 1000)
                price = random.uniform(10000, 1000000)
                
                c.execute("INSERT INTO wallet_transactions (character_id, date, item_id, item_name, quantity, unit_price, is_buy) VALUES (?,?,?,?,?,?,?)",
                          (char_id, date, item[0], item[1], qty, price, is_buy))
            
            # 3. Fees y Taxes
            for i in range(50):
                days_ago = random.randint(0, 30)
                date = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
                ref = random.choice(["brokers_fee", "transaction_tax"])
                amt = -random.uniform(5000, 50000)
                c.execute("INSERT INTO wallet_journal (character_id, date, ref_type, amount) VALUES (?,?,?,?)",
                          (char_id, date, ref, amt))
            
            conn.commit()
        conn.close()
