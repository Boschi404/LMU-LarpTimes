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
        laps_remaining: Optional[int] = None,
        current_tyre_age: int = 1,
        current_fuel: float = 100.0,
        max_stops: int = 3,
        formation_lap: bool = False,
        # Time-based race support
        duration_hours: Optional[float] = None,
        avg_pace: Optional[float] = None,
        # Optional compound recommendation inputs
        laps_history: Optional[List[Dict[str, Any]]] = None,
        weather_forecast: Optional[List[Dict[str, Any]]] = None,
        track_temp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute the optimal strategy and alternative strategies.
        Returns a dictionary containing the optimal stops, pit laps, and total time,
        as well as alternatives (1, 2, 3 stops, etc.).

        Supports two modes:
          - **Fixed laps**: pass `laps_remaining` (e.g. 50-lap sprint).
          - **Time-based**: pass `duration_hours` (e.g. 6.0 for 6 hours).
            If `avg_pace` is not given, it's estimated from the model fit at
            average fuel/age (first stint, half tank).

        If `laps_history` is provided, also returns a recommended compound per stint
        (and per alternative) using the same `analysis/compounds.py` recommender.
        """
        # Time-based → laps conversion
        if duration_hours is not None and laps_remaining is None:
            if avg_pace is None:
                # Estimate pace at half tank, fresh tyres
                pace = self.model_fit.predict(current_tyre_age, self.fuel_capacity / 2)
                if pace <= 0:
                    pace = 100.0  # safety fallback (~1:40)
            else:
                pace = avg_pace
            laps_remaining = int(duration_hours * 3600 / pace)
            laps_remaining = max(laps_remaining, 1)

        if laps_remaining is None:
            laps_remaining = 40  # sensible default
        # Convert current fuel level to integer laps remaining
        # Use / not // to avoid FP floor issues (32.0 // 3.2 = 9.0 on some builds)
        fuel_curr_laps = max(0, int(round(current_fuel / self.fuel_consumption)))

        # Account for formation lap fuel consumption
        if formation_lap and fuel_curr_laps > 0:
            fuel_curr_laps -= 1
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

                # Option 3: Out of fuel, force pit (if stops left)
                if k_fuel < 1 and stops_left >= 1:
                    # No lap — immediately pit, then start with full fuel
                    future_time, future_path = solve(lap_idx, 0, self.L_fuel, stops_left - 1)
                    cost = self.pit_loss + future_time
                    if cost < best_time:
                        best_time = cost
                        best_path = ["pit"] + future_path

                # Option 2: Pit after completing this lap - valid if we have fuel for this lap and stops left
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
                
                entry: Dict[str, Any] = {
                    "stops": s,
                    "pit_laps": pit_laps,
                    "total_time": total_time,
                    "decisions": path
                }

                # Compound recommendation per stint (only if we have history)
                if laps_history is not None:
                    from analysis.compounds import plan_compounds
                    entry["compound_plan"] = plan_compounds(
                        pit_laps_relative=pit_laps,
                        total_laps=laps_remaining,
                        laps_history=laps_history,
                        weather_per_stint=weather_forecast,
                        track_temp=track_temp,
                    )

                results[s] = entry

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
            "alternatives": results,
            "laps_used": laps_remaining,
        }
print("Pit strategist module written.")
