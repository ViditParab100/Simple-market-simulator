"""
Tests for salaries / cash recirculation.
The Producer (employer) pays each living worker a wage every tick.
"""
import pytest
from market.engine import SimulationEngine
from market.metrics import MetricsCollector
from agents.base import Agent
from agents.producer import ProducerAgent
from agents.market_maker import MarketMakerAgent
from agents.rational import RationalAgent
from agents.panic import PanicAgent
from logger.thought_logger import ThoughtLogger


class StubAgent(Agent):
    def think(self, s): return []
    def act(self, s):   return []


def make_engine(agents, ticks=10, salary=0.0, consume=0.0, seed_hist=True):
    eng = SimulationEngine(
        agents=agents,
        logger=ThoughtLogger(verbose=False),
        initial_price_history=[round(19.0 + i*0.25, 2) for i in range(10)] if seed_hist else None,
        consumption_rate=consume,
        salary=salary,
        metrics_collector=MetricsCollector(),
    )
    eng.run(ticks)
    return eng


# ── employer flag ────────────────────────────────────────────────────────────

def test_producer_is_employer():
    assert ProducerAgent("P", 10, 100.0).is_employer

def test_other_agents_are_not_employers():
    assert not MarketMakerAgent("MM", 10, 100.0).is_employer
    assert not StubAgent("a", 10, 100.0).is_employer


# ── payroll basics (single tick via engine) ──────────────────────────────────

def test_payroll_transfers_cash_employer_to_workers():
    p  = ProducerAgent("P", inventory=12, cash=1000.0, production_rate=20)
    w1 = StubAgent("w1", inventory=5, cash=100.0)
    w2 = StubAgent("w2", inventory=5, cash=100.0)
    make_engine([p, w1, w2], ticks=1, salary=10.0)
    # Each worker should have received roughly one tick of wages
    assert w1.wages_received == pytest.approx(10.0)
    assert w2.wages_received == pytest.approx(10.0)
    assert p.wages_paid == pytest.approx(20.0)

def test_payroll_conserves_cash():
    """Wages move cash between agents; they don't create or destroy it."""
    p  = ProducerAgent("P", inventory=12, cash=1000.0, production_rate=0, sell_discount=0.98)
    w1 = StubAgent("w1", inventory=5, cash=100.0)
    w2 = StubAgent("w2", inventory=5, cash=100.0)
    agents = [p, w1, w2]
    start_cash = sum(a.cash for a in agents)
    make_engine(agents, ticks=5, salary=10.0)
    end_cash = sum(a.cash for a in agents)
    assert end_cash == pytest.approx(start_cash)

def test_no_payroll_when_salary_zero():
    p  = ProducerAgent("P", inventory=12, cash=1000.0)
    w1 = StubAgent("w1", inventory=5, cash=100.0)
    make_engine([p, w1], ticks=5, salary=0.0)
    assert w1.wages_received == 0.0

def test_payroll_capped_by_employer_cash():
    """If the employer can't cover the bill, workers split what's available."""
    p  = ProducerAgent("P", inventory=0, cash=15.0, production_rate=0)
    w1 = StubAgent("w1", inventory=100, cash=0.0)   # lots of stock so no starving deaths
    w2 = StubAgent("w2", inventory=100, cash=0.0)
    make_engine([p, w1, w2], ticks=1, salary=50.0)  # bill 100 > pool 15
    # Total paid cannot exceed the employer's starting cash
    assert w1.wages_received + w2.wages_received == pytest.approx(15.0, abs=1e-6)

def test_dead_workers_not_paid():
    p  = ProducerAgent("P", inventory=12, cash=1000.0)
    w1 = StubAgent("w1", inventory=5, cash=100.0)
    w1.alive = False
    make_engine([p, w1], ticks=3, salary=10.0)
    assert w1.wages_received == 0.0


# ── metrics ───────────────────────────────────────────────────────────────────

def test_metrics_track_total_wages():
    p  = ProducerAgent("P", inventory=12, cash=2000.0, production_rate=20)
    w  = [MarketMakerAgent("MM", 5, 500.0), RationalAgent("Ra", 5, 500.0)]
    collector = MetricsCollector()
    eng = SimulationEngine(
        agents=[p, *w],
        logger=ThoughtLogger(verbose=False),
        initial_price_history=[round(19.0 + i*0.25, 2) for i in range(10)],
        salary=10.0, metrics_collector=collector,
    )
    eng.run(5)
    metrics = collector.compute([p, *w], eng.order_book.last_price)
    assert metrics.total_wages > 0


# ── the headline behaviour: recirculation reduces death ──────────────────────

def survival_market():
    return [
        ProducerAgent("Producer", inventory=12, cash=200.0, production_rate=25),
        MarketMakerAgent("MM", inventory=5, cash=300.0),
        RationalAgent("Ra",    inventory=5, cash=300.0),
        PanicAgent("Pa",       inventory=6, cash=200.0),
    ]

def test_salary_keeps_workers_solvent():
    """With salaries, workers should hold more cash at the end than without."""
    no_pay = survival_market()
    make_engine(no_pay, ticks=15, consume=4.0, salary=0.0)
    cash_without = sum(a.cash for a in no_pay if not a.is_employer)

    with_pay = survival_market()
    make_engine(with_pay, ticks=15, consume=4.0, salary=15.0)
    cash_with = sum(a.cash for a in with_pay if not a.is_employer)

    assert cash_with > cash_without

def test_salary_reduces_deaths():
    """Cash recirculation should keep at least as many workers alive."""
    no_pay = survival_market()
    make_engine(no_pay, ticks=18, consume=4.0, salary=0.0)
    alive_without = sum(1 for a in no_pay if a.alive)

    with_pay = survival_market()
    make_engine(with_pay, ticks=18, consume=4.0, salary=15.0)
    alive_with = sum(1 for a in with_pay if a.alive)

    assert alive_with >= alive_without
