"""Multi-class detection and class-specific analysis for LMU.

Provides car-to-class mapping (Hypercar/LMP2/GT3), class-specific strategy
parameters, fuzzy car name detection, and traffic penalty estimation when
different classes interact on track.
"""

from typing import Dict, List, Optional, Any

# ══════════════════════════════════════════════════════════════════════════════
# Known car-to-class mapping for LMU
# ══════════════════════════════════════════════════════════════════════════════

CAR_CLASSES: Dict[str, str] = {
    # ── Hypercar / GTP ──────────────────────────────────────────────────
    "Ferrari 499P": "Hypercar",
    "Ferrari 499P LMH": "Hypercar",
    "Toyota GR010": "Hypercar",
    "Toyota GR010 Hybrid": "Hypercar",
    "Porsche 963": "Hypercar",
    "Cadillac V-Series.R": "Hypercar",
    "Cadillac V-LMDh": "Hypercar",
    "BMW M Hybrid V8": "Hypercar",
    "Peugeot 9X8": "Hypercar",
    "Alpine A424": "Hypercar",
    "Lamborghini SC63": "Hypercar",
    "Aston Martin Valkyrie": "Hypercar",
    "Acura ARX-06": "Hypercar",
    "Vanwall Vandervell 680": "Hypercar",
    "Glickenhaus 007": "Hypercar",
    "Isotta Fraschini Tipo 6": "Hypercar",
    "Dallara LMP1": "Hypercar",
    "Rebellion R13": "Hypercar",
    "Audi R18": "Hypercar",
    "Toyota TS050": "Hypercar",
    "Porsche 919": "Hypercar",

    # ── LMP2 ────────────────────────────────────────────────────────────
    "Oreca 07": "LMP2",
    "Ligier JS P217": "LMP2",
    "Aurus 01": "LMP2",
    "Riley Mk30": "LMP2",
    "Dallara P217": "LMP2",
    "Oreca 05": "LMP2",
    "Ligier JS P2": "LMP2",
    "Gibson": "LMP2",

    # ── GT3 ─────────────────────────────────────────────────────────────
    "Ferrari 296 GT3": "GT3",
    "Porsche 911 GT3 R": "GT3",
    "Porsche 992 GT3 R": "GT3",
    "Lamborghini Huracan GT3": "GT3",
    "Lamborghini Huracán GT3": "GT3",
    "Lamborghini Huracan ST": "GT3",
    "Mercedes AMG GT3": "GT3",
    "Mercedes-AMG GT3": "GT3",
    "BMW M4 GT3": "GT3",
    "McLaren 720S GT3": "GT3",
    "Aston Martin Vantage GT3": "GT3",
    "Audi R8 LMS GT3": "GT3",
    "Audi R8 LMS Evo GT3": "GT3",
    "Audi R8 LMS GT2": "GT3",
    "Ford Mustang GT3": "GT3",
    "Corvette Z06 GT3": "GT3",
    "Corvette C8 GT3": "GT3",
    "Lexus RC F GT3": "GT3",
    "Acura NSX GT3": "GT3",
    "Nissan GT-R NISMO GT3": "GT3",
    "Honda NSX GT3": "GT3",
    "Porsche 911 GT3": "GT3",
    "Ferrari 488 GT3": "GT3",
}

# ══════════════════════════════════════════════════════════════════════════════
# Class-specific parameters for strategy calculations
# ══════════════════════════════════════════════════════════════════════════════

CLASS_PARAMS: Dict[str, Dict[str, Any]] = {
    "Hypercar": {
        "fuel_consumption": 4.5,       # L/lap (average)
        "pit_loss_seconds": 35.0,
        "tyre_wear_rate": 0.08,        # % per lap for Soft
        "avg_speed_kmh": 220,
        "display_name": "Hypercar",
        "color": "#ff6b6b",            # red
        "color_bg": "rgba(255,107,107,0.15)",
        "badge_class": "badge-hypercar",
    },
    "LMP2": {
        "fuel_consumption": 3.2,
        "pit_loss_seconds": 32.0,
        "tyre_wear_rate": 0.065,
        "avg_speed_kmh": 195,
        "display_name": "LMP2",
        "color": "#4a9eff",            # blue
        "color_bg": "rgba(74,158,255,0.15)",
        "badge_class": "badge-lmp2",
    },
    "GT3": {
        "fuel_consumption": 2.8,
        "pit_loss_seconds": 28.0,
        "tyre_wear_rate": 0.055,
        "avg_speed_kmh": 170,
        "display_name": "GT3",
        "color": "#2ea043",            # green
        "color_bg": "rgba(46,160,67,0.15)",
        "badge_class": "badge-gt3",
    },
}

