import logging
from dataclasses import dataclass
from core.esi_client import ESIClient
from core.auth_manager import AuthManager

logger = logging.getLogger('eve.tax_service')

@dataclass
class CharacterTaxes:
    sales_tax_pct: float
    broker_fee_pct: float # Base skill-only fee for fallback
    accounting_lvl: int
    broker_relations_lvl: int
    status: str = "idle" 
    standings: dict = None # {entity_id: standing_value}
    standings_status: str = "idle"

class TaxService:
    _instance = None

    def __init__(self):
        self.char_taxes: dict[int, CharacterTaxes] = {}
        self.client = ESIClient()
        self.location_cache = {} # {loc_id: {"corp": id, "faction": id, "type": "npc"|"structure"}}

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = TaxService()
        return cls._instance

    def get_taxes(self, char_id: int) -> CharacterTaxes:
        return self.char_taxes.get(char_id, CharacterTaxes(8.0, 3.0, 0, 0, "idle", {}, "idle"))

    def refresh_from_esi(self, char_id: int, token: str):
        logger.info(f"Refrescando Skills/Standings para char={char_id}...")
        try:
            # 1. REFRESH SKILLS
            s_res = self.client.character_skills(char_id, token)
            acc_lvl, brk_lvl = 0, 0
            skill_status = "ready"
            
            if s_res == "missing_scope":
                skill_status = "missing_scope"
            elif not s_res:
                skill_status = "error"
            else:
                for s in s_res.get('skills', []):
                    if s['skill_id'] == 3444: acc_lvl = s['trained_skill_level']
                    if s['skill_id'] == 3446: brk_lvl = s['trained_skill_level']

            sales_tax = 8.0 * (1.0 - 0.11 * acc_lvl)
            base_broker_fee = 3.0 - (0.1 * brk_lvl)

            # 2. REFRESH STANDINGS
            std_res = self.client.character_standings(char_id, token)
            standings = {}
            standings_status = "ready"
            
            if std_res == "missing_scope":
                standings_status = "missing_scope"
            elif not std_res:
                standings_status = "error"
            else:
                for s in std_res:
                    standings[s['from_id']] = s['standing']

            self.char_taxes[char_id] = CharacterTaxes(
                sales_tax_pct=max(0.0, sales_tax),
                broker_fee_pct=max(0.0, base_broker_fee),
                accounting_lvl=acc_lvl,
                broker_relations_lvl=brk_lvl,
                status=skill_status,
                standings=standings,
                standings_status=standings_status
            )
            return True
        except Exception as e:
            logger.error(f"Error refreshing TaxService: {e}")
            return False

    def get_effective_broker_fee(self, char_id: int, location_id: int, token: str) -> tuple[float, str]:
        """
        Retorna (tasa_fee, descripcion_fuente)
        """
        taxes = self.get_taxes(char_id)
        br_lvl = taxes.broker_relations_lvl
        
        # 1. Identificar ubicación
        loc_info = self._get_location_info(location_id, token)
        
        if loc_info["type"] == "structure":
            return 1.0, "ESTRUCTURA (ESTIMADO)" # Upwell suele ser 1.0% o variable. Fallback 1%.

        if loc_info["type"] == "npc":
            # Fórmula: 3.0% - 0.1%*BR - 0.03%*Faction - 0.02%*Corp
            fee = 3.0 - (0.1 * br_lvl)
            source = f"NPC (Skills Lvl {br_lvl})"
            
            if taxes.standings_status == "ready" and taxes.standings:
                f_id = loc_info.get("faction")
                c_id = loc_info.get("corp")
                f_std = taxes.standings.get(f_id, 0.0) if f_id else 0.0
                c_std = taxes.standings.get(c_id, 0.0) if c_id else 0.0
                
                reduction = (0.03 * f_std) + (0.02 * c_std)
                fee -= reduction
                source = "NPC + STANDINGS"
            elif taxes.standings_status == "missing_scope":
                source = "NPC (Skills sin Standings)"
            
            return max(0.0, fee), source

        return taxes.broker_fee_pct, "FALLBACK (SKILLS)"

    def _get_location_info(self, loc_id: int, token: str):
        if loc_id in self.location_cache:
            return self.location_cache[loc_id]
        
        info = {"corp": None, "faction": None, "type": "unknown"}
        
        if loc_id < 100000000: # Estación NPC
            data = self.client.universe_stations(loc_id)
            if data:
                info["type"] = "npc"
                info["corp"] = data.get("owner")
                # Las facciones no siempre vienen en el station endpoint directo, pero podemos inferir o ignorar si no está.
                # Para simplificar, solo usaremos la corp de la estación si no tenemos facción.
            else:
                info["type"] = "unknown"
        elif loc_id > 1000000000: # Estructura
            # Esto requiere token y a veces falla si no se tiene permiso de la estructura
            data = self.client.universe_structures(loc_id, token)
            if data:
                info["type"] = "structure"
            else:
                info["type"] = "structure" # Si falla, asumimos estructura por ID alto
        
        self.location_cache[loc_id] = info
        return info
