"""
Crea dati sintetici realistici per demo/tests.
Popola il DB con 3 sessioni (Practice, Qualifying, Race)
su Le Mans con gomme Miste, Soft e Hard.

Uso:
    python demo_seed.py
"""

import os
import sys
import random

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database
import numpy as np


def seed_demo(owner_email: str = "demo@lemansultimate.com"):
    """Crea dati demo realistici."""
    db = database.DEFAULT_DB_PATH
    database.init_db(db_path=db)

    # Set owner
    try:
        database.set_owner_email(owner_email, db_path=db)
    except Exception:
        pass

    rng = np.random.default_rng(2026)

    sessions_data = [
        {"track": "Le Mans", "layout": "GP", "car": "Ferrari 499P", "type": "PRACTICE", "n": 25,
         "compounds": ["Soft", "Soft", "Medium"], "weather": "DRY", "temp": 32,
         "base": 218.0, "cliff": 10, "b1": 0.08, "b2": 0.35, "alpha": 0.025, "fuel_cap": 110, "fuel_con": 4.2},
        {"track": "Le Mans", "layout": "GP", "car": "Ferrari 499P", "type": "QUALIFYING", "n": 12,
         "compounds": ["Soft", "Soft"], "weather": "DRY", "temp": 28,
         "base": 215.0, "cliff": 8, "b1": 0.06, "b2": 0.30, "alpha": 0.02, "fuel_cap": 90, "fuel_con": 3.8},
        {"track": "Le Mans", "layout": "GP", "car": "Ferrari 499P", "type": "RACE", "n": 42,
         "compounds": ["Medium", "Medium", "Hard", "Medium"], "weather": "DRY", "temp": 30,
         "base": 219.0, "cliff": 14, "b1": 0.05, "b2": 0.28, "alpha": 0.03, "fuel_cap": 110, "fuel_con": 4.0},
    ]

    total_laps = 0
    for sess in sessions_data:
        sid = database.create_session(
            track=sess["track"], layout=sess["layout"], car=sess["car"],
            session_type=sess["type"], db_path=db,
        )
        n = sess["n"]
        stint_count = len(sess["compounds"])
        laps_per_stint = n // stint_count

        for stint_idx, compound in enumerate(sess["compounds"]):
            start_lap = stint_idx * laps_per_stint + 1
            end_lap = (stint_idx + 1) * laps_per_stint if stint_idx < stint_count - 1 else n
            stint_laps = end_lap - start_lap + 1

            stint_id = database.create_stint(
                session_id=sid, stint_number=stint_idx + 1,
                compound_front=compound, compound_rear=compound,
                start_lap=start_lap, start_fuel_l=sess["fuel_cap"], db_path=db,
            )

            for i in range(stint_laps):
                age = i + 1
                deg = sess["b1"] * age + sess["b2"] * max(0.0, age - sess["cliff"])
                fuel = sess["fuel_cap"] - sess["fuel_con"] * i
                fuel = max(fuel, 5.0)

                # Random noise
                noise = float(rng.normal(0, 0.2))
                # Occasional anomaly (traffic)
                anomaly = 0
                anomaly_reason = None
                extra = 0.0
                if rng.random() < 0.03 and i > 2:
                    extra = float(rng.uniform(1.0, 2.0))
                    anomaly = 1
                    anomaly_reason = "Traffic (demo)"

                lap_time = sess["base"] + sess["alpha"] * fuel + deg + noise + extra
                lap_num = start_lap + i

                database.insert_lap({
                    "session_id": sid, "stint_id": stint_id,
                    "lap_number": lap_num,
                    "lap_time": round(lap_time, 3),
                    "sector_1": round(lap_time * 0.33, 3),
                    "sector_2": round(lap_time * 0.34, 3),
                    "sector_3": round(lap_time * 0.33, 3),
                    "is_valid_lap": 1,
                    "is_pit_in_lap": 1 if i == stint_laps - 1 and stint_idx < stint_count - 1 else 0,
                    "is_pit_out_lap": 1 if i == 0 and stint_idx > 0 else 0,
                    "compound_front": compound,
                    "compound_rear": compound,
                    "tyre_age_laps": age,
                    "wear_pct_start_FL": round(min(100, age * 4), 1),
                    "wear_pct_start_FR": round(min(100, age * 4), 1),
                    "wear_pct_start_RL": round(min(100, age * 3.5), 1),
                    "wear_pct_start_RR": round(min(100, age * 3.5), 1),
                    "wear_pct_end_FL": round(min(100, (age + 1) * 4), 1),
                    "wear_pct_end_FR": round(min(100, (age + 1) * 4), 1),
                    "wear_pct_end_RL": round(min(100, (age + 1) * 3.5), 1),
                    "wear_pct_end_RR": round(min(100, (age + 1) * 3.5), 1),
                    "fuel_start_l": round(fuel, 1),
                    "fuel_end_l": round(max(0, fuel - sess["fuel_con"]), 1),
                    "fuel_used_l": round(sess["fuel_con"], 2),
                    "track_temp": sess["temp"],
                    "ambient_temp": sess["temp"] - 8,
                    "weather_state": sess["weather"],
                    "rain_intensity": 0.0,
                    "completed_at": f"2026-07-01T10:{lap_num:02d}:00",
                    "anomaly_flag": anomaly,
                    "anomaly_reason": anomaly_reason,
                }, db_path=db)
                total_laps += 1

        # Record pit stops
        for stint_idx in range(stint_count - 1):
            pit_lap = (stint_idx + 1) * laps_per_stint
            pit_loss = round(25.0 + float(rng.normal(0, 2)), 1)
            database.insert_pit_stop(
                session_id=sid, lap_number=pit_lap,
                in_lap_number=pit_lap,
                out_lap_number=pit_lap + 1,
                pit_loss=pit_loss, db_path=db,
            )

    print(f"✅ Demo seed: {len(sessions_data)} sessioni, {total_laps} giri totali")
    print(f"   DB: {db}")
    print(f"   Owner: {owner_email}")
    print(f"   Apri http://127.0.0.1:8000 nel browser")


if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "demo@lemansultimate.com"
    seed_demo(email)
