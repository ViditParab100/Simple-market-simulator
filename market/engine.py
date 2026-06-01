from __future__ import annotations
from .order_book import OrderBook
from .models import MarketState, Trade
from agents.base import Agent
from logger.thought_logger import ThoughtLogger

_CONTAGION_DUMP_THRESHOLD = 10   # units sold by one agent in one tick to trigger contagion
_CONTAGION_PULSE_STRENGTH = 0.20 # delta added to Panic activation score for all NPCs


class SimulationEngine:
    def __init__(
        self,
        agents: list[Agent],
        logger: ThoughtLogger,
        initial_price_history: list[float] | None = None,
    ):
        self.agents       = agents
        self.order_book   = OrderBook()
        self.logger       = logger
        self.tick         = 0
        self.price_history: list[float] = list(initial_price_history or [])
        self._agent_map: dict[str, Agent] = {a.agent_id: a for a in agents}

        if self.price_history:
            self.order_book.last_price = self.price_history[-1]

    # ------------------------------------------------------------------

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

    def _broadcast_contagion(self, trades: list[Trade]):
        """
        If any single seller moved >= threshold units this tick, broadcast a
        contagion pulse to all HybridNPCs so their Panic signal spikes next tick.
        """
        # Lazy import to avoid circular dependency
        from agents.hybrid.npc import HybridNPC

        sold_by: dict[str, int] = {}
        for t in trades:
            sold_by[t.seller_id] = sold_by.get(t.seller_id, 0) + t.quantity

        if not any(v >= _CONTAGION_DUMP_THRESHOLD for v in sold_by.values()):
            return

        for agent in self.agents:
            if isinstance(agent, HybridNPC):
                agent.mood.contagion_pulse = _CONTAGION_PULSE_STRENGTH

    def _clear_contagion(self):
        """Reset contagion pulses at the start of each tick."""
        from agents.hybrid.npc import HybridNPC
        for agent in self.agents:
            if isinstance(agent, HybridNPC):
                agent.mood.contagion_pulse = 0.0

    # ------------------------------------------------------------------

    def run(self, ticks: int):
        self.logger.log_header(len(self.agents), ticks)

        for _ in range(ticks):
            self.tick += 1

            # Snapshot end-of-last-tick state for agents to read
            state = self._build_market_state()

            # Fresh order book; clear last tick's contagion pulses
            self.order_book.clear()
            self._clear_contagion()

            self.logger.log_tick_start(self.tick)

            # Each agent thinks then submits orders
            for agent in self.agents:
                thoughts = agent.think(state)
                orders   = agent.act(state)
                self.logger.log_thought(self.tick, agent.agent_id, thoughts, orders)
                for order in orders:
                    self.order_book.add_order(order)

            # Match, settle, contagion check
            trades = self.order_book.match(self.tick)
            self._settle(trades)
            self._broadcast_contagion(trades)

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
