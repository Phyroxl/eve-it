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
    lines.append("[CONFIG DIAGNOSTICS]")
    if isinstance(cfg, dict):
        meta = cfg.get("_metadata") or {}
        lines.append(f"  Config Path         : {meta.get('config_path', meta.get('path', 'N/A'))}")
        lines.append(f"  Config Exists       : {meta.get('config_exists', meta.get('exists', 'N/A'))}")
        lines.append(f"  Fallback Used       : {meta.get('config_fallback_used', 'N/A')}")
        if meta.get("config_load_error"):
            lines.append(f"  Load Error          : {meta.get('config_load_error')}")
        
        lines.append("")
        lines.append("[EFFECTIVE CONFIG VALUES]")
        # Show critical values that affect automation execution
        critical_keys = [
            "enabled", "dry_run", "experimental_paste_enabled", 
            "paste_into_focused_window", "modify_order_step_enabled",
            "modify_order_strategy", "visual_ocr_enabled",
            "visual_ocr_paste_after_unverified_modify_click",
            "never_confirm_final_order"
        ]
        for k in critical_keys:
            if k in cfg:
                lines.append(f"  {k:<18}: {cfg[k]}")
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
    Ensure [AUTOMATION] appears exactly once in a diagnostic report, 
    preserving any sections that might follow it.
    """
    marker = "[AUTOMATION]"
    
    # If report is empty or None, just return the section
    if not report:
        return automation_section

    # Robust replacement: find ALL [AUTOMATION] blocks and remove them to avoid duplicates
    # A block starts with [AUTOMATION] and ends before the next '['
    import re
    # This regex finds [AUTOMATION] and everything until the next [ or end of string
    pattern = r"\[AUTOMATION\].*?(?=\n\[|$)"
    # Use DOTALL to make . match newlines
    new_report = re.sub(pattern, "", report, flags=re.DOTALL)
    
    # Clean up trailing whitespace and add the new section
    return new_report.rstrip() + "\n\n" + automation_section


def format_config_section(config: dict) -> str:
    """Format the [CONFIG DIAGNOSTICS] and [EFFECTIVE CONFIG VALUES] sections."""
    lines = []
    lines.append("[CONFIG DIAGNOSTICS]")
    meta = config.get("_metadata") or {}
    lines.append(f"  Config Path         : {meta.get('config_path', 'N/A')}")
    lines.append(f"  Config Exists       : {meta.get('config_exists', 'N/A')}")
    lines.append(f"  Fallback Used       : {meta.get('config_fallback_used', 'N/A')}")
    if meta.get("config_load_error"):
        lines.append(f"  Load Error          : {meta.get('config_load_error')}")
    
    lines.append("")
    lines.append("[EFFECTIVE CONFIG VALUES]")
    critical_keys = [
        "enabled", "dry_run", "experimental_paste_enabled", 
        "paste_into_focused_window", "modify_order_step_enabled",
        "modify_order_strategy", "visual_ocr_enabled",
        "visual_ocr_paste_after_unverified_modify_click",
        "never_confirm_final_order"
    ]
    for k in critical_keys:
        if k in config:
            lines.append(f"  {k:<18}: {config[k]}")
    
    return "\n".join(lines)


def replace_or_append_config_section(report: str, config_section: str) -> str:
    """
    Ensure [CONFIG DIAGNOSTICS] and [EFFECTIVE CONFIG VALUES] are updated in the report.
    Since they are usually together, we look for [CONFIG DIAGNOSTICS].
    """
    marker = "[CONFIG DIAGNOSTICS]"
    if marker in report:
        start_idx = report.index(marker)
        # Look for the next section marker '[' after the start of this section
        # BUT skip [EFFECTIVE CONFIG VALUES] which is part of our update
        next_search_start = start_idx + len(marker)
        next_section_idx = -1
        
        current_pos = next_search_start
        while True:
            idx = report.find("[", current_pos)
            if idx == -1: break
            section_name = report[idx:report.find("]", idx)+1]
            if section_name not in ["[CONFIG DIAGNOSTICS]", "[EFFECTIVE CONFIG VALUES]"]:
                next_section_idx = idx
                break
            current_pos = idx + 1
        
        head = report[:start_idx].rstrip()
        tail = ""
        if next_section_idx != -1:
            tail = "\n\n" + report[next_section_idx:].lstrip()
            
        return head + "\n\n" + config_section + tail

    # If [CONFIG] was the old marker, replace it
    old_marker = "[CONFIG]"
    if old_marker in report:
        start_idx = report.index(old_marker)
        next_section_idx = report.find("[", start_idx + len(old_marker))
        head = report[:start_idx].rstrip()
        tail = ""
        if next_section_idx != -1:
            tail = "\n\n" + report[next_section_idx:].lstrip()
        return head + "\n\n" + config_section + tail
            
    return report.rstrip() + "\n\n" + config_section


def _format_automation_section(automation: dict) -> list:
    def _b(val) -> str:
        if val is None:
            return "N/A"
        return str(val)

    lines = []
    lines.append("[AUTOMATION]")
    lines.append(f"  Automation Run ID    : {_b(automation.get('automation_run_id'))}")
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
    lines.append(f"  Visual OCR Mode      : {automation.get('visual_ocr_detection_mode', 'strict')}")
    lines.append(f"  Visual OCR Candidates: {_b(automation.get('visual_ocr_candidates_count'))}")
    lines.append(f"  Visual OCR Price     : {_b(automation.get('visual_ocr_matched_price'))}")
    lines.append(f"  Visual OCR Quantity  : {_b(automation.get('visual_ocr_matched_quantity'))}")
    lines.append(f"  Visual OCR Row X     : {_b(automation.get('visual_ocr_row_x'))}")
    lines.append(f"  Visual OCR Row Y     : {_b(automation.get('visual_ocr_row_y'))}")
    lines.append(f"  Visual OCR Row Score : {_b(automation.get('visual_ocr_score'))}")
    
    # Phase 3E: Manual region diagnostics
    # Read from config dict in automation data if available
    m_reg_cfg = automation.get("config") or {}
    m_reg_enabled = m_reg_cfg.get("visual_ocr_manual_region_enabled", "N/A")
    lines.append(f"  Manual Region Enabled: {_b(m_reg_enabled)}")
    lines.append(f"  Manual Region Width  : {m_reg_cfg.get('manual_region_width_px', 'N/A')} px")
    lines.append(f"  Manual Region Height : {m_reg_cfg.get('manual_region_height_px', 'N/A')} px")
    
    # Saved profile status
    s_sell = m_reg_cfg.get("saved_regions_sell", False)
    s_buy = m_reg_cfg.get("saved_regions_buy", False)
    lines.append(f"  Saved Regions Profile: SELL={_b(s_sell)} BUY={_b(s_buy)}")

    # Calibration process status
    c_req = m_reg_cfg.get("calibration_required", False)
    c_can = m_reg_cfg.get("calibration_cancelled", False)
    lines.append(f"  Calibration Required : {_b(c_req)}")
    lines.append(f"  Calibration Cancelled: {_b(c_can)}")

    # Saved profile failure and retry status
    s_fail = m_reg_cfg.get("visual_ocr_saved_profile_failed", False)
    s_sug  = m_reg_cfg.get("visual_ocr_suggested_action", "none")
    s_ret  = m_reg_cfg.get("visual_ocr_retry_after_profile_fail", False)
    lines.append(f"  Saved Profile Failed : {_b(s_fail)}")
    lines.append(f"  Suggested Action     : {s_sug}")
    lines.append(f"  Retry After Failure  : {_b(s_ret)}")

    dbg = automation.get("visual_ocr_debug") or {}
    m_used = dbg.get("manual_region_used", False)
    m_src  = m_reg_cfg.get("manual_region_source", "n/a")
    lines.append(f"  Manual Region Used   : {_b(m_used)} ({m_src if m_used else 'N/A'})")
    if m_used:
        lines.append(f"  Manual Region Ratios : {dbg.get('manual_region_ratios')}")
        if "manual_qty_col_ratios" in dbg:
            lines.append(f"  Manual Qty Col Ratios: {dbg.get('manual_qty_col_ratios')}")
        if "manual_price_col_ratios" in dbg:
            lines.append(f"  Manual Price Col Ratios: {dbg.get('manual_price_col_ratios')}")
            
        m_w = dbg.get("manual_region_width_px")
        m_h = dbg.get("manual_region_height_px")
        if m_w is not None and m_h is not None:
            lines.append(f"  Manual Region Width Px: {m_w}")
            lines.append(f"  Manual Region Height Px: {m_h}")
            if m_h < 180:
                lines.append("  Manual Region Warning: region_too_short")

    lines.append(f"  Visual OCR Price X   : {automation.get('visual_ocr_price_x0')} to {automation.get('visual_ocr_price_x1')}")
    lines.append(f"  Visual OCR Qty X     : {automation.get('visual_ocr_qty_x0')} to {automation.get('visual_ocr_qty_x1')}")
    lines.append(f"  Visual OCR Blue Bands: {_b(automation.get('visual_ocr_blue_bands_found'))}")
    lines.append(f"  Visual OCR Section   : {_b(automation.get('visual_ocr_section_used'))}")
    lines.append(f"  Visual OCR Sec Y Min : {_b(automation.get('visual_ocr_section_y_min'))}")
    lines.append(f"  Visual OCR Sec Y Max : {_b(automation.get('visual_ocr_section_y_max'))}")
    dbg = automation.get("visual_ocr_debug") or {}
    lines.append(f"  Visual OCR Raw Bands : {len(dbg.get('raw_candidate_bands') or [])}")
    lines.append(f"  Visual OCR Rej Height: {len(dbg.get('rejected_bands_by_height') or [])}")
    lines.append(f"  Visual OCR Rej Offset: {len(dbg.get('rejected_bands_by_offset') or [])}")
    lines.append(f"  Visual OCR Rej Top   : {len(dbg.get('rejected_bands_by_top_edge') or [])}")
    lines.append(f"  Visual OCR Rej Bot   : {len(dbg.get('rejected_bands_by_bottom_edge') or [])}")
    lines.append(f"  Visual OCR Filtered  : {len(dbg.get('filtered_candidate_bands') or [])}")
    
    # Click diagnostics
    rc_attempts = automation.get("visual_ocr_rc_attempts", 0)
    if rc_attempts > 0:
        lines.append(f"  Visual OCR RC Attempts: {rc_attempts}")
        details = automation.get("visual_ocr_rc_attempt_details") or []
        for det in details:
            lines.append(f"    #{det.get('index')} point={det.get('point')} name={det.get('name')} menu_open={det.get('menu_open')}")
    
    menu_open = automation.get("visual_ocr_context_menu_open", False)
    lines.append(f"  Visual OCR Menu Open : {menu_open}")

    # Stability diagnostics
    lines.append(f"  Visual OCR Mod Hover : {automation.get('visual_ocr_modify_hover_ms', 0)} ms")
    lines.append(f"  Visual OCR Menu Recheck: {automation.get('visual_ocr_menu_recheck_before_modify', False)}")
    lines.append(f"  Visual OCR Menu Pre-Clk: {automation.get('visual_ocr_menu_open_before_modify_click', False)}")
    lines.append(f"  Visual OCR Mod Retry : {automation.get('visual_ocr_modify_retry_count', 0)}")

    rc_x = automation.get("visual_ocr_rc_x")
    rc_y = automation.get("visual_ocr_rc_y")
    if rc_x is not None:
        lines.append(f"  Visual OCR Right Clk : ({rc_x}, {rc_y})")
        
    # Corrected offsets display
    cfg_data = automation.get("config") or {}
    off_x = cfg_data.get("visual_ocr_modify_menu_offset_x", "N/A")
    off_y = cfg_data.get("visual_ocr_modify_menu_offset_y", "N/A")
    lines.append(f"  Visual OCR Mod Off   : ({off_x}, {off_y})")
    
    m_x = automation.get("visual_ocr_menu_x")
    m_y = automation.get("visual_ocr_menu_y")
    if m_x is not None:
        lines.append(f"  Visual OCR Mod Clk   : ({m_x}, {m_y})")
    
    # We used to calculate min_order_y here using 'data', but it's cleaner 
    # to have the detector provide it or just show N/A if missing.
    min_order_y = automation.get('visual_ocr_min_order_y', 'N/A')
    lines.append(f"  Visual OCR Min Ord Y : {min_order_y}")

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
    lines.append(f"  Visual OCR Qty Type  : {automation.get('visual_ocr_quantity_match_type', 'none')}")
    
    ocr_attempts = dbg.get("ocr_attempts") or []
    if ocr_attempts:
        lines.append(f"  Visual OCR OCR Attempts: {len(ocr_attempts)}")
        for i, att in enumerate(ocr_attempts[:3]):
            lines.append(f"    #{i+1} band={att.get('band')} marker={att.get('marker_matched')} p='{att.get('price_text')}' q='{att.get('quantity_text')}' score={att.get('score', 0)}")
    
    lines.append(f"  Visual OCR Qty Target: {automation.get('visual_ocr_quantity_target', 'N/A')}")
    lines.append(f"  Visual OCR Qty Norm  : {automation.get('visual_ocr_quantity_normalized', 'N/A')}")
    lines.append(f"  Visual OCR Qty Diff  : {automation.get('visual_ocr_quantity_diff', 'N/A')}")
    lines.append(f"  Visual OCR Qty Reason: {automation.get('visual_ocr_quantity_reason', 'none')}")
    
    # Phase 3F: Safety Guards
    lines.append("-" * 36)
    lines.append("SAFETY GUARDS")
    lines.append("-" * 36)
    lines.append(f"  Automation Run ID    : {automation.get('automation_run_id', 'N/A')}")
    lines.append(f"  Process PID          : {automation.get('process_pid', 'N/A')}")
    lines.append(f"  Running Guard        : {automation.get('automation_running_guard', 'N/A')}")
    lines.append(f"  Automation Cancelled : {_b(automation.get('automation_cancelled'))}")
    lines.append(f"  Paste Attempted      : {_b(automation.get('paste_attempted'))}")
    lines.append(f"  Paste Guard Consumed : {_b(automation.get('paste_guard_consumed'))}")
    lines.append(f"  Safe To Paste        : {_b(automation.get('safe_to_paste'))}")
    lines.append(f"  Paste Block Reason   : {automation.get('paste_block_reason', 'none')}")
    lines.append(f"  Foreground Win Handle: {automation.get('foreground_win_handle', '0')}")
    lines.append(f"  Foreground Win Title : {automation.get('foreground_win_title', 'N/A')}")
    lines.append(f"  Foreground Matches   : {_b(automation.get('foreground_matches_selected'))}")
    lines.append(f"  Context Menu Sent    : {_b(automation.get('context_menu_click_sent'))}")
    lines.append(f"  Modify Menu Sent     : {_b(automation.get('modify_menu_click_sent'))}")
    lines.append(f"  Price Pasted         : {_b(automation.get('price_pasted'))}")
    lines.append("-" * 36)
    
    best_rej = dbg.get("best_rejected_row")
    if best_rej and automation.get("status") != "unique_match":
        lines.append("  Visual OCR Best Rej. :")
        lines.append(f"    band={best_rej.get('band')} marker={best_rej.get('marker_matched')}")
        
        p_norm   = best_rej.get('normalized_price', 0.0)
        p_target = best_rej.get('target_price', 0.0)
        p_diff   = abs(p_norm - p_target)
        lines.append(f"    p='{best_rej.get('price_text')}' norm={p_norm} target={p_target} diff={p_diff:.1f}")
        
        q_norm   = best_rej.get('normalized_quantity', 0)
        q_target = best_rej.get('target_quantity', 0)
        q_type   = best_rej.get('quantity_match_type', 'none')
        lines.append(f"    q='{best_rej.get('quantity_text')}' norm={q_norm} target={q_target} type={q_type}")
        
        lines.append(f"    p_match={best_rej.get('price_match')} q_match={best_rej.get('quantity_match')} reason={best_rej.get('reject_reason')}")
    
    rej = dbg.get("marker_rejected_bands") or []
    if rej:
        lines.append(f"  Visual OCR Marker Rejected: {len(rej)}")
        for r in rej[:3]:
            lines.append(f"    band={r.get('band')} pix={r.get('marker_pixels')} rgb={r.get('marker_avg_rgb')}")

    if ocr_attempts:
        lines.append(f"  Visual OCR First Price Text: {ocr_attempts[0].get('price_text', 'N/A')}")
        lines.append(f"  Visual OCR First Qty Text: {ocr_attempts[0].get('quantity_text', 'N/A')}")
    dbg_path = automation.get("visual_ocr_debug_screenshot_path")
    if dbg_path:
        lines.append(f"  Visual OCR Debug Img : {dbg_path}")
    overlay_path = automation.get("visual_ocr_debug_overlay_path")
    if overlay_path:
        lines.append(f"  Visual OCR Overlay   : {overlay_path}")
    
    # Phase 3D: Backend details
    lines.append(f"  Visual OCR Backend   : {_b(automation.get('visual_ocr_backend'))}")
    lines.append(f"  Visual OCR Tesseract : {_b(automation.get('visual_ocr_tesseract_cmd'))}")
    ready = automation.get('visual_ocr_tesseract_ready')
    lines.append(f"  Visual OCR Tess Ready: {_b(ready)}")
    if not ready:
        lines.append(f"  Visual OCR PyTess    : {_b(automation.get('visual_ocr_pytesseract_available'))}")
        lines.append(f"  Visual OCR Suggest   : {_b(automation.get('visual_ocr_suggested_path'))}")

    lines.append(f"  Candidate Win Count  : {_b(automation.get('candidate_windows_count'))}")
    
    rej_wins = automation.get("rejected_windows") or []
    if rej_wins:
        lines.append("  Rejected Windows     :")
        for rw in rej_wins:
            lines.append(f"    - {rw.get('title')} — {rw.get('reason')}")
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
