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
