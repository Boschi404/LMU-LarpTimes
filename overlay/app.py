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

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSizePolicy, QMenu
)

import database
from telemetry.source import TelemetrySource, TelemetryFrame
from analysis.models import fit_degradation_model, fit_fuel_model
from analysis.strategist import PitStrategist

# ──────────────────────────────────────────────────────────────────────────────
# Color & Font Tokens (aligned with app_new design system)

BG_0 = QColor(10, 14, 24, 230)
BG_1 = QColor(17, 21, 31, 220)
BG_2 = QColor(22, 29, 46, 220)
BORDER_DIM = QColor(28, 33, 40, 255)
BORDER_BRIGHT = QColor(45, 51, 59, 255)

ACCENT_GREEN = QColor(29, 209, 161)
ACCENT_BLUE = QColor(74, 158, 255)
ACCENT_RED = QColor(255, 107, 107)
ACCENT_AMBER = QColor(255, 169, 77)

TEXT_PRIMARY = QColor(240, 244, 255)
TEXT_SECONDARY = QColor(125, 133, 144)
TEXT_MUTED = QColor(156, 163, 175)

FONT_TITLE = "Geist"
FONT_VALUE = "JetBrains Mono"

def qcolor_hex(c: QColor) -> str:
    return '#%02x%02x%02x' % (c.red(), c.green(), c.blue())

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
                print(f"[Worker] Frame lap={frame.lap_number}, fuel={frame.fuel:.1f}, in_pits={frame.in_pits}")
                lap_id = self._detector.process_frame(frame)
                if lap_id is not None:
                    print(f"[Worker] Lap completed, id={lap_id}")
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
    Styled with the LMU LarpTimes dark glassmorphism aesthetic.
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
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {qcolor_hex(BG_PANEL)}; color: {qcolor_hex(TEXT_PRIMARY)}; border: 1px solid {qcolor_hex(BORDER_BRIGHT)}; }}
            QMenu::item:selected {{ background-color: {qcolor_hex(ACCENT_BLUE)}; }}
        """)
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
        self.setMinimumSize(340, 220)
        self.move(self._cfg.get("x", 50), self._cfg.get("y", 50))
        if self._cfg.get("visible", True):
            self.show()

    # ── UI layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        # ── Header ──────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(8)

        self._lbl_brand = QLabel("LMU  LarpTimes")
        self._lbl_brand.setFont(QFont(FONT_TITLE, 8, QFont.Weight.Bold))
        self._lbl_brand.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)}; letter-spacing: 1px;")
        
        self._lbl_track_car = QLabel("—")
        self._lbl_track_car.setFont(QFont(FONT_TITLE, 8, QFont.Weight.Bold))
        self._lbl_track_car.setStyleSheet(f"color: {qcolor_hex(ACCENT_BLUE)}; letter-spacing: 1px;")
        self._lbl_track_car.setAlignment(Qt.AlignmentFlag.AlignRight)

        header_layout.addWidget(self._lbl_brand)
        header_layout.addStretch()
        header_layout.addWidget(self._lbl_track_car)
        outer.addLayout(header_layout)

        # ── Main Data Grid 3x3 ──────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 4, 0, 4)

        def cell(label_text, default="—", font_size=10):
            wrap = QVBoxLayout()
            wrap.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setFont(QFont(FONT_TITLE, 7, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; letter-spacing: 1px;")
            val = QLabel(default)
            val.setFont(QFont(FONT_VALUE, font_size, QFont.Weight.Bold))
            val.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")
            wrap.addWidget(lbl)
            wrap.addWidget(val)
            return wrap, val

        c1, self._lbl_delta    = cell("DELTA", "+0.000", 11)
        c2, self._lbl_lap_time  = cell("GIRO", "—", 11)
        c3, self._lbl_sector    = cell("SETTORI", "—", 10)
        c4, self._lbl_fuel      = cell("CARBURANTE", "— L", 11)
        c5, self._lbl_fuel_laps = cell("GIRI CARB.", "—", 10)
        c6, self._lbl_wear      = cell("USURA FL", "—%", 10)
        c7, self._lbl_cliff     = cell("CLIFF", "—", 10)
        c8, self._lbl_compound  = cell("MESCOLA", "—", 10)
        c9, self._lbl_pit       = cell("BOX", "—", 11)

        # Righe 0 e 1 (Dati giro e risorse)
        grid.addLayout(c1, 0, 0)
        grid.addLayout(c2, 0, 1)
        grid.addLayout(c3, 0, 2)
        grid.addLayout(c4, 1, 0)
        grid.addLayout(c5, 1, 1)
        grid.addLayout(c6, 1, 2)
        
        # Righe 2 e 3 (Pianificazione e condizioni)
        grid.addLayout(c7, 2, 0)
        grid.addLayout(c8, 2, 1)
        grid.addLayout(c9, 2, 2)
        
        outer.addLayout(grid)

        # ── Bottom Grid (Meteo) ─────────────────────────────────────────
        grid2 = QGridLayout()
        grid2.setSpacing(12)
        grid2.setContentsMargins(0, 4, 0, 0)
        c10, self._lbl_weather = cell("METEO", "—", 10)
        c11, self._lbl_track_temp = cell("PISTA", "—", 10)
        c12, self._lbl_ambient = cell("ARIA", "—", 10)
        
        grid2.addLayout(c10, 0, 0)
        grid2.addLayout(c11, 0, 1)
        grid2.addLayout(c12, 0, 2)
        outer.addLayout(grid2)

        # ── Warning banner ──────────────────────────────────────────────
        self._lbl_warning = QLabel("")
        self._lbl_warning.setFont(QFont(FONT_TITLE, 8, QFont.Weight.Bold))
        self._lbl_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; padding: 2px;")
        self._lbl_warning.setVisible(False)
        outer.addWidget(self._lbl_warning)

        self.setLayout(outer)

    # ── Background painting ───────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        painter.setBrush(QBrush(BG_0))
        painter.setPen(QPen(ACCENT_GREEN.darker(150), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        grad = QLinearGradient(0, 0, rect.width(), 0)
        grad.setColorAt(0.0, ACCENT_GREEN)
        grad.setColorAt(1.0, ACCENT_BLUE)
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, rect.width(), 2, 2, 2)

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

        # Header Info
        self._lbl_track_car.setText(f"{frame.track_name} — {frame.car_name}")

        # Delta
        delta = frame.delta_best
        sign = "+" if delta > 0 else ""
        delta_str = f"{sign}{delta:.3f}"
        color = qcolor_hex(ACCENT_RED) if delta > 0 else qcolor_hex(ACCENT_GREEN)
        self._lbl_delta.setText(delta_str)
        self._lbl_delta.setStyleSheet(f"color: {color};")

        # Lap time
        lt = frame.last_lap_time
        lt_str = f"{lt:.1f}s" if lt > 0 else "—"
        self._lbl_lap_time.setText(lt_str)

        # Sectors (da cumulative LMU: S2 = cum-S2 - S1, S3 = lap - cum-S2)
        s1 = frame.last_sector1
        s2 = frame.last_sector2 - frame.last_sector1
        s3 = lt - frame.last_sector2 if lt > 0 else 0
        self._lbl_sector.setText(f"{s1:.1f} / {s2:.1f} / {s3:.1f}")

        # Fuel
        fl = frame.fuel
        fc = frame.fuel_capacity
        self._lbl_fuel.setText(f"{fl:.0f}L")
        fuel_color = qcolor_hex(ACCENT_AMBER) if fl < 10 else qcolor_hex(TEXT_PRIMARY)
        self._lbl_fuel.setStyleSheet(f"color: {fuel_color};")

        # Fuel laps remaining
        fuel_laps = self._estimate_fuel_laps(frame)
        self._lbl_fuel_laps.setText(f"{fuel_laps:.1f}")
        fuel_color2 = qcolor_hex(ACCENT_AMBER) if fuel_laps < 3 else qcolor_hex(TEXT_PRIMARY)
        self._lbl_fuel_laps.setStyleSheet(f"color: {fuel_color2};")

        # Wear FL
        wear_fl = (1.0 - frame.tyre_wear[0]) * 100.0
        self._lbl_wear.setText(f"{wear_fl:.0f}%")
        wc = qcolor_hex(ACCENT_AMBER) if wear_fl < 40 else qcolor_hex(TEXT_PRIMARY)
        self._lbl_wear.setStyleSheet(f"color: {wc};")

        # Cliff
        cliff_laps = self._estimate_cliff_laps(frame)
        self._lbl_cliff.setText(str(cliff_laps) if cliff_laps < 999 else "—")
        cc = qcolor_hex(ACCENT_AMBER) if cliff_laps < 5 else qcolor_hex(TEXT_PRIMARY)
        self._lbl_cliff.setStyleSheet(f"color: {cc};")

        # Compound
        c = frame.tyre_compounds[0] or "—"
        self._lbl_compound.setText(c)

        # Pit
        if self._pit_plan:
            next_pit = next((l for l in self._pit_plan if l >= self._current_lap), None)
            if next_pit is not None:
                laps_to_pit = next_pit - self._current_lap
                if laps_to_pit == 0:
                    self._lbl_pit.setText("BOX!")
                    self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; font-weight: bold;")
                else:
                    self._lbl_pit.setText(f"Giro {next_pit}")
                    self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")
            else:
                self._lbl_pit.setText("—")
                self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
        else:
            self._lbl_pit.setText("—")
            self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

        # Weather
        w = frame.weather_state
        rain = "RAIN" if frame.rain_intensity > 0 else ""
        self._lbl_weather.setText(f"{w} {rain}".strip())

        # Temps
        self._lbl_track_temp.setText(f"{frame.track_temp:.0f}°")
        self._lbl_ambient.setText(f"{frame.ambient_temp:.0f}°")

        # Warning
        if fuel_laps < 2 and not frame.in_pits:
            self._lbl_warning.setText("CARBURANTE CRITICO")
            self._lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_AMBER)}; padding: 2px;")
            self._lbl_warning.setVisible(True)
        elif self._pit_plan and self._current_lap in self._pit_plan:
            self._lbl_warning.setText("BOX QUESTO GIRO")
            self._lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; padding: 2px;")
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