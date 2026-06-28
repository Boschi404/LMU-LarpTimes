"""
Tests for the cloud sync layer (database/cloud.py +
database.push_pending_sessions / pull_remote_sessions / get_sync_status).

Covers:
  - NullSync returns empty/disabled
  - MockSync roundtrip: push → pull
  - set_backend() / get_backend()
  - backend_from_config() builds the right backend per config
  - push_pending_sessions() marks sessions as 'pushed' on success
  - push_pending_sessions() marks 'failed' on backend error
  - pull_remote_sessions() dedups via import_sessions
  - get_sync_status() returns correct counts
  - Migration creates sync_queue on existing DBs
"""

import os
import sys
import json
import pytest

# Ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Fresh DB with one session and 5 laps."""
    import database
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path=db_path)
    sid = database.create_session(
        track="Le Mans", layout="GP", car="Ferrari 499P",
        session_type="RACE", started_at="2026-06-13T10:00:00",
        db_path=db_path,
    )
    stint_id = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="Medium", compound_rear="Medium",
        start_lap=1, start_fuel_l=100.0, db_path=db_path,
    )
    for i in range(1, 6):
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
        }, db_path=db_path)
    return db_path


class _MockBackend:
    """In-memory mock implementing the CloudSync interface."""
    def __init__(self, fail_push=False, transform_on_pull=None):
        self._store = {}
        self.fail_push = fail_push
        self.transform_on_pull = transform_on_pull
        self.push_calls = 0
        self.pull_calls = 0
        self.backend_name = "mock"

    def push(self, payload):
        self.push_calls += 1
        if self.fail_push:
            return {"ok": False, "remote_id": None, "error": "mock failure"}
        # Store the first session's uuid as key
        first_uuid = payload["sessions"][0]["session"]["session_uuid"]
        self._store[first_uuid] = payload
        return {"ok": True, "remote_id": first_uuid, "error": None}

    def pull(self):
        self.pull_calls += 1
        out = list(self._store.values())
        if self.transform_on_pull:
            out = [self.transform_on_pull(p) for p in out]
        return out

    def status(self):
        return {
            "enabled": True,
            "backend": self.backend_name,
            "message": f"Mock with {len(self._store)} stored payloads",
        }


# ──────────────────────────────────────────────────────────────────────────────
# NullSync
# ──────────────────────────────────────────────────────────────────────────────

def test_null_sync_status():
    from database.cloud import NullSync
    s = NullSync()
    status = s.status()
    assert status["enabled"] is False
    assert s.push({"version": 1, "sessions": []})["ok"] is False
    assert s.pull() == []


# ──────────────────────────────────────────────────────────────────────────────
# Backend factory
# ──────────────────────────────────────────────────────────────────────────────

def test_backend_from_config_null():
    from database.cloud import backend_from_config
    b = backend_from_config({"backend": "null"})
    assert isinstance(b, type(backend_from_config({})))


def test_backend_from_config_turso():
    from database.cloud import backend_from_config, TursoSync
    b = backend_from_config({
        "backend": "turso",
        "turso": {"url": "libsql://foo", "auth_token": "tok"},
    })
    assert isinstance(b, TursoSync)
    assert b.url == "libsql://foo"
    assert b.auth_token == "tok"


def test_backend_from_config_duckdb():
    from database.cloud import backend_from_config, DuckDBR2Sync
    b = backend_from_config({
        "backend": "duckdb-r2",
        "duckdb_r2": {
            "endpoint": "https://r2.example",
            "access_key": "ak", "secret_key": "sk",
            "bucket": "my-bucket", "prefix": "x/",
        },
    })
    assert isinstance(b, DuckDBR2Sync)
    assert b.bucket == "my-bucket"


def test_backend_from_config_http():
    from database.cloud import backend_from_config, HTTPSync
    b = backend_from_config({
        "backend": "http",
        "http": {"base_url": "https://api.example.com", "auth_token": "abc"},
    })
    assert isinstance(b, HTTPSync)
    assert b.auth_token == "abc"


def test_set_get_backend():
    from database.cloud import set_backend, get_backend, NullSync
    original = get_backend()
    try:
        mock = _MockBackend()
        set_backend(mock)
        assert get_backend() is mock
    finally:
        set_backend(original)


# ──────────────────────────────────────────────────────────────────────────────
# push_pending_sessions
# ──────────────────────────────────────────────────────────────────────────────

