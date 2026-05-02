import json
import os
from pathlib import Path
from core.market_models import FilterConfig, PerformanceConfig

_CONFIG_DIR = Path(__file__).resolve().parent.parent / 'config'
_MARKET_FILTERS_FILE = _CONFIG_DIR / 'market_filters.json'
_PERFORMANCE_FILE = _CONFIG_DIR / 'performance_config.json'

def save_market_filters(config: FilterConfig):
    """Guarda la configuración de filtros en un archivo JSON."""
    _CONFIG_DIR.mkdir(exist_ok=True)
    try:
        data = {
            "capital_max": config.capital_max,
            "capital_min": config.capital_min,
            "vol_min_day": config.vol_min_day,
            "margin_min_pct": config.margin_min_pct,
            "spread_max_pct": config.spread_max_pct,
            "exclude_plex": config.exclude_plex,
            "broker_fee_pct": config.broker_fee_pct,
            "sales_tax_pct": config.sales_tax_pct,
            "score_min": config.score_min,
            "risk_max": config.risk_max,
            "buy_orders_min": config.buy_orders_min,
            "sell_orders_min": config.sell_orders_min,
            "history_days_min": config.history_days_min,
            "profit_day_min": config.profit_day_min,
            "profit_unit_min": config.profit_unit_min,
            "require_buy_sell": config.require_buy_sell,
            "selected_category": config.selected_category,
            "max_item_types": config.max_item_types,
        }
        _MARKET_FILTERS_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Error guardando filtros: {e}")

def load_market_filters() -> FilterConfig:
    """Carga la configuración de filtros desde el archivo JSON o devuelve la por defecto."""
    if not _MARKET_FILTERS_FILE.exists():
        return FilterConfig()

    try:
        data = json.loads(_MARKET_FILTERS_FILE.read_text(encoding='utf-8'))
        
        # Defensive Migration: if max_item_types is 1, it's likely a legacy bug value.
        # We migrate it to 0 (no limit) unless the user specifically has 1 item in the file.
        if data.get("max_item_types") == 1:
            print("[MARKET CONFIG] Migrating legacy max_item_types=1 to 0 (No Limit)")
            data["max_item_types"] = 0
        # Deprecated UI inputs: broker_fee_pct and sales_tax_pct are now sourced from ESI at scan time.
        # Values in the file are kept for backward compatibility but will be overridden by ESI.
        _defaults = FilterConfig()
        for _deprecated in ('broker_fee_pct', 'sales_tax_pct'):
            if _deprecated in data and data[_deprecated] != getattr(_defaults, _deprecated):
                print(f"[MARKET CONFIG] deprecated UI setting loaded: {_deprecated}={data[_deprecated]} (will be overridden by ESI at scan time)")
        _defaults = FilterConfig()
        return FilterConfig(
            capital_max=data.get("capital_max", _defaults.capital_max),
            capital_min=data.get("capital_min", _defaults.capital_min),
            vol_min_day=data.get("vol_min_day", _defaults.vol_min_day),
            margin_min_pct=data.get("margin_min_pct", _defaults.margin_min_pct),
            spread_max_pct=data.get("spread_max_pct", _defaults.spread_max_pct),
            exclude_plex=data.get("exclude_plex", _defaults.exclude_plex),
            broker_fee_pct=data.get("broker_fee_pct", _defaults.broker_fee_pct),
            sales_tax_pct=data.get("sales_tax_pct", _defaults.sales_tax_pct),
            score_min=data.get("score_min", _defaults.score_min),
            risk_max=data.get("risk_max", _defaults.risk_max),
            buy_orders_min=data.get("buy_orders_min", _defaults.buy_orders_min),
            sell_orders_min=data.get("sell_orders_min", _defaults.sell_orders_min),
            history_days_min=data.get("history_days_min", _defaults.history_days_min),
            profit_day_min=data.get("profit_day_min", _defaults.profit_day_min),
            profit_unit_min=data.get("profit_unit_min", _defaults.profit_unit_min),
            require_buy_sell=data.get("require_buy_sell", _defaults.require_buy_sell),
            selected_category=data.get("selected_category", _defaults.selected_category),
            max_item_types=data.get("max_item_types", _defaults.max_item_types),
        )
    except Exception as e:
        print(f"Error cargando filtros: {e}")
        return FilterConfig()
def save_performance_config(config: PerformanceConfig):
    _CONFIG_DIR.mkdir(exist_ok=True)
    try:
        data = {
            "auto_refresh_enabled": config.auto_refresh_enabled,
            "refresh_interval_min": config.refresh_interval_min
        }
        _PERFORMANCE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Error guardando performance config: {e}")

def load_performance_config() -> PerformanceConfig:
    if not _PERFORMANCE_FILE.exists():
        return PerformanceConfig()
    try:
        data = json.loads(_PERFORMANCE_FILE.read_text(encoding='utf-8'))
        return PerformanceConfig(
            auto_refresh_enabled=data.get("auto_refresh_enabled", False),
            refresh_interval_min=data.get("refresh_interval_min", 5)
        )
    except Exception as e:
        print(f"Error cargando performance config: {e}")
        return PerformanceConfig()

def load_contracts_filters():
    from core.contracts_models import ContractsFilterConfig
    import json, os, dataclasses
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config', 'contracts_filters.json'))
    if not os.path.exists(path):
        cfg = ContractsFilterConfig()
        save_contracts_filters(cfg)
        return cfg
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        fields = {f.name for f in dataclasses.fields(ContractsFilterConfig)}
        return ContractsFilterConfig(**{k: v for k, v in data.items() if k in fields})
    except Exception:
        return ContractsFilterConfig()


def save_contracts_filters(config) -> None:
    import json, os, dataclasses
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config', 'contracts_filters.json'))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dataclasses.asdict(config), f, indent=2)

def save_ui_config(view_id: str, config: dict):
    """Guarda la configuración de la interfaz (columnas, etc.)"""
    _CONFIG_DIR.mkdir(exist_ok=True)
    file = _CONFIG_DIR / f'ui_{view_id}.json'
    try:
        file.write_text(json.dumps(config, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Error guardando ui config {view_id}: {e}")

def load_ui_config(view_id: str) -> dict:
    """Carga la configuración de la interfaz."""
    file = _CONFIG_DIR / f'ui_{view_id}.json'
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Error cargando ui config {view_id}: {e}")
        return {}

def save_tax_overrides(overrides: dict):
    _CONFIG_DIR.mkdir(exist_ok=True)
    file = _CONFIG_DIR / 'tax_overrides.json'
    try:
        file.write_text(json.dumps(overrides, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Error guardando tax overrides: {e}")

def load_tax_overrides() -> dict:
    file = _CONFIG_DIR / 'tax_overrides.json'
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Error cargando tax overrides: {e}")
        return {}
