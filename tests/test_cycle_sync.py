"""Tests: hotkey cycle index synchronization after direct replica selection."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reset_hotkey_state():
    """Reset all module-level cycle state in replicator_hotkeys."""
    import overlay.replicator_hotkeys as hk
    hk._last_cycle_client_id = None
    hk._last_cycle_client_id_time = 0.0
    hk._last_group_index.clear()
    hk._last_hk_cfg = {}
    hk._cached_titles = []
    hk._hwnd_cache = {}


def _make_hk_cfg(groups: dict) -> dict:
    """Build a minimal hk_cfg with the given groups dict."""
    return {'groups': groups, 'per_client': {}}


def _make_group(clients_order: list, enabled: bool = True, name: str = '') -> dict:
    return {
        'enabled': enabled,
        'clients_order': clients_order,
        'name': name or ('group-' + clients_order[0][:5] if clients_order else 'g'),
        'next': 'F14',
        'prev': 'F15',
    }


# ---------------------------------------------------------------------------
# TestNoteActiveClientChanged
# ---------------------------------------------------------------------------

class TestNoteActiveClientChanged(unittest.TestCase):

    def setUp(self):
        _reset_hotkey_state()

    def tearDown(self):
        _reset_hotkey_state()

    def _configure_groups(self, groups: dict):
        import overlay.replicator_hotkeys as hk
        hk._last_hk_cfg = _make_hk_cfg(groups)

    def test_updates_last_cycle_client_id(self):
        import overlay.replicator_hotkeys as hk
        hk.note_active_client_changed('EVE — Alice', source='test')
        self.assertEqual(hk._last_cycle_client_id, 'EVE — Alice')

    def test_updates_last_cycle_client_id_time(self):
        import overlay.replicator_hotkeys as hk
        before = time.monotonic()
        hk.note_active_client_changed('EVE — Bob', source='test')
        self.assertGreaterEqual(hk._last_cycle_client_id_time, before)

    def test_updates_group_index_for_matching_group(self):
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure_groups({'g1': _make_group(clients)})

        # Simulate: hotkey cycled to C (idx 2)
        hk._last_group_index['g1'] = 2
        hk._last_cycle_client_id = 'EVE — C'

        # User clicks A directly
        hk.note_active_client_changed('EVE — A', source='replica_click')

        self.assertEqual(hk._last_group_index['g1'], 0)

    def test_does_not_update_group_index_when_not_in_group(self):
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C']
        self._configure_groups({'g1': _make_group(clients)})
        hk._last_group_index['g1'] = 1

        # Client X is not in g1
        hk.note_active_client_changed('EVE — X', source='replica_click')

        # g1 index must remain unchanged
        self.assertEqual(hk._last_group_index['g1'], 1)
        # But last_cycle_client_id is updated
        self.assertEqual(hk._last_cycle_client_id, 'EVE — X')

    def test_updates_all_groups_containing_client(self):
        import overlay.replicator_hotkeys as hk
        clients_g1 = ['EVE — A', 'EVE — B', 'EVE — C']
        clients_g2 = ['EVE — C', 'EVE — D', 'EVE — E']
        self._configure_groups({
            'g1': _make_group(clients_g1),
            'g2': _make_group(clients_g2),
        })
        hk._last_group_index['g1'] = 2
        hk._last_group_index['g2'] = 0

        hk.note_active_client_changed('EVE — C', source='test')

        self.assertEqual(hk._last_group_index['g1'], 2)  # C is at idx 2 in g1
        self.assertEqual(hk._last_group_index['g2'], 0)  # C is at idx 0 in g2

    def test_skips_disabled_groups(self):
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C']
        disabled = _make_group(clients)
        disabled['enabled'] = False
        self._configure_groups({'g1': disabled})
        hk._last_group_index['g1'] = 2

        hk.note_active_client_changed('EVE — A', source='test')

        # Disabled group must NOT be updated
        self.assertEqual(hk._last_group_index['g1'], 2)

    def test_updates_global_index_when_in_cached_titles(self):
        import overlay.replicator_hotkeys as hk
        hk._cached_titles = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        hk._last_group_index['__global__'] = 2  # was at C

        hk.note_active_client_changed('EVE — A', source='test')

        self.assertEqual(hk._last_group_index['__global__'], 0)

    def test_no_op_when_empty_title(self):
        import overlay.replicator_hotkeys as hk
        hk._last_cycle_client_id = 'EVE — Prev'
        hk.note_active_client_changed('', source='test')
        self.assertEqual(hk._last_cycle_client_id, 'EVE — Prev')

    def test_no_op_groups_when_hk_cfg_empty(self):
        import overlay.replicator_hotkeys as hk
        hk._last_hk_cfg = {}
        hk._last_group_index['g1'] = 2

        hk.note_active_client_changed('EVE — A', source='test')

        self.assertEqual(hk._last_group_index['g1'], 2)  # untouched


# ---------------------------------------------------------------------------
# TestCycleSyncScenario — end-to-end cycle index logic
# ---------------------------------------------------------------------------

class TestCycleSyncScenario(unittest.TestCase):
    """
    Simulate the resolver logic of _cycle_group in isolation to verify that
    after note_active_client_changed, the next hotkey starts from the correct
    client — not from a stale index.
    """

    def setUp(self):
        _reset_hotkey_state()

    def tearDown(self):
        _reset_hotkey_state()

    def _configure(self, clients_order: list, group_id: str = 'g1'):
        import overlay.replicator_hotkeys as hk
        hk._last_hk_cfg = _make_hk_cfg({group_id: _make_group(clients_order)})
        hk._cached_titles = list(clients_order)

    def _simulate_resolver(self, titles: list, group_id: str = 'g1') -> int:
        """Replicate the _cycle_group index-resolver priority logic."""
        import overlay.replicator_hotkeys as hk
        now = time.monotonic()

        current_idx = -1
        if (hk._last_cycle_client_id and hk._last_cycle_client_id in titles
                and (now - hk._last_cycle_client_id_time) < 5.0):
            current_idx = titles.index(hk._last_cycle_client_id)

        if current_idx == -1:
            current_idx = hk._last_group_index.get(group_id, -1)

        return current_idx

    def _simulate_cycle(self, titles: list, direction: int = 1,
                        group_id: str = 'g1') -> str:
        """Simulate one cycle step; returns target title."""
        current_idx = self._simulate_resolver(titles, group_id)
        start = current_idx if current_idx != -1 else -1
        for attempt in range(1, len(titles) + 1):
            idx = (start + direction * attempt) % len(titles)
            return titles[idx]
        return ''

    def test_click_A_then_hotkey_goes_to_B(self):
        """Core bug scenario: click A after cycling to C → hotkey must go to B not D."""
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure(clients)

        # Simulate hotkey cycled to C (index 2)
        hk._last_cycle_client_id = 'EVE — C'
        hk._last_cycle_client_id_time = time.monotonic()
        hk._last_group_index['g1'] = 2

        # User clicks A directly → sync state
        hk.note_active_client_changed('EVE — A', source='replica_click')

        target = self._simulate_cycle(clients)
        self.assertEqual(target, 'EVE — B',
                         f"Expected 'EVE — B' after clicking A, got {target!r}")

    def test_click_B_then_hotkey_goes_to_C(self):
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D', 'EVE — E']
        self._configure(clients)

        hk._last_cycle_client_id = 'EVE — E'
        hk._last_cycle_client_id_time = time.monotonic()
        hk._last_group_index['g1'] = 4

        hk.note_active_client_changed('EVE — B', source='replica_click')

        target = self._simulate_cycle(clients)
        self.assertEqual(target, 'EVE — C')

    def test_click_last_then_hotkey_wraps_to_A(self):
        """Clicking the last account; next hotkey should wrap to first."""
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure(clients)

        hk._last_cycle_client_id = 'EVE — B'
        hk._last_cycle_client_id_time = time.monotonic()
        hk._last_group_index['g1'] = 1

        hk.note_active_client_changed('EVE — D', source='replica_click')

        target = self._simulate_cycle(clients)
        self.assertEqual(target, 'EVE — A')

    def test_no_sync_stale_client_id_uses_last_group_index(self):
        """Without note_active_client_changed, stale last_cycle_client_id causes wrong cycle."""
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure(clients)

        # Stale: last_cycle_client_id is recent but points to C
        hk._last_cycle_client_id = 'EVE — C'
        hk._last_cycle_client_id_time = time.monotonic()
        hk._last_group_index['g1'] = 2

        # No note_active_client_changed called (bug scenario)
        # Resolver picks _last_cycle_client_id → C → cycles to D (wrong!)
        target = self._simulate_cycle(clients)
        self.assertEqual(target, 'EVE — D',
                         "Without sync, stale state produces D (the bug)")

    def test_with_sync_overrides_stale_client_id(self):
        """With note_active_client_changed, resolver picks the clicked client."""
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure(clients)

        hk._last_cycle_client_id = 'EVE — C'
        hk._last_cycle_client_id_time = time.monotonic()
        hk._last_group_index['g1'] = 2

        # Sync to A
        hk.note_active_client_changed('EVE — A', source='replica_click')

        target = self._simulate_cycle(clients)
        self.assertEqual(target, 'EVE — B',
                         "With sync, resolver uses A and cycles to B (the fix)")

    def test_multi_group_sync_consistency(self):
        """Clicking a shared client updates both group indices."""
        import overlay.replicator_hotkeys as hk
        clients_g1 = ['EVE — A', 'EVE — B', 'EVE — C']
        clients_g2 = ['EVE — D', 'EVE — E', 'EVE — A']
        hk._last_hk_cfg = _make_hk_cfg({
            'g1': _make_group(clients_g1),
            'g2': _make_group(clients_g2),
        })
        hk._last_group_index['g1'] = 2  # was at C
        hk._last_group_index['g2'] = 1  # was at E

        hk.note_active_client_changed('EVE — A', source='test')

        self.assertEqual(hk._last_group_index['g1'], 0)  # A is idx 0 in g1
        self.assertEqual(hk._last_group_index['g2'], 2)  # A is idx 2 in g2

    def test_prev_direction_from_synced_state(self):
        """Sync to C, press 'prev' hotkey → must go to B."""
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure(clients)

        hk._last_cycle_client_id = 'EVE — A'
        hk._last_cycle_client_id_time = time.monotonic()
        hk._last_group_index['g1'] = 0

        hk.note_active_client_changed('EVE — C', source='test')

        target = self._simulate_cycle(clients, direction=-1)
        self.assertEqual(target, 'EVE — B')

    def test_repeated_sync_overwrites_correctly(self):
        """Multiple sequential syncs; last one wins."""
        import overlay.replicator_hotkeys as hk
        clients = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        self._configure(clients)

        hk.note_active_client_changed('EVE — A', source='test')
        hk.note_active_client_changed('EVE — D', source='test')
        hk.note_active_client_changed('EVE — B', source='test')

        self.assertEqual(hk._last_cycle_client_id, 'EVE — B')
        self.assertEqual(hk._last_group_index.get('g1'), 1)


# ---------------------------------------------------------------------------
# TestResolutionPriority
# ---------------------------------------------------------------------------

class TestResolutionPriority(unittest.TestCase):
    """Verify that last_cycle_client_id takes priority over last_group_index."""

    def setUp(self):
        _reset_hotkey_state()

    def tearDown(self):
        _reset_hotkey_state()

    def test_client_id_priority_over_group_index(self):
        """If last_cycle_client_id=A and last_group_index=2, resolver uses A (idx 0)."""
        import overlay.replicator_hotkeys as hk
        titles = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']
        now = time.monotonic()

        hk._last_cycle_client_id = 'EVE — A'
        hk._last_cycle_client_id_time = now
        hk._last_group_index['g1'] = 2  # stale, points to C

        # Simulate resolver
        current_idx = -1
        if (hk._last_cycle_client_id and hk._last_cycle_client_id in titles
                and (now - hk._last_cycle_client_id_time) < 5.0):
            current_idx = titles.index(hk._last_cycle_client_id)
        if current_idx == -1:
            current_idx = hk._last_group_index.get('g1', -1)

        self.assertEqual(current_idx, 0,
                         "last_cycle_client_id=A should resolve to idx 0, not stale idx 2")

    def test_group_index_fallback_when_client_id_old(self):
        """If last_cycle_client_id is > 5s old, falls through to last_group_index."""
        import overlay.replicator_hotkeys as hk
        titles = ['EVE — A', 'EVE — B', 'EVE — C', 'EVE — D']

        hk._last_cycle_client_id = 'EVE — A'
        hk._last_cycle_client_id_time = time.monotonic() - 10.0  # 10s ago → stale
        hk._last_group_index['g1'] = 2  # C at idx 2

        now = time.monotonic()
        current_idx = -1
        if (hk._last_cycle_client_id and hk._last_cycle_client_id in titles
                and (now - hk._last_cycle_client_id_time) < 5.0):
            current_idx = titles.index(hk._last_cycle_client_id)
        if current_idx == -1:
            current_idx = hk._last_group_index.get('g1', -1)

        self.assertEqual(current_idx, 2,
                         "Stale client_id should fall through to last_group_index=2")


if __name__ == '__main__':
    unittest.main()
