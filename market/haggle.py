"""
Phase 3 — Bilateral Haggling Protocol.

Before orders hit the central order book each tick, agents have a chance
to negotiate bilaterally. If a deal is reached, it settles directly and
neither party needs to submit to the book. Only unresolved needs flow
to the regular market.

Flow per tick:
  1. HaggleCoordinator collects one HaggleIntent per agent.
  2. Compatible buyer/seller pairs are identified (price limits overlap).
  3. HaggleSession runs up to max_rounds of concession-based negotiation.
  4. Agreed trades are returned; the engine settles them and rebuilds state.
  5. Agents then run think() + act() against the post-haggle state.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from market.models import Order, OrderSide, Trade, MarketState


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class HaggleIntent:
    """
    An agent's pre-tick negotiation intent.

    price_target : the price the agent ideally wants
    price_limit  : the worst price they will accept
                   (buyer: upper limit; seller: lower limit)
    quantity     : units they want to trade
    """
    agent_id:     str
    side:         OrderSide
    price_target: float
    price_limit:  float
    quantity:     int


@dataclass
class HaggleResult:
    agreed:    bool
    price:     float | None
    quantity:  int | None
    buyer_id:  str
    seller_id: str
    log:       list[str] = field(default_factory=list)


# ── Negotiation session ───────────────────────────────────────────────────────

class HaggleSession:
    """
    Bilateral negotiation between one buyer and one seller.

    Concession model:
      - Both parties open at their price_target.
      - Each round without a deal, each party moves toward their price_limit
        by (1 / max_rounds) of the remaining gap.
      - A deal is struck the first round where buyer_bid >= seller_ask.
      - Deal price = midpoint of the crossing offers.
    """

    def __init__(self, buyer: HaggleIntent, seller: HaggleIntent, max_rounds: int = 3):
        self.buyer      = buyer
        self.seller     = seller
        self.max_rounds = max_rounds

    def run(self) -> HaggleResult:
        b_id = self.buyer.agent_id
        s_id = self.seller.agent_id
        qty  = min(self.buyer.quantity, self.seller.quantity)

        log = [
            f"Haggle: {b_id} (buyer) <-> {s_id} (seller)  |  {qty} units",
            f"  Buyer  target ${self.buyer.price_target:.2f}  |  limit ${self.buyer.price_limit:.2f}",
            f"  Seller target ${self.seller.price_target:.2f}  |  floor ${self.seller.price_limit:.2f}",
        ]

        buyer_bid  = self.buyer.price_target
        seller_ask = self.seller.price_target

        for rnd in range(1, self.max_rounds + 1):
            log.append(
                f"  Round {rnd}: buyer bids ${buyer_bid:.2f}  |  seller asks ${seller_ask:.2f}"
            )

            if buyer_bid >= seller_ask:
                deal_price = round((buyer_bid + seller_ask) / 2, 2)
                log.append(f"  DEAL at ${deal_price:.2f} x {qty} units")
                return HaggleResult(
                    agreed=True, price=deal_price, quantity=qty,
                    buyer_id=b_id, seller_id=s_id, log=log,
                )

            # Both concede by an equal fraction of their remaining room
            step = 1.0 / self.max_rounds
            buyer_gap  = self.buyer.price_limit  - buyer_bid
            seller_gap = seller_ask - self.seller.price_limit

            buyer_bid  = round(buyer_bid  + buyer_gap  * step, 2)
            seller_ask = round(seller_ask - seller_gap * step, 2)

        log.append(f"  NO DEAL after {self.max_rounds} rounds.")
        return HaggleResult(
            agreed=False, price=None, quantity=None,
            buyer_id=b_id, seller_id=s_id, log=log,
        )


# ── Coordinator ───────────────────────────────────────────────────────────────

class HaggleCoordinator:
    """
    Collects intents from all agents, pairs compatible buyers and sellers,
    and runs negotiation sessions.

    Pairing rule: a buyer and seller are compatible if the buyer's price_limit
    >= the seller's price_limit (there exists a deal zone).

    Each agent participates in at most one session per tick.
    Pairs are shuffled so the same agents don't always meet first.
    """

    def __init__(self, max_rounds: int = 3, seed: int | None = None):
        self.max_rounds = max_rounds
        self._rng       = random.Random(seed)

    def run(
        self,
        agents: list,          # list[Agent] — typed loosely to avoid circular import
        state: MarketState,
        tick: int,
    ) -> list[tuple[Trade, list[str]]]:
        """
        Returns a list of (Trade, negotiation_log) for every bilateral deal struck.
        """
        intents = []
        for agent in agents:
            intent = agent.haggle_intent(state)
            if intent is not None:
                intents.append((agent, intent))

        buyers  = [(a, i) for a, i in intents if i.side == OrderSide.BID]
        sellers = [(a, i) for a, i in intents if i.side == OrderSide.ASK]

        self._rng.shuffle(buyers)
        self._rng.shuffle(sellers)

        used: set[str] = set()
        results: list[tuple[Trade, list[str]]] = []

        for buyer_agent, b_intent in buyers:
            if buyer_agent.agent_id in used:
                continue
            for seller_agent, s_intent in sellers:
                if seller_agent.agent_id in used:
                    continue
                if buyer_agent.agent_id == seller_agent.agent_id:
                    continue
                # Check deal zone exists
                if b_intent.price_limit < s_intent.price_limit:
                    continue

                session = HaggleSession(b_intent, s_intent, self.max_rounds)
                result  = session.run()

                if result.agreed:
                    trade = Trade(
                        buyer_id=result.buyer_id,
                        seller_id=result.seller_id,
                        price=result.price,
                        quantity=result.quantity,
                        tick=tick,
                    )
                    results.append((trade, result.log))
                    used.add(buyer_agent.agent_id)
                    used.add(seller_agent.agent_id)
                    break  # buyer is matched; move to next buyer

        return results
