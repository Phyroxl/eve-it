"""Tests: sync_resize_triggered signal and apply_size guard logic."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class MockOverlay:
    """Minimal stand-in for ReplicationOverlay (no Qt / Win32 required)."""

    def __init__(self):
        self._sync_active = False
        self._applying_sync_resize = False
        self._w = 200
        self._h = 150
        self.resize_calls = []
        self.emit_calls = []

    def width(self): return self._w
    def height(self): return self._h

    def resize(self, w, h):
        self._w, self._h = w, h
        self.resize_calls.append((w, h))

    def apply_size(self, w, h):
        if self._applying_sync_resize:
            return
        self._applying_sync_resize = True
        try:
            self.resize(max(50, w), max(50, h))
        finally:
            self._applying_sync_resize = False

    def _emit_sync_resize(self):
        if self._sync_active and not self._applying_sync_resize:
            self.emit_calls.append((self._w, self._h))


class TestSyncResizeBroadcast(unittest.TestCase):

    def test_apply_size_calls_resize(self):
        ov = MockOverlay()
        ov.apply_size(300, 250)
        self.assertEqual(ov.resize_calls, [(300, 250)])

    def test_apply_size_enforces_minimum(self):
        ov = MockOverlay()
        ov.apply_size(10, 10)
        self.assertEqual(ov.resize_calls, [(50, 50)])

    def test_apply_size_guard_prevents_recursion(self):
        ov = MockOverlay()
        ov._applying_sync_resize = True
        ov.apply_size(400, 300)
        self.assertEqual(ov.resize_calls, [])

    def test_guard_flag_cleared_after_apply_size(self):
        ov = MockOverlay()
        ov.apply_size(300, 200)
        self.assertFalse(ov._applying_sync_resize)

    def test_emit_only_when_sync_active(self):
        ov = MockOverlay()
        ov._sync_active = False
        ov._emit_sync_resize()
        self.assertEqual(ov.emit_calls, [])

    def test_emit_when_sync_active(self):
        ov = MockOverlay()
        ov._sync_active = True
        ov._emit_sync_resize()
        self.assertEqual(ov.emit_calls, [(200, 150)])

    def test_no_emit_when_applying_sync_resize(self):
        ov = MockOverlay()
        ov._sync_active = True
        ov._applying_sync_resize = True
        ov._emit_sync_resize()
        self.assertEqual(ov.emit_calls, [])

    def test_broadcast_to_peers_excludes_source(self):
        """Simulates _on_sync_resize_direct logic."""
        source = MockOverlay()
        peer1 = MockOverlay()
        peer2 = MockOverlay()
        refs = [source, peer1, peer2]

        def broadcast(src, w, h):
            for ov in refs:
                if ov is not src:
                    ov.apply_size(w, h)

        broadcast(source, 320, 240)
        self.assertEqual(source.resize_calls, [])
        self.assertEqual(peer1.resize_calls, [(320, 240)])
        self.assertEqual(peer2.resize_calls, [(320, 240)])


if __name__ == '__main__':
    unittest.main()
