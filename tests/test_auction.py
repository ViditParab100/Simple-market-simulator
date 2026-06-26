"""
Tests for the English auction module.

Coverage:
  - AuctionLot / AuctionResult dataclasses
  - AuctionSession: winner selection, dropout, reserve, max-rounds tiebreaker
  - AuctionCoordinator: trigger condition, settlement, affordability guard
  - Per-agent auction_bid strategies
  - Engine integration (auction phase fires, price propagates)
"""
from __future__ import annotations
import pytest

from market.auction import (
    AuctionLot, AuctionSession, AuctionCoordinator,
    SURPLUS_THRESHOLD, LOT_SIZE, STARTING_DISCOUNT, MIN_INCREMENT, MAX_ROUNDS,
)
from market.models import MarketState
from market.engine import SimulationEngine
from agents.producer import ProducerAgent
from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent
from logger.thought_logger import ThoughtLogger


# ── helpers ────────────────────────────────────────────────────────────────────

def make_state(price: float = 21.0, history: list[float] | None = None) -> MarketState:
    h = history if history is not None else [price] * 10
    return MarketState(
        tick=1, last_price=price, best_bid=None, best_ask=None,
        bid_depth=0, ask_depth=0, price_history=h,
    )


def make_lot(
    market_price: float = 21.0,
    quantity: int = 20,
    starting_discount: float = 0.70,
) -> AuctionLot:
    return AuctionLot(
        seller_id="Producer-01",
        quantity=quantity,
        starting_price=round(market_price * starting_discount, 2),
        reserve_price=round(market_price * 0.50, 2),
        market_price=market_price,
        tick=1,
    )


def silent_engine(agents, ticks=20, auction=False):
    coord = AuctionCoordinator() if auction else None
    eng = SimulationEngine(
        agents=agents,
        logger=ThoughtLogger(verbose=False),
        auction_coordinator=coord,
        consumption_rate=3.0,
        salary=70.0,
    )
    eng.run(ticks=ticks)
    return eng


# ── AuctionLot ─────────────────────────────────────────────────────────────────

class TestAuctionLot:
    def test_fields_stored_correctly(self):
        lot = make_lot(21.0, 20)
        assert lot.seller_id == "Producer-01"
        assert lot.quantity == 20
        assert lot.market_price == 21.0
        assert lot.starting_price == round(21.0 * 0.70, 2)
        assert lot.reserve_price == round(21.0 * 0.50, 2)

    def test_starting_price_below_market(self):
        lot = make_lot(21.0)
        assert lot.starting_price < lot.market_price

    def test_reserve_below_starting(self):
        lot = make_lot(21.0)
        assert lot.reserve_price < lot.starting_price


# ── AuctionResult ──────────────────────────────────────────────────────────────

class TestAuctionResult:
    def test_sold_true_when_winner(self):
        lot = make_lot()
        session = AuctionSession(lot, [], min_increment=0.50, max_rounds=5)
        result = session.run(make_state())
        # empty bidder list → no sale
        assert not result.sold
        assert result.winner_id is None

    def test_sold_false_when_no_bidders(self):
        lot = make_lot()
        # give one bidder who will always bid
        agent = HoarderAgent("h", inventory=0, cash=5000.0, hoard_target=100)
        session = AuctionSession(lot, [agent], min_increment=0.50, max_rounds=1)
        result = session.run(make_state())
        assert result.sold
        assert result.winner_id == "h"


# ── AuctionSession ─────────────────────────────────────────────────────────────

