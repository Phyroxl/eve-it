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
        from core.config_manager import _CONFIG_DIR
        path = _CONFIG_DIR / 'tax_overrides.json'
        
        overrides = self._get_overrides_for_char(char_id)
        
        # 1. Sales Tax
        sales_tax = None
        source_st = "ESI/Skills"
        
        # Prioridad 1: Override específico por ubicación
        for ov in overrides:
            if str(ov.get("location_id")) == str(location_id) and "sales_tax_pct" in ov:
                sales_tax = ov["sales_tax_pct"]
                source_st = "CALIBRADO MANUAL (LOC)"
                break
        
        # Prioridad 2: Override global del personaje (sin location_id)
        if sales_tax is None:
            for ov in overrides:
                if "sales_tax_pct" in ov and "location_id" not in ov:
                    sales_tax = ov["sales_tax_pct"]
                    source_st = "CALIBRADO MANUAL (GLOBAL)"
                    break
        
        # Prioridad 3: ESI / Skills
        if sales_tax is None:
            char_base = self.get_taxes(char_id)
            sales_tax = char_base.sales_tax_pct
            source_st = char_base.source

        # 2. Broker Fee
        broker_fee = None
        source_bf = "ESI/Skills"
        
        # Prioridad 1: Override específico por ubicación
        for ov in overrides:
            if str(ov.get("location_id")) == str(location_id) and "broker_fee_pct" in ov:
                broker_fee = ov["broker_fee_pct"]
                source_bf = "CALIBRADO MANUAL (LOC)"
                break
        
        # Prioridad 2: Override global del personaje (sin location_id)
        if broker_fee is None:
            for ov in overrides:
                if "broker_fee_pct" in ov and "location_id" not in ov:
                    broker_fee = ov["broker_fee_pct"]
                    source_bf = "CALIBRADO MANUAL (GLOBAL)"
                    break
        
        # Prioridad 3: ESI / Standings / NPC Formula
        if broker_fee is None:
            broker_fee, source_bf = self.get_effective_broker_fee(char_id, location_id, token)
        
        final_source = source_st if "CALIBRADO" in source_st else source_bf
        if "CALIBRADO" in source_st and "CALIBRADO" in source_bf:
            final_source = "CALIBRADO MANUAL"
            
        debug_info = f"ST={sales_tax}% ({source_st}), BF={broker_fee}% ({source_bf})"
        
        # DIAGNÓSTICO EN CONSOLA (una sola vez por combinación char+loc en esta sesión)
        _debug_key = (char_id, location_id)
        if not hasattr(self, '_debug_printed'):
            self._debug_printed = set()
        if _debug_key not in self._debug_printed:
            self._debug_printed.add(_debug_key)
            print(f"[TAX DEBUG] char_id={char_id} location_id={location_id}")
            print(f"[TAX DEBUG] overrides_path={path.absolute()} exists={path.exists()}")
            print(f"[TAX DEBUG] override_match={'True' if 'CALIBRADO' in final_source else 'False'} source={final_source}")
            print(f"[TAX DEBUG] final_sales_tax={sales_tax} final_broker_fee={broker_fee}")
        
        logger.info(f"[TAX_DIAG] char={char_id} loc={location_id} -> {debug_info} | final_source={final_source}")
        
        return sales_tax, broker_fee, final_source, debug_info

    def refresh_from_esi(self, char_id: int, token: str):
        from core.config_manager import _CONFIG_DIR
        path = _CONFIG_DIR / 'tax_overrides.json'
        logger.info(f"[TAX_RELOAD] Iniciando refresco para char={char_id}...")
        logger.info(f"[TAX_RELOAD] Buscando overrides en: {path.absolute()}")
        logger.info(f"[TAX_RELOAD] Archivo existe: {path.exists()}")
        
        self.overrides = load_tax_overrides() # Recargar al refrescar
        self._debug_printed = set()  # Resetear caché de debug para mostrar logs en este refresh
        self.location_cache = {}  # Forzar re-lookup de faction_id tras refresh de standings
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

            f_id = loc_info.get("faction")
            c_id = loc_info.get("corp")
            f_std = 0.0
            c_std = 0.0
            standings_applied = False

            if taxes.standings_status == "ready" and taxes.standings:
                f_std = taxes.standings.get(f_id, 0.0) if f_id else 0.0
                c_std = taxes.standings.get(c_id, 0.0) if c_id else 0.0
                reduction = (0.03 * f_std) + (0.02 * c_std)
                fee -= reduction
                source = "REAL ESI + STANDINGS"
                standings_applied = True
            elif taxes.standings_status == "missing_scope":
                source = "NPC (Skills sin Standings)"
            elif taxes.standings_status == "idle":
                source = f"NPC (Skills Lvl {br_lvl}, standings pendientes)"
                logger.warning(f"[TAX] standings_status=idle para char={char_id} al calcular broker fee. Llama a refresh_from_esi primero.")

            # Diagnóstico detallado una vez por (char, loc)
            _dbg_key = ("bf", char_id, location_id)
            if not hasattr(self, '_debug_printed'):
                self._debug_printed = set()
            if _dbg_key not in self._debug_printed:
                self._debug_printed.add(_dbg_key)
                reduction_val = (0.03 * f_std) + (0.02 * c_std) if standings_applied else 0.0
                print(f"[TAX DEBUG BF] char={char_id} loc={location_id}")
                print(f"[TAX DEBUG BF] br_lvl={br_lvl} -> base_fee={3.0 - 0.3*br_lvl:.4f}%")
                print(f"[TAX DEBUG BF] loc_type={loc_info['type']} corp_id={c_id} faction_id={f_id}")
                print(f"[TAX DEBUG BF] standings_status={taxes.standings_status} standings_keys={list(taxes.standings.keys()) if taxes.standings else []}")
                print(f"[TAX DEBUG BF] f_std={f_std} c_std={c_std} reduction={reduction_val:.4f}%")
                print(f"[TAX DEBUG BF] final_fee={max(0.0, fee):.4f}% source={source}")
                if f_id and taxes.standings and f_id not in taxes.standings:
                    print(f"[TAX DEBUG BF] WARNING: faction_id={f_id} NO encontrado en standings. Verifica que ESI devuelve standing para esta facción.")

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
                if corp_id:
                    c_info = self.client.corporation_info(corp_id)
                    if c_info:
                        info["faction"] = c_info.get("faction_id")
                    else:
                        logger.warning(f"[TAX] corporation_info falló para corp_id={corp_id} (loc={loc_id}). Sin reducción de facción.")
            else:
                logger.warning(f"[TAX] universe_stations falló para loc_id={loc_id}.")
        elif loc_id > 1000000000: # Estructura
            data = self.client.universe_structures(loc_id, token)
            if data:
                info["type"] = "structure"
            else:
                info["type"] = "structure"
                logger.info(f"[TAX] universe_structures no accesible para loc_id={loc_id} (privada o sin auth). Usando fee de estructura.")

        self.location_cache[loc_id] = info
        logger.info(f"[TAX] _get_location_info loc={loc_id} -> {info}")
        return info
