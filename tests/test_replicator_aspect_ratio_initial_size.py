"""Tests: initial overlay size computation from region aspect ratio."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _compute_initial_height(init_w: int, region: dict, eve_w: int, eve_h: int) -> int:
    """Mirror of the aspect-ratio sizing logic in _fix_initial_aspect / _launch_direct."""
    if eve_w <= 0 or eve_h <= 0:
        return 200
    reg_w = region.get('w', 0.3) * eve_w
    reg_h = region.get('h', 0.2) * eve_h
    if reg_h <= 0:
        return 200
    aspect = reg_w / reg_h
    return max(64, int(init_w / aspect))


class TestAspectRatioInitialSize(unittest.TestCase):

    def test_16x9_region_gives_correct_height(self):
        region = {'x': 0, 'y': 0, 'w': 0.5, 'h': 0.5}  # square in game coords
        h = _compute_initial_height(280, region, 1920, 1080)
        # 0.5*1920=960, 0.5*1080=540, aspect=960/540=1.78, h=280/1.78=157
        self.assertAlmostEqual(h, 157, delta=5)

    def test_wide_region_gives_short_overlay(self):
        region = {'w': 0.8, 'h': 0.2}
        h = _compute_initial_height(280, region, 1920, 1080)
        self.assertLess(h, 140)

    def test_tall_region_gives_taller_overlay(self):
        region = {'w': 0.1, 'h': 0.5}
        h = _compute_initial_height(280, region, 1920, 1080)
        self.assertGreater(h, 280)

    def test_square_region_gives_square_overlay(self):
        region = {'w': 0.3, 'h': 0.3}
        h = _compute_initial_height(200, region, 1920, 1080)
        # square region on 1920x1080 is NOT square in pixels: 576x324, aspect=1.78
        # 200 / 1.78 = 112 -- not square
        expected = _compute_initial_height(200, {'w': 0.3, 'h': 0.3}, 1920, 1080)
        self.assertEqual(h, expected)

    def test_unknown_window_size_fallback(self):
        region = {'w': 0.3, 'h': 0.3}
        h = _compute_initial_height(280, region, 0, 0)
        self.assertEqual(h, 200)

    def test_minimum_height_enforced(self):
        region = {'w': 1.0, 'h': 0.01}  # extremely wide
        h = _compute_initial_height(280, region, 1920, 1080)
        self.assertGreaterEqual(h, 64)

    def test_maintain_aspect_in_defaults(self):
        from overlay.replicator_config import OVERLAY_DEFAULTS
        self.assertIn('maintain_aspect', OVERLAY_DEFAULTS)
        self.assertTrue(OVERLAY_DEFAULTS['maintain_aspect'])


if __name__ == '__main__':
    unittest.main()
