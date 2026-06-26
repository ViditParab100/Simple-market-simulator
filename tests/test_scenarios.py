"""Tests for Phase 5 ScenarioRunner and predefined scenarios."""
import pytest
from market.scenarios import (
    ScenarioEvent, ScenarioRunner,
    hoarding_crash_scenario, panic_cascade_scenario,
    speculator_bubble_scenario, supply_disruption_scenario, NAMED_SCENARIOS,
)
from market.order_book import OrderBook
from agents.base import Agent
from market.models import Order, Trade, MarketState


class StubAgent(Agent):
    def think(self, s): return []
    def act(self, s):   return []


def make_agent(agent_id, inventory=30, cash=500.0):
    return StubAgent(agent_id, inventory, cash)

def fresh_book(last_price: float = 20.0) -> OrderBook:
    ob = OrderBook()
    ob.last_price = last_price
    return ob


# ── ScenarioEvent ──────────────────────────────────────────────────────────────

def test_scenario_event_describe_supply_shock():
    e = ScenarioEvent(tick=5, action="supply_shock", params={"fraction": 0.5})
    assert "supply_shock" in e.describe()
    assert "50%" in e.describe()

def test_scenario_event_describe_price_inject():
    e = ScenarioEvent(tick=3, action="price_inject", params={"price": 15.0})
    assert "15.00" in e.describe()

def test_scenario_event_describe_agent_collapse():
    e = ScenarioEvent(tick=7, action="agent_collapse", params={"agent_id": "bob"})
    assert "bob" in e.describe()

def test_scenario_event_describe_demand_surge():
    e = ScenarioEvent(tick=4, action="demand_surge", params={"cash": 200.0})
    assert "200" in e.describe()


# ── ScenarioRunner ─────────────────────────────────────────────────────────────

class TestScenarioRunner:

    def test_fires_at_correct_tick(self):
        runner = ScenarioRunner([
            ScenarioEvent(tick=5, action="price_inject", params={"price": 15.0})
        ])
        ob   = fresh_book(20.0)
        hist = [20.0]
        fired = runner.apply(tick=5, agents=[], order_book=ob, price_history=hist)
        assert len(fired) == 1

    def test_does_not_fire_at_wrong_tick(self):
        runner = ScenarioRunner([
            ScenarioEvent(tick=5, action="price_inject", params={"price": 15.0})
        ])
        ob   = fresh_book(20.0)
        hist = [20.0]
        fired = runner.apply(tick=3, agents=[], order_book=ob, price_history=hist)
        assert len(fired) == 0

    def test_fires_multiple_events_same_tick(self):
        runner = ScenarioRunner([
            ScenarioEvent(tick=5, action="price_inject",  params={"price": 15.0}),
            ScenarioEvent(tick=5, action="demand_surge",  params={"cash": 100.0}),
        ])
        agents = [make_agent("a")]
        ob     = fresh_book(20.0)
        hist   = [20.0]
        fired  = runner.apply(tick=5, agents=agents, order_book=ob, price_history=hist)
        assert len(fired) == 2

    def test_fired_descriptions_are_strings(self):
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="price_inject", params={"price": 10.0})
        ])
        fired = runner.apply(1, [], fresh_book(), [20.0])
        assert all(isinstance(d, str) for d in fired)

    def test_scheduled_ticks_property(self):
        runner = ScenarioRunner([
            ScenarioEvent(tick=3,  action="price_inject", params={}),
            ScenarioEvent(tick=7,  action="supply_shock", params={}),
            ScenarioEvent(tick=10, action="demand_surge", params={}),
        ])
        assert runner.scheduled_ticks == [3, 7, 10]


# ── supply_shock ───────────────────────────────────────────────────────────────

class TestSupplyShock:

    def test_reduces_all_inventories(self):
        agents = [make_agent("a", 40), make_agent("b", 20)]
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="supply_shock", params={"fraction": 0.5})
        ])
        runner.apply(1, agents, fresh_book(), [20.0])
        assert agents[0].inventory == 20
        assert agents[1].inventory == 10

    def test_targets_specific_agents(self):
        a = make_agent("a", 40)
        b = make_agent("b", 40)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="supply_shock",
                          params={"fraction": 0.5, "agent_ids": ["a"]})
        ])
        runner.apply(1, [a, b], fresh_book(), [20.0])
        assert a.inventory == 20
        assert b.inventory == 40   # untouched

    def test_inventory_never_goes_negative(self):
        agent  = make_agent("a", 5)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="supply_shock", params={"fraction": 0.99})
        ])
        runner.apply(1, [agent], fresh_book(), [20.0])
        assert agent.inventory >= 0

    def test_zero_fraction_no_change(self):
        agent  = make_agent("a", 30)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="supply_shock", params={"fraction": 0.0})
        ])
        runner.apply(1, [agent], fresh_book(), [20.0])
        assert agent.inventory == 30


