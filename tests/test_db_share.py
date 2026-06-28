"""
Tests for the sharing pattern (database.export_sessions + import_sessions
+ scripts/bundle_laps.py).

Covers:
  - export returns a valid payload with version + sessions
  - export filters by car and by track
  - import adds new sessions and laps
  - import dedups: re-importing the same payload does NOT duplicate
  - import with overwrite_existing=True DOES replace
  - roundtrip: export → import → export → identical structure
  - import with no sessions returns the error key
  - CLI: bundle_laps.py export/import/info work on a real DB
"""

import os
import sys
import json
import gzip
import tempfile
import subprocess
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Create a fresh DB and seed it with one session, 2 stints, 10 laps."""
    import database
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path=db_path)

    # Seed
    session_id = database.create_session(
        track="Le Mans",
        layout="Grand Prix",
        car="Ferrari 499P",
        session_type="RACE",
        started_at="2026-06-13T10:00:00",
        db_path=db_path,
    )
    # 1 stint
    stint_id = database.create_stint(
        session_id=session_id,
        stint_number=1,
        compound_front="Medium",
        compound_rear="Medium",
        start_lap=1,
        start_fuel_l=100.0,
        db_path=db_path,
    )
    # 10 laps
    for i in range(1, 11):
        database.insert_lap(
            {
                "session_id": session_id,
                "stint_id": stint_id,
                "lap_number": i,
                "lap_time": 220.0 + i * 0.5,
                "sector_1": 75.0,
                "sector_2": 80.0,
                "sector_3": 65.0 + i * 0.5,
                "is_valid_lap": 1,
                "is_pit_in_lap": 0,
                "is_pit_out_lap": 0,
                "compound_front": "Medium",
                "compound_rear": "Medium",
                "tyre_age_laps": i,
                "wear_pct_start_FL": 5.0 * i,
                "wear_pct_start_FR": 5.0 * i,
                "wear_pct_start_RL": 4.0 * i,
                "wear_pct_start_RR": 4.0 * i,
                "wear_pct_end_FL": 5.0 * (i + 1),
                "wear_pct_end_FR": 5.0 * (i + 1),
                "wear_pct_end_RL": 4.0 * (i + 1),
                "wear_pct_end_RR": 4.0 * (i + 1),
                "fuel_start_l": 100.0 - i * 4.0,
                "fuel_end_l": 96.0 - i * 4.0,
                "fuel_used_l": 4.0,
                "track_temp": 28.0,
                "ambient_temp": 20.0,
                "weather_state": "DRY",
                "rain_intensity": 0.0,
                "completed_at": f"2026-06-13T10:0{i}:00",
            },
            db_path=db_path,
        )
    return db_path


# ──────────────────────────────────────────────────────────────────────────────
# export_sessions
# ──────────────────────────────────────────────────────────────────────────────

def test_export_empty_db(tmp_path):
    import database
    db_path = str(tmp_path / "empty.db")
    database.init_db(db_path=db_path)
    payload = database.export_sessions(db_path=db_path)
    assert payload["version"] == 1
    assert payload["session_count"] == 0
    assert payload["lap_count"] == 0
    assert payload["sessions"] == []


def test_export_returns_seeded_data(tmp_db):
    import database
    payload = database.export_sessions(db_path=tmp_db)
    assert payload["version"] == 1
    assert payload["session_count"] == 1
    assert payload["lap_count"] == 10
    assert len(payload["sessions"]) == 1

    entry = payload["sessions"][0]
    assert entry["session"]["car"] == "Ferrari 499P"
    assert entry["session"]["track"] == "Le Mans"
    assert len(entry["laps"]) == 10
    assert len(entry["stints"]) == 1


def test_export_filters_by_car(tmp_db):
    import database
    payload = database.export_sessions(db_path=tmp_db, car="Ferrari 499P")
    assert payload["session_count"] == 1
    payload = database.export_sessions(db_path=tmp_db, car="Porsche 963")
    assert payload["session_count"] == 0


def test_export_filters_by_track(tmp_db):
    import database
    payload = database.export_sessions(db_path=tmp_db, track="Le Mans")
    assert payload["session_count"] == 1
    payload = database.export_sessions(db_path=tmp_db, track="Spa")
    assert payload["session_count"] == 0


def test_export_lap_has_session_uuid_and_stint_number(tmp_db):
    import database
    payload = database.export_sessions(db_path=tmp_db)
    for lap in payload["sessions"][0]["laps"]:
        assert "session_uuid" in lap
        assert lap["session_uuid"]  # non-empty
        assert "stint_number" in lap


# ──────────────────────────────────────────────────────────────────────────────
# import_sessions
# ──────────────────────────────────────────────────────────────────────────────

def test_import_invalid_payload_returns_error(tmp_path):
    import database
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path=db_path)
    summary = database.import_sessions(payload={"oops": "no sessions"}, db_path=db_path)
    assert "error" in summary
    assert summary["laps_added"] == 0


def test_import_adds_new_sessions_and_laps(tmp_path):
    import database
    db_path = str(tmp_path / "dest.db")
    database.init_db(db_path=db_path)

    payload = {
        "version": 1,
        "exported_at": "2026-06-13T10:00:00",
        "session_count": 1,
        "lap_count": 3,
        "sessions": [
            {
                "session": {
                    "session_uuid": "abc-123",
                    "track": "Le Mans",
                    "layout": "Grand Prix",
                    "car": "Porsche 963",
                    "session_type": "RACE",
                    "started_at": "2026-06-13T09:00:00",
                    "completed_at": "",
                },
                "stints": [
                    {
                        "stint_number": 1,
                        "compound_front": "Medium",
                        "compound_rear": "Medium",
                        "start_lap": 1,
                        "end_lap": 3,
                        "start_fuel_l": 100.0,
                        "end_fuel_l": 88.0,
                    }
                ],
                "laps": [
                    {
                        "session_uuid": "abc-123",
                        "stint_number": 1,
                        "lap_number": 1,
                        "lap_time": 220.0,
                        "sector_1": 75.0, "sector_2": 80.0, "sector_3": 65.0,
                        "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
                        "compound_front": "Medium", "compound_rear": "Medium",
                        "tyre_age_laps": 1,
                        "wear_pct_start_FL": 0.0, "wear_pct_start_FR": 0.0,
                        "wear_pct_start_RL": 0.0, "wear_pct_start_RR": 0.0,
                        "wear_pct_end_FL": 5.0, "wear_pct_end_FR": 5.0,
                        "wear_pct_end_RL": 4.0, "wear_pct_end_RR": 4.0,
                        "fuel_start_l": 100.0, "fuel_end_l": 96.0, "fuel_used_l": 4.0,
                        "track_temp": 28.0, "ambient_temp": 20.0,
                        "weather_state": "DRY", "rain_intensity": 0.0,
                        "completed_at": "2026-06-13T09:01:00",
                        "anomaly_flag": 0, "anomaly_reason": None, "is_deleted": 0,
                    },
                    {"session_uuid": "abc-123", "stint_number": 1, "lap_number": 2, "lap_time": 221.0,
                     "sector_1": 75.0, "sector_2": 80.0, "sector_3": 66.0,
                     "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
                     "compound_front": "Medium", "compound_rear": "Medium",
                     "tyre_age_laps": 2, "wear_pct_start_FL": 5.0, "wear_pct_start_FR": 5.0,
                     "wear_pct_start_RL": 4.0, "wear_pct_start_RR": 4.0,
                     "wear_pct_end_FL": 10.0, "wear_pct_end_FR": 10.0,
                     "wear_pct_end_RL": 8.0, "wear_pct_end_RR": 8.0,
                     "fuel_start_l": 96.0, "fuel_end_l": 92.0, "fuel_used_l": 4.0,
                     "track_temp": 28.0, "ambient_temp": 20.0,
                     "weather_state": "DRY", "rain_intensity": 0.0,
                     "completed_at": "2026-06-13T09:02:00",
                     "anomaly_flag": 0, "anomaly_reason": None, "is_deleted": 0},
                    {"session_uuid": "abc-123", "stint_number": 1, "lap_number": 3, "lap_time": 222.0,
                     "sector_1": 75.0, "sector_2": 80.0, "sector_3": 67.0,
                     "is_valid_lap": 1, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
                     "compound_front": "Medium", "compound_rear": "Medium",
                     "tyre_age_laps": 3, "wear_pct_start_FL": 10.0, "wear_pct_start_FR": 10.0,
                     "wear_pct_start_RL": 8.0, "wear_pct_start_RR": 8.0,
                     "wear_pct_end_FL": 15.0, "wear_pct_end_FR": 15.0,
                     "wear_pct_end_RL": 12.0, "wear_pct_end_RR": 12.0,
                     "fuel_start_l": 92.0, "fuel_end_l": 88.0, "fuel_used_l": 4.0,
                     "track_temp": 28.0, "ambient_temp": 20.0,
                     "weather_state": "DRY", "rain_intensity": 0.0,
                     "completed_at": "2026-06-13T09:03:00",
                     "anomaly_flag": 0, "anomaly_reason": None, "is_deleted": 0},
                ],
                "pit_stops": [],
            }
        ],
    }
    summary = database.import_sessions(payload=payload, db_path=db_path)
    assert summary["sessions_added"] == 1
    assert summary["laps_added"] == 3
    assert summary["laps_skipped"] == 0

    # Verify in DB
    laps = database.get_all_laps_for_archive(include_deleted=False, db_path=db_path)
    assert len(laps) == 3


def test_import_dedup_skips_existing_laps(tmp_db):
    import database
    # First export the seeded data
    payload = database.export_sessions(db_path=tmp_db)
    # Now re-import into the SAME DB — all 10 laps should be skipped
    summary = database.import_sessions(payload=payload, db_path=tmp_db)
    assert summary["sessions_added"] == 0
    assert summary["laps_added"] == 0
    assert summary["laps_skipped"] == 10


def test_import_overwrite_replaces_existing_laps(tmp_db):
    """When overwrite_existing=True, ALL matching laps are replaced,
    even if their values are identical. We verify by counting and by
    checking the modified lap_time is persisted."""
    import database
    payload = database.export_sessions(db_path=tmp_db)
    original_lap_count = len(payload["sessions"][0]["laps"])
    # Modify a lap time in the payload
    payload["sessions"][0]["laps"][0]["lap_time"] = 999.0
    summary = database.import_sessions(payload=payload, db_path=tmp_db, overwrite_existing=True)
    # All matching laps (session_uuid, lap_number) are overwritten
    assert summary["laps_overwritten"] == original_lap_count
    assert summary["laps_added"] == 0
    # Verify the change is persisted
    laps = database.get_all_laps_for_archive(include_deleted=False, db_path=tmp_db)
    target = next(l for l in laps if l["lap_number"] == 1)
    assert target["lap_time"] == 999.0


def test_roundtrip_export_import_export(tmp_db):
    import database
    p1 = database.export_sessions(db_path=tmp_db)
    # Import into a fresh DB
    import database as db2
    new_path = tmp_db + "_new"
    db2.init_db(db_path=new_path)
    summary = db2.import_sessions(payload=p1, db_path=new_path)
    assert summary["laps_added"] == 10
    # Re-export from new DB
    p2 = db2.export_sessions(db_path=new_path)
    # Same session count and lap count
    assert p1["session_count"] == p2["session_count"]
    assert p1["lap_count"] == p2["lap_count"]


def test_import_merges_new_laps_into_existing_session(tmp_db):
    """Re-importing with 1 brand new lap (lap 11) should add it,
    while skipping laps 1-10."""
    import database
    payload = database.export_sessions(db_path=tmp_db)
    # Append a new lap (lap 11) to the payload
    new_lap = dict(payload["sessions"][0]["laps"][0])
    new_lap["lap_number"] = 11
    new_lap["lap_time"] = 240.0
    new_lap["stint_number"] = 1
    payload["sessions"][0]["laps"].append(new_lap)
    payload["lap_count"] = 11

    summary = database.import_sessions(payload=payload, db_path=tmp_db)
    assert summary["laps_added"] == 1
    assert summary["laps_skipped"] == 10

    laps = database.get_all_laps_for_archive(include_deleted=False, db_path=tmp_db)
    assert len(laps) == 11


# ──────────────────────────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────────────────────────

def test_api_export_endpoint(tmp_db, monkeypatch):
    """GET /api/laps/export returns the payload."""
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)
    resp = client.get("/api/laps/export?car=Ferrari 499P&track=Le Mans")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_count"] == 1
    assert data["lap_count"] == 10


def test_api_import_endpoint(tmp_db, monkeypatch, tmp_path):
    """POST /api/laps/import adds laps from an exported payload."""
    from fastapi.testclient import TestClient
    import database
    import web.server as server_mod
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_db)
    client = TestClient(server_mod.app)

    # Export then re-import via API
    payload = database.export_sessions(db_path=tmp_db)
    resp = client.post("/api/laps/import", json=payload)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["sessions_added"] == 0  # already exists
    assert summary["laps_skipped"] == 10


# ──────────────────────────────────────────────────────────────────────────────
# CLI (bundle_laps.py)
# ──────────────────────────────────────────────────────────────────────────────

def test_cli_export_import_roundtrip(tmp_db, tmp_path):
    """The CLI: export to a .lmubundle file, then import into a new DB."""
    bundle_path = str(tmp_path / "test.lmubundle")
    target_db = str(tmp_path / "target.db")

    # Export
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [
        sys.executable,
        os.path.join(project_root, "scripts", "bundle_laps.py"),
        "--db", tmp_db,
        "export",
        "--out", bundle_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Export failed: {result.stderr}"
    assert os.path.exists(bundle_path)
    assert os.path.getsize(bundle_path) > 0

    # Verify gzip header
    with open(bundle_path, "rb") as f:
        assert f.read(2) == b"\x1f\x8b"

    # Import into a new DB
    cmd = [
        sys.executable,
        os.path.join(project_root, "scripts", "bundle_laps.py"),
        "--db", target_db,
        "import",
        "--in", bundle_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Import failed: {result.stderr}"
    assert "laps_added" in result.stdout

    # Verify laps in target DB
    import database
    laps = database.get_all_laps_for_archive(include_deleted=False, db_path=target_db)
    assert len(laps) == 10


def test_cli_info_prints_summary(tmp_db, tmp_path):
    bundle_path = str(tmp_path / "test.lmubundle")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Export
    subprocess.run([
        sys.executable,
        os.path.join(project_root, "scripts", "bundle_laps.py"),
        "--db", tmp_db,
        "export",
        "--out", bundle_path,
    ], check=True)
    # Info
    result = subprocess.run([
        sys.executable,
        os.path.join(project_root, "scripts", "bundle_laps.py"),
        "info",
        "--in", bundle_path,
    ], capture_output=True, text=True, check=True)
    assert "Sessions:" in result.stdout
    assert "10 laps" in result.stdout
    assert "Ferrari 499P" in result.stdout
