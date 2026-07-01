"""Advanced weather radar — predicts rain windows and gives pit timing advice."""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class RainWindow:
    probability: float  # 0-1
    expected_start_min: Optional[int]  # minutes from now
    expected_duration_min: Optional[int]
    intensity: str  # "light", "moderate", "heavy"
    recommendation: str


def analyze_rain_risk(
    current_weather: str,
    rain_intensity: float,  # 0-1
    forecast_data: Optional[List[Dict]] = None,
    lap_time_avg: float = 0,
    laps_remaining: int = 0,
    track_temp: Optional[float] = None,
) -> List[RainWindow]:
    """Analyze rain risk and return rain windows with recommendations."""
    # If no forecast data, estimate from current conditions
    windows = []

    if not forecast_data:
        # Simple heuristic: if rain_intensity > 0.3, rain is active
        if rain_intensity > 0.3:
            windows.append(RainWindow(
                probability=0.9,
                expected_start_min=0,
                expected_duration_min=None,
                intensity="heavy" if rain_intensity > 0.7 else "moderate",
                recommendation="Wet tyres required — pit now if on slicks"
            ))
        elif rain_intensity > 0.05:
            windows.append(RainWindow(
                probability=0.4,
                expected_start_min=5,
                expected_duration_min=10,
                intensity="light",
                recommendation="Light rain possible — monitor conditions"
            ))
        else:
            # Dry conditions, but check track temp for potential rain
            windows.append(RainWindow(
                probability=0.1,
                expected_start_min=None,
                expected_duration_min=None,
                intensity="light",
                recommendation="Dry conditions — no rain expected"
            ))
    else:
        # Process structured forecast data points
        for point in forecast_data:
            prob = point.get("probability", 0.0)
            start_min = point.get("expected_start_min")
            duration = point.get("expected_duration_min")
            intensity = point.get("intensity", "light")
            windows.append(RainWindow(
                probability=prob,
                expected_start_min=start_min,
                expected_duration_min=duration,
                intensity=intensity,
                recommendation=point.get("recommendation", "Monitor weather"),
            ))

    return windows


def get_pit_recommendation(
    rain_windows: List[RainWindow],
    laps_remaining: int,
    lap_time_avg: float,
    current_lap: int,
    current_compound: str,
    pit_loss_seconds: float = 30.0,
) -> str:
    """Get a human-readable pit recommendation based on weather."""
    if not rain_windows:
        return "☀️ No weather data — assume dry"

    for window in rain_windows:
        if window.probability < 0.3:
            continue

        if window.expected_start_min is not None and window.expected_start_min <= 5:
            if "Wet" not in current_compound and "Intermediate" not in current_compound and "Inter" not in current_compound:
                return "⚠️ RAIN INCOMING — Pit now for wet tyres!"
        elif window.expected_start_min is not None and window.expected_start_min <= 15:
            if "Wet" not in current_compound and "Intermediate" not in current_compound and "Inter" not in current_compound:
                return f"🌧 Rain in ~{window.expected_start_min}min — plan pit for wets soon"

    if any(w.expected_start_min == 0 and w.probability > 0.5 for w in rain_windows):
        if "Wet" not in current_compound and "Intermediate" not in current_compound and "Inter" not in current_compound:
            return "🔴 RAIN IS HERE — PIT NOW for wet tyres!"

    # If currently raining and on wets, no action needed
    for window in rain_windows:
        if window.expected_start_min == 0 and window.probability > 0.7:
            if "Wet" in current_compound or "Intermediate" in current_compound or "Inter" in current_compound:
                return "🌧 Rain active — you're on the right tyres"

    return "☀️ No weather concerns — stay on current tyres"
