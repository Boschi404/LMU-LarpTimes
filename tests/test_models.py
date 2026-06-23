import pytest
import numpy as np
from analysis.models import fit_degradation_model, fit_fuel_model


def test_fit_degradation_and_fuel_models():
    """
    Test fitting models on synthetic data with known coefficients.
    """
    # Parameters for generation
    base_time_true = 100.0
    alpha_true = 0.03  # fuel coefficient
    beta_1_true = 0.05  # degradation rate before cliff
    beta_2_true = 0.15  # additional degradation rate after cliff (total = 0.20)
    cliff_lap_true = 12.0
    fuel_cons_true = 3.0
    
    # Generate 30 laps of training data
    laps = []
    np.random.seed(42)
    
    for i in range(1, 31):
        fuel_start = 80.0 - (i - 1) * fuel_cons_true
        fuel_used = fuel_cons_true
        fuel_end = fuel_start - fuel_used
        tyre_age = i
        
        # Compute lap time according to the formula
        deg = beta_1_true * tyre_age + beta_2_true * max(0.0, tyre_age - cliff_lap_true)
        lap_time = base_time_true + alpha_true * fuel_start + deg
        # Add small gaussian noise
        lap_time += np.random.normal(0, 0.05)
        
        laps.append({
            "lap_time": lap_time,
            "fuel_start_l": fuel_start,
            "fuel_end_l": fuel_end,
            "fuel_used_l": fuel_used,
            "tyre_age_laps": tyre_age,
            "is_pit_in_lap": 0,
            "is_pit_out_lap": 0
        })

    # Fit tyre degradation model
    fit = fit_degradation_model(laps)
    
    # Check closeness
    assert pytest.approx(fit.base_time, abs=0.5) == base_time_true
    assert pytest.approx(fit.alpha, abs=0.01) == alpha_true
    assert pytest.approx(fit.beta_1, abs=0.02) == beta_1_true
    assert pytest.approx(fit.beta_2, abs=0.04) == beta_2_true
    assert fit.cliff_lap == cliff_lap_true
    
    # Fit fuel consumption model
    mean_fuel, std_fuel = fit_fuel_model(laps)
    assert pytest.approx(mean_fuel, abs=0.05) == fuel_cons_true
    assert std_fuel < 0.1
