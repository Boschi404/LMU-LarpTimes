import os
import pytest
import database
from analysis.anomaly import detect_anomalies_for_session


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_anomaly.db"
    db_path = str(db_file)
    database.init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_anomaly_detection(temp_db):
    """
    Test pace and fuel anomaly detection.
    """
    session_id = database.create_session("Spa", "GP", "Porsche 963", "PRACTICE", db_path=temp_db)
    
    # Insert 12 laps: 10 normal, 1 pace anomaly, 1 fuel anomaly
    # Normal laps take ~100s, use ~3.0L fuel, and tyre age is incremental
    for i in range(1, 13):
        lap_time = 100.0 + 0.1 * i  # Slow degradation
        fuel_used = 3.0
        fuel_start = 80.0 - 3.0 * i
        
        if i == 5:
            lap_time = 105.0  # Injected pace anomaly (+5.0 seconds)
        if i == 9:
            fuel_used = 6.0  # Injected fuel anomaly (double consumption)
            
        lap_data = {
            "session_id": session_id,
            "lap_number": i,
            "stint_number": 1,
            "lap_time": lap_time,
            "sector_1": lap_time * 0.35,
            "sector_2": lap_time * 0.70,
            "sector_3": lap_time * 0.30,
            "is_valid_lap": 1,
            "is_pit_in_lap": 0,
            "is_pit_out_lap": 0,
            "compound_front": "Soft",
            "compound_rear": "Soft",
            "tyre_age_laps": i,
            "wear_pct_start_FL": 0.0, "wear_pct_start_FR": 0.0, "wear_pct_start_RL": 0.0, "wear_pct_start_RR": 0.0,
            "wear_pct_end_FL": 1.0, "wear_pct_end_FR": 1.0, "wear_pct_end_RL": 1.0, "wear_pct_end_RR": 1.0,
            "fuel_start_l": fuel_start,
            "fuel_end_l": fuel_start - fuel_used,
            "fuel_used_l": fuel_used,
            "track_temp": 28.0,
            "ambient_temp": 22.0,
            "weather_state": "DRY",
            "rain_intensity": 0.0,
            "anomaly_flag": 0,
            "anomaly_reason": None
        }
        database.insert_lap(lap_data, db_path=temp_db)

    # Run anomaly detector
    detect_anomalies_for_session("Porsche 963", "Spa", db_path=temp_db)
    
    # Read laps back from database
    laps = database.get_all_laps_for_archive(db_path=temp_db)
    
    # Sort by lap number (from 1 to 12)
    laps.sort(key=lambda l: l["lap_number"])
    
    # Lap 5 should be flagged as pace anomaly
    assert laps[4]["anomaly_flag"] == 1
    assert "Tempo anomalo" in laps[4]["anomaly_reason"]
    
    # Lap 9 should be flagged as fuel anomaly
    assert laps[8]["anomaly_flag"] == 1
    assert "Consumo anomalo" in laps[8]["anomaly_reason"]
    
    # Other laps should not be anomalies
    for i, lap in enumerate(laps):
        if i not in [4, 8]:
            assert lap["anomaly_flag"] == 0
            assert lap["anomaly_reason"] is None
