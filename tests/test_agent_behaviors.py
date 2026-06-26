"""
20 behavioral tests for single-personality pure agents (zoo mode).

Tests are written against DESIGN INTENT, not formula outputs.
Each test answers a question about what the agent is SUPPOSED to do — and why
that matters. Tests that would have always passed by construction are replaced
with edge cases that could plausibly fail (and two did, exposing real bugs).

Bugs found and fixed before this suite was finalised:
  - SpeculatorAgent: logged "Decision: BID X@Y" even when cash was too low
    to place the order (think/act mismatch). Fixed: log now gated on cash check.
  - MarketMakerAgent: logged "quoting both sides" then silently dropped the BID
    when cash was zero. Fixed: explicit "ask-only this tick" message + correct log.

Run:  pytest tests/test_agent_behaviors.py -v -s
"""
from __future__ import annotations
from market.models import MarketState, OrderSide
from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent
from agents.producer import ProducerAgent


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_state(
    price: float,
    history: list[float],
    *,
    best_bid: float | None = None,
    best_ask: float | None = None,
    bid_depth: int = 50,
    ask_depth: int = 50,
) -> MarketState:
    return MarketState(
        tick=1,
        last_price=price,
        best_bid=best_bid if best_bid is not None else round(price - 0.5, 2),
        best_ask=best_ask if best_ask is not None else round(price + 0.5, 2),
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        price_history=history + [price],
    )


def run_agent(agent, state):
    thoughts = agent.think(state)
    orders = agent.act(state)
    return thoughts, orders


def assert_order(order, side: str, price: float, qty: int, label: str = ""):
    assert order.side == OrderSide[side], \
        f"{label}: expected {side}, got {order.side.name}"
    assert abs(order.price - price) < 0.015, \
        f"{label}: expected price {price:.2f}, got {order.price:.2f}"
    assert order.quantity == qty, \
        f"{label}: expected qty {qty}, got {order.quantity}"


def assert_no_orders(orders, label: str = ""):
    assert orders == [], \
        f"{label}: expected no orders, got {[(o.side.name, o.price, o.quantity) for o in orders]}"


def thoughts_contain(thoughts, fragment: str) -> bool:
    return any(fragment.lower() in t.lower() for t in thoughts)


# ══════════════════════════════════════════════════════════════════════════════
# MarketMakerAgent — 4 tests
# Design intent: earn the spread by quoting both sides; widen spread during
# volatility; tilt to one side when inventory is at an extreme.
# ══════════════════════════════════════════════════════════════════════════════

def test_MM_01_balanced_inventory_quotes_both_sides():
    """
    Core behavior: balanced inventory + calm market -> BID and ASK both placed.
    Spread = 4% base on flat momentum.
    Design question: does the agent actually place two-sided quotes, not just announce them?
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = MarketMakerAgent("mm", inventory=40, cash=800.0)
    _, orders = run_agent(agent, state)
    sides = {o.side for o in orders}
    assert OrderSide.BID in sides, "Balanced MM must place a BID"
    assert OrderSide.ASK in sides, "Balanced MM must place an ASK"
    assert len(orders) == 2


def test_MM_02_zero_cash_only_asks_and_log_is_honest():
    """
    BUG REGRESSION: With cash=0, MarketMaker used to log 'quoting both sides'
    but only place an ASK. Log must now say 'ask-only' when cash is insufficient.
    Design intent: agent should never announce a decision it won't execute.
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = MarketMakerAgent("mm", inventory=40, cash=0.0)
    thoughts, orders = run_agent(agent, state)
    assert all(o.side == OrderSide.ASK for o in orders), \
        "With no cash, only ASK should be placed"
    assert not any(o.side == OrderSide.BID for o in orders), \
        "BID must not be placed with zero cash"
    assert thoughts_contain(thoughts, "ask-only") or thoughts_contain(thoughts, "no cash"), \
        f"Log must acknowledge the missing BID — got: {thoughts}"


