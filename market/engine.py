from __future__ import annotations
from .order_book import OrderBook
from .models import MarketState, Trade
from agents.base import Agent
from logger.thought_logger import ThoughtLogger


class SimulationEngine:
    def __init__(self, agents: list[Agent], logger: ThoughtLogger):
        self.agents = agents
        self.order_book = OrderBook()
        self.logger = logger
        self.tick = 0
        self.price_history: list[float] = []
        self._agent_map: dict[str, Agent] = {a.agent_id: a for a in agents}

    def _build_market_state(self) -> MarketState:
        return MarketState(
            tick=self.tick,
            last_price=self.order_book.last_price,
            best_bid=self.order_book.best_bid(),
            best_ask=self.order_book.best_ask(),
            bid_depth=self.order_book.bid_depth(),
            ask_depth=self.order_book.ask_depth(),
            price_history=self.price_history.copy(),
        )

    def _settle(self, trades: list[Trade]):
        for trade in trades:
            if trade.buyer_id in self._agent_map:
                self._agent_map[trade.buyer_id].on_trade(trade)
            if trade.seller_id in self._agent_map:
                self._agent_map[trade.seller_id].on_trade(trade)

    def run(self, ticks: int):
        self.logger.log_header(len(self.agents), ticks)

        for _ in range(ticks):
            self.tick += 1

            # Snapshot end-of-last-tick state for agents to read
            state = self._build_market_state()

            # Fresh order book each tick
            self.order_book.clear()

            self.logger.log_tick_start(self.tick)

            # Each agent thinks then submits orders
            for agent in self.agents:
                thoughts = agent.think(state)
                orders = agent.act(state)
                self.logger.log_thought(self.tick, agent.agent_id, thoughts, orders)
                for order in orders:
                    self.order_book.add_order(order)

            # Match and settle
            trades = self.order_book.match(self.tick)
            self._settle(trades)

            if trades:
                self.price_history.append(trades[-1].price)
                for trade in trades:
                    self.logger.log_trade(trade)

            self.logger.log_tick_summary(
                self.tick,
                self.order_book.last_price,
                self.order_book.best_bid(),
                self.order_book.best_ask(),
                len(trades),
            )

        self.logger.log_final_state(self.agents, self.order_book.last_price)
