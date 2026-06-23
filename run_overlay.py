"""Run the LMU Pit Strategist overlay demo with synthetic data."""
from overlay.app import run_overlay
from telemetry.source import SyntheticReplaySource

if __name__ == "__main__":
    source = SyntheticReplaySource(
        track_name="Le Mans",
        car_name="Ferrari 499P LMH",
        lap_time_base=225.0,
        fuel_capacity=110.0,
        initial_fuel=105.0,
        fuel_consumption=4.8,
        cliff_lap=18,
        anomaly_laps={5: 2.0, 12: 1.8},
        total_laps=40,
        tick_rate=0.5
    )
    run_overlay(source)
