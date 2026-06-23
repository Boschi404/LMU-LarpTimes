import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Union
from analysis.models import DegradationModelFit


class PitStrategist:
    """
    Race pit stop strategist based on dynamic programming.
    Optimizes total race time by choosing when to pit.
    """
    def __init__(
        self,
        fuel_capacity: float,
        fuel_consumption: float,
        pit_loss: float,
        model_fit: DegradationModelFit
    ):
        self.fuel_capacity = fuel_capacity
        self.fuel_consumption = fuel_consumption
        self.pit_loss = pit_loss
        self.model_fit = model_fit
        
        # Max laps of fuel we can run on a single tank
        self.L_fuel = int(self.fuel_capacity // self.fuel_consumption)

    def optimize(
        self,
        laps_remaining: int,
        current_tyre_age: int,
        current_fuel: float,
        max_stops: int = 3
    ) -> Dict[str, Any]:
        """
        Compute the optimal strategy and alternative strategies.
        Returns a dictionary containing the optimal stops, pit laps, and total time,
        as well as alternatives (1, 2, 3 stops, etc.).
        """
        # Convert current fuel level to integer laps remaining
        fuel_curr_laps = int(current_fuel // self.fuel_consumption)
        # Ensure we have at least 0 fuel laps
        fuel_curr_laps = max(0, fuel_curr_laps)

        results = {}
        
        # Compute strategy for each stop count from 0 to max_stops
        for s in range(max_stops + 1):
            memo: Dict[Tuple[int, int, int, int], Tuple[float, List[str]]] = {}
            
            def solve(lap_idx: int, age: int, k_fuel: int, stops_left: int) -> Tuple[float, List[str]]:
                # Base case: completed all laps
                if lap_idx > laps_remaining:
                    if stops_left == 0:
                        return 0.0, []
                    else:
                        return float("inf"), []

                state = (lap_idx, age, k_fuel, stops_left)
                if state in memo:
                    return memo[state]

                best_time = float("inf")
                best_path = []

                # Option 1: Stay (no pit) - valid if we have fuel for this lap
                if k_fuel >= 1:
                    fuel_liters = k_fuel * self.fuel_consumption
                    # predict returns float
                    lap_time_est = self.model_fit.predict(age, fuel_liters)
                    future_time, future_path = solve(lap_idx + 1, age + 1, k_fuel - 1, stops_left)
                    cost = lap_time_est + future_time
                    if cost < best_time:
                        best_time = cost
                        best_path = ["stay"] + future_path

                # Option 2: Pit - valid if we have fuel for this lap and stops left
                if k_fuel >= 1 and stops_left >= 1:
                    fuel_liters = k_fuel * self.fuel_consumption
                    lap_time_est = self.model_fit.predict(age, fuel_liters)
                    # Next lap starts with full tank (self.L_fuel)
                    future_time, future_path = solve(lap_idx + 1, 0, self.L_fuel, stops_left - 1)
                    cost = lap_time_est + self.pit_loss + future_time
                    if cost < best_time:
                        best_time = cost
                        best_path = ["pit"] + future_path

                memo[state] = (best_time, best_path)
                return memo[state]

            total_time, path = solve(1, current_tyre_age, fuel_curr_laps, s)
            
            if total_time != float("inf"):
                # Convert path of decisions to actual pit laps (1-based index relative to remaining laps)
                # Note: "pit" decision on lap_idx means the car enters pits at the END of lap_idx.
                pit_laps = []
                for idx, decision in enumerate(path):
                    if decision == "pit":
                        pit_laps.append(idx + 1)
                
                results[s] = {
                    "stops": s,
                    "pit_laps": pit_laps,
                    "total_time": total_time,
                    "decisions": path
                }

        # Find the overall best strategy
        best_s = None
        best_time = float("inf")
        for s, strat in results.items():
            if strat["total_time"] < best_time:
                best_time = strat["total_time"]
                best_s = s

        optimal_strat = results[best_s] if best_s is not None else None
        
        return {
            "optimal": optimal_strat,
            "alternatives": results
        }
print("Pit strategist module written.")
