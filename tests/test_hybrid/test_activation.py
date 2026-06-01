"""
Tests for per-archetype activation signal functions.
Each function must return a value in [0, 1] and respond correctly
to the market conditions that are supposed to trigger it.
"""
import pytest
from market.models import MarketState
from agents.hybrid.activation import (
    market_maker_signal,
    speculator_signal,
    hoarder_signal,
    panic_signal,
    rational_signal,
)


def state(
    last_price: float = 20.0,
    best_bid: float | None = 19.5,
    best_ask: float | None = 20.5,
    bid_depth: int = 50,
    ask_depth: int = 50,
    price_history: list[float] | None = None,
) -> MarketState:
    return MarketState(
        tick=1,
        last_price=last_price,
        best_bid=best_bid,
        best_ask=best_ask,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        price_history=price_history or [],
    )

def uptrend() -> MarketState:
    return state(last_price=22.0, price_history=[18.0, 19.0, 20.0, 21.0, 22.0])

def downtrend() -> MarketState:
    return state(last_price=16.0, price_history=[20.0, 19.0, 18.0, 17.0, 16.0])

def flat() -> MarketState:
    return state(last_price=20.0, price_history=[20.0] * 6)


# ── output range ───────────────────────────────────────────────────────────────

def test_all_signals_in_range():
    """Every signal function must return a value in [0, 1]."""
    states = [uptrend(), downtrend(), flat(), state(price_history=[])]
    fns = [
        lambda s: market_maker_signal(s, 40, 600),
        lambda s: speculator_signal(s, 10, 400),
        lambda s: hoarder_signal(s, 20, 800),
        lambda s: panic_signal(s, 30, 300),
        lambda s: rational_signal(s, 25, 500),
    ]
    for fn in fns:
        for s in states:
            result = fn(s)
            assert 0.0 <= result <= 1.0, f"{fn} returned {result} out of [0,1]"


# ── MarketMaker signal ─────────────────────────────────────────────────────────

def test_mm_signal_higher_with_wide_spread():
    narrow = state(best_bid=19.9, best_ask=20.1)   # 1% spread
    wide   = state(best_bid=18.0, best_ask=22.0)   # 20% spread
    assert market_maker_signal(wide, 40, 600) > market_maker_signal(narrow, 40, 600)

def test_mm_signal_lower_with_imbalanced_inventory():
    balanced   = market_maker_signal(flat(), inventory=40, cash=600, max_inventory=80)
    imbalanced = market_maker_signal(flat(), inventory=79, cash=600, max_inventory=80)
    assert balanced > imbalanced

def test_mm_signal_with_no_quotes():
    s = state(best_bid=None, best_ask=None)
    result = market_maker_signal(s, 40, 600)
    assert 0.0 <= result <= 1.0


# ── Speculator signal ──────────────────────────────────────────────────────────

def test_speculator_zero_in_flat_market():
    assert speculator_signal(flat(), 10, 400, momentum_threshold=0.02) == 0.0

def test_speculator_zero_with_no_history():
    assert speculator_signal(state(price_history=[]), 10, 400) == 0.0

def test_speculator_positive_in_uptrend():
    assert speculator_signal(uptrend(), 10, 400, momentum_threshold=0.02) > 0.0

def test_speculator_positive_in_downtrend():
    assert speculator_signal(downtrend(), 20, 400, momentum_threshold=0.02) > 0.0

def test_speculator_zero_when_maxed_long():
    # In uptrend but at max position — no room to buy
    assert speculator_signal(uptrend(), inventory=30, cash=400, max_position=30) == 0.0

def test_speculator_scales_with_momentum_strength():
    mild_up   = state(last_price=20.5, price_history=[20.0, 20.1, 20.2, 20.3, 20.5])
    strong_up = uptrend()
    mild_sig   = speculator_signal(mild_up,   10, 400, momentum_threshold=0.02)
    strong_sig = speculator_signal(strong_up, 10, 400, momentum_threshold=0.02)
    assert strong_sig >= mild_sig


# ── Hoarder signal ─────────────────────────────────────────────────────────────

def test_hoarder_higher_when_below_target():
    below = hoarder_signal(flat(), inventory=20,  cash=800, hoard_target=100)
    at    = hoarder_signal(flat(), inventory=100, cash=800, hoard_target=100)
    assert below > at

def test_hoarder_scales_with_scarcity():
    scarce  = state(bid_depth=90, ask_depth=10)   # scarcity_index = 0.9
    ample   = state(bid_depth=10, ask_depth=90)   # scarcity_index = 0.1
    assert hoarder_signal(scarce, 20, 800) > hoarder_signal(ample, 20, 800)

def test_hoarder_zero_when_shortfall_zero_and_ample():
    # At target, low scarcity — signal should be near-zero
    result = hoarder_signal(state(bid_depth=10, ask_depth=90), inventory=100, cash=800, hoard_target=100)
    assert result < 0.15


# ── Panic signal ───────────────────────────────────────────────────────────────

def test_panic_zero_in_flat_market():
    assert panic_signal(flat(), 30, 500, panic_threshold=-0.10) == 0.0

def test_panic_zero_with_no_history():
    assert panic_signal(state(price_history=[]), 30, 500) == 0.0

def test_panic_positive_in_sharp_downtrend():
    assert panic_signal(downtrend(), 30, 500, panic_threshold=-0.10) > 0.0

def test_panic_zero_when_no_inventory():
    # Can't panic-sell what you don't have
    assert panic_signal(downtrend(), inventory=0, cash=500) == 0.0

def test_panic_amplified_by_low_cash():
    rich  = panic_signal(downtrend(), 30, cash=1000.0, cash_floor=50.0)
    broke = panic_signal(downtrend(), 30, cash=10.0,   cash_floor=50.0)
    assert broke > rich

def test_panic_higher_in_steeper_drop():
    mild_drop   = state(last_price=18.5, price_history=[20.0, 19.5, 19.0, 18.8, 18.5])
    steep_drop  = downtrend()
    assert panic_signal(steep_drop, 30, 300) >= panic_signal(mild_drop, 30, 300)


# ── Rational signal ────────────────────────────────────────────────────────────

def test_rational_zero_with_no_history():
    assert rational_signal(state(price_history=[]), 25, 500) == 0.0

def test_rational_zero_when_price_near_fair_value():
    assert rational_signal(flat(), 25, 500, margin=0.05) == 0.0

def test_rational_positive_when_overvalued():
    s = state(last_price=24.0, price_history=[20.0] * 5)
    assert rational_signal(s, 25, 500, margin=0.05) > 0.0

def test_rational_positive_when_undervalued():
    s = state(last_price=16.0, price_history=[20.0] * 5)
    assert rational_signal(s, 25, 500, margin=0.05) > 0.0

def test_rational_scales_with_deviation():
    small_dev = state(last_price=21.5, price_history=[20.0] * 5)  # +7.5%
    large_dev = state(last_price=25.0, price_history=[20.0] * 5)  # +25%
    assert rational_signal(large_dev, 25, 500) > rational_signal(small_dev, 25, 500)
