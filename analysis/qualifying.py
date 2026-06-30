"""Qualifying strategy analysis.

Detects outlap / hotlap / inlap patterns and suggests:
  - Minimum viable fuel load
  - Optimal outlap pace (slow enough to save fuel, fast enough to heat tyres)
  - Optimal inlap pace
  - Fuel saving potential vs current setup
"""
from typing import Dict, Any, List, Optional, Tuple
from analysis.models import DegradationModelFit


# ── Lap type classification ──────────────────────────────────────────────

LAP_OUTLAP = "outlap"
LAP_HOTLAP = "hotlap"
LAP_INLAP = "inlap"
LAP_UNKNOWN = "unknown"

# ── Tyre temperature states ──────────────────────────────────────────────

TYRE_COLD = "cold"
TYRE_IN_WINDOW = "in_window"
TYRE_DEGRADED = "degraded"


def classify_qualifying_laps(laps: List[Dict[str, Any]]) -> List[str]:
    """Classify each lap in a qualifying session by its role.

    Heuristics (applied in order):
      1. If ``is_pit_out_lap`` → outlap.
      2. If ``is_pit_in_lap`` → inlap.
      3. First *N* non-pit-out laps after a pit-out → hot laps.
      4. Anything after an inlap is ignored (usually partial).
      5. If no pit-out is found → all laps are ``unknown``.

    Returns a list of the same length as *laps*.
    """
    if not laps:
        return []

    types: List[str] = [LAP_UNKNOWN] * len(laps)

    # Find first pit-out index and last pit-in index
    out_idx: Optional[int] = None
    in_idx: Optional[int] = None
    for i, lap in enumerate(laps):
        if lap.get("is_pit_out_lap"):
            out_idx = i
        if lap.get("is_pit_in_lap"):
            in_idx = i

    if out_idx is None:
        # No pit out → cannot reliably classify
        return types

    # Everything from out_idx onwards is hot laps until pit-in
    for i in range(out_idx, len(laps)):
        if in_idx is not None and i > in_idx:
            types[i] = LAP_INLAP  # post-inlap garbage
        else:
            types[i] = LAP_HOTLAP

    # Override: pit-out lap is outlap
    if out_idx is not None:
        types[out_idx] = LAP_OUTLAP
    # Override: pit-in lap is inlap (if we found one)
    if in_idx is not None:
        types[in_idx] = LAP_INLAP

    return types


# ── Tyre temperature window estimation ──────────────────────────────────

_COMPOUND_WINDOW_END: Dict[str, int] = {
    "Soft": 2,
    "Medium": 3,
    "Hard": 4,
}
_WET_COMPOUNDS = {"Wet", "Intermediate", "FullWet", "Wet"}


