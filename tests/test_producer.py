"""
Tests for ProducerAgent — the supply side of the economy.
"""
import pytest
from market.models import MarketState, OrderSide
from market.engine import SimulationEngine
from agents.producer import ProducerAgent
from agents.market_maker import MarketMakerAgent
from agents.rational import RationalAgent
from agents.panic import PanicAgent
from logger.thought_logger import ThoughtLogger


def state(last_price: float = 20.0, price_history=None) -> MarketState:
    return MarketState(
        tick=1, last_price=last_price,
        best_bid=last_price - 0.5, best_ask=last_price + 0.5,
        bid_depth=50, ask_depth=50, price_history=price_history or [],
    )

def run(agent: ProducerAgent, s: MarketState):
    thoughts = agent.think(s)
    orders   = agent.act(s)
    return thoughts, orders


# ── produce() ──────────────────────────────────────────────────────────────────

def test_produce_adds_inventory():
    p = ProducerAgent("P", inventory=0, cash=100.0, production_rate=8)
    made = p.produce()
    assert made == 8
    assert p.inventory == 8

def test_produce_tracks_total():
    p = ProducerAgent("P", inventory=0, cash=100.0, production_rate=5)
    p.produce(); p.produce(); p.produce()
    assert p.produced_total == 15
    assert p.inventory == 15

def test_base_agents_produce_nothing():
    mm = MarketMakerAgent("MM", inventory=10, cash=100.0)
    assert mm.produce() == 0.0
    assert mm.inventory == 10


# ── selling behaviour ────────────────────────────────────────────────────────────

def test_producer_asks_when_holding_stock():
    p = ProducerAgent("P", inventory=10, cash=100.0)
    _, orders = run(p, state(20.0))
    assert len(orders) == 1
    assert orders[0].side == OrderSide.ASK

def test_producer_sells_entire_stock():
    p = ProducerAgent("P", inventory=12, cash=100.0)
    _, orders = run(p, state(20.0))
    assert orders[0].quantity == 12

def test_producer_ask_below_market():
    p = ProducerAgent("P", inventory=10, cash=100.0, sell_discount=0.98)
    _, orders = run(p, state(20.0))
    assert orders[0].price < 20.0

def test_producer_respects_floor_price():
    p = ProducerAgent("P", inventory=10, cash=100.0, sell_discount=0.98, floor_price=50.0)
    _, orders = run(p, state(20.0))
    assert orders[0].price == 50.0   # floor overrides the discount

def test_producer_holds_when_empty():
    p = ProducerAgent("P", inventory=0, cash=100.0)
    _, orders = run(p, state(20.0))
    assert orders == []

def test_producer_never_survival_bids():
    p = ProducerAgent("P", inventory=1, cash=1000.0)
    p.consumption_rate = 5    # even if forced to consume, it won't panic-buy
    assert p.survival_order(state(20.0)) is None

def test_producer_haggle_intent_is_ask():
    p = ProducerAgent("P", inventory=10, cash=100.0)
    intent = p.haggle_intent(state(20.0))
    assert intent is not None
    assert intent.side == OrderSide.ASK


# ── engine integration: a producer sustains a consuming market ───────────────────

def consuming_market_with_producer():
    return [
        ProducerAgent("Producer", inventory=10, cash=200.0, production_rate=10),
        MarketMakerAgent("MM", inventory=5, cash=800.0),
        RationalAgent("Ra",    inventory=5, cash=500.0),
        PanicAgent("Pa",       inventory=6, cash=300.0),
    ]

def make_engine(agents, ticks, rate):
    from market.metrics import MetricsCollector
    eng = SimulationEngine(
        agents=agents,
        logger=ThoughtLogger(verbose=False),
        initial_price_history=[round(19.0 + i*0.25, 2) for i in range(10)],
        consumption_rate=rate,
        metrics_collector=MetricsCollector(),
    )
    eng.run(ticks)
    return eng

def test_production_mints_supply_each_tick():
    agents = consuming_market_with_producer()
    producer = agents[0]
    make_engine(agents, ticks=10, rate=2.0)
    # 10 ticks * production_rate 10 = 100 units minted
    assert producer.produced_total == 100

def test_producer_prevents_total_collapse():
    """
    With a producer, total system inventory should NOT drain to zero the way
    it does in a consumption-only economy — supply is replenished each tick.
    """
    agents = consuming_market_with_producer()
    make_engine(agents, ticks=15, rate=2.0)
    total_inv = sum(a.inventory for a in agents)
    assert total_inv > 0   # market still has stock; didn't fully collapse

def test_producer_accumulates_cash_from_sales():
    agents = consuming_market_with_producer()
    producer = agents[0]
    start_cash = producer.cash
    make_engine(agents, ticks=15, rate=3.0)
    # Selling its output should grow the producer's cash
    assert producer.cash > start_cash

def test_market_stays_liquid_with_producer():
    """A producer + consumers should keep trading well past the freeze point."""
    agents = consuming_market_with_producer()
    eng = make_engine(agents, ticks=15, rate=3.0)
    total_trades = sum(a.trade_count for a in agents)
    assert total_trades > 3   # more than the old freeze-at-tick-3 behaviour
