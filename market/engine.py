from __future__ import annotations
from .order_book import OrderBook
from .models import MarketState, Trade
from .haggle import HaggleCoordinator
from agents.base import Agent
from logger.thought_logger import ThoughtLogger

_CONTAGION_DUMP_THRESHOLD = 10
_CONTAGION_PULSE_STRENGTH = 0.20


class SimulationEngine:
    def __init__(
        self,
        agents: list[Agent],
        logger: ThoughtLogger,
        initial_price_history: list[float] | None = None,
        haggle_coordinator: HaggleCoordinator | None = None,
    ):
        self.agents              = agents
        self.order_book          = OrderBook()
        self.logger              = logger
        self.haggle_coordinator  = haggle_coordinator
        self.tick                = 0
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

    def _settle_one(self, trade: Trade):
        self._settle([trade])

    def _broadcast_contagion(self, trades: list[Trade]):
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
        from agents.hybrid.npc import HybridNPC
        for agent in self.agents:
            if isinstance(agent, HybridNPC):
                agent.mood.contagion_pulse = 0.0

    # ------------------------------------------------------------------

    def run(self, ticks: int):
        self.logger.log_header(len(self.agents), ticks)

        for _ in range(ticks):
            self.tick += 1

            state = self._build_market_state()
            self.order_book.clear()
            self._clear_contagion()

            self.logger.log_tick_start(self.tick)

            # ── Phase 1: Pre-market bilateral haggling ──────────────────
            if self.haggle_coordinator:
                haggle_results = self.haggle_coordinator.run(
                    self.agents, state, self.tick
                )
                for trade, log in haggle_results:
                    self.logger.log_haggle_session(log)
                    self._settle_one(trade)
                    self.price_history.append(trade.price)
                    self.order_book.last_price = trade.price
                    self.logger.log_trade(trade)

                # Rebuild state so agents see post-haggle inventory/price
                if haggle_results:
                    state = self._build_market_state()

            # ── Phase 2: Regular order-book market ──────────────────────
            for agent in self.agents:
                thoughts = agent.think(state)
                orders   = agent.act(state)
                self.logger.log_thought(self.tick, agent.agent_id, thoughts, orders)
                for order in orders:
                    self.order_book.add_order(order)

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
