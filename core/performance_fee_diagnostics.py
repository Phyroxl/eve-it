import sqlite3
import re
import logging
from datetime import datetime, timedelta
from core.performance_fee_allocator import score_nearby_transaction_for_fee

logger = logging.getLogger('eve.performance_fee_diagnostics')

def get_recent_fee_journal_entries(conn, character_id, limit=100, date_from=None, date_to=None):
    """Obtiene filas recientes de brokers_fee, transaction_tax y market_transaction."""
    c = conn.cursor()
    query = """
        SELECT id, date, ref_type, amount, description, reason, context_id, context_id_type
        FROM wallet_journal
        WHERE character_id = ? 
          AND ref_type IN ('brokers_fee', 'transaction_tax', 'market_transaction')
    """
    params = [character_id]
    
    if date_from and date_to:
        query += " AND substr(date, 1, 10) BETWEEN ? AND ?"
        params.extend([date_from, date_to])
        
    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)
    
    c.execute(query, params)
    rows = c.fetchall()
    
    results = []
    for r in rows:
        results.append({
            'id': r[0],
            'date': r[1],
            'ref_type': r[2],
            'amount': r[3],
            'description': r[4],
            'reason': r[5],
            'context_id': r[6],
            'context_id_type': r[7]
        })
    return results

def find_nearby_transactions(conn, character_id, journal_date_str, window_seconds=60):
    """Busca transacciones de wallet cerca de la fecha del journal entry."""
    try:
        j_date = datetime.fromisoformat(journal_date_str.replace('Z', ''))
    except:
        return []
        
    t_start = (j_date - timedelta(seconds=window_seconds)).isoformat()
    t_end = (j_date + timedelta(seconds=window_seconds)).isoformat()
    
    c = conn.cursor()
    query = """
        SELECT transaction_id, date, item_id, item_name, quantity, unit_price, is_buy, order_id, location_id
        FROM wallet_transactions
        WHERE character_id = ? AND date BETWEEN ? AND ?
    """
    c.execute(query, (character_id, t_start, t_end))
    rows = c.fetchall()
    
    results = []
    for r in rows:
        t_date = datetime.fromisoformat(r[1].replace('Z', ''))
        delta = (t_date - j_date).total_seconds()
        
        results.append({
            'transaction_id': r[0],
            'date': r[1],
            'item_id': r[2],
            'item_name': r[3],
            'quantity': r[4],
            'unit_price': r[5],
            'is_buy': r[6],
            'order_id': r[7],
            'location_id': r[8],
            'seconds_delta': delta
        })
    return results

