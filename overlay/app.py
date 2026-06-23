"""
LMU Pit Strategist — Overlay Live (Processo A)

Finestra trasparente always-on-top PySide6 che mostra dati strategici
mentre si guida. Richiede LMU in modalità finestra o finestra senza bordi.

Hotkey globale: Ctrl+Shift+O — mostra/nasconde l'overlay.
Drag: tieni premuto il mouse sull'overlay per spostarlo.
"""

import sys
import signal
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
    QFont, QColor, QPainter, QLinearGradient, QPen, QBrush, QFontDatabase
)

# Color & font tokens aligned with web UI design
# CSS equivalents: --bg-0, --bg-1, --bg-2, --accent-green, --accent-blue, --accent-red, --text-primary, --text-muted
BG_0 = QColor(10, 14, 24, 230)        # --bg-0
BG_1 = QColor(17, 21, 31, 220)        # --bg-1
BG_2 = QColor(22, 29, 46, 220)        # --bg-2
ACCENT_GREEN = QColor(29, 209, 161)
ACCENT_BLUE = QColor(74, 158, 255)
ACCENT_RED = QColor(255, 107, 107)
ACCENT_AMBER = QColor(255, 169, 77)
TEXT_PRIMARY = QColor(240, 244, 255)
TEXT_MUTED = QColor(156, 163, 175)

def qcolor_hex(c: QColor) -> str:
    """Return CSS-style hex for QColor (ignores alpha for simplicity)."""
    return '#%02x%02x%02x' % (c.red(), c.green(), c.blue())
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QMenu
)

import database
from telemetry.source import TelemetrySource, TelemetryFrame
from analysis.models import fit_degradation_model, fit_fuel_model
from analysis.strategist import PitStrategist


# ──────────────────────────────────────────────────────────────────────────────
# Config persistence
# ──────────────────────────────────────────────────────────────────────────────

import paths
CONFIG_PATH = paths.data_path("overlay", "overlay_config.json")
DEFAULT_CONFIG = {"x": 50, "y": 50, "visible": True, "in_game_only": False}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Telemetry worker thread
# ──────────────────────────────────────────────────────────────────────────────

class TelemetryWorker(QObject):
    """Runs TelemetrySource polling in a background thread and emits frame signals."""
    frame_ready = Signal(object)       # TelemetryFrame
    lap_completed = Signal(int)        # lap_id in DB

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

        TICK = 0.05  # 20 Hz UI poll
        while self._running:
            frame = self.source.get_next_frame()
            if frame is not None:
                # Record to DB
                lap_id = self._detector.process_frame(frame)
                if lap_id is not None:
                    self.lap_completed.emit(lap_id)
                self.frame_ready.emit(frame)
            time.sleep(TICK)

    def stop(self):
        self._running = False
        self.source.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Overlay widget
# ──────────────────────────────────────────────────────────────────────────────

