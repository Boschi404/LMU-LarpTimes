"""
Real-time adaptive strategy refresher + audio cues for the LMU overlay.

Three things live here:

1. AudioEngine — plays short .wav cues on Windows via winsound.
   Non-Windows: falls back to no-op. Audio cues:
     - "pit_now"   : box questo giro
     - "pit_soon"  : box fra N giri (N <= 2)
     - "low_fuel"  : carburante critico
     - "strategy_changed" : piano strategia cambiato (es. meteo)
     - "practice_complete": stint di pratica completato

2. PracticeAdvisor — looks at how many clean laps exist for the
   (car, track, compound) combination in the DB and suggests practice
   runs to enrich the model.

3. StrategyRefresher — a QObject driven by a QTimer. Every N seconds,
   checks whether any of the strategy inputs have changed since the last
   calculation (weather, fuel, lap count, compound), and if so re-runs
   the strategist and emits a signal with the new plan + a reason.

This is process-local: it lives inside the overlay process, polls the
shared DB, and emits a Qt signal that OverlayManager listens to.
"""

import os
import sys
import time
import platform
from typing import Optional, List, Dict, Any, Set

from PySide6.QtCore import QObject, QTimer, Signal


# ══════════════════════════════════════════════════════════════════════════════
# Audio Engine (Windows winsound, cross-platform no-op)
# ══════════════════════════════════════════════════════════════════════════════