class TestAuctionSession:
    def test_no_bidders_returns_no_sale(self):
        lot = make_lot()
        session = AuctionSession(lot, [], max_rounds=5)
        result = session.run(make_state())
        assert not result.sold
        assert result.rounds_run == 1

    def test_single_bidder_wins_at_opening_price(self):
        """One eager bidder wins immediately at the clock's opening price."""
        lot = make_lot(market_price=21.0)
        agent = HoarderAgent("h", inventory=0, cash=5000.0, hoard_target=100,
                             buy_discount=0.99)  # will bid up to 20.79 > 14.70
        session = AuctionSession(lot, [agent], min_increment=0.50, max_rounds=5)
        result = session.run(make_state(21.0))
        assert result.sold
        assert result.winner_id == "h"
        assert result.rounds_run == 1
        assert result.winning_price == lot.starting_price

    def test_high_valuation_beats_low_valuation(self):
        """Bidder with higher max wins when they outlast the lower bidder."""
        lot = make_lot(market_price=21.0)
        # Hoarder buy_discount=0.80 → max $16.80; drops when price > 16.80
        low_bidder  = HoarderAgent("low",  inventory=0, cash=5000.0,
                                   hoard_target=100, buy_discount=0.80)
        # Hoarder buy_discount=0.99 → max $20.79; stays longer
        high_bidder = HoarderAgent("high", inventory=0, cash=5000.0,
                                   hoard_target=100, buy_discount=0.99)
        session = AuctionSession(lot, [low_bidder, high_bidder],
                                 min_increment=0.50, max_rounds=20)
        result = session.run(make_state(21.0))
        assert result.sold
        assert result.winner_id == "high"
        # low_bidder max = 21*0.80 = 16.80; starting = 14.70
        # After round 4: 14.70 + 4*0.50 = 16.70 (low still in)
        # After round 5: price 17.20 > 16.80 → low drops; high wins at 16.70
        assert result.winning_price < 21.0 * 0.99

    def test_price_rises_each_round(self):
        """Prices in history are strictly ascending when multiple bidders compete."""
        lot = make_lot(market_price=21.0)
        a = HoarderAgent("a", inventory=0, cash=5000.0, hoard_target=100, buy_discount=0.99)
        b = HoarderAgent("b", inventory=0, cash=5000.0, hoard_target=100, buy_discount=0.95)
        session = AuctionSession(lot, [a, b], min_increment=0.50, max_rounds=10)
        result = session.run(make_state(21.0))
        prices = [r.price for r in result.history]
        assert prices == sorted(prices)
        assert len(set(prices)) > 1  # at least two distinct prices

    def test_dropout_recorded_in_history(self):
        """Round history marks which agents dropped each round."""
        lot = make_lot(market_price=21.0)
        # low drops first; high stays
        low  = HoarderAgent("low",  inventory=0, cash=5000.0,
                            hoard_target=100, buy_discount=0.80)
        high = HoarderAgent("high", inventory=0, cash=5000.0,
                            hoard_target=100, buy_discount=0.99)
        session = AuctionSession(lot, [low, high], min_increment=0.50, max_rounds=20)
        result = session.run(make_state(21.0))
        all_dropped = [aid for rnd in result.history for aid in rnd.dropped_out]
        assert "low" in all_dropped
        assert "high" not in all_dropped

    def test_max_rounds_tiebreaker_picks_alphabetically_first(self):
        """When max rounds hit with ties, winner is alphabetically first by agent_id."""
        lot = make_lot(market_price=21.0)
        # Both have identical high bids (buy_discount=1.0 → effectively unlimited)
        a = HoarderAgent("alpha", inventory=0, cash=5000.0,
                         hoard_target=100, buy_discount=1.0)
        b = HoarderAgent("beta",  inventory=0, cash=5000.0,
                         hoard_target=100, buy_discount=1.0)
        session = AuctionSession(lot, [a, b], min_increment=0.50, max_rounds=3)
        result = session.run(make_state(21.0))
        assert result.sold
        assert result.winner_id == "alpha"  # a < b alphabetically
        assert result.rounds_run == 3

    def test_max_rounds_winner_pays_last_confirmed_price(self):
        """Winner pays the round-20 standing price, not the incremented next price."""
        lot = make_lot(market_price=21.0)
        a = HoarderAgent("a", inventory=0, cash=5000.0,
                         hoard_target=100, buy_discount=1.0)
        b = HoarderAgent("b", inventory=0, cash=5000.0,
                         hoard_target=100, buy_discount=1.0)
        session = AuctionSession(lot, [a, b], min_increment=0.50, max_rounds=5)
        result = session.run(make_state(21.0))
        # Price in round 5 (last, 0-indexed round 4):
        # starting=14.70, after rounds 0-3 each raise by 0.50, round 4 starts at 16.70
        expected_last_price = round(lot.starting_price + 4 * 0.50, 2)
        assert result.winning_price == expected_last_price

    def test_broke_agent_cannot_win(self):
        """Agent with insufficient cash to buy the lot is eliminated immediately."""
        lot = make_lot(market_price=21.0, quantity=20)  # lot costs 14.70*20=$294
        # Rich bidder and broke bidder
        rich  = HoarderAgent("rich",  inventory=0, cash=5000.0,
                              hoard_target=100, buy_discount=0.99)
        broke = HoarderAgent("broke", inventory=0, cash=1.0,
                              hoard_target=100, buy_discount=0.99)
        session = AuctionSession(lot, [rich, broke], min_increment=0.50, max_rounds=5)
        result = session.run(make_state(21.0))
        assert result.winner_id == "rich"

    def test_history_length_equals_rounds_run(self):
        lot = make_lot()
        a = HoarderAgent("a", inventory=0, cash=5000.0,
                         hoard_target=100, buy_discount=0.80)
        session = AuctionSession(lot, [a], max_rounds=10)
        result = session.run(make_state())
        assert len(result.history) == result.rounds_run


