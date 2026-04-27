import sqlite3
from datetime import datetime, timedelta
from core.performance_models import DailyPnLEntry, ItemPerformanceSummary, CharacterPerformanceSummary

class PerformanceEngine:
    def __init__(self, db_path=None):
        import os
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "data", "market_performance.db")
        else:
            self.db_path = db_path

    def find_active_characters(self):
        """Descubre personajes leyendo los logs locales y resolviendo IDs vía ESI público."""
        import logging
        import requests
        from core.log_parser import find_log_files, extract_character_name
        log = logging.getLogger('eve.performance_engine')

        log_files = find_log_files()[:20]
        names = set()
        for f in log_files:
            name = extract_character_name(f)
            if name and not name.isdigit() and "_" not in name:
                names.add(name)

        if not names:
            log.info("[CHARS] Sin archivos de log detectados — combo quedará vacío hasta login ESI")
            return []

        log.info(f"[CHARS] Nombres detectados en logs: {names}")
        try:
            url = "https://esi.evetech.net/latest/universe/ids/"
            res = requests.post(url, json=list(names), timeout=10)
            if res.status_code == 200:
                data = res.json()
                chars = data.get('characters', [])
                log.info(f"[CHARS] ESI /universe/ids/ resolvió: {chars}")
                return chars
            log.warning(f"[CHARS] ESI /universe/ids/ → HTTP {res.status_code}: {res.text[:200]}")
        except Exception as e:
            log.warning(f"[CHARS] ESI /universe/ids/ falló: {e}")
        # No usar fallback con id=0 — un ID 0 nunca es válido en EVE y contamina la DB
        log.info("[CHARS] No se pudieron resolver IDs — el usuario debe hacer login ESI manual")
        return []

    def build_daily_pnl(self, character_id, date_from: str, date_to: str):
        """Genera un listado de PnL diario para un rango de fechas (YYYY-MM-DD)."""
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()

            query_trans = """
                SELECT substr(date, 1, 10) as day,
                       SUM(CASE WHEN is_buy = 0 THEN quantity * unit_price ELSE 0 END) as income,
                       SUM(CASE WHEN is_buy = 1 THEN quantity * unit_price ELSE 0 END) as cost,
                       COUNT(*) as count
                FROM wallet_transactions
                WHERE character_id = ? AND substr(date, 1, 10) BETWEEN ? AND ?
                GROUP BY substr(date, 1, 10)
            """
            c.execute(query_trans, (character_id, date_from, date_to))
            trans_rows = {row[0]: row for row in c.fetchall()}

            query_journal = """
                SELECT substr(date, 1, 10) as day,
                       SUM(CASE WHEN ref_type = 'brokers_fee' THEN ABS(amount) ELSE 0 END) as fees,
                       SUM(CASE WHEN ref_type = 'transaction_tax' THEN ABS(amount) ELSE 0 END) as tax
                FROM wallet_journal
                WHERE character_id = ? AND substr(date, 1, 10) BETWEEN ? AND ?
                GROUP BY substr(date, 1, 10)
            """
            c.execute(query_journal, (character_id, date_from, date_to))
            journal_rows = {row[0]: row for row in c.fetchall()}

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
        finally:
            conn.close()
        return results

    def build_item_summary(self, character_id, date_from, date_to):
        conn = sqlite3.connect(self.db_path)
        try:
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
            
            # También necesitamos los fees asociados a este item si existen en el journal (opcional, pero por ahora estimamos)
            # Para el MVP, estimamos fees como el 1.5% de las ventas si no hay detalle exacto por item
        finally:
            conn.close()

        summaries = []
        for r in rows:
            item_id, item_name, sold, bought, income, cost, trades = r

            # Cálculos Refinados
            avg_buy_price = (cost / bought) if bought > 0 else 0
            
            # El beneficio crudo es Income - Cost (pero esto castiga la acumulación)
            profit_raw = income - cost
            
            # El beneficio realizado es: lo vendido - lo que costó comprarlo (estimado)
            # Nota: Si sold > bought en el periodo, usamos el avg_buy_price (que vendrá de compras previas no vistas, 
            # pero al menos es una base). Si avg_buy_price es 0, no podemos estimar bien.
            realized_cost = sold * avg_buy_price
            # Estimación de fees (Broker + Tax ~ 2.5% promedio)
            est_fees = income * 0.025 if sold > 0 else 0
            realized_profit = income - realized_cost - est_fees
            
            # Valor del inventario abierto (neto acumulado)
            net = bought - sold
            inventory_value = net * avg_buy_price if net > 0 else 0
            
            margin = (realized_profit / realized_cost * 100) if realized_cost > 0 else 0
            
            # Lógica Operativa Mejorada
            status = "Normal"
            if bought == 0 and sold > 0:
                status = "Liquidando"
            elif net == 0 and bought > 0:
                status = "Flujo Equilibrado"
            elif net > bought * 0.7 and bought > 5:
                status = "Acumulando Stock"
            elif sold > bought * 0.5 and bought > 0:
                status = "Rotando Bien"
            elif net > 0 and sold < bought * 0.1:
                status = "Salida Lenta"
            elif inventory_value > 500000000: # Más de 500M atrapados
                status = "Exposición Alta"

            summaries.append(ItemPerformanceSummary(
                character_id=character_id,
                item_id=item_id,
                item_name=item_name or f"Item {item_id}",
                period_start=datetime.fromisoformat(date_from),
                period_end=datetime.fromisoformat(date_to),
                total_sold_units=sold,
                total_bought_units=bought,
                net_units=net,
                gross_income=income,
                gross_cost=cost,
                fees_paid=est_fees,
                profit_net=profit_raw,
                realized_profit_est=realized_profit,
                inventory_value_est=inventory_value,
                margin_real_pct=margin,
                trade_count=trades,
                status_text=status
            ))

        # Ordenamos por beneficio realizado estimado
        summaries.sort(key=lambda x: x.realized_profit_est, reverse=True)
        return summaries

    def build_character_summary(self, character_id, date_from, date_to):
        item_summaries = self.build_item_summary(character_id, date_from, date_to)
        daily = self.build_daily_pnl(character_id, date_from, date_to)
        
        total_income = sum(d.gross_income for d in daily)
        total_cost = sum(d.gross_cost for d in daily)
        total_broker_fees = sum(d.fees for d in daily)
        total_sales_tax = sum(d.tax for d in daily)
        total_fees = total_broker_fees + total_sales_tax
        
        # Net Cashflow (Rolling Trade Profit)
        net_cashflow = total_income - total_cost - total_fees
        
        # Realized Profit (Closed accounting based on COGS)
        total_realized_profit = sum(s.realized_profit_est for s in item_summaries)
        inventory_exposure = sum(s.inventory_value_est for s in item_summaries)
        
        # Diagnóstico de contexto
        context = "Operativa Balanceada"
        if total_cost > total_income * 1.5:
            context = "Acumulación Intensa (Rolling Negativo, Stock Creciendo)"
        elif total_income > total_cost * 1.5:
            context = "Liquidación de Stock (Cashflow Alto, Desinversión)"
        elif total_realized_profit > abs(net_cashflow) and net_cashflow < 0:
            context = "Operativa Saludable con Reinversión"
        
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            c.execute("SELECT balance, date FROM wallet_snapshots WHERE character_id = ? ORDER BY date DESC LIMIT 1", (character_id,))
            row = c.fetchone()
            wallet = row[0] if row else 0
            last_sync = datetime.fromisoformat(row[1]) if row else datetime.utcnow()
        finally:
            conn.close()

        return CharacterPerformanceSummary(
            character_id=character_id,
            character_name="Piloto", 
            portrait_url="",
            period_start=datetime.fromisoformat(date_from),
            period_end=datetime.fromisoformat(date_to),
            total_income=total_income,
            total_cost=total_cost,
            broker_fees=total_broker_fees,
            sales_tax=total_sales_tax,
            total_fees=total_fees,
            net_cashflow=net_cashflow,
            total_realized_profit=total_realized_profit,
            inventory_exposure=inventory_exposure,
            wallet_current=wallet,
            last_synced_at=last_sync,
            period_context=context
        )
