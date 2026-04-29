"""
Pure pricing functions for Quick Order Update.
No Qt, no ESI, no side effects.
"""

_NO_COMPETITOR = 0.0
_SENTINEL_MAX = 9_000_000_000_000.0  # ESI uses 9e12 when no orders exist


def price_tick(price: float) -> float:
    """Return the ISK tick size for a given price (EVE market rules)."""
    if price < 100:
        return 0.01
    if price < 1_000:
        return 0.1
    if price < 10_000:
        return 1.0
    if price < 100_000:
        return 10.0
    if price < 1_000_000:
        return 100.0
    if price < 10_000_000:
        return 1_000.0
    if price < 100_000_000:
        return 10_000.0
    return 100_000.0


def recommend_sell_price(competitor_sell: float) -> float:
    """Return the recommended sell price to undercut competitor by one tick."""
    return max(0.01, competitor_sell - price_tick(competitor_sell))


def recommend_buy_price(competitor_buy: float) -> float:
    """Return the recommended buy price to outbid competitor by one tick."""
    return competitor_buy + price_tick(competitor_buy)


def _has_competitor(price: float) -> bool:
    return price > _NO_COMPETITOR and price < _SENTINEL_MAX


def build_order_update_recommendation(order, analysis) -> dict:
    """
    Build a recommendation dict for a single order.

    Parameters
    ----------
    order    : OpenOrder dataclass (order_id, type_id, item_name, is_buy_order, price, ...)
    analysis : OpenOrderAnalysis dataclass (competitor_price, best_buy, best_sell,
               competitive, state, ...)

    Returns
    -------
    dict with keys:
        side, my_price, competitor_price, best_buy, best_sell, tick,
        recommended_price, reason, action_needed
    """
    side = "BUY" if order.is_buy_order else "SELL"
    my_price = order.price
    competitor_price = analysis.competitor_price if analysis else _NO_COMPETITOR
    best_buy = analysis.best_buy if analysis else _NO_COMPETITOR
    best_sell = analysis.best_sell if analysis else _NO_COMPETITOR

    has_comp = _has_competitor(competitor_price)

    if not has_comp:
        recommended_price = my_price
        reason = "Sin competidor identificado — mantener precio"
        action_needed = False
    elif order.is_buy_order:
        recommended_price = recommend_buy_price(competitor_price)
        already_best = analysis.competitive if analysis else False
        action_needed = not already_best
        reason = (
            "Ya liderando — sin cambio necesario"
            if not action_needed
            else f"Subir a {recommended_price:,.2f} ISK para superar competidor"
        )
    else:
        recommended_price = recommend_sell_price(competitor_price)
        already_best = analysis.competitive if analysis else False
        action_needed = not already_best
        reason = (
            "Ya liderando — sin cambio necesario"
            if not action_needed
            else f"Bajar a {recommended_price:,.2f} ISK para superar competidor"
        )

    tick = price_tick(competitor_price) if has_comp else price_tick(my_price)

    return {
        "side": side,
        "my_price": my_price,
        "competitor_price": competitor_price,
        "best_buy": best_buy,
        "best_sell": best_sell,
        "tick": tick,
        "recommended_price": recommended_price,
        "reason": reason,
        "action_needed": action_needed,
    }
