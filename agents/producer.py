from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class ProducerAgent(Agent):
    """
    The supply side of the economy. Each tick it mints `production_rate` units
    (a farm/mine/factory) and offers its surplus to the market.

    Pricing is **cost-plus anchored**: the producer sells at
    `base_cost * (1 + margin)`, NOT at "just below the last trade". Chasing the
    last price creates a runaway feedback loop with desperate survival bids
    (every frantic trade lifts the next ask). Anchoring to a stable production
    cost gives the market a price floor/ceiling so inflation can't spiral.

    Without a Producer, a consuming market depletes to zero and everyone starves.
    With one, supply is continuously replenished at a stable price.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        production_rate: int = 25,
        base_cost: float = 20.0,     # cost to produce one unit (the price anchor)
        margin: float = 0.05,        # markup over cost
        floor_price: float = 1.0,    # never sell below this
    ):
        super().__init__(agent_id, inventory, cash)
        self.production_rate = production_rate
        self.base_cost       = base_cost
        self.margin          = margin
        self.floor_price     = floor_price
        self.is_employer     = True    # pays wages to the other agents
        self._pending_orders: list[Order] = []
        self._last_produced: float = 0.0

    def anchor_price(self) -> float:
        """Stable cost-plus sell price, independent of market frenzy."""
        return max(self.floor_price, round(self.base_cost * (1 + self.margin), 2))

    def _reserve(self) -> int:
        """Units to keep back for the producer's own survival before selling."""
        if self.consumption_rate <= 0:
            return 0
        # Keep a couple of ticks of food so the producer never starves itself.
        return int(self.consumption_rate * 2)

    def produce(self) -> float:
        """Mint this tick's output into inventory. Called by the engine."""
        self.inventory      += self.production_rate
        self.produced_total += self.production_rate
        self._last_produced  = self.production_rate
        return self.production_rate

    def think(self, state: MarketState) -> list[str]:
        price     = state.last_price or _DEFAULT_PRICE
        ask_price = self.anchor_price()

        reserve   = self._reserve()
        sell_qty  = max(0, int(self.inventory) - reserve)

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"Produced {self._last_produced:.0f} units this tick (rate {self.production_rate}/tick).",
            f"Cost-plus anchor: ${self.base_cost:.2f} cost + {self.margin:.0%} = ${ask_price:.2f} "
            f"(ignoring market frenzy at ${price:.2f}).",
        ]

        if reserve > 0:
            thoughts.append(f"Holding back {reserve} units for own survival.")

        if sell_qty > 0:
            thoughts.append(f"Offering surplus: ASK {sell_qty} @ ${ask_price:.2f}.")
            self._pending_orders = [
                Order(self.agent_id, OrderSide.ASK, ask_price, sell_qty, state.tick)
            ]
        else:
            thoughts.append("No surplus to sell this tick. Holding.")
            self._pending_orders = []

        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        sell_qty = max(0, int(self.inventory) - self._reserve())
        if sell_qty <= 0:
            return None
        anchor = self.anchor_price()
        # Eager seller around its anchor; will shave the margin but not chase higher
        return HaggleIntent(
            self.agent_id, OrderSide.ASK,
            price_target=anchor,
            price_limit=max(self.floor_price, round(self.base_cost, 2)),
            quantity=sell_qty,
        )

    def survival_order(self, state: MarketState) -> Order | None:
        # The producer is a net supplier — it never panic-buys.
        return None

    def auction_bid(self, lot, current_price, round_num, state):
        return None  # seller never bids in its own auction

    def trade_remark(self, role: str, price: float, qty: int) -> str:
        return f"Shipped {qty} units at my ${price:.2f} cost-plus price. Supply keeps flowing."
