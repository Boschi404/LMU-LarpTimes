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
import time
import json as _json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

import database
from analysis.anomaly import detect_anomalies_for_session
from analysis.models import fit_degradation_model, fit_fuel_model, DegradationModelFit
from analysis.strategist import PitStrategist
from analysis.weather import linear_rain_forecast, build_stint_weather_forecast

import paths
BASE_DIR = paths.base_dir()
TEMPLATES_DIR = os.path.join(BASE_DIR, "web", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")

# ══════════════════════════════════════════════════════════════════════════════
# Security middleware
# ══════════════════════════════════════════════════════════════════════════════

# Simple in-memory rate limiter: {ip: [(timestamp, count), ...]}
_rate_limit_store: Dict[str, List[float]] = {}
_RATE_LIMIT = 200  # max requests per minute per IP


def reset_rate_limit():
    """Clear the rate-limit counter (useful in tests)."""
    _rate_limit_store.clear()

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers and enforce basic rate limiting."""

    async def dispatch(self, request: Request, call_next):
        # Rate limiting (skip static files)
        if not request.url.path.startswith("/static"):
            client_ip = request.client.host if request.client else "127.0.0.1"
            now = time.time()
            # Clean old entries
            if client_ip in _rate_limit_store:
                _rate_limit_store[client_ip] = [
                    t for t in _rate_limit_store[client_ip]
                    if now - t < 60
                ]
            else:
                _rate_limit_store[client_ip] = []
            if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT:
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate limit exceeded (200 req/min)"},
                )
            _rate_limit_store[client_ip].append(now)

        response: Response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "interest-cohort=()"

        return response

# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

_MAX_IMPORT_SIZE = 50 * 1024 * 1024  # 50 MB max import payload
_MAX_IMPORT_DEPTH = 5                # max nesting in import

def _validate_import_payload(payload: Any) -> Optional[str]:
    """
    Validate the structure of an import payload.
    Returns an error string if invalid, None if OK.
    """
    if not isinstance(payload, dict):
        return "payload must be a JSON object"
    if "sessions" not in payload:
        return "payload missing 'sessions' key"
    sessions = payload["sessions"]
    if not isinstance(sessions, list):
        return "'sessions' must be a list"
    if len(sessions) > _MAX_IMPORT_DEPTH:
        return f"too many sessions ({len(sessions)} > {_MAX_IMPORT_DEPTH})"
    for i, entry in enumerate(sessions):
        if not isinstance(entry, dict):
            return f"sessions[{i}] must be an object"
        sess = entry.get("session")
        if not isinstance(sess, dict):
            return f"sessions[{i}].session must be an object"
        laps = entry.get("laps")
        if laps is not None and not isinstance(laps, list):
            return f"sessions[{i}].laps must be a list"
        if isinstance(laps, list) and len(laps) > 5000:
            return f"sessions[{i}] too many laps ({len(laps)} > 5000)"
        stints = entry.get("stints")
        if stints is not None and not isinstance(stints, list):
            return f"sessions[{i}].stints must be a list"
        if isinstance(stints, list) and len(stints) > 30:
            return f"sessions[{i}] too many stints ({len(stints)} > 30)"
    return None


@asynccontextmanager
async def lifespan(app):
    database.init_db()
    # Security audit on startup (silent — only warnings/criticals shown)
    try:
        from security.self_audit import run_audit as _run_audit
        _run_audit(silent=True)
    except ImportError:
        pass
    yield

app = FastAPI(title="LMU Pit Strategist", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
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
# API — Community DB (opt-in, push, pull, status)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/cloud/user")
async def get_cloud_user():
    """Return the local user's opt-in status and identity."""
    return database.get_local_user()


@app.post("/api/cloud/opt-in")
async def opt_in(request: Request):
    """
    Opt the local user in to the community DB.
    Body: {"display_name": "<optional>"}
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return database.opt_in_to_community(display_name=body.get("display_name"))


@app.post("/api/cloud/opt-out")
async def opt_out(request: Request):
    """
    Opt the local user out.
    Body: {"delete_cloud_data": bool}
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return database.opt_out_of_community(
        delete_cloud_data=bool(body.get("delete_cloud_data", False))
    )


@app.post("/api/cloud/display-name")
async def set_cloud_display_name(request: Request):
    """Update the user's display name. Body: {"display_name": "..."}."""
    body = await request.json()
    return database.set_display_name(new_name=body.get("display_name", ""))


@app.get("/api/cloud/status")
async def cloud_status():
    """Combined status: backend + sync state + user."""
    return {
        "user": database.get_local_user(),
        "sync": database.get_sync_status(),
    }


@app.post("/api/cloud/push")
async def cloud_push():
    """Push all pending sessions to the cloud."""
    return database.push_pending_sessions()


@app.post("/api/cloud/pull")
async def cloud_pull():
    """Pull all community sessions and import locally (with dedup)."""
    return database.pull_remote_sessions()


# ──────────────────────────────────────────────────────────────────────────────
# API — Sharing (export/import for the global DB pattern)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/laps/export")
async def export_laps(
    car: Optional[str] = None,
    track: Optional[str] = None,
):
    """
    Export sessions + laps + stints + pit stops as a portable JSON payload.

    Optional filters: car, track. The payload can be saved as a file,
    shared, and re-imported with POST /api/laps/import.
    """
    payload = database.export_sessions(
        db_path=database.DEFAULT_DB_PATH,
        car=car,
        track=track,
    )
    return payload


@app.post("/api/laps/import")
async def import_laps(
    request: Request,
    overwrite_existing: bool = False,
):
    """
    Import laps from a payload previously produced by /api/laps/export.

    Security: validates payload structure and enforces size limits.
    Dedup is automatic on (session_uuid, lap_number). Pass
    overwrite_existing=true to REPLACE existing laps with the imported ones.
    """
    # Size limit check (raw body)
    body_raw = await request.body()
    if len(body_raw) > _MAX_IMPORT_SIZE:
        return JSONResponse(
            status_code=413,
            content={"error": f"payload too large ({len(body_raw)} bytes > {_MAX_IMPORT_SIZE} bytes)"},
        )

    # Parse
    try:
        body = _json.loads(body_raw)
    except _json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"invalid JSON: {e}"},
        )

    # Structure validation
    err = _validate_import_payload(body)
    if err:
        return JSONResponse(status_code=422, content={"error": err})

    summary = database.import_sessions(
        payload=body,
        db_path=database.DEFAULT_DB_PATH,
        overwrite_existing=overwrite_existing,
    )
    return summary


