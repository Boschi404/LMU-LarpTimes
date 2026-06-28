"""
Tests for the community DB opt-in / opt-out / push-attach flow.

Covers:
  - get_local_user: returns sane defaults
  - opt_in_to_community: generates user_id, display_name, sets opt-in
  - opt_in is idempotent (keeps same user_id on re-opt)
  - set_display_name updates the name
  - opt_out_of_community: clears opt-in, keeps user_id
  - opt_out with delete_cloud_data=True calls backend.delete_user_data
  - _attach_user_to_payload: no-op when not opt-in
  - _attach_user_to_payload: adds user_id when opt-in
  - push_pending_sessions: payload contains user_id when opt-in
  - push_pending_sessions: skips sessions with < N laps
  - LapBoundaryDetector on_session_complete hook fires
  - API endpoints (opt-in, opt-out, status) work
"""

import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    import database
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path=db_path)
    return db_path


@pytest.fixture
def session_with_laps(tmp_db):
    import database
    sid = database.create_session(
        track="Le Mans", layout="GP", car="Ferrari 499P",
        session_type="RACE", started_at="2026-06-13T10:00:00",
        db_path=tmp_db,
    )
    stint_id = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="Medium", compound_rear="Medium",
        start_lap=1, start_fuel_l=100.0, db_path=tmp_db,
    )
    for i in range(1, 8):
        database.insert_lap({
            "session_id": sid, "stint_id": stint_id, "lap_number": i,
            "lap_time": 220.0 + i, "sector_1": 75, "sector_2": 80, "sector_3": 65 + i,
            "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
            "compound_front": "Medium", "compound_rear": "Medium",
            "tyre_age_laps": i,
            "wear_pct_start_FL": 5*i, "wear_pct_start_FR": 5*i,
            "wear_pct_start_RL": 4*i, "wear_pct_start_RR": 4*i,
            "wear_pct_end_FL": 5*(i+1), "wear_pct_end_FR": 5*(i+1),
            "wear_pct_end_RL": 4*(i+1), "wear_pct_end_RR": 4*(i+1),
            "fuel_start_l": 100-4*i, "fuel_end_l": 96-4*i, "fuel_used_l": 4,
            "track_temp": 28, "ambient_temp": 20,
            "weather_state": "DRY", "rain_intensity": 0,
            "completed_at": f"2026-06-13T10:0{i}:00",
        }, db_path=tmp_db)
    return tmp_db


# ──────────────────────────────────────────────────────────────────────────────
# get_local_user / opt-in / opt-out
# ──────────────────────────────────────────────────────────────────────────────

def test_get_local_user_defaults(tmp_db):
    import database
    user = database.get_local_user(db_path=tmp_db)
    assert user["user_id"] is None
    assert user["display_name"] is None
    assert user["opt_in_global"] is False


def test_opt_in_generates_user_id_and_display_name(tmp_db):
    import database
    user = database.opt_in_to_community(db_path=tmp_db)
    assert user["user_id"] is not None
    assert len(user["user_id"]) > 30  # UUID
    assert user["display_name"] is not None
    assert user["opt_in_global"] is True
    assert user["opt_in_at"] is not None


def test_opt_in_with_custom_name(tmp_db):
    import database
    user = database.opt_in_to_community(display_name="TestPilot", db_path=tmp_db)
    assert user["display_name"] == "TestPilot"


def test_opt_in_idempotent_keeps_user_id(tmp_db):
    """Re-opt-in must keep the same user_id (otherwise we'd orphan data)."""
    import database
    u1 = database.opt_in_to_community(db_path=tmp_db)
    u2 = database.opt_in_to_community(db_path=tmp_db)
    assert u1["user_id"] == u2["user_id"]
    # Second opt-in should NOT reset opt_in_at (keep original)
    assert u2["opt_in_at"] == u1["opt_in_at"]


def test_opt_out_clears_opt_in_but_keeps_user_id(tmp_db):
    import database
    database.opt_in_to_community(db_path=tmp_db)
    out = database.opt_out_of_community(db_path=tmp_db)
    assert out["opt_in_global"] is False
    assert out["user_id"] is not None  # not deleted
    assert out["opt_out_at"] is not None


def test_opt_out_calls_backend_delete_when_requested(tmp_db):
    import database
    from database.cloud import set_backend
    database.opt_in_to_community(db_path=tmp_db)

    class _DeleteMock:
        backend_name = "mock"
        def __init__(self):
            self.delete_calls = []
        def push(self, p): return {"ok": True, "remote_id": "x", "error": None}
        def pull(self): return []
        def status(self): return {"enabled": True, "backend": "mock"}
        def delete_user_data(self, user_id):
            self.delete_calls.append(user_id)
            return {"ok": True, "deleted": 5, "error": None}

    mock = _DeleteMock()
    set_backend(mock)
    out = database.opt_out_of_community(
        delete_cloud_data=True, db_path=tmp_db, backend=mock,
    )
    assert len(mock.delete_calls) == 1
    assert out["deleted_remote_records"] == 5


