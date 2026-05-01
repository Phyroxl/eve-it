from __future__ import annotations
from typing import Dict, List
from core.contracts_models import (
    ContractItem, ContractArbitrageResult, ScoreBreakdown, ContractsFilterConfig
)

from core.contract_blueprint_utils import classify_blueprint_item, get_valuation_strategy

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
    config: ContractsFilterConfig,
    metadata_map: Optional[Dict[int, dict]] = None
) -> List[ContractItem]:
    """
    Convierte items ESI en ContractItem.
    Items sin precio en Jita → jita_sell_price=0.0.
    """
    items = []
    for raw in items_raw:
        type_id = raw.get('type_id', 0)
        quantity = raw.get('quantity', 1)
        is_included = raw.get('is_included', True)
        prices = price_index.get(type_id, {'best_sell': 0.0, 'best_buy': 0.0})
        sell_price = prices['best_sell']
        buy_price = prices['best_buy']
        
        item_name = name_map.get(type_id, f"Unknown [{type_id}]")
        meta = metadata_map.get(type_id, {}) if metadata_map else {}
        cat_id = meta.get('category_id')
        
        classification = classify_blueprint_item(raw, item_name, cat_id)
        strategy = get_valuation_strategy(classification)
        
        val_status = "ok"
        if strategy == "zero":
            val_status = "bpc_ignored"
        elif strategy == "uncertain":
            val_status = "uncertain_ignored"
            
        items.append(ContractItem(
            type_id=type_id,
            item_name=item_name,
            quantity=quantity,
            is_included=is_included,
            jita_sell_price=sell_price,
            jita_buy_price=buy_price,
            line_sell_value=quantity * sell_price,
            line_buy_value=quantity * buy_price,
            pct_of_total=0.0,
            is_blueprint=classification in ("bpo", "bpc", "unknown_blueprint"),
            is_copy=(classification == "bpc"),
            valuation_status=val_status
        ))
    return items


