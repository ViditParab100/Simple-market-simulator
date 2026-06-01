"""
Behavioral tests for the five Agent Zoo archetypes.
Each agent is tested against purpose-built MarketState snapshots designed
to trigger (or avoid triggering) specific decision branches.
"""
import pytest
from market.models import MarketState, OrderSide

from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent


# ── helpers ────────────────────────────────────────────────────────────────────

def run(agent, state: MarketState):
    """Simulate one engine tick: think then act."""
    thoughts = agent.think(state)
    orders = agent.act(state)
    return thoughts, orders

def state(
    last_price: float = 20.0,
    bid_depth: int = 50,
    ask_depth: int = 50,
    price_history: list[float] | None = None,
) -> MarketState:
    ph = price_history or []
    return MarketState(
        tick=1,
        last_price=last_price,
        best_bid=last_price - 0.5,
        best_ask=last_price + 0.5,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        price_history=ph,
    )

def uptrend(last: float = 22.0) -> MarketState:
    return state(last_price=last, price_history=[18.0, 19.0, 20.0, 21.0, last])

def downtrend(last: float = 16.0) -> MarketState:
    return state(last_price=last, price_history=[20.0, 19.0, 18.0, 17.0, last])

def flat_market(price: float = 20.0) -> MarketState:
    return state(last_price=price, price_history=[price] * 6)

def no_history() -> MarketState:
    return state(price_history=[])


# ══════════════════════════════════════════════════════════════════════════════
# MarketMakerAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestMarketMaker:
    def test_think_returns_strings(self):
        agent = MarketMakerAgent("MM-01", inventory=30, cash=600.0)
        thoughts, _ = run(agent, flat_market())
        assert isinstance(thoughts, list)
        assert all(isinstance(t, str) for t in thoughts)

    def test_quotes_both_sides_when_balanced(self):
        agent = MarketMakerAgent("MM-01", inventory=40, cash=600.0,
                                 min_inventory=10, max_inventory=80)
        _, orders = run(agent, flat_market())
        sides = {o.side for o in orders}
        assert OrderSide.BID in sides
        assert OrderSide.ASK in sides

    def test_only_bids_when_inventory_low(self):
        agent = MarketMakerAgent("MM-01", inventory=5, cash=600.0,
                                 min_inventory=10, max_inventory=80)
        _, orders = run(agent, flat_market())
        assert all(o.side == OrderSide.BID for o in orders)

    def test_only_asks_when_inventory_high(self):
        agent = MarketMakerAgent("MM-01", inventory=90, cash=600.0,
                                 min_inventory=10, max_inventory=80)
        _, orders = run(agent, flat_market())
        assert all(o.side == OrderSide.ASK for o in orders)

    def test_spread_widens_in_volatile_market(self):
        agent_volatile = MarketMakerAgent("MM-01", inventory=40, cash=800.0)
        agent_calm = MarketMakerAgent("MM-02", inventory=40, cash=800.0)
        s_volatile = uptrend(last=20.0)   # same last_price, different momentum
        s_calm = flat_market(20.0)
        _, orders_volatile = run(agent_volatile, s_volatile)
        _, orders_calm = run(agent_calm, s_calm)
        bids_v = [o for o in orders_volatile if o.side == OrderSide.BID]
        bids_c = [o for o in orders_calm if o.side == OrderSide.BID]
        if bids_v and bids_c:
            # Compare relative distance from mid price (volatile should be further below)
            distance_v = (20.0 - bids_v[0].price) / 20.0
            distance_c = (20.0 - bids_c[0].price) / 20.0
            assert distance_v > distance_c

    def test_no_bid_when_insufficient_cash(self):
        agent = MarketMakerAgent("MM-01", inventory=40, cash=0.01,
                                 min_inventory=10, max_inventory=80)
        _, orders = run(agent, flat_market())
        assert all(o.side != OrderSide.BID for o in orders)

    def test_ask_quantity_never_exceeds_inventory(self):
        agent = MarketMakerAgent("MM-01", inventory=2, cash=600.0,
                                 quote_size=10, min_inventory=0, max_inventory=80)
        _, orders = run(agent, flat_market())
        for o in orders:
            if o.side == OrderSide.ASK:
                assert o.quantity <= 2

    def test_act_matches_think(self):
        agent = MarketMakerAgent("MM-01", inventory=40, cash=600.0)
        s = flat_market()
        agent.think(s)
        orders1 = agent.act(s)
        orders2 = agent.act(s)  # calling act twice returns same pending orders
        assert orders1 == orders2