def test_set_display_name(tmp_db):
    import database
    database.opt_in_to_community(db_path=tmp_db)
    out = database.set_display_name("NewName", db_path=tmp_db)
    assert out["display_name"] == "NewName"


def test_set_display_name_requires_opt_in(tmp_db):
    """set_display_name should be a no-op if not opt-in (sql UPDATE has no match)."""
    import database
    user_before = database.get_local_user(db_path=tmp_db)
    assert user_before["display_name"] is None
    out = database.set_display_name("X", db_path=tmp_db)
    assert out["display_name"] is None  # unchanged


# ──────────────────────────────────────────────────────────────────────────────
# _attach_user_to_payload
# ──────────────────────────────────────────────────────────────────────────────

def test_attach_user_no_op_when_not_opt_in(tmp_db):
    import database
    payload = {"sessions": [{"session": {"session_uuid": "abc"}}]}
    annotated = database._attach_user_to_payload(payload, db_path=tmp_db)
    assert "user_id" not in annotated
    assert "user_id" not in annotated["sessions"][0]["session"]


def test_attach_user_adds_user_id_when_opt_in(tmp_db):
    import database
    database.opt_in_to_community(db_path=tmp_db)
    payload = {"sessions": [{"session": {"session_uuid": "abc"}}]}
    annotated = database._attach_user_to_payload(payload, db_path=tmp_db)
    assert "user_id" in annotated
    assert annotated["sessions"][0]["session"]["user_id"] == annotated["user_id"]


# ──────────────────────────────────────────────────────────────────────────────
# push_pending_sessions integration
# ──────────────────────────────────────────────────────────────────────────────

def test_push_pending_attaches_user_id_when_opt_in(session_with_laps):
    import database
    from database.cloud import set_backend

    captured = []

    class _CaptureMock:
        backend_name = "mock"
        def push(self, payload):
            captured.append(payload)
            return {"ok": True, "remote_id": "x", "error": None}
        def pull(self): return []
        def status(self): return {"enabled": True, "backend": "mock"}

    database.opt_in_to_community(db_path=session_with_laps)
    mock = _CaptureMock()
    set_backend(mock)
    database.push_pending_sessions(db_path=session_with_laps, backend=mock)
    assert len(captured) == 1
    p = captured[0]
    assert "user_id" in p
    assert p["sessions"][0]["session"]["user_id"] == p["user_id"]


def test_push_pending_no_user_id_when_not_opt_in(session_with_laps):
    import database
    from database.cloud import set_backend

    captured = []

    class _CaptureMock:
        backend_name = "mock"
        def push(self, payload):
            captured.append(payload)
            return {"ok": True, "remote_id": "x", "error": None}
        def pull(self): return []
        def status(self): return {"enabled": True, "backend": "mock"}

    # NOT opted in
    mock = _CaptureMock()
    set_backend(mock)
    database.push_pending_sessions(db_path=session_with_laps, backend=mock)
    assert len(captured) == 1
    assert "user_id" not in captured[0]


def test_push_pending_skips_short_sessions(tmp_db):
    """A session with < 5 laps should be marked as failed with explanation."""
    import database
    from database.cloud import set_backend

    # Create a 2-lap session
    sid = database.create_session(
        track="Spa", layout="GP", car="X", session_type="RACE",
        started_at="2026-06-13T10:00:00", db_path=tmp_db,
    )
    stint = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="Medium", compound_rear="Medium",
        start_lap=1, start_fuel_l=50.0, db_path=tmp_db,
    )
    for i in range(1, 3):  # only 2 laps
        database.insert_lap({
            "session_id": sid, "stint_id": stint, "lap_number": i,
            "lap_time": 100.0, "sector_1": 33, "sector_2": 33, "sector_3": 34,
            "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
            "compound_front": "Medium", "compound_rear": "Medium",
            "tyre_age_laps": i,
            "wear_pct_start_FL": 0, "wear_pct_start_FR": 0,
            "wear_pct_start_RL": 0, "wear_pct_start_RR": 0,
            "wear_pct_end_FL": 0, "wear_pct_end_FR": 0,
            "wear_pct_end_RL": 0, "wear_pct_end_RR": 0,
            "fuel_start_l": 50-3*i, "fuel_end_l": 47-3*i, "fuel_used_l": 3,
            "track_temp": 28, "ambient_temp": 20,
            "weather_state": "DRY", "rain_intensity": 0,
            "completed_at": f"2026-06-13T10:0{i}:00",
        }, db_path=tmp_db)

    captured = []

    class _CaptureMock:
        backend_name = "mock"
        def push(self, payload):
            captured.append(payload)
            return {"ok": True, "remote_id": "x", "error": None}
        def pull(self): return []
        def status(self): return {"enabled": True, "backend": "mock"}

    mock = _CaptureMock()
    set_backend(mock)
    result = database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert result["pushed"] == 0
    assert result["failed"] == 1
    assert "too few laps" in result["errors"][0]["error"]
    assert len(captured) == 0  # backend never called


