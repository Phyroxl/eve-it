"""Tests: position/size persistence via replicator_config."""
import sys
import os
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestLayoutPersistence(unittest.TestCase):

    def _make_cfg(self):
        return {'overlays': {}}

    def test_get_overlay_cfg_returns_defaults_for_new_title(self):
        from overlay.replicator_config import get_overlay_cfg, OVERLAY_DEFAULTS
        cfg = self._make_cfg()
        ov = get_overlay_cfg(cfg, 'EVE — Alice')
        self.assertEqual(ov['x'], OVERLAY_DEFAULTS['x'])
        self.assertEqual(ov['y'], OVERLAY_DEFAULTS['y'])
        self.assertEqual(ov['w'], OVERLAY_DEFAULTS['w'])
        self.assertEqual(ov['h'], OVERLAY_DEFAULTS['h'])

    def test_get_overlay_cfg_restores_saved_values(self):
        from overlay.replicator_config import get_overlay_cfg
        cfg = {'overlays': {'EVE — Bob': {'x': 123, 'y': 456, 'w': 300, 'h': 250}}}
        ov = get_overlay_cfg(cfg, 'EVE — Bob')
        self.assertEqual(ov['x'], 123)
        self.assertEqual(ov['y'], 456)
        self.assertEqual(ov['w'], 300)
        self.assertEqual(ov['h'], 250)

    def test_get_overlay_cfg_fills_missing_keys_with_defaults(self):
        from overlay.replicator_config import get_overlay_cfg, OVERLAY_DEFAULTS
        cfg = {'overlays': {'EVE — Carol': {'x': 10}}}
        ov = get_overlay_cfg(cfg, 'EVE — Carol')
        self.assertEqual(ov['x'], 10)
        self.assertEqual(ov['fps'], OVERLAY_DEFAULTS['fps'])

    def test_save_overlay_cfg_persists_all_keys(self):
        from overlay.replicator_config import save_overlay_cfg, get_overlay_cfg

        with tempfile.TemporaryDirectory() as td:
            import overlay.replicator_config as rc
            original_path = rc.CFG_PATH
            rc.CFG_PATH = Path(td) / 'config' / 'replicator.json'
            try:
                cfg = self._make_cfg()
                data = {'x': 99, 'y': 88, 'w': 200, 'h': 150, 'fps': 60}
                save_overlay_cfg(cfg, 'EVE - Dave', data)
                # Reload from disk
                saved = json.loads(rc.CFG_PATH.read_text(encoding='utf-8'))
                self.assertEqual(saved['overlays']['EVE - Dave']['x'], 99)
                self.assertEqual(saved['overlays']['EVE - Dave']['fps'], 60)
            finally:
                rc.CFG_PATH = original_path

    def test_save_overlay_cfg_merges_not_overwrites(self):
        from overlay.replicator_config import save_overlay_cfg

        with tempfile.TemporaryDirectory() as td:
            import overlay.replicator_config as rc
            original_path = rc.CFG_PATH
            rc.CFG_PATH = Path(td) / 'config' / 'replicator.json'
            try:
                cfg = {'overlays': {'EVE — Eve': {'label_color': '#ff0000', 'x': 5}}}
                save_overlay_cfg(cfg, 'EVE — Eve', {'x': 50, 'y': 60})
                self.assertEqual(cfg['overlays']['EVE — Eve']['label_color'], '#ff0000')
                self.assertEqual(cfg['overlays']['EVE — Eve']['x'], 50)
            finally:
                rc.CFG_PATH = original_path


if __name__ == '__main__':
    unittest.main()
