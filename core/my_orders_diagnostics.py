import time
from datetime import datetime
from typing import Dict, Any, List

def format_my_orders_diagnostic_report(diag: Dict[str, Any], icon_diag: Dict[str, Any]) -> str:
    """
    Generates a detailed text report for My Orders diagnostics.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Header & Summary
    lines = [
        "==============================================",
        "     EVE iT — MY ORDERS DIAGNOSTIC REPORT      ",
        "==============================================",
        f"Timestamp:   {ts}",
        f"Char ID:     {diag.get('char_id', 'Unknown')}",
        f"Char Name:   {diag.get('char_name', 'Unknown').upper()}",
        f"Duration:    {diag.get('duration', 0):.2f}s",
        f"Status:      {diag.get('status', 'FINISHED')}",
        "",
        "[ORDERS SUMMARY]",
        f"Sell Orders Count:  {diag.get('sell_count', 0)}",
        f"Buy Orders Count:   {diag.get('buy_count', 0)}",
        f"Total Orders:       {diag.get('total_count', 0)}",
        f"Rows Sell Table:    {diag.get('rows_sell_table', 0)}",
        f"Rows Buy Table:     {diag.get('rows_buy_table', 0)}",
        "",
        "[TAXES]",
        f"Sales Tax:   {diag.get('sales_tax', '---')}%",
        f"Broker Fee:  {diag.get('broker_fee', '---')}%",
        f"Source:      {diag.get('tax_source', '---')}",
        f"Location ID: {diag.get('location_id', '---')}",
        "",
        "[COST BASIS (WAC)]",
        f"Cache File:      {diag.get('wac_cache_file', '---')}",
        f"Analyzed Items:  {diag.get('wac_item_count', 0)}",
        f"Last Tx ID:      {diag.get('wac_last_tx_id', 0)}",
        f"Cache Hit Rate:  {diag.get('wac_hit_rate', 0):.1f}%",
        f"Items Without Cost: {diag.get('wac_missing_count', 0)}",
    ]
    
    bs = diag.get("wac_backfill_stats", {})
    if bs:
        lines.extend([
            f"Backfill Count:  {bs.get('count', 0)} tx",
            f"Backfill Oldest: {bs.get('oldest', '---')}",
            f"Backfill Newest: {bs.get('newest', '---')}",
            f"Requested Days:  {bs.get('requested_days', 0)}",
        ])
    
    lines.extend([
        "",
        "[MARKET SYNCHRONIZATION]",
    ])
    
    mt = diag.get("market_timings", {})
    if mt:
        lines.extend([
            f"Source:         {mt.get('source', '---').upper()}",
            f"Force Refresh:  {mt.get('force_refresh', False)}",
            f"Type IDs Count: {mt.get('type_ids_count', '---')}",
            f"Types Fetched:  {mt.get('type_ids_fetched', '---')}",
            f"Types Failed:   {mt.get('type_ids_failed', '---')}",
            f"Cache Hit:      {mt.get('cache_hit', False)}",
            f"Cache Age:      {mt.get('cache_age_seconds', 0):.1f}s",
            f"Orders Count:   {mt.get('orders_count', 0):,}",
            f"Download Time:  {mt.get('total_elapsed', 0):.2f}s",
            f"Pages Total:    {mt.get('pages_total', 0)}",
            f"Pages Failed:   {mt.get('pages_failed', 0)}",
        ])
    else:
        lines.append("No market sync data available for this session.")
        
    lines.extend([
        "",
        "[ORDER STATE DEBUG — WATCHLIST]",
    ])
    
    watchlist = []
    all_orders = diag.get("all_orders", [])
    for o in all_orders:
        name = o.item_name.lower()
        state = o.analysis.state.lower()
        # Watchlist: Wasp I o cualquier orden superada
        if "wasp i" in name or "superada" in state:
            watchlist.append(o)
            
    if not watchlist:
        lines.append("No critical orders found in watchlist.")
    else:
        for o in watchlist[:15]:
            d = getattr(o, "_state_debug", {})
            lines.extend([
                f"Item:       {o.item_name} ({'BUY' if o.is_buy_order else 'SELL'})",
                f"Price:      {o.price:,.2f} ISK",
                f"Location:   {o.location_id}",
                f"Best Abs:   {o.analysis.best_buy if o.is_buy_order else o.analysis.best_sell:,.2f} ISK",
                f"Comp Price: {o.analysis.competitor_price:,.2f} ISK",
                f"State:      {o.analysis.state.upper()}",
                f"Competitive:{o.analysis.competitive}",
                f"Difference: {o.analysis.difference_to_best:,.2f} ISK",
                f"Counts:     LocBuy={d.get('market_orders_loc_buy_count', 0)}, LocSell={d.get('market_orders_loc_sell_count', 0)}, OwnExcluded={d.get('own_orders_excluded_count', 0)}",
                "----------------------------------------------"
            ])

    lines.extend([
        "",
        "[ICON SUMMARY]",
        f"Total Requests:     {icon_diag.get('requests', 0)}",
        f"Sell Requests:      {diag.get('sell_icon_requests', 0)}",
        f"Buy Requests:       {diag.get('buy_icon_requests', 0)}",
        f"Detail Requests:    {diag.get('detail_icon_requests', 0)}",
        f"Cache Hits:         {icon_diag.get('cache_hits', 0)}",
        f"Loaded Icons:       {icon_diag.get('loaded', 0)}",
        f"Failed Icons (All): {icon_diag.get('failed_count', 0)}",
        f"Placeholders Gen:   {icon_diag.get('placeholders', 0)}",
        f"Missing Type ID:    {len(diag.get('missing_type_id_items', []))}",
        "",
        "[ICON ENDPOINT SUCCESS]",
        f"/icon:     {icon_diag.get('endpoint_icon', 0)}",
        f"/render:   {icon_diag.get('endpoint_render', 0)}",
        f"/bp:       {icon_diag.get('endpoint_bp', 0)}",
        f"/bpc:      {icon_diag.get('endpoint_bpc', 0)}",
        f"/portrait: {icon_diag.get('endpoint_portrait', 0)}",
        "",
        "[TABLE CALLBACK DIAGNOSTICS]",
        f"Sell Immediate Applied: {diag.get('icon_immediate_applied_sell', 0)}",
        f"Buy Immediate Applied:  {diag.get('icon_immediate_applied_buy', 0)}",
        f"Sell Callback Direct:   {diag.get('icon_direct_applied_sell', 0)}",
        f"Sell Callback Fallback: {diag.get('icon_fallback_applied_sell', 0)}",
        f"Sell Callback Missed:   {diag.get('icon_missed_sell', 0)}",
        f"Buy Callback Direct:    {diag.get('icon_direct_applied_buy', 0)}",
        f"Buy Callback Fallback:  {diag.get('icon_fallback_applied_buy', 0)}",
        f"Buy Callback Missed:    {diag.get('icon_missed_buy', 0)}",
        f"Gen Skipped:            {diag.get('generation_skipped', 0)}",
        "",
        "[DASH CELL DIAGNOSTICS]",
        f"Sell Dash Cells: {len(diag.get('sell_dash_cells', []))}",
        f"Buy Dash Cells:  {len(diag.get('buy_dash_cells', []))}",
        "",
        "[ITEM COLUMN DIAGNOSTICS]",
        f"Sell Item Column: {diag.get('sell_item_col', 'Unknown')}",
        f"Buy Item Column:  {diag.get('buy_item_col', 'Unknown')}",
        f"Sell Header:      {diag.get('sell_header', 'Unknown')}",
        f"Buy Header:       {diag.get('buy_header', 'Unknown')}",
    ])
    
    # Failed/Missing Items
    missed = diag.get('missing_type_id_items', [])
    failed = diag.get('failed_items', [])
    callback_missed = diag.get('callback_missed_items', [])
    skipped = diag.get('skipped_items', [])
    
    all_troubled = []
    for item in missed: all_troubled.append({**item, "reason": "MISSING_TYPE_ID"})
    for item in failed: all_troubled.append({**item, "reason": "ICON_FAILED_ALL"})
    for item in callback_missed: all_troubled.append({**item, "reason": "CALLBACK_MISSED_CELL"})
    for item in skipped: all_troubled.append({**item, "reason": "GENERATION_SKIPPED"})
    
    if not all_troubled:
        lines.append("No troubled items found.")
    else:
        lines.append("[MISSING / PLACEHOLDER ICON ITEMS]")
        for i, item in enumerate(all_troubled[:50]):
            side = item.get('side', '???')
            name = item.get('item_name', 'Unknown')
            tid = item.get('type_id', '???')
            reason = item.get('reason', 'UNKNOWN')
            row = item.get('row', '???')
            lines.append(f"{i+1:2}. [{side}] {name} (ID {tid}) - Row {row} - Status: {reason}")

    # Dash Cells Sample
    lines.append("")
    lines.append("[DASH CELL DETAILS]")
    dash_cells = diag.get('sell_dash_cells', []) + diag.get('buy_dash_cells', [])
    if not dash_cells:
        lines.append("No cells with '-' found.")
    else:
        for i, cell in enumerate(dash_cells[:20]):
            lines.append(f"{i+1:2}. [{cell['side']}] Row {cell['row']} Col {cell['col']} ({cell['header']}) - TID {cell['type_id']} - Has Icon: {cell['has_icon']}")

    lines.append("")
    lines.append("[LAST ICON ERRORS]")
    errs = icon_diag.get("last_errors", [])
    if not errs:
        lines.append("No recent errors recorded.")
    else:
        for e in errs[-15:]:
            cleaned = e.replace("?size=24", "").replace("&size=24", "")
            lines.append(f"● {cleaned}")

    lines.append("")
    lines.append("[TYPE ID VALIDATION]")
    lines.append(f"Sell rows with type_id: {diag.get('sell_rows_with_tid', 0)}")
    lines.append(f"Buy rows with type_id:  {diag.get('buy_rows_with_tid', 0)}")

    lines.append("")
    lines.append("[NOTES]")
    for n in diag.get('notes', []):
        lines.append(f"- {n}")
    
    if not diag.get('notes'):
        lines.append("- Todos los procesos terminaron según lo esperado.")
        lines.append("- Si un item no tiene icono, es probable que no tenga imagen oficial en los servidores de EVE.")

    return "\n".join(lines)
