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
    valuation_status: str = "ok" # "ok", "bpc_ignored", "uncertain_ignored"

    @classmethod
    def from_dict(cls, d: dict) -> ContractItem:
        return cls(**d)


@dataclass
class ScoreBreakdown:
    roi_component: float
    profit_component: float
    simplicity_component: float
    penalties_applied: List[str]
    final_score: float

    @classmethod
    def from_dict(cls, d: dict) -> ScoreBreakdown:
        return cls(**d)


@dataclass
class ScanDiagnostics:
    total_scanned: int = 0
    after_basic_filters: int = 0
    excluded_by_price: int = 0
    excluded_by_complexity: int = 0
    excluded_by_no_price: int = 0
    excluded_by_blueprint: int = 0
    excluded_by_bpc: int = 0
    excluded_by_category: int = 0
    excluded_by_low_profit: int = 0
    excluded_by_low_roi: int = 0
    profitable: int = 0
    excluded_by_no_items: int = 0
    excluded_by_zero_value: int = 0
    contract_cache_hits: int = 0
    contract_cache_misses: int = 0

    def to_summary(self) -> str:
        return (f"Total: {self.total_scanned} | Profitable: {self.profitable} | "
                f"Low Profit/ROI: {self.excluded_by_low_profit}/{self.excluded_by_low_roi} | "
                f"BP/BPC: {self.excluded_by_blueprint}/{self.excluded_by_bpc} | "
                f"No Items/Val: {self.excluded_by_no_items}/{self.excluded_by_zero_value}")


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
    valuation_warning: Optional[str] = None
    score: float = 0.0
    score_breakdown: Optional[ScoreBreakdown] = None
    filter_reason: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> ContractArbitrageResult:
        items = [ContractItem.from_dict(i) for i in d.pop('items', [])]
        score_bd = d.pop('score_breakdown', None)
        if score_bd:
            score_bd = ScoreBreakdown.from_dict(score_bd)
        return cls(items=items, score_breakdown=score_bd, **d)


@dataclass
class ContractsFilterConfig:
    region_id: int = 10000002
    capital_max_isk: float = 1_000_000_000.0
    capital_min_isk: float = 1_000_000.0
    profit_min_isk: float = 0.0
    roi_min_pct: float = 1.0
    item_types_max: int = 50
    broker_fee_pct: float = 3.0
    sales_tax_pct: float = 8.0
    max_contracts_to_scan: int = 1000
    price_reference: str = "sell"
    exclude_no_price: bool = True
    exclude_blueprints: bool = False
    exclude_bpcs: bool = False
    category_filter: str = "all"  # ships, modules, etc.
