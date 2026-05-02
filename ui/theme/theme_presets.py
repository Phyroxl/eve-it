"""
ui/theme/theme_presets.py — 20 Preset Themes for EVE iT Market Command.
Each preset defines a complete visual identity consistent with EVE Online archetypes.
"""

THEME_PRESETS = {
    "replicator_core": {
        "name": "Replicator Core",
        "description": "Tema base del Replicador. Oscuro, cian, azul petróleo, verde neón suave.",
        "swatches": ["#05070A", "#0B1016", "#00D9FF", "#00FFB3", "#FF4D5E"],
        "tokens": {
            "BG_WINDOW": "#05070a", "NAV_BG": "#0b1016", "NAV_BORDER": "#1e293b",
            "TAB_ACTIVE_BG": "#10161d", "TAB_ACTIVE_TEXT": "#00c8ff", "TAB_INACTIVE_TEXT": "#64748b",
            "ACCENT": "#00c8ff", "ACCENT_SECONDARY": "#00ffb3", "SUCCESS": "#10b981", "DANGER": "#ef4444"
        }
    },
    "translator_neon": {
        "name": "Translator Neon",
        "description": "Inspirado en EVE Chat Translator. Negro profundo, cian brillante, verde turquesa.",
        "swatches": ["#020406", "#00F2FF", "#00FF9D", "#0A0F14", "#FF007A"],
        "tokens": {
            "BG_WINDOW": "#020406", "NAV_BG": "#0a0f14", "NAV_BORDER": "#16212e",
            "TAB_ACTIVE_BG": "#00f2ff", "TAB_ACTIVE_TEXT": "#000000", "TAB_INACTIVE_TEXT": "#4fd1d9",
            "ACCENT": "#00f2ff", "ACCENT_SECONDARY": "#00ff9d", "SUCCESS": "#00ff9d", "DANGER": "#ff007a",
            "TABLE_BG": "#040609", "CARD_BG": "#080c12", "SIDEBAR_BG": "#030507"
        }
    },
    "caldari_navy": {
        "name": "Caldari Navy",
        "description": "Azul acero, gris militar, cian frío. Sensación corporativa y militar.",
        "swatches": ["#0b121c", "#1e293b", "#00d9ff", "#94a3b8", "#cbd5e1"],
        "tokens": {
            "BG_WINDOW": "#0b121c", "NAV_BG": "#16212e", "NAV_BORDER": "#334155",
            "TAB_ACTIVE_BG": "#334155", "TAB_ACTIVE_TEXT": "#00d9ff", "TAB_INACTIVE_TEXT": "#94a3b8",
            "ACCENT": "#00d9ff", "ACCENT_SECONDARY": "#7dd3fc", "SUCCESS": "#22c55e", "DANGER": "#f43f5e",
            "TABLE_BG": "#0f172a", "CARD_BG": "#1e293b", "SIDEBAR_BG": "#0b121c"
        }
    },
    "gallente_emerald": {
        "name": "Gallente Emerald",
        "description": "Verde esmeralda, negro profundo, dorado suave. Elegante y orgánico.",
        "swatches": ["#040a08", "#061a14", "#10b981", "#fbbf24", "#d1fae5"],
        "tokens": {
            "BG_WINDOW": "#040a08", "NAV_BG": "#061a14", "NAV_BORDER": "#064e3b",
            "TAB_ACTIVE_BG": "#064e3b", "TAB_ACTIVE_TEXT": "#10b981", "TAB_INACTIVE_TEXT": "#34d399",
            "ACCENT": "#10b981", "ACCENT_SECONDARY": "#fbbf24", "SUCCESS": "#10b981", "DANGER": "#f43f5e",
            "TABLE_BG": "#05110d", "CARD_BG": "#061a14", "SIDEBAR_BG": "#040a08"
        }
    },
    "amarr_gold": {
        "name": "Amarr Gold",
        "description": "Negro, dorado, ámbar, marfil suave. Tema premium imperial.",
        "swatches": ["#080705", "#1a160b", "#fbbf24", "#f59e0b", "#fff7ed"],
        "tokens": {
            "BG_WINDOW": "#080705", "NAV_BG": "#1a160b", "NAV_BORDER": "#451a03",
            "TAB_ACTIVE_BG": "#451a03", "TAB_ACTIVE_TEXT": "#fbbf24", "TAB_INACTIVE_TEXT": "#d97706",
            "ACCENT": "#fbbf24", "ACCENT_SECONDARY": "#fef3c7", "SUCCESS": "#fbbf24", "DANGER": "#b91c1c",
            "TABLE_BG": "#0c0b08", "CARD_BG": "#1a160b", "SIDEBAR_BG": "#080705"
        }
    },
    "minmatar_rust": {
        "name": "Minmatar Rust",
        "description": "Negro carbón, cobre, naranja quemado, rojo óxido. Industrial agresivo.",
        "swatches": ["#0a0807", "#1c1410", "#ea580c", "#9a3412", "#fdba74"],
        "tokens": {
            "BG_WINDOW": "#0a0807", "NAV_BG": "#1c1410", "NAV_BORDER": "#431407",
            "TAB_ACTIVE_BG": "#431407", "TAB_ACTIVE_TEXT": "#ea580c", "TAB_INACTIVE_TEXT": "#9a3412",
            "ACCENT": "#ea580c", "ACCENT_SECONDARY": "#fdba74", "SUCCESS": "#fb923c", "DANGER": "#ef4444",
            "TABLE_BG": "#0e0d0b", "CARD_BG": "#1c1410", "SIDEBAR_BG": "#0a0807"
        }
    },
    "blood_raider": {
        "name": "Blood Raider Crimson",
        "description": "Negro, rojo sangre, granate, gris oscuro. Tema peligro y combate.",
        "swatches": ["#050202", "#1a0a0a", "#ef4444", "#7f1d1d", "#fecaca"],
        "tokens": {
            "BG_WINDOW": "#050202", "NAV_BG": "#1a0a0a", "NAV_BORDER": "#450a0a",
            "TAB_ACTIVE_BG": "#450a0a", "TAB_ACTIVE_TEXT": "#ef4444", "TAB_INACTIVE_TEXT": "#991b1b",
            "ACCENT": "#ef4444", "ACCENT_SECONDARY": "#f87171", "SUCCESS": "#ef4444", "DANGER": "#991b1b",
            "TABLE_BG": "#080404", "CARD_BG": "#1a0a0a", "SIDEBAR_BG": "#050202"
        }
    },
    "guristas_venom": {
        "name": "Guristas Venom",
        "description": "Negro, verde ácido, amarillo tóxico. Tema pirata.",
        "swatches": ["#050602", "#131a0a", "#bef264", "#a3e635", "#ecfccb"],
        "tokens": {
            "BG_WINDOW": "#050602", "NAV_BG": "#131a0a", "NAV_BORDER": "#365314",
            "TAB_ACTIVE_BG": "#365314", "TAB_ACTIVE_TEXT": "#bef264", "TAB_INACTIVE_TEXT": "#65a30d",
            "ACCENT": "#bef264", "ACCENT_SECONDARY": "#ecfccb", "SUCCESS": "#bef264", "DANGER": "#f43f5e",
            "TABLE_BG": "#080a04", "CARD_BG": "#131a0a", "SIDEBAR_BG": "#050602"
        }
    },
    "sansha_void": {
        "name": "Sansha Void",
        "description": "Negro violeta, púrpura eléctrico, azul oscuro. Tema oscuro sci-fi.",
        "swatches": ["#040206", "#110a1a", "#d946ef", "#a21caf", "#f5d0fe"],
        "tokens": {
            "BG_WINDOW": "#040206", "NAV_BG": "#110a1a", "NAV_BORDER": "#4a044e",
            "TAB_ACTIVE_BG": "#4a044e", "TAB_ACTIVE_TEXT": "#d946ef", "TAB_INACTIVE_TEXT": "#701a75",
            "ACCENT": "#d946ef", "ACCENT_SECONDARY": "#f5d0fe", "SUCCESS": "#d946ef", "DANGER": "#ef4444",
            "TABLE_BG": "#07040a", "CARD_BG": "#110a1a", "SIDEBAR_BG": "#040206"
        }
    },
    "abyssal_storm": {
        "name": "Abyssal Storm",
        "description": "Negro, morado, azul eléctrico, rosa controlado. Alto contraste abisal.",
        "swatches": ["#020204", "#0a0a14", "#3b82f6", "#8b5cf6", "#f472b6"],
        "tokens": {
            "BG_WINDOW": "#020204", "NAV_BG": "#0a0a14", "NAV_BORDER": "#1e1b4b",
            "TAB_ACTIVE_BG": "#1e1b4b", "TAB_ACTIVE_TEXT": "#3b82f6", "TAB_INACTIVE_TEXT": "#4338ca",
            "ACCENT": "#3b82f6", "ACCENT_SECONDARY": "#f472b6", "SUCCESS": "#8b5cf6", "DANGER": "#ef4444",
            "TABLE_BG": "#040408", "CARD_BG": "#0a0a14", "SIDEBAR_BG": "#020204"
        }
    },
    "jita_terminal": {
        "name": "Jita Terminal",
        "description": "Negro, verde terminal, amarillo de datos. Tema trading y mercado.",
        "swatches": ["#000000", "#051505", "#22c55e", "#fbbf24", "#dcfce7"],
        "tokens": {
            "BG_WINDOW": "#000000", "NAV_BG": "#051505", "NAV_BORDER": "#052e16",
            "TAB_ACTIVE_BG": "#052e16", "TAB_ACTIVE_TEXT": "#22c55e", "TAB_INACTIVE_TEXT": "#15803d",
            "ACCENT": "#22c55e", "ACCENT_SECONDARY": "#fbbf24", "SUCCESS": "#22c55e", "DANGER": "#b91c1c",
            "TABLE_BG": "#020802", "CARD_BG": "#051505", "SIDEBAR_BG": "#000000"
        }
    },
    "ice_belt": {
        "name": "Ice Belt",
        "description": "Azul hielo, negro, blanco azulado, cian pálido. Frío y limpio.",
        "swatches": ["#020617", "#0f172a", "#f0f9ff", "#e0f2fe", "#0ea5e9"],
        "tokens": {
            "BG_WINDOW": "#020617", "NAV_BG": "#0f172a", "NAV_BORDER": "#1e293b",
            "TAB_ACTIVE_BG": "#1e293b", "TAB_ACTIVE_TEXT": "#f0f9ff", "TAB_INACTIVE_TEXT": "#7dd3fc",
            "ACCENT": "#0ea5e9", "ACCENT_SECONDARY": "#f0f9ff", "SUCCESS": "#0ea5e9", "DANGER": "#f43f5e",
            "TABLE_BG": "#060b1e", "CARD_BG": "#0f172a", "SIDEBAR_BG": "#020617"
        }
    },
    "solar_flare": {
        "name": "Solar Flare",
        "description": "Negro, naranja, amarillo, rojo suave. Cálido y energético.",
        "swatches": ["#0c0a09", "#1c1917", "#f97316", "#facc15", "#fef3c7"],
        "tokens": {
            "BG_WINDOW": "#0c0a09", "NAV_BG": "#1c1917", "NAV_BORDER": "#44403c",
            "TAB_ACTIVE_BG": "#44403c", "TAB_ACTIVE_TEXT": "#f97316", "TAB_INACTIVE_TEXT": "#a8a29e",
            "ACCENT": "#f97316", "ACCENT_SECONDARY": "#facc15", "SUCCESS": "#facc15", "DANGER": "#dc2626",
            "TABLE_BG": "#100d0c", "CARD_BG": "#1c1917", "SIDEBAR_BG": "#0c0a09"
        }
    },
    "deep_space": {
        "name": "Deep Space",
        "description": "Negro puro, azul muy oscuro, violeta tenue. Elegante y minimalista.",
        "swatches": ["#000000", "#030712", "#1d4ed8", "#4338ca", "#93c5fd"],
        "tokens": {
            "BG_WINDOW": "#000000", "NAV_BG": "#030712", "NAV_BORDER": "#111827",
            "TAB_ACTIVE_BG": "#111827", "TAB_ACTIVE_TEXT": "#3b82f6", "TAB_INACTIVE_TEXT": "#1f2937",
            "ACCENT": "#3b82f6", "ACCENT_SECONDARY": "#6366f1", "SUCCESS": "#3b82f6", "DANGER": "#991b1b",
            "TABLE_BG": "#010103", "CARD_BG": "#030712", "SIDEBAR_BG": "#000000"
        }
    },
    "quantum_blue": {
        "name": "Quantum Blue",
        "description": "Azul eléctrico, navy, cian, blanco. Moderno y premium.",
        "swatches": ["#020617", "#1e40af", "#60a5fa", "#38bdf8", "#ffffff"],
        "tokens": {
            "BG_WINDOW": "#020617", "NAV_BG": "#0f172a", "NAV_BORDER": "#1e3a8a",
            "TAB_ACTIVE_BG": "#1e40af", "TAB_ACTIVE_TEXT": "#ffffff", "TAB_INACTIVE_TEXT": "#60a5fa",
            "ACCENT": "#60a5fa", "ACCENT_SECONDARY": "#38bdf8", "SUCCESS": "#38bdf8", "DANGER": "#f43f5e",
            "TABLE_BG": "#030a1e", "CARD_BG": "#0f172a", "SIDEBAR_BG": "#020617"
        }
    },
    "rogue_drone": {
        "name": "Rogue Drone",
        "description": "Negro, verde lima, naranja tenue, gris metal. Tema robótico.",
        "swatches": ["#09090b", "#18181b", "#84cc16", "#f97316", "#e4e4e7"],
        "tokens": {
            "BG_WINDOW": "#09090b", "NAV_BG": "#18181b", "NAV_BORDER": "#27272a",
            "TAB_ACTIVE_BG": "#27272a", "TAB_ACTIVE_TEXT": "#84cc16", "TAB_INACTIVE_TEXT": "#52525b",
            "ACCENT": "#84cc16", "ACCENT_SECONDARY": "#f97316", "SUCCESS": "#84cc16", "DANGER": "#dc2626",
            "TABLE_BG": "#0c0c0e", "CARD_BG": "#18181b", "SIDEBAR_BG": "#09090b"
        }
    },
    "triglavian": {
        "name": "Triglavian Singularity",
        "description": "Negro, rojo triglavian, naranja, gris. Exótico y combativo.",
        "swatches": ["#000000", "#100000", "#ff0000", "#ff7b00", "#333333"],
        "tokens": {
            "BG_WINDOW": "#000000", "NAV_BG": "#100000", "NAV_BORDER": "#300000",
            "TAB_ACTIVE_BG": "#300000", "TAB_ACTIVE_TEXT": "#ff0000", "TAB_INACTIVE_TEXT": "#600000",
            "ACCENT": "#ff0000", "ACCENT_SECONDARY": "#ff7b00", "SUCCESS": "#ff0000", "DANGER": "#600000",
            "TABLE_BG": "#050000", "CARD_BG": "#100000", "SIDEBAR_BG": "#000000"
        }
    },
    "eden_luxury": {
        "name": "Eden Luxury",
        "description": "Negro, champagne, oro suave, azul profundo. Premium y sobrio.",
        "swatches": ["#0a0a0a", "#171717", "#fef3c7", "#d4d4d8", "#1e3a8a"],
        "tokens": {
            "BG_WINDOW": "#0a0a0a", "NAV_BG": "#171717", "NAV_BORDER": "#262626",
            "TAB_ACTIVE_BG": "#262626", "TAB_ACTIVE_TEXT": "#fef3c7", "TAB_INACTIVE_TEXT": "#52525b",
            "ACCENT": "#fef3c7", "ACCENT_SECONDARY": "#d4d4d8", "SUCCESS": "#1e3a8a", "DANGER": "#7f1d1d",
            "TABLE_BG": "#0d0d0d", "CARD_BG": "#171717", "SIDEBAR_BG": "#0a0a0a"
        }
    },
    "stealth_ops": {
        "name": "Stealth Ops",
        "description": "Negro mate, gris carbón, azul apagado. Bajo contraste para sesiones largas.",
        "swatches": ["#080a0c", "#111827", "#4b5563", "#1f2937", "#10b981"],
        "tokens": {
            "BG_WINDOW": "#080a0c", "NAV_BG": "#111827", "NAV_BORDER": "#1f2937",
            "TAB_ACTIVE_BG": "#1f2937", "TAB_ACTIVE_TEXT": "#9ca3af", "TAB_INACTIVE_TEXT": "#4b5563",
            "ACCENT": "#4b5563", "ACCENT_SECONDARY": "#1f2937", "SUCCESS": "#10b981", "DANGER": "#991b1b",
            "TABLE_BG": "#0a0d10", "CARD_BG": "#111827", "SIDEBAR_BG": "#080a0c"
        }
    },
    "hypernet_candy": {
        "name": "HyperNet Candy",
        "description": "Negro, magenta, cian, violeta. Llamativo pero legible.",
        "swatches": ["#050505", "#101010", "#ff00ff", "#00ffff", "#8b5cf6"],
        "tokens": {
            "BG_WINDOW": "#050505", "NAV_BG": "#101010", "NAV_BORDER": "#202020",
            "TAB_ACTIVE_BG": "#202020", "TAB_ACTIVE_TEXT": "#ff00ff", "TAB_INACTIVE_TEXT": "#00ffff",
            "ACCENT": "#ff00ff", "ACCENT_SECONDARY": "#00ffff", "SUCCESS": "#00ffff", "DANGER": "#ff00ff",
            "TABLE_BG": "#080808", "CARD_BG": "#101010", "SIDEBAR_BG": "#050505"
        }
    }
}