def test_push_pending_no_backend_configured(tmp_db):
    """Default backend is NullSync → push should fail gracefully."""
    import database
    from database.cloud import set_backend, NullSync
    set_backend(NullSync())
    result = database.push_pending_sessions(db_path=tmp_db)
    assert result["pushed"] == 0
    assert result["failed"] == 1
    assert "error" in result["errors"][0]


def test_push_pending_success_marks_pushed(tmp_db):
    import database
    from database.cloud import set_backend
    mock = _MockBackend()
    set_backend(mock)
    result = database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert result["pushed"] == 1
    assert result["failed"] == 0
    assert mock.push_calls == 1
    # sync_queue should have 1 pushed
    status = database.get_sync_status(db_path=tmp_db)
    assert status["counts"]["pushed"] == 1
    assert status["counts"]["pending"] == 0


def test_push_pending_failure_marks_failed(tmp_db):
    import database
    from database.cloud import set_backend
    mock = _MockBackend(fail_push=True)
    set_backend(mock)
    result = database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert result["pushed"] == 0
    assert result["failed"] == 1
    status = database.get_sync_status(db_path=tmp_db)
    assert status["counts"]["failed"] == 1


def test_push_pending_skips_already_pushed(tmp_db):
    import database
    from database.cloud import set_backend
    mock = _MockBackend()
    set_backend(mock)
    # First push
    database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert mock.push_calls == 1
    # Second push — should be a no-op
    database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert mock.push_calls == 1  # still 1, not 2


def test_push_pending_only_sends_new_sessions(tmp_db):
    """If a session is already 'pushed', and a new one is added, only
    the new one is pushed."""
    import database
    from database.cloud import set_backend
    mock = _MockBackend()
    set_backend(mock)
    database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert mock.push_calls == 1
    # Add a second session WITH enough laps to pass the min filter
    sid2 = database.create_session(
        track="Spa", layout="GP", car="Porsche 963",
        session_type="RACE", started_at="2026-06-14T10:00:00",
        db_path=tmp_db,
    )
    stint2 = database.create_stint(
        session_id=sid2, stint_number=1,
        compound_front="Soft", compound_rear="Soft",
        start_lap=1, start_fuel_l=80.0, db_path=tmp_db,
    )
    for i in range(1, 6):
        database.insert_lap({
            "session_id": sid2, "stint_id": stint2, "lap_number": i,
            "lap_time": 90.0 + i, "sector_1": 30, "sector_2": 30, "sector_3": 30 + i,
            "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
            "compound_front": "Soft", "compound_rear": "Soft",
            "tyre_age_laps": i,
            "wear_pct_start_FL": 5*i, "wear_pct_start_FR": 5*i,
            "wear_pct_start_RL": 4*i, "wear_pct_start_RR": 4*i,
            "wear_pct_end_FL": 5*(i+1), "wear_pct_end_FR": 5*(i+1),
            "wear_pct_end_RL": 4*(i+1), "wear_pct_end_RR": 4*(i+1),
            "fuel_start_l": 80-3*i, "fuel_end_l": 77-3*i, "fuel_used_l": 3,
            "track_temp": 28, "ambient_temp": 20,
            "weather_state": "DRY", "rain_intensity": 0,
            "completed_at": f"2026-06-14T10:0{i}:00",
        }, db_path=tmp_db)
    database.push_pending_sessions(db_path=tmp_db, backend=mock)
    assert mock.push_calls == 2  # pushed the new one only


# ──────────────────────────────────────────────────────────────────────────────
# pull_remote_sessions
# ──────────────────────────────────────────────────────────────────────────────

