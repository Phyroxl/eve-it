from typing import List, Dict, Any
from .market_models import MarketOpportunity, LiquidityMetrics, ScoreBreakdown, FilterConfig, InventoryItem, InventoryAnalysis
from .cost_basis_service import CostBasisService
from .tax_service import TaxService

def parse_opportunities(orders: List[Dict[str, Any]], history: Dict[int, List[Dict[str, Any]]], item_names: Dict[int, str] = None, config: FilterConfig = None) -> List[MarketOpportunity]:
    if config is None: config = FilterConfig()
    if item_names is None: item_names = {}
    grouped_orders = {}
    for order in orders:
        t_id = order['type_id']
        if t_id not in grouped_orders: grouped_orders[t_id] = {'buy': [], 'sell': []}
        if order.get('is_buy_order', False): grouped_orders[t_id]['buy'].append(order)
        else: grouped_orders[t_id]['sell'].append(order)
    opportunities = []
    for t_id, type_orders in grouped_orders.items():
        buy_orders = type_orders['buy']
        sell_orders = type_orders['sell']
        best_buy = max([o['price'] for o in buy_orders]) if buy_orders else 0.0
        best_sell = min([o['price'] for o in sell_orders]) if sell_orders else 0.0
        if best_buy > 0 and best_sell > 0:
            spread_pct = ((best_sell - best_buy) / best_buy) * 100
            b_fee = config.broker_fee_pct / 100.0
            s_tax = config.sales_tax_pct / 100.0
            profit_per_unit = best_sell * (1.0 - s_tax - b_fee) - best_buy * (1.0 + b_fee)
            margin_net_pct = (profit_per_unit / best_buy) * 100 if best_buy > 0 else 0
        else:
            spread_pct = 0.0; profit_per_unit = 0.0; margin_net_pct = 0.0
        hist = history.get(t_id, [])
        if hist:
            hist = sorted(hist, key=lambda x: x['date'], reverse=True)
            recent_5d = hist[:5]
            vol_5d = sum(h.get('volume', 0) for h in recent_5d)
            history_days = len(hist)
        else:
            vol_5d = 0; history_days = 0
        profit_day_est = profit_per_unit * (vol_5d / 5.0) if vol_5d > 0 else 0.0
        risk_level = "High"
        if margin_net_pct > 10 and vol_5d > 100: risk_level = "Low"
        elif margin_net_pct > 5 and vol_5d > 20: risk_level = "Medium"
        tags = []
        if vol_5d > 500: tags.append("Rápida")
        elif vol_5d < 50: tags.append("Lenta")
        if margin_net_pct > 20: tags.append("Buen margen")
        if spread_pct > 50 or margin_net_pct < 2: tags.append("Cuidado")
        if best_buy > 100_000_000: tags.append("Capital alto")
        if risk_level == "Low" and margin_net_pct > 15: tags.append("Sólida")
        liq = LiquidityMetrics(volume_5d=vol_5d, history_days=history_days, buy_orders_count=len(buy_orders), sell_orders_count=len(sell_orders))
        daily_vol = vol_5d / 5.0
        rec_qty = int(daily_vol * 0.2)
        if rec_qty < 1 and vol_5d > 0: rec_qty = 1
        if best_buy > 0:
            cap_limit = int(config.capital_max / best_buy)
            rec_qty = min(rec_qty, cap_limit)
        rec_cost = rec_qty * best_buy
        opp = MarketOpportunity(type_id=t_id, item_name=item_names.get(t_id, f"Type {t_id}"), best_buy_price=best_buy, best_sell_price=best_sell, margin_net_pct=margin_net_pct, profit_per_unit=profit_per_unit, profit_day_est=profit_day_est, spread_pct=spread_pct, risk_level=risk_level, tags=tags, liquidity=liq, recommended_qty=rec_qty, recommended_cost=rec_cost)
        opportunities.append(opp)
    return opportunities

def apply_filters(opportunities: List[MarketOpportunity], config: FilterConfig) -> List[MarketOpportunity]:
    filtered = []; risk_map = {"Low": 1, "Medium": 2, "High": 3}
    for opp in opportunities:
        if opp.best_buy_price == 0: continue
        if config.exclude_plex and "plex" in opp.item_name.lower(): continue
        if opp.best_buy_price > config.capital_max: continue
        if opp.liquidity.volume_5d < config.vol_min_day: continue
        if opp.margin_net_pct < config.margin_min_pct: continue
        if opp.spread_pct > config.spread_max_pct: continue
        current_risk = risk_map.get(opp.risk_level, 3)
        if current_risk > config.risk_max: continue
        if opp.liquidity.buy_orders_count < config.buy_orders_min: continue
        if opp.liquidity.sell_orders_count < config.sell_orders_min: continue
        if opp.liquidity.history_days < config.history_days_min: continue
        if opp.profit_day_est < config.profit_day_min: continue
        filtered.append(opp)
    return filtered