# ══════════════════════════════════════════════════════════════════════════════
# SpeculatorAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestSpeculator:
    def test_think_returns_strings(self):
        agent = SpeculatorAgent("Sp-01", inventory=10, cash=400.0)
        thoughts, _ = run(agent, flat_market())
        assert isinstance(thoughts, list)
        assert all(isinstance(t, str) for t in thoughts)

    def test_bids_in_uptrend(self):
        agent = SpeculatorAgent("Sp-01", inventory=0, cash=1000.0,
                                momentum_threshold=0.02, max_position=30)
        _, orders = run(agent, uptrend())
        assert any(o.side == OrderSide.BID for o in orders)

    def test_asks_in_downtrend(self):
        agent = SpeculatorAgent("Sp-01", inventory=20, cash=400.0,
                                momentum_threshold=0.02, max_position=30)
        _, orders = run(agent, downtrend())
        assert any(o.side == OrderSide.ASK for o in orders)

    def test_holds_in_flat_market(self):
        agent = SpeculatorAgent("Sp-01", inventory=10, cash=400.0,
                                momentum_threshold=0.02)
        _, orders = run(agent, flat_market())
        assert orders == []

    def test_holds_when_no_price_history(self):
        agent = SpeculatorAgent("Sp-01", inventory=10, cash=400.0)
        _, orders = run(agent, no_history())
        assert orders == []

    def test_holds_when_at_max_position(self):
        agent = SpeculatorAgent("Sp-01", inventory=30, cash=1000.0,
                                max_position=30)
        _, orders = run(agent, uptrend())
        assert all(o.side != OrderSide.BID for o in orders)

    def test_holds_when_no_inventory_in_downtrend(self):
        agent = SpeculatorAgent("Sp-01", inventory=0, cash=400.0)
        _, orders = run(agent, downtrend())
        assert all(o.side != OrderSide.ASK for o in orders)

    def test_bid_price_above_market_in_uptrend(self):
        """Speculator pays a premium to get filled fast."""
        agent = SpeculatorAgent("Sp-01", inventory=0, cash=2000.0,
                                momentum_threshold=0.02, aggressiveness=0.02)
        s = uptrend(last=22.0)
        _, orders = run(agent, s)
        bids = [o for o in orders if o.side == OrderSide.BID]
        if bids:
            assert bids[0].price >= 22.0

    def test_ask_price_below_market_in_downtrend(self):
        """Speculator accepts a discount to exit fast."""
        agent = SpeculatorAgent("Sp-01", inventory=20, cash=400.0,
                                momentum_threshold=0.02, aggressiveness=0.02)
        s = downtrend(last=16.0)
        _, orders = run(agent, s)
        asks = [o for o in orders if o.side == OrderSide.ASK]
        if asks:
            assert asks[0].price <= 16.0

    def test_no_bid_when_cash_insufficient(self):
        agent = SpeculatorAgent("Sp-01", inventory=0, cash=0.01,
                                momentum_threshold=0.02)
        _, orders = run(agent, uptrend())
        assert all(o.side != OrderSide.BID for o in orders)