# Default for unknown cars — GT3 is the most populous class in LMU
DEFAULT_CLASS = "GT3"


def detect_class(car_name: Optional[str]) -> str:
    """Detect the class of a car from its name using fuzzy substring matching.

    Iterates over known names in CAR_CLASSES and returns the class of the
    first entry whose known name is a substring of *car_name* (case-insensitive).
    Unknown cars default to GT3.
    """
    if not car_name:
        return DEFAULT_CLASS
    car_lower = car_name.lower()
    for known_name, car_class in CAR_CLASSES.items():
        if known_name.lower() in car_lower:
            return car_class
    return DEFAULT_CLASS


def get_class_params(car_class: str) -> Dict[str, Any]:
    """Get strategy parameters for a car class, falling back to GT3 defaults."""
    return CLASS_PARAMS.get(car_class, CLASS_PARAMS[DEFAULT_CLASS]).copy()


def add_class_to_laps(laps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add class info (*car_class*, *class_color*, *class_display*) to each lap dict.

    Operates in-place and also returns the list for convenience.
    """
    for lap in laps:
        car = lap.get("car", "")
        car_class = detect_class(car)
        params = get_class_params(car_class)
        lap["car_class"] = car_class
        lap["class_color"] = params["color"]
        lap["class_display"] = params["display_name"]
    return laps


def get_available_classes(laps: List[Dict[str, Any]]) -> List[str]:
    """Return sorted list of unique car classes present in *laps*."""
    classes: set = set()
    for lap in laps:
        car = lap.get("car", "")
        classes.add(detect_class(car))
    return sorted(classes, key=lambda c: {"Hypercar": 0, "LMP2": 1, "GT3": 2}.get(c, 99))


# ══════════════════════════════════════════════════════════════════════════════
# Traffic penalty estimation
# ══════════════════════════════════════════════════════════════════════════════

# Baseline traffic penalties (seconds per lap) for class interactions.
# Key = (faster_class, slower_class)
_TRAFFIC_BASE_PENALTIES: Dict[tuple, float] = {
    ("Hypercar", "GT3"): 2.0,
    ("Hypercar", "LMP2"): 0.5,
    ("LMP2", "GT3"): 1.0,
    ("Hypercar", "Hypercar"): 0.0,
    ("LMP2", "LMP2"): 0.0,
    ("GT3", "GT3"): 0.0,
}


def estimate_traffic_penalty(
    own_class: str,
    traffic_class: str,
    track_length_km: float = 5.0,
    traffic_density: float = 0.5,
) -> float:
    """Estimate lap-time penalty (seconds) caused by traffic from a slower class.

    Parameters
    ----------
    own_class : str
        Class of the car being analysed (e.g. "Hypercar").
    traffic_class : str
        Class of the slower traffic (e.g. "GT3").
    track_length_km : float
        Approximate track length in kilometres (default 5.0).
    traffic_density : float
        How much slower-class traffic is on track, 0.0 (none) to 1.0 (heavy).

    Returns
    -------
    float
        Estimated seconds lost per lap due to traffic, capped at 5.0 s.
    """
    if own_class == traffic_class:
        return 0.0

    key = (own_class, traffic_class)
    # Try both orderings
    base = _TRAFFIC_BASE_PENALTIES.get(key)
    if base is None:
        base = _TRAFFIC_BASE_PENALTIES.get((traffic_class, own_class))

    if base is None:
        # Fall back to speed-difference heuristic
        own_params = get_class_params(own_class)
        traffic_params = get_class_params(traffic_class)
        speed_diff = own_params["avg_speed_kmh"] - traffic_params["avg_speed_kmh"]
        if speed_diff <= 0:
            return 0.0
        base = (track_length_km / max(speed_diff, 1)) * 2.0  # rough heuristic

    return round(min(base * traffic_density * 1.5, 5.0), 2)


def compute_traffic_adjusted_pace(
    lap_time: float,
    own_class: str,
    slower_classes_present: List[str],
    traffic_density: float,
    track_length_km: float = 5.0,
) -> float:
    """Adjust a lap time upward to account for traffic from slower classes.

    Returns the lap time *plus* the sum of traffic penalties for every slower
    class present on track.
    """
    penalty = 0.0
    for tc in slower_classes_present:
        penalty += estimate_traffic_penalty(
            own_class, tc, track_length_km, traffic_density,
        )
    return lap_time + penalty
