import logging
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from core.market_models import FilterConfig

logger = logging.getLogger('eve.market.selector')

@dataclass
class CandidateStats:
    type_id: int
    best_buy: float
    best_sell: float
    spread_pct: float
    profit: float
    margin_pct: float
    buy_orders: int
    sell_orders: int
    score: float

def build_economic_candidates(grouped_orders: Dict[int, Dict[str, List[Dict]]], config: FilterConfig) -> List[CandidateStats]:
    """
    Convierte órdenes agrupadas en objetos CandidateStats con cálculos básicos.
    """
    candidates = []
    broker = config.broker_fee_pct / 100.0
    tax = config.sales_tax_pct / 100.0

    for tid, data in grouped_orders.items():
        buys = data.get('buy', [])
        sells = data.get('sell', [])

        if not buys or not sells:
            continue

        # Mejores precios (asumiendo que las órdenes ya vienen ordenadas por el cliente ESI o el worker)
        # buy: mayor precio primero. sell: menor precio primero.
        best_buy = buys[0]['price']
        best_sell = sells[0]['price']

        if best_buy <= 0:
            continue

        # Spread
        spread_abs = best_sell - best_buy
        spread_pct = (spread_abs / best_buy) * 100.0 if best_buy > 0 else 10000.0

        # Beneficio estimado (Simple: 1 unidad)
        # profit = best_sell * (1 - tax - broker) - best_buy * (1 + broker)
        # Nota: Usamos la misma lógica que market_engine para consistencia
        profit = best_sell * (1.0 - tax - broker) - best_buy * (1.0 + broker)
        margin = (profit / best_buy) * 100.0 if best_buy > 0 else -100.0

        # Puntuación heurística rápida (Margen * Log(Órdenes))
        # Esto prioriza items con margen pero castiga los que tienen spread absurdo si aplicamos pre-filtro
        orders_weight = min(len(buys) + len(sells), 100) / 10.0
        score = max(0, margin) * orders_weight

        candidates.append(CandidateStats(
            type_id=tid,
            best_buy=best_buy,
            best_sell=best_sell,
            spread_pct=spread_pct,
            profit=profit,
            margin_pct=margin,
            buy_orders=len(buys),
            sell_orders=len(sells),
            score=score
        ))
    
    return candidates

def prefilter_candidates(candidates: List[CandidateStats], config: FilterConfig) -> Tuple[List[CandidateStats], Dict[str, int]]:
    """
    Filtra candidatos basándose en criterios de saneamiento (capital, spread, profit, PLEX).
    Devuelve la lista filtrada y un diccionario de estadísticas de eliminación.
    """
    removed = {
        "capital": 0,
        "spread": 0,
        "margin": 0,
        "profit": 0,
        "plex": 0
    }
    
    filtered = []
    
    # IDs conocidos de items que no queremos que dominen el top (PLEX)
    EXCLUDED_IDS = {44992} # PLEX
    
    for c in candidates:
        # 1. PLEX / ID filter
        if config.exclude_plex and c.type_id in EXCLUDED_IDS:
            removed["plex"] += 1
            continue
            
        # 2. Capital
        if c.best_buy > config.capital_max:
            removed["capital"] += 1
            continue
            
        # 3. Spread
        if c.spread_pct > config.spread_max_pct:
            removed["spread"] += 1
            continue
            
        # 4. Margin / Profit
        if c.margin_pct < config.margin_min_pct:
            removed["margin"] += 1
            continue
            
        if config.margin_min_pct >= 0 and c.profit <= 0:
            removed["profit"] += 1
            continue
            
        # 5. Sanity: best_sell debe ser mayor que best_buy (incluido en profit > 0 pero por si acaso)
        if c.best_sell <= c.best_buy:
            removed["profit"] += 1
            continue

        filtered.append(c)
        
    return filtered, removed

def select_final_candidates(candidates: List[CandidateStats], limit: int) -> List[int]:
    """
    Ordena por score y devuelve el top N de type_ids.
    """
    # Ordenar por score descendente
    sorted_candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
    return [c.type_id for c in sorted_candidates[:limit]]
