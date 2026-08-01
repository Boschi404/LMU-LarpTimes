"""
LMU Pit Strategist — Overlay shared constants, config, and utilities.
Shared between overlay/app.py (full) and overlay/app_new.py (modular).
"""

import json
import os
from typing import Dict, Any, List, Optional

from PySide6.QtGui import QColor

import paths

# ══════════════════════════════════════════════════════════════════════════════
# Design System — v2 Cockpit
# ══════════════════════════════════════════════════════════════════════════════

BG_DEEP = QColor(7, 8, 9)
BG_APP = QColor(10, 12, 14)
BG_SURFACE = QColor(15, 19, 23)
BG_ELEVATED = QColor(22, 27, 32)
BG_INSET = QColor(30, 37, 44)
BORDER = QColor(30, 37, 44)
BORDER_STRONG = QColor(40, 48, 56)

ACCENT_AMBER = QColor(255, 107, 0)
ACCENT_AMBER_BRIGHT = QColor(255, 136, 0)
ACCENT_RED = QColor(255, 34, 0)
ACCENT_GREEN = QColor(0, 255, 136)
ACCENT_BLUE = QColor(0, 136, 255)
ACCENT_PURPLE = QColor(170, 102, 255)
ACCENT_CYAN = QColor(0, 200, 255)

TEXT_PRIMARY = QColor(240, 244, 248)
TEXT_SECONDARY = QColor(200, 212, 224)
TEXT_TERTIARY = QColor(90, 106, 122)
TEXT_MUTED = QColor(53, 64, 74)

FONT_DISPLAY = "Rajdhani"
FONT_MONO = "JetBrains Mono"
FONT_UI = "Inter"


def qcolor_hex(c: QColor) -> str:
    return '#%02x%02x%02x' % (c.red(), c.green(), c.blue())


# ══════════════════════════════════════════════════════════════════════════════
# Config persistence (shared by full + modular overlays)
# ══════════════════════════════════════════════════════════════════════════════

CONFIG_PATH = paths.data_path("overlay", "overlay_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    # Full overlay (app.py) position + visibility
    "x": 50, "y": 50, "visible": True,
    # Modular: per-component positions, visibility, and enabled flags
    "delta_x": 50,  "delta_y": 50,  "delta_vis": True, "delta_enabled": True,
    "fuel_x":  220, "fuel_y": 50,  "fuel_vis":  True, "fuel_enabled":  True,
    "cliff_x": 390, "cliff_y": 50,  "cliff_vis": True, "cliff_enabled": True,
    "pit_x":   560, "pit_y": 50,  "pit_vis":   True, "pit_enabled":   True,
    "weather_x": 50,  "weather_y": 120, "weather_vis": True, "weather_enabled": True,
    "wear_x": 220, "wear_y": 120, "wear_vis": True, "wear_enabled": True,
    "compound_x": 390, "compound_y": 120, "compound_vis": True, "compound_enabled": True,
    "sectors_x": 560, "sectors_y": 120, "sectors_vis": True, "sectors_enabled": True,
    "qualy_x": 50,  "qualy_y": 190, "qualy_vis": True, "qualy_enabled": True,
    "practice_x": 50, "practice_y": 260, "practice_vis": True, "practice_enabled": True,
    # Global toggles
    "in_game_only": False,
    # Audio
    "audio_enabled": True,
    "audio_volume": 1.0,
    # Practice mode (suggests practice laps when data is scarce)
    "practice_mode": True,
    # Hotkey IDs (used by app.py & app_new.py; both share the same registry)
    "hk_full_id":    1,
    "hk_modular_id": 2,
    "hk_hideall_id": 3,
    "_current_profile": "last_used",
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


# ── Profile auto-save support (used by modular overlay) ──────────────────

_active_profile_name: Optional[str] = None
PROFILES_DIR = paths.data_path("overlay", "profiles")


def set_active_profile_name(name: Optional[str]) -> None:
    """Set the active layout profile name (for app_new.py profile system)."""
    global _active_profile_name
    _active_profile_name = name


def _ensure_profiles_dir() -> str:
    os.makedirs(PROFILES_DIR, exist_ok=True)
    return PROFILES_DIR


def _extract_layout_keys(config: dict) -> dict:
    """Return only layout-relevant keys from a config dict."""
    keys = {}
    for k, v in config.items():
        if k.endswith(('_x', '_y', '_vis', '_enabled')):
            keys[k] = v
        elif k in ('in_game_only', 'tray_x', 'tray_y', 'warning_x', 'warning_y'):
            keys[k] = v
    return keys


def _save_profile(name: str, config: dict) -> None:
    """Save layout keys from config into a named profile file."""
    _ensure_profiles_dir()
    path = os.path.join(PROFILES_DIR, f"{name}.json")
    layout_keys = _extract_layout_keys(config)
    with open(path, 'w') as f:
        json.dump(layout_keys, f, indent=2)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    # Auto-save layout to profile system (only active in modular mode)
    try:
        _ensure_profiles_dir()
        layout_keys = _extract_layout_keys(cfg)
        if _active_profile_name:
            path = os.path.join(PROFILES_DIR, f"{_active_profile_name}.json")
            with open(path, "w") as pf:
                json.dump(layout_keys, pf, indent=2)
        # Always save last_used snapshot
        path2 = os.path.join(PROFILES_DIR, "last_used.json")
        with open(path2, "w") as pf:
            json.dump(layout_keys, pf, indent=2)
    except Exception:
        pass  # Don't let profile save failures break config saving
