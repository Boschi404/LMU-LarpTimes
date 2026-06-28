"""
Milestone E — LiveSharedMemorySource stubbed tests.

These tests verify the LMU live source **without** requiring LMU or rFactor 2
running. They monkey-patch the vendored shared-memory modules so the source
can be exercised in isolation.

What we cover:
  - start() picks LMU when its shared memory reports a valid game version
  - start() falls back to rFactor 2 when LMU version is 0 and RF2 reports running
  - start() silently no-ops when neither sim is available
  - get_next_frame() parses an LMU frame into a TelemetryFrame
  - get_next_frame() parses an RF2 frame when active_api == "RF2"
  - stop() is safe to call even if start() never connected
  - get_next_frame() before start() returns None
"""

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers: build mock LMU/RF2 structures that mimic the vendored modules
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_lmu_data(
    game_version: int = 1,
    track_name: str = "Le Mans",
    car_name: str = "Ferrari 499P",
    lap_number: int = 5,
    fuel: float = 80.0,
    fuel_capacity: float = 110.0,
    lap_time: float = 215.5,
    track_temp: float = 28.0,
    ambient_temp: float = 20.0,
    raining: float = 0.0,
    in_pits: int = 0,
    pit_state: int = 0,
    sector: int = 1,
    lap_invalidated: int = 0,
    delta_best: float = 0.123,
    s1: float = 75.0,
    s2: float = 150.0,
):
    """Build an object that quacks like LMUData as the source uses it."""
    wheel = SimpleNamespace(mWear=0.85)
    telem = SimpleNamespace(
        mVehicleModel=car_name.encode("utf-8"),
        mVehicleName=car_name.encode("utf-8"),
        mFrontTireCompoundName=b"Medium",
        mRearTireCompoundName=b"Medium",
        mLapNumber=lap_number,
        mElapsedTime=1234.5,
        mFuel=fuel,
        mFuelCapacity=fuel_capacity,
        mWheels=[wheel] * 4,
        mLapInvalidated=bool(lap_invalidated),
        mDeltaBest=delta_best,
    )
    veh_scoring = SimpleNamespace(
        mIsPlayer=True,
        mInPits=bool(in_pits),
        mPitState=pit_state,
        mSector=sector,
        mLastSector1=s1,
        mLastSector2=s2,
        mLastLapTime=lap_time,
    )
    scoring_info = SimpleNamespace(
        mTrackName=track_name.encode("utf-8"),
        mTrackTemp=track_temp,
        mAmbientTemp=ambient_temp,
        mRaining=raining,
        mSession=9,  # RACE
        mNumVehicles=1,
    )
    telemetry = SimpleNamespace(
        playerVehicleIdx=0,
        telemInfo=[telem],
    )
    scoring = SimpleNamespace(
        scoringInfo=scoring_info,
        vehScoringInfo=[veh_scoring],
    )
    generic = SimpleNamespace(gameVersion=game_version)
    return SimpleNamespace(generic=generic, telemetry=telemetry, scoring=scoring)


def _install_mock_lmu(monkeypatch, lmu_data):
    """Patch telemetry.source so `from lmu_data import SimInfo` returns our mock."""
    # Create a fake lmu_data module
    fake_module = types.ModuleType("lmu_data")

    class FakeSimInfo:
        def __init__(self):
            self.LMUData = lmu_data
        def close(self):
            pass

    fake_module.SimInfo = FakeSimInfo

    # The source does sys.path.insert(0, .../pyLMUSharedMemory) at import time,
    # then "from lmu_data import SimInfo as LMUSimInfo" — so we inject into
    # sys.modules under the name "lmu_data".
    monkeypatch.setitem(sys.modules, "lmu_data", fake_module)
    return fake_module


def _install_mock_rf2(monkeypatch, running: bool = True, smem: bool = True):
    """Patch telemetry.source so `from sharedMemoryAPI import SimInfoAPI` works."""
    fake_module = types.ModuleType("sharedMemoryAPI")

    class FakeSimInfoAPI:
        def __init__(self):
            self._running = running
            self._smem = smem
            self.Rf2Scor = SimpleNamespace(
                mScoringInfo=SimpleNamespace(
                    mTrackName=b"Le Mans",
                    mTrackTemp=28.0,
                    mAmbientTemp=20.0,
                    mRaining=0.0,
                    mSession=9,
                )
            )
        def isRF2running(self):
            return self._running
        def isSharedMemoryAvailable(self):
            return self._smem
        def playersVehicleTelemetry(self):
            wheel = SimpleNamespace(mWear=0.9)
            return SimpleNamespace(
                mLapNumber=7,
                mElapsedTime=2000.0,
                mFuel=70.0,
                mFuelCapacity=110.0,
                mWheels=[wheel] * 4,
            )
        def playersVehicleScoring(self):
            return SimpleNamespace(
                mInPits=False,
                mPitState=0,
                mSector=1,
                mLastSector1=70.0,
                mLastSector2=140.0,
                mLastLapTime=210.0,
            )
        def vehicleName(self):
            return b"Ferrari 499P"
        def close(self):
            pass

    fake_module.SimInfoAPI = FakeSimInfoAPI
    monkeypatch.setitem(sys.modules, "sharedMemoryAPI", fake_module)
    return fake_module


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_returns_none_before_start():
    from telemetry.source import LiveSharedMemorySource
    src = LiveSharedMemorySource()
    # start() not called
    assert src.get_next_frame() is None
    src.stop()  # must be safe