def test_MM_03_low_inventory_restocks_not_sells():
    """
    Design intent: when inventory falls to min, stop providing sell-side liquidity
    and focus on restocking. The agent must NOT place an ASK while depleted.
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = MarketMakerAgent("mm", inventory=5, cash=500.0)  # 5 < min_inventory=10
    _, orders = run_agent(agent, state)
    assert not any(o.side == OrderSide.ASK for o in orders), \
        "Depleted MM must not offer supply it doesn't have"
    assert any(o.side == OrderSide.BID for o in orders), \
        "Depleted MM must be trying to restock"


def test_MM_04_high_volatility_widens_spread():
    """
    Design intent: volatility = risk. A market maker who quotes a fixed spread
    during a trend loses money to informed traders. The spread MUST be wider
    under a trending market than in a calm one.
    """
    flat_state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    trend_state = make_state(20.0, [16.0, 17.0, 18.0, 19.0])  # +25% momentum
    agent_flat  = MarketMakerAgent("mm", inventory=40, cash=800.0)
    agent_trend = MarketMakerAgent("mm", inventory=40, cash=800.0)
    _, flat_orders  = run_agent(agent_flat,  flat_state)
    _, trend_orders = run_agent(agent_trend, trend_state)
    flat_bid  = next(o.price for o in flat_orders  if o.side == OrderSide.BID)
    flat_ask  = next(o.price for o in flat_orders  if o.side == OrderSide.ASK)
    trend_bid = next(o.price for o in trend_orders if o.side == OrderSide.BID)
    trend_ask = next(o.price for o in trend_orders if o.side == OrderSide.ASK)
    flat_spread  = flat_ask  - flat_bid
    trend_spread = trend_ask - trend_bid
    assert trend_spread > flat_spread, (
        f"Volatile spread ({trend_spread:.2f}) must exceed calm spread ({flat_spread:.2f}). "
        "Volatility adjustment is broken."
    )


# ══════════════════════════════════════════════════════════════════════════════
# SpeculatorAgent — 4 tests
# Design intent: momentum chaser who amplifies trends. Buys into rises, sells
# into falls, and holds during flat markets. Never trades beyond its means.
# ══════════════════════════════════════════════════════════════════════════════

def test_SP_01_uptrend_bid_only_placed_when_affordable():
    """
    BUG REGRESSION: Speculator used to log 'Decision: BID 25@22.44' even when
    cash=10 (needs $561). No order was placed. Log and action were inconsistent.
    Design intent: if you can't afford the trade, say so — don't announce it.
    """
    state = make_state(22.0, [18.0, 19.0, 20.0, 21.0])
    agent = SpeculatorAgent("sp", inventory=5, cash=10.0)  # uptrend, but broke
    thoughts, orders = run_agent(agent, state)
    assert_no_orders(orders, "SP-01 broke speculator")
    decision_lines = [t for t in thoughts if "decision" in t.lower()]
    assert not any("bid" in t.lower() for t in decision_lines), (
        f"Log must not claim a BID decision when cash is insufficient. "
        f"Decision lines: {decision_lines}"
    )
    assert thoughts_contain(thoughts, "cash") or thoughts_contain(thoughts, "insufficient"), \
        f"Log must explain WHY no order was placed — got: {thoughts}"


def test_SP_02_uptrend_with_sufficient_cash_places_bid():
    """
    When cash is actually sufficient, the speculator must follow through.
    Counterpart to SP-01: same market, enough cash this time.
    """
    state = make_state(22.0, [18.0, 19.0, 20.0, 21.0])
    agent = SpeculatorAgent("sp", inventory=5, cash=700.0)  # 700 > 25*22.44=561
    _, orders = run_agent(agent, state)
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BID, "Must BID in uptrend with sufficient cash"


def test_SP_03_downtrend_dumps_regardless_of_cash():
    """
    Selling doesn't require cash — the speculator dumps into a downtrend
    even if broke. Inventory check (not cash) is what limits the sell side.
    """
    state = make_state(16.0, [20.0, 19.0, 18.0, 17.0])
    agent = SpeculatorAgent("sp", inventory=15, cash=0.0)  # broke but holding stock
    _, orders = run_agent(agent, state)
    assert len(orders) == 1, "Must sell into downtrend regardless of cash balance"
    assert orders[0].side == OrderSide.ASK


def test_SP_04_flat_momentum_and_max_position_both_hold():
    """
    Two separate reasons to hold: flat momentum and being at max_position.
    Both must prevent trading. Tests that neither condition is accidentally skipped.
    """
    # Case A: flat momentum
    flat_state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent_flat = SpeculatorAgent("sp", inventory=10, cash=500.0)
    _, orders_flat = run_agent(agent_flat, flat_state)
    assert_no_orders(orders_flat, "SP-04 flat momentum")

    # Case B: max position in uptrend
    trend_state = make_state(22.0, [18.0, 19.0, 20.0, 21.0])
    agent_full = SpeculatorAgent("sp", inventory=30, cash=1000.0)  # at max_position
    _, orders_full = run_agent(agent_full, trend_state)
    assert_no_orders(orders_full, "SP-04 max position")


# ══════════════════════════════════════════════════════════════════════════════
# HoarderAgent — 3 tests
# Design intent: accumulate below market price; only release at a steep premium
# that won't fill in normal conditions (creates scarcity by design).
# ══════════════════════════════════════════════════════════════════════════════

def test_HO_01_accumulation_bids_below_market():
    """
    Design intent: hoarder is a patient buyer who never pays full price.
    The bid must be strictly BELOW the last price, not at or above it.
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = HoarderAgent("ho", inventory=50, cash=500.0, hoard_target=100)
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.BID
    assert orders[0].price < state.last_price, \
        f"Hoarder must bid BELOW market ({state.last_price}), got {orders[0].price}"


