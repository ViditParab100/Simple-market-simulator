from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class MarketMakerAgent(Agent):
    """
    Quotes both sides of the market to earn the spread.
    Widens spread when volatility is high. Tilts quotes when inventory is imbalanced.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        base_spread: float = 0.04,
        quote_size: int = 5,
        max_inventory: int = 80,
        min_inventory: int = 10,
    ):
        super().__init__(agent_id, inventory, cash)
        self.base_spread = base_spread
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.min_inventory = min_inventory
        self._pending_orders: list[Order] = []

    def think(self, state: MarketState) -> list[str]:
        price = state.last_price or _DEFAULT_PRICE
        momentum = abs(state.price_momentum)
        spread = round(self.base_spread * (1 + momentum * 5), 4)

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"Spread: {spread * 100:.1f}%  |  Momentum signal: {state.price_momentum:+.1%}",
        ]
        orders: list[Order] = []

        bid_price = round(price * (1 - spread / 2), 2)
        ask_price = round(price * (1 + spread / 2), 2)

        if self.inventory <= self.min_inventory:
            thoughts.append(f"Inventory LOW ({self.inventory}/{self.min_inventory} min) -- restocking. Bid only.")
            if self.cash >= bid_price * self.quote_size:
                orders.append(Order(self.agent_id, OrderSide.BID, bid_price, self.quote_size, state.tick))
                thoughts.append(f"Decision: BID {self.quote_size} @ ${bid_price:.2f}")
            else:
                thoughts.append("Not enough cash to restock. Holding.")

        elif self.inventory >= self.max_inventory:
            thoughts.append(f"Inventory HIGH ({self.inventory}/{self.max_inventory} max) -- offloading. Ask only.")
            ask_qty = min(self.quote_size, self.inventory)
            orders.append(Order(self.agent_id, OrderSide.ASK, ask_price, ask_qty, state.tick))
            thoughts.append(f"Decision: ASK {ask_qty} @ ${ask_price:.2f}")

        else:
            thoughts.append(f"Inventory balanced ({self.inventory} units) -- quoting both sides.")
            thoughts.append(f"Decision: BID {self.quote_size} @ ${bid_price:.2f}  |  ASK {self.quote_size} @ ${ask_price:.2f}")
            if self.cash >= bid_price * self.quote_size:
                orders.append(Order(self.agent_id, OrderSide.BID, bid_price, self.quote_size, state.tick))
            ask_qty = min(self.quote_size, self.inventory)
            if ask_qty > 0:
                orders.append(Order(self.agent_id, OrderSide.ASK, ask_price, ask_qty, state.tick))

        self._pending_orders = orders
        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        price = state.last_price or _DEFAULT_PRICE
        spread = self.base_spread
        # Only negotiate when inventory is imbalanced — otherwise let the book handle it
        if self.inventory <= self.min_inventory and self.cash >= price:
            return HaggleIntent(
                self.agent_id, OrderSide.BID,
                price_target=round(price * (1 - spread / 2), 2),
                price_limit=round(price * (1 - spread / 4), 2),
                quantity=self.quote_size,
            )
        if self.inventory >= self.max_inventory:
            return HaggleIntent(
                self.agent_id, OrderSide.ASK,
                price_target=round(price * (1 + spread / 2), 2),
                price_limit=round(price * (1 + spread / 4), 2),
                quantity=min(self.quote_size, self.inventory),
            )
        return None
