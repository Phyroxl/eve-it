"""Tests: live diagnostics API in replicator_hotkeys."""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import overlay.replicator_hotkeys as hk


def _reset_diag():
    hk.set_hotkey_diagnostics_enabled(False, None)
    hk.clear_hotkey_diagnostics()


class TestDiagnosticsDisabled(unittest.TestCase):

    def setUp(self):
        _reset_diag()

    def test_diag_event_noop_when_disabled(self):
        hk._diag_event('cycle_group_enter', group_id='1', direction='next')
        self.assertEqual(len(hk.get_hotkey_diagnostics_events()), 0)

    def test_callback_not_called_when_disabled(self):
        calls = []
        hk._hotkey_diagnostics_callback = calls.append
        hk._diag_event('cycle_group_enter', group_id='1', direction='next')
        # callback must NOT be called — _enabled is still False
        self.assertEqual(len(calls), 0)


class TestDiagnosticsEnabled(unittest.TestCase):

    def setUp(self):
        _reset_diag()

    def tearDown(self):
        _reset_diag()

    def test_event_stored_in_ring_buffer(self):
        hk.set_hotkey_diagnostics_enabled(True)
        hk._diag_event('cycle_group_enter', group_id='1', direction='next')
        events = hk.get_hotkey_diagnostics_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'cycle_group_enter')

    def test_event_has_timestamp(self):
        hk.set_hotkey_diagnostics_enabled(True)
        hk._diag_event('test_event', x=1)
        ev = hk.get_hotkey_diagnostics_events()[0]
        self.assertIn('ts', ev)
        self.assertRegex(ev['ts'], r'^\d{2}:\d{2}:\d{2}\.\d{3}$')

    def test_callback_called_with_event(self):
        calls = []
        hk.set_hotkey_diagnostics_enabled(True, calls.append)
        hk._diag_event('cycle_group_skipped', reason='cooldown', delta_ms=5.0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['type'], 'cycle_group_skipped')
        self.assertEqual(calls[0]['reason'], 'cooldown')

    def test_callback_exception_does_not_propagate(self):
        def bad_cb(ev):
            raise RuntimeError("boom")
        hk.set_hotkey_diagnostics_enabled(True, bad_cb)
        try:
            hk._diag_event('cycle_group_enter', group_id='1', direction='next')
        except RuntimeError:
            self.fail("_diag_event must not propagate callback exceptions")

    def test_clear_empties_buffer(self):
        hk.set_hotkey_diagnostics_enabled(True)
        hk._diag_event('ev1')
        hk._diag_event('ev2')
        hk.clear_hotkey_diagnostics()
        self.assertEqual(len(hk.get_hotkey_diagnostics_events()), 0)

    def test_disable_removes_callback(self):
        calls = []
        hk.set_hotkey_diagnostics_enabled(True, calls.append)
        hk.set_hotkey_diagnostics_enabled(False, None)
        hk._diag_event('cycle_group_enter')
        self.assertEqual(len(calls), 0)

    def test_ring_buffer_bounded_at_1000(self):
        hk.set_hotkey_diagnostics_enabled(True)
        for i in range(1200):
            hk._diag_event('x', i=i)
        self.assertLessEqual(len(hk.get_hotkey_diagnostics_events()), 1000)

    def test_get_events_returns_snapshot(self):
        hk.set_hotkey_diagnostics_enabled(True)
        hk._diag_event('a')
        snap1 = hk.get_hotkey_diagnostics_events()
        hk._diag_event('b')
        snap2 = hk.get_hotkey_diagnostics_events()
        self.assertEqual(len(snap1), 1)
        self.assertEqual(len(snap2), 2)

    def test_extra_fields_preserved_in_event(self):
        hk.set_hotkey_diagnostics_enabled(True)
        hk._diag_event('focus_result', focus_ok=True, total_ms=1.5, target_title='EVE - Alpha')
        ev = hk.get_hotkey_diagnostics_events()[0]
        self.assertTrue(ev['focus_ok'])
        self.assertAlmostEqual(ev['total_ms'], 1.5)
        self.assertEqual(ev['target_title'], 'EVE - Alpha')


if __name__ == '__main__':
    unittest.main()
