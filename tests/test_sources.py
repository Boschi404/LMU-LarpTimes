import pytest
from telemetry.source import SyntheticReplaySource, TelemetryFrame


def test_synthetic_source_basic():
    """
    Test basic state updates of the synthetic source.
    """
    source = SyntheticReplaySource(
        track_name="Monza",
        car_name="Ferrari 499P",
        lap_time_base=100.0,
        fuel_capacity=100.0,
        initial_fuel=50.0,
        fuel_consumption=5.0,
        tick_rate=1.0  # 1 simulated second per tick
    )
    
    source.start()
    
    # Get initial frame
    frame = source.get_next_frame()
    assert frame is not None
    assert frame.track_name == "Monza"
    assert frame.car_name == "Ferrari 499P"
    assert frame.fuel == 50.0
    assert frame.lap_number == 1
    assert frame.in_pits is False
    
    # Run a full lap. Track length is 5793. Base speed for 100s lap is 57.93 m/s.
    # At 1.0s ticks, it should take ~100-103 ticks depending on fuel weight effect
    ticks = 0
    while source.lap_number == 1 and ticks < 150:
        source.get_next_frame()
        ticks += 1
        
    frame = source.get_next_frame()
    assert frame.lap_number == 2
    assert frame.last_lap_time > 95.0
    assert frame.fuel < 50.0  # Fuel must decrease
    assert sum(frame.tyre_wear) < 4.0  # Tyre wear must decrease (from 1.0)
    source.stop()


def test_synthetic_source_pit_stop():
    """
    Test that pit stops are simulated correctly.
    """
    source = SyntheticReplaySource(
        track_name="Monza",
        car_name="Ferrari 499P",
        initial_fuel=20.0,
        fuel_consumption=5.0,
        pit_stop_duration=5.0,
        pit_laps=[1],  # Pit at the end of lap 1
        tick_rate=1.0
    )
    
    source.start()
    
    # Run lap 1
    ticks = 0
    while source.lap_number == 1 and not source.in_pits and ticks < 150:
        source.get_next_frame()
        ticks += 1
        
    # We should have entered the pits
    assert source.in_pits is True
    assert source.pit_state == 2 or source.pit_state == 3
    
    # Stay in pits for 5 ticks
    for _ in range(5):
        frame = source.get_next_frame()
        assert frame.in_pits is True
        
    # Get one more frame, should exit pits and be on lap 2
    frame = source.get_next_frame()
    assert frame.in_pits is False
    assert frame.lap_number == 2
    assert frame.fuel == source.fuel_capacity  # Refueled
    assert frame.tyre_wear == [1.0, 1.0, 1.0, 1.0]  # Tyres replaced
    assert source.stint_number == 2
    
    source.stop()
