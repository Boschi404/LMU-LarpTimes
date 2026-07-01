"""
LMU Pit Strategist — Overlay Live MODULARE (Processo A)

Quattro finestrelle separate, ognuna un componente singolo:
  1. DeltaOverlay   — delta dal miglior giro
  2. FuelOverlay    — giri di carburante stimati rimanenti
  3. CliffOverlay   — giri al cliff degrado gomme
  4. PitOverlay     — prossimo pit stop (giro + quanti mancano)

Stesse regole di app.py (PySide6 frameless, always-on-top, drag-to-move,
auto-hide when in_game_only=True, persistenza in overlay_config.json).

NOVITÀ rispetto alla versione precedente:
  - Menu di configurazione (tasto destro / pulsante ingranaggio) per
    attivare/disattivare ciascun componente, riordinare, resettare posizioni.
  - Hotkey globali: Ctrl+Shift+O toggle full, Ctrl+Shift+M toggle modulare.

Esempio di utilizzo:
    from overlay.app_new import run_overlay
    from telemetry.source import LiveSharedMemorySource
    run_overlay(LiveSharedMemorySource())
"""

import sys
import ctypes
import ctypes.wintypes
import json
import os
import time
from typing import Optional, List, Dict, Any

from PySide6.QtCore import (
    Qt, QPoint, QTimer, Signal, QObject, QThread
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QPen, QBrush
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu,
    QWidgetAction, QCheckBox, QDialog, QInputDialog, QMessageBox,
    QSlider, QPushButton, QRadioButton
)

import database
from telemetry.source import TelemetrySource, TelemetryFrame
from analysis.models import fit_degradation_model, fit_fuel_model
from analysis.strategist import PitStrategist
from analysis.qualifying import QualifyingAnalyst, classify_qualifying_laps, TYRE_COLD, TYRE_IN_WINDOW, TYRE_DEGRADED
from analysis.tyre_manager import estimate_remaining_life, TyreStatus
from analysis.practice import analyze_practice_data
from overlay.strategy_refresher import (
    AudioEngine, PracticeAdvisor, StrategyRefresher,
)
from overlay.icons import settings_icon, icon_pixmap, clean_action_text

# ══════════════════════════════════════════════════════════════════════════════
# Design System (aligned with web UI & app.py)
# ══════════════════════════════════════════════════════════════════════════════

BG_0 = QColor(5, 7, 9, 240)        # --bg-app with alpha
BG_1 = QColor(13, 17, 23, 230)     # --surface-1
BG_2 = QColor(20, 26, 33, 230)     # --surface-2
BORDER_DIM = QColor(28, 33, 40)    # --border-dim (keep)
BORDER_BRIGHT = QColor(45, 51, 59) # --border-bright (keep)

ACCENT_GREEN = QColor(46, 160, 67)   # --accent-green #2ea043
ACCENT_BLUE = QColor(0, 161, 255)    # --accent-blue #00a1ff
ACCENT_RED = QColor(255, 77, 77)     # --accent-red #ff4d4d
ACCENT_AMBER = QColor(247, 129, 102) # --accent-orange #f78166
ACCENT_PURPLE = QColor(188, 140, 255) # --accent-purple #bc8cff

TEXT_PRIMARY = QColor(230, 237, 243)   # --text-primary
TEXT_SECONDARY = QColor(125, 133, 144) # --text-secondary
TEXT_MUTED = QColor(72, 79, 88)       # --text-muted

FONT_TITLE = "Rajdhani"   # change from Geist to Rajdhani
FONT_VALUE = "JetBrains Mono"  # keep for numeric values

# Default positions per component
DEFAULT_POSITIONS = {
    "delta": (50, 50),
    "fuel":  (220, 50),
    "cliff": (390, 50),
    "pit":   (560, 50),
    "weather": (50, 120),
    "wear": (220, 120),
    "compound": (390, 120),
    "sectors": (560, 120),
    "qualy": (50, 190),
    "practice": (50, 260),
}
# Logical order of components
COMPONENT_ORDER = ["delta", "fuel", "cliff", "pit", "weather", "wear", "compound", "sectors", "qualy", "practice"]
COMPONENT_LABELS = {
    "delta": "Delta",
    "fuel":  "Carburante",
    "cliff": "Cliff gomme",
    "pit":   "Pit stop",
    "weather": "Meteo",
    "wear": "Usura gomme",
    "compound": "Mescola",
    "sectors": "Settori",
    "qualy": "Qualifica",
    "practice": "Pratica",
}


def qcolor_hex(c: QColor) -> str:
    return '#%02x%02x%02x' % (c.red(), c.green(), c.blue())


# ══════════════════════════════════════════════════════════════════════════════
# Config persistence
# ══════════════════════════════════════════════════════════════════════════════