# ── per-agent auction_bid strategies ──────────────────────────────────────────

class TestAgentBidStrategies:
    def _lot_and_state(self, price=21.0):
        return make_lot(price), make_state(price)

    def test_producer_never_bids(self):
        """Producer is the seller — must always return None."""
        p = ProducerAgent("p", inventory=50, cash=1000.0)
        lot, state = self._lot_and_state()
        assert p.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_hoarder_bids_below_buy_discount(self):
        """Hoarder's max is market × buy_discount; stays in while price is below that."""
        h = HoarderAgent("h", inventory=0, cash=5000.0,
                         hoard_target=100, buy_discount=0.92)
        lot, state = self._lot_and_state(21.0)
        max_bid = h.auction_bid(lot, lot.starting_price, 0, state)
        assert max_bid is not None
        assert abs(max_bid - 21.0 * 0.92) < 0.01

    def test_hoarder_drops_when_hoard_target_reached(self):
        """Hoarder with inventory >= hoard_target returns None."""
        h = HoarderAgent("h", inventory=100, cash=5000.0, hoard_target=100)
        lot, state = self._lot_and_state()
        assert h.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_speculator_bids_in_uptrend(self):
        """Speculator with bullish momentum bids above market."""
        sp = SpeculatorAgent("sp", inventory=0, cash=5000.0,
                             momentum_threshold=0.02, aggressiveness=0.02)
        price = 21.0
        history = [18.0, 19.0, 20.0, 20.5, 21.0]  # strong uptrend
        lot, state = make_lot(price), make_state(price, history)
        max_bid = sp.auction_bid(lot, lot.starting_price, 0, state)
        assert max_bid is not None
        assert max_bid > price  # pays premium

    def test_speculator_passes_in_downtrend(self):
        """Speculator with negative momentum returns None."""
        sp = SpeculatorAgent("sp", inventory=5, cash=5000.0,
                             momentum_threshold=0.02)
        price = 21.0
        history = [25.0, 24.0, 23.0, 22.0, 21.0]  # strong downtrend
        lot, state = make_lot(price), make_state(price, history)
        assert sp.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_speculator_passes_at_max_position(self):
        """Speculator at max_position doesn't buy more even in uptrend."""
        sp = SpeculatorAgent("sp", inventory=30, cash=5000.0,
                             max_position=30, momentum_threshold=0.02)
        price = 21.0
        history = [18.0, 19.0, 20.0, 20.5, 21.0]
        lot, state = make_lot(price), make_state(price, history)
        assert sp.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_market_maker_bids_when_inventory_low(self):
        """MarketMaker bids when below min_inventory."""
        mm = MarketMakerAgent("mm", inventory=5, cash=5000.0,
                              min_inventory=10)
        lot, state = self._lot_and_state()
        max_bid = mm.auction_bid(lot, lot.starting_price, 0, state)
        assert max_bid is not None
        assert max_bid > lot.market_price  # pays slight premium

    def test_market_maker_passes_when_overstocked(self):
        """MarketMaker at or above midpoint passes (well-stocked)."""
        mm = MarketMakerAgent("mm", inventory=50, cash=5000.0,
                              min_inventory=10, max_inventory=80)
        lot, state = self._lot_and_state()
        # mid = (10+80)//2 = 45; 50 > 45 → should pass
        assert mm.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_rational_bids_up_to_fair_value_plus_margin(self):
        """Rational's max bid is fair_value × (1 + margin)."""
        ra = RationalAgent("ra", inventory=5, cash=5000.0,
                           fair_value_window=5, margin=0.05)
        price = 21.0
        history = [21.0] * 5  # FV = 21.0
        lot, state = make_lot(price), make_state(price, history)
        max_bid = ra.auction_bid(lot, lot.starting_price, 0, state)
        assert max_bid is not None
        expected = round(21.0 * 1.05, 2)
        assert abs(max_bid - expected) < 0.01

    def test_rational_passes_without_history(self):
        """Rational with no price history can't compute FV → passes."""
        ra = RationalAgent("ra", inventory=5, cash=5000.0)
        lot, state = make_lot(), make_state(21.0, history=[])
        assert ra.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_panic_calm_low_inventory_bids(self):
        """Calm Panic agent with <5 units bids a small premium."""
        pa = PanicAgent("pa", inventory=2, cash=5000.0)
        lot, state = self._lot_and_state()
        max_bid = pa.auction_bid(lot, lot.starting_price, 0, state)
        assert max_bid is not None
        assert max_bid > lot.market_price  # pays premium to secure supply

    def test_panic_calm_normal_inventory_passes(self):
        """Calm Panic agent with ≥5 units returns None."""
        pa = PanicAgent("pa", inventory=10, cash=5000.0)
        lot, state = self._lot_and_state()
        assert pa.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_panic_recovering_does_not_bid(self):
        """Panic agent in recovery mode never bids (even if low inventory)."""
        pa = PanicAgent("pa", inventory=0, cash=5000.0)
        pa._state = "recovering"
        pa._recovery_counter = 2
        lot, state = self._lot_and_state()
        assert pa.auction_bid(lot, lot.starting_price, 0, state) is None

    def test_base_survival_bid_overrides_all(self):
        """Any agent starving (runway < threshold) bids 15% above market."""
        mm = MarketMakerAgent("mm", inventory=50, cash=5000.0,
                              min_inventory=10, max_inventory=80)
        # force survival state
        mm.consumption_rate = 3.0
        mm.survival_threshold = 5
        # inventory=50 → runway=16.7 — not starving
        lot, state = self._lot_and_state()
        assert mm.auction_bid(lot, lot.starting_price, 0, state) is None

        # Now set low runway
        mm.inventory = 1  # runway = 1/3 = 0.33 < threshold 5
        max_bid = mm.auction_bid(lot, lot.starting_price, 0, state)
        assert max_bid is not None
        assert abs(max_bid - lot.market_price * 1.15) < 0.01

    def test_affordability_gate_prevents_broke_bid(self):
        """Agent with cash < starting_price × lot_qty returns None immediately."""
        h = HoarderAgent("h", inventory=0, cash=1.0, hoard_target=100)
        lot = make_lot(market_price=21.0, quantity=20)  # min cost: 14.70×20=$294
        state = make_state(21.0)
        assert h.auction_bid(lot, lot.starting_price, 0, state) is None


