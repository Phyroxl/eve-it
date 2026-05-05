"""Tests: verify_foreground_window and _cycle_group index-guard behaviour."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from collections import deque

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── verify_foreground_window ──────────────────────────────────────────────────

class TestVerifyForegroundWindow(unittest.TestCase):

    def test_returns_false_for_zero_hwnd(self):
        from overlay.win32_capture import verify_foreground_window
        verified, actual, elapsed = verify_foreground_window(0)
        self.assertFalse(verified)
        self.assertEqual(actual, 0)
        self.assertAlmostEqual(elapsed, 0.0, places=2)

    def test_returns_true_when_fg_matches_immediately(self):
        from overlay.win32_capture import verify_foreground_window
        with patch('overlay.win32_capture.user32') as mock_u32:
            mock_u32.GetForegroundWindow.return_value = 9999
            verified, actual, elapsed = verify_foreground_window(9999, timeout_ms=40, poll_ms=2)
        self.assertTrue(verified)
        self.assertEqual(actual, 9999)
        self.assertLess(elapsed, 40)

    def test_returns_false_on_timeout_when_fg_never_matches(self):
        from overlay.win32_capture import verify_foreground_window
        with patch('overlay.win32_capture.user32') as mock_u32:
            mock_u32.GetForegroundWindow.return_value = 1111  # different hwnd
            verified, actual, elapsed = verify_foreground_window(9999, timeout_ms=20, poll_ms=2)
        self.assertFalse(verified)
        self.assertEqual(actual, 1111)
        self.assertGreaterEqual(elapsed, 18)  # near timeout

    def test_returns_actual_hwnd_on_failure(self):
        from overlay.win32_capture import verify_foreground_window
        with patch('overlay.win32_capture.user32') as mock_u32:
            mock_u32.GetForegroundWindow.return_value = 5555
            verified, actual, _ = verify_foreground_window(7777, timeout_ms=15, poll_ms=2)
        self.assertFalse(verified)
        self.assertEqual(actual, 5555)

    def test_verify_matches_after_delay(self):
        """Simulate FG changing to target after a short delay."""
        from overlay.win32_capture import verify_foreground_window
        call_count = [0]
        def side_effect():
            call_count[0] += 1
            # First 2 calls: wrong hwnd; then correct
            return 9999 if call_count[0] > 2 else 1111
        with patch('overlay.win32_capture.user32') as mock_u32:
            mock_u32.GetForegroundWindow.side_effect = side_effect
            verified, actual, elapsed = verify_foreground_window(9999, timeout_ms=100, poll_ms=1)
        self.assertTrue(verified)
        self.assertEqual(actual, 9999)


# ── _cycle_group index guard ──────────────────────────────────────────────────

def _reset_hk_state():
    import overlay.replicator_hotkeys as hk
    hk._cycle_in_progress = False
    hk._last_cycle_time = 0.0
    hk._last_cycle_client_id = None
    hk._last_cycle_client_id_time = 0.0
    hk._last_group_index = {}
    hk._hotkey_diagnostics_enabled = False
    hk._hotkey_diagnostics_callback = None
    hk._hotkey_diagnostics_events = deque(maxlen=1000)
    hk._hwnd_cache = {}


def _build_cfg(titles=None):
    if titles is None:
        titles = ['EVE - Alpha', 'EVE - Beta', 'EVE - Gamma']
    return {
        'hotkeys': {
            'groups': {
                'g1': {
                    'enabled': True,
                    'clients_order': titles,
                    'next': 'F14',
                    'prev': 'CTRL+F14',
                    'name': 'Test',
                }
            }
        }
    }


def _extract_cycle_group(cfg):
    """Register hotkeys and grab the _cycle_group partial for g1 direction=+1."""
    import threading
    import overlay.replicator_hotkeys as hk
    captured = []

    def fake_start(self_t):
        captured.extend(self_t._args[0] if self_t._args else [])

    with patch.object(threading.Thread, 'start', fake_start), \
         patch.object(hk._user32, 'RegisterHotKey', return_value=True), \
         patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
         patch('overlay.win32_capture.resolve_eve_window_handle', return_value=0):
        hk.register_hotkeys(cfg)

    for _, _, cb in captured:
        if hasattr(cb, 'func') and cb.func.__name__ == '_cycle_group':
            if cb.args[1] == 1:
                return cb
    return None


class TestCycleGroupIndexGuard(unittest.TestCase):

    def setUp(self):
        _reset_hk_state()

    def tearDown(self):
        _reset_hk_state()

    def _run_cb(self, cb, verified, fg_hwnd=1001, fg_title='EVE - Alpha'):
        """Helper: run cb() with standard patches. Patches ReplicationOverlay class directly."""
        with patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.focus_eve_window_perf', return_value=(True, 'ok')), \
             patch('overlay.win32_capture.verify_foreground_window',
                   return_value=(verified, 1002 if verified else 0, 2.0 if verified else 40.0)), \
             patch('overlay.win32_capture.get_foreground_hwnd', return_value=fg_hwnd), \
             patch('overlay.win32_capture.get_window_title', return_value=fg_title), \
             patch('overlay.replication_overlay.ReplicationOverlay') as mock_cls, \
             patch('overlay.replication_overlay._OVERLAY_REGISTRY', set()):
            mock_cls.notify_active_client_changed = MagicMock()
            cb()

    def test_index_advanced_when_verified(self):
        """When focus_ok=True and verified=True, _last_group_index must advance."""
        import overlay.replicator_hotkeys as hk
        cfg = _build_cfg()
        hk._hwnd_cache = {'EVE - Alpha': 1001, 'EVE - Beta': 1002, 'EVE - Gamma': 1003}
        cb = _extract_cycle_group(cfg)
        self.assertIsNotNone(cb, "No _cycle_group partial found")

        self._run_cb(cb, verified=True)

        self.assertIn('g1', hk._last_group_index)
        self.assertEqual(hk._last_cycle_client_id, 'EVE - Beta')

    def test_index_not_advanced_when_not_verified(self):
        """When focus_ok=True but verified=False, _last_group_index must NOT advance."""
        import overlay.replicator_hotkeys as hk
        cfg = _build_cfg()
        hk._hwnd_cache = {'EVE - Alpha': 1001, 'EVE - Beta': 1002, 'EVE - Gamma': 1003}
        cb = _extract_cycle_group(cfg)
        self.assertIsNotNone(cb)

        self._run_cb(cb, verified=False)

        self.assertNotIn('g1', hk._last_group_index)
        self.assertIsNone(hk._last_cycle_client_id)

    def test_focus_verify_result_event_emitted(self):
        """A focus_verify_result diagnostic event must be emitted."""
        import overlay.replicator_hotkeys as hk
        hk.set_hotkey_diagnostics_enabled(True)
        cfg = _build_cfg()
        hk._hwnd_cache = {'EVE - Alpha': 1001, 'EVE - Beta': 1002, 'EVE - Gamma': 1003}
        cb = _extract_cycle_group(cfg)
        self.assertIsNotNone(cb)

        self._run_cb(cb, verified=True)

        types = [e['type'] for e in hk.get_hotkey_diagnostics_events()]
        self.assertIn('focus_verify_result', types)

    def test_focus_verify_result_contains_verified_field(self):
        import overlay.replicator_hotkeys as hk
        hk.set_hotkey_diagnostics_enabled(True)
        cfg = _build_cfg()
        hk._hwnd_cache = {'EVE - Alpha': 1001, 'EVE - Beta': 1002, 'EVE - Gamma': 1003}
        cb = _extract_cycle_group(cfg)

        self._run_cb(cb, verified=False)

        evs = [e for e in hk.get_hotkey_diagnostics_events() if e['type'] == 'focus_verify_result']
        self.assertTrue(evs)
        self.assertFalse(evs[0]['verified'])
        self.assertEqual(evs[0]['actual_hwnd'], 0)


if __name__ == '__main__':
    unittest.main()
