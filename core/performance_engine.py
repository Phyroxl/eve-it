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
        """Calcula el resumen por item con lógica de WAC (Weighted Average Cost) global."""
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()

            # 1. Obtener actividad del periodo actual
            query_period = """
                SELECT item_id, item_name,
                       SUM(CASE WHEN is_buy = 0 THEN quantity ELSE 0 END) as sold_qty,
                       SUM(CASE WHEN is_buy = 1 THEN quantity ELSE 0 END) as bought_qty,
                       SUM(CASE WHEN is_buy = 0 THEN quantity * unit_price ELSE 0 END) as income,
                       SUM(CASE WHEN is_buy = 1 THEN quantity * unit_price ELSE 0 END) as cost,
                       COUNT(*) as trades
                FROM wallet_transactions
                WHERE character_id = ? AND substr(date, 1, 10) BETWEEN ? AND ?
                GROUP BY item_id
            """
            c.execute(query_period, (character_id, date_from, date_to))
            period_rows = c.fetchall()

            # 2. Para cada item, calcular su WAC global (no solo del periodo)
            # Esto evita el error de beneficio 100% en items comprados hace tiempo.
            summaries = []
            for r in period_rows:
                item_id, item_name, sold_qty, bought_qty, income, cost, trades = r
                
                # Buscamos el precio medio de compra histórico para este personaje/item
                c.execute("""
                    SELECT SUM(quantity * unit_price) / SUM(quantity)
                    FROM wallet_transactions
                    WHERE character_id = ? AND item_id = ? AND is_buy = 1
                """, (character_id, item_id))
                res_wac = c.fetchone()
                wac_global = res_wac[0] if res_wac and res_wac[0] else 0
                
                # Si no hay compras históricas en DB, usamos el precio de compra medio del periodo
                # Si tampoco hay en el periodo, el WAC será 0 (Venta huérfana)
                avg_buy_price = wac_global if wac_global > 0 else (cost / bought_qty if bought_qty > 0 else 0)
                
                # COGS: Cost of Goods Sold (Lo que nos costó adquirir lo que hemos vendido)
                cogs = sold_qty * avg_buy_price
                
                # Fees: Usamos una estimación proporcional basada en los fees totales del periodo
                # (Proporcional al volumen de venta de este item vs ventas totales)
                # Nota: Esto es una aproximación para el desglose por item.
                # El neto TOTAL usará los fees reales del journal.
                est_fees = income * 0.025 if sold_qty > 0 else 0
                
                net_profit = income - cogs - est_fees
                net_units = bought_qty - sold_qty
                inventory_val = net_units * avg_buy_price if net_units > 0 else 0
                margin = (net_profit / cogs * 100) if cogs > 0 else 0
                
                # Lógica de Status
                status = "Normal"
                if avg_buy_price == 0 and sold_qty > 0: status = "Coste Desconocido"
                elif bought_qty == 0 and sold_qty > 0: status = "Liquidando"
                elif net_units == 0: status = "Flujo Cerrado"
                elif net_units > 0: status = "Incrementando Stock"

                summaries.append(ItemPerformanceSummary(
                    character_id=character_id,
                    item_id=item_id,
                    item_name=item_name or f"Item {item_id}",
                    period_start=datetime.fromisoformat(date_from),
                    period_end=datetime.fromisoformat(date_to),
                    total_sold_units=sold_qty,
                    total_bought_units=bought_qty,
                    net_units=net_units,
                    gross_income=income,
                    gross_cost=cost,
                    fees_paid=est_fees,
                    net_profit=net_profit,
                    cogs_total=cogs,
                    avg_buy_price=avg_buy_price,
                    inventory_value_est=inventory_val,
                    margin_real_pct=margin,
                    trade_count=trades,
                    status_text=status
                ))

        finally:
            conn.close()

        summaries.sort(key=lambda x: x.net_profit, reverse=True)
        return summaries

    def build_character_summary(self, character_id, date_from, date_to):
        item_summaries = self.build_item_summary(character_id, date_from, date_to)
        daily = self.build_daily_pnl(character_id, date_from, date_to)
        
        total_income = sum(d.gross_income for d in daily)
        total_cost = sum(d.gross_cost for d in daily)
        total_broker_fees = sum(d.fees for d in daily)
        total_sales_tax = sum(d.tax for d in daily)
        total_fees = total_broker_fees + total_sales_tax
        
        # Net Cashflow (Rolling Trade Profit): Variación neta de ISK en cartera por trading
        net_cashflow = total_income - total_cost - total_fees
        
        # Net Profit: Beneficio contable basado en COGS
        total_cogs = sum(s.cogs_total for s in item_summaries)
        total_net_profit = total_income - total_cogs - total_fees
        
        inventory_exposure = sum(s.inventory_value_est for s in item_summaries)
        
        # Diagnóstico de contexto contable
        context = "Operativa Balanceada"
        if total_cost > total_income * 2:
            context = "Inversión Pesada (Cashflow Negativo, Stock Creciendo)"
        elif total_income > total_cost * 2:
            context = "Desinversión / Liquidación (Cashflow > Profit)"
        elif total_net_profit > 0 and net_cashflow < 0:
            context = "Rentable con Reinversión (Profit positivo pero sin liquidez)"
        elif total_net_profit < 0:
            context = "Operativa en Pérdida"
        
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
            total_net_profit=total_net_profit,
            total_cogs=total_cogs,
            inventory_exposure=inventory_exposure,
            wallet_current=wallet,
            last_synced_at=last_sync,
            period_context=context
        )
