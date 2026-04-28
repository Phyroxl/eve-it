from __future__ import annotations
from typing import Dict, List
from core.contracts_models import (
    ContractItem, ContractArbitrageResult, ScoreBreakdown, ContractsFilterConfig
)


def build_price_index(market_orders: List[dict]) -> Dict[int, dict]:
    """
    Retorna {type_id: {'best_sell': float, 'best_buy': float}}.
    best_sell = min price de sell orders (is_buy_order=False)
    best_buy  = max price de buy orders  (is_buy_order=True)
    """
    index: Dict[int, dict] = {}
    for order in market_orders:
        tid = order.get('type_id')
        price = order.get('price', 0.0)
        is_buy = order.get('is_buy_order', False)
        if tid not in index:
            index[tid] = {'best_sell': None, 'best_buy': None}
        if is_buy:
            if index[tid]['best_buy'] is None or price > index[tid]['best_buy']:
                index[tid]['best_buy'] = price
        else:
            if index[tid]['best_sell'] is None or price < index[tid]['best_sell']:
                index[tid]['best_sell'] = price
    for tid in index:
        if index[tid]['best_sell'] is None:
            index[tid]['best_sell'] = 0.0
        if index[tid]['best_buy'] is None:
            index[tid]['best_buy'] = 0.0
    return index


def analyze_contract_items(
    items_raw: List[dict],
    price_index: Dict[int, dict],
    name_map: Dict[int, str],
    config: ContractsFilterConfig
) -> List[ContractItem]:
    """
    Convierte items ESI en ContractItem.
    Items sin precio en Jita → jita_sell_price=0.0.
    pct_of_total se calcula después en calculate_contract_metrics().
    """
    items = []
    for raw in items_raw:
        type_id = raw.get('type_id', 0)
        quantity = raw.get('quantity', 1)
        is_included = raw.get('is_included', True)
        prices = price_index.get(type_id, {'best_sell': 0.0, 'best_buy': 0.0})
        sell_price = prices['best_sell']
        buy_price = prices['best_buy']
        items.append(ContractItem(
            type_id=type_id,
            item_name=name_map.get(type_id, f"Unknown [{type_id}]"),
            quantity=quantity,
            is_included=is_included,
            jita_sell_price=sell_price,
            jita_buy_price=buy_price,
            line_sell_value=quantity * sell_price,
            line_buy_value=quantity * buy_price,
            pct_of_total=0.0,
            is_blueprint="Blueprint" in name_map.get(type_id, ""),
            is_copy=raw.get('is_blueprint_copy', False)
        ))
    return items


def calculate_contract_metrics(
    contract_raw: dict,
    items: List[ContractItem],
    config: ContractsFilterConfig
) -> ContractArbitrageResult:
    """
    Construye ContractArbitrageResult.
    Solo items con is_included=True cuentan para el valor.
    Fees se aplican sobre la reventa:
        fees = jita_sell_value * (broker_fee_pct + sales_tax_pct) / 100
        net_profit = jita_sell_value - fees - contract_cost
    """
    included = [i for i in items if i.is_included]
    jita_sell_value = sum(i.line_sell_value for i in included)
    jita_buy_value = sum(i.line_buy_value for i in included)

    if jita_sell_value > 0:
        for item in included:
            item.pct_of_total = (item.line_sell_value / jita_sell_value) * 100.0

    value_concentration = 0.0
    if included and jita_sell_value > 0:
        value_concentration = max(i.line_sell_value for i in included) / jita_sell_value

    contract_cost = contract_raw.get('price', 0.0)
    gross_profit = jita_sell_value - contract_cost
    fees = jita_sell_value * (config.broker_fee_pct + config.sales_tax_pct) / 100.0
    net_profit = jita_sell_value - fees - contract_cost
    roi_pct = (net_profit / contract_cost * 100.0) if contract_cost > 0 else 0.0

    unresolved = [i for i in included if i.jita_sell_price == 0.0]
    type_ids = list({i.type_id for i in included})
    total_units = sum(i.quantity for i in included)

    return ContractArbitrageResult(
        contract_id=contract_raw.get('contract_id', 0),
        region_id=contract_raw.get('region_id', config.region_id),
        issuer_id=contract_raw.get('issuer_id', 0),
        contract_cost=contract_cost,
        date_expired=contract_raw.get('date_expired', ''),
        location_id=contract_raw.get('start_location_id', 0),
        item_type_count=len(type_ids),
        total_units=total_units,
        items=items,
        jita_sell_value=jita_sell_value,
        jita_buy_value=jita_buy_value,
        gross_profit=gross_profit,
        net_profit=net_profit,
        roi_pct=roi_pct,
        value_concentration=value_concentration,
        has_unresolved_items=len(unresolved) > 0,
        unresolved_count=len(unresolved),
        has_blueprints=any(i.is_blueprint or i.is_copy for i in items),
    )


