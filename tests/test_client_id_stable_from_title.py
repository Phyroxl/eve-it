"""Tests: _extract_label() — character name extraction from EVE window titles."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _extract_label(title: str) -> str:
    """Mirror of ReplicationOverlay._extract_label — pure function, no Qt."""
    for sep in (' — ', ' - ', ' – '):
        if sep in title:
            return title.split(sep, 1)[-1].strip()
    return title


class TestExtractLabel(unittest.TestCase):

    def test_em_dash_separator(self):
        self.assertEqual(_extract_label('EVE — Nina Herrera'), 'Nina Herrera')

    def test_ascii_dash_separator(self):
        self.assertEqual(_extract_label('EVE - Bob Smith'), 'Bob Smith')

    def test_en_dash_separator(self):
        self.assertEqual(_extract_label('EVE – Alice Jones'), 'Alice Jones')

    def test_no_separator_returns_full_title(self):
        self.assertEqual(_extract_label('SomeWindow'), 'SomeWindow')

    def test_multiple_dashes_takes_last_part(self):
        # Only split on first occurrence
        self.assertEqual(_extract_label('EVE — Alpha — Beta'), 'Alpha — Beta')

    def test_whitespace_stripped(self):
        self.assertEqual(_extract_label('EVE —   Padded Name  '), 'Padded Name')

    def test_empty_string_returns_empty(self):
        self.assertEqual(_extract_label(''), '')

    def test_only_separator_returns_empty_string(self):
        result = _extract_label('EVE — ')
        self.assertEqual(result, '')

    def test_unicode_character_name(self):
        self.assertEqual(_extract_label('EVE — Ñoño Española'), 'Ñoño Española')

    def test_pid_suffix_in_title_preserved(self):
        # If no separator, full title including PID hint is returned
        full = 'Nina Herrera [#1234]'
        self.assertEqual(_extract_label(full), full)

    def test_priority_em_dash_over_ascii(self):
        # em-dash comes first in the loop → wins
        title = 'EVE — Char — Sub - Other'
        self.assertEqual(_extract_label(title), 'Char — Sub - Other')


if __name__ == '__main__':
    unittest.main()
