"""
Lucide SVG icons for the LMU overlay.

Each function returns an SVG string at the requested size.
Use icon_widget() to create a QLabel that renders the SVG, or
icon_pixmap() to get a QPixmap for use with QPushButton/QIcon.
"""

import re
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# Icon functions (each returns an SVG string)
# ══════════════════════════════════════════════════════════════════════════════


def settings_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="3"/>'
        f'<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        f'</svg>'
    )


def refresh_cw_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>'
        f'<path d="M21 3v5h-5"/>'
        f'<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>'
        f'<path d="M3 21v-5h5"/>'
        f'</svg>'
    )


def eye_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/>'
        f'<circle cx="12" cy="12" r="3"/>'
        f'</svg>'
    )


def eye_off_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/>'
        f'<path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>'
        f'<path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/>'
        f'<path d="M2 2l20 20"/>'
        f'</svg>'
    )


def globe_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="10"/>'
        f'<path d="M2 12h20"/>'
        f'<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>'
        f'</svg>'
    )


def x_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M18 6 6 18"/>'
        f'<path d="m6 6 12 12"/>'
        f'</svg>'
    )


def rotate_ccw_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
        f'<path d="M3 3v5h5"/>'
        f'</svg>'
    )


def zap_icon(size=16) -> str:
    """Fuel / zap icon."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="13 2 3 14 12 14 11 22 21 10 12 10"/>'
        f'</svg>'
    )


def circle_dot_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="10"/>'
        f'<circle cx="12" cy="12" r="1"/>'
        f'</svg>'
    )


def play_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="5 3 19 12 5 21 5 3"/>'
        f'</svg>'
    )


def crosshair_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="10"/>'
        f'<path d="M22 12h-4"/>'
        f'<path d="M6 12H2"/>'
        f'<path d="M12 6V2"/>'
        f'<path d="M12 22v-4"/>'
        f'</svg>'
    )


def flame_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>'
        f'</svg>'
    )


def droplet_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>'
        f'</svg>'
    )


def thermometer_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>'
        f'</svg>'
    )


def cloud_rain_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M12 20v-8"/>'
        f'<path d="M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/>'
        f'<path d="M4.2 11.2A7 7 0 1 1 18 10"/>'
        f'</svg>'
    )


def cloud_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9z"/>'
        f'</svg>'
    )


def flag_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>'
        f'<line x1="4" x2="4" y1="22" y2="15"/>'
        f'</svg>'
    )


def volume_2_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
        f'<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
        f'<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'
        f'</svg>'
    )


def volume_x_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
        f'<line x1="22" y1="9" x2="16" y2="15"/>'
        f'<line x1="16" y1="9" x2="22" y2="15"/>'
        f'</svg>'
    )


def check_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<polyline points="20 6 9 17 4 12"/>'
        f'</svg>'
    )


def alert_triangle_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
        f'<line x1="12" y1="9" x2="12" y2="13"/>'
        f'<line x1="12" y1="17" x2="12.01" y2="17"/>'
        f'</svg>'
    )


def moon_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>'
        f'</svg>'
    )


def book_open_icon(size=16) -> str:
    """Graduation-cap / practice icon."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
        f'<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'
        f'</svg>'
    )


def ban_icon(size=16) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="10"/>'
        f'<path d="m4.9 4.9 14.2 14.2"/>'
        f'</svg>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


def icon_pixmap(svg_str: str, size: int = 16, color: str = "#7d8590"):
    """
    Render an SVG string to a QPixmap.

    The 'currentColor' in the SVG stroke is replaced with *color*.
    Returns a transparent-background QPixmap ready for use with QIcon.
    """
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QPixmap, QPainter
    from PySide6.QtCore import Qt

    colored = svg_str.replace('stroke="currentColor"', f'stroke="{color}"')
    renderer = QSvgRenderer(bytes(colored, encoding="utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def icon_widget(svg_str: str, size: int = 16, color: str = "#7d8590"):
    """
    Return a QLabel that renders the given SVG icon as a pixmap.
    """
    from PySide6.QtWidgets import QLabel

    pixmap = icon_pixmap(svg_str, size, color)
    lbl = QLabel()
    lbl.setPixmap(pixmap)
    return lbl


def make_icon_button(svg_str: str, size: int = 16, color: str = "#7d8590",
                     hover_color: Optional[str] = None, parent=None):
    """
    Return a QPushButton with an SVG icon.
    The button is square (size + 8) and transparent.
    """
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtGui import QIcon

    pixmap = icon_pixmap(svg_str, size, color)
    icon = QIcon(pixmap)
    btn = QPushButton(parent)
    btn.setIcon(icon)
    btn.setIconSize(pixmap.size())
    btn.setFixedSize(size + 8, size + 8)
    if hover_color:
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; }}"
            f"QPushButton:hover {{ background: transparent; }}"
        )
    return btn


def clean_action_text(text: str) -> str:
    """Remove emoji / icon prefix from menu action text."""
    # Strip common emoji characters from the start of the string
    emoji_pattern = (
        r'^[\u2600-\u27BF\u2B50\u2700-\u27BF'
        r'\u2600-\u26FF\u2700-\u27BF'
        r'\U0001F300-\U0001F9FF'
        r'\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA'
        r'\u25AA\u25AB\u25B6\u25C0\u25FB-\u25FE'
        r'\u2600-\u27BF]+\s*'
    )
    return re.sub(emoji_pattern, '', text)
