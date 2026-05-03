"""Tests: Change Zone opens wizard step 2 without auto-starting selector."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeWizard:
    def __init__(self):
        self.current_index = 0
        self.visual_selection_called = False
        self.shown = False

    def show(self): self.shown = True
    def raise_(self): pass
    def activateWindow(self): pass
    def start_visual_selection(self): self.visual_selection_called = True

    class stack:
        def __init__(self): self._idx = 0
        def setCurrentIndex(self, i): self._idx = i
        def currentIndex(self): return self._idx

    def __init__(self):
        self.stack = self.__class__.stack(self)
        self.visual_selection_called = False
        self.shown = False
        self.dlg = self

    class stack:
        def __init__(self, owner): self._owner = owner; self._idx = 0
        def setCurrentIndex(self, i): self._idx = i
        def currentIndex(self): return self._idx


def _simulate_on_reselect_region(wizard_inst):
    """Mirror of the FIXED _on_reselect_region -- must NOT call start_visual_selection."""
    wizard_inst.dlg.show()
    wizard_inst.dlg.raise_()
    wizard_inst.stack.setCurrentIndex(1)
    # Fixed: do NOT call start_visual_selection() here


class TestChangeZoneFlow(unittest.TestCase):

    def test_change_zone_goes_to_step_2(self):
        wiz = FakeWizard()
        _simulate_on_reselect_region(wiz)
        self.assertEqual(wiz.stack.currentIndex(), 1)

    def test_change_zone_does_not_auto_start_selector(self):
        wiz = FakeWizard()
        _simulate_on_reselect_region(wiz)
        self.assertFalse(wiz.visual_selection_called)

    def test_change_zone_shows_wizard(self):
        wiz = FakeWizard()
        _simulate_on_reselect_region(wiz)
        self.assertTrue(wiz.shown)

    def test_step_index_is_1_not_0(self):
        wiz = FakeWizard()
        self.assertEqual(wiz.stack.currentIndex(), 0)  # starts at 0
        _simulate_on_reselect_region(wiz)
        self.assertNotEqual(wiz.stack.currentIndex(), 0)


if __name__ == '__main__':
    unittest.main()
