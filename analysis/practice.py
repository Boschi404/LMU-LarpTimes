"""Practice data quality analysis.

Analyses the current data to tell the driver:
  - Whether they need laps at different FUEL levels (full tank vs low fuel)
  - Whether they need laps at different TYRE ages (new vs worn)
  - Whether they need to try different COMPOUNDS
  - Whether the degradation/fuel models will be reliable

This helps drivers run efficient practice sessions that yield good data
for the race strategist and qualifying analyst.
"""
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


def analyze_practice_data(
    laps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyse the collected practice data and return coverage gaps."""
    if not laps:
        return {
            "has_data": False,
            "total_laps": 0,
            "coverage": "none",
            "suggestions": [
                {
                    "priority": "high",
                    "message": "Nessun giro registrato. Fai almeno 5 giri per iniziare.",
                    "action": "Guida in PRACTICE per 5+ giri"
                }
            ]
        }

    # ── Fuel range analysis ─────────────────────────────────────────────
    fuel_starts = [l.get("fuel_start_l", 0) for l in laps if l.get("fuel_used_l", 0) > 0]
    fuel_max = max(fuel_starts) if fuel_starts else 0
    fuel_min = min(fuel_starts) if fuel_starts else 0
    fuel_range = fuel_max - fuel_min
    fuel_unique = len(set(round(f, 0) for f in fuel_starts)) if fuel_starts else 0

    # Check if we have a good spread of fuel data
    fuel_coverage = "good"
    fuel_suggestion = None
    if fuel_range < 20 and len(laps) >= 3:
        fuel_coverage = "poor"
        fuel_suggestion = {
            "priority": "medium" if len(laps) >= 5 else "low",
            "message": (
                f"Tutti i giri hanno ~{fuel_max:.0f}L di benzina. "
                f"Fai un giro con serbatoio quasi vuoto ({fuel_max*0.2:.0f}-{fuel_max*0.3:.0f}L) "
                f"per calibrare l'effetto carburante."
            ),
            "action": "Stint con benzina bassa"
        }
    elif fuel_max > 0 and fuel_min > fuel_max * 0.5:
        # Not enough low-fuel laps
        fuel_coverage = "partial"
        fuel_suggestion = {
            "priority": "low" if len(laps) >= 8 else "medium",
            "message": (
                f"Benzina tra {fuel_min:.0f}L e {fuel_max:.0f}L. "
                f"Prova un giro con {fuel_max*0.2:.0f}L per vedere "
                f"l'effetto carburante sul tempo."
            ),
            "action": "1 giro a basso carburante"
        }

    # ── Tyre age analysis ───────────────────────────────────────────────
    tyre_ages = [l.get("tyre_age_laps", 0) for l in laps]
    age_max = max(tyre_ages) if tyre_ages else 0
    age_min = min(tyre_ages) if tyre_ages else 0
    age_range = age_max - age_min
    age_unique = len(set(tyre_ages))

    # Count laps at low tyre age (1-3) vs high tyre age (>8)
    laps_young = sum(1 for a in tyre_ages if a <= 3)
    laps_old = sum(1 for a in tyre_ages if a >= 8)

    tyre_coverage = "good"
    tyre_suggestion = None
    if age_range < 5 and len(laps) >= 5:
        tyre_coverage = "poor"
        tyre_suggestion = {
            "priority": "medium",
            "message": (
                f"Gomme sempre tra {age_min} e {age_max} giri di età. "
                f"Fai uno stint di 8+ giri per vedere il degrado gomme "
                f"e stimare il cliff."
            ),
            "action": "Stint lungo (8+ giri)"
        }
    elif laps_old < 2 and len(laps) >= 5:
        tyre_coverage = "partial"
        tyre_suggestion = {
            "priority": "low",
            "message": (
                f"Hai {laps_young} giri con gomme fresche ma solo {laps_old} "
                f"con gomme usate (>{8}giri). Fai uno stint più lungo "
                f"per vedere il degrado."
            ),
            "action": "Stint da 10+ giri"
        }

    # ── Compound analysis ───────────────────────────────────────────────
    compounds = set()
    for l in laps:
        c = l.get("compound_front") or l.get("compound") or "Unknown"
        compounds.add(c)

    compound_suggestions = []
    if "Soft" not in compounds:
        compound_suggestions.append({
            "priority": "low",
            "message": "Prova la mescola Soft per vedere il guadagno sul giro singolo.",
            "action": "1 stint con Soft"
        })
    if "Medium" not in compounds:
        compound_suggestions.append({
            "priority": "medium",
            "message": "Mancano dati con Medium (la mescola da gara più comune).",
            "action": "1 stint con Medium"
        })
    if "Hard" not in compounds:
        compound_suggestions.append({
            "priority": "low",
            "message": "Hard non testata — utile in endurance o clima caldo.",
            "action": "1 stint con Hard"
        })

    # ── Overall assessment ──────────────────────────────────────────────
    dry_laps = [l for l in laps if l.get("weather_state") in ("DRY", None, "")]
    wet_laps = [l for l in laps if l.get("weather_state") in ("WET", "RAIN", "HEAVY_RAIN")]
    has_wet_data = len(wet_laps) >= 3

    suggestions = []
    assessment = "complete"

    if len(laps) < 3:
        assessment = "insufficient"
        suggestions.append({
            "priority": "high",
            "message": f"Solo {len(laps)} giri. Servono almeno 8-12 giri per modelli affidabili.",
            "action": "Continua a guidare"
        })
    elif len(laps) < 8:
        assessment = "minimum"
        suggestions.append({
            "priority": "high",
            "message": f"{len(laps)} giri — dati minimi. A 12+ giri le stime migliorano molto.",
            "action": "Fai 5+ giri ancora"
        })
    else:
        # Enough laps, check specific coverage
        if fuel_suggestion:
            suggestions.append(fuel_suggestion)
        if tyre_suggestion:
            suggestions.append(tyre_suggestion)
        suggestions.extend(compound_suggestions)

        if not any(s.get("priority") in ("high", "medium") for s in suggestions):
            assessment = "complete"
        else:
            assessment = "partial"

    return {
        "has_data": True,
        "total_laps": len(laps),
        "dry_laps": len(dry_laps),
        "wet_laps": len(wet_laps),
        "has_wet_data": has_wet_data,
        "fuel": {
            "min_l": round(fuel_min, 1),
            "max_l": round(fuel_max, 1),
            "range_l": round(fuel_range, 1),
            "unique_levels": fuel_unique,
            "coverage": fuel_coverage,
        },
        "tyre": {
            "min_age": age_min,
            "max_age": age_max,
            "range_laps": age_range,
            "laps_young": laps_young,
            "laps_old": laps_old,
            "coverage": tyre_coverage,
        },
        "compounds": sorted(list(compounds)),
        "missing_compounds": [c for c in ["Soft", "Medium", "Hard"] if c not in compounds],
        "coverage": assessment,
        "suggestions": suggestions,
    }