def diagnose_fee_allocation(conn, character_id, date_from, date_to, limit=100):
    """Genera diagnósticos estructurados sobre la asignación de fees."""
    entries = get_recent_fee_journal_entries(conn, character_id, limit, date_from, date_to)
    
    summary = {
        "journal_fee_entries": 0,
        "broker_fee_entries": 0,
        "transaction_tax_entries": 0,
        "market_transaction_entries": 0,
        "entries_with_context_id": 0,
        "entries_with_nearby_transactions": 0,
        "orphan_entries": 0
    }
    
    diagnosed_entries = []
    
    for e in entries:
        summary["journal_fee_entries"] += 1
        if e['ref_type'] == 'brokers_fee': summary["broker_fee_entries"] += 1
        elif e['ref_type'] == 'transaction_tax': summary["transaction_tax_entries"] += 1
        elif e['ref_type'] == 'market_transaction': summary["market_transaction_entries"] += 1
        
        if e['context_id']: summary["entries_with_context_id"] += 1
            
        nearby = find_nearby_transactions(conn, character_id, e['date'])
        # Pre-calcular score para nearby
        for nb in nearby:
            nb['score'] = score_nearby_transaction_for_fee(e, nb)
        nearby.sort(key=lambda x: x['score'])
        
        if nearby: summary["entries_with_nearby_transactions"] += 1
        
        diag = {
            "journal_id": e['id'],
            "date": e['date'],
            "ref_type": e['ref_type'],
            "amount": e['amount'],
            "description": e['description'],
            "reason": e['reason'],
            "context_id": e['context_id'],
            "context_id_type": e['context_id_type'],
            "classification": "orphan",
            "nearby_transactions": nearby,
            "best_guess_item_id": None,
            "best_guess_item_name": None,
            "best_guess_order_id": None,
            "best_match_rule": "none",
            "confidence": "none"
        }
        
        # A) Exact Match
        if e['context_id'] and e['context_id_type'] in ('transaction_id', 'market_transaction_id', 'order_id'):
            c = conn.cursor()
            if e['context_id_type'] == 'order_id':
                c.execute("SELECT item_id, item_name, order_id FROM wallet_transactions WHERE order_id = ? LIMIT 1", (e['context_id'],))
                row = c.fetchone()
                if row:
                    diag["classification"] = "exact_order_context"
                    diag["confidence"] = "high"
                    diag["best_guess_item_id"] = row[0]
                    diag["best_guess_item_name"] = row[1]
                    diag["best_guess_order_id"] = row[2]
                    diag["best_match_rule"] = "context_id"
            else:
                c.execute("SELECT item_id, item_name, order_id FROM wallet_transactions WHERE transaction_id = ? LIMIT 1", (e['context_id'],))
                row = c.fetchone()
                if row:
                    diag["classification"] = "exact_transaction_context"
                    diag["confidence"] = "high"
                    diag["best_guess_item_id"] = row[0]
                    diag["best_guess_item_name"] = row[1]
                    diag["best_guess_order_id"] = row[2]
                    diag["best_match_rule"] = "context_id"

        # B) Description Match
        if diag["classification"] == "orphan":
            all_text = f"{e['description'] or ''} {e['reason'] or ''}"
            numbers = re.findall(r'\d+', all_text)
            for n in numbers:
                val = int(n)
                if val > 1000000:
                    c = conn.cursor()
                    c.execute("SELECT item_id, item_name, order_id FROM wallet_transactions WHERE order_id = ? OR transaction_id = ? LIMIT 1", (val, val))
                    row = c.fetchone()
                    if row:
                        diag["classification"] = "description_match"
                        diag["confidence"] = "medium"
                        diag["best_guess_item_id"] = row[0]
                        diag["best_guess_item_name"] = row[1]
                        diag["best_guess_order_id"] = row[2]
                        diag["best_match_rule"] = "description_id"
                        break

        # C) Timing Match
        if diag["classification"] == "orphan" and nearby:
            best = nearby[0]
            
            if e['ref_type'] == 'transaction_tax':
                # Heurística: Venta en el mismo segundo
                if best['is_buy'] == 0 and abs(best['seconds_delta']) == 0:
                    diag["classification"] = "timing_exact_sale_cluster"
                    diag["confidence"] = "high"
                    diag["best_match_rule"] = "exact_timestamp_sale"
                else:
                    diag["classification"] = "timing_nearest_transaction"
                    diag["confidence"] = "medium" if abs(best['seconds_delta']) < 5 else "low"
                    diag["best_match_rule"] = "nearest_neighbor"
                
                diag["best_guess_item_id"] = best['item_id']
                diag["best_guess_item_name"] = best['item_name']
                diag["best_guess_order_id"] = best['order_id']
                
            elif e['ref_type'] == 'brokers_fee':
                if len(nearby) == 1:
                    diag["classification"] = "broker_fee_nearest_transaction"
                    diag["confidence"] = "medium"
                    diag["best_match_rule"] = "sole_nearby_transaction"
                elif abs(best['seconds_delta']) < 10 and abs(nearby[1]['seconds_delta']) > 30:
                    diag["classification"] = "broker_fee_nearest_transaction"
                    diag["confidence"] = "medium"
                    diag["best_match_rule"] = "dominant_nearby_transaction"
                else:
                    diag["classification"] = "broker_fee_ambiguous_cluster"
                    diag["confidence"] = "low"
                    diag["best_match_rule"] = "ambiguous_timing"
                
                diag["best_guess_item_id"] = best['item_id']
                diag["best_guess_item_name"] = best['item_name']
                diag["best_guess_order_id"] = best['order_id']

        if diag["classification"] == "orphan":
            summary["orphan_entries"] += 1
            
        diagnosed_entries.append(diag)
        
    return {
        "summary": summary,
        "entries": diagnosed_entries
    }

