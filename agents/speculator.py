from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class SpeculatorAgent(Agent):
    """
    Momentum follower. Buys aggressively in uptrends, dumps in downtrends.
    Pays a price premium to get filled fast. Amplifies bubbles and crashes.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        momentum_threshold: float = 0.02,
        max_position: int = 30,
        aggressiveness: float = 0.02,
    ):
        super().__init__(agent_id, inventory, cash)
        self.momentum_threshold = momentum_threshold
        self.max_position = max_position
        self.aggressiveness = aggressiveness
        self._pending_orders: list[Order] = []

    def think(self, state: MarketState) -> list[str]:
        price = state.last_price or _DEFAULT_PRICE
        momentum = state.price_momentum

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"Momentum: {momentum:+.1%} (last 5 ticks)  |  Threshold: +/-{self.momentum_threshold:.1%}",
        ]
        orders: list[Order] = []

        if len(state.price_history) < 2:
            thoughts.append("Not enough history to read momentum. Holding.")
            self._pending_orders = []
            return thoughts

        if momentum > self.momentum_threshold:
            room = self.max_position - self.inventory
            if room <= 0:
                thoughts.append(f"UPTREND (+{momentum:.1%}) but at max position ({self.inventory}/{self.max_position}). Holding.")
            elif self.cash <= 0:
                thoughts.append("UPTREND detected but out of cash. Holding.")
            else:
                qty = max(1, min(room, int(room * momentum * 10)))
                bid_price = round(price * (1 + self.aggressiveness), 2)
                thoughts.append(f"UPTREND detected ({momentum:+.1%}) -- riding the wave LONG.")
                thoughts.append(f"Position: {self.inventory}/{self.max_position}  |  Buying {qty} units.")
                thoughts.append(f"Decision: BID {qty} @ ${bid_price:.2f} (paying {self.aggressiveness:.0%} premium to get filled fast)")
                if self.cash >= bid_price * qty:
                    orders.append(Order(self.agent_id, OrderSide.BID, bid_price, qty, state.tick))

        elif momentum < -self.momentum_threshold:
            if self.inventory <= 0:
                thoughts.append(f"DOWNTREND ({momentum:.1%}) but no inventory to sell. Holding.")
            else:
                qty = max(1, min(self.inventory, int(self.inventory * abs(momentum) * 10)))
                ask_price = round(price * (1 - self.aggressiveness), 2)
                thoughts.append(f"DOWNTREND detected ({momentum:.1%}) -- cutting position.")
                thoughts.append(f"Position: {self.inventory} units  |  Selling {qty} units.")
                thoughts.append(f"Decision: ASK {qty} @ ${ask_price:.2f} (taking {self.aggressiveness:.0%} discount to exit fast)")
                orders.append(Order(self.agent_id, OrderSide.ASK, ask_price, qty, state.tick))

        else:
            thoughts.append(f"Momentum flat ({momentum:+.1%}). No signal. Holding.")

        self._pending_orders = orders
        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        if len(state.price_history) < 2:
            return None
        price    = state.last_price or _DEFAULT_PRICE
        momentum = state.price_momentum
        if momentum > self.momentum_threshold and self.inventory < self.max_position:
            room = self.max_position - self.inventory
            return HaggleIntent(
                self.agent_id, OrderSide.BID,
                price_target=price,
                price_limit=round(price * (1 + self.aggressiveness * 2), 2),
                quantity=min(5, room),
            )
        if momentum < -self.momentum_threshold and self.inventory > 0:
            return HaggleIntent(
                self.agent_id, OrderSide.ASK,
                price_target=price,
                price_limit=round(price * (1 - self.aggressiveness * 2), 2),
                quantity=min(5, self.inventory),
            )
        return None
