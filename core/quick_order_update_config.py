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
    "enabled":                              False,
    "dry_run":                              True,
    "confirm_required":                     True,
    "open_market_delay_ms":                 1000,
    "focus_client_delay_ms":                700,
    "paste_price_delay_ms":                 300,
    "post_action_delay_ms":                 300,
    "restore_clipboard_after":              False,
    "client_window_title_contains":         "EVE",
    "use_pywinauto":                        True,
    "use_pyautogui_fallback":               False,
    "max_attempts":                         1,
    "require_window_selection":             True,
    "allow_title_fallback_without_selection": False,
    "exclude_self_app_windows":             True,
    "experimental_paste_enabled":           False,
    "paste_into_focused_window":            False,
    "clear_price_field_before_paste":       True,
    "paste_method":                         "ctrl+v",
    "pre_paste_delay_ms":                   300,
    "never_confirm_final_order":            True,
    # Phase 3: Modify Order preparation (safe defaults — disabled)
    "modify_order_step_enabled":                False,
    "modify_order_strategy":                    "manual_focus_guard",
    "modify_order_delay_ms":                    800,
    "require_modify_dialog_ready":              False,
    "paste_without_modify_dialog_verification": True,
    # Phase 3B: hotkey_experimental parameters (unconfigured and inactive by default)
    "modify_order_hotkey":                      "",
    "modify_order_verify_window_title_contains": "Modify Order",
    "modify_order_post_hotkey_delay_ms":        500,
    "allow_unverified_modify_order_paste":      False,
    # Phase 3C: visual_ocr strategy (disabled by default)
    "visual_ocr_enabled":                       False,
    "visual_ocr_require_unique_match":          True,
    "visual_ocr_match_price":                   True,
    "visual_ocr_match_quantity":                True,
    "visual_ocr_require_own_order_marker":      True,
    "visual_ocr_side_section_required":         True,
    "visual_ocr_allow_unverified_paste":        False,
    "visual_ocr_context_menu_delay_ms":         300,
    "visual_ocr_modify_dialog_delay_ms":        700,
    "visual_ocr_right_click_x_offset":          80,
    "visual_ocr_right_click_y_offset":          0,
    "visual_ocr_menu_click_mode":               "relative_to_right_click",
    "visual_ocr_menu_click_x_offset":           60,
    "visual_ocr_menu_click_y_offset":           85,
    "visual_ocr_debug_save_screenshot":         True,
    "visual_ocr_debug_dir":                     "data/debug/visual_ocr",
    # Phase 3C hardening: section y-axis ratios
    "visual_ocr_sell_section_y_min_ratio":      0.22,
    "visual_ocr_sell_section_y_max_ratio":      0.58,
    "visual_ocr_buy_section_y_min_ratio":       0.55,
    "visual_ocr_buy_section_y_max_ratio":       0.88,
    # Phase 3C hardening: column x-axis ratios
    "visual_ocr_qty_col_x_min_ratio":           0.38,
    "visual_ocr_qty_col_x_max_ratio":           0.52,
    "visual_ocr_price_col_x_min_ratio":         0.48,
    "visual_ocr_price_col_x_max_ratio":         0.68,
    # Phase 3C hardening: marker detection ratios
    "visual_ocr_marker_x_min_ratio":            0.20,
    "visual_ocr_marker_x_max_ratio":            0.32,
    "visual_ocr_marker_required":               True,
    # Phase 3C hardening: row height and padding
    "visual_ocr_min_row_height":                8,
    "visual_ocr_max_row_height":                28,
    "visual_ocr_row_crop_y_padding":            2,
    "visual_ocr_min_order_row_y_offset_from_section": 45,
    "visual_ocr_debug_save_crops":              True,
    "visual_ocr_debug_max_crops":               5,
    "visual_ocr_manual_region_enabled":          True,
    "visual_ocr_manual_region_prompt_each_time": False,
    "visual_ocr_manual_region_save_profile":     True,
    "visual_ocr_manual_qty_left_padding_px":     20,
    "visual_ocr_manual_qty_right_padding_px":    8,
    "visual_ocr_manual_price_left_padding_px":   8,
    "visual_ocr_manual_price_right_padding_px":  8,
    "visual_ocr_price_match_abs_tolerance":      15.0,
    "visual_ocr_price_match_rel_tolerance":      0.001,
    "visual_ocr_allow_quantity_suffix_match":    True,
    "visual_ocr_quantity_suffix_min_digits":     2,
    "visual_ocr_modify_menu_offset_x":           65,
    "visual_ocr_modify_menu_offset_y":           37,
    "visual_ocr_context_menu_delay_ms":          400,
    "visual_ocr_modify_dialog_delay_ms":         700,
    "visual_ocr_right_click_x_offset":           20,
    "visual_ocr_right_click_y_offset":           0,
}

