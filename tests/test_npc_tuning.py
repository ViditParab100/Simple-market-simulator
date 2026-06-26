"""
10 behavioral test cases for fine-tuning Hybrid NPC personality weights.

Each test:
  1. Defines a precise market scenario
  2. States which archetype SHOULD dominate and why
  3. Runs the contest
  4. On failure: prints actual scores and computes the minimum weight change
     needed to make the expected archetype win

Run:  pytest tests/test_npc_tuning.py -v -s
Fix:  apply the printed weight suggestions to agents/hybrid/roster.py
"""
from __future__ import annotations
import pytest
from market.models import MarketState
from agents.hybrid.activation import ArchetypeTag
from agents.hybrid.mood import MoodState
from agents.hybrid.personality import PersonalityProfile
from agents.hybrid.npc import HybridNPC


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_state(
    price: float,
    history: list[float],
    bid_depth: int = 50,
    ask_depth: int = 50,
    best_bid: float | None = None,
    best_ask: float | None = None,
) -> MarketState:
    return MarketState(
        tick=1,
        last_price=price,
        best_bid=best_bid if best_bid is not None else price - 0.5,
        best_ask=best_ask if best_ask is not None else price + 0.5,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        price_history=history + [price],
    )


def make_npc(weights: dict[ArchetypeTag, float],
             inventory: int = 10, cash: float = 500.0,
             contagion: float = 0.0) -> HybridNPC:
    npc = HybridNPC("test", inventory, cash, PersonalityProfile(weights))
    npc.mood.contagion_pulse = contagion
    return npc


def run_contest(npc: HybridNPC, state: MarketState) -> tuple[ArchetypeTag, dict]:
    npc.think(state)
    contest = npc._last_contest
    return contest.winner, contest.scores


def weight_fix(scores: dict, expected: ArchetypeTag, raw_signals: dict,
               current_weights: dict) -> str:
    """
    Compute the minimum weight the expected archetype needs to win,
    then scale the others down proportionally.
    """
    winner_score = max(scores.values())
    sig = raw_signals.get(expected, 0.0)
    if sig <= 0:
        return f"  Cannot fix: {expected.value} raw signal is 0 -- adjust the signal function instead."

    required_w = winner_score / sig + 0.01   # just above the current winner
    required_w = min(required_w, 0.95)

    others = {t: w for t, w in current_weights.items() if t != expected}
    remaining = 1.0 - required_w
    total_other = sum(others.values()) or 1.0
    new_weights = {expected: round(required_w, 2)}
    for t, w in others.items():
        new_weights[t] = round(w / total_other * remaining, 2)

    lines = [f"  Suggested weight fix -> {expected.value}: {required_w:.2f}"]
    for t, w in new_weights.items():
        if t != expected:
            lines.append(f"    {t.value}: {current_weights[t]:.2f} -> {w:.2f}")
    return "\n".join(lines)


def assert_winner(npc: HybridNPC, state: MarketState,
                  expected: ArchetypeTag, base_weights: dict,
                  msg: str = ""):
    """
    Run the contest and assert expected archetype wins.
    On failure: print contest scores + weight fix suggestion.
    """
    winner, scores = run_contest(npc, state)
    if winner != expected:
        raw = npc._last_contest.raw_signals
        print(f"\n  FAILED: expected {expected.value}, got {winner.value}")
        print("  Contest scores:")
        for t in sorted(scores, key=lambda x: scores[x], reverse=True):
            print(f"    {t.value:<14} score={scores[t]:.3f}  raw_signal={raw.get(t,0):.3f}")
        print(weight_fix(scores, expected, raw, base_weights))
    assert winner == expected, (
        f"{msg}\n  Expected dominant: {expected.value}  Got: {winner.value}"
    )


# ── NPC weight tables (mirrors roster.py) ─────────────────────────────────────

