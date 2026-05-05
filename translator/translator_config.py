"""translator_config.py - Settings"""
import json, os
from dataclasses import dataclass, field, asdict

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'translator_config.json')

@dataclass
class TranslatorProfile:
    name: str = 'default'
    target_lang: str = 'es'
    show_original: bool = True
    show_translation: bool = True
    active_channels: list = field(default_factory=lambda: ['ch_local'])
    font_size: int = 11
    opacity: float = 0.88
    fade_seconds: int = 12
    alert_keywords: list = field(default_factory=lambda: ['tackle','scram','cyno','hostile','primary'])
    alert_color: str = '#ff4444'
    normal_color: str = '#00c8ff'
    system_color: str = 'rgba(200,230,255,0.45)'
    bg_color: str = '#000000'
    original_color: str = 'rgba(200,220,255,0.75)'
    max_messages: int = 30
    always_on_top: bool = True
    compact_mode: bool = False
    hotkey_toggle: str = 'F9'
    translation_mode: str = 'gamer'
    show_portraits: bool = True

@dataclass
class TranslatorConfig:
    profiles: dict = field(default_factory=dict)
    active_profile: str = 'default'
    overlay_x: int = 20
    overlay_y: int = 100
    overlay_w: int = 420
    overlay_h: int = 380
    enabled: bool = True

    def get_profile(self):
        data = self.profiles.get(self.active_profile, {})
        p = TranslatorProfile()
        for k, v in data.items():
            if hasattr(p, k): setattr(p, k, v)
        return p

    def save_profile(self, profile):
        self.profiles[profile.name] = asdict(profile)

    def save(self):
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as e:
            import logging
            logging.getLogger('eve.translator').error(f"Error guardando config del traductor: {e}")

    @classmethod
    def load(cls):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            cfg = cls()
            for k, v in data.items():
                if hasattr(cfg, k): setattr(cfg, k, v)
            return cfg
        except Exception:
            cfg = cls()
            cfg.profiles['default'] = asdict(TranslatorProfile())
            return cfg
