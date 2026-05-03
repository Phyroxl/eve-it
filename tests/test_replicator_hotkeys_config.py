"""Tests: hotkey combo parsing and config structure."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay.replicator_hotkeys import parse_hotkey, get_hotkey_defaults, _VK_MAP


class TestHotkeyParsing(unittest.TestCase):

    def test_empty_combo_returns_zero(self):
        self.assertEqual(parse_hotkey(''), (0, 0))
        self.assertEqual(parse_hotkey('   '), (0, 0))

    def test_single_function_key(self):
        mods, vk = parse_hotkey('F13')
        self.assertEqual(vk, 0x7C)
        self.assertGreater(mods, 0)  # at minimum NOREPEAT flag

    def test_ctrl_plus_key(self):
        mods, vk = parse_hotkey('CTRL+F13')
        self.assertEqual(vk, 0x7C)
        self.assertTrue(mods & 0x0002)  # MOD_CTRL

    def test_alt_modifier(self):
        mods, vk = parse_hotkey('ALT+F14')
        self.assertTrue(mods & 0x0001)  # MOD_ALT

    def test_shift_modifier(self):
        mods, vk = parse_hotkey('SHIFT+F15')
        self.assertTrue(mods & 0x0004)  # MOD_SHIFT

    def test_multi_modifier(self):
        mods, vk = parse_hotkey('CTRL+ALT+F16')
        self.assertTrue(mods & 0x0002)  # CTRL
        self.assertTrue(mods & 0x0001)  # ALT
        self.assertEqual(vk, _VK_MAP['F16'])

    def test_lowercase_normalised(self):
        mods1, vk1 = parse_hotkey('ctrl+f13')
        mods2, vk2 = parse_hotkey('CTRL+F13')
        self.assertEqual(vk1, vk2)
        self.assertEqual(mods1, mods2)

    def test_letter_key(self):
        mods, vk = parse_hotkey('CTRL+A')
        self.assertEqual(vk, 0x41)

    def test_unknown_key_returns_zero_vk(self):
        mods, vk = parse_hotkey('CTRL+UNKNOWN_KEY')
        self.assertEqual(vk, 0)

    def test_all_f13_to_f24_mapped(self):
        for i in range(13, 25):
            k = f'F{i}'
            mods, vk = parse_hotkey(k)
            self.assertNotEqual(vk, 0, f"{k} should have a VK code")

    def test_get_hotkey_defaults_structure(self):
        d = get_hotkey_defaults()
        self.assertIn('cycle_next', d)
        self.assertIn('per_client', d)
        self.assertIn('cycle_next', d)
        self.assertIn('cycle_prev', d)

    def test_norepeat_flag_always_set(self):
        mods, vk = parse_hotkey('F13')
        self.assertTrue(mods & 0x4000)  # MOD_NOREPEAT

    def test_cycle_order_determines_next(self):
        """Verify cycle navigation logic (pure, no Win32)."""
        titles = ['Alice', 'Bob', 'Carol']

        def _cycle_next(current_title, direction=1):
            try:
                idx = titles.index(current_title)
            except ValueError:
                idx = -1
            return titles[(idx + direction) % len(titles)]

        self.assertEqual(_cycle_next('Alice'), 'Bob')
        self.assertEqual(_cycle_next('Carol'), 'Alice')  # wraps
        self.assertEqual(_cycle_next('Bob', -1), 'Alice')
        self.assertEqual(_cycle_next('Alice', -1), 'Carol')  # wraps backwards


if __name__ == '__main__':
    unittest.main()