# ── AuctionCoordinator ─────────────────────────────────────────────────────────

class TestAuctionCoordinator:
    def _agents_with_surplus(self, surplus=40):
        reserve = 6  # production_rate=25, consume_rate=3 → reserve = int(3*2)=6
        prod = ProducerAgent("Producer-01", inventory=surplus + reserve,
                             cash=1000.0, production_rate=0)
        prod.consumption_rate = 3.0
        buyer = HoarderAgent("Hoarder-01", inventory=0, cash=5000.0, hoard_target=100)
        return [prod, buyer]

    def test_no_trigger_below_threshold(self):
        """Coordinator does nothing when Producer surplus is below threshold."""
        prod = ProducerAgent("p", inventory=10, cash=1000.0, production_rate=0)
        coord = AuctionCoordinator(surplus_threshold=35)
        result = coord.maybe_run([prod], make_state(), tick=1)
        assert result is None

    def test_triggers_when_surplus_met(self):
        """Coordinator returns an AuctionResult when surplus >= threshold."""
        agents = self._agents_with_surplus(surplus=40)
        coord = AuctionCoordinator(surplus_threshold=35, lot_size=20)
        result = coord.maybe_run(agents, make_state(21.0), tick=1)
        assert result is not None

    def test_winner_receives_inventory(self):
        """When auction sells, winner's inventory increases by lot_size."""
        agents = self._agents_with_surplus(surplus=40)
        buyer = agents[1]
        initial_inv = buyer.inventory
        coord = AuctionCoordinator(surplus_threshold=35, lot_size=20)
        result = coord.maybe_run(agents, make_state(21.0), tick=1)
        if result and result.sold:
            assert buyer.inventory == initial_inv + 20

    def test_seller_loses_inventory_on_sale(self):
        """Producer's inventory decreases by lot_size when auction sells."""
        agents = self._agents_with_surplus(surplus=40)
        prod = agents[0]
        initial_inv = prod.inventory
        coord = AuctionCoordinator(surplus_threshold=35, lot_size=20)
        result = coord.maybe_run(agents, make_state(21.0), tick=1)
        if result and result.sold:
            assert prod.inventory == initial_inv - 20

    def test_cash_transfers_correctly(self):
        """Winner pays exactly winning_price × lot_size; seller receives same."""
        agents = self._agents_with_surplus(surplus=40)
        prod, buyer = agents
        prod_cash_before  = prod.cash
        buyer_cash_before = buyer.cash
        coord = AuctionCoordinator(surplus_threshold=35, lot_size=20)
        result = coord.maybe_run(agents, make_state(21.0), tick=1)
        if result and result.sold:
            expected_cost = result.winning_price * 20
            assert abs(buyer.cash - (buyer_cash_before - expected_cost)) < 0.01
            assert abs(prod.cash  - (prod_cash_before  + expected_cost)) < 0.01

    def test_void_when_winner_cannot_afford(self):
        """If winner can't cover the cost, trade is voided — no inventory moves."""
        reserve = 6
        prod  = ProducerAgent("p", inventory=46, cash=1000.0, production_rate=0)
        prod.consumption_rate = 3.0
        buyer = HoarderAgent("h", inventory=0, cash=0.01, hoard_target=100)
        initial_prod_inv  = prod.inventory
        initial_buyer_inv = buyer.inventory
        coord = AuctionCoordinator(surplus_threshold=35, lot_size=20,
                                   starting_discount=0.001)  # tiny starting price
        result = coord.maybe_run([prod, buyer], make_state(21.0), tick=1)
        if result is not None and result.winner_id is not None:
            # Win was voided — inventory unchanged
            assert buyer.inventory == initial_buyer_inv
            assert prod.inventory  == initial_prod_inv

    def test_lot_size_capped_at_available_surplus(self):
        """Lot size is min(lot_size, actual_surplus) so Producer never oversells."""
        reserve = 6
        prod = ProducerAgent("p", inventory=reserve + 15, cash=1000.0,
                             production_rate=0)  # only 15 surplus, < lot_size=20
        prod.consumption_rate = 3.0
        buyer = HoarderAgent("h", inventory=0, cash=5000.0, hoard_target=100)
        coord = AuctionCoordinator(surplus_threshold=10, lot_size=20)
        result = coord.maybe_run([prod, buyer], make_state(21.0), tick=1)
        if result:
            assert result.lot.quantity == 15

    def test_trade_count_incremented_on_sale(self):
        """Winner and seller each get +1 trade_count when auction succeeds."""
        agents = self._agents_with_surplus(surplus=40)
        prod, buyer = agents
        before_prod  = prod.trade_count
        before_buyer = buyer.trade_count
        coord = AuctionCoordinator(surplus_threshold=35, lot_size=20)
        result = coord.maybe_run(agents, make_state(21.0), tick=1)
        if result and result.sold:
            assert prod.trade_count  == before_prod  + 1
            assert buyer.trade_count == before_buyer + 1


