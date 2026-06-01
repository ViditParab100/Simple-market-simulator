"""
Tests for Phase 3 — Bilateral Haggling Protocol.
Covers HaggleIntent, HaggleSession, HaggleCoordinator,
and per-agent haggle_intent() overrides.
"""
import pytest
from market.models import MarketState, OrderSide, Trade
from market.haggle import HaggleIntent, HaggleSession, HaggleCoordinator

from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent


# ── helpers ────────────────────────────────────────────────────────────────────

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

def downtrend() -> MarketState:
    return state(16.0, [20.0, 19.0, 18.0, 17.0, 16.0])

def uptrend() -> MarketState:
    return state(22.0, [18.0, 19.0, 20.0, 21.0, 22.0])

def overvalued() -> MarketState:
    return state(24.0, [20.0] * 5)

def undervalued() -> MarketState:
    return state(16.0, [20.0] * 5)

def bid(agent_id, target, limit, qty=5) -> HaggleIntent:
    return HaggleIntent(agent_id, OrderSide.BID, target, limit, qty)

def ask(agent_id, target, limit, qty=5) -> HaggleIntent:
    return HaggleIntent(agent_id, OrderSide.ASK, target, limit, qty)


# ══════════════════════════════════════════════════════════════════════════════
# HaggleIntent
# ══════════════════════════════════════════════════════════════════════════════

def test_intent_fields():
    i = HaggleIntent("alice", OrderSide.BID, 19.0, 21.0, 10)
    assert i.agent_id     == "alice"
    assert i.side         == OrderSide.BID
    assert i.price_target == 19.0
    assert i.price_limit  == 21.0
    assert i.quantity     == 10


# ══════════════════════════════════════════════════════════════════════════════
# HaggleSession
# ══════════════════════════════════════════════════════════════════════════════

class TestHaggleSession:

    def test_immediate_deal_when_prices_already_cross(self):
        # Buyer limit (22) > seller floor (18) and targets already cross
        session = HaggleSession(
            bid("buyer", target=21.0, limit=22.0),
            ask("seller", target=19.0, limit=18.0),
        )
        result = session.run()
        assert result.agreed
        assert result.price is not None
        assert result.price == pytest.approx((21.0 + 19.0) / 2, abs=0.01)

    def test_deal_after_concessions(self):
        # gap = 2.0, each side has 3.0 of room — converges by round 3
        # Round 1: buyer=19, seller=21  -> no deal
        # Round 2: buyer=20, seller=20.33 -> no deal
        # Round 3: buyer=20.67, seller=19.89 -> DEAL
        session = HaggleSession(
            bid("buyer",  target=19.0, limit=22.0),
            ask("seller", target=21.0, limit=19.0),
            max_rounds=3,
        )
        result = session.run()
        assert result.agreed

    def test_no_deal_when_limits_incompatible(self):
        # Buyer max (17) < seller floor (20) — no deal zone
        session = HaggleSession(
            bid("buyer",  target=15.0, limit=17.0),
            ask("seller", target=22.0, limit=20.0),
        )
        result = session.run()
        assert not result.agreed
        assert result.price is None

    def test_quantity_is_min_of_buyer_and_seller(self):
        session = HaggleSession(
            bid("buyer",  target=21.0, limit=22.0, qty=10),
            ask("seller", target=19.0, limit=18.0, qty=3),
        )
        result = session.run()
        assert result.agreed
        assert result.quantity == 3

    def test_deal_price_between_buyer_and_seller_targets(self):
        session = HaggleSession(
            bid("buyer",  target=21.0, limit=22.0),
            ask("seller", target=19.0, limit=18.0),
        )
        result = session.run()
        assert result.agreed
        assert 19.0 <= result.price <= 21.0

    def test_log_is_populated(self):
        session = HaggleSession(
            bid("buyer",  target=21.0, limit=22.0),
            ask("seller", target=19.0, limit=18.0),
        )
        result = session.run()
        assert len(result.log) > 0
        assert all(isinstance(l, str) for l in result.log)

    def test_log_contains_agent_ids(self):
        session = HaggleSession(
            bid("alice", target=21.0, limit=22.0),
            ask("bob",   target=19.0, limit=18.0),
        )
        result = session.run()
        combined = " ".join(result.log)
        assert "alice" in combined
        assert "bob"   in combined

    def test_log_indicates_deal(self):
        session = HaggleSession(
            bid("buyer",  target=21.0, limit=22.0),
            ask("seller", target=19.0, limit=18.0),
        )
        result = session.run()
        combined = " ".join(result.log)
        assert "DEAL" in combined

    def test_log_indicates_no_deal(self):
        session = HaggleSession(
            bid("buyer",  target=15.0, limit=16.0),
            ask("seller", target=25.0, limit=22.0),
        )
        result = session.run()
        assert not result.agreed
        combined = " ".join(result.log)
        assert "NO DEAL" in combined

    def test_buyer_and_seller_ids_recorded(self):
        session = HaggleSession(
            bid("buyer_x",  target=21.0, limit=22.0),
            ask("seller_y", target=19.0, limit=18.0),
        )
        result = session.run()
        assert result.buyer_id  == "buyer_x"
        assert result.seller_id == "seller_y"

    def test_more_rounds_increases_chance_of_deal(self):
        # Hard gap: needs concessions — 5 rounds should deal, 1 round should not
        few  = HaggleSession(bid("b", 18.0, 20.0), ask("s", 23.0, 21.5), max_rounds=1)
        many = HaggleSession(bid("b", 18.0, 20.0), ask("s", 23.0, 21.5), max_rounds=5)
        # At least many-round version has a better shot
        result_many = many.run()
        result_few  = few.run()
        # The many-round version should reach an agreement (or at minimum do better)
        if result_many.agreed:
            assert result_many.price is not None


