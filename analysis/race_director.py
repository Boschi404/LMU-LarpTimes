"""Race Director — reconstructs a full race session timeline from lap data."""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class RaceEvent:
    lap_number: int
    event_type: str  # "pit_in", "pit_out", "weather_change", "anomaly", "stint_start", "stint_end"
    description: str
    severity: str  # "info", "warning", "critical"
    lap_time: Optional[float] = None


@dataclass
class StintInfo:
    stint_number: int
    start_lap: int
    end_lap: int
    compound: str
    laps_in_stint: int
    avg_lap_time: Optional[float]
    best_lap_time: Optional[float]
    fuel_used: Optional[float]


@dataclass
class RaceSummary:
    session_id: str
    car: str
    track: str
    total_laps: int
    total_time: Optional[float]
    best_lap_time: Optional[float]
    avg_lap_time: Optional[float]
    stints: List[StintInfo]
    events: List[RaceEvent]
    weather_timeline: List[Dict[str, Any]]
    positions: Optional[List[Dict[str, Any]]] = None


def build_race_timeline(
    laps: List[Dict[str, Any]],
    session_id: str,
) -> Optional[RaceSummary]:
    """Build a complete race timeline from lap data."""
    if not laps:
        return None

    # Basic info
    first = laps[0]
    car = first.get("car", "")
    track = first.get("track", "")
    total_laps = len(laps)

    # Calculate total time
    valid_laps = [l for l in laps if l.get("lap_time") and l.get("is_valid_lap")]
    total_time = sum(l.get("lap_time", 0) for l in valid_laps) if valid_laps else None
    best_lap_time = min(l.get("lap_time") for l in valid_laps) if valid_laps else None
    avg_lap_time = total_time / len(valid_laps) if valid_laps and total_time else None

    # Build stints
    stints = []
    events = []
    current_stint = None

    for i, lap in enumerate(laps):
        lap_num = lap.get("lap_number", i + 1)
        is_pit_in = lap.get("is_pit_in_lap", False)
        is_pit_out = lap.get("is_pit_out_lap", False)
        compound = lap.get("compound_front", "Unknown")
        stint = lap.get("stint_number", 1)
        stint = stint if stint is not None else 1

        # Stint tracking
        if current_stint is None or stint != current_stint["stint_number"]:
            if current_stint is not None:
                current_stint["end_lap"] = lap_num - 1
                stints.append(current_stint)
                events.append(RaceEvent(
                    lap_number=lap_num - 1,
                    event_type="stint_end",
                    description=f"End of stint {current_stint['stint_number']} ({current_stint['compound']})",
                    severity="info",
                ))
            current_stint = {
                "stint_number": stint,
                "start_lap": lap_num,
                "end_lap": lap_num,
                "compound": compound,
                "laps_in_stint": 0,
                "avg_lap_time": None,
                "best_lap_time": None,
                "fuel_used": 0,
            }
            events.append(RaceEvent(
                lap_number=lap_num,
                event_type="stint_start",
                description=f"Stint {stint} begins — {compound} tyres",
                severity="info",
            ))

        if current_stint:
            current_stint["end_lap"] = lap_num
            current_stint["laps_in_stint"] += 1

            lt = lap.get("lap_time")
            if lt:
                if current_stint["best_lap_time"] is None or lt < current_stint["best_lap_time"]:
                    current_stint["best_lap_time"] = lt

            fuel = lap.get("fuel_used_l", 0)
            if fuel:
                current_stint["fuel_used"] = (current_stint["fuel_used"] or 0) + fuel

        # Pit events
        if is_pit_in:
            events.append(RaceEvent(
                lap_number=lap_num,
                event_type="pit_in",
                description=f"Pit IN — {compound} stint {stint}",
                severity="info",
                lap_time=lap.get("lap_time"),
            ))
        if is_pit_out:
            events.append(RaceEvent(
                lap_number=lap_num,
                event_type="pit_out",
                description=f"Pit OUT — fresh {compound} tyres",
                severity="info",
            ))

        # Anomaly events
        if lap.get("anomaly_flag"):
            events.append(RaceEvent(
                lap_number=lap_num,
                event_type="anomaly",
                description=lap.get("anomaly_reason", "Anomalous lap detected"),
                severity="warning",
                lap_time=lap.get("lap_time"),
            ))

    # Close last stint
    if current_stint:
        stint_laps = [l for l in valid_laps if l.get("stint_number") == current_stint["stint_number"]]
        if stint_laps:
            current_stint["avg_lap_time"] = sum(l.get("lap_time", 0) for l in stint_laps) / len(stint_laps)
        current_stint["end_lap"] = total_laps
        stints.append(current_stint)

    # Build stint info objects properly
    stints_info = []
    for s in stints:
        stint_laps_data = [l for l in valid_laps if l.get("stint_number") == s["stint_number"]]
        avg = None
        if stint_laps_data:
            avg = sum(l.get("lap_time", 0) for l in stint_laps_data) / len(stint_laps_data)
        stints_info.append(StintInfo(
            stint_number=s["stint_number"],
            start_lap=s["start_lap"],
            end_lap=s["end_lap"],
            compound=s["compound"],
            laps_in_stint=s["laps_in_stint"],
            avg_lap_time=avg,
            best_lap_time=s["best_lap_time"],
            fuel_used=s["fuel_used"],
        ))

    # Weather timeline
    weather_timeline = []
    last_weather = None
    for lap in laps:
        w = lap.get("weather_state")
        if w and w != last_weather:
            weather_timeline.append({
                "lap_number": lap.get("lap_number"),
                "weather": w,
                "track_temp": lap.get("track_temp"),
                "rain_intensity": lap.get("rain_intensity", 0),
            })
            last_weather = w

    return RaceSummary(
        session_id=session_id,
        car=car,
        track=track,
        total_laps=total_laps,
        total_time=total_time,
        best_lap_time=best_lap_time,
        avg_lap_time=avg_lap_time,
        stints=stints_info,
        events=events,
        weather_timeline=weather_timeline,
    )


def race_summary_to_dict(summary: Optional[RaceSummary]) -> Dict:
    """Convert RaceSummary to a JSON-serializable dict."""
    if summary is None:
        return {"error": "No race data available"}
    return {
        "session_id": summary.session_id,
        "car": summary.car,
        "track": summary.track,
        "total_laps": summary.total_laps,
        "total_time": summary.total_time,
        "best_lap_time": summary.best_lap_time,
        "avg_lap_time": summary.avg_lap_time,
        "stints": [
            {
                "stint_number": s.stint_number,
                "start_lap": s.start_lap,
                "end_lap": s.end_lap,
                "compound": s.compound,
                "laps_in_stint": s.laps_in_stint,
                "avg_lap_time": s.avg_lap_time,
                "best_lap_time": s.best_lap_time,
                "fuel_used": s.fuel_used,
            }
            for s in summary.stints
        ],
        "events": [
            {
                "lap_number": e.lap_number,
                "event_type": e.event_type,
                "description": e.description,
                "severity": e.severity,
                "lap_time": e.lap_time,
            }
            for e in summary.events
        ],
        "weather_timeline": summary.weather_timeline,
    }
