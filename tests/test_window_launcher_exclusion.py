"""
Tests for launcher exclusion and window scoring in core/window_automation.py.
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.window_automation import _score_window

class TestWindowLauncherExclusion(unittest.TestCase):

    def test_launcher_titles_penalized(self):
        """Common launcher titles should have negative score."""
        titles = [
            "Iniciador de EVE",
            "EVE Launcher",
            "Launcher",
            "EVE Online Launcher",
            "iniciador",
            "the launcher"
        ]
        for t in titles:
            score, is_self = _score_window(t)
            self.assertTrue(score <= 0, f"Title '{t}' should be penalized (score={score})")
            self.assertLess(score, 0, f"Title '{t}' should have negative score (score={score})")
            self.assertFalse(is_self)

    def test_character_windows_high_score(self):
        """Actual EVE client windows (character names) should have high positive score."""
        character_titles = [
            "EVE — Nina Herrera",
            "EVE — Azode",
            "EVE - Phyroxl",
            "EVE - CCP Guard"
        ]
        for t in character_titles:
            score, is_self = _score_window(t)
            self.assertGreaterEqual(score, 90, f"Title '{t}' should have high score (score={score})")
            self.assertFalse(is_self)

    def test_generic_eve_windows_low_positive_score(self):
        """Generic EVE windows should have lower but positive score."""
        score, is_self = _score_window("EVE Online")
        self.assertEqual(score, 40)
        self.assertFalse(is_self)
        
        score, is_self = _score_window("EVE")
        self.assertEqual(score, 20)
        self.assertFalse(is_self)

    def test_self_app_markers_excluded(self):
        """EVE iT own windows should be marked as is_self_app and have very low score."""
        titles = [
            "EVE iT",
            "Market Command",
            "Quick Order Update",
            "Antigravity"
        ]
        for t in titles:
            score, is_self = _score_window(t)
            self.assertEqual(score, -100)
            self.assertTrue(is_self)

    def test_best_candidate_resolution(self):
        """Ensure character window wins over launcher."""
        launcher_score, _ = _score_window("Iniciador de EVE")
        client_score, _ = _score_window("EVE — Nina Herrera")
        self.assertGreater(client_score, launcher_score)

if __name__ == "__main__":
    unittest.main()