def test_pull_imports_remote_payloads(tmp_db, tmp_path):
    import database
    from database.cloud import set_backend
    # Create a source DB
    src_db = str(tmp_path / "source.db")
    database.init_db(db_path=src_db)
    src_sid = database.create_session(
        track="Monza", layout="GP", car="Porsche 963",
        session_type="RACE", started_at="2026-06-15T10:00:00",
        db_path=src_db,
    )
    src_stint = database.create_stint(
        session_id=src_sid, stint_number=1,
        compound_front="Soft", compound_rear="Soft",
        start_lap=1, start_fuel_l=80.0, db_path=src_db,
    )
    for i in range(1, 8):  # 7 laps, above min_laps_per_session=5
        database.insert_lap({
            "session_id": src_sid, "stint_id": src_stint, "lap_number": i,
            "lap_time": 80.0 + i, "sector_1": 27, "sector_2": 27, "sector_3": 26 + i,
            "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
            "compound_front": "Soft", "compound_rear": "Soft",
            "tyre_age_laps": i,
            "wear_pct_start_FL": 5*i, "wear_pct_start_FR": 5*i,
            "wear_pct_start_RL": 4*i, "wear_pct_start_RR": 4*i,
            "wear_pct_end_FL": 5*(i+1), "wear_pct_end_FR": 5*(i+1),
            "wear_pct_end_RL": 4*(i+1), "wear_pct_end_RR": 4*(i+1),
            "fuel_start_l": 80-3*i, "fuel_end_l": 77-3*i, "fuel_used_l": 3,
            "track_temp": 30, "ambient_temp": 22,
            "weather_state": "DRY", "rain_intensity": 0,
            "completed_at": f"2026-06-15T10:0{i}:00",
        }, db_path=src_db)

    # The source exports its sessions and we "send" via a mock backend
    from database.cloud import set_backend
    mock = _MockBackend()
    set_backend(mock)
    database.push_pending_sessions(db_path=src_db, backend=mock)
    assert mock.push_calls == 1

    # Now pull from mock into tmp_db
    summary = database.pull_remote_sessions(db_path=tmp_db, backend=mock)
    assert summary["payloads_processed"] == 1
    assert summary["sessions_added"] == 1
    assert summary["laps_added"] == 7

    # Verify in tmp_db (it already had 5 Ferrari laps, now has +7 Porsche)
    laps = database.get_all_laps_for_archive(include_deleted=False, db_path=tmp_db)
    assert len(laps) == 12
    cars = {l["car"] for l in laps}
    assert "Porsche 963" in cars
    assert "Ferrari 499P" in cars  # original session still there


def test_pull_dedups_existing_laps(tmp_db):
    """Pulling the same payload twice doesn't duplicate laps."""
    import database
    from database.cloud import set_backend
    mock = _MockBackend()
    set_backend(mock)
    database.push_pending_sessions(db_path=tmp_db, backend=mock)

    # First pull (into a fresh DB)
    import tempfile
    fresh = tempfile.mktemp(suffix=".db")
    database.init_db(db_path=fresh)
    s1 = database.pull_remote_sessions(db_path=fresh, backend=mock)
    assert s1["laps_added"] == 5
    # Second pull — all dedup
    s2 = database.pull_remote_sessions(db_path=fresh, backend=mock)
    assert s2["laps_added"] == 0
    assert s2["laps_skipped"] == 5


def test_pull_skips_invalid_payloads(tmp_db):
    """If the backend returns non-dict or dicts without 'sessions', skip."""
    import database

    class _WeirdBackend:
        backend_name = "weird"
        def push(self, p): return {"ok": True, "remote_id": "x", "error": None}
        def pull(self):
            return [None, "string", {"no_sessions": "key"}, {"sessions": []}]
        def status(self): return {"enabled": True, "backend": "weird"}

    summary = database.pull_remote_sessions(db_path=tmp_db, backend=_WeirdBackend())
    assert summary["payloads_processed"] == 1  # only the empty-but-valid one
    assert summary["sessions_added"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# get_sync_status
# ──────────────────────────────────────────────────────────────────────────────

def test_get_sync_status_returns_counts(tmp_db):
    import database
    status = database.get_sync_status(db_path=tmp_db)
    assert "backend" in status
    assert "counts" in status
    assert status["counts"]["pushed"] == 0
    assert status["counts"]["pending"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Migration: sync_queue is created on pre-existing DBs
# ──────────────────────────────────────────────────────────────────────────────

def test_migration_creates_sync_queue_on_existing_db(tmp_path):
    """If a DB was initialised BEFORE this version (no sync_queue), a
    subsequent init_db() call must create it via migration."""
    import database
    import sqlite3
    db_path = str(tmp_path / "legacy.db")
    # Manually create a minimal DB without sync_queue
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY,
            session_uuid TEXT, track TEXT, layout TEXT,
            car TEXT, session_type TEXT, started_at TEXT, completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    # Now run init_db — should add sync_queue
    database.init_db(db_path=db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_queue'"
    )
    assert cur.fetchone() is not None
    conn.close()
