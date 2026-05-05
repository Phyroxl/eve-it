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
        if verified:
            reliable_ret = (True, 'reliable_focus strategy=fast verified=True verify_ms=2.0 actual=1002 total_ms=5.0')
        else:
            reliable_ret = (False, 'reliable_focus strategy=failed verified=False actual=0 total_ms=40.0 attempts=fast:false,raise_sync:false,attach_thread:false')
        with patch('overlay.win32_capture.is_hwnd_valid', return_value=True), \
             patch('overlay.win32_capture.focus_eve_window_reliable', return_value=reliable_ret), \
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


# ── focus_eve_window_reliable unit tests ─────────────────────────────────────

class TestFocusEveWindowReliable(unittest.TestCase):
    """Tests for the budgeted focus_eve_window_reliable function."""

    def _make_user32(self, is_window=True, is_visible=True, is_iconic=False, fg_hwnd=9999):
        m = MagicMock()
        m.IsWindow.return_value = int(is_window)
        m.IsWindowVisible.return_value = int(is_visible)
        m.IsIconic.return_value = int(is_iconic)
        m.GetForegroundWindow.return_value = fg_hwnd
        m.SetForegroundWindow.return_value = 1
        m.SetWindowPos.return_value = 1
        m.ShowWindow.return_value = 1
        return m

    def test_returns_false_for_hwnd_zero(self):
        from overlay.win32_capture import focus_eve_window_reliable
        ok, detail = focus_eve_window_reliable(0)
        self.assertFalse(ok)
        self.assertIn('invalid_hwnd', detail)

    def test_returns_false_for_invalid_window(self):
        from overlay.win32_capture import focus_eve_window_reliable
        with patch('overlay.win32_capture.user32') as mu:
            mu.IsWindow.return_value = 0
            ok, detail = focus_eve_window_reliable(1234)
        self.assertFalse(ok)
        self.assertIn('invalid_hwnd', detail)

    def test_detail_contains_strategy_and_total_ms(self):
        from overlay.win32_capture import focus_eve_window_reliable
        with patch('overlay.win32_capture.user32') as mu, \
             patch('overlay.win32_capture.verify_foreground_window', return_value=(True, 9999, 3.0)):
            mu.IsWindow.return_value = 1
            mu.IsWindowVisible.return_value = 1
            mu.IsIconic.return_value = 0
            ok, detail = focus_eve_window_reliable(9999)
        self.assertTrue(ok)
        self.assertIn('strategy=', detail)
        self.assertIn('total_ms=', detail)

    def test_fast_strategy_on_immediate_verify(self):
        from overlay.win32_capture import focus_eve_window_reliable
        with patch('overlay.win32_capture.user32') as mu, \
             patch('overlay.win32_capture.verify_foreground_window', return_value=(True, 9999, 2.0)):
            mu.IsWindow.return_value = 1
            mu.IsWindowVisible.return_value = 1
            mu.IsIconic.return_value = 0
            ok, detail = focus_eve_window_reliable(9999)
        self.assertTrue(ok)
        self.assertIn('strategy=fast', detail)
        self.assertIn('verified=True', detail)

    def test_retry_async_strategy_when_fast_fails(self):
        from overlay.win32_capture import focus_eve_window_reliable
        call_count = [0]
        def fake_verify(hwnd, timeout_ms=40, poll_ms=2):
            call_count[0] += 1
            if call_count[0] == 1:
                return False, 0, float(timeout_ms)  # fast fails
            return True, hwnd, 5.0                   # retry_async succeeds
        with patch('overlay.win32_capture.user32') as mu, \
             patch('overlay.win32_capture.verify_foreground_window', side_effect=fake_verify):
            mu.IsWindow.return_value = 1
            mu.IsWindowVisible.return_value = 1
            mu.IsIconic.return_value = 0
            ok, detail = focus_eve_window_reliable(9999, max_total_ms=60)
        self.assertTrue(ok)
        self.assertIn('strategy=retry_async', detail)

    def test_fails_fast_respects_budget(self):
        """With max_total_ms=1, should return quickly with budget_exceeded or fast:skipped."""
        from overlay.win32_capture import focus_eve_window_reliable
        with patch('overlay.win32_capture.user32') as mu, \
             patch('overlay.win32_capture.verify_foreground_window', return_value=(False, 0, 50.0)):
            mu.IsWindow.return_value = 1
            mu.IsWindowVisible.return_value = 1
            mu.IsIconic.return_value = 0
            t0 = time.perf_counter()
            ok, detail = focus_eve_window_reliable(9999, max_total_ms=1)
            elapsed = (time.perf_counter() - t0) * 1000
        self.assertFalse(ok)
        # Must not have taken much longer than budget
        self.assertLess(elapsed, 500)

    def test_no_attach_thread_when_flag_false(self):
        """AttachThreadInput must NOT be called when ENABLE_ATTACH_THREAD_FALLBACK=False."""
        import overlay.win32_capture as wc
        from overlay.win32_capture import focus_eve_window_reliable
        original = wc.ENABLE_ATTACH_THREAD_FALLBACK
        try:
            wc.ENABLE_ATTACH_THREAD_FALLBACK = False
            with patch('overlay.win32_capture.user32') as mu, \
                 patch('overlay.win32_capture.verify_foreground_window', return_value=(False, 0, 20.0)):
                mu.IsWindow.return_value = 1
                mu.IsWindowVisible.return_value = 1
                mu.IsIconic.return_value = 0
                focus_eve_window_reliable(9999, max_total_ms=60)
            mu.AttachThreadInput.assert_not_called()
        finally:
            wc.ENABLE_ATTACH_THREAD_FALLBACK = original

    def test_budget_exceeded_flag_in_detail(self):
        """When all strategies exhaust the budget, detail should contain budget_exceeded."""
        from overlay.win32_capture import focus_eve_window_reliable
        with patch('overlay.win32_capture.user32') as mu, \
             patch('overlay.win32_capture.verify_foreground_window', return_value=(False, 0, 30.0)):
            mu.IsWindow.return_value = 1
            mu.IsWindowVisible.return_value = 1
            mu.IsIconic.return_value = 0
            ok, detail = focus_eve_window_reliable(9999, max_total_ms=60)
        self.assertFalse(ok)
        self.assertIn('budget_exceeded=', detail)


if __name__ == '__main__':
    unittest.main()
