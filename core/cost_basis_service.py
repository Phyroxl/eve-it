import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
from core.esi_client import ESIClient
from core.auth_manager import AuthManager

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
        self.client = ESIClient()
        self.last_fetch_time = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = CostBasisService()
        return cls._instance

    def get_cost_basis(self, type_id: int) -> Optional[CostBasis]:
        return self.cache.get(type_id)

    def refresh_from_esi(self, char_id: int, token: str):
        """
        Calcula el Coste Medio Ponderado (WAC) del stock actual basado en transacciones.
        Procesa cronológicamente para que las ventas descuenten stock correctamente.
        """
        logger.info(f"Refrescando WAC para char={char_id}...")
        try:
            transactions = self.client.wallet_transactions(char_id, token)
            if not transactions:
                logger.warning("No se obtuvieron transacciones de la wallet.")
                return False

            if transactions == "missing_scope":
                logger.warning("Falta permiso esi-wallet.read_character_wallet.v1")
                return False

            # Ordenar por fecha ASCENDENTE (de más antigua a más reciente)
            # para procesar el flujo de stock correctamente.
            sorted_tx = sorted(transactions, key=lambda x: x['date'])
            
            # Estado temporal: type_id -> {qty, cost}
            stock_map = {}
            
            for t in sorted_tx:
                t_id = t['type_id']
                qty = t['quantity']
                price = t['unit_price']
                is_buy = t.get('is_buy', False)
                
                if t_id not in stock_map:
                    stock_map[t_id] = {'qty': 0, 'cost': 0.0}
                
                curr = stock_map[t_id]
                
                if is_buy:
                    # Añadir al stock y al coste total
                    curr['qty'] += qty
                    curr['cost'] += (qty * price)
                else:
                    # Venta: Reducir cantidad
                    if curr['qty'] > 0:
                        # El coste medio no cambia al vender, pero el coste total acumulado sí
                        avg_unit = curr['cost'] / curr['qty']
                        curr['qty'] -= qty
                        if curr['qty'] <= 0:
                            curr['qty'] = 0
                            curr['cost'] = 0.0
                        else:
                            curr['cost'] = curr['qty'] * avg_unit
                    else:
                        # Venta sin registro de compra previa: No podemos calcular coste negativo de forma fiable
                        pass

            # Generar caché final
            new_cache = {}
            now = datetime.now()
            for t_id, data in stock_map.items():
                if data['qty'] > 0:
                    avg = data['cost'] / data['qty']
                    new_cache[t_id] = CostBasis(
                        type_id=t_id,
                        average_buy_price=avg,
                        total_quantity=data['qty'],
                        total_spent=data['cost'],
                        last_updated=now,
                        confidence='high' if len(sorted_tx) > 20 else 'medium'
                    )
            
            self.cache = new_cache
            self.last_fetch_time = now
            logger.info(f"WAC actualizado: {len(self.cache)} items con stock activo.")
            return True
            
        except Exception as e:
            logger.error(f"Error refrescando CostBasis (WAC): {e}")
            return False

    def has_wallet_scope(self) -> bool:
        auth = AuthManager.instance()
        return "esi-wallet.read_character_wallet.v1" in auth.scopes
