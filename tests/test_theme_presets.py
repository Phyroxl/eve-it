"""
tests/test_theme_presets.py
Validation for the 20 preset themes and their application.
"""
import pytest
import os
import sys

# Ensure root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.theme.theme_manager import ThemeManager
from ui.theme.theme_presets import THEME_PRESETS
from ui.theme.theme_tokens import DEFAULT_TOKENS

@pytest.fixture
def tm(tmp_path):
    m = ThemeManager.instance()
    m.config_path = str(tmp_path / "test_presets.json")
    m.reset_all()
    return m

def test_preset_count():
    assert len(THEME_PRESETS) == 20

def test_preset_structure():
    required_keys = ["name", "description", "swatches", "tokens"]
    for pid, data in THEME_PRESETS.items():
        for key in required_keys:
            assert key in data, f"Preset {pid} is missing {key}"
        assert isinstance(data["swatches"], list)
        assert len(data["swatches"]) >= 3
        assert isinstance(data["tokens"], dict)

def test_apply_each_preset(tm):
    for pid in THEME_PRESETS:
        assert tm.apply_preset(pid) == True
        assert tm.theme_data["active_preset"] == pid
        qss = tm.get_qss()
        assert len(qss) > 100
        # Check if at least one core token from preset is in QSS (if defined)
        p_tokens = THEME_PRESETS[pid]["tokens"]
        if "ACCENT" in p_tokens:
            assert p_tokens["ACCENT"].lower() in qss.lower()

def test_preset_persistence(tm):
    tm.apply_preset("amarr_gold")
    tm.save_theme()
    
    # New instance or reload
    tm.load_theme()
    assert tm.theme_data["active_preset"] == "amarr_gold"
    assert tm.get_token("ACCENT") == THEME_PRESETS["amarr_gold"]["tokens"]["ACCENT"]

def test_corrupt_config_fallback(tm):
    # Create corrupt config
    os.makedirs(os.path.dirname(tm.config_path), exist_ok=True)
    with open(tm.config_path, 'w') as f:
        f.write("NOT JSON")
        
    tm.load_theme()
    assert tm.theme_data["active_preset"] == "replicator_core"
    assert tm.get_token("ACCENT") == DEFAULT_TOKENS["ACCENT"]