# ── demand_surge ───────────────────────────────────────────────────────────────

class TestDemandSurge:

    def test_increases_all_cash(self):
        agents = [make_agent("a", cash=100.0), make_agent("b", cash=200.0)]
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="demand_surge", params={"cash": 50.0})
        ])
        runner.apply(1, agents, fresh_book(), [20.0])
        assert agents[0].cash == 150.0
        assert agents[1].cash == 250.0

    def test_targets_specific_agents(self):
        a = make_agent("a", cash=100.0)
        b = make_agent("b", cash=100.0)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="demand_surge",
                          params={"cash": 100.0, "agent_ids": ["a"]})
        ])
        runner.apply(1, [a, b], fresh_book(), [20.0])
        assert a.cash == 200.0
        assert b.cash == 100.0


# ── agent_collapse ─────────────────────────────────────────────────────────────

class TestAgentCollapse:

    def test_zeros_inventory_and_cash(self):
        agent  = make_agent("target", inventory=40, cash=500.0)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="agent_collapse", params={"agent_id": "target"})
        ])
        runner.apply(1, [agent], fresh_book(), [20.0])
        assert agent.inventory == 0
        assert agent.cash      == 0.0

    def test_leaves_other_agents_untouched(self):
        target  = make_agent("target", inventory=40, cash=500.0)
        bystander = make_agent("bystander", inventory=30, cash=300.0)
        runner  = ScenarioRunner([
            ScenarioEvent(tick=1, action="agent_collapse", params={"agent_id": "target"})
        ])
        runner.apply(1, [target, bystander], fresh_book(), [20.0])
        assert bystander.inventory == 30
        assert bystander.cash      == 300.0


# ── price_inject ───────────────────────────────────────────────────────────────

class TestPriceInject:

    def test_sets_order_book_last_price(self):
        ob   = fresh_book(20.0)
        hist = []
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="price_inject", params={"price": 15.0})
        ])
        runner.apply(1, [], ob, hist)
        assert ob.last_price == 15.0

    def test_appends_to_price_history(self):
        ob   = fresh_book(20.0)
        hist = [20.0]
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="price_inject", params={"price": 15.0})
        ])
        runner.apply(1, [], ob, hist)
        assert 15.0 in hist

    def test_multiple_injects_append_in_order(self):
        ob   = fresh_book(20.0)
        hist = []
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="price_inject", params={"price": 22.0}),
            ScenarioEvent(tick=2, action="price_inject", params={"price": 25.0}),
        ])
        runner.apply(1, [], ob, hist)
        runner.apply(2, [], ob, hist)
        assert hist[-2] == 22.0
        assert hist[-1] == 25.0


# ── Predefined scenarios ───────────────────────────────────────────────────────

