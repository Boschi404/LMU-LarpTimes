"""
LMU Pit Strategist — Overlay Live (Processo A)

Finestre separate frameless sempre-in-primo-piano PySide6 per metriche singole.
Layout tabulare, compatto, senza emoji. Drag-to-move per ogni finestra.

Hotkey globale: Ctrl+Shift+O — mostra/nasconde tutte le overlay.
"""

import sys
import ctypes
import ctypes.wintypes
import json
import os
import threading
import time
from typing import Optional, List

from PySide6.QtCore import (
    Qt, QPoint, QTimer, Signal, QObject, QThread
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QPen, QBrush
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu
)

import database
from telemetry.source import TelemetrySource, TelemetryFrame
from analysis.models import fit_degradation_model, fit_fuel_model
from analysis.strategist import PitStrategist

# ══════════════════════════════════════════════════════════════════════════════
# Design System (from web UI)
# ══════════════════════════════════════════════════════════════════════════════

BG_0 = QColor(10, 14, 24, 230)
BG_1 = QColor(17, 21, 31, 220)
BG_2 = QColor(22, 29, 46, 220)
ACCENT_GREEN = QColor(29, 209, 161)
ACCENT_BLUE = QColor(74, 158, 255)
ACCENT_RED = QColor(255, 107, 107)
ACCENT_AMBER = QColor(255, 169, 77)
TEXT_PRIMARY = QColor(240, 244, 255)
TEXT_MUTED = QColor(156, 163, 175)

def qcolor_hex(c: QColor) -> str:
    """Return CSS-style hex for QColor."""
    return '#%02x%02x%02x' % (c.red(), c.green(), c.blue())

# ══════════════════════════════════════════════════════════════════════════════
# Config persistence
# ══════════════════════════════════════════════════════════════════════════════

import paths
CONFIG_PATH = paths.data_path("overlay", "overlay_config.json")
DEFAULT_CONFIG = {
    "delta_x": 50, "delta_y": 50, "delta_vis": True,
    "fuel_x": 220, "fuel_y": 50, "fuel_vis": True,
    "cliff_x": 390, "cliff_y": 50, "cliff_vis": True,
    "pit_x": 560, "pit_y": 50, "pit_vis": True,
    "in_game_only": False,
}

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# ══════════════════════════════════════════════════════════════════════════════
# Telemetry Worker
# ══════════════════════════════════════════════════════════════════════════════

class TelemetryWorker(QObject):
    """Background thread polling telemetry."""
    frame_ready = Signal(object)  # TelemetryFrame
    lap_completed = Signal(int)   # lap_id

    def __init__(self, source: TelemetrySource, db_path: str):
        super().__init__()
        self.source = source
        self.db_path = db_path
        self._running = False
        self._detector = None

    def start_source(self):
        """Called in worker thread."""
        from telemetry.detector import LapBoundaryDetector
        self._detector = LapBoundaryDetector(db_path=self.db_path)
        self.source.start()
        self._running = True

        TICK = 0.05  # 20 Hz
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
        self.source.stop()

# ══════════════════════════════════════════════════════════════════════════════
# Mini-Window Base Class
# ══════════════════════════════════════════════════════════════════════════════

