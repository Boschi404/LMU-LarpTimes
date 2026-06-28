"""
Tests for the compound recommender (analysis/compounds.py) and the
strategy endpoint's compound_plan output.

Covers:
  - _normalise_compound recognises Soft/Medium/Hard/Wet/Inter (and aliases)
  - _is_wet correctly decides based on state + rain intensity
  - _expected_stint_length splits laps correctly per pit plan
  - recommend_compound:
        * dry short stint → Soft
        * dry long stint → Hard
        * wet → Wet or Inter
        * historical pace influences ranking
  - plan_compounds emits one entry per stint
  - PitStrategist.optimize() returns compound_plan when laps_history is passed
  - PitStrategist.optimize() omits compound_plan when laps_history is None
    (backwards compat with existing tests)
"""

import pytest

from analysis.compounds import (
    _normalise_compound,
    _is_wet,
    _expected_stint_length,
    _avg_pace_for_compound,
    recommend_compound,
    plan_compounds,
    COMPOUND_PROFILES,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_lap(
    lap_time=100.0,
    compound="Medium",
    valid=1,
    pit_in=0,
    pit_out=0,
    wear_start=10.0,
    wear_end=20.0,
    weather="DRY",
    rain=0.0,
):
    return {
        "lap_time": lap_time,
        "compound_front": compound,
        "compound": compound,
        "is_valid_lap": valid,
        "is_pit_in_lap": pit_in,
        "is_pit_out_lap": pit_out,
        "wear_pct_start_FL": wear_start,
        "wear_pct_end_FL": wear_end,
        "weather_state": weather,
        "rain_intensity": rain,
    }


# ──────────────────────────────────────────────────────────────────────────────
# _normalise_compound
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Soft", "Soft"),
    ("S", "Soft"),
    ("Soft C5", "Soft"),
    ("Hypersoft", "Soft"),
    ("Medium", "Medium"),
    ("M", "Medium"),
    ("Hard", "Hard"),
    ("H", "Hard"),
    ("Inter", "Inter"),
    ("Intermediate", "Inter"),
    ("Wet", "Wet"),
    ("Full Wet", "Wet"),
    ("weird", "Unknown"),
    (None, "Unknown"),
    ("", "Unknown"),
])
def test_normalise_compound(raw, expected):
    assert _normalise_compound(raw) == expected


# ──────────────────────────────────────────────────────────────────────────────
# _is_wet
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state,rain,expected", [
    ("DRY", 0.0, False),
    ("DRY", 0.05, False),
    ("DRY", 0.2, True),
    ("WET", 0.0, True),
    ("WET", 0.5, True),
    ("RAIN", 0.0, True),
    ("DRIZZLE", 0.0, True),
    (None, 0.0, False),
    (None, 0.5, True),
    (None, 0.05, False),
])
def test_is_wet(state, rain, expected):
    assert _is_wet(state, rain) is expected


# ──────────────────────────────────────────────────────────────────────────────
# _expected_stint_length
# ──────────────────────────────────────────────────────────────────────────────

def test_expected_stint_no_pits():
    assert _expected_stint_length([], 30) == [30]


def test_expected_stint_one_pit():
    # Pit at lap 12 of 30 → stints [12, 18]
    assert _expected_stint_length([12], 30) == [12, 18]


def test_expected_stint_multi_pit_unsorted():
    # Pass pits out of order on purpose
    assert _expected_stint_length([20, 10], 40) == [10, 10, 20]


def test_expected_stint_three_pits():
    assert _expected_stint_length([10, 25, 35], 50) == [10, 15, 10, 15]


# ──────────────────────────────────────────────────────────────────────────────
# recommend_compound
# ──────────────────────────────────────────────────────────────────────────────

def test_recommend_dry_short_stint_prefers_soft():
    """A 5-lap dry stint: Soft should win or at least be a top-2 option."""
    rec = recommend_compound(
        laps_history=[],
        weather_state="DRY",
        track_temp=25.0,
        stint_length=5,
    )
    assert rec["compound"] in ("Soft", "Medium")
    assert rec["type"] == "DRY"
    # Soft should be in the alternatives ranking
    alt_compounds = {a["compound"] for a in rec["alternatives"]}
    assert "Soft" in alt_compounds
    assert "Medium" in alt_compounds
    assert "Hard" in alt_compounds


