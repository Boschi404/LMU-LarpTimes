"""
LMU Pit Strategist — Overlay Live FULL (Processo A)

Finestra unica, griglia 3×3 con tutti i dati.
Stesse feature del modulare: audio cue, refresher, race detection,
settings dialog, practice advisor. Hotkey globale: Ctrl+Shift+O.
"""

import sys
import signal
import ctypes
import ctypes.wintypes
import json
import os
import threading
import time
from typing import Optional, List, Dict, Any

from PySide6.QtCore import (
    Qt, QPoint, QTimer, Signal, QObject, QThread
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QPen, QBrush
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSizePolicy, QMenu, QDialog, QCheckBox, QSlider, QPushButton, QRadioButton
)

import database
from telemetry.source import TelemetrySource, TelemetryFrame
from analysis.models import fit_degradation_model, fit_fuel_model
from analysis.strategist import PitStrategist
from analysis.qualifying import QualifyingAnalyst, TYRE_COLD, TYRE_IN_WINDOW, TYRE_DEGRADED
from analysis.tyre_manager import estimate_remaining_life, TyreStatus
from analysis.classes import detect_class
from analysis.practice import analyze_practice_data
from overlay.strategy_refresher import AudioEngine, PracticeAdvisor, StrategyRefresher
from overlay.icons import settings_icon, icon_pixmap, clean_action_text

# ══════════════════════════════════════════════════════════════════════════════
# Design System
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


def qcolor_hex(c: QColor) -> str:
    return '#%02x%02x%02x' % (c.red(), c.green(), c.blue())


# ══════════════════════════════════════════════════════════════════════════════
# Config persistence
# ══════════════════════════════════════════════════════════════════════════════

import paths
CONFIG_PATH = paths.data_path("overlay", "overlay_config.json")
DEFAULT_CONFIG = {
    "x": 50, "y": 50, "visible": True, "in_game_only": False,
    "audio_enabled": True, "audio_volume": 1.0, "practice_mode": True,
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        return {**DEFAULT_CONFIG, **json.load(open(CONFIG_PATH))}
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# Telemetry worker
# ══════════════════════════════════════════════════════════════════════════════

class TelemetryWorker(QObject):
    frame_ready = Signal(object)
    lap_completed = Signal(int)
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
            on_race_started=self._race_wrapper,
            on_qualifying_started=self._qualifying_wrapper,
        )
        self.source.start()
        self._running = True
        TICK = 0.05
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

    def _race_wrapper(self, session_uuid, car, track):
        self.race_started.emit(session_uuid, car, track)

    def _qualifying_wrapper(self, session_uuid, car, track):
        self.qualifying_started.emit(session_uuid, car, track)


# ══════════════════════════════════════════════════════════════════════════════
# Settings Dialog (shared with modulare)
# ══════════════════════════════════════════════════════════════════════════════

COMPONENT_ORDER = ["delta", "fuel", "cliff", "pit"]
COMPONENT_LABELS = {
    "delta": "Delta", "fuel": "Carburante",
    "cliff": "Cliff gomme", "pit": "Pit stop",
}


