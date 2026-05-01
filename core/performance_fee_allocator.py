import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('eve.performance_fee_allocator')

def score_nearby_transaction_for_fee(entry, tx_item) -> float:
    """
    Calcula un score de afinidad para una transacción candidata.
    A MENOR score, mejor es el match (0 es perfecto).
    entry: dict con 'ref_type', 'date', etc.
    tx_item: dict con 'seconds_delta', 'is_buy', etc.
    """
    dt = abs(tx_item['seconds_delta'])
    
    # 1. Penalización base por tiempo
    score = dt
    
    # 2. Preferencia de lado (transaction_tax -> SELL)
    if entry['ref_type'] == 'transaction_tax':
        if tx_item['is_buy']: # Es una compra
            score += 100.0 # Penalizar compras para taxes (suelen ser de ventas)
        else:
            # Es venta: boost
            score -= 0.1
            
    # 3. Preferencia por dt=0 (Exactamente el mismo segundo)
    if dt == 0:
        score -= 0.5 
        
    return score

def allocate_item_fees(conn, character_id, date_from, date_to) -> dict:
    """
    Asigna fees reales del wallet_journal a cada item_id basándose en:
    1. Exact Match (context_id -> transaction_id o order_id)
    2. Timing Cluster Match (Tax cerca de venta, broker cerca de buy/sell)
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
                    "fee_allocation_timing_entries": 0,
                    "fee_allocation_high_conf_timing": 0, # NUEVO
                    "fee_allocation_estimated_entries": 0,
                    "fee_allocation_orphan_entries": 0,
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
                'allocated': False,
                'confidence': 'none'
            })

        # 3. FASE A: Exact Match (context_id)
        for entry in journal_entries:
            if entry['ctx_id']:
                target_tid = None
                if entry['ctx_type'] in ('transaction_id', 'market_transaction_id'):
                    target_tid = entry['ctx_id']
                
                if target_tid:
                    for t in transactions:
                        if t['tid'] == target_tid:
                            if entry['ref_type'] == 'transaction_tax':
                                allocation[t['item_id']]["allocated_sales_tax"] += entry['amount']
                            else:
                                allocation[t['item_id']]["allocated_broker_fees"] += entry['amount']
                            
                            allocation[t['item_id']]["fee_allocation_exact_entries"] += 1
                            entry['allocated'] = True
                            entry['confidence'] = 'high'
                            break
                
                elif entry['ctx_type'] == 'order_id':
                    target_oid = entry['ctx_id']
                    matched_items = set([t['item_id'] for t in transactions if t['order_id'] == target_oid])
                    if matched_items:
                        item_id = list(matched_items)[0]
                        if entry['ref_type'] == 'transaction_tax':
                            allocation[item_id]["allocated_sales_tax"] += entry['amount']
                        else:
                            allocation[item_id]["allocated_broker_fees"] += entry['amount']
                        
                        allocation[item_id]["fee_allocation_exact_entries"] += 1
                        entry['allocated'] = True
                        entry['confidence'] = 'high'

        # 4. FASE B: Timing Cluster Match
        for entry in journal_entries:
            if entry['allocated']:
                continue
            
            # Buscar transacciones en ventana de +/- 60s
            try:
                j_date = datetime.fromisoformat(entry['date'].replace('Z', ''))
            except:
                continue
                
            nearby_candidates = []
            for t in transactions:
                try:
                    t_date = datetime.fromisoformat(t['date'].replace('Z', ''))
                    delta = (t_date - j_date).total_seconds()
                    if abs(delta) <= 60:
                        candidate = t.copy()
                        candidate['seconds_delta'] = delta
                        candidate['score'] = score_nearby_transaction_for_fee(entry, candidate)
                        nearby_candidates.append(candidate)
                except:
                    continue
            
            if not nearby_candidates:
                continue
                
            # Ordenar por mejor score
            nearby_candidates.sort(key=lambda x: x['score'])
            best = nearby_candidates[0]
            
            # Heurísticas de asignación
            if entry['ref_type'] == 'transaction_tax':
                # Si hay un SELL exacto (dt=0), alta confianza
                if best['is_buy'] == 0 and abs(best['seconds_delta']) == 0:
                    allocation[best['item_id']]["allocated_sales_tax"] += entry['amount']
                    allocation[best['item_id']]["fee_allocation_high_conf_timing"] += 1
                    entry['allocated'] = True
                    entry['confidence'] = 'high'
                else:
                    # Asignar al mejor (usualmente venta más cercana)
                    allocation[best['item_id']]["allocated_sales_tax"] += entry['amount']
                    allocation[best['item_id']]["fee_allocation_timing_entries"] += 1
                    entry['allocated'] = True
                    entry['confidence'] = 'medium' if abs(best['seconds_delta']) < 5 else 'low'
            
            elif entry['ref_type'] == 'brokers_fee':
                # Broker fee: asignar al más cercano si es razonablemente único o dominante
                if len(nearby_candidates) == 1:
                    allocation[best['item_id']]["allocated_broker_fees"] += entry['amount']
                    allocation[best['item_id']]["fee_allocation_timing_entries"] += 1
                    entry['allocated'] = True
                    entry['confidence'] = 'medium'
                else:
                    # Si el mejor es mucho mejor que el segundo (ej: delta < 10 vs delta > 30)
                    if abs(best['seconds_delta']) < 10 and abs(nearby_candidates[1]['seconds_delta']) > 30:
                        allocation[best['item_id']]["allocated_broker_fees"] += entry['amount']
                        allocation[best['item_id']]["fee_allocation_timing_entries"] += 1
                        entry['allocated'] = True
                        entry['confidence'] = 'medium'
                    else:
                        # Ambiguo: Dejar para proporcional o asignar con confianza baja
                        pass

        # 5. FASE C: Proportional Fallback (Totals preservation)
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
            
            # Confidence logic update
            has_exact = stats["fee_allocation_exact_entries"] > 0
            has_high_timing = stats["fee_allocation_high_conf_timing"] > 0
            has_est = stats["fee_allocation_estimated_entries"] > 0
            has_timing = stats["fee_allocation_timing_entries"] > 0

            if has_exact or has_high_timing:
                stats["fee_allocation_confidence"] = "high" if not has_est else "medium"
                stats["allocation_method"] = "exact_match" if has_exact else "timing_cluster"
            elif has_timing:
                stats["fee_allocation_confidence"] = "medium" if not has_est else "low"
                stats["allocation_method"] = "timing_cluster"
            elif has_est:
                stats["fee_allocation_confidence"] = "low"
                stats["allocation_method"] = "proportional_fallback"
            else:
                stats["fee_allocation_confidence"] = "low"
                stats["allocation_method"] = "no_data"

    except Exception as e:
        logger.error(f"Error in allocate_item_fees: {e}", exc_info=True)
    
    return allocation
