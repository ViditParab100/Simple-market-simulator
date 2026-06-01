from __future__ import annotations
from abc import ABC, abstractmethod
from market.models import Order, Trade, MarketState
from market.haggle import HaggleIntent


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
        if trade.buyer_id == self.agent_id:
            self.trade_count += 1
            self.inventory += trade.quantity
            self.cash -= trade.price * trade.quantity
        elif trade.seller_id == self.agent_id:
            self.trade_count += 1
            self.inventory -= trade.quantity
            self.cash += trade.price * trade.quantity

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        """
        Return a pre-tick negotiation intent, or None to skip haggling.
        Override in each subclass to express archetype-specific thresholds.
        """
        return None

    def net_worth(self, market_price: float) -> float:
        return self.cash + self.inventory * market_price
