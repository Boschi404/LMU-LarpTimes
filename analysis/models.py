import numpy as np
from scipy.optimize import minimize
from typing import Dict, Any, List, Optional, Tuple, Union


def huber_loss(residuals: np.ndarray, delta: float = 1.35) -> float:
    """
    Compute the Huber loss for a set of residuals.
    """
    abs_res = np.abs(residuals)
    loss = np.where(abs_res <= delta, 0.5 * residuals**2, delta * (abs_res - 0.5 * delta))
    return float(np.sum(loss))


class DegradationModelFit:
    """
    Fits and represents the fitted tyre degradation and fuel effect parameters.
    """
    def __init__(
        self,
        base_time: float,
        alpha: float,
        beta_1: float,
        beta_2: float,
        cliff_lap: float,
        huber_loss_val: float
    ):
        self.base_time = base_time
        self.alpha = alpha  # fuel weight coefficient (sec/liter)
        self.beta_1 = beta_1  # tyre wear degradation (sec/lap) before cliff
        self.beta_2 = beta_2  # additional tyre wear degradation (sec/lap) after cliff
        self.cliff_lap = cliff_lap  # tyre age at which cliff begins
        self.huber_loss_val = huber_loss_val

    def predict(self, tyre_age: Union[float, np.ndarray], fuel_l: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """
        Predict the lap time under given tyre age and fuel load.
        """
        deg = self.beta_1 * tyre_age + self.beta_2 * np.maximum(0.0, tyre_age - self.cliff_lap)
        return self.base_time + self.alpha * fuel_l + deg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_time": self.base_time,
            "alpha": self.alpha,
            "beta_1": self.beta_1,
            "beta_2": self.beta_2,
            "cliff_lap": self.cliff_lap,
            "huber_loss": self.huber_loss_val
        }


def fit_degradation_model(laps: List[Dict[str, Any]]) -> DegradationModelFit:
    """
    Fit a joint regression model for fuel effect and tyre degradation (with a possible cliff).
    Using Huber loss minimization for robustness against remaining outliers.
    """
    n = len(laps)
    T = np.array([l["lap_time"] for l in laps])
    F = np.array([l["fuel_start_l"] for l in laps])
    A = np.array([l["tyre_age_laps"] for l in laps])

    # Fallback/Default values if we have too few data points
    if n < 5:
        # Defaults
        alpha = 0.04
        beta_1 = 0.05
        beta_2 = 0.0
        cliff_lap = 999.0
        base_time = float(np.mean(T) - alpha * np.mean(F) - beta_1 * np.mean(A))
        return DegradationModelFit(base_time, alpha, beta_1, beta_2, cliff_lap, 0.0)

    # Simplified linear fit if 5 <= N < 10 (no cliff estimation)
    if n < 10:
        def obj_simple(params):
            base, a, b1 = params
            preds = base + a * F + b1 * A
            return huber_loss(T - preds)

        init_guess = [np.mean(T), 0.04, 0.05]
        # bounds: base time around mean, alpha >= 0, beta_1 >= 0
        bounds = [(np.mean(T) - 50.0, np.mean(T) + 50.0), (0.0, 0.5), (0.0, 1.0)]
        res = minimize(obj_simple, init_guess, bounds=bounds, method="L-BFGS-B")
        
        base_time, alpha, beta_1 = res.x
        return DegradationModelFit(base_time, alpha, beta_1, 0.0, 999.0, res.fun)

    # Full fit: grid search over cliff C in [5, 25]
    best_loss = float("inf")
    best_params = None
    best_c = 999.0

    # Grid search over potential cliff laps
    for C in range(5, 26):
        def obj_full(params):
            base, a, b1, b2 = params
            preds = base + a * F + b1 * A + b2 * np.maximum(0.0, A - C)
            return huber_loss(T - preds)

        init_guess = [np.mean(T), 0.04, 0.05, 0.1]
        bounds = [(np.mean(T) - 50.0, np.mean(T) + 50.0), (0.0, 0.5), (0.0, 1.0), (0.0, 2.0)]
        res = minimize(obj_full, init_guess, bounds=bounds, method="L-BFGS-B")
        
        if res.fun < best_loss:
            best_loss = res.fun
            best_params = res.x
            best_c = float(C)

    base_time, alpha, beta_1, beta_2 = best_params
    
    # If the cliff slope addition is negligible, we can simplify/treat as no cliff
    if beta_2 < 0.01:
        beta_2 = 0.0
        best_c = 999.0

    return DegradationModelFit(base_time, alpha, beta_1, beta_2, best_c, best_loss)


def fit_fuel_model(laps: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Estimate the mean fuel consumption per lap and its standard deviation.
    """
    # Filter out pit-in and pit-out laps to calculate clean consumption
    clean_laps = [
        l for l in laps 
        if l["is_pit_in_lap"] == 0 and l["is_pit_out_lap"] == 0 and l["fuel_used_l"] > 0
    ]
    
    if not clean_laps:
        # Fallback defaults
        return 3.2, 0.1
        
    fuel_used = np.array([l["fuel_used_l"] for l in clean_laps])
    mean_fuel = float(np.mean(fuel_used))
    std_fuel = float(np.std(fuel_used))
    
    return mean_fuel, max(0.01, std_fuel)
