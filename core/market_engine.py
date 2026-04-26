from typing import List, Dict, Any
from .market_models import MarketOpportunity, LiquidityMetrics, ScoreBreakdown, FilterConfig

def parse_opportunities(orders: List[Dict[str, Any]], history: Dict[int, List[Dict[str, Any]]], item_names: Dict[int, str] = None) -> List[MarketOpportunity]:
    if item_names is None:
        item_names = {}
        
    # Group orders by type_id
    grouped_orders = {}
    for order in orders:
        t_id = order['type_id']
        if t_id not in grouped_orders:
            grouped_orders[t_id] = {'buy': [], 'sell': []}
            
        if order['is_buy_order']:
            grouped_orders[t_id]['buy'].append(order)
        else:
            grouped_orders[t_id]['sell'].append(order)
            
    opportunities = []
    
    for t_id, type_orders in grouped_orders.items():
        buy_orders = type_orders['buy']
        sell_orders = type_orders['sell']
        
        # Best buy is highest buy order price
        best_buy = max([o['price'] for o in buy_orders]) if buy_orders else 0.0
        # Best sell is lowest sell order price
        best_sell = min([o['price'] for o in sell_orders]) if sell_orders else 0.0
        
        if best_buy > 0 and best_sell > 0:
            spread_pct = ((best_sell - best_buy) / best_buy) * 100
            # Broker fees (approx 3%) and sales tax (approx 8%) -> Total 11% average for basic
            # Net margin = (Sell - Buy - Fees) / Buy
            # Let's use simplified 8% total fee for station trading (max skills is ~3.6%, let's use a flat 5% total for conservative estimate)
            # Actually net profit per unit: best_sell * 0.95 - best_buy * 1.02? Let's just do best_sell * 0.92 - best_buy to be safe, or just simpler.
            profit_per_unit = (best_sell * 0.92) - best_buy
            margin_net_pct = (profit_per_unit / best_buy) * 100 if best_buy > 0 else 0
        else:
            spread_pct = 0.0
            profit_per_unit = 0.0
            margin_net_pct = 0.0

        hist = history.get(t_id, [])
        if hist:
            # Sort history by date descending
            hist = sorted(hist, key=lambda x: x['date'], reverse=True)
            recent_5d = hist[:5]
            vol_5d = sum(h.get('volume', 0) for h in recent_5d)
            history_days = len(hist)
        else:
            vol_5d = 0
            history_days = 0
            
        profit_day_est = profit_per_unit * (vol_5d / 5.0) if vol_5d > 0 else 0.0
        
        # Risk assessment simplified
        risk_level = "High"
        if margin_net_pct > 10 and vol_5d > 100:
            risk_level = "Low"
        elif margin_net_pct > 5 and vol_5d > 20:
            risk_level = "Medium"

        liq = LiquidityMetrics(
            volume_5d=vol_5d,
            history_days=history_days,
            buy_orders_count=len(buy_orders),
            sell_orders_count=len(sell_orders)
        )
        
        opp = MarketOpportunity(
            type_id=t_id,
            item_name=item_names.get(t_id, f"Type {t_id}"),
            best_buy_price=best_buy,
            best_sell_price=best_sell,
            margin_net_pct=margin_net_pct,
            profit_per_unit=profit_per_unit,
            profit_day_est=profit_day_est,
            spread_pct=spread_pct,
            risk_level=risk_level,
            liquidity=liq
        )
        opportunities.append(opp)
        
    return opportunities

def apply_filters(opportunities: List[MarketOpportunity], config: FilterConfig) -> List[MarketOpportunity]:
    filtered = []
    for opp in opportunities:
        # FILTROS DUROS (eliminan antes de scoring)
        if opp.best_buy_price == 0:
            continue
        if opp.liquidity.volume_5d < config.vol_min_day:
            continue
        if opp.spread_pct > config.spread_max_pct:
            continue
        if opp.liquidity.history_days < 3:
            continue
            
        # Additional UI filters
        if opp.best_buy_price > config.capital_max:
            continue
        if opp.margin_net_pct < config.margin_min_pct:
            continue
            
        filtered.append(opp)
    return filtered

def score_opportunity(opp: MarketOpportunity, config: FilterConfig) -> ScoreBreakdown:
    # Normalizations (heuristic based for Jita)
    liq_norm = min(opp.liquidity.volume_5d / 5000.0, 1.0)
    roi_norm = min(opp.margin_net_pct / 50.0, 1.0)
    # 500M ISK/day max cap for normalization
    profit_day_norm = min(max(opp.profit_day_est, 0) / 500_000_000.0, 1.0)
    
    # score_base = liq_norm*0.50 + roi_norm*0.30 + profit_day_norm*0.20
    base_score = (liq_norm * 0.50) + (roi_norm * 0.30) + (profit_day_norm * 0.20)
    
    penalties = []
    # - vol_5d < 10 -> x0.60
    if opp.liquidity.volume_5d < 10:
        penalties.append(0.60)
    # - spread > 25% -> x0.70
    if opp.spread_pct > 25.0:
        penalties.append(0.70)
    # - history_days < 5 -> x0.50
    if opp.liquidity.history_days < 5:
        penalties.append(0.50)
    # - buy_orders_count <= 2 -> x0.75
    if opp.liquidity.buy_orders_count <= 2:
        penalties.append(0.75)
        
    final_score = base_score
    for p in penalties:
        final_score *= p
        
    final_score *= 100 # scale 0-100
    
    return ScoreBreakdown(
        base_score=base_score,
        liquidity_norm=liq_norm,
        roi_norm=roi_norm,
        profit_day_norm=profit_day_norm,
        penalties=penalties,
        final_score=final_score
    )
