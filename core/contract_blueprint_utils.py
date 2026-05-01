from typing import Dict, Optional

def classify_blueprint_item(item_raw: dict, item_name: str, category_id: Optional[int] = None) -> str:
    """
    Classifies a contract item as BPO, BPC, or non-blueprint.
    Returns: "non_blueprint", "bpo", "bpc", "unknown_blueprint"
    """
    # ESI contract items endpoint provides is_blueprint_copy
    is_copy = item_raw.get('is_blueprint_copy')
    
    # Check if it's a blueprint by category or name
    is_bp_by_cat = (category_id == 9)
    is_bp_by_name = "Blueprint" in item_name
    
    if not is_bp_by_cat and not is_bp_by_name:
        return "non_blueprint"
        
    if is_copy is True:
        return "bpc"
    if is_copy is False:
        return "bpo"
        
    # If is_copy is missing, we try to guess from name
    if "Blueprint Copy" in item_name or " BPC" in item_name or "(Copy)" in item_name:
        return "bpc"
    
    # If we know it's a blueprint but don't know if it's a copy
    return "unknown_blueprint"

def should_exclude_blueprint(classification: str, config_exclude_bp: bool) -> bool:
    if not config_exclude_bp:
        return False
    return classification in ("bpo", "bpc", "unknown_blueprint")

def get_valuation_strategy(classification: str) -> str:
    """
    Returns: "market" (use jita price), "zero" (BPC valuation), "uncertain"
    """
    if classification == "non_blueprint":
        return "market"
    if classification == "bpo":
        # We only value BPOs if we are sure? Actually user said 
        # "Solo valorar como BPO si está clasificado de forma razonablemente segura como original."
        return "market"
    if classification == "bpc":
        return "zero"
    return "uncertain"
