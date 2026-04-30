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

    # ------------------------------------------------------------------ market validation
    m_val = data.get("market_validation") or {}
    lines.append("")
    lines.append("[MARKET COMPETITOR REVALIDATION]")
    lines.append(f"  Checked              : {m_val.get('checked', 'N/A')}")
    lines.append(f"  Is Fresh             : {m_val.get('is_fresh', 'N/A')}")
    lines.append(f"  Market Scope         : {m_val.get('market_scope', 'N/A')}")
    lines.append(f"  Filtered By Location : {m_val.get('filtered_by_location', 'N/A')}")
    lines.append(f"  Target Location ID   : {m_val.get('target_location_id', 'N/A')}")
    lines.append(f"  Regional Orders Count: {m_val.get('regional_orders_count', 'N/A')}")
    lines.append(f"  Location Orders Count: {m_val.get('location_orders_count', 'N/A')}")
    lines.append(f"  Old Competitor Price : {_fmt(m_val.get('old_competitor_price'), ' ISK')}")
    lines.append(f"  Fresh Best Sell      : {_fmt(m_val.get('fresh_best_sell'), ' ISK')}")
    lines.append(f"  Fresh Best Buy       : {_fmt(m_val.get('fresh_best_buy'), ' ISK')}")
    lines.append(f"  Fresh Competitor Price: {_fmt(m_val.get('fresh_competitor_price'), ' ISK')}")
    lines.append(f"  Fresh Recommended    : {_fmt(m_val.get('fresh_recommended_price'), ' ISK')}")
    lines.append(f"  Used Fresh Price     : {m_val.get('used_fresh_price', 'N/A')}")
    lines.append(f"  Price Changed        : {m_val.get('price_changed', 'N/A')}")
    lines.append(f"  Own Orders Excluded  : {m_val.get('own_orders_excluded_count', 'N/A')}")
    m_warnings = m_val.get("warnings") or []
    if m_warnings:
        lines.append("  Warnings:")
        for mw in m_warnings:
            lines.append(f"    * {mw}")
    else:
        lines.append("  Warnings             : (none)")
    # ------------------------------------------------------------------ /market validation

    lines.append("")
    lines.append("[WHY NOT AUTO COPY]")
    all_block_reasons = list(v_warnings) + list(f_warnings) + list(m_warnings)
    is_conf = validation.get("is_confident", True)
    is_fresh_ord = freshness.get("is_fresh", True)
    is_fresh_mkt = m_val.get("is_fresh", True)
    
    if not is_conf or not is_fresh_ord or not is_fresh_mkt:
        lines.append("  Auto-copy was BLOCKED because:")
        for r in all_block_reasons:
            lines.append(f"    - {r}")
        if not all_block_reasons:
            lines.append("    (no specific reason recorded)")
    else:
        lines.append("  Auto-copy proceeded normally (confidence: Alta, order fresh, market fresh).")
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

    # ------------------------------------------------------------------ automation
    automation = data.get("automation") or {}
    if automation:
        lines.append("")
        lines += _format_automation_section(automation)

    return "\n".join(lines)


def format_automation_section(automation: dict) -> str:
    """Return just the [AUTOMATION] section as a string (for appending to existing report)."""
    return "\n".join(_format_automation_section(automation))


def replace_or_append_automation_section(report: str, automation_section: str) -> str:
    """
    Ensure [AUTOMATION] appears exactly once in a diagnostic report.

    If `report` already contains '[AUTOMATION]', that block (from the marker to
    end-of-string) is replaced with `automation_section`.
    If it does not, `automation_section` is appended.

    This prevents the double-section problem that occurs when:
      1. format_quick_update_report() includes [AUTOMATION] because data["automation"] is set, AND
      2. _on_automate() in the dialog appends format_automation_section() on top.
    """
    marker = "[AUTOMATION]"
    if marker in report:
        # Keep everything before the first occurrence of the marker
        head = report[: report.index(marker)].rstrip()
        return head + "\n\n" + automation_section
    return report + "\n\n" + automation_section


