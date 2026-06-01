from __future__ import annotations
import random
from .base import Agent
from market.models import Order, OrderSide, MarketState

_DEFAULT_PRICE = 20.0


class RandomAgent(Agent):
    """Baseline agent that acts randomly. Used to verify the engine loop works."""

    def __init__(self, agent_id: str, inventory: int, cash: float, seed: int | None = None):
        super().__init__(agent_id, inventory, cash)
        self.rng = random.Random(seed)

    def think(self, state: MarketState) -> list[str]:
        price = state.last_price or _DEFAULT_PRICE
        action = self._pick_action(state)
        return [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${price:.2f}",
            f"No strategy - picking randomly. Action: {action.upper()}",
        ]

    def act(self, state: MarketState) -> list[Order]:
        price = state.last_price or _DEFAULT_PRICE
        action = self._pick_action(state)

        if action == "buy" and self.cash >= price:
            bid_price = round(price * self.rng.uniform(0.95, 1.05), 2)
            qty = self.rng.randint(1, 5)
            return [Order(self.agent_id, OrderSide.BID, bid_price, qty, state.tick)]

        if action == "sell" and self.inventory > 0:
            ask_price = round(price * self.rng.uniform(0.95, 1.05), 2)
            qty = self.rng.randint(1, min(5, self.inventory))
            return [Order(self.agent_id, OrderSide.ASK, ask_price, qty, state.tick)]

        return []

    def _pick_action(self, state: MarketState) -> str:
        choices = ["hold"]
        if self.cash >= (state.last_price or _DEFAULT_PRICE):
            choices.append("buy")
        if self.inventory > 0:
            choices.append("sell")
        return self.rng.choice(choices)
