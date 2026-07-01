"""Real-time tyre management: predicts remaining useful life of tyres during a stint."""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class TyreStatus:
    """Predicted status of the current set of tyres."""
    optimal: bool           # Tyres in optimal window?
    remaining_laps: int     # Estimated laps before cliff
    cliff_lap: int          # Current estimated cliff lap
    wear_rate: float        # % wear per lap (recent average)
    temp_status: str        # "cold" / "optimal" / "hot" / "degraded"
    recommendation: str     # Human-readable advice


# Base wear rates per compound (% wear per lap, as fraction of 1.0)
COMPOUND_WEAR_RATES = {
    "Soft": 0.10,
    "Medium": 0.065,
    "Hard": 0.04,
    "Wet": 0.08,
    "Intermediate": 0.07,
}

# Optimal temperature window (tyre age laps) per compound
COMPOUND_TEMP_WINDOW = {
    "Soft": (2, 3),
    "Medium": (2, 4),
    "Hard": (2, 5),
}

CLIFF_THRESHOLD = 0.30  # 30% remaining tread = cliff threshold


def normalize_compound(compound: str) -> str:
    """Match compound string to known keys regardless of casing."""
    mapping = {
        "soft": "Soft",
        "medium": "Medium",
        "hard": "Hard",
        "wet": "Wet",
        "intermediate": "Intermediate",
        "inters": "Intermediate",
        "super soft": "Soft",
        "supersoft": "Soft",
        "ultrasoft": "Soft",
        "ultra soft": "Soft",
    }
    return mapping.get(compound.lower().strip(), compound)


def estimate_remaining_life(
    current_wear: List[float],           # [FL, FR, RL, RR] 0.0-1.0 (1.0 = new)
    tyre_age_laps: int,                  # Current tyre age in laps
    compound: str,                       # "Soft", "Medium", "Hard", etc.
    track_temp: Optional[float] = None,  # Track temperature in Celsius
    historical_cliff: Optional[int] = None,  # Historical cliff lap from model
    recent_wear_rates: Optional[List[float]] = None,  # Wear %/lap for last N laps
) -> TyreStatus:
    """Predict remaining tyre life based on current state.

    Parameters
    ----------
    current_wear : list of float
        Tyre wear for [FL, FR, RL, RR] where 0.0 = completely worn, 1.0 = brand new.
    tyre_age_laps : int
        Number of laps this tyre set has been used.
    compound : str
        Tyre compound name (Soft, Medium, Hard, Wet, Intermediate).
    track_temp : float or None
        Track temperature in degrees Celsius.
    historical_cliff : int or None
        Cliff lap from the fitted degradation model (if available).
    recent_wear_rates : list of float or None
        Measured wear rates (% per lap as fraction of 1.0) for recent laps.

    Returns
    -------
    TyreStatus with prediction and recommendation.
    """
    # --- 1. Determine base wear rate ---
    base_rate = COMPOUND_WEAR_RATES.get(normalize_compound(compound), 0.065)

    # --- 2. Use recent actual wear rate if available ---
    if recent_wear_rates and len(recent_wear_rates) >= 2:
        # Average of last 3 measurements (or fewer if not enough)
        recent = recent_wear_rates[-3:]
        wear_rate = sum(recent) / len(recent)
    else:
        wear_rate = base_rate

    # --- 3. Temperature adjustment ---
    temp_factor = 1.0
    if track_temp is not None:
        if track_temp > 40:
            temp_factor = 1.30   # +30% wear on very hot track
        elif track_temp > 35:
            temp_factor = 1.15   # +15% wear on hot track
        elif track_temp < 15:
            temp_factor = 0.85   # -15% wear on cold track
        elif track_temp < 10:
            temp_factor = 0.75   # -25% wear on very cold track

    adjusted_rate = wear_rate * temp_factor

    # --- 4. Calculate remaining life ---
    # Average remaining tread across all four corners
    avg_wear = sum(current_wear) / len(current_wear) if current_wear else 0.5
    remaining_tread = max(0.0, avg_wear - CLIFF_THRESHOLD)

    if adjusted_rate > 0:
        remaining_laps = int(remaining_tread / adjusted_rate)
    else:
        remaining_laps = 0

    # --- 5. Cliff lap estimation ---
    if historical_cliff is not None and historical_cliff < 999:
        # Combine historical model with real-time data
        cliff_from_historical = historical_cliff
        cliff_from_current = tyre_age_laps + remaining_laps
        cliff_lap = min(cliff_from_historical, cliff_from_current)
    else:
        cliff_lap = tyre_age_laps + remaining_laps

    # Ensure cliff_lap is at least tyre_age_laps
    if cliff_lap < tyre_age_laps:
        cliff_lap = tyre_age_laps

    # Recompute remaining_laps from cliff_lap if we used historical
    if historical_cliff is not None and historical_cliff < 999:
        remaining_laps = max(0, cliff_lap - tyre_age_laps)

    # --- 6. Temperature status ---
    temp_window = COMPOUND_TEMP_WINDOW.get(normalize_compound(compound), (2, 3))
    if tyre_age_laps < temp_window[0]:
        temp_status = "cold"
    elif tyre_age_laps <= temp_window[1]:
        temp_status = "optimal"
    elif tyre_age_laps <= temp_window[1] + 2:
        temp_status = "hot"
    else:
        temp_status = "degraded"

    # --- 7. Generate recommendation ---
    recommendations = []
    if avg_wear <= CLIFF_THRESHOLD + 0.02 or remaining_laps <= 0:
        recommendations.append("⚠ PIT NOW — tyres critically worn")
    elif remaining_laps <= 1:
        recommendations.append("⚠ PIT NOW — tyres near cliff")
    elif remaining_laps <= 2:
        recommendations.append(f"Pit in {remaining_laps} laps — tyres near cliff")
    elif remaining_laps <= 5:
        recommendations.append(f"Watch tyres — ~{remaining_laps} laps remaining")
    else:
        recommendations.append(f"Tyres OK — ~{remaining_laps} laps before cliff")

    if temp_status == "cold":
        recommendations.append("Tyres cold — push to heat them")
    elif temp_status == "hot":
        recommendations.append("Tyres hot — manage pace")
    elif temp_status == "degraded":
        recommendations.append("Tyres overheating — adjust pace")

    return TyreStatus(
        optimal=(temp_status == "optimal" and remaining_laps > 0),
        remaining_laps=remaining_laps,
        cliff_lap=cliff_lap,
        wear_rate=round(adjusted_rate * 100, 1),
        temp_status=temp_status,
        recommendation=" | ".join(recommendations),
    )
