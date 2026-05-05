"""Tests: passive macro input timing diagnostics — epoch-aware grouping."""
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
    hk._focus_epoch_id = 0
    hk._macro_seq_epoch_id = -1
    hk._macro_seq_target = ''
    hk._macro_seq_focus_hwnd = 0
    hk._macro_seq_focus_ok = False
    hk._macro_seq_keys = []
    hk._macro_seq_key_times = []
    hk._macro_seq_key_deltas = []
    hk._macro_seq_key_fg_hwnds = []
    hk._macro_seq_last_key_perf = 0.0
    hk._macro_stats_total = 0
    hk._macro_stats_complete_safe = 0
    hk._macro_stats_complete_risky = 0
    hk._macro_stats_incomplete = 0
    hk._macro_stats_fg_mismatch = 0
    hk._macro_stats_min_first_delta = float('inf')
    hk._macro_stats_max_first_delta = 0.0
    hk._macro_stats_recommended_min_delay = 0.0
    hk._macro_observed_epochs = set()
    hk._macro_missing_pending_epoch = -1
    hk._macro_missing_pending_target = ''
    hk._macro_missing_pending_time = 0.0
    hk._macro_stats_missing_after_focus = 0
    hk._macro_stats_missing_targets = []
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
    """New thresholds: <30ms=too_early, 30-50ms=risky, >=50ms=safer"""

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

    def test_too_early_under_30ms(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.010  # 10ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x70)  # F1
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'too_early')
        self.assertEqual(evs[0]['key'], 'F1')

    def test_too_early_at_0ms(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.001  # ~1ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x70)  # F1
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'too_early')

    def test_risky_30_to_50ms(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.040  # 40ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x71)  # F2
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'risky')

    def test_safer_50ms_or_more(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.060  # 60ms ago
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        evs = self._call_with_fg(0x72)  # F3
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['timing_class'], 'safer')

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

    def test_event_carries_epoch_id(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.060
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 7
        evs = self._call_with_fg(0x70)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['epoch'], 7)

    def test_event_carries_fg_hwnd(self):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.060
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
        hk._last_focus_done_time = time.perf_counter() - 0.060
        hk._last_focus_done_ok = True
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=0):
            result = _on_macro_key(0x70)
        self.assertIsNone(result)


# ── MACRO_SEQ epoch-aware grouping ───────────────────────────────────────────

class TestMacroSeqEpochGrouping(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True
        hk._last_focus_done_time = time.perf_counter() - 0.100  # 100ms
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1

    def tearDown(self):
        _reset_diag_state()

    def _press(self, *vks, fg_hwnd=1001):
        from overlay.replicator_hotkeys import _on_macro_key
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=fg_hwnd):
            for vk in vks:
                _on_macro_key(vk)

    def test_same_epoch_groups_keys_together(self):
        """Keys within same epoch and 300ms window form one sequence."""
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._press(0x70, 0x71, 0x72)  # F1, F2, F3
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['key_count'], 3)
        for key in ('F1', 'F2', 'F3'):
            self.assertIn(key, seqs[0]['keys_seen'])

    def test_different_epochs_split_sequences(self):
        """The count=80 bug: epoch change must split the sequence."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        import overlay.replicator_hotkeys as hk

        # Epoch 1: press F1
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1

        # Simulate macro cycling to next account — epoch increments
        hk._focus_epoch_id = 2
        hk._last_focus_done_target = 'EVE - Bravo'
        hk._last_focus_done_hwnd = 1002

        # Epoch 2: press F1 again — should flush epoch 1 first
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1002):
            _on_macro_key(0x70)  # F1 again

        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        # Epoch 1 was flushed on epoch change; epoch 2 is still pending
        self.assertEqual(len(seqs), 1, "Epoch change must produce exactly one flushed sequence")
        self.assertEqual(seqs[0]['epoch'], 1)
        self.assertEqual(seqs[0]['key_count'], 1)

        # Flush epoch 2
        _flush_macro_seq()
        seqs2 = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs2), 2)
        self.assertEqual(seqs2[1]['epoch'], 2)

    def test_epoch_change_triggers_flush(self):
        """Verify that merely changing epoch causes flush without explicit call."""
        from overlay.replicator_hotkeys import _on_macro_key
        import overlay.replicator_hotkeys as hk

        hk._focus_epoch_id = 5
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1 in epoch 5

        # Now change epoch — next key press should flush
        hk._focus_epoch_id = 6
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1002):
            _on_macro_key(0x71)  # F2 in epoch 6 — triggers flush of epoch 5

        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['epoch'], 5)

    def test_timeout_triggers_flush(self):
        """Keys > 300ms apart must form separate sequences."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1 — starts seq
            hk._macro_seq_last_key_perf -= 0.401  # simulate 401ms elapsed
            _on_macro_key(0x71)  # F2 — flushes seq 1, starts seq 2

        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
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
        self.assertEqual(hk._macro_seq_key_deltas, [])
        self.assertEqual(hk._macro_seq_key_fg_hwnds, [])
        self.assertEqual(hk._macro_seq_last_key_perf, 0.0)
        self.assertEqual(hk._macro_seq_epoch_id, -1)
        self.assertEqual(hk._macro_seq_target, '')
        self.assertEqual(hk._macro_seq_focus_hwnd, 0)
        self.assertFalse(hk._macro_seq_focus_ok)

    def test_flush_noop_when_empty(self):
        from overlay.replicator_hotkeys import _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        _flush_macro_seq()  # no keys — should not emit any event
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 0)


