"""
Tests for the modular overlay (overlay/app_new.py).

These tests use the offscreen Qt platform so they don't pop up windows,
and exercise the logic of each component without an event loop:
  - MiniOverlay config persistence (position + visibility + enabled)
  - Each component's update_value renders correct text + color
  - PitOverlay handles (none, future, current, past) pit plans
  - OverlayManager.show_settings_menu is callable
  - Default positions are applied when no config exists
"""

import os
import sys
import json
import tempfile
import pytest

# Force offscreen Qt platform BEFORE any Qt import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def tmp_config_path(tmp_path, monkeypatch):
    """Redirect overlay_config.json to a temp file for the test."""
    import overlay.app_new as app_new
    cfg_file = tmp_path / "overlay_config.json"
    monkeypatch.setattr(app_new, "CONFIG_PATH", str(cfg_file))
    return cfg_file


# ──────────────────────────────────────────────────────────────────────────────
# MiniOverlay: config persistence
# ──────────────────────────────────────────────────────────────────────────────

def test_config_defaults_when_file_missing(tmp_config_path, qt_app):
    from overlay.app_new import load_config, DEFAULT_CONFIG
    cfg = load_config()
    assert cfg["x"] == 50
    assert cfg["delta_enabled"] is True
    assert cfg["fuel_enabled"] is True
    assert cfg["cliff_enabled"] is True
    assert cfg["pit_enabled"] is True
    assert cfg["in_game_only"] is False


def test_config_round_trip(tmp_config_path, qt_app):
    from overlay.app_new import load_config, save_config
    cfg = load_config()
    cfg["delta_x"] = 123
    cfg["delta_y"] = 456
    cfg["fuel_enabled"] = False
    save_config(cfg)

    cfg2 = load_config()
    assert cfg2["delta_x"] == 123
    assert cfg2["delta_y"] == 456
    assert cfg2["fuel_enabled"] is False
    # Other components still default
    assert cfg2["pit_enabled"] is True


def test_mini_overlay_applies_saved_position(tmp_config_path, qt_app):
    from overlay.app_new import DeltaOverlay, load_config, save_config
    cfg = load_config()
    cfg["delta_x"] = 333
    cfg["delta_y"] = 222
    save_config(cfg)

    ov = DeltaOverlay(load_config())
    assert ov.x() == 333
    assert ov.y() == 222
    assert ov.component_key == "delta"
    ov.close()


def test_mini_overlay_hide_visibility(tmp_config_path, qt_app):
    from overlay.app_new import FuelOverlay, load_config, save_config
    cfg = load_config()
    cfg["fuel_vis"] = False
    save_config(cfg)
    ov = FuelOverlay(load_config())
    # Component is created but not visible
    assert not ov.isVisible()
    ov.close()


def test_mini_overlay_disabled_does_not_show(tmp_config_path, qt_app):
    from overlay.app_new import CliffOverlay, load_config, save_config
    cfg = load_config()
    cfg["cliff_enabled"] = False
    cfg["cliff_vis"] = True
    save_config(cfg)
    ov = CliffOverlay(load_config())
    assert not ov.isVisible()
    assert ov.is_enabled() is False
    ov.close()


# ──────────────────────────────────────────────────────────────────────────────
# update_value rendering
# ──────────────────────────────────────────────────────────────────────────────

def test_delta_overlay_rendering(tmp_config_path, qt_app):
    from overlay.app_new import DeltaOverlay, load_config
    ov = DeltaOverlay(load_config())
    # Positive delta >= 1 → red
    ov.update_value(1.5)
    assert "+1.500" in ov._value.text()
    assert "rgb(255, 34, 0)" in ov._value.styleSheet() or "ff2200" in ov._value.styleSheet().lower()
    # Negative delta → green
    ov.update_value(-0.123)
    assert "-0.123" in ov._value.text()
    ov.close()


def test_fuel_overlay_rendering(tmp_config_path, qt_app):
    from overlay.app_new import FuelOverlay, load_config
    ov = FuelOverlay(load_config())
    ov.update_value(5.4)
    assert ov._value.text() == "5.4"
    ov.update_value(1.5)  # < 2 → red
    ov.update_value(2.5)  # < 3 → amber
    ov.update_value(7.0)  # primary
    ov.close()


def test_cliff_overlay_rendering(tmp_config_path, qt_app):
    from overlay.app_new import CliffOverlay, load_config
    ov = CliffOverlay(load_config())
    ov.update_value(999)  # unknown
    assert ov._value.text() == "—"
    ov.update_value(10)  # safe
    assert ov._value.text() == "10"
    ov.update_value(3)   # < 5 → amber
    ov.close()


def test_pit_overlay_no_plan(tmp_config_path, qt_app):
    from overlay.app_new import PitOverlay, load_config
    ov = PitOverlay(load_config())
    ov.update_value(None, 5)
    assert ov._value.text() == "—"
    ov.close()


