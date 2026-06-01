import pytest
from agents.random_agent import RandomAgent
from market.models import MarketState, OrderSide


def make_state(last_price: float = 20.0, bid_depth: int = 50, ask_depth: int = 50) -> MarketState:
    return MarketState(
        tick=1,
        last_price=last_price,
        best_bid=last_price - 0.5,
        best_ask=last_price + 0.5,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
    )

def run(agent: RandomAgent, state: MarketState):
    """Simulate one engine tick: think then act."""
    thoughts = agent.think(state)
    orders = agent.act(state)
    return thoughts, orders


# ── think ──────────────────────────────────────────────────────────────────────

def test_think_returns_list_of_strings():
    agent = RandomAgent("R-01", inventory=20, cash=400.0, seed=1)
    thoughts, _ = run(agent, make_state())
    assert isinstance(thoughts, list)
    assert all(isinstance(t, str) for t in thoughts)

def test_think_contains_inventory_info():
    agent = RandomAgent("R-01", inventory=20, cash=400.0, seed=1)
    thoughts, _ = run(agent, make_state())
    combined = " ".join(thoughts)
    assert "20" in combined   # inventory
    assert "400" in combined  # cash

def test_think_reports_chosen_action():
    agent = RandomAgent("R-01", inventory=20, cash=400.0, seed=1)
    thoughts, _ = run(agent, make_state())
    action_line = thoughts[-1].upper()
    assert any(word in action_line for word in ("BUY", "SELL", "HOLD"))


# ── act ────────────────────────────────────────────────────────────────────────

def test_act_returns_list():
    agent = RandomAgent("R-01", inventory=20, cash=400.0, seed=1)
    _, orders = run(agent, make_state())
    assert isinstance(orders, list)

def test_act_no_bid_when_cash_below_price():
    # Market price far exceeds cash — agent can never buy
    state = make_state(last_price=1000.0)
    for seed in range(20):
        agent = RandomAgent("R", inventory=10, cash=5.0, seed=seed)
        _, orders = run(agent, state)
        for o in orders:
            assert o.side != OrderSide.BID

def test_act_no_ask_when_inventory_zero():
    for seed in range(20):
        agent = RandomAgent("R", inventory=0, cash=1000.0, seed=seed)
        _, orders = run(agent, make_state())
        for o in orders:
            assert o.side != OrderSide.ASK

def test_act_ask_quantity_does_not_exceed_inventory():
    agent = RandomAgent("R", inventory=2, cash=1000.0, seed=7)
    for _ in range(10):
        _, orders = run(agent, make_state())
        for o in orders:
            if o.side == OrderSide.ASK:
                assert o.quantity <= 2

def test_act_order_quantity_positive():
    agent = RandomAgent("R-01", inventory=20, cash=400.0, seed=3)
    for _ in range(10):
        _, orders = run(agent, make_state())
        for o in orders:
            assert o.quantity > 0

def test_act_order_price_positive():
    agent = RandomAgent("R-01", inventory=20, cash=400.0, seed=3)
    for _ in range(10):
        _, orders = run(agent, make_state())
        for o in orders:
            assert o.price > 0


# ── think / act consistency ────────────────────────────────────────────────────

def test_thought_and_action_agree():
    """If think() says HOLD, act() must return no orders."""
    for seed in range(30):
        agent = RandomAgent("R", inventory=20, cash=400.0, seed=seed)
        state = make_state()
        thoughts, orders = run(agent, state)
        action_line = thoughts[-1].upper()
        if "HOLD" in action_line:
            assert orders == [], f"seed={seed}: thought HOLD but submitted {orders}"

def test_thought_buy_means_bid_submitted():
    """If think() says BUY, act() must submit a BID (not an ASK)."""
    for seed in range(50):
        agent = RandomAgent("R", inventory=20, cash=400.0, seed=seed)
        state = make_state()
        thoughts, orders = run(agent, state)
        if "BUY" in thoughts[-1].upper() and orders:
            assert all(o.side == OrderSide.BID for o in orders)

def test_thought_sell_means_ask_submitted():
    """If think() says SELL, act() must submit an ASK (not a BID)."""
    for seed in range(50):
        agent = RandomAgent("R", inventory=20, cash=400.0, seed=seed)
        state = make_state()
        thoughts, orders = run(agent, state)
        if "SELL" in thoughts[-1].upper() and orders:
            assert all(o.side == OrderSide.ASK for o in orders)


# ── determinism ────────────────────────────────────────────────────────────────

def test_same_seed_produces_same_result():
    state = make_state()
    a1 = RandomAgent("R", inventory=20, cash=400.0, seed=99)
    a2 = RandomAgent("R", inventory=20, cash=400.0, seed=99)
    assert run(a1, state) == run(a2, state)

def test_different_seeds_can_produce_different_results():
    state = make_state()
    results = set()
    for seed in range(10):
        agent = RandomAgent("R", inventory=20, cash=400.0, seed=seed)
        _, orders = run(agent, state)
        results.add(tuple((o.side, o.quantity) for o in orders))
    assert len(results) > 1, "Expected variation across seeds"
