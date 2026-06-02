"""
Tests for the survival-consumption mechanic (Phase 7).
Covers Agent.consume(), runway(), survival_order(), and engine integration.
"""
import pytest
from market.models import MarketState, OrderSide
from market.engine import SimulationEngine
from agents.base import Agent
from agents.market_maker import MarketMakerAgent
from agents.rational import RationalAgent
from logger.thought_logger import ThoughtLogger


class StubAgent(Agent):
    def think(self, s): return []
    def act(self, s):   return []


def state(last_price: float = 20.0, price_history=None) -> MarketState:
    return MarketState(
        tick=1, last_price=last_price,
        best_bid=last_price - 0.5, best_ask=last_price + 0.5,
        bid_depth=50, ask_depth=50, price_history=price_history or [],
    )


# ── consume() ──────────────────────────────────────────────────────────────────

def test_consume_disabled_by_default():
    a = StubAgent("a", inventory=20, cash=100.0)
    got, starved = a.consume()
    assert got == 0.0
    assert not starved
    assert a.inventory == 20

def test_consume_reduces_inventory():
    a = StubAgent("a", inventory=20, cash=100.0)
    a.consumption_rate = 3
    got, starved = a.consume()
    assert got == 3
    assert a.inventory == 17
    assert not starved

def test_consume_tracks_total():
    a = StubAgent("a", inventory=20, cash=100.0)
    a.consumption_rate = 2
    a.consume(); a.consume(); a.consume()
    assert a.consumed_total == 6
    assert a.inventory == 14

def test_consume_starves_when_insufficient():
    a = StubAgent("a", inventory=1, cash=100.0)
    a.consumption_rate = 5
    got, starved = a.consume()
    assert got == 1          # only had 1 unit
    assert a.inventory == 0
    assert starved
    assert a.starved_ticks == 1

def test_consume_never_negative_inventory():
    a = StubAgent("a", inventory=0, cash=100.0)
    a.consumption_rate = 4
    a.consume()
    assert a.inventory == 0


# ── death / starvation streak ────────────────────────────────────────────────

def test_agent_starts_alive():
    a = StubAgent("a", inventory=20, cash=100.0)
    assert a.alive

def test_agent_dies_after_starvation_limit():
    a = StubAgent("a", inventory=0, cash=100.0)
    a.consumption_rate = 4
    a.starvation_limit = 3
    a.consume(1); assert a.alive       # streak 1
    a.consume(2); assert a.alive       # streak 2
    a.consume(3); assert not a.alive   # streak 3 -> dead
    assert a.died_tick == 3

def test_eating_resets_starvation_streak():
    a = StubAgent("a", inventory=4, cash=100.0)
    a.consumption_rate = 4
    a.starvation_limit = 2
    # tick 1: only 0 in stock after... actually has 4, eats 4 fully -> no starve
    a.consume(1)
    assert a.consecutive_starved == 0
    # now empty: starve once
    a.consume(2)
    assert a.consecutive_starved == 1
    assert a.alive
    # refill and eat fully -> streak resets
    a.inventory = 10
    a.consume(3)
    assert a.consecutive_starved == 0

def test_dead_agent_does_not_consume():
    a = StubAgent("a", inventory=100, cash=100.0)
    a.consumption_rate = 4
    a.alive = False
    got, starved = a.consume(1)
    assert got == 0.0
    assert a.inventory == 100


# ── runway() ───────────────────────────────────────────────────────────────────

def test_runway_infinite_when_not_consuming():
    a = StubAgent("a", inventory=20, cash=100.0)
    assert a.runway() == float("inf")

def test_runway_computes_ticks_left():
    a = StubAgent("a", inventory=20, cash=100.0)
    a.consumption_rate = 4
    assert a.runway() == 5.0

def test_runway_zero_when_empty():
    a = StubAgent("a", inventory=0, cash=100.0)
    a.consumption_rate = 2
    assert a.runway() == 0.0


# ── survival_order() ─────────────────────────────────────────────────────────────

def test_no_survival_order_when_not_consuming():
    a = StubAgent("a", inventory=2, cash=1000.0)
    assert a.survival_order(state()) is None

def test_no_survival_order_when_comfortable():
    # runway 10 ticks, threshold 3 -> comfortable
    a = StubAgent("a", inventory=20, cash=1000.0)
    a.consumption_rate = 2
    assert a.survival_order(state()) is None

def test_survival_order_when_runway_short():
    # runway = 1 tick, threshold 3 -> should bid
    a = StubAgent("a", inventory=2, cash=1000.0)
    a.consumption_rate = 2
    order = a.survival_order(state(20.0))
    assert order is not None
    assert order.side == OrderSide.BID

