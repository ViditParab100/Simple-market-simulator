from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class ProducerAgent(Agent):
    """
    The supply side of the economy. Each tick it mints `production_rate` units
    (a farm/mine/factory) and offers its stock to the market, slightly below the
    last price so it reliably clears against buyers' bids.

    Without a Producer, a consuming market depletes to zero and everyone starves.
    With one, supply is continuously replenished, so the market can reach a
    flowing equilibrium instead of freezing or collapsing.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        production_rate: int = 25,
        sell_discount: float = 0.98,   # ask just below market to ensure fills
        floor_price: float = 1.0,      # never sell below this
    ):
        super().__init__(agent_id, inventory, cash)
        self.production_rate = production_rate
        self.sell_discount   = sell_discount
        self.floor_price     = floor_price
        self.is_employer     = True    # pays wages to the other agents
        self._pending_orders: list[Order] = []
        self._last_produced: float = 0.0

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
        ask_price = max(self.floor_price, round(price * self.sell_discount, 2))

        reserve   = self._reserve()
        sell_qty  = max(0, int(self.inventory) - reserve)

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"Produced {self._last_produced:.0f} units this tick (rate {self.production_rate}/tick).",
        ]

        if reserve > 0:
            thoughts.append(f"Holding back {reserve} units for own survival.")

        if sell_qty > 0:
            thoughts.append(
                f"Offering surplus to market: ASK {sell_qty} @ ${ask_price:.2f} "
                f"({self.sell_discount:.0%} of market to ensure fills)."
            )
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
        price = state.last_price or _DEFAULT_PRICE
        # Eager seller: targets just below market, will go lower to move stock
        return HaggleIntent(
            self.agent_id, OrderSide.ASK,
            price_target=round(price * self.sell_discount, 2),
            price_limit=max(self.floor_price, round(price * 0.90, 2)),
            quantity=sell_qty,
        )

    def survival_order(self, state: MarketState) -> Order | None:
        # The producer is a net supplier — it never panic-buys.
        return None
