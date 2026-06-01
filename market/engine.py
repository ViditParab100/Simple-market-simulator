from __future__ import annotations
from .order_book import OrderBook
from .models import MarketState, Trade
from .haggle import HaggleCoordinator
from .events import EventBus, trade_event, tick_summary_event
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
        event_bus: EventBus | None = None,
    ):
        self.agents             = agents
        self.order_book         = OrderBook()
        self.logger             = logger
        self.haggle_coordinator = haggle_coordinator
        self.event_bus          = event_bus
        self.tick               = 0
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

    def _settle(self, trades: list[Trade], haggle: bool = False):
        for trade in trades:
            if trade.buyer_id in self._agent_map:
                self._agent_map[trade.buyer_id].on_trade(trade)
            if trade.seller_id in self._agent_map:
                self._agent_map[trade.seller_id].on_trade(trade)
            if self.event_bus:
                buyer = self._agent_map.get(trade.buyer_id)
                self.event_bus.publish(trade_event(
                    trade,
                    buyer_inventory=buyer.inventory if buyer else 0,
                    buyer_cash=buyer.cash if buyer else 0.0,
                    tick=self.tick,
                    haggle=haggle,
                ))

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
            tick_trades: list[Trade] = []

            self.logger.log_tick_start(self.tick)

            # ── Phase 1: Bilateral haggling ─────────────────────────────
            if self.haggle_coordinator:
                haggle_results = self.haggle_coordinator.run(
                    self.agents, state, self.tick
                )
                for trade, log in haggle_results:
                    self.logger.log_haggle_session(log)
                    self._settle([trade], haggle=True)
                    self.price_history.append(trade.price)
                    self.order_book.last_price = trade.price
                    self.logger.log_trade(trade)
                    tick_trades.append(trade)

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
            self._settle(trades, haggle=False)
            self._broadcast_contagion(trades)
            tick_trades.extend(trades)

            if trades:
                self.price_history.append(trades[-1].price)
                for trade in trades:
                    self.logger.log_trade(trade)

            # ── Tick summary + event ─────────────────────────────────────
            self.logger.log_tick_summary(
                self.tick,
                self.order_book.last_price,
                self.order_book.best_bid(),
                self.order_book.best_ask(),
                len(tick_trades),
            )

            if self.event_bus:
                self.event_bus.publish(tick_summary_event(
                    tick=self.tick,
                    last_price=self.order_book.last_price,
                    bid_depth=self.order_book.bid_depth(),
                    ask_depth=self.order_book.ask_depth(),
                    trades_this_tick=len(tick_trades),
                ))

        self.logger.log_final_state(self.agents, self.order_book.last_price)
