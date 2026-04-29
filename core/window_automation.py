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


class EVEWindowAutomation:
    """
    Experimental automation assistant for Quick Order Update.

    Usage:
        cfg  = load_quick_order_update_config()
        auto = EVEWindowAutomation(cfg)
        result = auto.execute_quick_order_update(order_data, price_text)

    The returned dict always contains the keys listed in _base_result().
    """

    def __init__(self, config: dict):
        self.enabled           = bool(config.get("enabled",                  False))
        self.dry_run           = bool(config.get("dry_run",                  True))
        self.confirm_required  = bool(config.get("confirm_required",         True))
        self.open_market_delay = int(config.get("open_market_delay_ms",      1000))
        self.focus_delay       = int(config.get("focus_client_delay_ms",     700))
        self.paste_delay       = int(config.get("paste_price_delay_ms",      300))
        self.post_delay        = int(config.get("post_action_delay_ms",      300))
        self.restore_clipboard = bool(config.get("restore_clipboard_after",  False))
        self.window_title      = config.get("client_window_title_contains",  "EVE")
        self.use_pywinauto     = bool(config.get("use_pywinauto",            True))
        self.use_pyautogui_fb  = bool(config.get("use_pyautogui_fallback",   False))
        self.max_attempts      = int(config.get("max_attempts",              1))

    # ── public API ──────────────────────────────────────────────────────────

    def execute_quick_order_update(self, order_data: dict,
                                   recommended_price_text: str) -> dict:
        """
        Run automation sequence. Returns diagnostic dict.
        NEVER executes the final order-confirm action.
        """
        result = self._base_result(recommended_price_text)
        result["enabled"]  = self.enabled
        result["dry_run"]  = self.dry_run
        result["delays"]   = {
            "open_market_delay_ms":  self.open_market_delay,
            "focus_client_delay_ms": self.focus_delay,
            "paste_price_delay_ms":  self.paste_delay,
            "post_action_delay_ms":  self.post_delay,
        }

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
            result["status"] = "dry_run"
            result["steps_executed"] += [
                "would_wait_open_market_delay",
                "would_find_eve_window",
                "would_focus_eve_window",
                "would_copy_price_to_clipboard",
                "would_wait_paste_delay",
            ]
            result["steps_skipped"].append("no_confirm_final_action (by_design)")
            _log.info(
                f"[AUTOMATION] dry_run — would process price={recommended_price_text}"
            )
            return result

        # Real mode
        return self._execute_real(result, recommended_price_text)

    # ── private helpers ─────────────────────────────────────────────────────

    def _execute_real(self, result: dict, price_text: str) -> dict:
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

        # 3. Find EVE window
        win = self._find_eve_window(result, errors)

        # 4. Focus window
        if win is not None:
            focused = self._focus_window(win, result, errors)
            if focused:
                self._safe_sleep(self.focus_delay, "focus_delay", result, errors)

        # 5. Safety: NEVER confirm the final order change
        result["steps_skipped"].append("final_confirm_NOT_EXECUTED_BY_DESIGN")
        _log.info("[AUTOMATION] final confirm skipped — user must confirm manually")

        has_errors = bool(errors)
        result["status"] = (
            "error"   if has_errors and not result["window_found"] else
            "partial" if has_errors else
            "success"
        )
        return result

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

    @staticmethod
    def _base_result(price_text: str) -> dict:
        return {
            "status":                 "disabled",
            "enabled":                False,
            "dry_run":                True,
            "steps_executed":         [],
            "steps_skipped":          [],
            "errors":                 [],
            "window_found":           False,
            "window_title":           None,
            "focused":                False,
            "clipboard_set":          False,
            "recommended_price_text": price_text,
            "delays":                 {},
        }
