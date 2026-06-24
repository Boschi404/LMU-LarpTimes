import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import uuid
import database
from telemetry.source import TelemetryFrame


class LapBoundaryDetector:
    def __init__(self, db_path: str = database.DEFAULT_DB_PATH, fallback_pit_loss: float = 30.0):
        self.db_path = db_path
        self.fallback_pit_loss = fallback_pit_loss
        self.session_id: Optional[int] = None
        self.session_uuid: Optional[str] = None
        self.track_name: str = ""
        self.session_type: str = ""
        self.car_name: str = ""
        self.current_lap_number: int = -1
        self.last_saved_lap: int = -1
        self.stint_number: int = 1
        self.current_stint_id: Optional[int] = None
        self.tyre_age_laps: int = 1
        self.lap_start_fuel: float = 0.0
        self.lap_start_wear: List[float] = [0.0, 0.0, 0.0, 0.0]
        self.lap_start_compounds: List[str] = ["", ""]
        self.lap_is_valid: bool = True
        self.lap_start_in_pits: bool = False
        self.pit_in_lap_number: Optional[int] = None
        self.pit_in_lap_time: Optional[float] = None
        self.in_pit_stop_sequence: bool = False

    def _create_session(self, frame: TelemetryFrame) -> None:
        self.track_name = frame.track_name
        self.session_type = frame.session_type
        self.car_name = frame.car_name
        self.session_uuid = str(uuid.uuid4())
        started_at = __import__('datetime').datetime.now().isoformat()
        self.session_id = database.create_session(
            track=self.track_name,
            layout=frame.layout_name or "Standard",
            car=self.car_name,
            session_type=self.session_type,
            started_at=started_at,
            db_path=self.db_path
        )
        print(f"[Detector] New session: {self.session_type} @ {self.track_name} [{self.car_name}] uuid={self.session_uuid}")
        self._reset_stint_state(frame)

    def _reset_stint_state(self, frame: TelemetryFrame) -> None:
        self.stint_number = 1
        self.tyre_age_laps = 1
        self.current_stint_id = database.create_stint(
            session_id=self.session_id,
            stint_number=self.stint_number,
            compound_front=frame.tyre_compounds[0],
            compound_rear=frame.tyre_compounds[1],
            start_lap=frame.lap_number,
            start_fuel_l=frame.fuel,
            db_path=self.db_path
        )
        self._take_lap_snapshots(frame)
        self.pit_in_lap_number = None
        self.pit_in_lap_time = None
        self.in_pit_stop_sequence = False

    def _take_lap_snapshots(self, frame: TelemetryFrame) -> None:
        self.lap_start_fuel = frame.fuel
        self.lap_start_wear = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
        self.lap_start_compounds = list(frame.tyre_compounds)
        self.lap_is_valid = frame.is_valid_lap
        self.lap_start_in_pits = frame.in_pits

    def process_frame(self, frame: TelemetryFrame) -> Optional[int]:
        if frame is None:
            return None

        # 1. Session reset: lap number went backwards
        if self.session_id is not None and frame.lap_number < self.current_lap_number:
            print(f"[Detector] Session reset: lap {self.current_lap_number} -> {frame.lap_number}")
            self._create_session(frame)
            self.current_lap_number = frame.lap_number
            return None

        # 2. New session detection
        if (self.session_id is None or
            frame.track_name != self.track_name or
            frame.session_type != self.session_type or
            frame.car_name != self.car_name):
            if self.session_id is not None:
                print(f"[Detector] Session change: {self.session_type} @ {self.track_name} -> {frame.session_type} @ {frame.track_name}")
            self._create_session(frame)
            self.current_lap_number = frame.lap_number
            return None

        if not frame.is_valid_lap:
            self.lap_is_valid = False

        if frame.lap_number > self.current_lap_number:
            lap_gap = frame.lap_number - self.current_lap_number
            if lap_gap > 1:
                print(f"[WARNING] Lap jump detected: {self.current_lap_number} -> {frame.lap_number} (gap={lap_gap})")

            completed_lap = self.current_lap_number

            # 4. Avoid double-save
            if completed_lap == self.last_saved_lap:
                print(f"[WARNING] Duplicate lap detected: {completed_lap}, skipping")
                self.current_lap_number = frame.lap_number
                return None

            # 11. Validate lap time
            if not frame.last_lap_time or frame.last_lap_time < 20.0:
                print(f"[WARNING] Discarding lap {completed_lap}: invalid lap_time={frame.last_lap_time}")
                self.current_lap_number = frame.lap_number
                self._take_lap_snapshots(frame)
                return None

            # 2. Save only valid laps
            if not self.lap_is_valid:
                print(f"[Detector] Lap {completed_lap} invalid, skipping save")
                self.current_lap_number = frame.lap_number
                self.last_saved_lap = completed_lap
                self._handle_stint_change(frame, completed_lap)
                return None

            current_wear = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
            s1 = frame.last_sector1
            s2 = frame.last_sector2 - frame.last_sector1
            s3 = frame.last_lap_time - frame.last_sector2

            is_pit_in = 1 if (frame.in_pits or frame.pit_state in [2, 3]) else 0
            is_pit_out = 1 if self.lap_start_in_pits else 0

            lap_data = {
                "session_id": self.session_id,
                "stint_id": self.current_stint_id,
                "lap_number": completed_lap,
                "lap_time": frame.last_lap_time,
                "sector_1": max(0.0, s1),
                "sector_2": max(0.0, s2),
                "sector_3": max(0.0, s3),
                "is_valid_lap": 1,
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
                "completed_at": __import__('datetime').datetime.now().isoformat(),
            }

            lap_id = database.insert_lap(lap_data, db_path=self.db_path)
            print(f"[Detector] Lap {completed_lap} saved (id={lap_id}, time={frame.last_lap_time:.3f}s)")
            self.last_saved_lap = completed_lap

            if is_pit_in:
                self.pit_in_lap_number = completed_lap
                self.pit_in_lap_time = frame.last_lap_time
                self.in_pit_stop_sequence = True
                print(f"[Detector] Pit entry detected at lap {completed_lap}")

            elif self.in_pit_stop_sequence and is_pit_out:
                total_pit_laps_time = self.pit_in_lap_time + frame.last_lap_time
                clean_laps = database.get_laps_for_analysis(
                    car=self.car_name,
                    track=self.track_name,
                    db_path=self.db_path
                )
                if clean_laps:
                    ref_lap_time = float(np.median([l["lap_time"] for l in clean_laps]))
                else:
                    ref_lap_time = frame.last_lap_time
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
                print(f"[Detector] Pit exit at lap {completed_lap}, loss={pit_loss:.2f}s")
                self.in_pit_stop_sequence = False
                self.pit_in_lap_number = None
                self.pit_in_lap_time = None

            self._handle_stint_change(frame, completed_lap)

            self.current_lap_number = frame.lap_number
            self.last_lap_time = frame.last_lap_time
            self._take_lap_snapshots(frame)

            return lap_id

        return None

    def _handle_stint_change(self, frame: TelemetryFrame, completed_lap: int) -> None:
        tyres_changed = False
        if frame.tyre_compounds != self.lap_start_compounds:
            tyres_changed = True
            print(f"[Detector] Compound change detected at lap {completed_lap}")
        else:
            current_wear = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
            for start, curr in zip(self.lap_start_wear, current_wear):
                if curr < start - 10.0:
                    tyres_changed = True
                    print(f"[Detector] Tyre change detected at lap {completed_lap} (wear drop)")
                    break

        if tyres_changed or (frame.in_pits or frame.pit_state in [2, 3]):
            if self.current_stint_id:
                current_wear = [(1.0 - w) * 100.0 for w in frame.tyre_wear]
                database.update_stint_end(
                    stint_id=self.current_stint_id,
                    end_lap=completed_lap,
                    end_fuel_l=frame.fuel,
                    db_path=self.db_path
                )
            self.stint_number += 1
            self.tyre_age_laps = 1
            self.current_stint_id = database.create_stint(
                session_id=self.session_id,
                stint_number=self.stint_number,
                compound_front=frame.tyre_compounds[0],
                compound_rear=frame.tyre_compounds[1],
                start_lap=frame.lap_number,
                start_fuel_l=frame.fuel,
                db_path=self.db_path
            )
            print(f"[Detector] New stint #{self.stint_number} started at lap {frame.lap_number}")
        else:
            self.tyre_age_laps += 1
