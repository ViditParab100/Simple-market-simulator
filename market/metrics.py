"""
Phase 5 — Metrics.

Collects per-tick market data and computes a final summary including:
  - Price: start/end/min/max, volatility, max drawdown
  - Activity: total trades, total volume, ticks with trades
  - Wealth: Gini coefficient at start vs end
  - Per-agent: net worth delta, trade count

The MetricsCollector is independent of the event bus — it is
called directly by the engine at the end of each tick.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base import Agent


# ── Pure metric functions ─────────────────────────────────────────────────────

def gini(values: list[float]) -> float:
    """
    Gini coefficient of a distribution (0 = perfect equality, 1 = maximum inequality).
    Negative values are clamped to 0 before calculation.
    """
    vals = sorted(max(0.0, v) for v in values)
    n    = len(vals)
    if n == 0:
        return 0.0
    total = sum(vals)
    if total == 0.0:
        return 0.0
    numer = sum((i + 1) * v for i, v in enumerate(vals))
    return (2 * numer) / (n * total) - (n + 1) / n


def price_volatility(prices: list[float]) -> float:
    """Standard deviation of a price series (population stddev)."""
    if len(prices) < 2:
        return 0.0
    avg      = sum(prices) / len(prices)
    variance = sum((p - avg) ** 2 for p in prices) / len(prices)
    return variance ** 0.5


def max_drawdown(prices: list[float]) -> float:
    """
    Maximum peak-to-trough decline over the price series.
    Returns a positive fraction (0.20 = 20% drawdown).
    """
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    worst = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak if peak > 0 else 0.0
        if dd > worst:
            worst = dd
    return worst


# ── Per-tick record ───────────────────────────────────────────────────────────

@dataclass
class TickRecord:
    tick:        int
    price:       float | None
    bid_depth:   int
    ask_depth:   int
    trade_count: int
    volume:      int


# ── Summary ───────────────────────────────────────────────────────────────────

@dataclass
class AgentSummary:
    agent_id:      str
    net_worth_start: float
    net_worth_end:   float
    trade_count:     int

    @property
    def pnl(self) -> float:
        return self.net_worth_end - self.net_worth_start

    @property
    def pnl_pct(self) -> float:
        if self.net_worth_start == 0:
            return 0.0
        return self.pnl / self.net_worth_start


@dataclass
class RunMetrics:
    # Price
    price_start:      float
    price_end:        float
    price_min:        float
    price_max:        float
    volatility:       float
    max_drawdown_pct: float   # 0.20 = 20%

    # Activity
    total_ticks:       int
    ticks_with_trades: int
    total_trades:      int
    total_volume:      int

    # Wealth distribution
    gini_start: float
    gini_end:   float

    # Per-agent
    agents: list[AgentSummary] = field(default_factory=list)

    @property
    def price_change_pct(self) -> float:
        if self.price_start == 0:
            return 0.0
        return (self.price_end - self.price_start) / self.price_start


# ── Collector ─────────────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Called by the engine each tick and at the end of a run.
    Holds no reference to the engine — data is passed in explicitly.
    """

    def __init__(self):
        self._records: list[TickRecord] = []
        self._initial_worths: dict[str, float] = {}

    def record_initial(self, agents: list[Agent], last_price: float):
        """Call once before the simulation starts."""
        price = last_price or 0.0
        self._initial_worths = {
            a.agent_id: a.net_worth(price) for a in agents
        }

    def record_tick(
        self,
        tick:        int,
        last_price:  float | None,
        bid_depth:   int,
        ask_depth:   int,
        trade_count: int,
        volume:      int,
    ):
        self._records.append(TickRecord(
            tick=tick,
            price=last_price,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            trade_count=trade_count,
            volume=volume,
        ))

    def compute(self, agents: list[Agent], last_price: float | None) -> RunMetrics:
        price       = last_price or 0.0
        all_prices  = [r.price for r in self._records if r.price is not None]
        price_start = all_prices[0]  if all_prices else price
        price_end   = all_prices[-1] if all_prices else price

        worths_end  = [a.net_worth(price) for a in agents]
        worths_start = list(self._initial_worths.values())

        agent_sums = [
            AgentSummary(
                agent_id=a.agent_id,
                net_worth_start=self._initial_worths.get(a.agent_id, 0.0),
                net_worth_end=a.net_worth(price),
                trade_count=a.trade_count,
            )
            for a in agents
        ]

        return RunMetrics(
            price_start      = price_start,
            price_end        = price_end,
            price_min        = min(all_prices, default=price),
            price_max        = max(all_prices, default=price),
            volatility       = price_volatility(all_prices),
            max_drawdown_pct = max_drawdown(all_prices),
            total_ticks      = len(self._records),
            ticks_with_trades= sum(1 for r in self._records if r.trade_count > 0),
            total_trades     = sum(r.trade_count for r in self._records),
            total_volume     = sum(r.volume for r in self._records),
            gini_start       = gini(worths_start),
            gini_end         = gini(worths_end),
            agents           = agent_sums,
        )
