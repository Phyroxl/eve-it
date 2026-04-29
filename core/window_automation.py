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
        result["experimental_paste_enabled"]     = self.exp_paste_enabled
        result["paste_into_focused_window"]      = self.paste_into_focused
        result["clear_price_field_before_paste"] = self.clear_before_paste
        result["paste_method"]                   = self.paste_method
        result["never_confirm_final_order"]      = self.never_confirm

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

        return self._execute_real(result, recommended_price_text, selected_window)

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
            "would_wait_pre_paste_delay",
            "would_send_ctrl_a_if_enabled",
            "would_paste_price_if_enabled",
            "would_wait_paste_delay",
        ]
        result["steps_skipped"].append("no_confirm_final_action (by_design)")
        _log.info(
            f"[AUTOMATION] dry_run — would process price={price_text} "
            f"window={selected_window.get('title') if selected_window else 'title_search'}"
        )
        return result

    def _execute_real(self, result: dict, price_text: str,
                      selected_window: Optional[dict]) -> dict:
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

        # 5. Experimental Paste (optional, disabled by default)
        if result["window_found"] and result["focused"]:
            self._handle_experimental_paste(result, price_text, errors)
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
        }
