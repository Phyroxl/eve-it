import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from core.esi_client import ESIClient
from core.auth_manager import AuthManager
import os
import json

logger = logging.getLogger('eve.cost_basis')

@dataclass
class CostBasis:
    type_id: int
    average_buy_price: float
    total_quantity: int
    total_spent: float # Representa el valor del inventario actual a precio de coste
    last_updated: datetime
    confidence: str  # 'high', 'medium', 'low'

class CostBasisService:
    _instance = None
    
    def __init__(self):
        self.cache: Dict[int, CostBasis] = {}
        self.stock_map: Dict[str, dict] = {} # tid (str) -> {qty, cost}
        self.last_transaction_id = 0
        self.client = ESIClient()
        self.last_fetch_time = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = CostBasisService()
        return cls._instance

    def get_cost_basis(self, type_id: int) -> Optional[CostBasis]:
        return self.cache.get(type_id)

    def _get_cache_path(self, char_id: int):
        path = os.path.join("data", "cache")
        if not os.path.exists(path):
            os.makedirs(path)
        return os.path.join(path, f"cost_basis_v2_{char_id}.json")

    def load_from_file(self, char_id: int):
        path = self._get_cache_path(char_id)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.stock_map = data.get('stock_map', {})
                    self.last_transaction_id = data.get('last_transaction_id', 0)
                    logger.info(f"Loaded {len(self.stock_map)} items from cost basis cache.")
            except Exception as e:
                logger.error(f"Error loading cost basis cache: {e}")

    def save_to_file(self, char_id: int):
        path = self._get_cache_path(char_id)
        try:
            with open(path, 'w') as f:
                json.dump({
                    'stock_map': self.stock_map,
                    'last_transaction_id': self.last_transaction_id
                }, f)
        except Exception as e:
            logger.error(f"Error saving cost basis cache: {e}")

    def _rebuild_cache_from_map(self):
        new_cache = {}
        now = datetime.now()
        for tid_str, data in self.stock_map.items():
            if data['qty'] > 0:
                tid = int(tid_str)
                avg = data['cost'] / data['qty']
                new_cache[tid] = CostBasis(
                    type_id=tid,
                    average_buy_price=avg,
                    total_quantity=data['qty'],
                    total_spent=data['cost'],
                    last_updated=now,
                    confidence='high'
                )
        self.cache = new_cache
        self.last_fetch_time = now

    def get_item_diagnostics(self, type_id: int) -> dict:
        tid_str = str(type_id)
        data = self.stock_map.get(tid_str, {})
        cb = self.get_cost_basis(type_id)
        
        return {
            "type_id": type_id,
            "stock_map_qty": data.get("qty", 0),
            "stock_map_cost": data.get("cost", 0.0),
            "average_buy_price": cb.average_buy_price if cb else 0.0,
            "last_transaction_id": self.last_transaction_id,
            "in_cache": cb is not None,
            "source": "persistent_store" if tid_str in self.stock_map else "none"
        }

    def refresh_from_esi(self, char_id: int, token: str, current_assets: List[dict] = None):
        """
        Calcula el Coste Medio Ponderado (WAC) persistente.
        Solo procesa transacciones nuevas no vistas anteriormente.
        """
        logger.info(f"Refrescando WAC persistente para char={char_id} (assets_provided={current_assets is not None})...")
        try:
            self.load_from_file(char_id)
            
            transactions = self.client.wallet_transactions(char_id, token)
            if transactions == "missing_scope":
                logger.warning("Falta permiso esi-wallet.read_character_wallet.v1")
                return False
                
            # 1. Procesar nuevas transacciones si existen
            if transactions:
                new_txs = [t for t in transactions if t['transaction_id'] > self.last_transaction_id]
                if new_txs:
                    logger.info(f"Procesando {len(new_txs)} nuevas transacciones...")
                    # Ordenar por ID ascendente para flujo cronológico correcto
                    sorted_tx = sorted(new_txs, key=lambda x: x['transaction_id'])
                    
                    for t in sorted_tx:
                        tid_str = str(t['type_id'])
                        qty = t['quantity']
                        price = t['unit_price']
                        is_buy = t.get('is_buy', False)
                        
                        if tid_str not in self.stock_map:
                            self.stock_map[tid_str] = {'qty': 0, 'cost': 0.0}
                        
                        curr = self.stock_map[tid_str]
                        
                        if is_buy:
                            curr['qty'] += qty
                            curr['cost'] += (qty * price)
                        else:
                            if curr['qty'] > 0:
                                avg_unit = curr['cost'] / curr['qty']
                                curr['qty'] -= qty
                                if curr['qty'] <= 0:
                                    curr['qty'] = 0
                                    curr['cost'] = 0.0
                                    logger.info(f"Position closed for {tid_str} (sold all stock)")
                                else:
                                    curr['cost'] = curr['qty'] * avg_unit
                        
                        self.last_transaction_id = max(self.last_transaction_id, t['transaction_id'])

            # 2. Reconciliación opcional con activos reales
            if current_assets is not None:
                asset_qty_map = {}
                for a in current_assets:
                    tid = str(a['type_id'])
                    asset_qty_map[tid] = asset_qty_map.get(tid, 0) + a['quantity']
                
                reconciled_count = 0
                for tid_str, data in self.stock_map.items():
                    if data['qty'] > 0:
                        real_qty = asset_qty_map.get(tid_str, 0)
                        if real_qty == 0:
                            # RESET: No hay stock real del item, forzamos cierre de posición
                            logger.info(f"Reconcile RESET {tid_str}: item not in assets.")
                            data['qty'] = 0
                            data['cost'] = 0.0
                            reconciled_count += 1
                if reconciled_count > 0:
                    logger.info(f"Reconciled {reconciled_count} items (stock 0 in assets).")

            self.save_to_file(char_id)
            self._rebuild_cache_from_map()
            return True
            
        except Exception as e:
            logger.error(f"Error refrescando CostBasis (WAC) persistente: {e}")
            return False

    def has_wallet_scope(self) -> bool:
        auth = AuthManager.instance()
        return "esi-wallet.read_character_wallet.v1" in auth.scopes
