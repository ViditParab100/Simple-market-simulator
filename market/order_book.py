from __future__ import annotations
from typing import Optional
from .models import Order, OrderSide, Trade


class OrderBook:
    def __init__(self):
        self.bids: list[Order] = []
        self.asks: list[Order] = []
        self.last_price: Optional[float] = None

    def add_order(self, order: Order):
        if order.side == OrderSide.BID:
            self.bids.append(order)
        else:
            self.asks.append(order)

    def match(self, tick: int) -> list[Trade]:
        """Price-time priority matching. Trade price = midpoint of matched bid/ask."""
        self.bids.sort(key=lambda o: o.price, reverse=True)
        self.asks.sort(key=lambda o: o.price)

        trades: list[Trade] = []
        bi, ai = 0, 0

        while bi < len(self.bids) and ai < len(self.asks):
            bid = self.bids[bi]
            ask = self.asks[ai]

            if bid.price < ask.price:
                break

            # Prevent self-trading
            if bid.agent_id == ask.agent_id:
                ai += 1
                continue

            qty = min(bid.quantity, ask.quantity)
            price = round((bid.price + ask.price) / 2, 2)

            trades.append(Trade(
                buyer_id=bid.agent_id,
                seller_id=ask.agent_id,
                price=price,
                quantity=qty,
                tick=tick,
            ))
            self.last_price = price

            bid.quantity -= qty
            ask.quantity -= qty

            if bid.quantity == 0:
                bi += 1
            if ask.quantity == 0:
                ai += 1

        return trades

    def best_bid(self) -> Optional[float]:
        return max((o.price for o in self.bids), default=None)

    def best_ask(self) -> Optional[float]:
        return min((o.price for o in self.asks), default=None)

    def bid_depth(self) -> int:
        return sum(o.quantity for o in self.bids)

    def ask_depth(self) -> int:
        return sum(o.quantity for o in self.asks)

    def clear(self):
        self.bids = []
        self.asks = []
