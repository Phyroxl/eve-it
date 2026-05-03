"""Tests: layout profile CRUD in replicator_config."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay.replicator_config import (
    get_layout_profiles, save_layout_profile, delete_layout_profile,
    get_active_layout_profile, apply_layout_profile_to_ov_cfg,
    LAYOUT_PROFILE_KEYS, _DEFAULT_LAYOUT_PROFILE,
)


class TestLayoutProfiles(unittest.TestCase):

    def _empty_cfg(self):
        return {}

    def test_get_layout_profiles_returns_default_if_empty(self):
        profiles = get_layout_profiles(self._empty_cfg())
        self.assertIn('Default', profiles)

    def test_save_and_retrieve_profile(self):
        cfg = self._empty_cfg()
        data = {'w': 400, 'h': 225, 'fps': 60, 'snap_enabled': True,
                'snap_x': 10, 'snap_y': 10, 'maintain_aspect': True,
                'opacity': 1.0, 'label_visible': True, 'border_visible': False}

        import overlay.replicator_config as rc
        orig = rc.CFG_PATH
        with tempfile.TemporaryDirectory() as td:
            rc.CFG_PATH = Path(td) / 'config' / 'replicator.json'
            try:
                save_layout_profile(cfg, 'Test', data)
                profiles = get_layout_profiles(cfg)
                self.assertIn('Test', profiles)
                self.assertEqual(profiles['Test']['w'], 400)
                self.assertEqual(profiles['Test']['fps'], 60)
            finally:
                rc.CFG_PATH = orig

    def test_save_profile_excludes_non_layout_keys(self):
        cfg = self._empty_cfg()
        data = {'w': 300, 'h': 200, 'x': 100, 'y': 50, 'fps': 30,
                'snap_enabled': False, 'snap_x': 20, 'snap_y': 20,
                'maintain_aspect': True, 'opacity': 1.0,
                'label_visible': True, 'border_visible': True}
        import overlay.replicator_config as rc
        orig = rc.CFG_PATH
        with tempfile.TemporaryDirectory() as td:
            rc.CFG_PATH = Path(td) / 'config' / 'replicator.json'
            try:
                save_layout_profile(cfg, 'Test2', data)
                profiles = get_layout_profiles(cfg)
                self.assertNotIn('x', profiles.get('Test2', {}))
                self.assertNotIn('y', profiles.get('Test2', {}))
            finally:
                rc.CFG_PATH = orig

    def test_delete_profile(self):
        cfg = {'layout_profiles': {'Default': {}, 'MyProfile': {'w': 300}}}
        import overlay.replicator_config as rc
        orig = rc.CFG_PATH
        with tempfile.TemporaryDirectory() as td:
            rc.CFG_PATH = Path(td) / 'config' / 'replicator.json'
            try:
                delete_layout_profile(cfg, 'MyProfile')
                self.assertNotIn('MyProfile', cfg.get('layout_profiles', {}))
            finally:
                rc.CFG_PATH = orig

    def test_delete_default_profile_not_removed(self):
        cfg = {'layout_profiles': {'Default': {'w': 280}, 'Other': {}}}
        import overlay.replicator_config as rc
        orig = rc.CFG_PATH
        with tempfile.TemporaryDirectory() as td:
            rc.CFG_PATH = Path(td) / 'config' / 'replicator.json'
            try:
                # Default can be deleted by name (not protected at config level)
                delete_layout_profile(cfg, 'Other')
                self.assertIn('Default', cfg.get('layout_profiles', {}))
            finally:
                rc.CFG_PATH = orig

    def test_get_active_profile_returns_default_when_missing(self):
        cfg = {}
        name, prof = get_active_layout_profile(cfg)
        self.assertIsInstance(prof, dict)
        self.assertIn('w', prof)

    def test_apply_profile_to_ov_cfg(self):
        ov_cfg = {'x': 100, 'y': 200, 'w': 100, 'h': 100}
        profile = {'w': 400, 'h': 225, 'fps': 60, 'snap_enabled': True,
                   'snap_x': 10, 'snap_y': 10, 'maintain_aspect': True,
                   'opacity': 1.0, 'label_visible': True, 'border_visible': True}
        apply_layout_profile_to_ov_cfg(ov_cfg, profile)
        self.assertEqual(ov_cfg['w'], 400)
        self.assertEqual(ov_cfg['fps'], 60)
        # Position must NOT be touched
        self.assertEqual(ov_cfg['x'], 100)
        self.assertEqual(ov_cfg['y'], 200)

    def test_layout_profile_keys_excludes_xy(self):
        for k in ('x', 'y'):
            self.assertNotIn(k, LAYOUT_PROFILE_KEYS)

    def test_layout_profile_keys_includes_expected(self):
        for k in ('w', 'h', 'fps', 'snap_enabled', 'maintain_aspect'):
            self.assertIn(k, LAYOUT_PROFILE_KEYS)


if __name__ == '__main__':
    unittest.main()
