from __future__ import annotations
from .base import Agent
from market.models import Order, OrderSide, MarketState
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class PanicAgent(Agent):
    """
    Calm under normal conditions but triggers a full inventory dump when price
    drops past the panic threshold. Creates sell cascades. Enters a recovery
    period after dumping before it will consider trading again.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        panic_threshold: float = -0.10,
        dump_discount: float = 0.90,
        recovery_ticks: int = 3,
    ):
        super().__init__(agent_id, inventory, cash)
        self.panic_threshold = panic_threshold
        self.dump_discount = dump_discount
        self.recovery_ticks = recovery_ticks
        self._state = "calm"       # calm | recovering
        self._recovery_counter = 0
        self._pending_orders: list[Order] = []

    def think(self, state: MarketState) -> list[str]:
        price = state.last_price or _DEFAULT_PRICE
        momentum = state.price_momentum

        thoughts = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"Price change (5 ticks): {momentum:+.1%}  |  Panic threshold: {self.panic_threshold:.0%}",
            f"State: {self._state.upper()}",
        ]
        orders: list[Order] = []

        if self._state == "recovering":
            self._recovery_counter -= 1
            thoughts.append(f"Recovering... {self._recovery_counter} tick(s) until calm returns. Holding.")
            if self._recovery_counter <= 0:
                self._state = "calm"
                thoughts.append("Recovery complete. Returning to calm state.")

        elif self._state == "calm":
            if momentum <= self.panic_threshold:
                thoughts.append(
                    f"!! PANIC THRESHOLD BREACHED ({momentum:+.1%} <= {self.panic_threshold:.0%}) !!"
                )
                self._state = "recovering"
                self._recovery_counter = self.recovery_ticks

                if self.inventory > 0:
                    dump_price = round(price * self.dump_discount, 2)
                    thoughts.append(
                        f"DUMPING entire position: {self.inventory} units @ ${dump_price:.2f} "
                        f"({int(self.dump_discount * 100)}% of market). Getting OUT."
                    )
                    thoughts.append("Loss is acceptable. Holding further is psychologically impossible.")
                    orders.append(Order(self.agent_id, OrderSide.ASK, dump_price, self.inventory, state.tick))
                else:
                    thoughts.append("Wanted to panic sell but inventory already empty.")
            else:
                thoughts.append("No panic signal. Market is stable. Holding.")

        self._pending_orders = orders
        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def trade_remark(self, role: str, price: float, qty: int) -> str:
        if role == "buyer":
            return f"Had to grab {qty} @ ${price:.2f} — can't risk running out!"
        return f"Get me out! Dumped {qty} @ ${price:.2f}, take it, take it!"

    def auction_bid(self, lot, current_price, round_num, state):
        base = super().auction_bid(lot, current_price, round_num, state)
        if base is not None:
            return base
        if self.cash < current_price * lot.quantity:
            return None
        if self._state != "calm":
            return None  # recovering after a dump — sit out
        # Calm: participate only when low on inventory (small premium to secure supply)
        if self.inventory < 5:
            return round(lot.market_price * 1.02, 2)
        return None

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        if self._state != "calm" or self.inventory <= 0:
            return None
        if state.price_momentum <= self.panic_threshold:
            price = state.last_price or _DEFAULT_PRICE
            # Will accept down to dump_discount; tries to start at market
            return HaggleIntent(
                self.agent_id, OrderSide.ASK,
                price_target=price,
                price_limit=round(price * self.dump_discount, 2),
                quantity=self.inventory,
            )
        return None
