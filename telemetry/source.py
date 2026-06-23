import sys
import os
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import paths

# Setup path for vendored dependencies
VENDOR_PATH = paths.data_path("vendor")
sys.path.insert(0, os.path.join(VENDOR_PATH, "pyLMUSharedMemory"))
sys.path.insert(0, os.path.join(VENDOR_PATH, "pyRfactor2SharedMemory"))


@dataclass
class TelemetryFrame:
    """
    Standard telemetry frame shared between live and synthetic sources.
    All strings are Python strings. Tyre wear is 0.0-1.0 (1.0 = brand new).
    """
    track_name: str = ""
    layout_name: str = ""
    car_name: str = ""
    session_type: str = "PRACTICE"  # PRACTICE, QUALIFYING, RACE
    lap_number: int = 1
    stint_number: int = 1
    elapsed_time: float = 0.0
    fuel: float = 0.0
    fuel_capacity: float = 0.0
    tyre_wear: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])  # FL, FR, RL, RR
    tyre_compounds: List[str] = field(default_factory=lambda: ["Medium", "Medium"])  # front, rear
    track_temp: float = 25.0
    ambient_temp: float = 20.0
    weather_state: str = "DRY"
    rain_intensity: float = 0.0
    is_valid_lap: bool = True
    in_pits: bool = False
    pit_state: int = 0  # 0=none, 1=request, 2=entering, 3=stopped, 4=exiting
    sector: int = 0  # 0=sector3, 1=sector1, 2=sector2
    last_sector1: float = 0.0
    last_sector2: float = 0.0  # cumulative (S1+S2)
    last_lap_time: float = 0.0
    delta_best: float = 0.0


class TelemetrySource(ABC):
    """
    Abstract Base Class for telemetry sources.
    """
    @abstractmethod
    def start(self) -> None:
        """Start the telemetry source connection/simulation."""
        pass

    @abstractmethod
    def get_next_frame(self) -> Optional[TelemetryFrame]:
        """Fetch the latest telemetry frame. Returns None if no frame is available."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop and clean up the telemetry source."""
        pass


