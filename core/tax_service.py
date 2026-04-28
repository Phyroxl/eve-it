import logging
from dataclasses import dataclass
from core.esi_client import ESIClient
from core.auth_manager import AuthManager

logger = logging.getLogger('eve.tax_service')

@dataclass
class CharacterTaxes:
    sales_tax_pct: float
    broker_fee_pct: float
    accounting_lvl: int
    broker_relations_lvl: int
    is_estimated: bool = True
    status: str = "idle" # "ready", "missing_scope", "error"

class TaxService:
    _instance = None

    def __init__(self):
        self.char_taxes: dict[int, CharacterTaxes] = {}
        self.client = ESIClient()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = TaxService()
        return cls._instance

    def get_taxes(self, char_id: int) -> CharacterTaxes:
        return self.char_taxes.get(char_id, CharacterTaxes(8.0, 3.0, 0, 0, True, "idle"))

    def refresh_from_esi(self, char_id: int, token: str):
        logger.info(f"Refrescando Skills/Taxes para char={char_id}...")
        try:
            res = self.client.character_skills(char_id, token)
            
            if res == "missing_scope":
                logger.warning(f"Falta permiso de skills para {char_id}.")
                self.char_taxes[char_id] = CharacterTaxes(8.0, 3.0, 0, 0, True, "missing_scope")
                return False
                
            if not res:
                logger.warning("No se pudo obtener skills (error ESI).")
                self.char_taxes[char_id] = CharacterTaxes(8.0, 3.0, 0, 0, True, "error")
                return False

            skills = res.get('skills', [])
            acc_lvl = 0
            brk_lvl = 0
            
            for s in skills:
                if s['skill_id'] == 3444: acc_lvl = s['trained_skill_level']
                if s['skill_id'] == 3446: brk_lvl = s['trained_skill_level']

            # Cálculos EVE 2024
            sales_tax = 8.0 * (1.0 - 0.11 * acc_lvl)
            broker_fee = 3.0 - (0.1 * brk_lvl)

            self.char_taxes[char_id] = CharacterTaxes(
                sales_tax_pct=max(0.0, sales_tax),
                broker_fee_pct=max(0.0, broker_fee),
                accounting_lvl=acc_lvl,
                broker_relations_lvl=brk_lvl,
                is_estimated=False,
                status="ready"
            )
            logger.info(f"Taxes actualizados para {char_id}: Tax={sales_tax:.2f}%, Fee={broker_fee:.2f}%")
            return True
        except Exception as e:
            logger.error(f"Error calculando taxes: {e}")
            self.char_taxes[char_id] = CharacterTaxes(8.0, 3.0, 0, 0, True, "error")
            return False
