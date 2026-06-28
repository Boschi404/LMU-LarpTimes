"""
Tyre compound recommender.

Given the laps in the database, current weather, predicted future weather
and current stint length, this module suggests the best compound for each
stint in a multi-stop strategy.

Logic:
  - A stint in DRY weather uses a DRY compound (Soft / Medium / Hard / Inter)
  - A stint in WET weather uses a WET compound
  - Among DRY compounds, the best one is the one with the best historical
    (car, track) pace AND the lowest degradation (i.e. longest stint before
    cliff), weighted by how long the stint will actually be.
  - If historical data is insufficient, fall back to a simple heuristic:
        soft   -> qualifying / short stint (≤ 8 laps)
        medium -> standard stint (8-20 laps)
        hard   -> long stint (> 20 laps)
        inter  -> light rain
        wet    -> heavy rain
"""

from typing import Dict, Any, List, Optional, Tuple
import statistics


# ── Compound catalogue ──────────────────────────────────────────────────────
# Each compound has a "type" (DRY/WET) and a typical stint length window.
# Numbers are intentionally conservative and tunable.

COMPOUND_PROFILES: Dict[str, Dict[str, Any]] = {
    # DRY
    "Soft":   {"type": "DRY", "short_stint": 0,  "long_stint": 10, "pace_factor": 0.997},
    "Medium": {"type": "DRY", "short_stint": 8,  "long_stint": 22, "pace_factor": 1.000},
    "Hard":   {"type": "DRY", "short_stint": 18, "long_stint": 40, "pace_factor": 1.004},
    # WET
    "Inter":  {"type": "WET", "short_stint": 0,  "long_stint": 30, "pace_factor": 1.020},
    "Wet":    {"type": "WET", "short_stint": 0,  "long_stint": 40, "pace_factor": 1.040},
}


def _normalise_compound(raw: Optional[str]) -> str:
    """Map vendor-specific compound names to our canonical catalogue.
    Returns 'Unknown' if no match.
    """
    if not raw:
        return "Unknown"
    s = raw.strip().lower()
    # Common patterns from LMU / rF2: "Soft", "S", "C5", "Medium", "Hard", "Inter", "Wet"
    if s.startswith("s") or "soft" in s or "supersoft" in s or "hypersoft" in s or "ultrasoft" in s:
        return "Soft"
    if s.startswith("m") or "medium" in s:
        return "Medium"
    if s.startswith("h") or "hard" in s:
        return "Hard"
    if "inter" in s:
        return "Inter"
    if "wet" in s or "full wet" in s:
        return "Wet"
    return "Unknown"


def _is_wet(weather_state: Optional[str], rain_intensity: float = 0.0) -> bool:
    """Decide whether to use a WET compound based on current/forecast state."""
    if not weather_state:
        return rain_intensity > 0.1
    return weather_state.upper() in ("WET", "RAIN", "DRIZZLE") or rain_intensity > 0.1


def _expected_stint_length(
    pit_laps_relative: List[int],
    total_laps: int,
) -> List[int]:
    """
    Given the list of pit laps (1-based, relative to laps_remaining) and the
    total number of laps, return the length of each stint in laps.
    The last stint is from last_pit to total_laps.
    """
    if not pit_laps_relative:
        return [total_laps]
    boundaries = [0] + sorted(pit_laps_relative) + [total_laps]
    return [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]


def _avg_pace_for_compound(
    laps: List[Dict[str, Any]],
    compound: str,
) -> Optional[float]:
    """
    Average lap time across the historical clean laps driven on this exact
    compound, corrected by stint age and fuel (rough): we just take the raw
    mean — not the cleanest model, but the most direct 'this compound was
    fast for me' signal.
    """
    target = compound.lower()
    samples = [
        l["lap_time"]
        for l in laps
        if _normalise_compound(l.get("compound_front") or l.get("compound")) == compound
        and l.get("is_valid_lap") == 1
        and not l.get("is_pit_in_lap")
        and not l.get("is_pit_out_lap")
    ]
    if not samples:
        return None
    return float(statistics.mean(samples))


def _avg_wear_rate_for_compound(
    laps: List[Dict[str, Any]],
    compound: str,
) -> Optional[float]:
    """
    Mean % wear increase per lap on this compound.
    Reads wear_pct_start_FL → wear_pct_end_FL (or any wheel available).
    Lower is better (lasts longer before cliff).
    """
    target = compound
    deltas = []
    for l in laps:
        if _normalise_compound(l.get("compound_front") or l.get("compound")) != target:
            continue
        ws = l.get("wear_pct_start_FL")
        we = l.get("wear_pct_end_FL")
        if ws is None or we is None:
            continue
        if we > ws:  # valid measurement (wear increased)
            deltas.append(we - ws)
    if not deltas:
        return None
    return float(statistics.mean(deltas))


