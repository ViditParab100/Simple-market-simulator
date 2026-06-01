"""
Per-archetype activation signal functions.

Each function takes the current market state and the agent's personal state,
and returns a raw signal in [0, 1] representing how strongly that archetype
wants to take control this tick.

These are combined with personality base weights inside PersonalityProfile
to produce the final activation score.
"""
from __future__ import annotations
from enum import Enum
from market.models import MarketState


class ArchetypeTag(Enum):
    MARKET_MAKER = "MarketMaker"
    SPECULATOR   = "Speculator"
    HOARDER      = "Hoarder"
    PANIC        = "Panic"
    RATIONAL     = "Rational"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def market_maker_signal(state: MarketState, inventory: int, cash: float,
                        max_inventory: int = 80, min_inventory: int = 10) -> float:
    """
    Strong when the spread is wide (opportunity to earn) and inventory is balanced.
    Weakens when inventory is very skewed or the market has strong momentum.
    """
    if state.best_bid is None or state.best_ask is None:
        return 0.3  # still willing to quote in a thin market

    spread = (state.best_ask - state.best_bid) / state.best_ask
    spread_signal = _clamp(spread / 0.10)  # normalised: 10% spread = full signal

    # Inventory balance: 1.0 when perfectly centred, drops toward edges
    inv_ratio = inventory / max_inventory if max_inventory > 0 else 0.5
    balance = 1.0 - abs(inv_ratio - 0.5) * 2   # 1.0 at midpoint, 0.0 at extremes

    # Momentum dampens market-making (hard to quote in a fast-moving market)
    momentum_penalty = _clamp(abs(state.price_momentum) * 5)

    raw = spread_signal * 0.5 + balance * 0.5 - momentum_penalty * 0.3
    return _clamp(raw)


def speculator_signal(state: MarketState, inventory: int, cash: float,
                      max_position: int = 30, momentum_threshold: float = 0.02) -> float:
    """
    Strong when there is clear price momentum (up or down).
    Scales with the magnitude of momentum above the threshold.
    """
    if len(state.price_history) < 2:
        return 0.0

    momentum = abs(state.price_momentum)
    if momentum < momentum_threshold:
        return 0.0

    # How far above threshold is the momentum?
    excess = (momentum - momentum_threshold) / (0.20 - momentum_threshold)  # normalise to 20% ceiling

    # Position room: less signal when already maxed out
    if state.price_momentum > 0:
        room_ratio = max(0.0, (max_position - inventory) / max_position)
    else:
        room_ratio = 1.0 if inventory > 0 else 0.0

    return _clamp(excess * room_ratio)


def hoarder_signal(state: MarketState, inventory: int, cash: float,
                   hoard_target: int = 100) -> float:
    """
    Strong when scarcity is rising and the agent is still below their hoard target.
    Fades once the target is met.
    """
    shortfall_ratio = max(0.0, (hoard_target - inventory) / hoard_target)
    scarcity_bonus  = state.scarcity_index  # 0.0 = all supply, 1.0 = all demand

    return _clamp(shortfall_ratio * 0.6 + scarcity_bonus * 0.4)


def panic_signal(state: MarketState, inventory: int, cash: float,
                 panic_threshold: float = -0.10,
                 cash_floor: float = 50.0) -> float:
    """
    Strong when price is falling hard, cash is critically low, or recent
    momentum is sharply negative. A stack of bad signals drives it to 1.0.
    """
    if len(state.price_history) < 2:
        return 0.0

    momentum = state.price_momentum

    # Price drop component
    drop_ratio = _clamp(abs(min(0.0, momentum)) / abs(panic_threshold))

    # Cash pressure (0 = comfortable, 1 = nearly broke)
    cash_pressure = _clamp(1.0 - (cash / max(cash_floor, 1.0))) if cash < cash_floor * 3 else 0.0

    # Only matters if actually holding inventory worth worrying about
    has_inventory = 1.0 if inventory > 0 else 0.0

    return _clamp((drop_ratio * 0.6 + cash_pressure * 0.4) * has_inventory)


def rational_signal(state: MarketState, inventory: int, cash: float,
                    fair_value_window: int = 10, margin: float = 0.05) -> float:
    """
    Strong when price has meaningfully deviated from fair value (either direction).
    Zero when there is not enough price history.
    """
    if len(state.price_history) < 2:
        return 0.0

    window = state.price_history[-fair_value_window:]
    fv = sum(window) / len(window)
    price = state.last_price or fv

    deviation = abs((price - fv) / fv)
    if deviation < margin:
        return 0.0

    # Scale: deviation at 2x margin = full signal
    return _clamp((deviation - margin) / margin)


# Registry so PersonalityProfile can look up by tag
SIGNAL_FN = {
    ArchetypeTag.MARKET_MAKER: market_maker_signal,
    ArchetypeTag.SPECULATOR:   speculator_signal,
    ArchetypeTag.HOARDER:      hoarder_signal,
    ArchetypeTag.PANIC:        panic_signal,
    ArchetypeTag.RATIONAL:     rational_signal,
}
