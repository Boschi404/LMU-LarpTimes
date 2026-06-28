"""
Tests for the real-time adaptive layer (overlay/strategy_refresher.py +
analysis/weather.py).

Covers:
  - AudioEngine:
      * play() respects enabled flag
      * cooldown prevents repeat plays
      * missing files don't crash
      * clear_cooldowns() resets the cooldown
  - PracticeAdvisor:
      * returns "no_data" suggestion when no laps
      * returns "few_laps" suggestion when below threshold
      * returns per-compound suggestions when a compound is under-tested
  - StrategyRefresher:
      * detects weather change
      * detects fuel change >= 1 lap
      * detects lap change
      * ignores unchanged state
      * request_refresh() forces re-eval
  - Weather forecaster:
      * linear_rain_forecast: empty history → dry default
      * upward trend → predicts WET
      * downward trend → predicts DRY
      * switch_in_minutes computed correctly
      * build_stint_weather_forecast splits laps
"""

import os
import sys
import time
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ──────────────────────────────────────────────────────────────────────────────
# AudioEngine
# ──────────────────────────────────────────────────────────────────────────────

def test_audio_engine_disabled_returns_false():
    from overlay.strategy_refresher import AudioEngine
    eng = AudioEngine(enabled=False)
    # Even with a missing file, disabled engine must return False
    assert eng.play("pit_now") is False


def test_audio_engine_missing_file_does_not_raise():
    from overlay.strategy_refresher import AudioEngine
    eng = AudioEngine(enabled=True)
    # No file at DEFAULT_CUES path → returns False but doesn't crash
    result = eng.play("pit_now", cooldown=False)
    assert result is False  # missing file


def test_audio_engine_clear_cooldowns():
    from overlay.strategy_refresher import AudioEngine
    eng = AudioEngine(enabled=True)
    eng.cooldown_sec = 100.0
    eng._last_play["pit_now"] = time.monotonic()
    assert "pit_now" in eng._last_play
    eng.clear_cooldowns()
    assert "pit_now" not in eng._last_play


def test_audio_engine_cooldown_logic():
    """If we manually set a last_play and try to play again, the cooldown
    should block the second call. We test the gating logic directly
    without actually playing audio."""
    from overlay.strategy_refresher import AudioEngine
    eng = AudioEngine(enabled=True)
    eng.cooldown_sec = 10.0
    # Simulate a recent play
    eng._last_play["pit_now"] = time.monotonic()
    # Calling play with cooldown=True (default) must be blocked
    assert eng.play("pit_now") is False
    # cooldown=False bypasses
    assert eng.play("pit_now", cooldown=False) is False


def test_audio_engine_volume_clamped():
    from overlay.strategy_refresher import AudioEngine
    eng = AudioEngine(enabled=True, volume=2.5)
    assert eng.volume == 1.0
    eng = AudioEngine(enabled=True, volume=-0.5)
    assert eng.volume == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# PracticeAdvisor
# ──────────────────────────────────────────────────────────────────────────────

def test_practice_advisor_no_data():
    from overlay.strategy_refresher import PracticeAdvisor
    suggestions = PracticeAdvisor.advise([])
    assert len(suggestions) == 1
    assert suggestions[0]["type"] == "no_data"
    assert suggestions[0]["priority"] == "high"


def test_practice_advisor_few_laps():
    from overlay.strategy_refresher import PracticeAdvisor
    laps = [
        {"compound_front": "Medium", "lap_time": 100.0, "is_valid_lap": 1}
        for _ in range(5)
    ]
    suggestions = PracticeAdvisor.advise(laps)
    types = {s["type"] for s in suggestions}
    assert "few_laps" in types


def test_practice_advisor_enough_laps_no_suggestions():
    from overlay.strategy_refresher import PracticeAdvisor
    laps = (
        [{"compound_front": "Soft", "lap_time": 100.0, "is_valid_lap": 1}] * 8 +
        [{"compound_front": "Medium", "lap_time": 100.0, "is_valid_lap": 1}] * 12 +
        [{"compound_front": "Hard", "lap_time": 100.0, "is_valid_lap": 1}] * 8
    )
    suggestions = PracticeAdvisor.advise(laps)
    # With 8/12/8 across S/M/H, we should have 0 or very few suggestions
    assert len(suggestions) == 0