class OverlayWidget(QWidget):
    """
    Transparent frameless always-on-top overlay.
    Styled with a semi-transparent dark background and vibrant accent colours.
    """

    def __init__(self, db_path: str = database.DEFAULT_DB_PATH):
        super().__init__()
        self.db_path = db_path
        self._cfg = load_config()
        self._drag_pos: Optional[QPoint] = None

        # Strategy state
        self._car: Optional[str] = None
        self._track: Optional[str] = None
        self._pit_plan: Optional[List[int]] = None   # absolute lap numbers to pit
        self._total_race_laps: int = 0
        self._current_lap: int = 1

        # Visibility state
        self._user_wants_visible = True

        self._setup_window()
        self._build_ui()
        self._setup_hotkeys()

    # ── Window setup ──────────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_close_app = menu.addAction("Chiudi App")
        act_close_overlay = menu.addAction("Chiudi Overlay")
        act_minimize = menu.addAction("Minimizza App")
        act_settings = menu.addAction("Impostazioni")

        action = menu.exec(event.globalPos())
        if action == act_close_app:
            QApplication.quit()
        elif action == act_close_overlay or action == act_minimize:
            self._user_wants_visible = False
            self.hide()
            self._cfg["visible"] = False
            save_config(self._cfg)
        elif action == act_settings:
            import webbrowser
            webbrowser.open("http://127.0.0.1:8000/")

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumSize(320, 180)
        self.move(self._cfg.get("x", 50), self._cfg.get("y", 50))
        if self._cfg.get("visible", True):
            self.show()

    # ── UI layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(6)

        # Title row
        title_row = QHBoxLayout()
        lbl_title = QLabel("🏁 LMU Pit Strategist")
        # Title font (use Geist if available, fallback to system)
        lbl_title.setFont(QFont("Geist", 10, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {qcolor_hex(ACCENT_GREEN)}; letter-spacing: 1px;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        outer.addLayout(title_row)

        # Separator line (drawn in paintEvent)
        outer.addSpacing(2)

        def _row(label_text: str, default: str = "—") -> tuple:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Geist", 9))
            lbl.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            lbl.setMinimumWidth(140)
            val = QLabel(default)
            val.setFont(QFont("JetBrains Mono", 11, QFont.Weight.Bold))
            val.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            return row, val

        row1, self._lbl_delta       = _row("Delta vs miglior giro:")
        row2, self._lbl_fuel_laps   = _row("Giri carburante rimasti:")
        row3, self._lbl_cliff       = _row("Giri al cliff gomma:")
        row4, self._lbl_pit_info    = _row("Box suggerito:")
        row5, self._lbl_warning     = _row("")   # warning banner

        for r in (row1, row2, row3, row4, row5):
            outer.addLayout(r)

        # Warning label styling override
        self._lbl_warning.setStyleSheet(
            f"color: {qcolor_hex(ACCENT_AMBER)}; font-size: 10pt; font-weight: bold;"
        )
        self._lbl_warning.setVisible(False)

        self.setLayout(outer)

    # ── Background painting ───────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded semi-transparent background
        rect = self.rect()
        # Background using web UI token BG_0 with slight opacity
        painter.setBrush(QBrush(BG_0))
        painter.setPen(QPen(ACCENT_GREEN.darker(150), 1.2))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)

        # Top accent gradient matching web accents
        grad = QLinearGradient(0, 0, rect.width(), 0)
        grad.setColorAt(0.0, ACCENT_GREEN)
        grad.setColorAt(1.0, ACCENT_BLUE)
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, rect.width(), 3, 2, 2)

    # ── Drag to move ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        if self._drag_pos:
            pos = self.pos()
            self._cfg["x"] = pos.x()
            self._cfg["y"] = pos.y()
            save_config(self._cfg)
            self._drag_pos = None

    # ── Hotkey (Windows) ──────────────────────────────────────────────────────

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
            self._hotkey_timer = QTimer(self)
            self._hotkey_timer.timeout.connect(self._check_hotkeys)
            self._hotkey_timer.start(100)
        except Exception:
            pass

    def _check_hotkeys(self):
        msg = ctypes.wintypes.MSG()
        WM_HOTKEY = 0x0312
        if ctypes.windll.user32.PeekMessageW(
            ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, 1
        ):
            if msg.message == WM_HOTKEY:
                if msg.wParam == self._hotkey_toggle_id or msg.wParam == self._hotkey_ctrli_id:
                    self._toggle_visibility()

    def _toggle_visibility(self):
        if self._user_wants_visible:
            self._user_wants_visible = False
            self.hide()
            self._cfg["visible"] = False
        else:
            self._user_wants_visible = True
            cfg = load_config()
            in_game_only = cfg.get("in_game_only", False)
            if not in_game_only:
                self.show()
                self._cfg["visible"] = True
        save_config(self._cfg)

    def _apply_auto_visibility(self, frame: TelemetryFrame):
        cfg = load_config()
        in_game_only = cfg.get("in_game_only", False)
        if not in_game_only or not self._user_wants_visible:
            return

        is_in_game = not frame.in_pits and frame.lap_number > 0 and frame.elapsed_time > 2.0
        if is_in_game and not self.isVisible():
            self.show()
            self._cfg["visible"] = True
            save_config(self._cfg)
        elif not is_in_game and self.isVisible():
            self.hide()
            self._cfg["visible"] = False
            save_config(self._cfg)

    def closeEvent(self, _event):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_toggle_id)
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_ctrli_id)
        except Exception:
            pass

    def update_frame(self, frame: TelemetryFrame):
        """Called every tick from TelemetryWorker.frame_ready signal."""
        self._apply_auto_visibility(frame)
        self._current_lap = frame.lap_number

        # ── Delta best ──────────────────────────────────────────────────
        delta = frame.delta_best
        sign = "+" if delta > 0 else ""
        delta_str = f"{sign}{delta:.3f} s"
        color = qcolor_hex(ACCENT_RED) if delta > 0 else qcolor_hex(ACCENT_GREEN)
        self._lbl_delta.setText(delta_str)
        self._lbl_delta.setStyleSheet(f"color: {color}; font-weight: bold;")

        # ── Fuel laps remaining ─────────────────────────────────────────
        fuel_laps = self._estimate_fuel_laps(frame)
        self._lbl_fuel_laps.setText(f"{fuel_laps:.1f} giri")
        fuel_color = qcolor_hex(ACCENT_AMBER) if fuel_laps < 3 else qcolor_hex(TEXT_PRIMARY)
        self._lbl_fuel_laps.setStyleSheet(f"color: {fuel_color}; font-weight: bold;")

        # ── Giri al cliff ───────────────────────────────────────────────
        cliff_laps = self._estimate_cliff_laps(frame)
        self._lbl_cliff.setText(f"{cliff_laps} giri" if cliff_laps < 999 else "N/D")
        cliff_color = qcolor_hex(ACCENT_AMBER) if cliff_laps < 5 else qcolor_hex(TEXT_PRIMARY)
        self._lbl_cliff.setStyleSheet(f"color: {cliff_color}; font-weight: bold;")

        # ── Pit countdown ───────────────────────────────────────────────
        if self._pit_plan:
            next_pit = next((l for l in self._pit_plan if l >= self._current_lap), None)
            if next_pit is not None:
                laps_to_pit = next_pit - self._current_lap
                if laps_to_pit == 0:
                    self._lbl_pit_info.setText("⚠️ BOX QUESTO GIRO!")
                    self._lbl_pit_info.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; font-weight: bold;")
                else:
                    self._lbl_pit_info.setText(f"Giro {next_pit}  (fra {laps_to_pit})")
                    self._lbl_pit_info.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)}; font-weight: bold;")
            else:
                self._lbl_pit_info.setText("Nessuna sosta prevista")
                self._lbl_pit_info.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
        else:
            self._lbl_pit_info.setText("Calcola strategia nell'UI")
            self._lbl_pit_info.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

        # ── Warning banner ──────────────────────────────────────────────
        # Show warning if we're burning fuel faster than expected
        if fuel_laps < 2 and not frame.in_pits:
            self._lbl_warning.setText("⚠️ CARBURANTE QUASI ESAURITO!")
            self._lbl_warning.setVisible(True)
        elif self._pit_plan and self._current_lap in self._pit_plan:
            self._lbl_warning.setText("🔴 È ORA DI ENTRARE AI BOX!")
            self._lbl_warning.setVisible(True)
        else:
            self._lbl_warning.setVisible(False)

    def on_lap_completed(self, _lap_id: int):
        """Recalculate strategy after a new lap is saved."""
        self._refresh_strategy()

    def _estimate_fuel_laps(self, frame: TelemetryFrame) -> float:
        """Estimate laps remaining based on current fuel and historical consumption."""
        fuel = frame.fuel
        if self._car and self._track:
            clean_laps = database.get_laps_for_analysis(
                self._car, self._track, db_path=self.db_path
            )
            if clean_laps:
                mean_cons, _ = fit_fuel_model(clean_laps)
                if mean_cons > 0:
                    return fuel / mean_cons
        # Fallback: assume 3.2 L/lap
        return fuel / 3.2

    def _estimate_cliff_laps(self, frame: TelemetryFrame) -> int:
        """Estimate laps remaining before tyre degradation cliff."""
        if self._car and self._track:
            laps = database.get_laps_for_analysis(
                self._car, self._track, db_path=self.db_path
            )
            if len(laps) >= 5:
                from telemetry.detector import LapBoundaryDetector
                # rough tyre age from stint info
                model = fit_degradation_model(laps)
                if model.cliff_lap < 999:
                    # Estimate current tyre age from last_lap in DB (use lap_number in session)
                    current_age = frame.lap_number  # Approximation
                    laps_to_cliff = max(0, int(model.cliff_lap) - current_age)
                    return laps_to_cliff
        return 999

    def _refresh_strategy(self):
        """Re-fetch pit plan from DB for current car/track."""
        if not self._car or not self._track:
            return
        laps = database.get_laps_for_analysis(
            self._car, self._track, db_path=self.db_path
        )
        if len(laps) < 5:
            return
        try:
            model = fit_degradation_model(laps)
            mean_cons, _ = fit_fuel_model(laps)
            pit_losses = database.get_pit_stops_loss_by_session(
                self._car, self._track, db_path=self.db_path
            )
            pit_loss = sum(pit_losses) / len(pit_losses) if pit_losses else 30.0

            # Dummy race config: use stored value or default 40 laps
            strat = PitStrategist(
                fuel_capacity=100.0,
                fuel_consumption=mean_cons,
                pit_loss=pit_loss,
                model_fit=model
            )
            remaining = max(1, self._total_race_laps - self._current_lap)
            result = strat.optimize(
                laps_remaining=remaining,
                current_tyre_age=1,
                current_fuel=100.0,
                max_stops=3
            )
            if result["optimal"]:
                # Convert relative pit laps to absolute
                self._pit_plan = [
                    self._current_lap + p - 1
                    for p in result["optimal"]["pit_laps"]
                ]
        except Exception:
            pass

    def set_session_info(self, car: str, track: str, total_laps: int = 40):
        self._car = car
        self._track = track
        self._total_race_laps = total_laps

    def set_pit_plan(self, pit_laps: List[int]):
        self._pit_plan = pit_laps


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_overlay(source: TelemetrySource, db_path: str = database.DEFAULT_DB_PATH):
    """
    Launch the overlay application.
    Accepts any TelemetrySource — live or synthetic.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    overlay = OverlayWidget(db_path=db_path)

    def cleanup():
        try:
            ctypes.windll.user32.UnregisterHotKey(None, overlay._hotkey_toggle_id)
            ctypes.windll.user32.UnregisterHotKey(None, overlay._hotkey_ctrli_id)
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
    worker.frame_ready.connect(overlay.update_frame)
    worker.lap_completed.connect(overlay.on_lap_completed)

    thread.start()

    # Handle Ctrl+C cleanly on Windows and POSIX
    def handle_sigint(signum, frame):
        worker.stop()
        thread.quit()
        thread.wait()
        app.quit()

    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        ret = app.exec()
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        worker.stop()
        thread.quit()
        thread.wait()

    return ret


if __name__ == "__main__":
    # Standalone demo using SyntheticReplaySource
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
