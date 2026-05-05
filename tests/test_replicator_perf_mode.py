"""Tests: performance mode config correctness and _cycle_group_ultra behaviour."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from collections import deque

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay.replicator_config import get_perf_cfg, PERFORMANCE_MODE_CONFIGS


class TestPerfModeConfig(unittest.TestCase):

    def test_get_perf_cfg_defaults_to_safe(self):
        self.assertEqual(get_perf_cfg({}), PERFORMANCE_MODE_CONFIGS['safe'])

    def test_get_perf_cfg_unknown_mode_falls_back_to_safe(self):
        self.assertEqual(
            get_perf_cfg({'performance_mode': 'turbo_super_extreme'}),
            PERFORMANCE_MODE_CONFIGS['safe'],
        )

    def test_safe_use_ultra_raw_path_false(self):
        self.assertFalse(PERFORMANCE_MODE_CONFIGS['safe']['use_ultra_raw_path'])

    def test_ultra_use_ultra_raw_path_true(self):
        self.assertTrue(PERFORMANCE_MODE_CONFIGS['ultra']['use_ultra_raw_path'])

    def test_ultra_skip_hwnd_validity_check_false(self):
        self.assertFalse(PERFORMANCE_MODE_CONFIGS['ultra']['skip_hwnd_validity_check'])

    def test_combat_skip_hwnd_validity_check_false(self):
        self.assertFalse(PERFORMANCE_MODE_CONFIGS['combat']['skip_hwnd_validity_check'])

    def test_ultra_notify_active_client_false(self):
        self.assertFalse(PERFORMANCE_MODE_CONFIGS['ultra']['notify_active_client'])

    def test_combat_notify_active_client_false(self):
        self.assertFalse(PERFORMANCE_MODE_CONFIGS['combat']['notify_active_client'])

    def test_safe_notify_active_client_true(self):
        self.assertTrue(PERFORMANCE_MODE_CONFIGS['safe']['notify_active_client'])

    def test_balanced_notify_active_client_true(self):
        self.assertTrue(PERFORMANCE_MODE_CONFIGS['balanced']['notify_active_client'])

    def test_ultra_verify_foreground_true(self):
        self.assertTrue(PERFORMANCE_MODE_CONFIGS['ultra']['verify_foreground'])

    def test_ultra_verify_timeout_ms_positive(self):
        self.assertGreater(PERFORMANCE_MODE_CONFIGS['ultra']['verify_timeout_ms'], 0)

    def test_safe_verify_foreground_false(self):
        self.assertFalse(PERFORMANCE_MODE_CONFIGS['safe']['verify_foreground'])

    def test_all_modes_have_required_keys(self):
        required = {'min_cycle_ms', 'capture_suspend_ms', 'use_ultra_raw_path',
                    'skip_hwnd_validity_check', 'verify_foreground', 'verify_timeout_ms',
                    'notify_active_client'}
        for mode in ('safe', 'balanced', 'combat', 'ultra'):
            with self.subTest(mode=mode):
                self.assertTrue(required.issubset(PERFORMANCE_MODE_CONFIGS[mode].keys()))

    def test_ultra_min_cycle_ms_less_than_safe(self):
        self.assertLess(
            PERFORMANCE_MODE_CONFIGS['ultra']['min_cycle_ms'],
            PERFORMANCE_MODE_CONFIGS['safe']['min_cycle_ms'],
        )


# ── Helper to register and capture ultra callbacks ────────────────────────────

def _capture_ultra_callbacks(cfg, hwnd_map=None):
    """Call register_hotkeys with mocked thread start; return list of (mods,vk,cb)."""
    import threading
    import overlay.replicator_hotkeys as hk

    hk._cycle_in_progress = False
    hk._last_cycle_time = 0.0
    hk._last_cycle_client_id = None
    hk._last_cycle_client_id_time = 0.0
    hk._last_group_index = {}
    hk._group_hwnd_order_cache = {}
    hk._hotkey_ultra_events = deque(maxlen=500)
    hk._hwnd_cache = hwnd_map or {}

    captured = []

    def fake_start(self_t):
        regs = self_t._args[0] if self_t._args else []
        captured.extend(regs)

    with patch.object(threading.Thread, 'start', fake_start), \
         patch.object(hk._user32, 'RegisterHotKey', return_value=True), \
         patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
         patch('overlay.win32_capture.resolve_eve_window_handle', return_value=0):
        hk.register_hotkeys(cfg)

    return captured


def _find_ultra_cb(captured, direction):
    """Find the _cycle_group_ultra partial for the given direction."""
    for _, _, cb in captured:
        if hasattr(cb, 'func') and cb.func.__name__ == '_cycle_group_ultra':
            if cb.args[1] == direction:
                return cb
    return None


# ── Behavioural tests ─────────────────────────────────────────────────────────

class TestCycleGroupUltraBehaviour(unittest.TestCase):

    def _base_cfg(self, titles=None, perf_mode='ultra'):
        if titles is None:
            titles = ['EVE - Alpha', 'EVE - Beta']
        return {
            'hotkeys': {
                'performance_mode': perf_mode,
                'groups': {
                    'g1': {
                        'enabled': True,
                        'clients_order': titles,
                        'next': 'F14',
                        'prev': 'CTRL+F14',
                        'name': 'Test',
                    }
                },
            }
        }

    def test_notify_not_called_in_ultra_mode(self):
        """Ultra mode must NOT call notify_active_client_changed."""
        import overlay.replicator_hotkeys as hk
        cfg = self._base_cfg()
        hwnd_map = {'EVE - Alpha': 1001, 'EVE - Beta': 1002}
        captured = _capture_ultra_callbacks(cfg, hwnd_map)
        cb = _find_ultra_cb(captured, 1)
        self.assertIsNotNone(cb, "No ultra callback registered")

        notify_mock = MagicMock()
        with patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.focus_eve_window_ultra_verified',
                   return_value=(True, True, 1002, 5.0)), \
             patch('overlay.replication_overlay.ReplicationOverlay'
                   '.notify_active_client_changed', notify_mock):
            cb()

        notify_mock.assert_not_called()

    def test_notify_called_when_perf_cfg_enables_it(self):
        """A perf_cfg with notify_active_client=True must call the notify method."""
        import overlay.replicator_hotkeys as hk
        # Use a safe-like perf_cfg but routed through ultra path by injecting directly
        hk._cycle_in_progress = False
        hk._last_cycle_time = 0.0
        hk._last_cycle_client_id = None
        hk._last_cycle_client_id_time = 0.0
        hk._last_group_index = {}
        hk._hotkey_ultra_events = deque(maxlen=500)
        hk._group_hwnd_order_cache = {}
        hk._hwnd_cache = {'EVE - Alpha': 1001, 'EVE - Beta': 1002}

        cfg = self._base_cfg()
        perf_cfg = {**PERFORMANCE_MODE_CONFIGS['ultra'], 'notify_active_client': True}

        import threading
        captured = []

        def fake_start(self_t):
            captured.extend(self_t._args[0] if self_t._args else [])

        notify_mock = MagicMock()
        with patch.object(threading.Thread, 'start', fake_start), \
             patch.object(hk._user32, 'RegisterHotKey', return_value=True), \
             patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.resolve_eve_window_handle', return_value=0):
            hk.register_hotkeys(cfg)

        cb = _find_ultra_cb(captured, 1)
        self.assertIsNotNone(cb)

        # Replace perf_cfg in the partial with notify=True version
        from functools import partial
        patched_cb = partial(cb.func, cb.args[0], cb.args[1], perf_cfg)

        with patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.focus_eve_window_ultra_verified',
                   return_value=(True, True, 1002, 5.0)), \
             patch('overlay.replication_overlay.ReplicationOverlay'
                   '.notify_active_client_changed', notify_mock):
            patched_cb()

        notify_mock.assert_called_once()

    def test_index_not_advanced_when_not_verified(self):
        """When focus is requested but not verified, _last_group_index must not change."""
        import overlay.replicator_hotkeys as hk
        cfg = self._base_cfg()
        hwnd_map = {'EVE - Alpha': 1001, 'EVE - Beta': 1002}
        captured = _capture_ultra_callbacks(cfg, hwnd_map)
        cb = _find_ultra_cb(captured, 1)
        self.assertIsNotNone(cb)

        with patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.focus_eve_window_ultra_verified',
                   return_value=(True, False, 9999, 10.0)):
            cb()

        types = [e[0] for e in hk._hotkey_ultra_events]
        self.assertIn('cycle_not_verified', types)
        self.assertNotIn('cycle_ok', types)
        self.assertNotIn('g1', hk._last_group_index)

    def test_index_advanced_when_verified(self):
        """When focus is verified, _last_group_index must be updated."""
        import overlay.replicator_hotkeys as hk
        cfg = self._base_cfg()
        hwnd_map = {'EVE - Alpha': 1001, 'EVE - Beta': 1002}
        captured = _capture_ultra_callbacks(cfg, hwnd_map)
        cb = _find_ultra_cb(captured, 1)
        self.assertIsNotNone(cb)

        notify_mock = MagicMock()
        with patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.focus_eve_window_ultra_verified',
                   return_value=(True, True, 1002, 8.0)), \
             patch('overlay.replication_overlay.ReplicationOverlay'
                   '.notify_active_client_changed', notify_mock):
            cb()

        types = [e[0] for e in hk._hotkey_ultra_events]
        self.assertIn('cycle_ok', types)
        self.assertNotIn('cycle_not_verified', types)
        self.assertIn('g1', hk._last_group_index)

    def test_cooldown_not_set_when_hwnd_invalid(self):
        """An all-invalid-HWND run must NOT update _last_cycle_time (no false cooldown)."""
        import overlay.replicator_hotkeys as hk
        cfg = self._base_cfg()
        hwnd_map = {'EVE - Alpha': 1001, 'EVE - Beta': 1002}
        captured = _capture_ultra_callbacks(cfg, hwnd_map)
        cb = _find_ultra_cb(captured, 1)
        self.assertIsNotNone(cb)

        # All HWNDs invalid, resolve also returns nothing
        with patch('overlay.win32_capture.is_hwnd_valid', return_value=False), \
             patch('overlay.win32_capture.resolve_eve_window_handle', return_value=0):
            cb()

        # _last_cycle_time must remain 0.0 — no cooldown imposed
        self.assertEqual(hk._last_cycle_time, 0.0)
        types = [e[0] for e in hk._hotkey_ultra_events]
        self.assertIn('invalid_hwnd', types)

    def test_cache_refresh_ok_event_logged(self):
        """A stale-then-resolved HWND must emit cache_refresh_ok to the ring buffer."""
        import overlay.replicator_hotkeys as hk
        hk._hwnd_cache = {'EVE - Alpha': 0, 'EVE - Beta': 0}  # stale
        cfg = self._base_cfg()
        captured = _capture_ultra_callbacks(cfg, {})
        hk._hwnd_cache = {'EVE - Alpha': 0, 'EVE - Beta': 0}
        cb = _find_ultra_cb(captured, 1)
        self.assertIsNotNone(cb)

        notify_mock = MagicMock()
        with patch('overlay.win32_capture.is_hwnd_valid', side_effect=lambda h: h != 0 and True), \
             patch('overlay.win32_capture.resolve_eve_window_handle', return_value=1099), \
             patch('overlay.win32_capture.focus_eve_window_ultra_verified',
                   return_value=(True, True, 1099, 4.0)), \
             patch('overlay.replication_overlay.ReplicationOverlay'
                   '.notify_active_client_changed', notify_mock):
            cb()

        types = [e[0] for e in hk._hotkey_ultra_events]
        self.assertIn('cache_refresh_ok', types)


if __name__ == '__main__':
    unittest.main()
