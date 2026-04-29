import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class MarketScanDiagnostics:
    scan_id: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    mode: str = "Unknown"  # Simple or Advanced
    region_id: int = 0
    status: str = "Incomplete"
    
    # Worker Config & Category
    selected_category_worker: str = "Todos"
    selected_category_ui: str = "Todos"
    worker_config_snapshot: Dict[str, Any] = field(default_factory=dict)
    ui_config_at_filter_time: Dict[str, Any] = field(default_factory=dict)
    
    # Pipeline Counts
    raw_orders_count: int = 0
    grouped_type_ids_count: int = 0
    economic_candidates_count: int = 0
    initial_candidates_count: int = 0
    relevant_orders_initial_count: int = 0
    opps_initial_count: int = 0
    final_candidates_count: int = 0
    relevant_orders_enriched_count: int = 0
    opps_enriched_count: int = 0
    final_emitted_count: int = 0
    
    # Candidate Prefilter Stats
    viable_candidates_count: int = 0
    prefilter_removed_capital: int = 0
    prefilter_removed_margin: int = 0
    prefilter_removed_spread: int = 0
    prefilter_removed_profit: int = 0
    prefilter_removed_plex: int = 0
    
    # Candidate Distribution
    candidate_top_spread_min: float = 0.0
    candidate_top_spread_max: float = 0.0
    candidate_top_spread_avg: float = 0.0
    final_candidates_spread_min: float = 0.0
    final_candidates_spread_max: float = 0.0
    final_candidates_spread_avg: float = 0.0
    final_candidates_margin_min: float = 0.0
    final_candidates_margin_max: float = 0.0
    final_candidates_margin_avg: float = 0.0
    
    # Enrichment Diagnosis
    enriched_with_buy_count: int = 0
    enriched_with_sell_count: int = 0
    enriched_with_both_count: int = 0
    enriched_parse_input_sample: List[Dict[str, Any]] = field(default_factory=list)
    
    # UI Results
    ui_all_opportunities_count: int = 0
    ui_filtered_count: int = 0
    
    # Filter Diagnosis
    filter_diagnostics: Dict[str, Any] = field(default_factory=dict)
    dominant_filter: Optional[str] = None
    
    # Metadata & History Stats
    metadata_total: int = 0
    metadata_cached: int = 0
    metadata_fetched: int = 0
    metadata_failed: int = 0
    
    history_cache_hits: int = 0
    history_cache_misses: int = 0
    history_fetched: int = 0
    history_failed: int = 0
    history_dict_count: int = 0
    
    # Fallback info
    fallback_used: bool = False
    fallback_reason: str = ""
    fallback_kept_is_enriched_false: bool = False
    
    # Icon Stats
    icon_requests: int = 0
    icon_loaded: int = 0
    icon_failed: int = 0
    icon_cache_size: int = 0
    
    # Timings (seconds)
    market_orders_elapsed: float = 0.0
    grouping_elapsed: float = 0.0
    candidate_selection_elapsed: float = 0.0
    metadata_elapsed: float = 0.0
    history_elapsed: float = 0.0
    names_elapsed: float = 0.0
    parse_elapsed: float = 0.0
    total_elapsed: float = 0.0
    
    # Logs
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_report(self) -> str:
        duration = self.finished_at - self.started_at if self.finished_at > 0 else 0.0
        
        report = []
        report.append("==============================================")
        report.append("     EVE iT — MARKET COMMAND SCAN REPORT      ")
        report.append("==============================================")
        report.append(f"Scan ID:   {self.scan_id}")
        report.append(f"Status:    {self.status}")
        report.append(f"Mode:      {self.mode}")
        report.append(f"Region:    {self.region_id}")
        report.append(f"Duration:  {duration:.2f}s")
        report.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.started_at))}")
        report.append("")

        report.append("[PIPELINE COUNTS]")
        report.append(f"Raw Orders:               {self.raw_orders_count}")
        report.append(f"Grouped Types:            {self.grouped_type_ids_count}")
        report.append(f"Economic Candidates:      {self.economic_candidates_count}")
        report.append(f"Initial Candidates:       {self.initial_candidates_count}")
        report.append(f"Relevant Orders (Init):   {self.relevant_orders_initial_count}")
        report.append(f"Opps (Initial):           {self.opps_initial_count}")
        report.append(f"Final Candidates:         {self.final_candidates_count}")
        report.append(f"Relevant Orders (Enr):   {self.relevant_orders_enriched_count}")
        report.append(f"Opps (Enriched):          {self.opps_enriched_count}")
        report.append(f"Final Emitted:            {self.final_emitted_count}")
        report.append(f"UI Received:              {self.ui_all_opportunities_count}")
        report.append(f"UI Filtered Results:      {self.ui_filtered_count}")
        report.append("")

        report.append("[CANDIDATE PREFILTER]")
        report.append(f"Economic Candidates:      {self.economic_candidates_count}")
        report.append(f"Viable Candidates:        {self.viable_candidates_count}")
        report.append(f"Removed by Capital:       {self.prefilter_removed_capital}")
        report.append(f"Removed by Margin:        {self.prefilter_removed_margin}")
        report.append(f"Removed by Spread:        {self.prefilter_removed_spread}")
        report.append(f"Removed by Profit:        {self.prefilter_removed_profit}")
        report.append(f"Removed by PLEX:          {self.prefilter_removed_plex}")
        report.append(f"Top Cand. Spread (m/a/M): {self.candidate_top_spread_min:.1f} / {self.candidate_top_spread_avg:.1f} / {self.candidate_top_spread_max:.1f}")
        report.append(f"Final Spread (m/a/M):     {self.final_candidates_spread_min:.1f} / {self.final_candidates_spread_avg:.1f} / {self.final_candidates_spread_max:.1f}")
        report.append(f"Final Margin (m/a/M):     {self.final_candidates_margin_min:.1f} / {self.final_candidates_margin_avg:.1f} / {self.final_candidates_margin_max:.1f}")
        report.append("")

        if self.enriched_parse_input_sample:
            report.append("[ENRICHMENT DIAGNOSIS]")
            report.append(f"Types with Both B/S:      {self.enriched_with_both_count}")
            report.append(f"Types with Buy Only:      {self.enriched_with_buy_count}")
            report.append(f"Types with Sell Only:     {self.enriched_with_sell_count}")
            report.append("Sample Input to Parse (Top 5):")
            for item in self.enriched_parse_input_sample[:5]:
                report.append(f"  - ID {item.get('id')}: B={item.get('buy_count')} S={item.get('sell_count')} Spr={item.get('spread'):.1f}% Hist={item.get('has_history')}")
            report.append("")

        if self.filter_diagnostics:
            report.append("[FILTER DIAGNOSTICS]")
            report.append(f"Dominant Filter:          {str(self.dominant_filter).upper()}")
            report.append(f"Total Raw (at UI):        {self.filter_diagnostics.get('total_raw', 0)}")
            report.append(f"Pass Base Filter:         {self.filter_diagnostics.get('after_base', 0)}")
            report.append(f"Pass Category Filter:     {self.filter_diagnostics.get('after_category', 0)}")
            
            removed = self.filter_diagnostics.get("removed", {})
            if removed:
                report.append("--- Removal Reasons ---")
                for key, val in sorted(removed.items()):
                    if val > 0:
                        report.append(f"  - {key:20}: {val}")
        report.append("")

        report.append("[HISTORY & METADATA]")
        report.append(f"Metadata Total/Cached:    {self.metadata_total} / {self.metadata_cached}")
        report.append(f"Metadata Fetched/Failed:  {self.metadata_fetched} / {self.metadata_failed}")
        report.append(f"History Hits/Misses:      {self.history_cache_hits} / {self.history_cache_misses}")
        report.append(f"History Fetched/Failed:   {self.history_fetched} / {self.history_failed}")
        report.append(f"History Dict Size:        {self.history_dict_count}")
        report.append("")

        report.append("[ICONS]")
        report.append(f"Icon Requests:            {self.icon_requests}")
        report.append(f"Icon Loaded/Failed:       {self.icon_loaded} / {self.icon_failed}")
        report.append(f"Icon Cache Size:          {self.icon_cache_size}")
        report.append("")

        report.append("[WORKER CONFIG SNAPSHOT]")
        report.append(json.dumps(self.worker_config_snapshot, indent=2))
        report.append("")

        report.append("[UI CONFIG AT FILTER TIME]")
        report.append(json.dumps(self.ui_config_at_filter_time, indent=2))
        report.append("")

        report.append("[TIMINGS]")
        report.append(f"Market Orders:            {self.market_orders_elapsed:.2f}s")
        report.append(f"Grouping/Candidates:      {(self.grouping_elapsed + self.candidate_selection_elapsed):.2f}s")
        report.append(f"Metadata Fetch:           {self.metadata_elapsed:.2f}s")
        report.append(f"History Fetch:            {self.history_elapsed:.2f}s")
        report.append(f"Parse/Enrich:             {self.parse_elapsed:.2f}s")
        report.append(f"Total Worker Time:        {self.total_elapsed:.2f}s")
        report.append("")

        if self.fallback_used:
            report.append("[FALLBACK]")
            report.append(f"Fallback Used:            YES")
            report.append(f"Reason:                   {self.fallback_reason}")
            report.append(f"Kept is_enriched=False:   {self.fallback_kept_is_enriched_false}")
            report.append("")

        if self.warnings:
            report.append("[WARNINGS]")
            for w in self.warnings:
                report.append(f"! {w}")
            report.append("")

        if self.errors:
            report.append("[ERRORS]")
            for e in self.errors:
                report.append(f"X {e}")
            report.append("")

        if self.notes:
            report.append("[NOTES]")
            for n in self.notes:
                report.append(f"- {n}")
            report.append("")

        report.append("==============================================")
        report.append("             END OF REPORT                    ")
        report.append("==============================================")
        
        return "\n".join(report)
