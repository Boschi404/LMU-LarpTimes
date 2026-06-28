"""
Adaptive weather forecaster.

Given current weather (state + rain_intensity + track_temp) and a
sequence of historical weather observations (with timestamps), this
module produces a simple linear forecast: if rain intensity is
trending up, predict WET in N minutes; if stable, no change.

This is intentionally simple — it's a placeholder for a real weather
service. The intent is that the UI / overlay can call it to anticipate
when to switch to wet tyres.
"""

from typing import Dict, Any, List, Optional, Tuple
import math


def linear_rain_forecast(
    history: List[Dict[str, Any]],
    horizon_minutes: int = 15,
    threshold: float = 0.3,
) -> Dict[str, Any]:
    """
    Linear extrapolation of rain intensity.

    Args:
        history: list of {t_min, rain_intensity, weather_state} (t_min in
            minutes from "now", or 0 = most recent)
        horizon_minutes: how far ahead to forecast
        threshold: rain_intensity above which we consider it WET

    Returns:
        {
            "current_state": "DRY" | "WET" | "MIXED",
            "current_rain": float,
            "predicted_state_in_horizon": "DRY" | "WET" | "MIXED",
            "predicted_rain_in_horizon": float,
            "trend_per_minute": float,  # positive = raining more
            "switch_in_minutes": Optional[int],
        }
    """
    if not history:
        return {
            "current_state": "DRY",
            "current_rain": 0.0,
            "predicted_state_in_horizon": "DRY",
            "predicted_rain_in_horizon": 0.0,
            "trend_per_minute": 0.0,
            "switch_in_minutes": None,
        }

    # Sort by t_min ascending (oldest first)
    h = sorted(history, key=lambda x: x.get("t_min", 0))
    t = [float(x.get("t_min", 0)) for x in h]
    r = [float(x.get("rain_intensity", 0.0)) for x in h]

    current_rain = r[-1] if r else 0.0
    current_state = h[-1].get("weather_state", "DRY")

    # Simple linear regression: r = a + b*t
    n = len(t)
    if n >= 2 and t[-1] != t[0]:
        mean_t = sum(t) / n
        mean_r = sum(r) / n
        num = sum((t[i] - mean_t) * (r[i] - mean_r) for i in range(n))
        den = sum((t[i] - mean_t) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0.0
    else:
        slope = 0.0

    predicted_rain = max(0.0, min(1.0, current_rain + slope * horizon_minutes))
    predicted_state = "WET" if predicted_rain >= threshold else "DRY"

    # When does it cross the threshold?
    switch_in = None
    if slope > 0 and current_rain < threshold:
        # Solve current_rain + slope*t = threshold
        t_cross = (threshold - current_rain) / slope
        if 0 <= t_cross <= 120:
            switch_in = int(math.ceil(t_cross))
    elif slope < 0 and current_rain >= threshold:
        t_cross = (current_rain - threshold) / (-slope)
        if 0 <= t_cross <= 120:
            switch_in = int(math.ceil(t_cross))

    return {
        "current_state": current_state,
        "current_rain": round(current_rain, 3),
        "predicted_state_in_horizon": predicted_state,
        "predicted_rain_in_horizon": round(predicted_rain, 3),
        "trend_per_minute": round(slope, 4),
        "switch_in_minutes": switch_in,
    }


def build_stint_weather_forecast(
    total_laps: int,
    avg_lap_time_s: float,
    weather_forecast: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Build a per-stint weather forecast from a single horizon forecast.

    Splits the race into N stints (one per pit stop) and assigns the
    predicted weather to each stint based on its time window.

    Args:
        total_laps: total laps remaining
        avg_lap_time_s: average lap time (to convert laps → minutes)
        weather_forecast: output of linear_rain_forecast()

    Returns:
        list of {"stint": i, "weather_state": "...", "rain_intensity": float}
    """
    if total_laps <= 0:
        return []

    # Default: split into 2 stints (half/half)
    n_stints = 2
    boundaries = [0, total_laps // 2, total_laps]
    if total_laps < 6:
        n_stints = 1
        boundaries = [0, total_laps]

    predicted_rain = weather_forecast.get("predicted_rain_in_horizon", 0.0)
    current_rain = weather_forecast.get("current_rain", 0.0)
    threshold = 0.3

    out = []
    for i in range(n_stints):
        # First half = current weather, second half = predicted
        rain = current_rain if i == 0 else predicted_rain
        state = "WET" if rain >= threshold else "DRY"
        out.append({
            "stint": i + 1,
            "weather_state": state,
            "rain_intensity": round(rain, 3),
        })
    return out