def estimate_tyre_temp_window(
    laps: List[Dict[str, Any]],
    types: List[str],
) -> Dict[str, Any]:
    """Estimate tyre temperature window for qualifying laps.

    Uses ``tyre_age_laps`` as a proxy for tyre temperature, adjusted by
    ``compound_front`` and ``track_temp`` from the database.

    Parameters
    ----------
    laps:
        List of lap dicts as returned by ``database.get_laps_for_analysis``.
    types:
        Lap role classification from :func:`classify_qualifying_laps`.

    Returns
    -------
    dict with keys:
        - **laps_classified** — per-lap tyre state annotations
        - **best_in_window** — fastest lap when tyres were optimal
        - **best_outside_window** — fastest lap when cold or degraded
        - **window_lost_time** — gap between best in-window and outside
        - **optimal_hotlaps_count** — consecutive hotlaps before deg
        - **tyre_window_message** — human-readable summary
    """
    if not laps or not types:
        return {
            "laps_classified": [],
            "best_in_window": None,
            "best_outside_window": None,
            "window_lost_time": None,
            "optimal_hotlaps_count": 0,
            "tyre_window_message": "No lap data available.",
        }

    # Determine compound and track temperature (use first lap as reference)
    compound: str = laps[0].get("compound_front", "Medium") or "Medium"
    track_temp: Optional[float] = laps[0].get("track_temp")

    is_wet: bool = compound in _WET_COMPOUNDS

    if is_wet:
        # Wet/Intermediate tyres never reach optimal temperature window
        window_start: int = 999
        window_end: int = -1
    else:
        window_start = 2
        window_end = _COMPOUND_WINDOW_END.get(compound, 3)

        # Temperature adjustments
        if track_temp is not None:
            if track_temp < 20:
                window_start += 1  # slower warmup on cold track
            if track_temp > 35:
                window_end -= 1  # faster degradation on hot track

        # Clamp to sensible bounds
        window_start = max(2, window_start)
        window_end = max(window_start, window_end)

    # Classify each lap
    laps_classified: List[Dict[str, Any]] = []
    best_in_window: Optional[float] = None
    best_outside_window: Optional[float] = None

    for lap, typ in zip(laps, types):
        lap_number: int = lap.get("lap_number", 0)
        lap_time: Optional[float] = lap.get("lap_time")
        tyre_age: int = lap.get("tyre_age_laps", 1)

        # Determine tyre state
        if is_wet:
            tyre_state: str = TYRE_DEGRADED
        elif tyre_age < window_start:
            tyre_state = TYRE_COLD
        elif tyre_age <= window_end:
            tyre_state = TYRE_IN_WINDOW
        else:
            tyre_state = TYRE_DEGRADED

        laps_classified.append({
            "lap_number": lap_number,
            "role": typ,
            "tyre_state": tyre_state,
            "lap_time": lap_time,
        })

        # Track best times
        if lap_time is not None:
            if tyre_state == TYRE_IN_WINDOW:
                if best_in_window is None or lap_time < best_in_window:
                    best_in_window = lap_time
            else:
                if best_outside_window is None or lap_time < best_outside_window:
                    best_outside_window = lap_time

    # Window lost time (how much slower you are outside the window)
    window_lost_time: Optional[float] = None
    if best_in_window is not None and best_outside_window is not None:
        delta = best_outside_window - best_in_window
        window_lost_time = max(0.0, delta)

    # How many consecutive hotlaps you can do before falling out of window
    if is_wet:
        optimal_hotlaps_count: int = 0
    else:
        optimal_hotlaps_count = max(0, window_end - window_start + 1)

    # ── Human-readable message ─────────────────────────────────────────
    if is_wet:
        compound_label = compound or "Wet"
        tyre_window_message = (
            f"🌧 {compound_label} tyres — optimal window N/A, "
            f"consider pit strategy based on track conditions"
        )
    else:
        compound_label = compound or "Medium"
        temp_note = ""
        if track_temp is not None:
            if track_temp < 20:
                temp_note = f" (cold track {track_temp:.0f}°C → +1 lap warmup)"
            elif track_temp > 35:
                temp_note = f" (hot track {track_temp:.0f}°C → faster deg)"

        hotlap_plural = "s" if optimal_hotlaps_count != 1 else ""
        tyre_window_message = (
            f"🛞 {compound_label} tyres: optimal laps {window_start}-{window_end} "
            f"({optimal_hotlaps_count} hotlap{hotlap_plural} per run)"
            f"{temp_note}"
        )

    return {
        "laps_classified": laps_classified,
        "best_in_window": best_in_window,
        "best_outside_window": best_outside_window,
        "window_lost_time": window_lost_time,
        "optimal_hotlaps_count": optimal_hotlaps_count,
        "tyre_window_message": tyre_window_message,
    }


# ── Qualifying analyst ───────────────────────────────────────────────────

