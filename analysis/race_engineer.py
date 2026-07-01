"""Race Engineer — coordinates fuel, tyres, weather, traffic, and strategy
into a single state machine that generates priority-ordered voice events."""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import IntEnum
import time

from analysis.tyre_manager import estimate_remaining_life, TyreStatus
from analysis.weather_radar import analyze_rain_risk, RainWindow
from analysis.classes import detect_class, estimate_traffic_penalty, get_class_params


class Priority(IntEnum):
    CRITICAL = 4   # Must speak NOW
    WARNING = 3    # Speak within next opportunity
    INFO = 2       # Nice to know
    STATUS = 1     # Periodic status update
    SILENT = 0     # Nothing to say


@dataclass
class RaceEngineerEvent:
    priority: Priority
    category: str      # "fuel", "tyres", "weather", "traffic", "strategy", "performance", "session", "system"
    message: str       # Short message for overlay display
    tts_text: str      # Full text for TTS
    event_id: str      # Unique ID for dedup
    timestamp: float = field(default_factory=time.time)


@dataclass
class RaceState:
    # Fuel
    fuel_l: float = 0
    fuel_capacity: float = 0
    fuel_consumption_lap: float = 0
    fuel_laps_remaining: float = 0
    fuel_pct: float = 100

    # Tyres
    tyre_wear: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    tyre_age_laps: int = 0
    tyre_compound: str = "Medium"
    tyre_status: Optional[TyreStatus] = None

    # Weather
    weather_state: str = ""
    rain_intensity: float = 0
    track_temp: Optional[float] = None
    ambient_temp: Optional[float] = None
    rain_windows: List[RainWindow] = field(default_factory=list)

    # Traffic
    car_class: str = "GT3"
    car_name: str = ""
    traffic_penalty: float = 0
    traffic_density: float = 0

    # Session
    session_type: str = ""
    current_lap: int = 0
    total_laps: int = 0
    lap_time: float = 0
    best_lap_time: Optional[float] = None
    delta_best: float = 0

    # Strategy
    pit_plan: Optional[List[int]] = None
    next_pit_lap: Optional[int] = None
    strategy_text: str = ""

    # History for trend detection
    lap_times_history: List[float] = field(default_factory=list)
    fuel_history: List[float] = field(default_factory=list)
    tyre_age_history: List[int] = field(default_factory=list)