# ── MACRO_SEQ analysis ────────────────────────────────────────────────────────

class TestMacroSeqAnalysis(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True

    def tearDown(self):
        _reset_diag_state()

    def _setup_focus(self, hwnd=1001, target='EVE - Alpha', delta_ago_s=0.100):
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - delta_ago_s
        hk._last_focus_done_hwnd = hwnd
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = target
        hk._focus_epoch_id = 1

    def _press_all_8(self, fg_hwnd=1001):
        from overlay.replicator_hotkeys import _on_macro_key
        vks = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]  # F1-F8
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=fg_hwnd):
            for vk in vks:
                _on_macro_key(vk)

    def _get_seq(self):
        import overlay.replicator_hotkeys as hk
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        return seqs

    def test_complete_safe_all_8_keys_first_delta_50ms(self):
        """All 8 keys, first_delta >= 50ms → complete_safe."""
        from overlay.replicator_hotkeys import _flush_macro_seq
        self._setup_focus(delta_ago_s=0.080)  # 80ms
        self._press_all_8()
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['sequence_status'], 'complete_safe')
        self.assertEqual(seqs[0]['key_count'], 8)
        self.assertEqual(seqs[0]['keys_missing'], [])

    def test_complete_risky_all_8_keys_first_delta_under_50ms(self):
        """All 8 keys, first_delta < 50ms → complete_risky."""
        from overlay.replicator_hotkeys import _flush_macro_seq
        self._setup_focus(delta_ago_s=0.035)  # 35ms
        self._press_all_8()
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['sequence_status'], 'complete_risky')

    def test_incomplete_missing_f4(self):
        """Missing F4 → incomplete status."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        self._setup_focus(delta_ago_s=0.080)
        vks = [0x70, 0x71, 0x72, 0x74, 0x75, 0x76, 0x77]  # F1,F2,F3,F5,F6,F7,F8 (no F4)
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            for vk in vks:
                _on_macro_key(vk)
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['sequence_status'], 'incomplete')
        self.assertIn('F4', seqs[0]['keys_missing'])

    def test_foreground_mismatch(self):
        """fg_hwnd != focus_hwnd → foreground_mismatch status."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        self._setup_focus(hwnd=1001, delta_ago_s=0.080)
        # Press with fg_hwnd different from focus_hwnd (1001)
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=9999):
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['sequence_status'], 'foreground_mismatch')
        self.assertTrue(len(seqs[0]['fg_mismatch_keys']) > 0)

    def test_first_last_min_max_deltas(self):
        """first/last/min/max delta fields are present and reasonable."""
        from overlay.replicator_hotkeys import _flush_macro_seq
        self._setup_focus(delta_ago_s=0.080)
        self._press_all_8()
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        seq = seqs[0]
        self.assertIn('first_key_delta_ms', seq)
        self.assertIn('last_key_delta_ms', seq)
        self.assertIn('min_delta_ms', seq)
        self.assertIn('max_delta_ms', seq)
        self.assertGreaterEqual(seq['first_key_delta_ms'], 0.0)
        self.assertGreaterEqual(seq['last_key_delta_ms'], 0.0)
        self.assertGreaterEqual(seq['min_delta_ms'], 0.0)
        self.assertGreaterEqual(seq['max_delta_ms'], seq['min_delta_ms'])

    def test_too_early_keys_classification(self):
        """Keys pressed <30ms after focus are flagged as too_early."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        # Set focus_done just now so delta is ~0
        hk._last_focus_done_time = time.perf_counter() - 0.005  # 5ms
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        self.assertIn('F1', seqs[0]['too_early_keys'])

    def test_risky_keys_classification(self):
        """Keys pressed 30-50ms after focus are flagged as risky."""
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        import overlay.replicator_hotkeys as hk
        hk._last_focus_done_time = time.perf_counter() - 0.040  # 40ms
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1
        _flush_macro_seq()
        seqs = self._get_seq()
        self.assertEqual(len(seqs), 1)
        self.assertIn('F1', seqs[0]['risky_keys'])


# ── Recommended delay logic ───────────────────────────────────────────────────

class TestRecommendedDelay(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True

    def tearDown(self):
        _reset_diag_state()

    def _press_all_8_with_delta(self, delta_s, hwnd=1001):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        hk._last_focus_done_time = time.perf_counter() - delta_s
        hk._last_focus_done_hwnd = hwnd
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=hwnd):
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        return seqs[0] if seqs else None

    def test_risky_first_delta_under_50ms_rec_50(self):
        """complete_risky (first_delta < 50ms) → recommended = 50ms."""
        seq = self._press_all_8_with_delta(0.035)  # 35ms
        self.assertIsNotNone(seq)
        self.assertEqual(seq['sequence_status'], 'complete_risky')
        self.assertEqual(seq['recommended_min_delay_ms'], 50.0)

    def test_rec_70_when_first_delta_50_to_70ms(self):
        """first_delta in [50, 70) → recommended = 70ms."""
        seq = self._press_all_8_with_delta(0.060)  # 60ms
        self.assertIsNotNone(seq)
        self.assertEqual(seq['sequence_status'], 'complete_safe')
        self.assertEqual(seq['recommended_min_delay_ms'], 70.0)

    def test_rec_round_up_to_10_when_first_delta_ge_70ms(self):
        """first_delta >= 70ms → round up to next multiple of 10."""
        seq = self._press_all_8_with_delta(0.083)  # ~83ms → ceil(83/10)*10 = 90
        self.assertIsNotNone(seq)
        self.assertEqual(seq['sequence_status'], 'complete_safe')
        self.assertEqual(seq['recommended_min_delay_ms'], 90.0)

    def test_incomplete_rec_max_80_first_plus_20(self):
        """incomplete → rec = max(80, first_delta + 20)."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        hk._last_focus_done_time = time.perf_counter() - 0.080  # 80ms
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        # Press only F1 (missing F2-F8)
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['sequence_status'], 'incomplete')
        first = seqs[0]['first_key_delta_ms']
        expected = max(80.0, first + 20.0)
        self.assertAlmostEqual(seqs[0]['recommended_min_delay_ms'], round(expected, 1), delta=1.0)

    def test_fg_mismatch_rec_max_80_first_plus_20(self):
        """foreground_mismatch → rec = max(80, first_delta + 20)."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        hk._last_focus_done_time = time.perf_counter() - 0.080  # 80ms
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=9999):  # mismatch
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0]['sequence_status'], 'foreground_mismatch')
        first = seqs[0]['first_key_delta_ms']
        expected = max(80.0, first + 20.0)
        self.assertAlmostEqual(seqs[0]['recommended_min_delay_ms'], round(expected, 1), delta=1.0)


# ── Macro summary stats ───────────────────────────────────────────────────────

class TestMacroSummary(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True

    def tearDown(self):
        _reset_diag_state()

    def test_initial_all_zeros(self):
        from overlay.replicator_hotkeys import get_macro_summary
        s = get_macro_summary()
        self.assertEqual(s['total_macro_sequences'], 0)
        self.assertEqual(s['complete_safe_count'], 0)
        self.assertEqual(s['complete_risky_count'], 0)
        self.assertEqual(s['incomplete_count'], 0)
        self.assertEqual(s['foreground_mismatch_count'], 0)
        self.assertEqual(s['min_first_delta_seen_ms'], 0.0)
        self.assertEqual(s['max_first_delta_seen_ms'], 0.0)
        self.assertEqual(s['recommended_min_delay_ms'], 0.0)

    def test_increments_on_complete_safe(self):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq, get_macro_summary
        hk._last_focus_done_time = time.perf_counter() - 0.100
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        s = get_macro_summary()
        self.assertEqual(s['total_macro_sequences'], 1)
        self.assertEqual(s['complete_safe_count'], 1)
        self.assertEqual(s['complete_risky_count'], 0)

    def test_increments_on_complete_risky(self):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq, get_macro_summary
        hk._last_focus_done_time = time.perf_counter() - 0.035  # 35ms
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        s = get_macro_summary()
        self.assertEqual(s['complete_risky_count'], 1)
        self.assertEqual(s['total_macro_sequences'], 1)

    def test_increments_on_incomplete(self):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq, get_macro_summary
        hk._last_focus_done_time = time.perf_counter() - 0.100
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # only F1
        _flush_macro_seq()
        s = get_macro_summary()
        self.assertEqual(s['incomplete_count'], 1)

    def test_increments_on_fg_mismatch(self):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq, get_macro_summary
        hk._last_focus_done_time = time.perf_counter() - 0.100
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=9999):
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        s = get_macro_summary()
        self.assertEqual(s['foreground_mismatch_count'], 1)

    def test_clear_resets_stats(self):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq, get_macro_summary, clear_hotkey_diagnostics
        hk._last_focus_done_time = time.perf_counter() - 0.100
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            for vk in [0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77]:
                _on_macro_key(vk)
        _flush_macro_seq()
        s_before = get_macro_summary()
        self.assertEqual(s_before['total_macro_sequences'], 1)

        clear_hotkey_diagnostics()
        s_after = get_macro_summary()
        self.assertEqual(s_after['total_macro_sequences'], 0)
        self.assertEqual(s_after['complete_safe_count'], 0)
        self.assertEqual(s_after['recommended_min_delay_ms'], 0.0)

    def test_get_macro_summary_returns_correct_structure(self):
        from overlay.replicator_hotkeys import get_macro_summary
        s = get_macro_summary()
        expected_keys = {
            'total_macro_sequences', 'complete_safe_count', 'complete_risky_count',
            'incomplete_count', 'foreground_mismatch_count',
            'min_first_delta_seen_ms', 'max_first_delta_seen_ms', 'recommended_min_delay_ms',
            'missing_after_focus_count', 'missing_after_focus_targets',
        }
        self.assertEqual(set(s.keys()), expected_keys)


# ── Hook lifecycle ────────────────────────────────────────────────────────────

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


# ── Replica window title filter ───────────────────────────────────────────────

class TestReplicaWindowFilter(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()

    def tearDown(self):
        _reset_diag_state()

    def test_replica_prefix_detected(self):
        from overlay.replicator_hotkeys import _is_replica_window_title
        self.assertTrue(_is_replica_window_title('Replica - EVE — Lana Drake'))
        self.assertTrue(_is_replica_window_title('Réplica - EVE — Lana Drake'))
        self.assertTrue(_is_replica_window_title('Replica — EVE — Lana Drake'))
        self.assertTrue(_is_replica_window_title('Réplica — EVE — Lana Drake'))

    def test_real_client_not_detected(self):
        from overlay.replicator_hotkeys import _is_replica_window_title
        self.assertFalse(_is_replica_window_title('EVE — Lana Drake'))
        self.assertFalse(_is_replica_window_title('EVE - Alpha'))
        self.assertFalse(_is_replica_window_title(''))
        self.assertFalse(_is_replica_window_title(None))

    def test_fg_replica_ignored_event_emitted(self):
        """When fg title starts with replica prefix, fg_replica_ignored event is emitted."""
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True
        hk._diag_event('fg_replica_ignored', fg_hwnd=9999, fg_title='Replica - EVE — Lana Drake')
        evs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'fg_replica_ignored']
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['fg_hwnd'], 9999)
        self.assertIn('Replica', evs[0]['fg_title'])

    def test_fg_replica_does_not_match_client(self):
        """_is_replica_window_title returns False for plain EVE client with same suffix."""
        from overlay.replicator_hotkeys import _is_replica_window_title
        # Even though 'EVE — Lana Drake' ⊂ 'Replica - EVE — Lana Drake',
        # the plain client title must NOT be classified as replica.
        self.assertFalse(_is_replica_window_title('EVE — Lana Drake'))


# ── Missing macro after focus detection ───────────────────────────────────────

class TestMissingMacroAfterFocus(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True

    def tearDown(self):
        _reset_diag_state()

    def _set_pending(self, epoch=5, target='EVE - Alpha'):
        import overlay.replicator_hotkeys as hk
        import time
        hk._macro_missing_pending_epoch = epoch
        hk._macro_missing_pending_target = target
        hk._macro_missing_pending_time = time.perf_counter() - 0.200

    def test_missing_detected_when_no_macro_observed(self):
        """check_and_emit emits macro_missing_after_focus when epoch has no observed keys."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        self._set_pending(epoch=5, target='EVE - Alpha')
        _check_and_emit_missing_macro('next_cycle_without_macro')
        evs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_missing_after_focus']
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['epoch'], 5)
        self.assertEqual(evs[0]['target'], 'EVE - Alpha')
        self.assertEqual(evs[0]['reason'], 'next_cycle_without_macro')

    def test_missing_not_emitted_when_macro_observed(self):
        """If epoch was observed in _macro_observed_epochs, no missing event."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        self._set_pending(epoch=5)
        hk._macro_observed_epochs.add(5)
        _check_and_emit_missing_macro('next_cycle_without_macro')
        evs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_missing_after_focus']
        self.assertEqual(len(evs), 0)

    def test_missing_not_emitted_when_no_pending(self):
        """With _macro_missing_pending_epoch = -1, no event emitted."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        hk._macro_missing_pending_epoch = -1
        _check_and_emit_missing_macro('next_cycle_without_macro')
        evs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_missing_after_focus']
        self.assertEqual(len(evs), 0)

    def test_pending_cleared_after_emission(self):
        """After emitting missing, pending state is cleared."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        self._set_pending(epoch=7)
        _check_and_emit_missing_macro('next_cycle_without_macro')
        self.assertEqual(hk._macro_missing_pending_epoch, -1)
        self.assertEqual(hk._macro_missing_pending_target, '')

    def test_pending_cleared_when_macro_was_observed(self):
        """When epoch was observed, pending is cleared without emitting."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        self._set_pending(epoch=3)
        hk._macro_observed_epochs.add(3)
        _check_and_emit_missing_macro('next_cycle_without_macro')
        self.assertEqual(hk._macro_missing_pending_epoch, -1)

    def test_stopping_flushes_missing(self):
        """diagnostic_stopped_without_macro reason is emitted by uninstall."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        self._set_pending(epoch=9, target='EVE - Bravo')
        _check_and_emit_missing_macro('diagnostic_stopped_without_macro')
        evs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_missing_after_focus']
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['reason'], 'diagnostic_stopped_without_macro')
        self.assertEqual(evs[0]['target'], 'EVE - Bravo')

    def test_macro_key_marks_epoch_observed(self):
        """_on_macro_key adds epoch to _macro_observed_epochs."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key
        hk._last_focus_done_time = time.perf_counter() - 0.060
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 4
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)  # F1
        self.assertIn(4, hk._macro_observed_epochs)

    def test_summary_includes_missing_count(self):
        """get_macro_summary() exposes missing_after_focus_count and targets."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import get_macro_summary, _check_and_emit_missing_macro
        self._set_pending(epoch=2, target='EVE - Charlie')
        _check_and_emit_missing_macro('next_cycle_without_macro')
        s = get_macro_summary()
        self.assertEqual(s['missing_after_focus_count'], 1)
        self.assertIn('EVE - Charlie', s['missing_after_focus_targets'])

    def test_missing_not_emitted_when_diag_disabled(self):
        """No emission if diagnostics are disabled."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _check_and_emit_missing_macro
        hk._hotkey_diagnostics_enabled = False
        self._set_pending(epoch=6)
        _check_and_emit_missing_macro('next_cycle_without_macro')
        evs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_missing_after_focus']
        self.assertEqual(len(evs), 0)