def calculate_contract_metrics(
    contract_raw: dict,
    items: List[ContractItem],
    config: ContractsFilterConfig
) -> ContractArbitrageResult:
    """
    Construye ContractArbitrageResult.
    Solo items con is_included=True y valuation_status='ok' cuentan para el valor.
    """
    included = [i for i in items if i.is_included]
    
    # Valuation logic: ignore BPCs and uncertain items
    jita_sell_value = 0.0
    jita_buy_value = 0.0
    has_ignored_items = False
    warning = None
    
    for i in included:
        if i.valuation_status == "ok":
            jita_sell_value += i.line_sell_value
            jita_buy_value += i.line_buy_value
        else:
            has_ignored_items = True
            
    if any(i.valuation_status == "bpc_ignored" for i in included):
        warning = "Contiene BPC: valoración automática desactivada para copias"
    elif any(i.valuation_status == "uncertain_ignored" for i in included):
        warning = "Blueprint no clasificado: valoración desactivada"

    if jita_sell_value > 0:
        for item in included:
            if item.valuation_status == "ok":
                item.pct_of_total = (item.line_sell_value / jita_sell_value) * 100.0
            else:
                item.pct_of_total = 0.0

    value_concentration = 0.0
    if included and jita_sell_value > 0:
        valid_items = [i for i in included if i.valuation_status == "ok"]
        if valid_items:
            value_concentration = max(i.line_sell_value for i in valid_items) / jita_sell_value

    contract_cost = contract_raw.get('price', 0.0)
    gross_profit = jita_sell_value - contract_cost
    fees = jita_sell_value * (config.broker_fee_pct + config.sales_tax_pct) / 100.0
    net_profit = jita_sell_value - fees - contract_cost
    roi_pct = (net_profit / contract_cost * 100.0) if contract_cost > 0 else 0.0

    unresolved = [i for i in included if i.jita_sell_price == 0.0 and i.valuation_status == "ok"]
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
        has_blueprints=any(i.is_blueprint for i in items),
        valuation_warning=warning
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
    config: ContractsFilterConfig,
    diagnostics: Optional[ScanDiagnostics] = None
) -> List[ContractArbitrageResult]:
    """Filtra y devuelve top 1000 ordenados por score DESC."""
    result = []
    
    if diagnostics:
        diagnostics.total_scanned += len(contracts)
        
    for c in contracts:
        if diagnostics:
            # Stats de items a nivel global de lo visto
            diagnostics.val_total_items_seen += len(c.items)
            priced_count = sum(1 for i in c.items if i.jita_sell_price > 0)
            diagnostics.val_items_priced += priced_count
            diagnostics.val_items_missing_price += (len(c.items) - priced_count)
            
            if priced_count == len(c.items) and len(c.items) > 0:
                diagnostics.val_all_priced += 1
            elif priced_count > 0:
                diagnostics.val_partial_pricing += 1
            else:
                diagnostics.val_no_priced += 1

        # --- FILTROS DE EXCLUSIÓN EXPLÍCITA (OCULTAN RESULTADOS) ---
        
        # 0. Sanity Checks
        if c.item_type_count == 0:
            c.filter_reason = "No contiene items"
            if diagnostics: diagnostics.excluded_by_no_items += 1
            continue
            
        # 1. Capital (Coste)
        if c.contract_cost < config.capital_min_isk or c.contract_cost > config.capital_max_isk:
            c.filter_reason = f"Capital fuera de rango ({c.contract_cost/1e6:.1f}M)"
            if diagnostics: diagnostics.excluded_by_low_profit += 1 # Reutilizamos counter por ahora
            continue

        # 2. Blueprints
        if config.exclude_blueprints and c.has_blueprints:
            c.filter_reason = "Contiene Blueprints"
            if diagnostics: diagnostics.excluded_by_blueprint += 1
            continue
            
        if config.exclude_bpcs:
            has_copy = any(i.is_copy for i in c.items)
            if has_copy:
                c.filter_reason = "Contiene Copias BPC"
                if diagnostics: diagnostics.excluded_by_bpc += 1
                continue
        
        # 3. Complexity
        if c.item_type_count > config.item_types_max:
            c.filter_reason = f"Items {c.item_type_count} > {config.item_types_max}"
            if diagnostics: diagnostics.excluded_by_complexity += 1
            continue
            
        # 4. Exclusión explícita por falta de precio
        if config.exclude_no_price and c.jita_sell_value <= 0:
            c.filter_reason = "Sin valoración (Excluido por filtro)"
            if diagnostics: diagnostics.excluded_by_no_price += 1
            continue

        # --- CRITERIOS DE RENTABILIDAD (NO OCULTAN SI LOS FILTROS SON 0) ---
        
        c.filter_reason = "Rentable"
        
        if c.jita_sell_value <= 0:
            # Desglose de por qué es Zero Value
            if not c.items:
                c.filter_reason = "Detalles no disponibles"
                if diagnostics: diagnostics.zv_item_details_missing += 1
            else:
                unpriced = sum(1 for i in c.items if i.jita_sell_price <= 0)
                if unpriced == len(c.items):
                    c.filter_reason = "Sin precio Jita"
                    if diagnostics: diagnostics.zv_all_items_missing_price += 1
                else:
                    c.filter_reason = "Valoración zero"
                    if diagnostics: diagnostics.zv_unknown += 1
            
            if diagnostics: diagnostics.excluded_by_zero_value += 1
            # Si el usuario NO marcó exclude_no_price, lo dejamos pasar aunque sea 0
            # Pero si min_profit > 0, entonces sí se ocultará en el siguiente paso

        # Profit & ROI: Solo ocultan si el usuario puso un umbral real (>0)
        if config.profit_min_isk > 0 and c.net_profit < config.profit_min_isk:
            c.filter_reason = f"Profit bajo ({c.net_profit/1e6:.1f}M)"
            if diagnostics: diagnostics.excluded_by_low_profit += 1
            continue

        if config.roi_min_pct > 0 and c.roi_pct < config.roi_min_pct:
            c.filter_reason = f"ROI bajo ({c.roi_pct:.1f}%)"
            if diagnostics: diagnostics.excluded_by_low_roi += 1
            continue

        # Si llegamos aquí, el contrato es visible
        if c.net_profit > 0 and c.jita_sell_value > 0:
            if diagnostics: diagnostics.profitable += 1
        
        result.append(c)

    # Filtro por categoría (basado en el item de mayor valor)
    cat_filter = str(config.category_filter).lower()
    if cat_filter not in ("all", "todas las categorías", "none", ""):
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
                # Normalización para comparación
                if str(item_cat).lower() == cat_filter:
                    final_filtered.append(c)
                else:
                    if diagnostics: diagnostics.excluded_by_category += 1
            else:
                if diagnostics: diagnostics.excluded_by_category += 1
        result = final_filtered

    result.sort(key=lambda x: x.score, reverse=True)
    return result[:1000]