class RaceEngineer:
    """Central coordinator that monitors all race systems and generates voice events.

    Each telemetry frame is fed to update_from_frame(), which evaluates every
    subsystem and returns the single highest-priority event to speak (or None).

    Cooldowns prevent message spam: 20s between messages, 3min dedup per event_id.
    """

    def __init__(self):
        self.state = RaceState()
        self._last_event_time: Dict[str, float] = {}
        self._spoken_ids: Dict[str, float] = {}  # event_id → timestamp (3min dedup)
        self._min_event_interval = 20   # seconds between same category
        self._critical_cooldown = 45    # seconds between critical events
        self._lap_counter = 0
        self._session_start_lap = 0     # track which lap we told session start

    def update_from_frame(self, frame) -> Optional[RaceEngineerEvent]:
        """Process a telemetry frame and return the highest-priority event to speak."""
        if not frame:
            return None

        # Update state
        self.state.current_lap = getattr(frame, 'lap_number', 0) or 0
        self.state.lap_time = getattr(frame, 'last_lap_time', 0) or 0
        self.state.delta_best = getattr(frame, 'delta_best', 0) or 0
        self.state.session_type = getattr(frame, 'session_type', '') or ''
        self.state.car_name = getattr(frame, 'car_name', '') or ''

        # Track lap times for consistency check
        lap_time = self.state.lap_time
        if lap_time and lap_time > 0:
            self.state.lap_times_history.append(lap_time)
            if len(self.state.lap_times_history) > 10:
                self.state.lap_times_history.pop(0)

        # Update fuel
        self.state.fuel_l = getattr(frame, 'fuel', 0) or 0
        self.state.fuel_capacity = getattr(frame, 'fuel_capacity', 0) or 100

        # Track fuel history for consumption estimation
        if hasattr(self.state, 'fuel_history'):
            if self.state.fuel_l > 0:
                self.state.fuel_history.append(self.state.fuel_l)
                if len(self.state.fuel_history) > 10:
                    self.state.fuel_history.pop(0)

        # Update tyres
        tyre_wear = getattr(frame, 'tyre_wear', None)
        self.state.tyre_wear = list(tyre_wear) if tyre_wear else [1.0] * 4

        tyre_compounds = getattr(frame, 'tyre_compounds', None)
        if tyre_compounds and len(tyre_compounds) > 0:
            self.state.tyre_compound = tyre_compounds[0] or "Medium"

        # Track tyre age (increment when lap number increases)
        lap_num = self.state.current_lap
        if lap_num != self._lap_counter:
            if lap_num > self._lap_counter:
                tyre_age = getattr(frame, 'tyre_age_laps', None)
                if tyre_age:
                    self.state.tyre_age_laps = tyre_age
                else:
                    self.state.tyre_age_laps += 1
            self._lap_counter = lap_num or 0

        # Update weather
        self.state.weather_state = getattr(frame, 'weather_state', '') or ''
        self.state.rain_intensity = getattr(frame, 'rain_intensity', 0) or 0
        self.state.track_temp = getattr(frame, 'track_temp', None)
        self.state.ambient_temp = getattr(frame, 'ambient_temp', None)

        # Detect car class
        self.state.car_class = detect_class(self.state.car_name)

        # Compute derived values
        self._compute_fuel_remaining()
        self._compute_tyre_status()
        self._compute_weather_risk()

        # Return highest priority event
        return self._get_priority_event()

    def update_strategy(self, pit_plan: Optional[List[int]], current_lap: int, total_laps: int):
        """Update strategy info from the strategy refresher."""
        self.state.pit_plan = pit_plan
        self.state.current_lap = current_lap
        self.state.total_laps = total_laps
        if pit_plan:
            next_pit = next((l for l in pit_plan if l > current_lap), None)
            self.state.next_pit_lap = next_pit
        else:
            self.state.next_pit_lap = None

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _compute_fuel_remaining(self):
        """Calculate fuel status from frame data."""
        # Estimate consumption from recent fuel history
        consumption = 0.0
        if len(self.state.fuel_history) >= 3:
            recent = self.state.fuel_history[-3:]
            diffs = [recent[i] - recent[i+1] for i in range(len(recent)-1)]
            positive_diffs = [d for d in diffs if d > 0]
            if positive_diffs:
                consumption = sum(positive_diffs) / len(positive_diffs)

        if consumption > 0:
            self.state.fuel_consumption_lap = consumption
            self.state.fuel_laps_remaining = self.state.fuel_l / consumption
        else:
            # Fallback: use class-based default
            params = get_class_params(self.state.car_class)
            default_cons = params.get('fuel_consumption', 3.2)
            self.state.fuel_consumption_lap = default_cons
            self.state.fuel_laps_remaining = self.state.fuel_l / default_cons

        cap = self.state.fuel_capacity
        self.state.fuel_pct = (self.state.fuel_l / cap * 100) if cap > 0 else 0

    def _compute_tyre_status(self):
        """Get tyre status from tyre manager."""
        try:
            self.state.tyre_status = estimate_remaining_life(
                current_wear=self.state.tyre_wear,
                tyre_age_laps=self.state.tyre_age_laps,
                compound=self.state.tyre_compound,
                track_temp=self.state.track_temp,
                historical_cliff=None,
            )
        except Exception:
            self.state.tyre_status = None

    def _compute_weather_risk(self):
        """Get weather risk assessment."""
        try:
            self.state.rain_windows = analyze_rain_risk(
                current_weather=self.state.weather_state,
                rain_intensity=self.state.rain_intensity,
                track_temp=self.state.track_temp,
            )
        except Exception:
            self.state.rain_windows = []

    # ── Event prioritisation ─────────────────────────────────────────────────

    def _get_priority_event(self) -> Optional[RaceEngineerEvent]:
        """Evaluate all subsystems and return the highest-priority event."""
        events = []

        for evaluator in [
            self._evaluate_critical_tyres,
            self._evaluate_critical_fuel,
            self._evaluate_critical_weather,
            self._evaluate_critical_strategy,
            self._evaluate_warning_fuel,
            self._evaluate_warning_tyres,
            self._evaluate_warning_weather,
            self._evaluate_warning_strategy,
            self._evaluate_traffic,
            self._evaluate_performance,
            self._evaluate_session,
        ]:
            try:
                event = evaluator()
                if event:
                    events.append(event)
            except Exception:
                pass

        if not events:
            return None

        # Sort by priority (highest first), then by timestamp (oldest first for same priority)
        events.sort(key=lambda e: (-e.priority.value, e.timestamp))

        # Check dedup: don't return an event_id we've spoken within 3 minutes
        best = events[0]
        now = time.time()
        if best.event_id in self._spoken_ids:
            if now - self._spoken_ids[best.event_id] < 180:
                # Try next-highest priority event
                for ev in events[1:]:
                    if ev.event_id not in self._spoken_ids or now - self._spoken_ids[ev.event_id] >= 180:
                        best = ev
                        break
                else:
                    # All events are deduped — check if the same event is still valid
                    if now - self._spoken_ids.get(best.event_id, 0) < 180:
                        return None

        return best

    def mark_spoken(self, event: RaceEngineerEvent):
        """Called after an event has been successfully spoken."""
        now = time.time()
        self._last_event_time[event.category] = now
        self._spoken_ids[event.event_id] = now

    def _can_speak(self, category: str, priority: Priority) -> bool:
        """Check cooldown for a category."""
        now = time.time()
        last = self._last_event_time.get(category, 0)

        if priority >= Priority.CRITICAL:
            return now - last >= self._critical_cooldown
        elif priority >= Priority.WARNING:
            return now - last >= self._min_event_interval
        else:
            return now - last >= self._min_event_interval * 2

    # ── Subsystem evaluators (each returns an event or None) ─────────────────
    # These are wrapped in try/except in _get_priority_event so they never crash

    def _evaluate_critical_fuel(self) -> Optional[RaceEngineerEvent]:
        if self.state.fuel_laps_remaining <= 0 and self.state.fuel_l < 2:
            if self._can_speak("fuel", Priority.CRITICAL):
                return RaceEngineerEvent(
                    priority=Priority.CRITICAL, category="fuel",
                    message="PIT NOW — fuel critical!",
                    tts_text="Fuel critical, box this lap!",
                    event_id="fuel_critical",
                )
        return None

    def _evaluate_critical_tyres(self) -> Optional[RaceEngineerEvent]:
        if self.state.tyre_status and self.state.tyre_status.remaining_laps <= 0:
            if self._can_speak("tyres", Priority.CRITICAL):
                return RaceEngineerEvent(
                    priority=Priority.CRITICAL, category="tyres",
                    message="PIT NOW — tyres at cliff!",
                    tts_text="Pit now, tyres critically worn!",
                    event_id="tyre_critical",
                )
        return None

    def _evaluate_critical_weather(self) -> Optional[RaceEngineerEvent]:
        for w in self.state.rain_windows:
            if w.expected_start_min is not None and w.expected_start_min <= 2 and w.probability > 0.6:
                if self._can_speak("weather", Priority.CRITICAL):
                    return RaceEngineerEvent(
                        priority=Priority.CRITICAL, category="weather",
                        message="RAIN — pit for wets!",
                        tts_text="Rain on track! Pit now for wet tyres!",
                        event_id="rain_now",
                    )
        return None

    def _evaluate_critical_strategy(self) -> Optional[RaceEngineerEvent]:
        if self.state.next_pit_lap:
            laps_to_pit = self.state.next_pit_lap - self.state.current_lap
            if laps_to_pit == 0:
                if self._can_speak("strategy", Priority.CRITICAL):
                    return RaceEngineerEvent(
                        priority=Priority.CRITICAL, category="strategy",
                        message="Pit window OPEN — box this lap!",
                        tts_text="Pit window open. Box this lap for your planned stop.",
                        event_id="pit_now_strategy",
                    )
        return None

    def _evaluate_warning_fuel(self) -> Optional[RaceEngineerEvent]:
        laps = self.state.fuel_laps_remaining
        if 0 < laps <= 3:
            if self._can_speak("fuel", Priority.WARNING):
                return RaceEngineerEvent(
                    priority=Priority.WARNING, category="fuel",
                    message=f"Pit in {int(laps)}L — fuel low",
                    tts_text=f"Pit in {int(laps)} laps, fuel low at {self.state.fuel_pct:.0f} percent.",
                    event_id=f"fuel_low_{int(laps)}",
                )
        return None

    def _evaluate_warning_tyres(self) -> Optional[RaceEngineerEvent]:
        ts = self.state.tyre_status
        if ts:
            rl = ts.remaining_laps
            if 1 <= rl <= 3:
                if self._can_speak("tyres", Priority.WARNING):
                    return RaceEngineerEvent(
                        priority=Priority.WARNING, category="tyres",
                        message=f"Pit in {rl}L — tyres degrading",
                        tts_text=f"Pit in {rl} laps, tyres reaching cliff.",
                        event_id=f"tyre_warn_{rl}",
                    )
            elif 4 <= rl <= 6:
                if self._can_speak("tyres", Priority.INFO):
                    return RaceEngineerEvent(
                        priority=Priority.INFO, category="tyres",
                        message=f"~{rl}L before cliff",
                        tts_text=f"Approximately {rl} laps remaining on these tyres.",
                        event_id=f"tyre_info_{rl}",
                    )
            elif ts.temp_status == "cold":
                if self._can_speak("tyres", Priority.INFO):
                    return RaceEngineerEvent(
                        priority=Priority.INFO, category="tyres",
                        message="Tyres still cold",
                        tts_text="Tyres still cold, push to bring them in the window.",
                        event_id="tyre_cold",
                    )
        return None

    def _evaluate_warning_weather(self) -> Optional[RaceEngineerEvent]:
        for w in self.state.rain_windows:
            if w.expected_start_min is not None and 3 <= w.expected_start_min <= 8 and w.probability > 0.5:
                if self._can_speak("weather", Priority.WARNING):
                    return RaceEngineerEvent(
                        priority=Priority.WARNING, category="weather",
                        message=f"Rain in ~{w.expected_start_min}m",
                        tts_text=f"Rain expected in approximately {w.expected_start_min} minutes. Prepare pit for wet tyres.",
                        event_id=f"rain_soon_{w.expected_start_min}",
                    )
            elif w.expected_start_min is not None and 9 <= w.expected_start_min <= 20 and w.probability > 0.5:
                if self._can_speak("weather", Priority.INFO):
                    return RaceEngineerEvent(
                        priority=Priority.INFO, category="weather",
                        message=f"Rain in ~{w.expected_start_min}m",
                        tts_text=f"Rain expected in about {w.expected_start_min} minutes. Monitor conditions.",
                        event_id=f"rain_later_{w.expected_start_min}",
                    )
        return None

    def _evaluate_warning_strategy(self) -> Optional[RaceEngineerEvent]:
        if self.state.next_pit_lap:
            laps_to_pit = self.state.next_pit_lap - self.state.current_lap
            if 1 <= laps_to_pit <= 2:
                if self._can_speak("strategy", Priority.WARNING):
                    return RaceEngineerEvent(
                        priority=Priority.WARNING, category="strategy",
                        message=f"Pit in {laps_to_pit}L — strategy",
                        tts_text=f"Pit in {laps_to_pit} laps, strategy calls for a stop.",
                        event_id=f"pit_soon_{laps_to_pit}",
                    )
        return None

    def _evaluate_traffic(self) -> Optional[RaceEngineerEvent]:
        if self.state.car_class == "Hypercar" and self.state.current_lap > 3:
            try:
                penalty = estimate_traffic_penalty("Hypercar", "GT3", traffic_density=0.5)
                if penalty > 1.0:
                    if self._can_speak("traffic", Priority.INFO):
                        return RaceEngineerEvent(
                            priority=Priority.INFO, category="traffic",
                            message=f"Traffic ~{penalty:.1f}s/lap",
                            tts_text=f"GT3 traffic ahead, losing approximately {penalty:.1f} seconds per lap.",
                            event_id=f"traffic_{int(penalty)}",
                        )
            except Exception:
                pass
        return None

    def _evaluate_performance(self) -> Optional[RaceEngineerEvent]:
        # Personal best: when delta_best is <= 0 and we have a valid lap time
        # (delta_best <= 0 means current lap is faster than or equal to best)
        if self.state.delta_best <= 0 and self.state.lap_time > 0 and self.state.current_lap > 1:
            if self._can_speak("performance", Priority.INFO):
                return RaceEngineerEvent(
                    priority=Priority.INFO, category="performance",
                    message="Personal Best!",
                    tts_text=f"Personal best lap! {self.state.lap_time:.1f} seconds.",
                    event_id=f"pb_{self.state.current_lap}",
                )

        # Consistency check every 5 laps
        if len(self.state.lap_times_history) >= 5 and self.state.current_lap % 5 == 0:
            times = self.state.lap_times_history[-5:]
            spread = max(times) - min(times)
            if spread < 0.5:
                if self._can_speak("performance", Priority.STATUS):
                    return RaceEngineerEvent(
                        priority=Priority.STATUS, category="performance",
                        message=f"Consistent! ±{spread:.2f}s / 5 laps",
                        tts_text=f"Great consistency, last 5 laps within {spread:.2f} seconds.",
                        event_id=f"consistent_{self.state.current_lap}",
                    )
        return None

    def _evaluate_session(self) -> Optional[RaceEngineerEvent]:
        # Session start announcement (once per session)
        if self.state.current_lap >= 1 and self.state.current_lap != self._session_start_lap:
            self._session_start_lap = self.state.current_lap

            if self.state.current_lap == 1 and self.state.session_type:
                stype = self.state.session_type.upper()
                if "RACE" in stype:
                    if self._can_speak("session", Priority.INFO):
                        return RaceEngineerEvent(
                            priority=Priority.INFO, category="session",
                            message="Race session — engineer online",
                            tts_text="Race session detected. Race engineer online. Good luck!",
                            event_id="race_start",
                        )
                elif "QUAL" in stype or "HOT" in stype:
                    if self._can_speak("session", Priority.INFO):
                        return RaceEngineerEvent(
                            priority=Priority.INFO, category="session",
                            message="Qualifying — hotlap mode active",
                            tts_text="Qualifying session detected. Hotlap mode active.",
                            event_id="qualy_start",
                        )
        return None

    # ── Summary ──────────────────────────────────────────────────────────────

    def get_state_summary(self) -> str:
        """Get a concise state summary for the overlay display."""
        parts = []
        if self.state.fuel_laps_remaining > 0:
            parts.append(f"⛽ {self.state.fuel_laps_remaining:.1f}L")
        if self.state.tyre_status:
            parts.append(f"🛞 {self.state.tyre_status.remaining_laps}L")
        if self.state.rain_intensity > 0.1:
            parts.append(f"🌧 {self.state.rain_intensity:.0%}")
        if self.state.next_pit_lap:
            parts.append(f"🏁 PIT L{self.state.next_pit_lap}")
        return " | ".join(parts) if parts else ""
