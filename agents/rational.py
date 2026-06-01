from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class RationalAgent(Agent):
    """
    Anchors to a moving-average fair value. Buys when price is meaningfully
    below fair value; sells when meaningfully above. Acts as a market stabilizer.
    Slow to react but consistently mean-reverts.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        fair_value_window: int = 10,
        margin: float = 0.05,
        trade_size: int = 3,
    ):
        super().__init__(agent_id, inventory, cash)
        self.fair_value_window = fair_value_window
        self.margin = margin
        self.trade_size = trade_size
        self._pending_orders: list[Order] = []

    def _fair_value(self, state: MarketState) -> float | None:
        if len(state.price_history) < 2:
            return None
        window = state.price_history[-self.fair_value_window:]
        return sum(window) / len(window)

    def think(self, state: MarketState) -> list[str]:
        price = state.last_price or _DEFAULT_PRICE
        fv = self._fair_value(state)

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
        ]
        orders: list[Order] = []

        if fv is None:
            thoughts.append("Insufficient price history to estimate fair value. Holding.")
            self._pending_orders = []
            return thoughts

        deviation = (price - fv) / fv
        thoughts.append(
            f"Fair value ({self.fair_value_window}-tick avg): ${fv:.2f}  |  "
            f"Deviation: {deviation:+.1%}  |  Margin: +/-{self.margin:.0%}"
        )

        if deviation < -self.margin:
            thoughts.append(f"Market UNDERVALUED ({deviation:+.1%} below fair). This is a buying opportunity.")
            thoughts.append(f"Decision: BID {self.trade_size} units @ ${price:.2f} (at market to ensure fill)")
            if self.cash >= price * self.trade_size:
                orders.append(Order(self.agent_id, OrderSide.BID, price, self.trade_size, state.tick))
            else:
                thoughts.append("Insufficient cash for full position. Holding.")

        elif deviation > self.margin:
            qty = min(self.trade_size, self.inventory)
            thoughts.append(f"Market OVERVALUED ({deviation:+.1%} above fair). Selling into strength.")
            if qty > 0:
                thoughts.append(f"Decision: ASK {qty} units @ ${price:.2f} (at market to ensure fill)")
                orders.append(Order(self.agent_id, OrderSide.ASK, price, qty, state.tick))
            else:
                thoughts.append("Would sell but inventory is empty. Holding.")

        else:
            thoughts.append(
                f"Price within {self.margin:.0%} of fair value ({deviation:+.1%}). "
                f"No action warranted. Holding."
            )

        self._pending_orders = orders
        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        fv = self._fair_value(state)
        if fv is None:
            return None
        price     = state.last_price or _DEFAULT_PRICE
        deviation = (price - fv) / fv
        half      = self.margin / 2
        if deviation < -self.margin and self.cash >= price:
            # Undervalued — want to buy, willing to go up to halfway toward fair value
            return HaggleIntent(
                self.agent_id, OrderSide.BID,
                price_target=price,
                price_limit=round(price * (1 + half), 2),
                quantity=self.trade_size,
            )
        if deviation > self.margin and self.inventory > 0:
            # Overvalued — want to sell, willing to go down to halfway toward fair value
            return HaggleIntent(
                self.agent_id, OrderSide.ASK,
                price_target=price,
                price_limit=round(price * (1 - half), 2),
                quantity=min(self.trade_size, self.inventory),
            )
        return None
