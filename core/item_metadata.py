from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ItemCategory:
    id: str
    name: str
    keywords: List[str]
    group_ids: List[int] = None

# Definición de categorías principales para filtros
MARKET_CATEGORIES = [
    ItemCategory("ships", "Naves", ["Ship", "Frigate", "Cruiser", "Destroyer", "Battleship", "Industrial", "Mining"]),
    ItemCategory("modules", "Módulos", ["Module", "Launcher", "Turret", "Shield", "Armor", "Battery"]),
    ItemCategory("ammo", "Munición", ["Ammo", "Charge", "Script", "Frequency Crystal", "Hybrid Charge"]),
    ItemCategory("drones", "Drones", ["Drone", "Fighter"]),
    ItemCategory("rigs", "Rigs", ["Rig"]),
    ItemCategory("implants", "Implantes", ["Implant", "Hardwiring"]),
    ItemCategory("blueprints", "Planos (BPO/BPC)", ["Blueprint"]),
    ItemCategory("ore", "Minerales / Gas", ["Ore", "Mineral", "Ice", "Gas"]),
    ItemCategory("industry", "Industria / Salvamento", ["Salvage", "Component", "Datacore", "Decryptor", "Polymer"]),
    ItemCategory("skills", "Libros de Habilidades", ["Skill"]),
    ItemCategory("pi", "Planetary Interaction", ["Planetary"]),
    ItemCategory("abyssal", "Abisal / Especial", ["Abyssal", "Mutaplasmid", "Officer", "Deadspace"]),
]

class ItemMetadataHelper:
    @staticmethod
    def get_icon_url(type_id: int, is_blueprint: bool = False, is_copy: bool = False) -> str:
        """
        Retorna la URL del servidor de imágenes de EVE para un type_id.
        Maneja casos especiales para planos.
        """
        if is_blueprint or is_copy:
            return f"https://images.evetech.net/types/{type_id}/bp?size=64"
        return f"https://images.evetech.net/types/{type_id}/icon?size=64"

    @staticmethod
    def is_blueprint(item_name: str, type_id: int = 0) -> bool:
        """Heurística para detectar si un item es un plano."""
        return "Blueprint" in item_name

    @staticmethod
    def resolve_category(item_name: str) -> str:
        """Asigna una categoría simplificada basada en el nombre."""
        name_lower = item_name.lower()
        for cat in MARKET_CATEGORIES:
            for kw in cat.keywords:
                if kw.lower() in name_lower:
                    return cat.id
        return "other"

    @staticmethod
    def get_category_name(category_id: str) -> str:
        for cat in MARKET_CATEGORIES:
            if cat.id == category_id:
                return cat.name
        return "Otros"
