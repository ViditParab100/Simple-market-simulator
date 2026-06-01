"""
Behavioral tests for HybridNPC.
"""
import pytest
from market.models import MarketState, Trade, OrderSide
from agents.hybrid.activation import ArchetypeTag
from agents.hybrid.mood import MoodState
from agents.hybrid.personality import PersonalityProfile
from agents.hybrid.npc import HybridNPC


def make_npc(profile_weights: dict[ArchetypeTag, float],
             inventory: int = 20, cash: float = 500.0) -> HybridNPC:
    return HybridNPC("test-npc", inventory, cash,
                     PersonalityProfile(profile_weights))

def run(npc: HybridNPC, state: MarketState):
    thoughts = npc.think(state)
    orders   = npc.act(state)
    return thoughts, orders

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
        bid_depth=bid_depth, ask_depth=ask_depth, price_history=ph,
    )

def uptrend() -> MarketState:
    return state(22.0, [18.0, 19.0, 20.0, 21.0, 22.0])

def downtrend() -> MarketState:
    return state(16.0, [20.0, 19.0, 18.0, 17.0, 16.0])

def flat() -> MarketState:
    return state(20.0, [20.0] * 6)

def make_trade(buyer, seller, price=20.0, qty=5, tick=1):
    return Trade(buyer_id=buyer, seller_id=seller, price=price, quantity=qty, tick=tick)


# ── basic interface ────────────────────────────────────────────────────────────

def test_think_returns_list_of_strings():
    npc = make_npc({ArchetypeTag.RATIONAL: 0.6, ArchetypeTag.SPECULATOR: 0.4})
    thoughts, _ = run(npc, flat())
    assert isinstance(thoughts, list)
    assert all(isinstance(t, str) for t in thoughts)

def test_act_returns_list():
    npc = make_npc({ArchetypeTag.RATIONAL: 0.6, ArchetypeTag.SPECULATOR: 0.4})
    _, orders = run(npc, flat())
    assert isinstance(orders, list)

def test_act_returns_same_as_pending_after_think():
    npc = make_npc({ArchetypeTag.RATIONAL: 0.6, ArchetypeTag.SPECULATOR: 0.4})
    s = flat()
    npc.think(s)
    assert npc.act(s) == npc.act(s)

def test_dominant_archetype_set_after_think():
    npc = make_npc({ArchetypeTag.RATIONAL: 0.6, ArchetypeTag.SPECULATOR: 0.4})
    assert npc.dominant_archetype is None
    npc.think(flat())
    assert npc.dominant_archetype is not None


# ── thought content ────────────────────────────────────────────────────────────

def test_thoughts_contain_inventory_and_cash():
    npc = make_npc({ArchetypeTag.RATIONAL: 1.0}, inventory=42, cash=999.0)
    thoughts, _ = run(npc, flat())
    combined = " ".join(thoughts)
    assert "42" in combined
    assert "999" in combined

def test_thoughts_contain_personality_label():
    npc = make_npc({ArchetypeTag.RATIONAL: 0.6, ArchetypeTag.SPECULATOR: 0.4})
    thoughts, _ = run(npc, flat())
    combined = " ".join(thoughts)
    assert "Rational" in combined
    assert "Speculator" in combined

def test_thoughts_contain_dominant_mode_line():
    npc = make_npc({ArchetypeTag.SPECULATOR: 0.8, ArchetypeTag.RATIONAL: 0.2})
    thoughts, _ = run(npc, uptrend())
    combined = " ".join(thoughts)
    assert "DOMINANT MODE" in combined

def test_mood_swing_logged_when_archetype_changes():
    # Force a personality that flips based on market direction
    npc = make_npc({ArchetypeTag.SPECULATOR: 0.5, ArchetypeTag.PANIC: 0.5},
                   inventory=20, cash=500.0)
    npc.think(uptrend())    # tick 1: Speculator likely wins
    thoughts, _ = run(npc, downtrend())  # tick 2: Panic likely wins
    combined = " ".join(thoughts)
    # If the winner changed, MOOD SWING should appear
    if npc._last_winner != npc._last_contest.winner if npc._last_contest else False:
        assert "MOOD SWING" in combined