class AudioEngine:
    """
    Plays short audio cues. Uses Windows winsound for .wav. On other
    platforms, prints a fallback to stdout (useful for tests + Linux dev).
    """

    # Cue names → path
    DEFAULT_CUES: Dict[str, str] = {
        "pit_now":          "audio/pit_now.wav",
        "pit_soon":         "audio/pit_soon.wav",
        "low_fuel":         "audio/low_fuel.wav",
        "strategy_changed": "audio/strategy_changed.wav",
        "practice_complete": "audio/practice_complete.wav",
    }

    def __init__(self, enabled: bool = True, volume: float = 1.0):
        self.enabled = enabled
        self.volume = max(0.0, min(1.0, float(volume)))
        self._last_play: Dict[str, float] = {}  # cue_name → monotonic time
        self.cooldown_sec = 5.0  # never play the same cue more than once / 5s
        self._platform = platform.system()

    def play(self, cue: str, cooldown: bool = True) -> bool:
        """
        Play a cue. Returns True if played, False if skipped (disabled,
        cooldown, no audio backend, etc.).
        """
        if not self.enabled:
            return False
        if cooldown:
            last = self._last_play.get(cue, 0.0)
            if (time.monotonic() - last) < self.cooldown_sec:
                return False
        path = self.DEFAULT_CUES.get(cue, "")
        if not path:
            return False
        # Check file exists (otherwise no-op gracefully)
        if not os.path.isfile(path):
            # For tests: silent fail; in production: log a warning once
            return False
        played = self._play_native(path)
        if played:
            self._last_play[cue] = time.monotonic()
        return played

    def _play_native(self, path: str) -> bool:
        if self._platform == "Windows":
            try:
                import winsound
                # SND_FILENAME | SND_ASYNC | SND_NODEFAULT
                winsound.PlaySound(
                    path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return True
            except Exception:
                return False
        else:
            # Cross-platform fallback: try aplay (Linux) or afplay (macOS)
            try:
                import subprocess
                if self._platform == "Darwin":
                    subprocess.Popen(["afplay", path],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["aplay", path],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                return True
            except Exception:
                return False

    def clear_cooldowns(self):
        self._last_play.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Practice Advisor
# ══════════════════════════════════════════════════════════════════════════════

class PracticeAdvisor:
    """
    Suggests practice actions when there isn't enough data to make a
    reliable strategy call.

    For each (car, track, compound) we want at least N clean laps before
    we trust the degradation model. If the count is below the threshold,
    we return a list of human-readable suggestions.
    """

    MIN_LAPS_PER_COMPOUND = 8
    MIN_LAPS_PER_CAR_TRACK = 12

    @staticmethod
    def advise(laps_for_car_track: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []

        if not laps_for_car_track:
            return [{
                "type": "no_data",
                "priority": "high",
                "title": "Nessun dato per questa combinazione",
                "message": (
                    "Fai 12-15 giri di pratica con mescola Media per "
                    "iniziare a costruire il modello di degrado."
                ),
            }]

        # Per-compound counts
        by_compound: Dict[str, int] = {}
        for l in laps_for_car_track:
            c = l.get("compound_front") or l.get("compound") or "Unknown"
            by_compound[c] = by_compound.get(c, 0) + 1

        # Total
        total = len(laps_for_car_track)
        if total < PracticeAdvisor.MIN_LAPS_PER_CAR_TRACK:
            suggestions.append({
                "type": "few_laps",
                "priority": "high" if total < 5 else "medium",
                "title": f"Solo {total} giri registrati",
                "message": (
                    f"Servono almeno {PracticeAdvisor.MIN_LAPS_PER_CAR_TRACK} giri "
                    "per stime affidabili. Continua a guidare in pratica."
                ),
            })

        # Missing compounds
        for c, threshold in [("Soft", 6), ("Medium", 8), ("Hard", 6)]:
            if by_compound.get(c, 0) < threshold:
                suggestions.append({
                    "type": "missing_compound",
                    "priority": "low",
                    "title": f"Pochi dati su {c}",
                    "message": (
                        f"Hai solo {by_compound.get(c, 0)} giri con {c}. "
                        f"Prova uno stint di {threshold - by_compound.get(c, 0)} giri "
                        f"per migliorare le stime su questa mescola."
                    ),
                })

        return suggestions


# ══════════════════════════════════════════════════════════════════════════════
# Strategy Refresher (QObject driven by a QTimer)
# ══════════════════════════════════════════════════════════════════════════════

class StrategyRefresher(QObject):
    """
    Periodically re-runs the pit strategist and emits a signal when the
    plan changes (or when a reason for re-evaluation is detected).

    Triggers (any of these causes a re-evaluation):
      - Current weather state changed
      - Current fuel level changed by > 1 lap
      - Current lap number advanced
      - Track temperature changed by > 3°C
      - Manual refresh (call request_refresh())
    """

    plan_updated = Signal(dict, str)   # (plan, reason)
    audio_cue = Signal(str)            # cue name

    def __init__(
        self,
        manager,  # OverlayManager (avoid circular import)
        interval_ms: int = 5000,
    ):
        super().__init__()
        self._manager = manager
        self._interval_ms = interval_ms
        self._last_state: Optional[Dict[str, Any]] = None
        self._last_plan_signature: Optional[str] = None
        self._timer: Optional[QTimer] = None
        self._refresh_requested = False

    def start(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval_ms)

    def stop(self):
        if self._timer:
            self._timer.stop()
            self._timer = None

    def request_refresh(self):
        """Force a refresh on the next tick."""
        self._refresh_requested = True

    def _current_state_snapshot(self) -> Optional[Dict[str, Any]]:
        """Snapshot the inputs that may trigger a re-strategy."""
        frame = getattr(self._manager, "_last_frame", None)
        if frame is None:
            return None
        return {
            "weather_state": frame.weather_state,
            "rain_intensity": round(frame.rain_intensity, 2),
            "fuel_laps": round(frame.fuel / 3.2, 1),  # approx laps
            "current_lap": frame.lap_number,
            "track_temp": round(frame.track_temp, 1),
        }

    def _has_state_changed(self, snap: Dict[str, Any]) -> Optional[str]:
        if self._last_state is None:
            return "first_run"
        prev = self._last_state
        if prev["weather_state"] != snap["weather_state"]:
            return "weather_changed"
        if prev["rain_intensity"] != snap["rain_intensity"]:
            return "rain_intensity_changed"
        if abs(prev["fuel_laps"] - snap["fuel_laps"]) >= 1.0:
            return "fuel_changed"
        if prev["current_lap"] != snap["current_lap"]:
            return "lap_changed"
        if abs(prev["track_temp"] - snap["track_temp"]) >= 3.0:
            return "track_temp_changed"
        return None

    def _plan_signature(self, plan: Optional[Dict[str, Any]]) -> str:
        if not plan:
            return "none"
        pit_laps = plan.get("pit_laps", [])
        comp_plan = plan.get("compound_plan", [])
        compounds = tuple((c.get("stint"), c.get("compound")) for c in comp_plan)
        return f"{plan.get('stops', 0)}|{tuple(pit_laps)}|{compounds}"

    def _tick(self):
        snap = self._current_state_snapshot()
        if snap is None:
            return

        reason = "forced" if self._refresh_requested else self._has_state_changed(snap)
        self._refresh_requested = False
        if reason is None:
            return

        # Trigger re-strategy
        try:
            self._manager._refresh_strategy()
        except Exception:
            return

        plan = getattr(self._manager, "_pit_plan", None)
        # Recover compound plan: it's recomputed only when _refresh_strategy runs
        # the full path with weather. Re-run optimize() to get the full plan.
        full_plan = self._recompute_full_plan()
        sig = self._plan_signature(full_plan)

        if sig != self._last_plan_signature:
            self._last_plan_signature = sig
            self.audio_cue.emit("strategy_changed")
            self.plan_updated.emit(full_plan or {}, reason)

        # Practice-mode cue: if no plan, suggest practice
        if not full_plan and self._manager._car and self._manager._track:
            # Just nudge once
            self.audio_cue.emit("practice_complete")

        self._last_state = snap

    def _recompute_full_plan(self) -> Optional[Dict[str, Any]]:
        """
        Re-run optimize() with the latest weather so we get the full
        plan including compound_plan. Returns None if data insufficient.
        """
        m = self._manager
        if not m._car or not m._track:
            return None
        laps = self._safe_get_laps()
        if not laps or len(laps) < 5:
            return None
        try:
            from analysis.models import fit_degradation_model, fit_fuel_model
            from analysis.strategist import PitStrategist
            model = fit_degradation_model(laps)
            mean_cons, _ = fit_fuel_model(laps)
            pit_losses = self._safe_get_pit_losses()
            pit_loss = sum(pit_losses) / len(pit_losses) if pit_losses else 30.0
            strat = PitStrategist(
                fuel_capacity=100.0,
                fuel_consumption=mean_cons,
                pit_loss=pit_loss,
                model_fit=model,
            )
            remaining = max(1, m._total_race_laps - m._current_lap)
            frame = getattr(m, "_last_frame", None)
            weather = "DRY"
            rain = 0.0
            track_temp = None
            if frame is not None:
                weather = frame.weather_state or "DRY"
                rain = frame.rain_intensity
                track_temp = frame.track_temp
            weather_forecast = [{
                "weather_state": weather,
                "rain_intensity": rain,
            }]
            result = strat.optimize(
                laps_remaining=remaining,
                current_tyre_age=1,
                current_fuel=100.0,
                max_stops=3,
                laps_history=laps,
                weather_forecast=weather_forecast,
                track_temp=track_temp,
            )
            return result.get("optimal")
        except Exception:
            return None

    def _safe_get_laps(self):
        import database
        m = self._manager
        try:
            return database.get_laps_for_analysis(
                m._car, m._track, db_path=m.db_path
            )
        except Exception:
            return []

    def _safe_get_pit_losses(self):
        import database
        m = self._manager
        try:
            return database.get_pit_stops_loss_by_session(
                m._car, m._track, db_path=m.db_path
            )
        except Exception:
            return []
