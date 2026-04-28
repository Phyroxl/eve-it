import logging
from dataclasses import dataclass
from core.esi_client import ESIClient
from core.auth_manager import AuthManager
from core.config_manager import load_tax_overrides

logger = logging.getLogger('eve.tax_service')

@dataclass
class CharacterTaxes:
    sales_tax_pct: float
    broker_fee_pct: float  # Base fee for the current character (skills only)
    accounting_lvl: int
    broker_relations_lvl: int
    status: str = "idle" 
    standings: dict = None # {entity_id: standing_value}
    standings_status: str = "idle"
    source: str = "ESTIMADO"

class TaxService:
    _instance = None

    def __init__(self):
        self.char_taxes: dict[int, CharacterTaxes] = {}
        self.client = ESIClient()
        self.location_cache = {} # {loc_id: {"corp": id, "faction": id, "type": "npc"|"structure"}}
        self.overrides = load_tax_overrides()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = TaxService()
        return cls._instance

    def get_taxes(self, char_id: int) -> CharacterTaxes:
        # 1. Verificar Overrides Globales (Si existen)
        char_key = str(char_id)
        if char_key in self.overrides:
            ov = self.overrides[char_key]
            # Si el override es para el character general (sin loc_id específico)
            if "sales_tax_pct" in ov and "location_id" not in ov:
                base = self.char_taxes.get(char_id, CharacterTaxes(8.0, 3.0, 0, 0, "idle", {}, "idle"))
                base.sales_tax_pct = ov["sales_tax_pct"]
                base.source = "CALIBRADO MANUAL"
                return base

        return self.char_taxes.get(char_id, CharacterTaxes(8.0, 3.0, 0, 0, "idle", {}, "idle"))

    def refresh_from_esi(self, char_id: int, token: str):
        logger.info(f"Refrescando Skills/Standings para char={char_id}...")
        self.overrides = load_tax_overrides() # Recargar al refrescar
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

            # Fórmulas EVE Actualizadas (v1.1.22)
            # Sales Tax: 8.0% base, -11% per Accounting level
            sales_tax = 8.0 * (1.0 - 0.11 * acc_lvl)
            # Broker Fee NPC: 3.0% base, -0.3% per Broker Relations level
            base_broker_fee = 3.0 - (0.3 * brk_lvl)

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

            source = "REAL ESI"
            if skill_status == "missing_scope": source = "FALTAN PERMISOS"
            
            # Aplicar Overrides de Character si existen
            char_key = str(char_id)
            if char_key in self.overrides:
                ov = self.overrides[char_key]
                if "sales_tax_pct" in ov:
                    sales_tax = ov["sales_tax_pct"]
                    source = "CALIBRADO MANUAL"

            self.char_taxes[char_id] = CharacterTaxes(
                sales_tax_pct=max(0.0, sales_tax),
                broker_fee_pct=max(0.0, base_broker_fee),
                accounting_lvl=acc_lvl,
                broker_relations_lvl=brk_lvl,
                status=skill_status,
                standings=standings,
                standings_status=standings_status,
                source=source
            )
            return True
        except Exception as e:
            logger.error(f"Error refreshing TaxService: {e}")
            return False

    def get_effective_broker_fee(self, char_id: int, location_id: int, token: str) -> tuple[float, str]:
        """
        Retorna (tasa_fee_efectiva, descripcion_fuente)
        """
        # 1. Verificar Overrides específicos por ubicación
        char_key = str(char_id)
        if char_key in self.overrides:
            ov = self.overrides[char_key]
            # Si el override coincide con la ubicación
            if ov.get("location_id") == location_id and "broker_fee_pct" in ov:
                return ov["broker_fee_pct"], "CALIBRADO MANUAL"

        taxes = self.get_taxes(char_id)
        br_lvl = taxes.broker_relations_lvl
        
        loc_info = self._get_location_info(location_id, token)
        
        if loc_info["type"] == "structure":
            return 1.0, "ESTRUCTURA (ESTIMADO)"

        if loc_info["type"] == "npc":
            # Fórmula real: 3.0% - 0.3%*BR - 0.03%*Faction - 0.02%*Corp
            fee = 3.0 - (0.3 * br_lvl)
            source = f"NPC (Skills Lvl {br_lvl})"
            
            if taxes.standings_status == "ready" and taxes.standings:
                f_id = loc_info.get("faction")
                c_id = loc_info.get("corp")
                f_std = taxes.standings.get(f_id, 0.0) if f_id else 0.0
                c_std = taxes.standings.get(c_id, 0.0) if c_id else 0.0
                
                reduction = (0.03 * f_std) + (0.02 * c_std)
                fee -= reduction
                source = "REAL ESI + STANDINGS"
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
                corp_id = data.get("owner")
                info["corp"] = corp_id
                # Obtener la facción de la corporación
                if corp_id:
                    c_info = self.client.corporation_info(corp_id)
                    if c_info:
                        info["faction"] = c_info.get("faction_id")
        elif loc_id > 1000000000: # Estructura
            data = self.client.universe_structures(loc_id, token)
            if data:
                info["type"] = "structure"
            else:
                info["type"] = "structure" 
        
        self.location_cache[loc_id] = info
        return info