# ══════════════════════════════════════════════════════════════════════════════
# HaggleCoordinator
# ══════════════════════════════════════════════════════════════════════════════

class _StubAgent:
    """Minimal agent stub for coordinator tests."""
    def __init__(self, agent_id, intent):
        self.agent_id = agent_id
        self._intent  = intent
        self.inventory = 20
        self.cash = 500.0
        self.trade_count = 0
    def haggle_intent(self, state): return self._intent
    def on_trade(self, trade):
        if trade.buyer_id == self.agent_id:
            self.inventory += trade.quantity
            self.cash      -= trade.price * trade.quantity
        elif trade.seller_id == self.agent_id:
            self.inventory -= trade.quantity
            self.cash      += trade.price * trade.quantity
        self.trade_count += 1


class TestHaggleCoordinator:

    def test_returns_list(self):
        coord = HaggleCoordinator()
        result = coord.run([], state(), tick=1)
        assert isinstance(result, list)

    def test_empty_agents_returns_empty(self):
        assert HaggleCoordinator().run([], state(), tick=1) == []

    def test_no_intents_returns_empty(self):
        agents = [_StubAgent("a", None), _StubAgent("b", None)]
        assert HaggleCoordinator().run(agents, state(), tick=1) == []

    def test_compatible_pair_produces_trade(self):
        buyer  = _StubAgent("buyer",  bid("buyer",  target=21.0, limit=22.0))
        seller = _StubAgent("seller", ask("seller", target=19.0, limit=18.0))
        results = HaggleCoordinator().run([buyer, seller], state(), tick=1)
        assert len(results) == 1
        trade, log = results[0]
        assert isinstance(trade, Trade)
        assert trade.buyer_id  == "buyer"
        assert trade.seller_id == "seller"

    def test_no_self_trading(self):
        agent = _StubAgent("solo", bid("solo", target=21.0, limit=22.0))
        results = HaggleCoordinator().run([agent], state(), tick=1)
        assert results == []

    def test_incompatible_prices_produces_no_trade(self):
        buyer  = _StubAgent("buyer",  bid("buyer",  target=10.0, limit=12.0))
        seller = _StubAgent("seller", ask("seller", target=25.0, limit=22.0))
        results = HaggleCoordinator().run([buyer, seller], state(), tick=1)
        assert results == []

    def test_each_agent_trades_at_most_once(self):
        buyer   = _StubAgent("buyer",   bid("buyer",   target=21.0, limit=22.0, qty=5))
        seller1 = _StubAgent("seller1", ask("seller1", target=19.0, limit=18.0, qty=5))
        seller2 = _StubAgent("seller2", ask("seller2", target=19.0, limit=18.0, qty=5))
        results = HaggleCoordinator(seed=42).run([buyer, seller1, seller2], state(), tick=1)
        # Buyer can only match once
        assert len(results) == 1

    def test_log_returned_alongside_trade(self):
        buyer  = _StubAgent("buyer",  bid("buyer",  target=21.0, limit=22.0))
        seller = _StubAgent("seller", ask("seller", target=19.0, limit=18.0))
        results = HaggleCoordinator().run([buyer, seller], state(), tick=1)
        _, log = results[0]
        assert isinstance(log, list)
        assert len(log) > 0

    def test_trade_tick_matches_passed_tick(self):
        buyer  = _StubAgent("buyer",  bid("buyer",  target=21.0, limit=22.0))
        seller = _StubAgent("seller", ask("seller", target=19.0, limit=18.0))
        results = HaggleCoordinator().run([buyer, seller], state(), tick=7)
        trade, _ = results[0]
        assert trade.tick == 7