def _format_automation_section(automation: dict) -> list:
    def _b(val) -> str:
        if val is None:
            return "N/A"
        return str(val)

    lines = []
    lines.append("[AUTOMATION]")
    lines.append(f"  Enabled              : {_b(automation.get('enabled'))}")
    lines.append(f"  Dry Run              : {_b(automation.get('dry_run'))}")
    lines.append(f"  Status               : {_b(automation.get('status'))}")
    lines.append(f"  Window Source        : {_b(automation.get('window_source'))}")
    lines.append(f"  Selected Win Handle  : {_b(automation.get('selected_window_handle'))}")
    lines.append(f"  Selected Win Title   : {_b(automation.get('selected_window_title'))}")
    lines.append(f"  Window Found         : {_b(automation.get('window_found'))}")
    lines.append(f"  Window Title         : {_b(automation.get('window_title'))}")
    lines.append(f"  Focused              : {_b(automation.get('focused'))}")
    lines.append(f"  Clipboard Set        : {_b(automation.get('clipboard_set'))}")
    lines.append(f"  Recommended Price    : {_b(automation.get('recommended_price_text'))}")
    lines.append(f"  Exp. Paste Enabled   : {_b(automation.get('experimental_paste_enabled'))}")
    lines.append(f"  Paste into Focused   : {_b(automation.get('paste_into_focused_window'))}")
    lines.append(f"  Clear Price Field    : {_b(automation.get('clear_price_field_before_paste'))}")
    lines.append(f"  Paste Method         : {_b(automation.get('paste_method'))}")
    lines.append(f"  Price Pasted         : {_b(automation.get('price_pasted'))}")
    lines.append(f"  Modify Order Step    : {_b(automation.get('modify_order_step_enabled'))}")
    lines.append(f"  Modify Order Strategy: {_b(automation.get('modify_order_strategy'))}")
    lines.append(f"  Paste Without Verify : {_b(automation.get('paste_without_modify_dialog_verification'))}")
    lines.append(f"  Modify Hotkey Config : {'set' if automation.get('modify_order_hotkey_configured') else 'empty'}")
    lines.append(f"  Modify Dialog Verified: {_b(automation.get('modify_order_dialog_verified'))}")
    lines.append(f"  Require Dialog Ready : {_b(automation.get('require_modify_dialog_ready'))}")
    lines.append(f"  Allow Unverified Paste: {_b(automation.get('allow_unverified_modify_order_paste'))}")
    modify_warn = automation.get("modify_order_warning")
    if modify_warn:
        lines.append(f"  Modify Order Warning : {modify_warn}")
    lines.append(f"  Never Confirm Order  : {_b(automation.get('never_confirm_final_order'))}")
    # Phase 3C: visual_ocr
    lines.append(f"  Visual OCR Enabled   : {_b(automation.get('visual_ocr_enabled'))}")
    lines.append(f"  Visual OCR Status    : {_b(automation.get('visual_ocr_status'))}")
    lines.append(f"  Visual OCR Candidates: {_b(automation.get('visual_ocr_candidates_count'))}")
    lines.append(f"  Visual OCR Price     : {_b(automation.get('visual_ocr_matched_price'))}")
    lines.append(f"  Visual OCR Quantity  : {_b(automation.get('visual_ocr_matched_quantity'))}")
    lines.append(f"  Visual OCR Row X     : {_b(automation.get('visual_ocr_row_x'))}")
    lines.append(f"  Visual OCR Row Y     : {_b(automation.get('visual_ocr_row_y'))}")
    lines.append(f"  Visual OCR Blue Bands: {_b(automation.get('visual_ocr_blue_bands_found'))}")
    lines.append(f"  Visual OCR Section   : {_b(automation.get('visual_ocr_section_used'))}")
    lines.append(f"  Visual OCR Sec Y Min : {_b(automation.get('visual_ocr_section_y_min'))}")
    lines.append(f"  Visual OCR Sec Y Max : {_b(automation.get('visual_ocr_section_y_max'))}")
    dbg = automation.get("visual_ocr_debug") or {}
    lines.append(f"  Visual OCR Panel X   : {dbg.get('market_panel_x_min', 'N/A')} to {dbg.get('market_panel_x_max', 'N/A')}")
    lines.append(f"  Visual OCR Blue Pix  : {dbg.get('sample_dark_blue_pixels_count', 'N/A')}")
    lines.append(f"  Visual OCR Avg Color : {dbg.get('average_blue_candidate_rgb', 'N/A')}")
    top_rows = dbg.get("top_blue_candidate_rows")
    if top_rows:
        lines.append("  Visual OCR Top Rows  :")
        for tr in top_rows:
            lines.append(f"    y={tr.get('y')} pix={tr.get('blue_pixels')}")
    lines.append(f"  Visual OCR Own Marker: {_b(automation.get('visual_ocr_own_marker_matched'))}")
    lines.append(f"  Visual OCR Price Txt : {_b(automation.get('visual_ocr_price_text'))}")
    lines.append(f"  Visual OCR Qty Txt   : {_b(automation.get('visual_ocr_quantity_text'))}")
    dbg_path = automation.get("visual_ocr_debug_screenshot_path")
    if dbg_path:
        lines.append(f"  Visual OCR Debug Img : {dbg_path}")
    overlay_path = automation.get("visual_ocr_debug_overlay_path")
    if overlay_path:
        lines.append(f"  Visual OCR Overlay   : {overlay_path}")
    lines.append(f"  Candidate Win Count  : {_b(automation.get('candidate_windows_count'))}")
    cands = automation.get("candidate_windows") or []
    if cands:
        lines.append("  Candidate Windows:")
        for c in cands[:8]:
            flag = " [IGNORAR-propia app]" if c.get("is_self_app") else ""
            lines.append(
                f"    score={c.get('score',0):+4d}  "
                f"handle={c.get('handle','?')}  "
                f"{c.get('title','?')}{flag}"
            )
    else:
        lines.append("  Candidate Windows    : (none detected)")

    steps_exec = automation.get("steps_executed") or []
    lines.append("  Steps Executed:")
    for s in steps_exec:
        lines.append(f"    + {s}")
    if not steps_exec:
        lines.append("    (none)")

    steps_skip = automation.get("steps_skipped") or []
    lines.append("  Steps Skipped:")
    for s in steps_skip:
        lines.append(f"    - {s}")
    if not steps_skip:
        lines.append("    (none)")

    a_errors = automation.get("errors") or []
    lines.append("  Errors:")
    for e in a_errors:
        lines.append(f"    ! {e}")
    if not a_errors:
        lines.append("    (none)")

    delays = automation.get("delays") or {}
    lines.append("  Delays (ms):")
    if delays:
        for k, v in delays.items():
            lines.append(f"    {k}: {v}")
    else:
        lines.append("    (none)")

    lines.append(f"  Final Confirm Action : NOT_EXECUTED_BY_DESIGN")

    return lines
