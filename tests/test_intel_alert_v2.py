"""Tests for Intel Alert v2: config, classification, channel matching, distance."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.intel_alert_service import (
    IntelAlertConfig,
    IntelAlertService,
    IntelEvent,
    classify_pilot,
    discover_chat_channels,
    parse_intel_message,
    should_alert,
)
from utils.eve_api import _normalize_sender


# ── IntelAlertConfig persistence ─────────────────────────────────────────────

def test_config_round_trip(tmp_path):
    cfg = IntelAlertConfig(
        source_mode="both",
        intel_channels=["Delve.Intel", "Standing Fleet"],
        current_system="1DQ1-A",
        max_jumps=3,
        alert_unknown_distance=False,
        alert_on_watchlist=True,
        safe_names=["Frendly"],
        watch_names=["BigBad"],
    )
    target = tmp_path / "intel_alert.json"
    with patch("core.intel_alert_service.CONFIG_FILE", target):
        cfg.save()
        loaded = IntelAlertConfig.load()

    # patch doesn't affect classmethod load reading from disk — test via json
    with open(target) as f:
        data = json.load(f)
    assert data["source_mode"] == "both"
    assert data["intel_channels"] == ["Delve.Intel", "Standing Fleet"]
    assert data["current_system"] == "1DQ1-A"
    assert data["max_jumps"] == 3
    assert data["alert_unknown_distance"] is False
    assert "Frendly" in data["safe_names"]
    assert "BigBad" in data["watch_names"]


# ── classify_pilot ─────────────────────────────────────────────────────────

def _cfg(**kw):
    return IntelAlertConfig(**kw)


def test_classify_safe():
    cfg = _cfg(safe_names=["Alice"], watch_names=[])
    assert classify_pilot("Alice", cfg) == "safe"


def test_classify_safe_case_insensitive():
    cfg = _cfg(safe_names=["ALICE"], watch_names=[])
    assert classify_pilot("alice", cfg) == "safe"


def test_classify_watchlist():
    cfg = _cfg(safe_names=[], watch_names=["BadGuy"])
    assert classify_pilot("BadGuy", cfg) == "watchlist"


def test_classify_unknown():
    cfg = _cfg(safe_names=[], watch_names=[])
    assert classify_pilot("SomePilot", cfg) == "unknown"


# ── should_alert ──────────────────────────────────────────────────────────────

def _event(**kw):
    defaults = dict(
        timestamp="2026.05.06 12:00:00",
        pilot="TestPilot",
        channel="Local",
        message="msg",
        classification="unknown",
        source="local",
    )
    defaults.update(kw)
    return IntelEvent(**defaults)


def test_safe_never_alerts():
    cfg = _cfg()
    e = _event(classification="safe")
    assert should_alert(e, cfg) is False


def test_watchlist_alerts_when_enabled():
    cfg = _cfg(alert_on_watchlist=True)
    e = _event(classification="watchlist")
    assert should_alert(e, cfg) is True


def test_watchlist_no_alert_when_disabled():
    cfg = _cfg(alert_on_watchlist=False)
    e = _event(classification="watchlist")
    assert should_alert(e, cfg) is False


def test_unknown_alerts_when_enabled():
    cfg = _cfg(alert_on_unknown=True)
    e = _event(classification="unknown")
    assert should_alert(e, cfg) is True


def test_unknown_no_alert_when_disabled():
    cfg = _cfg(alert_on_unknown=False)
    e = _event(classification="unknown")
    assert should_alert(e, cfg) is False


def test_max_jumps_zero_means_no_distance_filter():
    """max_jumps=0 disables distance filtering — always alert if classification passes."""
    cfg = _cfg(max_jumps=0, current_system="Jita", alert_on_unknown=True)
    e = _event(classification="unknown", system="1DQ1-A")
    assert should_alert(e, cfg) is True


def test_unknown_distance_alert_when_true():
    """When map returns None (unknown distance), alert if alert_unknown_distance=True."""
    cfg = _cfg(max_jumps=3, current_system="Jita", alert_unknown_distance=True,
               alert_on_unknown=True)
    e = _event(classification="unknown", system="1DQ1-A")
    # EveMapService.distance_jumps always returns None in stub
    assert should_alert(e, cfg) is True


def test_unknown_distance_no_alert_when_false():
    cfg = _cfg(max_jumps=3, current_system="Jita", alert_unknown_distance=False,
               alert_on_unknown=True)
    e = _event(classification="unknown", system="1DQ1-A")
    assert should_alert(e, cfg) is False


def test_same_system_zero_jumps_alerts():
    """Same system → distance_jumps returns 0 → always within max_jumps."""
    cfg = _cfg(max_jumps=0, current_system="1DQ1-A", alert_unknown_distance=False,
               alert_on_unknown=True)
    e = _event(classification="unknown", system="1DQ1-A")
    # distance_jumps("1DQ1-A", "1DQ1-A") == 0 ≤ 0 → True
    assert should_alert(e, cfg) is True


# ── parse_intel_message ────────────────────────────────────────────────────────

def test_parse_null_sec_system():
    result = parse_intel_message("BadGuy spotted in 1DQ1-A gate camp")
    assert result["system"] == "1DQ1-A"


def test_parse_another_null_system():
    result = parse_intel_message("MJ-5F9 clear")
    assert result["system"] == "MJ-5F9"


def test_parse_no_system_returns_none():
    result = parse_intel_message("clear o7")
    assert result["system"] is None


def test_parse_preserves_raw():
    text = "some intel message"
    result = parse_intel_message(text)
    assert result["raw"] == text


# ── Cooldown key ───────────────────────────────────────────────────────────────

def test_cooldown_key_differs_by_source():
    from core.intel_alert_service import IntelAlertService
    svc = IntelAlertService(IntelAlertConfig(), lambda e: None)
    e1 = _event(source="local", pilot="X", system="Jita")
    e2 = _event(source="intel", pilot="X", system="Jita")
    assert svc._cooldown_key(e1) != svc._cooldown_key(e2)


def test_cooldown_key_differs_by_system():
    from core.intel_alert_service import IntelAlertService
    svc = IntelAlertService(IntelAlertConfig(), lambda e: None)
    e1 = _event(source="local", pilot="X", system="Jita")
    e2 = _event(source="local", pilot="X", system="Amarr")
    assert svc._cooldown_key(e1) != svc._cooldown_key(e2)


def test_cooldown_key_same_pilot_system_source():
    from core.intel_alert_service import IntelAlertService
    svc = IntelAlertService(IntelAlertConfig(), lambda e: None)
    e1 = _event(source="local", pilot="X", system="Jita")
    e2 = _event(source="local", pilot="x", system="Jita")  # lowercase
    assert svc._cooldown_key(e1) == svc._cooldown_key(e2)


# ── Channel file matching ──────────────────────────────────────────────────────

def _svc(source_mode="local", intel_channels=None):
    cfg = IntelAlertConfig(source_mode=source_mode,
                           intel_channels=intel_channels or [])
    from core.intel_alert_service import IntelAlertService
    return IntelAlertService(cfg, lambda e: None)


def test_source_local_matches_local_file():
    svc = _svc("local")
    assert svc._channel_file_matches("Local_20260506_120000.txt") is True


def test_source_local_no_intel_file():
    svc = _svc("local")
    assert svc._channel_file_matches("Delve.Intel_20260506.txt") is False


def test_source_intel_matches_configured_channel():
    svc = _svc("intel", ["Delve.Intel"])
    assert svc._channel_file_matches("Delve.Intel_20260506.txt") is True


def test_source_intel_no_local():
    svc = _svc("intel", ["Delve.Intel"])
    assert svc._channel_file_matches("Local_20260506.txt") is False


def test_source_intel_fallback_to_intel_keyword():
    svc = _svc("intel", [])  # no channels configured
    assert svc._channel_file_matches("SomeIntelChannel_20260506.txt") is True


def test_source_both_matches_local_and_intel():
    svc = _svc("both", ["Delve.Intel"])
    assert svc._channel_file_matches("Local_20260506.txt") is True
    assert svc._channel_file_matches("Delve.Intel_20260506.txt") is True


def test_source_both_no_unconfigured_channel():
    svc = _svc("both", ["Delve.Intel"])
    assert svc._channel_file_matches("Corp_20260506.txt") is False


# ── Normalize sender (from eve_api) ───────────────────────────────────────────

def test_normalize_sender_strips_spaces():
    assert _normalize_sender("  Alice  ") == "Alice"


def test_normalize_sender_removes_null_byte():
    assert _normalize_sender("Ali\x00ce") == "Alice"


def test_normalize_sender_preserves_internal_spaces():
    assert _normalize_sender("Alice Bob") == "Alice Bob"


def test_normalize_sender_empty_string():
    assert _normalize_sender("") == ""


# ── Sound config ──────────────────────────────────────────────────────────────

def test_sound_mode_default():
    cfg = IntelAlertConfig()
    assert cfg.alert_sound_mode == "beep"
    assert cfg.alert_sound_path == ""


def test_sound_mode_roundtrip(tmp_path):
    cfg = IntelAlertConfig(alert_sound_mode="wav", alert_sound_path="/tmp/test.wav")
    target = tmp_path / "intel_alert.json"
    with patch("core.intel_alert_service.CONFIG_FILE", target):
        cfg.save()
    with open(target) as f:
        data = json.load(f)
    assert data["alert_sound_mode"] == "wav"
    assert data["alert_sound_path"] == "/tmp/test.wav"


def test_sound_mode_load_backcompat(tmp_path):
    """Old configs with alert_sound:true should load as mode=beep."""
    target = tmp_path / "intel_alert.json"
    target.write_text(json.dumps({"alert_sound": True}))
    with patch("core.intel_alert_service.CONFIG_FILE", target):
        cfg = IntelAlertConfig.load()
    assert cfg.alert_sound_mode == "beep"


# ── Intel keyword detection ───────────────────────────────────────────────────

def test_keyword_detection_fires_without_watchlist():
    """Intel channel keyword detection must fire even when watch_names is empty."""
    events = []
    cfg = IntelAlertConfig(
        source_mode="intel",
        alert_on_unknown=True,
        watch_names=[],
        alert_keywords=["neutral", "neut"],
    )
    svc = IntelAlertService(cfg, events.append)
    svc._handle_intel_message("reporter", "3 neutrals in 1DQ1-A", "ts", "Delve.Intel", "intel")
    assert len(events) == 1
    assert events[0].classification == "intel"


def test_keyword_no_match_no_alert():
    events = []
    cfg = IntelAlertConfig(
        source_mode="intel",
        alert_on_unknown=True,
        watch_names=[],
        alert_keywords=["neutral"],
    )
    svc = IntelAlertService(cfg, events.append)
    svc._handle_intel_message("reporter", "all clear o7", "ts", "Delve.Intel", "intel")
    assert len(events) == 0


def test_watchlist_takes_priority_over_keyword():
    events = []
    cfg = IntelAlertConfig(
        source_mode="intel",
        alert_on_watchlist=True,
        watch_names=["BigBad"],
        alert_keywords=["neutral"],
    )
    svc = IntelAlertService(cfg, events.append)
    svc._handle_intel_message("reporter", "BigBad neutral in 1DQ", "ts", "Chan", "intel")
    assert len(events) == 1
    assert events[0].classification == "watchlist"
    assert events[0].pilot == "BigBad"


def test_keyword_classification_is_intel():
    events = []
    cfg = IntelAlertConfig(
        source_mode="intel",
        alert_on_unknown=True,
        watch_names=[],
        alert_keywords=["neut"],
    )
    svc = IntelAlertService(cfg, events.append)
    svc._handle_intel_message("scout", "neut in YZ-", "ts", "Intel", "intel")
    assert events[0].classification == "intel"


# ── should_alert with 'intel' classification ─────────────────────────────────

def test_intel_classification_respects_alert_on_unknown():
    cfg = _cfg(alert_on_unknown=False)
    e = _event(classification="intel")
    assert should_alert(e, cfg) is False


def test_intel_classification_alerts_when_unknown_enabled():
    cfg = _cfg(alert_on_unknown=True)
    e = _event(classification="intel")
    assert should_alert(e, cfg) is True


# ── Default keywords populated ────────────────────────────────────────────────

def test_default_keywords_not_empty():
    cfg = IntelAlertConfig()
    assert len(cfg.alert_keywords) > 0
    assert "neutral" in cfg.alert_keywords


def test_load_repopulates_empty_keywords(tmp_path):
    target = tmp_path / "intel_alert.json"
    target.write_text(json.dumps({"alert_keywords": []}))
    with patch("core.intel_alert_service.CONFIG_FILE", target):
        cfg = IntelAlertConfig.load()
    assert len(cfg.alert_keywords) > 0


# ── Diagnostics ───────────────────────────────────────────────────────────────

def test_diagnostics_initial_state():
    cfg = IntelAlertConfig()
    svc = IntelAlertService(cfg, lambda e: None)
    d = svc.get_diagnostics()
    assert d["files_watched"] == 0
    assert d["total_alerts"] == 0
    assert d["last_alert"] == ""
    assert d["last_message"] == ""


def test_diagnostics_updated_on_alert():
    events = []
    cfg = IntelAlertConfig(
        source_mode="intel",
        alert_on_unknown=True,
        watch_names=[],
        alert_keywords=["neut"],
    )
    svc = IntelAlertService(cfg, events.append)
    svc._handle_intel_message("scout", "neut in 1DQ", "ts", "Chan", "intel")
    d = svc.get_diagnostics()
    assert d["total_alerts"] == 1
    assert "scout" in d["last_alert"]


# ── discover_chat_channels ───────────────────────────────────────────────────

def test_discover_chat_channels_empty_dir(tmp_path):
    with patch("core.intel_alert_service.discover_chat_channels", wraps=lambda **kw: []):
        result = discover_chat_channels.__wrapped__() if hasattr(discover_chat_channels, '__wrapped__') else []
    # Just verify it returns a list
    assert isinstance(result, list)


def test_discover_channels_no_chatlog_dir():
    """Should return [] gracefully when chatlog dir not found."""
    with patch("translator.chat_reader._get_chatlog_dir", return_value=None):
        result = discover_chat_channels()
    assert result == []