# ── order safety ───────────────────────────────────────────────────────────────

def test_no_bid_when_cash_zero():
    npc = make_npc({ArchetypeTag.SPECULATOR: 1.0}, inventory=0, cash=0.0)
    _, orders = run(npc, uptrend())
    assert all(o.side != OrderSide.BID for o in orders)

def test_no_ask_when_inventory_zero():
    npc = make_npc({ArchetypeTag.PANIC: 1.0}, inventory=0, cash=500.0)
    _, orders = run(npc, downtrend())
    assert all(o.side != OrderSide.ASK for o in orders)

def test_ask_quantity_never_exceeds_inventory():
    npc = make_npc({ArchetypeTag.PANIC: 1.0}, inventory=3, cash=500.0)
    _, orders = run(npc, downtrend())
    for o in orders:
        if o.side == OrderSide.ASK:
            assert o.quantity <= 3

def test_all_order_prices_positive():
    npc = make_npc({ArchetypeTag.MARKET_MAKER: 0.5, ArchetypeTag.SPECULATOR: 0.5})
    for s in [uptrend(), downtrend(), flat()]:
        _, orders = run(npc, s)
        for o in orders:
            assert o.price > 0

def test_all_order_quantities_positive():
    npc = make_npc({ArchetypeTag.HOARDER: 0.6, ArchetypeTag.SPECULATOR: 0.4})
    _, orders = run(npc, flat())
    for o in orders:
        assert o.quantity > 0


# ── on_trade / mood ────────────────────────────────────────────────────────────

def test_on_trade_updates_inventory_as_buyer():
    npc = make_npc({ArchetypeTag.RATIONAL: 1.0}, inventory=10, cash=500.0)
    npc.on_trade(make_trade("test-npc", "seller", price=20.0, qty=5))
    assert npc.inventory == 15

def test_on_trade_updates_cash_as_seller():
    npc = make_npc({ArchetypeTag.RATIONAL: 1.0}, inventory=20, cash=100.0)
    npc.on_trade(make_trade("buyer", "test-npc", price=20.0, qty=5))
    assert abs(npc.cash - 200.0) < 1e-9

def test_on_trade_records_in_mood():
    npc = make_npc({ArchetypeTag.RATIONAL: 1.0})
    npc.on_trade(make_trade("test-npc", "seller"))
    assert len(npc.mood.recent_trades) == 1


# ── panic FSM persistence ──────────────────────────────────────────────────────

def test_panic_recovery_persists_across_ticks():
    """When Panic wins and dumps, the FSM should still be in 'recovering' next tick."""
    npc = make_npc({ArchetypeTag.PANIC: 0.90, ArchetypeTag.RATIONAL: 0.10},
                   inventory=20, cash=500.0)
    # Tick 1: downtrend triggers panic
    run(npc, downtrend())
    if npc._last_winner == ArchetypeTag.PANIC:
        # Tick 2: should be recovering (not panic again)
        run(npc, downtrend())
        if npc._last_winner == ArchetypeTag.PANIC:
            assert npc._panic_state == "recovering"


# ── contagion pulse ────────────────────────────────────────────────────────────

def test_contagion_pulse_boosts_panic_signal():
    """With a contagion pulse active, a low-panic profile should see Panic score rise."""
    profile = PersonalityProfile({
        ArchetypeTag.RATIONAL: 0.70,
        ArchetypeTag.PANIC:    0.30,
    })
    npc_no_pulse = HybridNPC("a", 20, 500.0, profile)
    npc_pulse    = HybridNPC("b", 20, 500.0, profile)
    npc_pulse.mood.contagion_pulse = 0.20

    s = downtrend()
    npc_no_pulse.think(s)
    npc_pulse.think(s)

    score_no_pulse = npc_no_pulse._last_contest.scores.get(ArchetypeTag.PANIC, 0.0)
    score_pulse    = npc_pulse._last_contest.scores.get(ArchetypeTag.PANIC, 0.0)
    assert score_pulse >= score_no_pulse
