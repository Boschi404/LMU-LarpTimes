import os
import pytest
import database
from telemetry.source import TelemetryFrame
from telemetry.detector import LapBoundaryDetector


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_detector.db"
    db_path = str(db_file)
    database.init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_detector_basic(temp_db):
    """
    Test basic lap boundary detection, sectors, and database insertion.
    """
    detector = LapBoundaryDetector(db_path=temp_db)
    
    # Frame 1: start of lap 1
    f1 = TelemetryFrame(
        track_name="Monza",
        car_name="Ferrari 499P",
        lap_number=1,
        fuel=80.0,
        tyre_wear=[1.0, 1.0, 1.0, 1.0],
        tyre_compounds=["Medium", "Medium"],
        elapsed_time=0.0
    )
    res1 = detector.process_frame(f1)
    assert res1 is None
    assert detector.session_id == 1
    
    # Frame 2: halfway through lap 1
    f2 = TelemetryFrame(
        track_name="Monza",
        car_name="Ferrari 499P",
        lap_number=1,
        fuel=78.4,
        tyre_wear=[0.99, 0.99, 0.99, 0.99],
        tyre_compounds=["Medium", "Medium"],
        elapsed_time=50.0
    )
    res2 = detector.process_frame(f2)
    assert res2 is None
    
    # Frame 3: start of lap 2 (completing lap 1)
    # LMU reports last lap times in scoring
    f3 = TelemetryFrame(
        track_name="Monza",
        car_name="Ferrari 499P",
        lap_number=2,
        fuel=76.8,
        tyre_wear=[0.98, 0.98, 0.98, 0.98],
        tyre_compounds=["Medium", "Medium"],
        elapsed_time=100.0,
        last_lap_time=100.0,
        last_sector1=35.0,
        last_sector2=70.0
    )
    
    res3 = detector.process_frame(f3)
    assert res3 is not None  # Lap database ID returned
    assert res3 == 1
    
    # Fetch from database
    laps = database.get_all_laps_for_archive(db_path=temp_db)
    assert len(laps) == 1
    lap = laps[0]
    assert lap["lap_number"] == 1
    assert lap["lap_time"] == 100.0
    assert lap["sector_1"] == 35.0
    assert lap["sector_2"] == 35.0  # 70.0 - 35.0
    assert lap["sector_3"] == 30.0  # 100.0 - 70.0
    assert lap["fuel_start_l"] == 80.0
    assert lap["fuel_end_l"] == 76.8
    assert pytest.approx(lap["fuel_used_l"]) == 3.2
    assert lap["tyre_age_laps"] == 1
    assert detector.tyre_age_laps == 2


def test_detector_tyre_change(temp_db):
    """
    Test that stint resets and tyre age resets when tyres are changed.
    """
    detector = LapBoundaryDetector(db_path=temp_db)
    
    # Start lap 1
    detector.process_frame(TelemetryFrame(
        track_name="Monza", car_name="Ferrari 499P", lap_number=1,
        fuel=80.0, tyre_wear=[0.95, 0.95, 0.95, 0.95],
        tyre_compounds=["Medium", "Medium"]
    ))
    
    # Start lap 2 (Medium compound, wear continues)
    detector.process_frame(TelemetryFrame(
        track_name="Monza", car_name="Ferrari 499P", lap_number=2,
        fuel=75.0, tyre_wear=[0.93, 0.93, 0.93, 0.93],
        tyre_compounds=["Medium", "Medium"],
        last_lap_time=100.0, last_sector1=35.0, last_sector2=70.0
    ))
    
    assert detector.tyre_age_laps == 2
    assert detector.stint_number == 1
    
    # Start lap 3 with different compound (Soft)
    detector.process_frame(TelemetryFrame(
        track_name="Monza", car_name="Ferrari 499P", lap_number=3,
        fuel=70.0, tyre_wear=[1.0, 1.0, 1.0, 1.0],
        tyre_compounds=["Soft", "Soft"],
        last_lap_time=100.0, last_sector1=35.0, last_sector2=70.0
    ))
    
    # Tyres were replaced! Tyre age resets to 1, stint increments to 2
    assert detector.tyre_age_laps == 1
    assert detector.stint_number == 2