class LiveSharedMemorySource(TelemetrySource):
    """
    Reads live data from Le Mans Ultimate shared memory.
    Falls back to rFactor 2 if LMU shared memory is not found.
    """
    def __init__(self):
        self.lmu_info = None
        self.rf2_info = None
        self.active_api = None  # "LMU" or "RF2"
        self.running = False

    def start(self) -> None:
        self.running = True
        # Try to initialize LMU Shared Memory
        try:
            from lmu_mmap import SimInfo as LMUSimInfo
            self.lmu_info = LMUSimInfo()
            # Test if we can read version or if LMU is running
            if self.lmu_info.LMUData.generic.gameVersion > 0:
                self.active_api = "LMU"
                return
        except Exception:
            self.lmu_info = None

        # Fallback to rFactor 2 Shared Memory
        try:
            from sharedMemoryAPI import SimInfoAPI as RF2SimInfo
            self.rf2_info = RF2SimInfo()
            if self.rf2_info.isRF2running() and self.rf2_info.isSharedMemoryAvailable():
                self.active_api = "RF2"
                return
        except Exception:
            self.rf2_info = None

    def get_next_frame(self) -> Optional[TelemetryFrame]:
        if not self.running:
            return None

        if self.active_api == "LMU" and self.lmu_info:
            try:
                data = self.lmu_info.LMUData
                # Check game running
                if data.generic.gameVersion <= 0:
                    return None

                # Player vehicle index
                p_idx = data.telemetry.playerVehicleIdx
                if p_idx >= len(data.telemetry.telemInfo):
                    return None

                telem = data.telemetry.telemInfo[p_idx]
                
                # Find player scoring
                scoring = None
                for i in range(data.scoring.scoringInfo.mNumVehicles):
                    veh = data.scoring.vehScoringInfo[i]
                    if veh.mIsPlayer:
                        scoring = veh
                        break

                if not scoring:
                    return None

                # Parse track names and car name
                def clean_str(b: bytes) -> str:
                    return b.partition(b'\0')[0].decode('utf-8', errors='ignore').strip()

                track = clean_str(data.scoring.scoringInfo.mTrackName)
                car = clean_str(telem.mVehicleModel)
                if not car:
                    car = clean_str(telem.mVehicleName)

                # Compounds
                comp_front = clean_str(telem.mFrontTireCompoundName)
                comp_rear = clean_str(telem.mRearTireCompoundName)

                # Sector formatting: S0=sector3, S1=sector1, S2=sector2 in S397 scoring
                # But in standard telemetry we represent: 1=sector1, 2=sector2, 3=sector3
                sector_raw = scoring.mSector
                if sector_raw == 1:
                    sector = 1
                elif sector_raw == 2:
                    sector = 2
                else:
                    sector = 3

                # Session mapping
                session_raw = data.scoring.scoringInfo.mSession
                if session_raw == 0:
                    session_type = "PRACTICE"  # Test day
                elif session_raw in [1, 2, 3, 4]:
                    session_type = "PRACTICE"
                elif session_raw in [5, 6, 7, 8]:
                    session_type = "QUALIFYING"
                else:
                    session_type = "RACE"

                # Tyre wear: 4 wheels
                wear = [
                    telem.mWheels[0].mWear,
                    telem.mWheels[1].mWear,
                    telem.mWheels[2].mWear,
                    telem.mWheels[3].mWear
                ]

                frame = TelemetryFrame(
                    track_name=track,
                    layout_name="",  # Layout details are typically merged in track name
                    car_name=car,
                    session_type=session_type,
                    lap_number=telem.mLapNumber,
                    stint_number=1,  # Stint is computed in detector
                    elapsed_time=telem.mElapsedTime,
                    fuel=telem.mFuel,
                    fuel_capacity=telem.mFuelCapacity,
                    tyre_wear=wear,
                    tyre_compounds=[comp_front, comp_rear],
                    track_temp=data.scoring.scoringInfo.mTrackTemp,
                    ambient_temp=data.scoring.scoringInfo.mAmbientTemp,
                    weather_state="WET" if data.scoring.scoringInfo.mRaining > 0.1 else "DRY",
                    rain_intensity=data.scoring.scoringInfo.mRaining,
                    is_valid_lap=not telem.mLapInvalidated,
                    in_pits=scoring.mInPits,
                    pit_state=scoring.mPitState,
                    sector=sector,
                    last_sector1=scoring.mLastSector1,
                    last_sector2=scoring.mLastSector2,
                    last_lap_time=scoring.mLastLapTime,
                    delta_best=telem.mDeltaBest
                )
                return frame
            except Exception:
                return None

        elif self.active_api == "RF2" and self.rf2_info:
            try:
                # Fallback implementation for rFactor 2
                if not self.rf2_info.isRF2running() or not self.rf2_info.isSharedMemoryAvailable():
                    return None

                telem = self.rf2_info.playersVehicleTelemetry()
                scoring = self.rf2_info.playersVehicleScoring()

                def clean_str(b: bytes) -> str:
                    return bytes(b).partition(b'\0')[0].decode('utf-8', errors='ignore').strip()

                track = clean_str(self.rf2_info.Rf2Scor.mScoringInfo.mTrackName)
                car = clean_str(self.rf2_info.vehicleName())

                # Session mapping
                session_raw = self.rf2_info.Rf2Scor.mScoringInfo.mSession
                if session_raw == 0:
                    session_type = "PRACTICE"
                elif session_raw in [1, 2, 3, 4]:
                    session_type = "PRACTICE"
                elif session_raw in [5, 6, 7, 8]:
                    session_type = "QUALIFYING"
                else:
                    session_type = "RACE"

                wear = [
                    telem.mWheels[0].mWear,
                    telem.mWheels[1].mWear,
                    telem.mWheels[2].mWear,
                    telem.mWheels[3].mWear
                ]

                # sector mapping
                sector_raw = scoring.mSector
                if sector_raw == 1:
                    sector = 1
                elif sector_raw == 2:
                    sector = 2
                else:
                    sector = 3

                frame = TelemetryFrame(
                    track_name=track,
                    layout_name="",
                    car_name=car,
                    session_type=session_type,
                    lap_number=telem.mLapNumber,
                    stint_number=1,
                    elapsed_time=telem.mElapsedTime,
                    fuel=telem.mFuel,
                    fuel_capacity=telem.mFuelCapacity,
                    tyre_wear=wear,
                    tyre_compounds=["Medium", "Medium"],  # rF2 doesn't name compounds directly in telem structure
                    track_temp=self.rf2_info.Rf2Scor.mScoringInfo.mTrackTemp,
                    ambient_temp=self.rf2_info.Rf2Scor.mScoringInfo.mAmbientTemp,
                    weather_state="WET" if self.rf2_info.Rf2Scor.mScoringInfo.mRaining > 0.1 else "DRY",
                    rain_intensity=self.rf2_info.Rf2Scor.mScoringInfo.mRaining,
                    is_valid_lap=True,  # Fallback
                    in_pits=scoring.mInPits,
                    pit_state=scoring.mPitState,
                    sector=sector,
                    last_sector1=scoring.mLastSector1,
                    last_sector2=scoring.mLastSector2,
                    last_lap_time=scoring.mLastLapTime,
                    delta_best=0.0
                )
                return frame
            except Exception:
                return None

        return None

    def stop(self) -> None:
        self.running = False
        if self.lmu_info:
            self.lmu_info.close()
        if self.rf2_info:
            self.rf2_info.close()


