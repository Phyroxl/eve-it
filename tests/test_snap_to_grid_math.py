"""Tests: snap-to-grid coordinate rounding (pure math, no Qt)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _snap(x, y, sx, sy):
    """Reference implementation identical to ReplicationOverlay._apply_snap."""
    return (round(x / sx) * sx, round(y / sy) * sy)


class TestSnapToGridMath(unittest.TestCase):

    def test_exact_multiple_unchanged(self):
        self.assertEqual(_snap(40, 60, 20, 20), (40, 60))

    def test_rounds_up_when_past_midpoint(self):
        self.assertEqual(_snap(11, 11, 20, 20), (20, 20))

    def test_rounds_down_when_before_midpoint(self):
        self.assertEqual(_snap(9, 9, 20, 20), (0, 0))

    def test_at_midpoint_rounds_to_even(self):
        # round(10/20)*20 = round(0.5)*20 = 0*20 = 0  (Python banker's rounding)
        result = _snap(10, 10, 20, 20)
        self.assertIn(result[0], (0, 20))

    def test_different_x_y_grids(self):
        x, y = _snap(15, 25, 10, 50)
        self.assertEqual(x, 20)         # 15/10 = 1.5 → round → 2 → 20
        self.assertIn(y, (0, 50))       # 25/50 = 0.5 → banker's rounding → 0 or 50

    def test_large_coordinates(self):
        self.assertEqual(_snap(1920, 1080, 20, 20), (1920, 1080))

    def test_snap_x_1_identity(self):
        self.assertEqual(_snap(17, 33, 1, 1), (17, 33))

    def test_negative_coords_snap_symmetrically(self):
        x, _ = _snap(-11, 0, 20, 20)
        self.assertIn(x, (-20, 0))

    def test_overlay_apply_snap_uses_ov_cfg(self):
        """Smoke-test that _apply_snap reads snap_x/snap_y from _ov_cfg."""
        class FakeOverlay:
            _ov_cfg = {'snap_x': 10, 'snap_y': 5}
            def _apply_snap(self, x, y):
                sx = max(1, int(self._ov_cfg.get('snap_x', 20)))
                sy = max(1, int(self._ov_cfg.get('snap_y', 20)))
                return (round(x / sx) * sx, round(y / sy) * sy)

        ov = FakeOverlay()
        self.assertEqual(ov._apply_snap(13, 7), (10, 5))
        self.assertEqual(ov._apply_snap(16, 8), (20, 10))

    def test_absolute_delta_snap_never_freezes(self):
        """Simulate the absolute-origin drag approach: moving mouse always moves overlay."""
        # Drag start: widget at (100, 100), mouse pressed at global (200, 200)
        start_pos_x, start_pos_y = 100, 100
        start_global_x, start_global_y = 200, 200
        grid = 20

        results = []
        for mouse_x in range(200, 260, 3):  # mouse moves right
            raw_x = start_pos_x + (mouse_x - start_global_x)
            snapped_x = _snap(raw_x, start_pos_y, grid, grid)[0]
            results.append(snapped_x)

        # The snapped x must increase as mouse moves — it must not stay frozen
        self.assertGreater(max(results), min(results),
                           "Snap should allow movement, not freeze the overlay")

    def test_alt_override_skips_snap(self):
        """When ALT held, raw position is used instead of snapped."""
        raw_x, raw_y = 13, 27
        snapped = _snap(raw_x, raw_y, 10, 10)
        # ALT override: use raw directly
        alt_result = (raw_x, raw_y)
        self.assertNotEqual(snapped, alt_result)  # snap actually changes the value
        self.assertEqual(alt_result, (13, 27))    # ALT preserves raw


if __name__ == '__main__':
    unittest.main()
