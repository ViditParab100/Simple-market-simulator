"""
Tests for mood modifier functions and MoodState.
"""
import pytest
from market.models import Trade
from agents.hybrid.activation import ArchetypeTag
from agents.hybrid.mood import (
    MoodState,
    streak_modifier,
    volatility_modifier,
    cash_pressure_modifier,
    contagion_modifier,
    compute_mood_deltas,
)


def trade(buyer: str, seller: str, price: float = 20.0, qty: int = 5, tick: int = 1) -> Trade:
    return Trade(buyer_id=buyer, seller_id=seller, price=price, quantity=qty, tick=tick)


# ── MoodState.record_trade ─────────────────────────────────────────────────────

def test_record_trade_stores_trade():
    mood = MoodState()
    t = trade("alice", "bob")
    mood.record_trade(t, "alice")
    assert len(mood.recent_trades) == 1

def test_record_trade_caps_at_10():
    mood = MoodState()
    for i in range(15):
        mood.record_trade(trade("alice", "bob", tick=i), "alice")
    assert len(mood.recent_trades) == 10


# ── streak_modifier ────────────────────────────────────────────────────────────

def test_winning_streak_boosts_speculator():
    mood = MoodState()
    # Alice bought at $18 when market is now $20 -> profitable buys
    for i in range(3):
        mood.record_trade(trade("alice", "bob", price=18.0, tick=i), "alice")
    deltas = streak_modifier(mood, "alice", last_price=20.0)
    assert deltas.get(ArchetypeTag.SPECULATOR, 0.0) > 0.0

def test_winning_streak_suppresses_panic():
    mood = MoodState()
    for i in range(3):
        mood.record_trade(trade("alice", "bob", price=18.0, tick=i), "alice")
    deltas = streak_modifier(mood, "alice", last_price=20.0)
    assert deltas.get(ArchetypeTag.PANIC, 0.0) < 0.0

def test_losing_streak_boosts_panic():
    mood = MoodState()
    # Alice bought at $22 when market is now $20 -> losing buys
    for i in range(3):
        mood.record_trade(trade("alice", "bob", price=22.0, tick=i), "alice")
    deltas = streak_modifier(mood, "alice", last_price=20.0)
    assert deltas.get(ArchetypeTag.PANIC, 0.0) > 0.0

def test_losing_streak_suppresses_rational():
    mood = MoodState()
    for i in range(3):
        mood.record_trade(trade("alice", "bob", price=22.0, tick=i), "alice")
    deltas = streak_modifier(mood, "alice", last_price=20.0)
    assert deltas.get(ArchetypeTag.RATIONAL, 0.0) < 0.0

def test_no_trades_no_streak():
    mood = MoodState()
    deltas = streak_modifier(mood, "alice", last_price=20.0)
    assert deltas == {}


# ── volatility_modifier ────────────────────────────────────────────────────────

def test_volatility_boosts_speculator_and_panic():
    volatile = [20.0, 22.5, 18.0, 23.0, 17.5]
    deltas = volatility_modifier(volatile)
    assert deltas.get(ArchetypeTag.SPECULATOR, 0.0) > 0.0
    assert deltas.get(ArchetypeTag.PANIC, 0.0) > 0.0

def test_volatility_suppresses_market_maker_and_rational():
    volatile = [20.0, 22.5, 18.0, 23.0, 17.5]
    deltas = volatility_modifier(volatile)
    assert deltas.get(ArchetypeTag.MARKET_MAKER, 0.0) < 0.0
    assert deltas.get(ArchetypeTag.RATIONAL, 0.0) < 0.0

def test_low_volatility_returns_small_deltas():
    flat = [20.0, 20.01, 20.02, 20.01, 20.0]
    deltas = volatility_modifier(flat)
    for v in deltas.values():
        assert abs(v) < 0.05

def test_volatility_empty_history():
    assert volatility_modifier([]) == {}

def test_volatility_short_history():
    assert volatility_modifier([20.0, 21.0]) == {}


# ── cash_pressure_modifier ─────────────────────────────────────────────────────

def test_cash_pressure_amplifies_panic_when_broke():
    deltas = cash_pressure_modifier(cash=5.0, cash_floor=50.0)
    assert deltas.get(ArchetypeTag.PANIC, 0.0) > 0.0

def test_cash_pressure_suppresses_hoarder_when_broke():
    deltas = cash_pressure_modifier(cash=5.0, cash_floor=50.0)
    assert deltas.get(ArchetypeTag.HOARDER, 0.0) < 0.0

def test_cash_pressure_no_effect_when_rich():
    deltas = cash_pressure_modifier(cash=10000.0, cash_floor=50.0)
    assert deltas == {}

def test_cash_pressure_returns_empty_at_threshold():
    deltas = cash_pressure_modifier(cash=150.0, cash_floor=50.0)
    assert deltas == {}


# ── contagion_modifier ─────────────────────────────────────────────────────────

def test_contagion_boosts_panic():
    deltas = contagion_modifier(pulse=0.20)
    assert deltas.get(ArchetypeTag.PANIC, 0.0) > 0.0

def test_contagion_zero_pulse_returns_empty():
    assert contagion_modifier(pulse=0.0) == {}

def test_contagion_capped_at_0_30():
    deltas = contagion_modifier(pulse=1.0)
    assert deltas.get(ArchetypeTag.PANIC, 0.0) <= 0.30


# ── compute_mood_deltas ────────────────────────────────────────────────────────

def test_compute_mood_deltas_returns_dict():
    mood = MoodState()
    deltas = compute_mood_deltas(mood, "alice", cash=500.0,
                                 price_history=[20.0] * 5, last_price=20.0)
    assert isinstance(deltas, dict)

def test_compute_mood_deltas_aggregates_sources():
    mood = MoodState()
    mood.contagion_pulse = 0.20
    # With contagion active, Panic should be boosted
    deltas = compute_mood_deltas(mood, "alice", cash=500.0,
                                 price_history=[20.0] * 5, last_price=20.0)
    assert deltas.get(ArchetypeTag.PANIC, 0.0) > 0.0

def test_compute_mood_deltas_all_values_finite():
    mood = MoodState()
    for i in range(3):
        mood.record_trade(trade("alice", "bob", price=18.0, tick=i), "alice")
    mood.contagion_pulse = 0.15
    deltas = compute_mood_deltas(mood, "alice", cash=30.0,
                                 price_history=[20.0, 22.0, 18.0, 21.0, 19.0],
                                 last_price=19.0)
    for v in deltas.values():
        assert -1.0 <= v <= 1.0