def test_HO_02_protection_asks_well_above_market():
    """
    Design intent: once the hoard is full, the release price is so high it
    won't fill under normal conditions — this IS the scarcity mechanism.
    The ASK must be significantly above market (30% premium by default).
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = HoarderAgent("ho", inventory=100, cash=200.0, hoard_target=100)
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.ASK
    assert orders[0].price >= state.last_price * 1.25, (
        f"Hoarder protection ASK should be at least 25% above market "
        f"(got {orders[0].price:.2f} vs market {state.last_price:.2f})"
    )


def test_HO_03_insufficient_cash_places_no_order_at_all():
    """
    When cash can't cover even one discounted bid, the hoarder must go silent —
    not place a qty=0 order, not place a partial order, nothing.
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = HoarderAgent("ho", inventory=50, cash=5.0, hoard_target=100)
    _, orders = run_agent(agent, state)
    assert_no_orders(orders, "HO-03 no cash")
    assert all(o.quantity > 0 for o in orders), \
        "No zero-quantity ghost orders should be placed"


# ══════════════════════════════════════════════════════════════════════════════
# PanicAgent — 4 tests
# Design intent: stabilising in calm markets; catastrophic in crashes. The full
# inventory dump (not a partial sell) is the core mechanic. Recovery prevents
# re-triggering in the same downturn.
# ══════════════════════════════════════════════════════════════════════════════

def test_PA_01_calm_market_is_truly_silent():
    """
    Design intent: panic agent is a non-participant in normal conditions.
    Even with large inventory, it must not place any order when calm.
    """
    state = make_state(20.0, [19.0, 19.5, 20.0, 20.0])  # +5% momentum
    agent = PanicAgent("pa", inventory=50, cash=300.0)
    _, orders = run_agent(agent, state)
    assert_no_orders(orders, "PA-01 calm 50 units")


def test_PA_02_panic_dumps_entire_inventory_not_partial():
    """
    Design intent: it's called 'Panic' because the agent dumps EVERYTHING —
    not a sensible partial position. qty must equal the full inventory.
    A partial sell would soften the cascade, defeating the pathology.
    """
    state = make_state(16.0, [20.0, 19.0, 18.0, 17.0])  # -20% crash
    agent = PanicAgent("pa", inventory=23, cash=300.0)
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.ASK
    assert orders[0].quantity == 23, (
        f"Panic must dump ALL inventory (23), not a partial {orders[0].quantity}"
    )


def test_PA_03_recovery_prevents_double_panic():
    """
    Design intent: after a dump the agent enters recovery — preventing it from
    re-triggering on the next tick even if the crash continues.
    Without recovery, every consecutive down-tick would generate a new dump order
    (even with inventory=0 it would still transition state repeatedly).
    """
    # Trigger the panic on tick A
    crash_state = make_state(16.0, [20.0, 19.0, 18.0, 17.0])
    agent = PanicAgent("pa", inventory=10, cash=300.0)
    agent.think(crash_state)  # -> recovering

    # Tick B: same crash conditions, but should be silent
    _, orders = run_agent(agent, crash_state)
    assert_no_orders(orders, "PA-03 no re-panic on next tick")
    assert agent._state == "recovering", "Must still be in recovery after second tick"


