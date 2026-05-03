"""Tests: should_show_overlays() — hide-when-inactive exclusion logic."""
import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _should_show(fg_hwnd: int, eve_hwnds: set, own_pid: int) -> bool:
    """Pure-Python mirror of should_show_overlays() for unit testing (no Win32)."""
    if not fg_hwnd:
        return True
    if fg_hwnd in eve_hwnds:
        return True
    # Simulate the pid check (injected as own_pid instead of os.getpid())
    return _fake_get_pid(fg_hwnd) == own_pid


# Simulated process-id table for tests
_PID_TABLE: dict = {}


def _fake_get_pid(hwnd: int) -> int:
    return _PID_TABLE.get(hwnd, 0)


class TestShouldShowOverlays(unittest.TestCase):

    def setUp(self):
        _PID_TABLE.clear()

    def test_foreground_is_eve_window_show(self):
        eve_hwnds = {100, 200, 300}
        self.assertTrue(_should_show(200, eve_hwnds, own_pid=42))

    def test_foreground_is_other_app_hide(self):
        eve_hwnds = {100, 200}
        _PID_TABLE[999] = 9999  # some other process
        self.assertFalse(_should_show(999, eve_hwnds, own_pid=42))

    def test_foreground_is_own_process_show(self):
        eve_hwnds = {100}
        own_pid = os.getpid()
        _PID_TABLE[555] = own_pid  # Salva Suite / dialog / overlay
        self.assertTrue(_should_show(555, eve_hwnds, own_pid=own_pid))

    def test_foreground_is_zero_show(self):
        self.assertTrue(_should_show(0, set(), own_pid=42))

    def test_empty_eve_list_own_process_still_shows(self):
        own_pid = os.getpid()
        _PID_TABLE[777] = own_pid
        self.assertTrue(_should_show(777, set(), own_pid=own_pid))

    def test_empty_eve_list_foreign_process_hides(self):
        _PID_TABLE[888] = 9999
        self.assertFalse(_should_show(888, set(), own_pid=42))

    def test_hwnd_in_both_eve_and_own_shows(self):
        # EVE match takes priority (short-circuits before pid check)
        own_pid = os.getpid()
        eve_hwnds = {100}
        _PID_TABLE[100] = own_pid
        self.assertTrue(_should_show(100, eve_hwnds, own_pid=own_pid))

    def test_qt_context_menu_hwnd_own_process_shows(self):
        own_pid = os.getpid()
        context_menu_hwnd = 12345
        _PID_TABLE[context_menu_hwnd] = own_pid
        self.assertTrue(_should_show(context_menu_hwnd, set(), own_pid=own_pid))

    def test_should_show_overlays_importable(self):
        """Smoke test: function exists and runs without crashing on dummy data."""
        from overlay.win32_capture import should_show_overlays
        # With hwnd=0 always returns True
        result = should_show_overlays(0, set())
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
