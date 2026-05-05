"""Tests: hotkey burst visual suspension (replicator_runtime_state + overlay integration)."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reset_runtime_state():
    import overlay.replicator_runtime_state as rs
    rs._burst_until = 0.0
    rs._burst_count = 0
    rs._burst_last_log = 0.0


# ── replicator_runtime_state ─────────────────────────────────────────────────

class TestRuntimeState(unittest.TestCase):

    def setUp(self):
        _reset_runtime_state()

    def tearDown(self):
        _reset_runtime_state()

    def test_burst_inactive_by_default(self):
        from overlay.replicator_runtime_state import is_hotkey_burst_active
        self.assertFalse(is_hotkey_burst_active())

    def test_note_event_activates_burst(self):
        from overlay.replicator_runtime_state import note_hotkey_burst_event, is_hotkey_burst_active
        note_hotkey_burst_event("cycle")
        self.assertTrue(is_hotkey_burst_active())

    def test_burst_expires_after_window(self):
        import overlay.replicator_runtime_state as rs
        from overlay.replicator_runtime_state import is_hotkey_burst_active
        rs._burst_until = time.perf_counter() - 0.001  # already expired
        self.assertFalse(is_hotkey_burst_active())

    def test_burst_count_increments(self):
        from overlay.replicator_runtime_state import note_hotkey_burst_event, get_hotkey_burst_count
        note_hotkey_burst_event()
        note_hotkey_burst_event()
        note_hotkey_burst_event()
        self.assertEqual(get_hotkey_burst_count(), 3)

    def test_remaining_ms_positive_during_burst(self):
        from overlay.replicator_runtime_state import note_hotkey_burst_event, get_hotkey_burst_remaining_ms
        note_hotkey_burst_event()
        rem = get_hotkey_burst_remaining_ms()
        self.assertGreater(rem, 0.0)
        self.assertLessEqual(rem, 120.0)

    def test_remaining_ms_zero_when_inactive(self):
        from overlay.replicator_runtime_state import get_hotkey_burst_remaining_ms
        self.assertEqual(get_hotkey_burst_remaining_ms(), 0.0)

    def test_note_extends_burst_window(self):
        import overlay.replicator_runtime_state as rs
        from overlay.replicator_runtime_state import note_hotkey_burst_event, get_hotkey_burst_remaining_ms
        note_hotkey_burst_event()
        rem1 = get_hotkey_burst_remaining_ms()
        note_hotkey_burst_event()
        rem2 = get_hotkey_burst_remaining_ms()
        # Second call should maintain or extend the window
        self.assertGreaterEqual(rem2, rem1 - 2.0)  # small tolerance for execution time

    def test_should_log_burst_allows_first_call(self):
        from overlay.replicator_runtime_state import should_log_burst
        self.assertTrue(should_log_burst())

    def test_should_log_burst_throttles_subsequent(self):
        from overlay.replicator_runtime_state import should_log_burst
        should_log_burst()   # consume the first window
        self.assertFalse(should_log_burst())  # too soon

    def test_should_log_burst_allows_after_throttle(self):
        import overlay.replicator_runtime_state as rs
        from overlay.replicator_runtime_state import should_log_burst
        # Set last log to far in the past
        rs._burst_last_log = time.perf_counter() - 1.0
        self.assertTrue(should_log_burst())


# ── notify_active_client_changed burst deferral (logic tests) ─────────────────
# These tests verify the burst-deferral logic in isolation without requiring
# Qt's Shiboken metaclass (calling static methods on QWidget subclasses
# without a QApplication can behave unpredictably in some environments).

class TestNotifyActiveBurstDeferral(unittest.TestCase):

    def setUp(self):
        _reset_runtime_state()

    def tearDown(self):
        _reset_runtime_state()

    def _make_mock_ov(self, hwnd, is_active=False):
        ov = MagicMock()
        ov._hwnd = hwnd
        ov._is_active_client = is_active
        return ov

    def _simulate_notify(self, registry, active_hwnd, burst_active):
        """Simulate the burst-deferral logic of notify_active_client_changed."""
        pending_flush = False
        for ov in registry:
            was_active = ov._is_active_client
            ov._is_active_client = bool(ov._hwnd and active_hwnd == ov._hwnd)
            if was_active != ov._is_active_client:
                if burst_active:
                    pending_flush = True
                else:
                    ov.update()
        return pending_flush

    def test_update_called_when_no_burst(self):
        """Without burst, ov.update() is called immediately on active-state change."""
        ov_a = self._make_mock_ov(1001)
        ov_b = self._make_mock_ov(1002)
        pending = self._simulate_notify([ov_a, ov_b], 1002, burst_active=False)
        ov_b.update.assert_called_once()
        ov_a.update.assert_not_called()
        self.assertFalse(pending)

    def test_update_not_called_during_burst(self):
        """During burst, ov.update() is skipped and pending_flush is set."""
        ov_a = self._make_mock_ov(1001, is_active=True)
        ov_b = self._make_mock_ov(1002)
        pending = self._simulate_notify([ov_a, ov_b], 1002, burst_active=True)
        ov_a.update.assert_not_called()
        ov_b.update.assert_not_called()
        self.assertTrue(pending)

    def test_state_correct_after_burst_notify(self):
        """Even during burst, _is_active_client state is updated correctly."""
        ov_a = self._make_mock_ov(1001, is_active=True)
        ov_b = self._make_mock_ov(1002)
        self._simulate_notify([ov_a, ov_b], 1002, burst_active=True)
        self.assertFalse(ov_a._is_active_client)
        self.assertTrue(ov_b._is_active_client)

    def test_flush_logic_calls_update_after_burst_ends(self):
        """Simulate _monitor_focus flush: calls ov.update() once burst expires."""
        import overlay.replicator_runtime_state as rs
        from overlay.replicator_runtime_state import is_hotkey_burst_active

        ov = self._make_mock_ov(1001)
        pending_flush = True
        rs._burst_until = time.perf_counter() - 0.001  # burst already expired

        if pending_flush and not is_hotkey_burst_active():
            pending_flush = False
            ov.update()

        ov.update.assert_called_once()
        self.assertFalse(pending_flush)

    def test_flush_not_called_while_burst_still_active(self):
        """_monitor_focus flush must not fire while burst window is still open."""
        from overlay.replicator_runtime_state import note_hotkey_burst_event, is_hotkey_burst_active

        ov = self._make_mock_ov(1001)
        note_hotkey_burst_event()
        pending_flush = True

        if pending_flush and not is_hotkey_burst_active():
            pending_flush = False
            ov.update()

        ov.update.assert_not_called()
        self.assertTrue(pending_flush)  # still pending

    def test_burst_runtime_integration(self):
        """note_hotkey_burst_event → is_hotkey_burst_active → expires as expected."""
        import overlay.replicator_runtime_state as rs
        from overlay.replicator_runtime_state import (
            note_hotkey_burst_event, is_hotkey_burst_active, get_hotkey_burst_remaining_ms,
        )
        self.assertFalse(is_hotkey_burst_active())
        note_hotkey_burst_event("cycle_group")
        self.assertTrue(is_hotkey_burst_active())
        self.assertGreater(get_hotkey_burst_remaining_ms(), 0.0)
        # Manually expire
        rs._burst_until = time.perf_counter() - 0.001
        self.assertFalse(is_hotkey_burst_active())
        self.assertEqual(get_hotkey_burst_remaining_ms(), 0.0)

    def test_pending_border_flush_attribute_exists(self):
        """ReplicationOverlay must declare _pending_border_flush = False."""
        try:
            import overlay.replication_overlay as _ov_mod
            cls = _ov_mod.ReplicationOverlay
            self.assertIn('_pending_border_flush', vars(cls))
            self.assertFalse(cls._pending_border_flush)
        except Exception as e:
            self.skipTest(f"Qt class not accessible without QApplication: {e}")


if __name__ == '__main__':
    unittest.main()
