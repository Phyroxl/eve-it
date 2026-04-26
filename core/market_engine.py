from typing import List, Dict, Any
from .market_models import MarketOpportunity, LiquidityMetrics, ScoreBreakdown, FilterConfig

def parse_opportunities(orders: List[Dict[str, Any]], history: Dict[int, List[Dict[str, Any]]], item_names: Dict[int, str] = None, config: FilterConfig = None) -> List[MarketOpportunity]:
    if config is None:
        config = FilterConfig()
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
            
            # Station trading fee calculation:
            # When buying: you pay broker fee on best_buy
            # When selling: you pay broker fee + sales tax on best_sell
            # Cost = best_buy + (best_buy * broker_fee) + (best_sell * broker_fee) + (best_sell * sales_tax)
            # Or simply, Profit = best_sell * (1 - sales_tax - broker_fee) - best_buy * (1 + broker_fee)
            b_fee = config.broker_fee_pct / 100.0
            s_tax = config.sales_tax_pct / 100.0
            
            profit_per_unit = best_sell * (1.0 - s_tax - b_fee) - best_buy * (1.0 + b_fee)
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
            
        # Tags for quick read
        tags = []
        if vol_5d > 500: tags.append("Rápida")
        elif vol_5d < 50: tags.append("Lenta")
        
        if margin_net_pct > 20: tags.append("Buen margen")
        if spread_pct > 50 or margin_net_pct < 2: tags.append("Cuidado")
        
        if best_buy > 100_000_000: tags.append("Capital alto")
        if risk_level == "Low" and margin_net_pct > 15: tags.append("Sólida")

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
            tags=tags,
            liquidity=liq
        )
        opportunities.append(opp)
        
    return opportunities

def apply_filters(opportunities: List[MarketOpportunity], config: FilterConfig) -> List[MarketOpportunity]:
    filtered = []
    
    risk_map = {"Low": 1, "Medium": 2, "High": 3}
    
    for opp in opportunities:
        # 1. Filtros Básicos (ya existentes pero limpios)
        if opp.best_buy_price == 0: continue
        if config.exclude_plex and "plex" in opp.item_name.lower(): continue
        
        if opp.best_buy_price > config.capital_max: continue
        if opp.liquidity.volume_5d < config.vol_min_day: continue
        if opp.margin_net_pct < config.margin_min_pct: continue
        if opp.spread_pct > config.spread_max_pct: continue
        
        # 2. Filtros Avanzados (Fase 1)
        if opp.score_breakdown and opp.score_breakdown.final_score < config.score_min:
            continue
            
        current_risk = risk_map.get(opp.risk_level, 3)
        if current_risk > config.risk_max:
            continue
            
        if opp.liquidity.buy_orders_count < config.buy_orders_min: continue
        if opp.liquidity.sell_orders_count < config.sell_orders_min: continue
        if opp.liquidity.history_days < config.history_days_min: continue
        if opp.profit_day_est < config.profit_day_min: continue
            
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
