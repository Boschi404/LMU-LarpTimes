"""Pit Stop Practice Tool — tracks and analyzes pit stop performance."""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class PitStopRecord:
    session_id: str
    lap_number: int
    pit_in_time: Optional[float]  # lap time of pit in lap
    pit_out_time: Optional[float]  # lap time of pit out lap
    pit_loss_seconds: float        # estimated time lost in pit
    track: str
    car: str
    stint: int
    compound: str


def extract_pit_stops(laps: List[Dict]) -> List[PitStopRecord]:
    """Extract all pit stops from lap data."""
    pit_stops = []

    for i, lap in enumerate(laps):
        if lap.get('is_pit_in_lap') and i + 1 < len(laps):
            pit_in = lap
            pit_out = laps[i + 1]

            # Estimate pit loss: pit_in lap time + pit_out lap time - 2 * avg lap time
            # Or use the stored pit_loss if available
            pit_loss = lap.get('pit_loss_seconds', 0)
            if not pit_loss and pit_in.get('lap_time') and pit_out.get('lap_time'):
                # Estimate from surrounding laps
                surrounding = [l.get('lap_time') for l in laps[max(0, i-3):i] if l.get('lap_time')]
                if surrounding:
                    avg_lap = sum(surrounding) / len(surrounding)
                    pit_loss = (pit_in.get('lap_time', 0) or 0) + (pit_out.get('lap_time', 0) or 0) - 2 * avg_lap
                    pit_loss = max(0, pit_loss)

            pit_stops.append(PitStopRecord(
                session_id=str(lap.get('session_id', '')),
                lap_number=lap.get('lap_number', 0),
                pit_in_time=pit_in.get('lap_time'),
                pit_out_time=pit_out.get('lap_time'),
                pit_loss_seconds=round(pit_loss or 0, 1),
                track=lap.get('track', ''),
                car=lap.get('car', ''),
                stint=lap.get('stint_number', 0),
                compound=lap.get('compound_front', ''),
            ))

    return pit_stops


def analyze_pit_performance(pit_stops: List[PitStopRecord]) -> Dict[str, Any]:
    """Analyze pit stop performance and provide improvement tips."""
    if not pit_stops:
        return {"error": "No pit stop data available"}

    losses = [p.pit_loss_seconds for p in pit_stops if p.pit_loss_seconds > 0]

    result: Dict[str, Any] = {
        "total_pit_stops": len(pit_stops),
        "avg_loss": round(sum(losses) / len(losses), 1) if losses else None,
        "best_loss": round(min(losses), 1) if losses else None,
        "worst_loss": round(max(losses), 1) if losses else None,
        "recent_pit_stops": [
            {
                "session_id": p.session_id,
                "lap": p.lap_number,
                "loss": round(p.pit_loss_seconds, 1),
                "track": p.track,
                "car": p.car,
                "compound": p.compound,
                "pit_in_time": round(p.pit_in_time, 2) if p.pit_in_time else None,
                "pit_out_time": round(p.pit_out_time, 2) if p.pit_out_time else None,
            }
            for p in pit_stops[-10:]  # last 10
        ],
        "improvement_potential": round(max(losses) - min(losses), 1) if len(losses) >= 2 else None,
        "loss_history": [round(p.pit_loss_seconds, 1) for p in pit_stops if p.pit_loss_seconds > 0],
    }

    # Generate tips
    tips = []
    if result["avg_loss"] and result["avg_loss"] > 35:
        tips.append("Pit loss is high (>35s) — practice speed limit entry and exit")
    if result["avg_loss"] and result["avg_loss"] > 30:
        tips.append("Aim for consistent 28-30s pit stops — practice your routine")
    if result["best_loss"] and result["best_loss"] < 28:
        tips.append(f"Your best is {result['best_loss']}s — target that every stop")
    if result["improvement_potential"] and result["improvement_potential"] > 5:
        tips.append(f"You're losing {result['improvement_potential']}s between best and worst — consistency is key")
    if result["total_pit_stops"] < 3:
        tips.append("More data needed — do at least 3 practice pit stops for meaningful stats")
    if result["total_pit_stops"] >= 5:
        tips.append("Good sample size! Review the pit loss chart to spot patterns")

    result["tips"] = tips
    return result
