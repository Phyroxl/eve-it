from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class WalletTransaction:
    transaction_id: int
    character_id: int
    date: datetime
    item_id: int
    item_name: str
    quantity: int
    unit_price: float
    is_buy: bool
    order_id: int
    client_id: int
    location_id: int
    total_isk: float = 0.0

    def __post_init__(self):
        self.total_isk = self.quantity * self.unit_price

@dataclass
class DailyPnLEntry:
    character_id: int
    date: str  # YYYY-MM-DD
    gross_income: float
    gross_cost: float
    fees: float
    tax: float
    profit_net: float
    cumulative_profit_net: float
    transaction_count: int

@dataclass
class ItemPerformanceSummary:
    character_id: int
    item_id: int
    item_name: str
    period_start: datetime
    period_end: datetime
    total_sold_units: int
    total_bought_units: int
    gross_income: float
    gross_cost: float
    fees_paid: float
    profit_net: float
    margin_real_pct: float
    trade_count: int

@dataclass
class CharacterPerformanceSummary:
    character_id: int
    character_name: str
    portrait_url: str
    period_start: datetime
    period_end: datetime
    total_profit_net: float
    total_income: float
    total_cost: float
    total_fees: float
    wallet_current: float
    last_synced_at: datetime

@dataclass
class FeeBreakdown:
    character_id: int
    period_start: datetime
    period_end: datetime
    broker_fees_total: float
    sales_tax_total: float
    total_fees: float
    fees_as_pct_of_income: float
