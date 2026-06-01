from __future__ import annotations
from abc import ABC, abstractmethod
from market.models import Order, Trade, MarketState


class Agent(ABC):
    def __init__(self, agent_id: str, inventory: int, cash: float):
        self.agent_id = agent_id
        self.inventory = inventory
        self.cash = cash
        self.trade_count = 0

    @abstractmethod
    def think(self, state: MarketState) -> list[str]:
        """Return lines of internal reasoning. Runs before act() each tick."""
        ...

    @abstractmethod
    def act(self, state: MarketState) -> list[Order]:
        """Return orders to submit this tick."""
        ...

    def on_trade(self, trade: Trade):
        self.trade_count += 1
        if trade.buyer_id == self.agent_id:
            self.inventory += trade.quantity
            self.cash -= trade.price * trade.quantity
        elif trade.seller_id == self.agent_id:
            self.inventory -= trade.quantity
            self.cash += trade.price * trade.quantity

    def net_worth(self, market_price: float) -> float:
        return self.cash + self.inventory * market_price
