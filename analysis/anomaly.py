import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import database


def detect_anomalies_for_session(
    car: str,
    track: str,
    db_path: str = database.DEFAULT_DB_PATH,
    z_threshold: float = 3.0
) -> None:
    """
    Perform robust anomaly detection on laps in the database for a given car and track.
    Updates the database with anomaly flags and reasons.
    """
    # Fetch all non-deleted laps to analyze (including valid and invalid laps,
    # but we only check valid laps for pace anomalies, and clean laps for fuel anomalies)
    all_laps = database.get_all_laps_by_session(car, track, db_path=db_path)
    if not all_laps:
        return

    # Group laps by compound and track temp band (5 degrees steps)
    buckets: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for lap in all_laps:
        if lap["is_deleted"] == 1 or lap["is_valid_lap"] == 0:
            continue
        compound = lap["compound_front"]
        temp_band = int(lap["track_temp"] / 5.0) * 5
        key = (compound, temp_band)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(lap)

    # For each bucket, compute pace anomalies
    pace_anomalies: Dict[int, str] = {}  # lap_id -> reason
    for key, laps in buckets.items():
        if len(laps) < 3:
            # Not enough data for Z-score, use fallback correction and simple range check
            alpha, beta = 0.05, 0.08
        else:
            # Perform a simple linear regression to estimate alpha (fuel) and beta (tyre age)
            # T = theta_0 + alpha * F + beta * A
            T = np.array([l["lap_time"] for l in laps])
            F = np.array([l["fuel_start_l"] for l in laps])
            A = np.array([l["tyre_age_laps"] for l in laps])
            
            # Design matrix
            X = np.column_stack((np.ones_like(F), F, A))
            try:
                # Solve least squares
                coeffs, _, _, _ = np.linalg.lstsq(X, T, rcond=None)
                # Ensure coefficients are positive/reasonable, otherwise fallback
                alpha = coeffs[1] if coeffs[1] >= 0 else 0.05
                beta = coeffs[2] if coeffs[2] >= 0 else 0.08
            except Exception:
                alpha, beta = 0.05, 0.08

        # Calculate corrected lap times
        T_raw = np.array([l["lap_time"] for l in laps])
        F_raw = np.array([l["fuel_start_l"] for l in laps])
        A_raw = np.array([l["tyre_age_laps"] for l in laps])
        T_corrected = T_raw - (alpha * F_raw + beta * A_raw)

        # Robust Z-score via MAD
        median_T = np.median(T_corrected)
        mad_T = np.median(np.abs(T_corrected - median_T))
        if mad_T < 0.15:
            mad_T = 0.15  # Minimum MAD to avoid false positives on identical laps

        z_scores = 0.6745 * (T_corrected - median_T) / mad_T

        for lap, z in zip(laps, z_scores):
            if abs(z) > z_threshold:
                pace_anomalies[lap["id"]] = f"Tempo anomalo (Z-score: {z:.2f})"

    # Compute fuel consumption anomalies
    # Group by car, track, and session_type (fuel consumption is session-independent but good to analyze globally)
    # We filter out pit-in, pit-out and invalid laps for fuel calculation
    clean_fuel_laps = [
        l for l in all_laps
        if l["is_deleted"] == 0 
          and l["is_valid_lap"] == 1 
          and l["is_pit_in_lap"] == 0 
          and l["is_pit_out_lap"] == 0
    ]
    
    fuel_anomalies: Dict[int, str] = {}
    if len(clean_fuel_laps) >= 3:
        fuel_used = np.array([l["fuel_used_l"] for l in clean_fuel_laps])
        median_fuel = np.median(fuel_used)
        mad_fuel = np.median(np.abs(fuel_used - median_fuel))
        if mad_fuel < 0.05:
            mad_fuel = 0.05

        z_fuel_scores = 0.6745 * (fuel_used - median_fuel) / mad_fuel
        
        for lap, z_f in zip(clean_fuel_laps, z_fuel_scores):
            if abs(z_f) > z_threshold:
                fuel_anomalies[lap["id"]] = f"Consumo anomalo (Z-score: {z_f:.2f})"

    # Update database for all laps
    for lap in all_laps:
        lap_id = lap["id"]
        is_anomaly = False
        reasons = []

        if lap_id in pace_anomalies:
            is_anomaly = True
            reasons.append(pace_anomalies[lap_id])
        if lap_id in fuel_anomalies:
            is_anomaly = True
            reasons.append(fuel_anomalies[lap_id])

        if is_anomaly:
            reason_text = " & ".join(reasons)
            database.update_lap_anomaly(lap_id, True, reason_text, db_path=db_path)
        else:
            # Reset to clean if it was previously flagged
            database.update_lap_anomaly(lap_id, False, None, db_path=db_path)
print("Anomaly detector module written.")
