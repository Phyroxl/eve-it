from PySide6.QtCore import QThread, Signal
from core.esi_client import ESIClient
from core.market_engine import parse_opportunities, score_opportunity
from core.market_models import FilterConfig
import time

class MarketRefreshWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(list)
    error = Signal(str)

    # Legacy signals for compatibility if needed, but we'll update views
    progress_changed = Signal(int, str)
    data_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, region_id=10000002, config=None):
        super().__init__()
        self.region_id = region_id
        self.client = ESIClient()
        self.config = config if config else FilterConfig()
        self.is_running = True
        self.last_results = []

    def stop(self):
        self.is_running = False
        
    def run(self):
        try:
            self.emit_progress(5, "Fetching market orders...")
            orders = self.client.market_orders(self.region_id)
            if not self.is_running: return
            if not orders:
                self.emit_error("Failed to fetch market orders.")
                return

            self.emit_progress(30, f"Fetched {len(orders)} orders. Finding candidates...")
            
            # ... (rest of filtering logic)
            temp_grouped = {}
            for o in orders:
                t = o['type_id']
                if t not in temp_grouped:
                    temp_grouped[t] = {'buy': [], 'sell': []}
                if o['is_buy_order']:
                    temp_grouped[t]['buy'].append(o)
                else:
                    temp_grouped[t]['sell'].append(o)
            
            scored_candidates = []
            for t, group in temp_grouped.items():
                if len(group['buy']) >= 2 and len(group['sell']) >= 2:
                    best_buy = max(o['price'] for o in group['buy'])
                    best_sell = min(o['price'] for o in group['sell'])
                    
                    if best_buy > 0 and best_buy <= self.config.capital_max:
                        spread = ((best_sell - best_buy) / best_buy) * 100
                        if spread <= self.config.spread_max_pct:
                            b_fee = self.config.broker_fee_pct / 100.0
                            s_tax = self.config.sales_tax_pct / 100.0
                            profit = best_sell * (1.0 - s_tax - b_fee) - best_buy * (1.0 + b_fee)
                            margin_net = (profit / best_buy) * 100 if best_buy > 0 else 0
                            
                            if margin_net >= self.config.margin_min_pct:
                                scored_candidates.append({
                                    'type_id': t,
                                    'margin': margin_net,
                                    'profit': profit,
                                    'orders_count': len(group['buy']) + len(group['sell'])
                                })
                            
            if not self.is_running: return
            scored_candidates.sort(key=lambda x: x['margin'] * min(x['orders_count'], 50), reverse=True)
            
            # For Advanced mode, we might want more than 150, but let's keep it 150 for now for speed
            candidates = [c['type_id'] for c in scored_candidates[:150]]
            
            if self.config.exclude_plex and 44992 in candidates:
                candidates.remove(44992)
                
            total_candidates = len(candidates)
            self.emit_progress(40, f"Fetching history for {total_candidates} items...")
            
            history_dict = {}
            for i, cid in enumerate(candidates):
                if not self.is_running: return
                hist = self.client.market_history(self.region_id, cid)
                if hist:
                    history_dict[cid] = hist
                if i % 10 == 0:
                    pct = 40 + int((i / max(total_candidates, 1)) * 40)
                    self.emit_progress(pct, f"History: {i}/{total_candidates}")
            
            self.emit_progress(85, "Fetching item names...")
            names_dict = {}
            chunk_size = 500
            for i in range(0, len(candidates), chunk_size):
                chunk = candidates[i:i+chunk_size]
                names_data = self.client.universe_names(chunk)
                if names_data:
                    for n in names_data:
                        names_dict[n['id']] = n['name']
            
            self.emit_progress(90, "Parsing opportunities...")
            # Note: names_dict only has names for candidates
            opps = parse_opportunities(orders, history_dict, names_dict, self.config)
            
            # FILTRAR: Solo quedarnos con los que realmente procesamos (candidatos)
            # y que pasan los filtros finales del motor.
            final_opps = [o for o in opps if o.type_id in candidates]
            from core.market_engine import apply_filters
            final_opps = apply_filters(final_opps, self.config)
            
            self.emit_progress(95, "Scoring...")
            for opp in final_opps:
                opp.score_breakdown = score_opportunity(opp, self.config)
                
            self.last_results = final_opps
            self.emit_progress(100, "Done")
            self.finished.emit(final_opps)
            self.data_ready.emit(final_opps)
            
        except Exception as e:
            self.emit_error(str(e))

    def emit_progress(self, pct, text):
        self.progress.emit(pct)
        self.status.emit(text)
        self.progress_changed.emit(pct, text)

    def emit_error(self, msg):
        self.error.emit(msg)
        self.error_occurred.emit(msg)