class SyntheticReplaySource(TelemetrySource):
    """
    Generates realistic synthetic telemetry frames to support testing without the game.
    """
    def __init__(
        self,
        track_name: str = "Monza",
        car_name: str = "Ferrari 499P LMH",
        session_type: str = "PRACTICE",
        lap_time_base: float = 100.0,  # Base lap time on empty tank and fresh tyres
        fuel_capacity: float = 100.0,
        initial_fuel: float = 80.0,
        fuel_consumption: float = 3.2,  # Liters per lap
        fuel_effect: float = 0.05,  # Seconds slower per liter of fuel
        wear_rate: List[float] = None,  # Tyre wear increase fraction per lap FL, FR, RL, RR
        cliff_lap: int = 15,
        cliff_wear_multiplier: float = 4.0,  # Tire wear accelerates by 4x after cliff
        tyre_degradation_effect: float = 0.1,  # Seconds slower per 1% wear
        pit_stop_duration: float = 30.0,  # Duration in seconds of service
        anomaly_laps: Dict[int, float] = None,  # {lap_number: delay_seconds}
        pit_laps: List[int] = None,  # Laps at the end of which player pits
        total_laps: int = 40,
        tick_rate: float = 0.1  # Simulated seconds per step (for real-time or fast simulation)
    ):
        self.track_name = track_name
        self.car_name = car_name
        self.session_type = session_type
        self.lap_time_base = lap_time_base
        self.fuel_capacity = fuel_capacity
        self.fuel = initial_fuel
        self.fuel_consumption = fuel_consumption
        self.fuel_effect = fuel_effect
        self.wear_rate = wear_rate if wear_rate else [0.012, 0.012, 0.010, 0.010]
        self.cliff_lap = cliff_lap
        self.cliff_wear_multiplier = cliff_wear_multiplier
        self.tyre_degradation_effect = tyre_degradation_effect
        self.pit_stop_duration = pit_stop_duration
        self.anomaly_laps = anomaly_laps if anomaly_laps else {}
        self.pit_laps = pit_laps if pit_laps else []
        self.total_laps = total_laps
        self.tick_rate = tick_rate

        # Simulation states
        self.lap_number = 1
        self.stint_number = 1
        self.tyre_age_laps = 1
        self.elapsed_time = 0.0
        self.lap_start_et = 0.0
        self.current_lap_dist = 0.0
        self.track_length = 5793.0  # meters
        self.tyre_wear = [1.0, 1.0, 1.0, 1.0]  # 1.0 is brand new
        self.in_pits = False
        self.pit_state = 0
        self.pit_stop_timer = 0.0
        self.is_valid_lap = True

        self.last_lap_time = 0.0
        self.last_sector1 = 0.0
        self.last_sector2 = 0.0

        self.running = False
        self.track_temp = 30.0
        self.ambient_temp = 22.0
        self.rain_intensity = 0.0
        self.weather_state = "DRY"
        self.sector = 1

    def start(self) -> None:
        self.running = True

    def get_next_frame(self) -> Optional[TelemetryFrame]:
        if not self.running or self.lap_number > self.total_laps + 1:
            return None

        # 1. Capture current frame data representing start-of-tick state
        frame = TelemetryFrame(
            track_name=self.track_name,
            layout_name="Grand Prix",
            car_name=self.car_name,
            session_type=self.session_type,
            lap_number=self.lap_number,
            stint_number=self.stint_number,
            elapsed_time=self.elapsed_time,
            fuel=self.fuel,
            fuel_capacity=self.fuel_capacity,
            tyre_wear=list(self.tyre_wear),
            tyre_compounds=[f"Soft-{self.stint_number}", f"Soft-{self.stint_number}"],
            track_temp=self.track_temp,
            ambient_temp=self.ambient_temp,
            weather_state=self.weather_state,
            rain_intensity=self.rain_intensity,
            is_valid_lap=self.is_valid_lap,
            in_pits=self.in_pits,
            pit_state=self.pit_state,
            sector=self.sector,
            last_sector1=self.last_sector1,
            last_sector2=self.last_sector2,
            last_lap_time=self.last_lap_time,
            delta_best=random.uniform(-0.5, 0.5)
        )

        # 2. Advance physics/simulation for the next tick
        self.track_temp += random.uniform(-0.01, 0.01)

        if self.in_pits:
            # Stationary in pits getting refueled and tyres changed
            self.pit_stop_timer += self.tick_rate
            self.pit_state = 3  # Stopped
            self.elapsed_time += self.tick_rate

            if self.pit_stop_timer >= self.pit_stop_duration:
                # Finished service
                self.fuel = self.fuel_capacity
                self.tyre_wear = [1.0, 1.0, 1.0, 1.0]
                self.tyre_age_laps = 1
                self.stint_number += 1
                self.in_pits = False
                self.pit_state = 4  # Exiting
                self.current_lap_dist = 0.0
                self.lap_start_et = self.elapsed_time
                self.is_valid_lap = True
                self.sector = 1
        else:
            # Driving on track
            avg_wear_pct = (1.0 - sum(self.tyre_wear) / 4.0) * 100.0
            current_target = self.lap_time_base + (self.fuel_effect * self.fuel) + (self.tyre_degradation_effect * avg_wear_pct)
            
            if self.lap_number in self.anomaly_laps:
                current_target += self.anomaly_laps[self.lap_number]
                
            current_target += random.normalvariate(0, 0.2)

            speed = self.track_length / current_target  # Average speed in m/s
            self.current_lap_dist += speed * self.tick_rate
            self.elapsed_time += self.tick_rate

            # Fuel consumption
            fuel_per_meter = self.fuel_consumption / self.track_length
            self.fuel -= fuel_per_meter * speed * self.tick_rate
            if self.fuel < 0:
                self.fuel = 0.0

            # Tyre wear
            for i in range(4):
                base_wear_rate = self.wear_rate[i]
                if self.tyre_age_laps > self.cliff_lap:
                    base_wear_rate *= self.cliff_wear_multiplier
                wear_per_meter = base_wear_rate / self.track_length
                self.tyre_wear[i] -= wear_per_meter * speed * self.tick_rate
                if self.tyre_wear[i] < 0:
                    self.tyre_wear[i] = 0.0

            # Sector calculation based on distance
            dist_fraction = self.current_lap_dist / self.track_length
            if dist_fraction < 0.35:
                self.sector = 1
            elif dist_fraction < 0.70:
                self.sector = 2
            else:
                self.sector = 3

            # Check if lap completed
            if self.current_lap_dist >= self.track_length:
                # Lap finished
                self.last_lap_time = self.elapsed_time - self.lap_start_et
                self.last_sector1 = self.last_lap_time * 0.35
                self.last_sector2 = self.last_lap_time * 0.70

                if self.lap_number in self.pit_laps or self.fuel < self.fuel_consumption:
                    self.in_pits = True
                    self.pit_state = 2  # Entering
                    self.pit_stop_timer = 0.0
                    self.sector = 3
                
                self.lap_number += 1
                if not self.in_pits:
                    self.tyre_age_laps += 1
                    self.current_lap_dist = 0.0
                    self.lap_start_et = self.elapsed_time
                    self.is_valid_lap = True
                    self.sector = 1

        return frame

    def stop(self) -> None:
        self.running = False
