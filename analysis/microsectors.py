"""Micro-sector analysis and optimal lap assembly.

Splits each of the 3 standard sectors into N sub-sectors (default 3),
then computes the theoretical optimal lap as the sum of the best
micro-sector times across all laps.
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np

# Number of micro-sectors per standard sector
MICRO_SECTORS_PER_SECTOR = 3
TOTAL_MICRO_SECTORS = MICRO_SECTORS_PER_SECTOR * 3  # 9

# Micro-sector labels
MICRO_LABELS = [
    "S1-A (entry)", "S1-B (mid)", "S1-C (exit)",
    "S2-A (entry)", "S2-B (mid)", "S2-C (exit)",
    "S3-A (entry)", "S3-B (mid)", "S3-C (exit)",
]


def compute_microsector_times(
    sector_1: float,
    sector_2: float,
    sector_3: float,
    speed_samples: Optional[List[Dict[str, Any]]] = None,
    track_distance_km: Optional[float] = None,
) -> List[float]:
    """Split each sector into N micro-sectors with estimated times.

    If speed samples are available, uses speed changes to detect natural
    breakpoints (braking zones, corner exits). Otherwise splits evenly.

    Returns list of 9 micro-sector times.
    """
    sector_times = [sector_1, sector_2, sector_3]
    micro_times = []

    if speed_samples and len(speed_samples) > 3:
        # Use speed trace to find natural breakpoints within each sector
        total_time = sum(sector_times) if sum(sector_times) > 0 else 1.0
        for si, sec_time in enumerate(sector_times):
            # Find samples in this sector's time range
            sector_start = sum(sector_times[:si]) / total_time
            sector_end = (sum(sector_times[:si + 1])) / total_time

            sec_samples = [
                s for s in speed_samples
                if sector_start <= (s.get('distance_pct', 0) or 0) / 100.0 <= sector_end
            ]

            if len(sec_samples) >= 6:
                # Find braking points (local speed minima)
                speeds = [s.get('speed', 0) or 0 for s in sec_samples]
                # Split at points of max deceleration
                sub_times = _split_by_speed_profile(sec_time, speeds, MICRO_SECTORS_PER_SECTOR)
                micro_times.extend(sub_times)
            else:
                # Even split as fallback
                part = sec_time / MICRO_SECTORS_PER_SECTOR if sec_time > 0 else 0
                micro_times.extend([part] * MICRO_SECTORS_PER_SECTOR)
    else:
        # Even split
        for sec_time in sector_times:
            part = sec_time / MICRO_SECTORS_PER_SECTOR if sec_time > 0 else 0
            micro_times.extend([part] * MICRO_SECTORS_PER_SECTOR)

    return micro_times


def _split_by_speed_profile(
    sector_time: float,
    speeds: List[float],
    n_parts: int,
) -> List[float]:
    """Split a sector's time into N parts using speed profile to find natural breakpoints.

    Detects deceleration events (braking) and uses them as micro-sector boundaries.
    Falls back to even split if no clear braking points.
    """
    if len(speeds) < n_parts + 1:
        part = sector_time / n_parts if sector_time > 0 else 0
        return [part] * n_parts

    # Find local minima (braking points)
    diffs = np.diff(speeds)
    brake_zones = []
    for i in range(1, len(diffs) - 1):
        if diffs[i - 1] > 0 and diffs[i] < 0 and abs(diffs[i]) > 5:
            brake_zones.append(i)

    if len(brake_zones) >= n_parts - 1:
        # Use detected braking zones as split points
        # Pick the strongest braking events
        brake_strengths = [(i, abs(diffs[i])) for i in brake_zones]
        brake_strengths.sort(key=lambda x: x[1], reverse=True)
        split_indices = sorted([i for i, _ in brake_strengths[:n_parts - 1]])

        # Convert sample indices to time proportions
        proportions = [(split_indices[0] + 1) / len(speeds)]
        for i in range(1, len(split_indices)):
            proportions.append((split_indices[i] - split_indices[i - 1]) / len(speeds))
        proportions.append(1.0 - sum(proportions))

        # Normalize to ensure we sum to 1.0 exactly
        total_prop = sum(proportions)
        if total_prop > 0:
            proportions = [p / total_prop for p in proportions]

        return [sector_time * p for p in proportions]

    # Fallback: even split
    part = sector_time / n_parts if sector_time > 0 else 0
    return [part] * n_parts


def compute_optimal_lap(
    laps: List[Dict[str, Any]],
    telemetry_map: Optional[Dict[int, Dict]] = None,
    track_distance_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute the theoretical optimal lap from a set of laps.

    Args:
        laps: List of lap dicts (must have id, lap_time, sector_1/2/3)
        telemetry_map: Optional dict mapping lap_id -> list of speed samples
        track_distance_km: Track length for distance normalization

    Returns:
        Dict with:
        - optimal_micro_times: list of 9 best micro-sector times
        - optimal_total_time: sum of best micro-sector times
        - improvement_potential: optimal vs actual best lap
        - micro_labels: labels for each micro-sector
        - per_lap_deltas: list of deltas per micro-sector for each lap
        - best_lap_id: the actual fastest lap
        - best_lap_time: fastest actual lap time
    """
    if not laps:
        return {"error": "No lap data available"}

    n_micro = TOTAL_MICRO_SECTORS

    # Compute micro-sector times for all laps
    all_micro_times: List[List[float]] = []
    for lap in laps:
        samples = telemetry_map.get(lap['id'], []) if telemetry_map else []
        micro = compute_microsector_times(
            lap.get('sector_1', 0) or 0,
            lap.get('sector_2', 0) or 0,
            lap.get('sector_3', 0) or 0,
            samples,
            track_distance_km,
        )
        all_micro_times.append(micro)

    if not all_micro_times:
        return {"error": "Could not compute micro-sector times"}

    # Best per micro-sector across all laps
    optimal_micro = []
    for i in range(n_micro):
        times_i = [mt[i] for mt in all_micro_times if i < len(mt)]
        if times_i:
            optimal_micro.append(min(times_i))
        else:
            optimal_micro.append(0)

    optimal_total = sum(optimal_micro)

    # Find the actual best lap by total lap time
    valid_laps = [l for l in laps if l.get('lap_time') is not None and l.get('lap_time', 0) > 0]
    if not valid_laps:
        return {"error": "No valid laps with lap_time data"}

    best_lap = min(valid_laps, key=lambda l: l.get('lap_time', float('inf')))
    best_lap_time = best_lap.get('lap_time', 0) or 0
    improvement = best_lap_time - optimal_total

    # Per-lap delta from optimal
    per_lap_deltas = []
    for i, (lap, micro_times) in enumerate(zip(laps, all_micro_times)):
        if len(micro_times) == n_micro:
            deltas = [round(micro_times[j] - optimal_micro[j], 4) for j in range(n_micro)]
        else:
            deltas = [0] * n_micro
        per_lap_deltas.append({
            "lap_id": lap['id'],
            "lap_number": lap.get('lap_number', i + 1),
            "total_gap": round(sum(deltas), 4),
            "micro_deltas": deltas,
            "micro_times": micro_times[:n_micro] if len(micro_times) >= n_micro
                           else micro_times + [0] * (n_micro - len(micro_times)),
        })

    return {
        "optimal_micro_times": [round(t, 4) for t in optimal_micro],
        "optimal_total_time": round(optimal_total, 4),
        "improvement_potential": round(max(0, improvement), 4),
        "improvement_percent": round(
            max(0, improvement) / best_lap_time * 100, 2
        ) if best_lap_time > 0 else 0,
        "micro_labels": MICRO_LABELS[:n_micro],
        "num_micro_sectors": n_micro,
        "per_lap_deltas": per_lap_deltas,
        "best_lap_id": best_lap['id'],
        "best_lap_time": best_lap_time,
        "best_lap_number": best_lap.get('lap_number', 0),
        "num_laps_analyzed": len(laps),
    }


def format_time(seconds: float) -> str:
    """Format seconds to human-readable time string."""
    if seconds is None or seconds <= 0:
        return "0.000"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:06.3f}" if m > 0 else f"{s:.3f}"