class MiniOverlay(QWidget):
    """
    Compact frameless always-on-top window for one metric.
    Draggable, configurable position and visibility.
    """

    def __init__(self, title: str, width: int = 140, height: int = 60, manager=None):
        super().__init__()
        self.title = title
        self._cfg_prefix = title.lower()
        self._drag_pos: Optional[QPoint] = None
        self._manager = manager
        self._user_wants_visible = True

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(width, height)

        cfg = load_config()
        self.move(cfg.get(f"{self._cfg_prefix}_x", 50), cfg.get(f"{self._cfg_prefix}_y", 50))
        if cfg.get(f"{self._cfg_prefix}_vis", True):
            self.show()

        self._build_ui()

    def _build_ui(self):
        raise NotImplementedError

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_close_app = menu.addAction("Chiudi App")
        act_close_overlay = menu.addAction("Chiudi Overlay")
        act_minimize = menu.addAction("Minimizza App")
        act_settings = menu.addAction("Impostazioni")

        action = menu.exec(event.globalPos())
        if action == act_close_app:
            QApplication.quit()
        elif action == act_close_overlay:
            if self._manager:
                self._manager.hide_all()
        elif action == act_minimize:
            if self._manager:
                self._manager.hide_all()
        elif action == act_settings:
            import webbrowser
            webbrowser.open("http://127.0.0.1:8000/")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.setBrush(QBrush(BG_0))
        painter.setPen(QPen(ACCENT_GREEN.darker(150), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        grad = QLinearGradient(0, 0, rect.width(), 0)
        grad.setColorAt(0.0, ACCENT_GREEN)
        grad.setColorAt(1.0, ACCENT_BLUE)
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, rect.width(), 2, 2, 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        if self._drag_pos:
            pos = self.pos()
            cfg = load_config()
            cfg[f"{self._cfg_prefix}_x"] = pos.x()
            cfg[f"{self._cfg_prefix}_y"] = pos.y()
            save_config(cfg)
            self._drag_pos = None

    def set_visible(self, visible: bool):
        if visible:
            self.show()
        else:
            self.hide()
        cfg = load_config()
        cfg[f"{self._cfg_prefix}_vis"] = visible
        save_config(cfg)

# ══════════════════════════════════════════════════════════════════════════════
# Individual Mini-Windows
# ══════════════════════════════════════════════════════════════════════════════

class DeltaOverlay(MiniOverlay):
    """Delta vs best lap."""
    def __init__(self, manager=None):
        super().__init__("delta", 140, 50, manager=manager)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        lbl_title = QLabel("Delta")
        lbl_title.setFont(QFont("Geist", 7))
        lbl_title.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

        self.lbl_value = QLabel("—")
        self.lbl_value.setFont(QFont("JetBrains Mono", 12, QFont.Weight.Bold))
        self.lbl_value.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        self.setLayout(layout)

    def update(self, delta: float):
        sign = "+" if delta > 0 else ""
        self.lbl_value.setText(f"{sign}{delta:.3f}s")
        color = qcolor_hex(ACCENT_RED) if delta > 0 else qcolor_hex(ACCENT_GREEN)
        self.lbl_value.setStyleSheet(f"color: {color}; font-weight: bold;")

class FuelOverlay(MiniOverlay):
    """Fuel laps remaining."""
    def __init__(self, manager=None):
        super().__init__("fuel", 140, 50, manager=manager)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        lbl_title = QLabel("Fuel")
        lbl_title.setFont(QFont("Geist", 7))
        lbl_title.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

        self.lbl_value = QLabel("—")
        self.lbl_value.setFont(QFont("JetBrains Mono", 12, QFont.Weight.Bold))
        self.lbl_value.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        self.setLayout(layout)

    def update(self, fuel_laps: float):
        self.lbl_value.setText(f"{fuel_laps:.1f}L")
        color = qcolor_hex(ACCENT_AMBER) if fuel_laps < 3 else qcolor_hex(TEXT_PRIMARY)
        self.lbl_value.setStyleSheet(f"color: {color}; font-weight: bold;")

class CliffOverlay(MiniOverlay):
    """Tyre cliff prediction."""
    def __init__(self, manager=None):
        super().__init__("cliff", 140, 50, manager=manager)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        lbl_title = QLabel("Cliff")
        lbl_title.setFont(QFont("Geist", 7))
        lbl_title.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

        self.lbl_value = QLabel("—")
        self.lbl_value.setFont(QFont("JetBrains Mono", 12, QFont.Weight.Bold))
        self.lbl_value.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        self.setLayout(layout)

    def update(self, cliff_laps: int):
        text = f"{cliff_laps}L" if cliff_laps < 999 else "ND"
        self.lbl_value.setText(text)
        color = qcolor_hex(ACCENT_AMBER) if cliff_laps < 5 else qcolor_hex(TEXT_PRIMARY)
        self.lbl_value.setStyleSheet(f"color: {color}; font-weight: bold;")

class PitOverlay(MiniOverlay):
    """Next pit info."""
    def __init__(self, manager=None):
        super().__init__("pit", 160, 50, manager=manager)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        lbl_title = QLabel("Pit")
        lbl_title.setFont(QFont("Geist", 7))
        lbl_title.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

        self.lbl_value = QLabel("—")
        self.lbl_value.setFont(QFont("JetBrains Mono", 11, QFont.Weight.Bold))
        self.lbl_value.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        self.setLayout(layout)

    def update(self, pit_info: str, is_critical: bool = False):
        self.lbl_value.setText(pit_info)
        color = qcolor_hex(ACCENT_RED) if is_critical else qcolor_hex(TEXT_PRIMARY)
        self.lbl_value.setStyleSheet(f"color: {color}; font-weight: bold;")

# ══════════════════════════════════════════════════════════════════════════════
# Warning Overlay (popup-style)
# ══════════════════════════════════════════════════════════════════════════════

class WarningOverlay(MiniOverlay):
    """Large warning message."""
    def __init__(self, manager=None):
        super().__init__("warning", 200, 70, manager=manager)
        self.hide()  # Hidden by default

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.lbl_warning = QLabel("—")
        self.lbl_warning.setFont(QFont("Geist", 9, QFont.Weight.Bold))
        self.lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)};")
        self.lbl_warning.setWordWrap(True)

        layout.addWidget(self.lbl_warning)
        self.setLayout(layout)

    def show_warning(self, message: str):
        self.lbl_warning.setText(message)
        self.show()

    def hide_warning(self):
        self.hide()