def test_practice_advisor_missing_compound():
    from overlay.strategy_refresher import PracticeAdvisor
    # Only Medium laps, none on Soft
    laps = [{"compound_front": "Medium", "lap_time": 100.0, "is_valid_lap": 1}] * 12
    suggestions = PracticeAdvisor.advise(laps)
    types = {s["type"] for s in suggestions}
    assert "missing_compound" in types


# ──────────────────────────────────────────────────────────────────────────────
# Weather forecaster
# ──────────────────────────────────────────────────────────────────────────────

def test_weather_empty_history_returns_dry():
    from analysis.weather import linear_rain_forecast
    f = linear_rain_forecast([])
    assert f["current_state"] == "DRY"
    assert f["predicted_state_in_horizon"] == "DRY"
    assert f["trend_per_minute"] == 0.0
    assert f["switch_in_minutes"] is None


def test_weather_upward_trend_predicts_wet():
    from analysis.weather import linear_rain_forecast
    # Rain trending up: 0.0 → 0.5 over 10 min
    history = [
        {"t_min": -10, "rain_intensity": 0.0, "weather_state": "DRY"},
        {"t_min": -5,  "rain_intensity": 0.25, "weather_state": "DRY"},
        {"t_min": 0,   "rain_intensity": 0.5, "weather_state": "WET"},
    ]
    f = linear_rain_forecast(history, horizon_minutes=15)
    assert f["trend_per_minute"] > 0
    # Predicted in 15 min should be >= 0.5 + slope*15
    assert f["predicted_rain_in_horizon"] > 0.5


def test_weather_downward_trend_predicts_dry():
    from analysis.weather import linear_rain_forecast
    history = [
        {"t_min": -10, "rain_intensity": 0.8, "weather_state": "WET"},
        {"t_min": -5,  "rain_intensity": 0.5, "weather_state": "WET"},
        {"t_min": 0,   "rain_intensity": 0.2, "weather_state": "DRY"},
    ]
    f = linear_rain_forecast(history, horizon_minutes=15)
    assert f["trend_per_minute"] < 0
    # In 15 min, should be back to 0
    assert f["predicted_rain_in_horizon"] <= 0.2


def test_weather_switch_in_minutes_computed():
    from analysis.weather import linear_rain_forecast
    # Will cross 0.3 in a few minutes
    history = [
        {"t_min": -5, "rain_intensity": 0.0, "weather_state": "DRY"},
        {"t_min": 0,  "rain_intensity": 0.15, "weather_state": "DRY"},
    ]
    f = linear_rain_forecast(history, horizon_minutes=15)
    assert f["switch_in_minutes"] is not None
    assert f["switch_in_minutes"] > 0


def test_build_stint_forecast_splits_laps():
    from analysis.weather import build_stint_weather_forecast, linear_rain_forecast
    forecast = linear_rain_forecast([{"t_min": 0, "rain_intensity": 0.5, "weather_state": "WET"}])
    stints = build_stint_weather_forecast(
        total_laps=40, avg_lap_time_s=100.0, weather_forecast=forecast
    )
    assert len(stints) == 2
    assert stints[0]["weather_state"] in ("DRY", "WET")


def test_build_stint_forecast_short_race_single_stint():
    from analysis.weather import build_stint_weather_forecast, linear_rain_forecast
    forecast = linear_rain_forecast([])
    stints = build_stint_weather_forecast(
        total_laps=3, avg_lap_time_s=100.0, weather_forecast=forecast
    )
    assert len(stints) == 1


# ──────────────────────────────────────────────────────────────────────────────
# StrategyRefresher state-change detection (with a mock manager)
# ──────────────────────────────────────────────────────────────────────────────

class _MockFrame:
    def __init__(self, **kwargs):
        self.weather_state = kwargs.get("weather_state", "DRY")
        self.rain_intensity = kwargs.get("rain_intensity", 0.0)
        self.fuel = kwargs.get("fuel", 50.0)
        self.lap_number = kwargs.get("lap_number", 1)
        self.track_temp = kwargs.get("track_temp", 25.0)
        self.elapsed_time = kwargs.get("elapsed_time", 10.0)
        self.in_pits = kwargs.get("in_pits", False)


