"""
Engine integration tests.
Every test runs the real survival economy (consume=3, salary=70) with a
Producer in the roster — matching what the CLI now does in all modes.
"""
import random
import pytest
from market.engine import SimulationEngine
from agents.random_agent import RandomAgent
from agents.producer import ProducerAgent
from logger.thought_logger import ThoughtLogger

_SEED_HISTORY = [round(19.0 + i * 0.25, 2) for i in range(10)]


def make_agents(n: int = 3, seed: int = 42) -> list:
    """One Producer + n RandomAgents, starting on bare-minimum inventory."""
    rng = random.Random(seed)
    agents = [ProducerAgent("Producer-01", inventory=12, cash=200.0, production_rate=20)]
    agents += [
        RandomAgent(
            agent_id=f"R-{i + 1:02d}",
            inventory=rng.randint(3, 8),
            cash=round(rng.uniform(200, 600), 2),
            seed=seed + i,
        )
        for i in range(n)
    ]
    return agents


def silent_engine(agents, ticks: int = 10) -> SimulationEngine:
    engine = SimulationEngine(
        agents=agents,
        logger=ThoughtLogger(verbose=False),
        initial_price_history=_SEED_HISTORY,
        consumption_rate=3.0,
        salary=70.0,
    )
    engine.run(ticks=ticks)
    return engine


# ── basic operation ────────────────────────────────────────────────────────────

def test_engine_runs_without_error():
    silent_engine(make_agents(3), ticks=5)

def test_engine_tick_counter():
    engine = silent_engine(make_agents(2), ticks=7)
    assert engine.tick == 7

def test_engine_zero_ticks():
    engine = silent_engine(make_agents(2), ticks=0)
    assert engine.tick == 0


# ── price history ──────────────────────────────────────────────────────────────

def test_price_history_grows_when_trades_occur():
    engine = silent_engine(make_agents(4, seed=1), ticks=30)
    # Survival pressure guarantees trades — price history must grow past seed
    assert len(engine.price_history) > len(_SEED_HISTORY)

def test_price_history_prices_positive():
    engine = silent_engine(make_agents(4, seed=1), ticks=20)
    assert all(p > 0 for p in engine.price_history)

def test_price_history_length_bounded_by_ticks():
    ticks = 15
    engine = silent_engine(make_agents(4), ticks=ticks)
    # seed entries + at most one new price per tick
    assert len(engine.price_history) <= len(_SEED_HISTORY) + ticks


# ── conservation laws ──────────────────────────────────────────────────────────

def test_cash_is_conserved():
    """Trades and salary both redistribute cash — neither creates nor destroys it."""
    agents = make_agents(4, seed=10)
    initial = sum(a.cash for a in agents)
    silent_engine(agents, ticks=30)
    final = sum(a.cash for a in agents)
    assert abs(final - initial) < 1e-6

def test_no_negative_inventory():
    agents = make_agents(4, seed=5)
    silent_engine(agents, ticks=30)
    assert all(a.inventory >= 0 for a in agents)

def test_no_negative_cash():
    agents = make_agents(4, seed=5)
    silent_engine(agents, ticks=30)
    assert all(a.cash >= 0 for a in agents)


# ── survival economy ───────────────────────────────────────────────────────────

def test_no_deaths_in_balanced_economy():
    """consume=3 + salary=70 is the sustainable balance — nobody should starve."""
    agents = make_agents(4, seed=7)
    silent_engine(agents, ticks=30)
    assert all(a.alive for a in agents)

def test_agents_consume_food_each_tick():
    """Every agent's consumed_total should be positive after a real run."""
    agents = make_agents(3, seed=2)
    silent_engine(agents, ticks=10)
    assert all(a.consumed_total > 0 for a in agents)

def test_producer_stays_solvent():
    """Producer mints + sells — it should not go bankrupt in a balanced economy."""
    agents = make_agents(3, seed=9)
    producer = agents[0]
    silent_engine(agents, ticks=20)
    assert producer.cash >= 0
    assert producer.alive


# ── trade count ────────────────────────────────────────────────────────────────

def test_trade_counts_non_negative():
    agents = make_agents(3, seed=7)
    silent_engine(agents, ticks=20)
    assert all(a.trade_count >= 0 for a in agents)

def test_total_trade_count_even():
    """Every trade increments exactly one buyer and one seller."""
    agents = make_agents(4, seed=3)
    silent_engine(agents, ticks=30)
    total = sum(a.trade_count for a in agents)
    assert total % 2 == 0

def test_survival_pressure_drives_trades():
    """Agents must buy food — there should be meaningful trade activity."""
    agents = make_agents(4, seed=1)
    silent_engine(agents, ticks=20)
    total_trades = sum(a.trade_count for a in agents)
    assert total_trades > 0


# ── agent isolation ────────────────────────────────────────────────────────────

def test_agents_in_engine_are_same_objects():
    """Engine must settle trades on the original agent objects, not copies."""
    agents = make_agents(2, seed=99)
    initial_cash = sum(a.cash for a in agents)
    silent_engine(agents, ticks=20)
    # Salary + trades must have moved cash — objects mutated in place
    final_cash = sum(a.cash for a in agents)
    assert abs(final_cash - initial_cash) < 1e-6  # conserved, not frozen
    assert any(a.trade_count > 0 for a in agents)  # but trades did happen
