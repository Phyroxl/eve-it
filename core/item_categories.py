from typing import List, Dict, Set, Tuple

# ESI Category IDs:
# 6 = Ships
# 18 = Drones / Fighters
# 7 = Modules
# 8 = Charges (Ammo, Scripts, Crystals)
# 9 = Blueprints
# 16 = Skills (Drone Interfacing is here!)
# 20 = Implants
# 25 = Asteroids (Ore, Ice)
# 32 = Subsystems (Strategic Cruisers)
# 42 = Structure Modules
# 43 = Boosters
# 65 = Structures
# 91 = SKINs
# 30 = Apparel (Clothing)

# Group IDs específicos:
# 18 = Minerals (Tritanium, etc.)
# 1546 = Salvaged Materials
# 1982 = Abyssal Filaments

CATEGORY_MAPPING = {
    "Naves": {"categories": {6}}, # Ships (Strategic Cruisers category 32 excluded as requested)
    "Drones": {"categories": {18}}, # Drones & Fighters
    "Módulos": {
        "categories": {7, 42}, # Modules & Structure Modules
        "exclude_groups": {773, 774, 775, 776, 777, 778, 779, 780, 781, 782, 1137, 1159, 1308, 1136, 1158, 1206, 1226}
    },
    "Munición": {"categories": {8}},
    "Munición avanzada": {"categories": {8}, "keywords": ["Advanced", "Navy", "Faction", "T2", "Void", "Quake", "Javelin"]},
    "Minerales": {"groups": {18}},
    "Ore / Menas": {"categories": {25}}, # Asteroids (Ore/Ice)
    "Salvage": {"groups": {1546}},
    "Implants": {"categories": {20}},
    "Rigs": {"groups": {773, 774, 775, 776, 777, 778, 779, 780, 781, 782, 1137, 1159, 1308, 1136, 1158, 1206, 1226}},
    "Blueprints": {"categories": {9}},
    "Estructuras": {"categories": {65, 40, 22}},
    "Skins": {"categories": {91}},
    "Filamentos": {"groups": {1982}},
    "Boosters": {"categories": {43}},
    "Cargas / Scripts": {"groups": {907, 908, 909, 910, 911}},
}

def get_all_categories() -> List[str]:
    return ["Todos"] + list(CATEGORY_MAPPING.keys())

def is_type_in_category(category: str, category_id: int, group_id: int, item_name: str = "") -> Tuple[bool, str]:
    """
    Retorna (match, reason).
    Filtro ESTRICTO basado en metadatos reales de EVE.
    """
    if category == "Todos":
        return True, "Modo Todos"
    
    mapping = CATEGORY_MAPPING.get(category)
    if not mapping:
        return True, "Categoría no definida en mapping"

    # Si no hay metadatos fiables, EXCLUIR en modo estricto
    if category_id is None or group_id is None:
        return False, "Metadatos faltantes (Strict mode)"

    # 1. Verificar por IDs de Categoría
    if "categories" in mapping and category_id in mapping["categories"]:
        # Verificar exclusiones (ej: Rigs fuera de Módulos)
        if "exclude_groups" in mapping and group_id in mapping["exclude_groups"]:
            return False, f"Excluido por grupo ID {group_id}"
        
        # Verificar keywords solo si la categoría las requiere (ej: Munición avanzada)
        if "keywords" in mapping:
            match = any(kw.lower() in item_name.lower() for kw in mapping["keywords"])
            return match, "Coincidencia de keyword avanzada" if match else "Keyword avanzada no coincide"
            
        return True, f"Coincidencia por categoría ID {category_id}"

    # 2. Verificar por IDs de Grupo
    if "groups" in mapping and group_id in mapping["groups"]:
        return True, f"Coincidencia por grupo ID {group_id}"

    return False, "No pertenece a la categoría"
