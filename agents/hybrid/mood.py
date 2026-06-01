"""
Mood modifier layer.

Mood modifiers are deltas added to (or subtracted from) an archetype's
raw activation score before the contest is decided. They capture the
psychological state of the NPC: confidence from a winning streak, fear
from losses, contagion from watching a neighbour panic-sell.

Each modifier returns a dict[ArchetypeTag, float] — positive values
boost that archetype, negative values suppress it.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from market.models import Trade
from .activation import ArchetypeTag


@dataclass
class MoodState:
    """Tracks the information needed to compute mood modifiers each tick."""
    recent_trades: list[Trade] = field(default_factory=list)   # agent's own trades
    contagion_pulse: float = 0.0                                # set externally by contagion tracker

    # --- streak helpers ---

    def record_trade(self, trade: Trade, agent_id: str):
        self.recent_trades.append(trade)
        if len(self.recent_trades) > 10:
            self.recent_trades.pop(0)

    def _profit_on(self, trade: Trade, agent_id: str, prev_price: float) -> float:
        if trade.buyer_id == agent_id:
            return prev_price - trade.price  # profit if bought below some reference
        elif trade.seller_id == agent_id:
            return trade.price - prev_price
        return 0.0

    def winning_streak(self, agent_id: str, last_price: float) -> int:
        """Count consecutive profitable trades (last N, up to 3)."""
        streak = 0
        for trade in reversed(self.recent_trades[-3:]):
            if trade.buyer_id == agent_id and trade.price < last_price:
                streak += 1
            elif trade.seller_id == agent_id and trade.price > last_price:
                streak += 1
            else:
                break
        return streak

    def losing_streak(self, agent_id: str, last_price: float) -> int:
        """Count consecutive loss-making trades (last N, up to 3)."""
        streak = 0
        for trade in reversed(self.recent_trades[-3:]):
            if trade.buyer_id == agent_id and trade.price > last_price:
                streak += 1
            elif trade.seller_id == agent_id and trade.price < last_price:
                streak += 1
            else:
                break
        return streak


def streak_modifier(mood: MoodState, agent_id: str,
                    last_price: float) -> dict[ArchetypeTag, float]:
    """
    Winning streak: boosts Speculator, suppresses Panic.
    Losing streak: boosts Panic, suppresses Rational.
    """
    deltas: dict[ArchetypeTag, float] = {}
    wins  = mood.winning_streak(agent_id, last_price)
    losses = mood.losing_streak(agent_id, last_price)

    if wins > 0:
        boost = wins * 0.08
        deltas[ArchetypeTag.SPECULATOR] = deltas.get(ArchetypeTag.SPECULATOR, 0.0) + boost
        deltas[ArchetypeTag.PANIC]      = deltas.get(ArchetypeTag.PANIC,      0.0) - boost * 0.5

    if losses > 0:
        boost = losses * 0.10
        deltas[ArchetypeTag.PANIC]     = deltas.get(ArchetypeTag.PANIC,     0.0) + boost
        deltas[ArchetypeTag.RATIONAL]  = deltas.get(ArchetypeTag.RATIONAL,  0.0) - boost * 0.4
        deltas[ArchetypeTag.SPECULATOR]= deltas.get(ArchetypeTag.SPECULATOR,0.0) - boost * 0.3

    return deltas


def volatility_modifier(price_history: list[float]) -> dict[ArchetypeTag, float]:
    """
    High volatility amplifies whichever instinct is loudest:
    boosts Speculator and Panic, suppresses MarketMaker and Rational.
    """
    if len(price_history) < 3:
        return {}

    window = price_history[-5:]
    avg    = sum(window) / len(window)
    stddev = (sum((p - avg) ** 2 for p in window) / len(window)) ** 0.5
    vol    = stddev / avg if avg > 0 else 0.0  # coefficient of variation

    # Normalise: 5% CV = moderate, 10%+ = high
    magnitude = min(vol / 0.10, 1.0)

    return {
        ArchetypeTag.SPECULATOR:   magnitude * 0.15,
        ArchetypeTag.PANIC:        magnitude * 0.12,
        ArchetypeTag.MARKET_MAKER: -magnitude * 0.10,
        ArchetypeTag.RATIONAL:     -magnitude * 0.08,
    }


def cash_pressure_modifier(cash: float,
                            cash_floor: float = 50.0) -> dict[ArchetypeTag, float]:
    """
    Very low cash suppresses Hoarder (can't hoard without money)
    and amplifies Panic (desperation to liquidate).
    """
    if cash >= cash_floor * 3:
        return {}

    pressure = max(0.0, 1.0 - cash / (cash_floor * 3))
    return {
        ArchetypeTag.PANIC:   pressure * 0.20,
        ArchetypeTag.HOARDER: -pressure * 0.15,
    }


def contagion_modifier(pulse: float) -> dict[ArchetypeTag, float]:
    """
    When a neighbour has just panic-dumped, a contagion pulse is broadcast.
    It boosts Panic for all NPCs this tick.
    """
    if pulse <= 0:
        return {}
    return {ArchetypeTag.PANIC: min(pulse, 0.30)}


def compute_mood_deltas(
    mood: MoodState,
    agent_id: str,
    cash: float,
    price_history: list[float],
    last_price: float,
) -> dict[ArchetypeTag, float]:
    """Aggregate all mood modifiers into a single delta map."""
    combined: dict[ArchetypeTag, float] = {}

    for source in [
        streak_modifier(mood, agent_id, last_price),
        volatility_modifier(price_history),
        cash_pressure_modifier(cash),
        contagion_modifier(mood.contagion_pulse),
    ]:
        for tag, delta in source.items():
            combined[tag] = combined.get(tag, 0.0) + delta

    return combined
