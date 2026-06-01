import pytest
from market.models import MarketState, Order, Trade, OrderSide


def make_state(**kwargs):
    defaults = dict(tick=1, last_price=20.0, best_bid=19.5, best_ask=20.5, bid_depth=50, ask_depth=50)
    defaults.update(kwargs)
    return MarketState(**defaults)


# ── scarcity_index ─────────────────────────────────────────────────────────────

def test_scarcity_equal_sides():
    assert make_state(bid_depth=50, ask_depth=50).scarcity_index == 0.5

def test_scarcity_all_demand():
    # Only buyers, no supply → scarcity_index == 1.0
    assert make_state(bid_depth=100, ask_depth=0).scarcity_index == 1.0

def test_scarcity_all_supply():
    # Only sellers, no demand → scarcity_index == 0.0
    assert make_state(bid_depth=0, ask_depth=100).scarcity_index == 0.0

def test_scarcity_zero_depth_returns_neutral():
    assert make_state(bid_depth=0, ask_depth=0).scarcity_index == 0.5

def test_scarcity_partial():
    state = make_state(bid_depth=30, ask_depth=70)
    assert abs(state.scarcity_index - 0.3) < 1e-9


# ── price_momentum ─────────────────────────────────────────────────────────────

def test_momentum_no_history():
    assert make_state(price_history=[]).price_momentum == 0.0

def test_momentum_single_price():
    assert make_state(price_history=[20.0]).price_momentum == 0.0

def test_momentum_rising():
    state = make_state(price_history=[20.0, 20.5, 21.0, 21.5, 22.0])
    assert state.price_momentum > 0

def test_momentum_falling():
    state = make_state(price_history=[22.0, 21.5, 21.0, 20.5, 20.0])
    assert state.price_momentum < 0

def test_momentum_flat():
    state = make_state(price_history=[20.0, 20.0, 20.0])
    assert state.price_momentum == 0.0

def test_momentum_uses_last_5_ticks():
    # Long history — only the last 5 matter
    history = [10.0] * 20 + [20.0, 20.5, 21.0, 21.5, 22.0]
    state = make_state(price_history=history)
    assert state.price_momentum > 0


# ── Order / Trade dataclasses ──────────────────────────────────────────────────

def test_order_fields():
    o = Order(agent_id="A", side=OrderSide.BID, price=19.5, quantity=10, tick=3)
    assert o.agent_id == "A"
    assert o.side == OrderSide.BID
    assert o.price == 19.5
    assert o.quantity == 10
    assert o.tick == 3

def test_trade_fields():
    t = Trade(buyer_id="B", seller_id="S", price=20.0, quantity=5, tick=2)
    assert t.buyer_id == "B"
    assert t.seller_id == "S"
    assert t.price == 20.0
    assert t.quantity == 5
    assert t.tick == 2
