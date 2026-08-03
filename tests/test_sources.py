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


def test_synthetic_source_race_fields():
    """Race/scoring fields are populated by the synthetic source (Tier A overlay data)."""
    source = SyntheticReplaySource(total_laps=40, tick_rate=1.0)
    source.start()
    frame = source.get_next_frame()
    assert frame.position > 0
    assert frame.total_vehicles > 0
    assert frame.race_total_laps == 40
    assert frame.vehicle_class
    assert frame.gap_ahead > 0
    assert frame.gap_behind > 0
    assert frame.gap_leader > 0
    assert frame.session_time_remaining > 0
    assert frame.flag_state == 0
    assert frame.under_yellow is False
    source.stop()


def test_telemetry_frame_race_defaults():
    """TelemetryFrame race fields default to safe zero/empty values."""
    frame = TelemetryFrame()
    assert frame.position == 0
    assert frame.class_position == 0
    assert frame.vehicle_class == ""
    assert frame.total_vehicles == 0
    assert frame.gap_ahead == 0.0
    assert frame.gap_behind == 0.0
    assert frame.gap_leader == 0.0
    assert frame.laps_behind_leader == 0
    assert frame.race_total_laps == 0
    assert frame.flag_state == 0
    assert frame.under_yellow is False
    assert frame.best_sector1 == 0.0
    assert frame.best_sector2 == 0.0
    assert frame.best_lap_time == 0.0


def test_synthetic_source_start_idempotent():
    """Regressione: run_overlay_live.py avvia il source e TelemetryWorker lo
    riavvia → il secondo start() NON deve resettare lo stato della simulazione
    (con LMU attiva il doppio start riapriva l'mmap → crash nativo)."""
    source = SyntheticReplaySource(tick_rate=1.0)
    source.start()
    source.start()  # secondo avvio (flusso run_overlay_live + TelemetryWorker)
    assert source.running is True
    # La simulazione deve proseguire senza reset: elapsed_time avanza
    f1 = source.get_next_frame()
    assert f1 is not None and f1.elapsed_time >= 0.0
    for _ in range(10):
        source.get_next_frame()
    elapsed_before = source.elapsed_time
    assert elapsed_before > 0.0
    source.start()  # terzo avvio a metà simulazione — NON deve resettare
    f_n = source.get_next_frame()
    assert f_n is not None
    assert source.elapsed_time >= elapsed_before  # nessun reset a zero
    source.stop()


def test_live_source_start_guard_without_lmu():
    """LiveSharedMemorySource.start() deve essere chiamabile due volte senza
    crash quando LMU non è attiva (fallback RF2 assente → nessun mmap)."""
    from telemetry.source import LiveSharedMemorySource
    src = LiveSharedMemorySource()
    src.start()
    src.start()  # idempotente o fallback innocuo
    assert src.running is True
    src.stop()


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