# ──────────────────────────────────────────────────────────────────────────────
# API — Weather forecast
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/weather/forecast")
async def get_weather_forecast(
    history: Optional[str] = None,  # JSON: [{"t_min": -10, "rain_intensity": 0.1, "weather_state": "DRY"}, ...]
    horizon_minutes: int = 15,
):
    """
    Linear extrapolation of rain intensity. Returns predicted state and
    when (if ever) rain will cross the WET threshold.

    `history` is a JSON string of observations. If omitted, returns a
    DRY/calm default.
    """
    import json as _json
    hist_list = []
    if history:
        try:
            hist_list = _json.loads(history)
        except Exception:
            hist_list = []
    forecast = linear_rain_forecast(hist_list, horizon_minutes=horizon_minutes)
    return {
        "horizon_minutes": horizon_minutes,
        "forecast": forecast,
    }


@app.get("/api/weather/stint-forecast")
async def get_stint_weather_forecast(
    total_laps: int = 40,
    avg_lap_time_s: float = 100.0,
    history: Optional[str] = None,
    horizon_minutes: int = 15,
):
    """
    Build a per-stint weather forecast from the linear forecast above.
    Useful for the UI to show 'stint 2 will be WET — consider Inter'.
    """
    import json as _json
    hist_list = []
    if history:
        try:
            hist_list = _json.loads(history)
        except Exception:
            hist_list = []
    forecast = linear_rain_forecast(hist_list, horizon_minutes=horizon_minutes)
    stint_forecast = build_stint_weather_forecast(
        total_laps=total_laps,
        avg_lap_time_s=avg_lap_time_s,
        weather_forecast=forecast,
    )
    return {
        "forecast": forecast,
        "stints": stint_forecast,
    }


# ──────────────────────────────────────────────────────────────────────────────
# API — Giri
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/laps")
async def get_laps(
    car: Optional[str] = None,
    track: Optional[str] = None,
    compound: Optional[str] = None,
    owner_email: Optional[str] = None,
    include_deleted: bool = False
):
    """Restituisce tutti i giri, opzionalmente filtrati.

    Se `owner_email` è passato, filtra solo i giri di quell'utente.
    Se non è passato, restituisce tutti i giri (modalità admin).
    """
    laps = database.get_all_laps_for_archive(include_deleted=include_deleted)
    if car:
        laps = [l for l in laps if l.get("car") == car]
    if track:
        laps = [l for l in laps if l.get("track") == track]
    if compound:
        laps = [l for l in laps if l.get("compound_front") == compound]
    if owner_email:
        owner = owner_email.strip().lower()
        laps = [l for l in laps if (l.get("owner_email") or "").lower() == owner]
    return laps


@app.get("/api/owner")
async def get_owner():
    """Return the current local owner email (or empty string)."""
    return {"email": database.get_owner_email() or ""}


@app.post("/api/owner")
async def set_owner(request: Request):
    """Set the local owner email. Body: {"email": "..."} or {"email": null}."""
    body = await request.json()
    email = body.get("email")
    try:
        new_email = database.set_owner_email(email)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return {"email": new_email or ""}


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
    max_stops: int = 3,
    track_temp: Optional[float] = None,
    weather_state: Optional[str] = "DRY",
    rain_intensity: float = 0.0,
):
    """Calcola la strategia di pit stop ottimale.

    Parametri meteo (opzionali):
      - track_temp: temperatura tracciato attuale in °C
      - weather_state: "DRY" o "WET" — condizione attuale
      - rain_intensity: 0.0-1.0 — intensità pioggia attuale

    Se vengono passati, l'API includerà anche un compound_plan
    (mescola consigliata per ogni stint) basato su meteo + dati storici.
    """
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

    # If weather is provided, ask strategist to also recommend compounds
    weather_forecast = None
    if weather_state or rain_intensity:
        weather_forecast = [{
            "weather_state": weather_state or "DRY",
            "rain_intensity": rain_intensity,
        }]

    result = strat.optimize(
        laps_remaining=laps_remaining,
        current_tyre_age=current_tyre_age,
        current_fuel=current_fuel,
        max_stops=max_stops,
        laps_history=clean_laps if weather_forecast else None,
        weather_forecast=weather_forecast,
        track_temp=track_temp,
    )

    return {
        "car": car,
        "track": track,
        "compound": compound,
        "laps_remaining": laps_remaining,
        "mean_fuel_consumption": round(mean_fuel, 3),
        "pit_loss_seconds": round(pit_loss, 1),
        "current_weather": {
            "state": weather_state,
            "rain_intensity": rain_intensity,
            "track_temp": track_temp,
        },
        "result": result
    }
