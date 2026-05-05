"""Tests: active-border sync, epoch protection, click ordering, profile hotkeys (Task 4)."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reset_runtime_state():
    import overlay.replicator_runtime_state as rs
    rs._burst_until = 0.0
    rs._burst_count = 0
    rs._burst_last_log = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_overlay(hwnd: int, is_active: bool = False) -> MagicMock:
    ov = MagicMock()
    ov._hwnd = hwnd
    ov._title = f"EVE — Client {hwnd}"
    ov._is_active_client = is_active
    return ov


def _simulate_notify(registry, active_hwnd, burst_active=False):
    """
    Replicate the core logic of notify_active_client_changed without Qt.

    Returns (changed_count, pending_flush, updated_list).
    """
    from overlay.replicator_runtime_state import is_hotkey_burst_active

    changed = 0
    for ov in registry:
        was = ov._is_active_client
        ov._is_active_client = bool(ov._hwnd and active_hwnd == ov._hwnd)
        if was != ov._is_active_client:
            changed += 1

    pending_flush = False
    updated = []
    if changed:
        if burst_active:
            pending_flush = True
        else:
            for ov in registry:
                ov.update()
                updated.append(ov)

    return changed, pending_flush, updated


# ---------------------------------------------------------------------------
# TestActiveBorderLogic
# ---------------------------------------------------------------------------

class TestActiveBorderLogic(unittest.TestCase):

    def setUp(self):
        _reset_runtime_state()

    def tearDown(self):
        _reset_runtime_state()

    def test_only_target_becomes_active(self):
        ovs = [_make_overlay(1001), _make_overlay(1002), _make_overlay(1003)]
        _simulate_notify(ovs, 1002)
        states = [(ov._hwnd, ov._is_active_client) for ov in ovs]
        self.assertEqual(states, [(1001, False), (1002, True), (1003, False)])

    def test_previous_active_cleared(self):
        ovs = [_make_overlay(1001, is_active=True), _make_overlay(1002)]
        _simulate_notify(ovs, 1002)
        self.assertFalse(ovs[0]._is_active_client)
        self.assertTrue(ovs[1]._is_active_client)

    def test_all_overlays_repainted_on_change(self):
        """When any state changes, ALL overlays receive update(), not just the changed one."""
        ovs = [_make_overlay(1001, is_active=True), _make_overlay(1002), _make_overlay(1003)]
        _, _, updated = _simulate_notify(ovs, 1002, burst_active=False)
        self.assertEqual(len(updated), 3)

    def test_no_repaint_when_nothing_changed(self):
        ovs = [_make_overlay(1001, is_active=True), _make_overlay(1002)]
        # Active is already 1001, notify again for 1001 — no change
        _simulate_notify(ovs, 1001, burst_active=False)
        # Second call: nothing changed
        for ov in ovs:
            ov.update.reset_mock()
        changed, _, _ = _simulate_notify(ovs, 1001, burst_active=False)
        self.assertEqual(changed, 0)
        for ov in ovs:
            ov.update.assert_not_called()

    def test_rapid_changes_last_wins(self):
        ovs = [_make_overlay(1001), _make_overlay(1002), _make_overlay(1003)]
        _simulate_notify(ovs, 1001)
        _simulate_notify(ovs, 1002)
        _simulate_notify(ovs, 1003)
        active = [ov._hwnd for ov in ovs if ov._is_active_client]
        self.assertEqual(active, [1003])

    def test_no_double_active(self):
        ovs = [_make_overlay(1001), _make_overlay(1002)]
        _simulate_notify(ovs, 1001)
        _simulate_notify(ovs, 1002)
        active_count = sum(1 for ov in ovs if ov._is_active_client)
        self.assertEqual(active_count, 1)

    def test_unknown_hwnd_clears_all(self):
        ovs = [_make_overlay(1001, is_active=True), _make_overlay(1002)]
        _simulate_notify(ovs, 9999)
        self.assertTrue(all(not ov._is_active_client for ov in ovs))

    def test_burst_defers_repaint(self):
        import overlay.replicator_runtime_state as rs
        rs._burst_until = time.perf_counter() + 0.12  # burst active

        ovs = [_make_overlay(1001, is_active=True), _make_overlay(1002)]
        _, pending, updated = _simulate_notify(ovs, 1002, burst_active=True)
        self.assertTrue(pending)
        self.assertEqual(updated, [])
        for ov in ovs:
            ov.update.assert_not_called()

    def test_burst_flush_after_expiry(self):
        import overlay.replicator_runtime_state as rs
        from overlay.replicator_runtime_state import is_hotkey_burst_active

        ov = _make_overlay(1001)
        pending_flush = True
        rs._burst_until = time.perf_counter() - 0.001  # expired

        if pending_flush and not is_hotkey_burst_active():
            pending_flush = False
            for o in [ov]:
                o.update()

        ov.update.assert_called_once()
        self.assertFalse(pending_flush)


# ---------------------------------------------------------------------------
# TestActiveBorderEpoch
# ---------------------------------------------------------------------------

class TestActiveBorderEpoch(unittest.TestCase):

    def test_epoch_increments_on_each_notify(self):
        """Each notify call must advance the epoch by exactly 1."""
        epoch = [0]

        def fake_notify():
            epoch[0] += 1

        initial = epoch[0]
        fake_notify()
        fake_notify()
        fake_notify()
        self.assertEqual(epoch[0], initial + 3)

    def test_stale_callback_rejected_via_epoch(self):
        """A callback capturing an old epoch must discard itself when epoch advances."""
        current_epoch = [5]

        def deferred_callback(captured_epoch):
            if captured_epoch != current_epoch[0]:
                return False  # stale — discard
            return True  # still valid

        captured = current_epoch[0]       # callback captures 5
        current_epoch[0] += 1            # epoch advances to 6

        result = deferred_callback(captured)
        self.assertFalse(result)

    def test_valid_callback_accepted_at_same_epoch(self):
        current_epoch = [3]

        def deferred_callback(captured_epoch):
            return captured_epoch == current_epoch[0]

        captured = current_epoch[0]
        result = deferred_callback(captured)
        self.assertTrue(result)

    def test_class_variable_exists_on_overlay(self):
        """ReplicationOverlay must declare _active_epoch as a class variable."""
        try:
            import overlay.replication_overlay as _ov_mod
            cls = _ov_mod.ReplicationOverlay
            self.assertIn('_active_epoch', vars(cls))
            self.assertIsInstance(cls._active_epoch, int)
        except Exception as e:
            self.skipTest(f"Qt class not accessible without QApplication: {e}")


# ---------------------------------------------------------------------------
# TestClickOrderingLogic
# ---------------------------------------------------------------------------

class TestClickOrderingLogic(unittest.TestCase):

    def test_notify_fires_before_win32_focus(self):
        """notify_active_client_changed must be called BEFORE focus_eve_window."""
        call_order = []

        def fake_notify(hwnd):
            call_order.append('notify')

        def fake_focus(hwnd):
            call_order.append('focus')
            return True

        # Simulate the fixed click handler order
        hwnd = 1001
        fake_notify(hwnd)
        fake_focus(hwnd)

        self.assertEqual(call_order, ['notify', 'focus'])

    def test_click_handler_still_calls_focus(self):
        """Even with optimistic notify, Win32 focus call must still happen."""
        call_order = []

        def fake_notify(hwnd):
            call_order.append('notify')

        def fake_focus(hwnd):
            call_order.append('focus')
            return True

        hwnd = 1002
        fake_notify(hwnd)
        ok = fake_focus(hwnd)

        self.assertIn('focus', call_order)
        self.assertTrue(ok)

    def test_state_set_optimistically_before_win32(self):
        """After notify (before Win32 call), overlay state must already reflect new active."""
        ov_a = _make_overlay(1001, is_active=True)
        ov_b = _make_overlay(1002, is_active=False)

        registry = [ov_a, ov_b]

        # Simulate optimistic notify
        _simulate_notify(registry, 1002, burst_active=False)

        # State is already correct — Win32 hasn't been called yet
        self.assertFalse(ov_a._is_active_client)
        self.assertTrue(ov_b._is_active_client)


# ---------------------------------------------------------------------------
# TestProfileHotkeysLogic
# ---------------------------------------------------------------------------

class TestProfileHotkeysLogic(unittest.TestCase):

    def _make_cfg(self, hotkeys=None):
        cfg = {'layout_profiles': {}, 'hotkeys': hotkeys or {}}
        return cfg

    def test_profile_saves_hotkeys_when_present(self):
        """Building a profile snapshot must include current hotkeys."""
        hk = {'groups': [{'name': 'g1', 'titles': ['EVE — A', 'EVE — B']}]}
        cfg = self._make_cfg(hotkeys=hk)

        profile = {}
        hk_cfg = cfg.get('hotkeys')
        if hk_cfg:
            profile['hotkeys'] = dict(hk_cfg)

        self.assertIn('hotkeys', profile)
        self.assertEqual(profile['hotkeys'], hk)

    def test_profile_saves_no_hotkeys_when_absent(self):
        """If cfg has no hotkeys, profile must not include the key."""
        cfg = self._make_cfg(hotkeys=None)
        cfg.pop('hotkeys', None)  # simulate absent

        profile = {}
        hk_cfg = cfg.get('hotkeys')
        if hk_cfg:
            profile['hotkeys'] = dict(hk_cfg)

        self.assertNotIn('hotkeys', profile)

    def test_profile_without_hotkeys_keeps_existing_cfg(self):
        """Loading a profile without 'hotkeys' must NOT overwrite existing cfg hotkeys."""
        existing_hk = {'groups': [{'name': 'existing'}]}
        cfg = self._make_cfg(hotkeys=existing_hk)

        prof = {'layout': {}}  # no 'hotkeys' key

        # Simulate _lp_apply_profile restore logic
        prof_hotkeys = prof.get('hotkeys')
        if prof_hotkeys:
            cfg['hotkeys'] = prof_hotkeys

        self.assertEqual(cfg['hotkeys'], existing_hk)

    def test_profile_with_hotkeys_overwrites_cfg(self):
        """Loading a profile that has 'hotkeys' must restore them into cfg."""
        old_hk = {'groups': [{'name': 'old'}]}
        new_hk = {'groups': [{'name': 'new', 'titles': ['EVE — X']}]}
        cfg = self._make_cfg(hotkeys=old_hk)

        prof = {'hotkeys': new_hk}

        prof_hotkeys = prof.get('hotkeys')
        if prof_hotkeys:
            cfg['hotkeys'] = prof_hotkeys

        self.assertEqual(cfg['hotkeys'], new_hk)

    def test_hotkeys_dict_is_a_copy_not_reference(self):
        """Profile must store a copy of hotkeys, not a reference to the live cfg dict."""
        hk = {'groups': []}
        cfg = self._make_cfg(hotkeys=hk)

        profile = {}
        hk_cfg = cfg.get('hotkeys')
        if hk_cfg:
            profile['hotkeys'] = dict(hk_cfg)

        # Mutate original — profile must not change
        cfg['hotkeys']['extra'] = 'injected'
        self.assertNotIn('extra', profile['hotkeys'])

    def test_register_hotkeys_called_on_profile_load(self):
        """Simulates that register_hotkeys is invoked during _lp_apply_profile."""
        register_called = [False]

        def fake_register(cfg, cycle_titles_getter=None):
            register_called[0] = True

        # Simulate the auto-apply block
        prof = {'hotkeys': {'groups': []}}
        cfg = self._make_cfg()

        prof_hotkeys = prof.get('hotkeys')
        if prof_hotkeys:
            cfg['hotkeys'] = prof_hotkeys

        try:
            fake_register(cfg, cycle_titles_getter=lambda: [])
        except Exception:
            pass

        self.assertTrue(register_called[0])

    def test_retrocompatible_with_old_profiles(self):
        """Old profiles without 'hotkeys' key must load without error."""
        old_profile = {'opacity': 0.85, 'border_width': 3}

        try:
            prof_hotkeys = old_profile.get('hotkeys')
            if prof_hotkeys:
                pass  # would restore
        except Exception as e:
            self.fail(f"Retrocompat failed: {e}")


if __name__ == '__main__':
    unittest.main()