def test_stop_is_safe_without_start():
    from telemetry.source import LiveSharedMemorySource
    src = LiveSharedMemorySource()
    src.stop()  # must not raise
    assert src.running is False


def test_live_source_uses_lmu_when_available(monkeypatch):
    from telemetry.source import LiveSharedMemorySource

    lmu_data = _make_mock_lmu_data(game_version=1)
    _install_mock_lmu(monkeypatch, lmu_data)

    src = LiveSharedMemorySource()
    src.start()
    assert src.active_api == "LMU"
    assert src.running is True

    frame = src.get_next_frame()
    assert frame is not None
    assert frame.track_name == "Le Mans"
    assert frame.car_name == "Ferrari 499P"
    assert frame.lap_number == 5
    assert frame.fuel == 80.0
    assert frame.fuel_capacity == 110.0
    assert frame.last_lap_time == 215.5
    assert frame.delta_best == pytest.approx(0.123)
    assert frame.session_type == "RACE"
    assert frame.weather_state == "DRY"
    assert frame.is_valid_lap is True
    assert frame.tyre_compounds == ["Medium", "Medium"]
    assert len(frame.tyre_wear) == 4

    src.stop()
    assert src.running is False


def test_live_source_falls_back_to_rf2_when_lmu_idle(monkeypatch):
    from telemetry.source import LiveSharedMemorySource

    # LMU present but game version == 0 (idle) → should fallback
    lmu_data = _make_mock_lmu_data(game_version=0)
    _install_mock_lmu(monkeypatch, lmu_data)
    _install_mock_rf2(monkeypatch, running=True, smem=True)

    src = LiveSharedMemorySource()
    src.start()
    assert src.active_api == "RF2"
    assert src.lmu_info is None  # LMU was abandoned

    frame = src.get_next_frame()
    assert frame is not None
    assert frame.fuel == 70.0
    assert frame.lap_number == 7
    assert frame.session_type == "RACE"
    src.stop()


def test_live_source_no_op_when_neither_available(monkeypatch):
    from telemetry.source import LiveSharedMemorySource

    # LMU idle + RF2 not running
    lmu_data = _make_mock_lmu_data(game_version=0)
    _install_mock_lmu(monkeypatch, lmu_data)
    _install_mock_rf2(monkeypatch, running=False, smem=False)

    src = LiveSharedMemorySource()
    src.start()
    assert src.active_api is None
    assert src.get_next_frame() is None
    src.stop()


def test_live_source_lmu_frame_in_pits_flag(monkeypatch):
    from telemetry.source import LiveSharedMemorySource

    lmu_data = _make_mock_lmu_data(in_pits=1, pit_state=2)
    _install_mock_lmu(monkeypatch, lmu_data)

    src = LiveSharedMemorySource()
    src.start()
    frame = src.get_next_frame()
    assert frame.in_pits is True
    assert frame.pit_state == 2
    src.stop()


def test_live_source_lmu_weather_wet(monkeypatch):
    from telemetry.source import LiveSharedMemorySource

    lmu_data = _make_mock_lmu_data(raining=0.7)
    _install_mock_lmu(monkeypatch, lmu_data)

    src = LiveSharedMemorySource()
    src.start()
    frame = src.get_next_frame()
    assert frame.weather_state == "WET"
    assert frame.rain_intensity == pytest.approx(0.7)
    src.stop()


def test_live_source_lmu_session_qualifying(monkeypatch):
    from telemetry.source import LiveSharedMemorySource

    lmu_data = _make_mock_lmu_data()
    lmu_data.scoring.scoringInfo.mSession = 6  # QUALIFYING
    _install_mock_lmu(monkeypatch, lmu_data)

    src = LiveSharedMemorySource()
    src.start()
    frame = src.get_next_frame()
    assert frame.session_type == "QUALIFYING"
    src.stop()


def test_live_source_lmu_handles_exception(monkeypatch):
    """If LMU raises mid-frame, source should return None, not crash."""
    from telemetry.source import LiveSharedMemorySource

    # Build a class whose .scoring property raises — used to simulate a broken
    # shared-memory pointer after the source has selected LMU.
    class _BoomScoring:
        @property
        def scoring(self):
            raise RuntimeError("boom")

    _BoomScoring.generic = _make_mock_lmu_data().generic
    _BoomScoring.telemetry = _make_mock_lmu_data().telemetry
    _BoomScoring.scoring = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

    class _FakeSimInfo:
        def __init__(self):
            self.LMUData = _BoomScoring()
        def close(self):
            pass

    fake_module = types.ModuleType("lmu_data")
    fake_module.SimInfo = _FakeSimInfo
    monkeypatch.setitem(sys.modules, "lmu_data", fake_module)

    src = LiveSharedMemorySource()
    src.start()
    assert src.active_api == "LMU"
    assert src.get_next_frame() is None  # exception swallowed
    src.stop()