class TestPredefinedScenarios:

    def test_hoarding_crash_returns_runner(self):
        assert isinstance(hoarding_crash_scenario(), ScenarioRunner)

    def test_panic_cascade_returns_runner(self):
        assert isinstance(panic_cascade_scenario(), ScenarioRunner)

    def test_speculator_bubble_returns_runner(self):
        assert isinstance(speculator_bubble_scenario(), ScenarioRunner)

    def test_hoarding_crash_fires_at_expected_ticks(self):
        runner = hoarding_crash_scenario()
        assert 5 in runner.scheduled_ticks
        assert 10 in runner.scheduled_ticks
        assert 15 in runner.scheduled_ticks

    def test_panic_cascade_fires_at_expected_ticks(self):
        runner = panic_cascade_scenario()
        assert 8  in runner.scheduled_ticks
        assert 12 in runner.scheduled_ticks

    def test_speculator_bubble_fires_on_tick_9(self):
        runner = speculator_bubble_scenario()
        assert 9 in runner.scheduled_ticks

    def test_named_scenarios_registry_complete(self):
        assert "hoarding_crash"     in NAMED_SCENARIOS
        assert "panic_cascade"      in NAMED_SCENARIOS
        assert "speculator_bubble"  in NAMED_SCENARIOS
        assert "supply_disruption"  in NAMED_SCENARIOS

    def test_hoarding_crash_reduces_inventory_at_tick_5(self):
        runner = hoarding_crash_scenario()
        agent  = make_agent("a", inventory=40)
        ob     = fresh_book(21.0)
        hist   = [21.0]
        runner.apply(5, [agent], ob, hist)
        assert agent.inventory < 40   # supply shock fired

    def test_panic_cascade_injects_price_at_tick_8(self):
        runner = panic_cascade_scenario()
        ob     = fresh_book(21.0)
        hist   = [21.0]
        runner.apply(8, [], ob, hist)
        assert ob.last_price < 21.0   # price was injected lower

    def test_speculator_bubble_injects_rising_prices(self):
        runner = speculator_bubble_scenario()
        ob     = fresh_book(21.0)
        hist   = []
        for tick in range(1, 8):
            runner.apply(tick, [], ob, hist)
        # Price history should show an upward trend
        if len(hist) >= 2:
            assert hist[-1] > hist[0]

    def test_supply_disruption_returns_runner(self):
        assert isinstance(supply_disruption_scenario(), ScenarioRunner)

    def test_supply_disruption_fires_at_ticks_5_and_20(self):
        runner = supply_disruption_scenario()
        assert 5  in runner.scheduled_ticks
        assert 20 in runner.scheduled_ticks


# ── production_cut / production_restore ───────────────────────────────────────

class TestProductionCut:

    def _producer_stub(self, rate: int = 20):
        """StubAgent with a production_rate attribute."""
        agent = make_agent("P", inventory=50)
        agent.production_rate = rate
        return agent

    def test_cuts_production_rate_by_fraction(self):
        p      = self._producer_stub(20)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="production_cut", params={"fraction": 0.75})
        ])
        runner.apply(1, [p], fresh_book(), [20.0])
        assert p.production_rate == 5   # 20 * 0.25 = 5

    def test_production_rate_never_below_one(self):
        p      = self._producer_stub(1)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="production_cut", params={"fraction": 0.99})
        ])
        runner.apply(1, [p], fresh_book(), [20.0])
        assert p.production_rate >= 1

    def test_only_affects_agents_with_production_rate(self):
        producer = self._producer_stub(20)
        worker   = make_agent("W", inventory=30)   # no production_rate
        runner   = ScenarioRunner([
            ScenarioEvent(tick=1, action="production_cut", params={"fraction": 0.5})
        ])
        runner.apply(1, [producer, worker], fresh_book(), [20.0])
        assert producer.production_rate == 10
        assert not hasattr(worker, "production_rate")

    def test_targets_specific_agent(self):
        p1 = self._producer_stub(20); p1.agent_id = "P1"
        p2 = self._producer_stub(20); p2.agent_id = "P2"
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="production_cut",
                          params={"fraction": 0.5, "agent_ids": ["P1"]})
        ])
        runner.apply(1, [p1, p2], fresh_book(), [20.0])
        assert p1.production_rate == 10
        assert p2.production_rate == 20  # untouched

    def test_describe_mentions_percentage(self):
        e = ScenarioEvent(tick=5, action="production_cut", params={"fraction": 0.75})
        assert "75%" in e.describe()
        assert "production_cut" in e.describe()


class TestProductionRestore:

    def _producer_stub(self, rate: int = 5):
        agent = make_agent("P", inventory=50)
        agent.production_rate = rate
        return agent

    def test_restores_production_rate(self):
        p      = self._producer_stub(5)
        runner = ScenarioRunner([
            ScenarioEvent(tick=1, action="production_restore", params={"rate": 20})
        ])
        runner.apply(1, [p], fresh_book(), [20.0])
        assert p.production_rate == 20

    def test_describe_mentions_rate(self):
        e = ScenarioEvent(tick=20, action="production_restore", params={"rate": 20})
        assert "20" in e.describe()
        assert "production_restore" in e.describe()

    def test_cut_then_restore_cycle(self):
        p = self._producer_stub(20)
        runner = ScenarioRunner([
            ScenarioEvent(tick=5,  action="production_cut",     params={"fraction": 0.75}),
            ScenarioEvent(tick=20, action="production_restore",  params={"rate": 20}),
        ])
        runner.apply(5,  [p], fresh_book(), [20.0])
        assert p.production_rate == 5
        runner.apply(20, [p], fresh_book(), [20.0])
        assert p.production_rate == 20
