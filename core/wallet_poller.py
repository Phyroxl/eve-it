import sqlite3
import os
import logging
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer, QThread
from core.esi_client import ESIClient

class WalletPoller(QObject):
    finished = Signal()
    error = Signal(str)
    sync_report = Signal(dict)  # diagnóstico completo emitido antes de finished

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
        log = logging.getLogger('eve.wallet_poller')
        log.info(f"[POLL] Iniciando sync para char_id={character_id}")
        report = {
            'char_id': character_id,
            'balance': None,
            'esi_journal_count': 0,
            'esi_trans_count': 0,
            'saved_journal': 0,
            'saved_trans': 0,
            'db_snapshots': 0,
            'db_transactions': 0,
            'db_journal': 0,
            'db_trans_date_min': None,
            'db_trans_date_max': None,
            'error': None,
        }
        try:
            # 1. Wallet Balance
            balance = self.client.character_wallet(character_id, token)
            report['balance'] = balance
            if balance is not None:
                self._save_snapshot(character_id, balance)
                log.info(f"[POLL] Balance guardado: {balance:.0f} ISK para char_id={character_id}")
            else:
                log.warning(f"[POLL] character_wallet devolvió None para char_id={character_id} — token inválido o scope ausente")

            # 2. Wallet Journal (Fees/Taxes)
            journal_entries = self.client.character_wallet_journal(character_id, token)
            report['esi_journal_count'] = len(journal_entries) if journal_entries else 0
            if journal_entries:
                report['saved_journal'] = self._save_journal(character_id, journal_entries)
            log.info(f"[POLL] Journal: {report['esi_journal_count']} recibidas, {report['saved_journal']} guardadas")

            # 3. Wallet Transactions (Sales/Purchases)
            transactions = self.client.character_wallet_transactions(character_id, token)
            report['esi_trans_count'] = len(transactions) if transactions else 0
            if transactions:
                report['saved_trans'] = self._save_transactions(character_id, transactions)
            log.info(f"[POLL] Transacciones: {report['esi_trans_count']} recibidas, {report['saved_trans']} guardadas")

            if not transactions and not journal_entries:
                log.warning(f"[POLL] ESI devolvió 0 transacciones Y 0 journal — personaje sin historial o token expirado")

            # 4. Verificar estado real en DB tras el guardado
            conn = sqlite3.connect(self.db_path)
            try:
                report['db_snapshots'] = conn.execute(
                    "SELECT COUNT(*) FROM wallet_snapshots WHERE character_id=?", (character_id,)
                ).fetchone()[0]
                report['db_transactions'] = conn.execute(
                    "SELECT COUNT(*) FROM wallet_transactions WHERE character_id=?", (character_id,)
                ).fetchone()[0]
                report['db_journal'] = conn.execute(
                    "SELECT COUNT(*) FROM wallet_journal WHERE character_id=?", (character_id,)
                ).fetchone()[0]
                row = conn.execute(
                    "SELECT MIN(substr(date,1,10)), MAX(substr(date,1,10)) FROM wallet_transactions WHERE character_id=?",
                    (character_id,)
                ).fetchone()
                report['db_trans_date_min'] = row[0]
                report['db_trans_date_max'] = row[1]
            finally:
                conn.close()

            log.info(
                f"[POLL] DB final: {report['db_snapshots']} snaps, "
                f"{report['db_transactions']} trans ({report['db_trans_date_min']} → {report['db_trans_date_max']}), "
                f"{report['db_journal']} journal"
            )

            self.sync_report.emit(report)
            self.finished.emit()
        except Exception as e:
            log.error(f"WalletPoller Error: {e}", exc_info=True)
            report['error'] = str(e)
            self.sync_report.emit(report)
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
        saved = 0
        try:
            c = conn.cursor()
            valid_types = ["market_transaction", "brokers_fee", "transaction_tax"]
            for e in entries:
                if e.get('ref_type') in valid_types:
                    c.execute("INSERT OR REPLACE INTO wallet_journal (id, character_id, date, ref_type, amount, balance, description) VALUES (?,?,?,?,?,?,?)",
                              (e['id'], char_id, e['date'], e['ref_type'], e['amount'], e.get('balance'), e.get('description')))
                    saved += 1
            conn.commit()
        finally:
            conn.close()
        return saved

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
        saved = 0
        try:
            c = conn.cursor()
            for t in transactions:
                item_name = names_map.get(t['type_id'], "")
                c.execute("""INSERT OR REPLACE INTO wallet_transactions
                             (transaction_id, character_id, date, item_id, item_name, quantity, unit_price, is_buy, order_id, client_id, location_id)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (t['transaction_id'], char_id, t['date'], t['type_id'], item_name, t['quantity'], t['unit_price'],
                           1 if t['is_buy'] else 0, t.get('order_id'), t.get('client_id'), t.get('location_id')))
                saved += 1
            conn.commit()
        finally:
            conn.close()
        return saved

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
