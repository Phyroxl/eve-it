"""
Diagnostics / report formatter for Quick Order Update.
Pure text output, no Qt, no ESI.
"""

from typing import Any


def format_quick_update_report(data: dict) -> str:
    """
    Format a human-readable diagnostic report from a recommendation dict.

    Expected keys in `data` (all optional, defaults to 'N/A'):
        order_id, type_id, item_name, location_name,
        side, my_price, competitor_price, best_buy, best_sell,
        tick, recommended_price, reason, action_needed,
        clipboard_value, market_window_opened,
        validation, config, errors, notes
    """

    def _fmt(val: Any, suffix: str = "") -> str:
        if val is None:
            return "N/A"
        if isinstance(val, float):
            return f"{val:,.2f}{suffix}"
        return f"{val}{suffix}"

    lines = []

    lines.append("[ORDER]")
    lines.append(f"  order_id        : {_fmt(data.get('order_id'))}")
    lines.append(f"  type_id         : {_fmt(data.get('type_id'))}")
    lines.append(f"  item_name       : {_fmt(data.get('item_name'))}")
    lines.append(f"  location        : {_fmt(data.get('location_name'))}")
    lines.append(f"  side            : {_fmt(data.get('side'))}")
    lines.append(f"  my_price        : {_fmt(data.get('my_price'), ' ISK')}")

    lines.append("")
    lines.append("[MARKET]")
    lines.append(f"  competitor_price: {_fmt(data.get('competitor_price'), ' ISK')}")
    lines.append(f"  best_buy        : {_fmt(data.get('best_buy'), ' ISK')}")
    lines.append(f"  best_sell       : {_fmt(data.get('best_sell'), ' ISK')}")
    lines.append(f"  tick            : {_fmt(data.get('tick'), ' ISK')}")

    # ------------------------------------------------------------------ validation
    validation = data.get("validation") or {}
    lines.append("")
    lines.append("[ORDER PRICE VALIDATION]")
    lines.append(f"  My Order Price              : {_fmt(data.get('my_price'), ' ISK')}")
    lines.append(f"  Competitor Price            : {_fmt(validation.get('competitor_price', data.get('competitor_price')), ' ISK')}")
    lines.append(f"  Competitor == My Price      : {validation.get('own_price_eq_competitor', 'N/A')}")
    lines.append(f"  Stale Order Suspected       : {validation.get('stale_suspected', 'N/A')}")
    lines.append(f"  Confidence                  : {validation.get('confidence_label', 'N/A')}")
    v_warnings = validation.get("warnings") or []
    if v_warnings:
        lines.append("  Warnings:")
        for w in v_warnings:
            lines.append(f"    ⚠ {w}")
    else:
        lines.append("  Warnings                    : (none)")

    # ------------------------------------------------------------------ freshness
    freshness = data.get("freshness") or {}
    lines.append("")
    lines.append("[ORDER FRESHNESS]")
    lines.append(f"  Checked              : {freshness.get('checked', 'N/A')}")
    lines.append(f"  Order Exists         : {freshness.get('order_exists', 'N/A')}")
    lines.append(f"  Old Local Price      : {_fmt(freshness.get('old_price'), ' ISK')}")
    fp = freshness.get("fresh_price")
    lines.append(f"  Fresh ESI Price      : {_fmt(fp, ' ISK') if fp is not None else 'N/A'}")
    lines.append(f"  Price Changed        : {freshness.get('price_changed', 'N/A')}")
    lines.append(f"  Is Fresh             : {freshness.get('is_fresh', 'N/A')}")
    f_warnings = freshness.get("warnings") or []
    if f_warnings:
        lines.append("  Warnings:")
        for fw in f_warnings:
            lines.append(f"    * {fw}")
    else:
        lines.append("  Warnings             : (none)")
    # ------------------------------------------------------------------ /freshness

    lines.append("")
    lines.append("[WHY NOT AUTO COPY]")
    all_block_reasons = list(v_warnings) + list(f_warnings)
    if not validation.get("is_confident", True) or not freshness.get("is_fresh", True):
        lines.append("  Auto-copy was BLOCKED because:")
        for r in all_block_reasons:
            lines.append(f"    - {r}")
        if not all_block_reasons:
            lines.append("    (no specific reason recorded)")
    else:
        lines.append("  Auto-copy proceeded normally (confidence: Alta, order fresh).")
    # ------------------------------------------------------------------ /validation

    lines.append("")
    lines.append("[RECOMMENDATION]")
    lines.append(f"  recommended     : {_fmt(data.get('recommended_price'), ' ISK')}")
    lines.append(f"  reason          : {_fmt(data.get('reason'))}")
    lines.append(f"  action_needed   : {_fmt(data.get('action_needed'))}")

    lines.append("")
    lines.append("[ACTIONS]")
    lines.append(f"  clipboard       : {_fmt(data.get('clipboard_value'))}")
    lines.append(f"  market_window   : {_fmt(data.get('market_window_opened'))}")

    cfg = data.get("config")
    lines.append("")
    lines.append("[CONFIG]")
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            lines.append(f"  {k:<18}: {v}")
    else:
        lines.append(f"  {_fmt(cfg)}")

    errors = data.get("errors") or []
    lines.append("")
    lines.append("[ERRORS]")
    if errors:
        for e in errors:
            lines.append(f"  - {e}")
    else:
        lines.append("  (none)")

    notes = data.get("notes") or []
    lines.append("")
    lines.append("[NOTES]")
    if notes:
        for n in notes:
            lines.append(f"  - {n}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)