# ══════════════════════════════════════════════════════════════════════════════
# Overlay Manager
# ══════════════════════════════════════════════════════════════════════════════

class OverlayManager(QObject):
    """Manages all mini-overlays and telemetry updates."""

    def __init__(self, db_path: str = database.DEFAULT_DB_PATH):
        super().__init__()
        self.db_path = db_path

        # State
        self._car: Optional[str] = None
        self._track: Optional[str] = None
        self._pit_plan: Optional[List[int]] = None
        self._current_lap: int = 1
        self._total_race_laps: int = 0

        # Visibility state
        self._user_wants_visible = True

        # Create mini-windows
        self.delta_ov = DeltaOverlay(manager=self)
        self.fuel_ov = FuelOverlay(manager=self)
        self.cliff_ov = CliffOverlay(manager=self)
        self.pit_ov = PitOverlay(manager=self)
        self.warning_ov = WarningOverlay(manager=self)

        # Hotkeys
        self._setup_hotkeys()

    def hide_all(self):
        self._user_wants_visible = False
        for ov in (self.delta_ov, self.fuel_ov, self.cliff_ov, self.pit_ov):
            ov.hide()
            cfg = load_config()
            cfg[f"{ov._cfg_prefix}_vis"] = False
            save_config(cfg)
        self.warning_ov.hide()

    def show_all(self):
        self._user_wants_visible = True
        cfg = load_config()
        in_game_only = cfg.get("in_game_only", False)
        if not in_game_only:
            for ov in (self.delta_ov, self.fuel_ov, self.cliff_ov, self.pit_ov):
                ov.show()
                cfg[f"{ov._cfg_prefix}_vis"] = True
                save_config(cfg)

    def _apply_auto_visibility(self, frame: TelemetryFrame):
        cfg = load_config()
        in_game_only = cfg.get("in_game_only", False)
        if not in_game_only or not self._user_wants_visible:
            return

        is_in_game = not frame.in_pits and frame.lap_number > 0 and frame.elapsed_time > 2.0
        if is_in_game and not self.delta_ov.isVisible():
            for ov in (self.delta_ov, self.fuel_ov, self.cliff_ov, self.pit_ov):
                ov.show()
                cfg[f"{ov._cfg_prefix}_vis"] = True
                save_config(cfg)
        elif not is_in_game and self.delta_ov.isVisible():
            for ov in (self.delta_ov, self.fuel_ov, self.cliff_ov, self.pit_ov):
                ov.hide()
                cfg[f"{ov._cfg_prefix}_vis"] = False
                save_config(cfg)

    def _setup_hotkeys(self):
        self._hotkey_toggle_id = 1
        self._hotkey_ctrli_id = 2
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        VK_O = 0x4F
        VK_I = 0x49
        try:
            ctypes.windll.user32.RegisterHotKey(None, self._hotkey_toggle_id, MOD_CONTROL | MOD_SHIFT, VK_O)
            ctypes.windll.user32.RegisterHotKey(None, self._hotkey_ctrli_id, MOD_CONTROL, VK_I)
            self._hotkey_timer = QTimer()
            self._hotkey_timer.timeout.connect(self._check_hotkeys)
            self._hotkey_timer.start(100)
        except Exception:
            pass

    def _check_hotkeys(self):
        msg = ctypes.wintypes.MSG()
        WM_HOTKEY = 0x0312
        if ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, 1):
            if msg.message == WM_HOTKEY:
                if msg.wParam == self._hotkey_toggle_id:
                    self._toggle_all_visible()
                elif msg.wParam == self._hotkey_ctrli_id:
                    self._toggle_all_visible()

    def _toggle_all_visible(self):
        if self._user_wants_visible:
            self.hide_all()
        else:
            self.show_all()

    def update_frame(self, frame: TelemetryFrame):
        """Update all overlays from telemetry frame."""
        self._current_lap = frame.lap_number

        # Apply in-game only visibility rule
        self._apply_auto_visibility(frame)

        # Delta
        delta = frame.delta_best
        self.delta_ov.update(delta)

        # Fuel
        fuel_laps = self._estimate_fuel_laps(frame)
        self.fuel_ov.update(fuel_laps)

        # Cliff
        cliff_laps = self._estimate_cliff_laps(frame)
        self.cliff_ov.update(cliff_laps)

        # Pit
        self._update_pit_display()

        # Warning
        if fuel_laps < 2 and not frame.in_pits:
            self.warning_ov.show_warning("LOW FUEL")
        elif self._pit_plan and self._current_lap in self._pit_plan:
            self.warning_ov.show_warning("BOX NOW")
        else:
            self.warning_ov.hide_warning()

    def _update_pit_display(self):
        if self._pit_plan:
            next_pit = next((l for l in self._pit_plan if l >= self._current_lap), None)
            if next_pit is not None:
                laps_to_pit = next_pit - self._current_lap
                if laps_to_pit == 0:
                    self.pit_ov.update("BOX", is_critical=True)
                else:
                    self.pit_ov.update(f"L{next_pit} ({laps_to_pit}L)", is_critical=False)
            else:
                self.pit_ov.update("None", is_critical=False)
        else:
            self.pit_ov.update("—", is_critical=False)

    def _estimate_fuel_laps(self, frame: TelemetryFrame) -> float:
        fuel = frame.fuel
        if self._car and self._track:
            clean_laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if clean_laps:
                mean_cons, _ = fit_fuel_model(clean_laps)
                if mean_cons > 0:
                    return fuel / mean_cons
        return fuel / 3.2

    def _estimate_cliff_laps(self, frame: TelemetryFrame) -> int:
        if self._car and self._track:
            laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if len(laps) >= 5:
                model = fit_degradation_model(laps)
                if model.cliff_lap < 999:
                    current_age = frame.lap_number
                    return max(0, int(model.cliff_lap) - current_age)
        return 999

    def on_lap_completed(self, _lap_id: int):
        self._refresh_strategy()

    def _refresh_strategy(self):
        if not self._car or not self._track:
            return
        laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
        if len(laps) < 5:
            return
        try:
            model = fit_degradation_model(laps)
            mean_cons, _ = fit_fuel_model(laps)
            pit_losses = database.get_pit_stops_loss_by_session(self._car, self._track, db_path=self.db_path)
            pit_loss = sum(pit_losses) / len(pit_losses) if pit_losses else 30.0

            strat = PitStrategist(
                fuel_capacity=100.0,
                fuel_consumption=mean_cons,
                pit_loss=pit_loss,
                model_fit=model
            )
            remaining = max(1, self._total_race_laps - self._current_lap)
            result = strat.optimize(laps_remaining=remaining, current_tyre_age=1, current_fuel=100.0, max_stops=3)
            if result["optimal"]:
                self._pit_plan = [self._current_lap + p - 1 for p in result["optimal"]["pit_laps"]]
        except Exception:
            pass

    def set_session_info(self, car: str, track: str, total_laps: int = 40):
        self._car = car
        self._track = track
        self._total_race_laps = total_laps

    def set_pit_plan(self, pit_laps: List[int]):
        self._pit_plan = pit_laps

# ══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def run_overlay(source: TelemetrySource, db_path: str = database.DEFAULT_DB_PATH):
    """Launch overlay application with modular mini-windows."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    manager = OverlayManager(db_path=db_path)

    def cleanup():
        try:
            ctypes.windll.user32.UnregisterHotKey(None, manager._hotkey_toggle_id)
            ctypes.windll.user32.UnregisterHotKey(None, manager._hotkey_ctrli_id)
        except Exception:
            pass
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

    thread.start()

    ret = app.exec()

    return ret

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
        tick_rate=0.5
    )
    sys.exit(run_overlay(source))