def test_survival_bid_above_market():
    a = StubAgent("a", inventory=1, cash=1000.0)
    a.consumption_rate = 2
    order = a.survival_order(state(20.0))
    assert order.price > 20.0   # pays a premium to secure supply

def test_survival_bid_escalates_with_urgency():
    # Nearly starving agent bids higher than a mildly-low one
    mild = StubAgent("m", inventory=5, cash=1000.0); mild.consumption_rate = 2  # runway 2.5
    dire = StubAgent("d", inventory=1, cash=1000.0); dire.consumption_rate = 2  # runway 0.5
    o_mild = mild.survival_order(state(20.0))
    o_dire = dire.survival_order(state(20.0))
    assert o_dire.price > o_mild.price

def test_no_survival_order_without_cash():
    a = StubAgent("a", inventory=1, cash=0.0)
    a.consumption_rate = 2
    assert a.survival_order(state(20.0)) is None

def test_survival_qty_positive():
    a = StubAgent("a", inventory=1, cash=1000.0)
    a.consumption_rate = 2
    order = a.survival_order(state(20.0))
    assert order.quantity > 0


# ── engine integration ───────────────────────────────────────────────────────────

def make_engine(agents, ticks=10, rate=2.0):
    eng = SimulationEngine(
        agents=agents,
        logger=ThoughtLogger(verbose=False),
        initial_price_history=[round(19.0 + i * 0.25, 2) for i in range(10)],
        consumption_rate=rate,
        metrics_collector=__import__("market.metrics", fromlist=["MetricsCollector"]).MetricsCollector(),
    )
    eng.run(ticks)
    return eng

def zoo_agents():
    from agents.speculator import SpeculatorAgent
    from agents.hoarder import HoarderAgent
    from agents.panic import PanicAgent
    return [
        MarketMakerAgent("MM", inventory=30, cash=800.0),
        SpeculatorAgent("Sp",  inventory=10, cash=600.0),
        HoarderAgent("Ho",     inventory=20, cash=1000.0, hoard_target=60),
        PanicAgent("Pa",       inventory=40, cash=300.0),
        RationalAgent("Ra",    inventory=25, cash=500.0),
    ]

def test_engine_applies_consumption_rate_to_agents():
    agents = zoo_agents()
    SimulationEngine(agents=agents, logger=ThoughtLogger(verbose=False),
                     consumption_rate=2.0)
    assert all(a.consumption_rate == 2.0 for a in agents)

def test_engine_zero_rate_leaves_agents_unconsuming():
    agents = zoo_agents()
    SimulationEngine(agents=agents, logger=ThoughtLogger(verbose=False),
                     consumption_rate=0.0)
    assert all(a.consumption_rate == 0.0 for a in agents)

def test_consumption_depletes_inventory_over_run():
    agents = zoo_agents()
    start_total = sum(a.inventory for a in agents)
    make_engine(agents, ticks=10, rate=2.0)
    end_total = sum(a.inventory for a in agents)
    # Net inventory should fall (consumption removes units from the system)
    assert end_total < start_total

def test_agents_accumulate_consumed_total():
    agents = zoo_agents()
    make_engine(agents, ticks=10, rate=2.0)
    assert any(a.consumed_total > 0 for a in agents)

def test_consumption_breaks_deadlock_more_trades():
    """A consuming market should produce at least as many trades as a frozen one."""
    frozen = zoo_agents()
    e_frozen = SimulationEngine(agents=frozen, logger=ThoughtLogger(verbose=False),
                                initial_price_history=[round(19.0 + i*0.25, 2) for i in range(10)],
                                consumption_rate=0.0)
    e_frozen.run(15)
    frozen_trades = sum(a.trade_count for a in frozen)

    consuming = zoo_agents()
    e_consume = SimulationEngine(agents=consuming, logger=ThoughtLogger(verbose=False),
                                 initial_price_history=[round(19.0 + i*0.25, 2) for i in range(10)],
                                 consumption_rate=3.0)
    e_consume.run(15)
    consume_trades = sum(a.trade_count for a in consuming)

    assert consume_trades >= frozen_trades

def test_metrics_report_consumption():
    from market.metrics import MetricsCollector
    agents = zoo_agents()
    collector = MetricsCollector()
    eng = SimulationEngine(agents=agents, logger=ThoughtLogger(verbose=False),
                           initial_price_history=[round(19.0 + i*0.25, 2) for i in range(10)],
                           consumption_rate=2.0, metrics_collector=collector)
    eng.run(10)
    metrics = collector.compute(agents, eng.order_book.last_price)
    assert metrics.total_consumed > 0
