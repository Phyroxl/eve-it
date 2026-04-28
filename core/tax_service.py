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
        char_key = str(char_id)
        # Buscar en cache o crear default
        base = self.char_taxes.get(char_id, CharacterTaxes(8.0, 3.0, 0, 0, "idle", {}, "idle"))
        
        # 1. Aplicar Overrides Globales de Personaje (Prioridad sobre skills)
        overrides = self._get_overrides_for_char(char_id)
        for ov in overrides:
            if "sales_tax_pct" in ov:
                base.sales_tax_pct = ov["sales_tax_pct"]
                base.source = "CALIBRADO MANUAL"
            if "broker_fee_pct" in ov and "location_id" not in ov:
                base.broker_fee_pct = ov["broker_fee_pct"]
                base.source = "CALIBRADO MANUAL"
        
        return base

    def _get_overrides_for_char(self, char_id: int) -> list[dict]:
        """Retorna una lista de dicts de overrides para el personaje, normalizando el formato."""
        import os
        from core.config_manager import _CONFIG_DIR
        path = _CONFIG_DIR / 'tax_overrides.json'
        
        char_key = str(char_id)
        if char_key not in self.overrides:
            # Reintentar con int si la clave fuera int (aunque JSON siempre tiene strings)
            # o buscar si alguna clave string coincide tras convertir
            found_val = None
            for k, v in self.overrides.items():
                if str(k) == char_key:
                    found_val = v
                    break
            if not found_val:
                return []
            val = found_val
        else:
            val = self.overrides[char_key]
        
        logger.info(f"[TAX] Overrides encontrados para char={char_id} (path={path})")
        
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            return [val]
        return []

    def get_effective_taxes(self, char_id: int, location_id: int, token: str):
        """
        Función CENTRAL para obtener taxes finales aplicables.
        Retorna (sales_tax, broker_fee, source, debug_info)
        """
        overrides = self._get_overrides_for_char(char_id)
        
        # 1. Sales Tax (Global)
        # Prioridad: Override por ubicación (si existe y tiene sales_tax_pct) > Override global > ESI
        sales_tax = None
        source_st = "ESI/Skills"
        
        # Primero buscar en overrides que tengan esta ubicación
        for ov in overrides:
            if str(ov.get("location_id")) == str(location_id) and "sales_tax_pct" in ov:
                sales_tax = ov["sales_tax_pct"]
                source_st = "CALIBRADO MANUAL (LOC)"
                break
        
        # Si no, buscar override global
        if sales_tax is None:
            for ov in overrides:
                if "sales_tax_pct" in ov and "location_id" not in ov:
                    sales_tax = ov["sales_tax_pct"]
                    source_st = "CALIBRADO MANUAL (GLOBAL)"
                    break
        
        if sales_tax is None:
            char_base = self.get_taxes(char_id)
            sales_tax = char_base.sales_tax_pct
            source_st = char_base.source

        # 2. Broker Fee (Depende de ubicación)
        broker_fee, source_bf = self.get_effective_broker_fee(char_id, location_id, token)
        
        final_source = source_st if "CALIBRADO" in source_st else source_bf
        if "CALIBRADO" in source_st and "CALIBRADO" in source_bf:
            final_source = "CALIBRADO MANUAL"
            
        debug_info = f"ST={sales_tax}% ({source_st}), BF={broker_fee}% ({source_bf})"
        logger.info(f"[TAX_DIAG] char={char_id} loc={location_id} -> {debug_info} | final_source={final_source}")
        
        return sales_tax, broker_fee, final_source, debug_info

    def refresh_from_esi(self, char_id: int, token: str):
        from core.config_manager import _CONFIG_DIR
        path = _CONFIG_DIR / 'tax_overrides.json'
        logger.info(f"[TAX_RELOAD] Iniciando refresco para char={char_id}...")
        logger.info(f"[TAX_RELOAD] Buscando overrides en: {path.absolute()}")
        logger.info(f"[TAX_RELOAD] Archivo existe: {path.exists()}")
        
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
            
            # Aplicar Overrides de Character (Prioridad Absoluta)
            overrides = self._get_overrides_for_char(char_id)
            for ov in overrides:
                if "sales_tax_pct" in ov:
                    sales_tax = ov["sales_tax_pct"]
                    source = "CALIBRADO MANUAL"
                    logger.info(f"[TAX] Override SALES TAX detectado: {sales_tax}%")

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
            logger.info(f"[TAX] Resultado Final char={char_id}: SalesTax={sales_tax}%, BrokerBase={base_broker_fee}%, Source={source}")
            return True
        except Exception as e:
            logger.error(f"Error refreshing TaxService: {e}")
            return False

    def get_effective_broker_fee(self, char_id: int, location_id: int, token: str) -> tuple[float, str]:
        """
        Retorna (tasa_fee_efectiva, descripcion_fuente)
        """
        overrides = self._get_overrides_for_char(char_id)
        
        # 1. Verificar Overrides específicos por ubicación (int o str)
        for ov in overrides:
            loc_match = False
            ov_loc = ov.get("location_id")
            if ov_loc is not None:
                if str(ov_loc) == str(location_id):
                    loc_match = True
            
            if loc_match and "broker_fee_pct" in ov:
                logger.info(f"[TAX] Aplicando override BROKER FEE LOC={location_id}: {ov['broker_fee_pct']}%")
                return ov["broker_fee_pct"], "CALIBRADO MANUAL"

        # 2. Verificar Override General de Broker Fee para el personaje
        for ov in overrides:
            if "broker_fee_pct" in ov and "location_id" not in ov:
                logger.info(f"[TAX] Usando override BROKER FEE BASE como efectivo: {ov['broker_fee_pct']}%")
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
