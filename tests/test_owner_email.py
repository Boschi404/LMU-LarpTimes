"""
Tests for the owner_email identity (S-2, S-3).

Covers:
  - get_owner_email returns None initially
  - set_owner_email validates and normalises
  - set_owner_email backfills old sessions/laps
  - create_session auto-tags with current owner_email
  - insert_lap auto-tags with current owner_email
  - get_all_laps_for_archive includes owner_email
  - API: GET /api/owner, POST /api/owner, /api/laps?owner_email=...
  - Validation: invalid email raises ValueError
"""

import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def tmp_db(tmp_path):
    import database
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path=db_path)
    return db_path


# ── get/set owner_email ──────────────────────────────────────────────────

def test_get_owner_email_empty(tmp_db):
    import database
    assert database.get_owner_email(db_path=tmp_db) is None


def test_set_owner_email_normalises_lowercase(tmp_db):
    import database
    e = database.set_owner_email("  Alice@Example.COM  ", db_path=tmp_db)
    assert e == "alice@example.com"


def test_set_owner_email_invalid_raises(tmp_db):
    import database
    with pytest.raises(ValueError):
        database.set_owner_email("not-an-email", db_path=tmp_db)
    with pytest.raises(ValueError):
        database.set_owner_email("no-at-sign.com", db_path=tmp_db)
    with pytest.raises(ValueError):
        database.set_owner_email("foo@", db_path=tmp_db)
    with pytest.raises(ValueError):
        database.set_owner_email("@no-user.com", db_path=tmp_db)


def test_set_owner_email_clears_with_none(tmp_db):
    import database
    database.set_owner_email("a@b.com", db_path=tmp_db)
    assert database.get_owner_email(db_path=tmp_db) == "a@b.com"
    database.set_owner_email(None, db_path=tmp_db)
    assert database.get_owner_email(db_path=tmp_db) is None


def test_set_owner_email_clears_with_empty_string(tmp_db):
    import database
    database.set_owner_email("a@b.com", db_path=tmp_db)
    database.set_owner_email("", db_path=tmp_db)
    assert database.get_owner_email(db_path=tmp_db) is None


# ── Backfill old sessions/laps ─────────────────────────────────────────

def test_set_owner_email_backfills_sessions(tmp_db):
    import database
    # Create a session BEFORE setting owner
    sid = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T10:00:00",
        db_path=tmp_db,
    )
    # Now set owner — should backfill
    database.set_owner_email("alice@example.com", db_path=tmp_db)
    # Check the session has owner_email
    conn = database.get_db_connection(db_path=tmp_db)
    row = conn.execute(
        "SELECT owner_email FROM sessions WHERE id = ?", (sid,)
    ).fetchone()
    conn.close()
    assert row["owner_email"] == "alice@example.com"


def test_set_owner_email_backfills_laps(tmp_db):
    import database
    # Create session + lap BEFORE owner is set
    sid = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T10:00:00",
        db_path=tmp_db,
    )
    stint = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="M", compound_rear="M",
        start_lap=1, start_fuel_l=50.0, db_path=tmp_db,
    )
    database.insert_lap({
        "session_id": sid, "stint_id": stint, "lap_number": 1,
        "lap_time": 100.0, "sector_1": 33, "sector_2": 33, "sector_3": 34,
        "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
        "compound_front": "M", "compound_rear": "M",
        "tyre_age_laps": 1,
        "wear_pct_start_FL": 0, "wear_pct_start_FR": 0,
        "wear_pct_start_RL": 0, "wear_pct_start_RR": 0,
        "wear_pct_end_FL": 5, "wear_pct_end_FR": 5,
        "wear_pct_end_RL": 4, "wear_pct_end_RR": 4,
        "fuel_start_l": 50, "fuel_end_l": 47, "fuel_used_l": 3,
        "track_temp": 25, "ambient_temp": 20,
        "weather_state": "DRY", "rain_intensity": 0,
        "completed_at": "2026-01-01T10:01:00",
    }, db_path=tmp_db)

    # Set owner
    database.set_owner_email("bob@example.com", db_path=tmp_db)

    # Check the lap has owner_email
    conn = database.get_db_connection(db_path=tmp_db)
    row = conn.execute(
        "SELECT owner_email FROM laps WHERE session_id = ?", (sid,)
    ).fetchone()
    conn.close()
    assert row["owner_email"] == "bob@example.com"


# ── Auto-tag on new sessions/laps ──────────────────────────────────────

def test_new_session_auto_tagged(tmp_db):
    import database
    database.set_owner_email("alice@example.com", db_path=tmp_db)
    sid = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T10:00:00",
        db_path=tmp_db,
    )
    conn = database.get_db_connection(db_path=tmp_db)
    row = conn.execute(
        "SELECT owner_email FROM sessions WHERE id = ?", (sid,)
    ).fetchone()
    conn.close()
    assert row["owner_email"] == "alice@example.com"


