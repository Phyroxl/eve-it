"""
Tests for core/quick_order_update_config.py.

Covers:
  1. missing config file → creates default with enabled=False, dry_run=True
  2. default enabled is False
  3. default dry_run is True
  4. corrupt JSON → renamed .corrupt, recreated with defaults
  5. negative delays → clamped to 0
  6. huge delays → clamped to 30000
  7. validate_quick_order_update_config returns all expected keys
  8. bool fields normalised correctly
  9. max_attempts clamped to [1, 10]
  10. empty string for window title keeps default
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.quick_order_update_config import (
    load_quick_order_update_config,
    save_default_quick_order_update_config_if_missing,
    validate_quick_order_update_config,
    _DEFAULT_CONFIG,
    _MAX_DELAY_MS,
)


class TestLoadDefaultCreation(unittest.TestCase):
    """load/save creates config with safe defaults when file is absent."""

    def _with_tmp_config(self, content=None):
        """Return a temporary file path (optionally pre-filled)."""
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if content is None:
            os.remove(path)          # simulate missing file
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        return path

    def _patch_config_path(self, path):
        import core.quick_order_update_config as mod
        self._orig = mod._CONFIG_PATH
        mod._CONFIG_PATH = path
        return mod

    def _restore(self, mod):
        mod._CONFIG_PATH = self._orig

    def test_missing_file_creates_default(self):
        path = self._with_tmp_config(content=None)
        mod = self._patch_config_path(path)
        try:
            cfg = load_quick_order_update_config()
            self.assertTrue(os.path.exists(path), "config file should have been created")
            self.assertIsInstance(cfg, dict)
        finally:
            self._restore(mod)
            if os.path.exists(path):
                os.remove(path)

    def test_default_enabled_is_false(self):
        path = self._with_tmp_config(content=None)
        mod = self._patch_config_path(path)
        try:
            cfg = load_quick_order_update_config()
            self.assertFalse(cfg["enabled"], "enabled must default to False")
        finally:
            self._restore(mod)
            if os.path.exists(path):
                os.remove(path)

    def test_default_dry_run_is_true(self):
        path = self._with_tmp_config(content=None)
        mod = self._patch_config_path(path)
        try:
            cfg = load_quick_order_update_config()
            self.assertTrue(cfg["dry_run"], "dry_run must default to True")
        finally:
            self._restore(mod)
            if os.path.exists(path):
                os.remove(path)

    def test_corrupt_json_renamed_and_recreated(self):
        path = self._with_tmp_config(content="{ this is not valid json }")
        mod = self._patch_config_path(path)
        try:
            cfg = load_quick_order_update_config()
            # Corrupt file should have been renamed
            self.assertFalse(os.path.exists(path) and
                             open(path).read().startswith("{ this"),
                             "corrupt file content should not remain at original path")
            # Config returned should be the safe default
            self.assertFalse(cfg["enabled"])
            self.assertTrue(cfg["dry_run"])
        finally:
            self._restore(mod)
            # Clean up any .corrupt.* files created in tmp dir
            tmp_dir = os.path.dirname(path)
            base = os.path.basename(path)
            for f in os.listdir(tmp_dir):
                if f.startswith(base):
                    try:
                        os.remove(os.path.join(tmp_dir, f))
                    except OSError:
                        pass


class TestValidateConfig(unittest.TestCase):
    """validate_quick_order_update_config sanitises values correctly."""

    def test_negative_delays_clamped_to_zero(self):
        cfg = validate_quick_order_update_config({
            "enabled": True,
            "open_market_delay_ms":  -500,
            "focus_client_delay_ms": -1,
            "paste_price_delay_ms":  -9999,
            "post_action_delay_ms":  -1,
        })
        for key in ("open_market_delay_ms", "focus_client_delay_ms",
                    "paste_price_delay_ms", "post_action_delay_ms"):
            self.assertEqual(cfg[key], 0, f"{key} should be clamped to 0")

    def test_huge_delays_clamped_to_max(self):
        cfg = validate_quick_order_update_config({
            "open_market_delay_ms":  999_999,
            "focus_client_delay_ms": 50_000,
            "paste_price_delay_ms":  31_000,
            "post_action_delay_ms":  100_000,
        })
        for key in ("open_market_delay_ms", "focus_client_delay_ms",
                    "paste_price_delay_ms", "post_action_delay_ms"):
            self.assertLessEqual(cfg[key], _MAX_DELAY_MS,
                                 f"{key} should be clamped to {_MAX_DELAY_MS}")

    def test_all_expected_keys_present(self):
        cfg = validate_quick_order_update_config({})
        for key in _DEFAULT_CONFIG:
            self.assertIn(key, cfg, f"key '{key}' missing from validated config")

    def test_bool_fields_normalised(self):
        cfg = validate_quick_order_update_config({
            "enabled":             1,
            "dry_run":             0,
            "confirm_required":    "yes",
            "restore_clipboard_after": "",
        })
        self.assertIsInstance(cfg["enabled"],           bool)
        self.assertIsInstance(cfg["dry_run"],           bool)
        self.assertIsInstance(cfg["confirm_required"],  bool)
        self.assertTrue(cfg["enabled"])
        self.assertFalse(cfg["dry_run"])
        self.assertTrue(cfg["confirm_required"])  # bool("yes") == True

    def test_max_attempts_clamped(self):
        cfg_low  = validate_quick_order_update_config({"max_attempts": 0})
        cfg_high = validate_quick_order_update_config({"max_attempts": 100})
        self.assertEqual(cfg_low["max_attempts"],  1)
        self.assertEqual(cfg_high["max_attempts"], 10)

    def test_empty_window_title_keeps_default(self):
        cfg = validate_quick_order_update_config({"client_window_title_contains": "   "})
        self.assertEqual(cfg["client_window_title_contains"], "EVE")

    def test_valid_window_title_accepted(self):
        cfg = validate_quick_order_update_config({"client_window_title_contains": "EVE Online"})
        self.assertEqual(cfg["client_window_title_contains"], "EVE Online")

    def test_confirm_required_defaults_true(self):
        cfg = validate_quick_order_update_config({})
        self.assertTrue(cfg["confirm_required"])

    def test_save_default_returns_dict(self):
        """save_default_...if_missing should not crash even if file exists."""
        import core.quick_order_update_config as mod
        cfg = mod.save_default_quick_order_update_config_if_missing()
        self.assertIsInstance(cfg, dict)
        self.assertIn("enabled", cfg)


if __name__ == "__main__":
    unittest.main()