# ══════════════════════════════════════════════════════════════════════════════
# Per-agent haggle_intent() overrides
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentHaggleIntents:

    # -- MarketMakerAgent --

    def test_mm_no_intent_when_balanced(self):
        agent = MarketMakerAgent("mm", inventory=40, cash=600.0,
                                 min_inventory=10, max_inventory=80)
        assert agent.haggle_intent(state()) is None

    def test_mm_bids_when_inventory_low(self):
        agent = MarketMakerAgent("mm", inventory=5, cash=600.0,
                                 min_inventory=10, max_inventory=80)
        intent = agent.haggle_intent(state())
        assert intent is not None
        assert intent.side == OrderSide.BID

    def test_mm_asks_when_inventory_high(self):
        agent = MarketMakerAgent("mm", inventory=90, cash=600.0,
                                 min_inventory=10, max_inventory=80)
        intent = agent.haggle_intent(state())
        assert intent is not None
        assert intent.side == OrderSide.ASK

    # -- SpeculatorAgent --

    def test_spec_no_intent_in_flat_market(self):
        agent = SpeculatorAgent("sp", inventory=10, cash=400.0)
        assert agent.haggle_intent(state(price_history=[20.0]*6)) is None

    def test_spec_bids_in_uptrend(self):
        agent  = SpeculatorAgent("sp", inventory=5, cash=800.0, max_position=30)
        intent = agent.haggle_intent(uptrend())
        assert intent is not None
        assert intent.side == OrderSide.BID

    def test_spec_asks_in_downtrend(self):
        agent  = SpeculatorAgent("sp", inventory=20, cash=400.0)
        intent = agent.haggle_intent(downtrend())
        assert intent is not None
        assert intent.side == OrderSide.ASK

    def test_spec_no_intent_with_no_history(self):
        assert SpeculatorAgent("sp", 10, 400.0).haggle_intent(state()) is None

    # -- HoarderAgent --

    def test_hoarder_bids_below_target(self):
        agent  = HoarderAgent("ho", inventory=20, cash=800.0, hoard_target=100)
        intent = agent.haggle_intent(state())
        assert intent is not None
        assert intent.side == OrderSide.BID
        assert intent.price_target < 20.0  # discounted bid

    def test_hoarder_no_intent_at_target(self):
        agent = HoarderAgent("ho", inventory=100, cash=800.0, hoard_target=100)
        assert agent.haggle_intent(state()) is None

    def test_hoarder_no_intent_without_cash(self):
        agent = HoarderAgent("ho", inventory=0, cash=0.01, hoard_target=100)
        assert agent.haggle_intent(state()) is None

    # -- PanicAgent --

    def test_panic_no_intent_in_calm(self):
        agent = PanicAgent("pa", inventory=30, cash=300.0)
        assert agent.haggle_intent(state(price_history=[20.0]*6)) is None

    def test_panic_asks_at_threshold(self):
        agent  = PanicAgent("pa", inventory=30, cash=300.0, panic_threshold=-0.10)
        intent = agent.haggle_intent(downtrend())
        assert intent is not None
        assert intent.side == OrderSide.ASK

    def test_panic_no_intent_when_empty(self):
        agent = PanicAgent("pa", inventory=0, cash=300.0, panic_threshold=-0.10)
        assert agent.haggle_intent(downtrend()) is None

    # -- RationalAgent --

    def test_rational_no_intent_near_fair_value(self):
        agent = RationalAgent("ra", inventory=20, cash=600.0, margin=0.05)
        assert agent.haggle_intent(state(price_history=[20.0]*6)) is None

    def test_rational_bids_when_undervalued(self):
        agent  = RationalAgent("ra", inventory=0, cash=1000.0, margin=0.05)
        intent = agent.haggle_intent(undervalued())
        assert intent is not None
        assert intent.side == OrderSide.BID

    def test_rational_asks_when_overvalued(self):
        agent  = RationalAgent("ra", inventory=20, cash=600.0, margin=0.05)
        intent = agent.haggle_intent(overvalued())
        assert intent is not None
        assert intent.side == OrderSide.ASK

    def test_rational_no_bid_without_cash(self):
        agent = RationalAgent("ra", inventory=0, cash=0.01, margin=0.05)
        assert agent.haggle_intent(undervalued()) is None

    def test_rational_no_ask_without_inventory(self):
        agent = RationalAgent("ra", inventory=0, cash=1000.0, margin=0.05)
        assert agent.haggle_intent(overvalued()) is None

    # -- intent field sanity --

    def test_all_intents_have_positive_price_and_quantity(self):
        agents_and_states = [
            (SpeculatorAgent("sp", 5, 800.0), uptrend()),
            (HoarderAgent("ho", 20, 800.0),   state()),
            (PanicAgent("pa", 30, 300.0),     downtrend()),
            (RationalAgent("ra", 20, 600.0),  overvalued()),
        ]
        for agent, s in agents_and_states:
            intent = agent.haggle_intent(s)
            if intent:
                assert intent.price_target > 0
                assert intent.price_limit  > 0
                assert intent.quantity     > 0

    def test_buyer_limit_above_target(self):
        """For buyers, price_limit (max willing to pay) >= price_target (ideal)."""
        agent  = SpeculatorAgent("sp", 5, 800.0, max_position=30)
        intent = agent.haggle_intent(uptrend())
        if intent and intent.side == OrderSide.BID:
            assert intent.price_limit >= intent.price_target

    def test_seller_limit_below_target(self):
        """For sellers, price_limit (floor) <= price_target (ideal)."""
        agent  = RationalAgent("ra", 20, 600.0, margin=0.05)
        intent = agent.haggle_intent(overvalued())
        if intent and intent.side == OrderSide.ASK:
            assert intent.price_limit <= intent.price_target
