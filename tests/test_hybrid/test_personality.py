"""
Tests for PersonalityProfile: weight normalisation, contest outcome,
and thought-line generation.
"""
import pytest
from market.models import MarketState
from agents.hybrid.activation import ArchetypeTag
from agents.hybrid.mood import MoodState
from agents.hybrid.personality import PersonalityProfile, ContestResult


def state(
    last_price: float = 20.0,
    price_history: list[float] | None = None,
    bid_depth: int = 50,
    ask_depth: int = 50,
) -> MarketState:
    ph = price_history or []
    return MarketState(
        tick=1, last_price=last_price,
        best_bid=last_price - 0.5, best_ask=last_price + 0.5,
        bid_depth=bid_depth, ask_depth=ask_depth,
        price_history=ph,
    )

def downtrend_state() -> MarketState:
    return state(last_price=16.0, price_history=[20.0, 19.0, 18.0, 17.0, 16.0])

def uptrend_state() -> MarketState:
    return state(last_price=22.0, price_history=[18.0, 19.0, 20.0, 21.0, 22.0])


# ── PersonalityProfile construction ───────────────────────────────────────────

def test_weights_normalised_to_one():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:   3,
        ArchetypeTag.SPECULATOR: 1,
    })
    total = sum(profile.base_weights.values())
    assert abs(total - 1.0) < 1e-9

def test_empty_profile_raises():
    with pytest.raises(ValueError):
        PersonalityProfile({})

def test_label_lists_archetypes():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:   0.5,
        ArchetypeTag.SPECULATOR: 0.5,
    })
    label = profile.label()
    assert "Rational" in label
    assert "Speculator" in label


# ── run_contest ────────────────────────────────────────────────────────────────

def test_run_contest_returns_contest_result():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:   0.6,
        ArchetypeTag.SPECULATOR: 0.4,
    })
    result = profile.run_contest(state(), inventory=20, cash=500.0,
                                 mood=MoodState(), agent_id="test")
    assert isinstance(result, ContestResult)

def test_contest_winner_is_in_profile():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:   0.6,
        ArchetypeTag.PANIC:      0.4,
    })
    result = profile.run_contest(state(), 20, 500.0, MoodState(), "test")
    assert result.winner in {ArchetypeTag.RATIONAL, ArchetypeTag.PANIC}

def test_contest_scores_keys_match_profile():
    profile = PersonalityProfile({
        ArchetypeTag.SPECULATOR: 0.5,
        ArchetypeTag.HOARDER:    0.5,
    })
    result = profile.run_contest(state(), 20, 500.0, MoodState(), "test")
    assert set(result.scores.keys()) == {ArchetypeTag.SPECULATOR, ArchetypeTag.HOARDER}

def test_all_scores_in_range():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:     0.40,
        ArchetypeTag.SPECULATOR:   0.35,
        ArchetypeTag.PANIC:        0.25,
    })
    result = profile.run_contest(downtrend_state(), 30, 300.0, MoodState(), "test")
    for score in result.scores.values():
        assert 0.0 <= score <= 1.0

def test_winner_has_highest_score():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:   0.5,
        ArchetypeTag.SPECULATOR: 0.5,
    })
    result = profile.run_contest(uptrend_state(), 5, 800.0, MoodState(), "test")
    assert result.scores[result.winner] == max(result.scores.values())

def test_margin_is_non_negative():
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL:   0.5,
        ArchetypeTag.SPECULATOR: 0.5,
    })
    result = profile.run_contest(state(), 20, 500.0, MoodState(), "test")
    assert result.margin >= 0.0

def test_panic_dominant_in_downtrend_for_panic_heavy_profile():
    profile = PersonalityProfile({
        ArchetypeTag.PANIC:      0.70,
        ArchetypeTag.RATIONAL:   0.30,
    })
    result = profile.run_contest(downtrend_state(), inventory=30, cash=50.0,
                                 mood=MoodState(), agent_id="test")
    assert result.winner == ArchetypeTag.PANIC

def test_speculator_dominant_in_uptrend_for_spec_heavy_profile():
    profile = PersonalityProfile({
        ArchetypeTag.SPECULATOR: 0.80,
        ArchetypeTag.RATIONAL:   0.20,
    })
    result = profile.run_contest(uptrend_state(), inventory=5, cash=800.0,
                                 mood=MoodState(), agent_id="test")
    assert result.winner == ArchetypeTag.SPECULATOR


# ── ContestResult.thought_lines ───────────────────────────────────────────────

def test_thought_lines_returns_list_of_strings():
    profile = PersonalityProfile({ArchetypeTag.RATIONAL: 0.6, ArchetypeTag.PANIC: 0.4})
    result  = profile.run_contest(state(), 20, 500.0, MoodState(), "test")
    lines   = result.thought_lines()
    assert isinstance(lines, list)
    assert all(isinstance(l, str) for l in lines)

def test_thought_lines_contain_winner_name():
    profile = PersonalityProfile({
        ArchetypeTag.PANIC:    0.80,
        ArchetypeTag.RATIONAL: 0.20,
    })
    result = profile.run_contest(downtrend_state(), 30, 50.0, MoodState(), "test")
    combined = " ".join(result.thought_lines())
    assert result.winner.value in combined

def test_thought_lines_contain_all_archetype_names():
    profile = PersonalityProfile({
        ArchetypeTag.SPECULATOR: 0.5,
        ArchetypeTag.HOARDER:    0.5,
    })
    result = profile.run_contest(state(), 20, 500.0, MoodState(), "test")
    combined = " ".join(result.thought_lines())
    assert "Speculator" in combined
    assert "Hoarder" in combined