class QualifyingAnalyst:
    """Analyse telemetry from a qualifying session and produce suggestions."""

    def __init__(
        self,
        fuel_consumption_lap: float,  # litres per lap
        model_fit: DegradationModelFit,
        safety_buffer_laps: float = 0.3,  # extra fuel (in laps-worth)
        target_hotlaps: int = 2,          # desired hot laps per run
    ):
        self.fuel_consumption_lap = fuel_consumption_lap
        self.model_fit = model_fit
        self.safety_buffer_laps = safety_buffer_laps
        self.target_hotlaps = target_hotlaps

    def analyze(
        self,
        laps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run full qualifying analysis on *laps*.

        Returns a dictionary with lap classification, fuel assessment,
        and pace targets.
        """
        types = classify_qualifying_laps(laps)
        result: Dict[str, Any] = {
            "lap_types": types,
            "num_outlaps": types.count(LAP_OUTLAP),
            "num_hotlaps": types.count(LAP_HOTLAP),
            "num_inlaps": types.count(LAP_INLAP),
        }

        # Group by type
        hotlaps = [l for l, t in zip(laps, types) if t == LAP_HOTLAP]
        outlaps = [l for l, t in zip(laps, types) if t == LAP_OUTLAP]
        inlaps = [l for l, t in zip(laps, types) if t == LAP_INLAP]

        # ── Pace deltas ────────────────────────────────────────────────
        if hotlaps:
            best_hot = min(l["lap_time"] for l in hotlaps)
            avg_hot = sum(l["lap_time"] for l in hotlaps) / len(hotlaps)
            result["best_hotlap_time"] = best_hot
            result["avg_hotlap_time"] = avg_hot
        else:
            best_hot = None
            result["best_hotlap_time"] = None
            result["avg_hotlap_time"] = None

        if outlaps:
            avg_out = sum(l["lap_time"] for l in outlaps) / len(outlaps)
            result["avg_outlap_time"] = avg_out
            result["outlap_delta_from_hot"] = (
                avg_out - best_hot if best_hot else None
            )
        else:
            result["avg_outlap_time"] = None
            result["outlap_delta_from_hot"] = None

        if inlaps:
            avg_in = sum(l["lap_time"] for l in inlaps) / len(inlaps)
            result["avg_inlap_time"] = avg_in
            result["inlap_delta_from_hot"] = (
                avg_in - best_hot if best_hot else None
            )
        else:
            result["avg_inlap_time"] = None
            result["inlap_delta_from_hot"] = None

        # ── Fuel analysis ───────────────────────────────────────────────
        fuel_data = self._fuel_analysis(laps, types)
        result.update(fuel_data)

        # ── Tyre temperature window analysis ─────────────────────────
        tyre_data = estimate_tyre_temp_window(laps, types)
        result["tyre_temp_window"] = tyre_data

        # ── Suggestions ────────────────────────────────────────────────
        result["suggestions"] = self._build_suggestions(result, laps)

        return result

    def _fuel_analysis(
        self,
        laps: List[Dict[str, Any]],
        types: List[str],
    ) -> Dict[str, Any]:
        """Extract fuel usage stats and compute optimal fuel."""
        hotlaps = [l for l, t in zip(laps, types) if t == LAP_HOTLAP]
        outlaps = [l for l, t in zip(laps, types) if t == LAP_OUTLAP]
        inlaps = [l for l, t in zip(laps, types) if t == LAP_INLAP]

        # Actual per-lap consumption
        def mean_consumption(ll: List[Dict[str, Any]]) -> Optional[float]:
            vals = [l.get("fuel_used_l", 0) for l in ll if l.get("fuel_used_l", 0) > 0]
            return sum(vals) / len(vals) if vals else None

        cons_out = mean_consumption(outlaps)
        cons_hot = mean_consumption(hotlaps)
        cons_in = mean_consumption(inlaps)

        # Weighted average consumption
        all_cons = [
            v for v in [cons_out, cons_hot, cons_in] if v is not None
        ]
        avg_cons = (
            sum(all_cons) / len(all_cons) if all_cons
            else self.fuel_consumption_lap
        )

        # Current fuel data from the last lap
        last_lap = laps[-1] if laps else {}
        fuel_start = last_lap.get("fuel_start_l", 0) or 0
        fuel_end = last_lap.get("fuel_end_l", 0) or 0
        fuel_current = fuel_end  # last reading
        fuel_used_total = sum(
            l.get("fuel_used_l", 0) for l in laps if l.get("fuel_used_l")
        )

        # Minimum fuel needed for one more run: outlap + N hotlaps + inlap + buffer
        laps_needed = 1 + self.target_hotlaps + 1  # out + hot*N + in
        fuel_needed = laps_needed * avg_cons * (1 + self.safety_buffer_laps / laps_needed)
        fuel_saving = max(0, fuel_current - fuel_needed)

        return {
            "avg_fuel_consumption": avg_cons,
            "fuel_start": fuel_start,
            "fuel_end": fuel_end,
            "fuel_current": fuel_current,
            "fuel_used_total": fuel_used_total,
            "fuel_needed_for_run": round(fuel_needed, 1),
            "fuel_saving_potential": round(fuel_saving, 1),
            "estimated_laps_in_tank": round(fuel_current / avg_cons, 1) if avg_cons > 0 else 0,
            "target_hotlaps": self.target_hotlaps,
        }

    def _build_suggestions(
        self,
        analysis: Dict[str, Any],
        laps: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate human-readable suggestions from the analysis."""
        suggestions: List[str] = []

        # 1. Fuel saving
        fuel_save = analysis.get("fuel_saving_potential", 0)
        if fuel_save > 1.0:
            suggestions.append(
                f"💧 You can reduce fuel by ~{fuel_save:.1f}L "
                f"({analysis.get('estimated_laps_in_tank', 0):.1f} laps in tank, "
                f"need ~{analysis.get('fuel_needed_for_run', 0):.1f}L for "
                f"{analysis.get('target_hotlaps', 2)} hot laps + outlap + inlap)"
            )
        elif fuel_save > 0.2:
            suggestions.append(
                f"💧 Slight fuel surplus ({fuel_save:.1f}L) — could shave a tiny bit"
            )
        else:
            suggestions.append(
                f"✅ Fuel load looks efficient for {analysis.get('target_hotlaps', 2)} hot laps"
            )

        # 2. Outlap pace
        out_delta = analysis.get("outlap_delta_from_hot")
        if out_delta is not None:
            if out_delta > 10:
                suggestions.append(
                    f"🐢 Outlap is {out_delta:.1f}s slower than hot lap — "
                    f"you could push a bit more to heat tyres, "
                    f"or accept the extra time if fuel-saving"
                )
            elif out_delta > 5:
                suggestions.append(
                    f"⏱ Outlap is {out_delta:.1f}s off hot lap pace — "
                    f"reasonable outlap. You could gain ~{out_delta-3:.1f}s by "
                    f"pushing slightly more"
                )
            else:
                suggestions.append(
                    f"⚡ Good outlap (only {out_delta:.1f}s off pace) — "
                    f"tyres seem well managed"
                )

        # 3. Inlap pace
        in_delta = analysis.get("inlap_delta_from_hot")
        if in_delta is not None:
            if in_delta > 15:
                suggestions.append(
                    f"🏁 Inlap is {in_delta:.1f}s slower — fine if saving fuel, "
                    f"but you could tighten it to ~{max(5.0, in_delta - 5):.1f}s delta"
                )
            elif in_delta > 5:
                suggestions.append(
                    f"🏁 Inlap delta {in_delta:.1f}s — reasonable. "
                    f"Try targeting ~{max(3.0, in_delta - 3):.1f}s for fuel savings"
                )

        # 4. Hot lap count suggestion
        num_hot = analysis.get("num_hotlaps", 0)
        if num_hot < self.target_hotlaps:
            suggestions.append(
                f"🔄 Only {num_hot} hot lap(s) completed — "
                f"try for {self.target_hotlaps} per run if tyres can manage"
            )

        if not suggestions:
            suggestions.append("Not enough data for qualifying analysis yet.")

        return suggestions


def analyze_qualifying(
    laps: List[Dict[str, Any]],
    fuel_consumption_lap: float = 3.2,
    model_fit: Optional[DegradationModelFit] = None,
    target_hotlaps: int = 2,
) -> Dict[str, Any]:
    """Convenience wrapper — create and run a `QualifyingAnalyst`."""
    if model_fit is None:
        model_fit = DegradationModelFit()
    analyst = QualifyingAnalyst(
        fuel_consumption_lap=fuel_consumption_lap,
        model_fit=model_fit,
        target_hotlaps=target_hotlaps,
    )
    return analyst.analyze(laps)