def recommend_compound(
    laps_history: List[Dict[str, Any]],
    weather_state: Optional[str] = "DRY",
    rain_intensity: float = 0.0,
    track_temp: Optional[float] = None,
    stint_length: int = 15,
) -> Dict[str, Any]:
    """
    Recommend the best compound for a single stint given the conditions and
    how long the stint will be.

    Returns:
      {
        "compound": "Medium",
        "type": "DRY" or "WET",
        "score": <float lower=better>,
        "reasoning": "...",
        "alternatives": [{"compound": "Hard", "type": "DRY", "score": ...}, ...]
      }
    """
    wet = _is_wet(weather_state, rain_intensity)

    # 1. Filter candidate compounds by type
    if wet:
        # Prefer Wet over Inter for heavy rain; both are options
        candidates = ["Wet", "Inter"]
    else:
        candidates = ["Soft", "Medium", "Hard"]

    # 2. Score each candidate
    scored: List[Tuple[str, float, str]] = []
    for c in candidates:
        profile = COMPOUND_PROFILES[c]

        # Base score: how well the compound's typical stint window matches
        # the requested stint length. 0 = perfect match, 1 = off by full window.
        if profile["short_stint"] <= stint_length <= profile["long_stint"]:
            window_score = 0.0
            window_reason = f"stint length {stint_length} within {c} window"
        elif stint_length < profile["short_stint"]:
            window_score = 0.3  # compound is "too hard" — slow
            window_reason = f"{c} overbuilt for {stint_length}-lap stint"
        else:
            window_score = 0.6  # compound is "too soft" — will cliff
            window_reason = f"{c} will degrade over {stint_length}-lap stint"

        # Pace score (lower is better, in seconds)
        pace = _avg_pace_for_compound(laps_history, c)
        if pace is not None:
            # Compare to median lap time in the dataset to get a relative score
            all_paces = [
                l["lap_time"] for l in laps_history
                if l.get("is_valid_lap") == 1
                and not l.get("is_pit_in_lap")
                and not l.get("is_pit_out_lap")
                and l.get("lap_time")
            ]
            if all_paces:
                median_pace = statistics.median(all_paces)
                pace_delta = abs(pace - median_pace)
                # Convert to score: 1s = 0.5, capped at 2
                pace_score = min(pace_delta * 0.5, 2.0)
                pace_reason = f"historical pace {pace:.2f}s vs median {median_pace:.2f}s"
            else:
                pace_score = 0.5
                pace_reason = "no pace history"
        else:
            # No history: penalise less than the window mismatch
            pace_score = 0.4
            pace_reason = "no historical data for this compound"

        # Wear score (lower wear rate = better for long stint)
        wear = _avg_wear_rate_for_compound(laps_history, c)
        if wear is not None:
            # 10%/lap = 0.5 penalty, 20%/lap = 1.0
            wear_score = min(wear / 20.0, 1.0)
            wear_reason = f"avg wear {wear:.1f}%/lap"
        else:
            wear_score = 0.3
            wear_reason = "no wear history"

        # Track-temp adjustment: very hot = softer compounds suffer more
        temp_penalty = 0.0
        if track_temp is not None and not wet:
            if track_temp > 40 and c == "Soft":
                temp_penalty = 0.4
            elif track_temp < 15 and c == "Hard":
                temp_penalty = 0.2

        total = window_score + pace_score + wear_score + temp_penalty
        reason = (
            f"{c}: {window_reason}; {pace_reason}; {wear_reason}"
            + (f"; hot-track penalty for {c}" if temp_penalty else "")
        )
        scored.append((c, total, reason))

    # 3. Pick the lowest total score
    scored.sort(key=lambda t: t[1])
    best = scored[0]

    return {
        "compound": best[0],
        "type": COMPOUND_PROFILES[best[0]]["type"],
        "score": round(best[1], 3),
        "reasoning": best[2],
        "alternatives": [
            {"compound": c, "type": COMPOUND_PROFILES[c]["type"], "score": round(s, 3)}
            for c, s, _ in scored
        ],
    }


def plan_compounds(
    pit_laps_relative: List[int],
    total_laps: int,
    laps_history: List[Dict[str, Any]],
    weather_per_stint: Optional[List[Dict[str, Any]]] = None,
    track_temp: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Given an optimal pit plan, return a recommended compound for each stint.

    Args:
        pit_laps_relative: pit lap numbers, 1-based, relative to laps_remaining
        total_laps: total number of laps remaining in the race
        laps_history: historical laps (for the same car/track)
        weather_per_stint: optional list of {weather_state, rain_intensity}
            for each stint (length must match stints). If None, uses last
            known weather for ALL stints.
        track_temp: current track temperature

    Returns:
        list of {"stint": i, "laps": N, "compound": "...", "type": "...",
                 "reasoning": "..."}
    """
    stint_lengths = _expected_stint_length(pit_laps_relative, total_laps)

    results = []
    for i, length in enumerate(stint_lengths):
        if weather_per_stint and i < len(weather_per_stint):
            ws = weather_per_stint[i]
            weather = ws.get("weather_state", "DRY")
            rain = float(ws.get("rain_intensity", 0.0))
        else:
            weather = "DRY"
            rain = 0.0
            # Pull last known from history as a soft fallback
            if laps_history:
                last = laps_history[-1]
                weather = last.get("weather_state", "DRY") or "DRY"
                rain = float(last.get("rain_intensity", 0.0))

        rec = recommend_compound(
            laps_history=laps_history,
            weather_state=weather,
            rain_intensity=rain,
            track_temp=track_temp,
            stint_length=length,
        )
        results.append({
            "stint": i + 1,
            "laps": length,
            "compound": rec["compound"],
            "type": rec["type"],
            "weather": weather,
            "rain_intensity": rain,
            "reasoning": rec["reasoning"],
            "alternatives": rec["alternatives"],
        })

    return results