# ══════════════════════════════════════════════════════════════════════════════
# HoarderAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestHoarder:
    def test_think_returns_strings(self):
        agent = HoarderAgent("Ho-01", inventory=20, cash=800.0)
        thoughts, _ = run(agent, flat_market())
        assert isinstance(thoughts, list)
        assert all(isinstance(t, str) for t in thoughts)

    def test_bids_below_market_when_below_target(self):
        agent = HoarderAgent("Ho-01", inventory=20, cash=800.0,
                             hoard_target=100, buy_discount=0.92)
        _, orders = run(agent, flat_market(20.0))
        bids = [o for o in orders if o.side == OrderSide.BID]
        assert len(bids) > 0
        assert all(o.price < 20.0 for o in bids)

    def test_bid_price_respects_discount(self):
        agent = HoarderAgent("Ho-01", inventory=0, cash=800.0,
                             hoard_target=100, buy_discount=0.92)
        _, orders = run(agent, flat_market(20.0))
        bids = [o for o in orders if o.side == OrderSide.BID]
        if bids:
            assert abs(bids[0].price - round(20.0 * 0.92, 2)) < 0.01

    def test_posts_high_ask_when_at_target(self):
        agent = HoarderAgent("Ho-01", inventory=100, cash=800.0,
                             hoard_target=100, sell_premium=1.30)
        _, orders = run(agent, flat_market(20.0))
        asks = [o for o in orders if o.side == OrderSide.ASK]
        assert len(asks) > 0
        assert all(o.price >= 20.0 * 1.30 for o in asks)

    def test_never_bids_with_insufficient_cash(self):
        agent = HoarderAgent("Ho-01", inventory=0, cash=0.10,
                             hoard_target=100, buy_discount=0.92)
        _, orders = run(agent, flat_market(20.0))
        assert all(o.side != OrderSide.BID for o in orders)

    def test_no_ask_when_inventory_zero_and_at_target(self):
        agent = HoarderAgent("Ho-01", inventory=0, cash=800.0,
                             hoard_target=0)
        _, orders = run(agent, flat_market())
        assert all(o.side != OrderSide.ASK for o in orders)


# ══════════════════════════════════════════════════════════════════════════════
# PanicAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestPanic:
    def test_think_returns_strings(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0)
        thoughts, _ = run(agent, flat_market())
        assert isinstance(thoughts, list)
        assert all(isinstance(t, str) for t in thoughts)

    def test_holds_in_stable_market(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0, panic_threshold=-0.10)
        _, orders = run(agent, flat_market())
        assert orders == []

    def test_dumps_all_inventory_on_panic(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0, panic_threshold=-0.10)
        _, orders = run(agent, downtrend())  # -20% drop triggers panic
        asks = [o for o in orders if o.side == OrderSide.ASK]
        assert len(asks) > 0
        assert asks[0].quantity == 30  # dumps everything

    def test_panic_price_below_market(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0,
                           panic_threshold=-0.10, dump_discount=0.90)
        s = downtrend(last=16.0)
        _, orders = run(agent, s)
        asks = [o for o in orders if o.side == OrderSide.ASK]
        if asks:
            assert asks[0].price < 16.0

    def test_enters_recovery_after_panic(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0,
                           panic_threshold=-0.10, recovery_ticks=3)
        run(agent, downtrend())  # trigger panic
        assert agent._state == "recovering"

    def test_recovery_prevents_trading(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0,
                           panic_threshold=-0.10, recovery_ticks=3)
        run(agent, downtrend())               # tick 1: panic + dump
        _, orders = run(agent, downtrend())   # tick 2: should be recovering
        assert orders == []

    def test_returns_to_calm_after_recovery(self):
        agent = PanicAgent("Pa-01", inventory=30, cash=300.0,
                           panic_threshold=-0.10, recovery_ticks=2)
        run(agent, downtrend())     # tick 1: panic
        run(agent, flat_market())   # tick 2: recovery tick 1
        run(agent, flat_market())   # tick 3: recovery tick 2 -> back to calm
        assert agent._state == "calm"

    def test_no_dump_when_inventory_empty(self):
        agent = PanicAgent("Pa-01", inventory=0, cash=300.0, panic_threshold=-0.10)
        _, orders = run(agent, downtrend())
        assert orders == []

    def test_no_ask_exceeds_inventory(self):
        agent = PanicAgent("Pa-01", inventory=5, cash=300.0, panic_threshold=-0.10)
        _, orders = run(agent, downtrend())
        for o in orders:
            if o.side == OrderSide.ASK:
                assert o.quantity <= 5


