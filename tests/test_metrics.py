"""Tests for Phase 5 metric functions and MetricsCollector."""
import pytest
from market.metrics import gini, price_volatility, max_drawdown, MetricsCollector
from agents.base import Agent
from market.models import Order, Trade, MarketState


class StubAgent(Agent):
    def think(self, s): return []
    def act(self, s):   return []


# ── gini ───────────────────────────────────────────────────────────────────────

def test_gini_perfect_equality():
    assert gini([10.0, 10.0, 10.0, 10.0]) == pytest.approx(0.0, abs=1e-9)

def test_gini_maximum_inequality():
    # One person has everything
    result = gini([0.0, 0.0, 0.0, 100.0])
    assert result == pytest.approx(0.75, abs=1e-9)

def test_gini_empty():
    assert gini([]) == 0.0

def test_gini_single_value():
    assert gini([50.0]) == pytest.approx(0.0, abs=1e-9)

def test_gini_all_zeros():
    assert gini([0.0, 0.0, 0.0]) == 0.0

def test_gini_between_zero_and_one():
    result = gini([10.0, 20.0, 30.0, 40.0])
    assert 0.0 <= result <= 1.0

def test_gini_higher_for_more_unequal():
    equal   = gini([25.0, 25.0, 25.0, 25.0])
    unequal = gini([5.0,  10.0, 30.0, 55.0])
    assert unequal > equal

def test_gini_negatives_clamped_to_zero():
    # Negative values treated as 0 (bankrupt agents have 0 effective wealth)
    result = gini([-10.0, 50.0, 50.0])
    assert 0.0 <= result <= 1.0


# ── price_volatility ───────────────────────────────────────────────────────────

def test_volatility_flat_prices():
    assert price_volatility([20.0, 20.0, 20.0, 20.0]) == pytest.approx(0.0)

def test_volatility_positive_for_varying():
    assert price_volatility([18.0, 20.0, 22.0]) > 0.0

def test_volatility_empty():
    assert price_volatility([]) == 0.0

def test_volatility_single():
    assert price_volatility([20.0]) == 0.0

def test_volatility_increases_with_spread():
    narrow = price_volatility([19.0, 20.0, 21.0])
    wide   = price_volatility([15.0, 20.0, 25.0])
    assert wide > narrow

def test_volatility_symmetric():
    # Volatility is symmetric around the mean
    up   = price_volatility([20.0, 22.0, 24.0])
    down = price_volatility([24.0, 22.0, 20.0])
    assert up == pytest.approx(down, abs=1e-9)


# ── max_drawdown ───────────────────────────────────────────────────────────────

def test_drawdown_always_rising():
    assert max_drawdown([10.0, 12.0, 14.0, 16.0]) == pytest.approx(0.0)

def test_drawdown_single_drop():
    # Peak 20, trough 16 -> 20% drawdown
    result = max_drawdown([20.0, 18.0, 16.0])
    assert result == pytest.approx(0.20, abs=0.01)

def test_drawdown_partial_recovery():
    # Peak 20, drops to 15 (-25%), recovers to 18 — worst is still 25%
    result = max_drawdown([20.0, 15.0, 18.0])
    assert result == pytest.approx(0.25, abs=0.01)

def test_drawdown_empty():
    assert max_drawdown([]) == 0.0

def test_drawdown_single():
    assert max_drawdown([20.0]) == 0.0

def test_drawdown_between_zero_and_one():
    result = max_drawdown([10.0, 20.0, 5.0, 18.0])
    assert 0.0 <= result <= 1.0


# ── MetricsCollector ───────────────────────────────────────────────────────────

def make_agent(agent_id, inventory=20, cash=400.0):
    return StubAgent(agent_id, inventory, cash)

def test_collector_record_initial():
    collector = MetricsCollector()
    agents = [make_agent("a", inventory=10, cash=200.0)]
    collector.record_initial(agents, last_price=20.0)
    assert "a" in collector._initial_worths
    assert collector._initial_worths["a"] == pytest.approx(400.0)  # 10*20 + 200

def test_collector_record_tick_accumulates():
    collector = MetricsCollector()
    collector.record_tick(1, 20.0, 50, 50, 2, 10)
    collector.record_tick(2, 21.0, 40, 60, 1, 5)
    assert len(collector._records) == 2

def test_collector_compute_returns_run_metrics():
    from market.metrics import RunMetrics
    collector = MetricsCollector()
    agents = [make_agent("a", 20, 400.0), make_agent("b", 15, 300.0)]
    collector.record_initial(agents, last_price=20.0)
    collector.record_tick(1, 20.0, 50, 50, 1, 5)
    collector.record_tick(2, 21.0, 40, 60, 2, 8)
    result = collector.compute(agents, last_price=21.0)
    assert isinstance(result, RunMetrics)

def test_collector_total_trades():
    collector = MetricsCollector()
    agents = [make_agent("a")]
    collector.record_initial(agents, last_price=20.0)
    collector.record_tick(1, 20.0, 50, 50, 3, 15)
    collector.record_tick(2, 21.0, 40, 60, 2, 8)
    result = collector.compute(agents, 21.0)
    assert result.total_trades == 5

def test_collector_total_volume():
    collector = MetricsCollector()
    agents = [make_agent("a")]
    collector.record_initial(agents, last_price=20.0)
    collector.record_tick(1, 20.0, 50, 50, 1, 10)
    collector.record_tick(2, 21.0, 40, 60, 1, 7)
    result = collector.compute(agents, 21.0)
    assert result.total_volume == 17

def test_collector_ticks_with_trades():
    collector = MetricsCollector()
    agents = [make_agent("a")]
    collector.record_initial(agents, last_price=20.0)
    collector.record_tick(1, 20.0, 50, 50, 2, 10)
    collector.record_tick(2, 21.0, 40, 60, 0, 0)   # no trades this tick
    collector.record_tick(3, 21.5, 45, 55, 1, 5)
    result = collector.compute(agents, 21.5)
    assert result.ticks_with_trades == 2

def test_collector_price_range():
    collector = MetricsCollector()
    agents = [make_agent("a")]
    collector.record_initial(agents, last_price=20.0)
    for price in [20.0, 22.0, 18.0, 21.0]:
        collector.record_tick(1, price, 50, 50, 0, 0)
    result = collector.compute(agents, 21.0)
    assert result.price_min == 18.0
    assert result.price_max == 22.0

def test_collector_gini_computed():
    collector = MetricsCollector()
    agents = [make_agent("a", 10, 200.0), make_agent("b", 10, 200.0)]
    collector.record_initial(agents, last_price=20.0)
    collector.record_tick(1, 20.0, 50, 50, 0, 0)
    result = collector.compute(agents, 20.0)
    # Equal wealth -> Gini near 0
    assert result.gini_start == pytest.approx(0.0, abs=0.01)
    assert result.gini_end   == pytest.approx(0.0, abs=0.01)

def test_collector_agent_summaries_populated():
    collector = MetricsCollector()
    agents = [make_agent("alpha", 20, 400.0)]
    collector.record_initial(agents, last_price=20.0)
    collector.record_tick(1, 20.0, 50, 50, 0, 0)
    result = collector.compute(agents, 20.0)
    assert len(result.agents) == 1
    assert result.agents[0].agent_id == "alpha"
