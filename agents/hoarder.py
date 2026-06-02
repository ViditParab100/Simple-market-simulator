from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class HoarderAgent(Agent):
    """
    Obsessive accumulator. Bids below market to fish for cheap units.
    Only sells at a steep premium. Triggers artificial scarcity when hoarding at scale.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        hoard_target: int = 100,
        buy_discount: float = 0.92,
        sell_premium: float = 1.30,
    ):
        super().__init__(agent_id, inventory, cash)
        self.hoard_target = hoard_target
        self.buy_discount = buy_discount
        self.sell_premium = sell_premium
        self._pending_orders: list[Order] = []

    def think(self, state: MarketState) -> list[str]:
        price = state.last_price or _DEFAULT_PRICE
        shortfall = self.hoard_target - self.inventory

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"Hoard target: {self.hoard_target} units  |  Shortfall: {max(0, shortfall)} units",
            f"Scarcity index: {state.scarcity_index:.2f}",
        ]
        orders: list[Order] = []

        if shortfall > 0:
            bid_price = round(price * self.buy_discount, 2)
            qty = min(5, shortfall)
            thoughts.append(f"Still {shortfall} short of target. ACCUMULATION mode.")
            thoughts.append(f"Fishing for distressed sellers: BID @ ${bid_price:.2f} ({self.buy_discount:.0%} of market)")
            if self.cash >= bid_price * qty:
                orders.append(Order(self.agent_id, OrderSide.BID, bid_price, qty, state.tick))
                thoughts.append(f"Decision: BID {qty} units @ ${bid_price:.2f}")
            else:
                thoughts.append("Not enough cash to bid. Holding position.")
        else:
            sell_price = round(price * self.sell_premium, 2)
            premium_pct = (self.sell_premium - 1) * 100
            thoughts.append(f"Target reached ({self.inventory}/{self.hoard_target}). Protecting the hoard.")
            thoughts.append(
                f"Will only release supply at {premium_pct:.0f}% premium: ${sell_price:.2f}. "
                f"Current market (${price:.2f}) is too low."
            )
            if self.inventory > 0:
                orders.append(Order(self.agent_id, OrderSide.ASK, sell_price, min(3, self.inventory), state.tick))
                thoughts.append(f"Decision: ASK 3 units @ ${sell_price:.2f} -- unlikely to fill at this premium.")

        self._pending_orders = orders
        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def trade_remark(self, role: str, price: float, qty: int) -> str:
        if role == "buyer":
            return f"Mine now — {qty} more units secured at ${price:.2f}. Never enough."
        return f"Parting with {qty}? Only because ${price:.2f} was too good to refuse."

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        shortfall = self.hoard_target - self.inventory
        if shortfall <= 0:
            return None
        price = state.last_price or _DEFAULT_PRICE
        # Target is a steep discount; limit is a small concession above target
        target = round(price * self.buy_discount, 2)
        limit  = round(price * min(self.buy_discount + 0.04, 0.99), 2)
        qty    = min(5, shortfall)
        if self.cash < limit * qty:
            return None
        return HaggleIntent(
            self.agent_id, OrderSide.BID,
            price_target=target, price_limit=limit, quantity=qty,
        )