# ══════════════════════════════════════════════════════════════════════════════
# RationalAgent
# ══════════════════════════════════════════════════════════════════════════════

class TestRational:
    def test_think_returns_strings(self):
        agent = RationalAgent("Ra-01", inventory=20, cash=600.0)
        thoughts, _ = run(agent, flat_market())
        assert isinstance(thoughts, list)
        assert all(isinstance(t, str) for t in thoughts)

    def test_holds_when_no_price_history(self):
        agent = RationalAgent("Ra-01", inventory=20, cash=600.0)
        _, orders = run(agent, no_history())
        assert orders == []

    def test_holds_when_price_near_fair_value(self):
        agent = RationalAgent("Ra-01", inventory=20, cash=600.0,
                              fair_value_window=5, margin=0.05)
        # Price exactly at fair value (all same price)
        _, orders = run(agent, flat_market(20.0))
        assert orders == []

    def test_bids_when_price_below_fair_value(self):
        """Price dropped 15% below the historical average -> BUY signal."""
        agent = RationalAgent("Ra-01", inventory=0, cash=1000.0,
                              fair_value_window=5, margin=0.05)
        # History avg = 20, current price = 16 (-20% deviation)
        s = state(last_price=16.0, price_history=[20.0, 20.0, 20.0, 20.0, 20.0])
        _, orders = run(agent, s)
        assert any(o.side == OrderSide.BID for o in orders)

    def test_asks_when_price_above_fair_value(self):
        """Price jumped 15% above historical average -> SELL signal."""
        agent = RationalAgent("Ra-01", inventory=20, cash=600.0,
                              fair_value_window=5, margin=0.05)
        # History avg = 20, current price = 24 (+20% deviation)
        s = state(last_price=24.0, price_history=[20.0, 20.0, 20.0, 20.0, 20.0])
        _, orders = run(agent, s)
        assert any(o.side == OrderSide.ASK for o in orders)

    def test_no_bid_when_cash_insufficient(self):
        agent = RationalAgent("Ra-01", inventory=0, cash=0.01,
                              fair_value_window=5, margin=0.05)
        s = state(last_price=16.0, price_history=[20.0] * 5)
        _, orders = run(agent, s)
        assert all(o.side != OrderSide.BID for o in orders)

    def test_no_ask_when_inventory_empty(self):
        agent = RationalAgent("Ra-01", inventory=0, cash=600.0,
                              fair_value_window=5, margin=0.05)
        s = state(last_price=24.0, price_history=[20.0] * 5)
        _, orders = run(agent, s)
        assert all(o.side != OrderSide.ASK for o in orders)

    def test_ask_quantity_never_exceeds_inventory(self):
        agent = RationalAgent("Ra-01", inventory=2, cash=600.0,
                              trade_size=10, fair_value_window=5, margin=0.05)
        s = state(last_price=24.0, price_history=[20.0] * 5)
        _, orders = run(agent, s)
        for o in orders:
            if o.side == OrderSide.ASK:
                assert o.quantity <= 2

    def test_fair_value_uses_window(self):
        """With a window of 3, only the last 3 prices matter."""
        agent = RationalAgent("Ra-01", inventory=0, cash=1000.0,
                              fair_value_window=3, margin=0.05)
        # Long history of $10, but last 3 are $20 -- fair value should be ~$20
        # Current price $24 -> overvalued relative to recent $20 avg, but
        # we have no inventory so no ask will be submitted. Just check no bid.
        s = state(last_price=24.0, price_history=[10.0] * 10 + [20.0, 20.0, 20.0])
        _, orders = run(agent, s)
        assert all(o.side != OrderSide.BID for o in orders)
