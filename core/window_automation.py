"""
Experimental EVE window automation for Quick Order Update — Phase 2.

SAFETY INVARIANTS (never violated):
  - Disabled by default (config["enabled"] must be True to do anything)
  - Dry-run by default (config["dry_run"] must be False to touch the OS)
  - NEVER performs the final confirm/accept action on an EVE order
  - pywinauto and pyautogui are optional — app does not break without them
  - No hardcoded pixel coordinates in this phase
"""

import logging
import time
from typing import Optional

_log = logging.getLogger('eve.market.window_automation')

# ── optional imports (never required) ──────────────────────────────────────
try:
    import pywinauto as _pywinauto          # noqa: F401
    _PYWINAUTO_AVAILABLE = True
except ImportError:
    _PYWINAUTO_AVAILABLE = False

try:
    import pyautogui as _pyautogui          # noqa: F401
    _PYAUTOGUI_AVAILABLE = True
except ImportError:
    _PYAUTOGUI_AVAILABLE = False

try:
    from PIL import ImageGrab as _ImageGrab
    _PIL_IMAGEGRAB_AVAILABLE = True
except ImportError:
    _ImageGrab = None
    _PIL_IMAGEGRAB_AVAILABLE = False

# ── Window scoring ──────────────────────────────────────────────────────────
# These strings identify the *own* EVE iT application — must never be auto-selected
_SELF_APP_MARKERS = ["EVE iT", "Market Command", "Quick Order Update"]

# Positive score rules for EVE Online client windows (first match wins)
_EVE_SCORE_RULES = [
    ("EVE -", 100),      # "EVE - Character Name" — most specific
    ("EVE Online", 80),
    ("EVE", 60),
]


def _score_window(title: str) -> tuple:
    """Return (score: int, is_self_app: bool) for a window title."""
    is_self = any(m in title for m in _SELF_APP_MARKERS)
    if is_self:
        return -100, True
    for pattern, pts in _EVE_SCORE_RULES:
        if pattern in title:
            return pts, False
    return 0, False


def _win32_get_title(handle: int) -> str:
    """Fast window title lookup via ctypes — no Application connection needed."""
    try:
        import ctypes
        length = ctypes.windll.user32.GetWindowTextLengthW(handle) + 1
        if length <= 1:
            return ""
        buf = ctypes.create_unicode_buffer(length)
        ctypes.windll.user32.GetWindowTextW(handle, buf, length)
        return buf.value
    except Exception:
        return ""


