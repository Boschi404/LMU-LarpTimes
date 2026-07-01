"""
Tests for overlay/icons.py

Verifies that:
  - Each icon function returns a valid SVG string
  - icon_pixmap produces a QPixmap of the expected size
  - icon_widget returns a QLabel
  - clean_action_text strips emoji prefixes
"""

import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# ── SVG validity ─────────────────────────────────────────────────────────────

def _check_svg(svg_str: str, expected_size: int = 16):
    """Check that the SVG string is well-formed and has the right size."""
    assert svg_str.startswith('<svg'), f"SVG should start with <svg>, got {svg_str[:30]}"
    assert f'width="{expected_size}"' in svg_str, f"SVG should have width={expected_size}"
    assert f'height="{expected_size}"' in svg_str, f"SVG should have height={expected_size}"
    assert 'viewBox="0 0 24 24"' in svg_str, "SVG should have standard viewBox"
    assert 'stroke="currentColor"' in svg_str, "SVG should use currentColor for theming"
    assert svg_str.endswith('</svg>'), "SVG should end with </svg>"


def test_settings_icon():
    from overlay.icons import settings_icon
    _check_svg(settings_icon(), 16)
    _check_svg(settings_icon(size=24), 24)


def test_refresh_cw_icon():
    from overlay.icons import refresh_cw_icon
    _check_svg(refresh_cw_icon())


def test_eye_icon():
    from overlay.icons import eye_icon
    _check_svg(eye_icon())


def test_eye_off_icon():
    from overlay.icons import eye_off_icon
    _check_svg(eye_off_icon())


def test_globe_icon():
    from overlay.icons import globe_icon
    _check_svg(globe_icon())


def test_x_icon():
    from overlay.icons import x_icon
    _check_svg(x_icon())


def test_rotate_ccw_icon():
    from overlay.icons import rotate_ccw_icon
    _check_svg(rotate_ccw_icon())


def test_zap_icon():
    from overlay.icons import zap_icon
    _check_svg(zap_icon())


def test_circle_dot_icon():
    from overlay.icons import circle_dot_icon
    _check_svg(circle_dot_icon())


def test_play_icon():
    from overlay.icons import play_icon
    _check_svg(play_icon())


def test_crosshair_icon():
    from overlay.icons import crosshair_icon
    _check_svg(crosshair_icon())


def test_flame_icon():
    from overlay.icons import flame_icon
    _check_svg(flame_icon())


def test_droplet_icon():
    from overlay.icons import droplet_icon
    _check_svg(droplet_icon())


def test_thermometer_icon():
    from overlay.icons import thermometer_icon
    _check_svg(thermometer_icon())


def test_cloud_rain_icon():
    from overlay.icons import cloud_rain_icon
    _check_svg(cloud_rain_icon())


def test_cloud_icon():
    from overlay.icons import cloud_icon
    _check_svg(cloud_icon())


def test_flag_icon():
    from overlay.icons import flag_icon
    _check_svg(flag_icon())


def test_volume_2_icon():
    from overlay.icons import volume_2_icon
    _check_svg(volume_2_icon())


def test_volume_x_icon():
    from overlay.icons import volume_x_icon
    _check_svg(volume_x_icon())


def test_check_icon():
    from overlay.icons import check_icon
    _check_svg(check_icon())


def test_alert_triangle_icon():
    from overlay.icons import alert_triangle_icon
    _check_svg(alert_triangle_icon())


def test_moon_icon():
    from overlay.icons import moon_icon
    _check_svg(moon_icon())


def test_book_open_icon():
    from overlay.icons import book_open_icon
    _check_svg(book_open_icon())


def test_ban_icon():
    from overlay.icons import ban_icon
    _check_svg(ban_icon())


# ── QPixmap rendering ────────────────────────────────────────────────────────

def test_icon_pixmap(qt_app):
    """icon_pixmap should return a QPixmap of the requested size."""
    from overlay.icons import icon_pixmap, settings_icon
    pix = icon_pixmap(settings_icon(), size=16, color="#7d8590")
    assert not pix.isNull(), "Pixmap should not be null"
    assert pix.width() == 16
    assert pix.height() == 16

    pix2 = icon_pixmap(settings_icon(), size=32, color="#ff0000")
    assert pix2.width() == 32
    assert pix2.height() == 32


def test_icon_widget(qt_app):
    """icon_widget should return a QLabel with a non-null pixmap."""
    from overlay.icons import icon_widget, settings_icon
    lbl = icon_widget(settings_icon(), size=16, color="#7d8590")
    assert lbl.pixmap() is not None
    assert not lbl.pixmap().isNull()


# ── clean_action_text ────────────────────────────────────────────────────────

def test_clean_action_text_no_emoji():
    from overlay.icons import clean_action_text
    assert clean_action_text("Hello World") == "Hello World"


def test_clean_action_text_strips_leading_emoji():
    from overlay.icons import clean_action_text
    assert clean_action_text("\u2699  Settings") == "Settings"
    assert clean_action_text("\U0001f441  Show All") == "Show All"
    assert clean_action_text("\u274c  Exit") == "Exit"
    assert clean_action_text("\U0001f310  Open Web") == "Open Web"


def test_clean_action_text_strips_multiple_emoji():
    from overlay.icons import clean_action_text
    result = clean_action_text("\U0001f3af Best lap")
    assert result == "Best lap"
