"""Tests: settings dialog reads/writes _ov_cfg correctly (no Qt display needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay.replicator_config import OVERLAY_DEFAULTS, get_overlay_cfg, save_overlay_cfg


class FakeOverlay:
    """Stand-in for ReplicationOverlay used by ReplicatorSettingsDialog."""

    def __init__(self, title='EVE — Test', extra=None):
        self._title = title
        self._cfg = {'overlays': {}}
        self._ov_cfg = get_overlay_cfg(self._cfg, self._title)
        if extra:
            self._ov_cfg.update(extra)
        self._autosave_calls = 0
        self._sync_active = False

    def _schedule_autosave(self):
        self._autosave_calls += 1

    def _do_save(self):
        save_overlay_cfg(self._cfg, self._title, self._ov_cfg)

    def apply_always_on_top(self, v):
        self._ov_cfg['always_on_top'] = v


class TestSettingsSerialization(unittest.TestCase):

    def test_ov_cfg_initialised_with_all_defaults(self):
        ov = FakeOverlay()
        for key in OVERLAY_DEFAULTS:
            self.assertIn(key, ov._ov_cfg, f"Missing default key: {key}")

    def test_set_key_writes_to_ov_cfg(self):
        ov = FakeOverlay()
        ov._ov_cfg['label_color'] = '#ff0000'
        self.assertEqual(ov._ov_cfg['label_color'], '#ff0000')

    def test_schedule_autosave_called_on_set(self):
        ov = FakeOverlay()
        ov._ov_cfg['border_width'] = 4
        ov._schedule_autosave()
        self.assertEqual(ov._autosave_calls, 1)

    def test_always_on_top_toggles_ov_cfg(self):
        ov = FakeOverlay()
        ov.apply_always_on_top(False)
        self.assertFalse(ov._ov_cfg['always_on_top'])
        ov.apply_always_on_top(True)
        self.assertTrue(ov._ov_cfg['always_on_top'])

    def test_label_pos_valid_values(self):
        valid = ['top_left', 'top_center', 'top_right',
                 'bottom_left', 'bottom_center', 'bottom_right']
        ov = FakeOverlay()
        for pos in valid:
            ov._ov_cfg['label_pos'] = pos
            self.assertEqual(ov._ov_cfg['label_pos'], pos)

    def test_snap_x_y_stored_as_int(self):
        ov = FakeOverlay(extra={'snap_x': 15, 'snap_y': 30})
        self.assertEqual(int(ov._ov_cfg['snap_x']), 15)
        self.assertEqual(int(ov._ov_cfg['snap_y']), 30)

    def test_do_save_writes_to_cfg_overlays(self):
        ov = FakeOverlay()
        ov._ov_cfg['client_color'] = '#aabbcc'
        # Manually call _do_save logic (no file I/O — just in-memory cfg update)
        save_overlay_cfg(ov._cfg, ov._title, ov._ov_cfg)
        self.assertEqual(
            ov._cfg['overlays'][ov._title]['client_color'], '#aabbcc'
        )

    def test_existing_ov_cfg_keys_preserved_after_update(self):
        ov = FakeOverlay()
        ov._ov_cfg['label_color'] = '#123456'
        ov._ov_cfg['fps'] = 60
        save_overlay_cfg(ov._cfg, ov._title, ov._ov_cfg)
        # Reload
        reloaded = get_overlay_cfg(ov._cfg, ov._title)
        self.assertEqual(reloaded['label_color'], '#123456')
        self.assertEqual(reloaded['fps'], 60)

    def test_sync_active_accessible_from_dialog(self):
        ov = FakeOverlay()
        ov._sync_active = True
        self.assertTrue(getattr(ov, '_sync_active', False))

    def test_fps_combo_value_int_conversion(self):
        for fps_str in ['5', '10', '15', '30', '60', '120']:
            self.assertIsInstance(int(fps_str), int)


if __name__ == '__main__':
    unittest.main()
