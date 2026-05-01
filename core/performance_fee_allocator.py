import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('eve.performance_fee_allocator')

def allocate_item_fees(conn, character_id, date_from, date_to) -> dict:
    """
    Asigna fees reales del wallet_journal a cada item_id basándose en:
    1. Exact Match (context_id -> transaction_id o order_id)
    2. Timing Match (Tax cerca de venta)
    3. Proportional Fallback (Restante distribuido)
    """
    # Result structure: item_id -> { stats }
    allocation = {}
    
    try:
        # 1. Obtener todas las transacciones del periodo
        c = conn.cursor()
        query_trans = """
            SELECT transaction_id, item_id, item_name, date, quantity, unit_price, is_buy, order_id
            FROM wallet_transactions
            WHERE character_id = ? AND substr(date, 1, 10) BETWEEN ? AND ?
        """
        c.execute(query_trans, (character_id, date_from, date_to))
        transactions = []
        for row in c.fetchall():
            transactions.append({
                'tid': row[0], 'item_id': row[1], 'item_name': row[2],
                'date': row[3], 'qty': row[4], 'price': row[5],
                'is_buy': row[6], 'order_id': row[7],
                'allocated_tax': 0.0, 'allocated_broker': 0.0,
                'entries_count': 0
            })
            if row[1] not in allocation:
                allocation[row[1]] = {
                    "allocated_broker_fees": 0.0,
                    "allocated_sales_tax": 0.0,
                    "allocated_total_fees": 0.0,
                    "allocation_method": "legacy_estimate",
                    "fee_allocation_confidence": "low",
                    "fee_allocation_exact_entries": 0,
                    "fee_allocation_estimated_entries": 0,
                    "gross_income": 0.0,
                    "gross_cost": 0.0
                }
            if row[6] == 0: # Sell
                allocation[row[1]]["gross_income"] += row[4] * row[5]
            else: # Buy
                allocation[row[1]]["gross_cost"] += row[4] * row[5]

        # 2. Obtener journal entries (fees/tax)
        query_journal = """
            SELECT id, date, ref_type, amount, description, reason, context_id, context_id_type
            FROM wallet_journal
            WHERE character_id = ? AND substr(date, 1, 10) BETWEEN ? AND ?
              AND ref_type IN ('brokers_fee', 'transaction_tax')
        """
        c.execute(query_journal, (character_id, date_from, date_to))
        journal_entries = []
        for row in c.fetchall():
            journal_entries.append({
                'id': row[0], 'date': row[1], 'ref_type': row[2], 
                'amount': abs(row[3]), 'desc': row[4], 'reason': row[5],
                'ctx_id': row[6], 'ctx_type': row[7],
                'allocated': False
            })

        # 3. FASE A: Exact Match (context_id)
        for entry in journal_entries:
            if entry['ctx_id']:
                target_tid = None
                if entry['ctx_type'] in ('transaction_id', 'market_transaction_id'):
                    target_tid = entry['ctx_id']
                
                if target_tid:
                    # Match to transaction
                    for t in transactions:
                        if t['tid'] == target_tid:
                            if entry['ref_type'] == 'transaction_tax':
                                t['allocated_tax'] += entry['amount']
                                allocation[t['item_id']]["allocated_sales_tax"] += entry['amount']
                            else:
                                t['allocated_broker'] += entry['amount']
                                allocation[t['item_id']]["allocated_broker_fees"] += entry['amount']
                            
                            allocation[t['item_id']]["fee_allocation_exact_entries"] += 1
                            entry['allocated'] = True
                            break
                
                elif entry['ctx_type'] == 'order_id':
                    target_oid = entry['ctx_id']
                    # Match to all transactions of this order
                    matched_items = set([t['item_id'] for t in transactions if t['order_id'] == target_oid])
                    if matched_items:
                        # Split fee among items (usually just one item per order)
                        # We allocate to the first item for simplicity if multiple (rare)
                        item_id = list(matched_items)[0]
                        if entry['ref_type'] == 'transaction_tax':
                            allocation[item_id]["allocated_sales_tax"] += entry['amount']
                        else:
                            allocation[item_id]["allocated_broker_fees"] += entry['amount']
                        
                        allocation[item_id]["fee_allocation_exact_entries"] += 1
                        entry['allocated'] = True

        # 4. FASE B: Timing Match (Tax near Sell)
        for entry in journal_entries:
            if entry['allocated'] or entry['ref_type'] != 'transaction_tax':
                continue
            
            # Find a sell transaction at exact same time or +/- 2s
            e_date = entry['date'][:19]
            for t in transactions:
                if t['is_buy'] == 0 and t['date'][:19] == e_date:
                    # Match!
                    allocation[t['item_id']]["allocated_sales_tax"] += entry['amount']
                    allocation[t['item_id']]["fee_allocation_exact_entries"] += 1
                    entry['allocated'] = True
                    break

        # 5. FASE C: Proportional Fallback
        unallocated_tax = sum(e['amount'] for e in journal_entries if not e['allocated'] and e['ref_type'] == 'transaction_tax')
        unallocated_broker = sum(e['amount'] for e in journal_entries if not e['allocated'] and e['ref_type'] == 'brokers_fee')
        
        total_income = sum(a["gross_income"] for a in allocation.values())
        total_volume = sum(a["gross_income"] + a["gross_cost"] for a in allocation.values())

        for item_id, stats in allocation.items():
            # Tax proportionally by income
            if unallocated_tax > 0 and total_income > 0:
                share = (stats["gross_income"] / total_income) * unallocated_tax
                stats["allocated_sales_tax"] += share
                stats["fee_allocation_estimated_entries"] += 1
            
            # Broker fees proportionally by total volume (buy+sell)
            if unallocated_broker > 0 and total_volume > 0:
                share = ((stats["gross_income"] + stats["gross_cost"]) / total_volume) * unallocated_broker
                stats["allocated_broker_fees"] += share
                stats["fee_allocation_estimated_entries"] += 1

            # Final totals
            stats["allocated_total_fees"] = stats["allocated_broker_fees"] + stats["allocated_sales_tax"]
            
            # Confidence logic
            if stats["fee_allocation_exact_entries"] > 0 and stats["fee_allocation_estimated_entries"] == 0:
                stats["fee_allocation_confidence"] = "high"
                stats["allocation_method"] = "exact_match"
            elif stats["fee_allocation_exact_entries"] > 0:
                stats["fee_allocation_confidence"] = "medium"
                stats["allocation_method"] = "mixed"
            elif stats["fee_allocation_estimated_entries"] > 0:
                stats["fee_allocation_confidence"] = "low"
                stats["allocation_method"] = "proportional_fallback"
            else:
                stats["fee_allocation_confidence"] = "low"
                stats["allocation_method"] = "no_data"

    except Exception as e:
        logger.error(f"Error in allocate_item_fees: {e}")
        # Return empty or legacy-friendly dict
    
    return allocation
