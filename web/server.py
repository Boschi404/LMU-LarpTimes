"""
LMU Pit Strategist — Server Web Esterno (Processo B)

FastAPI server che espone:
  GET  /               → pagina principale (Profilo + Archivio giri)
  GET  /api/profile    → statistiche aggregate per combinazione auto/pista/mescola
  GET  /api/laps       → tutti i giri (non eliminati)
  POST /api/laps/{id}/delete  → soft-delete di un giro
  POST /api/laps/{id}/restore → ripristino soft-delete
  GET  /api/strategy   → calcola strategia ottimale
  GET  /api/sessions   → lista sessioni
  GET  /api/overlay/settings → lettura impostazioni overlay
  POST /api/overlay/settings → scrittura impostazioni overlay
  GET  /api/setup      → consigli setup basati su condizioni meteo/temperatura
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database
from analysis.anomaly import detect_anomalies_for_session
from analysis.models import fit_degradation_model, fit_fuel_model, DegradationModelFit
from analysis.strategist import PitStrategist

import paths
BASE_DIR = paths.base_dir()
TEMPLATES_DIR = os.path.join(BASE_DIR, "web", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")

@asynccontextmanager
async def lifespan(app):
    database.init_db()
    yield

app = FastAPI(title="LMU Pit Strategist", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Serve static files (JS, CSS, images)
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Minimum valid laps for reliable estimates
MIN_LAPS_FOR_ESTIMATE = 10


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (f != f) else f   # NaN check
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Pages
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


# ──────────────────────────────────────────────────────────────────────────────
# API — Sessioni
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
async def get_sessions():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, track, layout, car, session_type, started_at FROM sessions ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# API — Overlay Settings
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/overlay/settings")
async def get_overlay_settings():
    import json
    import os
    config_path = paths.data_path("overlay", "overlay_config.json")
    default_settings = {"in_game_only": False}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                default_settings["in_game_only"] = data.get("in_game_only", False)
        except Exception:
            pass
    return default_settings


@app.post("/api/overlay/settings")
async def set_overlay_settings(request: Request):
    import json
    import os
    body = await request.json()
    config_path = paths.data_path("overlay", "overlay_config.json")
    existing = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                existing = json.load(f)
        except Exception:
            pass
    if "in_game_only" in body:
        existing["in_game_only"] = bool(body["in_game_only"])
    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
    return {"status": "ok", "in_game_only": existing.get("in_game_only", False)}


# ──────────────────────────────────────────────────────────────────────────────
# API — Filters
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/filters/cars")
async def get_filter_cars():
    laps = database.get_all_laps_for_archive(include_deleted=False)
    cars = sorted({l.get("car", "") for l in laps if l.get("car")})
    return cars


@app.get("/api/filters/tracks")
async def get_filter_tracks():
    laps = database.get_all_laps_for_archive(include_deleted=False)
    tracks = sorted({l.get("track", "") for l in laps if l.get("track")})
    return tracks


@app.get("/api/filters/compounds")
async def get_filter_compounds():
    laps = database.get_all_laps_for_archive(include_deleted=False)
    compounds = sorted({l.get("compound_front", "") for l in laps if l.get("compound_front")})
    return compounds


# ──────────────────────────────────────────────────────────────────────────────
# API — Setup Advisor
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/setup")
async def get_setup_advice(car: str, track: str):
    """
    Restituisce consigli di setup basati su:
    - Track/air temperature vs lap time
    - Weather conditions vs performance
    - Tyre compound performance at different temps
    - Historical best laps under similar conditions
    """
    laps = database.get_all_laps_for_archive(include_deleted=False)

    car_laps = [l for l in laps if l.get("car") == car and l.get("track") == track]
    valid_laps = [l for l in car_laps if l.get("is_valid_lap") == 1 and not l.get("is_pit_in_lap") and not l.get("is_pit_out_lap")]

    if not valid_laps:
        return {
            "car": car, "track": track,
            "insufficient_data": True,
            "message": "Insufficient valid laps for setup analysis. Complete more laps first.",
            "recommendations": []
        }

    # Group by track temperature ranges (5-degree buckets)
    temp_buckets = {}
    for l in valid_laps:
        tt = l.get("track_temp")
        if tt is None:
            continue
        bucket = int(tt // 5) * 5  # 20-25, 25-30, 30-35, etc.
        if bucket not in temp_buckets:
            temp_buckets[bucket] = []
        temp_buckets[bucket].append(l)

    # Find optimal temperature range
    best_lap_by_temp = {}
    for bucket, bucket_laps in temp_buckets.items():
        times = [l["lap_time"] for l in bucket_laps if l.get("lap_time")]
        if times:
            best_lap_by_temp[bucket] = min(times)

    overall_best = min(best_lap_by_temp.values()) if best_lap_by_temp else None
    optimal_temp_range = None
    if overall_best:
        for bucket, time in best_lap_by_temp.items():
            if time == overall_best:
                optimal_temp_range = f"{bucket}°C - {bucket+5}°C"
                break

    # Weather analysis
    weather_perf = {}
    for l in valid_laps:
        w = l.get("weather_state", "UNKNOWN")
        if w not in weather_perf:
            weather_perf[w] = []
        if l.get("lap_time"):
            weather_perf[w].append(l["lap_time"])

    weather_avg = {w: sum(times)/len(times) for w, times in weather_perf.items() if times}

    # Compound performance at different conditions
    compound_perf = {}
    for l in valid_laps:
        c = l.get("compound_front", "Unknown")
        tt = l.get("track_temp")
        if c not in compound_perf:
            compound_perf[c] = []
        if l.get("lap_time"):
            compound_perf[c].append({
                "lap_time": l["lap_time"],
                "track_temp": tt,
                "wear_start": l.get("wear_pct_start_FL"),
                "wear_end": l.get("wear_pct_end_FL")
            })

    compound_stats = {}
    for c, data in compound_perf.items():
        if data:
            valid_wear = [d for d in data if d.get("wear_end") and d.get("wear_start")]
            compound_stats[c] = {
                "avg_lap": sum(d["lap_time"] for d in data) / len(data),
                "count": len(data),
                "temps": [d["track_temp"] for d in data if d.get("track_temp") is not None],
                "avg_wear_increase": sum((d["wear_end"] or 0) - (d["wear_start"] or 0) for d in valid_wear) / max(1, len(valid_wear))
            }

    # Setup recommendations
    recommendations = []

    # Temperature-based recommendations
    current_avg_temp = sum(l.get("track_temp", 0) for l in valid_laps[-5:]) / min(5, len(valid_laps[-5:])) if valid_laps else None

    if optimal_temp_range and current_avg_temp:
        current_bucket = int(current_avg_temp // 5) * 5
        if current_bucket != int(overall_best // 5) * 5:
            diff = current_avg_temp - (int(overall_best // 5) * 5 + 2.5)
            if diff > 5:
                recommendations.append({
                    "type": "temp",
                    "priority": "high",
                    "title": "Track Temperature High",
                    "message": f"Current track temp (~{current_avg_temp:.0f}°C) is above optimal range ({optimal_temp_range}). Consider softening front wing and reducing camber.",
                    "impact": f"~{abs(diff)*0.3:.1f}s/lap penalty if unaddressed"
                })
            elif diff < -5:
                recommendations.append({
                    "type": "temp",
                    "priority": "high",
                    "title": "Track Temperature Low",
                    "message": f"Current track temp (~{current_avg_temp:.0f}°C) is below optimal range ({optimal_temp_range}). Consider stiffening front wing and increasing camber.",
                    "impact": f"~{abs(diff)*0.3:.1f}s/lap penalty if unaddressed"
                })

    # Weather recommendations
    if "WET" in weather_avg and "DRY" in weather_avg:
        wet_penalty = weather_avg["WET"] - weather_avg["DRY"]
        if wet_penalty > 5:
            recommendations.append({
                "type": "weather",
                "priority": "medium",
                "title": "Wet Conditions Detected",
                "message": f"Wet laps are ~{wet_penalty:.1f}s slower than dry. Use wet compound tyres and increase ride height.",
                "impact": f"{wet_penalty:.1f}s/lap in wet vs dry"
            })

    # Tyre wear analysis for setup hints
    high_wear_compounds = [c for c, s in compound_stats.items() if s.get("avg_wear_increase", 0) > 15]
    if high_wear_compounds:
        recommendations.append({
            "type": "wear",
            "priority": "medium",
            "title": "High Tyre Wear Detected",
            "message": f"Compounds {', '.join(high_wear_compounds)} show excessive wear (>15%/lap). Reduce camber and consider softer compound.",
            "impact": "Increased degradation in later stints"
        })

    # Fuel effect
    if len(valid_laps) >= 2:
        early_laps = [l for l in valid_laps if l.get("tyre_age_laps", 999) <= 3]
        late_laps = [l for l in valid_laps if l.get("tyre_age_laps", 0) >= 8]
        if early_laps and late_laps:
            early_avg = sum(l["lap_time"] for l in early_laps) / len(early_laps)
            late_avg = sum(l["lap_time"] for l in late_laps) / len(late_laps)
            fuel_effect = late_avg - early_avg
            if fuel_effect > 1.0:
                recommendations.append({
                    "type": "fuel",
                    "priority": "low",
                    "title": "Fuel Load Impact",
                    "message": f"Late laps are {fuel_effect:.1f}s slower than fresh tyres. Plan pit stops before significant degradation.",
                    "impact": f"{fuel_effect:.1f}s delta between fresh and worn tyres"
                })

    # Summary stats
    recent_laps = valid_laps[-5:] if len(valid_laps) >= 5 else valid_laps
    recent_avg = sum(l["lap_time"] for l in recent_laps) / len(recent_laps) if recent_laps else None
    all_best = min(l["lap_time"] for l in valid_laps) if valid_laps else None

    return {
        "car": car,
        "track": track,
        "total_valid_laps": len(valid_laps),
        "insufficient_data": len(valid_laps) < 5,
        "optimal_temp_range": optimal_temp_range,
        "current_avg_track_temp": current_avg_temp,
        "recent_avg_lap": recent_avg,
        "all_time_best": all_best,
        "weather_performance": weather_avg,
        "compound_stats": compound_stats,
        "temp_buckets": {str(k): v for k, v in temp_buckets.items()},
        "recommendations": recommendations
    }


# ──────────────────────────────────────────────────────────────────────────────
# API — Giri
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/laps")
async def get_laps(
    car: Optional[str] = None,
    track: Optional[str] = None,
    compound: Optional[str] = None,
    include_deleted: bool = False
):
    """Restituisce tutti i giri, opzionalmente filtrati."""
    laps = database.get_all_laps_for_archive(include_deleted=include_deleted)
    if car:
        laps = [l for l in laps if l.get("car") == car]
    if track:
        laps = [l for l in laps if l.get("track") == track]
    if compound:
        laps = [l for l in laps if l.get("compound_front") == compound]
    return laps


@app.post("/api/laps/{lap_id}/delete")
async def soft_delete_lap(lap_id: int):
    """Soft-delete di un giro (is_deleted=1)."""
    database.soft_delete_lap(lap_id, is_deleted=True)
    return {"status": "ok", "lap_id": lap_id, "deleted": True}


@app.post("/api/laps/{lap_id}/restore")
async def restore_lap(lap_id: int):
    """Ripristina un giro soft-eliminato."""
    database.soft_delete_lap(lap_id, is_deleted=False)
    return {"status": "ok", "lap_id": lap_id, "deleted": False}


# ──────────────────────────────────────────────────────────────────────────────
# API — Profilo
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/profile")
async def get_profile(car: str, track: str, compound: Optional[str] = None):
    """
    Restituisce statistiche aggregate, curva di degrado e warning su dati insufficienti.
    """
    # Run anomaly detection first to refresh flags
    try:
        detect_anomalies_for_session(car, track)
    except Exception:
        pass

    # Fetch clean laps
    clean_laps = database.get_laps_for_analysis(car, track, compound_front=compound)

    n_valid = len(clean_laps)
    insufficient = n_valid < MIN_LAPS_FOR_ESTIMATE

    if not clean_laps:
        return {
            "car": car, "track": track, "compound": compound,
            "n_valid_laps": 0,
            "insufficient_data": True,
            "warning": "Nessun giro valido disponibile per questa combinazione.",
            "avg_lap_time": None,
            "avg_fuel_consumption": None,
            "degradation_model": None,
            "degradation_curve": []
        }

    # Basic stats
    lap_times = [l["lap_time"] for l in clean_laps]
    avg_lap = float(np.mean(lap_times))
    std_lap  = float(np.std(lap_times))

    mean_fuel, std_fuel = fit_fuel_model(clean_laps)

    # Fit degradation model
    model: DegradationModelFit = fit_degradation_model(clean_laps)

    # Build curve data for Chart.js
    max_age = max(l["tyre_age_laps"] for l in clean_laps)
    avg_fuel_for_curve = float(np.mean([l["fuel_start_l"] for l in clean_laps]))
    curve = []
    for age in range(1, max_age + 2):
        predicted = model.predict(age, avg_fuel_for_curve)
        curve.append({"age": age, "predicted_time": round(float(predicted), 3)})

    # Build raw data points
    raw_points = [
        {
            "lap_number": l["lap_number"],
            "tyre_age": l["tyre_age_laps"],
            "lap_time": l["lap_time"],
            "fuel_start": l["fuel_start_l"]
        }
        for l in clean_laps
    ]

    warning = None
    if insufficient:
        warning = (
            f"Dati insufficienti: solo {n_valid} giri validi disponibili "
            f"(soglia consigliata: {MIN_LAPS_FOR_ESTIMATE}). "
            "Le stime potrebbero essere inaccurate."
        )

    return {
        "car": car,
        "track": track,
        "compound": compound,
        "n_valid_laps": n_valid,
        "insufficient_data": insufficient,
        "warning": warning,
        "avg_lap_time": round(avg_lap, 3),
        "std_lap_time": round(std_lap, 3),
        "avg_fuel_consumption": round(mean_fuel, 3),
        "std_fuel_consumption": round(std_fuel, 3),
        "degradation_model": model.to_dict(),
        "degradation_curve": curve,
        "raw_points": raw_points
    }


# ──────────────────────────────────────────────────────────────────────────────
# API — Strategia
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/strategy")
async def get_strategy(
    car: str,
    track: str,
    compound: Optional[str] = None,
    laps_remaining: int = 40,
    current_tyre_age: int = 1,
    current_fuel: float = 100.0,
    fuel_capacity: float = 100.0,
    max_stops: int = 3
):
    """Calcola la strategia di pit stop ottimale."""
    clean_laps = database.get_laps_for_analysis(car, track, compound_front=compound)
    if len(clean_laps) < 5:
        return JSONResponse(
            status_code=422,
            content={
                "error": f"Dati insufficienti: servono almeno 5 giri validi, trovati {len(clean_laps)}."
            }
        )

    model = fit_degradation_model(clean_laps)
    mean_fuel, _ = fit_fuel_model(clean_laps)
    pit_losses = database.get_pit_stops_loss_by_session(car, track)
    pit_loss = float(np.mean(pit_losses)) if pit_losses else 30.0

    strat = PitStrategist(
        fuel_capacity=fuel_capacity,
        fuel_consumption=mean_fuel,
        pit_loss=pit_loss,
        model_fit=model
    )

    result = strat.optimize(
        laps_remaining=laps_remaining,
        current_tyre_age=current_tyre_age,
        current_fuel=current_fuel,
        max_stops=max_stops
    )

    return {
        "car": car,
        "track": track,
        "compound": compound,
        "laps_remaining": laps_remaining,
        "mean_fuel_consumption": round(mean_fuel, 3),
        "pit_loss_seconds": round(pit_loss, 1),
        "result": result
    }