IRIS   = {ArchetypeTag.RATIONAL: 0.50, ArchetypeTag.SPECULATOR: 0.35, ArchetypeTag.PANIC: 0.15}
MARCUS = {ArchetypeTag.HOARDER: 0.55,  ArchetypeTag.MARKET_MAKER: 0.45}   # tuned: MM 0.40->0.45
DEX    = {ArchetypeTag.PANIC: 0.50, ArchetypeTag.SPECULATOR: 0.30, ArchetypeTag.RATIONAL: 0.20}  # tuned: Panic 0.35->0.50
VERA   = {ArchetypeTag.MARKET_MAKER: 0.55, ArchetypeTag.HOARDER: 0.30, ArchetypeTag.RATIONAL: 0.15}
REX    = {ArchetypeTag.HOARDER: 0.40, ArchetypeTag.PANIC: 0.40, ArchetypeTag.SPECULATOR: 0.20}  # tuned: Panic 0.30->0.40


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1
# Iris — moderate uptrend, price barely above fair value
# Prediction: SPECULATOR wins. Momentum signal is high; rational signal is
# weak (price only 5.5% above FV, just over the 5% margin).
# If RATIONAL wins → increase Iris SPECULATOR weight.
# ══════════════════════════════════════════════════════════════════════════════
def test_01_iris_moderate_uptrend_speculator_wins():
    """Iris chases momentum when trend is clear and price barely exceeds fair value."""
    # FV = mean([19,19.5,20,20.5,21]) = 20.0; price=21.1 → deviation 5.5% (just over 5% margin)
    # momentum = (21.1 - 19) / 19 = 11.1%  → strong speculator signal
    state = make_state(21.1, [19.0, 19.5, 20.0, 20.5])
    npc   = make_npc(IRIS, inventory=6, cash=600.0)
    assert_winner(npc, state, ArchetypeTag.SPECULATOR, IRIS,
                  "Iris should speculate on a strong uptrend when FV deviation is small.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2
# Iris — flat market, price 12% below fair value
# Prediction: RATIONAL wins. No momentum → zero speculator signal.
# Fair value far above price → full rational buy signal.
# ══════════════════════════════════════════════════════════════════════════════
def test_02_iris_below_fair_value_rational_wins():
    """Iris buys the dip with her dominant Rational side when market is flat."""
    # FV = mean([23,23,22,21,20.5]) = 21.9; price = 19.2 → deviation 12.3%
    # momentum ≈ (19.2 - 23) / 23 = -16.5%  → negative, kills speculator
    state = make_state(19.2, [23.0, 23.0, 22.0, 21.0])
    npc   = make_npc(IRIS, inventory=10, cash=600.0)
    assert_winner(npc, state, ArchetypeTag.RATIONAL, IRIS,
                  "Iris should anchor to fair value and buy the dip in a flat market.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3
# Iris — moderate downtrend but price 10% below fair value
# Prediction: RATIONAL wins over SPECULATOR sell-signal.
# This tests Iris's core trait: she anchors to fundamentals even when
# momentum says "sell". With price 10% below FV, rational signal = max;
# speculator signal fires on the downtrend but Rational's weight (0.50) holds.
# If SPECULATOR wins → increase Iris RATIONAL weight above 0.50.
# ══════════════════════════════════════════════════════════════════════════════
def test_03_iris_downtrend_rational_overrides_speculator():
    """Iris buys the dip via Rational even when Speculator sees a sell signal."""
    # FV = mean([22,21,20,19,18]) = 20; price=18 => 10% below FV
    # momentum = (18-22)/22 = -18.2% => spec fires a SELL signal
    # Rational signal = (0.10-0.05)/0.05 = 1.0; spec signal ~0.90
    # Score: Rational 0.50*1.0=0.50 > Speculator 0.35*0.90=0.315
    state = make_state(18.0, [22.0, 21.0, 20.0, 19.0])
    npc   = make_npc(IRIS, inventory=10, cash=600.0)
    assert_winner(npc, state, ArchetypeTag.RATIONAL, IRIS,
                  "Iris must stay anchored to fair value (buy signal) even against a falling trend.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4
# Marcus — very low inventory, high scarcity
# Prediction: HOARDER dominates. Shortfall ratio = (100 - 2) / 100 = 0.98.
# Scarcity index high (more bids than asks). Combined → near-max signal.
# ══════════════════════════════════════════════════════════════════════════════
def test_04_marcus_low_inventory_hoarder_dominates():
    """Marcus hoards aggressively when almost out of stock in a scarce market."""
    # Scarcity: bid_depth >> ask_depth → scarcity_index = 75 / (75+25) = 0.75
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0],
                       bid_depth=75, ask_depth=25)
    npc   = make_npc(MARCUS, inventory=2, cash=900.0)
    assert_winner(npc, state, ArchetypeTag.HOARDER, MARCUS,
                  "Marcus should hoard when he's nearly out of inventory and supply is scarce.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5
# Marcus — full inventory, very wide bid-ask spread
# Prediction: MARKET_MAKER wins. Spread = 4/22 ≈ 18%, well over 10% threshold.
# Hoarder fades (hoard_target met). MM signal near max.
# ══════════════════════════════════════════════════════════════════════════════
def test_05_marcus_wide_spread_market_maker_wins():
    """Marcus pivots to market-making when his hoard is full and the spread is wide."""
    # Spread = (24 - 20) / 24 = 16.7%   → MM signal ≈ 1.0
    # Inventory 90 / hoard_target 100 → shortfall only 10%  → hoarder signal low
    state = make_state(22.0, [22.0, 22.0, 22.0, 22.0],
                       best_bid=20.0, best_ask=24.0)
    npc   = make_npc(MARCUS, inventory=90, cash=200.0)
    assert_winner(npc, state, ArchetypeTag.MARKET_MAKER, MARCUS,
                  "Marcus should make markets when his hoard is full and the spread is attractive.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6
# Dex — clear uptrend, positive momentum
# Prediction: SPECULATOR wins. Panic signal = 0 (positive momentum).
# With inventory=6: room_ratio=(30-6)/30=0.80; spec_score=0.30*0.80=0.24 > rat_score=0.20*1.0=0.20
# If RATIONAL wins → lower inventory in the test or increase Dex SPECULATOR weight.
# ══════════════════════════════════════════════════════════════════════════════
def test_06_dex_uptrend_speculator_wins():
    """Dex chases a clear uptrend; Panic stays silent when price is rising."""
    # momentum = (22 - 18) / 18 = 22.2%  -> speculator signal near max
    # panic signal = 0 (no price drop); inventory=6 gives enough room ratio
    state = make_state(22.0, [18.0, 19.0, 20.0, 21.0])
    npc   = make_npc(DEX, inventory=6, cash=400.0)   # inventory=6 -> room_ratio=0.80
    assert_winner(npc, state, ArchetypeTag.SPECULATOR, DEX,
                  "Dex's Speculator side must dominate a strong uptrend.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 7
# Dex — crash after a losing streak (bought high, now underwater)
# Prediction: PANIC wins. Two losing trades suppress Speculator (-0.06 mood)
# and amplify Panic (+0.20 mood). With new weights (Panic=0.50, Spec=0.30):
#   Panic score = 0.50 * clamp(0.60+0.20) = 0.40
#   Spec score  = 0.30 * clamp(1.00-0.06) = 0.28
# If SPECULATOR still wins → increase Dex PANIC weight further.
# ══════════════════════════════════════════════════════════════════════════════
def test_07_dex_crash_panic_overrides_speculator():
    """Dex panics after losing trades in a crash; mood streak tips the scales."""
    from market.models import Trade
    state = make_state(12.0, [20.0, 18.0, 16.0, 14.0])
    npc   = make_npc(DEX, inventory=15, cash=400.0)
    # Simulate 2 losing buys: bought at 18 and 17 when price is now 12
    npc.mood.record_trade(Trade("test", "other", 18.0, 5, 1), "test")
    npc.mood.record_trade(Trade("test", "other", 17.0, 5, 2), "test")
    assert_winner(npc, state, ArchetypeTag.PANIC, DEX,
                  "Dex's Panic must beat Speculator after 2 losing trades in a crash.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 8
# Rex — slight downtrend (-9%) + contagion pulse
# Prediction: PANIC overrides HOARDER.
# Contagion alone can't beat hoarder (panic raw=0 in flat market).
# Adding a -9% downtrend gives panic raw signal ~0.54, then contagion (+0.30)
# pushes it to 0.84. With new weights (Panic=0.40, Hoarder=0.40):
#   Panic score = 0.40 * clamp(0.54+0.30) = 0.40 * 0.84 = 0.336
#   Hoarder score = 0.40 * 0.68 = 0.272
# If HOARDER still wins → increase Rex PANIC weight or raise contagion pulse.
# ══════════════════════════════════════════════════════════════════════════════
def test_08_rex_contagion_panic_overrides_hoarder():
    """Contagion from a neighbour's dump spikes Rex's Panic on a falling market."""
    # momentum = (18.9 - 21.0) / 21.0 = -10%  -> panic drop_ratio ~1.0
    # contagion_pulse = 0.30 adds to panic signal; combined > hoarder
    state = make_state(18.9, [21.0, 20.5, 20.0, 19.5])
    npc   = make_npc(REX, inventory=20, cash=500.0, contagion=0.30)
    assert_winner(npc, state, ArchetypeTag.PANIC, REX,
                  "Rex must panic when a neighbour dumps during a falling market.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 9
# Rex — calm market, no contagion, very low inventory
# Prediction: HOARDER dominates. No contagion, no panic trigger. Low inventory
# → near-max hoarder signal. Speculator has 0 signal (flat market).
# ══════════════════════════════════════════════════════════════════════════════
def test_09_rex_calm_low_inventory_hoarder_dominates():
    """Rex hoards relentlessly in a stable market when his stockpile is nearly empty."""
    # momentum = 0, no panic trigger, inventory = 3 → hoarder shortfall = 97/100
    state = make_state(20.0, [20.0, 20.0, 20.0, 20.0])
    npc   = make_npc(REX, inventory=3, cash=500.0, contagion=0.0)
    assert_winner(npc, state, ArchetypeTag.HOARDER, REX,
                  "Rex must hoard when inventory is critically low and the market is calm.")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 10
# Vera — very wide spread, low momentum
# Prediction: MARKET_MAKER dominates. 18% spread → maximum MM signal.
# Hoarder signal moderate (she has some inventory to sell). Rational quiet.
# ══════════════════════════════════════════════════════════════════════════════
def test_10_vera_wide_spread_market_maker_wins():
    """Vera quotes both sides and earns the spread when the market is illiquid."""
    # Spread = (24 - 20) / 24 = 16.7%  → MM signal near max
    # flat momentum → speculator/panic signals = 0, Hoarder moderate
    state = make_state(22.0, [22.0, 22.0, 22.0, 22.0],
                       best_bid=20.0, best_ask=24.0, bid_depth=40, ask_depth=40)
    npc   = make_npc(VERA, inventory=30, cash=700.0)
    assert_winner(npc, state, ArchetypeTag.MARKET_MAKER, VERA,
                  "Vera should dominate as market maker when the spread is wide and momentum is nil.")
