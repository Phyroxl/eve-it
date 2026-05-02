"""
ContractCostFallback: estimates average unit cost for items acquired via completed
item_exchange contracts, when no real WAC (CostBasisService) entry exists.

Priority rule: Real WAC always supersedes an estimate. An estimate is only saved
and used when CostBasisService.get_cost_basis(type_id) returns None.

Flow:
  1. refresh() is called by SyncWorker after WAC refresh, for SELL order type_ids missing WAC.
  2. Fetches character's completed item_exchange contracts where char is acceptor.
  3. For each acquired type_id, fetches ESI market history and picks the average price
     on the acquisition date (or nearest day within ±WINDOW_DAYS).
  4. Saves estimates to data/cache/contract_cost_estimates_{char_id}.json.
  5. get_estimate(type_id) returns the cached estimate for UI display.

Diagnostic logs: [CONTRACT COST FALLBACK] and [AVERAGE COST MISSING]
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("eve.contract_cost_fallback")


@dataclass
class ContractCostEstimate:
    type_id: int
    item_name: str
    estimated_unit_cost: float
    acquisition_date: str        # "YYYY-MM-DD"
    contract_id: int
    region_id: int
    exact_date_match: bool
    fallback_window_days: int
    historical_price: float
    source: str                  # "contract_historical_avg"
    created_at: str              # ISO timestamp
    updated_at: str              # ISO timestamp
    qty: int = 1


class ContractCostFallback:
    _instance: Optional["ContractCostFallback"] = None
    REGION_JITA: int = 10000002
    WINDOW_DAYS: int = 3

    def __init__(self):
        self._estimates: Dict[int, ContractCostEstimate] = {}
        self._loaded_char_id: Optional[int] = None

    @classmethod
    def instance(cls) -> "ContractCostFallback":
        if cls._instance is None:
            cls._instance = ContractCostFallback()
        return cls._instance

    # ──────────────────���──────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _cache_path(self, char_id: int) -> str:
        path = os.path.join("data", "cache")
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, f"contract_cost_estimates_{char_id}.json")

    def load_from_file(self, char_id: int) -> None:
        if self._loaded_char_id == char_id and self._estimates:
            return  # already loaded for this character
        self._loaded_char_id = char_id
        path = self._cache_path(char_id)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._estimates = {int(k): ContractCostEstimate(**v) for k, v in raw.items()}
            logger.info("[CCF] Loaded %d contract cost estimates for char %d", len(self._estimates), char_id)
        except Exception as e:
            logger.error("[CCF] Error loading estimates: %s", e)
            self._estimates = {}

    def save_to_file(self, char_id: int) -> None:
        path = self._cache_path(char_id)
        try:
            data = {str(k): asdict(v) for k, v in self._estimates.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[CCF] Error saving estimates: %s", e)

    # ─────────────────────────────────────────────���───────────────────────────
    # Public read
    # ─────────────────────────────────────────────────────────────────────────

    def get_estimate(self, type_id: int) -> Optional[ContractCostEstimate]:
        """Returns the cached estimate, or None if not available."""
        return self._estimates.get(type_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: market history lookup
    # ─────────────────────────────────────────────────────────────────────────

    def _get_historical_avg(
        self, esi, type_id: int, region_id: int, date_str: str
    ) -> Tuple[float, bool, int]:
        """
        Returns (price, exact_match, window_days_used).

        Queries ESI market history for the item, then:
        1. Returns the `average` price for date_str if present.
        2. Otherwise searches ±WINDOW_DAYS, returning the nearest day with data.
        3. Returns (0.0, False, 0) if no data found in the window.
        """
        try:
            history = esi.market_history(region_id, type_id)
            if not history:
                return 0.0, False, 0

            hist_map: Dict[str, float] = {
                entry["date"]: entry.get("average", 0.0)
                for entry in history
                if "date" in entry
            }

            # Exact match
            if date_str in hist_map and hist_map[date_str] > 0:
                return hist_map[date_str], True, 0

            # Window search ±WINDOW_DAYS
            try:
                target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return 0.0, False, 0

            for delta in range(1, self.WINDOW_DAYS + 1):
                for sign in (1, -1):
                    candidate = (target + timedelta(days=sign * delta)).strftime("%Y-%m-%d")
                    if candidate in hist_map and hist_map[candidate] > 0:
                        return hist_map[candidate], False, delta

            return 0.0, False, 0
        except Exception as e:
            logger.warning("[CCF] History fetch error type_id=%d: %s", type_id, e)
            return 0.0, False, 0

    # ─────────────────────────────────────────────────────────────────────────
    # Main refresh
    # ─────────────────────────────────────────────────────────────────────────

    def refresh(
        self,
        char_id: int,
        token: str,
        type_ids_needed: List[int],
        region_id: int = REGION_JITA,
    ) -> Dict[int, float]:
        """
        Fetches completed item_exchange contracts (character as acceptor) and
        estimates the unit cost of received items using ESI market history on
        the acquisition date.

        - Only processes type_ids_needed (items missing from WAC).
        - Never overwrites a real WAC cost.
        - Returns {type_id: estimated_unit_cost} for successfully estimated items.
        - Persists estimates to cache so subsequent calls use them directly.
        """
        from core.esi_client import ESIClient
        from core.cost_basis_service import CostBasisService

        if not type_ids_needed:
            return {}

        self.load_from_file(char_id)
        wac = CostBasisService.instance()

        # Filter out type_ids that already have real WAC — real cost always wins
        needed_set = {
            tid for tid in type_ids_needed
            if wac.get_cost_basis(tid) is None
        }
        if not needed_set:
            logger.info("[CCF] All type_ids have real WAC, skipping")
            return {}

        # Separate already-cached estimates from those still needing ESI calls
        still_needed = {tid for tid in needed_set if tid not in self._estimates}

        results: Dict[int, float] = {}
        for tid in needed_set - still_needed:
            est = self._estimates[tid]
            if est.estimated_unit_cost > 0:
                results[tid] = est.estimated_unit_cost
                logger.debug("[CCF] Cached estimate type_id=%d cost=%.0f", tid, est.estimated_unit_cost)

        if not still_needed:
            return results

        logger.info(
            "[CCF] refresh char=%d needed=%d still_uncached=%d region=%d",
            char_id, len(needed_set), len(still_needed), region_id,
        )

        esi = ESIClient()

        # ── Fetch completed contracts ───────────────────────���──────────────
        try:
            contracts = esi.character_contracts(char_id, token)
        except Exception as e:
            logger.warning("[CCF] Failed to fetch contracts: %s", e)
            return results
        if not contracts:
            logger.info("[CCF] No contracts for char %d", char_id)
            self._log_missing(still_needed, char_id, "no_contracts_returned")
            return results

        # Keep only: item_exchange, finished/deleted, character is acceptor
        relevant = [
            c for c in contracts
            if c.get("type") == "item_exchange"
            and c.get("status") in ("finished", "deleted")
            and c.get("acceptor_id") == char_id
        ]
        logger.info("[CCF] %d relevant contracts (acceptor, finished)", len(relevant))

        # ── Build acquisition map {type_id: [{date, qty, contract_id}]} ───
        acquisitions: Dict[int, List[dict]] = {}

        for contract in relevant:
            cid = contract.get("contract_id", 0)
            raw_date = contract.get("date_completed") or contract.get("date_accepted") or ""
            acq_date = raw_date[:10]  # "YYYY-MM-DD"
            if not acq_date:
                continue

            try:
                items = esi.contract_items(char_id, cid, token)
            except Exception as e:
                logger.debug("[CCF] contract_items cid=%d error: %s", cid, e)
                continue
            if not items:
                continue

            for item in items:
                tid = item.get("type_id")
                qty = item.get("quantity", 1)
                # is_included=True → seller provides to buyer (acceptor receives these)
                if not item.get("is_included", True):
                    continue
                if tid not in still_needed:
                    continue
                acquisitions.setdefault(tid, []).append(
                    {"date": acq_date, "qty": qty, "contract_id": cid}
                )

        logger.info("[CCF] Found acquisition data for %d/%d type_ids", len(acquisitions), len(still_needed))

        # ── Compute weighted average estimated cost per type_id ────────────
        now_str = datetime.now(timezone.utc).isoformat()

        for tid in still_needed:
            acq_list = acquisitions.get(tid, [])
            if not acq_list:
                logger.info(
                    "[AVERAGE COST MISSING] type_id=%d real_cost_found=False "
                    "contract_fallback_attempted=True contract_match_found=False "
                    "historical_price_found=False reason=no_contract_found",
                    tid,
                )
                continue

            total_qty = 0
            total_cost = 0.0
            best_contract_id = 0
            best_date = ""
            best_exact = False
            best_window = 0
            got_price = False

            for acq in acq_list:
                price, exact, window = self._get_historical_avg(esi, tid, region_id, acq["date"])
                if price <= 0:
                    continue
                got_price = True
                total_qty += acq["qty"]
                total_cost += price * acq["qty"]
                if not best_date or acq["date"] > best_date:
                    best_date = acq["date"]
                    best_contract_id = acq["contract_id"]
                    best_exact = exact
                    best_window = window

            if not got_price or total_qty == 0:
                logger.info(
                    "[AVERAGE COST MISSING] type_id=%d real_cost_found=False "
                    "contract_fallback_attempted=True contract_match_found=True "
                    "historical_price_found=False reason=no_history_in_window",
                    tid,
                )
                continue

            est_unit_cost = total_cost / total_qty

            estimate = ContractCostEstimate(
                type_id=tid,
                item_name=f"Type {tid}",
                estimated_unit_cost=est_unit_cost,
                acquisition_date=best_date,
                contract_id=best_contract_id,
                region_id=region_id,
                exact_date_match=best_exact,
                fallback_window_days=best_window,
                historical_price=est_unit_cost,
                source="contract_historical_avg",
                created_at=(
                    self._estimates[tid].created_at if tid in self._estimates else now_str
                ),
                updated_at=now_str,
                qty=total_qty,
            )
            self._estimates[tid] = estimate
            results[tid] = est_unit_cost

            logger.info(
                "[CONTRACT COST FALLBACK] character_id=%d type_id=%d "
                "contract_id=%d acquisition_date=%s historical_price=%.0f "
                "exact_date_match=%s fallback_window=%d "
                "estimated_unit_cost=%.0f source=contract_historical_avg",
                char_id, tid, best_contract_id, best_date,
                est_unit_cost, best_exact, best_window, est_unit_cost,
            )

        self.save_to_file(char_id)
        return results

    # ─────────────��────────────────────────────��──────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────���───────────────────────────────

    def _log_missing(self, type_ids, char_id: int, reason: str) -> None:
        for tid in type_ids:
            logger.info(
                "[AVERAGE COST MISSING] type_id=%d real_cost_found=False "
                "contract_fallback_attempted=True contract_match_found=False "
                "historical_price_found=False reason=%s",
                tid, reason,
            )