_RATIO_KEYS = (
    "visual_ocr_sell_section_y_min_ratio",
    "visual_ocr_sell_section_y_max_ratio",
    "visual_ocr_buy_section_y_min_ratio",
    "visual_ocr_buy_section_y_max_ratio",
    "visual_ocr_qty_col_x_min_ratio",
    "visual_ocr_qty_col_x_max_ratio",
    "visual_ocr_price_col_x_min_ratio",
    "visual_ocr_price_col_x_max_ratio",
    "visual_ocr_marker_x_min_ratio",
    "visual_ocr_marker_x_max_ratio",
)

_DELAY_KEYS = (
    "open_market_delay_ms",
    "focus_client_delay_ms",
    "paste_price_delay_ms",
    "post_action_delay_ms",
    "pre_paste_delay_ms",
    "modify_order_delay_ms",
    "modify_order_post_hotkey_delay_ms",
    "visual_ocr_context_menu_delay_ms",
    "visual_ocr_modify_dialog_delay_ms",
)
_MAX_DELAY_MS = 30_000

_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "quick_order_update.json")
)
_REGIONS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "quick_order_update_regions.json")
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
                "restore_clipboard_after", "use_pywinauto", "use_pyautogui_fallback",
                "require_window_selection", "allow_title_fallback_without_selection",
                "exclude_self_app_windows"):
        if key in config:
            result[key] = bool(config[key])

    for key in ("experimental_paste_enabled", "paste_into_focused_window",
                "clear_price_field_before_paste",
                "modify_order_step_enabled", "require_modify_dialog_ready",
                "paste_without_modify_dialog_verification",
                "allow_unverified_modify_order_paste",
                "visual_ocr_enabled", "visual_ocr_require_unique_match",
                "visual_ocr_match_price", "visual_ocr_match_quantity",
                "visual_ocr_require_own_order_marker", "visual_ocr_side_section_required",
                "visual_ocr_allow_unverified_paste", "visual_ocr_debug_save_screenshot",
                "visual_ocr_marker_required", "visual_ocr_debug_save_crops",
                "visual_ocr_manual_region_enabled", "visual_ocr_manual_region_prompt_each_time",
                "visual_ocr_manual_region_save_profile"):
        if key in config:
            result[key] = bool(config[key])

    # Safety: always TRUE
    result["never_confirm_final_order"] = True

    # Validate paste_method
    if "paste_method" in config:
        val = str(config["paste_method"]).lower()
        if val in ("ctrl+v", "typewrite"):
            result["paste_method"] = val
        else:
            result["paste_method"] = "ctrl+v"

    # Validate modify_order_strategy
    if "modify_order_strategy" in config:
        val = str(config["modify_order_strategy"]).lower()
        if val in ("manual_focus_guard", "hotkey_experimental", "visual_ocr"):
            result["modify_order_strategy"] = val
        else:
            result["modify_order_strategy"] = "manual_focus_guard"

    # modify_order_hotkey: any string is valid (empty string = not configured)
    if "modify_order_hotkey" in config:
        result["modify_order_hotkey"] = str(config["modify_order_hotkey"])

    # modify_order_verify_window_title_contains: must be non-empty
    if "modify_order_verify_window_title_contains" in config:
        val = config["modify_order_verify_window_title_contains"]
        if isinstance(val, str) and val.strip():
            result["modify_order_verify_window_title_contains"] = val.strip()

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

    for key in ("visual_ocr_right_click_x_offset", "visual_ocr_right_click_y_offset",
                "visual_ocr_menu_click_x_offset", "visual_ocr_menu_click_y_offset",
                "visual_ocr_min_row_height", "visual_ocr_max_row_height",
                "visual_ocr_row_crop_y_padding", "visual_ocr_min_order_row_y_offset_from_section",
                "visual_ocr_debug_max_crops"):
        if key in config:
            try:
                result[key] = int(config[key])
            except (TypeError, ValueError):
                pass

    # visual_ocr_menu_click_mode: must be a recognised mode
    if "visual_ocr_menu_click_mode" in config:
        val = str(config["visual_ocr_menu_click_mode"]).lower()
        if val in ("relative_to_right_click", "absolute"):
            result["visual_ocr_menu_click_mode"] = val

    # visual_ocr_debug_dir: any non-empty string
    if "visual_ocr_debug_dir" in config:
        val = config["visual_ocr_debug_dir"]
        if isinstance(val, str) and val.strip():
            result["visual_ocr_debug_dir"] = val.strip()

    # Ratio keys: clamp to [0.0, 1.0]
    for key in _RATIO_KEYS:
        if key in config:
            try:
                result[key] = max(0.0, min(1.0, float(config[key])))
            except (TypeError, ValueError):
                pass

    return result


def load_quick_order_update_regions() -> dict:
    """Load manual OCR regions from separate file."""
    path = _REGIONS_PATH
    if not os.path.exists(path):
        return {"sell": None, "buy": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        _log.error(f"[QU CONFIG] error reading regions: {exc}")
        return {"sell": None, "buy": None}


def save_quick_order_update_regions(regions: dict) -> bool:
    """Save manual OCR regions to separate file."""
    path = _REGIONS_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(regions, f, indent=2)
        return True
    except Exception as exc:
        _log.error(f"[QU CONFIG] error saving regions: {exc}")
        return False
