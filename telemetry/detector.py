import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import database
from telemetry.source import TelemetryFrame


class LapBoundaryDetector:
    """
    Listens to telemetry frames and detects lap boundaries, stint changes,
    tyre changes, and pit stops, saving them to SQLite.
    """
    def __init__(self, db_path: str = database.DEFAULT_DB_PATH, fallback_pit_loss: float = 30.0):
        self.db_path = db_path
        self.fallback_pit_loss = fallback_pit_loss

        # Tracking state
        self.session_id: Optional[int] = None
        self.track_name: str = ""
        self.session_type: str = ""
        self.car_name: str = ""
        
        self.current_lap_number: int = -1
        self.stint_number: int = 1
        self.tyre_age_laps: int = 1

        # Lap start snapshots
        self.lap_start_fuel: float = 0.0
        self.lap_start_wear: List[float] = [0.0, 0.0, 0.0, 0.0]  # in percent (0-100%)
        self.lap_start_compounds: List[str] = ["", ""]
        self.lap_is_valid: bool = True
        self.lap_start_in_pits: bool = False

        # Pit stop tracking
        self.pit_in_lap_number: Optional[int] = None
        self.pit_in_lap_time: Optional[float] = None
        self.in_pit_stop_sequence: bool = False

    def process_frame(self, frame: TelemetryFrame) -> Optional[int]:
        """
        Process a new telemetry frame.
        Returns the inserted lap database ID if a lap was completed, otherwise None.
        """
        # 1. Detect session changes
        if (self.session_id is None or 
            frame.track_name != self.track_name or 
            frame.session_type != self.session_type or 
            frame.car_name != self.car_name or
            frame.lap_number < self.current_lap_number):
            
            # Start a new session in DB
            self.track_name = frame.track_name
            self.session_type = frame.session_type
            self.car_name = frame.car_name
            
            self.session_id = database.create_session(
                track=self.track_name,
                layout=frame.layout_name or "Standard",
                car=self.car_name,
                session_type=self.session_type,
                db_path=self.db_path
            )
            
            # Reset stint state
            self.stint_number = 1
            self.tyre_age_laps = 1
            self.current_lap_number = frame.lap_number
            
            # Take snapshots
            self.lap_start_fuel = frame.fuel
            self.lap_start_wear = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
            self.lap_start_compounds = list(frame.tyre_compounds)
            self.lap_is_valid = frame.is_valid_lap
            self.lap_start_in_pits = frame.in_pits
            
            self.pit_in_lap_number = None
            self.pit_in_lap_time = None
            self.in_pit_stop_sequence = False
            
            return None

        # Track lap invalidation during the lap
        if not frame.is_valid_lap:
            self.lap_is_valid = False

        # 2. Detect lap completion
        # Lap number increments
        if frame.lap_number > self.current_lap_number:
            completed_lap = self.current_lap_number
            
            # We convert raw tyre wear (1.0 to 0.0) to wear percent (0% to 100%)
            current_wear = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
            
            # Calculate sector times
            s1 = frame.last_sector1
            s2 = frame.last_sector2 - frame.last_sector1
            s3 = frame.last_lap_time - frame.last_sector2
            
            # Determine if this lap was a pit-in lap
            # (either player was in pits at the end of the lap, or pit state indicates it)
            is_pit_in = 1 if (frame.in_pits or frame.pit_state in [2, 3]) else 0
            is_pit_out = 1 if self.lap_start_in_pits else 0

            # Insert lap into database
            lap_data = {
                "session_id": self.session_id,
                "lap_number": completed_lap,
                "stint_number": self.stint_number,
                "lap_time": frame.last_lap_time,
                "sector_1": max(0.0, s1),
                "sector_2": max(0.0, s2),
                "sector_3": max(0.0, s3),
                "is_valid_lap": 1 if self.lap_is_valid else 0,
                "is_pit_in_lap": is_pit_in,
                "is_pit_out_lap": is_pit_out,
                "compound_front": self.lap_start_compounds[0],
                "compound_rear": self.lap_start_compounds[1],
                "tyre_age_laps": self.tyre_age_laps,
                "wear_pct_start_FL": self.lap_start_wear[0],
                "wear_pct_start_FR": self.lap_start_wear[1],
                "wear_pct_start_RL": self.lap_start_wear[2],
                "wear_pct_start_RR": self.lap_start_wear[3],
                "wear_pct_end_FL": current_wear[0],
                "wear_pct_end_FR": current_wear[1],
                "wear_pct_end_RL": current_wear[2],
                "wear_pct_end_RR": current_wear[3],
                "fuel_start_l": self.lap_start_fuel,
                "fuel_end_l": frame.fuel,
                "fuel_used_l": max(0.0, self.lap_start_fuel - frame.fuel),
                "track_temp": frame.track_temp,
                "ambient_temp": frame.ambient_temp,
                "weather_state": frame.weather_state,
                "rain_intensity": frame.rain_intensity,
                "anomaly_flag": 0,
                "anomaly_reason": None
            }
            
            lap_id = database.insert_lap(lap_data, db_path=self.db_path)
            
            # --- Pit Stop Sequence Logic ---
            if is_pit_in:
                self.pit_in_lap_number = completed_lap
                self.pit_in_lap_time = frame.last_lap_time
                self.in_pit_stop_sequence = True
            
            elif self.in_pit_stop_sequence and is_pit_out:
                # We completed the pit out lap, we can calculate the pit loss!
                total_pit_laps_time = self.pit_in_lap_time + frame.last_lap_time
                
                # Fetch reference lap time (median of clean laps)
                clean_laps = database.get_laps_for_analysis(
                    car=self.car_name,
                    track=self.track_name,
                    db_path=self.db_path
                )
                
                if clean_laps:
                    ref_lap_time = np.median([l["lap_time"] for l in clean_laps])
                else:
                    ref_lap_time = frame.last_lap_time  # Fallback if no clean laps
                    
                # Pit loss is total time of pit-in + pit-out minus twice the clean lap time
                calculated_loss = total_pit_laps_time - (2 * ref_lap_time)
                pit_loss = max(self.fallback_pit_loss, calculated_loss)
                
                database.insert_pit_stop(
                    session_id=self.session_id,
                    lap_number=completed_lap,
                    pit_loss=pit_loss,
                    in_lap_number=self.pit_in_lap_number,
                    out_lap_number=completed_lap,
                    db_path=self.db_path
                )
                self.in_pit_stop_sequence = False
                self.pit_in_lap_number = None
                self.pit_in_lap_time = None
            
            # --- Stint and Tyre Age Reset Logic ---
            # Check if tyres were changed during the lap/pit stop
            # 1. Did compound names change?
            # 2. Did the wear percentage drop significantly (e.g. from high wear to low wear)?
            tyres_changed = False
            if frame.tyre_compounds != self.lap_start_compounds:
                tyres_changed = True
            else:
                # Check wear drop: start wear FL vs current wear FL
                # If current wear is lower by > 10% wear, tyres were replaced
                for start, curr in zip(self.lap_start_wear, current_wear):
                    if curr < start - 10.0:  # e.g., went from 40% wear back to 0% wear
                        tyres_changed = True
                        break
            
            if tyres_changed or is_pit_in:
                self.tyre_age_laps = 1
                self.stint_number += 1
            else:
                self.tyre_age_laps += 1

            # Prepare for the next lap
            self.current_lap_number = frame.lap_number
            self.lap_start_fuel = frame.fuel
            self.lap_start_wear = current_wear
            self.lap_start_compounds = list(frame.tyre_compounds)
            self.lap_is_valid = frame.is_valid_lap
            self.lap_start_in_pits = frame.in_pits
            
            return lap_id
            
        return None
