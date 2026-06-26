"""
English (ascending-price) auction.

Triggered when the Producer's surplus exceeds SURPLUS_THRESHOLD.  The lot
starts at STARTING_DISCOUNT × market price and rises by MIN_INCREMENT each
round until only one bidder remains or MAX_ROUNDS is hit.

Key design:
  - "Button auction": each round every active bidder declares their max
    willing price-per-unit.  Anyone whose max < current_price is eliminated.
  - Winner pays the standing clock price (not their private max).
  - Reserve price (50 % of market): if nobody bids at the opening price the
    auction is cancelled so the Producer doesn't give away stock for nothing.
  - Affordability gate lives in Agent.auction_bid() so agents can't win lots
    they can't pay for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base import Agent
    from market.models import MarketState

SURPLUS_THRESHOLD = 35    # Producer surplus above reserve to trigger
LOT_SIZE          = 20    # units per auction lot
STARTING_DISCOUNT = 0.70  # opening price = market_price × this
MIN_INCREMENT     = 0.50  # price rise per round ($)
MAX_ROUNDS        = 20    # safety cap on rounds


@dataclass
class AuctionLot:
    seller_id:      str
    quantity:       int
    starting_price: float
    reserve_price:  float   # auction cancelled if nobody bids this high
    market_price:   float   # last traded price at auction start
    tick:           int


@dataclass
class RoundResult:
    round_num:   int
    price:       float
    staying:     list[str]   # agent_ids still in after this round
    dropped_out: list[str]   # agent_ids that dropped this round


@dataclass
class AuctionResult:
    lot:           AuctionLot
    winner_id:     str | None
    winning_price: float | None
    rounds_run:    int
    history:       list[RoundResult] = field(default_factory=list)

    @property
    def sold(self) -> bool:
        return self.winner_id is not None


class AuctionSession:
    """Runs a single ascending-price auction for one lot."""

    def __init__(
        self,
        lot:           AuctionLot,
        bidders:       list["Agent"],
        min_increment: float = MIN_INCREMENT,
        max_rounds:    int   = MAX_ROUNDS,
    ):
        self.lot           = lot
        self.bidders       = {a.agent_id: a for a in bidders}
        self.min_increment = min_increment
        self.max_rounds    = max_rounds

    def run(self, state: "MarketState") -> AuctionResult:
        current_price = self.lot.starting_price
        active        = dict(self.bidders)
        history: list[RoundResult] = []

        for round_num in range(self.max_rounds):
            staying  = []
            dropping = []

            for aid, agent in active.items():
                max_bid = agent.auction_bid(self.lot, current_price, round_num, state)
                if max_bid is not None and max_bid >= current_price:
                    staying.append(aid)
                else:
                    dropping.append(aid)

            history.append(RoundResult(
                round_num=round_num,
                price=round(current_price, 2),
                staying=list(staying),
                dropped_out=dropping,
            ))

            for aid in dropping:
                del active[aid]

            if len(active) == 0:
                return AuctionResult(
                    lot=self.lot, winner_id=None, winning_price=None,
                    rounds_run=round_num + 1, history=history,
                )

            if len(active) == 1:
                winner_id = next(iter(active))
                return AuctionResult(
                    lot=self.lot,
                    winner_id=winner_id,
                    winning_price=round(current_price, 2),
                    rounds_run=round_num + 1,
                    history=history,
                )

            # Multiple bidders remain — raise the clock for next round
            current_price = round(current_price + self.min_increment, 2)

        # Max rounds hit with multiple bidders — pick alphabetically (deterministic).
        # Winner pays the price from the final round they confirmed, not the next increment.
        last_confirmed_price = history[-1].price if history else self.lot.starting_price
        winner_id = sorted(active.keys())[0]
        return AuctionResult(
            lot=self.lot,
            winner_id=winner_id,
            winning_price=last_confirmed_price,
            rounds_run=self.max_rounds,
            history=history,
        )


class AuctionCoordinator:
    """
    Checks each tick whether a Producer has enough surplus to trigger an auction.
    Settles the exchange between winner and seller when the auction succeeds.
    """

    def __init__(
        self,
        surplus_threshold: int   = SURPLUS_THRESHOLD,
        lot_size:          int   = LOT_SIZE,
        starting_discount: float = STARTING_DISCOUNT,
        min_increment:     float = MIN_INCREMENT,
        max_rounds:        int   = MAX_ROUNDS,
    ):
        self.surplus_threshold = surplus_threshold
        self.lot_size          = lot_size
        self.starting_discount = starting_discount
        self.min_increment     = min_increment
        self.max_rounds        = max_rounds

    def maybe_run(
        self,
        agents: list["Agent"],
        state:  "MarketState",
        tick:   int,
    ) -> AuctionResult | None:
        """
        Find a Producer with surplus >= threshold.  If found, run an auction
        and settle the trade.  Returns AuctionResult or None if no auction.
        """
        from agents.producer import ProducerAgent

        seller = next(
            (a for a in agents
             if isinstance(a, ProducerAgent) and a.alive
             and (a.inventory - a._reserve()) >= self.surplus_threshold),
            None,
        )
        if seller is None:
            return None

        market_price   = state.last_price or 20.0
        lot_qty        = min(self.lot_size, int(seller.inventory - seller._reserve()))
        starting_price = round(market_price * self.starting_discount, 2)
        reserve_price  = round(market_price * 0.50, 2)

        lot = AuctionLot(
            seller_id=seller.agent_id,
            quantity=lot_qty,
            starting_price=starting_price,
            reserve_price=reserve_price,
            market_price=market_price,
            tick=tick,
        )

        bidders = [a for a in agents if a.agent_id != seller.agent_id and a.alive]
        session = AuctionSession(lot, bidders, self.min_increment, self.max_rounds)
        result  = session.run(state)

        if result.sold:
            winner = next((a for a in agents if a.agent_id == result.winner_id), None)
            if winner is None:
                return result
            cost = result.winning_price * lot.quantity
            if winner.cash >= cost:
                winner.inventory   += lot.quantity
                winner.cash        -= cost
                seller.inventory   -= lot.quantity
                seller.cash        += cost
                winner.trade_count += 1
                seller.trade_count += 1
            else:
                # Winner overbid their means — void the result
                result = AuctionResult(
                    lot=lot, winner_id=None, winning_price=None,
                    rounds_run=result.rounds_run, history=result.history,
                )

        return result