def score_contract(c: ContractArbitrageResult) -> float:
    """
    Score 0-100:
        base = 0.45*roi_norm + 0.35*profit_norm + 0.20*simplicity
    Penalizaciones multiplicativas:
        net_profit <= 0            → 0.0
        roi_pct < 10%              → x0.70
        value_concentration > 0.80 → x0.75
        item_type_count > 30       → x0.80
        has_unresolved_items       → x0.85
    """
    if c.net_profit <= 0:
        return 0.0

    roi_norm = min(c.roi_pct / 100.0, 1.0)
    profit_norm = min(c.net_profit / 500_000_000.0, 1.0)
    simplicity = max(0.0, 1.0 - c.item_type_count / 20.0)
    base = 0.45 * roi_norm + 0.35 * profit_norm + 0.20 * simplicity

    penalties = []
    penalty = 1.0
    if c.roi_pct < 10.0:
        penalty *= 0.70
        penalties.append("ROI < 10%")
    if c.value_concentration > 0.80:
        penalty *= 0.75
        penalties.append("Concentración > 80%")
    if c.item_type_count > 30:
        penalty *= 0.80
        penalties.append("Complejidad alta")
    if c.has_unresolved_items:
        penalty *= 0.85
        penalties.append(f"{c.unresolved_count} items sin precio")

    final = round(base * penalty * 100.0, 1)
    c.score_breakdown = ScoreBreakdown(
        roi_component=round(roi_norm * 0.45 * 100, 2),
        profit_component=round(profit_norm * 0.35 * 100, 2),
        simplicity_component=round(simplicity * 0.20 * 100, 2),
        penalties_applied=penalties,
        final_score=final,
    )
    return final


def apply_contracts_filters(
    contracts: List[ContractArbitrageResult],
    config: ContractsFilterConfig
) -> List[ContractArbitrageResult]:
    """Filtra y devuelve top 1000 ordenados por score DESC."""
    result = [
        c for c in contracts
        if c.net_profit >= config.profit_min_isk
        and c.roi_pct >= config.roi_min_pct
        and c.item_type_count <= config.item_types_max
        and not (config.exclude_no_price and c.has_unresolved_items)
        and not (config.exclude_blueprints and c.has_blueprints)
    ]
    
    # Filtro por categoría (basado en el item de mayor valor)
    if config.category_filter != "all":
        from core.item_metadata import ItemMetadataHelper
        final_filtered = []
        for c in result:
            # Encontrar el item principal (mayor valor sell)
            main_item = None
            max_val = -1
            for it in c.items:
                if it.line_sell_value > max_val:
                    max_val = it.line_sell_value
                    main_item = it
            
            if main_item:
                item_cat = ItemMetadataHelper.resolve_category(main_item.item_name)
                if item_cat == config.category_filter:
                    final_filtered.append(c)
        result = final_filtered

    result.sort(key=lambda x: x.score, reverse=True)
    return result[:1000]