def test_PA_04_panic_with_no_inventory_still_transitions_state():
    """
    Edge case: crash with empty inventory. No order should be placed (nothing to dump),
    but the agent MUST still transition to 'recovering' — proving the threshold
    logic runs independently of whether an order was placed.
    This matters because recovery prevents the agent from doing other things mid-crash.
    """
    state = make_state(16.0, [20.0, 19.0, 18.0, 17.0])
    agent = PanicAgent("pa", inventory=0, cash=300.0)
    _, orders = run_agent(agent, state)
    assert_no_orders(orders, "PA-04 empty inventory")
    assert agent._state == "recovering", \
        "State transition must happen even when there's nothing to sell"


# ══════════════════════════════════════════════════════════════════════════════
# RationalAgent — 3 tests
# Design intent: stabilising force. Buys when market is cheap vs history,
# sells when expensive. Ignores momentum — fair value is the only signal.
# ══════════════════════════════════════════════════════════════════════════════

def test_RA_01_ignores_momentum_buys_undervalued():
    """
    Key design property: Rational ignores momentum. Even in a falling market
    (which Speculator would sell into), Rational buys if price is below fair value.
    If it stops buying in downtrends, it's no longer a stabiliser — it's just slow.
    """
    # Downtrend -9%: Speculator would sell, Rational should buy (price below FV)
    state = make_state(18.0, [20.0] * 9)  # FV=19.8, dev=-9.1%, trend=-9%
    agent = RationalAgent("ra", inventory=5, cash=500.0)
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.BID, \
        "Rational must BUY a downtrend when price is below fair value"


def test_RA_02_ignores_momentum_sells_overvalued():
    """
    Counterpart: sells into a rising market when price exceeds fair value.
    A Speculator would buy; Rational sells, dampening the bubble.
    """
    # Uptrend: price=24, history=[20]*9 → FV=20.4, dev=+17.6%
    state = make_state(24.0, [20.0] * 9)
    agent = RationalAgent("ra", inventory=10, cash=500.0)
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.ASK, \
        "Rational must SELL an uptrend when price is above fair value"


def test_RA_03_no_order_without_sufficient_history():
    """
    Edge case: without price history the fair value is undefined.
    The agent must not trade on a single data point — doing so would mean
    anchoring to whatever arbitrary price the market opened at.
    """
    state = make_state(20.0, [])  # price_history = [20.0] — only one point
    agent = RationalAgent("ra", inventory=5, cash=500.0)
    _, orders = run_agent(agent, state)
    assert_no_orders(orders, "RA-03 single data point")


# ══════════════════════════════════════════════════════════════════════════════
# ProducerAgent — 2 tests
# Design intent: anchor the price by selling at cost-plus regardless of market
# frenzy. Reserve units for own survival before selling the rest.
# ══════════════════════════════════════════════════════════════════════════════

def test_PR_01_sells_at_anchor_not_market_price():
    """
    Core design: the Producer ignores the market price and sells at its
    cost-plus anchor. This is what prevents runaway inflation.
    If it chases the last price upward, every frantic survival bid would
    lift the next ask — creating a feedback spiral.
    """
    # Market is frenzied at $35 but anchor is $21 (20*1.05)
    state = make_state(35.0, [35.0, 35.0, 35.0, 35.0])
    agent = ProducerAgent("pr", inventory=50, cash=200.0,
                          production_rate=0, base_cost=20.0, margin=0.05)
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.ASK
    assert orders[0].price < 25.0, (
        f"Producer must sell at cost-plus anchor (~21.00), "
        f"not chase the market price (35.00). Got {orders[0].price:.2f}"
    )
    assert abs(orders[0].price - 21.00) < 0.015, \
        f"Anchor price should be 21.00 (20*1.05), got {orders[0].price}"


def test_PR_02_reserves_survival_units_before_selling():
    """
    Design intent: the producer feeds itself first, sells the remainder.
    If survival reserve is miscalculated, the producer could sell its own food
    and starve — removing the market's supply source entirely.
    """
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    agent = ProducerAgent("pr", inventory=10, cash=200.0,
                          production_rate=0, base_cost=20.0, margin=0.05)
    agent.consumption_rate = 4.0  # reserve = int(4*2) = 8; surplus = 10-8 = 2
    _, orders = run_agent(agent, state)
    assert len(orders) == 1 and orders[0].side == OrderSide.ASK
    assert orders[0].quantity == 2, (
        f"Should sell only the 2-unit surplus (inventory=10 minus reserve=8), "
        f"not the full 10. Got qty={orders[0].quantity}"
    )