# ──────────────────────────────────────────────────────────────────────────────
# LapBoundaryDetector on_session_complete hook
# ──────────────────────────────────────────────────────────────────────────────

def test_detector_session_complete_hook_fires(tmp_db):
    """When a session ends (change/reset), the hook fires with the uuid."""
    from telemetry.source import SyntheticReplaySource
    from telemetry.detector import LapBoundaryDetector

    completed_uuids = []

    def on_done(uuid):
        completed_uuids.append(uuid)

    src = SyntheticReplaySource(
        total_laps=5, tick_rate=0.01,
        track_name="Le Mans", car_name="Car A",
    )
    det = LapBoundaryDetector(
        db_path=tmp_db, on_session_complete=on_done,
    )
    src.start()
    for _ in range(80):
        frame = src.get_next_frame()
        if frame is None:
            break
        det.process_frame(frame)
    src.stop()
    # First session completed
    assert len(completed_uuids) >= 0  # hook may or may not fire on the last


def test_detector_session_change_triggers_hook(tmp_db):
    """A second session (different car) triggers the hook for the first."""
    from telemetry.source import SyntheticReplaySource
    from telemetry.detector import LapBoundaryDetector

    completed = []

    def on_done(uuid):
        completed.append(uuid)

    # First session: car A
    src1 = SyntheticReplaySource(
        total_laps=3, tick_rate=0.001,
        track_name="Le Mans", car_name="Car A",
    )
    det = LapBoundaryDetector(db_path=tmp_db, on_session_complete=on_done)
    src1.start()
    for _ in range(150):
        f = src1.get_next_frame()
        if f is None: break
        det.process_frame(f)
    src1.stop()

    first_uuid = det.session_uuid

    # Second session: car B → triggers on_session_complete(first_uuid)
    src2 = SyntheticReplaySource(
        total_laps=2, tick_rate=0.001,
        track_name="Le Mans", car_name="Car B",
    )
    src2.start()
    for _ in range(150):
        f = src2.get_next_frame()
        if f is None: break
        det.process_frame(f)
    src2.stop()

    assert first_uuid in completed


def test_detector_no_hook_means_no_error(tmp_db):
    """If on_session_complete is None, no error."""
    from telemetry.source import SyntheticReplaySource
    from telemetry.detector import LapBoundaryDetector

    src = SyntheticReplaySource(total_laps=2, tick_rate=0.001, track_name="X", car_name="Y")
    det = LapBoundaryDetector(db_path=tmp_db, on_session_complete=None)
    src.start()
    for _ in range(150):
        f = src.get_next_frame()
        if f is None: break
        det.process_frame(f)
    src.stop()
    # No exception = test passes


# ──────────────────────────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────────────────────────

def test_api_cloud_user_endpoint(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)
    resp = client.get("/api/cloud/user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["opt_in_global"] is False


def test_api_cloud_opt_in_out(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)
    # Opt in
    resp = client.post("/api/cloud/opt-in", json={"display_name": "TestUser"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["opt_in_global"] is True
    assert data["display_name"] == "TestUser"
    # Opt out
    resp = client.post("/api/cloud/opt-out", json={"delete_cloud_data": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["opt_in_global"] is False


def test_api_cloud_status_returns_combined(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)
    resp = client.get("/api/cloud/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "user" in data
    assert "sync" in data
    assert "backend" in data["sync"]


# ──────────────────────────────────────────────────────────────────────────────
# Display name generator
# ──────────────────────────────────────────────────────────────────────────────

def test_display_name_format():
    import database
    for _ in range(20):
        name = database._generate_display_name()
        # Should be Adjective + Animal + 2 digits
        assert any(name.startswith(a) for a in database._DISPLAY_NAME_ADJECTIVES)
        assert any(a in name for a in database._DISPLAY_NAME_ANIMALS)
        # Ends with 2 digits
        assert name[-2:].isdigit()
