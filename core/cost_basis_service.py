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
    total_spent: float
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
        Descarga las transacciones de la wallet y calcula el coste promedio.
        Considera solo 'market_transaction' donde is_buy es True.
        """
        logger.info(f"Refrescando CostBasis para char={char_id}...")
        try:
            # esi-wallet.read_character_wallet.v1
            transactions = self.client.character_wallet_transactions(char_id, token)
            if not transactions:
                logger.warning("No se obtuvieron transacciones de la wallet.")
                return False

            # Agrupar por type_id
            temp_data = {} # type_id -> {total_isk, total_qty}
            
            for t in transactions:
                # ESI: 'is_buy': true significa que nosotros compramos el item (gasto de ISK)
                if t.get('is_buy'):
                    t_id = t['type_id']
                    qty = t['quantity']
                    unit_price = t['unit_price']
                    total_isk = qty * unit_price
                    
                    if t_id not in temp_data:
                        temp_data[t_id] = {'isk': 0.0, 'qty': 0}
                    
                    temp_data[t_id]['isk'] += total_isk
                    temp_data[t_id]['qty'] += qty

            # Calcular promedios
            new_cache = {}
            now = datetime.now()
            for t_id, data in temp_data.items():
                avg = data['isk'] / data['qty'] if data['qty'] > 0 else 0.0
                new_cache[t_id] = CostBasis(
                    type_id=t_id,
                    average_buy_price=avg,
                    total_quantity=data['qty'],
                    total_spent=data['isk'],
                    last_updated=now,
                    confidence='medium' # Podría ser 'high' si tenemos muchas transacciones
                )
            
            self.cache = new_cache
            self.last_fetch_time = now
            logger.info(f"CostBasis actualizado: {len(self.cache)} items calculados.")
            return True
            
        except Exception as e:
            logger.error(f"Error refrescando CostBasis: {e}")
            return False

    def has_wallet_scope(self) -> bool:
        auth = AuthManager.instance()
        # Verificamos si el token tiene el scope necesario
        # En una app real, decodificaríamos el JWT o usaríamos el verify endpoint
        # Por ahora, confiamos en lo que configuramos en AuthManager
        return "esi-wallet.read_character_wallet.v1" in auth.scopes
