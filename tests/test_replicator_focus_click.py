"""Tests: left-click focuses EVE client; drag/resize do not."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DRAG_THRESHOLD = 5  # mirror of replication_overlay._DRAG_THRESHOLD


class MockPoint:
    def __init__(self, x, y):
        self.x_val, self.y_val = x, y

    def x(self): return self.x_val
    def y(self): return self.y_val

    def __sub__(self, other):
        class _D:
            def __init__(s, dx, dy): s._dx, s._dy = dx, dy
            def x(s): return s._dx
            def y(s): return s._dy
        return _D(self.x_val - other.x_val, self.y_val - other.y_val)


class FakeOverlay:
    """Minimal stand-in for ReplicationOverlay mouse logic."""

    def __init__(self, hwnd=1234, width=200, height=150):
        self._hwnd = hwnd
        self._width = width
        self._height = height
        self._drag_start_global = None
        self._drag_start_pos = None
        self._drag_moved = False
        self._is_resizing = False
        self.focus_calls = []

    def width(self): return self._width
    def height(self): return self._height
    def pos(self): return MockPoint(100, 100)

    def _fake_focus(self, hwnd):
        self.focus_calls.append(hwnd)
        return True

    def _simulate_press(self, local_x, local_y, global_x, global_y):
        in_corner = local_x > self.width() - 25 and local_y > self.height() - 25
        if in_corner:
            self._is_resizing = True
            self._drag_start_global = None
            self._drag_moved = False
            return
        self._drag_start_global = MockPoint(global_x, global_y)
        self._drag_start_pos = self.pos()
        self._drag_moved = False

    def _simulate_move(self, global_x, global_y):
        if self._drag_start_global is None:
            return
        dx = global_x - self._drag_start_global.x()
        dy = global_y - self._drag_start_global.y()
        if not self._drag_moved:
            if abs(dx) > _DRAG_THRESHOLD or abs(dy) > _DRAG_THRESHOLD:
                self._drag_moved = True

    def _simulate_release(self, left_button=True):
        was_resizing = self._is_resizing
        self._is_resizing = False
        if left_button and not was_resizing and not self._drag_moved:
            self._fake_focus(self._hwnd)
        self._drag_start_global = None
        self._drag_start_pos = None
        self._drag_moved = False


class TestFocusClick(unittest.TestCase):

    def test_simple_click_calls_focus(self):
        ov = FakeOverlay()
        ov._simulate_press(50, 50, 200, 200)
        ov._simulate_release()
        self.assertEqual(ov.focus_calls, [1234])

    def test_drag_beyond_threshold_does_not_focus(self):
        ov = FakeOverlay()
        ov._simulate_press(50, 50, 200, 200)
        ov._simulate_move(210, 200)  # delta.x = 10 > threshold
        ov._simulate_release()
        self.assertEqual(ov.focus_calls, [])

    def test_drag_within_threshold_still_focuses(self):
        ov = FakeOverlay()
        ov._simulate_press(50, 50, 200, 200)
        ov._simulate_move(203, 201)  # delta.x = 3, delta.y = 1 < threshold
        ov._simulate_release()
        self.assertEqual(ov.focus_calls, [1234])

    def test_resize_corner_does_not_focus(self):
        ov = FakeOverlay()
        # Press in resize corner (bottom-right 25px zone)
        ov._simulate_press(180, 135, 300, 300)
        ov._simulate_release()
        self.assertEqual(ov.focus_calls, [])

    def test_right_button_does_not_focus(self):
        ov = FakeOverlay()
        ov._simulate_press(50, 50, 200, 200)
        ov._simulate_release(left_button=False)
        self.assertEqual(ov.focus_calls, [])

    def test_focus_receives_correct_hwnd(self):
        ov = FakeOverlay(hwnd=9999)
        ov._simulate_press(50, 50, 200, 200)
        ov._simulate_release()
        self.assertEqual(ov.focus_calls, [9999])

    def test_drag_moved_flag_reset_after_release(self):
        ov = FakeOverlay()
        ov._simulate_press(50, 50, 200, 200)
        ov._simulate_move(220, 200)
        ov._simulate_release()
        self.assertFalse(ov._drag_moved)

    def test_multiple_clicks_focus_each_time(self):
        ov = FakeOverlay()
        for _ in range(3):
            ov._simulate_press(50, 50, 200, 200)
            ov._simulate_release()
        self.assertEqual(len(ov.focus_calls), 3)


if __name__ == '__main__':
    unittest.main()
