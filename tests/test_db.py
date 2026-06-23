import os
import sqlite3
import pytest
import database


@pytest.fixture
def temp_db(tmp_path):
    """
    Create a temporary database path for tests.
    """
    db_file = tmp_path / "test_lmu.db"
    db_path = str(db_file)
    database.init_db(db_path)
    yield db_path
    # Clean up
    if os.path.exists(db_path):
        os.remove(db_path)


def test_init_db(temp_db):
    """
    Verify tables are created and WAL mode is enabled.
    """
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    # Verify WAL mode
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.lower() == "wal"
    
    # Verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "sessions" in tables
    assert "laps" in tables
    assert "pit_stops" in tables
    conn.close()


def test_create_session(temp_db):
    """
    Test creating a session.
    """
    session_id = database.create_session(
        track="Spa",
        layout="GP",
        car="Porsche 963",
        session_type="RACE",
        db_path=temp_db
    )
    assert session_id == 1
    
    conn = database.get_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    assert row["track"] == "Spa"
    assert row["layout"] == "GP"
    assert row["car"] == "Porsche 963"
    assert row["session_type"] == "RACE"
    conn.close()


def test_insert_lap_and_soft_delete(temp_db):
    """
    Test inserting, fetching, and soft-deleting a lap.
    """
    session_id = database.create_session("Spa", "GP", "Porsche 963", "RACE", db_path=temp_db)
    
    lap_data = {
        "session_id": session_id,
        "lap_number": 1,
        "stint_number": 1,
        "lap_time": 125.4,
        "sector_1": 41.2,
        "sector_2": 44.1,
        "sector_3": 40.1,
        "is_valid_lap": 1,
        "is_pit_in_lap": 0,
        "is_pit_out_lap": 0,
        "compound_front": "Soft",
        "compound_rear": "Soft",
        "tyre_age_laps": 1,
        "wear_pct_start_FL": 0.0,
        "wear_pct_start_FR": 0.0,
        "wear_pct_start_RL": 0.0,
        "wear_pct_start_RR": 0.0,
        "wear_pct_end_FL": 1.2,
        "wear_pct_end_FR": 1.1,
        "wear_pct_end_RL": 0.9,
        "wear_pct_end_RR": 0.9,
        "fuel_start_l": 80.0,
        "fuel_end_l": 76.5,
        "fuel_used_l": 3.5,
        "track_temp": 28.5,
        "ambient_temp": 22.0,
        "weather_state": "DRY",
        "rain_intensity": 0.0,
        "anomaly_flag": 0,
        "anomaly_reason": None
    }
    
    lap_id = database.insert_lap(lap_data, db_path=temp_db)
    assert lap_id == 1
    
    # Verify retrieval for analysis
    laps = database.get_laps_for_analysis("Porsche 963", "Spa", db_path=temp_db)
    assert len(laps) == 1
    assert laps[0]["lap_time"] == 125.4
    
    # Soft delete
    database.soft_delete_lap(lap_id, is_deleted=True, db_path=temp_db)
    
    # Should not be returned for analysis anymore
    laps_after_delete = database.get_laps_for_analysis("Porsche 963", "Spa", db_path=temp_db)
    assert len(laps_after_delete) == 0
    
    # Should still show up in archive
    archive_laps = database.get_all_laps_for_archive(db_path=temp_db, include_deleted=True)
    assert len(archive_laps) == 1
    assert archive_laps[0]["is_deleted"] == 1