import paths
CONFIG_PATH = paths.data_path("overlay", "overlay_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    # Full overlay (app.py) position + visibility
    "x": 50, "y": 50, "visible": True,
    # Modulare: per ogni componente {x, y, vis, enabled}
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


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    # Auto-save layout to profile system
    try:
        if _active_profile_name:
            _save_profile(_active_profile_name, cfg)
        _save_profile("last_used", cfg)
    except Exception:
        pass  # Don't let profile save failures break config saving


# ══════════════════════════════════════════════════════════════════════════════
# Profile system — save/load named layout snapshots
# ══════════════════════════════════════════════════════════════════════════════

PROFILES_DIR = paths.data_path("overlay", "profiles")
_active_profile_name: Optional[str] = None  # set by OverlayManager when a profile is active


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


def get_profile_names() -> List[str]:
    """Return sorted list of available profile names (excluding last_used)."""
    _ensure_profiles_dir()
    return sorted(
        f[:-5] for f in os.listdir(PROFILES_DIR)
        if f.endswith('.json') and f != 'last_used.json'
    )


def _save_profile(name: str, config: dict) -> None:
    """Save layout keys from config into a named profile file."""
    _ensure_profiles_dir()
    path = os.path.join(PROFILES_DIR, f"{name}.json")
    layout_keys = _extract_layout_keys(config)
    with open(path, 'w') as f:
        json.dump(layout_keys, f, indent=2)


def load_profile(name: str) -> dict:
    """Load a saved profile; returns {} if not found or corrupt."""
    _ensure_profiles_dir()
    path = os.path.join(PROFILES_DIR, f"{name}.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def delete_profile(name: str) -> bool:
    """Delete a named profile file. Returns True if successfully deleted."""
    _ensure_profiles_dir()
    path = os.path.join(PROFILES_DIR, f"{name}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Telemetry Worker
# ══════════════════════════════════════════════════════════════════════════════

class TelemetryWorker(QObject):
    """Runs TelemetrySource polling in a background thread and emits frame signals."""
    frame_ready = Signal(object)       # TelemetryFrame
    lap_completed = Signal(int)        # lap_id in DB
    race_started = Signal(str, str, str)  # session_uuid, car, track
    qualifying_started = Signal(str, str, str)  # session_uuid, car, track

    def __init__(self, source: TelemetrySource, db_path: str):
        super().__init__()
        self.source = source
        self.db_path = db_path
        self._running = False
        self._detector = None

    def start_source(self):
        from telemetry.detector import LapBoundaryDetector
        self._detector = LapBoundaryDetector(
            db_path=self.db_path,
            on_race_started=self._race_started_wrapper,
            on_qualifying_started=self._qualifying_started_wrapper,
        )
        self.source.start()
        self._running = True

        TICK = 0.05  # 20 Hz UI poll
        while self._running:
            frame = self.source.get_next_frame()
            if frame is not None:
                lap_id = self._detector.process_frame(frame)
                if lap_id is not None:
                    self.lap_completed.emit(lap_id)
                self.frame_ready.emit(frame)
            time.sleep(TICK)

    def stop(self):
        self._running = False
        try:
            self.source.stop()
        except Exception:
            pass

    def _race_started_wrapper(self, session_uuid, car, track):
        """Called from the detector thread when a RACE starts."""
        self.race_started.emit(session_uuid, car, track)

    def _qualifying_started_wrapper(self, session_uuid, car, track):
        """Called from the detector thread when a QUALIFYING session starts."""
        self.qualifying_started.emit(session_uuid, car, track)


# ══════════════════════════════════════════════════════════════════════════════
# MiniOverlay base class — one frameless always-on-top window per component
# ══════════════════════════════════════════════════════════════════════════════

class MiniOverlay(QWidget):
    """
    A small, frameless, always-on-top, draggable overlay.
    Subclasses override `update_value(...)` to render their specific data.
    The base class handles: dragging, hotkey toggle, config persistence,
    visibility, paint, and the right-click config menu.
    """

    # Subclasses set this in __init__
    component_key: str = ""   # e.g. "delta"
    value_label_text: str = ""  # e.g. "+0.000"

    def __init__(self, cfg: dict, db_path: str = database.DEFAULT_DB_PATH):
        super().__init__()
        if not self.component_key:
            raise RuntimeError("MiniOverlay subclass must set component_key")

        self.db_path = db_path
        self._cfg = cfg
        self._drag_pos: Optional[QPoint] = None

        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumSize(160, 90)
        self.resize(160, 90)

        # Apply saved position + visibility
        x = self._cfg.get(f"{self.component_key}_x", DEFAULT_POSITIONS[self.component_key][0])
        y = self._cfg.get(f"{self.component_key}_y", DEFAULT_POSITIONS[self.component_key][1])
        self.move(x, y)
        if self._cfg.get(f"{self.component_key}_vis", True) and self._cfg.get(f"{self.component_key}_enabled", True):
            self.show()
        else:
            self.hide()

        # Build UI (label + value)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self._title = QLabel(COMPONENT_LABELS[self.component_key].upper())
        self._title.setFont(QFont(FONT_TITLE, 7, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)}; letter-spacing: 1px;")
        self._value = QLabel("—")
        self._value.setFont(QFont(FONT_VALUE, 18, QFont.Weight.Bold))
        self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._title)
        layout.addWidget(self._value)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_value(self, *args, **kwargs):
        """Override in subclass. Update _value label and color."""
        raise NotImplementedError

    def is_enabled(self) -> bool:
        return bool(self._cfg.get(f"{self.component_key}_enabled", True))

    def show_overlay(self):
        self._cfg[f"{self.component_key}_vis"] = True
        self.show()
        save_config(self._cfg)

    def hide_overlay(self):
        self._cfg[f"{self.component_key}_vis"] = False
        self.hide()
        save_config(self._cfg)

    def toggle_visible(self):
        if self.isVisible():
            self.hide_overlay()
        else:
            self.show_overlay()

    def reset_position(self):
        x, y = DEFAULT_POSITIONS[self.component_key]
        self._cfg[f"{self.component_key}_x"] = x
        self._cfg[f"{self.component_key}_y"] = y
        self.move(x, y)
        save_config(self._cfg)

    # ── Right-click config menu ──────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {qcolor_hex(BG_0)}; color: {qcolor_hex(TEXT_PRIMARY)};
                     border: 1px solid {qcolor_hex(BORDER_BRIGHT)}; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px; }}
            QMenu::item:selected {{ background-color: {qcolor_hex(ACCENT_BLUE)}; }}
            QMenu::separator {{ height: 1px; background: {qcolor_hex(BORDER_BRIGHT)}; margin: 4px 8px; }}
        """)

        header = menu.addAction(f"  {COMPONENT_LABELS[self.component_key]}")
        header.setEnabled(False)
        menu.addSeparator()

        # Per-component enable toggle
        act_toggle = menu.addAction(
            "Disattiva" if self.is_enabled() else "Attiva"
        )
        # Hot-key hint shown to the user
        menu.addAction("Hotkey globale: Ctrl+Shift+M (modulare)")\
            .setEnabled(False)
        menu.addSeparator()

        act_reset = menu.addAction("Reset posizione")
        act_hide = menu.addAction("Nascondi questa finestra")

        chosen = menu.exec(event.globalPos())
        if chosen is act_toggle:
            new_state = not self.is_enabled()
            self._cfg[f"{self.component_key}_enabled"] = new_state
            save_config(self._cfg)
            if not new_state:
                self.hide()
        elif chosen is act_reset:
            self.reset_position()
        elif chosen is act_hide:
            self.hide_overlay()

    # ── Drag to move ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        if self._drag_pos:
            pos = self.pos()
            self._cfg[f"{self.component_key}_x"] = pos.x()
            self._cfg[f"{self.component_key}_y"] = pos.y()
            save_config(self._cfg)
            self._drag_pos = None

    # ── Paint (rounded rect + accent stripe) ─────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        # Shadow / depth effect
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect.adjusted(2, 2, 0, 0), 8, 8)

        # Background
        painter.setBrush(QBrush(BG_0))
        pen = QPen(BORDER_BRIGHT, 1)
        painter.setPen(pen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        # Grid dot pattern
        painter.setPen(QPen(QColor(255, 255, 255, 6), 1))
        dot_spacing = 24
        for x in range(dot_spacing, rect.width(), dot_spacing):
            for y in range(dot_spacing, rect.height(), dot_spacing):
                painter.drawPoint(x, y)

        # Top accent bar (6px blue with glow)
        painter.setBrush(QBrush(ACCENT_BLUE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, rect.width(), 6, 3, 3)
        glow = QLinearGradient(0, 0, 0, 24)
        glow.setColorAt(0.0, QColor(0, 161, 255, 80))
        glow.setColorAt(1.0, QColor(0, 161, 255, 0))
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(0, 0, rect.width(), 24, 3, 3)

        # Left accent bar (3px blue)
        painter.setBrush(QBrush(ACCENT_BLUE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 14, 3, rect.height() - 28, 1, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Concrete components
# ══════════════════════════════════════════════════════════════════════════════

class DeltaOverlay(MiniOverlay):
    component_key = "delta"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value.setFont(QFont(FONT_VALUE, 14, QFont.Weight.Bold))

    def update_value(self, delta: float, **_unused):
        sign = "+" if delta > 0 else ""
        color = qcolor_hex(ACCENT_GREEN) if delta <= 0 else qcolor_hex(ACCENT_RED)
        self._value.setText(f"{sign}{delta:.3f}")
        self._value.setStyleSheet(f"color: {color};")

        # Visual bar via background opacity based on delta magnitude
        intensity = min(abs(delta) * 20, 100)
        if delta > 0:
            bar_color = f"rgba(255, 77, 77, {intensity / 300.0})"
        else:
            bar_color = f"rgba(46, 160, 67, {intensity / 300.0})"
        self.setStyleSheet(f"background-color: {bar_color};")


class FuelOverlay(MiniOverlay):
    component_key = "fuel"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value.setFont(QFont(FONT_VALUE, 13, QFont.Weight.Bold))

    def update_value(self, fuel_laps: float, refuel_l: Optional[float] = None, **_unused):
        if fuel_laps < 2:
            color = qcolor_hex(ACCENT_RED)
        elif fuel_laps < 3:
            color = qcolor_hex(ACCENT_RED)
        else:
            color = qcolor_hex(TEXT_PRIMARY)

        if refuel_l is not None and refuel_l > 0:
            text = f"{fuel_laps:.1f}L / +{refuel_l:.1f}L"
            self._value.setFont(QFont(FONT_VALUE, 10, QFont.Weight.Bold))
        else:
            text = f"{fuel_laps:.1f}"
            self._value.setFont(QFont(FONT_VALUE, 13, QFont.Weight.Bold))

        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color};")


class CliffOverlay(MiniOverlay):
    component_key = "cliff"

    def update_value(self, cliff_laps: int, **_unused):
        if cliff_laps >= 999:
            text = "—"
            color = qcolor_hex(TEXT_MUTED)
        else:
            text = str(cliff_laps)
            color = qcolor_hex(ACCENT_AMBER) if cliff_laps < 5 else qcolor_hex(TEXT_PRIMARY)
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color};")


class PitOverlay(MiniOverlay):
    component_key = "pit"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value.setFont(QFont(FONT_VALUE, 14, QFont.Weight.Bold))

    def update_value(self, pit_plan: Optional[List[int]], current_lap: int, **_unused):
        if not pit_plan:
            text, color = "—", qcolor_hex(TEXT_MUTED)
        else:
            next_pit = next((l for l in pit_plan if l >= current_lap), None)
            if next_pit is None:
                text, color = "—", qcolor_hex(TEXT_MUTED)
            elif next_pit == current_lap:
                text, color = "BOX", qcolor_hex(ACCENT_RED)
            else:
                text = f"L{next_pit} ({next_pit - current_lap}L)"
                color = qcolor_hex(TEXT_PRIMARY)
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color};")


class WeatherOverlay(MiniOverlay):
    """Shows weather, track temp, ambient temp."""
    component_key = "weather"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title.setText("METEO".upper())
        self._value.setFont(QFont(FONT_VALUE, 12, QFont.Weight.Bold))

    def update_value(self, frame: Optional[TelemetryFrame] = None, **_unused):
        if frame is None or not frame.weather_state:
            self._value.setText("—")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            return
        w = frame.weather_state or "—"
        tt = f"{frame.track_temp:.0f}°" if frame.track_temp else "—"
        at = f"{frame.ambient_temp:.0f}°" if frame.ambient_temp else "—"
        rain = f"pioggia {frame.rain_intensity:.0%}" if frame.rain_intensity > 0 else ""
        parts = [w, f"pista {tt}", f"aria {at}"]
        if rain:
            parts.append(rain)
        self._value.setText(" | ".join(parts))
        self._value.setStyleSheet(f"color: {qcolor_hex(ACCENT_BLUE)}; font-size: 9px;")


class WearOverlay(MiniOverlay):
    """Shows tyre wear percentages and live remaining-life prediction."""
    component_key = "wear"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title.setText("USURA GOMME".upper())
        self._value.setFont(QFont(FONT_VALUE, 11, QFont.Weight.Bold))
        # Status line for tyre prediction
        self._status = QLabel("")
        self._status.setFont(QFont(FONT_VALUE, 7, QFont.Weight.Medium))
        self._status.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)};")
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._status.setWordWrap(False)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self._status)
        self.setMinimumSize(160, 110)

    def update_value(
        self,
        frame: Optional[TelemetryFrame] = None,
        tyre_status: Optional[Any] = None,
        **_unused,
    ):
        if frame is None:
            self._value.setText("—")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            self._status.setText("")
            return

        # Wear percentage display
        w = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
        text = f"FL {w[0]:.0f}%  FR {w[1]:.0f}%  RL {w[2]:.0f}%  RR {w[3]:.0f}%"

        # Colour based on tyre status or fallback to wear level
        if tyre_status is not None:
            remaining = tyre_status.remaining_laps
            if remaining <= 0:
                value_color = qcolor_hex(ACCENT_RED)
            elif remaining <= 2:
                value_color = qcolor_hex(ACCENT_RED)
            elif remaining <= 5:
                value_color = qcolor_hex(ACCENT_AMBER)
            else:
                value_color = qcolor_hex(ACCENT_GREEN)

            # Build status text
            status_parts = []
            if remaining <= 0:
                status_parts.append(f"CLIFF — pit now!")
            elif remaining <= 2:
                status_parts.append(f"⬇ pit in {remaining}L")
            elif remaining <= 5:
                status_parts.append(f"⬇ ~{remaining}L left")
            else:
                status_parts.append(f"✔ {remaining}L left")

            # Temp indicator
            ts = tyre_status.temp_status
            if ts == "cold":
                status_parts.append("❄ cold")
            elif ts == "hot":
                status_parts.append("🔥 hot")
            elif ts == "degraded":
                status_parts.append("⚠ overheated")
            elif ts == "optimal":
                status_parts.append("✓ temp OK")

            self._status.setText("  ".join(status_parts))

            # Colour the status line too
            if remaining <= 0:
                status_color = qcolor_hex(ACCENT_RED)
            elif remaining <= 2:
                status_color = qcolor_hex(ACCENT_RED)
            elif remaining <= 5:
                status_color = qcolor_hex(ACCENT_AMBER)
            else:
                status_color = qcolor_hex(ACCENT_GREEN)

            self._status.setStyleSheet(
                f"color: {status_color}; font-size: 8px; letter-spacing: 1px;"
            )
        else:
            # Fallback: colour by wear level
            value_color = qcolor_hex(ACCENT_AMBER) if min(w) < 40 else qcolor_hex(TEXT_PRIMARY)
            self._status.setText("")
            self._status.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)};")

        self._value.setText(text)
        self._value.setStyleSheet(f"color: {value_color}; font-size: 9px;")


class CompoundOverlay(MiniOverlay):
    """Shows current tyre compound."""
    component_key = "compound"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title.setText("MESCOLA".upper())
        self._value.setFont(QFont(FONT_VALUE, 12, QFont.Weight.Bold))

    def update_value(self, frame: Optional[TelemetryFrame] = None, **_unused):
        if frame is None:
            self._value.setText("—")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            return
        compound = frame.tyre_compounds[0] or "—"
        self._value.setText(compound)
        self._value.setStyleSheet(f"color: {qcolor_hex(ACCENT_GREEN)};")


class SectorsOverlay(MiniOverlay):
    """Shows sector times for the current lap."""
    component_key = "sectors"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title.setText("SETTORI".upper())
        self._value.setFont(QFont(FONT_VALUE, 11, QFont.Weight.Bold))

    def update_value(self, frame: Optional[TelemetryFrame] = None, **_unused):
        if frame is None:
            self._value.setText("—")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            return
        s1 = frame.last_sector1 if frame.last_sector1 else 0
        s2 = frame.last_sector2 - frame.last_sector1 if (frame.last_sector2 and frame.last_sector1) else 0
        s3 = frame.last_lap_time - frame.last_sector2 if (frame.last_lap_time and frame.last_sector2) else 0
        self._value.setText(f"S1 {s1:.1f}s  S2 {s2:.1f}s  S3 {s3:.1f}s")
        self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)}; font-size: 9px;")


class PracticeOverlay(MiniOverlay):
    """Shows practice data analysis: fuel range, tyre age, compound coverage."""
    component_key = "practice"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title.setText("PRATICA".upper())
        self._value.setFont(QFont(FONT_VALUE, 10, QFont.Weight.Bold))

    def update_value(self, practice_data: Optional[Dict[str, Any]] = None, **_unused):
        if practice_data is None:
            self._value.setText("\u2014")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; font-size: 10px;")
            return

        total = practice_data.get("total_laps", 0)
        fuel = practice_data.get("fuel", {})
        tyre = practice_data.get("tyre", {})
        compounds = practice_data.get("compounds", [])
        suggestions = practice_data.get("suggestions", [])

        lines = [f"{total} giri"]
        if fuel.get("range_lap", 0) > 0:
            lines.append(f"Carb. {fuel['min_l']}-{fuel['max_l']}L")
        if tyre.get("range_laps", 0) > 0:
            lines.append(f"Gomme {tyre['min_age']}-{tyre['max_age']}g")
        if compounds:
            lines.append(f"{'/'.join(compounds)}")

        if suggestions:
            # Show the most important suggestion
            top = max(suggestions, key=lambda s: {"high": 3, "medium": 2, "low": 1}.get(s.get("priority", "low"), 0))
            lines.append(f"{top.get('message', '')[:60]}")

        text = " | ".join(lines)
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {qcolor_hex(ACCENT_BLUE)}; font-size: 9px;")

class QualifyingOverlay(MiniOverlay):
    """Shows qualifying-specific info: best hotlap, fuel saving, outlap/inlap delta."""
    component_key = "qualy"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title.setText("QUALIFICA".upper())
        self._value.setFont(QFont(FONT_VALUE, 11, QFont.Weight.Bold))

    def update_value(self, qualy_data: Optional[Dict[str, Any]] = None, **_unused):
        if qualy_data is None:
            self._value.setText("—")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            return

        best = qualy_data.get("best_hotlap_time")
        fuel_save = qualy_data.get("fuel_saving_potential", 0)
        out_delta = qualy_data.get("outlap_delta_from_hot")
        in_delta = qualy_data.get("inlap_delta_from_hot")
        hotlaps = qualy_data.get("num_hotlaps", 0)
        suggestions = qualy_data.get("suggestions", [])

        lines = []
        if best:
            lines.append(f"Miglior {best:.1f}s")
        if hotlaps:
            lines.append(f"{hotlaps} hot lap(s)")
        if fuel_save > 0.5:
            lines.append(f"-{fuel_save:.1f}L risparmio")
        if out_delta is not None:
            lines.append(f"Out +{out_delta:.1f}s")
        if in_delta is not None:
            lines.append(f"In +{in_delta:.1f}s")

        # Tyre temperature window
        tyre_window = qualy_data.get("tyre_temp_window")
        if tyre_window:
            msg = tyre_window.get("tyre_window_message", "")
            if msg:
                lines.append(clean_action_text(msg))
            best_in = tyre_window.get("best_in_window")
            best_out = tyre_window.get("best_outside_window")
            if best_in and best_out:
                lost = best_in - best_out
                if lost > 0:
                    lines.append(f"Fuori finestra +{lost:.2f}s")
            hotlaps_opt = tyre_window.get("optimal_hotlaps_count")
            if hotlaps_opt is not None and hotlaps_opt > 0:
                lines.append(f"{hotlaps_opt}x hotlap/run")

        # Determine tyre window indicator color
        indicator_color = ACCENT_GREEN
        if tyre_window:
            lc = tyre_window.get("laps_classified", [])
            if lc:
                hotlap_states = [
                    l.get("tyre_state") for l in lc
                    if l.get("role") == "hotlap"
                ]
                if not hotlap_states:
                    hotlap_states = [l.get("tyre_state") for l in lc]
                if TYRE_IN_WINDOW in hotlap_states:
                    indicator_color = ACCENT_GREEN
                elif TYRE_COLD in hotlap_states:
                    indicator_color = ACCENT_AMBER
                else:
                    indicator_color = ACCENT_RED

        if lines:
            text = " | ".join(lines)
            self._value.setText(text)
            self._value.setStyleSheet(f"color: {qcolor_hex(indicator_color)}; font-size: 10px;")
        else:
            self._value.setText("Collecting data\u2026")
            self._value.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; font-size: 10px;")


# ══════════════════════════════════════════════════════════════════════════════
# Warning banner (separate window — same role as in app.py)
# ══════════════════════════════════════════════════════════════════════════════

class WarningOverlay(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._cfg = cfg
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedHeight(38)
        self._text = QLabel("")
        self._text.setFont(QFont(FONT_TITLE, 10, QFont.Weight.Bold))
        self._text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.addWidget(self._text)
        self.hide()

    def show_warning(self, text: str, critical: bool = False):
        self._text.setText(text)
        color = qcolor_hex(ACCENT_RED) if critical else qcolor_hex(ACCENT_AMBER)
        self._text.setStyleSheet(f"color: {color};")
        if self._cfg.get("warning_x", None) is not None:
            self.move(self._cfg["warning_x"], self._cfg.get("warning_y", 720))
        else:
            self.move(50, 720)
        self.adjustSize()
        self.show()

    def hide_warning(self):
        self.hide()


# ══════════════════════════════════════════════════════════════════════════════
# OverlayManager — owns all 4 components, runs the menu, handles hotkeys
# ══════════════════════════════════════════════════════════════════════════════

class OverlayManager(QObject):
    """
    Manages the 4 modular overlay components + the warning banner.
    Provides a config dialog (QMenu) that lets the user toggle each
    component on/off, reset positions, hide/show the warning, etc.
    """

    # Signals for hotkey polling
    toggle_all_signal = Signal()
    profile_changed = Signal(str)  # emitted when a profile is loaded/saved

    def __init__(self, db_path: str = database.DEFAULT_DB_PATH):
        super().__init__()
        self.db_path = db_path
        self._cfg = load_config()

        # Build components
        self.delta_ov = DeltaOverlay(self._cfg, db_path)
        self.fuel_ov  = FuelOverlay(self._cfg, db_path)
        self.cliff_ov = CliffOverlay(self._cfg, db_path)
        self.pit_ov   = PitOverlay(self._cfg, db_path)
        self.qualy_ov = QualifyingOverlay(self._cfg, db_path)
        self.practice_ov = PracticeOverlay(self._cfg, db_path)
        self.weather_ov = WeatherOverlay(self._cfg, db_path)
        self.wear_ov = WearOverlay(self._cfg, db_path)
        self.compound_ov = CompoundOverlay(self._cfg, db_path)
        self.sectors_ov = SectorsOverlay(self._cfg, db_path)
        self.components: Dict[str, MiniOverlay] = {
            "delta": self.delta_ov,
            "fuel":  self.fuel_ov,
            "cliff": self.cliff_ov,
            "pit":   self.pit_ov,
            "weather": self.weather_ov,
            "wear": self.wear_ov,
            "compound": self.compound_ov,
            "sectors": self.sectors_ov,
            "qualy": self.qualy_ov,
            "practice": self.practice_ov,
        }
        self.warning_ov = WarningOverlay(self._cfg)

        # State
        self._car: Optional[str] = None
        self._track: Optional[str] = None
        self._pit_plan: Optional[List[int]] = None
        self._total_race_laps: int = 0
        self._current_lap: int = 1
        self._last_frame: Optional[TelemetryFrame] = None
        self._user_wants_visible: bool = True
        self._session_type: Optional[str] = None
        self._qualy_data: Optional[Dict[str, Any]] = None
        # Tyre age tracking
        self._tyre_age_laps: int = 0
        self._last_stint: int = 0

        # Audio + adaptive strategy
        self.audio_engine = AudioEngine(
            enabled=bool(self._cfg.get("audio_enabled", True)),
            volume=float(self._cfg.get("audio_volume", 1.0)),
        )
        self.refresher = StrategyRefresher(self, interval_ms=5000)
        self.refresher.audio_cue.connect(self._play_audio_cue)
        self.refresher.plan_updated.connect(self._on_plan_updated)

        # Hotkey registration
        self._hk_modular_id = int(self._cfg.get("hk_modular_id", 2))
        self._hk_hideall_id = int(self._cfg.get("hk_hideall_id", 3))
        self._register_hotkeys()

        # Profile system — load stored profile on startup
        global _active_profile_name
        self._tray_widget = None  # will be set by run_overlay
        stored_profile = self._cfg.get("_current_profile", "last_used")
        profile_data = load_profile(stored_profile)
        if profile_data:
            _active_profile_name = stored_profile
            self._current_profile = stored_profile
            self._apply_profile_data(profile_data)
        else:
            # First run or profile missing — use defaults and enable auto-save
            _active_profile_name = "last_used"
            self._current_profile = "last_used"
            self._cfg["_current_profile"] = "last_used"

    # ── Hotkey handling (Windows) ────────────────────────────────────────────

    def _register_hotkeys(self):
        MOD_CONTROL = 0x0002
        MOD_SHIFT   = 0x0004
        VK_M = 0x4D
        VK_H = 0x48
        try:
            ctypes.windll.user32.RegisterHotKey(
                None, self._hk_modular_id, MOD_CONTROL | MOD_SHIFT, VK_M
            )
            ctypes.windll.user32.RegisterHotKey(
                None, self._hk_hideall_id, MOD_CONTROL | MOD_SHIFT, VK_H
            )
        except Exception:
            pass

    def unregister_hotkeys(self):
        for hk_id in (self._hk_modular_id, self._hk_hideall_id):
            try:
                ctypes.windll.user32.UnregisterHotKey(None, hk_id)
            except Exception:
                pass

    def poll_hotkeys(self):
        """Called periodically by a QTimer. Reacts to global hotkeys."""
        msg = ctypes.wintypes.MSG()
        WM_HOTKEY = 0x0312
        if ctypes.windll.user32.PeekMessageW(
            ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, 1
        ):
            if msg.message == WM_HOTKEY:
                if msg.wParam == self._hk_modular_id:
                    self.toggle_all_visible()
                elif msg.wParam == self._hk_hideall_id:
                    self.hide_all()

    # ── Visibility ───────────────────────────────────────────────────────────

    def toggle_all_visible(self):
        if self._user_wants_visible:
            self.hide_all()
        else:
            self.show_all()

    def show_all(self):
        self._user_wants_visible = True
        for key, ov in self.components.items():
            if self._cfg.get(f"{key}_enabled", True):
                ov.show_overlay()

    def hide_all(self):
        self._user_wants_visible = False
        for ov in self.components.values():
            ov.hide_overlay()
        self.warning_ov.hide_warning()

    def show_settings_menu(self, global_pos: QPoint):
        """
        The "config menu" the user can open to toggle which components are active.
        Triggered by:
          - right-click on the manager tray (or on a specific component, see below)
          - the gear button (in the dedicated manager widget)
        """
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {qcolor_hex(BG_0)}; color: {qcolor_hex(TEXT_PRIMARY)};
                     border: 1px solid {qcolor_hex(BORDER_BRIGHT)}; padding: 6px; }}
            QMenu::item {{ padding: 6px 28px 6px 8px; }}
            QMenu::item:selected {{ background-color: {qcolor_hex(ACCENT_BLUE)}; }}
            QMenu::separator {{ height: 1px; background: {qcolor_hex(BORDER_BRIGHT)}; margin: 4px 8px; }}
            QMenu::indicator {{ width: 14px; height: 14px; }}
        """)

        title = menu.addAction("  COMPONENTI MODULARI")
        title.setEnabled(False)
        menu.addSeparator()

        # One checkbox-style action per component
        for key in COMPONENT_ORDER:
            label = COMPONENT_LABELS[key]
            enabled = bool(self._cfg.get(f"{key}_enabled", True))
            act = QWidgetAction(menu)
            checkbox = QCheckBox(f"  {label}")
            checkbox.setChecked(enabled)
            checkbox.setStyleSheet(f"""
                QCheckBox {{ color: {qcolor_hex(TEXT_PRIMARY)}; padding: 4px 8px; }}
                QCheckBox::indicator {{ width: 14px; height: 14px; }}
                QCheckBox::indicator:unchecked {{
                    border: 1px solid {qcolor_hex(BORDER_BRIGHT)};
                    background: {qcolor_hex(BG_1)};
                }}
                QCheckBox::indicator:checked {{
                    border: 1px solid {qcolor_hex(ACCENT_BLUE)};
                    background: {qcolor_hex(ACCENT_BLUE)};
                }}
            """)
            # Connect the toggle
            def make_toggle(k):
                def _on_toggle(state):
                    self._cfg[f"{k}_enabled"] = bool(state)
                    save_config(self._cfg)
                    ov = self.components[k]
                    if not state:
                        ov.hide()
                    else:
                        ov.show_overlay()
                return _on_toggle
            checkbox.toggled.connect(make_toggle(key))
            act.setDefaultWidget(checkbox)
            menu.addAction(act)

        menu.addSeparator()
        act_show = menu.addAction("Mostra tutti")
        act_hide = menu.addAction("Nascondi tutti")
        menu.addSeparator()
        act_reset = menu.addAction("Reset posizioni di tutti i componenti")
        menu.addSeparator()
        # ── Layout Profile section ──────────────────────────────────────
        prof_header = menu.addAction(f"  PROFILI LAYOUT  [{self._current_profile}]")
        prof_header.setEnabled(False)

        act_save = menu.addAction("💾 Salva layout come...")
        # Saved profile actions: click to load
        saved_names = get_profile_names()
        profile_actions: List[tuple] = []
        for pname in saved_names:
            label = f"✓ {pname}" if pname == self._current_profile else f"  {pname}"
            act = menu.addAction(label)
            profile_actions.append((act, pname))

        menu.addSeparator()
        act_delete = menu.addAction("✕ Elimina profilo...")
        act_reset_def = menu.addAction("↺ Ripristina layout predefinito")
        menu.addSeparator()

        act_audio_toggle = menu.addAction(
            "Disattiva audio" if self.audio_engine.enabled
            else "Attiva audio"
        )
        act_audio_test = menu.addAction("Test suono 'pit_now'")
        act_refresh = menu.addAction("Ricalcola strategia adesso")
        act_practice = menu.addAction(
            "Disattiva practice mode" if self._cfg.get("practice_mode", True)
            else "Attiva practice mode"
        )
        menu.addSeparator()
        # Community DB section
        import database as _db
        _user = _db.get_local_user()
        act_cloud_optin = None
        act_cloud_optout = None
        act_cloud_sync = None
        act_cloud_pull = None
        if _user.get("opt_in_global"):
            act_cloud_sync = menu.addAction(f"Sync community data ({_user.get('display_name', '?')})")
            act_cloud_pull = menu.addAction("Pull community data")
            act_cloud_optout = menu.addAction("Disattiva community DB")
        else:
            act_cloud_optin = menu.addAction("Attiva community DB (opt-in)")
        menu.addSeparator()
        act_open_web = menu.addAction("Apri UI web (browser)")
        act_quit = menu.addAction("Esci")

        chosen = menu.exec(global_pos)
        if chosen is act_show:
            self.show_all()
        elif chosen is act_hide:
            self.hide_all()
        elif chosen is act_reset:
            for ov in self.components.values():
                ov.reset_position()
        # ── Profile actions ──────────────────────────────────────────
        elif chosen is act_save:
            self._prompt_save_profile()
        elif chosen is act_delete:
            self._prompt_delete_profile()
        elif chosen is act_reset_def:
            self._reset_to_default_layout()
        else:
            loaded = False
            for act, pname in profile_actions:
                if chosen is act:
                    self.load_profile_by_name(pname)
                    loaded = True
                    break
            if not loaded:
                # ── Regular actions ──────────────────────────────────
                if chosen is act_audio_toggle:
                    new_state = not self.audio_engine.enabled
                    self.audio_engine.enabled = new_state
                    self._cfg["audio_enabled"] = new_state
                    save_config(self._cfg)
                elif chosen is act_audio_test:
                    self.audio_engine.clear_cooldowns()
                    self.audio_engine.play("pit_now", cooldown=False)
                elif chosen is act_refresh:
                    self.refresher.request_refresh()
                elif chosen is act_practice:
                    new_state = not self._cfg.get("practice_mode", True)
                    self._cfg["practice_mode"] = new_state
                    save_config(self._cfg)
                # Community DB actions
                elif act_cloud_optin is not None and chosen is act_cloud_optin:
                    import database as _db
                    user = _db.opt_in_to_community()
                    if user.get("user_id"):
                        self.refresher.request_refresh()
                elif act_cloud_optout is not None and chosen is act_cloud_optout:
                    import database as _db
                    _db.opt_out_of_community(delete_cloud_data=False)
                elif act_cloud_sync is not None and chosen is act_cloud_sync:
                    import database as _db
                    _db.push_pending_sessions()
                elif act_cloud_pull is not None and chosen is act_cloud_pull:
                    import database as _db
                    _db.pull_remote_sessions()
                elif chosen is act_open_web:
                    import webbrowser
                    webbrowser.open("http://127.0.0.1:8000/")
                elif chosen is act_quit:
                    QApplication.quit()

    # ── Auto-visibility (in_game_only) ───────────────────────────────────────

    def _apply_auto_visibility(self, frame: TelemetryFrame):
        if not self._cfg.get("in_game_only", False) or not self._user_wants_visible:
            return
        is_in_game = (
            not frame.in_pits
            and frame.lap_number > 0
            and frame.elapsed_time > 2.0
        )
        for key, ov in self.components.items():
            if not self._cfg.get(f"{key}_enabled", True):
                continue
            if is_in_game and not ov.isVisible():
                ov.show_overlay()
            elif not is_in_game and ov.isVisible():
                ov.hide_overlay()

    # ── Update from telemetry ────────────────────────────────────────────────

    def update_frame(self, frame: TelemetryFrame):
        self._apply_auto_visibility(frame)
        self._current_lap = frame.lap_number
        self._last_frame = frame

        # Track tyre age: reset on stint change, increment on lap change
        if frame.stint_number != self._last_stint:
            self._tyre_age_laps = 0
            self._last_stint = frame.stint_number
        elif frame.lap_number > self._current_lap:
            self._tyre_age_laps += 1

        # Delta
        delta = frame.delta_best
        self.delta_ov.update_value(delta)

        # Fuel
        fuel_laps = self._estimate_fuel_laps(frame)
        refuel = self._calculate_refuel(frame)
        self.fuel_ov.update_value(fuel_laps, refuel_l=refuel)

        # Cliff
        cliff_laps = self._estimate_cliff_laps(frame)
        self.cliff_ov.update_value(cliff_laps)

        # Weather
        self.weather_ov.update_value(frame)

        # Wear — compute tyre status prediction
        try:
            # Estimate historical cliff from our model
            hist_cliff = None
            if self._car and self._track:
                laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
                if len(laps) >= 5:
                    model = fit_degradation_model(laps)
                    if model.cliff_lap < 999:
                        hist_cliff = int(model.cliff_lap)
            tyre_status = estimate_remaining_life(
                current_wear=frame.tyre_wear,
                tyre_age_laps=self._tyre_age_laps,
                compound=frame.tyre_compounds[0] if frame.tyre_compounds else "Medium",
                track_temp=frame.track_temp,
                historical_cliff=hist_cliff,
            )
            self.wear_ov.update_value(frame, tyre_status=tyre_status)
        except Exception:
            self.wear_ov.update_value(frame)

        # Compound
        self.compound_ov.update_value(frame)

        # Sectors
        self.sectors_ov.update_value(frame)

        # Pit
        self._update_pit_display()

        # Qualifying overlay (continually update as laps come in)
        if self._session_type == "QUALIFYING":
            self._run_qualifying_analysis()

        # Practice overlay
        if self._session_type is None or self._session_type == "PRACTICE":
            self._update_practice_analysis()

        # Warning
        if fuel_laps < 2 and not frame.in_pits:
            self.warning_ov.show_warning("LOW FUEL", critical=True)
        elif self._pit_plan and self._current_lap in self._pit_plan:
            self.warning_ov.show_warning("BOX NOW", critical=True)
        else:
            self.warning_ov.hide_warning()

    def _update_pit_display(self):
        self.pit_ov.update_value(self._pit_plan, self._current_lap)

    # ── Strategy refresh (called on each lap) ────────────────────────────────

    def on_lap_completed(self, _lap_id: int):
        if self._session_type == "QUALIFYING":
            self._run_qualifying_analysis()
        else:
            self._refresh_strategy()

    def on_race_started(self, session_uuid: str, car: str, track: str):
        """Called when a RACE session is detected.
        Sets session info and triggers immediate strategy calculation."""
        print(f"[Manager] Race started @ {track} [{car}]")
        self._session_type = "RACE"
        self.set_session_info(car=car, track=track, total_laps=60)
        self._refresh_strategy()
        self.audio_engine.play("strategy_changed")

    def on_qualifying_started(self, session_uuid: str, car: str, track: str):
        """Called when a QUALIFYING session is detected.
        Sets session info and runs qualifying analysis."""
        print(f"[Manager] Qualifying started @ {track} [{car}]")
        self._session_type = "QUALIFYING"
        self.set_session_info(car=car, track=track, total_laps=60)
        self._qualy_data = None
        self._run_qualifying_analysis()
        self.audio_engine.play("strategy_changed")

    def _estimate_fuel_laps(self, frame: TelemetryFrame) -> float:
        fuel = frame.fuel
        if self._car and self._track:
            laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if laps:
                mean_cons, _ = fit_fuel_model(laps)
                if mean_cons > 0:
                    return fuel / mean_cons
        return fuel / 3.2

    def _calculate_refuel(self, frame: TelemetryFrame) -> Optional[float]:
        """Calculate how much fuel to add at next pit stop."""
        if not self._car or not self._track:
            return None
        try:
            laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if not laps:
                return None
            _, mean_cons = fit_fuel_model(laps)
            if mean_cons <= 0:
                return None

            # If we have a pit plan, refuel for the next stint
            if self._pit_plan:
                nxt = next((l for l in self._pit_plan if l >= self._current_lap), None)
                if nxt is not None:
                    # Next stint: from nxt to next pit or race end
                    remaining_laps = (self._total_race_laps or 60) - nxt
                    next_stint_laps = remaining_laps
                    # Check if there's another pit after this
                    remaining_pits = [l for l in self._pit_plan if l > nxt]
                    if remaining_pits:
                        next_stint_laps = remaining_pits[0] - nxt
                    stint_fuel = next_stint_laps * mean_cons
                    current = frame.fuel
                    if stint_fuel > current:
                        return round(stint_fuel - current, 1)
                    return None

            # In pits → refuel to full
            if frame.in_pits or frame.pit_state in [2, 3]:
                if frame.fuel_capacity > 0:
                    to_full = frame.fuel_capacity - frame.fuel
                    if to_full > 1:
                        return round(to_full, 1)

            return None
        except Exception:
            return None

    def _estimate_cliff_laps(self, frame: TelemetryFrame) -> int:
        if self._car and self._track:
            laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if len(laps) >= 5:
                model = fit_degradation_model(laps)
                if model.cliff_lap < 999:
                    return max(0, int(model.cliff_lap) - frame.lap_number)
        return 999

    def _refresh_strategy(self):
        if not self._car or not self._track:
            return
        laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
        if len(laps) < 5:
            return
        try:
            model = fit_degradation_model(laps)
            mean_cons, _ = fit_fuel_model(laps)
            pit_losses = database.get_pit_stops_loss_by_session(
                self._car, self._track, db_path=self.db_path
            )
            pit_loss = sum(pit_losses) / len(pit_losses) if pit_losses else 30.0
            strat = PitStrategist(
                fuel_capacity=100.0,
                fuel_consumption=mean_cons,
                pit_loss=pit_loss,
                model_fit=model,
            )
            remaining = max(1, self._total_race_laps - self._current_lap)
            result = strat.optimize(
                laps_remaining=remaining,
                current_tyre_age=1,
                current_fuel=100.0,
                max_stops=3,
            )
            if result["optimal"]:
                self._pit_plan = [self._current_lap + p - 1 for p in result["optimal"]["pit_laps"]]
        except Exception:
            pass

    def _run_qualifying_analysis(self):
        """Query qualifying laps from the current car/track and analyse them."""
        if not self._car or not self._track:
            return
        try:
            # Get all laps for this car/track (practice data helps)
            all_laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if len(all_laps) < 3:
                self._qualy_data = None
                self.qualy_ov.update_value(None)
                return
            _, mean_cons = fit_fuel_model(all_laps)
            model = fit_degradation_model(all_laps)
            analyst = QualifyingAnalyst(fuel_consumption_lap=mean_cons, model_fit=model)
            self._qualy_data = analyst.analyze(all_laps)
            self.qualy_ov.update_value(self._qualy_data)

            # Log suggestions
            for s in self._qualy_data.get("suggestions", []):
                print(f"  [Qualy] {s}")
        except Exception as e:
            print(f"  [Qualy] Error: {e}")
            self._qualy_data = None
            self.qualy_ov.update_value(None)

    def _update_practice_analysis(self):
        """Analyse practice data and show coverage gaps in the overlay."""
        if not self._car or not self._track:
            return
        try:
            all_laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            result = analyze_practice_data(all_laps)
            self.practice_ov.update_value(result)
        except Exception as e:
            print(f"  [Practice] Error: {e}")
            self.practice_ov.update_value(None)

    def set_session_info(self, car: str, track: str, total_laps: int = 40):
        self._car = car
        self._track = track
        self._total_race_laps = total_laps

    def set_pit_plan(self, pit_laps: List[int]):
        self._pit_plan = pit_laps

    # ── Audio + refresher integration ────────────────────────────────────────

    def _play_audio_cue(self, cue: str):
        """Slot for StrategyRefresher.audio_cue signal."""
        self.audio_engine.play(cue)

    def _on_plan_updated(self, plan: Dict[str, Any], reason: str):
        """Slot for StrategyRefresher.plan_updated signal."""
        pit_laps = plan.get("pit_laps", [])
        # Convert relative pit laps → absolute (current_lap + p - 1)
        if pit_laps:
            self._pit_plan = [self._current_lap + p - 1 for p in pit_laps]
        else:
            self._pit_plan = []
        # Trigger immediate UI refresh
        self._update_pit_display()
        # Low-fuel audio
        if self._last_frame is not None:
            fuel_laps = self._estimate_fuel_laps(self._last_frame)
            if fuel_laps < 2 and not self._last_frame.in_pits:
                self.audio_engine.play("low_fuel")
        # Pit-now audio if next pit is current lap
        if self._pit_plan and self._current_lap in self._pit_plan:
            self.audio_engine.play("pit_now")
            self.warning_ov.show_warning("BOX NOW", critical=True)
        elif self._pit_plan:
            next_pit = next((l for l in self._pit_plan if l >= self._current_lap), None)
            if next_pit is not None and (next_pit - self._current_lap) <= 2:
                self.audio_engine.play("pit_soon")


    # ── Settings dialog ────────────────────────────────────────────────

    def open_settings_dialog(self):
        """Open the full settings modal dialog."""
        dialog = SettingsDialog(self)
        dialog.exec()

    # ── Profile management ───────────────────────────────────────────────

    @property
    def current_profile_name(self) -> str:
        return self._current_profile

    def set_tray(self, tray_widget) -> None:
        """Store reference to the tray widget for position + tooltip updates."""
        self._tray_widget = tray_widget

    def _apply_profile_data(self, data: dict) -> None:
        """Apply layout data from a profile to the config and reposition all components."""
        if not data:
            return
        # Merge profile data into cfg
        for k, v in data.items():
            self._cfg[k] = v
        # Reposition and update visibility for all components
        for key, ov in self.components.items():
            x = self._cfg.get(f"{key}_x", DEFAULT_POSITIONS[key][0])
            y = self._cfg.get(f"{key}_y", DEFAULT_POSITIONS[key][1])
            ov.move(x, y)
            vis = self._cfg.get(f"{key}_vis", True)
            enabled = self._cfg.get(f"{key}_enabled", True)
            if vis and enabled:
                if not ov.isVisible():
                    ov.show()
            else:
                ov.hide()
        # Update tray position if stored
        if self._tray_widget is not None:
            tx = self._cfg.get("tray_x")
            ty = self._cfg.get("tray_y")
            if tx is not None and ty is not None:
                self._tray_widget.move(tx, ty)
        # Save merged config (triggers profile auto-save)
        save_config(self._cfg)

    def load_profile_by_name(self, name: str) -> None:
        """Load a named profile and apply it, setting it as the active profile."""
        global _active_profile_name
        data = load_profile(name)
        if not data:
            return
        _active_profile_name = name
        self._current_profile = name
        self._cfg["_current_profile"] = name
        self._apply_profile_data(data)
        self.profile_changed.emit(name)

    def save_current_profile(self, name: str) -> None:
        """Save current layout as a named profile and set it active."""
        global _active_profile_name
        _save_profile(name, self._cfg)
        _active_profile_name = name
        self._current_profile = name
        self._cfg["_current_profile"] = name
        save_config(self._cfg)  # also updates last_used
        self.profile_changed.emit(name)

    def delete_profile_by_name(self, name: str) -> bool:
        """Delete a profile. If it was the active profile, fall back to last_used."""
        if not delete_profile(name):
            return False
        if self._current_profile == name:
            global _active_profile_name
            # Fall back to last_used
            _active_profile_name = "last_used"
            self._current_profile = "last_used"
            self._cfg["_current_profile"] = "last_used"
            save_config(self._cfg)
            self.profile_changed.emit("last_used")
        return True

    def _reset_to_default_layout(self) -> None:
        """Reset all component positions, enabled states, and visibility to defaults."""
        global _active_profile_name
        for key, ov in self.components.items():
            ov.reset_position()
            self._cfg[f"{key}_enabled"] = True
            self._cfg[f"{key}_vis"] = True
            ov.show()
        self._cfg["in_game_only"] = DEFAULT_CONFIG.get("in_game_only", False)
        _active_profile_name = None
        self._current_profile = "default"
        self._cfg["_current_profile"] = "default"
        save_config(self._cfg)
        self.profile_changed.emit("default")

    def _prompt_save_profile(self) -> None:
        """Show input dialog to save current layout as a named profile."""
        initial = self._current_profile if self._current_profile not in ("default", "last_used") else ""
        name, ok = QInputDialog.getText(
            None, "Salva layout",
            "Nome del profilo:",
            text=initial,
        )
        if ok and name.strip():
            self.save_current_profile(name.strip())

    def _prompt_delete_profile(self) -> None:
        """Show selection dialog to choose and delete a profile."""
        names = get_profile_names()
        if not names:
            QMessageBox.information(None, "Elimina profilo", "Nessun profilo salvato da eliminare.")
            return
        name, ok = QInputDialog.getItem(
            None, "Elimina profilo",
            "Seleziona il profilo da eliminare:",
            names, 0, False,
        )
        if ok and name:
            reply = QMessageBox.question(
                None, "Conferma eliminazione",
                f"Eliminare definitivamente il profilo \"{name}\"?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                if self.delete_profile_by_name(name):
                    QMessageBox.information(None, "Eliminato", f"Profilo \"{name}\" eliminato.")
                else:
                    QMessageBox.warning(None, "Errore", f"Impossibile eliminare il profilo \"{name}\".")


# ══════════════════════════════════════════════════════════════════════════════
# SettingsDialog — modal with volume slider, component toggles, etc.
# ══════════════════════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """Modal dialog for overlay settings: volume, components, audio, etc."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._cfg = load_config()
        self.setWindowTitle("Impostazioni Overlay")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {qcolor_hex(BG_0)};
                color: {qcolor_hex(TEXT_PRIMARY)};
                border: 1px solid {qcolor_hex(BORDER_BRIGHT)};
                border-radius: 8px;
            }}
            QLabel {{
                color: {qcolor_hex(TEXT_PRIMARY)};
                font-family: 'Rajdhani', 'Inter', sans-serif;
            }}
            .section-label {{
                color: {qcolor_hex(TEXT_MUTED)};
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            QCheckBox {{
                color: {qcolor_hex(TEXT_PRIMARY)};
                font-family: 'JetBrains Mono';
                spacing: 8px;
                padding: 4px 0;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {qcolor_hex(BORDER_BRIGHT)};
                background: {qcolor_hex(BG_1)};
                border-radius: 3px;
            }}
            QCheckBox::indicator:checked {{
                background: {qcolor_hex(ACCENT_BLUE)};
                border-color: {qcolor_hex(ACCENT_BLUE)};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {qcolor_hex(BG_1)};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {qcolor_hex(ACCENT_BLUE)};
                width: 14px; height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {qcolor_hex(ACCENT_BLUE)};
                border-radius: 2px;
            }}
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {qcolor_hex(ACCENT_BLUE)}, stop:1 #0072cc);
                color: {qcolor_hex(TEXT_PRIMARY)};
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-family: 'Rajdhani', 'Inter', sans-serif;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #00b8ff, stop:1 #0088dd);
            }}
            QRadioButton {{
                color: {qcolor_hex(TEXT_PRIMARY)};
                font-family: 'Rajdhani', 'Inter', sans-serif;
                font-size: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # ── Title ───────────────────────────────────────────────────────
        title = QLabel("Impostazioni")
        title.setFont(QFont(FONT_TITLE, 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # ── Audio section ───────────────────────────────────────────────
        audio_label = QLabel("SUONI")
        audio_label.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; font-size: 10px; "
                                  "text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(audio_label)

        self._cb_audio = QCheckBox("Abilita suoni (cue audio)")
        self._cb_audio.setChecked(self._cfg.get("audio_enabled", True))
        self._cb_audio.toggled.connect(self._on_audio_toggle)
        layout.addWidget(self._cb_audio)

        vol_layout = QHBoxLayout()
        vol_layout.setContentsMargins(24, 0, 0, 0)
        vol_label = QLabel("Volume:")
        vol_label.setFont(QFont(FONT_VALUE, 10))
        vol_label.setFixedWidth(60)
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(int(self._cfg.get("audio_volume", 1.0) * 100))
        self._volume_slider.valueChanged.connect(self._on_volume_change)
        self._vol_value = QLabel(f"{self._volume_slider.value()}%")
        self._vol_value.setFont(QFont(FONT_VALUE, 10))
        self._vol_value.setFixedWidth(40)
        vol_layout.addWidget(vol_label)
        vol_layout.addWidget(self._volume_slider, 1)
        vol_layout.addWidget(self._vol_value)
        layout.addLayout(vol_layout)

        test_btn = QPushButton("Test suono")
        test_btn.clicked.connect(self._on_test_sound)
        layout.addWidget(test_btn)

        # ── Components section ──────────────────────────────────────────
        comp_label = QLabel("COMPONENTI VISIBILI")
        comp_label.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; font-size: 10px; "
                                 "text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(comp_label)

        self._comp_checkboxes = {}
        for key in COMPONENT_ORDER:
            cb = QCheckBox(COMPONENT_LABELS[key])
            cb.setChecked(self._cfg.get(f"{key}_enabled", True))
            cb.toggled.connect(lambda state, k=key: self._on_comp_toggle(k, state))
            self._comp_checkboxes[key] = cb
            layout.addWidget(cb)

        # ── Mode toggles ────────────────────────────────────────────────
        mode_label = QLabel("MODALITÀ")
        mode_label.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; font-size: 10px; "
                                 "text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(mode_label)

        self._cb_in_game = QCheckBox("Solo quando in gioco (auto-hide)")
        self._cb_in_game.setChecked(self._cfg.get("in_game_only", False))
        self._cb_in_game.toggled.connect(self._on_in_game_toggle)
        layout.addWidget(self._cb_in_game)

        self._cb_practice = QCheckBox("Practice mode (suggerisci stint)")
        self._cb_practice.setChecked(self._cfg.get("practice_mode", True))
        self._cb_practice.toggled.connect(self._on_practice_toggle)
        layout.addWidget(self._cb_practice)

        # ── Overlay mode ──────────────────────────────────────────────
        mode_label = QLabel("MODO OVERLAY")
        mode_label.setStyleSheet("color: #7d8590; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(mode_label)
        mode_layout = QHBoxLayout()
        self._rb_full = QRadioButton("Full (1 finestra)")
        self._rb_modular = QRadioButton("Modulare (finestre multiple)")
        full_mode = self._cfg.get("overlay_mode", "full") == "full"
        self._rb_full.setChecked(full_mode)
        self._rb_modular.setChecked(not full_mode)
        for rb in [self._rb_full, self._rb_modular]:
            rb.toggled.connect(self._on_mode_change)
        mode_layout.addWidget(self._rb_full)
        mode_layout.addWidget(self._rb_modular)
        layout.addLayout(mode_layout)
        mode_hint = QLabel("Il cambio modalità richiede il riavvio dell'overlay")
        mode_hint.setStyleSheet("color: #505664; font-size: 10px;")
        layout.addWidget(mode_hint)

        # ── Reset buttons ───────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        reset_pos = QPushButton("Reset Posizioni")
        reset_pos.clicked.connect(self._on_reset_positions)
        hide_all = QPushButton("Nascondi Tutti")
        hide_all.clicked.connect(self._on_hide_all)
        btn_layout.addWidget(reset_pos)
        btn_layout.addWidget(hide_all)
        layout.addLayout(btn_layout)

        # ── Close ───────────────────────────────────────────────────────
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        layout.addStretch()

    # ── Handlers ────────────────────────────────────────────────────────

    def _on_audio_toggle(self, state):
        self._manager.audio_engine.enabled = state
        self._cfg["audio_enabled"] = state
        save_config(self._cfg)

    def _on_volume_change(self, val):
        volume = val / 100.0
        self._manager.audio_engine.volume = volume
        self._cfg["audio_volume"] = volume
        self._vol_value.setText(f"{val}%")
        save_config(self._cfg)

    def _on_test_sound(self):
        self._manager.audio_engine.clear_cooldowns()
        self._manager.audio_engine.play("pit_now", cooldown=False)

    def _on_comp_toggle(self, key, state):
        self._cfg[f"{key}_enabled"] = state
        save_config(self._cfg)
        ov = self._manager.components.get(key)
        if ov:
            if state:
                ov.show_overlay()
            else:
                ov.hide()

    def _on_in_game_toggle(self, state):
        self._cfg["in_game_only"] = state
        save_config(self._cfg)

    def _on_practice_toggle(self, state):
        self._cfg["practice_mode"] = state
        save_config(self._cfg)

    def _on_mode_change(self):
        new_mode = "full" if self._rb_full.isChecked() else "modular"
        self._cfg["overlay_mode"] = new_mode
        save_config(self._cfg)

    def _on_reset_positions(self):
        for ov in self._manager.components.values():
            ov.reset_position()

    def _on_hide_all(self):
        self._manager.hide_all()


# ══════════════════════════════════════════════════════════════════════════════
# Manager tray widget (small gear button that opens the settings menu/dialog)
# ══════════════════════════════════════════════════════════════════════════════

class ManagerTray(QWidget):
    """A tiny always-on-top widget with a single gear button to open the settings macro-menu.
    Left-click → quick menu.  Right-click → drag.  Double-click → settings dialog.
    """
    menu_requested = Signal(QPoint)  # global position to open menu at
    settings_requested = Signal()    # open the SettingsDialog

    def __init__(self, manager: OverlayManager, cfg: dict):
        super().__init__()
        self._manager = manager
        self._cfg = cfg
        self._profile_name = "last_used"
        self.setToolTip(f"Overlay Manager [{self._profile_name}]")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(44, 44)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._btn = QLabel()
        self._btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = icon_pixmap(settings_icon(), size=22, color=qcolor_hex(ACCENT_BLUE))
        self._btn.setPixmap(pix)
        self._btn.setFixedSize(44, 44)
        layout.addWidget(self._btn)

        x = cfg.get("tray_x", 50)
        y = cfg.get("tray_y", 160)
        self.move(x, y)
        self.show()

    def set_profile_name(self, name: str) -> None:
        """Update the profile name shown in the tray tooltip."""
        self._profile_name = name
        self.setToolTip(f"Overlay Manager [{name}]")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.menu_requested.emit(event.globalPos())
        elif event.button() == Qt.MouseButton.RightButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseDoubleClickEvent(self, event):
        """Double-click opens the full settings dialog."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.settings_requested.emit()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        if hasattr(self, "_drag_pos") and self._drag_pos:
            pos = self.pos()
            self._cfg["tray_x"] = pos.x()
            self._cfg["tray_y"] = pos.y()
            save_config(self._cfg)
            self._drag_pos = None

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        # Shadow / depth effect
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect.adjusted(2, 2, 0, 0), 8, 8)

        # Background
        painter.setBrush(QBrush(BG_0))
        painter.setPen(QPen(BORDER_BRIGHT, 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        # Top accent bar (6px blue)
        painter.setBrush(QBrush(ACCENT_BLUE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, rect.width(), 6, 3, 3)


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_overlay(source: TelemetrySource, db_path: str = database.DEFAULT_DB_PATH):
    """
    Launch the modular overlay application (4 separate mini-windows + tray).
    Accepts any TelemetrySource — live or synthetic.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    manager = OverlayManager(db_path=db_path)
    cfg = load_config()
    tray = ManagerTray(manager, cfg)
    manager.set_tray(tray)
    tray.menu_requested.connect(manager.show_settings_menu)
    tray.settings_requested.connect(manager.open_settings_dialog)
    manager.profile_changed.connect(tray.set_profile_name)
    tray.set_profile_name(manager.current_profile_name)

    # Hotkey polling timer
    hk_timer = QTimer()
    hk_timer.timeout.connect(manager.poll_hotkeys)
    hk_timer.start(100)

    def cleanup():
        manager.refresher.stop()
        manager.unregister_hotkeys()
        worker.stop()
        thread.quit()
        thread.wait()

    app.aboutToQuit.connect(cleanup)

    # Worker thread
    worker = TelemetryWorker(source, db_path)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.start_source)
    worker.frame_ready.connect(manager.update_frame)
    worker.lap_completed.connect(manager.on_lap_completed)
    worker.race_started.connect(manager.on_race_started)
    worker.qualifying_started.connect(manager.on_qualifying_started)
    thread.start()

    # Start the adaptive strategy refresher (re-evaluates every 5s if
    # weather / fuel / lap changes)
    manager.refresher.start()

    return app.exec()


if __name__ == "__main__":
    from telemetry.source import SyntheticReplaySource

    source = SyntheticReplaySource(
        track_name="Le Mans",
        car_name="Ferrari 499P LMH",
        lap_time_base=225.0,
        fuel_capacity=110.0,
        initial_fuel=105.0,
        fuel_consumption=4.8,
        cliff_lap=18,
        anomaly_laps={5: 2.0, 12: 1.8},
        total_laps=40,
        tick_rate=0.5,
    )
    sys.exit(run_overlay(source))