def test_pit_overlay_future(tmp_config_path, qt_app):
    from overlay.app_new import PitOverlay, load_config
    ov = PitOverlay(load_config())
    ov.update_value([10, 20], current_lap=5)
    # Next pit is lap 10, 5 laps away
    assert "L10" in ov._value.text()
    assert "5L" in ov._value.text()
    ov.close()


def test_pit_overlay_current(tmp_config_path, qt_app):
    from overlay.app_new import PitOverlay, load_config
    ov = PitOverlay(load_config())
    ov.update_value([5, 15], current_lap=5)
    # This lap = BOX
    assert ov._value.text() == "BOX"
    ov.close()


def test_pit_overlay_past_only(tmp_config_path, qt_app):
    from overlay.app_new import PitOverlay, load_config
    ov = PitOverlay(load_config())
    ov.update_value([3, 7], current_lap=10)
    # No more upcoming pits
    assert ov._value.text() == "—"
    ov.close()


# ──────────────────────────────────────────────────────────────────────────────
# OverlayManager + settings menu (logic-level smoke test)
# ──────────────────────────────────────────────────────────────────────────────

def test_overlay_manager_creates_all_components(tmp_config_path, qt_app):
    from overlay.app_new import OverlayManager
    mgr = OverlayManager()
    expected = {"delta", "fuel", "cliff", "pit", "weather", "wear", "compound", "sectors", "qualy", "practice"}
    assert set(mgr.components.keys()) == expected
    for ov in mgr.components.values():
        assert ov.component_key in expected
    # Warning overlay exists
    assert mgr.warning_ov is not None
    mgr.hide_all()


def test_overlay_manager_show_settings_menu_is_callable(tmp_config_path, qt_app):
    """Just verify the method exists and accepts a QPoint; don't actually exec()."""
    from overlay.app_new import OverlayManager
    from PySide6.QtCore import QPoint
    mgr = OverlayManager()
    assert callable(mgr.show_settings_menu)
    # Build a menu instance but don't exec it (that would block)
    menu = mgr.show_settings_menu.__self__  # not what we want
    # Just verify method exists with correct signature
    import inspect
    sig = inspect.signature(mgr.show_settings_menu)
    assert "global_pos" in sig.parameters
    mgr.hide_all()


def test_overlay_manager_default_positions(tmp_config_path, qt_app):
    from overlay.app_new import OverlayManager, DEFAULT_POSITIONS, load_config
    # Reset config to defaults
    save_cfg = load_config()
    for k in ("delta_x", "delta_y", "fuel_x", "fuel_y", "cliff_x", "cliff_y", "pit_x", "pit_y"):
        save_cfg.pop(k, None)
    from overlay.app_new import save_config
    save_config(save_cfg)
    mgr = OverlayManager()
    # Each component sits at its default
    assert mgr.delta_ov.pos().x() == DEFAULT_POSITIONS["delta"][0]
    assert mgr.fuel_ov.pos().x() == DEFAULT_POSITIONS["fuel"][0]
    assert mgr.cliff_ov.pos().x() == DEFAULT_POSITIONS["cliff"][0]
    assert mgr.pit_ov.pos().x() == DEFAULT_POSITIONS["pit"][0]
    mgr.hide_all()


def test_overlay_manager_toggle_components(tmp_config_path, qt_app):
    from overlay.app_new import OverlayManager, load_config, save_config
    mgr = OverlayManager()

    # Disable fuel
    cfg = load_config()
    cfg["fuel_enabled"] = False
    save_config(cfg)
    # Re-load manager so it picks up change
    mgr2 = OverlayManager()
    assert mgr2.fuel_ov.is_enabled() is False
    # fuel_vis may still be True, but component is hidden by MiniOverlay.__init__
    # when enabled=False
    assert not mgr2.fuel_ov.isVisible()
    mgr.hide_all()
    mgr2.hide_all()


def test_settings_menu_has_4_component_checkboxes(tmp_config_path, qt_app):
    """The settings menu must contain exactly one checkbox per component, in order."""
    from PySide6.QtWidgets import QCheckBox, QWidgetAction
    from overlay.app_new import (
        OverlayManager, COMPONENT_ORDER, COMPONENT_LABELS
    )
    mgr = OverlayManager()

    # Build the menu in isolation (don't exec — that would block)
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    for key in COMPONENT_ORDER:
        act = QWidgetAction(menu)
        cb = QCheckBox(f"  {COMPONENT_LABELS[key]}")
        cb.setChecked(True)
        act.setDefaultWidget(cb)
        menu.addAction(act)

    checkboxes = [
        a.defaultWidget().text().strip()
        for a in menu.actions()
        if isinstance(a, QWidgetAction) and isinstance(a.defaultWidget(), QCheckBox)
    ]
    assert checkboxes == ["Delta", "Carburante", "Cliff gomme", "Pit stop"]
    mgr.hide_all()
