"""
Config loader/validator for Quick Order Update automation.
Safe by design: creates defaults if missing, tolerates corrupt JSON.
"""
import json
import logging
import os
import time

_log = logging.getLogger('eve.market.quick_update.config')

_DEFAULT_CONFIG: dict = {
    "enabled":                     False,
    "dry_run":                     True,
    "confirm_required":            True,
    "open_market_delay_ms":        1000,
    "focus_client_delay_ms":       700,
    "paste_price_delay_ms":        300,
    "post_action_delay_ms":        300,
    "restore_clipboard_after":     False,
    "client_window_title_contains": "EVE",
    "use_pywinauto":               True,
    "use_pyautogui_fallback":      False,
    "max_attempts":                1,
}

_DELAY_KEYS = (
    "open_market_delay_ms",
    "focus_client_delay_ms",
    "paste_price_delay_ms",
    "post_action_delay_ms",
)
_MAX_DELAY_MS = 30_000

_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "quick_order_update.json")
)


def _config_path() -> str:
    return _CONFIG_PATH


def save_default_quick_order_update_config_if_missing() -> dict:
    """Create config file with defaults if it doesn't exist. Returns loaded config."""
    path = _config_path()
    if not os.path.exists(path):
        _write_default(path)
    return load_quick_order_update_config()


def _write_default(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_DEFAULT_CONFIG, f, indent=2)
    _log.info(f"[QU CONFIG] created default config at {path}")


def load_quick_order_update_config() -> dict:
    """Load and validate config. Creates defaults if missing. Tolerates corrupt JSON."""
    path = _config_path()
    if not os.path.exists(path):
        _write_default(path)
        return dict(_DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return validate_quick_order_update_config(data)
    except (json.JSONDecodeError, ValueError) as exc:
        _log.error(f"[QU CONFIG] corrupt config ({exc}) — renaming to .corrupt and recreating")
        ts = int(time.time())
        corrupt_path = f"{path}.corrupt.{ts}"
        try:
            os.rename(path, corrupt_path)
        except OSError:
            pass
        _write_default(path)
        return dict(_DEFAULT_CONFIG)
    except Exception as exc:
        _log.error(f"[QU CONFIG] error reading config: {exc} — using defaults")
        return dict(_DEFAULT_CONFIG)


def validate_quick_order_update_config(config: dict) -> dict:
    """Validate and sanitize config. Returns a complete, sanitized dict."""
    result = dict(_DEFAULT_CONFIG)

    for key in ("enabled", "dry_run", "confirm_required",
                "restore_clipboard_after", "use_pywinauto", "use_pyautogui_fallback"):
        if key in config:
            result[key] = bool(config[key])

    for key in _DELAY_KEYS:
        if key in config:
            try:
                val = int(config[key])
                result[key] = max(0, min(_MAX_DELAY_MS, val))
            except (TypeError, ValueError):
                pass

    if "max_attempts" in config:
        try:
            result["max_attempts"] = max(1, min(10, int(config["max_attempts"])))
        except (TypeError, ValueError):
            pass

    if "client_window_title_contains" in config:
        val = config["client_window_title_contains"]
        if isinstance(val, str) and val.strip():
            result["client_window_title_contains"] = val.strip()

    return result
