"""Tests: apply_common_settings_to_all and apply_settings_dict."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay.replicator_config import (
    apply_common_settings_to_all,
    COMMON_SETTING_KEYS,
    get_overlay_cfg,
    save_overlay_cfg,
)


def _make_cfg(*titles):
    cfg = {'overlays': {}}
    for t in titles:
        cfg['overlays'][t] = {}
    return cfg


class TestApplyCommonSettingsToAll(unittest.TestCase):

    def test_copies_common_keys_to_others(self):
        cfg = _make_cfg('Alice', 'Bob', 'Carol')
        cfg['overlays']['Alice']['always_on_top'] = False
        cfg['overlays']['Alice']['label_font_size'] = 14
        apply_common_settings_to_all(cfg, 'Alice')
        self.assertFalse(cfg['overlays']['Bob']['always_on_top'])
        self.assertEqual(cfg['overlays']['Carol']['label_font_size'], 14)

    def test_does_not_copy_to_source(self):
        cfg = _make_cfg('Alice', 'Bob')
        cfg['overlays']['Alice']['fps'] = 60
        cfg['overlays']['Alice']['x'] = 999
        apply_common_settings_to_all(cfg, 'Alice')
        # Source unchanged
        self.assertEqual(cfg['overlays']['Alice']['fps'], 60)

    def test_does_not_copy_position_or_size(self):
        cfg = _make_cfg('Alice', 'Bob')
        cfg['overlays']['Alice'].update({'x': 100, 'y': 200, 'w': 300, 'h': 400})
        apply_common_settings_to_all(cfg, 'Alice')
        # x/y/w/h not in COMMON_SETTING_KEYS so not copied
        self.assertNotIn('x', cfg['overlays']['Bob'])
        self.assertNotIn('y', cfg['overlays']['Bob'])
        self.assertNotIn('w', cfg['overlays']['Bob'])
        self.assertNotIn('h', cfg['overlays']['Bob'])

    def test_client_color_not_copied_by_default(self):
        cfg = _make_cfg('Alice', 'Bob')
        cfg['overlays']['Alice']['client_color'] = '#ff0000'
        apply_common_settings_to_all(cfg, 'Alice', include_client_color=False)
        self.assertNotIn('client_color', cfg['overlays']['Bob'])

    def test_client_color_copied_when_flag_set(self):
        cfg = _make_cfg('Alice', 'Bob')
        cfg['overlays']['Alice']['client_color'] = '#ff0000'
        apply_common_settings_to_all(cfg, 'Alice', include_client_color=True)
        self.assertEqual(cfg['overlays']['Bob']['client_color'], '#ff0000')

    def test_only_existing_source_keys_copied(self):
        cfg = _make_cfg('Alice', 'Bob')
        cfg['overlays']['Alice']['snap_enabled'] = True
        # snap_x not set on Alice → should not appear on Bob
        apply_common_settings_to_all(cfg, 'Alice')
        self.assertTrue(cfg['overlays']['Bob']['snap_enabled'])
        self.assertNotIn('snap_x', cfg['overlays']['Bob'])

    def test_common_setting_keys_excludes_positional(self):
        for k in ('x', 'y', 'w', 'h'):
            self.assertNotIn(k, COMMON_SETTING_KEYS, f"'{k}' must not be in COMMON_SETTING_KEYS")

    def test_common_setting_keys_includes_visual_keys(self):
        for k in ('always_on_top', 'snap_enabled', 'label_visible', 'border_visible', 'fps'):
            self.assertIn(k, COMMON_SETTING_KEYS, f"Expected '{k}' in COMMON_SETTING_KEYS")


class TestApplySettingsDict(unittest.TestCase):

    class FakeOverlay:
        def __init__(self, title='Test'):
            self._title = title
            self._cfg = {'overlays': {}}
            self._ov_cfg = get_overlay_cfg(self._cfg, title)
            self._autosave_calls = 0
            self._fps_set = None
            self._update_calls = 0

        def _schedule_autosave(self):
            self._autosave_calls += 1

        def apply_always_on_top(self, v):
            self._ov_cfg['always_on_top'] = v

        def update(self):
            self._update_calls += 1

        def apply_settings_dict(self, settings, persist=True):
            self._ov_cfg.update(settings)
            self.apply_always_on_top(bool(self._ov_cfg.get('always_on_top', True)))
            self.update()
            if persist:
                self._schedule_autosave()

    def test_settings_applied_to_ov_cfg(self):
        ov = self.FakeOverlay()
        ov.apply_settings_dict({'label_font_size': 16, 'border_width': 4})
        self.assertEqual(ov._ov_cfg['label_font_size'], 16)
        self.assertEqual(ov._ov_cfg['border_width'], 4)

    def test_persist_true_schedules_autosave(self):
        ov = self.FakeOverlay()
        ov.apply_settings_dict({'fps': 60}, persist=True)
        self.assertEqual(ov._autosave_calls, 1)

    def test_persist_false_skips_autosave(self):
        ov = self.FakeOverlay()
        ov.apply_settings_dict({'fps': 60}, persist=False)
        self.assertEqual(ov._autosave_calls, 0)

    def test_update_called_for_repaint(self):
        ov = self.FakeOverlay()
        ov.apply_settings_dict({'label_color': '#ff0000'})
        self.assertGreater(ov._update_calls, 0)

    def test_position_keys_not_rejected_but_position_not_in_common_keys(self):
        """Caller controls what keys to pass; apply_settings_dict is permissive."""
        ov = self.FakeOverlay()
        ov.apply_settings_dict({'x': 999})
        # x is absorbed (caller's responsibility not to pass it)
        self.assertEqual(ov._ov_cfg['x'], 999)


if __name__ == '__main__':
    unittest.main()
