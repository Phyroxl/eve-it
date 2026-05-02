from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class LiquidityMetrics:
    volume_5d: int
    history_days: int
    buy_orders_count: int
    sell_orders_count: int

@dataclass
class ScoreBreakdown:
    base_score: float
    liquidity_norm: float
    roi_norm: float
    profit_day_norm: float
    penalties: List[float]
    final_score: float

@dataclass
class MarketOpportunity:
    type_id: int
    item_name: str
    best_buy_price: float
    best_sell_price: float
    margin_net_pct: float
    profit_per_unit: float
    profit_day_est: float
    spread_pct: float
    risk_level: str
    tags: List[str]
    liquidity: LiquidityMetrics
    score_breakdown: Optional[ScoreBreakdown] = None
    recommended_qty: int = 0
    recommended_cost: float = 0.0
    is_enriched: bool = False

@dataclass
class FilterConfig:
    capital_max: float = 1_000_000_000_000.0  # 1 Trillion (Non-restrictive)
    capital_min: float = 0.0                   # 0 = no minimum unit price filter
    vol_min_day: int = 0
    margin_min_pct: float = -100.0             # Allow losses by default in exploration
    spread_max_pct: float = 1000.0
    exclude_plex: bool = False
    broker_fee_pct: float = 3.0
    sales_tax_pct: float = 8.0

    # Advanced Filters (Phase 1)
    score_min: float = 0.0
    risk_max: int = 3                          # 1: Low, 2: Medium, 3: High
    buy_orders_min: int = 0
    sell_orders_min: int = 0
    history_days_min: int = 0
    profit_day_min: float = 0.0
    profit_unit_min: float = 0.0               # Minimum net profit per unit
    require_buy_sell: bool = False             # Require both buy and sell orders present
    selected_category: str = "Todos"
    max_item_types: int = 0                    # 0 = No limit

@dataclass
class PerformanceConfig:
    auto_refresh_enabled: bool = False
    refresh_interval_min: int = 5

@dataclass
class OpenOrderAnalysis:
    is_buy: bool
    state: str
    gross_profit_per_unit: float
    net_profit_per_unit: float
    net_profit_total: float
    margin_pct: float
    best_buy: float
    best_sell: float
    spread_pct: float
    competitive: bool
    difference_to_best: float
    competitor_price: float = 0.0

@dataclass
class OpenOrder:
    order_id: int
    type_id: int
    item_name: str
    is_buy_order: bool
    price: float
    volume_total: int
    volume_remain: int
    issued: str
    location_id: int
    range: str
    analysis: Optional[OpenOrderAnalysis] = None

@dataclass
class InventoryAnalysis:
    best_buy: float
    best_sell: float
    spread_pct: float
    est_net_sell_unit: float
    est_total_value: float
    recommendation: str  # Sell, Hold, Review
    reason: str

@dataclass
class InventoryItem:
    type_id: int
    item_name: str
    quantity: int
    location_id: int
    analysis: Optional[InventoryAnalysis] = None
