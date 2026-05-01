"""
Market manipulation detector for SELL and BUY orders.

Pure functions — no side effects, no UI dependencies, fully testable.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ManipulationResult:
    manipulation_checked: bool = False
    manipulation_detected: bool = False
    manipulation_side: str = ""         # "SELL" | "BUY" | ""
    manipulation_reason: str = ""
    safe_competitor_price: Optional[float] = None
    original_competitor_price: Optional[float] = None
    blocked_auto_update: bool = False
    warning_level: str = ""             # "low" | "medium" | "high" | ""


def detect_sell_manipulation(
    best_sell: float,
    best_buy: float,
    sell_orders: Optional[List[dict]] = None,
    min_spread_ratio: float = 0.05,
    min_cue_qty: int = 1,
) -> ManipulationResult:
    """
    Detect possible SELL manipulation when best_sell is suspiciously close to best_buy.

    A typical manipulation pattern: a very small sell order placed just above the best buy
    price to lure sellers into under-pricing their items.

    Returns a ManipulationResult with safe_competitor_price set to the next valid sell
    price if manipulation is detected.
    """
    result = ManipulationResult(manipulation_checked=True, manipulation_side="SELL")

    if best_sell <= 0 or best_buy <= 0:
        return result

    spread_ratio = (best_sell - best_buy) / best_buy if best_buy > 0 else 1.0

    if spread_ratio < min_spread_ratio:
        result.manipulation_detected = True
        result.original_competitor_price = best_sell
        result.manipulation_reason = (
            f"best_sell ({best_sell:.2f}) is within {spread_ratio*100:.1f}% of "
            f"best_buy ({best_buy:.2f}); possible cue order near buy wall"
        )
        result.warning_level = "high" if spread_ratio < 0.01 else "medium"
        result.blocked_auto_update = True

        # Try to find a safer sell price from the order book
        if sell_orders:
            candidate = _next_valid_sell(sell_orders, best_buy, min_spread_ratio)
            if candidate:
                result.safe_competitor_price = candidate
                result.blocked_auto_update = False
                result.warning_level = "medium"
        return result

    # Optional: detect abnormally thin first level (small quantity cue)
    if sell_orders:
        top = sorted(
            [o for o in sell_orders if not o.get("is_buy_order", True)],
            key=lambda o: o.get("price", float("inf"))
        )
        if top and top[0].get("volume_remain", min_cue_qty + 1) <= min_cue_qty:
            result.manipulation_detected = True
            result.original_competitor_price = best_sell
            result.manipulation_reason = (
                f"best_sell order has very low quantity ({top[0].get('volume_remain')}); "
                "possible cue order"
            )
            result.warning_level = "low"
            if len(top) > 1:
                result.safe_competitor_price = top[1].get("price")
                result.blocked_auto_update = False

    return result


def detect_buy_manipulation(
    best_buy: float,
    sell_orders: Optional[List[dict]] = None,
    buy_orders: Optional[List[dict]] = None,
    estimated_profit_margin: Optional[float] = None,
    manipulation_jump_threshold: float = 0.50,
    min_safe_margin_pct: float = 20.0,
) -> ManipulationResult:
    """
    Detect BUY manipulation when the best buy price is far above the next valid level.

    If best_buy >= next_buy * (1 + manipulation_jump_threshold), flag manipulation.
    Allow the update if estimated_profit_margin >= min_safe_margin_pct.
    """
    result = ManipulationResult(manipulation_checked=True, manipulation_side="BUY")

    if best_buy <= 0:
        return result

    if not buy_orders:
        return result

    sorted_buys = sorted(
        [o for o in buy_orders if o.get("is_buy_order", False)],
        key=lambda o: o.get("price", 0),
        reverse=True,
    )

    if len(sorted_buys) < 2:
        return result

    next_buy = sorted_buys[1].get("price", 0)
    if next_buy <= 0:
        return result

    jump_ratio = best_buy / next_buy
    if jump_ratio >= (1.0 + manipulation_jump_threshold):
        result.manipulation_detected = True
        result.original_competitor_price = best_buy
        result.manipulation_reason = (
            f"best_buy ({best_buy:.2f}) is {(jump_ratio-1)*100:.0f}% above "
            f"next_buy ({next_buy:.2f}); possible inflated buy wall"
        )
        result.safe_competitor_price = next_buy

        if estimated_profit_margin is not None and estimated_profit_margin >= min_safe_margin_pct:
            result.warning_level = "medium"
            result.blocked_auto_update = False
            result.manipulation_reason += (
                f" — but margin ({estimated_profit_margin:.1f}%) >= {min_safe_margin_pct:.0f}%; update allowed"
            )
        else:
            result.warning_level = "high"
            result.blocked_auto_update = True
            result.manipulation_reason += (
                f" — margin too low ({estimated_profit_margin:.1f}% < {min_safe_margin_pct:.0f}%); blocking update"
                if estimated_profit_margin is not None
                else " — no margin data; blocking update"
            )

    return result


def get_safe_competitor_price(
    orders: List[dict],
    side: str,
    best_buy: float = 0.0,
    min_spread_ratio: float = 0.05,
) -> Optional[float]:
    """
    Return the safest competitor price for the given side after manipulation filtering.

    For SELL: skip the best sell if it looks manipulated, return the next valid one.
    For BUY: return best_buy as-is (buy manipulation check is done separately).
    """
    if side.upper() == "SELL":
        sell_prices = sorted(
            [o.get("price", 0) for o in orders if not o.get("is_buy_order", True) and o.get("price", 0) > 0]
        )
        for price in sell_prices:
            if best_buy <= 0 or (price - best_buy) / best_buy >= min_spread_ratio:
                return price
        return sell_prices[0] if sell_prices else None

    if side.upper() == "BUY":
        buy_prices = sorted(
            [o.get("price", 0) for o in orders if o.get("is_buy_order", False) and o.get("price", 0) > 0],
            reverse=True,
        )
        return buy_prices[0] if buy_prices else None

    return None


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

def _next_valid_sell(sell_orders: List[dict], best_buy: float, min_spread_ratio: float) -> Optional[float]:
    prices = sorted(
        [o.get("price", 0) for o in sell_orders if not o.get("is_buy_order", True) and o.get("price", 0) > 0]
    )
    for price in prices:
        if best_buy <= 0 or (price - best_buy) / best_buy >= min_spread_ratio:
            return price
    return None
