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

@dataclass
class FilterConfig:
    capital_max: float = 500_000_000.0
    vol_min_day: int = 20
    margin_min_pct: float = 5.0
    spread_max_pct: float = 40.0
    exclude_plex: bool = True
    broker_fee_pct: float = 3.0
    sales_tax_pct: float = 8.0
    
    # Advanced Filters (Phase 1)
    score_min: float = 0.0
    risk_max: int = 3  # 1: Low, 2: Medium, 3: High
    buy_orders_min: int = 0
    sell_orders_min: int = 0
    history_days_min: int = 0
    profit_day_min: float = 0.0

@dataclass
class PerformanceConfig:
    auto_refresh_enabled: bool = False
    refresh_interval_min: int = 5