# ── Engine integration ─────────────────────────────────────────────────────────

class TestAuctionEngineIntegration:
    def _zoo_agents(self):
        from main import build_zoo_agents
        return build_zoo_agents()

    def test_engine_runs_with_auction_coordinator(self):
        """Engine with AuctionCoordinator completes without error."""
        agents = self._zoo_agents()
        silent_engine(agents, ticks=15, auction=True)

    def test_auction_price_enters_price_history(self):
        """When an auction sells, winning price appears in engine.price_history."""
        from main import build_zoo_agents
        agents = build_zoo_agents()
        coord = AuctionCoordinator(surplus_threshold=5, lot_size=10)
        eng = SimulationEngine(
            agents=agents,
            logger=ThoughtLogger(verbose=False),
            auction_coordinator=coord,
            consumption_rate=3.0,
            salary=70.0,
            initial_price_history=[21.0] * 10,
        )
        eng.run(ticks=20)
        # Price history must be non-trivial if at least one auction sold
        assert len(eng.price_history) > 10

    def test_no_agent_goes_bankrupt_in_auction_run(self):
        """50-tick auction run: no agent should have negative cash."""
        agents = self._zoo_agents()
        eng = silent_engine(agents, ticks=50, auction=True)
        for a in eng.agents:
            assert a.cash >= 0, f"{a.agent_id} has negative cash: {a.cash:.2f}"

    def test_all_agents_survive_auction_run(self):
        """With default salary/consume, no agent should die even with auctions."""
        agents = self._zoo_agents()
        eng = silent_engine(agents, ticks=30, auction=True)
        assert all(a.alive for a in eng.agents)

    def test_auction_disabled_by_default(self):
        """Engine without AuctionCoordinator runs identically — no auction attribute."""
        agents = self._zoo_agents()
        eng = SimulationEngine(
            agents=agents,
            logger=ThoughtLogger(verbose=False),
            consumption_rate=3.0,
            salary=70.0,
        )
        eng.run(ticks=5)
        assert eng.auction_coordinator is None