class SettingsDialog(QDialog):
    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self._widget = widget
        self._cfg = load_config()
        self.setWindowTitle("Impostazioni Overlay")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {qcolor_hex(BG_0)}; color: {qcolor_hex(TEXT_PRIMARY)};
                       border: 1px solid {qcolor_hex(BORDER_BRIGHT)}; border-radius: 8px; }}
            QLabel {{ color: {qcolor_hex(TEXT_PRIMARY)}; font-family: 'Rajdhani', 'Inter', sans-serif; }}
            QCheckBox {{ color: {qcolor_hex(TEXT_PRIMARY)}; font-family: 'JetBrains Mono';
                         spacing: 8px; padding: 4px 0; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {qcolor_hex(BORDER_BRIGHT)};
                                   background: {qcolor_hex(BG_1)}; border-radius: 3px; }}
            QCheckBox::indicator:checked {{ background: {qcolor_hex(ACCENT_BLUE)};
                                            border-color: {qcolor_hex(ACCENT_BLUE)}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {qcolor_hex(BG_1)}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {qcolor_hex(ACCENT_BLUE)}; width: 14px; height: 14px;
                                          margin: -5px 0; border-radius: 7px; }}
            QSlider::sub-page:horizontal {{ background: {qcolor_hex(ACCENT_BLUE)}; border-radius: 2px; }}
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 {qcolor_hex(ACCENT_BLUE)}, stop:1 #0072cc);
                           color: {qcolor_hex(TEXT_PRIMARY)};
                           border: none; padding: 6px 16px; border-radius: 4px;
                           font-family: 'Rajdhani', 'Inter', sans-serif; font-weight: bold; font-size: 11px; }}
            QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                 stop:0 #00b8ff, stop:1 #0088dd); }}
            QRadioButton {{ color: {qcolor_hex(TEXT_PRIMARY)}; font-family: 'Rajdhani', 'Inter', sans-serif; font-size: 12px; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("Impostazioni")
        title.setFont(QFont(FONT_TITLE, 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # Audio
        al = QLabel("SUONI")
        al.setStyleSheet("color: #7d8590; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(al)
        self._cb_audio = QCheckBox("Abilita suoni")
        self._cb_audio.setChecked(self._cfg.get("audio_enabled", True))
        self._cb_audio.toggled.connect(self._on_audio)
        layout.addWidget(self._cb_audio)

        vl = QHBoxLayout()
        vl.setContentsMargins(24, 0, 0, 0)
        vlabel = QLabel("Volume:")
        vlabel.setFont(QFont(FONT_VALUE, 10))
        vlabel.setFixedWidth(60)
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(int(self._cfg.get("audio_volume", 1.0) * 100))
        self._vol.valueChanged.connect(self._on_vol)
        self._volv = QLabel(f"{self._vol.value()}%")
        self._volv.setFont(QFont(FONT_VALUE, 10))
        self._volv.setFixedWidth(40)
        vl.addWidget(vlabel)
        vl.addWidget(self._vol)
        vl.addWidget(self._volv)
        layout.addLayout(vl)
        tb = QPushButton("Test suono")
        tb.clicked.connect(self._on_test)
        layout.addWidget(tb)

        # Mode
        ml = QLabel("MODALITA")
        ml.setStyleSheet("color: #7d8590; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(ml)
        self._cb_ig = QCheckBox("Solo in gioco (auto-hide)")
        self._cb_ig.setChecked(self._cfg.get("in_game_only", False))
        self._cb_ig.toggled.connect(lambda s: self._save("in_game_only", s))
        layout.addWidget(self._cb_ig)
        self._cb_pr = QCheckBox("Practice mode")
        self._cb_pr.setChecked(self._cfg.get("practice_mode", True))
        self._cb_pr.toggled.connect(lambda s: self._save("practice_mode", s))
        layout.addWidget(self._cb_pr)

        # Overlay mode toggle
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

        # Buttons
        bh = QHBoxLayout()
        rp = QPushButton("Reset posizione")
        rp.clicked.connect(lambda: self._widget.move(
            self._cfg.__setitem__("x", 50) or 50,
            self._cfg.__setitem__("y", 50) or 50,
        ) and save_config(self._cfg) and None)
        ha = QPushButton("Nascondi")
        ha.clicked.connect(self._widget.hide)
        bh.addWidget(rp)
        bh.addWidget(ha)
        layout.addLayout(bh)

        cl = QPushButton("Chiudi")
        cl.clicked.connect(self.accept)
        layout.addWidget(cl)
        layout.addStretch()

    def _on_audio(self, s):
        self._widget.audio_engine.enabled = s
        self._save("audio_enabled", s)

    def _on_vol(self, v):
        vol = v / 100.0
        self._widget.audio_engine.volume = vol
        self._save("audio_volume", vol)
        self._volv.setText(f"{v}%")

    def _on_test(self):
        self._widget.audio_engine.clear_cooldowns()
        self._widget.audio_engine.play("pit_now", cooldown=False)

    def _save(self, k, v):
        self._cfg[k] = v
        save_config(self._cfg)

    def _on_mode_change(self):
        new_mode = "full" if self._rb_full.isChecked() else "modular"
        self._cfg["overlay_mode"] = new_mode
        save_config(self._cfg)


# ══════════════════════════════════════════════════════════════════════════════
# Overlay Widget
# ══════════════════════════════════════════════════════════════════════════════

class OverlayWidget(QWidget):
    def __init__(self, db_path: str = database.DEFAULT_DB_PATH):
        super().__init__()
        self.db_path = db_path
        self._cfg = load_config()
        self._drag_pos: Optional[QPoint] = None
        self._last_frame: Optional[TelemetryFrame] = None

        # Strategy state
        self._car: Optional[str] = None
        self._track: Optional[str] = None
        self._pit_plan: Optional[List[int]] = None
        self._total_race_laps: int = 0
        self._current_lap: int = 1
        self._session_type: Optional[str] = None
        self._qualy_data: Optional[Dict[str, Any]] = None
        # Tyre age tracking
        self._tyre_age_laps: int = 0
        self._last_stint: int = 0

        self._user_wants_visible = True

        # Audio + refresher
        self.audio_engine = AudioEngine(
            enabled=bool(self._cfg.get("audio_enabled", True)),
            volume=float(self._cfg.get("audio_volume", 1.0)),
        )
        self.refresher = StrategyRefresher(self, interval_ms=5000)
        self.refresher.audio_cue.connect(self._play_audio_cue)
        self.refresher.plan_updated.connect(self._on_plan_updated)

        self._setup_window()
        self._build_ui()
        self._setup_hotkeys()

    # ── Window ──────────────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {qcolor_hex(BG_0)}; color: {qcolor_hex(TEXT_PRIMARY)};
                     border: 1px solid {qcolor_hex(BORDER_BRIGHT)}; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px; }}
            QMenu::item:selected {{ background-color: {qcolor_hex(ACCENT_BLUE)}; }}
            QMenu::separator {{ height: 1px; background: {qcolor_hex(BORDER_BRIGHT)}; margin: 4px 8px; }}
        """)
        a_sett = menu.addAction("Impostazioni")
        a_refr = menu.addAction("Ricalcola strategia")
        menu.addSeparator()
        a_hide = menu.addAction("Nascondi")
        a_web = menu.addAction("Apri browser")
        menu.addSeparator()
        a_quit = menu.addAction("Esci")

        action = menu.exec(event.globalPos())
        if action is a_sett:
            self.open_settings_dialog()
        elif action is a_refr:
            self.refresher.request_refresh()
        elif action is a_hide:
            self._user_wants_visible = False
            self.hide()
            self._cfg["visible"] = False
            save_config(self._cfg)
        elif action is a_web:
            import webbrowser
            webbrowser.open("http://127.0.0.1:8000/")
        elif action is a_quit:
            QApplication.quit()

    def open_settings_dialog(self):
        SettingsDialog(self).exec()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumSize(340, 220)
        self.move(self._cfg.get("x", 50), self._cfg.get("y", 50))
        if self._cfg.get("visible", True):
            self.show()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 4)
        self._lbl_brand = QLabel("LMU  LarpTimes")
        self._lbl_brand.setFont(QFont(FONT_TITLE, 8, QFont.Weight.Bold))
        self._lbl_brand.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)}; letter-spacing: 1px;")
        self._lbl_track_car = QLabel("\u2014")
        self._lbl_track_car.setFont(QFont(FONT_TITLE, 8, QFont.Weight.Bold))
        self._lbl_track_car.setStyleSheet(f"color: {qcolor_hex(ACCENT_BLUE)}; letter-spacing: 1px;")
        self._lbl_track_car.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Settings gear button
        from PySide6.QtGui import QIcon
        self._btn_settings = QPushButton()
        pix = icon_pixmap(settings_icon(), size=14, color=qcolor_hex(TEXT_SECONDARY))
        self._btn_settings.setIcon(QIcon(pix))
        self._btn_settings.setIconSize(pix.size())
        self._btn_settings.setFixedSize(22, 22)
        self._btn_settings.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {qcolor_hex(BORDER_BRIGHT)};
                border-radius: 4px; color: {qcolor_hex(TEXT_SECONDARY)};
                font-size: 12px; padding: 0;
            }}
            QPushButton:hover {{
                background: {qcolor_hex(BG_2)}; color: {qcolor_hex(TEXT_PRIMARY)};
            }}
        """)
        self._btn_settings.clicked.connect(self.open_settings_dialog)

        hdr.addWidget(self._lbl_brand)
        hdr.addStretch()
        hdr.addWidget(self._btn_settings)
        hdr.addSpacing(6)
        hdr.addWidget(self._lbl_track_car)
        outer.addLayout(hdr)

        # 3x3 grid
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 4, 0, 4)

        def cell(label, default="\u2014", fs=10):
            container = QWidget()
            container.setStyleSheet(f"""
                QWidget {{
                    background: transparent;
                    border-left: 3px solid {qcolor_hex(ACCENT_BLUE)};
                    padding-left: 6px;
                }}
            """)
            w = QVBoxLayout(container)
            w.setContentsMargins(0, 0, 0, 0)
            w.setSpacing(2)
            lbl = QLabel(label)
            lbl.setFont(QFont(FONT_TITLE, 7, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)}; letter-spacing: 1px; background: transparent;")
            val = QLabel(default)
            val.setFont(QFont(FONT_VALUE, fs, QFont.Weight.Bold))
            val.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)}; background: transparent;")
            w.addWidget(lbl)
            w.addWidget(val)
            return container, val

        c1, self._lbl_delta    = cell("DELTA", "+0.000", 11)
        c2, self._lbl_lap_time = cell("GIRO", "\u2014", 11)
        c3, self._lbl_sector   = cell("SETTORI", "\u2014", 10)
        c4, self._lbl_fuel     = cell("CARBURANTE", "\u2014L", 11)
        c5, self._lbl_fuel_laps= cell("GIRI CARB.", "\u2014", 10)
        c6, self._lbl_wear     = cell("USURA FL", "\u2014%", 10)
        c7, self._lbl_cliff    = cell("CLIFF", "\u2014", 10)
        c8, self._lbl_compound = cell("MESCOLA", "\u2014", 10)
        c9, self._lbl_pit      = cell("BOX", "\u2014", 11)

        grid.addWidget(c1, 0, 0)
        grid.addWidget(c2, 0, 1)
        grid.addWidget(c3, 0, 2)
        grid.addWidget(c4, 1, 0)
        grid.addWidget(c5, 1, 1)
        grid.addWidget(c6, 1, 2)
        grid.addWidget(c7, 2, 0)
        grid.addWidget(c8, 2, 1)
        grid.addWidget(c9, 2, 2)
        outer.addLayout(grid)

        # Weather row
        wg = QGridLayout()
        wg.setSpacing(12)
        wg.setContentsMargins(0, 4, 0, 0)
        c10, self._lbl_weather   = cell("METEO", "\u2014", 10)
        c11, self._lbl_track_temp = cell("PISTA", "\u2014", 10)
        c12, self._lbl_ambient   = cell("ARIA", "\u2014", 10)
        wg.addWidget(c10, 0, 0)
        wg.addWidget(c11, 0, 1)
        wg.addWidget(c12, 0, 2)
        outer.addLayout(wg)

        # Tyre status row
        ts_row = QHBoxLayout()
        ts_row.setContentsMargins(0, 0, 0, 0)
        ts_row.setSpacing(8)
        self._lbl_tyre_status_title = QLabel("GOMME:")
        self._lbl_tyre_status_title.setFont(QFont(FONT_TITLE, 7, QFont.Weight.Bold))
        self._lbl_tyre_status_title.setStyleSheet(
            f"color: {qcolor_hex(TEXT_MUTED)}; letter-spacing: 1px;"
        )
        self._lbl_tyre_status = QLabel("\u2014")
        self._lbl_tyre_status.setFont(QFont(FONT_VALUE, 8, QFont.Weight.Bold))
        self._lbl_tyre_status.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)};")
        self._lbl_tyre_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ts_row.addWidget(self._lbl_tyre_status_title)
        ts_row.addWidget(self._lbl_tyre_status, 1)
        outer.addLayout(ts_row)

        # Warning
        self._lbl_warning = QLabel("")
        self._lbl_warning.setFont(QFont(FONT_TITLE, 8, QFont.Weight.Bold))
        self._lbl_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; padding: 2px;")
        self._lbl_warning.setVisible(False)
        outer.addWidget(self._lbl_warning)

        # Qualifying info (hidden by default)
        self._lbl_qualy = QLabel("")
        self._lbl_qualy.setFont(QFont(FONT_VALUE, 8, QFont.Weight.Bold))
        self._lbl_qualy.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lbl_qualy.setStyleSheet(f"color: {qcolor_hex(ACCENT_GREEN)}; padding: 2px;")
        self._lbl_qualy.setVisible(False)
        self._lbl_qualy.setWordWrap(True)
        outer.addWidget(self._lbl_qualy)
        self.setLayout(outer)

    # ── Paint ───────────────────────────────────────────────────────────────

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

    # ── Drag ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        if self._drag_pos:
            p = self.pos()
            self._cfg["x"], self._cfg["y"] = p.x(), p.y()
            save_config(self._cfg)
            self._drag_pos = None

    # ── Hotkeys ──────────────────────────────────────────────────────────────

    def _setup_hotkeys(self):
        self._hk_toggle = 1
        try:
            ctypes.windll.user32.RegisterHotKey(None, self._hk_toggle, 0x0002 | 0x0004, 0x4F)
            self._hk_timer = QTimer(self)
            self._hk_timer.timeout.connect(self._check_hk)
            self._hk_timer.start(100)
        except Exception:
            pass

    def _check_hk(self):
        msg = ctypes.wintypes.MSG()
        if ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
            if msg.message == 0x0312 and msg.wParam == self._hk_toggle:
                if self._user_wants_visible:
                    self._user_wants_visible = False
                    self.hide()
                else:
                    self._user_wants_visible = True
                    self.show()
                self._cfg["visible"] = self._user_wants_visible
                save_config(self._cfg)

    def _apply_auto_visibility(self, frame: TelemetryFrame):
        if not self._cfg.get("in_game_only", False) or not self._user_wants_visible:
            return
        in_game = not frame.in_pits and frame.lap_number > 0 and frame.elapsed_time > 2.0
        if in_game and not self.isVisible():
            self.show()
        elif not in_game and self.isVisible():
            self.hide()

    def closeEvent(self, _event):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._hk_toggle)
        except Exception:
            pass

    # ── Frame update ────────────────────────────────────────────────────────

    def update_frame(self, frame: TelemetryFrame):
        self._apply_auto_visibility(frame)

        # Track tyre age: reset on stint change, increment on lap number increase
        if frame.stint_number != self._last_stint:
            self._tyre_age_laps = 0
            self._last_stint = frame.stint_number
        elif frame.lap_number > self._current_lap:
            self._tyre_age_laps += 1

        self._current_lap = frame.lap_number
        self._last_frame = frame

        car_class = detect_class(frame.car_name)
        self._lbl_track_car.setText(f"{frame.track_name} — {frame.car_name}  [{car_class}]")

        # Delta
        d = frame.delta_best
        sign = "+" if d > 0 else ""
        self._lbl_delta.setText(f"{sign}{d:.3f}")
        self._lbl_delta.setStyleSheet(
            f"color: {qcolor_hex(ACCENT_RED) if d > 0 else qcolor_hex(ACCENT_GREEN)};"
        )

        # Lap time
        lt = frame.last_lap_time
        self._lbl_lap_time.setText(f"{lt:.1f}s" if lt > 0 else "\u2014")

        # Sectors
        s1 = frame.last_sector1
        s2 = frame.last_sector2 - frame.last_sector1
        s3 = lt - frame.last_sector2 if lt > 0 else 0
        self._lbl_sector.setText(f"{s1:.1f} / {s2:.1f} / {s3:.1f}")

        # Fuel
        fl = frame.fuel
        self._lbl_fuel.setText(f"{fl:.0f}L")
        self._lbl_fuel.setStyleSheet(
            f"color: {qcolor_hex(ACCENT_RED) if fl < 10 else qcolor_hex(TEXT_PRIMARY)};"
        )

        # Fuel laps
        f_laps = self._estimate_fuel_laps(frame)
        self._lbl_fuel_laps.setText(f"{f_laps:.1f}")
        self._lbl_fuel_laps.setStyleSheet(
            f"color: {qcolor_hex(ACCENT_RED) if f_laps < 3 else qcolor_hex(TEXT_PRIMARY)};"
        )

        # Refuel suggestion
        refuel = self._calculate_refuel(frame)
        if refuel is not None and refuel > 0:
            self._lbl_fuel.setText(f"{frame.fuel:.0f}L / +{refuel:.0f}L")
            self._lbl_fuel.setStyleSheet(f"color: {qcolor_hex(ACCENT_BLUE)};")
        else:
            self._lbl_fuel.setText(f"{frame.fuel:.0f}L")
            self._lbl_fuel.setStyleSheet(
                f"color: {qcolor_hex(ACCENT_RED) if frame.fuel < 10 else qcolor_hex(TEXT_PRIMARY)};"
            )

        # Wear
        wf = (1.0 - frame.tyre_wear[0]) * 100.0
        self._lbl_wear.setText(f"{wf:.0f}%")
        self._lbl_wear.setStyleSheet(
            f"color: {qcolor_hex(ACCENT_AMBER) if wf < 40 else qcolor_hex(TEXT_PRIMARY)};"
        )

        # Cliff
        cliff = self._estimate_cliff_laps(frame)
        self._lbl_cliff.setText(str(cliff) if cliff < 999 else "\u2014")
        self._lbl_cliff.setStyleSheet(
            f"color: {qcolor_hex(ACCENT_AMBER) if cliff < 5 else qcolor_hex(TEXT_PRIMARY)};"
        )

        # Tyre status — live prediction of remaining life
        try:
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
            remaining = tyre_status.remaining_laps
            if remaining <= 0:
                tyre_color = qcolor_hex(ACCENT_RED)
                status_text = f"PIT NOW — cliff reached!  ({tyre_status.temp_status})"
            elif remaining <= 2:
                tyre_color = qcolor_hex(ACCENT_RED)
                status_text = f"Pit in {remaining}L — near cliff  ({tyre_status.temp_status})"
            elif remaining <= 5:
                tyre_color = qcolor_hex(ACCENT_AMBER)
                status_text = f"~{remaining}L before cliff  ({tyre_status.temp_status})"
            else:
                tyre_color = qcolor_hex(ACCENT_GREEN)
                status_text = f"✔ OK — ~{remaining}L left  ({tyre_status.temp_status})"
            self._lbl_tyre_status.setText(status_text)
            self._lbl_tyre_status.setStyleSheet(
                f"color: {tyre_color}; font-size: 8px; letter-spacing: 1px;"
            )
        except Exception as e:
            self._lbl_tyre_status.setText("\u2014")
            self._lbl_tyre_status.setStyleSheet(f"color: {qcolor_hex(TEXT_SECONDARY)};")

        # Compound
        self._lbl_compound.setText(frame.tyre_compounds[0] or "\u2014")

        # Pit
        self._update_pit()

        # Qualifying
        if self._session_type == "QUALIFYING":
            self._run_qualifying_analysis()

        # Practice
        if self._session_type is None or self._session_type == "PRACTICE":
            self._update_practice_analysis()

        # Weather
        self._lbl_weather.setText(frame.weather_state or "\u2014")
        self._lbl_track_temp.setText(f"{frame.track_temp:.0f}\u00b0")
        self._lbl_ambient.setText(f"{frame.ambient_temp:.0f}\u00b0")

        # Warning
        if f_laps < 2 and not frame.in_pits:
            self._lbl_warning.setText("CARBURANTE CRITICO")
            self._lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; padding: 2px;")
            self._lbl_warning.setVisible(True)
        elif self._pit_plan and self._current_lap in self._pit_plan:
            self._lbl_warning.setText("BOX QUESTO GIRO")
            self._lbl_warning.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; padding: 2px;")
            self._lbl_warning.setVisible(True)
        else:
            self._lbl_warning.setVisible(False)

    def _update_pit(self):
        if self._pit_plan:
            nxt = next((l for l in self._pit_plan if l >= self._current_lap), None)
            if nxt is None:
                self._lbl_pit.setText("\u2014")
                self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")
            elif nxt == self._current_lap:
                self._lbl_pit.setText("BOX!")
                self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(ACCENT_RED)}; font-weight: bold;")
            else:
                self._lbl_pit.setText(f"L{nxt} ({nxt - self._current_lap}L)")
                self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(TEXT_PRIMARY)};")
        else:
            self._lbl_pit.setText("\u2014")
            self._lbl_pit.setStyleSheet(f"color: {qcolor_hex(TEXT_MUTED)};")

    # ── Strategy ────────────────────────────────────────────────────────────

    def on_lap_completed(self, _lap_id: int):
        if self._session_type == "QUALIFYING":
            self._run_qualifying_analysis()
        else:
            self._refresh_strategy()

    def on_race_started(self, session_uuid: str, car: str, track: str):
        print(f"[FullOverlay] Race started @ {track} [{car}]")
        self._session_type = "RACE"
        self._lbl_qualy.setVisible(False)
        self.set_session_info(car=car, track=track, total_laps=60)
        self._refresh_strategy()
        self.audio_engine.play("strategy_changed")

    def on_qualifying_started(self, session_uuid: str, car: str, track: str):
        print(f"[FullOverlay] Qualifying started @ {track} [{car}]")
        self._session_type = "QUALIFYING"
        self._qualy_data = None
        self._lbl_qualy.setVisible(True)
        self.set_session_info(car=car, track=track, total_laps=60)

    def set_session_info(self, car: str, track: str, total_laps: int = 40):
        self._car = car
        self._track = track
        self._total_race_laps = total_laps

    def set_pit_plan(self, pit_laps: List[int]):
        self._pit_plan = pit_laps

    def _run_qualifying_analysis(self):
        if not self._car or not self._track:
            return
        try:
            all_laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if len(all_laps) < 3:
                self._qualy_data = None
                self._lbl_qualy.setText("Collecting data\u2026")
                return
            _, mean_cons = fit_fuel_model(all_laps)
            model = fit_degradation_model(all_laps)
            analyst = QualifyingAnalyst(fuel_consumption_lap=mean_cons, model_fit=model)
            self._qualy_data = analyst.analyze(all_laps)

            # Build display text
            lines = []
            best = self._qualy_data.get("best_hotlap_time")
            hotlaps = self._qualy_data.get("num_hotlaps", 0)
            fuel_save = self._qualy_data.get("fuel_saving_potential", 0)
            out_delta = self._qualy_data.get("outlap_delta_from_hot")
            in_delta = self._qualy_data.get("inlap_delta_from_hot")
            if best:
                lines.append(f"Miglior {best:.1f}s")
            if hotlaps:
                lines.append(f"{hotlaps}x hot lap(s)")
            if fuel_save > 0.5:
                lines.append(f"-{fuel_save:.1f}L risparmio")
            if out_delta is not None:
                lines.append(f"Out +{out_delta:.1f}s")
            if in_delta is not None:
                lines.append(f"In +{in_delta:.1f}s")
            # Tyre temp window
            tyre_window = self._qualy_data.get("tyre_temp_window")
            if tyre_window:
                # Message (strip duplicate emoji, app_new style)
                msg = tyre_window.get("tyre_window_message", "")
                if msg:
                    lines.append(clean_action_text(msg))
                best_in = tyre_window.get("best_in_window")
                best_out = tyre_window.get("best_outside_window")
                if best_in and best_out:
                    lost = best_in - best_out
                    if lost > 0:
                        lines.append(f"Fuori +{lost:.2f}s")
                hotlaps_opt = tyre_window.get("optimal_hotlaps_count")
                if hotlaps_opt is not None and hotlaps_opt > 0:
                    lines.append(f"{hotlaps_opt}x/run")
            # Tyre window indicator color
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
            # Suggestions
            for s in self._qualy_data.get("suggestions", [])[:2]:
                lines.append(s)
            self._lbl_qualy.setText("  ".join(lines))
            self._lbl_qualy.setStyleSheet(f"color: {qcolor_hex(indicator_color)}; padding: 2px; font-size: 7px;")
            for s in self._qualy_data.get("suggestions", []):
                print(f"  [Qualy] {s}")
        except Exception as e:
            print(f"  [Qualy] Error: {e}")
            self._qualy_data = None
            self._lbl_qualy.setText("—")

    def _estimate_fuel_laps(self, frame: TelemetryFrame) -> float:
        fuel = frame.fuel
        if self._car and self._track:
            laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            if laps:
                mean_cons, _ = fit_fuel_model(laps)
                if mean_cons > 0:
                    return fuel / mean_cons
        return fuel / 3.2

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
            pit_losses = database.get_pit_stops_loss_by_session(self._car, self._track, db_path=self.db_path)
            pit_loss = sum(pit_losses) / len(pit_losses) if pit_losses else 30.0
            strat = PitStrategist(fuel_capacity=100.0, fuel_consumption=mean_cons, pit_loss=pit_loss, model_fit=model)
            remaining = max(1, self._total_race_laps - self._current_lap)
            result = strat.optimize(laps_remaining=remaining, current_tyre_age=1, current_fuel=100.0, max_stops=3)
            if result.get("optimal"):
                self._pit_plan = [self._current_lap + p - 1 for p in result["optimal"]["pit_laps"]]
        except Exception:
            pass

    def _play_audio_cue(self, cue: str):
        self.audio_engine.play(cue)

    def _on_plan_updated(self, plan: Dict[str, Any], reason: str):
        pit_laps = plan.get("pit_laps", [])
        self._pit_plan = [self._current_lap + p - 1 for p in pit_laps] if pit_laps else []
        self._update_pit()
        if self._last_frame:
            fl = self._estimate_fuel_laps(self._last_frame)
            if fl < 2 and not self._last_frame.in_pits:
                self.audio_engine.play("low_fuel")
        if self._pit_plan and self._current_lap in self._pit_plan:
            self.audio_engine.play("pit_now")
        elif self._pit_plan:
            nxt = next((l for l in self._pit_plan if l >= self._current_lap), None)
            if nxt is not None and (nxt - self._current_lap) <= 2:
                self.audio_engine.play("pit_soon")

    def _update_practice_analysis(self):
        """Analyse practice data coverage and show in the qualy label."""
        if not self._car or not self._track:
            return
        try:
            all_laps = database.get_laps_for_analysis(self._car, self._track, db_path=self.db_path)
            result = analyze_practice_data(all_laps)
            fuel = result.get("fuel", {})
            tyre = result.get("tyre", {})
            comps = result.get("compounds", [])
            total = result.get("total_laps", 0)
            suggestions = result.get("suggestions", [])

            lines = [f"{total} giri"]
            if fuel.get("range_l", 0) > 0:
                lines.append(f"Carb. {fuel['min_l']}-{fuel['max_l']}L")
            if tyre.get("range_laps", 0) > 0:
                lines.append(f"Gomme {tyre['min_age']}-{tyre['max_age']}g")
            if comps:
                lines.append(f"{'/'.join(comps)}")
            if suggestions:
                top = max(suggestions, key=lambda s: {"high": 3, "medium": 2, "low": 1}.get(s.get("priority", "low"), 0))
                lines.append(f"→ {top.get('message', '')[:50]}")

            self._lbl_qualy.setText("  ".join(lines))
            self._lbl_qualy.setStyleSheet(f"color: {qcolor_hex(ACCENT_BLUE)}; padding: 2px; font-size: 7px;")
            if not self._lbl_qualy.isVisible():
                self._lbl_qualy.setVisible(True)
        except Exception as e:
            print(f"  [Practice] Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Main entry
# ══════════════════════════════════════════════════════════════════════════════

def run_overlay(source: TelemetrySource, db_path: str = database.DEFAULT_DB_PATH):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    overlay = OverlayWidget(db_path=db_path)

    worker = TelemetryWorker(source, db_path)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.start_source)
    worker.frame_ready.connect(overlay.update_frame)
    worker.lap_completed.connect(overlay.on_lap_completed)
    worker.race_started.connect(overlay.on_race_started)
    worker.qualifying_started.connect(overlay.on_qualifying_started)
    thread.start()

    overlay.refresher.start()

    def cleanup():
        overlay.refresher.stop()
        worker.stop()
        thread.quit()
        thread.wait()

    app.aboutToQuit.connect(cleanup)

    def handle_sigint(signum, frame):
        cleanup()
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        ret = app.exec()
    finally:
        cleanup()
    return ret


if __name__ == "__main__":
    from telemetry.source import SyntheticReplaySource
    src = SyntheticReplaySource(
        track_name="Le Mans", car_name="Ferrari 499P LMH",
        lap_time_base=225.0, fuel_capacity=110.0, initial_fuel=105.0,
        fuel_consumption=4.8, cliff_lap=18,
        anomaly_laps={5: 2.0, 12: 1.8}, total_laps=40, tick_rate=0.5,
    )
    sys.exit(run_overlay(src))
