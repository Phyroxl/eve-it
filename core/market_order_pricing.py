"""
Pure pricing functions for Quick Order Update.
No Qt, no ESI, no side effects.
"""

_NO_COMPETITOR = 0.0
_SENTINEL_MAX = 9_000_000_000_000.0  # ESI uses 9e12 when no orders exist
_PRICE_EQ_TOLERANCE = 0.005          # 0.5 cent — same price for EVE purposes


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


def _prices_equal(a: float, b: float) -> bool:
    """True if two prices are indistinguishably close (within EVE tick tolerance)."""
    return abs(a - b) < _PRICE_EQ_TOLERANCE


def validate_quick_update_price_source(order, analysis) -> dict:
    """
    Validate that the competitor price in an analysis is trustworthy for
    Quick Order Update before auto-copying.

    Detects two main failure modes:
    1. competitor_price == own price  → own order likely included as competitor.
    2. best_sell / best_buy == own price in SELL/BUY context → same staleness risk.

    Parameters
    ----------
    order    : OpenOrder dataclass
    analysis : OpenOrderAnalysis dataclass (may be None)

    Returns
    -------
    dict with keys:
        is_confident    : bool  — True = safe to auto-copy
        stale_suspected : bool  — True = ESI order data may be stale
        own_price_eq_competitor : bool
        own_price       : float
        competitor_price : float
        price_source    : str   — human-readable source label
        warnings        : list[str]
        confidence_label : str  — "Alta" | "Baja"
    """
    warnings = []
    own_price = order.price if order else 0.0
    is_buy = order.is_buy_order if order else False
    competitor_price = analysis.competitor_price if analysis else 0.0
    best_buy = analysis.best_buy if analysis else 0.0
    best_sell = analysis.best_sell if analysis else 0.0

    own_eq_competitor = _prices_equal(own_price, competitor_price) and _has_competitor(competitor_price)

    # Check 1: competitor_price == own price
    if own_eq_competitor:
        warnings.append(
            f"PRECIO COMPETIDOR ({competitor_price:.2f} ISK) igual a MI PRECIO "
            f"({own_price:.2f} ISK). Posible orden propia incluida como competidor."
        )

    # Check 2: absolute best price equals own price — staleness indicator
    stale_suspected = False
    if not is_buy and best_sell > 0 and _prices_equal(own_price, best_sell) and own_eq_competitor:
        stale_suspected = True
        warnings.append(
            f"Mejor venta absoluta ({best_sell:.2f} ISK) coincide con mi precio. "
            "Puede que el order book esté desactualizado o que mi orden sea la líder."
        )
    if is_buy and best_buy > 0 and _prices_equal(own_price, best_buy) and own_eq_competitor:
        stale_suspected = True
        warnings.append(
            f"Mejor compra absoluta ({best_buy:.2f} ISK) coincide con mi precio. "
            "Puede que el order book esté desactualizado o que mi orden sea la líder."
        )

    # Check 3: no usable competitor
    if not _has_competitor(competitor_price):
        warnings.append("Sin competidor identificado — no se puede recomendar precio automático.")

    is_confident = len(warnings) == 0

    return {
        "is_confident": is_confident,
        "stale_suspected": stale_suspected,
        "own_price_eq_competitor": own_eq_competitor,
        "own_price": own_price,
        "competitor_price": competitor_price,
        "price_source": "analysis.competitor_price",
        "warnings": warnings,
        "confidence_label": "Alta" if is_confident else "Baja",
    }


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
        recommended_price, reason, action_needed,
        validation (sub-dict from validate_quick_update_price_source)
    """
    side = "BUY" if order.is_buy_order else "SELL"
    my_price = order.price
    competitor_price = analysis.competitor_price if analysis else _NO_COMPETITOR
    best_buy = analysis.best_buy if analysis else _NO_COMPETITOR
    best_sell = analysis.best_sell if analysis else _NO_COMPETITOR

    has_comp = _has_competitor(competitor_price)

    # Run validation before building recommendation
    validation = validate_quick_update_price_source(order, analysis)

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

    # Append validation warnings to reason if not confident
    if not validation["is_confident"]:
        reason = "⚠ " + reason + " [CONFIANZA BAJA — revisar manualmente]"

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
        "validation": validation,
    }
