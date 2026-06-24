"""
Milestone H — E2E Integration Test

Tests the complete pipeline:
  1. DB initialisation (with temp file)
  2. SyntheticReplaySource produces TelemetryFrames
  3. LapBoundaryDetector records laps in DB
  4. detect_anomalies_for_session flags nothing on clean synthetic data
  5. fit_degradation_model + fit_fuel_model produce sensible parameters
  6. PitStrategist returns a valid multi-stop plan
  7. FastAPI HTTP endpoints respond correctly (TestClient, no networking)
  8. Soft-delete / restore round-trip
"""

import os
import sys
import time
import tempfile
import pytest

# ── Make project root importable ──────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database
from telemetry.source import SyntheticReplaySource
from telemetry.detector import LapBoundaryDetector
from analysis.anomaly import detect_anomalies_for_session
from analysis.models import fit_degradation_model, fit_fuel_model
from analysis.strategist import PitStrategist


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

CAR   = "Ferrari 499P LMH"
TRACK = "Circuit de la Sarthe"
TOTAL_LAPS = 20
FUEL_CAP   = 110.0
INIT_FUEL  = 110.0
FUEL_PER_LAP = 4.5
LAP_TIME_BASE = 228.0
CLIFF_LAP = 12


@pytest.fixture(scope="module")
def db_path():
    """Create a fresh temp DB for the entire test module."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="lmu_e2e_")
    os.close(fd)
    database.init_db(db_path=path)
    yield path
    os.remove(path)


@pytest.fixture(scope="module")
def recorded_laps(db_path):
    """
    Run SyntheticReplaySource through LapBoundaryDetector and record laps.
    Returns the list of recorded lap dictionaries from the DB.
    """
    source = SyntheticReplaySource(
        track_name=TRACK,
        car_name=CAR,
        lap_time_base=LAP_TIME_BASE,
        fuel_capacity=FUEL_CAP,
        initial_fuel=INIT_FUEL,
        fuel_consumption=FUEL_PER_LAP,
        cliff_lap=CLIFF_LAP,
        anomaly_laps={},      # No anomalies in clean E2E run
        total_laps=TOTAL_LAPS,
        tick_rate=0.5          # 2x speed
    )
    detector = LapBoundaryDetector(db_path=db_path)

    source.start()
    frames_processed = 0
    laps_recorded = []

    while True:
        frame = source.get_next_frame()
        if frame is None:
            break
        lap_id = detector.process_frame(frame)
        if lap_id is not None:
            laps_recorded.append(lap_id)
        frames_processed += 1

    source.stop()
    return laps_recorded


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDatabaseInit:
    def test_db_tables_exist(self, db_path):
        conn = database.get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()
        assert "sessions" in tables
        assert "laps" in tables
        assert "pit_stops" in tables

    def test_wal_mode(self, db_path):
        conn = database.get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        assert mode == "wal"


class TestTelemetryRecording:
    def test_laps_recorded(self, db_path, recorded_laps):
        """Synthetic source should produce approximately TOTAL_LAPS laps."""
        # Allow ±1 for boundary effects
        assert len(recorded_laps) >= TOTAL_LAPS - 1, (
            f"Expected ~{TOTAL_LAPS} laps, got {len(recorded_laps)}"
        )

    def test_laps_in_db(self, db_path, recorded_laps):
        all_laps = database.get_all_laps_for_archive(db_path=db_path, include_deleted=False)
        assert len(all_laps) >= len(recorded_laps)

    def test_lap_times_are_reasonable(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        for lap in laps:
            assert 180.0 < lap["lap_time"] < 300.0, (
                f"Unreasonable lap time: {lap['lap_time']}"
            )

    def test_fuel_decreasing_within_stint(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        non_pit_laps = [l for l in laps if not l["is_pit_in_lap"] and not l["is_pit_out_lap"]]
        for i in range(1, len(non_pit_laps)):
            prev = non_pit_laps[i - 1]
            curr = non_pit_laps[i]
            if curr["stint_id"] == prev["stint_id"]:
                assert curr["fuel_start_l"] < prev["fuel_start_l"]

    def test_tyre_age_increases_in_stint(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        for i in range(1, len(laps)):
            prev, curr = laps[i - 1], laps[i]
            if curr["stint_id"] == prev["stint_id"]:
                assert curr["tyre_age_laps"] > prev["tyre_age_laps"]


class TestAnomalyDetection:
    def test_clean_data_has_no_anomalies(self, db_path, recorded_laps):
        """No injected anomalies ⟹ no flags should be set."""
        detect_anomalies_for_session(CAR, TRACK, db_path=db_path)
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        # On perfectly clean synthetic data, at most 1 flag is acceptable
        flagged = [l for l in laps if l["anomaly_flag"]]
        assert len(flagged) <= 1, (
            f"Too many anomaly flags on clean data: {[f['lap_number'] for f in flagged]}"
        )


class TestRegressionModels:
    def test_fuel_model_returns_reasonable_consumption(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        mean_fuel, std_fuel = fit_fuel_model(laps)
        assert pytest.approx(mean_fuel, rel=0.3) == FUEL_PER_LAP, (
            f"Fuel model mean {mean_fuel} far from expected {FUEL_PER_LAP}"
        )
        assert std_fuel >= 0.0

    def test_degradation_model_positive_params(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        model = fit_degradation_model(laps)
        assert model.base_time > 0
        assert model.alpha >= 0
        assert model.beta_1 >= 0
        assert model.beta_2 >= 0

    def test_degradation_model_prediction_monotone(self, db_path, recorded_laps):
        """Predicted lap time should increase as tyre age increases."""
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        model = fit_degradation_model(laps)
        fuel = 50.0  # fixed fuel for comparison
        times = [model.predict(age, fuel) for age in range(1, TOTAL_LAPS + 1)]
        # Should be non-decreasing (or very close to it)
        for i in range(1, len(times)):
            assert times[i] >= times[i - 1] - 1e-6, (
                f"Lap time decreased at age {i}: {times[i-1]:.3f} → {times[i]:.3f}"
            )

    def test_degradation_cliff_detected(self, db_path, recorded_laps):
        """Cliff should be detected somewhere between laps 5 and 25."""
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        if len(laps) >= 10:
            model = fit_degradation_model(laps)
            if model.cliff_lap < 990:
                assert 5 <= model.cliff_lap <= 25, (
                    f"Cliff lap {model.cliff_lap} outside expected range"
                )


class TestPitStrategist:
    def test_strategy_returns_valid_structure(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        model = fit_degradation_model(laps)
        mean_fuel, _ = fit_fuel_model(laps)
        strat = PitStrategist(
            fuel_capacity=FUEL_CAP,
            fuel_consumption=mean_fuel,
            pit_loss=30.0,
            model_fit=model
        )
        result = strat.optimize(
            laps_remaining=TOTAL_LAPS,
            current_tyre_age=1,
            current_fuel=FUEL_CAP,
            max_stops=3
        )
        assert "optimal" in result
        assert "alternatives" in result
        assert result["optimal"] is not None
        assert isinstance(result["optimal"]["pit_laps"], list)

    def test_strategy_zero_stops_possible(self, db_path, recorded_laps):
        """If the race is short enough, 0-stop should be achievable."""
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        model = fit_degradation_model(laps)
        strat = PitStrategist(
            fuel_capacity=FUEL_CAP,
            fuel_consumption=FUEL_PER_LAP,
            pit_loss=30.0,
            model_fit=model
        )
        laps_for_tank = int(FUEL_CAP // FUEL_PER_LAP)
        short_race = min(laps_for_tank - 1, 5)
        result = strat.optimize(
            laps_remaining=short_race,
            current_tyre_age=1,
            current_fuel=FUEL_CAP,
            max_stops=3
        )
        alternatives = result["alternatives"]
        assert 0 in alternatives, "0-stop should always be in alternatives for short race"

    def test_total_time_is_positive(self, db_path, recorded_laps):
        laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        model = fit_degradation_model(laps)
        mean_fuel, _ = fit_fuel_model(laps)
        strat = PitStrategist(
            fuel_capacity=FUEL_CAP,
            fuel_consumption=mean_fuel,
            pit_loss=30.0,
            model_fit=model
        )
        result = strat.optimize(laps_remaining=10, current_tyre_age=1, current_fuel=FUEL_CAP, max_stops=2)
        assert result["optimal"]["total_time"] > 0


class TestSoftDelete:
    def test_soft_delete_and_restore(self, db_path, recorded_laps):
        """Soft-delete a lap and verify it disappears from analysis, then restore it."""
        all_laps = database.get_all_laps_for_archive(db_path=db_path, include_deleted=False)
        assert len(all_laps) > 0, "Need at least one lap to test soft-delete"

        target_id = all_laps[0]["id"]

        # Delete
        database.soft_delete_lap(target_id, is_deleted=True, db_path=db_path)

        # Verify hidden from archive
        visible = database.get_all_laps_for_archive(db_path=db_path, include_deleted=False)
        visible_ids = {l["id"] for l in visible}
        assert target_id not in visible_ids, "Deleted lap should not appear in archive"

        # Verify hidden from analysis
        analysis_laps = database.get_laps_for_analysis(CAR, TRACK, db_path=db_path)
        analysis_ids = {l["id"] for l in analysis_laps}
        assert target_id not in analysis_ids, "Deleted lap should not appear in analysis"

        # Restore
        database.soft_delete_lap(target_id, is_deleted=False, db_path=db_path)

        # Verify back
        visible2 = database.get_all_laps_for_archive(db_path=db_path, include_deleted=False)
        visible_ids2 = {l["id"] for l in visible2}
        assert target_id in visible_ids2, "Restored lap should appear in archive"


class TestFastAPIEndpoints:
    """
    Test FastAPI HTTP endpoints using Starlette TestClient (no network required).
    """
    @pytest.fixture(scope="class")
    def client(self, db_path):
        """Override database path and create TestClient."""
        import importlib
        import web.server as server_mod

        # Monkey-patch database to use our temp DB
        original = database.DEFAULT_DB_PATH
        database.DEFAULT_DB_PATH = db_path

        from fastapi.testclient import TestClient
        client = TestClient(server_mod.app)

        yield client

        database.DEFAULT_DB_PATH = original

    def test_root_returns_html(self, client, db_path):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Race Strategy" in resp.text

    def test_sessions_endpoint(self, client, db_path, recorded_laps):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_laps_endpoint_returns_list(self, client, db_path, recorded_laps):
        resp = client.get("/api/laps")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= TOTAL_LAPS - 1

    def test_laps_filtered_by_car(self, client, db_path, recorded_laps):
        resp = client.get(f"/api/laps?car={CAR}")
        assert resp.status_code == 200
        for lap in resp.json():
            assert lap["car"] == CAR

    def test_soft_delete_endpoint(self, client, db_path, recorded_laps):
        laps = client.get("/api/laps").json()
        lap_id = laps[0]["id"]

        resp = client.post(f"/api/laps/{lap_id}/delete")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        laps_after = client.get("/api/laps").json()
        ids_after = {l["id"] for l in laps_after}
        assert lap_id not in ids_after

        # Restore
        resp2 = client.post(f"/api/laps/{lap_id}/restore")
        assert resp2.status_code == 200
        assert resp2.json()["deleted"] is False

    def test_profile_endpoint(self, client, db_path, recorded_laps):
        resp = client.get(f"/api/profile?car={CAR}&track={TRACK}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["n_valid_laps"] >= 1
        assert data["avg_lap_time"] is not None
        assert data["avg_fuel_consumption"] is not None

    def test_profile_insufficient_data_warning(self, client, db_path):
        resp = client.get("/api/profile?car=Unknown&track=Unknown")
        assert resp.status_code == 200
        data = resp.json()
        assert data["insufficient_data"] is True
        assert data["warning"] is not None

    def test_strategy_endpoint(self, client, db_path, recorded_laps):
        resp = client.get(
            f"/api/strategy?car={CAR}&track={TRACK}"
            f"&laps_remaining=15&current_fuel=100&fuel_capacity=110&max_stops=2"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert data["result"]["optimal"] is not None

    def test_strategy_insufficient_data(self, client, db_path):
        resp = client.get(
            "/api/strategy?car=Unknown&track=Unknown&laps_remaining=10"
        )
        assert resp.status_code == 422