def score_opportunity(opp: MarketOpportunity, config: FilterConfig) -> ScoreBreakdown:
    liq_norm = min(opp.liquidity.volume_5d / 5000.0, 1.0)
    roi_norm = min(opp.margin_net_pct / 50.0, 1.0)
    profit_day_norm = min(max(opp.profit_day_est, 0) / 500_000_000.0, 1.0)
    base_score = (liq_norm * 0.50) + (roi_norm * 0.30) + (profit_day_norm * 0.20)
    penalties = []
    if opp.liquidity.volume_5d < 10: penalties.append(0.60)
    if opp.spread_pct > 25.0: penalties.append(0.70)
    if opp.liquidity.history_days < 5: penalties.append(0.50)
    if opp.liquidity.buy_orders_count <= 2: penalties.append(0.75)
    final_score = base_score
    for p in penalties: final_score *= p
    final_score *= 100
    return ScoreBreakdown(base_score=base_score, liquidity_norm=liq_norm, roi_norm=roi_norm, profit_day_norm=profit_day_norm, penalties=penalties, final_score=final_score)

def analyze_character_orders(esi_orders: List[Dict[str, Any]], market_orders: List[Dict[str, Any]], item_names: Dict[int, str] = None, config: FilterConfig = None, char_id: int = 0, token: str = ""):
    from .market_models import OpenOrder, OpenOrderAnalysis
    if config is None: config = FilterConfig()
    if item_names is None: item_names = {}
    
    tax_service = TaxService.instance()
    tax_info = tax_service.get_taxes(char_id)
    s_tax = tax_info.sales_tax_pct / 100.0
        
    grouped_market = {}
    for o in market_orders:
        t_id = o['type_id']
        if t_id not in grouped_market: grouped_market[t_id] = {'buy': [], 'sell': []}
        if o.get('is_buy_order', False): grouped_market[t_id]['buy'].append(o)
        else: grouped_market[t_id]['sell'].append(o)
            
    best_prices = {}
    for t_id, data in grouped_market.items():
        best_buy = max([o['price'] for o in data['buy']]) if data['buy'] else 0.0
        best_sell = min([o['price'] for o in data['sell']]) if data['sell'] else 0.0
        best_prices[t_id] = (best_buy, best_sell)

    parsed_orders = []
    for eo in esi_orders:
        t_id = eo['type_id']; price = eo['price']; is_buy = eo.get('is_buy_order', False)
        loc_id = eo.get('location_id', 0)
        
        # Obtener Broker Fee específico para esta ubicación
        b_fee_val, b_fee_source = tax_service.get_effective_broker_fee(char_id, loc_id, token)
        b_fee = b_fee_val / 100.0
        
        bb, bs = best_prices.get(t_id, (0.0, 0.0))
        cost_basis = CostBasisService.instance().get_cost_basis(t_id)
        avg_cost = cost_basis.average_buy_price if cost_basis else 0.0
        spread_pct = ((bs - bb) / bb) * 100 if bb > 0 and bs > 0 else 0.0
        competitive = False; difference = 0.0; state = "Desconocido"
        gross_profit = 0.0; net_profit = 0.0; margin_pct = 0.0
        
        if is_buy:
            difference = bb - price
            competitive = difference <= 0
            if bs > 0:
                net_profit = bs * (1.0 - s_tax - b_fee) - price * (1.0 + b_fee)
                margin_pct = (net_profit / price) * 100 if price > 0 else 0
            state = "Competitiva" if competitive else "Superada"
            if margin_pct <= 0: state = "No Rentable"
        else:
            difference = price - bs
            competitive = difference <= 0
            if avg_cost > 0:
                base_cost = avg_cost
                net_profit = price * (1.0 - s_tax - b_fee) - base_cost
                margin_pct = (net_profit / base_cost) * 100 if base_cost > 0 else 0
                gross_profit = price - base_cost
                state = "Rentable" if net_profit > 0 else "Pérdida"
                if not competitive: state = "Superada con beneficio" if net_profit > 0 else "Superada en pérdida"
            else:
                state = "Sin coste real"
            if not competitive and price > bs * 1.05: state = "Fuera de Mercado"

        vol_remain = eo.get('volume_remain', 0)
        net_profit_total = net_profit * vol_remain
        analysis = OpenOrderAnalysis(is_buy=is_buy, state=state, gross_profit_per_unit=gross_profit, net_profit_per_unit=net_profit, net_profit_total=net_profit_total, margin_pct=margin_pct, best_buy=bb, best_sell=bs, spread_pct=spread_pct, competitive=competitive, difference_to_best=difference)
        
        o = OpenOrder(order_id=eo['order_id'], type_id=t_id, item_name=item_names.get(t_id, f"Type {t_id}"), is_buy_order=is_buy, price=price, volume_total=eo.get('volume_total', 0), volume_remain=vol_remain, issued=eo.get('issued', ''), location_id=loc_id, range=eo.get('range', ''), analysis=analysis)
        o._fee_source = b_fee_source
        o._b_fee_pct = b_fee_val
        parsed_orders.append(o)
    return parsed_orders