# ── Stale sequence classification ────────────────────────────────────────────

class TestStaleSequence(unittest.TestCase):

    def setUp(self):
        _reset_diag_state()
        import overlay.replicator_hotkeys as hk
        hk._hotkey_diagnostics_enabled = True

    def tearDown(self):
        _reset_diag_state()

    def _press_with_delta(self, delta_s, vk=0x70, hwnd=1001):
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        hk._last_focus_done_time = time.perf_counter() - delta_s
        hk._last_focus_done_hwnd = hwnd
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=hwnd):
            _on_macro_key(vk)
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        return seqs[0] if seqs else None

    def test_stale_over_1000ms_classified(self):
        """first_delta > 1000ms → status = stale_or_unrelated."""
        seq = self._press_with_delta(8.1)  # 8100ms
        self.assertIsNotNone(seq)
        self.assertEqual(seq['sequence_status'], 'stale_or_unrelated')

    def test_stale_rec_delay_is_zero(self):
        """stale_or_unrelated → rec_delay = 0 (no absurd recommendation)."""
        seq = self._press_with_delta(8.1)
        self.assertIsNotNone(seq)
        self.assertEqual(seq['recommended_min_delay_ms'], 0.0)

    def test_stale_does_not_update_min_first_delta(self):
        """stale sequence must not pollute _macro_stats_min_first_delta."""
        from overlay.replicator_hotkeys import get_macro_summary
        self._press_with_delta(8.1)
        s = get_macro_summary()
        self.assertEqual(s['min_first_delta_seen_ms'], 0.0)  # still at initial

    def test_stale_does_not_update_recommended_min_delay(self):
        """stale rec_delay=0 must not set recommended_min_delay to 8104ms."""
        from overlay.replicator_hotkeys import get_macro_summary
        self._press_with_delta(8.1)
        s = get_macro_summary()
        self.assertEqual(s['recommended_min_delay_ms'], 0.0)

    def test_normal_sequence_not_classified_stale(self):
        """first_delta <= 1000ms → not stale_or_unrelated."""
        seq = self._press_with_delta(0.080)  # 80ms
        self.assertIsNotNone(seq)
        self.assertNotEqual(seq['sequence_status'], 'stale_or_unrelated')

    def test_under_1000ms_not_stale(self):
        """first_delta < 1000ms → NOT stale_or_unrelated (use 999ms to avoid timing jitter)."""
        import overlay.replicator_hotkeys as hk
        from overlay.replicator_hotkeys import _on_macro_key, _flush_macro_seq
        hk._last_focus_done_time = time.perf_counter() - 0.999
        hk._last_focus_done_hwnd = 1001
        hk._last_focus_done_ok = True
        hk._last_focus_done_target = 'EVE - Alpha'
        hk._focus_epoch_id = 1
        with patch('overlay.win32_capture.get_foreground_hwnd', return_value=1001):
            _on_macro_key(0x70)
        _flush_macro_seq()
        seqs = [e for e in hk._hotkey_diagnostics_events if e['type'] == 'macro_seq_complete']
        self.assertEqual(len(seqs), 1)
        self.assertNotEqual(seqs[0]['sequence_status'], 'stale_or_unrelated')


if __name__ == '__main__':
    unittest.main()