def _win32_get_class(handle: int) -> str:
    """Fast window class name lookup via ctypes."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(handle, buf, 256)
        return buf.value
    except Exception:
        return ""


def list_candidate_windows(config: Optional[dict] = None) -> list:
    """
    List all visible windows as automation candidates.

    Returns a list sorted by score descending:
      {
        "handle":      int,
        "title":       str,
        "class_name":  str,
        "visible":     bool,
        "is_self_app": bool,   # True if this is the EVE iT app itself
        "score":       int,    # higher = better EVE client candidate
      }

    Requires pywinauto. Returns [] if not available or on error.
    """
    if not _PYWINAUTO_AVAILABLE:
        _log.debug("[AUTOMATION] list_candidate_windows: pywinauto not available")
        return []
    try:
        from pywinauto import findwindows
        handles = findwindows.find_windows(visible_only=True)
        candidates = []
        for handle in handles:
            title = _win32_get_title(handle)
            if not title.strip():
                continue
            class_name = _win32_get_class(handle)
            score, is_self = _score_window(title)
            candidates.append({
                "handle":      handle,
                "title":       title,
                "class_name":  class_name,
                "visible":     True,
                "is_self_app": is_self,
                "score":       score,
            })
        candidates.sort(key=lambda c: c["score"], reverse=True)
        _log.debug(f"[AUTOMATION] found {len(candidates)} candidate windows")
        return candidates
    except Exception as exc:
        _log.warning(f"[AUTOMATION] list_candidate_windows error: {exc}")
        return []


class EVEWindowAutomation:
    """
    Experimental automation assistant for Quick Order Update.

    Safety invariants:
    - never confirms or accepts the final order change
    - disabled unless config["enabled"] is True
    - dry-run mode only logs steps without touching anything
    - uses selected_window by handle when provided; falls back to title search
      only if allow_title_fallback_without_selection=True in config
    """

    def __init__(self, config: dict):
        self.enabled              = bool(config.get("enabled",                              False))
        self.dry_run              = bool(config.get("dry_run",                              True))
        self.confirm_required     = bool(config.get("confirm_required",                     True))
        self.open_market_delay    = int(config.get("open_market_delay_ms",                  1000))
        self.focus_delay          = int(config.get("focus_client_delay_ms",                 700))
        self.paste_delay          = int(config.get("paste_price_delay_ms",                  300))
        self.post_delay           = int(config.get("post_action_delay_ms",                  300))
        self.restore_clipboard    = bool(config.get("restore_clipboard_after",              False))
        self.window_title         = config.get("client_window_title_contains",              "EVE")
        self.use_pywinauto        = bool(config.get("use_pywinauto",                        True))
        self.use_pyautogui_fb     = bool(config.get("use_pyautogui_fallback",               False))
        self.max_attempts         = int(config.get("max_attempts",                          1))
        self.require_selection    = bool(config.get("require_window_selection",             True))
        self.allow_title_fallback = bool(config.get("allow_title_fallback_without_selection", False))
        self.exclude_self         = bool(config.get("exclude_self_app_windows",             True))
        self.exp_paste_enabled    = bool(config.get("experimental_paste_enabled",           False))
        self.paste_into_focused   = bool(config.get("paste_into_focused_window",            False))
        self.clear_before_paste   = bool(config.get("clear_price_field_before_paste",       True))
        self.paste_method         = str(config.get("paste_method",                          "ctrl+v"))
        self.pre_paste_delay      = int(config.get("pre_paste_delay_ms",                    300))
        self.never_confirm        = bool(config.get("never_confirm_final_order",            True))
        # Phase 3: Modify Order preparation
        self.modify_order_step_enabled   = bool(config.get("modify_order_step_enabled",                False))
        self.modify_order_strategy       = str(config.get("modify_order_strategy",                     "manual_focus_guard"))
        self.modify_order_delay          = int(config.get("modify_order_delay_ms",                     800))
        self.require_modify_dialog_ready = bool(config.get("require_modify_dialog_ready",              False))
        self.paste_without_modify_verify = bool(config.get("paste_without_modify_dialog_verification", True))
        # Phase 3B: hotkey_experimental parameters
        self.modify_order_hotkey           = str(config.get("modify_order_hotkey",                      ""))
        self.modify_verify_title           = str(config.get("modify_order_verify_window_title_contains", "Modify Order"))
        self.modify_post_hotkey_delay      = int(config.get("modify_order_post_hotkey_delay_ms",         500))
        self.allow_unverified_modify_paste = bool(config.get("allow_unverified_modify_order_paste",      False))
        # Phase 3C: visual_ocr strategy
        self.visual_ocr_enabled               = bool(config.get("visual_ocr_enabled",                     False))
        self.visual_ocr_require_unique_match  = bool(config.get("visual_ocr_require_unique_match",         True))
        self.visual_ocr_match_price           = bool(config.get("visual_ocr_match_price",                  True))
        self.visual_ocr_match_quantity        = bool(config.get("visual_ocr_match_quantity",               True))
        self.visual_ocr_require_own_marker    = bool(config.get("visual_ocr_require_own_order_marker",     True))
        self.visual_ocr_side_section_required = bool(config.get("visual_ocr_side_section_required",        True))
        self.visual_ocr_allow_unverified_paste = bool(config.get("visual_ocr_allow_unverified_paste",      False))
        self.visual_ocr_context_menu_delay    = int(config.get("visual_ocr_context_menu_delay_ms",         300))
        self.visual_ocr_modify_dialog_delay   = int(config.get("visual_ocr_modify_dialog_delay_ms",        700))
        self.visual_ocr_rc_x_offset          = int(config.get("visual_ocr_right_click_x_offset",          80))
        self.visual_ocr_rc_y_offset          = int(config.get("visual_ocr_right_click_y_offset",          0))
        self.visual_ocr_menu_click_mode      = str(config.get("visual_ocr_menu_click_mode",                "relative_to_right_click"))
        self.visual_ocr_menu_x_offset        = int(config.get("visual_ocr_menu_click_x_offset",           60))
        self.visual_ocr_menu_y_offset        = int(config.get("visual_ocr_menu_click_y_offset",           85))
        self.visual_ocr_debug_save           = bool(config.get("visual_ocr_debug_save_screenshot",         True))
        self.visual_ocr_debug_dir            = str(config.get("visual_ocr_debug_dir",                      "data/debug/visual_ocr"))
        # Phase 3C hardening: ratio-based section / column / marker config
        self.visual_ocr_sell_y_min_ratio   = float(config.get("visual_ocr_sell_section_y_min_ratio",  0.22))
        self.visual_ocr_sell_y_max_ratio   = float(config.get("visual_ocr_sell_section_y_max_ratio",  0.58))
        self.visual_ocr_buy_y_min_ratio    = float(config.get("visual_ocr_buy_section_y_min_ratio",   0.55))
        self.visual_ocr_buy_y_max_ratio    = float(config.get("visual_ocr_buy_section_y_max_ratio",   0.88))
        self.visual_ocr_price_x_min_ratio  = float(config.get("visual_ocr_price_col_x_min_ratio",    0.48))
        self.visual_ocr_price_x_max_ratio  = float(config.get("visual_ocr_price_col_x_max_ratio",    0.68))
        self.visual_ocr_qty_x_min_ratio    = float(config.get("visual_ocr_qty_col_x_min_ratio",      0.38))
        self.visual_ocr_qty_x_max_ratio    = float(config.get("visual_ocr_qty_col_x_max_ratio",      0.52))
        self.visual_ocr_marker_x_min_ratio = float(config.get("visual_ocr_marker_x_min_ratio",       0.20))
        self.visual_ocr_marker_x_max_ratio = float(config.get("visual_ocr_marker_x_max_ratio",       0.32))
        self.visual_ocr_marker_required    = bool(config.get("visual_ocr_marker_required",            True))
        # Phase 3C hardening: Blue detection calibration
        self.visual_ocr_blue_r_min = int(config.get("visual_ocr_blue_r_min", 5))
        self.visual_ocr_blue_r_max = int(config.get("visual_ocr_blue_r_max", 80))
        self.visual_ocr_blue_g_min = int(config.get("visual_ocr_blue_g_min", 10))
        self.visual_ocr_blue_g_max = int(config.get("visual_ocr_blue_g_max", 90))
        self.visual_ocr_blue_b_min = int(config.get("visual_ocr_blue_b_min", 35))
        self.visual_ocr_blue_b_max = int(config.get("visual_ocr_blue_b_max", 130))
        self.visual_ocr_blue_b_over_r = int(config.get("visual_ocr_blue_b_over_r", 8))
        self.visual_ocr_blue_b_over_g = int(config.get("visual_ocr_blue_b_over_g", 5))
        self.visual_ocr_blue_row_threshold = float(config.get("visual_ocr_blue_row_threshold", 0.02))
        self.visual_ocr_blue_detection_mode = config.get("visual_ocr_blue_detection_mode", "rgb_or_relative")
        # Phase 3C hardening: Market Panel limits
        self.visual_ocr_market_panel_x_min_ratio = float(config.get("visual_ocr_market_panel_x_min_ratio", 0.36))
        self.visual_ocr_market_panel_x_max_ratio = float(config.get("visual_ocr_market_panel_x_max_ratio", 0.70))
        # Phase 3D: Tesseract backend config
        self.visual_ocr_tesseract_cmd  = str(config.get("visual_ocr_tesseract_cmd",  ""))
        self.visual_ocr_tesseract_lang = str(config.get("visual_ocr_tesseract_lang", "eng"))
        self.visual_ocr_tesseract_psm  = int(config.get("visual_ocr_tesseract_psm",  7))

    # ── public API ──────────────────────────────────────────────────────────

    def execute_quick_order_update(self, order_data: dict, recommended_price_text: str,
                                   selected_window: Optional[dict] = None) -> dict:
        """
        Run automation sequence. Returns diagnostic dict.
        NEVER executes the final order-confirm action.

        Args:
            order_data:              order context (order_id, type_id, etc.)
            recommended_price_text:  formatted price string (no thousands sep)
            selected_window:         candidate dict from list_candidate_windows(), or None
        """
        result = self._base_result(recommended_price_text)
        result["enabled"]  = self.enabled
        result["dry_run"]  = self.dry_run
        result["delays"]   = {
            "open_market_delay_ms":  self.open_market_delay,
            "focus_client_delay_ms": self.focus_delay,
            "paste_price_delay_ms":  self.paste_delay,
            "pre_paste_delay_ms":    self.pre_paste_delay,
            "post_action_delay_ms":  self.post_delay,
        }
        result["experimental_paste_enabled"]               = self.exp_paste_enabled
        result["paste_into_focused_window"]               = self.paste_into_focused
        result["clear_price_field_before_paste"]          = self.clear_before_paste
        result["paste_method"]                            = self.paste_method
        result["never_confirm_final_order"]               = self.never_confirm
        result["modify_order_step_enabled"]               = self.modify_order_step_enabled
        result["modify_order_strategy"]                   = self.modify_order_strategy
        result["require_modify_dialog_ready"]             = self.require_modify_dialog_ready
        result["paste_without_modify_dialog_verification"] = self.paste_without_modify_verify
        result["modify_order_hotkey_configured"]          = bool(self.modify_order_hotkey)
        result["allow_unverified_modify_order_paste"]     = self.allow_unverified_modify_paste
        result["visual_ocr_enabled"]                      = self.visual_ocr_enabled

        if not self.enabled:
            result["status"] = "disabled"
            result["steps_skipped"] += [
                "automation_disabled_in_config",
                "no_window_search",
                "no_clipboard_set",
                "no_focus_attempt",
            ]
            return result

        if self.dry_run:
            return self._run_dry(result, recommended_price_text, selected_window)

        return self._execute_real(result, recommended_price_text, selected_window, order_data)

    # ── private helpers ─────────────────────────────────────────────────────

    def _run_dry(self, result: dict, price_text: str,
                 selected_window: Optional[dict]) -> dict:
        result["status"] = "dry_run"
        if selected_window:
            result["selected_window_handle"] = selected_window.get("handle")
            result["selected_window_title"]  = selected_window.get("title", "")
            result["window_source"]          = "selected_handle"
            result["steps_executed"].append(
                f"would_use_selected_window: {selected_window.get('title', '?')}"
            )
        else:
            result["window_source"] = "title_search"
            result["steps_executed"].append("would_find_eve_window_by_title")
        result["steps_executed"] += [
            "would_wait_open_market_delay",
            "would_focus_eve_window",
            "would_copy_price_to_clipboard",
            "would_prepare_modify_order_if_enabled",
            "would_wait_pre_paste_delay",
            "would_send_ctrl_a_if_enabled",
            "would_paste_price_if_enabled",
            "would_wait_paste_delay",
        ]
        result["modify_order_prepare_attempted"] = False
        result["modify_order_dialog_verified"]   = False
        result["modify_order_warning"] = "dry_run — modify order step not executed"
        result["steps_skipped"].append("no_confirm_final_action (by_design)")
        _log.info(
            f"[AUTOMATION] dry_run — would process price={price_text} "
            f"window={selected_window.get('title') if selected_window else 'title_search'}"
        )
        return result

    def _execute_real(self, result: dict, price_text: str,
                      selected_window: Optional[dict],
                      order_data: Optional[dict] = None) -> dict:
        errors = result["errors"]

        # 1. Wait open-market delay
        self._safe_sleep(self.open_market_delay, "open_market_delay", result, errors)

        # 2. Copy price to clipboard
        try:
            self._set_clipboard(price_text)
            result["clipboard_set"] = True
            result["steps_executed"].append("clipboard_set")
            _log.info(f"[AUTOMATION] clipboard_set text={price_text}")
        except Exception as exc:
            errors.append(f"clipboard_error: {exc}")

        # 3. Resolve window (by handle first, then optional fallback)
        win = None
        if selected_window and selected_window.get("handle"):
            handle = selected_window["handle"]
            result["selected_window_handle"] = handle
            result["selected_window_title"]  = selected_window.get("title", "")
            result["window_source"]          = "selected_handle"
            win = self._connect_by_handle(handle, result, errors)
        elif self.require_selection and not self.allow_title_fallback:
            errors.append(
                "no selected target window — select the EVE client window before automating"
            )
            result["steps_skipped"].append("window_search_skipped_no_selection")
        else:
            result["window_source"] = "title_search"
            win = self._find_eve_window(result, errors)

        if win is not None:
            result["window_found"] = True

        # 4. Focus window
        if win is not None:
            if self._focus_window(win, result, errors):
                result["focused"] = True
                self._safe_sleep(self.focus_delay, "focus_delay", result, errors)

        # 4.5. Prepare Modify Order Dialog (optional, disabled by default)
        if result["focused"]:
            self._prepare_modify_order_dialog(result, errors, order_data, win)

        # 5. Experimental Paste (optional, disabled by default)
        if result["window_found"] and result["focused"]:
            if not result.get("_paste_blocked_modify_dialog"):
                self._handle_experimental_paste(result, price_text, errors)
            # else: paste_skipped_modify_dialog_not_verified already recorded
        else:
            result["steps_skipped"].append("paste_skipped_no_focus")

        # 6. Safety: NEVER confirm the final order change
        result["steps_skipped"].append("final_confirm_NOT_EXECUTED_BY_DESIGN")
        _log.info("[AUTOMATION] final confirm skipped — user must confirm manually")

        has_errors = bool(errors)
        result["status"] = (
            "error"   if has_errors and not result["window_found"] else
            "partial" if has_errors else
            "success"
        )
        return result

    def _connect_by_handle(self, handle: int, result: dict, errors: list):
        """Connect to a window by its OS handle via pywinauto."""
        if not _PYWINAUTO_AVAILABLE:
            errors.append("pywinauto not available — cannot connect by handle")
            return None
        try:
            from pywinauto.application import Application
            app = Application().connect(handle=handle)
            win = app.window(handle=handle)
            title = ""
            try:
                title = win.window_text()
            except Exception:
                title = _win32_get_title(handle) or "unknown"
            result["window_found"] = True
            result["window_title"] = title
            result["steps_executed"].append(f"connected_to_handle_{handle}: {title}")
            _log.info(f"[AUTOMATION] connected to handle={handle} title={title}")
            return win
        except Exception as exc:
            errors.append(f"connect_by_handle error (handle={handle}): {exc}")
            result["steps_executed"].append(f"connect_by_handle_failed_{handle}")
            return None

    def _find_eve_window(self, result: dict, errors: list):
        if self.use_pywinauto and _PYWINAUTO_AVAILABLE:
            return self._find_via_pywinauto(result, errors)
        if self.use_pyautogui_fb and _PYAUTOGUI_AVAILABLE:
            result["steps_executed"].append("find_window_via_pyautogui_fallback")
            errors.append("pyautogui window search not implemented in this phase")
            return None
        errors.append(
            "pywinauto not installed — cannot find EVE window. "
            "Install pywinauto or set use_pywinauto=false in config."
        )
        result["steps_executed"].append("find_window_attempted_no_backend")
        return None

    def _find_via_pywinauto(self, result: dict, errors: list):
        try:
            from pywinauto import findwindows
            from pywinauto.application import Application
            handles = findwindows.find_windows(title_re=f".*{self.window_title}.*")
            if not handles:
                result["steps_executed"].append("find_window_attempted")
                errors.append(
                    f"no window with title containing '{self.window_title}' found"
                )
                return None
            handle = handles[0]
            app = Application().connect(handle=handle)
            win = app.window(handle=handle)
            title = ""
            try:
                title = win.window_text()
            except Exception:
                title = "unknown"
            result["window_found"] = True
            result["window_title"] = title
            result["steps_executed"].append(f"found_eve_window: {title}")
            _log.info(f"[AUTOMATION] found window: {title}")
            return win
        except Exception as exc:
            errors.append(f"pywinauto find_window error: {exc}")
            result["steps_executed"].append("find_window_attempted")
            return None

    def _focus_window(self, win, result: dict, errors: list) -> bool:
        try:
            win.set_focus()
            result["focused"] = True
            result["steps_executed"].append("focused_eve_window")
            _log.info("[AUTOMATION] window focused")
            return True
        except Exception as exc:
            errors.append(f"focus_error: {exc}")
            return False

    def _set_clipboard(self, text: str) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(text)
            return
        except Exception:
            pass
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            raise RuntimeError(
                "No clipboard backend available (neither Qt nor pyperclip)"
            )

    def _safe_sleep(self, ms: int, label: str, result: dict, errors: list) -> None:
        try:
            if ms > 0:
                time.sleep(ms / 1000.0)
            result["steps_executed"].append(f"waited_{label}")
        except Exception as exc:
            errors.append(f"{label}_sleep_error: {exc}")

    def _prepare_modify_order_dialog(self, result: dict, errors: list,
                                      order_data: Optional[dict] = None,
                                      win=None) -> None:
        """
        Phase 3 — optionally prepare the Modify Order dialog before pasting.

        Default config (modify_order_step_enabled=False) is a safe no-op that
        records a skip entry and never takes any OS action.  All strategies
        leave the final confirm entirely to the user.
        """
        if not self.modify_order_step_enabled:
            result["steps_skipped"].append("modify_order_prepare_skipped_safe_default")
            result["modify_order_warning"] = (
                "modify_order_step_enabled=false — safe default, no modify dialog action taken"
            )
            return

        result["modify_order_prepare_attempted"] = True

        if self.modify_order_strategy == "manual_focus_guard":
            result["steps_executed"].append("modify_order_prepare_attempted_manual_focus_guard")
            result["modify_order_dialog_verified"] = False
            result["modify_order_warning"] = (
                "manual_focus_guard: no blind clicks — "
                "user must manually open Modify Order before automating"
            )
            _log.info("[AUTOMATION] modify_order: manual_focus_guard — dialog not verified")
            self._safe_sleep(self.modify_order_delay, "modify_order_delay", result, errors)
            # Paste blocking for manual_focus_guard
            if self.require_modify_dialog_ready:
                result["steps_skipped"].append("paste_skipped_modify_dialog_not_verified")
                result["_paste_blocked_modify_dialog"] = True
                _log.warning("[AUTOMATION] paste blocked — require_modify_dialog_ready=true")
            elif not self.paste_without_modify_verify:
                result["steps_skipped"].append("paste_skipped_modify_dialog_not_verified")
                result["_paste_blocked_modify_dialog"] = True
                _log.warning("[AUTOMATION] paste blocked — paste_without_modify_dialog_verification=false")

        elif self.modify_order_strategy == "hotkey_experimental":
            # Phase 3B: delegates to dedicated method (handles own sleep + paste blocking)
            self._run_hotkey_experimental(result, errors)

        elif self.modify_order_strategy == "visual_ocr":
            # Phase 3C: detect own-order row via pixel color + OCR, right-click, menu click
            self._run_visual_ocr(result, order_data or {}, win, errors)

        else:
            result["steps_executed"].append(
                f"modify_order_prepare_attempted_unknown_strategy: {self.modify_order_strategy}"
            )
            result["modify_order_dialog_verified"] = False
            result["modify_order_warning"] = (
                f"unknown strategy '{self.modify_order_strategy}' — dialog not verified, paste blocked"
            )
            result["steps_skipped"].append("paste_skipped_modify_dialog_not_verified")
            result["_paste_blocked_modify_dialog"] = True

    def _run_hotkey_experimental(self, result: dict, errors: list) -> None:
        """
        Phase 3B — send a configurable hotkey to open Modify Order, then
        attempt to verify the dialog appeared by window-title search.

        NOTE: EVE Online renders its UI internally; the Modify Order interface
        is drawn inside the game window, NOT as a native OS dialog.  The
        window-title verification will almost always return False in practice.
        Users must configure the correct hotkey in their EVE client settings
        and set modify_order_hotkey in quick_order_update.json accordingly.
        This strategy is unconfigured (modify_order_hotkey="") by default.
        NEVER confirms the final order modification.
        """
        if not _PYWINAUTO_AVAILABLE:
            errors.append("pywinauto not available — hotkey_experimental requires pywinauto")
            result["modify_order_dialog_verified"] = False
            result["modify_order_warning"] = "hotkey_experimental requires pywinauto (not installed)"
            self._apply_hotkey_paste_blocking(result)
            return

        if not self.modify_order_hotkey:
            result["steps_skipped"].append("modify_order_hotkey_missing")
            result["modify_order_dialog_verified"] = False
            result["modify_order_warning"] = (
                "hotkey_experimental: modify_order_hotkey is empty — "
                "set it in config/quick_order_update.json to the EVE hotkey for Modify Order"
            )
            _log.warning("[AUTOMATION] hotkey_experimental: hotkey is empty — skipping")
            self._apply_hotkey_paste_blocking(result)
            return

        # Send the hotkey to the currently-focused EVE window
        try:
            from pywinauto import keyboard
            keyboard.send_keys(self.modify_order_hotkey)
            result["steps_executed"].append("sent_modify_order_hotkey")
            _log.info(f"[AUTOMATION] hotkey_experimental: sent hotkey={self.modify_order_hotkey!r}")
        except Exception as exc:
            errors.append(f"modify_order_hotkey_send_error: {exc}")
            result["modify_order_dialog_verified"] = False
            result["modify_order_warning"] = f"hotkey_experimental: hotkey send failed: {exc}"
            self._apply_hotkey_paste_blocking(result)
            return

        # Wait for the dialog to potentially appear
        self._safe_sleep(
            self.modify_post_hotkey_delay, "modify_order_post_hotkey_delay", result, errors
        )

        # Attempt to verify the dialog via OS window title search
        result["steps_executed"].append("modify_order_dialog_verification_attempted")
        verified = self._verify_modify_order_dialog(result, errors)
        result["modify_order_dialog_verified"] = verified

        if verified:
            result["steps_executed"].append("modify_order_dialog_verified")
            result["modify_order_warning"] = None
            _log.info("[AUTOMATION] hotkey_experimental: modify order dialog verified")
        else:
            result["steps_skipped"].append("modify_order_dialog_not_verified")
            result["modify_order_warning"] = (
                f"hotkey_experimental: no OS window found with title containing "
                f"'{self.modify_verify_title}' — EVE renders Modify Order in-game, "
                f"not as a native OS dialog"
            )
            _log.warning("[AUTOMATION] hotkey_experimental: dialog not verified")
            self._apply_hotkey_paste_blocking(result)

    def _verify_modify_order_dialog(self, result: dict, errors: list) -> bool:
        """
        Attempt to detect a window whose title contains
        modify_order_verify_window_title_contains.

        Caveat: EVE Online's Modify Order interface is rendered inside the game
        window and does NOT create a separate OS-level window.  This check will
        return False in virtually all real-world cases; it exists for completeness
        and for any future native-dialog scenario.
        """
        if not _PYWINAUTO_AVAILABLE:
            result["steps_skipped"].append("modify_dialog_verify_skipped_no_pywinauto")
            return False
        try:
            from pywinauto import findwindows
            handles = findwindows.find_windows(title_re=f".*{self.modify_verify_title}.*")
            return bool(handles)
        except Exception as exc:
            errors.append(f"modify_dialog_verify_error: {exc}")
            return False

    def _apply_hotkey_paste_blocking(self, result: dict) -> None:
        """
        Decide whether to block paste for the hotkey_experimental strategy.
        Blocks if require_modify_dialog_ready=True or allow_unverified_modify_order_paste=False.
        """
        if self.require_modify_dialog_ready and not result.get("modify_order_dialog_verified"):
            result["steps_skipped"].append("paste_skipped_modify_dialog_not_verified")
            result["_paste_blocked_modify_dialog"] = True
            _log.warning("[AUTOMATION] paste blocked — require_modify_dialog_ready=true")
        elif not self.allow_unverified_modify_paste and not result.get("modify_order_dialog_verified"):
            result["steps_skipped"].append("paste_skipped_modify_dialog_not_verified")
            result["_paste_blocked_modify_dialog"] = True
            _log.warning("[AUTOMATION] paste blocked — allow_unverified_modify_order_paste=false")

    # ── Phase 3C: visual_ocr methods ─────────────────────────────────────────

    def _run_visual_ocr(self, result: dict, order_data: dict, win,
                        errors: list) -> None:
        """
        Phase 3C — detect own-order row via blue-row pixel detection + OCR,
        right-click on the row, click "Modificar pedido" in the context menu,
        wait for the dialog, then optionally allow paste.

        NEVER confirms the final order modification.
        """
        if not self.visual_ocr_enabled:
            result["steps_skipped"].append("visual_ocr_disabled_in_config")
            result["steps_skipped"].append("paste_skipped_modify_dialog_not_verified")
            result["_paste_blocked_modify_dialog"] = True
            result["modify_order_warning"] = "visual_ocr_enabled=false — visual OCR step skipped"
            return

        handle = result.get("selected_window_handle")
        if not handle:
            errors.append("visual_ocr: no window handle — cannot take screenshot")
            result["visual_ocr_status"] = "error_no_handle"
            self._apply_visual_ocr_paste_blocking(result)
            return

        window_rect = self._get_window_rect(handle)
        result["visual_ocr_window_rect"] = window_rect

        screenshot = self._capture_window_screenshot(window_rect, result, errors)
        if screenshot is None:
            result["visual_ocr_status"] = "error_screenshot_failed"
            self._apply_visual_ocr_paste_blocking(result)
            return

        if self.visual_ocr_debug_save:
            self._save_debug_screenshot(screenshot, result)

        detection = self._run_visual_ocr_detect(screenshot, order_data, window_rect)
        if self.visual_ocr_debug_save:
            self._save_debug_overlay(screenshot, detection, result)
        result["visual_ocr_status"]           = detection.get("status")
        result["visual_ocr_candidates_count"] = detection.get("candidates_count", 0)
        result["visual_ocr_matched_price"]    = detection.get("matched_price", False)
        result["visual_ocr_matched_quantity"] = detection.get("matched_quantity", False)
        result["visual_ocr_debug"]            = detection.get("debug", {})
        dbg = detection.get("debug", {})
        result["visual_ocr_blue_bands_found"] = dbg.get("blue_bands_found", 0)
        result["visual_ocr_section_used"]     = dbg.get("section_used")
        result["visual_ocr_section_y_min"]    = dbg.get("section_y_min")
        result["visual_ocr_section_y_max"]    = dbg.get("section_y_max")
        result["visual_ocr_own_marker_matched"] = detection.get("matched_own_marker", False)
        result["visual_ocr_price_text"]       = detection.get("price_text")
        result["visual_ocr_quantity_text"]    = detection.get("quantity_text")
        
        # Phase 3D: Backend diagnostics
        result["visual_ocr_backend"]           = "pytesseract"
        result["visual_ocr_tesseract_cmd"]     = dbg.get("tesseract_cmd_used")
        result["visual_ocr_tesseract_ready"]   = dbg.get("tesseract_executable_ready")
        result["visual_ocr_pytesseract_available"] = dbg.get("pytesseract_module_available")
        result["visual_ocr_suggested_path"]    = dbg.get("tesseract_suggested_path")

        if detection.get("error"):
            errors.append(f"visual_ocr_detection: {detection['error']}")

        if detection.get("status") != "unique_match":
            result["visual_ocr_row_x"] = None
            result["visual_ocr_row_y"] = None
            result["steps_skipped"].append(
                f"visual_ocr_no_unique_match: {detection.get('status')}"
            )
            result["modify_order_warning"] = (
                f"visual_ocr: detection status={detection.get('status')} "
                f"candidates={detection.get('candidates_count', 0)}"
            )
            self._apply_visual_ocr_paste_blocking(result)
            return

        row_x = detection["row_center_x"]
        row_y = detection["row_center_y"]
        result["visual_ocr_row_x"] = row_x
        result["visual_ocr_row_y"] = row_y
        result["steps_executed"].append(f"visual_ocr_unique_match_found: ({row_x}, {row_y})")
        _log.info(f"[AUTOMATION] visual_ocr: unique match at ({row_x}, {row_y})")

        rc_x = row_x + self.visual_ocr_rc_x_offset
        rc_y = row_y + self.visual_ocr_rc_y_offset
        if not self._visual_ocr_right_click(rc_x, rc_y, result, errors):
            self._apply_visual_ocr_paste_blocking(result)
            return

        self._safe_sleep(
            self.visual_ocr_context_menu_delay, "visual_ocr_context_menu_delay", result, errors
        )

        if self.visual_ocr_menu_click_mode == "relative_to_right_click":
            menu_x = rc_x + self.visual_ocr_menu_x_offset
            menu_y = rc_y + self.visual_ocr_menu_y_offset
        else:
            menu_x = self.visual_ocr_menu_x_offset
            menu_y = self.visual_ocr_menu_y_offset

        if not self._visual_ocr_left_click(menu_x, menu_y, result, errors):
            self._apply_visual_ocr_paste_blocking(result)
            return

        result["steps_executed"].append("visual_ocr_modify_order_menu_clicked")
        self._safe_sleep(
            self.visual_ocr_modify_dialog_delay, "visual_ocr_modify_dialog_delay", result, errors
        )

        result["modify_order_dialog_verified"] = False
        result["modify_order_warning"] = (
            "visual_ocr: context menu clicked — cannot OS-verify dialog (EVE renders in-game)"
        )
        _log.info("[AUTOMATION] visual_ocr: modify order menu clicked, waiting for in-game dialog")

        if not self.visual_ocr_allow_unverified_paste:
            result["steps_skipped"].append("paste_skipped_visual_ocr_dialog_not_verified")
            result["_paste_blocked_modify_dialog"] = True
            _log.warning("[AUTOMATION] visual_ocr: paste blocked — visual_ocr_allow_unverified_paste=false")

    def _get_window_rect(self, handle: int) -> dict:
        """Return window bounding rect as {left, top, width, height} via ctypes."""
        try:
            import ctypes
            import ctypes.wintypes
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(rect))
            return {
                "left":   rect.left,
                "top":    rect.top,
                "width":  max(1, rect.right - rect.left),
                "height": max(1, rect.bottom - rect.top),
            }
        except Exception as exc:
            _log.warning(f"[AUTOMATION] _get_window_rect error: {exc}")
            return {"left": 0, "top": 0, "width": 800, "height": 600}

    def _capture_window_screenshot(self, window_rect: dict, result: dict,
                                   errors: list):
        """Capture PIL screenshot of the window region. Returns PIL Image or None."""
        left   = window_rect.get("left",   0)
        top    = window_rect.get("top",    0)
        right  = left + window_rect.get("width",  800)
        bottom = top  + window_rect.get("height", 600)
        bbox   = (left, top, right, bottom)

        if _PIL_IMAGEGRAB_AVAILABLE:
            try:
                screenshot = _ImageGrab.grab(bbox=bbox)
                result["steps_executed"].append("visual_ocr_screenshot_captured_pil")
                return screenshot
            except Exception as exc:
                _log.debug(f"[AUTOMATION] PIL ImageGrab failed: {exc}")

        if _PYAUTOGUI_AVAILABLE:
            try:
                screenshot = _pyautogui.screenshot(
                    region=(left, top, window_rect.get("width", 800), window_rect.get("height", 600))
                )
                result["steps_executed"].append("visual_ocr_screenshot_captured_pyautogui")
                return screenshot
            except Exception as exc:
                errors.append(f"visual_ocr_screenshot_pyautogui_error: {exc}")

        errors.append("visual_ocr_screenshot_failed: no screenshot backend available (PIL/pyautogui)")
        return None

    def _run_visual_ocr_detect(self, screenshot, order_data: dict,
                                window_rect: dict) -> dict:
        """Run EveMarketVisualDetector. Separated for testability."""
        try:
            from core.eve_market_visual_detector import EveMarketVisualDetector
            detector = EveMarketVisualDetector(self._build_visual_ocr_config())
            return detector.detect_own_order_row(screenshot, order_data, window_rect)
        except Exception as exc:
            _log.error(f"[AUTOMATION] _run_visual_ocr_detect error: {exc}")
            return {"status": "error", "error": str(exc), "candidates_count": 0,
                    "matched_price": False, "matched_quantity": False, "debug": {}}

    def _visual_ocr_right_click(self, x: int, y: int, result: dict,
                                 errors: list) -> bool:
        """Right-click at (x, y). Returns True on success."""
        try:
            if _PYAUTOGUI_AVAILABLE:
                _pyautogui.rightClick(x, y)
            else:
                import ctypes
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
            result["steps_executed"].append(f"visual_ocr_right_click: ({x}, {y})")
            _log.info(f"[AUTOMATION] visual_ocr: right-click at ({x}, {y})")
            return True
        except Exception as exc:
            errors.append(f"visual_ocr_right_click_error: {exc}")
            result["steps_skipped"].append("visual_ocr_right_click_failed")
            return False

    def _visual_ocr_left_click(self, x: int, y: int, result: dict,
                                errors: list) -> bool:
        """Left-click at (x, y). Returns True on success."""
        try:
            if _PYAUTOGUI_AVAILABLE:
                _pyautogui.click(x, y)
            else:
                import ctypes
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            result["steps_executed"].append(f"visual_ocr_left_click: ({x}, {y})")
            _log.info(f"[AUTOMATION] visual_ocr: left-click at ({x}, {y})")
            return True
        except Exception as exc:
            errors.append(f"visual_ocr_left_click_error: {exc}")
            result["steps_skipped"].append("visual_ocr_left_click_failed")
            return False

    def _apply_visual_ocr_paste_blocking(self, result: dict) -> None:
        """Block paste when the visual_ocr strategy failed to complete its steps."""
        result["steps_skipped"].append("paste_skipped_visual_ocr_step_failed")
        result["_paste_blocked_modify_dialog"] = True
        _log.warning("[AUTOMATION] visual_ocr: paste blocked — strategy did not complete")

    def _build_visual_ocr_config(self) -> dict:
        return {
            "visual_ocr_require_unique_match":      self.visual_ocr_require_unique_match,
            "visual_ocr_match_price":               self.visual_ocr_match_price,
            "visual_ocr_match_quantity":            self.visual_ocr_match_quantity,
            "visual_ocr_require_own_order_marker":  self.visual_ocr_require_own_marker,
            "visual_ocr_side_section_required":     self.visual_ocr_side_section_required,
            "visual_ocr_sell_section_y_min_ratio":  self.visual_ocr_sell_y_min_ratio,
            "visual_ocr_sell_section_y_max_ratio":  self.visual_ocr_sell_y_max_ratio,
            "visual_ocr_buy_section_y_min_ratio":   self.visual_ocr_buy_y_min_ratio,
            "visual_ocr_buy_section_y_max_ratio":   self.visual_ocr_buy_y_max_ratio,
            "visual_ocr_price_col_x_min_ratio":     self.visual_ocr_price_x_min_ratio,
            "visual_ocr_price_col_x_max_ratio":     self.visual_ocr_price_x_max_ratio,
            "visual_ocr_qty_col_x_min_ratio":       self.visual_ocr_qty_x_min_ratio,
            "visual_ocr_qty_col_x_max_ratio":       self.visual_ocr_qty_x_max_ratio,
            "visual_ocr_marker_x_min_ratio":        self.visual_ocr_marker_x_min_ratio,
            "visual_ocr_marker_x_max_ratio":        self.visual_ocr_marker_x_max_ratio,
            "visual_ocr_marker_required":           self.visual_ocr_marker_required,
            "visual_ocr_blue_r_min":                self.visual_ocr_blue_r_min,
            "visual_ocr_blue_r_max":                self.visual_ocr_blue_r_max,
            "visual_ocr_blue_g_min":                self.visual_ocr_blue_g_min,
            "visual_ocr_blue_g_max":                self.visual_ocr_blue_g_max,
            "visual_ocr_blue_b_min":                self.visual_ocr_blue_b_min,
            "visual_ocr_blue_b_max":                self.visual_ocr_blue_b_max,
            "visual_ocr_blue_b_over_r":             self.visual_ocr_blue_b_over_r,
            "visual_ocr_blue_b_over_g":             self.visual_ocr_blue_b_over_g,
            "visual_ocr_blue_row_threshold":        self.visual_ocr_blue_row_threshold,
            "visual_ocr_blue_detection_mode":       self.visual_ocr_blue_detection_mode,
            "visual_ocr_market_panel_x_min_ratio":  self.visual_ocr_market_panel_x_min_ratio,
            "visual_ocr_market_panel_x_max_ratio":  self.visual_ocr_market_panel_x_max_ratio,
            # Phase 3D: Tesseract backend config
            "visual_ocr_tesseract_cmd":             self.visual_ocr_tesseract_cmd,
            "visual_ocr_tesseract_lang":            self.visual_ocr_tesseract_lang,
            "visual_ocr_tesseract_psm":             self.visual_ocr_tesseract_psm,
        }

    def _save_debug_screenshot(self, screenshot, result: dict) -> None:
        """Save debug screenshot. Silent on failure."""
        try:
            import os
            os.makedirs(self.visual_ocr_debug_dir, exist_ok=True)
            ts   = int(time.time())
            path = os.path.join(self.visual_ocr_debug_dir, f"visual_ocr_{ts}.png")
            screenshot.save(path)
            result["visual_ocr_debug_screenshot_path"] = path
            _log.debug(f"[AUTOMATION] visual_ocr: debug screenshot saved to {path}")
        except Exception as exc:
            _log.debug(f"[AUTOMATION] visual_ocr: debug screenshot save failed: {exc}")

    def _save_debug_overlay(self, screenshot, detection: dict, result: dict) -> None:
        """Save annotated debug screenshot with detection overlay. Silent on failure."""
        try:
            import os
            from PIL import Image, ImageDraw, ImageFont
            if hasattr(screenshot, 'shape'):
                import numpy as _np
                img = Image.fromarray(screenshot.astype('uint8'))
            elif hasattr(screenshot, 'save'):
                img = screenshot.copy()
            else:
                return

            draw = ImageDraw.Draw(img)
            dbg  = detection.get("debug", {})
            w, h = img.size

            # 1. Draw Section rectangle (Yellow)
            sy_min = dbg.get("section_y_min")
            sy_max = dbg.get("section_y_max")
            if sy_min is not None and sy_max is not None:
                draw.rectangle([0, sy_min, w - 1, sy_max], outline=(255, 255, 0), width=2)
                draw.text((10, sy_min + 5), f"SECTION: {dbg.get('section_used', 'unknown').upper()}", fill=(255, 255, 0))

            # 2. Draw Market Panel limits (Gray)
            px_min = dbg.get("market_panel_x_min")
            px_max = dbg.get("market_panel_x_max")
            if px_min is not None and px_max is not None:
                draw.line([px_min, 0, px_min, h - 1], fill=(128, 128, 128), width=1)
                draw.line([px_max, 0, px_max, h - 1], fill=(128, 128, 128), width=1)
                draw.text((px_min + 5, 10), "MARKET PANEL", fill=(128, 128, 128))

            # 3. Draw Column zones (relative to panel)
            for x0, x1, color, label in (
                (dbg.get("price_col_x_min"), dbg.get("price_col_x_max"), (255, 128, 0), "PRICE"),
                (dbg.get("qty_col_x_min"),   dbg.get("qty_col_x_max"),   (0, 200, 255), "QTY"),
            ):
                if x0 is not None and x1 is not None:
                    # Draw dotted vertical lines or shaded region
                    draw.rectangle([x0, sy_min or 0, x1, sy_max or h-1], outline=color, width=1)
                    draw.text((x0 + 2, (sy_min or 10) + 20), label, fill=color)

            # 4. Candidate bands (Blue)
            for band in dbg.get("candidate_bands", []):
                draw.rectangle([px_min or 0, band[0], px_max or w-1, band[1]], outline=(100, 100, 255), width=1)

            # 5. Matched band (Green)
            matched_band = dbg.get("matched_band")
            if matched_band:
                draw.rectangle([px_min or 0, matched_band[0], px_max or w-1, matched_band[1]],
                               outline=(0, 255, 0), width=3)
                draw.text((px_min or 10, matched_band[0] - 15), "UNIQUE MATCH", fill=(0, 255, 0))

            # Summary text
            summary = [
                f"Size: {w}x{h}",
                f"Status: {detection.get('status')}",
                f"Bands: {dbg.get('blue_bands_found', 0)}",
                f"Blue Pixels: {dbg.get('sample_dark_blue_pixels_count', 0)}",
                f"Price OCR: {detection.get('price_text')}",
                f"Qty OCR: {detection.get('quantity_text')}",
            ]
            for i, txt in enumerate(summary):
                draw.text((10, 10 + i*15), txt, fill=(255, 255, 255))

            os.makedirs(self.visual_ocr_debug_dir, exist_ok=True)
            ts   = int(time.time())
            path = os.path.join(self.visual_ocr_debug_dir, f"visual_ocr_overlay_{ts}.png")
            img.save(path)
            result["visual_ocr_debug_overlay_path"] = path
            _log.debug(f"[AUTOMATION] visual_ocr: debug overlay saved to {path}")
        except Exception as exc:
            _log.debug(f"[AUTOMATION] visual_ocr: debug overlay save failed: {exc}")

    def _handle_experimental_paste(self, result: dict, price_text: str, errors: list) -> None:
        if not self.exp_paste_enabled:
            result["steps_skipped"].append("experimental_paste_disabled")
            return

        if not self.paste_into_focused:
            result["steps_skipped"].append("paste_into_focused_window_disabled")
            return

        # 1. Pre-paste delay
        self._safe_sleep(self.pre_paste_delay, "pre_paste_delay", result, errors)

        try:
            from pywinauto import keyboard
        except ImportError:
            errors.append("pywinauto.keyboard not available — cannot paste keys")
            return

        try:
            # 2. Clear field
            if self.clear_before_paste:
                keyboard.send_keys("^a")
                result["steps_executed"].append("sent_ctrl_a")
                time.sleep(0.1)

            # 3. Paste
            if self.paste_method == "ctrl+v":
                keyboard.send_keys("^v")
                result["steps_executed"].append("sent_ctrl_v")
                result["price_pasted"] = True
            elif self.paste_method == "typewrite":
                keyboard.send_keys(price_text)
                result["steps_executed"].append("typewrite_price")
                result["price_pasted"] = True
            
            _log.info(f"[AUTOMATION] price pasted via {self.paste_method}")

        except Exception as exc:
            errors.append(f"paste_error: {exc}")
            _log.error(f"[AUTOMATION] paste error: {exc}")

    @staticmethod
    def _base_result(price_text: str) -> dict:
        return {
            "status":                   "disabled",
            "enabled":                  False,
            "dry_run":                  True,
            "steps_executed":           [],
            "steps_skipped":            [],
            "errors":                   [],
            "window_found":             False,
            "window_title":             None,
            "focused":                  False,
            "clipboard_set":            False,
            "recommended_price_text":   price_text,
            "experimental_paste_enabled": False,
            "paste_into_focused_window":  False,
            "clear_price_field_before_paste": True,
            "paste_method":               "ctrl+v",
            "price_pasted":               False,
            "never_confirm_final_order":  True,
            "delays":                   {},
            "window_source":            None,
            "selected_window_handle":   None,
            "selected_window_title":    None,
            "candidate_windows_count":  0,
            "candidate_windows":        [],
            # Phase 3: Modify Order
            "modify_order_step_enabled":               False,
            "modify_order_strategy":                   "manual_focus_guard",
            "modify_order_prepare_attempted":          False,
            "modify_order_dialog_verified":            False,
            "require_modify_dialog_ready":             False,
            "paste_without_modify_dialog_verification": True,
            "modify_order_warning":                    None,
            # Phase 3B: hotkey_experimental
            "modify_order_hotkey_configured":          False,
            "allow_unverified_modify_order_paste":     False,
            # Phase 3C: visual_ocr
            "visual_ocr_enabled":                      False,
            "visual_ocr_status":                       None,
            "visual_ocr_candidates_count":             0,
            "visual_ocr_matched_price":                False,
            "visual_ocr_matched_quantity":             False,
            "visual_ocr_row_x":                        None,
            "visual_ocr_row_y":                        None,
            "visual_ocr_window_rect":                  None,
            "visual_ocr_debug":                        {},
            "visual_ocr_debug_screenshot_path":        None,
            # Phase 3C hardening: new diagnostic fields
            "visual_ocr_blue_bands_found":             0,
            "visual_ocr_section_used":                 None,
            "visual_ocr_section_y_min":                None,
            "visual_ocr_section_y_max":                None,
            "visual_ocr_own_marker_matched":           False,
            "visual_ocr_price_text":                   None,
            "visual_ocr_quantity_text":                None,
            "visual_ocr_debug_overlay_path":           None,
            # Phase 3D: backend diagnostics
            "visual_ocr_backend":                      "N/A",
            "visual_ocr_tesseract_cmd":                "N/A",
            "visual_ocr_tesseract_ready":              False,
            "visual_ocr_pytesseract_available":        False,
            "visual_ocr_suggested_path":               "N/A",
        }
