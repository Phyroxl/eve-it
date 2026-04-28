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
            "profit_day_min": config.profit_day_min
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
        return FilterConfig(
            capital_max=data.get("capital_max", 500_000_000.0),
            vol_min_day=data.get("vol_min_day", 20),
            margin_min_pct=data.get("margin_min_pct", 5.0),
            spread_max_pct=data.get("spread_max_pct", 40.0),
            exclude_plex=data.get("exclude_plex", True),
            broker_fee_pct=data.get("broker_fee_pct", 3.0),
            sales_tax_pct=data.get("sales_tax_pct", 8.0),
            score_min=data.get("score_min", 0.0),
            risk_max=data.get("risk_max", 3),
            buy_orders_min=data.get("buy_orders_min", 0),
            sell_orders_min=data.get("sell_orders_min", 0),
            history_days_min=data.get("history_days_min", 0),
            profit_day_min=data.get("profit_day_min", 0.0)
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
