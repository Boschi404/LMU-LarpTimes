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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

@asynccontextmanager
async def lifespan(app):
    database.init_db()
    yield

app = FastAPI(title="LMU Pit Strategist", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

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
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overlay", "overlay_config.json")
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
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overlay", "overlay_config.json")
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
