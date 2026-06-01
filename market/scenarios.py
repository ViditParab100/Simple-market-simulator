"""
Phase 5 — Scenario Runner.

Scenarios are timed interventions that fire at specific ticks to stress-test
the market. Each scenario is a list of ScenarioEvents applied by the engine
at the start of the designated tick (before haggling and order submission).

Built-in interventions:
  supply_shock    — strip inventory from all or specific agents
  demand_surge    — inject cash to increase buying pressure
  agent_collapse  — bankrupt a specific agent (zero inventory + cash)
  price_inject    — force a specific price into history (creates momentum signal)

Predefined failure-mode scenarios (from the README):
  hoarding_crash      — hoarder corners supply, price spikes, then crashes
  panic_cascade       — sudden price drop triggers simultaneous panic sells
  speculator_bubble   — rising prices feed a bubble, then a hard reversal
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base import Agent
    from market.order_book import OrderBook


# ── Event definition ──────────────────────────────────────────────────────────

@dataclass
class ScenarioEvent:
    tick:   int
    action: str   # "supply_shock" | "demand_surge" | "agent_collapse" | "price_inject"
    params: dict  = field(default_factory=dict)

    def describe(self) -> str:
        p = self.params
        if self.action == "supply_shock":
            targets = p.get("agent_ids", "all agents")
            return f"supply_shock: remove {p.get('fraction', 0)*100:.0f}% inventory from {targets}"
        if self.action == "demand_surge":
            return f"demand_surge: inject ${p.get('cash', 0):.0f} cash per agent"
        if self.action == "agent_collapse":
            return f"agent_collapse: {p.get('agent_id', '?')} goes bankrupt"
        if self.action == "price_inject":
            return f"price_inject: force last price to ${p.get('price', 0):.2f}"
        return f"{self.action}: {p}"


# ── Runner ────────────────────────────────────────────────────────────────────

class ScenarioRunner:
    """
    Holds a list of ScenarioEvents sorted by tick.
    The engine calls apply() at the START of each tick (before haggling).
    Returns a list of description strings for events that fired, so the
    engine can log them.
    """

    def __init__(self, events: list[ScenarioEvent]):
        self._events = sorted(events, key=lambda e: e.tick)

    def apply(
        self,
        tick:          int,
        agents:        list[Agent],
        order_book:    OrderBook,
        price_history: list[float],
    ) -> list[str]:
        fired: list[str] = []
        for event in self._events:
            if event.tick == tick:
                self._execute(event, agents, order_book, price_history)
                fired.append(event.describe())
        return fired

    def _execute(
        self,
        event:         ScenarioEvent,
        agents:        list[Agent],
        order_book:    OrderBook,
        price_history: list[float],
    ):
        p = event.params

        if event.action == "supply_shock":
            fraction   = float(p.get("fraction", 0.5))
            target_ids = p.get("agent_ids")   # None → all agents
            for agent in agents:
                if target_ids is None or agent.agent_id in target_ids:
                    agent.inventory = max(0, int(agent.inventory * (1.0 - fraction)))

        elif event.action == "demand_surge":
            cash_inject = float(p.get("cash", 100.0))
            target_ids  = p.get("agent_ids")
            for agent in agents:
                if target_ids is None or agent.agent_id in target_ids:
                    agent.cash += cash_inject

        elif event.action == "agent_collapse":
            target_id = p.get("agent_id", "")
            for agent in agents:
                if agent.agent_id == target_id:
                    agent.inventory = 0
                    agent.cash      = 0.0

        elif event.action == "price_inject":
            price = float(p.get("price", order_book.last_price or 20.0))
            price_history.append(price)
            order_book.last_price = price

    @property
    def scheduled_ticks(self) -> list[int]:
        return sorted({e.tick for e in self._events})


# ── Predefined failure-mode scenarios ─────────────────────────────────────────

def hoarding_crash_scenario() -> ScenarioRunner:
    """
    Scenario 1 — Hoarding → Artificial Scarcity → Price Spike → Crash.

    Tick 5:  Supply shock — strip 50% of inventory from all non-hoarder agents.
             The hoarder now holds a disproportionate share of total supply.
    Tick 10: Price inject to +40% — reflects artificial scarcity premium.
             Speculator doubles down. Rational sees overvaluation and tries to sell
             but hoarder won't release supply.
    Tick 15: Hard crash — inject price at -45% of spike.
             Hoarder's locked-up supply is now worthless relative to entry cost.
             PanicAgent dumps. Liquidity evaporates.
    """
    return ScenarioRunner([
        ScenarioEvent(tick=5,  action="supply_shock",
                      params={"fraction": 0.50}),
        ScenarioEvent(tick=10, action="price_inject",
                      params={"price": 30.0}),   # spike
        ScenarioEvent(tick=15, action="price_inject",
                      params={"price": 13.0}),   # crash
    ])


def panic_cascade_scenario() -> ScenarioRunner:
    """
    Scenario 2 — Panic Sell Cascade → Liquidity Drain → Price Collapse.

    Tick 8:  Sharp price inject (-28%) — exceeds PanicAgent threshold (-10%).
             All panic-capable agents dump simultaneously.
             Hoarder's lowball bids absorb some supply, but not enough.
    Tick 12: Second price inject (-15% from already depressed level).
             Second wave of panic from agents who recovered from tick 8.
    """
    return ScenarioRunner([
        ScenarioEvent(tick=8,  action="price_inject",
                      params={"price": 15.0}),   # -28% from seeded ~$21
        ScenarioEvent(tick=12, action="price_inject",
                      params={"price": 12.5}),   # second leg down
    ])


def speculator_bubble_scenario() -> ScenarioRunner:
    """
    Scenario 3 — Speculator Feedback Loop → Bubble → Reversal.

    Ticks 1–7: Inject steadily rising prices (+10–20% sequence).
               Speculator detects sustained momentum; keeps buying aggressively.
               MarketMaker widens spread. Rational starts selling.
    Tick 8:    Hard reversal — inject -35% price crash.
               Speculator (now overweight) becomes a panic seller.
               Rational's fair value estimate is stale; it hesitates.
               Market enters freefall.
    """
    rising = [22.0, 23.5, 25.0, 26.5, 28.0, 29.5, 31.0]
    events = [
        ScenarioEvent(tick=i + 1, action="price_inject", params={"price": p})
        for i, p in enumerate(rising)
    ]
    events.append(
        ScenarioEvent(tick=9, action="price_inject", params={"price": 18.0})  # reversal
    )
    return ScenarioRunner(events)


NAMED_SCENARIOS: dict[str, ScenarioRunner] = {
    "hoarding_crash":      hoarding_crash_scenario(),
    "panic_cascade":       panic_cascade_scenario(),
    "speculator_bubble":   speculator_bubble_scenario(),
}
