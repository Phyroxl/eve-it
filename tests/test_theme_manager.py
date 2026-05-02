"""
tests/test_theme_manager.py
Tests for ThemeManager and dynamic Theme proxy.
"""
import pytest
import os
import json
import sys

# Ensure root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.theme.theme_manager import ThemeManager
from ui.common.theme import Theme

@pytest.fixture
def tm(tmp_path):
    # Setup a fresh ThemeManager pointing to a temp config
    m = ThemeManager.instance()
    m.config_path = str(tmp_path / "test_theme.json")
    m.reset_all()
    return m

def test_default_tokens(tm):
    assert tm.get_token("ACCENT") == "#00c8ff"
    assert Theme.ACCENT == "#00c8ff"

def test_token_override_global(tm):
    tm.set_token("ACCENT", "#ff00ff")
    assert tm.get_token("ACCENT") == "#ff00ff"
    assert Theme.ACCENT == "#ff00ff"

def test_view_override(tm):
    tm.set_token("ACCENT", "#00ff00", view_scope="simple")
    # Global stays same
    assert tm.get_token("ACCENT") == "#00c8ff"
    # View is overridden
    assert tm.get_token("ACCENT", view_scope="simple") == "#00ff00"

def test_save_load(tm):
    tm.set_token("ACCENT", "#123456")
    tm.save_theme()
    
    # Reload
    tm.load_theme()
    assert tm.get_token("ACCENT") == "#123456"

def test_reset_view(tm):
    tm.set_token("ACCENT", "#00ff00", view_scope="simple")
    tm.reset_view("simple")
    assert tm.get_token("ACCENT", view_scope="simple") == "#00c8ff"

def test_qss_generation(tm):
    qss = tm.get_qss()
    assert "#00c8ff" in qss
    assert "MarketCommandRoot" in qss
