"""
Shared synthetic data generators for LMU Pit Strategist tests.

All test modules MUST use this instead of inventing their own lap generators.
This ensures comparability across module tests.

Usage:
    from tests.fixtures import make_synthetic_laps, make_synthetic_session, make_synthetic_pit_stops
"""

import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Add project root so we can import database
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def make_synthetic_laps(
    n: int = 60,
    cliff_lap: int = 15,
    beta_1: float = 0.05,
    beta_2: float = 0.30,
    base_time: float = 100.0,
    alpha: float = 0.03,
    noise_std: float = 0.15,
    n_outliers: int = 0,
    outlier_range: Tuple[float, float] = (1.5, 2.5),
    fuel_start: float = 100.0,
    fuel_end: float = 0.0,
    fuel_consumption: float = 3.2,
    rng_seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Generate N synthetic laps following the degradation model.

    lap_time = base_time + alpha * fuel + deg(tyre_age) + noise

    where deg(age) = beta_1 * age + beta_2 * max(0, age - cliff_lap)

    Outliers are injected at random positions (not first/last 2 laps)
    with extra time in [outlier_range[0], outlier_range[1]] seconds.

    Returns a list of dicts compatible with database.insert_lap().
    """
    rng = np.random.default_rng(rng_seed)
    laps = []

    for i in range(1, n + 1):
        age = i
        deg = beta_1 * age + beta_2 * max(0.0, age - cliff_lap)
        # Fuel decreases linearly
        fuel = fuel_start - (fuel_start - fuel_end) * (i - 1) / max(n - 1, 1)
        lap_time = base_time + alpha * fuel + deg + float(rng.normal(0, noise_std))

        laps.append({
            "session_id": 1,
            "stint_id": 1,
            "lap_number": i,
            "lap_time": round(lap_time, 3),
            "sector_1": round(lap_time * 0.33, 3),
            "sector_2": round(lap_time * 0.34, 3),
            "sector_3": round(lap_time * 0.33, 3),
            "is_valid_lap": 1,
            "is_pit_in_lap": 0,
            "is_pit_out_lap": 0,
            "compound_front": "Medium",
            "compound_rear": "Medium",
            "tyre_age_laps": age,
            "wear_pct_start_FL": round(min(100, age * 3), 1),
            "wear_pct_start_FR": round(min(100, age * 3), 1),
            "wear_pct_start_RL": round(min(100, age * 2.8), 1),
            "wear_pct_start_RR": round(min(100, age * 2.8), 1),
            "wear_pct_end_FL": round(min(100, (age + 1) * 3), 1),
            "wear_pct_end_FR": round(min(100, (age + 1) * 3), 1),
            "wear_pct_end_RL": round(min(100, (age + 1) * 2.8), 1),
            "wear_pct_end_RR": round(min(100, (age + 1) * 2.8), 1),
            "fuel_start_l": round(fuel, 1),
            "fuel_end_l": round(max(0, fuel - fuel_consumption), 1),
            "fuel_used_l": round(fuel_consumption, 2),
            "track_temp": 28,
            "ambient_temp": 20,
            "weather_state": "DRY",
            "rain_intensity": 0.0,
            "completed_at": f"2026-01-01T10:{i:02d}:00",
            "anomaly_flag": 0,
            "anomaly_reason": None,
            "is_deleted": 0,
        })

    # Inject outliers
    if n_outliers > 0:
        valid_positions = [i for i in range(2, n - 2)]  # not first/last 2
        if valid_positions and len(valid_positions) >= n_outliers:
            chosen = rng.choice(valid_positions, size=n_outliers, replace=False)
            for idx in chosen:
                extra = rng.uniform(outlier_range[0], outlier_range[1])
                laps[idx]["lap_time"] = round(laps[idx]["lap_time"] + extra, 3)
                laps[idx]["anomaly_flag"] = 1
                laps[idx]["anomaly_reason"] = "injected_test_outlier"

    return laps


def make_synthetic_pit_stops(
    n_stops: int = 3,
    pit_loss: float = 30.0,
    in_lap_numbers: Optional[List[int]] = None,
    out_lap_numbers: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate synthetic pit stop records.
    Each stop: in_lap, out_lap, pit_loss seconds.
    """
    if in_lap_numbers is None:
        # Distribute evenly
        in_lap_numbers = [10, 25, 40][:n_stops]
    if out_lap_numbers is None:
        out_lap_numbers = [l + 1 for l in in_lap_numbers]

    stops = []
    for i, (in_lap, out_lap) in enumerate(zip(in_lap_numbers, out_lap_numbers)):
        stops.append({
            "session_id": 1,
            "lap_number": in_lap,
            "in_lap_number": in_lap,
            "out_lap_number": out_lap,
            "pit_loss": round(pit_loss + (i * 2), 1),  # slight variation
        })
    return stops


def make_synthetic_session(
    db_path: str,
    car: str = "Ferrari",
    track: str = "Le Mans",
    session_type: str = "RACE",
    n_laps: int = 60,
    seed_data: bool = True,
) -> int:
    """
    Create a real DB session + laps using the shared fixture generator.
    Returns session_id.
    """
    import database

    sid = database.create_session(
        track=track, layout="GP", car=car,
        session_type=session_type, db_path=db_path,
    )
    stint_id = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="Medium", compound_rear="Medium",
        start_lap=1, start_fuel_l=100.0, db_path=db_path,
    )
    if seed_data:
        laps = make_synthetic_laps(n=n_laps, rng_seed=42 + n_laps)
        for lap in laps:
            lap["session_id"] = sid
            lap["stint_id"] = stint_id
            database.insert_lap(lap, db_path=db_path)
    return sid


def make_db_with_laps(db_path: str, n_laps: int = 60, **kwargs) -> Tuple[int, int]:
    """
    Create a synthetic DB with N laps.
    Returns (session_id, stint_id).
    """
    import database

    sid = database.create_session(
        track="Le Mans", layout="GP", car="Ferrari",
        session_type="RACE", db_path=db_path,
    )
    stint = database.create_stint(
        session_id=sid, stint_number=1,
        compound_front="Medium", compound_rear="Medium",
        start_lap=1, start_fuel_l=100.0, db_path=db_path,
    )
    laps = make_synthetic_laps(n=n_laps, **kwargs)
    for lap in laps:
        lap["session_id"] = sid
        lap["stint_id"] = stint
        database.insert_lap(lap, db_path=db_path)
    return sid, stint


from contextlib import contextmanager


@contextmanager
def temp_db_context(n_laps: int = 0, **kwargs):
    """Context manager that creates a temp DB (empty or with synthetic laps)."""
    import tempfile as _tf
    import database as _db
    db = _tf.mktemp(suffix=".db")
    _db.init_db(db_path=db)
    if n_laps > 0:
        make_db_with_laps(db, n_laps=n_laps, **kwargs)
    try:
        yield db
    finally:
        try:
            os.unlink(db)
        except Exception:
            pass
