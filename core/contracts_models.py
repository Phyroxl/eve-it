from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContractItem:
    type_id: int
    item_name: str
    quantity: int
    is_included: bool           # True = forma parte del contrato. False = comprador debe entregarlo
    jita_sell_price: float
    jita_buy_price: float
    line_sell_value: float      # quantity * jita_sell_price
    line_buy_value: float       # quantity * jita_buy_price
    pct_of_total: float         # line_sell_value / jita_sell_value * 100
    is_blueprint: bool = False
    is_copy: bool = False


@dataclass
class ScoreBreakdown:
    roi_component: float
    profit_component: float
    simplicity_component: float
    penalties_applied: List[str]
    final_score: float


@dataclass
class ContractArbitrageResult:
    contract_id: int
    region_id: int
    issuer_id: int
    contract_cost: float
    date_expired: str
    location_id: int
    item_type_count: int
    total_units: int
    items: List[ContractItem]
    jita_sell_value: float
    jita_buy_value: float
    gross_profit: float          # jita_sell_value - contract_cost
    net_profit: float            # gross_profit - fees
    roi_pct: float               # (net_profit / contract_cost) * 100
    value_concentration: float   # max(line_sell_value) / jita_sell_value
    has_unresolved_items: bool
    unresolved_count: int
    has_blueprints: bool = False
    score: float = 0.0
    score_breakdown: Optional[ScoreBreakdown] = None


@dataclass
class ContractsFilterConfig:
    region_id: int = 10000002
    capital_max_isk: float = 1_000_000_000.0
    capital_min_isk: float = 1_000_000.0
    profit_min_isk: float = 10_000_000.0
    roi_min_pct: float = 5.0
    item_types_max: int = 50
    broker_fee_pct: float = 3.0
    sales_tax_pct: float = 8.0
    max_contracts_to_scan: int = 1000
    price_reference: str = "sell"
    exclude_no_price: bool = True
    exclude_blueprints: bool = True
    category_filter: str = "all"  # ships, modules, etc.
