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
    net_units: int
    gross_income: float
    gross_cost: float
    fees_paid: float
    profit_net: float             # Crudo: Income - Cost - Fees
    realized_profit_est: float    # Aproximado: Lo ganado en ventas cerradas
    inventory_value_est: float    # Capital "atrapado" en el stock neto acumulado
    margin_real_pct: float
    trade_count: int
    status_text: str = ""

@dataclass
class CharacterPerformanceSummary:
    character_id: int
    character_name: str
    portrait_url: str
    period_start: datetime
    period_end: datetime
    
    total_income: float
    total_cost: float
    broker_fees: float
    sales_tax: float
    total_fees: float  # Combined fees + tax
    
    net_cashflow: float  # income - cost - fees - tax (Rolling Trade Profit in EVE Tycoon)
    total_realized_profit: float  # Closed profit based on estimated COGS
    
    inventory_exposure: float     # Valor estimado del stock acumulado en el periodo
    wallet_current: float
    last_synced_at: datetime
    period_context: str = ""       # Diagnóstico: "Acumulación", "Liquidación", etc.

@dataclass
class FeeBreakdown:
    character_id: int
    period_start: datetime
    period_end: datetime
    broker_fees_total: float
    sales_tax_total: float
    total_fees: float
    fees_as_pct_of_income: float
