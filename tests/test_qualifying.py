"""
Tests for qualifying analysis — lap classification and tyre temperature window.

Covers:
  - classify_qualifying_laps basic patterns
  - estimate_tyre_temp_window:
        * compound-based window (Soft/Medium/Hard)
        * track temperature adjustments (cold <20°C, hot >35°C)
        * wet compound handling
        * empty input edge case
        * best-in-window vs best-outside-window tracking
"""

from analysis.qualifying import (
    estimate_tyre_temp_window,
    classify_qualifying_laps,
    TYRE_COLD,
    TYRE_IN_WINDOW,
    TYRE_DEGRADED,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _lap(
    lap_number: int,
    lap_time: float = 100.0,
    compound: str = "Medium",
    track_temp: float = 25.0,
    tyre_age_laps: int | None = None,
    is_pit_out: bool = False,
    is_pit_in: bool = False,
) -> dict:
    """Build a minimal lap dict for tyre-window testing."""
    return {
        "lap_number": lap_number,
        "lap_time": lap_time,
        "compound_front": compound,
        "compound_rear": compound,
        "track_temp": track_temp,
        "tyre_age_laps": tyre_age_laps if tyre_age_laps is not None else lap_number,
        "is_pit_out_lap": int(is_pit_out),
        "is_pit_in_lap": int(is_pit_in),
        "sector_1": 33.0,
        "sector_2": 34.0,
        "sector_3": 33.0,
        "fuel_used_l": 3.2,
    }


def _default_types(n: int) -> list[str]:
    """Helper: outlap + (n-1) hotlaps."""
    return ["outlap"] + ["hotlap"] * (n - 1)


# ──────────────────────────────────────────────────────────────────────────────
# Lap classification
# ──────────────────────────────────────────────────────────────────────────────


def test_classify_empty_laps():
    assert classify_qualifying_laps([]) == []


def test_classify_no_pit_out_all_unknown():
    laps = [_lap(i) for i in range(1, 4)]
    types = classify_qualifying_laps(laps)
    assert all(t == "unknown" for t in types)


def test_classify_basic_run():
    laps = [
        _lap(1, is_pit_out=True),
        _lap(2),
        _lap(3),
        _lap(4, is_pit_in=True),
    ]
    types = classify_qualifying_laps(laps)
    assert types == ["outlap", "hotlap", "hotlap", "inlap"]


# ──────────────────────────────────────────────────────────────────────────────
# Tyre temperature window — compound sensitivity
# ──────────────────────────────────────────────────────────────────────────────


def test_soft_compound_window():
    """Soft at 25°C → optimal lap 2 only."""
    laps = [_lap(i, compound="Soft", track_temp=25.0) for i in range(1, 6)]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    assert result["optimal_hotlaps_count"] == 1
    assert result["tyre_window_message"] == (
        "🛞 Soft tyres: optimal laps 2-2 (1 hotlap per run)"
    )


def test_medium_compound_window():
    """Medium at 25°C → optimal laps 2-3."""
    laps = [_lap(i, compound="Medium", track_temp=25.0) for i in range(1, 6)]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    assert result["optimal_hotlaps_count"] == 2
    assert "optimal laps 2-3" in result["tyre_window_message"]


def test_hard_compound_window():
    """Hard at 25°C → optimal laps 2-4."""
    laps = [_lap(i, compound="Hard", track_temp=25.0) for i in range(1, 7)]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    assert result["optimal_hotlaps_count"] == 3
    assert "optimal laps 2-4" in result["tyre_window_message"]


# ──────────────────────────────────────────────────────────────────────────────
# Tyre temperature window — track temperature adjustments
# ──────────────────────────────────────────────────────────────────────────────


def test_cold_track_shifts_window_plus_one():
    """Hard at <20°C → slower warmup, window shifts +1 (laps 3-4)."""
    laps = [_lap(i, compound="Hard", track_temp=15.0) for i in range(1, 7)]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    assert result["optimal_hotlaps_count"] == 2
    assert "optimal laps 3-4" in result["tyre_window_message"]
    assert "cold track" in result["tyre_window_message"].lower()


def test_hot_track_shrinks_window_minus_one():
    """Hard at >35°C → faster degradation, window shrinks -1 (laps 2-3)."""
    laps = [_lap(i, compound="Hard", track_temp=38.0) for i in range(1, 7)]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    assert result["optimal_hotlaps_count"] == 2
    assert "optimal laps 2-3" in result["tyre_window_message"]
    assert "hot track" in result["tyre_window_message"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Wet compounds
# ──────────────────────────────────────────────────────────────────────────────


def test_wet_compound_all_degraded():
    """Wet / Intermediate tyres — no optimal window, all laps degraded."""
    for compound in ("Wet", "Intermediate", "FullWet"):
        laps = [_lap(i, compound=compound, track_temp=25.0) for i in range(1, 5)]
        result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
        assert result["optimal_hotlaps_count"] == 0
        assert result["best_in_window"] is None
        assert result["best_outside_window"] is not None  # best of the degraded lot
        for entry in result["laps_classified"]:
            assert entry["tyre_state"] == TYRE_DEGRADED


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────


def test_empty_laps_returns_default():
    """Empty laps + types → default dict with no lap data message."""
    result = estimate_tyre_temp_window([], [])
    assert result["laps_classified"] == []
    assert result["best_in_window"] is None
    assert result["best_outside_window"] is None
    assert result["window_lost_time"] is None
    assert result["optimal_hotlaps_count"] == 0
    assert "No lap data" in result["tyre_window_message"]


def test_mismatched_lengths_treated_as_empty():
    """Non-empty laps but empty types → treated as empty (types falsy)."""
    laps = [_lap(1)]
    result = estimate_tyre_temp_window(laps, [])
    assert result["optimal_hotlaps_count"] == 0
    assert "No lap data" in result["tyre_window_message"]


# ──────────────────────────────────────────────────────────────────────────────
# Best-in-window vs best-outside-window tracking
# ──────────────────────────────────────────────────────────────────────────────


def test_best_in_window_tracking():
    """Medium at 25°C (window 2-3): verify best_in vs best_outside.

    Lap layout:
      Lap 1 (cold,    105.0s)  → outside
      Lap 2 (in-window,101.0s) → best_in_window
      Lap 3 (in-window,102.0s)
      Lap 4 (degraded, 103.0s) → best_outside_window (fastest outside)
      Lap 5 (degraded, 104.0s)
    """
    laps = [
        _lap(1, lap_time=105.0, compound="Medium", track_temp=25.0, tyre_age_laps=1),
        _lap(2, lap_time=101.0, compound="Medium", track_temp=25.0, tyre_age_laps=2),
        _lap(3, lap_time=102.0, compound="Medium", track_temp=25.0, tyre_age_laps=3),
        _lap(4, lap_time=103.0, compound="Medium", track_temp=25.0, tyre_age_laps=4),
        _lap(5, lap_time=104.0, compound="Medium", track_temp=25.0, tyre_age_laps=5),
    ]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    assert result["best_in_window"] == 101.0
    assert result["best_outside_window"] == 103.0
    assert result["window_lost_time"] == 2.0  # 103 - 101


def test_best_outside_window_when_no_in_window():
    """If all laps are cold (before window), best_outside is set."""
    laps = [
        _lap(1, lap_time=102.0, compound="Medium", track_temp=25.0, tyre_age_laps=1),
        _lap(2, lap_time=101.0, compound="Medium", track_temp=25.0, tyre_age_laps=1),
    ]
    types = ["outlap", "hotlap"]
    result = estimate_tyre_temp_window(laps, types)
    assert result["best_in_window"] is None
    assert result["best_outside_window"] == 101.0


def test_window_lost_time_none_when_only_one_side():
    """If only in-window laps exist (no outside), lost_time is None."""
    laps = [
        _lap(2, lap_time=101.0, compound="Medium", track_temp=25.0, tyre_age_laps=2),
        _lap(3, lap_time=102.0, compound="Medium", track_temp=25.0, tyre_age_laps=3),
    ]
    types = ["hotlap", "hotlap"]
    result = estimate_tyre_temp_window(laps, types)
    assert result["best_in_window"] == 101.0
    assert result["best_outside_window"] is None
    assert result["window_lost_time"] is None


# ──────────────────────────────────────────────────────────────────────────────
# Per-lap classification details
# ──────────────────────────────────────────────────────────────────────────────


def test_laps_classified_keys():
    """Each classified lap entry has the expected keys."""
    laps = [_lap(i, compound="Medium", track_temp=25.0) for i in range(1, 4)]
    types = ["outlap", "hotlap", "hotlap"]
    result = estimate_tyre_temp_window(laps, types)
    for entry in result["laps_classified"]:
        assert "lap_number" in entry
        assert "role" in entry
        assert "tyre_state" in entry
        assert "lap_time" in entry


def test_laps_classified_states_medium():
    """Medium at 25°C: lap 1=cold, laps 2-3=in_window, 4+=degraded."""
    laps = [_lap(i, compound="Medium", track_temp=25.0) for i in range(1, 6)]
    result = estimate_tyre_temp_window(laps, _default_types(len(laps)))
    states = [e["tyre_state"] for e in result["laps_classified"]]
    assert states == [
        TYRE_COLD,
        TYRE_IN_WINDOW,
        TYRE_IN_WINDOW,
        TYRE_DEGRADED,
        TYRE_DEGRADED,
    ]
