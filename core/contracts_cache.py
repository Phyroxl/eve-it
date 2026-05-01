import json
import os
import logging
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from core.contracts_models import ContractArbitrageResult

logger = logging.getLogger('eve.contracts_cache')

class ContractsCache:
    _instance = None
    _cache_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'contracts_analysis_cache.json')
    VERSION = "1.0.0"

    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_cache(self):
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Check version
                    if data.get("version") != self.VERSION:
                        logger.info(f"Contract cache version mismatch ({data.get('version')} vs {self.VERSION}). Invalidating.")
                        self.cache = {}
                    else:
                        self.cache = data.get("entries", {})
                logger.info(f"Loaded {len(self.cache)} entries from contract cache.")
            except Exception as e:
                logger.error(f"Error loading contract cache: {e}")
                self.cache = {}

    def save_cache(self):
        os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
        try:
            data = {
                "version": self.VERSION,
                "entries": self.cache
            }
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving contract cache: {e}")

    def get_entry(self, contract_id: int, items_raw: List[dict], price: float) -> Optional[dict]:
        """
        Retrieves a cached analysis result if it matches the current contract state.
        We use contract_id and a hash of price + item data.
        """
        cid_str = str(contract_id)
        if cid_str not in self.cache:
            return None
        
        entry = self.cache[cid_str]
        
        # Verify state
        current_hash = self._calculate_hash(items_raw, price)
        if entry.get("state_hash") == current_hash:
            return entry.get("analysis")
        
        return None

    def get_light_entry(self, contract_id: int) -> Optional[dict]:
        """
        Retrieves cached analysis without verifying hash. 
        Useful for early filtering (e.g. discard known blueprints).
        """
        cid_str = str(contract_id)
        if cid_str in self.cache:
            return self.cache[cid_str].get("analysis")
        return None

    def set_entry(self, contract_id: int, items_raw: List[dict], price: float, analysis: dict):
        cid_str = str(contract_id)
        state_hash = self._calculate_hash(items_raw, price)
        self.cache[cid_str] = {
            "state_hash": state_hash,
            "analysis": analysis
        }

    def _calculate_hash(self, items_raw: List[dict], price: float) -> str:
        # Sort items to ensure stable hash
        sorted_items = sorted(items_raw, key=lambda x: (x.get('type_id', 0), x.get('quantity', 0)))
        data_str = f"{price}|{json.dumps(sorted_items, sort_keys=True)}"
        return hashlib.md5(data_str.encode('utf-8')).hexdigest()

    def clear_expired(self, current_contracts: List[dict]):
        """Optional: remove entries that are no longer in the public list."""
        valid_ids = {str(c['contract_id']) for c in current_contracts}
        new_cache = {cid: entry for cid, entry in self.cache.items() if cid in valid_ids}
        if len(new_cache) != len(self.cache):
            self.cache = new_cache
            self.save_cache()
