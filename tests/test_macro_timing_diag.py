"""Tests: passive macro input timing diagnostics."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reset_diag_state():
    import overlay.replicator_hotkeys as hk
    hk._last_focus_done_time = 0.0
    hk._last_focus_done_hwnd = 0
    hk._last_focus_done_target = ''
    hk._last_focus_done_ok = False
    hk._macro_seq_keys = []
    hk._macro_seq_key_times = []
    hk._macro_seq_last_key_perf = 0.0
    hk._hotkey_diagnostics_enabled = False
    hk._hotkey_diagnostics_events.clear()


# ── Focus-done snapshot ───────────────────────────────────────────────────────

class TestFocusDoneSnapshot(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()

    def tearDown(self):
        _reset_diag_state()

    def test_snapshot_initial_values(self):
        from overlay.replicator_hotkeys import _get_last_focus_done_snapshot
        snap = _get_last_focus_done_snapshot()
        self.assertEqual(snap['time'], 0.0)
        self.assertEqual(snap['hwnd'], 0)
        self.assertEqual(snap['target'], '')
        self.assertFalse(snap['ok'])

    def test_snapshot_reflects_module_state(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = 999.0
        hk._last_focus_done_hwnd = 12345
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._last_focus_done_ok = True
        from overlay.replicator_hotkeys import _get_last_focus_done_snapshot
        snap = _get_last_focus_done_snapshot()
        self.assertEqual(snap['time'], 999.0)
        self.assertEqual(snap['hwnd'], 12345)
        self.assertEqual(snap['target'], 'EVE - Alpha')
        self.assertTrue(snap['ok'])


# ── Delta classification ──────────────────────────────────────────────────────

class TestMacroKeyClassification(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True

    def tearDown(self):
        _reset_diag_state()

    def _call_with_fg(self, vk, fg_hwnd=1001):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=fg_hwnd):
            _on_macro_key(vk)
        return [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_key_observed']

    def test_too_early_under_10ms(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.005  # 5ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x70)  # F1
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'too_early')
        self.assertEqual(evs[0]['key'], 'F1')

    def test_risky_10_to_30ms(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.020  # 20ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x71)  # F2
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'risky')

    def test_safe_ish_30ms_or_more(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.060  # 60ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x72)  # F3
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'safe-ish')

    def test_no_event_when_no_focus_done(self):
        """No macro_key_observed event if _last_focus_done_time == 0."""
        evs = self._call_with_fg(0x70)
        self.assertEqual(len(evs), 0)

    def test_no_event_when_diagnostics_disabled(self):
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = False
        hk._last_focus_done_time = time.perf_counter() - 0.060
        hk._last_focus_done_ok = True
        evs = self._call_with_fg(0x70)
        self.assertEqual(len(evs), 0)

    def test_no_event_when_delta_too_old(self):
        """Delta > 5000ms: key is unrelated to last focus, no event."""
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 6.0  # 6 seconds ago
        hk._last_focus_done_ok = True
        evs = self._call_with_fg(0x70)
        self.assertEqual(len(evs), 0)

    def test_event_carries_fg_hwnd(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.050
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Bravo'
        evs = self._call_with_fg(0x73, fg_hwnd=9876)  # F4
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['fg_hwnd'], 9876)
        self.assertEqual(evs[0]['focus_target'], 'EVE - Bravo')

    def test_on_macro_key_returns_none(self):
        """_on_macro_key must not consume the key — it returns None."""
        from overlay.replicator_hotkeys import _on_macro_key
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.050
        hk._last_focus_done_ok = True
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=0):
            result = _on_macro_key(0x70)
        self.assertIsNone(result)


# ── MACRO_SEQ grouping ────────────────────────────────────────────────────────

class TestMacroSeqGrouping(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True
        hk._last_focus_done_time = time.perf_counter() - 0.100  # 100ms (safe-ish)
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'

    def tearDown(self):
        _reset_diag_state()

    def _press(self, *vks, fg_hwnd=1001):
        from overlay.replicator_hotkeys import _on_macro_key
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=fg_hwnd):
            for vk in vks:
                _on_macro_key(vk)

    def test_single_key_seq_flushed(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._press(0x70)  # F1
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertIn('F1', seqs[0]['keys_seen'])
        self.assertEqual(seqs[0]['key_count'], 1)

    def test_multi_key_seq_grouped(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._press(0x70, 0x71, 0x72)  # F1, F2, F3
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['key_count'], 3)
        for key in ('F1', 'F2', 'F3'):
            self.assertIn(key, seqs[0]['keys_seen'])

    def test_missing_keys_reported(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._press(0x70)  # F1 only
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        missing = seqs[0]['keys_missing']
        self.assertNotIn('F1', missing)
        for key in ('F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8'):
            self.assertIn(key, missing)

    def test_seq_split_after_timeout(self):
        """Keys > 300ms apart must form separate sequences."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1 — starts seq 1
            hk._macro_seq_last_key_perf -= 0.401  # simulate 401ms elapsed
            _on_macro_key(0x71)  # F2 — flushes seq 1, starts seq 2

        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        # Seq 1 (F1) flushed; seq 2 (F2) still pending
        self.assertEqual(len(seqs), 1)
        self.assertIn('F1', seqs[0]['keys_seen'])
        self.assertNotIn('F2', seqs[0]['keys_seen'])

    def test_flush_clears_state(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._press(0x70, 0x71)
        _flush_macro_seq()
        self.assertEqual(hk._macro_seq_keys, [])
        self.assertEqual(hk._macro_seq_key_times, [])
        self.assertEqual(hk._macro_seq_last_key_perf, 0.0)

    def test_flush_noop_when_empty(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        _flush_macro_seq()  # no keys — should not emit any event
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 0)

    def test_seq_duration_positive_for_multi_key(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._press(0x70, 0x71, 0x72)
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        # Duration should be >= 0
        self.assertGreaterEqual(seqs[0]['seq_duration_ms'], 0.0)


# ── set_hotkey_diagnostics_enabled hook lifecycle ─────────────────────────────

class TestHookLifecycle(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()

    def tearDown(self):
        _reset_diag_state()

    def test_enable_calls_install(self):
        import overlay.replicator_hotkeys as hk
        with patch.object(hk, '_install_macro_key_hook') as mock_install, \
             patch.object(hk, '_uninstall_macro_key_hook'):
            hk.set_hotkey_diagnostics_enabled(True, None)
            mock_install.assert_called_once()

    def test_disable_calls_uninstall(self):
        import overlay.replicator_hotkeys as hk
        with patch.object(hk, '_install_macro_key_hook'), \
             patch.object(hk, '_uninstall_macro_key_hook') as mock_uninstall:
            hk.set_hotkey_diagnostics_enabled(True, None)
            hk.set_hotkey_diagnostics_enabled(False, None)
            mock_uninstall.assert_called_once()


if __name__ == '__main__':
    unittest.main()