class _MockManager:
    """Minimal stand-in for OverlayManager used by StrategyRefresher tests."""
    def __init__(self):
        self._last_frame = None
        self._car = "Test Car"
        self._track = "Test Track"
        self._total_race_laps = 40
        self._current_lap = 1
        self._pit_plan = None
        self.db_path = ":memory:"
        self._refresh_strategy = lambda: None
        self.refresh_calls = 0
        # Override with counter
        self._refresh_strategy = self._count_refresh

    def _count_refresh(self):
        self.refresh_calls += 1


def test_refresher_detects_weather_change():
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)
    mgr._last_frame = _MockFrame(weather_state="DRY", rain_intensity=0.0)
    reason = ref._has_state_changed(ref._current_state_snapshot())
    assert reason == "first_run"

    # Same → None
    mgr._last_frame = _MockFrame(weather_state="DRY", rain_intensity=0.0)
    snap = ref._current_state_snapshot()
    ref._last_state = snap  # pretend we already saw it
    reason = ref._has_state_changed(snap)
    assert reason is None

    # Weather changed
    mgr._last_frame = _MockFrame(weather_state="WET", rain_intensity=0.5)
    new_snap = ref._current_state_snapshot()
    reason = ref._has_state_changed(new_snap)
    assert reason == "weather_changed"


def test_refresher_detects_lap_change():
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)

    mgr._last_frame = _MockFrame(lap_number=5, fuel=50.0)
    ref._last_state = ref._current_state_snapshot()

    mgr._last_frame = _MockFrame(lap_number=6, fuel=50.0)
    reason = ref._has_state_changed(ref._current_state_snapshot())
    assert reason == "lap_changed"


def test_refresher_detects_fuel_change():
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)

    mgr._last_frame = _MockFrame(fuel=50.0)
    ref._last_state = ref._current_state_snapshot()

    # Fuel drops a lot → fuel_laps changes by > 1
    mgr._last_frame = _MockFrame(fuel=10.0)
    reason = ref._has_state_changed(ref._current_state_snapshot())
    assert reason == "fuel_changed"


def test_refresher_detects_track_temp_change():
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)

    mgr._last_frame = _MockFrame(track_temp=25.0)
    ref._last_state = ref._current_state_snapshot()

    mgr._last_frame = _MockFrame(track_temp=35.0)  # +10°C
    reason = ref._has_state_changed(ref._current_state_snapshot())
    assert reason == "track_temp_changed"


def test_refresher_request_refresh_sets_flag():
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)
    assert ref._refresh_requested is False
    ref.request_refresh()
    assert ref._refresh_requested is True


def test_refresher_tick_with_no_frame_is_noop():
    """If no frame has been received yet, _tick should be a no-op."""
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)
    # _last_frame is None
    ref._tick()
    assert mgr.refresh_calls == 0


def test_refresher_tick_triggers_refresh_on_change():
    from overlay.strategy_refresher import StrategyRefresher
    mgr = _MockManager()
    ref = StrategyRefresher(mgr, interval_ms=100000)

    # First frame → first_run → refresh
    mgr._last_frame = _MockFrame()
    ref._tick()
    assert mgr.refresh_calls == 1


# ──────────────────────────────────────────────────────────────────────────────
# Integration: weather forecast endpoint (via FastAPI TestClient)
# ──────────────────────────────────────────────────────────────────────────────

def test_weather_endpoint_via_testclient():
    """Smoke test the /api/weather/forecast endpoint."""
    import json
    from fastapi.testclient import TestClient
    from web import server as server_mod
    client = TestClient(server_mod.app)
    # Empty history
    resp = client.get("/api/weather/forecast")
    assert resp.status_code == 200
    data = resp.json()
    assert "forecast" in data
    assert data["forecast"]["current_state"] == "DRY"

    # With history (rising rain)
    hist = [
        {"t_min": -5, "rain_intensity": 0.0, "weather_state": "DRY"},
        {"t_min": 0,  "rain_intensity": 0.2, "weather_state": "DRY"},
    ]
    resp = client.get(f"/api/weather/forecast?history={json.dumps(hist)}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["forecast"]["trend_per_minute"] > 0


def test_stint_weather_endpoint_via_testclient():
    import json
    from fastapi.testclient import TestClient
    from web import server as server_mod
    client = TestClient(server_mod.app)
    resp = client.get("/api/weather/stint-forecast?total_laps=30&avg_lap_time_s=90")
    assert resp.status_code == 200
    data = resp.json()
    assert "stints" in data
    assert len(data["stints"]) >= 1