def format_fee_diagnostics_report(diagnostics: dict) -> str:
    """Produce un reporte legible del diagnóstico de fees."""
    s = diagnostics["summary"]
    
    report = []
    report.append("══════════════════════════════════════════════════════════════")
    report.append(" [WALLET FEE DIAGNOSTICS] ")
    report.append("══════════════════════════════════════════════════════════════")
    report.append(f"Journal Fee Entries:      {s['journal_fee_entries']}")
    report.append(f"Broker Fee Entries:       {s['broker_fee_entries']}")
    report.append(f"Transaction Tax Entries:  {s['transaction_tax_entries']}")
    report.append(f"Market Trans. Entries:    {s['market_transaction_entries']}")
    report.append(f"Entries With Context ID:  {s['entries_with_context_id']}")
    report.append(f"Entries Near Trans:       {s['entries_with_nearby_transactions']}")
    report.append(f"Orphan Entries:           {s['orphan_entries']}")
    
    if s['journal_fee_entries'] > 0 and s['entries_with_context_id'] == 0:
        report.append("\n[!] WARNING: CONTEXT_ID UNAVAILABLE")
        report.append("ESI is not providing exact link IDs for this character.")
        report.append("Allocation relies on timing clusters and heuristics.")

    report.append("\nClassification Stats:")
    counts = {}
    for e in diagnostics["entries"]:
        c = e["classification"]
        counts[c] = counts.get(c, 0) + 1
    for c, count in sorted(counts.items()):
        report.append(f" - {c}: {count}")
    
    report.append("\n[DIAGNOSTIC NOTES]")
    report.append("- Sales often cluster: market_transaction + tax + SELL row at same time.")
    report.append("- Preferred: exact SELL timestamp (timing_exact_sale_cluster).")
    report.append("- Proportional fallback is used for orphan/ambiguous entries in the engine.")

    report.append("\n" + "═" * 60)
    report.append(" [RECENT FEE ENTRIES] ")
    report.append("═" * 60)
    
    from utils.formatters import format_isk
    
    for i, e in enumerate(diagnostics["entries"][:50]):
        report.append(f"\n#{i+1} ID: {e['journal_id']} | {e['date']}")
        report.append(f"Type: {e['ref_type']} | Amount: {format_isk(e['amount'], True)}")
        
        ctx = f"{e['context_id_type'] or 'None'}: {e['context_id'] or 'None'}"
        report.append(f"Context: {ctx}")
        
        if e['description']: report.append(f"Desc: {e['description']}")
        if e['reason']: report.append(f"Reason: {e['reason']}")
        
        report.append(f"Classification: {e['classification'].upper()} ({e['confidence'].upper()})")
        report.append(f"Match Rule: {e['best_match_rule']}")
        
        if e['best_guess_item_name']:
            report.append(f"Best Guess: {e['best_guess_item_name']} (ID:{e['best_guess_item_id']})")
        
        if e['nearby_transactions']:
            report.append(f"Nearby Transactions ({len(e['nearby_transactions'])}):")
            for t in e['nearby_transactions'][:3]:
                side = "BUY" if t['is_buy'] else "SELL"
                report.append(f"  - {t['date']} | {side} | {t['item_name']} | dt:{t['seconds_delta']}s | score:{t.get('score',0):.1f}")
        
        report.append("-" * 40)
        
    return "\n".join(report)