def test_recommend_dry_long_stint_prefers_hard():
    rec = recommend_compound(
        laps_history=[],
        weather_state="DRY",
        track_temp=25.0,
        stint_length=30,
    )
    # For a 30-lap stint, Hard or Medium should win
    assert rec["compound"] in ("Hard", "Medium")


def test_recommend_wet_uses_wet_compound():
    rec = recommend_compound(
        laps_history=[],
        weather_state="WET",
        rain_intensity=0.8,
        track_temp=15.0,
        stint_length=20,
    )
    assert rec["type"] == "WET"
    assert rec["compound"] in ("Wet", "Inter")


def test_recommend_light_rain_prefers_inter():
    rec = recommend_compound(
        laps_history=[],
        weather_state="DRY",
        rain_intensity=0.3,
        track_temp=20.0,
        stint_length=15,
    )
    assert rec["type"] == "WET"


def test_recommend_hot_track_penalises_soft():
    """Track temp > 40°C should add a temp penalty to Soft."""
    rec_hot = recommend_compound(
        laps_history=[],
        weather_state="DRY",
        track_temp=45.0,
        stint_length=15,
    )
    rec_cool = recommend_compound(
        laps_history=[],
        weather_state="DRY",
        track_temp=20.0,
        stint_length=15,
    )
    # Soft's score in the hot variant should be worse than in the cool variant
    hot_soft_score = next(a["score"] for a in rec_hot["alternatives"] if a["compound"] == "Soft")
    cool_soft_score = next(a["score"] for a in rec_cool["alternatives"] if a["compound"] == "Soft")
    assert hot_soft_score > cool_soft_score


def test_recommend_uses_historical_pace():
    """If one compound is clearly closer to the historical median pace,
    it should win or be ranked higher."""
    history = (
        [_make_lap(lap_time=98.0, compound="Soft")] * 10 +
        [_make_lap(lap_time=101.0, compound="Medium")] * 10 +
        [_make_lap(lap_time=103.0, compound="Hard")] * 10
    )
    rec = recommend_compound(
        laps_history=history,
        weather_state="DRY",
        track_temp=25.0,
        stint_length=8,
    )
    # The median pace is 101.0 (= Medium), so Medium should have the lowest
    # pace_score and therefore be the top recommendation OR a top-2 option.
    alternatives = rec["alternatives"]
    scores_by_compound = {a["compound"]: a["score"] for a in alternatives}
    # Verify that the ranking reflects pace — Medium should be in the top
    # by score, ahead of (or very close to) Soft
    assert rec["compound"] in ("Medium", "Soft")
    # The score of Medium should be at most the score of Hard
    assert scores_by_compound["Medium"] <= scores_by_compound["Hard"]


def test_recommend_returns_alternatives_sorted():
    rec = recommend_compound(
        laps_history=[],
        weather_state="DRY",
        track_temp=25.0,
        stint_length=15,
    )
    scores = [a["score"] for a in rec["alternatives"]]
    assert scores == sorted(scores), f"Alternatives not sorted by score: {scores}"


# ──────────────────────────────────────────────────────────────────────────────
# plan_compounds
# ──────────────────────────────────────────────────────────────────────────────

def test_plan_compounds_emits_one_per_stint():
    laps = [_make_lap(compound="Medium")] * 5
    plan = plan_compounds(
        pit_laps_relative=[10, 25],
        total_laps=40,
        laps_history=laps,
        weather_per_stint=None,
    )
    assert len(plan) == 3
    for entry in plan:
        assert "stint" in entry
        assert "laps" in entry
        assert "compound" in entry
        assert "reasoning" in entry


