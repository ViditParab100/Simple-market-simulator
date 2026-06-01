from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    BID = "BID"
    ASK = "ASK"


@dataclass
class Order:
    agent_id: str
    side: OrderSide
    price: float
    quantity: int
    tick: int


@dataclass
class Trade:
    buyer_id: str
    seller_id: str
    price: float
    quantity: int
    tick: int


@dataclass
class MarketState:
    tick: int
    last_price: Optional[float]
    best_bid: Optional[float]
    best_ask: Optional[float]
    bid_depth: int
    ask_depth: int
    price_history: list[float] = field(default_factory=list)

    @property
    def scarcity_index(self) -> float:
        """0.0 = all supply, 1.0 = all demand (low = abundant, high = scarce)."""
        total = self.bid_depth + self.ask_depth
        if total == 0:
            return 0.5
        return self.bid_depth / total

    @property
    def price_momentum(self) -> float:
        """Percentage change over the last 5 ticks. Positive = rising."""
        if len(self.price_history) < 2:
            return 0.0
        window = self.price_history[-5:]
        return (window[-1] - window[0]) / window[0]