def test_new_lap_auto_tagged(tmp_db):
    import database
    database.set_owner_email("alice@example.com", db_path=tmp_db)
    sid = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T10:00:00",
        db_path=tmp_db,
    )
    stint = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="M", compound_rear="M",
        start_lap=1, start_fuel_l=50.0, db_path=tmp_db,
    )
    database.insert_lap({
        "session_id": sid, "stint_id": stint, "lap_number": 1,
        "lap_time": 100.0, "sector_1": 33, "sector_2": 33, "sector_3": 34,
        "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
        "compound_front": "M", "compound_rear": "M",
        "tyre_age_laps": 1,
        "wear_pct_start_FL": 0, "wear_pct_start_FR": 0,
        "wear_pct_start_RL": 0, "wear_pct_start_RR": 0,
        "wear_pct_end_FL": 5, "wear_pct_end_FR": 5,
        "wear_pct_end_RL": 4, "wear_pct_end_RR": 4,
        "fuel_start_l": 50, "fuel_end_l": 47, "fuel_used_l": 3,
        "track_temp": 25, "ambient_temp": 20,
        "weather_state": "DRY", "rain_intensity": 0,
        "completed_at": "2026-01-01T10:01:00",
    }, db_path=tmp_db)
    conn = database.get_db_connection(db_path=tmp_db)
    row = conn.execute(
        "SELECT owner_email FROM laps WHERE session_id = ?", (sid,)
    ).fetchone()
    conn.close()
    assert row["owner_email"] == "alice@example.com"


def test_new_session_when_no_owner(tmp_db):
    """If no owner is set, new sessions have NULL owner_email."""
    import database
    sid = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T10:00:00",
        db_path=tmp_db,
    )
    conn = database.get_db_connection(db_path=tmp_db)
    row = conn.execute(
        "SELECT owner_email FROM sessions WHERE id = ?", (sid,)
    ).fetchone()
    conn.close()
    assert row["owner_email"] is None


# ── API endpoints ──────────────────────────────────────────────────────

def test_api_owner_get_set(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)

    # GET initial
    r = client.get("/api/owner")
    assert r.status_code == 200
    assert r.json() == {"email": "", "display_name": "", "logged_in": False}

    # POST set
    r = client.post("/api/owner", json={"email": "Test@X.com"})
    assert r.status_code == 200
    assert r.json()["email"] == "test@x.com"

    # GET again
    r = client.get("/api/owner")
    assert r.json()["email"] == "test@x.com"


def test_api_owner_invalid_email_rejected(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)
    r = client.post("/api/owner", json={"email": "not-an-email"})
    assert r.status_code == 400
    assert "invalid" in r.json()["error"]


def test_api_laps_filter_by_owner_email(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)

    # Create two sessions for different owners
    database.set_owner_email("alice@example.com", db_path=tmp_db)
    sid_a = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T10:00:00",
        db_path=tmp_db,
    )
    stint_a = database.create_stint(
        session_id=sid_a, stint_number=1,
        compound_front="M", compound_rear="M",
        start_lap=1, start_fuel_l=50.0, db_path=tmp_db,
    )
    for i in range(1, 4):
        database.insert_lap({
            "session_id": sid_a, "stint_id": stint_a, "lap_number": i,
            "lap_time": 100.0 + i, "sector_1": 33, "sector_2": 33, "sector_3": 34,
            "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
            "compound_front": "M", "compound_rear": "M",
            "tyre_age_laps": i,
            "wear_pct_start_FL": 0, "wear_pct_start_FR": 0,
            "wear_pct_start_RL": 0, "wear_pct_start_RR": 0,
            "wear_pct_end_FL": 5, "wear_pct_end_FR": 5,
            "wear_pct_end_RL": 4, "wear_pct_end_RR": 4,
            "fuel_start_l": 50, "fuel_end_l": 47, "fuel_used_l": 3,
            "track_temp": 25, "ambient_temp": 20,
            "weather_state": "DRY", "rain_intensity": 0,
            "completed_at": f"2026-01-01T10:0{i}:00",
        }, db_path=tmp_db)

    database.set_owner_email("bob@example.com", db_path=tmp_db)
    sid_b = database.create_session(
        track="Le Mans", layout="GP", car="X",
        session_type="RACE", started_at="2026-01-01T11:00:00",
        db_path=tmp_db,
    )
    stint_b = database.create_stint(
        session_id=sid_b, stint_number=1,
        compound_front="M", compound_rear="M",
        start_lap=1, start_fuel_l=50.0, db_path=tmp_db,
    )
    database.insert_lap({
        "session_id": sid_b, "stint_id": stint_b, "lap_number": 1,
        "lap_time": 200.0, "sector_1": 33, "sector_2": 33, "sector_3": 34,
        "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
        "compound_front": "M", "compound_rear": "M",
        "tyre_age_laps": 1,
        "wear_pct_start_FL": 0, "wear_pct_start_FR": 0,
        "wear_pct_start_RL": 0, "wear_pct_start_RR": 0,
        "wear_pct_end_FL": 5, "wear_pct_end_FR": 5,
        "wear_pct_end_RL": 4, "wear_pct_end_RR": 4,
        "fuel_start_l": 50, "fuel_end_l": 47, "fuel_used_l": 3,
        "track_temp": 25, "ambient_temp": 20,
        "weather_state": "DRY", "rain_intensity": 0,
        "completed_at": "2026-01-01T11:01:00",
    }, db_path=tmp_db)

    # Test API filter
    client = TestClient(server_mod.app)

    # No filter: all laps
    r = client.get("/api/laps")
    assert r.status_code == 200
    laps = r.json()
    assert len(laps) == 4  # 3 from alice + 1 from bob

    # Filter by alice
    r = client.get("/api/laps?owner_email=alice@example.com")
    laps = r.json()
    assert len(laps) == 3
    for l in laps:
        assert l.get("owner_email") == "alice@example.com"

    # Filter by bob
    r = client.get("/api/laps?owner_email=bob@example.com")
    laps = r.json()
    assert len(laps) == 1
    assert laps[0]["owner_email"] == "bob@example.com"

    # Filter by unknown
    r = client.get("/api/laps?owner_email=nobody@x.com")
    laps = r.json()
    assert len(laps) == 0