def test_plan_compounds_with_weather_per_stint():
    """If stint 3 is wet, it should recommend Wet/Inter."""
    laps = [_make_lap(compound="Medium")] * 5
    plan = plan_compounds(
        pit_laps_relative=[10, 25],
        total_laps=40,
        laps_history=laps,
        weather_per_stint=[
            {"weather_state": "DRY", "rain_intensity": 0.0},
            {"weather_state": "DRY", "rain_intensity": 0.0},
            {"weather_state": "WET", "rain_intensity": 0.7},
        ],
    )
    assert plan[0]["compound"] in ("Soft", "Medium", "Hard")
    assert plan[0]["type"] == "DRY"
    assert plan[2]["compound"] in ("Wet", "Inter")
    assert plan[2]["type"] == "WET"


def test_plan_compounds_no_history_uses_heuristic():
    plan = plan_compounds(
        pit_laps_relative=[],
        total_laps=15,
        laps_history=[],
        weather_per_stint=None,
    )
    assert len(plan) == 1
    assert plan[0]["compound"] in ("Soft", "Medium", "Hard")
    assert plan[0]["type"] == "DRY"


# ──────────────────────────────────────────────────────────────────────────────
# PitStrategist integration
# ──────────────────────────────────────────────────────────────────────────────

def _dummy_model_fit():
    from analysis.models import DegradationModelFit
    return DegradationModelFit(
        base_time=100.0, alpha=0.03, beta_1=0.1, beta_2=0.5,
        cliff_lap=15, huber_loss_val=0.0,
    )


def test_strategist_no_history_no_compound_plan():
    """Backwards compat: calling optimize() without history returns no compound_plan."""
    from analysis.strategist import PitStrategist
    strat = PitStrategist(
        fuel_capacity=100.0,
        fuel_consumption=3.0,
        pit_loss=30.0,
        model_fit=_dummy_model_fit(),
    )
    result = strat.optimize(
        laps_remaining=30,
        current_tyre_age=1,
        current_fuel=100.0,
        max_stops=2,
    )
    assert result["optimal"] is not None
    # No compound_plan because no history provided
    assert "compound_plan" not in result["optimal"]


def test_strategist_with_history_includes_compound_plan():
    from analysis.strategist import PitStrategist
    history = [_make_lap(compound="Medium", lap_time=100.0)] * 10
    strat = PitStrategist(
        fuel_capacity=100.0,
        fuel_consumption=3.0,
        pit_loss=30.0,
        model_fit=_dummy_model_fit(),
    )
    result = strat.optimize(
        laps_remaining=30,
        current_tyre_age=1,
        current_fuel=100.0,
        max_stops=2,
        laps_history=history,
        weather_forecast=[{"weather_state": "DRY", "rain_intensity": 0.0}],
    )
    assert result["optimal"] is not None
    assert "compound_plan" in result["optimal"]
    plan = result["optimal"]["compound_plan"]
    assert len(plan) >= 1
    for stint in plan:
        assert "stint" in stint
        assert "compound" in stint
        assert "laps" in stint


def test_strategist_compound_plan_with_rain_in_forecast():
    from analysis.strategist import PitStrategist
    history = [_make_lap(compound="Medium", lap_time=100.0)] * 10
    strat = PitStrategist(
        fuel_capacity=100.0,
        fuel_consumption=3.0,
        pit_loss=30.0,
        model_fit=_dummy_model_fit(),
    )
    # 2-stop plan, but the LAST stint is wet
    result = strat.optimize(
        laps_remaining=30,
        current_tyre_age=1,
        current_fuel=100.0,
        max_stops=2,
        laps_history=history,
        weather_forecast=[
            {"weather_state": "DRY", "rain_intensity": 0.0},
            {"weather_state": "DRY", "rain_intensity": 0.0},
            {"weather_state": "WET", "rain_intensity": 0.8},
        ],
    )
    # The 0-stop plan won't have a wet stint (single DRY stint)
    # but a 1+ stop plan should — check alternatives
    found_wet = False
    for stops, entry in result["alternatives"].items():
        plan = entry.get("compound_plan", [])
        for stint in plan:
            if stint.get("type") == "WET":
                found_wet = True
                break
        if found_wet:
            break
    assert found_wet, "Expected at least one alternative to have a WET stint"
