import sqlite3
from datetime import datetime, timedelta
from core.performance_models import DailyPnLEntry, ItemPerformanceSummary, CharacterPerformanceSummary

class PerformanceEngine:
    def __init__(self, db_path="data/market_performance.db"):
        self.db_path = db_path

    def find_active_characters(self):
        """Descubre personajes leyendo los logs locales y resolviendo IDs vía ESI público."""
        from core.log_parser import find_log_files, extract_character_name
        import requests
        
        # 1. Obtener nombres de los logs (últimos 20 archivos)
        log_files = find_log_files()[:20]
        names = set()
        for f in log_files:
            name = extract_character_name(f)
            if name and not name.isdigit() and "_" not in name:
                names.add(name)
        
        if not names:
            return []

        # 2. Resolver IDs vía ESI Público (No requiere token)
        try:
            url = "https://esi.evetech.net/latest/universe/ids/"
            res = requests.post(url, json=list(names))
            if res.status_code == 200:
                data = res.json()
                return data.get('characters', [])
        except Exception:
            pass
        return [{"id": 0, "name": n} for n in names] # Fallback

    def build_daily_pnl(self, character_id, date_from: str, date_to: str):
        """Genera un listado de PnL diario para un rango de fechas (YYYY-MM-DD)."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Agregamos transacciones por día
        query_trans = """
            SELECT substr(date, 1, 10) as day, 
                   SUM(CASE WHEN is_buy = 0 THEN quantity * unit_price ELSE 0 END) as income,
                   SUM(CASE WHEN is_buy = 1 THEN quantity * unit_price ELSE 0 END) as cost,
                   COUNT(*) as count
            FROM wallet_transactions
            WHERE character_id = ? AND day BETWEEN ? AND ?
            GROUP BY day
        """
        c.execute(query_trans, (character_id, date_from, date_to))
        trans_rows = {row[0]: row for row in c.fetchall()}

        # Agregamos fees y taxes desde el journal
        query_journal = """
            SELECT substr(date, 1, 10) as day,
                   SUM(CASE WHEN ref_type = 'brokers_fee' THEN ABS(amount) ELSE 0 END) as fees,
                   SUM(CASE WHEN ref_type = 'transaction_tax' THEN ABS(amount) ELSE 0 END) as tax
            FROM wallet_journal
            WHERE character_id = ? AND day BETWEEN ? AND ?
            GROUP BY day
        """
        c.execute(query_journal, (character_id, date_from, date_to))
        journal_rows = {row[0]: row for row in c.fetchall()}

        # Unimos los datos
        all_days = sorted(set(list(trans_rows.keys()) + list(journal_rows.keys())))
        results = []
        cumulative = 0
        for day in all_days:
            t = trans_rows.get(day, (day, 0, 0, 0))
            j = journal_rows.get(day, (day, 0, 0))
            
            income = t[1]
            cost = t[2]
            fees = j[1]
            tax = j[2]
            profit = income - cost - fees - tax
            cumulative += profit
            
            results.append(DailyPnLEntry(
                character_id=character_id,
                date=day,
                gross_income=income,
                gross_cost=cost,
                fees=fees,
                tax=tax,
                profit_net=profit,
                cumulative_profit_net=cumulative,
                transaction_count=t[3]
            ))
            
        conn.close()
        return results

    def build_item_summary(self, character_id, date_from, date_to):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        query = """
            SELECT item_id, item_name,
                   SUM(CASE WHEN is_buy = 0 THEN quantity ELSE 0 END) as sold,
                   SUM(CASE WHEN is_buy = 1 THEN quantity ELSE 0 END) as bought,
                   SUM(CASE WHEN is_buy = 0 THEN quantity * unit_price ELSE 0 END) as income,
                   SUM(CASE WHEN is_buy = 1 THEN quantity * unit_price ELSE 0 END) as cost,
                   COUNT(*) as trades
            FROM wallet_transactions
            WHERE character_id = ? AND substr(date, 1, 10) BETWEEN ? AND ?
            GROUP BY item_id
        """
        c.execute(query, (character_id, date_from, date_to))
        rows = c.fetchall()
        
        summaries = []
        for r in rows:
            # Una simplificación para el MVP: no podemos asignar fees exactos por item 
            # desde el journal sin un tracking de order_id muy preciso.
            # Estimamos un 3% de fees promedio sobre el volumen si no hay tracking.
            # Pero para el MVP, reportaremos profit bruto del item (ventas - compras).
            income = r[4]
            cost = r[5]
            profit = income - cost
            margin = (profit / cost * 100) if cost > 0 else 0
            
            summaries.append(ItemPerformanceSummary(
                character_id=character_id,
                item_id=r[0],
                item_name=r[1] or f"Item {r[0]}",
                period_start=datetime.fromisoformat(date_from),
                period_end=datetime.fromisoformat(date_to),
                total_sold_units=r[2],
                total_bought_units=r[3],
                gross_income=income,
                gross_cost=cost,
                fees_paid=0, # MVP simplification
                profit_net=profit,
                margin_real_pct=margin,
                trade_count=r[6]
            ))
            
        conn.close()
        # Sort by profit net
        summaries.sort(key=lambda x: x.profit_net, reverse=True)
        return summaries

    def build_character_summary(self, character_id, date_from, date_to):
        daily = self.build_daily_pnl(character_id, date_from, date_to)
        total_profit = sum(d.profit_net for d in daily)
        total_income = sum(d.gross_income for d in daily)
        total_cost = sum(d.gross_cost for d in daily)
        total_fees = sum(d.fees + d.tax for d in daily)
        
        # Get current wallet
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT balance, date FROM wallet_snapshots WHERE character_id = ? ORDER BY date DESC LIMIT 1", (character_id,))
        row = c.fetchone()
        wallet = row[0] if row else 0
        last_sync = datetime.fromisoformat(row[1]) if row else datetime.utcnow()
        conn.close()

        return CharacterPerformanceSummary(
            character_id=character_id,
            character_name="Piloto", # To be filled by UI
            portrait_url="",
            period_start=datetime.fromisoformat(date_from),
            period_end=datetime.fromisoformat(date_to),
            total_profit_net=total_profit,
            total_income=total_income,
            total_cost=total_cost,
            total_fees=total_fees,
            wallet_current=wallet,
            last_synced_at=last_sync
        )
