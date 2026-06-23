import pytest
from analysis.models import DegradationModelFit
from analysis.strategist import PitStrategist


def test_pit_strategist_basic():
    """
    Test strategist optimization with simple parameters.
    """
    # 1. Mock fitted model
    # base time = 100.0s, fuel effect = 0.03s/liter
    # tyre age degradation: 0.05s/lap before cliff (lap 15), 0.15s/lap after
    model_fit = DegradationModelFit(
        base_time=100.0,
        alpha=0.03,
        beta_1=0.05,
        beta_2=0.15,
        cliff_lap=15,
        huber_loss_val=0.0
    )
    
    # 2. Setup strategist
    # Fuel capacity 100L, consumption 4L/lap -> max stint is 25 laps
    # Pit loss is 30 seconds
    strategist = PitStrategist(
        fuel_capacity=100.0,
        fuel_consumption=4.0,
        pit_loss=30.0,
        model_fit=model_fit
    )
    
    # Gara di 40 giri, partiamo con 80 litri (20 giri di benzina) e gomme nuove
    res = strategist.optimize(
        laps_remaining=40,
        current_tyre_age=0,
        current_fuel=80.0,
        max_stops=3
    )
    
    assert res["optimal"] is not None
    assert res["optimal"]["stops"] == 1  # 1 stop is enough and forced by fuel
    # Fuel remaining is 20 laps, so we MUST pit at lap 20 or earlier.
    # The optimal lap to pit is exactly lap 20 (or very close) to maximize fuel stint.
    assert 20 in res["optimal"]["pit_laps"]
    
    # Check alternatives
    alternatives = res["alternatives"]
    # 0 stops should not be in alternatives or should be invalid (inf cost)
    assert 0 not in alternatives or alternatives[0]["total_time"] == float("inf")
    # 1 stop time should be better than 2 stops time
    assert 1 in alternatives
    assert 2 in alternatives
    assert alternatives[1]["total_time"] < alternatives[2]["total_time"]