def analyze_inventory(assets: List[Dict[str, Any]], market_orders: List[Dict[str, Any]], item_names: Dict[int, str] = None, config: FilterConfig = None, char_id: int = 0, token: str = ""):
    if config is None: config = FilterConfig()
    if item_names is None: item_names = {}
    tax_service = TaxService.instance()
    tax_info = tax_service.get_taxes(char_id)
    s_tax = tax_info.sales_tax_pct / 100.0
    
    grouped_market = {}
    for o in market_orders:
        t_id = o['type_id']
        if t_id not in grouped_market: grouped_market[t_id] = {'buy': [], 'sell': []}
        if o.get('is_buy_order', False): grouped_market[t_id]['buy'].append(o)
        else: grouped_market[t_id]['sell'].append(o)
    
    best_prices = {}
    for t_id, data in grouped_market.items():
        best_buy = max([o['price'] for o in data['buy']]) if data['buy'] else 0.0
        best_sell = min([o['price'] for o in data['sell']]) if data['sell'] else 0.0
        best_prices[t_id] = (best_buy, best_sell)
    
    results = []
    grouped_assets = {}
    for a in assets:
        t_id = a['type_id']
        if t_id not in grouped_assets: grouped_assets[t_id] = {'qty': 0, 'location': a.get('location_id', 0)}
        grouped_assets[t_id]['qty'] += a['quantity']
        
    for t_id, info in grouped_assets.items():
        bb, bs = best_prices.get(t_id, (0.0, 0.0)); qty = info['qty']
        loc_id = info['location']
        
        # Para inventario, usamos el fee de la ubicación del asset (o fallback si no hay)
        b_fee_val, _ = tax_service.get_effective_broker_fee(char_id, loc_id, token)
        b_fee = b_fee_val / 100.0
        
        cost_basis = CostBasisService.instance().get_cost_basis(t_id)
        avg_buy = cost_basis.average_buy_price if cost_basis else 0.0
        
        spread_pct = ((bs - bb) / bb) * 100 if bb > 0 and bs > 0 else 0.0
        est_net_sell = bs * (1.0 - s_tax - b_fee) if bs > 0 else 0.0
        est_total_value = est_net_sell * qty
        
        # Cálculo de Profit Real
        net_profit_unit = est_net_sell - avg_buy if avg_buy > 0 else 0.0
        net_profit_total = net_profit_unit * qty
        
        # Recomendación profesional basada en Profit
        recommendation = "MANTENER"
        reason = "Mercado estable"
        
        if bs == 0:
            recommendation = "REVISAR"
            reason = "Sin liquidez en Jita"
        elif spread_pct > 35:
            recommendation = "MANTENER"
            reason = "Spread excesivo (>35%)"
        elif avg_buy == 0:
            recommendation = "REVISAR"
            reason = "Falta registro de coste (WAC)"
        elif net_profit_unit < 0:
            recommendation = "MANTENER"
            reason = f"Venta con pérdida ({format_isk(abs(net_profit_unit))} / u)"
        elif net_profit_unit > 0:
            margin_on_cost = (net_profit_unit / avg_buy) * 100
            if margin_on_cost > 10:
                recommendation = "VENDER"
                reason = f"Profit sólido (+{margin_on_cost:.1f}% ROI)"
            else:
                recommendation = "MANTENER"
                reason = "Margen de beneficio bajo"
        else:
            recommendation = "MANTENER"
            reason = "Mejor esperar mejores precios"

        analysis = InventoryAnalysis(best_buy=bb, best_sell=bs, spread_pct=spread_pct, est_net_sell_unit=est_net_sell, est_total_value=est_total_value, recommendation=recommendation, reason=reason)
        item = InventoryItem(type_id=t_id, item_name=item_names.get(t_id, f"Type {t_id}"), quantity=qty, location_id=loc_id, analysis=analysis)
        item._avg_buy = avg_buy 
        item._net_profit_total = net_profit_total
        results.append(item)
    return results
